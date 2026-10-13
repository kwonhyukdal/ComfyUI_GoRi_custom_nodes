"""신체-사물 물리 결합 방지 (body_object) - 2026-10-12.

목적: 생성 이미지에서 인체 실루엣이 사물(구조물)과 물리적으로 결합(융합)되는 것을
탐지하고, 살짝 위치/형태를 바꿔 분리한다. 손 물리(옵션 A)와 같은 0~100 점수 +
95% 합격 선 체계를 공유한다(통합 합격 선 _PASS_LINE).

탐지 (self-contained, 참조 불필요):
  P = 인체 마스크 (mediapipe pose 기반 soft blob, 0~1)
  S = 구조 맵 (Canny 에지 밀도, 0~1) - 사물/표면이 있는 곳
  B = P 의 천이(경계) 영역
  결합 픽셀 = B ∩ (S 높음) ∩ (경계 명암 대비 낮음)
    -> 인체 경계가 디테일한 사물에 붙어 깨끗히 분리되지 않음
  merge_ratio = 결합픽셀 수 / 경계픽셀 수
  score = 100*(1-merge_ratio); passed = score >= 95 (통합 합격 선)

당김 (pull, best-effort):
  결합 방향 반대로 인체 영역을 몇 px 밀어 사물에서 살짝 떨어뜨린다.
  (warp 변위 + VAE 재인코드 + latent 블렌드, strength 기본 0.15)
  한계: 완전 분리는 인페인팅(별도 모델)이 필요 - 이 노드는 "살짝 위치/형태 변경"
  유도만 한다(사용자 지시: 교정은 못 하지만 살짝 바꿔서 방향으로).

참고: 손톱과 마찬가지로 "완벽 교정"이 아니라 "위반 완화 유도" 다.
"""

import math

import numpy as _np
import cv2

# 임계값 (모든 맵은 0~1 정규화 기준)
_S_HI = 0.30          # 구조(사물) 판정 - 이 이상이면 "사물/표면" 으로 본다
_CLEAR_LO = 16.0      # 경계 명암 대비 임계 - 이보다 낮으면 "융합(분리 안 됨)" 으로 본다
_SHIFT_PX = 6.0       # 미세 당김 이동량(픽셀)
_CORRECT_FRAC = 0.6   # 이동 비율(살짝)


def _structure_map(rgb):
    """uint8 RGB -> (H,W) 0~1 구조(에지) 맵. 사물/표면이 있는 곳이 밝다."""
    gray = rgb if rgb.ndim == 2 else cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if gray.dtype != _np.uint8:
        gray = _np.clip(gray, 0, 255).astype(_np.uint8)
    edges = cv2.Canny(gray, 50, 150)
    S = edges.astype(_np.float32) / 255.0
    k = max(3.0, gray.shape[1] / 300.0)
    S = cv2.GaussianBlur(S, (0, 0), k)
    return S


def _centroid(mask):
    """mask>0.25 영역의 무게중심 (x, y). 없으면 None."""
    ys, xs = _np.where(mask > 0.25)
    if len(xs) == 0:
        return None
    return (float(xs.mean()), float(ys.mean()))


def body_object_score(rgb, person_mask=None):
    """rgb: uint8 HWC. person_mask: (H,W) 0~1 (None 이면 내부 산출).

    반환: {score(0~100), passed(bool), note[...], merge_ratio}
    """
    if rgb is None:
        return {"score": 0.0, "passed": False, "note": ["이미지 없음"],
                "merge_ratio": 1.0}
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
        # 인체를 못 찾으면 결합할 대상이 없다 -> 통과 처리(합격 로직상 pass).
        return {"score": 100.0, "passed": True,
                "note": ["인체 마스크 없음(통과)"], "merge_ratio": 0.0}
    Pn = (P > 0.02).astype(_np.float32)
    if Pn.sum() < 20:
        return {"score": 100.0, "passed": True,
                "note": ["인체 영역 미미(통과)"], "merge_ratio": 0.0}
    S = _structure_map(rgb)
    # 경계 밴드: 팽창-침식 차이 (천이 영역)
    kernel = _np.ones((3, 3), _np.float32)
    dil = cv2.dilate(Pn, kernel, iterations=2)
    ero = cv2.erode(Pn, kernel, iterations=2)
    band = ((dil - ero) > 0).astype(_np.float32)
    band_px = _np.where(band > 0)
    if len(band_px[0]) == 0:
        return {"score": 100.0, "passed": True,
                "note": ["경계 없음(통과)"], "merge_ratio": 0.0}
    gray = (cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(_np.float32)
            if rgb.ndim == 3 else rgb.astype(_np.float32))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = _np.sqrt(gx * gx + gy * gy)
    s_vals = S[band_px]
    g_vals = grad[band_px]
    # 결합 = 경계인데 사물(고구조) 옆이고 명암 대비가 낮음(융합)
    merge_mask = (s_vals > _S_HI) & (g_vals < _CLEAR_LO)
    merge_ratio = float(_np.mean(merge_mask))
    score = round(100.0 * (1.0 - merge_ratio), 1)
    note = []
    if merge_ratio > 0:
        note.append("신체-사물 결합 비율 %.3f" % merge_ratio)
    return {"score": score, "passed": score >= 95.0, "note": note,
            "merge_ratio": merge_ratio}


