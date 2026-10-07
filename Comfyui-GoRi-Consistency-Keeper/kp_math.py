# -*- coding: utf-8 -*-
"""모드 앵카·가드… 를 위한 순수 수치/이미지 유틸. 포함시키지 않은 외부 상태는 없음."""

from __future__ import annotations

__all__ = [
"_match_spatial", "_drift_mse", "_drift_norm", "_get_samples", "_with_samples", "_damp_norm", "_damp_factor", "_lighting_mismatch", "_light_damp_factor", "_as_rgb_hwc", "_even_rgb", "_edge_mag_from_rgb", "_edge_map_from_rgb", "_local_edge", "_noise_floor", "_DRIFT_NORM_KNEE", "_PHYS_CEILING", "_DRIFT_NORM_ZERO", "_DECODE_MAX_PIXELS", "_DECODE_RETRY_PIXELS"
]

_ONCE_SEEN = set()


def _note_once(key: str, msg: str) -> None:
    """경고를 한 번만 출력한다. kp_math 는 main 과 별도 모듈이므로 자체 구현."""
    try:
        if key in _ONCE_SEEN:
            return
        _ONCE_SEEN.add(key)
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            import sys as _sys
            enc = getattr(_sys.stdout, "encoding", None) or "utf-8"
            print(msg.encode(enc, "replace").decode(enc, errors="replace"),
                  flush=True)
    except Exception:
        pass



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


def _with_samples(latent, out) -> tuple:
    """입력 LATENT dict 의 부가 키(noise_mask, batch_index)를 보존해 돌려준다.

    왜(Why) {"samples": out} 만 다시 만들지 않나 (2026-10-04 감사 12차):
    ComfyUI 의 `common_ksampler` 는 `latent.copy()` 로 noise_mask 와
    batch_index 를 다음 노드로 **전파한다**(nodes.py). 이 노드가 samples 만
    돌려주면 인페인트 마스크가 여기서 사라지고, 뒤에 이어진 KSampler 가
    마스크 밖까지 통째로 다시 그린다 — 오류도 로그도 없는 조용한 오답이다.
    ComfyUI 자체 샘플러들이 지키는 전파 관례를 그대로 따른다. dict 가
    아니면(방어) samples 만 있는 새 dict 를 돌려준다.
    """
    d = dict(latent) if isinstance(latent, dict) else {}
    d["samples"] = out
    return (d,)


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
        # 왜(Why) .float() 인가 (2026-10-07 감사): _drift_norm 은 분자를
        # 항상 float32 로 계산한다. 원본이 fp16 이면 구식(a-b)**2 는 fp16
        # 정밀도로 남아 두 함수의 값이 갈라진다 — 넘겨받을 수 없게 된다.
        # fp32 입력에서는 결과가 같다(테스트의 0.36 검증 불변).
        return float(_t.mean((a.float() - b.float()) ** 2).item())
    except Exception:
        return None


def _drift_norm(sampled, matched, _mse=None) -> float | None:
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
        if _mse is None:
            # 왜(Why) 인자로 받나 (2026-10-07 감사): 호출부(당김 루프)는
            # 같은 쌍의 제곱편차를 이미 계산해 로그에 쓴다. 여기서 다시
            # 계산하면 (sampled-matched)^2 가 루프마다 두 번 돈다. 값은
            # 같으니 넘겨받는다 — 안 넘기면 예전 그대로 직접 계산한다.
            _mse = float(_t.mean(
                (sampled.float() - matched.float()) ** 2).item())
        return float(_mse) / den
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


# 물리 상한: 당김 강도가 이 값을 넘으면 결과의 디테일이 **원본보다** 줄어든다.
#
# 근거 (WORK_STATUS 11-7). **대응 지점** 기준(landmark 주변 5% 창, 결과물 좌표
# 기준) — 화면 전체 평균이 아니라 같은 자리에 있는 원본/결과를 비교한다.
# 사람 7장, 강도 0 을 **검증용 기준선**으로 넣었다:
#
#   강도 0.00   평균  -1.2%   ← 당김이 없으니 0 근처 = 지표가 옳다
#   강도 0.20   평균 -33.5%
#   강도 0.40   평균 -36.1%
#
# 손실 몰림: 0.00→0.20 이 -32.2%p, 0.20→0.40 은 -2.7%p. **0.20 이 상한**이다.
# 그 이전 값 0.78 은 화면 전체 평균 지표(11-5)에서 나왔고, 그 지표는 강도 0
# 검증을 통과하지 못했다(0.40 에서 +12.5% 로 증가). **4배 과했다.**
_PHYS_CEILING = 0.20


