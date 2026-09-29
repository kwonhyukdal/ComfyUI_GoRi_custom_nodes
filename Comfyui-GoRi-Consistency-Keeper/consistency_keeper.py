# -*- coding: utf-8 -*-
"""(GoRi) Consistency Keeper — 2차 패스 일관성 당김 노드.

샘플러가 뽑은 latent를 원본·카메라 기준 latent 쪽으로 당겨
신원·구도의 틀어짐을 줄인다. 다시 그리지 않으므로(재인코딩·재샘플링 없음)
파손된 손가락 같은 것은 고치지 못한다 — 그건 디테일러 영역이다.

체결 (GoRi DNA):
  corrected = sampled + a*(camera - sampled) + b*(original - sampled)
  - a (strength_camera): 연출 방향 당김
  - b (strength_original): 원본 신원 당김
크기가 다르면 bicubic 리사이즈로 맞춘다. 배치·채널이 다르면 해당 기준은
건너뛴다(로그 후 계속). 외부 pip 패키지 없음 — ComfyUI 환경의 torch만 사용.
"""

from __future__ import annotations


def _get_samples(latent) -> object:
    """LATENT dict → samples 텐서. 없으면 None."""
    try:
        if isinstance(latent, dict):
            s = latent.get("samples")
            if s is not None and hasattr(s, "dim") and s.dim() == 4:
                return s
    except Exception:
        pass
    return None


def _match_spatial(ref, target) -> object:
    """ref를 target의 (N, C, H, W) 중 공간 크기에 맞춘다. 실패 시 None."""
    try:
        import torch.nn.functional as _f
        if tuple(ref.shape) == tuple(target.shape):
            return ref
        if ref.shape[0] != target.shape[0] or ref.shape[1] != target.shape[1]:
            return None
        resized = _f.interpolate(
            ref.to(dtype=target.dtype),
            size=(int(target.shape[2]), int(target.shape[3])),
            mode="bicubic", align_corners=False)
        return resized.to(device=target.device, dtype=target.dtype)
    except Exception:
        return None


def _drift_mse(a, b) -> float | None:
    """두 latent 평균제곱편차. 비교 불가면 None."""
    try:
        import torch as _t
        return float(_t.mean((a - b) ** 2).item())
    except Exception:
        return None


def _damp_factor(drift) -> float:
    """틀어짐 기반 자동 감쇠. 작으면 1, 크면 0으로 수렴.

    왜(Why): "융합하되 변형 없이" — 당기면 깨질 구도면 노드가 스스로
    손을 놓는다. 0.8부터 선형 감쇠, 2.0에서 0.
    """
    try:
        if drift is None or drift <= 0.8:
            return 1.0
        return max(0.0, 1.0 - (drift - 0.8) / 1.2)
    except Exception:
        return 1.0


def _lighting_mismatch(a, b) -> float | None:
    """조명 흐름 불일치 (Retinex 근사). 0=동일, ~2=무관.

    왜(Why): latent에는 RGB가 없어 고전 Retinex(저주파=조명)를
    채널평균+8x8 저역통과로 근사한다. 정규화 후 비교라 밝기 절대값이
    아닌 흐름 방향만 본다. 비교 불가면 None.
    """
    try:
        import torch.nn.functional as _f
        import torch as _t
        la = _t.mean(a.float(), dim=1, keepdim=True)
        lb = _t.mean(b.float(), dim=1, keepdim=True)
        la = _f.interpolate(la, size=(8, 8), mode="area")
        lb = _f.interpolate(lb, size=(8, 8), mode="area")
        la = la - la.mean()
        lb = lb - lb.mean()
        sa = float(la.std().item()) + 1e-6
        sb = float(lb.std().item()) + 1e-6
        return float(_t.mean(((la / sa) - (lb / sb)) ** 2).item())
    except Exception:
        return None


def _light_damp_factor(mismatch) -> float:
    """조명 게이트. 1.0 이하는 1, 2.0에서 0으로 선형 감쇠."""
    try:
        if mismatch is None or mismatch <= 1.0:
            return 1.0
        return max(0.0, 1.0 - (mismatch - 1.0))
    except Exception:
        return 1.0


def _decode_latent_rgb(vae, latent, cache=None):
    """latent -> RGB numpy 배열(H,W,3). 실행당 캐시로 중복 디코딩을 없앤다.

    왜(Why) 캐시가 필요한가(2026-09-28 실측): 한 실행에서 `sampled` 를
    **전 해상도로 두 번** 디코딩했다(인체 마스크용 + 부위맵용). 128x128
    latent 기준 1024x1024 이미지 2회 — VAE 디코딩이 이 노드에서 가장 비싼
    연산인데 같은 결과를 두 번 만들고 있었다. `original` 도 마찬가지.
    캐시 키는 (id(latent), 1.0) 이라 서로 다른 텐서를 섞지 않는다.
    """
    try:
        if vae is None or latent is None:
            return None
        import torch as _t
        import numpy as _np
        key = (id(latent), 1.0)
        if cache is not None and key in cache:
            return cache[key]
        with _t.no_grad():
            img = vae.decode(latent)
        if hasattr(img, "detach"):
            img = img.detach().cpu()
        arr = img.numpy() if hasattr(img, "numpy") else _np.asarray(img)
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.ndim == 4:
            arr = arr[0]
        if arr.ndim != 3:
            return None
        arr = _np.clip(arr, 0.0, 1.0)
        if cache is not None:
            cache[key] = arr
        return arr
    except Exception:
        return None


