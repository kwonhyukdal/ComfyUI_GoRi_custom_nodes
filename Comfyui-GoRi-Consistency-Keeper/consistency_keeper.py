# -*- coding: utf-8 -*-
"""(GoRi) Consistency Keeper — 2차 패스 일관성 당김 노드.

샘플러가 뽑은 latent를 원본·카메라 기준 latent 쪽으로 당겨
신원·구도의 틀어짐을 줄인다. 기본 경로는 다시 그리지 않으므로(재인코딩·
재샘플링 없음) 파손된 손가락 같은 것은 고치지 못한다 — 그건 디테일러
영역이다. repair_enable 을 켜면 예외가 아닌 확장이 된다 (2026-10-05):
판정기(anatomy_standard 규격 + mediapipe)가 파손 부위를 찾고, 그 좌표를
스탠다드 규격으로 교정해 그린 골격 이미지를 VAE 로 인코딩한 뒤 그
latent 쪽으로 파손 부위만 당긴다. 재샘플링은 하지 않는다 — 당김의
DNA("다시 그리지 않는다")를 지키고, 나중에 픽셀 데이터만 주입해
성능을 올릴 수 있는 슬롯 구조다.

체결 (GoRi DNA):
  corrected = sampled + a*(camera - sampled) + b*(original - sampled)
  - a (strength_camera): 연출 방향 당김
  - b (strength_original): 원본 신원 당김
  - strength_sampler(s) 는 이 당김 전체에 배율을 곱한다:
    corrected = sampled + s * (a*(camera - sampled) + b*(original - sampled)
                               + 부위별 보강)
크기가 다르면 bicubic 리사이즈로 맞춘다. 배치·채널이 다르면 해당 기준은
건너뛴다(로그 후 계속). 필수 의존성은 torch·numpy 뿐 — mediapipe 는
선택 의존(없으면 포즈 기반 기능만 꺼진다).
"""

from __future__ import annotations

# 이 노드의 독립 버전. 팩(pyproject.toml) 버전과 별개로 간다.
# 왜(Why) future import 다음인가: `from __future__` 는 docstring 바로 다음에
# 와야 한다 (SyntaxError). 버전 상수는 그 뒤 첫 코드다.
# 왜(Why) 노드마다 따로인가 (2026-10-02): 팩은 여러 노드를 한 번에 배포하는
# 관리 단위일 뿐이다. 키퍼만 고쳤는데 팩 버전을 올리면 카메라도 바뀐 것처럼
# 보인다. 각 노드는 자기 변경에만 버전을 올린다. 새 노드를 만들면 첫날부터
# __version__ 을 둔다 (test_pack.py 가 강제한다).
__version__ = "1.9.20"

# 해부학 스탠다드 규격 (2026-10-05). 판정기의 "정상 목표" 데이터다.
# 왜(Why) 상대→절대 폴백인가: ComfyUI 는 이 폴더를 패키지로 임포트하고,
# run_tests.bat 는 폴더 안에서 단독 실행한다. __init__.py 와 같은 짝이다.
try:
    from .anatomy_standard import (
        SPEC_VERSION as _ANATOMY_SPEC_VERSION,
        check_body_physics as _check_body_physics,
        summarize_checks as _summarize_checks,
        correct_order_violations as _correct_order_violations,
    )
except ImportError:
    from anatomy_standard import (
        SPEC_VERSION as _ANATOMY_SPEC_VERSION,
        check_body_physics as _check_body_physics,
        summarize_checks as _summarize_checks,
        correct_order_violations as _correct_order_violations,
    )

try:
    from .anatomy_parts import (
        PART_CATALOG as _PART_CATALOG,
        read_parts as _read_parts,
        finger_report as _finger_report,
        toe_blobs as _toe_blobs,
        summarize_parts as _summarize_parts,
        foot_comps as _foot_comps,
        unclaimed_feet as _unclaimed_feet,
    )
except ImportError:
    from anatomy_parts import (
        PART_CATALOG as _PART_CATALOG,
        read_parts as _read_parts,
        finger_report as _finger_report,
        toe_blobs as _toe_blobs,
        summarize_parts as _summarize_parts,
        foot_comps as _foot_comps,
        unclaimed_feet as _unclaimed_feet,
    )


import importlib as _importlib

# ---------------------------------------------------------------------------
# 기능별 분리 모듈 (2026-10-07 refactor)
#   kp_math  순수 수치/이미지 유틸 / kp_vae VAE 인코딩/디코딩·축소비율 학습
#   kp_sheet 캐릭터 시트 탐지 / kp_judge 판정층
# 아래 * import 는 이 파일의 공개 표면을 그대로 유지한다 (테스트는
# consistency_keeper.<이름> 에 접근하는 계약).
# ---------------------------------------------------------------------------
try:
    from .kp_math import *  # noqa: F403
    from .kp_vae import *  # noqa: F403
    from .kp_sheet import *  # noqa: F403
    from .kp_judge import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from kp_math import *  # noqa: F403
    from kp_vae import *  # noqa: F403
    from kp_sheet import *  # noqa: F403
    from kp_judge import *  # noqa: F403
# __version__ 은 파일 머리 상수에 있다 — 여기서 다시 할당하면 갱신 시
# 한쪽만 바뀌는 이중 관리가 생긴다 (2026-10-07 감사로 중복 할당 제거).


def _decode_latent_rgb(vae, latent, cache=None):
    """latent -> RGB numpy 배열(H,W,3). 실행당 캐시로 중복 디코딩을 없앤다.

    왜(Why) 캐시가 필요한가(2026-09-28 실측): 한 실행에서 `sampled` 를
    **전 해상도로 두 번** 디코딩했다(인체 마스크용 + 부위맵용). 128x128
    latent 기준 1024x1024 이미지 2회 — VAE 디코딩이 이 노드에서 가장 비싼
    연산인데 같은 결과를 두 번 만들고 있었다. `original` 도 마찬가지.
    캐시 키는 **내용 해시**다 — `id()` 였을 때 60회 중 56회가 엉뚱한 픽셀을
    반환했다(2026-10-03 실측, 주석은 `_latent_cache_key` 참조).
    """
    try:
        if vae is None or latent is None:
            return None
        import torch as _t
        import numpy as _np
        # 키를 못 만들면(None) 캐시를 아예 쓰지 않는다. 틀린 키로 엉뚱한
        # 픽셀을 주는 것보다 디코딩을 한 번 더 하는 것이 나쁘지 않다.
        # cache 가 없으면 키를 계산하지도 않는다 — 0.36ms 와 device->host
        # 전송을 공짜로 아낀다 (2026-10-04 감사 5차).
        key = _latent_cache_key(latent) if cache is not None else None
        if key is not None and cache is not None and key in cache:
            return cache[key]
        with _t.no_grad():
            img = _decode_capped(vae, latent)
        if hasattr(img, "detach"):
            img = img.detach().cpu()
        arr = img.numpy() if hasattr(img, "numpy") else _np.asarray(img)
        arr = _np.asarray(arr, dtype=_np.float32)
        arr = _as_rgb_hwc(arr)
        if arr is None:
            return None
        # 상한 때문에 포즈를 놓쳤으면 한 번만 크게 다시 디코드한다 (2026-10-01 실측).
        # 74MP 캐릭터 시트를 1MP 로 줄이면 패널 안 사람이 너무 작아 33점을 못 찾는데,
        # 6MP 로 올리면 다른 시트가 실패한다 — 상한값에 단조가 없어 숫자로 못 잡는다.
        # 그래서 '보통은 싼 값, 못 잡았을 때만 큰 값' 으로 판정을 직접 지킨다.
        try:
            _lh = int(latent.shape[-2])
            _lw = int(latent.shape[-1])
            # 왜(Why) 하드코딩 64 가 아니라 학습 배율인가 (2026-10-04
            # 감사): 64 는 SD 계열 기준(8²)이고 Qwen 은 16²=256 이다.
            # 가드가 작으면 **재시도가 아예 걸리지 않는다** — Qwen
            # 표준 해상도(1024~2048px, latent 64²~128²) 에서는 상한
            # 디코드가 실제로 일어나도 이 가드를 통과하지 않는다
            # (128² 기준 128*128*64 = 정확히 1MP 로 `>` 가 성립하지
            # 않음). `_decode_capped` 의 상한 조건과 같은 식으로 두면
            # "재시도 대상 = 실제로 상한이 걸린 디코드" 가 된다.
            if _lh * _lw * _vae_pixel_factor_for(vae) ** 2 \
                    > _DECODE_MAX_PIXELS:
                # 왜(Why) 포즈 가용성 게이트 (2026-10-04 감사):
                # mediapipe 없이는 `_pose_landmarks_from_tasks` 가
                # 무조건 None — "검출 실패"와 "검출 자체 불가" 가 같아
                # 재시도가 항상 돌고 4MP 배열이 캐시를 오염시킨다
                # (목적을 이룰 수 없는 재시도). 나머지 포즈 호출부도
                # `_pose_landmarker() is None` 으로 먼저 막는다.
                if _pose_landmarker() is not None:
                    u8 = (_np.clip(arr, 0.0, 1.0)
                          * 255.0).astype(_np.uint8)
                    if not _pose_landmarks_from_tasks(u8):
                        _release_vram()
                        with _t.no_grad():
                            img = _decode_capped(
                                vae, latent,
                                max_pixels=_DECODE_RETRY_PIXELS)
                        if hasattr(img, "detach"):
                            img = img.detach().cpu()
                        arr2 = (img.numpy() if hasattr(img, "numpy")
                                else _np.asarray(img))
                        arr2 = _as_rgb_hwc(
                            _np.asarray(arr2, dtype=_np.float32))
                        if arr2 is not None:
                            arr = arr2
        except Exception as _e:
            _note_retry_error(_e)
        if cache is not None and key is not None:
            cache[key] = arr
        return arr
    except Exception as _oe:
        # 왜(Why) 말하고 넘어가나 (2026-10-07 감사): 이 예외는 아래 모든
        # 소비자(부위 판독·시트 분석·인체 마스크)에서 각자 조용히 None 으로
        # degrade 했다 — 원인 한 줄이면 전부 설명된다.
        _note_once("decode_latent_rgb",
                   "[GoRi Consistency Keeper] ⚠ latent 디코드 실패 "
                   "(%s: %s) — 픽셀 기반 판독을 건너뜁니다"
                   % (type(_oe).__name__, str(_oe)[:80]))
        return None


_TASKS_LANDMARKER = []


_POSE_NOTED = False


# 손 세션 캐시. 포즈와 같은 1원소 리스트 방식 (재바인딩 없이 변이로 유지).
# 왜(Why) 같은 방식인가: `_TASKS_LANDMARKER` 가 이미 검증된 패턴이다.
# `global` 없이도 동작하고, 테스트가 stub 으로 교체할 수 있다.
_TASKS_HANDMARKER = []


_TASKS_HANDCOUNT = []


_TASKS_FACEMARKER = []


_HAND_NOTED = False


# 인체 마스크 감쇠 반경 = 랜드마크 bbox 긴 변의 몇 배인가.
# 왜(Why) 0.30 인가 (2026-09-30 실측 스윕): 뼈대 중심에서 0.30x체격 거리에서
# 가중치가 0 이 된다. 실측(인물 옆차 실물 생성본) 결과 —
#   0.60: 인물 0.86 / 배경 0.57 (구분 안 됨)
#   0.30: 인물 0.75 / 배경 0.31 (3배 대비, 화면 38% 배제)  <- 채택
#   0.25: 인물 0.65 / 배경 0.16 (배경은 더 좋은데 인물 팔끝까지 잘릴 위험)
_MASK_FALLOFF = 0.30


# 감쇠 반경의 바닥/천장(정규화 좌표). landmark 가 몰리거나 사람이 화면을 꽉
# 채울 때 마스크가 한 점으로 수축하거나 배경을 삼키는 것을 막는다.
# 자세한 사유는 `_person_mask_from_rgb` 참고.
_MASK_FALLOFF_MIN = 0.15


_MASK_FALLOFF_MAX = 0.75


# 인체 마스크 이진화 임계. _MASK_FALLOFF 스윕과 같은 실측에서 같이 정했다.
_MASK_MIN_WEIGHT = 0.35


# 관절 33점 모델 파일명. 이 노드와 함께 배포된다(Apache 2.0, Google MediaPipe).
_POSE_MODEL_FILENAME = "pose_landmarker_lite.task"


# 손 21점 모델 파일명. 이 노드와 함께 배포된다(Apache 2.0, Google MediaPipe).
# 왜(Why) 손 모델이 따로 필요한가 (2026-10-02): 포즈 33점은 손가락 끝 3점
# (새끼·검지·엄지)만 준다. 손가락 개수(5개)와 분리·뭉개짐을 판정하려면
# 손마다 21점이 필요하다. 포즈 모델은 손이 3개여도 33점 틀에 맞추고 끝이라
# 여분을 셀 수 없다. 손 모델은 손마다 21점을 돌려주므로 개수를 센다.
_HAND_MODEL_FILENAME = "hand_landmarker.task"


def _pose_model_path():
    """사용할 .task 모델 경로 문자열을 돌려준다 (항상 str, None 아님).

    호출부의 `is None` 검사는 방어용이다 — 지금은 도달하지 않는다.
    파일이 실제로 없으면 `PoseLandmarker` 생성 시점에 예외가 나고,
    그건 조용한 실패가 아니라 그 자리에서 드러나는 실패다(의도).

    (왜) 이게 없다면 관절 33점 이 꺼진다. 구 `mediapipe.solutions` API 는 Windows
    배포판에 없고(0.10.33 / 1.0.1 휠에 `mediapipe/python/` 항목 0개),
    tasks API 는 .task 모델 파일이 필요하다.

    (왜) 동봉한다: 이 파일은 인체 마스크·부위별 강도·프레이밍 판정의 전제다.
    없으면 세 기능이 **에러 없이 조용히** 꺼진다 — 사용자가 알아채기 어렵다.
    그래서 "설치하면 따라오는 쪽" 이 되도록 노드 폴더에 함께 넣고 `__file__`
    기준으로 찾는다. 사용자가 경로를 몰라도 되는 게 맞다.

    (왜) 탐색하지 않는다 (R61): 시스템 여러 곳을 뒤지지 않고 **자기 옆 한 곳만**
    본다. 그것도 존재 여부를 확인하지 않는다 — 경로가 잘못되면 조용히 None 이
    아니라 `PoseLandmarker` 생성 시점에 그 자리에서 죽어야 "조용한 실패" 가
    되지 않는다.

    (왜) 환경변수가 먼저: 사용자가 lite 대신 full/heavy 를 쓰고 싶을 수 있다.
    동봉본이 기본이고 환경변수가 선택지다.
    """
    import os as _os
    env = _os.environ.get("GORI_POSE_MODEL")
    if env:
        return env
    return _os.path.join(_os.path.dirname(_os.path.realpath(__file__)),
                          _POSE_MODEL_FILENAME)


def _hand_model_path():
    """사용할 손 .task 모델 경로 문자열을 돌려준다 (항상 str, None 아님).

    왜(Why) 환경변수가 먼저인가: 포즈와 같은 규칙. `GORI_HAND_MODEL` 로
    다른 손 모델을 쓸 수 있고, 동봉본이 기본이다.
    """
    import os as _os
    env = _os.environ.get("GORI_HAND_MODEL")
    if env:
        return env
    return _os.path.join(_os.path.dirname(_os.path.realpath(__file__)),
                          _HAND_MODEL_FILENAME)


def _face_model_path():
    """사용할 얼굴 .task 모델 경로 문자열 (항상 str, None 아님).

    face_landmarker.task (478점, Apache-2.0) — 2026-10-05 다운로드,
    pose/hand 와 같은 계열이다. `GORI_FACE_MODEL` 로 교체 가능.
    """
    import os as _os
    env = _os.environ.get("GORI_FACE_MODEL")
    if env:
        return env
    return _os.path.join(_os.path.dirname(_os.path.realpath(__file__)),
                         _FACE_MODEL_FILENAME)


_FACE_MODEL_FILENAME = "face_landmarker.task"


def _facemarker():
    """FaceLandmarker 세션 (478점). 실패하면 None.

    왜(Why) 임계가 0.1 인가 (2026-10-05 실측): 0.3 에서는 정면 얼굴도
    놓치는 프레임이 있었다(0707/0903 0검출). 0.1 에서 3얼굴 전부
    검출됐고 오탐은 관측되지 않았다. num_faces=4 — 개수 판독이 목적이
    손 개수 패스와 같다.
    """
    if _TASKS_FACEMARKER:
        return _TASKS_FACEMARKER[0]
    model = _face_model_path()
    try:
        from mediapipe.tasks.python import vision as _vision
        _BaseOptions = _find_base_options()
        if _BaseOptions is None:
            return None
        options = _vision.FaceLandmarkerOptions(
            base_options=_BaseOptions(model_asset_path=model),
            running_mode=_vision.RunningMode.IMAGE,
            num_faces=4,
            min_face_detection_confidence=0.1,
            min_face_presence_confidence=0.1)
        lm = _vision.FaceLandmarker.create_from_options(options)
    except Exception as _e:
        _note_pose_error('_facemarker', _e)
        return None
    _TASKS_FACEMARKER.append(lm)
    return lm


def _face_pts_from_tasks(u8):
    """uint8 → [얼굴별 478×(x,y)] 리스트. 판독 불가면 None."""
    try:
        import numpy as _np
    except Exception:
        return None
    fm = _facemarker()
    if fm is None:
        return None
    try:
        import mediapipe as _mp
        a = _np.ascontiguousarray(_np.asarray(u8, dtype=_np.uint8))
        if a.ndim != 3 or a.shape[2] != 3:
            return None
        a = _even_rgb(a)
        if a is None:
            return None
        img = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=a)
        res = fm.detect(img)
        groups = getattr(res, "face_landmarks", None)
        if not groups:
            return []
        out = []
        for g in groups:
            out.append([(float(p.x), float(p.y)) for p in g])
        return out
    except Exception as _e:
        _note_pose_error('_face_pts_from_tasks', _e)
        return None


def _skin_stats(u8, pts):
    """노출 피부 후보 소패치의 HSV 중앙값. 실패·부족하면 None.

    패치 위치는 **각 이미지 자신의** pose landmark(코 0, 입 9, 손목
    15/16, 뒤꿈치 29/30)를 따른다 — 원본과 결과의 프레이밍이 달라도
    각자의 부위에서 읽으므로 비교가 성립한다. 패치 3개 미만이면
    판독 불가(None)다.
    """
    try:
        import cv2
        import numpy as _np
    except Exception:
        return None
    if u8 is None or not pts:
        return None
    h, w = u8.shape[:2]
    try:
        hsv = cv2.cvtColor(u8, cv2.COLOR_RGB2HSV)
    except Exception:
        return None
    med = []
    for i in (0, 9, 15, 16, 29, 30):
        if i >= len(pts):
            continue
        p = pts[i]
        try:
            x = int(round(float(p[0]) * (w - 1)))
            y = int(round(float(p[1]) * (h - 1)))
        except (TypeError, ValueError):
            continue
        x0, x1 = max(0, x - 4), min(w, x + 5)
        y0, y1 = max(0, y - 4), min(h, y + 5)
        if x1 <= x0 or y1 <= y0:
            continue
        med.append(_np.median(hsv[y0:y1, x0:x1].reshape(-1, 3), axis=0))
    if len(med) < 3:
        return None
    m = _np.median(_np.stack(med), axis=0)
    return (float(m[0]), float(m[1]), float(m[2]))


def _skin_deviation(a, b):
    """두 피부 통계의 편차 (0~1, hue 는 원형 거리). 판독 불가면 None.

    임계 판정은 호출부가 한다 — 여기선 측정만. PROVISIONAL: 정상 분포가
    learn_log 에 쌓이면 확정한다.
    """
    if not a or not b:
        return None
    try:
        dh = min(abs(a[0] - b[0]), 180.0 - abs(a[0] - b[0])) / 90.0
        ds = abs(a[1] - b[1]) / 255.0
        dv = abs(a[2] - b[2]) / 255.0
        return round(min(1.0, dh + ds + dv), 4)
    except (TypeError, ValueError):
        return None


