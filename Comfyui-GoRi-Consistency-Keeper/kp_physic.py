"""2D 물리 접촉 판정 (physic) — Phy-SIC(MIT) 2D 변형 (2026-10-12).

출처: YuxuanSnow/Phy-SIC (SIGGRAPH Asia 2025, MIT License,
https://github.com/YuxuanSnow/Phy-SIC). 3D 표면-법선 판정을 2D 에지 규칙으로
번역해 키퍼 안에서만 쓴다(외부 모델·새 의존성 없음 — Canny/Sobel + mediapipe
랜드마크만). 데이터·체크포인트는 가져오지 않았고 판정 규칙만 이식했다.

Phy-SIC 원리 -> 2D 번역:
  1. 부호 판정  (정점-표면점)·법선 < 0 이면 침투
     -> 사물의 긴 직선 경계 에지가 인체 마스크 **내부**를 가로지르면 침투.
        정상 접촉(살짝 닿음)은 경계가 인체 실루엣과 겹칠 뿐 몸 안으로
        들어오지 않는다. 손이 벤치에 박힌 경우 벤치 판 에지가 손 마스크
        한가운데를 지난다.
  2. 거리 2종   침투 한계 / 접촉 유지 한계가 따로 있다.
     -> 밴드 두께로 관리: 관통 후보 선은 밴드 두께 이상 몸 안에 들어온 것만.
  3. 접촉 부위  손·다리·둔부·허벅지 등만 접촉 허용(PROX 정적 접촉 라벨).
     -> pose 랜드마크가 접촉 허용 부위 근처면 패널티를 완화한다(엄격/완화 2단).
  4. 가중치     접촉 유지 0.7 > 침투 제거 0.3 — 접촉을 유지하는 쪽이 강하다.
     -> 정상 접촉은 절대 밀지 않고 위반 밴드만 표면 밖으로 민다. 전체 인체를
        사물에서 밀어내던 구 방식(kp_body_object)과 다른 지점이다 — 구 방식은
        정상 접촉(앉은 엉덩이)까지 떠 있게 만들 수 있었다.

추가 판정 (사용자 지시 2026-10-12):
  - 걸침(hover): 엉덩이 중심이 지지 표면선(벤치 좌석 등)의 끝점 근처에 있으면
    "가장자리에 걸친 앉음" — 표면선 안쪽 방향으로 살짝 민다. 물리적으로
    안정한 앉음은 지지면 중심 쪽에 엉덩이가 있어야 한다.
  - 검열 손(censor hand): 한 손이 양 무릎 사이 중앙선에서 무릎 높이 이하로
    내려가 있으면 가림 배치(노출 회피로 추정되는 검열 자세)로 보고 옆으로
    살짝 민다. 무릎 **위에** 얹힌 자연스러운 손은 가까운 무릎 랜드마크와
    거리가 가까우므로 제외한다.
  - 운동화 끈(shoelace): 발목-발끝 랜드마크 밴드에서 끈의 X 연결 구조를
    본다. 정상은 대각 세그먼트가 발축 기준 ±두 클러스터를 이루고 교차가
    2개 이상이다(2026-10-12 밴드 실측: 정상 합성 ±77±2 도 클러스터, 불량
    실사 2장은 클러스터 부재 또는 확산). 엉킴·느슨함은 워핑으로 못 고치므로
    판정+로그만 하고 당김하지 않는다(회복은 세미 샘플링 2단계 과제).

걸침 끝점 검증 (2026-10-12 의자·소파 실측): 끝점 근접만 보면 정상 착석에서도
오탐했다 — 의자(스툴) 정상 착석 점수 75, 소파 정상 착석 점수 94. 원인: 좌석
에지 세그먼트는 가구 끝이 아니라 **인체에 가려진 절단 끝점**에서 끊기는 경우가
많고, 그 끝점이 엉덩이 바로 옆이면 걸침으로 오판한다. 수정: 끝점 너머를 연장
해 사람 영역 밖에서 (a) 에지가 이어지면 가구가 계속되는 것이므로 제외,
(b) 샘플이 전부 사람 안이면 증거 없음으로 제외, (c) 사람 밖에서 에지가
없어야 진짜 가구 끝으로 인정한다. Phy-SIC 의 "사물 표면은 몸 밖으로 이어진다"
원리와 같은 규율이다.

앞판 걸침(깊이 방향) 미탐에 대하여 (2026-10-12 실측, 미해결): 벤치 앞판에
걸쳐 앉은 이미지에서 엉덩이 중심이 앞판선보다 49px 아래였지만, 엉덩이
랜드마크는 고관절 중심이라 좌석 표면보다 아래에 뜨는 오프셋이 가구별로 다르다
(의자 정상 -60~-80px, 소파 정상 -24px, 벤치 위반 -49px — 정규화해도 분리
안 됨). 쿠션 꺼짐·살 두께가 오프셋을 지배하므로 2D 휴리스틱으로 임계값을
정할 수 없고 세미 샘플링 2단계(또는 깊이 단서) 과제로 남긴다.

점수 체계: kp_body_object / kp_hand_phys 와 같은 0~100 + 95 합격 선
(통합 합격 선 _PASS_LINE). 마스크·밴드는 노드 밖으로 나가지 않는다 —
모든 교정은 내부 워핑 + VAE 재인코드 블렌드로 끝낸다(소켓 추가 없음).
"""

import math

import numpy as _np
import cv2

# 합격 선 (손 물리·신체-사물과 같은 통합 합격 선)
_PASS_LINE = 95.0

# 관통(penetration) 판정 — 모든 픽셀 단위는 max(H, W) 기준 비율
_LINE_MIN_FRAC = 0.035   # 관통 후보 선의 최소 길이
_STRAIGHT_MAX = 0.18     # 직선성: PCA 제2고유값 루트/제1고유값 루트 상한
_EXT_FRAC = 0.6          # 선 연장 검사 거리 (선 길이 비율, 양끝 각각)
_EXT_HIT_MIN = 0.45      # 연장 경로에서 사물 에지 히트 비율 (이어짐 증거)
_S_HI = 0.30             # 사물(고구조) 판정 — kp_body_object 와 같은 값
_SIDE_CONTRAST = 0.12    # 선 양옆 구조 밀도 차 하한 (신체 내부 접힘 제외용)
_BAND_FRAC = 0.014       # 관통 밴드 두께
_SHIFT_PX = 6.0          # 미세 당김 이동량(픽셀) — kp_body_object 와 공유
_CORRECT_FRAC = 0.6      # 이동 비율(살짝)

# 접촉 허용 부위 (MediaPipe pose 33점 인덱스, Phy-SIC PROX 라벨의 2D 대응)
# 15/16 손목, 17~22 손가락, 23/24 엉덩이, 25/26 무릎, 27/28 발목, 29~32 발
_CONTACT_LMS = (15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
                27, 28, 29, 30, 31, 32)
_CONTACT_NEAR = 0.09     # 이 거리(정규화) 안에 접촉 부위가 있으면 완화 판정

# 패널티 (Phy-SIC: 접촉 유지 > 침투 제거 — 완화 단은 그 균형을 반영)
_PEN_PEN_STRICT = 12.0   # 접촉 허용 부위 밖에서의 관통
_PEN_PEN_SOFT = 7.0      # 접촉 허용 부위 근처의 관통 (박힘은 여전히 위반)
_PEN_HOVER = 6.0         # 엉덩이 걸침
_PEN_CENSOR = 6.0        # 검열성 손 배치

