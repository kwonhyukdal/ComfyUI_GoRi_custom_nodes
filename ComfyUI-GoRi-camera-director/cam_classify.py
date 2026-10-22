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

사물 검출은 EfficientDet-Lite0(ObjectDetector)로 한다. 이 모델은 반대로
**이 폴더에 동봉**한다 — 배포본에 키퍼 폴더가 없어서 키퍼에 두면 배포본에서
사물 검출이 조용히 꺼지기 때문이다. 없으면 사물 목록만 비고 사람·픽셀 판정은
그대로 돈다. `detect_objects` 는 **사람을 내보내지 않는다** — 사람의 근거는
포즈 모델이다.
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
           "classify_references", "person_slots", "detect_objects",
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

# 동봉 사물 검출 모델 (EfficientDet-Lite0, Apache-2.0). 왜(Why) 이 폴더인가:
# 배포본에는 Comfyui-GoRi-Consistency-Keeper/ 가 없다. 포즈 모델(.task)은
# 두 노드가 항상 세트라 키퍼에서 빌려 쓰지만, 이 모델을 키퍼에 두면
# 배포본에서 사물 검출이 **조용히** 꺼진다. 고지 문서는 같은 폴더의
# OBJECT_MODEL_LICENSE.txt 이고 R183 테스트가 파일과 서로 대조한다.
_OBJECT_MODEL = "efficientdet_lite0.tflite"
_OBJECT_ENV = "GORI_OBJECT_MODEL"
_OBJECT_MAX = 5
# 임계값 0.30. 왜(Why) 0.35 에서 내렸나 (2026-10-21 라운드 2 실측 정정):
# 종전 근거는 "0.30~0.40 에서 검출 장수와 오탐이 변하지 않았다" 였는데, 그 측정에
# 결함이 둘 있었다.
#   · 배경 표본이 **합성**(단색·그라디언트·난수·체커)이라 너무 쉬웠다. 실제 크롭
#     배경에서는 A_waist 에서 potted plant 0.235 가 나온다.
#   · hit 을 "사물이 하나라도 잡히면" 으로 세어, 의자를 찾으려던 표본에서 화분이
#     잡혀도 통과시켰다. 그래서 "임계를 내려도 이득이 없다" 는 결론이 나왔다.
# 실제 크롭 배경 5장 + **가구** 기준으로 다시 재니:
#   0.35  검출 5/8  가구 2/8  배경 오탐 0/5
#   0.30  검출 5/8  가구 3/8  배경 오탐 0/5   <- 채택. 이득만 있고 비용이 없다
#   0.25  같은 수치 (0.25~0.30 구간에 후보가 없다)
#   0.20  가구 3/8  배경 오탐 1/5 (A_waist) — 더 낮추면 오탐이 늘기 시작한다
# 0.25 와 0.30 중 0.30 을 고른 마지막 한 걸음은 **측정이 아니라 판단**이다 —
# "이 표본에서 수치가 같다면 더 높은 쪽이 안전하다(아래로 열어 둘 이유가 없다)".
# 측정이 갈리면(0.25 가 더 잡으면) 그때 다시 재서 정한다.
# 살아난 것은 W_chair_compare 의 chair 0.335 다. 0.35 는 **맞힌 의자를 버리고
# 있었다** — 미달의 일부는 모델이 아니라 우리 상수가 만든 것이었다.
# 미검출 3장(T_gen_chair·AB_gen_chair·AC_oncut)은 임계로 풀리지 않는다. 원시
# 후보 전량(임계 0.05, 원본 해상도)에 chair 가 **아예 없다** — 모델 한계다.
_OBJECT_MIN_SCORE = 0.30
# 사용자에게 내보내지 않는 이름 둘.
#   person  사람의 권위 있는 근거는 포즈 모델이다. ObjectDetector 는 합성
#           회색 사각형에서도 person 0.64 를 냈다(실측) — 두 근거가 어긋나면
#           로그가 사용자에게 모순을 보여준다.
#   ???     모델 라벨 90슬롯 중 자리표시(실측: labels.txt 11번째). 이름이
#           아니므로 그대로 내보내면 쓰레기 값이 된다.
_OBJECT_SKIP = ("person", "???")

_LOCK = threading.Lock()
_LANDMARKER = None
_LOAD_TRIED = False
_LOAD_NOTE = ""
_CACHE: dict = {}
_CACHE_MAX = 64
_OBJECT_DETECTOR = None
_OBJECT_TRIED = False
_OBJECT_NOTE = ""


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


