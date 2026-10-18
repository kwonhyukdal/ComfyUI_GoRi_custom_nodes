"""손 물리 정합성 검증기 (GoRi Consistency Keeper - 옵션 A 확장).

목적: mediapipe hand 21점 + 원본 픽셀로부터 **인간 물리 법칙 위반**을
측정해 0~100 점을 돌려준다. 키퍼의 합격 로직(95% 선)이 이 점수를 쓴다.

검사 항목 (각 25점, 합 100):
  1. count  — 손가락 끝점 5개가 서로 떨어져 있는가 (뭉침=붙음=fail)
  2. cross  — 인접 손가락 골격선이 교차하는가 (겹침=fail)
  3. bend   — 마디 굴절이 생리학적 범위(앞굽힘)를 벗어나 역전되는가 (뒤꺾임=fail)
  4. nail   — 손가락 끝 픽셀에 손톱 그라데이션(어두운 테두리→밝은 네일)이 있는가

좌표계: mediapipe 는 정규화(x,y in 0~1, 이미지 좌상단 원점). 픽셀 변환은
호출부에서 해준다 (image_w, image_h 전달).

설계 노트 (2026-10-12):
  - 2D 각도만으로는 "앞/뒤 굽힘"을 완벽히 구분 못 한다. 그래서 bend 는
    **마디 벡터 역전**(p0->p1->p2 가 ±180° 가까이 역방향으로 꺾이는 위상 이상)
    만 fail 로 본다. 순수 굴절각은 정상 범위로 두어 오탐을 막는다.
  - nail 은 끝점에서 손톱 방향(손가락 중심축 연장)으로 몇 px 띄운 박스의
    명도 분포로 본다. 네일은 주변 피부보다 밝고 가장자리가 진하다.
  - 이 모듈은 **측정만** 한다. 수정(당김)은 consistency_keeper 의 hand_pull 이 한다.
"""

import math

# mediapipe hand 21점 인덱스
# 엄지 0-1-2-3-4, 검지 5-6-7-8, 중지 9-10-11-12, 약지 13-14-15-16, 소지 17-18-19-20
_FINGER_TIPS = (4, 8, 12, 16, 20)
_FINGER_BASES = (1, 5, 9, 13, 17)  # 마디 시작 (CMC/MCP 근처)
# 각 손가락의 4점 폴리라인 (base->...->tip)
_FINGER_CHAINS = [
    (1, 2, 3, 4),     # 엄지
    (5, 6, 7, 8),     # 검지
    (9, 10, 11, 12),  # 중지
    (13, 14, 15, 16), # 약지
    (17, 18, 19, 20), # 소지
]
# 인접 손가락 쌍 (겹침 판정 대상)
_ADJ_PAIRS = [(0, 1), (1, 2), (2, 3), (3, 4)]

# 임계값
_TIP_MIN_SEP = 0.018   # 정규화 좌표 기준, 끝점간 최소 분리 (이하=붙음)
_BEND_FLIP_DEG = 150.0 # 마디 벡터 역전 판정 (두 마디가 이 각도 이상 역방향)


