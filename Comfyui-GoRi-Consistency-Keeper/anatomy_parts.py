# -*- coding: utf-8 -*-
"""(GoRi) 신체 부위 카탈로그 — 판독 (v1.9.17, 2026-10-05).

사용자 확정 부위표 (27부위 + 손가락 5 ×2 + 발가락 5 ×2 + 콧구멍 2).
**불가 부위 없음** — 콧구멍은 FaceMesh(478점) 기하 판독, 발가락은 발
ROI 픽셀 블롭 판독으로 읽는다. 이 모듈은 데이터와 순수 함수만 둔다
(검출 세션·디코딩·로그 없음 — 검출기 세션은 keeper 가 둔다).

판독 근거 (모두 실측):
  - BlazePose 33점: 몸통·사지·손목·발 (수치는 anatomy_standard 참조).
  - 손 21점: 손가락별 4점 (mcp 2,5,9,13,17 / tip 4,8,12,16,20).
  - FaceMesh 478점 (face_landmarker.task, 2026-10-05 다운로드,
    Apache-2.0): 콧구멍은 **고정 인덱스를 쓰지 않는다** — 실측 프로브
    (3얼굴 교차, tools/_probe_face*.py)에서 콧구멍 후보 인덱스의 위치가
    얼굴마다 흔들렸다 (125/354 vs 97/94 vs 19/20). 대신 비강 기지
    밴드(along 0.03~0.12, |lateral| <= 0.10)에서 좌우 대칭 정점 2개를
    **매 실행 기하로 찾는다**. 이 방식은 얼굴 형태·머리 방향에 덜
    흔들린다. 콧구멍이 실제로 막힌 얼굴(극단)은 밴드 정점 수로
    "판독 불가"로 기록된다 — 위반이 아니라 보류다.
  - 발가락: BlazePose 는 뒤꿈치(29/30)·발끝(31/32)뿐이다. 발 ROI
    (뒤꿈치↔발끝 축, 전방 절반)에서 배경 대비 밝기 차로 블롭을 세어
    판독한다 (cv2, keeper 쪽에서 이미지 필요). PROVISIONAL — 발가락
    개수의 실측 분포가 learn_log 에 쌓이면 확정한다.

판독 기록의 소비처:
  - learn_log (키퍼 학습 데이터 축적 — 사용자 원 의도)
  - 부위 존재/개수 위반은 damage_regions 후보로 keeper 에 넘긴다
    (개수는 손 개수 패스처럼 검증 가능한 것만 판정, 나머지는 기록).
"""

SPEC_VERSION = "2"

# --- BlazePose 33점 (MediaPipe / anatomy_standard 와 같은 표기) -------------
# 왜(Why) 2026-10-07 감사로 좌우를 바꿨나: 구 표기는 전부 뒤집혀 있었다
# (LM_EYE_R=2 를 "피사체 오른쪽 눈"이라 했으나 BlazePose 에서 2 는
# 왼쪽 눈이다). anatomy_standard(11=왼쪽 어깨)·kp_judge(PART_REGIONS)가
# MediaPipe 원표기를 쓰므로 learn_log 의 좌우 라벨이 그들과 엇갈렸다.
# BlazePose 원표기: 2=왼쪽 눈 5=오른쪽 눈 7=왼쪽 귀 8=오른쪽 귀
# 9=왼쪽 입꼬리 10=오른쪽 입꼬리 11=왼쪽 어깨 … 27=왼쪽 발목 28=오른쪽.
LM_NOSE = 0
LM_EYE_L = 2
LM_EYE_R = 5
LM_EAR_L = 7
LM_EAR_R = 8
LM_MOUTH_L = 9
LM_MOUTH_R = 10
LM_SHOULDER_L = 11
LM_SHOULDER_R = 12
LM_ELBOW_L = 13
LM_ELBOW_R = 14
LM_WRIST_L = 15
LM_WRIST_R = 16
LM_HIP_L = 23
LM_HIP_R = 24
LM_KNEE_L = 25
LM_KNEE_R = 26
LM_ANKLE_L = 27
LM_ANKLE_R = 28
LM_HEEL_L = 29
LM_HEEL_R = 30
LM_FOOT_L = 31
LM_FOOT_R = 32