def _person_mask_for_latent(vae, sampled, cache=None):
    """샘플 latent의 인체 영역 마스크 (latent 해상도, 0~1). 없으면 None.

    왜(Why): 손만 골라 당기면 몸통이 소외된다. 포즈 분할 마스크로
    신체 전체를 커버하고 배경은 그대로 둔다. mediapipe 미설치·VAE
    미연결·미검출이면 None → 기존 전역 당김 그대로 (조용히 스킵).
    """
    try:
        import mediapipe as _mp
    except Exception:
        return None
    try:
        import torch as _t
        import numpy as _np
        if vae is None or sampled is None:
            return None
        arr = _decode_latent_rgb(vae, sampled, cache=cache)
        if arr is None:
            return None
        u8 = (arr * 255.0).astype(_np.uint8)
        pose = _mp.solutions.pose.Pose(
            static_image_mode=True, enable_segmentation=True,
            min_detection_confidence=0.5)
        try:
            res = pose.process(u8)
        finally:
            try:
                pose.close()
            except Exception:
                pass
        seg = getattr(res, "segmentation_mask", None)
        if seg is None:
            return None
        seg = _np.asarray(seg, dtype=_np.float32)
        if seg.max() <= 0.01 and not getattr(
                res, "pose_landmarks", None):
            return None
        mask = (seg > 0.5).astype(_np.float32)
        if mask.max() <= 0:
            return None
        m = _t.from_numpy(mask[None, None]).to(
            device=sampled.device, dtype=sampled.dtype)
        _, _, lh, lw = sampled.shape
        import torch.nn.functional as _f
        m = _f.interpolate(m, size=(lh, lw), mode="bilinear",
                           align_corners=False)
        m = _f.avg_pool2d(m, kernel_size=3, stride=1, padding=1)
        m = m.clamp(0.0, 1.0)
        # 여기 있던 `del img, arr, seg, mask` 도 **한 번도 실행되지 않았다**.
        # img는 이 함수의 로컬이 아니라 `_decode_latent_rgb` 안의 로컬이라
        # NameError 가 났고 except 가 삼켰다. 명시적 del 은 필요 없다 —
        # 함수가 반환되면 로컬은 회수된다. 남은 것은 VRAM 정리뿐이다.
        del u8, seg, mask
        _release_vram()
        return m
    except Exception:
        return None



# ---------------------------------------------------------------------------
# 부위별 디테일 손실 감지 (2026-09-28)
#
# 왜(Why): 카메라 노드가 텍스트로 "손가락 5개·발가락 5개"를 넣지만 diffusion은
# 그 지시를 **강제하지 못한다**(사전확률은 부드러운 확률). 그런데 원본
# latent에는 이미 정확한 손이 들어 있다. 그러므로 해부는 "몇 개여야 한다"가
# 아니라 **"원본과 얼마나 달라졌는가"**로 접근할 수 있다 — 그건 산술이지
# 추측이 아니다.
#
# 한계(정확): 원본이 틀렸으면 복원도 틀린다. 원본이 정확한 부위만 근거가 된다.
# ---------------------------------------------------------------------------
# 에지 밀도 = 그 부위에 세부가 얼마나 살아 있는지. 뭉개진 부위는 밀도가 낮다.
# MediaPipe Pose 33점 인덱스 (정확한 좌우 대응이 중요 — 섞이면 다른 손을 잰다):
#   0 코 · 1~6 눈 · 7~8 귀 · 9~10 입
#   11/12 어깨L/R · 13/14 팔꿈치L/R · 15/16 손목L/R
#   17/18 새끼L/R · 19/20 검지L/R · 21/22 엄지L/R   ← 0-based 짝이 붙는다
#   23/24 골반L/R · 25/26 무릎L/R · 27/28 발목L/R · 29/30 발뒤꿈치L/R
#   31/32 발끝L/R
# 2026-09-28 정밀 검토에서 이 그룹이 틀린 것이 발견돼 고쳤다. 이전 값은
# hand_left(15~20)에 **오른손** 인덱스(17~20)가 들어 있었고(hand_right의
# 부분집합이라 같은 손을 두 번 로깅), arm_right가 왼손목(15)을 포함했으며,
# 발(29~32)은 아예 없었다 → "손이 뭉개졌다" 판정이 엉뚱한 손을 보고 있었다.
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
# 복원 우선 부위 — 뉘게되기 쉽고(디테일 손실), 원본 픽셀이 신뢰할 만한 부위
DETAIL_CRITICAL = ("hand_left", "hand_right", "leg_left", "leg_right",
                   "face")