# 걸침(hover) 판정
_HOVER_PROX = 0.06       # 엉덩이 중심-표면선 세그먼트 최대 거리 (정규화)
_HOVER_END = 0.05        # 표면선 끝점과의 거리 상한 (W 비율) — 끝에 걸쳤다
_SLOPE_MAX = 0.6         # 지지 표면선 기울기 상한 (대략 수평선)
_LINE_MIN2_FRAC = 0.08   # 지지 표면선 최소 길이 (구조선보다 길게)
_HIP_Y_TOL = 0.12        # 표면선 후보 y 가 엉덩이 y 근처여야 하는 범위

# 검열 손(censor hand) 판정 — 정규화 좌표 기준
# (2026-10-12 벤치 실측: 가림 손 y=0.646 > 양 무릎 y 최대 0.637 — 손이 양
#  무릎 관절 **아래**로 내려간 것이 가림의 신호다. 무릎 위에 얹힌 자연스러운
#  손(실측 y=0.554)은 관절보다 위라 제외된다. 무릎 간격은 넓게 벌어질 수
#  있어(실측 0.21) 간격 기반 임계값은 쓰지 않는다.)
_CENSOR_X_MARG = 0.02    # 양 무릎 x 범위의 바깥 허용 마진
_CENSOR_Y_DOWN = 0.08    # 무릎 관절 아래로 이만큼까지는 사이 판정
_CENSOR_HIP_DOWN = 0.12  # 엉덩이 y 에서 아래 한계 (바닥에 닿은 손 제외)

# 운동화 끈(shoelace) 판정 — 2026-10-12 밴드 실측 기반
# (정상 합성: 대각 세그먼트가 발축 기준 ±77±2 도 두 클러스터 + 교차 다수.
#  불량 실사 2장: 클러스터 부재(정면, 축 평행 지배) 또는 확산(측면, 전방위).
#  밴드 에지 밀도가 낮으면 판정 불가 — 무페널티로 오탐을 막는 안전변이다.)
_PEN_SHOELACE = 0.0      # 끈 X 구조 미검출은 교정 경로 없음 -> 로그 전용
_SHOE_T0 = 0.15          # 끈 밴드 시작 (발목->발끝 축 비율)
_SHOE_T1 = 0.70          # 끈 밴드 끝
_SHOE_HALF = 0.19        # 끈 밴드 반폭 (발길이 비율)
_SHOE_MIN_FOOT = 0.03    # 발이 이만큼(maxHW 비율) 작으면 판정 불가
_SHOE_MIN_SEG = 0.14     # 끈 세그먼트 최소 길이 (발길이 비율)
_SHOE_ANG_LO = 20.0      # 대각 판정 최소 각 (발축 기준, 도)
_SHOE_ANG_HI = 80.0      # 대각 판정 최대 각
_SHOE_CLUST_SPREAD = 22.0  # 부호별 대각 클러스터 확산 상한 (도)
_SHOE_CROSS_MIN = 2      # 정상 X 연결의 최소 교차 수
_SHOE_DENS_MIN = 0.04    # 밴드 에지 밀도 하한 (이하 판정 불가)
_SHOE_CANNY_LO = 30      # 흰 끈-흰 신발 저대비용 Canny 하한
_SHOE_CANNY_HI = 90      # 상한

# 샌들/슬리퍼 구분 (2026-10-12 run_0~run_4 실측): 생성 5장이 전부 샌들인데도
# 끈 판정이 발화했다 — 오픈 토는 X 구조가 없는 것이 정상이므로 발끝 피부
# 비율로 샌들을 먼저 걸러낸다.
_SHOE_OPEN_TOE_BOX = 0.12   # 발끝 주변 피부 검사 상자 크기 (발길이 비율)
_SHOE_OPEN_TOE_SKIN = 0.35  # 이 비율 이상 피부이면 오픈 토로 보고 끈 판정 스킵

# 팔 관통 걸침 제외 (2026-10-12 run_4 벤치 실측): 팔이 벤치 가장자리에 얹혀
# 손이 선 너머에 그대로 보이면 정상 접촉이다 — 손목 너머 작은 원에서 사람
# 비율로 손 가시성을 본다. 박힌 팔은 선 너머(사물 안쪽)에서 손이 사라져
# 사람 비율이 낮다(1.9.26 벤치 실측: 손 검출 실패가 박힘의 증거였던 것).
_ARM_CONTACT_WIDTH = 0.03   # 손목 너머 검사 원 반경 (maxHW 비율)
_ARM_CONTACT_BODY = 0.45    # 이 비율 이상 사람이면 손이 보인다(걸침) -> 제외


def _structure_map(rgb):
    """uint8 RGB -> (H,W) 0~1 구조(에지) 맵. kp_body_object 와 같은 규율."""
    gray = rgb if rgb.ndim == 2 else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if gray.dtype != _np.uint8:
        gray = _np.clip(gray, 0, 255).astype(_np.uint8)
    edges = cv2.Canny(gray, 50, 150)
    S = edges.astype(_np.float32) / 255.0
    k = max(3.0, gray.shape[1] / 300.0)
    S = cv2.GaussianBlur(S, (0, 0), k)
    return S


def _canny(rgb):
    """uint8 RGB -> 이진 Canny 에지 (0/1 float32)."""
    gray = rgb if rgb.ndim == 2 else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if gray.dtype != _np.uint8:
        gray = _np.clip(gray, 0, 255).astype(_np.uint8)
    return (cv2.Canny(gray, 50, 150) > 0).astype(_np.float32)


def _fit_line(pts):
    """점 집합 -> (p1, p2, length, straight) PCA 직선 피팅.

    straight = sqrt(제2고유값 / 제1고유값) — 0 에 가까울수록 직선.
    """
    pts = _np.asarray(pts, _np.float32)
    mean = pts.mean(axis=0)
    d = pts - mean
    cov = d.T @ d / max(len(pts), 1)
    vals, vecs = _np.linalg.eigh(cov)
    if vals[0] < 0:
        vals[0] = 0.0
    t = vecs[:, 1]
    half = math.sqrt(max(float(vals[1]), 0.0))
    straight = math.sqrt(float(vals[0])) / max(half, 1e-6)
    p1 = mean - t * half
    p2 = mean + t * half
    return p1, p2, 2.0 * half, float(straight)


def _scan_lines(edge_mask, min_len):
    """에지 마스크의 연결 성분을 직선 후보로 모은다.

    반환: [{p1, p2, dir, nrm, length}] — dir/nrm 은 단위 벡터,
    nrm 은 dir 를 시계 방향으로 90 도 돌린 법선.
    """
    out = []
    m = (edge_mask > 0).astype(_np.uint8)
    n_lab, lab = cv2.connectedComponents(m, connectivity=8)
    for i in range(1, n_lab):
        ys, xs = _np.where(lab == i)
        if len(xs) < 8:
            continue
        p1, p2, length, straight = _fit_line(
            _np.stack([xs, ys], axis=1).astype(_np.float32))
        if length < min_len or straight > _STRAIGHT_MAX:
            continue
        d = p2 - p1
        n = math.hypot(d[0], d[1])
        if n < 1e-3:
            continue
        d = d / n
        out.append({"p1": p1, "p2": p2, "dir": d,
                    "nrm": _np.array([-d[1], d[0]], _np.float32),
                    "length": length})
    return out


