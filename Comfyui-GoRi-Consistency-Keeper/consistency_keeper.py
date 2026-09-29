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


def _person_mask_for_latent(vae, sampled):
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
        with _t.no_grad():
            img = vae.decode(sampled)
        if hasattr(img, "detach"):
            img = img.detach().cpu()
        arr = img.numpy() if hasattr(img, "numpy") else _np.asarray(img)
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.ndim == 4:
            arr = arr[0]
        if arr.ndim != 3:
            return None
        arr = _np.clip(arr, 0.0, 1.0)
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
        # 디코드 잔재 정리 (VRAM) 후 반환.
        try:
            del img, arr, seg, mask
        except Exception:
            pass
        _release_vram()
        return m
    except Exception:
        return None



def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        import sys as _sys
        enc = getattr(_sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, "replace").decode(enc, errors="replace"), flush=True)


def _release_vram() -> None:
    """GPU 조각 반납. 마스크용 VAE 디코드 잔재 정리 (실패 무시)."""
    try:
        import gc as _gc
        _gc.collect()
        try:
            import torch as _t
            if hasattr(_t, "cuda") and _t.cuda.is_available():
                _t.cuda.empty_cache()
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
        try:
            a = max(-1.0, min(1.0, float(strength_camera)))
        except (ValueError, TypeError):
            a = 0.0
        try:
            b = max(-1.0, min(1.0, float(strength_original)))
        except (ValueError, TypeError):
            b = 0.0
        out = sampled.clone() if hasattr(sampled, "clone") else sampled
        # 인체 마스크 (없으면 전역 당김). 1회 계산해 양쪽 기준에 공유.
        _mask = _person_mask_for_latent(vae, sampled)
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
                if drift > 0.8:
                    eff = strength * _damp_factor(drift)
                    _log(f"[GoRi Consistency Keeper] ⚠ {name} 기준과 결과물 구도가 많이 "
                         f"다름 — 당김 자동 감쇠 {strength:.2f}→{eff:.2f}. "
                         f"같은 구도 기준 사용 권장")
            mismatch = _lighting_mismatch(sampled, matched)
            if mismatch is not None and mismatch > 1.0:
                _old_eff = eff
                eff = eff * _light_damp_factor(mismatch)
                _log(f"[GoRi Consistency Keeper] ⚠ {name} 조명 흐름 불일치 "
                     f"({mismatch:.2f}) — 당김 추가 감쇠 {_old_eff:.2f}→{eff:.2f}")
            if _mask is not None:
                out = out + eff * _mask * (matched - sampled)
            else:
                out = out + eff * (matched - sampled)
        _release_vram()
        return ({"samples": out},)
