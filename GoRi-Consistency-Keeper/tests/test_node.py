# -*- coding: utf-8 -*-
"""(GoRi) Consistency Keeper 로직 검증. 실행: python tests/test_node.py"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

import consistency_keeper as ck  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


try:
    import torch as _t
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

from __init__ import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
check("클래스 매핑",
      NODE_CLASS_MAPPINGS.get("GoRi_ConsistencyKeeper") is ck.GoRiConsistencyKeeper)
check("표시 이름",
      NODE_DISPLAY_NAME_MAPPINGS.get("GoRi_ConsistencyKeeper")
      == "(GoRi) Consistency Keeper")
check("출력 계약",
      ck.GoRiConsistencyKeeper.RETURN_TYPES == ("LATENT",)
      and ck.GoRiConsistencyKeeper.RETURN_NAMES == ("latent_out",))
check("입력 계약",
      ck.GoRiConsistencyKeeper.INPUT_TYPES()["required"].get("sampled_latent")
      == ("LATENT",)
      and "strength_camera" in ck.GoRiConsistencyKeeper.INPUT_TYPES()["required"]
      and "strength_original" in ck.GoRiConsistencyKeeper.INPUT_TYPES()["required"]
      and "original_latent" in ck.GoRiConsistencyKeeper.INPUT_TYPES()["optional"]
      and "camera_latent" in ck.GoRiConsistencyKeeper.INPUT_TYPES()["optional"])

if not HAS_TORCH:
    print("torch 없음 — 수치 테스트 생략")
else:
    node = ck.GoRiConsistencyKeeper()
    base = _t.zeros(1, 4, 8, 8)
    cam = _t.ones(1, 4, 8, 8)
    orig = _t.full((1, 4, 8, 8), 0.5)

    (out,) = node.run({"samples": base}, strength_camera=0.5,
                      strength_original=0.5,
                      camera_latent={"samples": cam},
                      original_latent={"samples": orig})
    _d1 = ck._damp_factor(1.0)
    _d2 = ck._damp_factor(0.25)
    expect = base + 0.5 * _d1 * (cam - base) + 0.5 * _d2 * (orig - base)
    check("블렌드 수식", _t.allclose(out["samples"], expect))

    (out0,) = node.run({"samples": base}, strength_camera=0.0,
                       strength_original=0.0,
                       camera_latent={"samples": cam},
                       original_latent={"samples": orig})
    check("강도 0은 원본 유지", _t.allclose(out0["samples"], base))

    big = _t.ones(1, 4, 16, 16)
    (outr,) = node.run({"samples": base}, strength_camera=1.0,
                       strength_original=0.0,
                       camera_latent={"samples": big})
    check("크기 달라도 리사이즈 후 당김",
          outr["samples"].shape == (1, 4, 8, 8)
          and _t.allclose(outr["samples"],
                          _t.ones(1, 4, 8, 8) * ck._damp_factor(1.0)))

    bad_batch = _t.ones(2, 4, 8, 8)
    (outb,) = node.run({"samples": base}, strength_camera=1.0,
                       strength_original=0.0,
                       camera_latent={"samples": bad_batch})
    check("배치 불일치는 건너뜀", _t.allclose(outb["samples"], base))

    (outn,) = node.run({"samples": base})
    check("기준 없으면 통과", _t.allclose(outn["samples"], base))

    try:
        node.run({"samples": None})
        check("빈 입력은 오류", False)
    except ValueError:
        check("빈 입력은 오류", True)

    check("틀어짐 측정", ck._drift_mse(base, cam) == 1.0)
    check("입력 불변 (원본 미수정)", _t.allclose(base, _t.zeros(1, 4, 8, 8)))
    grad = _t.zeros(1, 4, 8, 8)
    for _i in range(8):
        grad[:, :, :, _i] = float(_i) / 7.0
    check("조명 동일은 0 근처",
          (ck._lighting_mismatch(grad, grad) or 0.0) < 0.01)
    flip = _t.zeros(1, 4, 8, 8)
    for _i in range(8):
        flip[:, :, :, _i] = 1.0 - float(_i) / 7.0
    _lm = ck._lighting_mismatch(grad, flip)
    check("조명 반전은 큰 불일치", _lm is not None and _lm > 1.0, str(_lm))
    check("조명 게이트 계수", ck._light_damp_factor(0.5) == 1.0
          and ck._light_damp_factor(None) == 1.0
          and ck._light_damp_factor(1.5) == 0.5
          and ck._light_damp_factor(3.0) == 0.0)
    _req = ck.GoRiConsistencyKeeper.INPUT_TYPES()["required"]
    check("기본값 0.2", _req["strength_camera"][1]["default"] == 0.2
          and _req["strength_original"][1]["default"] == 0.2)
    far = _t.full((1, 4, 8, 8), 10.0)
    (outf,) = node.run({"samples": base}, strength_camera=0.5,
                       camera_latent={"samples": far})
    check("구도 불일치도 실행 생존", outf["samples"].shape == (1, 4, 8, 8))
    check("자동 감쇠 계수", ck._damp_factor(0.5) == 1.0
          and ck._damp_factor(None) == 1.0
          and 0.0 < ck._damp_factor(1.4) < 1.0
          and ck._damp_factor(3.0) == 0.0)
    (outd,) = node.run({"samples": base}, strength_camera=1.0,
                       camera_latent={"samples": far})
    check("큰 틀어짐은 당김 감쇠",
          _t.allclose(outd["samples"], base, atol=0.05))
    half = _t.full((1, 4, 8, 8), 0.5)
    (outn2,) = node.run({"samples": base}, strength_camera=-0.5,
                        camera_latent={"samples": half})
    check("음수 강도 (안티-레퍼런스)",
          _t.allclose(outn2["samples"], base - 0.5 * (half - base)))

print("-- 인체 마스크 가중 당김 --")
check("vae 없으면 마스크 None", ck._person_mask_for_latent(None, base) is None)


class _FakePose:
    def __init__(self, *a, **k):
        pass

    def process(self, img):
        import numpy as _np
        h, w = img.shape[0], img.shape[1]
        seg = _np.zeros((h, w), dtype=_np.float32)
        seg[h // 4:3 * h // 4, w // 4:3 * w // 4] = 0.9

        class _R:
            segmentation_mask = seg
            pose_landmarks = True
        return _R()

    def close(self):
        pass


import types as _types_m
_mp = _types_m.ModuleType("mediapipe")
_sol = _types_m.ModuleType("mediapipe.solutions")
_ps = _types_m.ModuleType("mediapipe.solutions.pose")
_ps.Pose = _FakePose
_sol.pose = _ps
_mp.solutions = _sol
_orig_mp = {k: sys.modules.get(k) for k in
            ("mediapipe", "mediapipe.solutions", "mediapipe.solutions.pose")}
sys.modules["mediapipe"] = _mp
sys.modules["mediapipe.solutions"] = _sol
sys.modules["mediapipe.solutions.pose"] = _ps


class _FakeVAE:
    def decode(self, samples):
        return _t.zeros(1, 3, 64, 64)


try:
    _mask = ck._person_mask_for_latent(_FakeVAE(), base)
    check("인체 마스크 생성", _mask is not None and tuple(_mask.shape) == (1, 1, 8, 8),
          repr(None if _mask is None else _mask.shape))
    check("마스크 중심 가중",
          _mask is not None and float(_mask[0, 0, 4, 4]) > float(_mask[0, 0, 0, 0]))
    (outm,) = node.run({"samples": base}, strength_camera=1.0,
                       camera_latent={"samples": cam}, vae=_FakeVAE())
    _c = float(outm["samples"][0, 0, 4, 4])
    _e = float(outm["samples"][0, 0, 0, 0])
    check("인체 부위만 당김", _c > _e + 0.2, f"c={_c:.3f} e={_e:.3f}")
finally:
    for _k, _v in _orig_mp.items():
        if _v is None:
            sys.modules.pop(_k, None)
        else:
            sys.modules[_k] = _v

print(f"\n결과: PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
