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

import importlib as _importlib


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
    """ref를 target의 (N, C, H, W) 중 공간 크기에 맞춘다. 실패 시 None.

    왜(Why) 크기가 같아도 device/dtype 을 확인하나 (2026-10-01 실측):
    크기가 같으면 `return ref` 로 바로 돌려주고 있었는데, 그 `ref` 는 워크플로에서
    넘어온 latent 라 **target 과 다른 장치에 있을 수 있다.** 실제로 하네스로
    처음 끝까지 돌렸을 때 여기서 죽었다 — 텐서 장치가 둘로 섞여 있다는
    RuntimeError 가 `out + eff * _mask * (matched - sampled)` 에서 났다.
    (에러 문구를 그대로 적지 않는다. 아래 테스트가 소스의 하드코딩된 디바이스
    문자열을 금지한다 — 이 노드는 어떤 장치에서도 돌아야 하기 때문.)

    이 버그는 v1.7.0 부터 있었으나 판정층 작업 전까지 이 노드가 끝까지
    실행된 적이 없어 드러나지 않았다. **조용히 못 도는 것과 죽는 것은
    둘 다 실패**이고, 죽는 쪽이 찾기 쉬워서 그나마 다행이었다.

    이미 device 와 dtype 이 같으면 아무것도 옮기지 않는다(무조건 `.to()` 를
    걸면 매 호출마다 복사가 생긴다).
    """
    try:
        import torch.nn.functional as _f
        if tuple(ref.shape) == tuple(target.shape):
            if (ref.device == target.device and ref.dtype == target.dtype):
                return ref
            return ref.to(device=target.device, dtype=target.dtype)
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


def _drift_norm(sampled, matched) -> float | None:
    """두 latent 를 **참조 크기 기준**으로 정규화한 불일치. 비교 불가면 None.

    왜(Why) MSE 를 그대로 쓰면 안 되는가 (2026-10-01 실측):
    `MSE(sampled, matched)` 는 **절대값**이라 latent 스케일에 비례한다.
    그런데 0.8 / 2.0 이라는 임계값은 SD 계열에서 잡은 값이고, Qwen Image
    2.1 (int8) 로 바꿔진 뒤 한 번도 재측정되지 않았다. 실측으로 드러난 사실:

        이전 실행   camera 5.72   original 14.33   → 둘 다 감쇠 0.00
        이번 실행   camera 5.198  original 14.217  → 둘 다 감쇠 0.00

    즉 이 워크플로의 **전형적인 값이 임계값보다 한 자릿수 크다.** 감쇠가 전부
    0 이 되어 노드가 무조건 아무것도 하지 않게 되어 있었다.

    게다가 `original` 의 불일치가 `camera` 보다 **더 컸다.** 같은 사람인데
    원본이 카메라에서 더 멀다면, 두 latent 의 스케일이 다르다는 뜻이다 —
    이미지가 실제로 다른 게 아니라 **단위가 다른 것.**

    그래서 크기로 나눈다. `matched` 의 평균제곱값으로 나누면 "얼마나 다른가"가
    "참조의 크기 대비 얼마나 다른가" 가 되고, 모델이 바뀌어도 임계값이 유지된다.
    0 = 완전히 같음, 1 = 참조 크기만큼 다름.

    **아직 임계값은 이 값으로 재측정되지 않았다.** 아래 실행 로그가 그 값을
    직접 말해준다. 그 실측값을 보고 임계값을 정한다 — 지금 숫자를 넣으면
    또 추측이 된다.
    """
    try:
        import torch as _t
        den = float(_t.mean(matched.float() ** 2).item())
        if den <= 1e-12:
            return None
        return float(_t.mean((sampled.float() - matched.float()) ** 2).item()) / den
    except Exception:
        return None


# --- 정규화 불일치 기준 (2026-10-01 실측) ---
# 왜(Why) 절대 MSE 를 안 쓰는가: MSE 는 latent 스케일에 비례하는 **절대값**이라
# 모델을 바꾸면 기준이 통째로 무효가 된다. 여기선 그 사고가 실제로 났다 —
# 0.8 / 2.0 은 SD 계열에서 잡은 값인데 Qwen Image 2.1 에서 정상 참조 4건이
# 4.227 ~ 8.384 로 측정됐다. 전부 2.0 위라 **정상 참조가 전부 0 으로 죽었다.**
# 정규화값은 스케일 무관해서 기준이 모델을 넘어간다.
#
# 기준을 정한 근거 (2026-10-01 실측 4건):
#   camera    0.2221 / 0.2585 / 0.3148 / 0.3932
#   original  0.2323 / 0.2759 / 0.4322 / 0.4872
#   → 정상 참조의 범위 0.222 ~ 0.487
#
# 감쇠는 **비정상**을 위한 장치다. 정상이면 건드리면 안 되므로 무감쇠 구간이
# 정상 범위를 **덮어야** 한다. 그래서 무감쇠 끝을 측정 최댓값(0.487) 바로 위인
# 0.50 으로 잡았다. 0 에 도달하는 지점은 측정 최댓값의 2 배로 두었다.
_DRIFT_NORM_KNEE = 0.50
# 물리 상한: 당김 강도가 이 값을 넘으면 결과의 에지 밀도가 **원본보다 낮아진다**.
# 근거는 WORK_STATUS 10-28 의 실측. 이미지 1장·시드 1개 기준이라잪정.
_PHYS_CEILING = 0.78
_DRIFT_NORM_ZERO = 1.00

_DRIFT_NORM_NOTED = False