def _edge_map_from_rgb(arr) -> "object | None":
    """RGB 배열(H,W,3) → 16x16 에지 밀도 맵. 실패 시 None."""
    try:
        import numpy as _np
        import torch as _t
        import torch.nn.functional as _f
        if arr is None or getattr(arr, "ndim", 0) != 3:
            return None
        arr = _np.clip(_np.asarray(arr, dtype=_np.float32), 0.0, 1.0)
        lum = (arr[..., 0] * .299 + arr[..., 1] * .587 + arr[..., 2] * .114)
        t = _t.from_numpy(lum[None, None])
        # Sobel (cv2 없이 torch만으로)
        kx = _t.tensor([[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]])
        ky = kx.t().contiguous()
        gx = _f.conv2d(t, kx[None, None])
        gy = _f.conv2d(t, ky[None, None])
        mag = (gx * gx + gy * gy).sqrt()[0, 0].numpy()
        mx = float(mag.max())
        # 왜(Why) 임계가 절대값이면 안 되는가(2026-09-28 실측): float32
        # conv2d 수치 노이즈 바닥이 이미지 크기에 따라 1e-8 근처까지 내려가
        # **디테일이 전혀 없는** 평탄 이미지가 mx>1e-8 로 통과한다. 그러면
        # `mag/mx` 정규화 결과가 1.0 이 되어 "뭉개진 부위"가 아니라
        # "디테일 최대"로 읽힌다 → detail_boost 가 전부 반대로 동작한다.
        # 실측: 64x64 평탄 이미지 값 0.5→0.0 / 0.45→1.0 (반전).
        # 해결: 노이즈 바닥을 **입력 대비 상대값**으로 잡는다.
        # 노이즈는 입력 변동이 아니라 **상쇄 오차**다: 커널 합이 0이라
        # 수학적으로는 0 이어야 하지만 float32 반올림 오차가 값에 비례해
        # 남는다(0.45 기준 실측 3e-7 > 기존 임계 1e-8).
        _floor = 1e-5 * (float(lum.mean()) + 1e-3)
        if mx <= max(1e-8, _floor):
            # 완전 평탄 이미지: 에지가 "0"이지 "None"이 아니다. 뭉개진 이미지도
            # 여기에 해당한다. None을 돌려주면 부위 비교가 불가능해져
            # "뭉개진 부위"를 판정할 수 없게 된다(실측에서 확인).
            return _np.zeros((16, 16), dtype=_np.float32)
        mag = mag / mx
        small = _f.adaptive_avg_pool2d(_t.from_numpy(mag[None, None]), 16)
        return small[0, 0].numpy()
    except Exception:
        return None


# 2026-09-28 정밀 검토: 여기 있던 `_edge_map(latent, vae)`는 **호출이 0건**인
# 죽은 함수였다(grep 확인). 내용 자체는 `_part_detail_map`의 디코드 블록과
# 복붙 수준으로 동일했고, 그 중복이 "실행당 VAE 디코딩 4~5회"의 원인이었다.
# 제거했다. 디코딩 공유는 별건으로 `_decode_small` 하나로 모았다.
# 참조가 필요한 곳은 `panel_signature`(에지맵 직접 계산)다.


def _part_detail_map(vae, latents, cache=None) -> "dict | None":
    """landmark별 (에지 밀도, x, y) 추출. MediaPipe 없으면 None.

    반환 형태: {"sampled": {"edge": [33 floats], "xy": [(x,y) x33]}, ...}
    xy가 있어야 부위별 **공간 마스크**를 만들 수 있다 — 33점 벡터만으로는
    화면의 어느 영역을 강화할지 알 수 없다.
    """
    try:
        import mediapipe as _mp
        import numpy as _np
        import torch as _t
    except Exception:
        return None
    if vae is None or not latents:
        return None
    out = {}
    for name, lat in latents.items():
        if lat is None:
            continue
        try:
            arr = _decode_latent_rgb(vae, lat, cache=cache)
            if arr is None:
                continue
            em = _edge_map_from_rgb(arr)
            if em is None:
                continue
            u8 = (_np.clip(arr, 0, 1) * 255).astype(_np.uint8)
            pose = _mp.solutions.pose.Pose(static_image_mode=True,
                                            enable_segmentation=False,
                                            min_detection_confidence=0.3)
            try:
                res = pose.process(u8)
            finally:
                try:
                    pose.close()
                except Exception:
                    pass
            lm = getattr(res, "pose_landmarks", None)
            if not lm:
                continue
            edge = [0.0] * 33
            xy = []
            for i, p in enumerate(lm.landmark[:33]):
                xy.append((float(p.x), float(p.y)))
                cx = min(15, max(0, int(p.x * 16)))
                cy = min(15, max(0, int(p.y * 16)))
                edge[i] = float(em[cy, cx])
            out[name] = {"edge": edge, "xy": xy}
            # 여기 있던 `del img, arr` 은 **한 번도 실행된 적이 없다**.
            # img는 이 함수의 로컬이 아니라 `_decode_latent_rgb` 안의 로컬이라
            # del 이 NameError를 던지고, 바로 아래 except 가 삼켰다. 주석이
            # 주장하던 "디코드 잔재 정리"는 실제로 한 번도 일어나지 않았다.
            # Python은 함수 반환 시 로컬을 회수하므로 명시적 del 이 필요 없다.
            # 여기서는 다음 반복을 위해 참조만 끊어준다(루프 안이라 arr/em 이
            # 살아 있는 동안 GPU 텐서를 붙들지 않게).
            del em, u8
        except Exception:
            continue
    return out or None


