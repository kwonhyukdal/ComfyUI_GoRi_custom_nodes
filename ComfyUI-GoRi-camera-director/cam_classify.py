# -*- coding: utf-8 -*-
"""참조 이미지 자동 분류 — 픽셀 근거로 '사람이 있는 칸'을 찾는다.

왜(Why) 이 모듈이 필요한가 (2026-10-19 사용자 지시):
슬롯 번호는 역할이 아니다. 사용자는 1번에 인물을 넣을 수도, 옷을 넣을 수도,
사물을 넣을 수도 있다. 예전 규약은 "첫 연결 = 주 피사체"라서, 1번이 옷 사진이면
프롬프트가 그 옷을 사람 신원으로 지목했다. 토픽이 역할을 말해 주면 기존 파서가
처리하지만, 토픽이 비면 근거가 없다. 그 빈 자리를 픽셀로 채운다.

무엇을 판정하나:
    person   사람이 실제로 서 있는 칸 (포즈 랜드마크 + 몸 크기 게이트)
    unknown  사람으로 볼 근거가 없는 칸

사람 판정은 mediapipe PoseLandmarker 로 한다. 피부색 비율이나 얼굴 검출은
실측에서 오탐이 컸다 — 침대 베개가 얼굴로 잡히고, 가을 숲이 피부색 57% 로
나왔다. 포즈 랜드마크 + 바운딩박스 크기 게이트가 그 오탐을 걸러낸다
(실측: 인물 8장 전부 검출, 가구·의상·소품·배경 11장 전부 미검출,
숲 사진 1장은 검출됐지만 bbox 0.09x0.30 이라 게이트에서 탈락).

모델은 이 폴더에 없다. 키퍼 폴더의 번들 모델을 빌려 쓴다(두 노드는 세트).
없으면 분류를 끄고 기존 동작(첫 연결 = 주 피사체)으로 돌아간다 — 조용히
실패하지 않고 한 번 로그를 남긴다.
"""

from __future__ import annotations

import os
import threading

try:
    from .cam_util import *  # noqa: F403
    from .cam_sheet import _np_as_rgb
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
    from cam_sheet import _np_as_rgb


__all__ = ["KIND_PERSON", "KIND_ITEM", "KIND_UNKNOWN", "classify_reference",
           "classify_references", "person_slots", "classifier_status",
           "clear_classify_cache"]

KIND_PERSON = "person"
# 단색 배경 위에 물건 하나. 옷 사진·제품 사진·스튜디오 가구가 여기 들어온다.
# 옷인지 사물인지는 픽셀로 가를 수 없어서(실측: 테두리 균일도 1.0 vs 1.0)
# '아이템'까지만 단정하고, 입을지 놓을지는 프롬프트가 조건문으로 맡긴다.
KIND_ITEM = "item"
KIND_UNKNOWN = "unknown"

# 분류 입력 크기. 포즈 모델은 256~384 입력에서 충분하고, 10장을 돌려도
# 1초 안쪽이다(실측 384px 에서 장당 약 90ms).
_MAX_SIDE = 384

# 몸 크기 게이트. 왜(Why) 크기까지 보나: 숲 사진에서 나무가 사람으로 검출됐고
# 랜드마크 신뢰도는 0.64 로 진짜 인물(0.52~0.89)과 겹쳤다. 갈린 것은 크기였다 —
# 오탐 bbox 0.09x0.30, 진짜 인물 0.29~0.65 x 0.46~1.75.
_MIN_BBOX_W = 0.20
_MIN_BBOX_H = 0.35

# 아이템(단색 배경 위 물건) 판정. 실측:
#   옷 사진 0.037·0.099 / 의자 0 / 소품 0.109  -> 테두리 균일도 1.0, 1.0, 0.985
#   침대 0.259 / 벤치 0.22~0.43 / 배경 0.22~0.53 -> 균일도가 낮다
# 피부 비율 상한을 함께 두는 이유: 얼굴 클로즈업이 포즈 검출에 실패해도
# 단색 배경이면 아이템으로 오판할 수 있다. 피부가 많으면 아이템이 아니다.
_ITEM_MIN_BORDER_DOM = 0.90
_ITEM_MAX_SKIN = 0.12

