"""손 미세 당김 (hand_pull) — 옵션 A 확장 (2026-10-12, 수정 2026-10-13).

목적: 검출된 손 landmark 의 물리 위반(붙음·겹침·뒤꺾임)을 줄이는 방향으로
이미지를 **살짝** 변형한다. 사용자 제안("손의 모양·위치를 살짝살짝 바꾸며
손과 손이 잘 표현되는 방향으로 당기기")을 받아들인다.

방식:
  1. 손 21점을 물리 위반이 완화되도록 _CORRECT_FRAC 만 보정한 reference 생성
     (_hand_ref_corrected). 끝점 뭉침→부채꼴 fan-out, 뒤꺾임→정상 굴절.
  2. 원본 이미지를 reference 로 **TPS(Thin Plate Spline) 워핑** — 손 영역만
     국소 변형된다 (scipy Rbf thin-plate).
  3. 손 마스크 영역에 워핑 결과를 strength 로 블렌드.

2026-10-13 실측 수정 (probe: hand_pull_fix_probe4.py, 실제 생성 이미지):
  - 워핑이 **역방향**이었다. output(q)=input(q+f(q)) 샘플링에 f 를 src 위치에
    dst-src 로 놓아 내용이 dst→src 로 움직였다 (합성 마커 실측: 마커 소멸).
    dst 위치에 src-dst 를 맞춰 output(dst)=input(src) 이 되게 고쳤다.
  - 각도 기준이 화면 **절대각**(_TARGET_ANGLES)이었다. 손이 아래를 향한 이미지
    (축 130°)에서는 목표각(0°±) 이 전부 반대 방향 — frac 1.0 에도 점수 33.3,
    뒤꺾임까지 유발. 손 축 기준 **상대각 + 체인 전체 회전**으로 바꿨다.
    측정: 상대각 frac 0.6 에서 landmark 점수 100 (절대각은 어떤 frac 도 33.3).
  - _CORRECT_FRAC 0.15 → 0.6: 0.15 로는 끝점 분리가 sep 0.005 로 멈춰
    0.018(합격선)에 못 미친다 (0.6 에서 100).

한계 (솔직히):
  - **손톱은 교정 안 됨** — 텍스처/디테일 영역이라 latent 당김으로 안 나온다.
    kp_hand_phys 에서 합격 점수에서 손톱을 뺀 이유다.
  - 워핑이 손을 더 망칠 위험이 있어 best-keep 이 악화 상태를 채택하지 않는다.
  - 참조가 입력 자신이므로 "완벽 교정"이 아니라 "위반 완화 유도" 다.
"""

import math

# mediapipe hand 21점 인덱스
_FINGER_TIPS = (4, 8, 12, 16, 20)
_FINGER_BASES = (1, 5, 9, 13, 17)
_FINGER_CHAINS = [
    (1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20),
]

# 손 축(손목0→중지MCP9) 기준 상대각 목표 (라디안). 엄지·소지가 양끝,
# 중지 0. 부호는 엄지 밑마디의 축 교차 부호로 뒤집는다 (자세 무관).
_TARGET_REL = (0.95, 0.30, 0.0, 0.30, 0.95)
_CORRECT_FRAC = 0.6  # 보정 비율 (2026-10-13 실측: 0.15 는 합격선 미달)