def _apply_region_strength(base_strength, matched, sampled,
                           strength_vec, parts, mask):
    """강도 벡터(33) → 공간 마스크 → 부위별 가중 블렌드. 새 텐서를 반환한다.

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
       → "기준 강도 대비 실제로 올랐는지"로 판정한다(부호 무관).

    **한계(정확):** strength가 이미 1.0이면 `min(1.0, 1.0*1.6) = 1.0`이라
    상향 자체가 불가능하다 → region 보강이 적용되지 않는다(정상). 100%보다
    더 당길 수는 없으므로 의도한 동작이다.
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


def detail_boost(parts_ref, parts_samp, strength, boost=1.6, thresh=0.35):
    """부위별 adaptive 강도 → (강도 배열|None, 로그 문자열).

    원본이 더 살아있는(=에지 밀도가 높은) 부위만 강도를 올려 그 부위를
    원본으로 당겨온다. 원본도 뭉개진 부위는 건드리지 않는다 — 원본을
    신뢰할 수 없기 때문(원본이 틀렸으면 복원도 틀린다).

    **중요**: 이 함수는 "손가락이 5개여야 한다"를 판정하지 않는다. latent에
    텍스트는 개입하지 않는다. 산술로 하는 것은 단 하나 —
    "원본과 이 부위가 얼마나 달라졌는가"다. 원본이 정확할 때만 효과가 있다.
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
        for region, idxs in PART_REGIONS.items():
            if region not in DETAIL_CRITICAL:
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
        return None, ""
    except Exception:
        return None, ""


# ---------------------------------------------------------------------------
# 캐릭터 시트 패널 검출 (2026-09-28)
#
# 왜(Why): 사용자가 캐릭터 시트를 물리는 목적은 **신원 일관성**이다. 실사용
# 표준 구조는 정면·후면 전신 + 상부얼굴 정면·후면 + 좌우 측면(한 사람)이다.
# 이 참조를 통째로 신원 소스로 쓰면 6개 뷰의 신원 신호가 **평균**나지만,
# 그건 카메라 노드가 텍스트로는 못 막는 실패다(카메라는 시트를 한 덩어리로
# 보기 때문이다). Keeper는 픽셀로 "몇 개인지"를 세지 않는다 — 대신 시트인지
# 확인하고, 결과와 가장 잘 맞는 **패널 하나**를 고른다(상관 계산).
#
# 왜(Why) 한계 — 패널과 결과는 공간 정렬이 되어 있지 않다. 정면 전신 패널을
# 허리 위 반신샷으로 끌어오면 위치가 안 맞아 오히려 나빠진다. 그래서 **프레이밍
# 유사도(인물 bbox 종횡비·상대 크기)**를 재서, 맞을 때만 그 패널을 신원
# 소스로 쓸 수 있게 한다. 이것도 추측이 아니라 산술이다.
#
# 단계(2026-09-28): 1단계는 **검출 + 게이트 + 로그만**. 강도 변경은 하지
# 않는다 — 콘솔로 실제 패널 수와 게이트 값을 확인한 뒤 2단계에서 반영한다.
# (왜 조용히 바꾸지 않는가: 잘못 감지했을 때 조용히 신원 복원이 약해지면
#  원인을 알 수 없다. 경고와 로그가 전부다.)
# ---------------------------------------------------------------------------

# 패널 내 문자(성공) / 패널 사이 공백(실패)의 상대 임계값. 시트는 콘텐츠가
# 조밀하고 사이가 비어 있는 배치를 갖는다.
_PANEL_ON_RATIO = 0.30
# 하나의 패널로 인정할 최소 너비 비율. 너무 좁은 띠(테두리, 텍스트)는 제외.
_PANEL_MIN_W_RATIO = 0.04


def column_profile(arr) -> "object | None":
    """RGB 배열 → 열별 "평탄하지 않은 정도" 프로파일 (W,). 실패 시 None.

    왜(Why) 에지맵(16x16)이 아니라 **전 해상도**인가: 실사용 시트는 6뷰를
    일자로 늘어놓는데, 16x16으로 줄이면 패널 하나가 2~3칸에 불과해 세 개만
    잡히는 문제가 실제로 발생했다(합성 시트에서 검출됨). 패널 경계는 원본
    해상도에서만 의미가 있다.
    프로파일 = 각 열의 표준편차. 패널 사이 빈 공간은 균일(STD≈0)이고,
    실루엣이 있는 패널 열은 값이 크다. 그래서 "평탄하지 않은 연속 구간"이
    곧 패널이다.
    """
    try:
        import numpy as _np
        if arr is None or getattr(arr, "ndim", 0) != 3:
            return None
        a = _np.clip(_np.asarray(arr, dtype=_np.float32), 0.0, 1.0)
        if a.shape[0] < 2 or a.shape[1] < 8:
            return None
        lum = (a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114)
        return lum.std(axis=0).astype(_np.float32)
    except Exception:
        return None


