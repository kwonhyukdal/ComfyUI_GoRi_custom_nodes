# -*- coding: utf-8 -*-
"""(GoRi) 신체 해부학 스탠다드 규격 — 판정기의 정상 목표 데이터.

이 모듈은 데이터와 순수 함수만 둔다 (검출·디코딩·로그 없음).
mediapipe 포즈 33점(BlazePose, (x, y, visibility) 3-튜플)을 입력으로 받아
2D 투영으로 검증 가능한 물리 규칙을 검사한다.

임계값 원칙 (저장소 원칙: 실측 전에 추측으로 판정하지 않는다):
  - 모든 임계값은 PROVISIONAL 이다. 2026-10-01 실측에서 정상 사진의
    투영 팔길이 좌우 차가 몸통길이 기준 0.745 까지 났으므로, 2D 투영에
    민감한 **비율 검사는 의도적으로 넣지 않았다.** 여기 넣은 검사는
    몸통 축이 대략 수직일 때만 성립하는 위/아래 순서 검사뿐이다.
  - 학습 축적(learn_log)이 정상/파손 분포를 쌓으면 그 실측으로
    임계값을 확정하고 PROVISIONAL 을 내린다.

검사 설계 (왜 이 3개인가):
  - 머리는 어깨 위, 엉덩이는 어깨 아래, 발목은 엉덩이 아래 — 서 있는
    그림에서 이 순서가 어긋나는 것은 포즈가 아니라 파손일 확률이 높다.
  - 앉은 자세·눕는 자세·크게 기울인 구도는 torso 축 수직 조건이나
    순서 하나만 어기게 되므로, 통합 판정은 검사 2개 이상 실패에서만
    damaged 를 연다 (DAMAGED_MIN_CHECKS). 정상 구도를 파손으로
    오판하는 비용이 수술 1회보다 크기 때문이다.
"""

SPEC_VERSION = "1"

# 임계값이 실측 확정 전임을 표시한다. 학습 축적이 근거를 쌓으면 내린다.
PROVISIONAL = True

# 순서 위반을 골격으로 교정할 때 쓰는 표준 간격 (정규화 좌표, 프레임 높이
# 기준 비율). 2026-10-01 실측(투영 팔길이 좌우 차 0.745)이 보여주듯 2D
# 투영상 절대 거리는 카메라에 따라 흔들리므로, 교정도 "방향만 바로 잡는
# 최소 간격"으로 둔다. 학습 축적이 정상 분포를 쌓으면 확정한다.
STANDARD_GAPS = {
    "head_above_shoulders": 0.08,
    "hips_below_shoulders": 0.15,
    "ankles_below_hips": 0.25,
}

# 통합 판정이 damaged 를 열기 위한 최소 실패 검사 수. 근거는 모듈 docstring.
DAMAGED_MIN_CHECKS = 2

# 몸통 축 수직 판정: 어깨 중점과 엉덩이 중점을 잇는 벡터의 |dy| 가
# |dx| 의 이 배수 이상이어야 "서 있는" 그림으로 본다. 3.0 이면 축이
# 세로축에서 약 18도 이상 기울지 않은 경우만 수직으로 셈이다 (tan 역수).
VERTICAL_AXIS_MIN = 3.0

# 검사 대상 점의 가시성 하한. judge_points 의 _JUDGE_VIS_MIN(0.30,
# 관절 132점 실측 분포)과 다른 값인 이유: 여기는 **판정을 여는** 검사라
# 거의 안 보이는 점으로 위/아래 순서를 말하면 관측값을 신뢰하는 것이
# 된다. 0.5 는 "명확히 보이는" 점만 검사에 쓰겠다는 뜻이다.
CHECK_VIS_MIN = 0.5