def _find_base_options():
    """mediapipe 의 BaseOptions 를 어디서든 찾아온다. 없으면 None.

    왜(Why) 탐색하나 (2026-10-01 실측): `BaseOptions` 의 위치가 버전마다
    다르다. 0.10.33 은 `mediapipe.tasks.python.core.base_options` 에만 있고,
    `mediapipe.tasks` 와 `mediapipe.tasks.python.vision` 에는 **없다**. 경로를
    하나 박아두면 다른 버전 사용자에게서 포즈가 조용히 통째로 꺼진다 — 그게
    실제로 일어난 바이다(ImportError → landmarker 미생성 → 픽셀 분석 전체 사망).
    순서대로 시도하고, 없으면 None 을 돌려 호출부가 로그를 남긴다.
    """
    for _path in ("mediapipe.tasks.python.core.base_options",
                  "mediapipe.tasks.python.vision.core.base_options",
                  "mediapipe.tasks.core.base_options"):
        try:
            _mod = _importlib.import_module(_path)
            _bo = getattr(_mod, "BaseOptions", None)
            if _bo is not None:
                return _bo
        except Exception:
            continue
    return None


def _pose_landmarker():
    """mediapipe tasks PoseLandmarker 세션. 실패하면 None.

    (왜) 세션은 한 번만 만들어 재사용한다. 모델 로드는 수 초 걸린다.
    """
    if _TASKS_LANDMARKER:
        return _TASKS_LANDMARKER[0]
    model = _pose_model_path()
    if model is None:
        return None
    try:
        from mediapipe.tasks.python import vision as _vision
        # 왜(Why) 여기서 가져오나 (2026-09-30 실측):
        # `mediapipe.tasks.BaseOptions` 는 0.10.33 의 tasks/__init__.py 에 없다
        # (ImportError). 그래서 landmarker 가 한 번도 만들어지지 않았고,
        # _part_detail_map 이 None 을 돌려주면서 그 아래 픽셀 공간 부위 분석
        # (detail_boost / _apply_region_strength) 이 통째로 죽었다. 단위
        # 테스트 223 건이 포즈 세션을 stub 으로 주입해서 이 경로를 검증하지
        # 못한 탓이다. 정답은 mediapipe 최상위가 아니라 그 안의 모듈 — landmarker 0.08초 생성, 33점
        # 검출까지 확인했다.
        _BaseOptions = _find_base_options()
        if _BaseOptions is None:
            # 왜(Why) 여기서 알리나 (2026-10-02): mediapipe.tasks 가 없으면
            # 아래 `_BaseOptions(...)` 에서 TypeError 가 나고 `_note_pose_error` 로
            # 잡힌다. 그런데 그건 "동작 중 실패" 로그지 "기능 꺼짐" 안내가 아니다.
            # macOS(휠 없음) 사용자는 포즈 기능이 통째로 꺼진 줄 모른다.
            # `_note_pose_unavailable` 은 그 안내인데 호출부가 dead 분기 안에
            # 있어서 영영 안 불렸다. 진짜 "없음" 조건인 여기에 둔다.
            _note_pose_unavailable()
            return None
        options = _vision.PoseLandmarkerOptions(
            base_options=_BaseOptions(model_asset_path=model),
            running_mode=_vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            # 왜(Why) False 로 고정하나 (2026-09-30 실측): True 로 세면
            # mediapipe 0.10.33 가 내부 ROI 마스크를 만들다가 **네이티브
            # SIGABRT** 로 죽는다(image_frame.cc "Check failed: 1 ==
            # ChannelSize()"). SIGABRT 는 try/except 로 못 잡아 ComfyUI 서버
            # 전체가 죽는다. 입력으로 막는 시도 3가지는 전부 실패했다(입력
            # 홀짝 판정 / 512px 축소 / 정사각 패딩). 인체 마스크는 이 세션이
            # 아니라 33점 포즈에서 직접 만든다(`_person_mask_from_rgb`).
            output_segmentation_masks=False)
        lm = _vision.PoseLandmarker.create_from_options(options)
    except Exception as _e:
        # 왜(Why) import 실패는 안내로, 나머지는 오류로 (2026-10-05 감사 67차):
        # mediapipe 미설치 환경의 첫 얼굴이 "ModuleNotFoundError: No module
        # named 'mediapipe'" 스택류 메시지면 사용자는 무엇을 해야 하는지
        # 모른다. __init__ 이 약속한 "이유를 콘솔에 한 번 알린다" 는 이
        # 안내(`_note_pose_unavailable`)다. import 성공 후의 실패는
        # 동작 중 오류라 기존 채널이 맞다.
        if isinstance(_e, ImportError):
            _note_pose_unavailable()
        else:
            _note_pose_error('_pose_landmarker', _e)
        return None
    _TASKS_LANDMARKER.append(lm)
    return lm


_HAND_MAX = 4


_HAND_MIN_CONF = 0.3


# 개수 세기용 저신뢰 패스 (2026-10-05 실측): 0.30 에서는 가려진 손을
# 놓친다(3팔 이미지: 3개 중 1개만 검출). 0.10 으로 내리면 3개 전부
# 검출되고 정상 이미지 3장에서 오탐 0이었다. 0.05 는 정상 이미지에서
# 없는 손 1개를 만들어냈으므로 그 아래로는 내리지 않는다. 손가락 품질
# 판정은 현행 0.30 을 그대로 쓴다 — 개수와 품질의 역할을 나눈다.
_HAND_COUNT_CONF = 0.1


# 손 개수 상한은 kp_judge `_HAND_COUNT_MAX_OK` 가 공급원이다 (star import 로
# 들어온다). 여기서 다시 정의하면 같은 규칙이 두 곳에서 갈라진다
# (2026-10-07 감사 — 예전엔 이 줄에 `= 2` 가 중복돼 있었다).


def _hand_landmarker():
    """mediapipe tasks HandLandmarker 세션. 실패하면 None.

    왜(Why) 포즈와 같은 1원소 리스트인가: 검증된 패턴을 따른다.
    왜(Why) num_hands=4 인가: 2개가 정상이고 3개 이상이 비정상이다.
    2개까지만 보면 3번째 손을 못 센다. 4개까지 봐야 여분을 잡는다.
    왜(Why) 임계 0.3 인가: 포즈의 0.3 재시도와 같은 실측 근거 (13장 중
    사람 있는 것은 0.3 에서 잡힌다). 손은 더 작아서 0.5 로 올리면 놓친다.
    """
    if _TASKS_HANDMARKER:
        return _TASKS_HANDMARKER[0]
    model = _hand_model_path()
    try:
        from mediapipe.tasks.python import vision as _vision
        _BaseOptions = _find_base_options()
        if _BaseOptions is None:
            _note_hand_unavailable()
            return None
        options = _vision.HandLandmarkerOptions(
            base_options=_BaseOptions(model_asset_path=model),
            running_mode=_vision.RunningMode.IMAGE,
            num_hands=_HAND_MAX,
            min_hand_detection_confidence=_HAND_MIN_CONF,
            min_hand_presence_confidence=_HAND_MIN_CONF,
            min_tracking_confidence=_HAND_MIN_CONF)
        lm = _vision.HandLandmarker.create_from_options(options)
    except Exception as _e:
        # 왜(Why) 포즈와 같은 분기인가 (2026-10-05 감사 67차): 미설치 첫
        # 얼굴은 안내여야지 스택류 오류가 아니다. import 성공 후의 실패는
        # 동작 중 오류라 기존 채널이 맞다.
        if isinstance(_e, ImportError):
            _note_hand_unavailable()
        else:
            _note_pose_error('_hand_landmarker', _e)
        return None
    _TASKS_HANDMARKER.append(lm)
    return lm


def _hand_landmarker_count():
    """개수 세기용 HandLandmarker 세션 (저신뢰 0.1). 실패하면 None.

    왜(Why) 세션을 둘로 나누나: 품질 판정용(0.3)과 개수용(0.1)의 임계가
    다르다. 같은 세션을 쓰면 품질 판정이 낮은 신뢰의 검출까지 받아
    손가락 판정이 흔들린다. 캐시 패턴은 _hand_landmarker 와 같다.
    """
    if _TASKS_HANDCOUNT:
        return _TASKS_HANDCOUNT[0]
    model = _hand_model_path()
    try:
        from mediapipe.tasks.python import vision as _vision
        _BaseOptions = _find_base_options()
        if _BaseOptions is None:
            _note_hand_unavailable()
            return None
        options = _vision.HandLandmarkerOptions(
            base_options=_BaseOptions(model_asset_path=model),
            running_mode=_vision.RunningMode.IMAGE,
            num_hands=_HAND_MAX,
            min_hand_detection_confidence=_HAND_COUNT_CONF,
            min_hand_presence_confidence=_HAND_COUNT_CONF,
            min_tracking_confidence=_HAND_COUNT_CONF)
        lm = _vision.HandLandmarker.create_from_options(options)
    except Exception as _e:
        # 왜(Why) 포즈와 같은 분기인가: 미설치 첫 얼굴은 안내여야지
        # 스택류 오류가 아니다 (_hand_landmarker 와 같은 근거).
        if isinstance(_e, ImportError):
            _note_hand_unavailable()
        else:
            _note_pose_error('_hand_landmarker_count', _e)
        return None
    _TASKS_HANDCOUNT.append(lm)
    return lm


def _note_hand_unavailable():
    """손 모델 없음을 한 번만 알린다 (조용한 실패 금지)."""
    global _HAND_NOTED
    if _HAND_NOTED:
        return
    _HAND_NOTED = True
    _log("[GoRi Consistency Keeper] 손가락 판정이 꺼져 있다. "
         "mediapipe tasks 의 " + _HAND_MODEL_FILENAME + " 을 못 읽는다. "
         "mediapipe 설치 여부, 설치 폴더에 파일이 있는지, 또는 "
         "GORI_HAND_MODEL 환경변수 경로가 맞는지 확인해 주세요. "
         "포즈 기반 판정은 계속 동작한다.")


def _hand_landmarks_from_tasks(u8):
    """uint8 HWC RGB → 손마다 21점 리스트. 실패하면 None.

    반환: [[(x, y, handedness), ... 21점], ... 손 개수만큼].
    handedness 는 Left 또는 Right 문자열 (MediaPipe 기준, 거울상 주의).
    """
    try:
        import numpy as _np
    except Exception:
        return None
    hl = _hand_landmarker()
    if hl is None:
        return None
    try:
        import mediapipe as _mp
        a = _np.ascontiguousarray(_np.asarray(u8, dtype=_np.uint8))
        if a.ndim != 3 or a.shape[2] != 3:
            return None
        # 왜(Why) 직접 자르지 않고 _even_rgb 를 쓰나: 수동 trim 은 <2px 가드를
        # 빼먹는다. 1px 입력이 0행/0열 배열이 되어 네이티브 SIGABRT 경로로 간다 —
        # _even_rgb 가 막기 위해 만들어진 바로 그 죽음이다. 같은 파일 헬퍼를 쓴다.
        a = _even_rgb(a)
        if a is None:
            return None
        img = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=a)
        res = hl.detect(img)
        groups = getattr(res, "hand_landmarks", None)
        if not groups:
            return None
        out = []
        for gi, g in enumerate(groups):
            hn = None
            try:
                hn = res.handedness[gi][0].category_name
            except Exception:
                pass
            pts = []
            for lm in g:
                pts.append((float(lm.x), float(lm.y), hn))
            if len(pts) == 21:
                out.append(pts)
        return out or None
    except Exception as _e:
        _note_pose_error('_hand_landmarks', _e)
        return None


def _hand_count_from_tasks(u8):
    """uint8 HWC RGB → 검출된 손 개수 int. 판정 불가면 None.

    왜(Why) 저신뢰 0.1 별도 패스인가 (2026-10-05 실측): 손가락 판정용
    검출(0.3)은 가려진 손을 놓쳐 3팔 이미지를 1손으로 봤다. 0.1 로
    내리면 3개 전부 잡히고 정상 3장 오탐 0 — 개수 위반의 근거는 개수
    전용 패스에서만 얻는다. 반환 None 은 "못 셌다"이지 위반이 아니므로
    호출부는 판단 보류로 떨어진다(조용히 막지 않는다).
    """
    try:
        import numpy as _np
    except Exception:
        return None
    hl = _hand_landmarker_count()
    if hl is None:
        return None
    try:
        import mediapipe as _mp
        a = _np.ascontiguousarray(_np.asarray(u8, dtype=_np.uint8))
        if a.ndim != 3 or a.shape[2] != 3:
            return None
        a = _even_rgb(a)
        if a is None:
            return None
        img = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=a)
        res = hl.detect(img)
        groups = getattr(res, "hand_landmarks", None)
        return len(groups) if groups else 0
    except Exception as _e:
        _note_pose_error('_hand_count_from_tasks', _e)
        return None


def _pose_landmarks_from_tasks(u8, with_visibility=False):
    """uint8 HWC RGB -> 33 (x, y). 모델/검출이 없으면 None.

    왜(Why) with_visibility 인자가 있나 (2026-10-01): 판정층(work_status 10절)은
    **관절이 보이는지** 를 알아야 하는데 이 함수는 좌표만 버리고 visibility 를
    흘려보내고 있었다. 판정층을 위해 landmark 를 **두 번째로 검출**하면 프레임마다
    mediapipe 가 한 번 더 돈다 — `new_vae_decode_in_per_frame_path` 와 같은 종류의
    낭비다. 그래서 한 번의 검출 결과를 두 형태로 읽게 한다.

    기본값이 False 라 기존 호출자(`_person_mask_from_rgb`, `subject_bbox`,
    `_pose_landmarks`) 는 **똑같이 2-튜플**을 받는다. 그대로 둔다.
    """
    lm = _pose_landmarker()
    if lm is None:
        return None
    try:
        import mediapipe as _mp
        arr = _even_rgb(u8)
        if arr is None:
            return None
        img = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=arr)
        res = lm.detect(img)
        groups = getattr(res, "pose_landmarks", None)
        if not groups:
            # 왜(Why) 여기서 한 번 더 시도하나 (2026-10-01 실측): 기본 세션의
            # `min_pose_detection_confidence=0.5` 가 **사람 있는 시트**를 놓쳤다.
            # 13장 실측에서 0.5 는 9/13, 0.3 은 12/13 이었다. 놓친 한 장은
            # 흰 배경 시트(캐릭터 시트1)인데 흰 배경 **의상 제품 사진** 3장은
            # 0.3 에서도 0 이다. 즉 0.3 재시도는 "사람 있는데 놓친 것" 과
            # "사람이 아예 없는 것" 을 **구별해 주는** 신호가 된다.
            # 그냥 0.5 에서 놓치면 게이트가 조용히 통과해 버린다.
            res = _pose_retry_low_conf(arr, _mp)
            groups = getattr(res, "pose_landmarks", None)
            if not groups:
                return None
        pts = groups[0]
        if len(pts) < 33:
            return None
        if not with_visibility:
            return [(float(p.x), float(p.y)) for p in pts[:33]]
        out = []
        for p in pts[:33]:
            # visibility 는 landmark 마다 없을 수 있다. 없는 것은 0.0 이다 —
            # 판정층이 "관측 불가"와 "관측됐으나 흐림"을 구분할 수 있어야 하는데,
            # 두 값이 합쳐져도 게이트 결과는 같으므로 한 값으로 읽어도 무방하다.
            vis = getattr(p, "visibility", None)
            out.append((float(p.x), float(p.y),
                        float(vis) if vis is not None else 0.0))
        return out
    except Exception as _e:
        _note_pose_error('_pose_landmarks_from_tasks', _e)
        return None


_POSE_ERR_NOTED = False


# 왜(Why) 손 에러도 이 플래그를 쓰나: `_note_pose_error` 가 포즈·손을 구분하지
# 않고 한 번만 말한다. 먼저 난 에러가 나중 에러를 가린다. 분리하면 로그가
# 늘고 테스트의 "1회" 단언이 깨진다. 구분이 필요해지면 where 를 키에 넣는다.


_DECODE_RETRY_NOTED = False


def _note_retry_error(exc):
    """상한 재시도 디코드가 실패한 이유를 한 번만 알린다 (조용한 실패 금지).

    재시도는 '있으면 더 좋고 없어도 동작하는' 개선이라 실패해도 상한본으로
    진행한다. 하지만 조용히 삼키면 포즈를 못 잡은 이유를 사용자가 알 수 없다.
    """
    global _DECODE_RETRY_NOTED
    if _DECODE_RETRY_NOTED:
        return
    _DECODE_RETRY_NOTED = True
    _log("[GoRi Consistency Keeper] ⚠ 상한 재시도 경로에서 오류 — 원래(상한본) "
         "해상도 결과로 진행한다: "
         + type(exc).__name__ + ": " + str(exc))


def _note_pose_error(where, exc):
    """Log a pose inference failure once. (Jev 2026-09-30: log_once, severity 1.93)

    Per-frame logging would flood the console, so it fires once per process.
    """
    global _POSE_ERR_NOTED
    if _POSE_ERR_NOTED:
        return
    _POSE_ERR_NOTED = True
    _log('[GoRi Consistency Keeper] ⚠ pose inference failed in ' + where + ': '
         + type(exc).__name__ + ': ' + str(exc))


def _note_pose_unavailable():
    """기능이 꺼진 이유를 한 번만 사용자에게 알린다 (조용한 실패 금지)."""
    global _POSE_NOTED
    if _POSE_NOTED:
        return
    _POSE_NOTED = True
    _log("[GoRi Consistency Keeper] 인체 마스크·부위별 강도·프레이밍 판정이 꺼져 있다. "
         "mediapipe tasks 의 " + _POSE_MODEL_FILENAME + " 을 못 읽는다. "
         "mediapipe 설치 여부, 설치 폴더에 파일이 있는지, 또는 "
         "GORI_POSE_MODEL 환경변수 경로가 맞는지 확인해 주세요. "
         "인물 위치만 쓰는 강도 조절은 계속 동작한다.")