def _panels_from_profile(profile, width: int, on_ratio: float = _PANEL_ON_RATIO,
                         min_w_ratio: float = _PANEL_MIN_W_RATIO) -> list:
    """열 프로파일 → 연속 콘텐츠 구간 [(x0, x1), ...]."""
    try:
        import numpy as _np
        p = _np.asarray(profile, dtype=_np.float32)
        if p.ndim != 1 or p.size < 8:
            return []
        peak = float(p.max())
        if peak <= 1e-6:
            return []                               # 전부 평탄 → 시트 아님
        on = p >= peak * on_ratio
        min_w = max(1, int(round(width * min_w_ratio)))
        panels = []
        start = None
        for i, v in enumerate(on):
            if v and start is None:
                start = i
            elif not v and start is not None:
                if i - start >= min_w:
                    panels.append((start, i))
                start = None
        if start is not None and len(on) - start >= min_w:
            panels.append((start, len(on)))
        return panels
    except Exception:
        return []


# 시트 판별 정규성 임계값. 왜(Why) 실측 보정값이다.
#   합성 시트(6·4패널): 폭비 1.00 / 간격비 1.00
#   실사용 사진들      : 폭비 1.55~6.48 / 간격비 0.34~1.00
# 즉 "패널이 3개 이상 + 폭이 고르게 + 간격이 고르게"가 시트를 가르는 신호다.
# 왜(Why) 이렇게 빡빡한가: 시트로 잘못 판정하면 6개 뷰를 6명 신원으로
# 평균내어 **신원 일관성이 오히려 망가진다.** 오탐이 누락보다 훨씬 위험하다.
SHEET_MIN_PANELS = 3
SHEET_MAX_WIDTH_RATIO = 1.60
SHEET_MIN_SPACING_RATIO = 0.60


def looks_like_sheet(panels) -> dict:
    """패널 구간이 시트인지 판정. {"sheet": bool, "n": int, "wreg": float,
    "greg": float}. 패널이 2개 이하는 시트로 보지 않는다.

    왜(Why) 2개는 왜(Why) 기준이 엄격한가: 방 2개·두 손·두 피사체가 있는
    사진은 흔하다. 실사용 표준 시트는 6뷰(정면·후면·상부얼굴 4)라 3개 이상
    정규 배치로 시작한다.
    """
    out = {"sheet": False, "n": len(panels or []), "wreg": 0.0, "greg": 0.0}
    try:
        pn = panels or []
        out["n"] = len(pn)
        if len(pn) < SHEET_MIN_PANELS:
            return out
        ws = [max(1, x1 - x0) for x0, x1 in pn]
        cs = [(x0 + x1) / 2.0 for x0, x1 in pn]
        gaps = [cs[i + 1] - cs[i] for i in range(len(cs) - 1)]
        wreg = max(ws) / min(ws)
        greg = (min(gaps) / max(gaps)) if gaps and max(gaps) > 0 else 0.0
        out["wreg"] = round(wreg, 2)
        out["greg"] = round(greg, 2)
        out["sheet"] = (wreg <= SHEET_MAX_WIDTH_RATIO
                        and greg >= SHEET_MIN_SPACING_RATIO)
        return out
    except Exception:
        return out


def detect_panels(arr) -> list:
    """RGB 배열 → 세로 패널 구간 [(x0, x1), ...]. 시트가 아니면 [].

    왜(Why) 열 방향만 보는가: 실사용 표준 시트는 정면·후면·측면을 **일자로**
    늘어놓은 형태다(사용자 실사용 구조). 2개 이상 콘텐츠 구간이 나오면 시트로
    본다. 세로로 쌓인 시트는 이번 단계에서 다루지 않는다(미검출 시 조용히
    기존 동작 — 오탐보다 누락이 안전하다).
    """
    prof = column_profile(arr)
    if prof is None:
        return []
    return _panels_from_profile(prof, len(prof))