# BlazePose 33점 인덱스 (검사에 쓰는 것만 명시한다)
LM_NOSE = 0
LM_SHOULDER_L = 11
LM_SHOULDER_R = 12
LM_HIP_L = 23
LM_HIP_R = 24
# 왜(Why) 27/28 인가: BlazePose 33점에서 29/30은 뒤꿈치(heel)다.
# 29/30을 발목으로 쓰면 correct_order_violations 가 뒤꿈치 y 만
# 옮기고 실제 발목은 제자리인 기형 하퇴 골격을 만든다(2026-10-07
# 감사 실측). anatomy_parts.py 도 같은 위상(LM_ANKLE_L=27,
# LM_ANKLE_R=28)을 쓴다 — 두 파일이 일치한다(2026-10-07 감사로 맞췄다).
LM_ANKLE_L = 27
LM_ANKLE_R = 28


def _pt(pts, i):
    """인덱스 i 의 (x, y, visibility) 를 float 로. 없거나 불량이면 None."""
    if pts is None or i >= len(pts):
        return None
    lm = pts[i]
    try:
        x, y = float(lm[0]), float(lm[1])
        vis = float(lm[2]) if len(lm) >= 3 else 0.0
    except (TypeError, ValueError, IndexError):
        return None
    if x != x or y != y or vis != vis:      # NaN 은 검사 대상이 아니다
        return None
    return (x, y, vis)


def _mid(a, b):
    """두 점의 중점 (가시성은 낮은 쪽을 따른다). 한쪽이라도 None 이면 None."""
    if a is None or b is None:
        return None
    vis = min(a[2], b[2])
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, vis)


def check_body_physics(pts):
    """포즈 33점 -> 물리 검사 리스트. 검사 불가면 [].

    반환 항목: {check_id, ok, detail, value, target, regions}
      - value/target 은 학습 축적이 정상·파손 분포를 재구성할 수 있게
        남기는 실측값이다. target 은 "이 방향/크기여야 한다" 의 기준.
      - regions 는 실패했을 때 수술 마스크가 덮을 PART_REGIONS 부위명.
        통과한 검사에서도 regions 를 남긴다 (마스크 후보 표기용).
    """
    checks = []
    sh = _mid(_pt(pts, LM_SHOULDER_L), _pt(pts, LM_SHOULDER_R))
    hp = _mid(_pt(pts, LM_HIP_L), _pt(pts, LM_HIP_R))
    if sh is None or hp is None or sh[2] < CHECK_VIS_MIN \
            or hp[2] < CHECK_VIS_MIN:
        # 어깨·골반 중점이 안 보이면 축부터 성립하지 않는다 — 검사 불가.
        return checks
    dx = hp[0] - sh[0]
    dy = hp[1] - sh[1]
    if abs(dy) < VERTICAL_AXIS_MIN * abs(dx):
        # 앉거나 눕거나 크게 기울인 구도 — 순서 검사는 여기서 못 한다.
        return checks

    def _order(check_id, top, bottom, regions, detail_ok, detail_bad):
        """top 점이 bottom 점보다 위(y 작음)여야 하는 검사 한 항목."""
        if top is None or bottom is None or top[2] < CHECK_VIS_MIN \
                or bottom[2] < CHECK_VIS_MIN:
            return
        value = bottom[1] - top[1]      # 양수 = top 이 위 (정상 방향)
        checks.append({
            "check_id": check_id,
            "ok": value >= 0.0,
            "detail": detail_ok if value >= 0.0 else detail_bad,
            "value": round(value, 4),
            "target": ">= 0.0",
            "regions": list(regions),
        })

    nose = _pt(pts, LM_NOSE)
    _order("head_above_shoulders", nose, sh, ("face",),
           "머리가 어깨 위",
           "수직 구도에서 머리가 어깨 아래 — 파손 가능성")
    _order("hips_below_shoulders", sh, hp, ("torso",),
           "엉덩이가 어깨 아래",
           "수직 구도에서 엉덩이가 어깨 위 — 파손 가능성")
    _order("ankles_below_hips",
           hp, _mid(_pt(pts, LM_ANKLE_L), _pt(pts, LM_ANKLE_R)),
           ("leg_left", "leg_right"),
           "발목이 엉덩이 아래",
           "수직 구도에서 발목이 엉덩이 위 — 파손 가능성")
    return checks