def _person_mask_from_rgb(u8):
    """uint8 HWC RGB -> (H, W) float 인물 마스크(0~1). 사람 없으면 None.

    왜(Why) mediapipe 세그멘테이션을 안 쓰는가 (2026-09-30 실측):
    `output_segmentation_masks=True` 는 mediapipe 0.10.33 에서 **네이티브
    SIGABRT** 로 프로세스를 죽인다 —
        image_frame.cc:415] Check failed: 1 == ChannelSize() (1 vs. 4)
    SIGABRT 는 try/except 로 못 잡으므로 그저 "안전"인 척할 뿐, 실제로는
    ComfyUI 서버 전체가 죽는다. 입력으로 막는 시도 3가지는 **전부 실패**했다
    (2026-09-30 실측): 입력 홀수/짝수 판정(짝수 1814x1244 도 죽음), 512px
    축소(896x1152 죽음), 정사각 패딩(1814x1243 죽음). 즉 내부 ROI 계산에 의존
    하는 크래시라 **크기 기반 방어가 불가능**하다.

    왜(Why) 33점으로 충분한가: 이 마스크는 "인물이 어디 있나" 라는 **부드러운
    공간 가중치**로만 쓰인다(`_person_mask_for_latent` → interpolate →
    avg_pool2d). 정밀 윤곽이 아니라면 뼈대를 따라 부드럽게 감쇠하는 것만으로
    같은 역할을 한다. 게다가 이 노드가 노리는 게 포즈·해부 일관성이므로
    포즈에서 만든 마스크가 더 일관되고, 전체 해상도라 축소 손실도 없다.
    """
    try:
        import numpy as _np
        pts = _pose_landmarks_from_tasks(u8)
        if not pts:
            return None
        arr = _np.asarray(u8)
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h < 2 or w < 2:
            return None
        # 왜(Why) float32 격자인가 (2026-10-04 감사 11차): mgrid 는 int64 를
        # 돌려주고 (격자 + 0.5) / w 는 float64 로 승격된다. 1024 픽셀 프레임
        # 기준 33회 루프가 float64 임시 배열을 프레임마다 수백 MB 흘린다.
        # 최종 출력은 어차피 astype(float32) 이라 float64 정밀도는 아무것도
        # 사지 않는다 — 좌표 격자를 처음부터 float32 로 만든다.
        xs = ((_np.arange(w, dtype=_np.float32) + _np.float32(0.5))
              / _np.float32(w))[None, :]
        ys = ((_np.arange(h, dtype=_np.float32) + _np.float32(0.5))
              / _np.float32(h))[:, None]
        best = None
        for (px, py) in pts[:33]:
            d = ((xs - _np.float32(px)) ** 2
                 + (ys - _np.float32(py)) ** 2)
            best = d if best is None else _np.minimum(best, d)
        dist = _np.sqrt(best)
        # 왜(Why) 반경을 **체격**으로 재나 (2026-09-30 실측): 처음엔 이미지 최대
        # 거리로 정규화했다. 그 결과 배경까지 전부 0.5~0.7 을 받아 마스크가
        # 99.9% 를 덮었고 "인물 영역만 당김" 이 사실상 동작하지 않았다
        # (실측 cover=0.999). 뼈대 주변에만 가중치를 주려면 감쇠 거리가 **몸집
        # 크기** 기준이어야 한다 — 랜드마크 bbox 의 긴 변을 쓴다.
        box = subject_bbox(pts)
        if box is None:
            return None
        body = max(box[2] - box[0], box[3] - box[1])
        r = _MASK_FALLOFF * float(body)
        # 왜(Why) 바닥/천장이 필요한가: bbox 만 믿으면 양쪽 끝에서 깨진다.
        # ① 랜드마크가 몇 점에 몰리면 bbox->0 이 되어 마스크가 한 점으로
        # 수축한다. ② 사람이 화면을 꽉 차면 bbox->1 이 되어 배경을 삼킨다.
        r = min(max(r, _MASK_FALLOFF_MIN), _MASK_FALLOFF_MAX)
        # (2026-10-04 감사 11차) 위 clamp 뒤의 `if r <= 0.0: return None` 은
        # 도달 불가능한 죽은 절이었다 — _MASK_FALLOFF_MIN=0.15 가 하한을
        # 보장하므로 r<=0 은 거짓이다. 지웠다.
        mask = _np.clip(1.0 - dist / r, 0.0, 1.0)
        return mask.astype(_np.float32)
    except Exception as _e:
        # 왜(Why) 넓은 except 를 쓰면서 반드시 로그를 남기나 (Jev 게이트
        # exception_swallowing_silent_none P=0.86): 이 노드가 픽셀 공간 분석
        # 은 예외를 삼키고 None 을 돌려주는 것이 설계다(프레임마다 죽이면
        # 노드가 못 쓴다). 그런데 **로그가 없으면** "조용히 꺼진 것" 과
        # "조용히 실패한 것" 이 구분되지 않는다 — 실제로 이 경로는 3개 버그
        # (import 경로 / SIGABRT / 디코드 레이아웃)를 한참 숨겼다. 넓게 잡되
        # 반드시 한 번 말한다.
        # 왜(Why) 포즈 채널이 아닌가 (2026-10-04 감사 5차): 이 try 안의
        # 유일한 포즈 callee 는 자기 안에서 실패를 삼키므로 여기까지 오는
        # 것은 numpy 지오메트리다. 포즈 채널을 쓰면 진짜 포즈 실패가
        # 묻히고, 그 채널은 한 번뿐이라 구조적 실패가 폭주도 막는다 —
        # 그래서 별도 once 채널로 보낸다.
        _note_once('person_mask',
                   "[GoRi Consistency Keeper] ⚠ person mask failed in "
                   "_person_mask_from_rgb: %s: %s"
                   % (type(_e).__name__, str(_e)))
        return None


def _person_mask_for_latent(vae, sampled, cache=None):
    """전체 latent -> 인물 마스크 (latent 해상도, 0~1). 실패하면 None.

    (왜) 구 `mediapipe.solutions` API 는 Windows 배포판에 없다. 0.10.33 과
    1.0.1 의 win_amd64 휠을 열어 `mediapipe/python/` 항목이 0개임을 확인했다.
    남는 경로는 0.10 의 tasks API 뿐이고, 그것은 .task 모델 파일이 필요하다.
    모델이 없으면 마스크 없이 조용히 넘어간다 (2026-09-30 실측).
    """
    try:
        import torch as _t
        import numpy as _np
        if vae is None or sampled is None:
            return None
        # 왜(Why) 경로가 아니라 **세션** 을 먼저 보는가: 게이트가 경로만 확인하면
        # VAE 디코딩(비싼 비용)을 먼저 다 쓴 뒤에야 "모델 못 읽음" 을 알게 된다.
        # 경로는 있고 파일이 깨졌거나(설치 경로에 한글 등) mediapipe 가 못 여는
        # 경우 매 실행마다 디코딩 1회를 버리게 된다 — 2026-09-30 실측으로
        # 확인한 회귀. 세션은 있으면 캐시되므로 여기서 부르는 비용이 없고,
        # 없으면 그 자리에서 0 원으로 빠져나간다.
        if _pose_landmarker() is None:
            return None
        arr = _decode_latent_rgb(vae, sampled, cache=cache)
        if arr is None:
            _release_vram()
            return None
        u8 = (_np.clip(arr, 0.0, 1.0) * 255.0).astype(_np.uint8)
        seg = _person_mask_from_rgb(u8)
        if seg is None or seg.max() <= 0.01:
            _release_vram()
            return None
        # 왜(Why) 임계 0.35 인가 (2026-09-30 실측): 감쇠 마스크를 그대로 쓰면
        # 배경에도 0.2~0.4 가 남아 "인물 영역만" 이라는 목적이 흐려진다(실측
        # 배경 평균 0.31). 0.35 로 이진화하면 인물 0.95 / 배경 0.31 로 갈리고
        # 화면의 38%가 완전히 빠진다. 그 뒤 보간+avg_pool 으로 다시 부드럽게.
        mask = (seg > _MASK_MIN_WEIGHT).astype(_np.float32)
        m = _t.from_numpy(mask[None, None]).to(
            device=sampled.device, dtype=sampled.dtype)
        _, _, lh, lw = sampled.shape
        import torch.nn.functional as _f
        m = _f.interpolate(m, size=(lh, lw), mode="bilinear",
                           align_corners=False)
        m = _f.avg_pool2d(m, kernel_size=3, stride=1, padding=1)
        m = m.clamp(0.0, 1.0)
        del u8, seg, mask
        _release_vram()
        return m
    except Exception:
        _release_vram()
        return None


_ONCE_SEEN = set()


def _note_once(key, msg):
    """같은 키의 메시지를 **한 번만** 말한다.

    왜(Why) 이게 필요한가: 조용한 실패가 오늘 하루에 세 번(import 실패,
    구문 오류, 잘못된 디코더) 진단을 가로막았다. 그런데`_local_edge` 는
    landmark 33개마다 불려서 그냥 로그를 남기면 스팸이 된다. 한 번만.
    """
    if key in _ONCE_SEEN:
        return
    _ONCE_SEEN.add(key)
    _log(msg)


# 2026-09-28 정밀 검토: 여기 있던 `_edge_map(latent, vae)`는 **호출이 0건**인
# 죽은 함수였다(grep 확인). 내용 자체는 `_part_detail_map`의 디코드 블록과
# 복붙 수준으로 동일했고, 그 중복이 "실행당 VAE 디코딩 4~5회"의 원인이었다.
# 제거했다. 디코딩 공유는 별건으로 `_decode_small` 하나로 모았다.
# 참조가 필요한 곳은 `panel_signature`(에지맵 직접 계산)다.


def _part_detail_map(vae, latents, cache=None) -> "dict | None":
    """landmark별 (에지 밀도, x, y) 추출. 모델 없으면 None.

    반환 형태: {"sampled": {"edge": [33 floats], "xy": [(x,y) x33]}, ...}
    xy가 지면별 **공간 마스크**를 만들 수 있다 — 33개 벡터만으로는
    화면 전면 을 설명할 수 없으므로. 그래프가 눈·손을 못 따라간다.

    (왜) 예전엔 `mediapipe.solutions.pose.Pose` 였는데 그 API 가 Windows
    배포판에 없다. tasks API + .task 모델로 대체한다.

    (왜) 경로가 아니라 세션으로 게이트를 건다: 아래 루프는 프레임마다 VAE
    디코딩을 한다. 게이트가 경로만 보면 파일이 못 열릴 때 **디코딩을 다 하고
    나서야** 포즈 없음을 알게 되어 비용을 버린다 (2026-09-30 실측). 세션은
    캐시되므로 여기서 부르는 비용은 없고, 못 열면 그 자리에서 0 원으로 빠진다.
    """
    try:
        import numpy as _np
    except Exception:
        return None
    if _pose_landmarker() is None:
        return None
    if vae is None or not latents:
        return None
    out = {}
    # 왜(Why) `_POSE_WHY` 를 남기나 (2026-10-01): 예전엔 `if not pts3: continue`
    # 뿐이었다. 그러면 **사람이 없는 사진**과 **탐지 실패**와 **이미지가 부적합**
    # 이 셋이 구분되지 않았다. 실측에서 `의상 교체1~3`(사람 없는 제품 사진) 이
    # 0점이라 "탐지 실패처럼" 보였고, 그 결과 판정 게이트가 조용히 제한 없이
    # 진행했다. 게이트를 켰는데 판정이 없다는 이유로 완전 통과하는 셈이다.
    #
    # 왜(Why) `global` 이 필수인가 (2026-10-01 실측): 이 선언이 없으면 아래
    # 다섯 줄이 **함수 지역 dict** 를 채운다. 함수는 `out` 만 돌려주므로 그
    # dict 는 버려지고, `run()` 이 읽는 모듈 수준 `_POSE_WHY` 는 영원히 비어
    # 있어 게이트가 항상 "사유 기록 없음" 을 본다. 사슬이 조용히 끊기면
    # `_pose_gate_message` 의 ⚠ 승격 경로도 영영 발동하지 않는다.
    # 8d2fd86("Stop the trust gate from passing in silence") 의 목적이
    # 정확히 이 경로였는데 `global` 한 줄로 무력화돼 있었다.
    #
    # 왜(Why) `_clear()` 가 아니라 키만 지우는가: 같은 dict 에 `_note_pose_why` 의
    # 중복 방지용 `_said` 도 산다. 통째로 비우면 **매 프레임마다** "한 번만"
    # 계약이 초기화되어 같은 사유가 스텝 수만큼 되풀이된다. 사유 키만 지운다.
    global _POSE_WHY
    for _k in [k for k in _POSE_WHY if k != "_said"]:
        del _POSE_WHY[_k]
    for name, lat in latents.items():
        if lat is None:
            continue
        try:
            arr = _decode_latent_rgb(vae, lat, cache=cache)
            if arr is None:
                _POSE_WHY[name] = "디코드 결과 없음"
                continue
            em = _edge_mag_from_rgb(arr)
            if em is None:
                _POSE_WHY[name] = "에지 맵 계산 실패"
                continue
            u8 = (_np.clip(arr, 0, 1) * 255).astype(_np.uint8)
            # (2026-10-04 감사): 여기서 "포즈 모델 없음" reason 을
            # 남기던 블록을 지웠다 — 진입부의 같은 검사가 이미 return
            # 하고 세션 캐시는 evict 되지 않으므로 도달 불가였고,
            # 소비자 게이트도 이 경로에서는 읽지 않았다.
            pts3 = _pose_landmarks_from_tasks(u8, with_visibility=True)
            if not pts3:
                # 왜(Why) "사람 없음" 과 "탐지 실패" 를 나눠 말하나 (2026-10-01
                # 실측): 13 장을 재서 봤다. 임계 0.3 에서도 0 인 것은 **의상
                # 제품 사진 3 장**(사람이 없다) 뿐이었고, 흰 배경 **시트**는
                # 0.3 에서 전부 잡혔다. 즉 "0.5 에서도 0.3 에서도 0" 은 이
                # 표본에서 "사람 없음" 을 뜻했다. 다만 이를 **단정**하지 않고
                # 그대로 말해, 다른 원본에서 같은 로그가 나오면 Investigate
                # 되도록 표기를 남긴다.
                _POSE_WHY[name] = ("사람 미검출 (임계 0.3 재시도까지 실패) "
                                   "— 제품 사진 등 사람이 없는 이미지일 수 있음, "
                                   "탐지 문제면 이 문구가 반복된다")
                continue
            edge = [0.0] * 33
            xy = []
            for i, (px, py, pv) in enumerate(pts3[:33]):
                # xy 는 **2-튜플 그대로** 둔다. `_apply_region_strength` 가
                # `for (px, py) in xy` 로 엄격 언팩하므로 3-튜플을 넣으면 죽는다.
                xy.append((px, py))
                # 왜(Why) `_local_edge` 인가: 예전엔 16×16 격자 셀 평균을 썼고
                # 손·다리에서 거의 0 이 나와 부위 하나도 못 골랐다(10-24 실측).
                # 이제 landmark 주변 5% 창을 본다. 5% 는 손 크기쯤이다.
                edge[i] = _local_edge(em, px, py)
            # pts 는 판정층이 그대로 받는 3-튜플(좌표 + 가시성).
            # 좌표를 다시 맞추는 자리(join)를 두지 않기 위해 원본을 함께 둔다.
            out[name] = {"edge": edge, "xy": xy, "pts": list(pts3[:33])}
            del em, u8
        except Exception as _e:
            # 조용히 넘기지 않는다. 예외 종류를 남겨야 원인을 아는다.
            _POSE_WHY[name] = "예외 %s: %s" % (type(_e).__name__, str(_e)[:60])
            continue
    # 왜(Why) `_POSE_WHY` 를 남기나 (2026-10-01): `_part_detail_map` 는 None 을
    # 돌려주는 쪽이라 **왜**를 잃는다. 호출부가 "사람이 없었다" 와 "탐지가
    # 깨졌다" 를 구분할 수 없게 되고, 게이트가 조용히 무력화된다.
    return out or None