# 두 점 사이 거리
def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seg_intersect(p1, p2, p3, p4):
    """두 선분 교차 여부 (표준 CCW 테스트)."""
    # 세 점 회전 방향(CCW) 부호 — 선분 교차 판정용
    def ccw(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


# 두 벡터 사이 각(도) — 길이가 0 이면 None
def _angle_between(v1, v2):
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    c = max(-1.0, min(1.0, dot / (n1 * n2)))
    return math.degrees(math.acos(c))


def score_one_hand(pts, image=None):
    """한 손의 21점(정규화) → 항목별 결과 dict.
    image: uint8 HWC (손톱용, None 이면 nail=0.5 로 중립).

    w/h 파라미터는 제거됐다 (2026-10-16 오딧): 손톱 샘플 좌표는
    image.shape 로 환산하므로 픽셀 크기를 따로 받을 이유가 없었고,
    호출부만 값을 넘기고 함수 안에서 쓰이지 않는 죽은 인자였다.
    """
    res = {"count_ok": True, "cross": False, "backward": False,
           "nail": 0.0, "sep_min": None, "note": []}
    if not pts or len(pts) != 21:
        res["count_ok"] = False
        res["note"].append("21점 아님")
        return res

    tips = [pts[i] for i in _FINGER_TIPS]

    # 1) count: 끝점 5개 분리
    seps = []
    for i in range(len(tips)):
        for j in range(i + 1, len(tips)):
            seps.append(_dist(tips[i], tips[j]))
    res["sep_min"] = min(seps) if seps else 0.0
    if res["sep_min"] < _TIP_MIN_SEP:
        res["count_ok"] = False
        res["note"].append("끝점 뭉침(붙음) sep=%.3f" % res["sep_min"])

    # 2) cross: 인접 손가락 폴리라인 교차
    chains = [[pts[k] for k in ch] for ch in _FINGER_CHAINS]
    for ai, bi in _ADJ_PAIRS:
        ca, cb = chains[ai], chains[bi]
        hit = False
        for s in range(len(ca) - 1):
            for t in range(len(cb) - 1):
                if _seg_intersect(ca[s], ca[s + 1], cb[t], cb[t + 1]):
                    hit = True
                    break
            if hit:
                break
        if hit:
            res["cross"] = True
            res["note"].append("겹침:%d-%d" % (ai, bi))
            break

    # 3) bend: 마디 벡터 역전
    for ch in _FINGER_CHAINS:
        for k in range(len(ch) - 2):
            p0, p1, p2 = pts[ch[k]], pts[ch[k + 1]], pts[ch[k + 2]]
            v1 = (p1[0] - p0[0], p1[1] - p0[1])
            v2 = (p2[0] - p1[0], p2[1] - p1[1])
            ang = _angle_between(v1, v2)
            if ang is None:
                continue
            # 순수 굴절각(0~180). 역전은 180 에 가까운데 벡터 방향이 반대인 경우.
            # 2D 에선 앞/뒤 불분명하므로, 마디가 "거의 180° 역방향으로 펴지는"
            # 위상 이상만 잡는다: cos<0 이면서 각도가 임계 이상.
            if ang >= _BEND_FLIP_DEG:
                # v1,v2 가 거의 반대 방향 -> 마디가 뒤로 꺾인 위상
                res["backward"] = True
                res["note"].append("뒤꺾임@%d" % ch[k + 1])
                break
        if res["backward"]:
            break

    # 4) nail: 손톱 그라데이션
    if image is not None:
        try:
            import numpy as _np
            arr = _np.asarray(image)
            ih, iw = arr.shape[0], arr.shape[1]
            nail_hits = 0
            for ti, t in enumerate(tips):
                px = int(t[0] * iw)
                py = int(t[1] * ih)
                # 끝점에서 손가락 안쪽(베이스 방향)으로 6~14px 박스 샘플
                bx = int(pts[_FINGER_BASES[ti]][0] * iw)
                by = int(pts[_FINGER_BASES[ti]][1] * ih)
                # 박스 좌상단
                x0, y0 = max(0, px - 8), max(0, py - 8)
                x1, y1 = min(iw, px + 8), min(ih, py + 8)
                if x1 - x0 < 3 or y1 - y0 < 3:
                    continue
                patch = arr[y0:y1, x0:x1]
                if patch.size == 0:
                    continue
                lum = patch.mean(axis=2) if patch.ndim == 3 else patch
                # 가장자리(외곽) vs 중심 밝기 비교
                edge = float(_np.percentile(lum, 20))
                core = float(_np.percentile(lum, 70))
                # 손톱은 중심이 가장자리보다 밝음 (네일 하이라이트)
                if core - edge > 8.0:
                    nail_hits += 1
            res["nail"] = nail_hits / max(1, len(tips))
        except Exception:
            res["nail"] = 0.0
    else:
        res["nail"] = 0.5  # 이미지 없으면 중립

    return res


def hand_physical_score(hands, image=None):
    """전체 손 → 종합 점수 dict.
    반환: {score(0~100), per_hand[...], detected(n), passed(bool)}

    점수 구성 (2026-10-12 설계 변경): **형태 3항목 100점 만점**.
      · count  (33.34) — 손가락 5개 분리
      · cross  (33.33) — 인접 손가락 비겹침
      · bend   (33.33) — 마디 비뒤꺾임
    nail(손톱)은 **합격 점수에 포함하지 않는다** — 손톱은 텍스처/디테일 영역이라
    키퍼의 latent 당김으로는 생성할 수 없다(2026-10-12 사용자 브리핑 합의).
    그래서 손톱은 per_hand[].nail 로만 로그에 남기고 passed 판정에서는 뺀다.
    이렇게 해야 "형태가 정상인 손"이 95점을 넘겨 합격할 수 있다.
    """
    if not hands:
        return {"score": 0.0, "per_hand": [], "detected": 0, "passed": False,
                "note": ["손 검출 실패"]}

    per = []
    total = 0.0
    for hpts in hands:
        r = score_one_hand(hpts, image=image)
        s = 0.0
        s += 33.34 if r["count_ok"] else 0.0
        s += 33.33 if not r["cross"] else 0.0
        s += 33.33 if not r["backward"] else 0.0
        r["score"] = s
        per.append(r)
        total += s

    score = total / len(hands)
    return {"score": round(score, 1), "per_hand": per, "detected": len(hands),
            "passed": score >= 95.0, "note": [n for r in per for n in r["note"]]}