def _damp_norm(v) -> float:
    """정규화 불일치 -> 감쇠 계수 0~1. 비교 불가면 1.0(안 건드림).

    왜(Why) `_damp_factor`(절대 MSE) 대신 별개 함수인가: 기존 함수는 그대로
    둔다. 새 기준을 켜도 예전 경로를 잃지 않고, **두 규칙이 각각 무슨 뜻인지**
    로그와 테스트에서 구분된다. 계층적으로도 "정규화 기준" 과 "구 기준" 이
    같은 이름 아래 섞이면 나중에 어느 쪽이 살아 있는지 알 수 없다.
    """
    try:
        if v is None:
            return 1.0
        if v != v:                      # nan 은 전파 차단이 우선 (R71 계약)
            return 0.0
        if v <= _DRIFT_NORM_KNEE:
            return 1.0
        span = _DRIFT_NORM_ZERO - _DRIFT_NORM_KNEE
        if span <= 0:
            return 1.0
        return max(0.0, 1.0 - (v - _DRIFT_NORM_KNEE) / span)
    except Exception:
        return 1.0


def _damp_factor(drift) -> float:
    """틀어짐 기반 자동 감쇠. 작으면 1, 크면 0으로 수렴.

    왜(Why): "융합하되 변형 없이" — 당기면 깨질 구도면 노드가 스스로
    손을 놓는다. 0.8부터 선형 감쇠, 2.0에서 0.

    **바닥을 두지 않는다 — 의도적으로.**
    처음엔 "감쇠가 0 이 되면 뒤 경로가 전부 죽는다" 고 보고 바닥(0.25)을
    넣었다. 그러자 기존 테스트 셋이 깨졌다:

        자동 감쇠 계수
        큰 틀어짐은 당김 감쇠
        감쇠로 eff=0 이면 region 당김도 0 (감쇠 우회 방지)

    세 번째가 핵심이다. **eff 가 0 이면 region 경로도 0 이어야 한다** 는
    계약이고, 그게 없는 순간 사용자가 강도를 올려 region 경로로 감쇠를
    우회할 수 있다. 그러면 "틀어지면 손을 놓는다" 는 노드의 목적이 무너진다.

    즉 바닥은 "조용한 무동작" 을 고치는 것처럼 보이지만 실제로는
    **안전장치를 뚫는 것**이었다. 문제는 바닥이 아니라 임계값이다 —
    위 `_drift_norm` docstring 의 실측값으로 다시 잡는다.
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


def _as_rgb_hwc(arr):
    """VAE decode 결과 -> (H,W,3) RGB. 레이아웃이 아니면 None.

    왜(Why) 이렇게 복잡하나 (2026-09-30 실측): ComfyUI 의 VAE 마다 decode 가
    주는 축 순서가 다르다. 여기서 쓰는 Qwen Image VAE 는 **(B,H,W,C=4)** 다 —
    arr[0] = (1888,1056,4). 그레이스케일 SD 계열은 (B,C,H,W) 라 arr[0] =
    (3,H,W) 다. 더 중요한 건 **채널이 4개** 라는 점이다. mediapipe.Image 는
    3채널 SRGB 만 받으므로 4채널을 그대로 넘기면 포즈 검출이 조용히 전부
    실패한다(실측 lm=None). 판정 근거는 첫 축이 4 이하라는 것(채널 축이면
    1/3/4, 공간 축이면 수백~).
    """
    try:
        import numpy as _np
        a = _np.asarray(arr, dtype=_np.float32)
        if a.ndim == 4:
            a = a[0]
        if a.ndim != 3:
            return None
        if a.shape[0] <= 4:
            a = _np.transpose(a, (1, 2, 0))
        if a.shape[-1] < 3:
            return None
        return _np.clip(a[..., :3], 0.0, 1.0)
    except Exception:
        return None


# VAE 가 latent 1칸을 몇 픽셀 이미지로 복원하는지 못 알아낼 때의 임시값.
# **8 은 SD 계열 기준이고 Qwen 은 16 이다.** 실패했을 때만 쓰는 안전망이며
# 정상 경로에서는 쓰이지 않는다.
_VAE_PIXEL_FACTOR_FALLBACK = 8


# VAE 의 "latent 1칸 = 이미지 몇 픽셀" 을 **클래스별로** 기억한다.
# **프로브로 재지 않는다** — 2026-10-01 실측으로 프로브는 사치다:
# 6.9GB 모델이 VRAM 에 오른 상태에서 128/256/512 인코딩을 시도하면 ms 가
# 아니라 초 단위가 걸렸고, 그 여파로 하네스 폴링이 타임아웃났다.
# 실제 디코드를 **이미 하고 있으니** 거기서 비율을 읽으면 공짜다.
_VAE_PIXEL_FACTOR_FALLBACK = 8
_VAE_FACTOR_BY_CLASS = {}


def _vae_factor_key(vae):
    """VAE 를 구조적으로 구분하는 키.

    왜(Why) VAE 클래스로 잡는가 (2026-10-01 실측): 처음엔 모듈 전역 하나로
    저장했다가 테스트가 오염되었고, production 도 같은 이유로 위험했다 —
    **한 세션에서 VAE 가 여러 개 로드된다.** 실제로 이 워크플로는 `WanVAE`
    와 `QwenImage21` 를 함께 쓴다. 전역 하나로 두면 한쪽에서 배운 배율이
    다른 쪽에 그대로 적용되어 조용히 틀린다.

    왜(Why) `id()` 가 아니라 클래스인가: `id()` 는 주소 재사용 때문에 위험하다
    (Jev 게이트가 명시적으로 금지). 그리고 배율은 **아키텍처의 속성**이므로
    같은 클래스면 같은 배율이다 — 이건 성질이지 우연이 아니다.
    """
    t = type(vae)
    return (getattr(t, "__module__", ""),
            getattr(t, "__qualname__", None) or getattr(t, "__name__", "?"))


def _vae_pixel_factor_for(vae) -> int:
    """이 VAE 에서 배운 배율. 배운 적 없으면 안전망."""
    if vae is None:
        return _VAE_PIXEL_FACTOR_FALLBACK
    try:
        return _VAE_FACTOR_BY_CLASS.get(_vae_factor_key(vae),
                                        _VAE_PIXEL_FACTOR_FALLBACK)
    except Exception:
        return _VAE_PIXEL_FACTOR_FALLBACK


def _vae_pixel_factor_learn(vae, latent, decoded) -> int:
    """디코드 결과로 축소 비율을 **배운다**. 배운 값을 돌려준다.

    왜(Why) 별도 프로브가 아닌가: 위 주석 — 프로브는 비싸고, 디코드는 이미
    하고 있다. `decoded` 의 높이가 latent 높이의 몇 배인지만 보면 끝이다.

    왜(Why) 실패해도 조용히 두는가: 처음엔 안전망을 쓴다. 그건 지금과 **같은**
    동작이므로 새로 나빠지는 것이 아니다. 첫 디코드 뒤부터 정확해진다.
    배율은 최적화 파라미터라 틀어도 **결과물의 정확성**을 해치지 않고 속도만
    달라진다.
    """
    try:
        if vae is None or latent is None or decoded is None:
            return _vae_pixel_factor_for(vae)
        lh = int(latent.shape[-2])
        ih = int(getattr(decoded, "shape", [-1, -1, -1, -1])[-2])
        if lh > 0 and ih > 0 and ih % lh == 0:
            f = ih // lh
            if 1 <= f <= 64:
                _VAE_FACTOR_BY_CLASS[_vae_factor_key(vae)] = f
    except Exception:
        pass
    return _vae_pixel_factor_for(vae)


def _encode_image_ref(vae, image):
    """IMAGE 텐서 -> 원본 기준 latent. 실패하면 None.

    왜(Why) 이 함수가 필요한가 (2026-10-01 실측으로 확정):
    `TextEncodeQwenImage21` 의 `latent` 출력은 **전부 0 인 빈 캔버스**다
    (`comfy_extras/nodes_qwen.py:181`). Qwen Edit 에는 "원본 latent" 라는
    개념이 없고, 원본은 `positive`/`negative` 컨디셔닝 안의
    `reference_latents` 로 들어간다(같은 파일 179행).

    즉 워크플로가 Latent 형식으로 넘겨주는 원본에는 **내용이 없다.** 그 상태로
    `MSE(생성결과, 전부 0)` 을 계산했으므로 로그에
    `original 틀어짐 MSE=14.06` 처럼 나오던 숫자는 **무의미했다.**
    게다가 정규화 값이 분모 0 으로 `n/a` 였는데, 그것이 결정적 단서였다.

    → 원본을 **이미지**로 받고 여기서 직접 인코딩한다. 이 노드는 이미 latent 를
    디코드하므로 vae 를 갖고 있고, 대칭적으로 인코딩도 할 수 있다.

    why(why): we do not resize. measured 2026-10-01: resizing to the sampled
    grid needs a factor we do not know on the first pass (fallback 8, Qwen is
    16) and produced an invalid 416x632 -> 'Calculated padded input size per
    channel: (1 x 625)'. The workflow already hands us the original resized to
    the canvas, so encoding as-is lets the VAE pick the grid. That removes the
    need to know the factor and removes the wrong-size path entirely.

    왜(Why) ComfyUI 의 VAEEncode 와 같은 순서인가: `movedim(-1, 1)` 로
    (B,H,W,C) 를 (B,C,H,W) 로 옮기고 앞 3채널만 쓴다. ComfyUI 고유 규약이라
    순서를 바꾸면 VAE 가 조용히 이상한 값을 낸다.

    크기가 비교 기준과 다르면 `_match_spatial` 이 보간으로 맞춰 준다. 그러면
    기준 자체가 리샘플된 값이 되어 "얼마나 다른가" 에 리샘플 차이가 섞이지만,
    **배율을 모른 채로 틀린 크기로 인코딩하는 것**(실측: 1x625 오류)보다
    확실히 낫다. 이 절차를 되돌리지 말 것.
    """
    if vae is None or image is None:
        return None
    try:
        import torch as _t
        # 왜(Why) 전치하지 않는가 (2026-10-01 실측): ComfyUI 의 `VAE.encode` 는
        # **(B,H,W,C) 를 받는다.** 내부에서 크롭을 하고 나서 전치한다:
        #     def encode(self, pixel_samples):        # ← (B,H,W,C)
        #         pixel_samples = self.vae_encode_crop_pixels(pixel_samples)
        #         pixel_samples = pixel_samples.movedim(-1, 1)     # 여기서 전치
        # 원래 `VAEEncode` 노드도 `vae.encode(pixels[:, :, :, :3])` 로 그대로
        # 넘긴다. 내가 미리 `movedim(-1, 1)` 하면 **전치가 두 번** 되고,
        # ComfyUI 는 dims 를 (3, 1544, ...) 로 읽어 크롭까지 망가뜨린다
        # (실측: "Calculated padded input size per channel: (1 x 1601)").
        # 주석에 "전치해야 한다"고 적어둔 것이 정확히 반대였다.
        px = image[..., :3]
        if px.dtype != _t.float32:
            px = px.to(dtype=_t.float32)
        # 큰 텐서를 굳이 CPU 에 만들지 않는다 — 대상 장치에서 직접 만든다.
        px = px.to(device=getattr(vae, "device", None) or px.device)
        # 크기 정리는 `vae_encode_crop_pixels` 가 **spacial_compression_encode()
        # (=16) 배수로 중앙 크롭** 한다. 내가 추가로 맞추지 않는다 —
        # 여기서 리사이즈하면 내용이 바뀌고, 크롭이 하는 일만 헛돌게 된다.
        lat = vae.encode(px)
        del px
        _release_vram()
        return lat
    except Exception as _e:
        _note_pose_error('_encode_image_ref', _e)
        _release_vram()
        return None


def _decode_capped(vae, latent, max_pixels=None):
    """VAE 디코드 — 픽셀 수가 상한을 넘으면 latent 를 먼저 줄인다.

    카메라 노드와 같은 규율(`QWEN_REF_MAX_PIXELS`). latent 축은 줄이되 종횡비는
    유지한다(면적 보간이라 비율이 어느 축이든 유지된다). 실패하면 원본 그대로
    디코드한다 — 상한은 최적화이지 동작 조건이 아니다.
    """
    try:
        import torch.nn.functional as _f
        import torch as _t
        h = int(latent.shape[-2])
        w = int(latent.shape[-1])
        # 왜(Why) 더 이상 8 을 박지 않는가 (2026-10-01): 이 8 은 SD 계열
        # 기준이고 Qwen 은 16 이다. 그 차이로 픽셀 상한이 **4배 느슨하게**
        # 동작했다 — 즉 상한이 있어도 실제로는 상한을 못 넘는다.
        # 값은 이전 디코드에서 **배웠다**(`_vae_pixel_factor_learn`). 처음엔
        # 안전망(8)이므로 첫 호출은 지금과 같다가, 두 번째부터 정확해진다.
        _fac = _vae_pixel_factor_for(vae)
        px = float(max(1, h) * max(1, w) * _fac * _fac)
        cap = _DECODE_MAX_PIXELS if max_pixels is None else int(max_pixels)
        if px <= cap:
            img = vae.decode(latent)
            # 왜(Why) 결과를 버리지 않는가: `_vae_pixel_factor_learn` 은 **배운
            # 배율**을 돌려준다. 그 값을 그대로 반환하면 디코드된 이미지가
            # 숫자로 바뀌고 디코딩이 조용히 무력화된다(실측: 마스크·캐시·
            # 디코드 검사 8건이 한꺼번에 깨졌다). 배율은 부수 효과이므로 버린다.
            _vae_pixel_factor_learn(vae, latent, img)
            return img
        scale = (cap / px) ** 0.5
        nh = max(8, int(h * scale))
        nw = max(8, int(w * scale))
        small = _f.interpolate(latent.float(), size=(nh, nw), mode="area")
        img = vae.decode(small)
        # 배율은 축소 전/후 어느 격자에서 읽어도 같다 — 둘 다 같은 비율이다.
        _vae_pixel_factor_learn(vae, small, img)
        del small
        _release_vram()
        return img
    except Exception:
        return vae.decode(latent)


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
            if _lh * _lw * 64 > _DECODE_MAX_PIXELS:
                u8 = (_np.clip(arr, 0.0, 1.0) * 255.0).astype(_np.uint8)
                if not _pose_landmarks_from_tasks(u8):
                    _release_vram()
                    with _t.no_grad():
                        img = _decode_capped(vae, latent,
                                             max_pixels=_DECODE_RETRY_PIXELS)
                    if hasattr(img, "detach"):
                        img = img.detach().cpu()
                    arr2 = img.numpy() if hasattr(img, "numpy") else _np.asarray(img)
                    arr2 = _as_rgb_hwc(_np.asarray(arr2, dtype=_np.float32))
                    if arr2 is not None:
                        arr = arr2
        except Exception as _e:
            _note_retry_error(_e)
        if cache is not None:
            cache[key] = arr
        return arr
    except Exception:
        return None


_TASKS_LANDMARKER = []
_POSE_NOTED = False

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

# VAE 디코드 해상도 상한(픽셀). 카메라 노드의 QWEN_REF_MAX_PIXELS 와 같은 숫자를
# 쓴다 — 두 노드가 한 규칙을 공유해야 나중에 한쪽만 올려도 헷갈리지 않는다.
# 왜(Why) 필요한가 (2026-10-01 실측): RTX 3080 10GB 에 QwenImage21 이 6.9GB 로
# 올라간 상태에서 1056x1888(2MP) latent 를 통째로 디코드하니 멈췄다. 디코드는
# 픽셀 수에 비례해 활성 메모리를 먹는다. **해상도만** 줄이고 비율은 유지하므로
# 마스크(람간 해상도로 보간)·에지 맵(16x16)·부위 판정은 semantics 가 그대로다.
_DECODE_MAX_PIXELS = 1024 * 1024

# 포즈 검출이 상한 때문에 실패했을 때만 올려 재시도하는 해상도 (2026-10-01 실측).
# 왜(Why) 상한값 하나로 안 되는가: 74MP 캐릭터 시트를 1MP 로 줄이면 패널 안의
# 사람이 너무 작아져 mediapipe 가 33점을 통째로 못 찾는다(13장 중 1장 포즈 소실).
# 반대로 6MP 로 올리면 다른 시트가 다시 실패한다 — 상한값에 단조성이 없다.
# 그래서 판정을 직접 지키는 쪽이 낫다: 보통은 1MP 로 싼 디코드로 끝내고,
# **포즈가 안 잡혔을 때만** 한 번 더 크게 디코드한다.
_DECODE_RETRY_PIXELS = 4 * 1024 * 1024

# 시트를 통째로 당겼을 때 강도를 얼마나 낮출까 (2단계).
# 왜(Why) 0.5 인가: 시트의 여러 뷰를 한 장의 latent 로 읽으면 신원 신호가
# **평균나고**, 그 평균은 카메라 노드가 텍스트로 못 막는 실패다. 그래도 절반은
# 남긴다 — 시트의 여하 시점/각도 정보가 완전히 버려지는 것도 손실이기 때문.
_SHEET_DAMP = 0.5

# 관절 33점 모델 파일명. 이 노드와 함께 배포된다(Apache 2.0, Google MediaPipe).
_POSE_MODEL_FILENAME = "pose_landmarker_lite.task"


def _pose_model_path():
    """Return the .task model path to use, or None.

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
        # 못한 탓이다. 정답은 긴 드이 아니라 그 안의 모듈 — landmarker 0.08초 생성, 33점
        # 검출까지 확인했다.
        _BaseOptions = _find_base_options()
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
        _note_pose_error('_pose_landmarker', _e)
        return None
    _TASKS_LANDMARKER.append(lm)
    return lm