def correct_order_violations(pts, checks):
    """판정에서 실패한 순서 검사를 STANDARD_GAPS 로 바로 잡은 좌표를 돌려준다.

    pts 는 (x, y, visibility) 3-튜플 열, checks 는 check_body_physics 의
    반환. 실패한 순서 검사가 없으면 None — 호출부는 "고칠 것이 없다"를
    구분해야 한다 (교정 없이 골격을 그리면 불필요한 당김이 된다).

    교정 원칙: **x 는 건드리지 않는다.** 좌우 위치(구도)는 사용자 의도고,
    이 함수가 고치는 것은 위/아래 순서(해부학·물리)뿐이다. 이동도 위반한
    점 그룹만 STANDARD_GAPS 만큼 옮기고 나머지는 그대로 둔다.
    """
    if not pts or not checks:
        return None
    sh = _mid(_pt(pts, LM_SHOULDER_L), _pt(pts, LM_SHOULDER_R))
    hp = _mid(_pt(pts, LM_HIP_L), _pt(pts, LM_HIP_R))
    if sh is None or hp is None:
        return None
    out = [list(p) if isinstance(p, (list, tuple)) else None for p in pts]
    if any(p is None for p in out):
        return None
    fixed = False

    def _set_y(idx, y):
        nonlocal fixed
        # 왜(Why) clamp (2026-10-07 감사): 어깨 y 가 표준 간격보다 화면
        # 상단에 가까우면 `sh[1] - gap` 이 음수가 되어 랜드마크가 [0,1]
        # 밖으로 나간다 — 렌더·비율 계산이 정의 밖 값을 받는다.
        # 경계(0/1)로 붙이는 것이 기대 순서는 그대로 유지한다.
        out[idx][1] = min(1.0, max(0.0, float(y)))
        fixed = True

    for c in checks:
        if c.get("ok", True):
            continue
        cid = c.get("check_id")
        gap = STANDARD_GAPS.get(cid)
        if gap is None:
            continue
        if cid == "head_above_shoulders":
            _set_y(LM_NOSE, sh[1] - gap)
        elif cid == "hips_below_shoulders":
            _set_y(LM_HIP_L, sh[1] + gap)
            _set_y(LM_HIP_R, sh[1] + gap)
        elif cid == "ankles_below_hips":
            _set_y(LM_ANKLE_L, hp[1] + gap)
            _set_y(LM_ANKLE_R, hp[1] + gap)
    if not fixed:
        return None
    return [tuple(p) for p in out]


def summarize_checks(checks):
    """검사 리스트 -> 통합 판정 dict.

    반환: {verdict, confidence, failed, regions}
      - verdict 는 consistency_keeper 의 _JUDGE_* 문자열과 같은 값을 쓴다
        ("intact" / "damaged" / "undetermined"). 원래 keeper 상수를
        import 하지 않는 이유는 순환 참조를 만들지 않기 위해서다.
      - 실패 검사가 있어도 DAMAGED_MIN_CHECKS 미만이면 undetermined —
        검사 하나는 투영 조건(앉음, 눕음, 카메라 각도)의 영향을 받는다.
      - 검사 **0건**은 0건 전부 통과와 다르다 (2026-10-07 감사): 근거가
        하나도 없는데 intact conf 1.0 을 주면 "증거 없는 확신" 이 된다 —
        축이 눕은 그림의 _sit90=[] 과 같은 입력이다. undetermined conf 0.0.
    """
    checks = list(checks or ())
    failed = [c for c in checks if not c.get("ok", True)]
    regions = set()
    for c in failed:
        for r in (c.get("regions") or ()):
            regions.add(str(r))
    if not failed:
        if not checks:
            return {"verdict": "undetermined", "confidence": 0.0,
                    "failed": [], "regions": []}
        return {"verdict": "intact", "confidence": 1.0,
                "failed": [], "regions": []}
    if len(failed) >= DAMAGED_MIN_CHECKS:
        return {"verdict": "damaged",
                "confidence": min(0.9, 0.5 + 0.1 * len(failed)),
                "failed": [c.get("check_id", "?") for c in failed],
                "regions": sorted(regions)}
    return {"verdict": "undetermined", "confidence": 0.5,
            "failed": [c.get("check_id", "?") for c in failed],
            "regions": sorted(regions)}
