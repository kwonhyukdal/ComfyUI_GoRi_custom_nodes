# -*- coding: utf-8 -*-
"""모드 앵카·가드… 를 위한 순수 수치/이미지 유틸. 포함시키지 않은 외부 상태는 없음."""

from __future__ import annotations

__all__ = [
"_match_spatial", "_drift_mse", "_drift_norm", "_drift_norm_masked", "_drift_tile_max", "_lowpass_latent", "_hf_restore_pass", "_get_samples", "_with_samples", "_damp_norm", "_damp_factor", "_content_change_gate", "_FACE_GATE_PERSON_FLOOR", "_prompt_intent", "_face_gate_open", "_bg_gate_open", "_lighting_mismatch", "_light_damp_factor", "_as_rgb_hwc", "_even_rgb", "_edge_mag_from_rgb", "_edge_map_from_rgb", "_local_edge", "_noise_floor", "_DRIFT_NORM_KNEE", "_PHYS_CEILING", "_DRIFT_NORM_ZERO", "_DECODE_MAX_PIXELS", "_DECODE_RETRY_PIXELS"
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

    임계값은 이 정규화값으로 **실측해 정했다** — 아래 `_DRIFT_NORM_KNEE = 0.50`
    / `_DRIFT_NORM_ZERO = 1.00` 이 그 값이고, 근거는 정상 참조 4건의 실측 범위
    0.222 ~ 0.487 이다(무감쇠 구간이 정상 범위를 덮어야 한다).
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


def _drift_norm_masked(sampled, matched, mask, _mse=None) -> float | None:
    """사람 마스크 영역만의 정규화 불일치. 비교 불가면 None.

    왜(Why) 마스크 버전이 필요한가 (2026-10-12 실측): 전체 프레임 정규화값은
    배경이 지배한다. 결과물과 참조의 **배경**이 같고 **사람 자세**만 다르면
    전체 정규화가 0.44~0.47 로 무감쇠 구간(<=0.50) 안에 들어 당김이 그대로
    적용됐다. 당김은 `eff * _mask * (matched - sampled)` 로 사람 영역만
    블렌드하므로 올바른 측정 대상은 사람 영역이다. 실측: 전체 정규화 0.44~
    0.63 에 강도 0.11~0.20 블렌드 -> 생성물 사람 전체에 잔상(더블 노출).
    정규화 방식은 `_drift_norm` 과 같다(참조 크기 기준). 마스크가 전부 0 이면
    den 이 0 이라 None — 그 상태의 블렌드는 어차피 아무것도 바꾸지 않는다.
    """
    try:
        import torch as _t
        if mask is None:
            return None
        m = mask.to(device=sampled.device, dtype=sampled.dtype)
        s = sampled.float() * m
        r = matched.float() * m
        den = float(_t.mean(r ** 2).item())
        if den <= 1e-12:
            return None
        if _mse is None:
            _mse = float(_t.mean((s - r) ** 2).item())
        return float(_mse) / den
    except Exception:
        return None


def _drift_tile_max(sampled, matched, mask, tiles=8) -> float | None:
    """마스크 영역을 tiles×tiles 로 나눈 타일별 정규화 불일치 중 최댓값.
    비교 불가 타일(커버리지 1% 미만·계산 실패)은 건너뛴다.
    유효 타일이 없으면 None.

    왜(Why, 2026-10-13): 배경 당김 게이트가 전체 평균만 본다 — 밝은 배경이
    평균을 깔아주면 어긋난 가구 다리 같은 국소 불일치가 그대로 찍힌다
    (bg_gate_calib.py 실측: 평균 0.0587 통과 vs band 국소 0.63).
    당장은 로그 관측용이다 — 임계 고정은 실측 분포가 모이면 한다. 타일
    임계는 텍스처 바닥과 겹쳐 성급히 고정하면 정상 당김을 막는다
    (같은 bg_gate_calib.py: 정상 동일 장면 타일최대 0.70~1.02가
    합성 고스트 0.45를 넘는다). 동작 변경 없음.
    """
    try:
        import torch as _t
        if mask is None:
            return None
        m = mask.to(device=sampled.device, dtype=sampled.dtype)
        h = int(sampled.shape[-2])
        w = int(sampled.shape[-1])
        if h <= 0 or w <= 0 or tiles < 1:
            return None
        best = None
        for i in range(tiles):
            for j in range(tiles):
                tm = m[..., i * h // tiles:(i + 1) * h // tiles,
                       j * w // tiles:(j + 1) * w // tiles]
                if float(tm.mean()) < 0.01:
                    continue
                v = _drift_norm_masked(
                    sampled[..., i * h // tiles:(i + 1) * h // tiles,
                            j * w // tiles:(j + 1) * w // tiles],
                    matched[..., i * h // tiles:(i + 1) * h // tiles,
                            j * w // tiles:(j + 1) * w // tiles],
                    tm)
                if v is not None and (best is None or v > best):
                    best = v
        return best
    except Exception:
        return None


def _lowpass_latent(lat, down=2):
    """latent 저역 통과 — area 축소 후 원격자로 확대.

    왜(Why) area 모드인가 (2026-10-12 실측): 고주파를 지우는 게 목적이라
    선형 보간은 자기 자신의 고주파를 다시 만들 수 있다. area 평균은 블록
    평균이라 확대 후에도 고주파가 생기지 않는다. down=2 는 latent 2칸 = 이미지
    32픽셀(Qwen 16배율) 기준 — 눈·입 같은 구조(LL)는 살리고 피부 질감·머리카락
    같은 HF 만 떼어낸다.
    """
    import torch.nn.functional as _f
    h = int(lat.shape[-2])
    w = int(lat.shape[-1])
    small = _f.interpolate(lat.float(),
                           size=(max(1, h // down), max(1, w // down)),
                           mode="area")
    big = _f.interpolate(small, size=(h, w), mode="area")
    return big.to(dtype=lat.dtype)


def _hf_restore_pass(sampled, out, down=2):
    """당김이 깎은 고주파(질감·에지)를 당김 전 상태에서 되살린다.

    왜(Why) 이 함수가 필요한가 (2026-10-12 실측, 실제 Qwen VAE):
    당김 블렌드 `out + eff * (matched - out)` 은 latent 공간의 선형 평균이라
    **저역통과 필터로 작동한다**. 참조가 2픽셀만 어긋나도(정렬된 정상 참조)
    eff 0.20 에서 라플라시안 분산이 전체 -14%·얼굴 -24% 깎였다(카메라 0.20 +
    원본 0.15 이중 당김이면 전체 -23%·얼굴 -31%). 이것이 "생성물이 번진다"
    신고의 직접 원인이다. 강도를 줄이면 신원 복원(이 노드의 존재 이유)이
    무뎌진다.

    해법: 저역(LL)은 당김 결과를 따르고 고주파(HF)는 당김 **전** 상태에서
    다시 얹는다. `lowpass(out) + (sampled - lowpass(sampled))`. HF 는 질감이지
    신원이 아니므로(신원·구도는 LL+중역에 있다) 당김의 신원 효과는 유지되고
    실측상 얼굴 선명도 0.76 -> 0.94 로 회복됐다. 부분 복원(alpha=0.5)은
    중역이 반쯤 상쇄돼 오히려 0.73 으로 **악화**되는 비단조 구간이 실측됐으므로
    완전 복원만 한다.

    계약: out 이 sampled 와 값이 같으면 **out 객체 그대로** 반환(바이트 단위
    무변화 — 부동소수점 재조합을 아예 하지 않는다). shape 이 다르거나 실패해도
    out 그대로. 장치·dtype 은 out 을 따른다. 디코드를 하지 않는다(비용 0).
    """
    try:
        import torch as _t
        if sampled is None or out is None:
            return out
        if tuple(sampled.shape) != tuple(out.shape):
            return out
        # 왜(Why) equal 단락 (2026-10-12): (lp + s - lp) 는 부동소수점에서
        # 비트 단위로 s 가 아니다. 당김이 없었던 실행은 기존 결과와 바이트
        # 단위로 같아야 한다는 계약을 지키기 위해 재조합 자체를 하지 않는다.
        if _t.equal(out, sampled):
            return out
        lp_out = _lowpass_latent(out, down)
        lp_s = _lowpass_latent(sampled, down)
        hf = sampled.float() - lp_s.float()
        return (lp_out.float() + hf).to(dtype=out.dtype)
    except Exception:
        return out


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


# 의도된 내용 변경 게이트 (2026-10-12 실측). 얼굴 정규화 drift 가 무감쇠
# 구간 안(참조와 일치)인데 사람 전체 정규화 drift 가 임계 아래 바닥(0.40)을
# 넘으면, 그 차이는 오차가 아니라 **의도된 내용 변경**(의상 교체 등)이다.
#
# 근거 실측 (실제 Qwen VAE, 결과물 vs 원본 사진):
#   의상 교체 실행   사람 0.329 / 얼굴 0.194   (얼굴이 훨씬 일치)
#   같은 그림 6px 이동  사람 0.348 / 얼굴 0.235
#   같은 그림 12px 이동 사람 0.376 / 얼굴 0.301
#   같은 그림 24px 이동 사람 0.445 / 얼굴 0.465   (얼굴도 같이 어긋남)
#
# 바닥 0.40 을 두는 이유: 사람 drift 가 0.40 아래면 당김 자체가 온화해서
# 게이트를 열 필요가 없다(정상 참조 범위 상단 근처). 어긋난 참조(24px)는
# 얼굴도 같이 어긋나 "얼굴 < 사람" 조건에서 걸러진다 — 게이트는 어긋남을
# 치지 않는다.
_FACE_GATE_PERSON_FLOOR = 0.40


def _content_change_gate(face_n, person_n) -> bool:
    """의도된 내용 변경 게이트. 참이면 몸을 참조로 끌어오지 않고 얼굴만 당긴다.

    세 조건: 얼굴이 무릎 안(참조와 일치), 사람 전체가 바닥 위(차이가
    유의미), 그리고 얼굴이 사람보다 더 일치(신원은 보존되고 내용만 바뀐
    지문). 세 번째가 어긋남을 걸러준다 — 24px 밀린 참조는 얼굴(0.465)이
    사람(0.445)보다 더 어긋나 여기서 거짓이 된다.

    None·NaN 은 거짓 — 판정 근거가 없으면 게이트를 열지 않는다(기존 동작).
    """
    try:
        if face_n is None or person_n is None:
            return False
        if face_n != face_n or person_n != person_n:   # nan
            return False
        return (face_n <= _DRIFT_NORM_KNEE
                and person_n > _FACE_GATE_PERSON_FLOOR
                and face_n < person_n)
    except Exception:
        return False


# 프롬프트 의도 판정 (2026-10-12, 1단계). 키퍼가 카메라 프롬프트를 직접
# 받아 "무엇이 의도된 변경인가"를 픽셀 지문만이 아니라 텍스트로 확인한다.
# 왜(Why) 교체 동사를 요구하나: 프롬프트는 항상 최종 상태를 묘사한다 —
# "wearing a red dress" 는 의상을 **바꾼 실행**에도, 원본이 이미 빨간
# 드레스인 실행에도 나온다. 묘사 명사만으로는 의도와 열화를 구분할 수
# 없다(거짓 양성 폭탄). 바꾸라는 동사(change/replace/교체/변경...)가
# 있을 때만 그 대상의 변경을 의도로 인정한다 — 보수적이고 안전하다.
# 프롬프트 판정은 게이트를 **닫는 방향으로만** 강화한다(당김 억제).
# 픽셀 지문으로 열리던 게이트를 프롬프트가 되칼 수는 없다 — 참조와
# 같아야 한다는 DNA 계약이 우선이다.
_PROMPT_CHANGE_VERBS = (
    "change", "replace", "swap", "switch to", "put on",
    "교체", "변경", "바꾸", "바꿔", "바뀐", "갈아입",
)
_PROMPT_OUTFIT_NOUNS = (
    "outfit", "clothes", "clothing", "dress", "top", "shirt", "pants",
    "skirt", "jacket", "costume", "garment",
    # 신발류 (2026-10-13). 왜(Why): "change her shoes to sandals" 처럼
    # 교체 동사가 있어도 대상 명사가 목록에 없으면 조인 창에서 걸러져
    # 의도=False 가 됐다 — 키퍼가 바뀐 신발을 원본으로 되돌린다.
    # "heels" 를 넣지 않는 이유: 부분 문자열 매칭이라 "wheels" 에도
    # 걸린다(오판). "high heel" 구문은 충돌이 없다.
    "shoe", "shoes", "sandal", "sandals", "boots",
    "sneaker", "sneakers", "slipper", "slippers", "footwear", "high heel",
    "의상", "옷", "복장", "드레스", "원피스", "상의", "하의", "치마", "자켓",
    "신발", "구두", "샌들", "단화", "운동화", "하이힐", "부츠",
)
_PROMPT_SCENE_NOUNS = (
    "background", "scene", "setting", "location", "backdrop",
    "street", "beach", "indoor", "outdoor", "room", "studio", "park",
    "배경", "장소", "장면", "무대", "실내", "실외",
)

# 조건·부정 표지 (2026-10-13 실측 — 거짓 양성의 실제 출처).
# 왜(Why) 필요한가: 카메라 노드의 정체성 앵커 문구(cam_anchors.py)가
#   "Preserve the same facial identity ... hairstyle, and clothing
#    unless the instruction explicitly changes them."
# 다. "clothing"(의상 명사) 과 "changes"(교체 동사) 가 **같은 절**에 있어서
# 매 실행이 의상 교체로 오판됐다 — 실측: 키퍼 로그에 매 실행
# "프롬프트가 의상 교체를 지시" 가 찍히고 얼굴 게이트가 열려 **몸(의상) 당김이
# 통째로 꺼졌다.** 사용자가 지시하지 않은 의상 변경(하의 청바지 -> 스커트)이
# 그대로 남았다.
# 조건·부정 문맥의 동사는 **지시가 아니므로** 의도로 세지 않는다.
_PROMPT_COND_MARKERS = (
    "unless", "if ", "when ", "do not", "don't", "does not", "never",
    "without", "not ", "no change", "no alteration",
)

# 동사 앞 몇 문자까지 조건·부정으로 볼지. 앵커 문구는 "changes" 4단어 앞에
# "unless" 가 있어 48자면 충분하다. 문장 경계(. ; 개행)는 넘지 않는다 —
# "no hats. change the outfit" 처럼 **다른 문장**의 부정이 지시를 죽이면 안 된다.
_PROMPT_COND_WINDOW = 48

# 한국어 부정은 **동사 뒤**에 온다("바꾸지 않는 한", "바꾸지 마"). 앞 창으로는
# 잡히지 않으므로 동사 직후 아주 좁은 창만 본다. 넓히면 "교체하고 배경은 바꾸지
# 않는다" 의 **진짜 교체**까지 죽는다 — 6자로 제한한다.
_PROMPT_COND_AFTER = ("지 않", "지않", "지 마", "지마", "면 안", "면안")
_PROMPT_COND_AFTER_WINDOW = 6


# 동사와 **대상 명사가 함께 있어야** 지시로 본다 (2026-10-13 실측 2차).
# 왜(Why) 필요한가: "아무 데나 동사 x 아무 데나 명사" 는 카메라 보일러플레이트에서
# 무조건 참이 된다. 실측(실제 프롬프트 6110자)에서 거짓 양성이 3개 남았다.
#   "However, changes requested by the user must be applied ..."  (changes)
#   "any changes requested by the user must be applied ..."       (changes)
#   "no limbs swapping between people"                            (swap)
# 셋 다 의상/장면 명사와 멀리 떨어져 있다 — **다른 절의 명사**를 끌어다 쓴 것.
# 지시라면 대상이 동사 옆에 있다("change the outfit", "replace the background").
_PROMPT_PAIR_WINDOW = 40


def _clause_before(text, i, window=_PROMPT_COND_WINDOW) -> str:
    """i 앞 window 문자 중 **마지막 문장 경계 뒤** 구간. 조건 표지 탐색용."""
    seg = text[max(0, i - window):i]
    cut = max(seg.rfind("."), seg.rfind(";"), seg.rfind("\n"),
              seg.rfind("!"), seg.rfind("?"))
    return seg[cut + 1:] if cut >= 0 else seg


def _has_change_instruction(text) -> bool:
    """교체 동사가 **조건·부정 문맥이 아닌** 곳에 하나라도 있는가.

    조건·부정 문맥의 동사는 지시가 아니다 — 그걸 지시로 세면 게이트가 잘못
    열려 몸 당김이 꺼진다(2026-10-13 실측). 반대로 진짜 지시("change the
    outfit to ...")는 앞에 표지가 없으므로 그대로 잡힌다.
    """
    for v in _PROMPT_CHANGE_VERBS:
        start = 0
        while True:
            i = text.find(v, start)
            if i < 0:
                break
            before = _clause_before(text, i)
            after = text[i + len(v):i + len(v) + _PROMPT_COND_AFTER_WINDOW]
            if (not any(m in before for m in _PROMPT_COND_MARKERS)
                    and not any(m in after for m in _PROMPT_COND_AFTER)):
                return True
            start = i + 1
    return False


def _prompt_intent(prompt) -> dict:
    """카메라 프롬프트에서 의도된 변경을 읽는다.

    반환: {"outfit_change": bool, "scene_change": bool}. None·빈 문자열은
    전부 거짓 — 판단 근거가 없으면 픽셀 게이트만 믿는다(기존 동작).

    판정 3단 (2026-10-13 실측으로 두 번 조여졌다):
      1  교체 동사가 있어야 한다 (묘사만으로는 의도와 열화를 못 가른다)
      2  그 동사가 **조건·부정 문맥이 아니어야** 한다
         ("unless the instruction explicitly changes them")
      3  그 동사 옆에 **대상 명사가 함께 있어야** 한다
         ("changes requested by the user ..." 는 지시가 아니다)
    """
    try:
        if not prompt or not isinstance(prompt, str):
            return {"outfit_change": False, "scene_change": False}
        text = prompt.lower()
        if not _has_change_instruction(text):
            return {"outfit_change": False, "scene_change": False}
        outfit = scene = False
        for v in _PROMPT_CHANGE_VERBS:
            start = 0
            while True:
                i = text.find(v, start)
                if i < 0:
                    break
                start = i + 1
                if any(m in _clause_before(text, i)
                       for m in _PROMPT_COND_MARKERS):
                    continue
                tail = text[i + len(v):i + len(v) + _PROMPT_COND_AFTER_WINDOW]
                if any(m in tail for m in _PROMPT_COND_AFTER):
                    continue
                win = text[max(0, i - _PROMPT_PAIR_WINDOW):
                           i + len(v) + _PROMPT_PAIR_WINDOW]
                if not outfit and any(n in win for n in _PROMPT_OUTFIT_NOUNS):
                    outfit = True
                if not scene and any(n in win for n in _PROMPT_SCENE_NOUNS):
                    scene = True
                if outfit and scene:
                    return {"outfit_change": True, "scene_change": True}
        return {"outfit_change": outfit, "scene_change": scene}
    except Exception:
        return {"outfit_change": False, "scene_change": False}


def _face_gate_open(face_n, person_n, intent_outfit=False) -> bool:
    """얼굴 게이트 최종 판정. 픽셀 지문 또는 프롬프트 의도 중 하나라도
    참이면 열린다 — 프롬프트가 의상 교체를 지시했으면 옷 쪽 참조로 당기는
    것은 무조건 틀렸으므로 픽셀 경계 구간과 무관하게 열린다."""
    try:
        if intent_outfit:
            return True
        return _content_change_gate(face_n, person_n)
    except Exception:
        return False


def _bg_gate_open(bg_n, intent_scene=False) -> bool:
    """배경 게이트 최종 판정. 프롬프트가 장면 변경을 지시하면 무조건 닫는다
    (배경이 달라진 건 의도다). 없으면 기존 하드 게이트(무릎 안만 열림)."""
    try:
        if intent_scene:
            return False
        return bg_n is not None and bg_n <= _DRIFT_NORM_KNEE
    except Exception:
        return False


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