def _even_rgb(u8):
    """mediapipe 에 넣을 RGB 배열(짝수 치수). 실패하면 None.

    왜(Why) 짝수로 잘라내나 (2026-09-30 실측, **프로세스 죽음** 버그):
    홀수 높이/너비 이미지는 mediapipe 0.10.33 내부 계산에서 깨질 수 있다.
    SIGABRT 는 try/except 로 못 잡으므로 아래 except 로는 "안전"이 되지 않고
    그저 흉내만 낸다 — 실제로는 ComfyUI 서버 전체가 죽는다. 그래서 방어는
    **호출 전**에 한다. 소비자는 결과(마스크/랜드마크)를 latent 해상도로
    보간하므로 ±1px 는 무의미하다.
    """
    try:
        import numpy as _np
        arr = _np.asarray(u8)
        # 왜(Why) 2 미만은 여기서 막나 (2026-10-01 무결성 실측): 0x0 과 1x1 은
        # "짝수면 통과" 조건을 만족해 mediapipe 까지 들어가고, 거기서 네이티브로
        # RET_CHECK 실패(roi->width > 0 && roi->height > 0)를 낸다. 프로세스는
        # 안 죽지만 어떤 환경에선 치명적이다. mediapipe 를 부르기 **전**에 끊는다.
        if arr.ndim < 2 or arr.shape[0] < 2 or arr.shape[1] < 2:
            return None
        if (arr.shape[0] % 2) or (arr.shape[1] % 2):
            arr = arr[:arr.shape[0] - (arr.shape[0] % 2),
                     :arr.shape[1] - (arr.shape[1] % 2)]
        return _np.ascontiguousarray(arr)
    except Exception:
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
    _log("[GoRi Consistency Keeper] 포즈가 안 잡혀 상한을 올려 다시 디코드했지만 "
         "실패했다. 해상도를 낮춘 상태로 진행한다: "
         + type(exc).__name__ + ": " + str(exc))