def _u8_rgb(image):
    """이미지 → uint8 (H,W,3), 긴 변 _MAX_SIDE 이하. 실패 시 None.

    왜(Why) 보간 없이 솎나(`a[::step, ::step]`): 포즈 랜드마크와 테두리·피부
    판정이 이 배열을 함께 쓰고 그 임계값들이 이 크기에서 실측으로 정해졌다.
    여기서 보간을 넣으면 세 경로가 한꺼번에 움직인다.

    검출만 손해를 보는가 — 아니다(2026-10-21 라운드 2 실측): 같은 8장에
    솎기 / INTER_AREA / 원본 해상도를 넣고 비교했더니 검출 5/8·가구 3/8 로
    **셋 다 동일**했다(점수만 0.48 대 0.55). 그래서 여기서는 건드리지 않는다 —
    다음 사람이 같은 실험을 다시 하지 않도록 이 문장을 남긴다.
    """
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


def _object_model_path() -> str:
    """사물 검출 모델 경로. 없으면 "".

    순서: 환경변수 > 이 폴더. 호출 때마다 읽는다 — 사용자가 노드를 띄운 뒤
    파일을 넣거나 빼는 경우가 있고, 그때 재시작을 요구할 이유가 없다.
    """
    here = os.path.dirname(os.path.realpath(__file__))
    for p in ((os.environ.get(_OBJECT_ENV) or "").strip(),
              os.path.join(here, _OBJECT_MODEL)):
        if p and os.path.isfile(p):
            return p
    return ""


def _object_detector():
    """ObjectDetector 1회 생성 후 재사용. 실패하면 None (한 번만 로그).

    잠금 규칙: `_LOCK` 은 **재진입이 안 된다**. 그래서 이 함수는 잠금을
    잡고 놓은 뒤 검출기를 돌려주고, 추론은 `detect_objects` 가 따로 잠근다.
    여기서 잡은 채로 detect() 를 부르면 교착이다.
    """
    global _OBJECT_DETECTOR, _OBJECT_TRIED, _OBJECT_NOTE
    if _OBJECT_TRIED:
        return _OBJECT_DETECTOR
    with _LOCK:
        if _OBJECT_TRIED:
            return _OBJECT_DETECTOR
        _OBJECT_TRIED = True
        path = _object_model_path()
        if not path:
            _OBJECT_NOTE = ("사물 검출 모델이 없어 참조 사물 검출을 끕니다 "
                            "(%s 또는 이 폴더의 %s)"
                            % (_OBJECT_ENV, _OBJECT_MODEL))
            _note_once("classify_obj_no_model",
                       "[Camera Director] " + _OBJECT_NOTE)
            return None
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            opts = vision.ObjectDetectorOptions(
                base_options=mp_python.BaseOptions(model_asset_path=path),
                running_mode=vision.RunningMode.IMAGE,
                max_results=_OBJECT_MAX,
                score_threshold=_OBJECT_MIN_SCORE)
            _OBJECT_DETECTOR = vision.ObjectDetector.create_from_options(opts)
            _note_once("classify_obj_on",
                       "[Camera Director] 참조 사물 검출 사용 (모델: %s)"
                       % os.path.basename(path))
        except Exception as e:  # noqa: BLE001
            _OBJECT_NOTE = ("참조 사물 검출을 켤 수 없습니다 (%s)"
                            % type(e).__name__)
            _note_once("classify_obj_fail", "[Camera Director] " + _OBJECT_NOTE)
            _OBJECT_DETECTOR = None
        return _OBJECT_DETECTOR


def detect_objects(image) -> list:
    """이미지 1장 → [{"name", "score", "bbox"}]. 사람과 자리표시는 뺀다.

    계약: `name` 은 비지 않은 str, `score` 는 0~1, `bbox` 는 (x, y, w, h) 이며
    **0~1 정규화**이고 (x, y) 가 좌상단이다. 검출기가 없거나 입력이 퇴화하면
    빈 목록 — 예외를 호출자에게 내보내지 않는다(노드가 멈추면 안 된다).

    왜(Why) 정규화하나: 모델 원본 `bounding_box` 는 **픽셀** 단위다
    (2026-10-21 실측: 359x256 입력에서 origin_x=207, width=137). 그대로
    쓰면 1 을 넘어 계약이 깨진다.
    """
    arr = _u8_rgb(image)
    if arr is None:
        return []
    return _detect_objects_arr(arr)