def _side_densities(line, Pn, radius):
    """선 양옆(법선 +-radius)의 사람 밀도와 구조 밀도를 잰다.

    반환: ((dens_p_a, dens_s_a), (dens_p_b, dens_s_b)) — a 는 +법선 쪽.
    """
    p1, p2, n = line["p1"], line["p2"], line["nrm"]
    L = line["length"]
    ts = _np.linspace(-L / 2.0, L / 2.0, max(int(L / 2.0), 8))
    c = (p1 + p2) / 2.0
    d = line["dir"]
    H, W = Pn.shape[:2]
    res = []
    for sign in (1.0, -1.0):
        pts = c[None, :] + ts[:, None] * d[None, :] \
            + sign * radius * n[None, :]
        xi = _np.clip(pts[:, 0].round().astype(_np.int64), 0, W - 1)
        yi = _np.clip(pts[:, 1].round().astype(_np.int64), 0, H - 1)
        res.append((float(_np.mean(Pn[yi, xi] > 0.3)),
                    float(_np.mean(Pn[yi, xi]))))
    return res[0], res[1]


def _edge_continues(line, edges, Pn):
    """선을 양끝 밖으로 연장했을 때 사물 에지가 이어지는지 본다.

    Phy-SIC 의 "사물 표면" 개념의 2D 대응 — 몸 안에서 시작한 선이 몸 밖에서도
    사물 에지로 이어지면 그 선은 사물 경계선이다(옷 주름은 몸 밖으로 이어지지
    않는다). 사람 영역 밖의 에지만 히트로 센다.
    """
    p1, p2, d = line["p1"], line["p2"], line["dir"]
    ext = line["length"] * _EXT_FRAC
    H, W = Pn.shape[:2]
    best = 0.0
    for end, sgn in ((p1, -1.0), (p2, 1.0)):
        ts = _np.linspace(2.0, ext, max(int(ext / 2.0), 6))
        pts = end[None, :] + sgn * ts[:, None] * d[None, :]
        xi = _np.clip(pts[:, 0].round().astype(_np.int64), 0, W - 1)
        yi = _np.clip(pts[:, 1].round().astype(_np.int64), 0, H - 1)
        outside = Pn[yi, xi] < 0.3
        if float(outside.sum()) < 2:
            continue
        hit = float(_np.mean(edges[yi, xi][outside] > 0))
        best = max(best, hit)
    return best >= _EXT_HIT_MIN


def _band_mask(line, Pn, band_px):
    """관통 선 주변 밴드 마스크 (인체 영역으로 한정)."""
    p1, p2 = line["p1"], line["p2"]
    m = _np.zeros(Pn.shape, _np.uint8)
    cv2.line(m, (int(round(p1[0])), int(round(p1[1]))),
             (int(round(p2[0])), int(round(p2[1]))),
             1, thickness=max(int(round(band_px * 2)), 3))
    m = cv2.dilate(m, _np.ones((3, 3), _np.uint8), iterations=1)
    return ((m > 0) & (Pn > 0.3)).astype(_np.float32)


# 팔 관통(arm penetration) 판정 — "손목이 보이는데 손이 검출되지 않는다"
_ARM_COS_PAR = 0.7        # 사물선이 팔 방향과 평행하면 자기 실루엣이다 (제외)
_ARM_T_MIN = 0.05         # 교차점이 팔꿈치 바로 뒤면 안 된다 (팔 길이 비율)
_ARM_T_MAX = 1.35         # 손목 너머 조금까지는 손 영역이다
_ARM_LINE_MIN = 0.8       # 사물선은 팔 길이의 80% 이상
_ARM_MARGIN = 0.15        # 교차점이 선분 끝에 붙어 있으면 우연이다
_ARM_HAND_NEAR = 0.6      # 이 거리(팔 길이 비율) 안에 손이 있으면 검출된 것


def _arm_penetrations(rgb, pose_lm, Pn, hand_lms):
    """팔꿈치-손목이 사물 직선 에지를 가로지르면 팔이 사물에 박힌 것이다.

    왜(Why) 손 21점 양분만으로는 부족하다 (2026-10-12 벤치 실측): 벤치에
    박힌 왼손은 mediapipe 손 검출이 **실패**했다(손이 사물에 가려 검출기가
    찾지 못한다 — 이것 자체가 박힘의 증거). 대신 pose 의 팔꿈치(13/14)-
    손목(15/16) 세그먼트가 긴 사물 에지(좌석 판 에지)를 가로지르는지 본다:
    팔꿈치와 손목이 에지 양옆에 있으면 팔이 사물을 관통한다. 실측: 팔꿈치
    y=832, 손목 y=1075, 좌석 에지 y=928 — 가로지름이 확인됐다.
    자기 실루엣(팔 윤곽선)은 팔 방향과 평행하므로 각도 필터로 제외한다.
    """
    out = []
    if pose_lm is None or len(pose_lm) < 33:
        return out
    H, W = Pn.shape[:2]
    maxHW = float(max(H, W))
    edges = (_canny(rgb) > 0).astype(_np.uint8) * 255
    found = cv2.HoughLinesP(
        edges, 1, _np.pi / 180.0,
        threshold=max(int(maxHW * 0.05), 40),
        minLineLength=maxHW * _LINE_MIN_FRAC * 0.5,
        maxLineGap=max(int(maxHW * 0.015), 8))
    if found is None:
        return out
    rows = [r for r in found]
    hand_centers = []
    for hand in hand_lms or []:
        if hand and len(hand) >= 10:
            w0, m9 = hand[0], hand[9]
            if all(v == v for pt in (w0, m9) for v in pt[:2]):
                hand_centers.append(((w0[0] + m9[0]) / 2.0,
                                     (w0[1] + m9[1]) / 2.0))
    for sh, el, wr in ((11, 13, 15), (12, 14, 16)):
        if not all(_lm_valid(pose_lm[i]) for i in (sh, el, wr)):
            continue
        e = pose_lm[el][:2]
        w = pose_lm[wr][:2]
        ep = _np.array([e[0] * W, e[1] * H], _np.float32)
        wp = _np.array([w[0] * W, w[1] * H], _np.float32)
        f = wp - ep
        flen = float(_np.linalg.norm(f))
        if flen < 1e-3:
            continue
        u = f / flen
        near = [hc for hc in hand_centers
                if math.hypot(hc[0] * W - wp[0], hc[1] * H - wp[1])
                < _ARM_HAND_NEAR * flen]
        if near:
            continue  # 손이 검출됐다 — 21점 양분 판정이 담당한다
        best = None
        for row in rows:
            x1, y1, x2, y2 = [float(v) for v in row[0]]
            a = _np.array([x1, y1], _np.float32)
            b = _np.array([x2, y2], _np.float32)
            d = b - a
            L = float(_np.linalg.norm(d))
            if L < max(_ARM_LINE_MIN * flen, _LINE_MIN_FRAC * maxHW * 0.5):
                continue
            d = d / L
            if abs(float(d @ u)) > _ARM_COS_PAR:
                continue  # 팔과 평행한 선 = 팔 자기 실루엣
            n = _np.array([-d[1], d[0]], _np.float32)
            se = float((ep - a) @ n)
            sw = float((wp - a) @ n)
            if se * sw >= 0:
                continue
            t = se / (se - sw)
            if t < _ARM_T_MIN or t > _ARM_T_MAX:
                continue
            cross = ep + u * (t * flen)
            s = float((cross - a) @ d)
            if s < _ARM_MARGIN * L or s > (1.0 - _ARM_MARGIN) * L:
                continue
            if best is None or L > best["L"]:
                best = {"a": a, "b": b, "L": L, "d": d, "cross": cross}
        if best is None:
            continue
        # 걸침 접촉 제외 (run_4 벤치 실측): 손목 너머(선의 손목 쪽) 작은 원에
        # 사람이 보이면 손이 사물 밖으로 나와 있는 것 — 얹힌 접촉이다.
        # 박힌 팔은 선 너머에서 손이 사라져 이 원의 사람 비율이 낮다.
        nvec = _np.array([-best["d"][1], best["d"][0]], _np.float32)
        sgn = float(_np.sign(float((wp - best["a"]) @ nvec)))
        if sgn == 0.0:
            sgn = 1.0
        r_disc = max(int(_ARM_CONTACT_WIDTH * maxHW), 6)
        ccx = int(_np.clip(round(float(wp[0] + nvec[0] * sgn * r_disc)),
                           0, W - 1))
        ccy = int(_np.clip(round(float(wp[1] + nvec[1] * sgn * r_disc)),
                           0, H - 1))
        dx0 = max(0, ccx - r_disc)
        dx1 = min(W, ccx + r_disc + 1)
        dy0 = max(0, ccy - r_disc)
        dy1 = min(H, ccy + r_disc + 1)
        disc = Pn[dy0:dy1, dx0:dx1]
        if disc.size and float(_np.mean(disc)) >= _ARM_CONTACT_BODY:
            continue
        # 당김: 손을 팔꿈치 쪽으로 (몸쪽으로 끌어낸다)
        band = _circle_band(wp, max(0.05 * maxHW, 0.6 * flen), Pn)
        if float(band.sum()) < 4:
            continue
        out.append({"line": {"p1": best["a"], "p2": best["b"]},
                    "band": band, "main_sign": 1.0, "shift": (-u[0], -u[1])})
    return out