def _note_pose_error(where, exc):
    """Log a pose inference failure once. (Jev 2026-09-30: log_once, severity 1.93)

    Per-frame logging would flood the console, so it fires once per process.
    """
    global _POSE_ERR_NOTED
    if _POSE_ERR_NOTED:
        return
    _POSE_ERR_NOTED = True
    _log('[GoRi Consistency Keeper] pose inference failed in ' + where + ': '
         + type(exc).__name__ + ': ' + str(exc))


def _note_pose_unavailable():
    """기능이 꺼진 이유를 한 번만 사용자에게 알린다 (조용한 실패 금지)."""
    global _POSE_NOTED
    if _POSE_NOTED:
        return
    _POSE_NOTED = True
    _log("[GoRi Consistency Keeper] 인체 마스크·부위별 강도·프레이밍 판정이 꺼져 있다. "
         "mediapipe tasks 의 " + _POSE_MODEL_FILENAME + " 을 못 읽는다. "
         "설치 폴더에 파일이 있는지, 또는 GORI_POSE_MODEL 환경변수 경로가 "
         "맞는지 확인해 주세요. 인물 위치만 쓰는 강도 조절은 계속 동작한다.")


_POSE_NOTED = False


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
        ys, xs = _np.mgrid[0:h, 0:w]
        xs = (xs + 0.5) / float(w)
        ys = (ys + 0.5) / float(h)
        best = None
        for (px, py) in pts[:33]:
            d = (xs - float(px)) ** 2 + (ys - float(py)) ** 2
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
        if r <= 0.0:
            return None
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
        _note_pose_error('_person_mask_from_rgb', _e)
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
            return None
        u8 = (_np.clip(arr, 0.0, 1.0) * 255.0).astype(_np.uint8)
        seg = _person_mask_from_rgb(u8)
        if seg is None or seg.max() <= 0.01:
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


