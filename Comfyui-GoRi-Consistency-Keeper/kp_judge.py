# -*- coding: utf-8 -*-
"""판정층 레퍼런스 판정·부위 allowance·손 판정."""

from __future__ import annotations

try:
    from .kp_math import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from kp_math import *  # noqa: F403

# 물리 판정 표준 (judge_points 의 physics=True 경로가 직접 부른다).
try:
    from .anatomy_standard import (
        check_body_physics as _check_body_physics,
        summarize_checks as _summarize_checks,
    )
except ImportError:  # 스탠드얼론/테스트 실행용
    from anatomy_standard import (
        check_body_physics as _check_body_physics,
        summarize_checks as _summarize_checks,
    )

# 왜(Why) anatomy_parts 에서 가져오나 (2026-10-07 감사): 손끝 인덱스는 한
# 곳에서만 정의한다 — anatomy_parts.FINGER_TIPS 가 그곳이고 여기는 복제하지
# 않는다. 두 상수가 갈라지면 판정(이쪽)과 기록(쪽)이 다른 손가락을 본다.
try:
    from .anatomy_parts import FINGER_TIPS
except ImportError:  # 스탠드얼론/테스트 실행용
    from anatomy_parts import FINGER_TIPS


__all__ = [
"_JUDGE_INTACT", "_JUDGE_DAMAGED", "_JUDGE_UNDETERMINED", "_JUDGE_CORE_LANDMARKS", "_judge_triples", "_judge_body_frame", "_JUDGE_VIS_MIN", "_JUDGE_TORSO_MIN", "judge_points", "judge_region_allowance", "judge_hands", "_HAND_TIPS", "_HAND_TIP_MIN_SEP", "_HAND_COUNT_MAX_OK", "_repair_regions_from_verdicts", "PART_REGIONS"
]


# ---------------------------------------------------------------------------
# 판정층 1층 (2026-10-01, WORK_STATUS 10절)
#
# 원본 영역을 **믿어도 되는지** 판정한다. 절대 평가("이 자세가 옳나")가 아니다.
# 원본이 캐릭터의 기준이므로 정상이면서 극적인 자세가 탈락해서는 안 된다.
# 따라서 관절 가동범위·체격 비례·좌우 대칭은 **판정 근거가 아니다.**
# WORK_STATUS 10-1 에서 방향을 정정한 이유다.
# ---------------------------------------------------------------------------

_JUDGE_INTACT = "intact"


_JUDGE_DAMAGED = "damaged"


_JUDGE_UNDETERMINED = "undetermined"


# 판정 대상 관절. 발은 **제외**한다 (2026-10-01 실측 근거는 아래 주석 참조).
_JUDGE_CORE_LANDMARKS = (
    (11, "l_shoulder"), (12, "r_shoulder"),
    (13, "l_elbow"), (14, "r_elbow"),
    (15, "l_wrist"), (16, "r_wrist"),
    (23, "l_hip"), (24, "r_hip"),
    (25, "l_knee"), (26, "r_knee"),
)


# 왜(Why) 관절 10개만인가 — 실측(2026-10-01, conf 0.3, 검출 11장, 관절별 중앙값):
#   어깨 1.00 · 팔꿈치 0.87~0.97 · 손목 0.81~0.90 · 골반 1.00 · 무릎 0.81~0.85
#   발목 0.21 · 발뒤꿈치 0.19 · 발끝 0.08
# 팔·다리는 중앙값이 높지만 **발은 0.1~0.2 다** — 관측값 자체가 신뢰할 수 없다.
# 발에 같은 임계를 걸면 정상 발도 전부 미판정이 되므로 판정 대상에서 뺀다.
# 무릎은 중앙값 0.83 이므로 판정 안에 남는다.

# 가시성 임계 0.30 의 근거 (2026-10-01 실측): 팔다리 관절 132점 중 **77%** 가
# 0.30 이상이고 중앙값은 0.93 이다. 0.50 으로 올리면 77% → 72% 로 떨어져
# 정상 팔·다리를 미판정으로 버린다. 추측 숫자가 아니라 분포에서 고른 값이다.
_JUDGE_VIS_MIN = 0.30