def panel_signature(arr, x0: int, x1: int) -> "object | None":
    """패널 구간의 에지 시그니처(정규화 8-bin 히스토그램). 비교용.

    왜(Why) 실루엣 경계를 잘라내고 내부만 보는가(2026-09-29 실측):
    원래 16x16 축소 에지맵(`_edge_map_from_rgb`)에 정규화 히스토그램을 얹었는데
    두 가지가 겹쳐 **모든 패널의 시그니처가 정확히 같아졌다**.

    ① 16x16 축소가 패널 내부 구조를 평균으로 지웠다. 줄무늬 간격을 5/40/16/9로
       갈라 만든 4개 패널이 전부 [0.984, 0.008, 0.008, 0...] 로 같았다.
    ② `mag / mx` 정규화가 문제였다. mx는 실루엣 경계의 최대 기울기인데 패널마다
       거의 동률이라, 정규화 후 **가장 강한 에지 하나가 항상 1.0** 이 되고
       나머지는 0으로 뭉개진다 → 히스토그램이 [1, 0, 0, ...] 로 붕괴.

    그래서 (a) 원본 해상도에서 Sobel을 직접 내고 (b) 실루엣 외곽 한 칸을
    잘라내 **내부 텍스처**만 본다. 패널 검출은 별도 함수(`column_profile`,
    전 해상도 열 프로파일)가 이미 담당하므로 축소를 다시 할 이유가 없다.
    """
    try:
        import numpy as _np
        import torch as _t
        import torch.nn.functional as _f
        a = _np.asarray(arr, dtype=_np.float32)
        if a.ndim != 3:
            return None
        w = a.shape[1]
        x0 = max(0, int(x0))
        x1 = min(w, int(x1))
        if x1 - x0 < 6:
            return None
        # 실루엣 외곽 1픽셀(패널 경계 = 가장 큰 기울기)을 제외한다.
        seg = _np.clip(a[:, x0 + 1:x1 - 1], 0.0, 1.0)
        if seg.shape[1] < 4 or seg.shape[0] < 4:
            return None
        lum = seg[..., 0] * .299 + seg[..., 1] * .587 + seg[..., 2] * .114
        t = _t.from_numpy(lum[None, None])
        kx = _t.tensor([[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]])
        ky = kx.t().contiguous()
        gx = _f.conv2d(t, kx[None, None])
        gy = _f.conv2d(t, ky[None, None])
        mag = (gx * gx + gy * gy).sqrt()[0, 0].numpy()
        if mag.size == 0:
            return None
        # mx 정규화는 버린다 — 내부 텍스처의 **분포**가 시그니처이므로
        # 자체 정규화(총합 1)만 하면 크기 차이와 무관해진다.
        mean = float(mag.mean())
        if mean <= max(1e-8, 1e-5 * (float(lum.mean()) + 1e-3)):
            return None                              # 평탄 패널 → 근거 없음
        # 로그 압축: 강한 에지 하나가 전체를 지배하지 않게 한다.
        em = _np.log1p(mag / mean).astype(_np.float32)
        # 시그니처는 **텍스처 밀도**를 본다. 히스토그램 총합 1 정규화는
        # "평탄한 픽셀이 몇 개인가"를 지워버려, 배경이 넓은 샘플과 배경이 좁은
        # 패널을 비교하면 밀도가 **반대로** 읽힌다(실측: 조밀한 줄무늬 샘플이
        # 성긴 패널에 더 높게 매칭됨). 그러므로 상위 절반만 잘라 **에지가 있는
        # 픽셀의 분포**만 남긴다. 그 분포 자체는 총합 1 정규화로 크기 무관하다.
        cut = _np.percentile(em, 60.0)
        em = _np.where(em > cut, em, 0.0)
        peak = float(em.max())
        if peak <= 1e-6:
            return None
        em = em / peak
        hist, _ = _np.histogram(em, bins=8, range=(0.0, 1.0), density=False)
        tot = float(hist.sum())
        if tot <= 1e-6:
            return None
        return hist / tot
    except Exception:
        return None


def signature_similarity(a, b) -> float:
    """두 시그니처의 코사인 유사도 0~1. 비교 불가면 0.0."""
    try:
        import numpy as _np
        if a is None or b is None:
            return 0.0
        va = _np.asarray(a, dtype=_np.float32).ravel()
        vb = _np.asarray(b, dtype=_np.float32).ravel()
        if va.size == 0 or va.size != vb.size:
            return 0.0
        na = float(_np.linalg.norm(va))
        nb = float(_np.linalg.norm(vb))
        if na <= 1e-8 or nb <= 1e-8:
            return 0.0
        return max(0.0, min(1.0, float(_np.dot(va, vb) / (na * nb))))
    except Exception:
        return 0.0


def subject_bbox(landmarks):
    """MediaPipe pose landmark → 인물 bbox (x0, y0, x1, y1) 정규화. 실패 None.

    왜(Why) bbox를 쓰는가: "패널이 결과와 맞는지"를 재려면 각 뷰 안에서
    인물이 차지하는 **프레이밍**을 비교해야 한다. 세그멘테이션이 없어도
    랜드마크 33점의 외곽으로 재는 것이면 충분하다.

    왜(Why) w, h 인자를 뺐나:landmark 좌표는 이미 **정규화(0~1)** 라서
    픽셀 크기가 필요 없다. 받던 인자는 `w < 1` 가드에만 쓰였고 실제로는
    `box_s`에 ref_arr의 너비를 넘기는 실수도 있었다(의도 뒤섞임).
    """
    try:
        import numpy as _np
        if landmarks is None:
            return None
        xs, ys = [], []
        for lm in landmarks:
            x = getattr(lm, "x", None)
            y = getattr(lm, "y", None)
            if x is None or y is None:
                continue
            if float(x) <= 0.0 or float(y) <= 0.0:
                continue
            xs.append(float(x))
            ys.append(float(y))
        if len(xs) < 8:
            return None
        arr = _np.asarray([xs, ys], dtype=_np.float32)
        # 머리 위쪽(0.02)·발 아래쪽(1.02)로 약간 여유 → 어깨만 나온 뷰가
        # 극단적으로 작아지는 것을 방지.
        x0 = max(0.0, float(arr[0].min()) - 0.02)
        x1 = min(1.0, float(arr[0].max()) + 0.02)
        y0 = max(0.0, float(arr[1].min()) - 0.02)
        y1 = min(1.0, float(arr[1].max()) + 0.02)
        if x1 - x0 < 0.02 or y1 - y0 < 0.02:
            return None
        return (x0, y0, x1, y1)
    except Exception:
        return None


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
        return max(0.0, min(1.0, 0.5 * ar_sim + 0.5 * h_sim))
    except Exception:
        return 0.0