# --- 손 21점: 손가락별 (mcp, tip) ----------------------------------------
FINGER_MCPS = (2, 5, 9, 13, 17)
FINGER_TIPS = (4, 8, 12, 16, 20)
FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")

# --- FaceMesh 콧구멍 판독 파라미터 (2026-10-05 실측 프로브 기반) ----------
# 얼굴 중심축: 눈사이(168) → 코끝(1). along = 축 방향 투영
# (0 = 코끝, + = 아래), lateral = 축에 수직 오프셋.
NOSTRIL_ALONG_MIN = 0.03
NOSTRIL_ALONG_MAX = 0.12
NOSTRIL_LATERAL_MAX = 0.10

# --- 부위 카탈로그: 사용자 확정 순서 그대로 -------------------------------
# 각 항목: 부위명 → (판독 원천, 근거 인덱스/방법).
# 원천: pose = BlazePose 점, face = FaceMesh, hand = 손 21점,
#       finger = 손가락 판독 (finger_report 경로 — hand 와 기록을 섞지 않음),
#       calc = pose 점 계산점, pixel = 이미지 블롭 (keeper 가 이미지를
#       넘겨야 한다), none = 현재 세션에서 읽을 수 없음 (기록 전용).
PART_CATALOG = {
    "head": ("pose", (LM_NOSE,)),                      # 머리 (코 상단 대표)
    "face": ("face", 1),                               # 얼굴 (FaceMesh 1 = 코끝)
    "eye_right": ("pose", (LM_EYE_R,)),
    "eye_left": ("pose", (LM_EYE_L,)),
    "nose": ("face", 1),
    "nostril_right": ("face", "nostril"),              # 기하 판독 (실측 방식)
    "nostril_left": ("face", "nostril"),
    "mouth": ("pose", (LM_MOUTH_R, LM_MOUTH_L)),
    "ear_right": ("pose", (LM_EAR_R,)),
    "ear_left": ("pose", (LM_EAR_L,)),
    "neck": ("calc", "neck"),                          # 어깨 중점↔코 중간
    "torso": ("calc", "torso"),                        # 어깨↔엉덩이 프레임
    "waist": ("calc", "waist"),                        # 어깨-엉덩이 중간
    "shoulder_right": ("pose", (LM_SHOULDER_R,)),
    "shoulder_left": ("pose", (LM_SHOULDER_L,)),
    "hip_right": ("pose", (LM_HIP_R,)),
    "hip_left": ("pose", (LM_HIP_L,)),
    "arm_right": ("pose", (LM_SHOULDER_R, LM_ELBOW_R, LM_WRIST_R)),
    "hand_right": ("hand", "right"),
    "arm_left": ("pose", (LM_SHOULDER_L, LM_ELBOW_L, LM_WRIST_L)),
    "hand_left": ("hand", "left"),
    "leg_right": ("pose", (LM_HIP_R, LM_KNEE_R, LM_ANKLE_R)),
    "foot_right": ("pose", (LM_ANKLE_R, LM_HEEL_R, LM_FOOT_R)),
    "leg_left": ("pose", (LM_HIP_L, LM_KNEE_L, LM_ANKLE_L)),
    "foot_left": ("pose", (LM_ANKLE_L, LM_HEEL_L, LM_FOOT_L)),
    "fingers_right": ("finger", "right"),
    "fingers_left": ("finger", "left"),
    "toes_right": ("pixel", "toes_right"),
    "toes_left": ("pixel", "toes_left"),
}