def _apply_region_strength(base_strength, matched, sampled,
                           strength_vec, parts, mask):
    """강도 벡터(33) → 공간 마스크 → 부위별 가중 블렌드. 보강할 부위가
    없거나 실패하면 None 을 반환한다.

    왜(Why): 33점 벡터만으로는 화면의 어느 영역을 강화할지 알 수 없다.
    sampled의 landmark 좌표로 각 점 주위에 원형 가중치를 뿌려 33×W 맵을 만든다.
    sampled 좌표를 쓰는 이유는 **결과물이 복원의 대상**이기 때문이다 — 원본의
    구도에 맞춰야 변형된 손을 원본 자리로 끌어올 수 있다.

    === 정밀 검토에서 발견한 3건 (2026-09-28, 전부 실측 재현) ===

    1) **크래시(H-1):** 예전에 `adaptive_avg_pool2d(heat, 32)[..., :lh, :lw]`
       로 크기를 맞추려 했다. 이 풀링의 출력은 **무조건 32×32**라서,
       latent가 48×48 이상(SD/SDXL 512px 전부)일 때 슬라이스로 복원되지 않고
       broadcasting 에러가 났다. 예외가 run()의 `except: pass`에 삼켜져
       **이 기능은 한 번도 실행된 적이 없었다.** → 풀링을 아예 제거했다.
       원형 blob 자체가 공간 감쇠를 갖고 있어 스무딩이 필요 없다.

    2) **강도 소거(H-2):** `heat = heat / heat.max()` 정규화를 하면 최댓값이
       항상 1.0이 된다. 그 결과 사용자가 5%를 요청해도 해당 부위는
       **100% 원본으로 덮어써졌다**(실측 20배 과다). `w` 자체가 강도이므로
       정규화하면 안 된다.
       또한 blob을 **더하면** 겹치는 랜드마크 개수만큼 강도가 누적돼
       포화(clamp 1.0)에 닿는다 — 실측에서 "0.33 요청 → 1.0 적용"이
       이 이유였다. 정규화와 별개로 고쳐야 한다.
       → **합이 아니라 최댓값(합집합)** 으로 합친다. "이 픽셀에서는 가장 강한
       보강 부위의 강도만큼 당긴다"가 사용자의 강도 의미와 정확히 일치한다.

    3) **경계 역전(M-2):** 예전 `active = vec > min(vec)` 판정은 단조 벡터에서
       전부 False가 되어 당김이 0이 되었고(강도 1.0에서 효과 소멸),
       **음수 강도에서는 정반대로** 부스트된 부위만 제외됐다.
       → "기준 강도 대비 실제로 올랐는지"로 판정한다(부호와 무관하게 설계.
         다만 현재 run() 은 eff>0 일 때만 region 경로에 진입하므로
         음수 강도는 여기에 도달하지 않는다 — 2026-10-04 감사 14차 확인).

    **한계(2026-10-05 감사 75차 정정):** run() 은 위젯 strength 가 아니라
    감쇠와 물리 상한(0.20)을 지난 eff 를 이 함수에 넘긴다. 따라서 옛
    문단의 "strength=1.0 → w=1.0 → 보강 불가" 시나리오는 도달 불가능하고,
    실제 bound 는 w = min(1.0, eff*1.6) ≤ 0.32 이다. 전역 당김 eff 위에
    이 증분이 **가산**되므로 합계 계수는 eff + w ≤ 0.52 — 원본을 넘치는
   (합계 1 초과) 일은 eff 상한이 막아준다. boost=1.6 은 기본 배율이며,
    올려도 이 bound 는 eff 쪽 상한이 지켜준다.
    """
    import torch as _t
    xy = (parts.get("sampled") or {}).get("xy")
    if not xy:
        return None                           # 보강할 부위 없음
    try:
        lh, lw = int(sampled.shape[-2]), int(sampled.shape[-1])
        heat = None
        radius = max(2, lh // 16)  # 랜드마크가 덮는 반경
        # 거리 계산은 **항상 float32** 로 한다.
        # 왜(Why)(2026-09-29 실측): d2 를 sampled.dtype(fp16)으로 계산하면
        # 최대값이 2*512^2 = 524288 으로 fp16 상한(65504)을 넘어 `inf` 가 된다.
        # 실측: 256x256 fp16 에서 13835 픽셀이 inf. 비교는 `d2 <= r^2` 이라
        # inf 는 탈락해 **결과는 우연히 맞았지만**, 그 경로는 inf 의 개수에만
        # 의존한다. 출력을 캐스팅하기 전에 inf 가 생기면 dtype 에 따라
        # true 로 판정될 수도 있다(비교는 fp32 에서 하므로 현재는 그렇지 않음).
        # 조용히 운에 기대지 않고 계산 단계에서 확실히 한다.
        ys = _t.arange(lh, dtype=_t.float32, device=sampled.device)[:, None]
        xs = _t.arange(lw, dtype=_t.float32, device=sampled.device)[None, :]
        r2 = float(radius * radius)
        thresh = abs(float(base_strength)) + 1e-9
        for i, (px, py) in enumerate(xy):
            if i >= len(strength_vec):
                break
            w = float(strength_vec[i])
            # 실제로 상향된 부위만. 기준 강도와 같으면 건드리지 않는다.
            if w <= 1e-8 or abs(w) <= thresh:
                continue
            cy, cx = int(py * lh), int(px * lw)
            d2 = (ys - cy) ** 2 + (xs - cx) ** 2
            # heat 는 sampled.dtype 을 유지한다(반환 텐서가 입력과 같은
            # dtype 이어야 호출부의 out + _inc 가 안전하다). 거리 계산만
            # float32 이므로 heat 를 만들 때 한 번만 캐스팅한다.
            blob = ((d2 <= r2).to(sampled.dtype) * w)
            # 합이 아니라 **최댓값**(합집합). 더하면 겹친 개수만큼 강도가
            # 누적돼 clamp 1.0에 닿아 사용자가 0.33을 줬는데 1.0이 적용된다.
            if heat is None:
                heat = blob[None, None]
            else:
                heat = _t.maximum(heat, blob[None, None])
        if heat is None or float(heat.max()) <= 1e-8:
            return None                       # 보강된 부위 없음
        heat = heat.clamp(0.0, 1.0)          # 정규화 금지, 상한만
        region = heat * (mask if mask is not None else 1.0)
        # **추가분**만 반환한다. 왜(Why): 예전엔 `out + region*(...)`
        # 을 반환했는데 호출부가 그것을 **대체로** 사용해버려서
        # strength_original 의 전역 블렌드 전체가 유실됐다
        # (2026-09-28 실측: region 미발동 대조군 대비 전역 전달량
        #  15~27%, 커버리지 19%). 전역 블렌드에 더하면
        # "보강 부위만 더 세게, 나머지는 그대로"가 된다.
        return region * (matched - sampled)
    except Exception as e:
        _log(f"[GoRi Consistency Keeper] ⚠ 부위별 복원 계산 실패 "
             f"({type(e).__name__}: {e}) — 전역 당김으로 진행합니다")
        return None


# PART_REGIONS 은 kp_judge 로 이동했다 (judge_region_allowance 가 직접 써서).
# ck.PART_REGIONS 접근 계약은 kp_judge 재수출로 유지한다.


# 복원 우선 부위 — 뉘게되기 쉽고(디테일 손실), 원본 픽셀이 신뢰할 만한 부위
DETAIL_CRITICAL = ("hand_left", "hand_right", "leg_left", "leg_right",
                   "face")


_NO_BOOST_NOTED = False


def _probe_detail_direction(vae, sampled, orig_ref, out):
    """원본을 당겼을 때 디테일이 늘는지 줄는지 **재서** 말한다 (미해결 5-1).

    왜(Why) 이게 먼저인가: 부위별 상향은 "원본은 살아있는데 결과가 뭉개졌다" 는
    가정 위에 세워졌다. 그 가정이 **거짓이면** 설계 방향이 통째로 뒤집힌다.

    왜(Why) 환경변수로 꺼는가 (2026-10-01): 항상 돌리면 프롬프트마다 디코딩
    3회가 추가돼 **디코딩 예산 검사**(R56)가 깨진다. 계측 장치가 정작 제품
    경로를 망가뜨릴 수는 없다. `GORI_PROBE_PHYSICS=1` 일 때만 돈다 — 측정
    전용 계기다.
    """
    if vae is None:
        return
    # 이 파일은 모듈 임포트를 지역에서 한다(아래 함수들도 모두 그렇다).
    import os as _os
    if _os.environ.get("GORI_PROBE_PHYSICS", "0") != "1":
        return
    try:
        def _dens(lat):
            # 왜(Why) `_decode_latent_rgb` 인가 (2026-10-01): `_decode_capped`
            # 는 **torch 텐서 (1,C,H,W)** 를 돌려준다. `_edge_map_from_rgb` 는
            # numpy **HWC 배열**을 받는다. 다른 디코더를 썼다가
            # `too many indices for tensor of dimension 4`
            # 오류로 조용히 실패했다. 이 함수가 RGB numpy 를 반환하는 계약이다.
            arr = _decode_latent_rgb(vae, lat)
            if arr is None:
                raise RuntimeError("디코드 결과 없음")
            em = _edge_map_from_rgb(arr)
            if em is None:
                raise RuntimeError("에지맵 없음")
            return float(em.mean())
        _s = _dens(sampled)
        _r = _dens(orig_ref)
        _o = _dens(out)
    except Exception as e:
        # 왜(Why) 예외를 말하나: 조용히 `return` 하니 "측정이 안 됐다" 와
        # "측정 결과가 안 바뀌었다" 를 구분할 수가 없었다. 사흘 만에 두 번째다.
        _log(f"[GoRi Consistency Keeper] 물리 방향 실측 실패 "
             f"({type(e).__name__}: {str(e)[:90]}) — 판정 보류")
        return
    _d_out = (_o - _s) / _s * 100.0 if _s > 1e-9 else 0.0
    _d_ref = (_o - _r) / _r * 100.0 if _r > 1e-9 else 0.0
    _verdict = ("당기면 살아난다" if _d_out > 0 else "당기면 뭉개진다")
    _log("[GoRi Consistency Keeper] 물리 방향 실측 "
         f"샘플 {_s:.4f} / 원본 {_r:.4f} / 결과 {_o:.4f} — "
         f"결과는 샘플 대비 {_d_out:+.1f}%, 원본 대비 {_d_ref:+.1f}% "
         f"⇒ {_verdict}")


_POSE_WHY = {}


# 심각 사유 접두어. `_pose_gate_message` 가 ⚠ 승격을 이 값으로만 판정한다.
# 생산지는 `_part_detail_map` 안의 세 문자열이다 — "디코드 결과 없음" /
# "에지 맵 계산 실패" / "예외 %s: ...". 사유 문구를 고칠 때 이 짝을 함께
# 고치지 않으면 ⚠ 가 조용히 사라진다 (2026-10-04 감사 46차, 승인 처리).
_SEVERE_WHY_PREFIXES = ("디코드", "에지", "예외")


# 낮춘 임계값 세션. 0.5 세션이 놓친 **사람 있는** 이미지를 되찾기 위한 것.
_POSE_LOOSE = [None]


_POSE_LOOSE_CONF = 0.3


def _pose_retry_low_conf(arr, _mp):
    """임계값 0.3 세션으로 한 번 더 시도한다 (13장 실측 기반).

    왜(Why) 별도 세션인가: `min_pose_detection_confidence` 는 **생성 시점**에
    고정된다. 세션을 새로 만들어야 한다. 한 번만 만들고 재사용한다.
    """
    try:
        if _POSE_LOOSE[0] is None:
            from mediapipe.tasks.python import vision as _V
            _BO = _find_base_options()
            if _BO is None:
                # _pose_landmarker 와 같은 이유: 없으면 TypeError 가 나고
                # transient error 로 잡힌다. 여기서도 꺼짐으로 알린다.
                _note_pose_unavailable()
                return None
            _opts = _V.PoseLandmarkerOptions(
                base_options=_BO(
                    model_asset_path=_pose_model_path()),
                running_mode=_V.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=_POSE_LOOSE_CONF,
                output_segmentation_masks=False)
            _POSE_LOOSE[0] = _V.PoseLandmarker.create_from_options(_opts)
        img = _mp.Image(image_format=_mp.ImageFormat.SRGB, data=arr)
        return _POSE_LOOSE[0].detect(img)
    except Exception as e:
        _note_pose_error('_pose_retry_low_conf', e)
        return None


def _pose_gate_message(why):
    """판정 게이트가 landmark 를 못 얻은 사유 → 로그 한 줄.

    왜(Why) 함수를 뺐나 (2026-10-01): 게이트 분기가 `run()` 안에서 인라인으로
    로그를 만들었는데, 그 **메시지 내용**을 테스트할 방법이 없었다. 사유별
    ⚠ 표시 규칙이 조용히 바뀌면 아무도 몰랐다. 함수로 빼면 규칙 자체를 고정한다.
    """
    # 왜(Why) "포즈 모델 없음" 이 빠졌나 (2026-10-04 감사 5차): 그 유일한
    # producer 는 4차에서 dead branch 로 지웠다. 소비자만 남아 있으면
    # 규칙이 죽은 문자열을 관리한다.
    severe = why.startswith(_SEVERE_WHY_PREFIXES)
    tag = "⚠ " if severe else ""
    return (f"[GoRi Consistency Keeper] {tag}판정 게이트: "
            f"원본 landmark 없음 — {why}"
            + ("" if severe else
               " → 제한 없이 진행합니다(막을 부위 판단 근거 없음)"))


def _note_pose_why(key, msg):
    """포즈 실패 사유를 키마다 **한 번만** 말한다 (무음 실패 제거).

    왜(Why) 한 번뿐인가: 같은 사유가 여러 노드에서 반복되면 로그를 읽을 수
    없다. 하지만 **한 번도 안 나오면** 조용한 실패가 된다. 한 번이 정답이다.
    """
    _seen = _POSE_WHY.setdefault("_said", set())
    if key in _seen:
        return
    _seen.add(key)
    _log(msg)


def _note_no_boost(worst, region, thresh, max_r=0.0, max_rg=""):
    """부위별 상향이 없었던 이유를 **한 번만** 말한다 (조용한 무동작 방지)."""
    global _NO_BOOST_NOTED
    if _NO_BOOST_NOTED:
        return
    _NO_BOOST_NOTED = True
    if not region:
        if max_r <= 1e-6:
            _log("[GoRi Consistency Keeper] 부위별 복원: 판단 불가 "
                 f"(원본 에지 최대 {max_r:.5f} @{max_rg} — 임계 1e-6 미만)")
        else:
            # 왜(Why) 이 분기가 필요한가 (2026-10-01 실측): 에지는 있는데
            # **손실이 0 이다** 는 전혀 다른 상태였다. 예전 코드는 둘을 같은
            # "에지가 0" 문구로 뭉뚱그려서 한참 잘못된 방향을 봤다.
            _log(f"[GoRi Consistency Keeper] 부위별 복원: 상향할 곳 없음 "
                 f"(원본 에지는 있으나 결과물이 더 날카로움 — 원본 에지 최대 "
                 f"{max_r:.4f} @{max_rg})")
        return
    # 왜(Why) 숫자 비교를 단정하지 않나 (2026-10-04 감사 13차): 이 로그는
    # "손실이 임계 미달"과 "판정 게이트가 부위를 막음" 두 경우가 같이 온다.
    # 부위별 손실 재계산(아래 루프)은 게이트를 모르므로 worst 가 임계 이상일
    # 수도 있다 — "{x}% < 임계" 를 무조건 쓰면 거짓말이 된다.
    _log(f"[GoRi Consistency Keeper] 부위별 복원: 상향하지 않았습니다 "
         f"(가장 손실 큰 부위 {region} {worst:.0%} — 임계 {thresh:.0%} 미달이거나 "
         f"판정 게이트가 막은 부위)")


def detail_boost(parts_ref, parts_samp, strength, boost=1.6, thresh=0.35,
                 allow=None):
    """부위별 adaptive 강도 → (강도 배열|None, 로그 문자열).

    원본이 더 살아있는(=에지 밀도가 높은) 부위만 강도를 올려 그 부위를
    원본으로 당겨온다. 원본도 뭉개진 부위는 건드리지 않는다 — 원본을
    신뢰할 수 없기 때문(원본이 틀렸으면 복원도 틀린다).

    **중요**: 이 함수는 "손가락이 5개여야 한다"를 판정하지 않는다. latent에
    텍스트는 개입하지 않는다. 산술로 하는 것은 단 하나 —
    "원본과 이 부위가 얼마나 달라졌는가"다. 원본이 정확할 때만 효과가 있다.

    왜(Why) allow 가 있나 (2026-10-01): 위 docstring의 "원본이 정확할 때만"을
    실제로 지키는 장치다. 이전까지는 **에지가 0 인지**로 대신 판단했는데
    그것은 "안 보인 것"과 "없어진 것"을 구분하지 못한다. 판정층(work_status
    10절)이 판정을 내려주면 그걸 받는다.

    왜(Why) 기본값이 None 인가: 판정이 없으면 **제한 없이** 기존대로 동작해야
    한다. opt-in 구조라 켜기 전까지 결과물이 바뀌지 않는다.
    allow 는 {부위명: 0.0|1.0} — `judge_region_allowance` 가 만든다.
    """
    try:
        import numpy as _np
        if not parts_ref or not parts_samp:
            return None, ""
        ref = (parts_ref.get("original") or {}).get("edge")
        samp = (parts_samp.get("sampled") or {}).get("edge")
        if not ref or not samp:
            return None, ""
        arr = _np.full(len(ref), float(strength), dtype=_np.float32)
        boost_list = []
        # 왜(Why) 게이트를 **먼저** 정규화하나: 안에서 형식이 틀린 값을 만날 때
        # 그 부위만 건너뛰면, 한 항목의 오타가 **전체 기능을 조용히 꺼버린다**
        # (silent degradation). 그래서 한 번에 청소한다. 해석 불가 항목은
        # "제한 없음" 으로 본다 — 오타로 부위를 막아버리는 게 더 나쁘다.
        # 그리고 그 사실은 한 번 말한다.
        gate = None
        if allow is not None:
            gate = {}
            if isinstance(allow, dict):
                _dropped = 0
                for _k, _v in allow.items():
                    try:
                        gate[str(_k)] = float(_v)
                    except (TypeError, ValueError):
                        _dropped += 1
                if _dropped:
                    _log(f"[GoRi Consistency Keeper] ⚠ 판정 허용도에서 해석 불가 "
                         f"항목 {_dropped}개를 무시했습니다 (제한 없음으로 처리)")
            else:
                gate = None
        for region, idxs in PART_REGIONS.items():
            if region not in DETAIL_CRITICAL:
                continue
            # 판정에서 미판정(allow 0)인 부위는 원본을 신뢰하지 못하므로
            # 건드리지 않는다. 올리는 것이지 줄이는 것이 아니므로 continue.
            if gate is not None and gate.get(region, 1.0) <= 0.0:
                continue
            r = sum(ref[i] for i in idxs) / len(idxs)
            s = sum(samp[i] for i in idxs) / len(idxs)
            if r <= 1e-6:
                # 원본도 에지가 0 = 원본부터 뭉개졌다. 원본을 신뢰할 수 없으므로
                # 건드리지 않는다(원본이 틀렸으면 복원도 틀린다).
                continue
            loss = (r - s) / r  # 0~1 (1 = 전부 손실)
            if loss >= thresh:
                for idx in idxs:
                    arr[idx] = min(1.0, strength * boost)
                boost_list.append(f"{region}({loss:.0%})")
        if boost_list:
            return arr, ", ".join(boost_list)
        # 왜(Why) 여기서 말하나 (2026-10-01 실측): 이 경로는 **한 번도 켜지지
        # 않았다** — 로그 0건, 실패 0건. 조용히 None 을 돌려주는 구조라
        # "안 되는 것" 과 "될 필요가 없는 것" 이 구분되지 않았다. 그래서 어떤
        # 부위가 얼마나 손실됐는지를 한 번 말한다. 판정 게이트는 이 경로에만
        # 걸려 있으므로 여기가 조용하면 게이트도 조용하다.
        _worst = 0.0
        _worst_r = ""
        _max_r = 0.0
        _max_rg = ""
        _stats = []
        for _rg, _idxs in PART_REGIONS.items():
            if _rg not in DETAIL_CRITICAL:
                continue
            _r = sum(ref[i] for i in _idxs) / len(_idxs)
            _s = sum(samp[i] for i in _idxs) / len(_idxs)
            _stats.append(f"{_rg} {_r:.4f}->{_s:.4f}")
            if _r > _max_r:
                _max_r = _r
                _max_rg = _rg
            if _r <= 1e-6:
                continue
            _l = (_r - _s) / _r
            if _l > _worst:
                _worst = _l
                _worst_r = _rg
        # 왜(Why) 숫자를 붙이나 (2026-10-01): "에지가 0" 이라는 말은
        # **0 인지 매우 작은 건지** 구분하지 못했다. 16×16 셀 → 5% 창으로
        # 바꿨는데도 여전히 0 이라 원본 해상도 자체를 의심하게 됐다.
        _log("[GoRi Consistency Keeper] 부위 에지 실측 (원본->결과): "
             + " / ".join(_stats))
        _note_no_boost(_worst, _worst_r, thresh, _max_r, _max_rg)
        return None, ""
    except Exception as _e:
        # 왜(Why) 로그를 남기나 (2026-10-04 감사 47차): 여기서 침묵하면
        # trust_gate=False 기본값에서는 이 브랜치에 다른 로그가 전혀 없어
        # 부위별 복원이 조용히 꺼진다 — "조용히 꺼버린다(silent
        # degradation)" 주석이 말하는 것이다.
        # 호출부의 "부위별 복원 실패" 로그는 _apply_region_strength 예외만
        # 잡는다. (None, "") 은 정상 무개입 경로도 반환하므로 호출부 else
        # 로그는 옳지 않다.
        _log("[GoRi Consistency Keeper] ⚠ 부위별 디테일 분석 실패 "
             f"({type(_e).__name__}: {_e}) — 부위별 복원을 건너뛰고 "
             "전역 당김만 적용")
        return None, ""


def judge_reference_trust(u8):
    """uint8 HWC RGB 원본 -> 판정 dict. 검출 실패도 미판정으로 친다.

    왜(Why) 프로덕션 경로가 이 함수를 **부르지 않는가** (2026-10-01 실측):
    `run()` 은 이미 `_part_detail_map` 이 디코드하며 얻은 landmark 를 가지고
    있어서 `judge_points(_pm["original"]["pts"])` 를 직접 부른다(R75). 이
    래퍼를 부르면 **VAE 디코드를 한 번 더** 하게 되어
    `new_vae_decode_in_per_frame_path` 와 같은 낭비가 된다.
    그래서 판정의 **진입점은 `judge_points`** 이고 이건 u8 -> 판정 변환이다.
    지우지 않는 이유: 테스트가 `u8` 입력에서 판정까지 한 번에 확인한다.
    판정 규칙 자체(`judge_points`)를 두 번 실행시키지 않고 검증하는 경로다.
    """
    return judge_points(_pose_landmarks_from_tasks(u8, with_visibility=True))


def _repair_mask_from_regions(xy, regions, lh, lw, device):
    """landmark 좌표 + 파손 부위 -> latent 해상도 당김 마스크 (1,1,lh,lw).

    _person_mask_from_rgb 와 같은 원리의 blob 이지만 **파손 부위의
    landmark 에만** 뿌린다. 덮을 부위가 없으면 None.

    왜(Why) 반경이 부위 보강(`_part_detail_map` 의 `lh // 16`)보다
    넓은가: 보강은 landmark
    한 점 주변을 세게 당기면 되지만, 당김은 파손된 부위 **전체**를 다시
    그려야 한다 — 손 크기쯤 되는 lh//8 이다. 코어(1.0) 주위에 0.5
    완충대를 한 겹 두는 것은 noise_mask 의 급경계가 재조합 티를 내는
    것을 막기 위함이다.
    """
    try:
        import torch as _t
        idxs = []
        for _r in regions:
            idxs.extend(PART_REGIONS.get(str(_r), ()))
        if not idxs or not xy:
            return None
        ys = _t.arange(lh, dtype=_t.float32, device=device)[:, None]
        xs = _t.arange(lw, dtype=_t.float32, device=device)[None, :]
        radius = max(3, lh // 8)
        core_r2 = float(radius * radius)
        outer_r2 = core_r2 * 2.0
        heat = None
        for i in idxs:
            if i >= len(xy):
                break
            try:
                px, py = float(xy[i][0]), float(xy[i][1])
            except (TypeError, ValueError, IndexError):
                continue
            cy = max(0, min(lh - 1, int(py * lh)))
            cx = max(0, min(lw - 1, int(px * lw)))
            d2 = (ys - cy) ** 2 + (xs - cx) ** 2
            w = _t.where(d2 <= core_r2, 1.0,
                         _t.where(d2 <= outer_r2, 0.5, 0.0))
            if heat is None:
                heat = w[None, None]
            else:
                heat = _t.maximum(heat, w[None, None])
        if heat is None:
            return None
        return heat.clamp(0.0, 1.0)
    except Exception as _me:
        _log("[GoRi Consistency Keeper] ⚠ 당김 마스크 계산 실패 "
             "(%s: %s) — 당기지 않습니다"
             % (type(_me).__name__, str(_me)[:80]))
        return None


def _learn_append(record):
    """판정 기록을 로컬 파일에 한 줄(JSONL)로 쌓는다. 출력 무영향.

    왜(Why) 로컬 전용인가 (사용자 확정 2026-10-05): 별도 서버·전송이
    없다. 이 파일은 학습 데이터 축적용 개인 기록이고 .gitignore 로
    저장소에서도 제외된다. 기록 실패는 once 로 한 번만 말한다 — 매
    실행마다 같은 실패를 반복 인쇄하면 로그가 쓰레기가 된다.
    """
    try:
        import json as _json
        import os as _os
        import time as _time
        # 왜(Why) _os.sep 문자열 결합인가: R61 계약상 경로 모듈 사용은
        # 동봉 모델 경로 조립에 최소한으로 묶여 있다. 이 폴더 하나를 더
        # 열려면 dirname/abspath 1회만 쓰고 나머지는 결합한다.
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _d = _here + _os.sep + "learn_log"
        _os.makedirs(_d, exist_ok=True)
        rec = dict(record)
        rec["ts"] = _time.strftime("%Y-%m-%dT%H:%M:%S")
        rec["spec"] = _ANATOMY_SPEC_VERSION
        with open(_d + _os.sep + "keeper_verdicts.jsonl", "a",
                  encoding="utf-8") as _f:
            _f.write(_json.dumps(rec, ensure_ascii=True) + "\n")
    except Exception as _le:
        _note_once("learn_write",
                   "[GoRi Consistency Keeper] ⚠ 학습 기록 저장 실패 "
                   "(%s: %s) — 출력에는 영향이 없습니다"
                   % (type(_le).__name__, str(_le)[:80]))


_SKELETON_PULL_STRENGTH = 0.12


# BlazePose 33점 골격 연결 (렌더링에 쓰는 것만).
_SKELETON_EDGES = (
    (11, 12), (11, 23), (12, 24), (23, 24),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (27, 31), (28, 30), (28, 32),
)


_SKELETON_HEAD = 0


def _render_skeleton_image(xy, h, w, device):
    """교정된 landmark 좌표 -> 골격 이미지 (1,h,w,3) 0~1 float32.

    검은 바탕에 흰 뼈대. 이 이미지가 "스탠다드 픽셀 데이터"의 1차
    형태다 — 나중에 부위별 정상 픽셀 라이브러리나 학습 확정 비율
    렌더링으로 같은 슬롯에 교체 주입할 수 있게 함수 하나로 둔다
    (2026-10-05 사용자: 픽셀 데이터만 더 주입하면 성능 향상이 쉽다).

    왜(Why) PIL 인가: ComfyUI 런타임에 항상 있고, 선·원 그리기는
    텐서 산술보다 낫다. 실패 시 None — 당김 스킵이 안전 방향이다.
    """
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (int(w), int(h)), (0, 0, 0))
        dr = ImageDraw.Draw(img)
        lw = max(2, int(h) // 256)

        def _px(i):
            if i >= len(xy):
                return None
            try:
                fx, fy = float(xy[i][0]), float(xy[i][1])
            except (TypeError, ValueError, IndexError):
                return None
            return (fx * w, fy * h)

        for a, b in _SKELETON_EDGES:
            pa, pb = _px(a), _px(b)
            if pa and pb:
                dr.line([pa, pb], fill=(255, 255, 255), width=lw)
        for i in range(min(len(xy), 33)):
            p = _px(i)
            if p:
                r = lw * (3 if i == _SKELETON_HEAD else 2)
                dr.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r],
                           fill=(255, 255, 255))
        import torch as _t
        _arr = _t.frombuffer(img.tobytes(), dtype=_t.uint8)
        _arr = _arr.reshape(1, int(h), int(w), 3).to(
            dtype=_t.float32, device=device) / 255.0
        return _arr
    except Exception as _re:
        _log("[GoRi Consistency Keeper] ⚠ 골격 렌더링 실패 (%s: %s) — "
             "당김을 건너뜁니다" % (type(_re).__name__, str(_re)[:80]))
        return None