def _detect_objects_arr(arr) -> list:
    """uint8 (H,W,3) 배열 → 사물 목록. `detect_objects` 의 본체.

    왜(Why) 나눠 두나: `classify_reference` 는 이미 `_u8_rgb` 를 거친 배열을
    들고 있다. 여기서 `detect_objects` 를 부르면 변환·축소가 두 번 돈다.
    """
    det = _object_detector()
    if det is None:
        return []
    try:
        import mediapipe as mp
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=arr)
        with _LOCK:
            res = det.detect(img)
    except Exception as e:  # noqa: BLE001
        # 왜(Why) 여기서 남기나: 모델 **로드** 실패는 `_object_detector` 가 사유를
        # 남기지만 **추론** 실패는 여기서만 알 수 있다. 이 줄이 없으면 참조 분석
        # 줄은 `검출 없음` 으로만 남아, 사용자도 우리도 "사물이 없다" 와
        # "검출기가 고장났다" 를 구분할 수 없다(2026-10-21 라운드 2).
        # 왜(Why) 로드 실패와 다른 키인가: 둘은 다른 원인이고 `_note_once` 는 키당
        # 한 번이라, 한 키를 나눠 쓰면 먼저 온 쪽이 나중 것을 가린다.
        _note_once("classify_obj_detect_err",
                   "[Camera Director] 참조 사물 검출 추론 중 오류 (%s)"
                   % type(e).__name__)
        return []
    h, w = int(arr.shape[0]), int(arr.shape[1])
    out = []
    for d in (res.detections or []):
        try:
            cat = d.categories[0]
            name = str(cat.category_name or "").strip()
            score = float(cat.score)
        except Exception:  # noqa: BLE001
            continue
        # NaN 은 어떤 비교에도 False 다 — `not score >= x` 로 걸러진다.
        if not name or name in _OBJECT_SKIP or not score >= _OBJECT_MIN_SCORE:
            continue
        try:
            bb = d.bounding_box
            x = max(0.0, min(1.0, float(bb.origin_x) / w))
            y = max(0.0, min(1.0, float(bb.origin_y) / h))
            bw = max(0.0, min(1.0 - x, float(bb.width) / w))
            bh = max(0.0, min(1.0 - y, float(bb.height) / h))
        except Exception:  # noqa: BLE001
            continue
        out.append({"name": name, "score": round(score, 3),
                    "bbox": (round(x, 4), round(y, 4),
                             round(bw, 4), round(bh, 4))})
    out.sort(key=lambda o: -o["score"])
    return out[:_OBJECT_MAX]


def _objs_copy(objs) -> list:
    """사물 목록의 얕은 깊이 복사 (dict 까지 새로 만든다).

    왜(Why) 복사하나: 캐시는 이 목록을 **공유**한다. 소비자가 원소 dict 를
    고치면 캐시가 오염되어 다음 호출이 틀린 값을 받는다 — 이 저장소가 이미
    `id()` 캐시로 겪은 부류다(R136). 항목이 5개 이하라 비용은 무시할 수 있다.
    """
    return [dict(o) for o in (objs or [])]


def _classify_objects_safe(arr) -> list:
    """사물 검출을 **부가 정보**로 얻는다. 실패해도 kind 판정을 깨지 않는다.

    왜(Why) 감싸나: 사람·아이템 판정이 주 기능이고 사물 목록은 덧붙는 정보다.
    검출 경로의 예상 밖 예외가 주 기능을 죽이면 사용자는 참조 분류 자체를
    잃는다. 대신 조용히 넘기지 않고 사유를 한 번 남긴다.
    """
    try:
        return _detect_objects_arr(arr)
    except Exception as e:  # noqa: BLE001
        _note_once("classify_obj_err",
                   "[Camera Director] 참조 사물 검출 중 오류 (%s)"
                   % type(e).__name__)
        return []


def classify_reference(image) -> dict:
    """이미지 1장 → {"kind", "poses", "bbox", "objects"}.

    kind 는 person / item / unknown 셋이다.
    - person  포즈 랜드마크 + 몸 크기 게이트
    - item    사람이 없고, 단색 배경 위에 물건 하나 (옷·제품·스튜디오 가구)
    - unknown 나머지 (배경·실내 사진 등)

    옷과 사물을 픽셀로 가르는 것은 실측에서 불가능했다(테두리 균일도 1.0 대 1.0).
    그래서 '아이템'까지만 단정하고, 입을지 놓을지는 프롬프트가 조건문으로 맡긴다.

    objects 는 `detect_objects` 의 목록이다 (사람·자리표시 제외, 0~1 정규화 bbox).
    캐시에 함께 실려 같은 이미지를 다시 넣으면 추론을 반복하지 않는다.
    """
    arr = _u8_rgb(image)
    if arr is None:
        return {"kind": KIND_UNKNOWN, "poses": 0, "bbox": (0.0, 0.0),
                "objects": []}
    key = _sig(arr)
    hit = _CACHE.get(key)
    if hit is not None:
        got = dict(hit)
        got["objects"] = _objs_copy(got.get("objects"))
        return got
    n, w, h = _probe(arr)
    objs = _classify_objects_safe(arr)
    is_person = n > 0 and w >= _MIN_BBOX_W and h >= _MIN_BBOX_H
    if is_person:
        out = {"kind": KIND_PERSON, "poses": n,
               "bbox": (round(w, 3), round(h, 3)), "objects": objs}
    else:
        bdom = _border_dominance(arr)
        skin = _skin_ratio(arr)
        out = {"kind": KIND_ITEM if (bdom >= _ITEM_MIN_BORDER_DOM
                                     and skin <= _ITEM_MAX_SKIN)
               else KIND_UNKNOWN,
               "poses": n, "bbox": (round(w, 3), round(h, 3)),
               "bdom": round(bdom, 3), "skin": round(skin, 3),
               "objects": objs}
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = dict(out)
    _CACHE[key]["objects"] = _objs_copy(objs)
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