def read_parts(pose_pts, hand_groups, face_group=None):
    """부위 판독. pose_pts: 33×(x,y,vis),
    hand_groups: {"right"|"left": 21×(x,y)} — **dict 계약** (2026-10-07 감사:
    예전 docstring 은 리스트형이라 적었으나 본문은 dict 만 읽는다. 리스트를
    넘기면 손·손가락 부위가 전부 absent 로 기록된다),
    face_group: [478×(x,y)] 또는 None.

    반환: {부위명: {present, vis, pos, src}} — pos 는 정규화 좌표
    (계산점 포함). 판독 불가 부위는 present=False, src 가 이유를 말한다.
    판정(위반)이 아니라 **판독**이 반환값이다 — 위반 판정은 keeper 가
    검증 가능한 것만 한다.
    """
    def _pp(i):
        if pose_pts is None or i >= len(pose_pts):
            return None
        try:
            x, y = float(pose_pts[i][0]), float(pose_pts[i][1])
            v = float(pose_pts[i][2]) if len(pose_pts[i]) >= 3 else 0.0
        except (TypeError, ValueError, IndexError):
            return None
        if x != x or y != y or v != v:
            return None
        return (x, y, v)

    out = {}
    sh_r, sh_l = _pp(LM_SHOULDER_R), _pp(LM_SHOULDER_L)
    hp_r, hp_l = _pp(LM_HIP_R), _pp(LM_HIP_L)
    for name, (src, ref) in PART_CATALOG.items():
        rec = {"present": False, "vis": 0.0, "pos": None, "src": src}
        if src == "pose":
            pts = [_pp(i) for i in (ref or ())]
            if ref and all(p is not None for p in pts):
                rec["present"] = True
                rec["vis"] = min(p[2] for p in pts)
                rec["pos"] = [sum(p[0] for p in pts) / len(pts),
                              sum(p[1] for p in pts) / len(pts)]
        elif src == "calc":
            if ref == "neck" and sh_r and sh_l and _pp(LM_NOSE):
                sh = ((sh_r[0] + sh_l[0]) / 2, (sh_r[1] + sh_l[1]) / 2)
                n = _pp(LM_NOSE)
                rec["present"] = True
                rec["vis"] = min(sh_r[2], sh_l[2], n[2])
                rec["pos"] = [(sh[0] + n[0]) / 2, (sh[1] + n[1]) / 2]
            elif ref == "torso" and sh_r and sh_l and hp_r and hp_l:
                rec["present"] = True
                rec["vis"] = min(sh_r[2], sh_l[2], hp_r[2], hp_l[2])
                rec["pos"] = [((sh_r[0] + sh_l[0] + hp_r[0] + hp_l[0]) / 4),
                              ((sh_r[1] + sh_l[1] + hp_r[1] + hp_l[1]) / 4)]
            elif ref == "waist" and sh_r and sh_l and hp_r and hp_l:
                rec["present"] = True
                rec["vis"] = min(sh_r[2], sh_l[2], hp_r[2], hp_l[2])
                rec["pos"] = [((sh_r[0] + sh_l[0]) / 2 + (hp_r[0] + hp_l[0]) / 2) / 2,
                              ((sh_r[1] + sh_l[1]) / 2 + (hp_r[1] + hp_l[1]) / 2) / 2]
        elif src == "hand":
            side = ref
            idx = {"right": LM_WRIST_R, "left": LM_WRIST_L}[side]
            w = _pp(idx)
            hg = (hand_groups or {}).get(side) if isinstance(
                hand_groups, dict) else None
            if hg is not None and w is not None:
                rec["present"] = True
                rec["vis"] = w[2]
                rec["pos"] = [w[0], w[1]]
        elif src == "finger":
            # 왜(Why) 별도 가지인가 (2026-10-07 감사): 예전엔 카탈로그가
            # fingers_* 를 ("hand", side) 로 두어 hand_* 와 **한 글자도
            # 다르지 않은 기록**이 나왔다. 손가락은 finger_report 경로로만
            # 읽는다 — 기록의 출처가 같아야 learn_log 를 해석할 수 있다.
            side = ref
            idx = {"right": LM_WRIST_R, "left": LM_WRIST_L}[side]
            w = _pp(idx)
            hg = (hand_groups or {}).get(side) if isinstance(
                hand_groups, dict) else None
            if hg is not None and w is not None:
                rep = finger_report(hg)
                if any(r.get("present") for r in rep.values()):
                    rec["present"] = True
                    rec["vis"] = w[2]
                    rec["pos"] = [w[0], w[1]]
        elif src == "face":
            if face_group is None:
                rec["src"] = "face: no facemesh"
            elif ref == 1:
                rec["present"] = True
                rec["vis"] = 1.0
                rec["pos"] = [face_group[1][0], face_group[1][1]]
            elif ref == "nostril":
                found = _nostrils(face_group)
                if found:
                    # _nostrils 는 x 정렬된 (좌, 우) 쌍을 돌려준다.
                    # 다른 부위와 같은 [x, y] 형식으로 기록한다.
                    (lx, ly), (rx, ry) = found
                    rec["present"] = True
                    rec["vis"] = 1.0
                    rec["pos"] = [lx, ly] if name == "nostril_left" \
                        else [rx, ry]
        out[name] = rec
    return out