def _skeleton_pull_pass(vae, sampled, out, pm, dcache,
                        orig_rgb=None):
    """파손 판정 -> 스탠다드 골격 참조로 국소 당김 -> 재판정.

    수술(재샘플링)을 대체하는 경로 (2026-10-05 사용자 결정): 키퍼의
    DNA("다시 그리지 않는다")를 지키기 위해, 판정기 좌표를 스탠다드
    규격으로 교정해 그린 골격 이미지를 VAE 로 인코딩하고 그 latent
    쪽으로 파손 부위만 당긴다. 샘플러·모델·조건이 필요 없다 —
    비용은 VAE 인코딩 1회와 디코딩 2회(판정)뿐이다.

    왜(Why) drift 감쇠를 쓰지 않나: _damp_norm 감쇠는 "같은 포즈의
    참조"를 위한 장치다. 골격 참조는 의도적으로 기하가 다르므로 그
    감쇠를 적용하면 항상 최대 감쇠로 당김이 죽는다. 대신 재판정
    폐기가 안전장치다 — 당긴 뒤 판정이 나아지지 않으면 되돌린다.

    왜(Why) 손은 당기지 않나 (v1): 손가락 6개 같은 살 수준 파손은
    골격 당김으로 지워진다는 보장이 없고, 손 부위를 골격 스텁으로
    당기면 오히려 손을 지운다. 손 판정은 기록만 남긴다(learn_log).
    나중에 부위별 정상 픽셀 라이브러리가 생기면 손도 같은 슬롯으로
    확장한다.

    반환: (out, 기록 dict). 기록은 learn_log 와 실측의 원천이다.
    """
    rec = {"kind": "skeleton_pull", "triggered": False}
    if vae is None:
        _note_once("pull_vae",
                   "[GoRi Consistency Keeper] repair_enable 을 켰지만 "
                   "vae 가 없습니다 — 골격 참조를 인코딩할 수 없어 당김 "
                   "없이 반환합니다")
        return out, rec
    s_pts = (pm or {}).get("sampled", {}).get("pts")
    if not s_pts:
        _log("[GoRi Consistency Keeper] 당김: 결과물 landmark 없음 — "
             "파손 판정을 못 하므로 건너뜁니다")
        return out, rec
    pose_v = judge_points(s_pts, physics=True)
    rec["pose_verdict"] = pose_v.get("verdict")
    rec["pose_checks"] = pose_v.get("checks", [])
    try:
        import numpy as _np_r
        _arr = _decode_latent_rgb(vae, sampled, cache=dcache)
        _u8 = (None if _arr is None else
               (_np_r.clip(_arr, 0.0, 1.0) * 255.0).astype(_np_r.uint8))
    except Exception:
        _u8 = None
    if _u8 is None:
        # 왜(Why) 말하고 넘어가나 (2026-10-07 감사): _u8 이 None 이면
        # 아래부위·발가락·발·피부·얼굴 판독이 전부 조용히 건너뛰어
        # learn_log 에 빈 값만 쌓인다 — 건너뜀 자체가 기록돼야 한다.
        _note_once("pull_pixel_read",
                   "[GoRi Consistency Keeper] ⚠ 결과물 픽셀 판독용 디코드 "
                   "실패 — 부위·발가락·발·피부 판독을 건너뛰고 기록만 "
                   "부분적으로 남깁니다")
    # 왜(Why) 한 번만 호출하나: 아래 부위 판독도 같은 _u8 로
    # _hand_landmarks_from_tasks 를 돌려 mediapipe 추론이 2배였다
    # (2026-10-07 감사). 결과를 재사용한다.
    _hs21 = _hand_landmarks_from_tasks(_u8) if _u8 is not None else None
    hand_v = judge_hands(_hs21)
    rec["hand_verdict"] = hand_v.get("verdict")
    # 개수 세기용 저신뢰 패스 (2026-10-05, v1.9.16). 손가락 판정 검출은
    # 가려진 손을 놓치므로(3팔 실측: 1/3) 개수는 별도 0.1 패스에서 센다.
    # None 은 "못 셌다" — 위반이 아니라 판단 보류다.
    _cnt = _hand_count_from_tasks(_u8) if _u8 is not None else None
    rec["hand_count"] = _cnt
    _count_bad = _cnt is not None and _cnt > _HAND_COUNT_MAX_OK

    # 부위 판독 (2026-10-05, v1.9.17): 27부위 카탈로그 전부를 결과물에서
    # 읽는다 — 기록이 learn_log 로 쌓이는 것이 "키퍼의 학습 데이터"다.
    # 판독 실패 부위는 absent 로 기록되지 위반이 아니다 (판정은 손 개수
    # 패스만 한다 — 검증 가능한 근거가 있는 것만).
    _hands21 = _hs21
    _hand_map = {}
    for _g in (_hands21 or []):
        if not _g:
            continue
        # 왜(Why) 소문자로 정규화하나: handedness 는 Left 와 Right 라는
        # 대문자로 오고 PART_CATALOG 키는 소문자다 — 그대로 두면 손이
        # 항상 absent 가 된다 (2026-10-05 스모크 실측).
        _hn = str(_g[0][2]).lower() if len(_g[0]) >= 3 else "?"
        _key = _hn if _hn in ("right", "left") else "?"
        _hand_map.setdefault(_key, _g)
    _face_groups = _face_pts_from_tasks(_u8) if _u8 is not None else None
    rec["face_count"] = (len(_face_groups)
                         if _face_groups is not None else None)
    _parts = _read_parts(s_pts, _hand_map,
                         _face_groups[0] if _face_groups else None)
    _frep = {}
    for _side in ("right", "left"):
        # 왜(Why) capitalize 폴백을 뺐나 (2026-10-07 감사): _hand_map 은
        # 위에서 handedness 를 소문자 right·left·? 표기로만 넣는데
        # .capitalize() 키("Right") 는 그 빌더에 존재하지 않는 죽은 폴백이다.
        _g = _hand_map.get(_side)
        if _g:
            _frep[_side] = _finger_report(_g)
    rec["fingers"] = _frep
    _toes = {}
    if _u8 is not None and s_pts and len(s_pts) >= 33:
        # 왜(Why) 2026-10-07 감사로 좌우를 바꿨나: BlazePose 원표기는
        # 27/29/31 = 왼쪽 발목/뒤꿈치/발끝, 28/30/32 = 오른쪽이다. 구 코드는
        # 이를 뒤집어 toes_right 에 왼쪽 발 기록이 쌓였다 (anatomy_parts
        # 좌우 반전 수정과 같은 감사).
        for _side, (_ia, _ih, _it) in (("right", (28, 30, 32)),
                                       ("left", (27, 29, 31))):
            try:
                _toes[_side] = _toe_blobs(_u8, s_pts[_ia], s_pts[_ih],
                                          s_pts[_it])
            except Exception:
                _toes[_side] = None
    rec["toes"] = _toes
    # toes 는 픽셀 원천이라 _read_parts 가 못 읽는다 — 블롭 판독값으로
    # 카탈로그 항목을 덮어쓴다 (판독 불가면 absent 유지).
    # 왜(Why) 요약이 덮어쓰기 뒤인가: summarize 를 먼저 하면 덮어쓴 값이
    # 기록에 안 들어가 덮어쓰기 자체가 죽은 코드가 된다 (2026-10-06 실측).
    for _side, _key in (("right", "toes_right"), ("left", "toes_left")):
        _parts[_key] = {"present": _toes.get(_side) is not None,
                        "vis": 1.0, "pos": None, "src": "pixel",
                        "count": _toes.get(_side)}
    rec["parts"] = _summarize_parts(_parts)

    # 발 개수 (2026-10-06, v1.9.18). BlazePose 는 발 2개 고정 토폴로지라
    # 다리 개수를 못 센다 — 팔 3개와 같은 사각지대다. 발목 아래 피부
    # 덩어리 중 발끝 랜드마크가 하나도 없는 것을 여분 다리 증거로 본다.
    # 발이 크롭되면 영역 자체가 없어 판단 불가(None)다 — 위반이 아니다.
    _feet = None
    _foot_bad = False
    if _u8 is not None and s_pts and len(s_pts) >= 33:
        try:
            _skin0 = _skin_stats(_u8, s_pts)
            _fcomps = _foot_comps(_u8, s_pts, _skin0) if _skin0 else None
            if _fcomps is not None:
                _t31 = float(s_pts[31][0])
                _t32 = float(s_pts[32][0])
                _unc = _unclaimed_feet(_fcomps, _t31, _t32)
                _feet = {"zone": True, "comps": len(_fcomps),
                         "unclaimed": len(_unc),
                         "detail": [[c[0], c[1], c[2]] for c in _fcomps]}
                _foot_bad = len(_unc) > 0
        except Exception:
            _feet = None
            _foot_bad = False
    rec["feet"] = _feet
    rec["foot_violation"] = _foot_bad

    # 피부색은 원본을 따라간다 (2026-10-05 사용자 확정): 원본과 결과의
    # 피부 통계를 **각자의** pose landmark 패치에서 재어 편차를 기록한다.
    # 프레이밍이 달라도 각자의 부위에서 읽으므로 성립한다. 편차 큼은
    # 외계 피부·변질 후보 — 임계는 PROVISIONAL 이고 판정 게이트는 아직
    # 안 건다 (분포 축적 후 확정).
    _skin = None
    if orig_rgb is not None and _u8 is not None:
        try:
            _o_pts = _pose_landmarks_from_tasks(orig_rgb,
                                                with_visibility=True)
            _skin = _skin_deviation(_skin_stats(orig_rgb, _o_pts),
                                    _skin_stats(_u8, s_pts))
        except Exception:
            _skin = None
    rec["skin_dev"] = _skin
    # 파손 부위: 평소엔 포즈 순서 검사만 보고 손은 골격 당김 범위 밖(v1).
    # **개수 위반일 때만** 예외다 — 스탠다드 골격은 팔 2개라 여분 팔
    # 영역에는 뼈대가 없고, 그 방향으로 당기면 여분 팔을 배경 쪽으로
    # 누른다. 어느 쪽이 여분인지 판별 근거가 없으므로(손목 매칭은 끼운
    # 손에서 오판 실측) 양손·양팔을 함께 덮는다.
    # 다리도 같다 (2026-10-06, v1.9.18): 골격은 다리 2개라 여분 다리
    # 영역에 뼈대가 없고, 양다리를 함께 덮는다. 어느 쪽이 여분인지는
    # 발끝 랜드마크가 없는 발이라 판별 근거가 없다.
    regions = _repair_regions_from_verdicts(pose_v, None)
    if _count_bad:
        regions.update(("hand_left", "hand_right",
                        "arm_left", "arm_right"))
    else:
        regions = {r for r in regions if not str(r).startswith("hand")}
    if _foot_bad:
        regions.update(("leg_left", "leg_right"))
    rec["regions"] = sorted(regions)
    rec["count_violation"] = _count_bad
    _pre_fail = sum(1 for c in pose_v.get("checks", [])
                    if not c.get("ok", True))
    if not regions or (_pre_fail == 0 and not _count_bad
                       and not _foot_bad):
        _log("[GoRi Consistency Keeper] 당김: 파손 판정 없음 "
              "(pose=%s hand=%s count=%s foot=%s) — 0원 통과"
              % (pose_v.get("verdict"), hand_v.get("verdict"), _cnt,
                 None if _feet is None else _feet.get("unclaimed")))
        return out, rec
    # 스탠다드 교정. 교정이 안 나오면 당길 근거가 없다 — 위반 좌표를
    # 그대로 그리면 그 좌표를 강화하는 꼴이므로 하지 않는다.
    fixed_pts = _correct_order_violations(s_pts, pose_v.get("checks", []))
    if fixed_pts is None:
        if not _count_bad and not _foot_bad:
            _log("[GoRi Consistency Keeper] 당김: 교정 좌표를 만들지 "
                 "못했습니다 — 건너뜁니다")
            return out, rec
        # 개수 위반은 좌표 교정이 대상이 아니다 (2026-10-05). 물리 순서가
        # 정상이면 결과 좌표 그대로가 스탠다드 골격이고, 여분 팔 영역에는
        # 뼈대가 없어 그 방향의 당김이 여분 팔을 배경 쪽으로 누른다.
        # 여분 다리도 같다 (2026-10-06) — 골격은 다리 2개라 여분 다리
        # 영역에 뼈대가 없어 그 방향으로 당기면 배경 쪽으로 눌린다.
        fixed_pts = list(s_pts)
    rec["triggered"] = True
    # 왜(Why) 미리 False 로 두나: 트리거 후 조기 반환(렌더/인코딩/정렬/
    # 마스크 실패)에서도 kept 키가 항상 있어야 소비자·테스트가 안전하다.
    # 재판정에 도달하면 실제 값으로 덮어쓴다.
    rec["kept"] = False
    rec["pre_fail"] = _pre_fail
    rec["eff"] = _SKELETON_PULL_STRENGTH
    import time as _time
    _t0 = _time.perf_counter()
    try:
        # 왜(Why) _vae_pixel_factor_for 인가: "* 8" 하드코딩은
        # Qwen(픽셀 계수 16) 골격 참조를 1/2 해상도로 그렸다
        # (2026-10-07 감사).
        _fac = _vae_pixel_factor_for(vae)
        # 왜(Why) if 문인가 (2026-10-07 감사): 삼항이 튜플 전체에 붙는
        # 연산자 우선순위 때문에 `_u8 is None` 일 때도 `_u8.shape[0]` 을
        # 먼저 평가해 AttributeError 로 Qwen 폴백 경로가 죽었다.
        if _u8 is not None:
            _h, _w = int(_u8.shape[0]), int(_u8.shape[1])
        else:
            _h, _w = (int(sampled.shape[-2]) * _fac,
                      int(sampled.shape[-1]) * _fac)
        _skel = _render_skeleton_image(
            [(p[0], p[1]) for p in fixed_pts], _h, _w, sampled.device)
        if _skel is None:
            return out, rec
        _enc = _encode_image_ref(vae, _skel)
        # 왜(Why) 이중 계약인가: _encode_image_ref 의 반환은 환경에 따라
        # LATENT dict 이거나 텐서다. _get_samples 는 dict 만 받으므로
        # 텐서면 그대로, dict 면 풀어서 쓴다 (실측: 텐서를 넣으면 None).
        _ref = (_get_samples(_enc) if isinstance(_enc, dict)
                else (_enc if hasattr(_enc, "dim") else None))
        del _skel, _enc
        if _ref is None:
            _log("[GoRi Consistency Keeper] ⚠ 골격 참조 인코딩 실패 — "
                 "당김 전 결과를 반환합니다")
            return out, rec
        _matched = _match_spatial(_ref, out)
        if _matched is None:
            _log("[GoRi Consistency Keeper] ⚠ 골격 참조 크기 정렬 실패 — "
                 "당김 전 결과를 반환합니다")
            return out, rec
        lh, lw = int(sampled.shape[-2]), int(sampled.shape[-1])
        mask = _repair_mask_from_regions(
            (pm.get("sampled") or {}).get("xy"), regions, lh, lw,
            sampled.device)
        if mask is None:
            return out, rec
        # 왜(Why) dtype 캐스팅인가: _repair_mask_from_regions 는
        # float32 를 만든다. 전역 블렌드는 _mask 를 sampled.dtype 로
        # 바꿔 쓰는데 여기서 안 바꾸면 fp16 실행에서 당김 결과가
        # float32 로 승격됐다(2026-10-07 감사).
        mask = mask.to(device=out.device, dtype=out.dtype)
        _pulled = out + _SKELETON_PULL_STRENGTH * mask * (_matched - out)
    except Exception as _pe:
        _log("[GoRi Consistency Keeper] ⚠ 골격 당김 실패 (%s: %s) — "
             "당김 전 결과를 반환합니다"
             % (type(_pe).__name__, str(_pe)[:90]))
        rec["kept"] = False
        return out, rec
    rec["pull_seconds"] = round(_time.perf_counter() - _t0, 3)
    # 재판정 (조용한 실패 금지). 나아지지 않으면 되돌린다 — 폐기가 안전.
    try:
        import numpy as _np_r
        _parr = _decode_latent_rgb(vae, _pulled)
        _pu8 = (None if _parr is None else
                (_np_r.clip(_parr, 0.0, 1.0) * 255.0).astype(_np_r.uint8))
    except Exception:
        _pu8 = None
    if _pu8 is None:
        _log("[GoRi Consistency Keeper] ⚠ 당김 결과 재판정용 디코드 실패 — "
             "당김 전 결과를 반환합니다")
        rec["kept"] = False
        return out, rec
    _p_pts = _pose_landmarks_from_tasks(_pu8, with_visibility=True)
    if _p_pts:
        post_pose = judge_points(_p_pts, physics=True)
    else:
        # 왜(Why) 미측정을 intact 로 세지 않나 (2026-10-07 감사, Jev
        # choice = defect P=1.0): landmark 가 없으면 검사 0건 = 실패 0건이
        # 되어 "2→0 으로 나아졌다" 로 보이고, 포즈를 아예 놓친 당김 결과
        # 까지 채택된다. 물리 개선은 측정 가능해야만 인정한다 — 개수·발은
        # 검출기가 달라 독립 측정으로 남는다.
        post_pose = {"verdict": _JUDGE_UNDETERMINED, "checks": [],
                     "damage_regions": []}
    _post_fail = sum(1 for c in post_pose.get("checks", [])
                     if not c.get("ok", True))
    rec["post_pose_verdict"] = post_pose.get("verdict")
    rec["post_fail"] = _post_fail
    # 채택 기준 (2026-10-05, v1.9.16): 물리 검사는 부위 개수를 못 보는
    # 사각지대가 있다(3팔 실측 — 순서 검사 3건 전부 통과). 개수 위반
    # 당김의 "나아짐"은 당긴 뒤 손 개수가 줄었는가로 잰다. 물리 개선과
    # 개수 개선 중 하나라도 있으면 채택, 둘 다 없으면 폐기한다.
    # 다리도 같다 (2026-10-06, v1.9.18): 당긴 뒤 주인 없는 발이 줄었는가로
    # 잰다 (3다리 실측 — 순서 검사 전부 통과).
    # 왜(Why) 세 신호가 OR 인가 (2026-10-07 감사): 각 신호는 자기 검출기로
    # 재는 독립 측정이다. 구 코드는 발 분기가 `rec["kept"]` 를 덮어써
    # 개수 개선이 있던 결과도 발이 안 나아지면 폐기했다 (A3 덮어쓰기 버그).
    _phys_ok = bool(_p_pts) and _post_fail < _pre_fail
    rec["kept"] = _phys_ok
    _count_ok = False
    if _count_bad:
        _post_cnt = _hand_count_from_tasks(_pu8)
        rec["post_hand_count"] = _post_cnt
        if _post_cnt is not None:
            _count_ok = _post_cnt < _cnt
            rec["kept"] = _phys_ok or _count_ok
    _post_unc = None
    _foot_ok = False
    if _foot_bad:
        try:
            _post_skin = _skin_stats(_pu8, _p_pts) if _p_pts else None
            _post_comps = (_foot_comps(_pu8, _p_pts, _post_skin)
                           if _post_skin and _p_pts and len(_p_pts) >= 33
                           else None)
            if _post_comps is not None:
                _post_unc = _unclaimed_feet(
                    _post_comps, float(_p_pts[31][0]), float(_p_pts[32][0]))
                _post_unc = len(_post_unc)
        except Exception:
            _post_unc = None
        rec["post_foot_unclaimed"] = _post_unc
        if _post_unc is not None:
            _pre_unc = (_feet or {}).get("unclaimed")
            _foot_ok = _post_unc < _pre_unc
            rec["kept"] = _phys_ok or _count_ok or _foot_ok
    if rec["kept"]:
        # 왜(Why) 신호가 실제로 개선된 것 기준인가: `_count_bad` 기준이면
        # 개수가 안 줄어도(2→2) "개수 개선" 로그가 나와 로그가 거짓말을
        # 했다 (2026-10-07 감사).
        if _count_ok:
            _log("[GoRi Consistency Keeper] 골격 당김 완료: %s 부위 "
                 "(eff=%.2f) — %.1f초, 개수 개선 (%s→%s). "
                 "결과를 채택합니다"
                 % (", ".join(rec["regions"]),
                    _SKELETON_PULL_STRENGTH, rec["pull_seconds"],
                    _cnt, rec.get("post_hand_count")))
        elif _foot_ok:
            _log("[GoRi Consistency Keeper] 골격 당김 완료: %s 부위 "
                 "(eff=%.2f) — %.1f초, 다리 개수 개선 (%s→%s). "
                 "결과를 채택합니다"
                 % (", ".join(rec["regions"]),
                    _SKELETON_PULL_STRENGTH, rec["pull_seconds"],
                    (_feet or {}).get("unclaimed"),
                    rec.get("post_foot_unclaimed")))
        else:
            _log("[GoRi Consistency Keeper] 골격 당김 완료: %s 부위 "
                 "(eff=%.2f) — %.1f초, 판정 나아짐 (실패 %d→%d). "
                 "결과를 채택합니다"
                 % (", ".join(rec["regions"]),
                    _SKELETON_PULL_STRENGTH,
                    rec["pull_seconds"], _pre_fail, _post_fail))
        return _pulled, rec
    if not _p_pts:
        _log("[GoRi Consistency Keeper] ⚠ 당김 결과 재판정에서 포즈를 찾지 "
             "못했습니다 — 개선을 확인할 수 없어 당김 결과를 폐기하고 "
             "당김 전 결과를 반환합니다")
    else:
        _log("[GoRi Consistency Keeper] ⚠ 당김 후에도 나아지지 않았습니다 "
             "(실패 %d→%d) — 당김 결과를 폐기하고 당김 전 결과를 반환합니다"
             % (_pre_fail, _post_fail))
    return out, rec