# 몸통(중어깨→중골반) 길이 하한. 실측 정상 검출 구간은 0.156~0.511 이다.
# 0.02 는 그 최솟값보다 7.8배 낮으므로 **퇴화 프레임만** 걸러내는 용도이며
# 정상 판정에 영향하지 않는다.
_JUDGE_TORSO_MIN = 0.02


def _judge_triples(landmarks):
    """landmark 열 -> [(x, y, visibility)] 리스트. 해석 불가하면 None 항목.

    왜(Why) 형태를 두 가지 다 받나: 경로마다 landmark 모양이 다르다 (구
    `mediapipe.solutions` 는 속성 객체, tasks API 는 튜플). 한쪽만 받는 코드는
    반대쪽 경로에서 **조용히** 전부 None 이 된다 — `subject_bbox` 가 그 사고를
    겪었다. 그래서 여기서 한 번 통일한다.
    """
    out = []
    if landmarks is None:
        return out
    for lm in landmarks:
        if isinstance(lm, (tuple, list)) and len(lm) >= 2:
            x, y = lm[0], lm[1]
            vis = lm[2] if len(lm) >= 3 else None
        else:
            x = getattr(lm, "x", None)
            y = getattr(lm, "y", None)
            vis = getattr(lm, "visibility", None)
        if x is None or y is None:
            out.append(None)
            continue
        out.append((float(x), float(y),
                    float(vis) if vis is not None else 0.0))
    return out


def _judge_body_frame(tri):
    """몸통 기준 프레임 -> (ox, oy, scale). 퇴화면 None.

    왜(Why) 몸통길이가 단위인가 (WORK_STATUS 10-2): landmark 좌표는 이미지마다
    정규화 스케일이 다르다. 중골반을 원점으로, 중어깨→중골반 거리를 단위로 삼으면
    거리·프레이밍이 상쇄되어 같은 사람의 비율이 항상 같은 숫자가 된다.
    """
    if not tri or len(tri) < 33:
        return None
    try:
        ls, rs = tri[11], tri[12]
        lh, rh = tri[23], tri[24]
        if ls is None or rs is None or lh is None or rh is None:
            return None
        ox = (lh[0] + rh[0]) * 0.5
        oy = (lh[1] + rh[1]) * 0.5
        sx = (ls[0] + rs[0]) * 0.5
        sy = (ls[1] + rs[1]) * 0.5
        scale = ((sx - ox) ** 2 + (sy - oy) ** 2) ** 0.5
        if scale < _JUDGE_TORSO_MIN:
            return None
        return (ox, oy, scale)
    except (TypeError, ValueError, IndexError):
        # ZeroDivisionError 는 올 수 없다 — 나눗셈이 없고 **0.5 제곱(**0.5)은
        # 0 에서 0.0 을 돌려준다. 선언해두면 "여기서 0 나눔이 난다" 는 거짓
        # 기대를 만든다.
        return None