def _face_axis(face_group):
    """얼굴 중심축 (168 눈사이 → 1 코끝) 단위벡터와 원점."""
    fx, fy = face_group[168][0], face_group[168][1]
    tx, ty = face_group[1][0], face_group[1][1]
    dx, dy = tx - fx, ty - fy
    n = (dx * dx + dy * dy) ** 0.5
    if n <= 0:
        return None
    return (fx, fy, dx / n, dy / n)


def _nostrils(face_group):
    """FaceMesh 478점 → 콧구멍 2좌표 (좌, 우). 못 찾으면 None.

    기하 (실측 방식): 비강 기지 밴드(along NOSTRIL_ALONG_MIN~MAX,
    |lateral| <= LATERAL_MAX)의 정점을 좌우로 갈라, 좌우 각각에서
    lateral 이 가장 큰 정점을 콧구멍 바닥으로 본다.
    """
    try:
        ax = _face_axis(face_group)
        if ax is None:
            return None
        fx, fy, ux, uy = ax
        # 축에 수직인 단위벡터 (좌우 부호는 아래에서 x 정렬로 정규화)
        vx, vy = -uy, ux
        tx, ty = float(face_group[1][0]), float(face_group[1][1])
        # 왜(Why) 축 길이로 나누나: 밴드 상수는 실측 프로브가 쓴
        # "얼굴축 길이 정규화" 좌표다(절대 좌표가 아니다) — 얼굴 크기와
        # 무관하게 같은 밴드가 되려면 축 길이로 나눠야 한다.
        axis_len = (((tx - fx) ** 2 + (ty - fy) ** 2) ** 0.5) or 1e-9
        lbest = rbest = None
        for i in range(len(face_group)):
            if i in (1, 168):
                continue
            x, y = float(face_group[i][0]), float(face_group[i][1])
            ddx, ddy = x - tx, y - ty
            along = (ddx * ux + ddy * uy) / axis_len
            lat = (ddx * vx + ddy * vy) / axis_len
            if not (NOSTRIL_ALONG_MIN <= along <= NOSTRIL_ALONG_MAX
                    and abs(lat) <= NOSTRIL_LATERAL_MAX):
                continue
            if lat < 0:
                if lbest is None or lat < lbest[1]:
                    lbest = (i, lat)
            else:
                if rbest is None or lat > rbest[1]:
                    rbest = (i, lat)
        if lbest is None or rbest is None:
            return None
        lp = (float(face_group[lbest[0]][0]),
              float(face_group[lbest[0]][1]))
        rp = (float(face_group[rbest[0]][0]),
              float(face_group[rbest[0]][1]))
        # 왜(Why) x 정렬로 되돌리나: 수직축 부호는 머리 방향에 따라
        # 뒤집힌다 — 라벨보다 실제 x 순서가 믿을 만하다.
        lo, hi = sorted((lp, rp), key=lambda p: p[0])
        return (lo, hi)
    except (TypeError, ValueError, IndexError):
        return None


def finger_report(hand21):
    """손 21점 → 손가락 5개 판독. 반환: {손가락명: {present, degenerate}}.

    degenerate 근거 (보수적): 끝점(4/8/12/16/20)이 중절(mcp)보다 손목에
    가까우면 접힘 — 주먹은 **정상**이므로 degenerate 가 아니다. 끝점과
    mcp 가 거의 겹치면(손 크기의 3% 이내) 관절 붕괴 후보로만 기록한다.
    """
    rep = {}
    if not hand21 or len(hand21) < 21:
        return rep
    try:
        pts = [(float(p[0]), float(p[1])) for p in hand21]
    except (TypeError, ValueError, IndexError):
        return rep
    wr = pts[0]
    size = max((abs(p[0] - wr[0]) ** 2 + abs(p[1] - wr[1]) ** 2) ** 0.5
               for p in pts[1:]) or 1e-9
    for name, mi, ti in zip(FINGER_NAMES, FINGER_MCPS, FINGER_TIPS):
        m, t = pts[mi], pts[ti]
        dm = ((m[0] - wr[0]) ** 2 + (m[1] - wr[1]) ** 2) ** 0.5
        dt = ((t[0] - wr[0]) ** 2 + (t[1] - wr[1]) ** 2) ** 0.5
        rep[name] = {
            "present": True,
            "degenerate": abs(dt - dm) < 0.03 * size,
        }
    return rep