def _shift_warp(u8, mask, dx, dy):
    """인체 영역(mask)을 (dx,dy)픽셀만큼 이동시킨 워핑. new(p)=old(p-shift).

    변위장 기반 translation: 현재 위치 p 의 값을 p-shift 위치 값으로 채운다.
    따라서 인체 내용이 +shift 방향으로 이동하고, 뒤쪽 가장자리는 배경/사물이
    채워진다(몇 px 이음새는 strength 블렌드로 완화).
    """
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


def body_object_pull_pass(vae, out, rgb, strength=0.15, cache=None,
                          max_iter=10):
    """신체-사물 결합을 줄이는 방향으로 out 을 미세 당긴다.

    반환: (out_latent, best_score, iter_done).
      out_latent: **가장 좋은 점수의 상태** (2026-10-12 best-keep 계약,
        kp_hand_repair 와 동일). 개선이 없으면 입력 그대로.
      best_score: 반환 이미지의 신체-사물 점수.
      iter_done: 실제 시프트 횟수. 개선이 없으면 0.
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
        H, W = u8.shape[:2]
        cur = out
        best_out = None
        best_score = None
        it_done = 0
        for it in range(max_iter):
            P = _person_mask_fn(u8)
            sc = body_object_score(u8, person_mask=P)
            if best_score is None or sc["score"] > best_score:
                best_score = sc["score"]
                best_out = cur
            if sc["passed"]:
                break
            # 지금까지의 최선보다 나빠졌으면 중단한다 (악화 상태에서 이어서
            # 밀어도 되돌아올 근거가 없다 — 2026-10-12 best-keep 계약).
            if (best_out is not None and best_out is not cur
                    and sc["score"] < best_score):
                break
            if P is None or float(_np.asarray(P).sum()) < 20:
                break
            S = _structure_map(u8)
            obj = (S > _S_HI) & (_np.asarray(P) < 0.3)
            if float(obj.sum()) < 10:
                break
            pc = _centroid(_np.asarray(P))
            oc = _centroid(obj)
            if pc is None or oc is None:
                break
            dx, dy = pc[0] - oc[0], pc[1] - oc[1]
            n = math.hypot(dx, dy)
            if n < 1e-3:
                break
            dx, dy = dx / n, dy / n
            shx = dx * _SHIFT_PX * _CORRECT_FRAC
            shy = dy * _SHIFT_PX * _CORRECT_FRAC
            warped = _shift_warp(u8, _np.asarray(P), shx, shy)
            warped_lat = _encode_rgb_safe(vae, warped)
            if warped_lat is None:
                break
            # latent 정렬 (손 당김과 동일 규율).
            warped_lat = _match_spatial(warped_lat, cur)
            if warped_lat is None:
                break
            mask_lat = _downsample_mask(_np.asarray(P), cur.shape)
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
        # 개선이 없었으면 입력 그대로를 돌려준다 — 호출자는 iter_done==0 으로
        # "이미 최선" 을 알 수 있다.
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


def _bind_helpers(decode_fn, encode_fn, downsample_fn, person_mask_fn):
    """consistency_keeper 가 자신의 VAE/마스크 헬퍼 + 인체마스크 fn 을 주입한다."""
    global _decode_latent_rgb_safe, _encode_rgb_safe, _downsample_mask, _person_mask_fn
    _decode_latent_rgb_safe = decode_fn
    _encode_rgb_safe = encode_fn
    _downsample_mask = downsample_fn
    _person_mask_fn = person_mask_fn