def _edge_mag_from_rgb(arr) -> "object | None":
    """RGB 배열(H,W,3) → **전체 해상도** 정규화 에지 크기(H,W). 실패 시 None.

    왜(Why) 이걸 분리했나 (2026-10-01 실측): landmark 별 에지를 재는데
    16×16 격자 셀을 썼더니 손·다리 landmark 가 대부분 `0` 이 나왔다.
    셀 하나가 96×64 픽셀의 **평균**이라 매끈한 피부에서는 0 이 되는 게 당연하다.
    그래서 `detail_boost` 가 부위 하나도 못 골랐다. 평균 대신 **로컬 창**으로
    재야 landmark 가 서 있는 자리를 본다.
    """
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
        _floor = 1e-5 * (float(lum.mean()) + 1e-3)
        if mx <= max(1e-8, _floor):
            # 완전 평탄 이미지: 에지가 "0"이지 "None"이 아니다. 뭉개진 이미지도
            # 여기에 해당한다. None을 돌려주면 부위 비교가 불가능해져
            # "뭉개진 부위"를 판정할 수 없게 된다(실측에서 확인).
            return _np.zeros_like(mag)
        # 왜(Why) 최대값이 아니라 **상위 0.5% 의 평균**인가 (2026-10-01 실측):
        # 강도별 곡선이 단조가 아니었다(0.15 ≈ 0.30 ≫ 0.60). 원인은 여기다.
        # 0.60 결과에 강한 에지 하나(아티팩트)가 생기면 `mx` 가 뛰고 **나머지
        # 픽셀 전체가 눌린다** — 지표가 단일 픽셀 스파이크에 지배되는 셈이다.
        # 상위 0.5% 의 평균은 그런 스파이크에 거의 흔들리지 않으면서도 진짜
        # 에지에는 반응한다. 비교 대상인 두 이미지 사이의 **척도**가 같아진다.
        _k = max(1, int(mag.size * 0.005))
        _ref = float(_np.partition(mag.ravel(), -_k)[-_k:].mean())
        if not (_ref > 0.0):
            _ref = mx
        return mag / _ref
    except Exception as e:
        # 왜(Why) 조용히 두지 않나: 실패하면 **부위 비교가 전부 무의미**해진다.
        # 아무 말 없이 None 이면 "상향할 곳 없음" 과 "재지를 못 읽음" 이 구분되지
        # 않는다(2026-10-01 실제로 한 번 헤맸다).
        _note_once("edge_mag", f"[GoRi Consistency Keeper] ⚠ 에지 맵 계산 실패 "
                               f"({type(e).__name__}: {str(e)[:80]})")
        return None