def toe_blobs(u8, ankle, heel, toe_tip):
    """발 ROI 픽셀 블롭 → 발가락 판독 후보 개수 (cv2). 실패하면 None.

    방법: 뒤꿈치↔발끝 축의 전방 절반(발가락 영역)을 사각 ROI로 자르고,
    Otsu 로 전경을 가른 뒤 연결 요소를 센다. PROVISIONAL — 블롭 개수는
    조명·양말·프레임 가장자리에 흔들린다. keeper 는 이 값을 기록만
    한다(개수 위반 판정은 하지 않는다 — 실측 분포가 쌓인 뒤 판정으로
    올린다).
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    try:
        ax, ay = float(ankle[0]), float(ankle[1])
        hx, hy = float(heel[0]), float(heel[1])
        tx, ty = float(toe_tip[0]), float(toe_tip[1])
    except (TypeError, ValueError, IndexError):
        return None
    h, w = u8.shape[:2]
    px = lambda v: max(0, min(int(round(v * w)), w - 1))
    py = lambda v: max(0, min(int(round(v * h)), h - 1))
    x0, x1 = sorted((px(hx), px(tx)))
    y0, y1 = sorted((py(hy), py(ty)))
    pad = max(4, (x1 - x0 + y1 - y0) // 6)
    x0, x1 = max(0, x0 - pad), min(w, x1 + pad)
    y0, y1 = max(0, y0 - pad), min(h, y1 + pad)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    roi = u8[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bw = cv2.threshold(gray, 0, 255,
                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # 전경 = 히스토그램의 작은 쪽(피부)을 고르는 보수 선택: 두 후보 중
    # 픽셀 수가 20~60% 범위인 쪽을 전경으로 택한다.
    n1 = int((bw > 0).sum())
    n2 = int(bw.size) - n1
    if not (0.2 * bw.size <= n1 <= 0.6 * bw.size):
        if not (0.2 * bw.size <= n2 <= 0.6 * bw.size):
            # 왜(Why) 여기서 되돌리나 (2026-10-07 감사): 예전엔 뒤집고
            # 끝이었다. 두 근본이 다 20~60% 밖이면(Otsu 가 조명을 못
            # 갈랐다) 뒤집어도 여전히 밖이라 **더러운 값을 세었다.**
            # 둘 다 밖이면 세는 대신 판독 불가(None) 가 맞다.
            return None
        bw = 255 - bw
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                    (3, 3)))
    cnt, lab = cv2.connectedComponents(bw)
    blobs = [int((lab == i).sum()) for i in range(1, cnt)]
    big = [b for b in blobs if b >= 0.02 * bw.size]
    return len(big) if big else None


def summarize_parts(parts):
    """판독 dict → 요약 (learn_log 한 줄용). {part: "ok"|"absent"|"lowvis"}."""
    summ = {}
    for name, r in (parts or {}).items():
        if not r.get("present"):
            summ[name] = "absent"
        elif r.get("vis", 0.0) < 0.3:
            summ[name] = "lowvis"
        else:
            summ[name] = "ok"
    return summ


# --- 발 개수 판독 파라미터 (2026-10-06 실측: 3다리 출력물 1건) ---------------
# BlazePose 는 발 2개 고정 토폴로지라 다리 개수를 못 센다 — 팔 3개와 같은
# 사각지대다. 발목 아래 피부 덩어리 중 발끝 랜드마크(31/32)가 하나도
# 들어있지 않은 것을 "주인 없는 발"로 본다.
# 실측 근거: 3다리 이미지에서 발 영역 덩어리 3개 중 1개(0.58~0.66)가 두
# 발끝(0.477/0.502)에서 0.078 떨어져 있었다. 정상 전신 표본은 아직 없어
# 임계는 PROVISIONAL — learn_log 분포가 쌓이면 확정한다.
FOOT_MIN_AREA_FRAC = 0.0005
FOOT_TIP_EXPAND = 0.01
FOOT_GAP_MIN = 0.06
# 주인 없는 덩어리도 가장 큰 덩어리의 20% 미만이면 같은 발이 그림자·잡음으로
# 갈라진 것으로 보고 제외한다 — 진짜 여분 발은 발 크기를 가진다.
FOOT_MIN_RATIO = 0.20


def foot_comps(u8, pose_pts, skin):
    """발 영역 피부 덩어리 목록. 반환: [[면적, x0, x1], ...] 또는 None.

    영역 = 발목 y~발끝 y 중간부터 바닥까지 × 다리 복도(엉덩이·무릎·발목·
    발끝 x 범위 + 여유). 발목이 화면 끝에 닿으면(크롭) 영역이 없어 None —
    판단 불가이지 위반이 아니다. skin 은 _skin_stats 값 (h, s, v).
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    try:
        h, w = u8.shape[:2]
        xs = [float(pose_pts[i][0]) for i in (23, 24, 25, 26, 27, 28, 31, 32)]
        x0 = max(0, int(min(xs) * w) - w // 12)
        x1 = min(w, int(max(xs) * w) + w // 12)
        if x1 <= x0:
            return None
        ay = max(float(pose_pts[27][1]), float(pose_pts[28][1]))
        ty = max(float(pose_pts[31][1]), float(pose_pts[32][1]))
        y0 = int(min(1.0, (ay + ty) / 2.0) * h)
        if y0 >= h - 4:
            return None
        hsv = cv2.cvtColor(u8, cv2.COLOR_RGB2HSV).astype(np.float32)
        dh = np.abs(hsv[:, :, 0] - skin[0])
        dh = np.minimum(dh, 180.0 - dh)
        mask = ((dh <= 12.0) &
                (np.abs(hsv[:, :, 1] - skin[1]) <= 45.0) &
                (np.abs(hsv[:, :, 2] - skin[2]) <= 45.0))
        sub = mask[y0:h, x0:x1]
        sub = cv2.morphologyEx(sub.astype(np.uint8) * 255,
                               cv2.MORPH_OPEN,
                               cv2.getStructuringElement(
                                   cv2.MORPH_ELLIPSE, (3, 3)))
        cnt, lab = cv2.connectedComponents(sub)
        out = []
        for i in range(1, cnt):
            area = int((lab == i).sum())
            if area < FOOT_MIN_AREA_FRAC * h * w:
                continue
            ys, xs2 = np.where(lab == i)
            out.append([area, round((xs2.min() + x0) / w, 4),
                        round((xs2.max() + x0) / w, 4)])
        out.sort(key=lambda c: c[0], reverse=True)
        return out
    except (TypeError, ValueError, IndexError):
        return None


def unclaimed_feet(comps, tip_x0, tip_x1):
    """주인 없는 발 덩어리 인덱스 목록 (순수 함수).

    덩어리가 두 발끝 x 중 하나라도 품으면(±FOOT_TIP_EXPAND) 주인 있음.
    주인 없는 덩어리도 (a) 가장 큰 덩어리의 20% 미만이면 잡음 갈라짐,
    (b) 양쪽 발끝에서 FOOT_GAP_MIN 이내면 같은 발의 그림자로 보고
    제외한다 — 멀리 떨어진 발 크기 덩어리만 여분 다리 증거다.
    """
    try:
        if not comps:
            return []
        maxa = max(c[0] for c in comps) or 1
        unc = []
        for idx, (_area, x0, x1) in enumerate(comps):
            claimed = ((x0 - FOOT_TIP_EXPAND) <= tip_x0 <= (x1 + FOOT_TIP_EXPAND)
                       or (x0 - FOOT_TIP_EXPAND) <= tip_x1 <= (x1 + FOOT_TIP_EXPAND))
            if claimed:
                continue
            if _area < FOOT_MIN_RATIO * maxa:
                continue
            gap = min(abs(x0 - tip_x0), abs(x0 - tip_x1),
                      abs(x1 - tip_x0), abs(x1 - tip_x1))
            if gap > FOOT_GAP_MIN:
                unc.append(idx)
        return unc
    except (TypeError, ValueError, IndexError):
        return []