def framing_similarity(box_a, box_b) -> float:
    """두 인물 bbox의 프레이밍 유사도 0~1. 비교 불가면 0.0.

    왜(Why) 이것이 게이트인가: 신원 소스로 쓸 패널은 결과와 **프레이밍이
    비슷해야** 픽셀이 대응한다. 종횡비와 상대 높이만 본다(배경/위치는 무시 —
    같은 캐릭터의 정면과 후면은 위치가 아니라 실루엣 비율로 판정한다).
    """
    try:
        if box_a is None or box_b is None:
            return 0.0
        aw = max(1e-6, float(box_a[2]) - float(box_a[0]))
        ah = max(1e-6, float(box_a[3]) - float(box_a[1]))
        bw = max(1e-6, float(box_b[2]) - float(box_b[0]))
        bh = max(1e-6, float(box_b[3]) - float(box_b[1]))
        ar_a, ar_b = aw / ah, bw / bh
        ar_sim = min(ar_a, ar_b) / max(ar_a, ar_b)          # 종횡비 0~1
        h_a = min(box_a[3], 1.0) - max(box_a[1], 0.0)
        h_b = min(box_b[3], 1.0) - max(box_b[1], 0.0)
        h_sim = min(h_a, h_b) / max(max(h_a, h_b), 1e-6)     # 상대 높이 0~1
        # 왜(Why) min 이 바깥에 있나 (2026-10-04 감사 56차): NaN 좌표가 들어오면
        # `min(1.0, nan)` 이 1.0 이 돼 게이트가 fail-open 했다. 바깥을 min 으로
        # 두면 docstring 대로 0.0(비교 불가)이 된다. 유한 입력에는 무영향.
        return min(1.0, max(0.0, 0.5 * ar_sim + 0.5 * h_sim))
    except Exception:
        return 0.0


# 이 값부터는 해당 패널을 신원 소스로 쓸 수 있다(2단계에서 강도 적용에 사용).
FRAMING_GATE = 0.60


def _pose_landmarks(img_arr):
    """RGB 배열 -> 33점 (x, y) 리스트. 모델 미설치/미검출 시 None.

    (왜) 예전엔 `mediapipe.solutions.pose.Pose` 였는데 그 API 가 없다.
    같은 이유로 tasks API + .task 모델로 대체한다.

    (왜) 범위 검사가 있다 (2026-10-02): 계약은 "float 0~1" 이다. 이 계약을
    어기면 `clip(0,1)` 이 **조용히** 값을 뭉갠다 — uint8 0~255 를 넘기면 전부
    255 가 되고 검출이 0개가 되며 예외도 안 난다. 그래서 "포즈가 죽었다" 는
    오해를 샌다. 실제로 이 함수를 원본 PNG 로 직접 부른 프로브가 0/18 을
    냈고(2026-09-30), 원인은 크기였다(1024px 캡 후 11/18).
    **production 경로에서는 이 검사가 절대 발동하지 않는다.** 실측 근거:
    두 호출자(`analyze_reference_sheet` 의
    `_full`·`_samp_src`) 모두
    `_decode_latent_rgb`/`_decode_small` 로
    오는데 둘 다 마지막에 `_as_rgb_hwc` 를 지나고 그 마지막 return 이
    `clip(0,1)`
    이다. 슬라이스(`ref_arr[:, x0:x1]`)와 `_content_crop` 도 범위를
    보존한다. 즉 발동 조건은 "production 이 계약을 어겼을 때" 뿐이다.
    """
    # `_pose_model_path() is None` 검사는 여기에 있었다. 도달 불가라 뺐다 —
    # 그 함수는 항상 str 을 돌려준다. 진짜 "없음" (mediapipe.tasks 미설치)은
    # `_pose_landmarker` 안에서 `_find_base_options() is None` 으로 잡아
    # `_note_pose_unavailable()` 을 부른다. 두 검사를 한 곳에 두면 안 된다.
    try:
        import numpy as _np
        if img_arr is None:
            return None
        a = _np.asarray(img_arr, dtype=_np.float32)
        if a.size:
            _lo = float(a.min())
            _hi = float(a.max())
            # 왜(Why) 부정형(NaN 을 통과시키는 형태가 아니라 만족을 요구하는
            # 형태)인가 (2026-10-04 감사 12차): `_lo < 0.0 or _hi > 1.0` 은
            # NaN 에서 두 비교가 전부 거짓이라 가드를 통과한다. 그러면
            # clip 이 NaN 을 그대로 남기고 uint8 캐스트가 미정의 동작이 된다
            # (검출이 조용히 죽거나 쓰레기 프레임을 본다). fp16 VAE 의
            # 디코드 오버플로가 실제 NaN 생산자다. "0..1 안에 있음" 을
            # 요구하면 NaN 은 자동으로 거부된다.
            if not (_lo >= 0.0 and _hi <= 1.0):
                _note_once(
                    "pose_input_range",
                    "[GoRi Consistency Keeper] pose input outside 0..1 "
                    "(min=%.4f max=%.4f dtype=%s) — uint8 0..255 를 float 로 "
                    "간주했습니다. clip 결과가 전부 255/0 이 되어 검출이 0개가 "
                    "됩니다. float 0~1 로 변환해 넘기거나 1024px 캡을 지키십시오."
                    % (_lo, _hi, a.dtype))
                return None
        u8 = (_np.clip(a, 0.0, 1.0) * 255.0).astype(_np.uint8)
        return _pose_landmarks_from_tasks(u8)
    except Exception as _e:
        # 왜(Why) once 로그를 남기나 (2026-10-04 감사 54차): out-of-range 는
        # 위 once 로그가 잡지만 그 이전 변환 단계(asarray/min)의 예외는
        # 여기서 무음으로 소멸했다. callee 는 자체 보고가 있지만 그 **전**의
        # 실패는 callee 에 도달하지 않는다. 실행 결과 자체는 매 런 "마스크
        # 없음" 로그로 보이므로 근본 원인만 once 로 남긴다.
        _note_once(
            "pose_input_conv",
            "[GoRi Consistency Keeper] pose input 변환 실패 (%s: %s) — "
            "포즈 검출을 건너뛰고 전역 당김으로 진행합니다"
            % (type(_e).__name__, _e))
        return None


def _panel_reference_latent(vae, ref_latent, panel_n, cache=None):
    """시트의 한 패널만 잘라 **진짜 latent** 로 돌려준다. 실패하면 None.

    왜(Why) 다시 VAE 로 인코딩하나: 패널 좌표는 픽셀 배열에서 얻었으므로
    여기서는 픽셀 텐서를 만들어 그대로 넘기고 싶지만, downstream 은 전부
    latent 를 기대한다(`_part_detail_map` 은 VAE 디코드, drift MSE 와 전역 블렌드
    도 latent 간 연산). 픽셀을 latent 자리에 넣으면 조용히 깨진다. 그래서
    **진짜 latent** 로 되돌려야 아무도 안 깨진다. 비용은 시트를 물었을 때만
    VAE encode 1회.
    """
    try:
        import numpy as _np
        import torch as _t
        if vae is None or ref_latent is None or not panel_n:
            return None
        full = _decode_latent_rgb(vae, ref_latent, cache=cache)
        if full is None:
            _release_vram()
            return None
        h, w = int(full.shape[0]), int(full.shape[1])
        x0 = max(0, min(w - 2, int(float(panel_n[0]) * w)))
        x1 = max(x0 + 1, min(w, int(float(panel_n[1]) * w)))
        if x1 - x0 < 8:
            _release_vram()
            return None
        crop = full[:, x0:x1]
        # 세로로 긴 패널은 정사각에 가깝게 잘라낸다 — VAE 물결에 덜 예민하다.
        ch, cw = int(crop.shape[0]), int(crop.shape[1])
        side = min(ch, cw)
        y0 = max(0, (ch - side) // 2)
        crop = crop[y0:y0 + side, :]
        lat = vae.encode(_t.from_numpy(
            _np.ascontiguousarray(crop))[None])
        del crop, full
        _release_vram()
        return lat
    except Exception as _e:
        # 왜(Why) 포즈 채널을 안 쓰나 + release (2026-10-04 감사):
        # 실패 원인은 encode/decode 이지 포즈가 아니다. 예외 경로가
        # release 를 안 해 crop/full 이 남았었다 — 그래서 이 자리에서
        # release 한다.
        _log("[GoRi Consistency Keeper] ⚠ panel reference encode "
             "failed: %s" % _e)
        _release_vram()
        return None


def analyze_reference_sheet(vae, ref_latent, sampled, cache=None) -> dict:
    """원본 참조가 캐릭터 시트인지 확인하고, 결과와 가장 잘 맞는 패널을 고른다.

    반환: {"panels", "raw", "sheet", "best", "match", "framing", "gate",
           "box"}. 판정 불가 시 panels=0.
    """
    out = {"panels": 0, "raw": 0, "sheet": False, "best": None, "match": 0.0,
           "panels_n": [],
           "framing": 0.0, "gate": False, "box": None, "wreg": 0.0, "greg": 0.0}
    try:
        ref_arr = _decode_small(vae, ref_latent, 0.5)
        if ref_arr is None:
            # 왜(Why) 여기서 또 말하나: 이 분기는 조용한 실패 두 가지("시트가
            # 아니다" 와 "디코드가 실패했다") 를 구분해 주는 유일한 자리다.
            # `_decode_small` 이 예외를 삼키고 None 을 돌려주므로, 로그가
            # 없으면 사용자가 "패널 0개" 를 보고 원본 문제를 의심하게 된다.
            # 왜(Why) `_note_pose_error` 를 안 쓰나 (2026-10-04 감사):
            # 여기는 **디코드 실패**지 포즈 추론 실패가 아니고 예외도
            # 없다(None). 그 채널로 보내면 "NoneType: None" 이라는
            # 거짓 메시지가 남고 `_POSE_ERR_NOTED` 까지 소모돼 뒤에
            # 오는 진짜 포즈 실패가 조용히 묻힌다. 디코드 실패는
            # 여기서 직접 경고한다(한 실행에 이 경로는 한 번).
            _log("[GoRi Consistency Keeper] ⚠ 참조 시트 디코드 실패 — "
                 "시트 판정을 건너뛰고 원본 경로로 진행합니다")
            _release_vram()
            return out
        raw = detect_panels(ref_arr)
        out["raw"] = len(raw)
        judge = looks_like_sheet(raw)
        out["panels"] = judge["n"]
        out["wreg"] = judge.get("wreg", 0.0)
        out["greg"] = judge.get("greg", 0.0)
        # 정규성 미달이면 시트로 보지 않는다. 오탐이 누락보다 위험하다
        # (시트로 잘못 보면 뷰들이 여러 사람 신원으로 평균된다).
        if not judge.get("sheet"):
            # 여기서 돌아가도 디코드 잔재를 남기면 안 된다 — 이 경로가
            # **가장 흔한 경로**(평범한 사진)라 정리가 사실상 안 돌았다.
            _release_vram()
            return out
        out["sheet"] = True
        panels = raw
        h, w = ref_arr.shape[0], ref_arr.shape[1]
        # 1) 결과와 가장 잘 맞는 패널 = **결과 이미지**와의 시그니처 상관 최대.
        # 왜(Why) 여기서 결과를 봐야 하나: 이전에는 시그니처를 `sig_ref`(시트 전체
        # 시그니처)와 비교했다. 시트 안의 모든 패널은 구성상 시트 전체와 비슷해서
        # 점수가 "이 패널이 얼마나 다른 뷰인가"를 재는 것으로 수렴하고, 생성 결과가
        # 어떤 뷰인지는 전혀 반영되지 않았다. README가 말하는 "결과와 가장 잘 맞는
        # 뷰"가 되려면 비교 대상이 결과여야 한다.
        samp_arr = _decode_small(vae, sampled, 0.25)
        # 샘플은 세로 한 장짜리 이미지라 패널 시그니처와 같은 넓이를 갖지 않는다.
        # 그래도 히스토그램은 총합 1로 정규화되므로 크기 차이는 상쇄된다.
        sig_samp = panel_signature(samp_arr, 0, samp_arr.shape[1]) if samp_arr is not None else None
        best, best_score = None, 0.0
        for idx, (x0, x1) in enumerate(panels):
            sig = panel_signature(ref_arr, x0, x1)
            score = signature_similarity(sig, sig_samp)
            if score > best_score:
                best, best_score = idx, score
        out["best"] = best
        out["match"] = round(best_score, 3)
        # 왜(Why) 정규화(0~1)로 주는가: 패널 좌표는 `_decode_small(0.5)` 즉
        # 절반 크기 이미지 기준이라, 소비자가 그대로 픽셀로 쓰면 해상도에
        # 종속된다. 비율로 주면 아무 해상도에서나 잘라낼 수 있다.
        _sw = float(ref_arr.shape[1]) or 1.0
        out["panels_n"] = [(a / _sw, b / _sw) for a, b in panels]
        # 2) 프레이밍 게이트: 고른 패널의 인물 비율이 결과와 맞는지
        if best is not None:
            x0, x1 = panels[best]
            # 왜(Why) 여기서만 원본 해상도로 다시 잡나 (2026-09-30 실측):
            # `ref_arr` 은 0.5배 축소본이라 패널 폭이 216 -> 108 px 로 줄어
            # 33점 검출이 실패한다. 그 결과 "인물 bbox 미검출" -> 프레이밍 게이트가
            # 항상 False -> 2단계 (A) 경로로 영영 못 들어간다. 패널 검출·유사도
            # 판정은 축소본으로 충분하니 **포즈만** 원본 크기로 본다.
            _pose_src = ref_arr[:, x0:x1]
            _full = _decode_latent_rgb(vae, ref_latent, cache=cache)
            if _full is not None and _full.shape[1] > ref_arr.shape[1]:
                _sx = float(_full.shape[1]) / float(ref_arr.shape[1])
                _pose_src = _full[:, int(x0 * _sx):max(
                    int(x0 * _sx) + 2, int(x1 * _sx))]
            lm_ref = _pose_landmarks(_content_crop(_pose_src))
            # 왜(Why) sampled 도 원본 해상도로 보나: 아래 `samp_arr` 은 판정용
            # 0.25배 축소본이라 33점이 잡히지 않고, 그러면 box_s 가 None 이 되어
            # framing_similarity 가 0.0(=게이트 차단)이 된다(2026-09-30 실측:
            # 참조는 0.747 인데 결과는 0.00). 양쪽 해상도를 맞춰야 비교가 된다.
            _samp_src = _decode_latent_rgb(vae, sampled, cache=cache)
            if _samp_src is None:
                _samp_src = samp_arr
            lm_s = _pose_landmarks(_content_crop(_samp_src))
            box_ref = subject_bbox(lm_ref)
            box_s = subject_bbox(lm_s)
            out["box"] = box_ref
            out["framing"] = round(framing_similarity(box_ref, box_s), 3)
            out["gate"] = out["framing"] >= FRAMING_GATE
        _release_vram()
    except Exception as _e:
        # 왜(Why) 로그를 남기나 (2026-09-30 실측): 여기가 조용하면 시트 경로가
        # "안 되는 이유"를 아예 말하지 않는다. 실제로 예외 하나가 시트 분석
        # 전체를 삼켜 로그가 0건이었고, 밖에서는 그것이 "시트가 아니다" 와
        # 구분되지 않았다.
        # 왜(Why) 포즈 채널이 아닌가 (2026-10-04 감사 3번째 위치):
        # 이 try 안의 callee 는 전부 자체적으로 None/예외를 삼키므로
        # 여기까지 오는 것은 MemoryError 급이다. 그때 포즈 채널을
        # 소모하면 뒤의 진짜 포즈 실패가 묻힌다.
        _log("[GoRi Consistency Keeper] ⚠ analyze_reference_sheet "
             "failed: %s" % _e)
        _release_vram()
    return out


def _log_sheet_analysis(info: dict, ref_name: str) -> None:
    """시트 분석 결과 로그. 판정 자체는 하지 않는다 — run() 이 이 결과를
    패널 대체·강도 감쇠에 반영한다(2단계)."""
    try:
        if not info:
            return
        if not info.get("sheet"):
            # 콘텐츠 구간이 있어도 정규성이 모자라면 시트가 아니다. 조용히
            # 넘기되 판정 수치를 남긴다 — 임계값 조정이 필요할 수 있으므로.
            if info.get("raw", 0) >= SHEET_MIN_PANELS:
                _log(f"[GoRi Consistency Keeper] {ref_name} 참조에 콘텐츠 "
                     f"구간 {info['raw']}개가 있으나 정규성 미달 — 시트로 보지 "
                     f"않습니다 (간격비 {info.get('greg', 0):.4f} ≥ "
                     f"{SHEET_MIN_SPACING_RATIO:.2f} 필요. 폭비 "
                     f"{info.get('wreg', 0):.2f} 는 기록용이며 판정에 쓰지 않음)")
            elif info.get("raw", 0) > 0:
                # 왜(Why) 이 줄이 필요한가: 패널이 1~2개면
                # 이전엔 로그가 없었다. 사용자가 시트가 아닌데
                # 판정 로그가 0개면 "시트가 아닌 것인지"와
                # "분석이 죽은 것"이 구분되지 않는다
                # (2026-09-30 실제로 정확히 이 혼동이 일어났다).
                _log(f"[GoRi Consistency Keeper] {ref_name} 시트 아닌 — "
                     f"패널 {info['raw']}개만 검출 (최소 {SHEET_MIN_PANELS}개 필요)")
            else:
                # 왜(Why) 이 줄이 필요한가 (2026-10-05 감사 64차): raw==0
                # (거의 균일한 이미지, column_profile 기각) 는 위 두 분기를
                # 모두 통과해 완전 무음이었다. "조용한 무동작 제거" 원칙에 따라
                # 판정 수치를 남긴다.
                _log(f"[GoRi Consistency Keeper] {ref_name} 시트 아닌 — "
                     "콘텐츠 구간 0개 (이미지가 거의 균일하거나 너무 작아 "
                     "열 프로필을 만들 수 없음)")
            return
        _log(f"[GoRi Consistency Keeper] {ref_name} 참조에서 {info['panels']}개 "
             f"패널 검출 — 캐릭터 시트 형태로 보입니다")
        if info.get("best") is None:
            _log(f"[GoRi Consistency Keeper] ⚠ 패널 매칭 실패 — 신원 평균 "
                 f"상태로 진행합니다")
            return
        _log(f"[GoRi Consistency Keeper]   가장 일치하는 뷰: "
             f"{info['best'] + 1}번 패널 (유사도 {info['match']:.2f})")
        if info.get("box") is None:
            # mediapipe 미설치/미검출이면 bbox가 없다. 이때 게이트를 0으로
            # 통과시킨 척하면 안 된다 — 판정 불가를 "불일치"와 구분해야
            # 원인을 알 수 있다.
            _log(f"[GoRi Consistency Keeper] ⚠ 인물 bbox 미검출 — 프레이밍 "
                 f"판정 불가 (mediapipe 미설치 또는 검출 실패). 패널을 신원 "
                 f"소스로 쓰지 않고 게이트 실패로 처리합니다")
        elif info.get("gate"):
            _log(f"[GoRi Consistency Keeper]   프레이밍 유사도 "
                 f"{info['framing']:.2f} — 픽셀이 대응하므로 이 뷰를 "
                 f"신원 소스로 쓸 수 있습니다")
        else:
            _log(f"[GoRi Consistency Keeper] {ref_name} 프레이밍 불일치 "
                 f"({info['framing']:.4f} < {FRAMING_GATE:.2f}) — 이 뷰는 "
                 f"결과와 위치가 대응하지 않아 신원 소스로 쓰지 않습니다. "
                 f"시트 각도를 결과 각도에 맞추면 더 정확해집니다")
    except Exception as _le:
        # 왜(Why) pass 를 그대로 두지 않나 (2026-10-07 감사): 전체를 덮은
        # try/pass 는 형식 오류 하나로 시트 판정 로그 전체가 조용히 사라졌다.
        # 판정 수치를 못 남기는 상태 자체를 한 번 말한다.
        _note_once("sheet_log",
                   "[GoRi Consistency Keeper] ⚠ 시트 분석 결과 로그 중 오류 "
                   "(%s: %s) — 판정 수치를 남기지 못했습니다"
                   % (type(_le).__name__, str(_le)[:80]))


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        import sys as _sys
        enc = getattr(_sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, "replace").decode(enc, errors="replace"), flush=True)