_DRIFT_NORM_ZERO = 1.00


def _damp_norm(v) -> float:
    """정규화 불일치 -> 감쇠 계수 0~1. None 은 1.0(안 건드림), NaN 은
    0.0(전파 차단, R71 계약).

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


def _noise_floor(lum) -> float:
    """평탄 판정 노이즈 바닥. max(1e-8, 상대 * (평균 + 절대)).

    왜(Why) 함수로 뽑나 (2026-10-07 감사): 같은 공식이 kp_math(에지 판정)와
    kp_sheet(패널 판정)에 **각자 한 번씩** 적혀 있었다. 한쪽만 고치면 두
    판정의 "평탄" 기준이 갈라진다 — 한 곳에서만 정의한다.
    """
    return max(1e-8,
               _NOISE_FLOOR_REL * (float(lum.mean()) + _NOISE_FLOOR_ABS))


_NOISE_FLOOR_REL = 1e-5
_NOISE_FLOOR_ABS = 1e-3


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
        # 왜(Why) 최소 크기 가드 (2026-10-07 감사): 예전엔 valid 컬볼루션이
        # 축 < 3 에서 음수 크기 RuntimeError 로 조용히 None 이 됐다.
        # replicate 선패딩은 퇴화 축(예: 너비 1)도 살려 계산해 버려
        # R55 "퇴화 모양 → 예외 없이 None" 계약이 깨진다. 원래 경계값
        # (H, W >= 3)을 명시로 지킨다.
        if lum.shape[0] < 3 or lum.shape[1] < 3:
            return None
        t = _t.from_numpy(lum[None, None])
        # Sobel (cv2 없이 torch만으로)
        kx = _t.tensor([[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]])
        ky = kx.t().contiguous()
        # 왜(Why) padding 인가 (2026-10-07 감사): valid 컬볼루션은 결과를
        # (H-2, W-2) 로 돌려 docstring 이 약속한 **전체 해상도(H,W)** 와
        # 어긋났다 — `_local_edge` 의 landmark 정규화 좌표가 2픽셀씩 밀린
        # 맵에 대응된 셈이다. replicate 는 영패딩의 인공 경계 에지 없이
        # 가장자리 픽셀을 이어 붙여 크기와 경계값을 동시에 지킨다.
        # (F.conv2d 에는 padding_mode 가 없다 — 이 토치 버전 실측
        # TypeError. 그래서 F.pad 로 미리 패딩한다.)
        _tp = _f.pad(t, (1, 1, 1, 1), mode="replicate")
        gx = _f.conv2d(_tp, kx[None, None])
        gy = _f.conv2d(_tp, ky[None, None])
        mag = (gx * gx + gy * gy).sqrt()[0, 0].numpy()
        mx = float(mag.max())
        # 왜(Why) 임계가 절대값이면 안 되는가(2026-09-28 실측): float32
        # conv2d 수치 노이즈 바닥이 이미지 크기에 따라 1e-8 근처까지 내려가
        # **디테일이 전혀 없는** 평탄 이미지가 mx>1e-8 로 통과한다. 그러면
        # `mag/mx` 정규화 결과가 1.0 이 되어 "뭉개진 부위"가 아니라
        # "디테일 최대"로 읽힌다 → detail_boost 가 전부 반대로 동작한다.
        # 실측: 64x64 평탄 이미지 값 0.5→0.0 / 0.45→1.0 (반전).
        # 해결: 노이즈 바닥을 **입력 대비 상대값**으로 잡는다.
        if mx <= _noise_floor(lum):
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