def _edge_continues_outside(line, edges, box, pad):
    """선을 양끝 밖으로 연장했을 때 손 사각형 밖에서 에지가 이어지는지 본다.

    손가락 틈새 에지는 손 안에서 끝난다 — 사물 에지(벤치 판)는 손 밖으로
    계속 이어진다(Phy-SIC 의 "사물 표면은 몸 밖으로 이어진다" 원리).
    2026-10-12 벤치 실측에서 무릎 위 자연스러운 손의 손가락 틈이 양분 후보에
    들어오는 오탐을 막는다.
    """
    p1, p2, d = line["p1"], line["p2"], line["dir"]
    ext = line["length"] * _EXT_FRAC
    H, W = edges.shape[:2]
    bx0, by0, bx1, by1 = box
    for end in (p1, p2):
        ts = _np.linspace(2.0, ext, max(int(ext / 2.0), 6))
        pts = end[None, :] + ts[:, None] * d[None, :]
        xi = _np.clip(pts[:, 0].round().astype(_np.int64), 0, W - 1)
        yi = _np.clip(pts[:, 1].round().astype(_np.int64), 0, H - 1)
        outside = (xi < bx0 - pad) | (xi > bx1 + pad) \
            | (yi < by0 - pad) | (yi > by1 + pad)
        if float(outside.sum()) < 2:
            continue
        if float(_np.mean(edges[yi, xi][outside] > 0)) >= _EXT_HIT_MIN:
            return True
    return False


def _hand_penetrations(edges, hand_lms, Pn):
    """손 랜드마크 기반 관통 판정 — Phy-SIC 부호 판정의 손 버전.

    왜(Why) 마스크 기반 판정만으로는 부족하다 (2026-10-12 벤치 실측):
    키퍼의 인물 마스크는 벤치·배경까지 포함하는 소프트 블롭이라 "마스크
    내부를 가로지르는 사물 에지" 가 의미를 잃는다. 대신 손 21점을 직접 쓴다:
    손 주변의 긴 직선 에지(벤치 판·팔걸이)가 손 점들을 **양분**하면(선 양옆에
    손 점이 각 3개 이상) 그 선이 손을 관통한다 — 손이 사물에 박힌 형태다.
    옷 주름은 곡선이라 양분 직선 후보에 잘 들어오지 않는다.
    """
    out = []
    if not hand_lms:
        return out
    H, W = Pn.shape[:2]
    maxHW = float(max(H, W))
    for hand in hand_lms:
        if not hand or len(hand) < 21:
            continue
        pts = _np.array([[p[0] * W, p[1] * H] for p in hand], _np.float32)
        if pts.shape != (21, 2) or bool(_np.isnan(pts).any()):
            continue
        c = pts.mean(axis=0)
        size = float(_np.linalg.norm(pts[9] - pts[0])) + 4.0
        m = _np.zeros((H, W), _np.uint8)
        cv2.rectangle(m,
                      (int(pts[:, 0].min() - size), int(pts[:, 1].min() - size)),
                      (int(pts[:, 0].max() + size), int(pts[:, 1].max() + size)),
                      1, -1)
        box = (float(pts[:, 0].min()), float(pts[:, 1].min()),
               float(pts[:, 0].max()), float(pts[:, 1].max()))
        cand = edges * (m > 0)
        min_len = max(_LINE_MIN_FRAC * maxHW * 0.5, size * 0.8)
        for line in _scan_lines(cand, min_len):
            if not _edge_continues_outside(line, edges, box, size):
                continue  # 손 안에서 끝나는 선 = 손가락 틈새
            n = line["nrm"]
            s = (pts - line["p1"]) @ n
            a = int((s > 1.0).sum())
            b = int((s < -1.0).sum())
            if a < 3 or b < 3:
                continue
            # 당김 방향: 손 점이 더 많은 쪽 (박힌 부분을 몸쪽으로 끌어낸다)
            sign = 1.0 if a >= b else -1.0
            band = _circle_band(c, size * 1.1, Pn)
            if float(band.sum()) < 4:
                continue
            out.append({"line": line, "band": band, "main_sign": sign})
            break
    return out