def _edge_map_from_rgb(arr) -> "object | None":
    """RGB 배열(H,W,3) → 16x16 에지 밀도 맵. 실패 시 None.

    전역 비교용이다. landmark 별 국소 에지는 `_local_edge` 를 쓴다 — 여기서
    셀 평균을 받으면 매끈한 부위에서 0 이 된다(2026-10-01 실측).
    """
    try:
        import torch as _t
        import torch.nn.functional as _f
        mag = _edge_mag_from_rgb(arr)
        if mag is None:
            return None
        small = _f.adaptive_avg_pool2d(_t.from_numpy(mag[None, None]), 16)
        return small[0, 0].numpy()
    except Exception as e:
        # 왜(Why) 조용히 두지 않나: 안쪽 실패는 이미 한 번 말한다. 여기가 조용하면
        # "풀링만 실패" 와 "에지 자체가 없음" 이 구분되지 않는다.
        _note_once("edge_map", f"[GoRi Consistency Keeper] ⚠ 16x16 에지 맵 만들기 실패 "
                               f"({type(e).__name__}: {str(e)[:80]})")
        return None


def _local_edge(mag, fx, fy, frac=0.05):
    """전체 해상도 에지맵에서 landmark 주변 창 평균. 실패 시 0.0.

    frac 은 **이미지 크기에 대한 비율**이다. 원본과 결과물의 해상도가 다를 수
    있으므로(예 1544x1019 vs 1360x768) 픽셀 수로 잡으면 비교가 **척도**를 타서
    공정한 비교가 아니다.
    """
    try:
        import numpy as _np
        m = _np.asarray(mag)
        if m.ndim != 2:
            return 0.0
        h, w = m.shape
        win = int(frac * min(h, w))
        if win < 1:
            return 0.0
        cx = int(fx * w)
        cy = int(fy * h)
        x0 = max(0, cx - win)
        x1 = min(w, cx + win)
        y0 = max(0, cy - win)
        y1 = min(h, cy + win)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        return float(m[y0:y1, x0:x1].mean())
    except Exception as e:
        # 왜(Why) 조용히 두지 않나: 0.0 은 "평평해서 0" 과 "계산 실패" 의
        # **같은 값**이다. 구분하지 못하면 뭐가 진짜인지 알 수 없다.
        _note_once("local_edge", f"[GoRi Consistency Keeper] ⚠ landmark 주변 "
                                f"에지 계산 실패 ({type(e).__name__}: "
                                f"{str(e)[:80]}) — 0 으로 대체")
        return 0.0


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
        import torch as _t
    except Exception:
        return None
    if _pose_landmarker() is None:
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
            em = _edge_mag_from_rgb(arr)
            if em is None:
                continue
            u8 = (_np.clip(arr, 0, 1) * 255).astype(_np.uint8)
            pts3 = _pose_landmarks_from_tasks(u8, with_visibility=True)
            if not pts3:
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




_NO_BOOST_NOTED = False


_DETAIL_DIR_NOTED = False
_DENS_PX = 640 * 360