# 이 값부터는 해당 패널을 신원 소스로 쓸 수 있다(2단계에서 강도 적용에 사용).
FRAMING_GATE = 0.60


def _decode_small(vae, latent, scale: float = 0.5):
    """latent → 축소 해상도 RGB numpy 배열(H,W,3). 실패 시 None.

    왜(Why) 기본 0.5인가: 패널 구조는 가로 해상도가 있어야 보인다(1/4로
    줄이면 6패널 시트의 패널 폭이 몇 픽셀까지 줄어 판별이 무너진다).
    샘플러 결과는 MediaPipe 랜드마크만 쓰므로 더 작아도 된다 → 호출부가 0.25.
    """
    try:
        import torch as _t
        import numpy as _np
        if vae is None or latent is None:
            return None
        import torch.nn.functional as _f
        s = float(scale)
        if not (0.05 <= s <= 1.0):
            return None
        with _t.no_grad():
            small = (_f.interpolate(latent.float(), scale_factor=s, mode="area")
                     if s < 1.0 else latent.float())
            img = vae.decode(small)
        if hasattr(img, "detach"):
            img = img.detach().cpu()
        arr = img.numpy() if hasattr(img, "numpy") else _np.asarray(img)
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.ndim == 4:
            arr = arr[0]
        if arr.ndim != 3:
            return None
        return _np.clip(arr, 0.0, 1.0)
    except Exception:
        return None


def _pose_landmarks(img_arr):
    """RGB 배열 → MediaPipe pose landmarks 리스트. 미설치/미검출 시 None."""
    try:
        import mediapipe as _mp
        import numpy as _np
        if img_arr is None:
            return None
        h, w = img_arr.shape[0], img_arr.shape[1]
        u8 = (_np.asarray(img_arr, dtype=_np.float32) * 255.0).astype(_np.uint8)
        pose = _mp.solutions.pose.Pose(static_image_mode=True,
                                       enable_segmentation=False,
                                       min_detection_confidence=0.5)
        try:
            res = pose.process(u8)
        finally:
            try:
                pose.close()
            except Exception:
                pass
        return getattr(res, "pose_landmarks", None)
    except Exception:
        return None


def analyze_reference_sheet(vae, ref_latent, sampled) -> dict:
    """원본 참조가 캐릭터 시트인지 확인하고, 결과와 가장 잘 맞는 패널을 고른다.

    반환: {"panels", "raw", "sheet", "best", "match", "framing", "gate",
           "box"}. 판정 불가 시 panels=0.
    """
    out = {"panels": 0, "raw": 0, "sheet": False, "best": None, "match": 0.0,
           "framing": 0.0, "gate": False, "box": None, "wreg": 0.0, "greg": 0.0}
    try:
        ref_arr = _decode_small(vae, ref_latent, 0.5)
        if ref_arr is None:
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
        # 2) 프레이밍 게이트: 고른 패널의 인물 비율이 결과와 맞는지
        if best is not None:
            x0, x1 = panels[best]
            lm_ref = _pose_landmarks(ref_arr[:, x0:x1])
            lm_s = _pose_landmarks(samp_arr)
            box_ref = subject_bbox(lm_ref)
            box_s = subject_bbox(lm_s)
            out["box"] = box_ref
            out["framing"] = round(framing_similarity(box_ref, box_s), 3)
            out["gate"] = out["framing"] >= FRAMING_GATE
        _release_vram()
    except Exception:
        _release_vram()
    return out


def _log_sheet_analysis(info: dict, ref_name: str) -> None:
    """시트 분석 결과 로그. 동작 변경은 하지 않는다(1단계)."""
    try:
        if not info:
            return
        if not info.get("sheet"):
            # 콘텐츠 구간이 있어도 정규성이 모자라면 시트가 아니다. 조용히
            # 넘기되 판정 수치를 남긴다 — 임계값 조정이 필요할 수 있으므로.
            if info.get("raw", 0) >= SHEET_MIN_PANELS:
                _log(f"[GoRi Consistency Keeper] {ref_name} 참조에 콘텐츠 "
                     f"구간 {info['raw']}개가 있으나 정규성 미달 — 시트로 보지 "
                     f"않습니다 (폭비 {info.get('wreg', 0):.2f} ≤ "
                     f"{SHEET_MAX_WIDTH_RATIO}, 간격비 {info.get('greg', 0):.2f} "
                     f"≥ {SHEET_MIN_SPACING_RATIO} 필요)")
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
                 f"판정 불가 (mediapipe 미설치 또는 검출 실패). 강도 변경 없음")
        elif info.get("gate"):
            _log(f"[GoRi Consistency Keeper]   프레이밍 유사도 "
                 f"{info['framing']:.2f} — 픽셀이 대응하므로 이 뷰를 "
                 f"신원 소스로 쓸 수 있습니다")
        else:
            _log(f"[GoRi Consistency Keeper] ⚠ 프레이밍 불일치 "
                 f"({info['framing']:.2f} < {FRAMING_GATE:.2f}) — 이 뷰는 "
                 f"결과와 위치가 대응하지 않아 신원 소스로 쓰지 않습니다. "
                 f"시트 각도를 결과 각도에 맞추면 더 정확해집니다")
    except Exception:
        pass


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