def _detect_penetrations(rgb, P, hand_lms=None, pose_lm=None):
    """관통(박힘) 후보 선을 찾는다.

    반환: [{line, band, main_sign, shift?}] — main_sign 은 사람이 더 많은
    쪽의 법선 부호(당김 방향). shift 가 있으면 그 벡터를 우선한다.
    """
    H, W = P.shape[:2]
    maxHW = float(max(H, W))
    Pn = (P > 0.02).astype(_np.float32)
    if Pn.sum() < 20:
        return []
    edges = _canny(rgb)
    out = _hand_penetrations(edges, hand_lms, Pn)
    out.extend(_arm_penetrations(rgb, pose_lm, Pn, hand_lms))
    S = _structure_map(rgb)
    interior = cv2.erode(Pn, _np.ones((3, 3), _np.float32), iterations=3)
    cand = (edges > 0) & (interior > 0)
    if float(cand.sum()) < 8:
        return out
    min_len = _LINE_MIN_FRAC * maxHW
    radius = max(4.0, _BAND_FRAC * maxHW)
    mask_out = []
    for line in _scan_lines(cand, min_len):
        (pa, sa), (pb, sb) = _side_densities(line, S, radius)
        # 한쪽은 사물(고구조), 반대쪽은 신체(저구조)여야 한다 — 신체 내부의
        # 접힘·직물선은 양옆 구조가 비슷하므로 여기서 걸러진다.
        hi, lo = max(sa, sb), min(sa, sb)
        if hi < _S_HI or hi - lo < _SIDE_CONTRAST:
            continue
        if not _edge_continues(line, edges, Pn):
            continue
        band = _band_mask(line, Pn, _BAND_FRAC * maxHW)
        if float(band.sum()) < 4:
            continue
        # 당김 방향: 사람이 더 많은 쪽 (밴드를 몸쪽으로 끌어낸다)
        (pa2, _), (pb2, _) = _side_densities(line, Pn, radius)
        main_sign = 1.0 if pa2 >= pb2 else -1.0
        mask_out.append({"line": line, "band": band, "main_sign": main_sign})
    return out + mask_out


def _lm_px(pt, W, H):
    """정규화 랜드마크 1개 -> 픽셀 (x, y). None 이면 None."""
    if pt is None:
        return None
    return (float(pt[0]) * W, float(pt[1]) * H)


def _lm_valid(pt):
    """랜드마크가 쓸 수 있는 값인가 — None/NaN 을 거른다.

    테스트·내부 경로에서 33점 중 일부만 채우는 부분 랜드마크를 안전하게
    받기 위한 가드다 (2026-10-12 R122 실측: None 항목 인덱싱 크래시).
    """
    if pt is None:
        return False
    try:
        return all(v == v for v in pt[:2])
    except (TypeError, IndexError):
        return False


def _seg_dist(p, a, b):
    """점 p 와 선분 a-b 의 최단 거리."""
    ab = b - a
    n2 = float(ab @ ab)
    if n2 < 1e-9:
        return float(math.hypot(p[0] - a[0], p[1] - a[1]))
    t = float((p - a) @ ab) / n2
    t = min(max(t, 0.0), 1.0)
    q = a + t * ab
    return float(math.hypot(p[0] - q[0], p[1] - q[1]))


def _detect_hover(pose_lm, rgb, P):
    """걸친 앉음 판정. 위반이면 {hip, dir(단위 픽셀 벡터, 안쪽), line} 반환.

    왜(Why) HoughLinesP 인가 (2026-10-12 벤치 실측): 벤치 좌석 에지는 나무
    결과 그림자로 Canny 연결 성분이 잘게 깨져 연결 성분 기반 _scan_lines 로는
    후보가 0개였다. Hough 는 끊긴 세그먼트를 직선으로 뭉치므로 좌석선이
    잡힌다. 사람 영역을 에지에서 제외하지 않는다 — 엉덩이 뒤 좌석선은 몸에
    가려져 있고, 몸 **옆**에서 이어지는 좌석선 끝점과 엉덩이의 거리가 걸침의
    증거이기 때문이다.
    """
    if pose_lm is None or len(pose_lm) < 33:
        return None
    if not all(_lm_valid(pose_lm[i]) for i in (23, 24, 25, 26)):
        return None
    H, W = P.shape[:2]
    maxHW = float(max(H, W))
    h1 = _lm_px(pose_lm[23], W, H)
    h2 = _lm_px(pose_lm[24], W, H)
    hc = ((h1[0] + h2[0]) / 2.0, (h1[1] + h2[1]) / 2.0)
    edges = (_canny(rgb) > 0).astype(_np.uint8) * 255
    found = cv2.HoughLinesP(
        edges, 1, _np.pi / 180.0,
        threshold=max(int(maxHW * 0.05), 40),
        minLineLength=maxHW * _LINE_MIN2_FRAC,
        maxLineGap=max(int(maxHW * 0.015), 8))
    if found is None:
        return None
    best = None
    for row in found:
        x1, y1, x2, y2 = [float(v) for v in row[0]]
        d = _np.array([x2 - x1, y2 - y1], _np.float32)
        n = float(math.hypot(d[0], d[1]))
        if n < 1e-3:
            continue
        d = d / n
        if abs(float(d[1])) > _SLOPE_MAX * abs(float(d[0])) + 1e-6:
            continue
        cy = (y1 + y2) / 2.0
        if abs(cy - hc[1]) > _HIP_Y_TOL * maxHW:
            continue
        a = _np.array([x1, y1], _np.float32)
        b = _np.array([x2, y2], _np.float32)
        dist = _seg_dist(_np.array(hc, _np.float32), a, b)
        if dist > _HOVER_PROX * maxHW:
            continue
        e1 = float(math.hypot(hc[0] - a[0], hc[1] - a[1]))
        e2 = float(math.hypot(hc[0] - b[0], hc[1] - b[1]))
        if min(e1, e2) > _HOVER_END * W:
            continue
        # 가구 끝 검증 (2026-10-12 의자·소파 실측): 끝점 근접만 보면 정상
        # 착석(의자 75점, 소파 94점)에서 오탐했다 — 좌석 에지는 가구 끝이
        # 아니라 인체에 가려진 절단 끝점에서 끊기고, 그 끝점이 엉덩이 바로
        # 옆이기 때문이다. 끝점 너머를 연장해 본다: 사람 밖에서 에지가
        # 이어지면 가구가 계속되는 것이므로 제외하고, 연장 샘플이 전부
        # 사람 안이면 증거 없음으로 제외한다. 사람 밖에서 에지가 없을 때만
        # 진짜 가구 끝으로 인정한다(Phy-SIC "사물은 몸 밖으로 이어진다").
        near = a if e1 <= e2 else b
        L2 = float(_np.linalg.norm(b - a))
        ext = L2 * _EXT_FRAC
        u2 = (b - a) / max(L2, 1e-6)
        sgn = 1.0 if near is b else -1.0
        ts = _np.linspace(2.0, ext, max(int(ext / 2.0), 6))
        pts = near[None, :] + sgn * ts[:, None] * u2[None, :]
        xi = _np.clip(pts[:, 0].round().astype(_np.int64), 0, W - 1)
        yi = _np.clip(pts[:, 1].round().astype(_np.int64), 0, H - 1)
        outside = P[yi, xi] <= 0.3
        if float(outside.sum()) < 2:
            continue  # 연장이 전부 사람 안 — 절단 끝점 (걸침 증거 없음)
        if float(_np.mean(edges[yi, xi][outside] > 0)) >= _EXT_HIT_MIN:
            continue  # 가구가 계속된다 — 끝점이 아니다
        # 안쪽 방향 = 엉덩이에서 먼 끝점 쪽 (표면선을 따라 안으로)
        far = a if e1 > e2 else b
        v = far - _np.array(hc, _np.float32)
        nv = float(math.hypot(v[0], v[1]))
        if nv < 1e-3:
            continue
        if best is None or dist < best["dist"]:
            best = {"dist": dist, "dir": v / nv, "hip": hc,
                    "line": {"p1": a, "p2": b}}
    return best