def judge_points(pts, physics=False):
    """landmark 열 -> 판정 dict (순수 함수, 검출 없음).

    physics=True 면 anatomy_standard 의 물리 규칙 검사가 추가되고,
    실패가 DAMAGED_MIN_CHECKS 이상이면 damaged 를 연다. 기본값 False —
    기존 호출부·테스트는 이 검사가 없는 결과를 그대로 받는다.
    반환 dict 에는 physics 여부와 무관하게 "damage_regions" 키가 있다
    (기본 경로는 항상 빈 리스트 — 소비자는 키 존재를 가정해도 된다).

    반환::

        {"verdict": "intact"|"damaged"|"undetermined",
         "confidence": float,
         "checks": [{"check_id", "ok", "detail"}],
         "low_visibility": [관절 이름],
         "low_indices": [관절 인덱스],
         "frame": (ox, oy, scale) or None}

    왜(Why) v1 은 damaged 를 **반환하지 않는다**: 기하 판정을 실측해 봤는데
    쓸 만한 신호가 없었다. 정상 사진에서 투영 팔길이의 좌우 차이가 최대 0.745
    (몸통길이 기준, 2026-10-01 실측) 나 났다 — 한쪽 팔이 앞으로 나온 사진에서는
    그게 정상이다. 임계값을 추측으로 넣으면 정상 사진의 절반이 "손상" 으로
    분류된다. 그러니 기하 검사 없이 판정할 수 있는 유일한 신뢰 신호인
    **가시성만** 쓴다. 기준 데이터를 실측해 넣을 때 damaged 를 연다.
    `_JUDGE_DAMAGED` 는 그때를 위해 상수로 남아 있다.

    왜(Why) undetermined 가 꼭 필요한가: 발 가시성은 실측 중앙값이 0.08~0.21 다.
    이걸 "정상"으로 떨어뜨리면 **스스로도 못 본 영역을 신뢰**하게 된다.
    그게 지금 strength 가 0.00 으로 죽는 사고와 같은 종류다.
    """
    checks = []
    tri = _judge_triples(pts)
    if not tri:
        checks.append({"check_id": "pose_detected", "ok": False,
                       "detail": "landmark 없음"})
        return {"verdict": _JUDGE_UNDETERMINED, "confidence": 1.0,
                "checks": checks, "low_visibility": [], "low_indices": [],
                "frame": None}

    checks.append({"check_id": "pose_detected", "ok": True, "detail": ""})

    frame = _judge_body_frame(tri)
    if frame is None:
        checks.append({"check_id": "body_frame", "ok": False,
                       "detail": "몸통 길이가 하한 이하거나 퇴화"})
        return {"verdict": _JUDGE_UNDETERMINED, "confidence": 1.0,
                "checks": checks, "low_visibility": [], "low_indices": [],
                "frame": None}
    checks.append({"check_id": "body_frame", "ok": True, "detail": ""})

    low = []
    low_idx = []
    worst = 1.0
    for idx, name in _JUDGE_CORE_LANDMARKS:
        lm = tri[idx] if idx < len(tri) else None
        vis = 0.0 if lm is None else lm[2]
        if vis < worst:
            worst = vis
        if vis < _JUDGE_VIS_MIN:
            low.append(name)
            low_idx.append(idx)
    vis_ok = not low
    checks.append({
        "check_id": "core_visibility",
        "ok": vis_ok,
        "detail": "" if vis_ok else "미확인 관절: " + ", ".join(low),
    })

    verdict = _JUDGE_INTACT if vis_ok else _JUDGE_UNDETERMINED
    # 물리 규칙 검사 (2026-10-05, opt-in). 왜(Why) 기본이 꺼져 있는가:
    # anatomy_standard 의 임계값은 PROVISIONAL 이다. 기본 경로에서
    # 켜두면 프로비전 임계의 오판이 기존 사용자 결과를 바꾼다. 켜는
    # 쪽(repair_enable)이 그 판단을 한다 — trust_gate 와 같은 opt-in 원칙.
    _dmg_regions = []
    if physics and tri:
        try:
            _ph = _check_body_physics(tri)
            checks.extend(_ph)
            _ph_sum = _summarize_checks(_ph)
            if _ph_sum.get("verdict") == _JUDGE_DAMAGED:
                verdict = _JUDGE_DAMAGED
                _dmg_regions = list(_ph_sum.get("regions") or ())
        except Exception as _pe:
            # 물리 검사의 예외가 판정 전체를 죽이지 않는다. 다만 조용히
            # 지우지는 않는다 — 사유를 checks 에 남겨 학습 기록이 본다.
            checks.append({"check_id": "body_physics", "ok": False,
                           "detail": "물리 검사 예외: %s"
                                     % type(_pe).__name__})
    # confidence 는 "그 판정을 내리는 근거의 세기"다. intact 면 가장 흐린
    # 관절의 가시성이 곧 근거이고, undetermined 면 그것이 미판정의 근거다.
    return {"verdict": verdict, "confidence": max(0.0, min(1.0, worst)),
            "checks": checks, "low_visibility": low, "low_indices": low_idx,
            "frame": frame, "damage_regions": _dmg_regions}