def _probe_detail_direction(vae, sampled, orig_ref, out):
    """원본을 당겼을 때 디테일이 늘는지 줄는지 **재서** 말한다 (미해결 5-1).

    왜(Why) 이게 먼저인가: 부위별 상향은 "원본은 살아있는데 결과가 뭉개졌다" 는
    가정 위에 세워졌다. 그 가정이 **거짓이면** 설계 방향이 통째로 뒤집힌다.
    어제까지는 "뭉개진다" 는 쪽을 손대지 않고 있었다.
    """
    global _DETAIL_DIR_NOTED
    if _DETAIL_DIR_NOTED or vae is None:
        return
    try:
        def _dens(lat):
            # 왜(Why) `_decode_latent_rgb` 인가 (2026-10-01): `_decode_capped`
            # 는 **torch 텐서 (1,C,H,W)** 를 돌려준다. `_edge_map_from_rgb` 는
            # numpy **HWC 배열**을 받는다. 다른 디코더를 썼다가
            # `too many indices for tensor of dimension 4` 로Measurement가
            # 조용히 실패했다. 이 함수가 RGB numpy 를 반환하는 계약이다.
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
        _DETAIL_DIR_NOTED = True
        _log(f"[GoRi Consistency Keeper] 물리 방향 실측 실패 "
             f"({type(e).__name__}: {str(e)[:90]}) — 판정 보류")
        return
    _DETAIL_DIR_NOTED = True
    _d_out = (_o - _s) / _s * 100.0 if _s > 1e-9 else 0.0
    _d_ref = (_o - _r) / _r * 100.0 if _r > 1e-9 else 0.0
    _verdict = ("당기면 살아난다" if _d_out > 0 else "당기면 뭉개진다")
    _log("[GoRi Consistency Keeper] 물리 방향 실측 "
         f"시본 {_s:.4f} / 원본 {_r:.4f} / 결과 {_o:.4f} — "
         f"결과는 시본 대비 {_d_out:+.1f}%, 원본 대비 {_d_ref:+.1f}% "
         f"⇒ {_verdict}")


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
    _log(f"[GoRi Consistency Keeper] 부위별 복원: 상향할 부위 없음 "
         f"(가장 손실 큰 부위 {region} {worst:.0%} < 임계 {thresh:.0%}) — "
         f"결과물이 원본만큼 살아 있습니다")


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

    왜(Why) 튜플과 객체 둘 다 받는가: landmark 의 모양이 **경로마다 다르다.**
    구 `mediapipe.solutions` 는 `.x`/`.y` 속성 있는 객체를 줬고, tasks API
    경로(`_pose_landmarks_from_tasks`)는 `(x, y)` 튜플을 준다. 속성만 보면
    튜플에서는 전부 None 이 되어 조용히 **bbox=None** 이 되고, 그 결과 프레이밍
    판정이 tasks 전환(2026-09-30) 이후 조용히 죽어 있었다 — 실측으로 확인했다
    (33점은 제대로 나오는데 bbox만 None). 한쪽만 받던 어느 쪽이든 조용히 죽으므로
    둘 다 받는다.
    """
    try:
        import numpy as _np
        if landmarks is None:
            return None
        xs, ys = [], []
        for lm in landmarks:
            if isinstance(lm, (tuple, list)) and len(lm) >= 2:
                x, y = lm[0], lm[1]
            else:
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
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


def judge_points(pts):
    """landmark 열 -> 판정 dict (순수 함수, 검출 없음).

    반환::

        {"verdict": "intact"|"damaged"|"undetermined",
         "confidence": float,
         "checks": [{"check_id", "ok", "detail"}],
         "low_visibility": [관절 이름],
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
    # confidence 는 "그 판정을 내리는 근거의 세기"다. intact 면 가장 흐린
    # 관절의 가시성이 곧 근거이고, undetermined 면 그것이 미판정의 근거다.
    return {"verdict": verdict, "confidence": max(0.0, min(1.0, worst)),
            "checks": checks, "low_visibility": low, "low_indices": low_idx,
            "frame": frame}


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


def judge_reference_trust(u8):
    """uint8 HWC RGB 원본 -> 판정 dict. 검출 실패도 미판정으로 친다."""
    return judge_points(_pose_landmarks_from_tasks(u8, with_visibility=True))


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
        return _as_rgb_hwc(arr)
    except Exception:
        return None


def _pose_landmarks(img_arr):
    """RGB 배열 -> 33점 (x, y) 리스트. 모델 미설치/미검출 시 None.

    (왜) 예전엔 `mediapipe.solutions.pose.Pose` 였는데 그 API 가 없다.
    같은 이유로 tasks API + .task 모델로 대체한다.
    """
    if _pose_model_path() is None:
        _note_pose_unavailable()
        return None
    try:
        import numpy as _np
        if img_arr is None:
            return None
        u8 = (_np.clip(_np.asarray(img_arr, dtype=_np.float32), 0.0, 1.0)
              * 255.0).astype(_np.uint8)
        return _pose_landmarks_from_tasks(u8)
    except Exception:
        return None


def _panel_reference_latent(vae, ref_latent, panel_n, cache=None):
    """시트의 한 패널만 잘라 **진짜 latent** 로 돌려준다. 실패하면 None.

    왜(Why) 다시 VAE 로 인코딩하나: 패널 좌표는 픽셀 배열에서 얻었으므로
    여기서Ended 픽셀 텐서를 만들어 그대로 넘기고 싶지만, downstream 은 전부
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
            return None
        h, w = int(full.shape[0]), int(full.shape[1])
        x0 = max(0, min(w - 2, int(float(panel_n[0]) * w)))
        x1 = max(x0 + 1, min(w, int(float(panel_n[1]) * w)))
        if x1 - x0 < 8:
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
        _note_pose_error('_panel_reference_latent', _e)
        return None


def _content_crop(arr, tol=0.06):
    """균일한 배경을 잘라 내용만 남긴다. 실패하면 원본 그대로.

    왜(Why) 필요한가 (2026-09-30 실측): 시트 패널은 세로로 흰 여백이 크다.
    패널을 x 로만 자르면 185x1888 이 남는데, 그 흰 띠 때문에 33점 검출이
    불안정해진다(실측: 4개 중 1개가 미검출). 여백을 잘라 185x711 로 만들면
    전 패널이 검출되고 프레이밍 게이트도 통과한다(0.747).
    """
    try:
        import numpy as _np
        a = _np.asarray(arr, dtype=_np.float32)
        if a.ndim != 3 or a.shape[0] < 4 or a.shape[1] < 4:
            return arr
        lum = a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114
        m = _np.abs(lum - float(_np.median(lum))) > float(tol)
        rows = _np.nonzero(m.any(axis=1))[0]
        cols = _np.nonzero(m.any(axis=0))[0]
        if not len(rows) or not len(cols):
            return arr
        out = a[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
        return out if out.size else arr
    except Exception:
        return arr


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
            # 없이(Why) 또 말하는가: 여기 론 마을 실패
            # ("시트니다") 와 구부할 수 없을 딜다. _decode_small 이
            # 예외를 실패하고 사인 일 사람이라서
            # 상여가 보이면 사용자ꊔ "패널 0개" 를 보고
            # 누 상여를 확인한다.
            _note_pose_error('analyze_reference_sheet.decode', None)
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
            # 항상 False -> 2단계 (A) 경로로 영영 못 들어간다. 패널 검감출·유사도
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
        _note_pose_error('analyze_reference_sheet', _e)
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
            elif info.get("raw", 0) > 0:
                # 없이(Why) 이 줄이 필요하단가: 패널이 1~2개이면 이전은 아누 말도 없었다. 사용자가 시트를 무에다고 판정 로그가 0개이면
                # "시트가 아닌 걸 모 아잣체다" 와 "분석이 죽다" 가 구부되지 않는다
                # (2026-09-30 실체로 정확히 이 혼동이 발일다).
                _log(f"[GoRi Consistency Keeper] {ref_name} 시트 아닌 — "
                     f"패널 {info['raw']}개만 검출 (최소 {SHEET_MIN_PANELS}개 필요)")
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
            },
        }

    def run(self, sampled_latent, strength_camera=0.2, strength_original=0.2,
            original_latent=None, camera_latent=None, vae=None,
            original_image=None, trust_gate=False):
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
        # 왜(Why) original_image 이 우선인가 (2026-10-01 실측):
        # `TextEncodeQwenImage21` 의 `latent` 출력은 **전부 0** 이다. 그
        # latent 를 `original_latent` 로 받는 한 원본 기준은 항상 빈 캔버스와
        # 비교하게 되고 숫자가 무의미하다. 이미지가 오면 그것을 직접 인코딩해
        # 기준을 세운다. 이미지 없으면 기존 경로(빈 latent) 그대로 둔다 —
        # 동작을 바꾸지 않기 위함이지, 그 경로가 옳다는 뜻이 아니다.
        if original_image is not None:
            _img_ref = _encode_image_ref(vae, original_image)
            if _img_ref is not None:
                _orig_ref = _img_ref
                _orig_from_image = True
                _log("[GoRi Consistency Keeper] 원본 기준을 이미지에서 직접 "
                     "인코딩했습니다 — Qwen Edit 의 latent 출력은 빈 캔버스라 "
                     "그대로 쓰면 비교가 무의미합니다")
            else:
                _orig_from_image = False
                _log("[GoRi Consistency Keeper] ⚠ original_image 인코딩 실패 — "
                     "original_latent 경로로 진행합니다 (Qwen Edit 에선 빈 "
                     "캔버스이므로 원본 기준이 사실상 없습니다)")
        else:
            _orig_from_image = False
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
        # 왜(Why) 이 로그가 필요한가 (2026-09-30 실측): 마스크가 없으면 당김이
        # **전역**으로 퍼져 배경까지 끌려간다. 그런데 마스크 유무가 로그로 안
        # 알려지면 "영향 없음"과 "전역 당김"을 구별할 수 없다 — 실제로 vae 를
        # 연결했는데 마스크가 조용히 None 이었던 상태를 로그 없이 한참 알지
        # 못했다. 한 줄로 충분하다.
        if vae is not None and _mask is None and not _multi:
            _log("[GoRi Consistency Keeper] 인체 마스크 없음 — 전역 당김으로 "
                 "진행합니다 (포즈 미검출 또는 VAE 미연결)")
        # 캐릭터 시트 참조 분석 (2단계: 판정을 강도에 반영한다).
        # 왜(Why) 여기가 **부위별 맵보다 먼저**인가: 아래 판정으로 기준 원본이
        # 패널로 바뀔 수 있다. 맵을 먼저 만들면 맵은 시트 전체를 보고 당김만
        # 패널을 보게 되어 둘이 서로 다른 원본을 참조하게 된다.
        if vae is not None and b and not _multi and _orig_ref is not None:
            _sheet = analyze_reference_sheet(vae, _orig_ref, sampled, cache=_dcache)
            _log_sheet_analysis(_sheet, "original")
            if _sheet.get("sheet") and _sheet.get("best") is not None:
                _pn = _sheet.get("panels_n") or []
                if _sheet.get("gate") and 0 <= _sheet["best"] < len(_pn):
                    # (A) 신원 신호가 섞이지 않게 **그 패널 하나만** 기준으로 쓴다
                    _panel = _panel_reference_latent(
                        vae, _orig_ref, _pn[_sheet["best"]], cache=_dcache)
                    # 왜(Why) dict 로 감싸나: `_get_samples` 은 LATENT dict
                    # 에서만 samples 를 꺼낸다. `vae.encode` 결과는 raw 텐서라
                    # 그대로 넘기면 조용히 None 이 되어 패널 대체가 통하지 않는다.
                    _p_ref = _get_samples({"samples": _panel})
                    if _p_ref is not None:
                        _orig_ref = _p_ref
                        _log(f"[GoRi Consistency Keeper]   2단계: "
                             f"{_sheet['best'] + 1}번 패널을 기준 원본으로 "
                             f"사용합니다 (시트 전체 대신 단일 뷰)")
                else:
                    # (B) 게이트를 못 통과하면 패널 프레이밍이 결과물과 다르다.
                    # 그래도 시트 전체를 강하게 당기면 신원 신호가 평균나므로
                    # 강도를 낮춘다 — 버리는 것보다 나음.
                    _old_b = b
                    b = _safe_strength(b * _SHEET_DAMP, "strength_original")
                    _log(f"[GoRi Consistency Keeper]   2단계: 프레이밍이 안 "
                         f"맞아 패널을 쓰지 않습니다. 시트 전체의 신원 신호가 "
                         f"섞이므로 강도를 낮춥니다 {_old_b:.2f}->{b:.2f}")
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
                _log(f"[GoRi Consistency Keeper] {name} 배치·채널 불일치 — 건너뜀")
                continue
            drift = _drift_mse(sampled, matched)
            # 정규화 값도 함께 재고 **둘 다** 로그한다.
            drift_n = _drift_norm(sampled, matched)
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
                if _dn < eff:
                    eff = _dn
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
            # 물리 상한 (2026-10-01 실측). 왜(Why) 있는가:
            # 당길수록 디테일이 줄고, **0.78 을 넘어서면 결과의 에지가 원본보다
            # 적어진다** — 참조로 당기는 노드가 참조보다 더 뭉개진 결과를 낸다.
            # 실측(같은 시드, 서있는 자세 1장, 강건한 지표):
            #   0.15 → 원본 대비 +6.1%   0.30 → +2.1%
            #   0.60 → +2.2%             0.90 → -1.5%   (여기서 하강)
            # **한 장짜리 실측이라잪정 값이다.** 더 많은 표본으로 갱신할 것.
            # 조용히 줄이지 않는다 — 잘렸을 때 반드시 말한다.
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
                    _pts = (_pm.get("original") or {}).get("pts")
                    if _pts:
                        _verdict = judge_points(_pts)
                        _allow = judge_region_allowance(_verdict)
                    if _allow is None:
                        _log("[GoRi Consistency Keeper] 판정 게이트 켰지만 원본 "
                             "landmark 가 없어 제한 없이 진행합니다")
                    else:
                        _blocked = sorted(k for k, v in _allow.items()
                                          if float(v) <= 0.0)
                        _verdict_name = (_verdict.get("verdict")
                                         if _verdict else "?")
                        _log("[GoRi Consistency Keeper] 판정 게이트 "
                             f"(verdict={_verdict_name}) — 미확인 부위 "
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
        _release_vram()
        return ({"samples": out},)