def _detect_censor(pose_lm, hand_lms):
    """검열성 손 배치(무릎 사이 가림) 판정.

    위반이면 {center, dir(단위 정규화 벡터, 무릎 쪽)} 반환.
    신호(2026-10-12 벤치 실측): 손 중심이 양 무릎 x 범위 안에 있으면서 양
    무릎 관절 **아래**로 내려간 경우 — 무릎 위에 얹힌 자연스러운 손은 관절
    위에 있으므로 제외된다. 가림 손을 무릎 쪽으로 옆으로 민다.
    """
    if pose_lm is None or len(pose_lm) < 33 or not hand_lms:
        return None
    if not all(_lm_valid(pose_lm[i]) for i in (23, 24, 25, 26)):
        return None
    k1 = pose_lm[25][:2]
    k2 = pose_lm[26][:2]
    hp1 = pose_lm[23][:2]
    hp2 = pose_lm[24][:2]
    x_lo = min(k1[0], k2[0]) - _CENSOR_X_MARG
    x_hi = max(k1[0], k2[0]) + _CENSOR_X_MARG
    knee_y_top = min(k1[1], k2[1])
    knee_y_bot = max(k1[1], k2[1])
    y_lo = knee_y_top - 0.005
    y_hi = knee_y_bot + _CENSOR_Y_DOWN
    hip_y_bot = max(hp1[1], hp2[1]) + _CENSOR_HIP_DOWN
    for hand in hand_lms:
        if not hand or len(hand) < 10:
            continue
        w = hand[0]
        m = hand[9]
        if any(v != v for pt in (w, m) for v in pt[:2]):
            continue
        cx = (w[0] + m[0]) / 2.0
        cy = (w[1] + m[1]) / 2.0
        if not (x_lo <= cx <= x_hi and y_lo <= cy <= y_hi):
            continue
        if cy > hip_y_bot:
            continue
        # 옆으로 민다 — 중앙선에서 더 가까운 무릎 쪽 (자연스러운 안착지)
        near_x = k1[0] if abs(cx - k1[0]) <= abs(cx - k2[0]) else k2[0]
        dx = near_x - cx
        if abs(dx) < 1e-6:
            dx = 1.0
        return {"center": (cx, cy), "dir": (math.copysign(1.0, dx), 0.0)}
    return None


def _line_cross(p1, d1, p3, d3):
    """두 직선 (p1,t*d1) 과 (p3,s*d3) 의 교차점. 평행이면 None."""
    den = float(d1[0] * d3[1] - d1[1] * d3[0])
    if abs(den) < 1e-9:
        return None
    dp = p3 - p1
    t = float(dp[0] * d3[1] - dp[1] * d3[0]) / den
    return p1 + t * d1


def _detect_shoelace(pose_lm, rgb):
    """운동화 끈 X 연결 판정. 위반 발 목록 [{side, center, note}] 반환.

    왜(Why) X 구조인가 (2026-10-12 밴드 실측): 발목(27/28)-발끝(31/32)
    랜드마크 축 주변 밴드에서 끈 에지를 모으면, 정상 X 연결은 발축 기준
    ±(20~80) 도 대각이 **두 개의 조밀한 클러스터**로 나오고 교차가 2개
    이상이다(합성 정상 실측 ±77±2 도, 교차 다수). 끈이 엉킨 실사 2장은
    (a) 정면: 축 평행 세그먼트가 지배해 대각 클러스터가 없거나
    (b) 측면: 각도가 전방위로 흩어져 클러스터 확산이 크다.
    두 클러스터 + 교차가 모두 있어야 통과다. 밴드 에지 밀도가
    _SHOE_DENS_MIN 미만이면 끈을 볼 수 없는 것(어두운 신발·가림·끈 없는
    신발)이므로 판정 불가 — 무페널티로 오탐을 막는다.
    엉킨 끈은 워핑으로 고칠 수 없어 플래그+로그만 하고 당김하지 않는다.
    """
    out = []
    if pose_lm is None or len(pose_lm) < 33 or rgb is None:
        return out
    H, W = rgb.shape[:2]
    maxHW = float(max(H, W))
    gray = rgb if rgb.ndim == 2 else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if gray.dtype != _np.uint8:
        gray = _np.clip(gray, 0, 255).astype(_np.uint8)
    edges = cv2.Canny(gray, _SHOE_CANNY_LO, _SHOE_CANNY_HI)
    for side, ai, ti in (("left", 27, 31), ("right", 28, 32)):
        if not all(_lm_valid(pose_lm[i]) for i in (ai, ti)):
            continue
        ap = pose_lm[ai][:2]
        tp = pose_lm[ti][:2]
        a = _np.array([ap[0] * W, ap[1] * H], _np.float32)
        t = _np.array([tp[0] * W, tp[1] * H], _np.float32)
        flen = float(_np.linalg.norm(t - a))
        if flen < _SHOE_MIN_FOOT * maxHW or flen < 12.0:
            continue
        u = (t - a) / flen
        # 오픈 토(샌들/슬리퍼) 스킵: 발끝 쪽 작은 상자에서 피부 비율이
        # 높으면 끈이 없는 신발이다 — X 구조 부재는 위반이 아니다.
        # MediaPipe 발끝(31/32)이 실제 발끝보다 위(발등)에 잡히는 경우가
        # 많아서, 축 끝(발목->발끝 벡터를 그대로 연장)을 본다.
        tc = a + u * flen * 1.08
        hb = max(int(_SHOE_OPEN_TOE_BOX * flen), 4)
        tx0 = int(_np.clip(round(float(tc[0])) - hb, 0, W - 1))
        tx1 = int(_np.clip(round(float(tc[0])) + hb + 1, 1, W))
        ty0 = int(_np.clip(round(float(tc[1])) - hb, 0, H - 1))
        ty1 = int(_np.clip(round(float(tc[1])) + hb + 1, 1, H))
        tbox = rgb[ty0:ty1, tx0:tx1]
        if tbox.size:
            tr = tbox[..., 0].astype(_np.int32)
            tg = tbox[..., 1].astype(_np.int32)
            tb = tbox[..., 2].astype(_np.int32)
            skin = (tr > 95) & (tg > 40) & (tb > 20) & (tr > tg) \
                & (tg >= tb) & ((tr - tb) > 15)
            if float(_np.mean(skin)) >= _SHOE_OPEN_TOE_SKIN:
                continue
        n = _np.array([-u[1], u[0]], _np.float32)
        half = _SHOE_HALF * flen
        q0 = a + u * (_SHOE_T0 * flen)
        q1 = a + u * (_SHOE_T1 * flen)
        quad = _np.array([q0 + n * half, q1 + n * half,
                          q1 - n * half, q0 - n * half], _np.float32)
        mask = _np.zeros((H, W), _np.uint8)
        cv2.fillPoly(mask, [quad.round().astype(_np.int32)], 1)
        m_area = float((mask > 0).sum())
        if m_area < 20:
            continue
        eb = edges * (mask > 0)
        dens = float((eb > 0).sum()) / m_area
        if dens < _SHOE_DENS_MIN:
            continue  # 끈 영역을 볼 수 없다 — 판정 불가 (오탐 안전변)
        found = cv2.HoughLinesP(
            eb, 1, _np.pi / 180.0, threshold=max(int(0.05 * flen), 6),
            minLineLength=max(int(_SHOE_MIN_SEG * flen), 6),
            maxLineGap=max(int(0.05 * flen), 3))
        segs = []
        axis_ang = math.degrees(math.atan2(float(u[1]), float(u[0])))
        for row in (found if found is not None else []):
            x1, y1, x2, y2 = [float(v) for v in row[0]]
            L = math.hypot(x2 - x1, y2 - y1)
            if L < _SHOE_MIN_SEG * flen:
                continue
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1)) - axis_ang
            ang = (ang + 90.0) % 180.0 - 90.0
            if _SHOE_ANG_LO <= abs(ang) <= _SHOE_ANG_HI:
                p1 = _np.array([x1, y1], _np.float32)
                d = _np.array([x2 - x1, y2 - y1], _np.float32)
                segs.append((p1, d / max(L, 1e-6), ang))
        pos = [s for s in segs if s[2] > 0]
        neg = [s for s in segs if s[2] < 0]
        if len(pos) < 2 or len(neg) < 2:
            out.append({"side": side, "center": (float(q0[0] + q1[0]) / 2.0,
                                                 float(q0[1] + q1[1]) / 2.0),
                        "note": "대각 클러스터 없음 (+%d/-%d)" % (len(pos), len(neg))})
            continue
        sp = max(s[2] for s in pos) - min(s[2] for s in pos)
        sn = max(s[2] for s in neg) - min(s[2] for s in neg)
        if sp > _SHOE_CLUST_SPREAD or sn > _SHOE_CLUST_SPREAD:
            out.append({"side": side, "center": (float(q0[0] + q1[0]) / 2.0,
                                                 float(q0[1] + q1[1]) / 2.0),
                        "note": "끈 각도 확산 (+%.0f/-%.0f 도)" % (sp, sn)})
            continue
        bx0, by0 = quad.min(axis=0)
        bx1, by1 = quad.max(axis=0)
        knot_t = _SHOE_T0 + 0.45 * (_SHOE_T1 - _SHOE_T0)
        crosses = 0
        knot = False
        for i in range(len(pos)):
            for j in range(len(neg)):
                if abs(pos[i][2] - neg[j][2]) < _SHOE_ANG_LO:
                    continue
                x = _line_cross(pos[i][0], pos[i][1],
                                neg[j][0], neg[j][1])
                if x is None or not (bx0 <= x[0] <= bx1
                                     and by0 <= x[1] <= by1):
                    continue
                crosses += 1
                t_along = float((x - a) @ u) / flen
                if t_along <= knot_t:
                    knot = True
        if crosses < _SHOE_CROSS_MIN:
            out.append({"side": side, "center": (float(q0[0] + q1[0]) / 2.0,
                                                 float(q0[1] + q1[1]) / 2.0),
                        "note": "X 교차 부족 (%d)" % crosses})
            continue
        if not knot:
            out.append({"side": side, "center": (float(q0[0] + q1[0]) / 2.0,
                                                 float(q0[1] + q1[1]) / 2.0),
                        "penalty": False,
                        "note": "X 연결은 있으나 발목 쪽 매듭 미확인 (로그만)"})
    return out