def _norm_angle(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def _hand_ref_corrected(hands):
    """현재 손 21점 → 물리 위반을 _CORRECT_FRAC 만 완화한 reference 좌표.

    반환: [[(x,y,h)...21], ...] (정규화 좌표, handedness 는 그대로).

    손 축(손목0→중지MCP9) 기준으로 각 손가락을 **체인 전체**로 베이스 주위에
    회전시킨다. 팁만 옮기면 중간 마디가 꺾여 뒤꺾임을 만들지만, 체인 전체
    회전은 내부 마디 각도를 보존하므로 bend 항목이 악화되지 않는다.
    엄지 측 부호는 엄지 밑마디(1)의 축 교차 부호로 판정한다.
    """
    out = []
    for hand in hands:
        new = [list(p) for p in hand]
        ax = hand[9][0] - hand[0][0]
        ay = hand[9][1] - hand[0][1]
        if math.hypot(ax, ay) < 1e-6:
            out.append([(x, y, h) for x, y, h in new])
            continue
        axis = math.atan2(ay, ax)
        cross = (ax * (hand[1][1] - hand[0][1])
                 - ay * (hand[1][0] - hand[0][0]))
        s = 1.0 if cross >= 0 else -1.0
        rel_targets = (s * _TARGET_REL[0], s * _TARGET_REL[1], 0.0,
                       -s * _TARGET_REL[3], -s * _TARGET_REL[4])
        for i, (bi, ti) in enumerate(zip(_FINGER_BASES, _FINGER_TIPS)):
            bx, by = hand[bi][0], hand[bi][1]
            dx, dy = hand[ti][0] - bx, hand[ti][1] - by
            if math.hypot(dx, dy) < 1e-6:
                continue
            cur = math.atan2(dy, dx)
            delta = _norm_angle((axis + rel_targets[i]) - cur) * _CORRECT_FRAC
            if abs(delta) < 1e-9:
                continue
            ca, sa = math.cos(delta), math.sin(delta)
            for k in _FINGER_CHAINS[i][1:]:
                px = hand[k][0] - bx
                py = hand[k][1] - by
                new[k] = (bx + px * ca - py * sa,
                          by + px * sa + py * ca,
                          hand[k][2])
        out.append([(x, y, h) for x, y, h in new])
    return out


def _hand_mask_from_landmarks(hands, h, w):
    """손 21점 → 손 영역 마스크 (H,W) 0~1. 팜 hull + 손가락 두꺼운 선 + 블러."""
    import numpy as _np
    import cv2
    mask = _np.zeros((h, w), _np.float32)
    thick = max(6, w // 90)
    for hand in hands:
        px = [(int(x * w), int(y * h)) for x, y, _ in hand]
        if len(px) < 21:
            continue
        palm = _np.array([[px[0], px[1], px[5], px[9], px[13], px[17]]],
                         _np.int32)
        cv2.fillConvexPoly(mask, palm, 1.0)
        for ch in _FINGER_CHAINS:
            for k in range(len(ch) - 1):
                cv2.line(mask, px[ch[k]], px[ch[k + 1]], 1.0, thickness=thick)
    mask = cv2.GaussianBlur(mask, (0, 0),
                            max(3.0, w / 400.0))
    return _np.clip(mask, 0.0, 1.0).astype(_np.float32)


def _warp_hands_tps(u8, src_pts, dst_pts, mask):
    """원본 u8(HWC)를 src→dst 로 **내용 이동**시키는 TPS 워핑.

    src/dst: [(x,y)...] 정규화 좌표. mask: (H,W) 0~1.
    반환: 워핑된 u8.

    내용 이동 방향 (2026-10-13 실측 수정): 샘플링은 output(q)=input(q+f(q))
    이라 f 를 **src 위치에 dst-src 로** 놓으면 output(src)=input(dst) — 내용이
    dst→src 반대 방향으로 움직였다 (합성 마커 실측: 마커가 목표 지점에 안
    나타나고 소멸). dst 위치에 src-dst 를 맞춰야 output(dst)=input(src),
    즉 내용이 src→dst 로 이동한다.
    """
    import numpy as _np
    from scipy.interpolate import Rbf
    h, w = u8.shape[:2]
    # control points → 픽셀 (y,x)
    sp = _np.array([[y * h, x * w] for x, y in src_pts], _np.float64)
    dp = _np.array([[y * h, x * w] for x, y in dst_pts], _np.float64)
    if len(sp) < 4 or len(sp) != len(dp):
        return u8
    ys, xs = _np.where(mask > 0.25)
    if len(xs) == 0:
        return u8
    sx, sy = xs.astype(_np.float64), ys.astype(_np.float64)
    warped = u8.astype(_np.float64)
    try:
        rbf_dx = Rbf(dp[:, 1], dp[:, 0], sp[:, 1] - dp[:, 1],
                     function="thin_plate", smooth=0.0)
        rbf_dy = Rbf(dp[:, 1], dp[:, 0], sp[:, 0] - dp[:, 0],
                     function="thin_plate", smooth=0.0)
        dx = rbf_dx(sx, sy)
        dy = rbf_dy(sx, sy)
    except Exception:
        return u8
    nx = _np.clip(sx + dx, 0, w - 1).astype(_np.int64)
    ny = _np.clip(sy + dy, 0, h - 1).astype(_np.int64)
    for c in range(3):
        warped[ys, xs, c] = u8[ny, nx, c]
    return _np.clip(warped, 0, 255).astype(_np.uint8)


def hand_pull_pass(vae, sampled, hands, strength=0.15, cache=None,
                   max_iter=3):
    """손 물리 위반을 줄이는 방향으로 sampled 를 미세 당긴다.

    반환: (out_latent, best_score, iter_done).
    out_latent: **가장 좋은 점수의 상태** (2026-10-12 best-keep 계약).
      동점이면 **나중 상태**를 채택한다 (2026-10-13 사용자 지시: "10번 시도 후
      95% 미만이 나오면 건너뛰지 말고 10번 시도 중 가장 높은 점수로 당겨서
      생성"). 점수는 3단계(33.3 단위)라 동점 안에도 기하 진행(sep 증가)이
      들어있다 — 픽셀 루프 실측에서 동점 구간에도 sep 이 0.009→0.017 로
      늘었다. 먼저가 아니라 나중을 쓰는 이유다.
      어떤 워프도 입력과 동점 이상이 못 되면(전부 악화) 입력 그대로 +
      iter_done==0 을 돌려준다 — 악화 상태는 절대 채택하지 않는다.
    best_score: 반환 이미지의 손 물리 점수 (워프 전 점수를 반환 이미지의
      점수로 보고하던 결함 수정).
    iter_done: 실제 워프 횟수. 호출자는 이 값으로 "이미 최선" 을 판정한다.
      0 이어도 best_score 가 있으면 동점 이상이 없었다는 뜻이다 (전부 악화).
    사유는 hand_pull_last_error() 로 읽는다 (2026-10-13: "당김 불가" 와
      "이미 최선" 이 로그에서 구분되지 않아 진단이 추측이 됐다).
    """
    global _LAST_ERROR
    _LAST_ERROR = None
    import numpy as _np
    try:
        from .kp_hand_phys import hand_physical_score as _score
    except ImportError:
        from kp_hand_phys import hand_physical_score as _score
    try:
        from .kp_math import _match_spatial as _match_spatial
    except ImportError:
        from kp_math import _match_spatial as _match_spatial
    try:
        rgb = None
        if cache is not None and ("hand_rgb", id(sampled)) in cache:
            rgb = cache[("hand_rgb", id(sampled))]
        if rgb is None:
            rgb = _decode_latent_rgb_safe(vae, sampled)
            if cache is not None:
                cache[("hand_rgb", id(sampled))] = rgb
        if rgb is None:
            _LAST_ERROR = "decode_failed"
            return sampled, None, 0
        u8 = (_np.clip(rgb, 0.0, 1.0) * 255.0).astype(_np.uint8)
        H, W = u8.shape[:2]
        out = sampled
        best_out = None
        best_score = None
        iter_done = 0
        for it in range(max_iter):
            # 현재 상태 점수. out 과 u8 은 항상 같은 상태다 — 점수가 반환
            # 이미지의 점수가 되게 하는 계약 (2026-10-12 실측 결함 수정).
            # 예전엔 워프 **전** 점수를 last_score 로 돌려 마지막 워프 결과의
            # 점수로 보고했고, best-keep 이 없어 악화 결과가 그대로 채택됐다
            # (실측: 66.7 -> 33.3 로 10회 워프가 악화만 함).
            sc = _score(hands, image=u8, w=W, h=H)
            # 동점은 나중이 이긴다 (>=): 최고 점수 상태 중 가장 당김이 많이
            # 적용된 것을 채택한다 (2026-10-13 사용자 지시 — 미달이어도 최고점
            # 채택, 건너뜀 금지). 전부 악화면 best_out 이 입력 그대로라 아래
            # 분기에서 입력 반환 + iter 0 이 된다.
            if best_score is None or sc["score"] >= best_score:
                best_score = sc["score"]
                best_out = out
            if sc["passed"]:
                _LAST_ERROR = None
                break
            # 지금까지의 최선보다 나빠졌으면 중단한다. 다음 워프는 이 나쁜
            # 상태에서 시작하므로 되돌아올 근거가 없다.
            if (best_out is not None and best_out is not out
                    and sc["score"] < best_score):
                break
            # 보정 reference + 마스크 + 워핑
            corrected = _hand_ref_corrected(hands)
            # 마스크는 원 위치와 보정 위치를 **모두** 덮는다 — 워핑은 내용을
            # src→dst 로 옮기는데, 마스크가 원 위치에만 있으면 dst 로 간
            # 픽셀이 워핑·블렌드 밖으로 빠진다 (2026-10-13 방향 수정에 동반).
            mask_px = _hand_mask_from_landmarks(hands + corrected, H, W)
            src = [(x, y) for hand in hands for (x, y, _) in hand]
            dst = [(x, y) for hand in corrected for (x, y, _) in hand]
            warped = _warp_hands_tps(u8, src, dst, mask_px)
            # 워핑 결과를 latent 로 인코딩
            warped_lat = _encode_rgb_safe(vae, warped)
            if warped_lat is None:
                _LAST_ERROR = "encode_failed"
                break
            # latent 크기·장치·dtype 정렬 (골격 당김과 동일 규율, 2026-10-12).
            warped_lat = _match_spatial(warped_lat, out)
            if warped_lat is None:
                _LAST_ERROR = "spatial_mismatch"
                break
            # 마스크를 latent 크기로 다운샘플 (numpy, 채널 1)
            mask_lat = _downsample_mask(mask_px, out.shape)
            if mask_lat is None:
                _LAST_ERROR = "mask_downsample_failed"
                break
            # numpy 마스크 -> out 과 같은 장치/dtype 텐서 (채널 1 로 broadcast).
            import torch as _t
            mask_t = _t.from_numpy(_np.ascontiguousarray(mask_lat)).to(
                device=out.device, dtype=out.dtype)
            out = out + strength * mask_t * (warped_lat - out)
            # 다음 반복을 위해 out 을 다시 디코드
            rgb = _decode_latent_rgb_safe(vae, out)
            if rgb is None:
                _LAST_ERROR = "redecode_failed"
                break
            u8 = (_np.clip(rgb, 0.0, 1.0) * 255.0).astype(_np.uint8)
            H, W = u8.shape[:2]
            hands = _reestimate_hands(u8, hands)  # 검출 재시도 (위치 이동 반영)
            iter_done = it + 1
        # best_out 이 입력 자신이면 어떤 워프도 동점 이상이 못 됐다는 뜻
        # (전부 악화 — 악화 중단이 먼저 끊었거나 max_iter 를 다 썼다).
        # 그때만 입력 그대로 + iter 0 을 돌려준다. 호출자는 iter_done==0 으로
        # "채택할 게 없음" 을 알 수 있다.
        if best_out is None or best_out is sampled:
            if _LAST_ERROR is None:
                _LAST_ERROR = "no_improvement"
            return sampled, best_score, 0
        _LAST_ERROR = None
        return best_out, best_score, iter_done
    except Exception as _e:
        _LAST_ERROR = "exception:%s: %s" % (type(_e).__name__, _e)
        return sampled, None, 0


def hand_pull_last_error():
    """가장 최근 hand_pull_pass 의 종료 사유 (str) 또는 None (성공/미실행)."""
    return _LAST_ERROR


# 아래 헬퍼들은 consistency_keeper 의 것을 가져쓰기 위해 런타임에 바인딩된다.
_decode_latent_rgb_safe = None
_encode_rgb_safe = None
_downsample_mask = None
_reestimate_hands = None
_LAST_ERROR = None


def _bind_helpers(decode_fn, encode_fn, downsample_fn, reestimate_fn):
    """consistency_keeper 가 자신의 VAE 헬퍼를 주입한다."""
    global _decode_latent_rgb_safe, _encode_rgb_safe, _downsample_mask, _reestimate_hands
    _decode_latent_rgb_safe = decode_fn
    _encode_rgb_safe = encode_fn
    _downsample_mask = downsample_fn
    _reestimate_hands = reestimate_fn