def _safe_strength(value, label: str) -> float:
    """위젯 강도를 [-1, 1] 로 안전하게 정규화한다.

    왜(Why) nan/inf 를 따로 잡나(2026-09-28 실측): CPython 의
    `min(1.0, float("nan"))` 은 **1.0** 을 돌려준다(비교가 항상 False 라서).
    즉 nan 이 "가장 강한 값"으로 해석되어 사용자가 0 을 넣은 자리에서
    100% 교체가 일어났다. inf 도 ±1.0 으로 클램프되어 같은 결과다.
    워크플로 JSON 이나 상위 수학 노드가 nan 을 그대로 넘길 수 있으므로
    강등하고 로그에 남긴다.
    """
    try:
        v = float(value)
    except (ValueError, TypeError):
        return 0.0
    try:
        if v != v:                       # nan
            _log(f"[GoRi Consistency Keeper] ⚠ {label}=nan — 강도 0 으로 "
                 f"강등합니다 (값이 없으면 원본을 그대로 유지해야 합니다)")
            return 0.0
        if v in (float("inf"), float("-inf")):
            _log(f"[GoRi Consistency Keeper] ⚠ {label}=inf — 강도 0 으로 "
                 f"강등합니다 (무한대는 클램프가 아니라 오류입니다)")
            return 0.0
    except Exception:
        return 0.0
    return max(-1.0, min(1.0, v))