def _nearest_contact_dist(line_centroid_px, pose_lm, W, H):
    """관통 선 중심에서 가장 가까운 접촉 허용 부위까지의 정규화 거리."""
    if pose_lm is None or len(pose_lm) < 33:
        return None
    cx, cy = line_centroid_px
    nx, ny = cx / W, cy / H
    best = None
    for i in _CONTACT_LMS:
        pt = pose_lm[i]
        if not _lm_valid(pt):
            continue
        d = math.hypot(nx - pt[0], ny - pt[1])
        if best is None or d < best:
            best = d
    return best


def _band_iou(a, b):
    """두 밴드 마스크의 IoU — 중복 관통 후보 통합용."""
    inter = float(((a > 0) & (b > 0)).sum())
    union = float(((a > 0) | (b > 0)).sum())
    return inter / union if union > 0 else 0.0


def _dedupe_pen(pen, thresh=0.6):
    """밴드가 겹치는 관통 후보는 하나로 센다 (이중 페널티 방지).

    2026-10-12 벤치 실측: 같은 손에서 거의 동일한 양분선이 2개 나와 같은
    위반을 두 번 셌다. 밴드 IoU 가 임계값 이상이면 첫 번째만 남긴다.
    """
    kept = []
    for item in pen:
        dup = False
        for k in kept:
            if _band_iou(item["band"], k["band"]) > thresh:
                dup = True
                break
        if not dup:
            kept.append(item)
    return kept


def physic_score(rgb, person_mask=None, pose_lm=None, hand_lms=None):
    """rgb: uint8 HWC. person_mask: (H,W) 0~1 (None 이면 내부 산출).
    pose_lm: 33 (x,y[,vis]) 정규화. hand_lms: [[(x,y,hand)...21], ...] 정규화.

    반환: {score, passed, note, pen(band 목록), censor, hover, shoelace}
      pen/censor/hover 는 pull_pass 가 쓰는 내부 교정 정보다. shoelace 는
      워핑 교정 경로가 없는 판정+로그 전용 플래그다.
    """
    if rgb is None:
        return {"score": 0.0, "passed": False, "note": ["이미지 없음"],
                "pen": [], "censor": None, "hover": None, "shoelace": []}
    H, W = rgb.shape[:2]
    P = None
    if person_mask is not None:
        P = _np.asarray(person_mask, _np.float32)
        if P.ndim == 3:
            P = P[:, :, 0]
        if P.shape != (H, W):
            P = cv2.resize(P, (W, H), interpolation=cv2.INTER_LINEAR)
    if P is None and _person_mask_fn is not None:
        P = _person_mask_fn(rgb)
    if P is None:
        return {"score": 100.0, "passed": True,
                "note": ["인체 마스크 없음(통과)"],
                "pen": [], "censor": None, "hover": None, "shoelace": []}
    pen = _detect_penetrations(rgb, P, hand_lms=hand_lms, pose_lm=pose_lm)
    pen = _dedupe_pen(pen)
    hover = _detect_hover(pose_lm, rgb, P)
    censor = _detect_censor(pose_lm, hand_lms)
    shoelace = _detect_shoelace(pose_lm, rgb)
    score = 100.0
    note = []
    maxHW = float(max(H, W))
    for item in pen:
        c = item["line"]["p1"] + item["line"]["p2"]
        c = (c[0] / 2.0, c[1] / 2.0)
        d = _nearest_contact_dist(c, pose_lm, W, H)
        if d is not None and d < _CONTACT_NEAR:
            score -= _PEN_PEN_SOFT
            note.append("신체-사물 관통(접촉 부위 인근, 완화) %.3f" % d)
        else:
            score -= _PEN_PEN_STRICT
            note.append("신체-사물 관통(엄격)")
    if hover is not None:
        score -= _PEN_HOVER
        note.append("지지 표면 가장자리 걸침 (거리 %.3f)" %
                    (hover["dist"] / maxHW))
    if censor is not None:
        score -= _PEN_CENSOR
        note.append("무릎 사이 가림 손 배치 (검열 추정)")
    for item in shoelace:
        if item.get("penalty", True):
            score -= _PEN_SHOELACE
        note.append("운동화 끈(%s): %s" % (item["side"], item["note"]))
    score = max(0.0, round(score, 1))
    return {"score": score, "passed": score >= _PASS_LINE, "note": note,
            "pen": pen, "censor": censor, "hover": hover,
            "shoelace": shoelace}