def _release_vram() -> None:
    """GPU 조각 반납. 마스크용 VAE 디코드 잔재 정리 (실패 무시).

    왜(Why) MPS도 같이 비우는가: macOS(M1/M2/M3)는 CUDA가 아니라 MPS 메모리
    파서를 쓴다. cuda만 비우면 맥에서는 아무것도 하지 않으므로, 이 노드가
    디코드한 잔재가 통합 캐시에 남는다. hasattr 가드로 없는 환경도 안전.
    """
    try:
        import gc as _gc
        _gc.collect()
        try:
            import torch as _t
            if hasattr(_t, "cuda") and _t.cuda.is_available():
                _t.cuda.empty_cache()
            mps = getattr(_t, "mps", None)
            if mps is not None and hasattr(mps, "empty_cache"):
                try:
                    if mps.is_available():
                        mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass


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
                "strength_camera": ("FLOAT", {"default": 0.2, "min": -1.0,
                                              "max": 1.0, "step": 0.05}),
                "strength_original": ("FLOAT", {"default": 0.2, "min": -1.0,
                                               "max": 1.0, "step": 0.05}),
            },
            "optional": {
                "original_latent": ("LATENT",),
                "camera_latent": ("LATENT",),
                "vae": ("VAE",),
            },
        }

    def run(self, sampled_latent, strength_camera=0.2, strength_original=0.2,
            original_latent=None, camera_latent=None, vae=None):
        sampled = _get_samples(sampled_latent)
        if sampled is None:
            raise ValueError("(GoRi) Consistency Keeper: sampled_latent이 비어 있음")
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
        if not (a or b) or (_orig_ref is None and _cam_ref is None):
            _release_vram()
            return ({"samples": out},)
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
            _log(f"[GoRi Consistency Keeper] ⚠ 배치 — 전역 당김만 적용합니다 (인체 마스크·부위별 복원은 단일 이미지 전용입니다)")
        # 실행당 디코드 캐시: sampled 를 전 해상도로 두 번 디코딩하던 것을
        # 한 번으로 줄인다 (2026-09-28 실측: 128² latent → 1024² 2회).
        _dcache = {}
        _mask = None if _multi else _person_mask_for_latent(
            vae, sampled, cache=_dcache)
        # 부위별 디테일 손실 감지: 원본 latent는 1회만 디코딩해 재사용한다.
        # 왜(Why): sampled/original을 매번 디코딩하면 VAE 비용이 2배다.
        _pm = None
        if vae is not None and b and not _multi:
            _pm = _part_detail_map(vae, {
                "sampled": sampled,
                "original": _orig_ref,
            }, cache=_dcache)
        # 캐릭터 시트 참조 분석 (1단계: 검출 + 프레이밍 게이트 + 로그만).
        # 왜(Why) 여기를 넣는가: 사용자가 시트를 물리는 목적은 신원 일관성인데,
        # 시트의 6개 뷰를 통째로 끌어오면 신원 신호가 평균나고 그것은 카메라
        # 노드가 텍스트로 못 막는 실패다. 강도는 아직 바꾸지 않고 **판정만**
        # 노출한다(실측 콘솔로 확인 후 2단계에서 반영).
        if vae is not None and b and not _multi and _orig_ref is not None:
            _log_sheet_analysis(analyze_reference_sheet(
                vae, _orig_ref, sampled), "original")
        for name, ref_latent, strength in (
                ("camera", camera_latent, a),
                ("original", original_latent, b)):
            if not strength:
                continue
            ref = _get_samples(ref_latent)
            if ref is None:
                _log(f"[GoRi Consistency Keeper] {name} 기준 없음 — 건너뜀")
                continue
            matched = _match_spatial(ref, sampled)
            if matched is None:
                _log(f"[GoRi Consistency Keeper] {name} 배치·채널 불일치 — 건너뜀")
                continue
            drift = _drift_mse(sampled, matched)
            eff = strength
            if drift is not None:
                _log(f"[GoRi Consistency Keeper] {name} 틀어짐 MSE={drift:.6f} "
                     f"당김 {strength:.2f}")
            # nan 은 모든 비교가 False 라 `> 0.8` 도 통과해 감쇠를
            # 건너뛴다 → 이후 0*(matched-sampled) 로 nan 이 전파된다.
            # `not (x <= 0.8)` 은 nan 에서 True 가 된다(2026-09-28).
            if drift is not None and not (drift <= 0.8):
                eff = strength * _damp_factor(drift)

                _log(f"[GoRi Consistency Keeper] ⚠ {name} 기준과 결과물 구도가 많이 "

                f"다름 — 당김 자동 감쇠 {strength:.2f}→{eff:.2f}. "

                f"같은 구도 기준 사용 권장")

            mismatch = _lighting_mismatch(sampled, matched)
            if mismatch is not None and not (mismatch <= 1.0):
                _old_eff = eff
                eff = eff * _light_damp_factor(mismatch)
                _log(f"[GoRi Consistency Keeper] ⚠ {name} 조명 흐름 불일치 "
                     f"({mismatch:.2f}) — 당김 추가 감쇠 {_old_eff:.2f}→{eff:.2f}")
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
                _darr, _regions = detail_boost(_pm, _pm, eff)
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
        _release_vram()
        return ({"samples": out},)