class GoRiConsistencyKeeper:
    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("latent_out",)
    FUNCTION = "run"
    CATEGORY = "GoRi/Refine"
    DESCRIPTION = ("샘플러 latent를 원본·카메라 기준 latent 쪽으로 당겨 "
                   "신원·구도 틀어짐을 줄이는 2차 패스 노드. "
                   "Decode 전에 연결한다.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sampled_latent": ("LATENT",),
                # 샘플러 결과물 보존 강도 (2026-10-02). 전체 보정량에 거는 마스터 게인이다.
                # 왜(Why) 필요한가: strength_camera/original 은 각 기준 쪽으로
                # "당기는 양" 만 정한다. 둘을 다 만지지 않고 키퍼 전체 효과를
                # 올리고 내릴 방법이 없었다. 1.0 = 기존 동작 그대로,
                # 0.0 = 통과(출력=입력), 0.5 = 절반만 반영.
                # 왜(Why) 기본 1.0 인가: 기존 워크플로와 바이트 단위로 같아야 한다.
                # 기본값을 낮추면 업데이트한 사용자 결과가 전부 바뀐다.
                # 왜(Why) 음수도 허용하나: camera/original 과 같은 규격(-1.0~1.0).
                # 음수는 보정을 뒤집는다(기준에서 밀어냄). 의도적으로 쓰는 경우만.
                # 참고 (감사 63차): 기준 강도도 음수(안티-레퍼런스)면 이중 음수로
                # 기준 쪽으로의 당김이 된다(|s × eff|). 두 음수를 같이 쓰는 것은
                # 이 조합을 원할 때만.
                "strength_sampler": ("FLOAT", {"default": 1.0, "min": -1.0,
                                              "max": 1.0, "step": 0.05}),
                "strength_camera": ("FLOAT", {"default": 0.2, "min": -1.0,
                                              "max": 1.0, "step": 0.05}),
                "strength_original": ("FLOAT", {"default": 0.2, "min": -1.0,
                                               "max": 1.0, "step": 0.05}),
            },
            "optional": {
                "original_latent": ("LATENT",),
                "camera_latent": ("LATENT",),
"vae": ("VAE",),
                # 원본을 **이미지**로 받는다 (2026-10-01 추가). Qwen Edit 의
                # `TextEncodeQwenImage21.latent` 출력은 전부 0 인 빈 캔버스라
                # Latent 로 받으면 기준이 비어 있다 — `_encode_image_ref` 참조.
                # 이게 있으면 그걸 인코딩해서 원본 기준으로 쓴다(우선).
                "original_image": ("IMAGE",),
                # 판정 게이트 on/off (2026-10-01). 기본 False = 기존 동작 그대로.
                # 왜(Why) 기본을 끄는가: 켰을 때 결과물이 달라지는 게 이 위젯의
                # 존재 이유인데, 꺼놓고 모르고 돌아가는 노드는 "왜 결과가 바뀌지
                # 않는지"를 설명할 수 없는 노드다. 켜는 쪽이 그 판단을 한다.
                "trust_gate": ("BOOLEAN", {"default": False}),
                # --- 판정 주도 교정 당김 (2026-10-05) ---
                # 왜(Why) 모두 optional dict **맨 끝**에만 두나 (R49 실측):
                # 위젯 중간 삽입은 기존 저장 워크플로의 widgets_values
                # 바인딩을 민다. 새 위젯은 항상 끝에 추가한다.
                # 골격 참조 당김 (2026-10-05): 재샘플링 수술을 폐기하고
                # "다시 그리지 않는다" DNA 로 복귀. 판정기 좌표를 스탠다드
                # 규격으로 교정해 그린 골격 이미지를 VAE 인코딩하고 그
                # latent 쪽으로 파손 부위만 당긴다. 모델·조건·시드가
                # 필요 없어 위젯은 스위치 하나뿐이다.
                "repair_enable": ("BOOLEAN", {"default": False}),
            },
        }

    def run(self, sampled_latent, strength_sampler=1.0,
            strength_camera=0.2, strength_original=0.2,
            original_latent=None, camera_latent=None, vae=None,
            original_image=None, trust_gate=False, repair_enable=False):
        sampled = _get_samples(sampled_latent)
        if sampled is None:
            raise ValueError("(GoRi) Consistency Keeper: sampled_latent이 비어 있음")
        s = _safe_strength(strength_sampler, "strength_sampler")
        a = _safe_strength(strength_camera, "strength_camera")
        b = _safe_strength(strength_original, "strength_original")
        out = sampled.clone() if hasattr(sampled, "clone") else sampled
        # 아무 일도 하지 않는 실행에서 VAE 디코드 + MediaPipe를 돌리지 않는다.
        # 왜(Why): 마스크 계산은 strength 값과 무관하게 무조건 실행돼서,
        # 강도 0이거나 참조 LATENT가 하나도 없는 no-op에서도 전 해상도
        # 디코딩 1회 + MediaPipe가 돌았다(실측).
        # **주의**: 전역 블렌드에는 VAE가 필요 없다(마스크가 None일 뿐이다).
        # 여기를 `vae is None`으로 막으면 VAE 미연결 + 전역 당김이 깨진다 →
        # vae 조건은 아래 마스크/시트 분석 쪽에만 둔다.
        _orig_ref = _get_samples(original_latent)
        _cam_ref = _get_samples(camera_latent)
        # 왜(Why) original_image 이 우선인가 (2026-10-01 실측):
        # `TextEncodeQwenImage21` 의 `latent` 출력은 **전부 0** 이다. 그
        # latent 를 `original_latent` 로 받는 한 원본 기준은 항상 빈 캔버스와
        # 비교하게 되고 숫자가 무의미하다. 이미지가 오면 그것을 직접 인코딩해
        # 기준을 세운다. 이미지 없으면 기존 경로(빈 latent) 그대로 둔다 —
        # 동작을 바꾸지 않기 위함이지, 그 경로가 옳다는 뜻이 아니다.
        # 왜(Why) no-op 판정을 인코딩 앞에 두나 (2026-10-04
        # 감사): 강도 0이면 `original_image` 인코딩은 **버려진다**
        # — 다중 MP 이미지를 통째로 한 번 인코딩하고(실측 비용)
        # 결과를 쓰지 않는다. 앞의 두 조건은 참조와 무관하므로
        # 인코딩보다 먼저 본다. 세 번째 조건(참조 없음)은
        # 인코딩 결과가 바꾸므로 아래에 둔다.
        if not s or not (a or b):
            if not repair_enable:
                _release_vram()
                return _with_samples(sampled_latent, out)
            # repair_enable 이면 강도와 무관하게 교정 판정까지 간다 —
            # t2i 에서는 당김 강도가 애초에 역할이 없고 이 노드의 개입은
            # 교정뿐이다(2026-10-05 사용자 지시).
            _log("[GoRi Consistency Keeper] 당김 강도 0 — 당김 없음, "
                 "교정 판정만 진행합니다")
        if original_image is not None:
            _img_ref = _encode_image_ref(vae, original_image)
            if _img_ref is not None:
                _orig_ref = _img_ref
                _log("[GoRi Consistency Keeper] 원본 기준을 이미지에서 직접 "
                     "인코딩했습니다 — Qwen Edit 의 latent 출력은 빈 캔버스라 "
                     "그대로 쓰면 비교가 무의미합니다")
            else:
                _log("[GoRi Consistency Keeper] ⚠ original_image 인코딩 실패 — "
                     "original_latent 경로로 진행합니다 (Qwen Edit 에선 빈 "
                     "캔버스이므로 원본 기준이 사실상 없습니다)")
        if _orig_ref is None and _cam_ref is None:
            if not repair_enable:
                if original_image is None:
                    # 왜(Why) (2026-10-04 감사 52차): 강도가 0 이 아닌데 둘 다
                    # 없으면 이 노드는 조용히 통과한다. 루프의 "기준 없음" 로그는
                    # 이 반환 뒤에 있어 여기서는 발화하지 않는다. 이미지 인코딩
                    # 실패로 여기 오면 위 original_image 인코딩 실패 로그가
                    # 이미 사유를 남겼으므로 다시 찍지 않는다.
                    _log("[GoRi Consistency Keeper] ⚠ 당김 강도가 0 이 아닌데 기준이 "
                         "없습니다 — original_latent 또는 camera_latent 를 연결하십시오 "
                         "(둘 다 없으면 이 노드는 입력을 그대로 통과시킵니다)")
                _release_vram()
                return _with_samples(sampled_latent, out)
            # t2i (2026-10-05 사용자 지시): LoadImage 를 끄고 프롬프트만으로
            # 만들면 원본 DNA 가 성립하지 않는다 — 당길 대상이 없으니 당김은
            # 할 일이 없고, 이 노드의 개입은 교정(해부학 스탠다드)뿐이다.
            # 조기 반환하지 않고 교정 블록까지 간다. 블렌드 루프는 ref 가
            # None 이면 스스로 건너뛰고(루프 머리의 "기준 없음 — 건너뜀"
            # 분기), 게인은 out==sampled 라 no-op 이다.
            _log("[GoRi Consistency Keeper] t2i — 당김 기준 없음 "
                 "(원본·카메라 미연결), 해부학 교정 당김만 대기합니다")
        # 인체 마스크(있으면 인물 영역만). 1회 계산해 양쪽 기준에 공유.
        # 배치>1 은 **전역 당김만** 적용한다(2026-09-28 실측).
        # 왜(Why): _person_mask_for_latent / _part_detail_map 은 요소 0의
        # 세그멘테이션·랜드마크만 계산해 (1,1,H,W) 로 전체 배치에
        # 브로드캐스트한다 → 2번째 이후 피사자가 **엉뚱한 부위**를 당긴다.
        # 요소를 순회하도록 고치는 게 옳지만 지금은 사람 마스크/부위 보강을
        # **끄는** 쪽이 오탐보다 안전하다(잘못된 부위 복원은 전역 당김보다
        # 복구 어렵다). 전역 블렌드는 배치 전체에 정확히 적용되므로 값
        # 손실은 없다.
        _multi = int(getattr(sampled, "shape", [1])[0] or 1) > 1
        if _multi:
            _log(f"[GoRi Consistency Keeper] ⚠ 배치 — 전역 당김만 적용합니다 "
                 f"(인체 마스크·부위별 복원·캐릭터 시트 분석은 단일 이미지 전용입니다)")
        # 실행당 디코드 캐시: sampled 를 전 해상도로 두 번 디코딩하던 것을
        # 한 번으로 줄인다 (2026-09-28 실측: 128² latent → 1024² 2회).
        _dcache = {}
        # 왜(Why) 당김 활성 여부로 마스크를 gate 하나: t2i(참조가
        # 없어 당김이 아예 없는 실행)에서 인체 마스크를 만들면
        # VAE 디코드+포즈 검출을 쓰고도 아무데도 쓰지 않았다
        # (2026-10-07 감사). 당김이 있는 실행에서만 계산한다.
        _pull_active = ((_cam_ref is not None and a)
                        or (_orig_ref is not None and b))
        _mask = None if (_multi or not _pull_active) else _person_mask_for_latent(
            vae, sampled, cache=_dcache)
        # 왜(Why) 이 로그가 필요한가 (2026-09-30 실측): 마스크가 없으면 당김이
        # **전역**으로 퍼져 배경까지 끌려간다. 그런데 마스크 유무가 로그로 안
        # 알려지면 "영향 없음"과 "전역 당김"을 구별할 수 없다 — 실제로 vae 를
        # 연결했는데 마스크가 조용히 None 이었던 상태를 로그 없이 한참 알지
        # 못했다. 한 줄로 충분하다.
        if (vae is not None and _mask is None and not _multi
                and _pull_active):
            # (2026-10-04 감사 13차) 이 분기는 vae 연결이 보장된 뒤라
            # "VAE 미연결" 을 원인으로 말할 수 없다.
            _log("[GoRi Consistency Keeper] 인체 마스크 없음 — 전역 당김으로 "
                 "진행합니다 (포즈/사람 미검출 또는 디코드 실패)")
        # 캐릭터 시트 참조 분석 (2단계: 판정을 강도에 반영한다).
        # 왜(Why) 여기가 **부위별 맵보다 먼저**인가: 아래 판정으로 기준 원본이
        # 패널로 바뀔 수 있다. 맵을 먼저 만들면 맵은 시트 전체를 보고 당김만
        # 패널을 보게 되어 둘이 서로 다른 원본을 참조하게 된다.
        if vae is not None and b and not _multi and _orig_ref is not None:
            _sheet = analyze_reference_sheet(vae, _orig_ref, sampled, cache=_dcache)
            _log_sheet_analysis(_sheet, "original")
            if _sheet.get("sheet"):
                _pn = _sheet.get("panels_n") or []
                _best = _sheet.get("best")
                if _best is None:
                    # 왜(Why) 격하하는가 (2026-10-04 감사 25차): 시트 확정
                    #(`sheet=True`) 상태에서 best 가 None 이면(패널 시그니처가
                    # 전부 0.0 — sampled 디코드 실패 등) 어느 분기도 안 타고
                    # 시트 전체를 풀 강도로 당긴다. R21 의 패널 생산 실패와 같은
                    # 조용한 무동작이라 (B) 와 같은 안전 방향으로 격하한다.
                    _old_b = b
                    b = _safe_strength(b * _SHEET_DAMP, "strength_original")
                    _log(f"[GoRi Consistency Keeper]   2단계: 시트로 확정됐지만 "
                         f"결과와 맞는 패널을 고르지 못했습니다. 시트 전체의 "
                         f"신원 신호가 섞이므로 당김 자동 감쇠 "
                         f"{_old_b:.2f}->{b:.2f}")
                elif _sheet.get("gate") and 0 <= _best < len(_pn):
                    # (A) 신원 신호가 섞이지 않게 **그 패널 하나만** 기준으로 쓴다
                    _panel = _panel_reference_latent(
                        vae, _orig_ref, _pn[_best], cache=_dcache)
                    # 왜(Why) dict 로 감싸나: `_get_samples` 은 LATENT dict
                    # 에서만 samples 를 꺼낸다. `vae.encode` 결과는 raw 텐서라
                    # 그대로 넘기면 조용히 None 이 되어 패널 대체가 통하지 않는다.
                    _p_ref = _get_samples({"samples": _panel})
                    if _p_ref is not None:
                        _orig_ref = _p_ref
                        _log(f"[GoRi Consistency Keeper]   2단계: "
                             f"{_best + 1}번 패널을 기준 원본으로 "
                             f"사용합니다 (시트 전체 대신 단일 뷰)")
                    else:
                        # 왜(Why) 조용히 통과시키지 않나 (2026-10-04 감사 21차):
                        # 패널 latent 생산이 None 이면(디코드 실패·패널 폭 미달)
                        # 여기서 아무것도 안 하면 **시트 전체를 풀 강도로 당기고
                        # 로그도 없다** — 2단계 (B) 가 막으려던 신원 평균화가
                        # 정확히 그 상태다. 대체 실패도 (B) 와 같은 안전 방향으로
                        # 격하하고 이유를 남긴다.
                        _old_b = b
                        b = _safe_strength(b * _SHEET_DAMP, "strength_original")
                        _log(f"[GoRi Consistency Keeper]   2단계: 패널 latent "
                             f"생산 실패 — 대체하지 못했습니다. 시트 전체의 "
                             f"신원 신호가 섞이므로 당김 자동 감쇠 "
                             f"{_old_b:.2f}->{b:.2f}")
                else:
                    # (B) 게이트를 못 통과하면 패널 프레이밍이 결과물과 다르다.
                    # 그래도 시트 전체를 강하게 당기면 신원 신호가 평균나므로
                    # 강도를 낮춘다 — 버리는 것보다 나음.
                    _old_b = b
                    b = _safe_strength(b * _SHEET_DAMP, "strength_original")
                    _log(f"[GoRi Consistency Keeper]   2단계: 프레이밍이 안 "
                         f"맞아 패널을 쓰지 않습니다. 시트 전체의 신원 신호가 "
                         f"섞이므로 당김 자동 감쇠 {_old_b:.2f}->{b:.2f}")
        # 부위별 디테일 손실 감지: 원본 latent는 1회만 디코딩해 재사용한다.
        # 왜(Why): sampled/original을 매번 디코딩하면 VAE 비용이 2배다.
        _pm = None
        if vae is not None and b and not _multi:
            _pm = _part_detail_map(vae, {
                "sampled": sampled,
                "original": _orig_ref,
            }, cache=_dcache)
        # 왜(Why) `original_latent` 이 아니라 `_orig_ref` 인가: 위 2단계가 기준
        # 원본을 패널로 바꿀 수 있다. 옛 입력을 그대로 쓰면 분석만 패널을 보고
        # 당김은 시트 전체를 당하게 되어 판정이 아무짝도 못 한다.
        # 왜(Why) 루프 안에서 `_get_samples` 를 다시 부르지 않는가: `_cam_ref` /
        # `_orig_ref` 는 위에서 이미 **텐서**로 뽑았다. `_get_samples` 은 LATENT
        # dict 전용이라 텐서를 넣으면 조용히 None 이 되어 전부 건너뛴다
        # (2026-09-30 실측으로 R55/R56/R59 가 전부 당김 0 이 됐다).
        for name, ref, strength in (
                ("camera", _cam_ref, a),
                ("original", _orig_ref, b)):
            if not strength:
                continue
            if ref is None:
                _log(f"[GoRi Consistency Keeper] {name} 기준 없음 — 건너뜀")
                continue
            matched = _match_spatial(ref, sampled)
            if matched is None:
                # 왜(Why) 두 사유를 구분하나 (2026-10-05 감사 68차): None 은
                # (1) 배치·채널 불일치(결정적 검사, 예외 없음)와 (2) 보간
                # 실패·OOM 등 예외 경로 양쪽에서 온다. 전부 "불일치" 로
                # 인쇄하면 환경 실패가 오진된다 (R28 로그 진실성 계약).
                if (ref.shape[0] == sampled.shape[0]
                        and ref.shape[1] == sampled.shape[1]):
                    _log(f"[GoRi Consistency Keeper] {name} 기준을 결과 "
                         "크기에 맞추지 못했습니다 — 건너뜀")
                else:
                    _log(f"[GoRi Consistency Keeper] {name} 배치·채널 "
                         "불일치 — 건너뜀")
                continue
            drift = _drift_mse(sampled, matched)
            # 정규화 값도 함께 재고 **둘 다** 로그한다.
            # 왜(Why) _mse 를 넘기나 (2026-10-07 감사): 같은 쌍의
            # 제곱편차를 두 번 계산하지 않는다 — 위 drift 가 분자 그대로다.
            drift_n = _drift_norm(sampled, matched, _mse=drift)
            eff = strength
            if drift is not None:
                _ns = "n/a" if drift_n is None else f"{drift_n:.4f}"
                _log(f"[GoRi Consistency Keeper] {name} 틀어짐 MSE={drift:.6f} "
                     f"정규화={_ns} 당김 {strength:.2f}")
            # 왜(Why) 정규화값으로 감쇠하나 (2026-10-01 실측): 절대 MSE 규칙
            # (0.8 / 2.0)은 이 워크플로에서 정상 참조 4건이 4.227~8.384 로
            # 측정돼 **전부 0 으로 죽었다.** 정규화값(0.222~0.487)은 모델을
            # 넘어가고 정상 범위를 안다. 비교 불가(None, 즉 참조가 퇴화)면
            # 예전 규칙으로 **떨어진다** — 조용히 "안 건드림" 으로 바뀌면 그게
            # 또 다른 조용한 실패가 된다.
            if drift_n is not None:
                _dn = strength * _damp_norm(drift_n)
                # 왜(Why) 크기 비교인가 (2026-10-04 감사 14차): 음수 강도
                # (기준에서 밀어냄)에서 _dn = strength*damp 는 0 쪽으로
                # **절댓값이 작아진다**. `_dn < eff` 는 음수에서 항상 거짓이라
                # 감쇠가 영원히 발동하지 않았다 — "틀어지면 손을 놓는다"
                # 계약이 밀어냄 방향에서만 깨져 있었다(양수 당김은 정상 동작,
                # 절대 MSE 폴백·조명 감쇠는 무조건 적용이라 셋이 서로 달랐다).
                # 절댓값 비교는 양수 경로(_dn, eff 전부 양수)와 완전히 동일하다.
                if abs(_dn) < abs(eff):
                    eff = _dn
                    # 왜(Why) NaN 을 갈라 쓰나 (2026-10-04 감사 28차): 유한한
                    # drift_n 이 여기 오려면 반드시 무릎(0.50)을 넘어야 하므로
                    # "x > 무릎" 이 참이다. 그러나 drift_n 이 NaN 이면
                    # _damp_norm(NaN)=0.0(R71 전파 차단)으로도 이 로그가
                    # 켜지고, "nan > 0.50" 은 거짓 비교를 인쇄한다. 사실대로
                    # 두 문구로 갈라 쓴다.
                    if drift_n != drift_n:
                        _log(f"[GoRi Consistency Keeper] ⚠ {name} 기준과 결과물 "
                             f"구도 비교 값이 NaN — 전파 차단으로 당김을 "
                             f"끕니다 {strength:.2f}→{eff:.2f}. "
                             f"같은 구도 기준 사용 권장")
                    else:
                        _log(f"[GoRi Consistency Keeper] ⚠ {name} 기준과 결과물 "
                             f"구도가 많이 다름 — 당김 자동 감쇠 {strength:.2f}"
                             f"→{eff:.2f} (정규화 {drift_n:.4f} > "
                             f"{_DRIFT_NORM_KNEE:.2f}). 같은 구도 기준 사용 권장")
            elif drift is not None and not (drift <= 0.8):
                # nan 은 모든 비교가 False 라 `> 0.8` 도 통과해 감쇠를
                # 건너뛴다 → 이후 0*(matched-sampled) 로 nan 이 전파된다.
                # `not (x <= 0.8)` 은 nan 에서 True 가 된다(2026-09-28).
                eff = strength * _damp_factor(drift)
                _log(f"[GoRi Consistency Keeper] ⚠ {name} 기준 정규화 불가 — "
                     f"절대 MSE 규칙으로 감쇠 {strength:.2f}→{eff:.2f}. "
                     f"참조가 퇴화했을 수 있습니다")

            mismatch = _lighting_mismatch(sampled, matched)
            if mismatch is not None and not (mismatch <= 1.0):
                _old_eff = eff
                eff = eff * _light_damp_factor(mismatch)
                _log(f"[GoRi Consistency Keeper] ⚠ {name} 조명 흐름 불일치 "
                     f"({mismatch:.2f}) — 당김 추가 감쇠 {_old_eff:.2f}→{eff:.2f}")
            # 물리 상한. 왜(Why) 있는가:
            # 당길수록 디테일이 줄고, **0.20 을 넘으면 더 줄어들지 않는다**
            # (대응 지점 기준, WORK_STATUS 11-7). 참조로 당기는 노드가
            # 참조보다 더 뭉개진 결과를 내는 걸 막는다.
            # 실측(사람 7장, 대응 지점 에지, 원본 대비 평균):
            #   0.00 → -1.2%(기준선)   0.20 → -33.5%   0.40 → -36.1%
            # 조용히 줄이지 않는다 — 잘렸을 때 반드시 말한다.
            # 왜(Why) 음수는 검사하지 않나 (2026-10-05 감사 63차): 상한의
            # 실측 근거가 "참조로 당겨서 생기는 디테일 손실" 측정이라
            # 밀어냄(음수)에는 근거가 없다. -1.0 안티-레퍼런스는 상한 없이
            # 선언 범위(-1.0~1.0) 그대로 작동한다.
            if eff > _PHYS_CEILING:
                _old_eff = eff
                eff = _PHYS_CEILING
                _log(f"[GoRi Consistency Keeper] ⚠ {name} 당김이 물리 상한을 "
                     f"넘었습니다 {_old_eff:.2f}→{eff:.2f} — 실측상 이 이상은 "
                     f"결과가 원본보다 뭉개집니다")
            # 부위별 adaptive 강도: 원본이 살아 있는데 결과가 뭉개진 부위만
            # 강도를 올려 그 부위를 원본 쪽으로 당긴다. 언제나 산술이며 추측이
            # 아니다 — "몇 개여야 한다"가 아니라 "얼마나 달라졌는가"만 본다.
            #
            # 정밀 검토에서 발견한 것 3건 (2026-09-28, 실측):
            # ① 감쇠된 eff가 아니라 **원래 strength**를 넘기고 있었다 → 구도가
            #    완전히 다른데 eff=0이어도 해당 부위가 100% 덮어써졌다(노드의
            #    "틀어지면 스스로 손을 놓는다"는 DNA가 깨짐). eff를 넘긴다.
            # ② 함수가 이미 `out + region*(...)`를 반환하는데 호출부가 다시
            #    `out + ...`로 더했다 → **텐서 전체가 2배**가 된다.
            # ③ ②를 고치면서 `continue` 로 region 분기가 전역 블렌드를
            #    **대체**하게 돼, strength_original 의 전역 전달량이 15~27%
            #    로 줄었다(커버리지 19%). → region 은 **추가분**으로 돌려주고
            #    전역 블렌드에 더한다. eff==0 이면 계산 자체를 건너뛴다
            #    (0*(inf-nan) 은 nan → 감쇠가 출력을 망가뜨림).
            if eff:
                if _mask is not None:
                    out = out + eff * _mask * (matched - sampled)
                else:
                    out = out + eff * (matched - sampled)
            # 부위별 상향은 전역 결과에 **더하는 추가분**이다.
            # eff == 0 이면 계산하지 않는다(0*inf = nan 방지).
            if name == "original" and _pm and eff > 0:
                _allow = None
                if trust_gate:
                    # 판정층 1층(work_status 10절). 원본 쪽 landmark 로
                    # "이 부위를 원본에서 당겨와도 되는가" 를 정한다.
                    # 판정이 없거나 vis 가 없으면 _allow=None = 제한 없음,
                    # 즉 기존 동작으로 떨어진다(조용히 막지 않는다).
                    # 왜(Why) _verdict 를 미리 None 으로 두나: 아래 else 분기가
                    # `_verdict.get("verdict")` 을 읽는데, _pts 가 없으면
                    # _verdict 가 대입 안 된다. 지금은 `_allow is not None` 이
                    # _pts 존재를 함의해서 안전하지만, 나중에 조건이 바뀌면
                    # UnboundLocalError 가 된다. 한 줄로 고정한다.
                    _verdict = None
                    _pts = (_pm.get("original") or {}).get("pts")
                    if _pts:
                        _verdict = judge_points(_pts)
                        _allow = judge_region_allowance(_verdict)
                    # 손가락 판정 (2026-10-02): 포즈 33점은 손가락 개수를 못 센다.
                    # 손 모델로 손 개수·끝점 분리를 보고, 손상됐으면 손 부위를 막는다.
                    # 포즈 게이트와 AND — 어느 한쪽이라도 막으면 막는다.
                    _hand_verdict = None
                    if _allow is not None:
                        try:
                            import numpy as _np_h
                            _h_rgb = _decode_latent_rgb(vae, _orig_ref, cache=_dcache)
                            _h_hs = None
                            if _h_rgb is not None:
                                _h_u8 = (_np_h.clip(_h_rgb, 0, 1) * 255).astype(_np_h.uint8)
                                _h_hs = _hand_landmarks_from_tasks(_h_u8)
                            if _h_hs:
                                _h_j = judge_hands(_h_hs)
                                _hand_verdict = _h_j.get("verdict")
                                if _hand_verdict == _JUDGE_DAMAGED:
                                    # 손상된 손은 원본에서 당겨오면 오류를 재주입한다.
                                    # 손 부위만 막고 나머지는 포즈 판정을 따른다.
                                    # 왜(Why) 양손을 함께 막나 (2026-10-05 감사 75차):
                                    # judge_hands 는 검출된 손 전체의 최악 끝마디
                                    # 간격 하나로 통합 판정한다(좌/우 개별 판정
                                    # 아님). 좌/우 handedness 라벨은 미러 이미지에서
                                    # 뒤집힐 수 있어(_hand_landmarks_from_tasks
                                    # 주석) 의도적으로 쓰지 않았다 — 양손 차단은
                                    # 과소 복원 방향이지 잘못된 손의 상향이 아니다.
                                    for _hr in ("hand_left", "hand_right"):
                                        if _hr in _allow:
                                            _allow[_hr] = 0.0
                                    _log("[GoRi Consistency Keeper] 손가락 게이트: "
                                         "원본 손 손상 — 손 부위를 당기지 않습니다")
                        except Exception as _he:
                            # 손 판정 실패는 포즈 판정을 덮지 않는다. 조용히 넘어가되
                            # 사유는 남긴다 (조용한 무력화 방지).
                            # 왜(Why) _pose_gate_message 를 안 쓰나 (2026-10-04
                            # 감사 5차): 그 메시지는 "원본 landmark 없음 → 제한 없이
                            # 진행합니다" 라는데, 여기는 landmark 가 **있는**
                            # 분기이고 예외 뒤에도 _allow 가 남아 제한이 적용된다.
                            # 손 게이트 전용 문구로 바로 쓴다.
                            _note_pose_why("hand_gate",
                                           "[GoRi Consistency Keeper] ⚠ "
                                           "손 판정 예외 (게이트 유지): %s: %s" % (
                                               type(_he).__name__, str(_he)[:50]))
                    if _allow is None:
                        # 왜(Why) 판단하지 않고 그대로 말하나 (2026-10-01):
                        # "사람이 없는 이미지" 라고 단정하면 추측이 된다.
                        # 판단은 하지 않고 **사유를 드러낸다**. 판단은 실측
                        # 근거가 쌓인 뒤에 한다.
                        _why = _POSE_WHY.get("original", "사유 기록 없음")
                        _note_pose_why("gate", _pose_gate_message(_why))
                        _allow = None
                    else:
                        _blocked = sorted(k for k, v in _allow.items()
                                          if float(v) <= 0.0)
                        _verdict_name = (_verdict.get("verdict")
                                         if _verdict else "?")
                        # 손 판정도 함께 보고한다 — 실행됐는지 구분하기 위해.
                        # _hand_verdict 가 None 이면 손 검출 없음/미실행이다.
                        _hand_txt = (" 손=%s" % _hand_verdict
                                     if _hand_verdict else "")
                        _log("[GoRi Consistency Keeper] 판정 게이트 "
                             f"(verdict={_verdict_name}{_hand_txt}) — 차단 부위 "
                             f"{_blocked if _blocked else '없음'}")
                _darr, _regions = detail_boost(_pm, _pm, eff, allow=_allow)
                if _darr is not None:
                    try:
                        _inc = _apply_region_strength(
                            eff, matched, sampled, _darr, _pm, _mask)
                        if _inc is not None:
                            out = out + _inc
                            _log(f"[GoRi Consistency Keeper] 부위별 복원 강도 상향 "
                                 f"({_regions}) — 원본이 살아있는데 결과가 "
                                 f"뭉개진 부위를 원본으로 당겨옵니다")
                    except Exception as e:
                        # 왜(Why) 로그를 남기는가: 예전엔 `pass`였다. 그
                        # 침묵 때문에 "이 기능이 아예 실행된 적 없다"를
                        # 한참 알 수 없었다.
                        _log(f"[GoRi Consistency Keeper] ⚠ 부위별 복원 실패 "
                             f"({type(e).__name__}: {e}) — 전역 당김만 적용")
        _probe_detail_direction(vae, sampled, _orig_ref, out)
        # 마스터 게인: 전체 보정량을 strength_sampler 로 스케일한다.
        # 왜(Why) 끝에서 한 번에 하나: 보정은 전부 `sampled + ...` 형태라
        # `sampled + s*(out-sampled)` 이 각 eff 에 s 를 곱한 것과 수학적으로 같다.
        # 두 곳(전역·부위)에 따로 넣으면 한쪽만 빠뜨리는 사고가 난다.
        # s==1.0 이면 바이트 단위로 기존과 같다 (곱셈 항등원).
        if s != 1.0:
            try:
                out = sampled + s * (out - sampled)
                # 왜(Why) 로그를 남기나 (2026-10-05 감사 63차): 위 per-ref
                # 로그의 "당김 0.20" 은 게인 적용 전 값이다. 특히 s<0 에서는
                # 당김이 밀어냄으로 뒤집히므로 무음이면 로그가 거짓말이 된다
                # (R28 의 로그 진실성 계약).
                _log(f"[GoRi Consistency Keeper] sampler 게인 {s:+.2f} 적용 — "
                     "위 당김 표기에 이 배율이 곱해진 값이 최종 보정입니다")
            except Exception as _e:
                _log(f"[GoRi Consistency Keeper] ⚠ sampler 게인 적용 실패 "
                     f"({type(_e).__name__}) — 게인 없이 반환")
        # 판정 주도 교정 당김 (2026-10-05). repair_enable 을 켠 실행만 여기 온다 —
        # 기본 경로는 이 블록 전체가 없는 것과 같다(결과 바이트 단위 동일).
        # 왜(Why) 마스터 게인 뒤인가: 교정의 대상은 **최종 출력**이다. 당김
        # 결과가 다시 파손 부위를 물어온 경우까지 검증하려면 블렌드가 모두
        # 끝난 뒤여야 한다. 게인 앞에 두면 교정 결과에 게인이 재적용돼
        # 이중 보정이 된다.
        if repair_enable and _multi:
            _log("[GoRi Consistency Keeper] repair_enable — 배치 실행에서는 "
                 "교정 당김을 지원하지 않습니다 (전역 당김만 적용)")
        elif repair_enable:
            if _pm is None and vae is not None:
                # 왜(Why) 자체 계산인가: strength_original 이 0 이면 위
                # 블록이 _pm 을 만들지 않는다. 당김은 결과물 판정이
                # 필요하므로 여기서 sampled 만 디코드한다. _dcache 덕에
                # 이미 디코드돼 있으면 0원이다.
                _pm = _part_detail_map(vae, {"sampled": sampled},
                                       cache=_dcache)
            _orig_rgb = None
            if original_image is not None:
                try:
                    import numpy as _np_o
                    _oi = original_image
                    if hasattr(_oi, "detach"):
                        _oi = _oi.detach().cpu().numpy()
                    # 왜(Why) _as_rgb_hwc 를 쓰나 (2026-10-07 감사): 여기만
                    # 축·채널 처리가 따로 라디었다. R87 이 증명하는 0~1 clip
                    # 계약과 4채널 방어를 공식 경로로 쓴다 — 수치는 같고
                    # (H,W,3) 이 아닌 입력만 방어가 강해진다.
                    _ohw = _as_rgb_hwc(_oi)
                    _orig_rgb = (None if _ohw is None else
                                 (_ohw * 255.0).astype(_np_o.uint8))
                    if _orig_rgb is None:
                        _note_once(
                            "orig_rgb_convert",
                            "[GoRi Consistency Keeper] ⚠ 원본 이미지를 RGB "
                            "배열로 바꾸지 못했습니다 (shape=%s) — 피부 편차 "
                            "판독을 건너뜁니다"
                            % (getattr(_oi, "shape", None),))
                except Exception:
                    _orig_rgb = None
            out, _rec = _skeleton_pull_pass(vae, sampled, out,
                                            _pm, _dcache,
                                            orig_rgb=_orig_rgb)
            _learn_append(_rec)
        _release_vram()
        return _with_samples(sampled_latent, out)