def _shift_warp(u8, mask, dx, dy):
    """mask 영역을 (dx,dy)픽셀 이동시킨 워핑. kp_body_object 와 같은 규율."""
    h, w = u8.shape[:2]
    ys, xs = _np.where(mask > 0.25)
    if len(xs) == 0:
        return u8
    sxn = _np.clip(xs - dx, 0, w - 1).astype(_np.int64)
    syn = _np.clip(ys - dy, 0, h - 1).astype(_np.int64)
    warped = u8.astype(_np.float64)
    for c in range(3):
        warped[ys, xs, c] = u8[syn, sxn, c]
    return _np.clip(warped, 0, 255).astype(_np.uint8)


def _circle_band(center, radius, Pn):
    """중심 (x,y) 반경 radius 원형 밴드 — 인체 영역으로 한정."""
    h, w = Pn.shape[:2]
    m = _np.zeros((h, w), _np.uint8)
    cv2.circle(m, (int(round(center[0])), int(round(center[1]))),
               max(int(round(radius)), 3), 1, -1)
    return ((m > 0) & (Pn > 0.3)).astype(_np.float32)


def _apply_corrections(u8, sc):
    """판정 결과를 픽셀 워핑으로 살짝 고친다 (한 번에 모든 위반).

    Phy-SIC 가중치 규율(접촉 유지 우선)을 따라 위반 밴드만 움직인다 —
    정상 접촉 영역은 건드리지 않는다.
    """
    H, W = u8.shape[:2]
    maxHW = float(max(H, W))
    cur = u8
    step = _SHIFT_PX * _CORRECT_FRAC
    for item in sc.get("pen") or []:
        band = item["band"]
        if item.get("shift") is not None:
            sx, sy = item["shift"]
        else:
            n = item["line"]["nrm"]
            sx, sy = float(n[0]) * item["main_sign"], \
                float(n[1]) * item["main_sign"]
        cur = _shift_warp(cur, band, sx * step, sy * step)
    if sc.get("hover") is not None:
        Pn2 = _person_mask_fn(cur) if _person_mask_fn is not None else None
        if Pn2 is not None:
            hv = sc["hover"]
            band = _circle_band(hv["hip"], 0.035 * maxHW,
                                (Pn2 > 0.02).astype(_np.float32))
            cur = _shift_warp(cur, band, hv["dir"][0] * step,
                              hv["dir"][1] * step)
    if sc.get("censor") is not None:
        Pn3 = _person_mask_fn(cur) if _person_mask_fn is not None else None
        if Pn3 is not None:
            cz = sc["censor"]
            band = _circle_band(cz["center"], 0.025 * maxHW,
                                (Pn3 > 0.02).astype(_np.float32))
            cur = _shift_warp(cur, band, cz["dir"][0] * step,
                              cz["dir"][1] * step)
    return cur


def physic_pull_pass(vae, out, rgb, strength=0.15, cache=None, max_iter=10,
                     pose_lm=None, hand_lms=None):
    """물리 위반(관통·걸침·가림 손)을 줄이는 방향으로 out 을 미세 당긴다.

    반환: (out_latent, best_score, iter_done) — kp_body_object 와 같은
    best-keep 계약. 개선이 없으면 입력 그대로(iter_done=0).
    """
    import torch as _t
    if (_person_mask_fn is None or _decode_latent_rgb_safe is None
            or _encode_rgb_safe is None or _downsample_mask is None):
        return out, None, 0
    try:
        from .kp_math import _match_spatial as _match_spatial
    except ImportError:
        from kp_math import _match_spatial as _match_spatial
    try:
        if rgb is None:
            return out, None, 0
        u8 = (_np.clip(rgb, 0.0, 1.0) * 255.0).astype(_np.uint8) \
            if rgb.dtype != _np.uint8 else rgb.copy()
        cur = out
        best_out = None
        best_score = None
        it_done = 0
        for it in range(max_iter):
            plm = pose_lm
            hlm = hand_lms
            if plm is None and _pose_fn is not None:
                plm = _pose_fn(u8, with_visibility=True)
            if hlm is None and _hands_fn is not None:
                hlm = _hands_fn(u8, plm)
            sc = physic_score(u8, pose_lm=plm, hand_lms=hlm)
            if best_score is None or sc["score"] > best_score:
                best_score = sc["score"]
                best_out = cur
            if sc["passed"]:
                break
            if (not sc["pen"]) and sc["hover"] is None \
                    and sc["censor"] is None and sc.get("shoelace"):
                # 끈 플래그만 남은 경우 — 워핑 교정 경로가 없어 반복이
                # 무의미하다(디코드/인코드 낭비). 판정은 note 로그로 남는다.
                break
            if best_out is not None and best_out is not cur \
                    and sc["score"] < best_score:
                break
            warped = _apply_corrections(u8, sc)
            warped_lat = _encode_rgb_safe(vae, warped)
            if warped_lat is None:
                break
            warped_lat = _match_spatial(warped_lat, cur)
            if warped_lat is None:
                break
            Pm = _person_mask_fn(u8)
            if Pm is None:
                break
            mask_lat = _downsample_mask(_np.asarray(Pm), cur.shape)
            if mask_lat is None:
                break
            mask_t = _t.from_numpy(_np.ascontiguousarray(mask_lat)).to(
                device=cur.device, dtype=cur.dtype)
            cur = cur + strength * mask_t * (warped_lat - cur)
            rgb2 = _decode_latent_rgb_safe(vae, cur)
            if rgb2 is None:
                break
            u8 = (_np.clip(rgb2, 0.0, 1.0) * 255.0).astype(_np.uint8)
            it_done = it + 1
        if best_out is None or best_out is out:
            return out, best_score, 0
        return best_out, best_score, it_done
    except Exception:
        return out, None, 0


# 아래 헬퍼들은 consistency_keeper 의 것을 가져쓰기 위해 런타임에 바인딩된다.
_decode_latent_rgb_safe = None
_encode_rgb_safe = None
_downsample_mask = None
_person_mask_fn = None
_pose_fn = None
_hands_fn = None


def _bind_helpers(decode_fn, encode_fn, downsample_fn, person_mask_fn,
                  pose_fn=None, hands_fn=None):
    """consistency_keeper 가 자신의 VAE/마스크/랜드마크 헬퍼를 주입한다.

    pose_fn: (u8, with_visibility) -> 33 랜드마크 또는 None
    hands_fn: (u8, pose_pts) -> [[(x,y,hand)...21], ...] 또는 None
    """
    global _decode_latent_rgb_safe, _encode_rgb_safe, _downsample_mask
    global _person_mask_fn, _pose_fn, _hands_fn
    _decode_latent_rgb_safe = decode_fn
    _encode_rgb_safe = encode_fn
    _downsample_mask = downsample_fn
    _person_mask_fn = person_mask_fn
    _pose_fn = pose_fn
    _hands_fn = hands_fn