_LOCK = threading.Lock()
_LANDMARKER = None
_LOAD_TRIED = False
_LOAD_NOTE = ""
_CACHE: dict = {}
_CACHE_MAX = 64


def _model_path() -> str:
    """포즈 모델 경로. 없으면 "".

    순서: 환경변수 > 이 폴더 > 키퍼 폴더(같은 팩). 두 노드는 항상 세트로
    쓰이므로 키퍼 번들 모델을 빌리는 것이 중복 배포보다 낫다.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    cands = [
        (os.environ.get("GORI_POSE_MODEL") or "").strip(),
        os.path.join(here, "pose_landmarker_lite.task"),
        os.path.join(here, os.pardir, "Comfyui-GoRi-Consistency-Keeper",
                     "pose_landmarker_lite.task"),
    ]
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return ""


def _landmarker():
    """PoseLandmarker 1회 생성 후 재사용. 실패하면 None (한 번만 로그)."""
    global _LANDMARKER, _LOAD_TRIED, _LOAD_NOTE
    with _LOCK:
        if _LOAD_TRIED:
            return _LANDMARKER
        _LOAD_TRIED = True
        path = _model_path()
        if not path:
            _LOAD_NOTE = ("포즈 모델이 없어 참조 자동 분류를 끕니다 "
                          "(GORI_POSE_MODEL 또는 키퍼 폴더의 .task)")
            _note_once("classify_no_model", "[Camera Director] " + _LOAD_NOTE)
            return None
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            opts = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=path),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=3,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5)
            _LANDMARKER = vision.PoseLandmarker.create_from_options(opts)
            _note_once("classify_on", "[Camera Director] 참조 자동 분류 사용 "
                       "(포즈 모델: %s)" % os.path.basename(path))
        except Exception as e:  # noqa: BLE001
            _LOAD_NOTE = f"참조 자동 분류를 켤 수 없습니다 ({type(e).__name__})"
            _note_once("classify_fail", "[Camera Director] " + _LOAD_NOTE)
            _LANDMARKER = None
        return _LANDMARKER


def classifier_status() -> str:
    """분류기 상태 문자열 (로그·테스트용)."""
    if not _LOAD_TRIED:
        return "unloaded"
    if _LANDMARKER is None:
        return _LOAD_NOTE or "off"
    return "on"


def _u8_rgb(image):
    """이미지 → uint8 (H,W,3), 긴 변 _MAX_SIDE 이하. 실패 시 None."""
    try:
        # CUDA 텐서를 np.asarray 하면 예외가 난다 — 먼저 CPU 로 내린다.
        if hasattr(image, "detach"):
            image = image.detach().cpu()
        a = _np_as_rgb(image)
        if a is None:
            return None
        import numpy as np
        h, w = int(a.shape[0]), int(a.shape[1])
        if h < 8 or w < 8:
            return None
        step = max(1, -(-max(h, w) // _MAX_SIDE))
        a = a[::step, ::step]
        return (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
    except Exception:  # noqa: BLE001
        return None


def _sig(arr) -> int:
    """축소 지문. 같은 이미지를 매 실행 다시 추론하지 않게 한다."""
    try:
        import numpy as np
        h, w = arr.shape[:2]
        sh, sw = max(1, h // 16), max(1, w // 16)
        small = arr[:sh * 16, :sw * 16].reshape(16, sh, 16, sw, 3).mean(axis=(1, 3))
        return hash(small.round(0).astype(np.uint8).tobytes())
    except Exception:  # noqa: BLE001
        return 0


def _probe(arr):
    """포즈 검출 → (인물 수, 가장 큰 bbox 폭, 높이). 검출 실패 시 (0, 0, 0)."""
    det = _landmarker()
    if det is None:
        return 0, 0.0, 0.0
    try:
        import mediapipe as mp
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
        with _LOCK:
            res = det.detect(img)
    except Exception:  # noqa: BLE001
        return 0, 0.0, 0.0
    poses = res.pose_landmarks or []
    best_w = best_h = 0.0
    for lm in poses:
        xs = [p.x for p in lm]
        ys = [p.y for p in lm]
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if w * h > best_w * best_h:
            best_w, best_h = float(w), float(h)
    return len(poses), best_w, best_h


def _border_dominance(arr) -> float:
    """테두리 픽셀이 한 색에 몰린 비율 (0~1). 단색 배경이면 1 에 가깝다."""
    try:
        import numpy as np
        a = arr.astype(np.float32) / 255.0
        lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
        h, w = lum.shape
        bw = max(1, min(h, w) // 20)
        border = np.concatenate([lum[:bw].ravel(), lum[-bw:].ravel(),
                                 lum[:, :bw].ravel(), lum[:, -bw:].ravel()])
        q = np.round(border * 8) / 8
        _, counts = np.unique(q, return_counts=True)
        return float(counts.max() / max(1, counts.sum()))
    except Exception:  # noqa: BLE001
        return 0.0


def _skin_ratio(arr) -> float:
    """YCbCr 피부 범위 비율. 아이템 오판(얼굴 클로즈업)을 거르는 보조 신호."""
    try:
        import numpy as np
        a = arr.astype(np.float32) / 255.0
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cb = 128 - 0.168736 * r * 255 - 0.331264 * g * 255 + 0.5 * b * 255
        cr = 128 + 0.5 * r * 255 - 0.418688 * g * 255 - 0.081312 * b * 255
        m = (cb > 77) & (cb < 127) & (cr > 133) & (cr < 173) & (y > 0.2)
        return float(m.mean())
    except Exception:  # noqa: BLE001
        return 1.0


def classify_reference(image) -> dict:
    """이미지 1장 → {"kind", "poses", "bbox"}.

    kind 는 person / item / unknown 셋이다.
    - person  포즈 랜드마크 + 몸 크기 게이트
    - item    사람이 없고, 단색 배경 위에 물건 하나 (옷·제품·스튜디오 가구)
    - unknown 나머지 (배경·실내 사진 등)

    옷과 사물을 픽셀로 가르는 것은 실측에서 불가능했다(테두리 균일도 1.0 대 1.0).
    그래서 '아이템'까지만 단정하고, 입을지 놓을지는 프롬프트가 조건문으로 맡긴다.
    """
    arr = _u8_rgb(image)
    if arr is None:
        return {"kind": KIND_UNKNOWN, "poses": 0, "bbox": (0.0, 0.0)}
    key = _sig(arr)
    hit = _CACHE.get(key)
    if hit is not None:
        return dict(hit)
    n, w, h = _probe(arr)
    is_person = n > 0 and w >= _MIN_BBOX_W and h >= _MIN_BBOX_H
    if is_person:
        out = {"kind": KIND_PERSON, "poses": n,
               "bbox": (round(w, 3), round(h, 3))}
    else:
        bdom = _border_dominance(arr)
        skin = _skin_ratio(arr)
        out = {"kind": KIND_ITEM if (bdom >= _ITEM_MIN_BORDER_DOM
                                     and skin <= _ITEM_MAX_SKIN)
               else KIND_UNKNOWN,
               "poses": n, "bbox": (round(w, 3), round(h, 3)),
               "bdom": round(bdom, 3), "skin": round(skin, 3)}
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = dict(out)
    return out


def classify_references(image_items) -> dict:
    """[(label, image)] → {label: kind}. 실패한 칸은 unknown."""
    out = {}
    for pair in image_items or []:
        try:
            label, img = pair
            n = int(str(label))
        except (TypeError, ValueError):
            continue
        try:
            out[n] = classify_reference(img)["kind"]
        except Exception:  # noqa: BLE001
            out[n] = KIND_UNKNOWN
    return out


def person_slots(kinds) -> list:
    """{label: kind} → 사람이 있는 슬롯 번호(오름차순)."""
    return sorted(int(k) for k, v in (kinds or {}).items()
                  if v == KIND_PERSON)


def clear_classify_cache() -> None:
    """캐시 비우기 (테스트·메모리 해제용)."""
    _CACHE.clear()