PART_REGIONS = {
    "face": (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    "hand_left": (15, 17, 19, 21),
    "hand_right": (16, 18, 20, 22),
    "arm_left": (11, 13, 15),
    "arm_right": (12, 14, 16),
    "leg_left": (23, 25, 27, 29, 31),
    "leg_right": (24, 26, 28, 30, 32),
    "torso": (11, 12, 23, 24),
}


def judge_region_allowance(verdict):
    """판정 dict -> 부위별 당김 허용도 {부위명: 0.0|1.0}. 판정 없으면 None.

    왜(Why) 부위 정의를 새 로 만들지 않는가: 프로젝트에 이미 `PART_REGIONS` 가
    있고 `detail_boost` 가 그 순서를 그대로 순회한다. 관절 인덱스를 **그 표에
    그대로 물려서** 교집합을 내는 것이 새 부위 체계를 만드는 유일한 방법이다.
    두 개의 부위 표가 생기면 이후 갱신할 때 한쪽만 고치는 사고가 난다.

    왜(Why) 판정 대상이 아닌 부위는 1.0 인가: 얼굴(0~10)은 사용자가 "원본
    일관성을 따른다" 고 정해서 판정에서 제외했다(10절). 그 부위를 0 으로 주면
    얼굴 신원 복원이 꺼져 버린다 — 사용자가 정한 결정을 코드가 뒤집는 셈이다.
    판정하지 않는다는 것은 **허용**이라는 뜻으로 쓴다.

    반환이 None 이면 판정이 없다는 뜻이고, 호출부는 None 을 "제한 없음" 으로
    읽어 기존 동작을 그대로 둔다 (opt-in 구조).
    """
    if not verdict:
        return None
    low = set()
    for i in (verdict.get("low_indices") or ()):
        try:
            low.add(int(i))
        except (TypeError, ValueError):
            continue
    core = set(idx for idx, _n in _JUDGE_CORE_LANDMARKS)
    out = {}
    for region, idxs in PART_REGIONS.items():
        touched = core & set(idxs)
        if not touched:
            out[region] = 1.0          # 판정 대상 아님 → 허용
        else:
            out[region] = 0.0 if (touched & low) else 1.0
    return out


_HAND_TIPS = FINGER_TIPS


# 끝점 최소 간격. 왜(Why) 0.001 인가 (2026-10-02 실측 2차):
#   정상 손 (참조 10개)  0.0041 ~ 0.0419
#   정상 손 (생성 8개)    0.0013 ~ 0.0024  ← 닿아있지만 융합 아님 (육안 확인)
#   합성 융합손           0.0000
# 0.003 으로 잡으면 생성 8개 전부 damaged (오탐). "닿음" 과 "융합" 은 2D 거리로
# 완전히 못 가른다 — 융합은 좌표 일치(0.000) 수준에서만 확정된다.
# 0.001 은 최소 정상(0.0013) 바로 아래다. 여유가 얇으므로 실물 뭉개진 손이
# 나오면 그때 다시 잰다. 손 개수(3개+)는 임계와 무관하게 확정적이다.
_HAND_TIP_MIN_SEP = 0.001


# 손 개수 상한: 1~2 정상, 초과(3+) 여분 손.
# 왜(Why) 상수를 여기서만 정의하나 (2026-10-07 감사): keeper 도 당김 트리거용
# `_HAND_COUNT_MAX_OK` 를 따로 적어 두었다 — 같은 규칙 2곳 표기. 여기 하나가
# 공급원이고 keeper 는 star import 로 이 값을 받는다.
_HAND_COUNT_MAX_OK = 2


def judge_hands(hands):
    """손 21점 리스트 → 손가락 개수·분리 판정 dict (순수 함수, 검출 없음).

    반환은 `judge_points` 와 같은 형식이되 `low_indices` 는 없다:
        {"verdict": "intact"|"damaged"|"undetermined",
         "confidence": float,
         "checks": [{"check_id", "ok", "detail"}],
         "low_visibility": [],
         "frame": None}

    왜(Why) 손 개수를 세나 (2026-10-02): 포즈 33점은 손이 3개여도 33점 틀에
    맞추고 끝이라 여분을 셀 수 없다. 손 모델은 손마다 21점을 돌려주므로
    개수를 센다. 3개 이상이면 여분 손이다.
    왜(Why) 끝점 분리를 보나: 6가락은 "6개가 추가"되는 게 아니라 손가락 2개가
    붙거나 1개가 갈라져 나온다 (ANATOMY_COUNT_NEGATIVE 주석과 같은 실측).
    끝점 5개가 뭉쳐 있으면 뭉개진 손이다.
    """
    out = {"verdict": _JUDGE_UNDETERMINED, "confidence": 0.0, "checks": [],
           "low_visibility": [], "frame": None}
    try:
        hs = hands or []
        n = len(hs)
        if n == 0:
            out["checks"].append({"check_id": "hands_absent", "ok": True,
                                  "detail": "검출된 손 없음 (판단 보류)"})
            out["confidence"] = 1.0
            return out
        # 손 개수: 1~2 정상, 초과 여분 (상단 _HAND_COUNT_MAX_OK 가 공급원)
        if n > _HAND_COUNT_MAX_OK:
            out["verdict"] = _JUDGE_DAMAGED
            out["confidence"] = 0.9
            out["checks"].append({"check_id": "hand_count", "ok": False,
                                  "detail": "손 %d개 검출 (2개 초과)" % n})
            return out
        out["checks"].append({"check_id": "hand_count", "ok": True,
                              "detail": "손 %d개" % n})
        # 손가락 끝 5개 분리: 가장 가까운 두 끝점 사이 거리
        # 왜(Why) found 플래그가 필요한가: 21점 미만 손만 있으면 루프가 한 번도
        # 안 돌아 `worst` 가 초기값 1.0 으로 남는다. 그러면 "분리됨" 으로 판정해
        # intact 을 돌려준다 — 측정 불가인데 정상이라고 하는 거짓 확신이다.
        # `undetermined` 가 있어야 하는 자리다.
        worst = 1.0
        found = False
        for _hi, pts in enumerate(hs):
            if len(pts) < 21:
                continue
            tips = [(pts[i][0], pts[i][1]) for i in _HAND_TIPS if i < len(pts)]
            if len(tips) < 5:
                continue
            for a in range(5):
                for b in range(a + 1, 5):
                    dx = tips[a][0] - tips[b][0]
                    dy = tips[a][1] - tips[b][1]
                    d = (dx * dx + dy * dy) ** 0.5
                    found = True
                    if d < worst:
                        worst = d
        if not found:
            out["checks"].append({"check_id": "fingertip_sep", "ok": False,
                                  "detail": "유효 21점 손 없음 (판단 보류)"})
            return out
        out["checks"].append({"check_id": "fingertip_sep", "ok": worst >= _HAND_TIP_MIN_SEP,
                              "detail": "최소 끝점 간격 %.4f (기준 %.3f)" % (worst, _HAND_TIP_MIN_SEP)})
        if worst < _HAND_TIP_MIN_SEP:
            out["verdict"] = _JUDGE_DAMAGED
            out["confidence"] = 0.8
        else:
            out["verdict"] = _JUDGE_INTACT
            out["confidence"] = 0.9
        return out
    except (TypeError, ValueError, IndexError):
        return out


# ---------------------------------------------------------------------------
# 판정 주도 교정 당김 (2026-10-05, v1.9.15 — v1.9.14 의 재샘플링 수술 폐기)
#
# 왜(Why) 여기서 교정 하나: 기본 경로는 "다시 그리지 않는다"가 DNA라
# 무너진 골격을 고칠 수 없었다(모듈 docstring). 사용자 정의(2026-10-05):
# "사용자의 의도를 반영해 원본의 일관성을 유지하고 신체 해부학 스탠다드를
# 유지한다" — 바뀐 포즈 안에서도 해부학은 정상이어야 하므로, 판정기가
# 파손 부위를 찾고 그 부위만 스탠다드 골격 참조 쪽으로 당긴다. 샘플러가
# 없어 비용은 VAE 인코딩 1회 + 판정 디코드 2회고, 파손이 없으면 0원이다.
# ---------------------------------------------------------------------------

def _repair_regions_from_verdicts(pose_verdict, hand_verdict):
    """판정 두 개 -> 당김 마스크가 덮을 PART_REGIONS 부위명 집합.

    왜(Why) 손 판정은 양손을 함께 덮나: judge_hands 는 좌/우를 못 가른다
    (handedness 라벨은 미러 이미지에서 뒤집힌다 — 손 게이트 3284행의
    선례와 같은 근거). 마스크는 과소 복원 방향으로 넓게 간다.
    """
    out = set()
    for r in ((pose_verdict or {}).get("damage_regions") or ()):
        out.add(str(r))
    if (hand_verdict or {}).get("verdict") == _JUDGE_DAMAGED:
        out.update(("hand_left", "hand_right"))
    return out
