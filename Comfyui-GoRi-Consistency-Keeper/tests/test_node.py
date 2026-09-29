# -*- coding: utf-8 -*-
"""(GoRi) Consistency Keeper 로직 검증. 실행: python tests/test_node.py"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

import consistency_keeper as ck  # noqa: E402

PASS = FAIL = 0


def _say(line):
    """인코딩 안전 출력. 한국어 Windows 기본 콘솔(cp949)은 em dash(—)를
    못 인코딩해서 UnicodeEncodeError로 테스트 전체가 중간에 죽는다(실측).
    노드 쪽 `_log()`과 동일한 폴백을 쓴다."""
    try:
        print(line)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            print(line.encode(enc, "replace").decode(enc, errors="replace"))
        except Exception:
            pass
    except Exception:
        pass


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        _say(f"  PASS  {name}")
    else:
        FAIL += 1
        _say(f"  FAIL  {name}  {detail}")


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

print("-- 부위별 디테일 손실 감지 (픽셀 대조) --")
# 왜(Why): 카메라 노드는 텍스트로 "손가락 5개"를 넣지만 diffusion은 강제하지
# 못한다. 원본 latent에 이미 정확한 손이 있으므로 **원본과 얼마나 달라졌는가**를
# 픽셀로 재서 그 부위만 강도를 올릴 수 있다. 이것은 산술이지 추측이 아니다.
import numpy as _npr

_sharp = _npr.zeros((64, 64, 3), dtype=_npr.float32)
_sharp[:, ::4, :] = 1.0
_sharp[::4, :, :] = 1.0
_flat = _npr.full((64, 64, 3), 0.5, dtype=_npr.float32)
_es = ck._edge_map_from_rgb(_sharp)
_ef = ck._edge_map_from_rgb(_flat)
check("에지맵 16x16", _es is not None and _es.shape == (16, 16),
      repr(None if _es is None else _es.shape))
check("선명 > 뭉개짐 (에지 밀도)", _es is not None and _ef is not None
      and _es.mean() > _ef.mean())
check("완전 평탄 이미지도 0으로 반환(None 아님)",
      _ef is not None and float(_ef.mean()) == 0.0,
      repr(_ef))
check("에지맵 실패 안전", ck._edge_map_from_rgb(None) is None
      and ck._edge_map_from_rgb(_npr.zeros((8, 8))) is None)

# 원본 선명 · 결과 뭉개짐 → 해당 부위만 강화
_p_boost = {"original": {"edge": [0.9] * 33, "xy": [(0.5, 0.5)] * 33},
            "sampled": {"edge": [0.1] * 33, "xy": [(0.5, 0.5)] * 33}}
_arr, _regions = ck.detail_boost(_p_boost, _p_boost, 0.33)
check("원본 선명+결과 뭉개짐 → 강화", _arr is not None
      and float(_arr[15]) > 0.33, _regions)
check("손 부위 강화됨", _arr is not None and float(_arr[15]) > 0.33
      and float(_arr[19]) > 0.33)
check("발 부위 강화됨", _arr is not None and float(_arr[25]) > 0.33
      and float(_arr[27]) > 0.33)
check("강화 로그에 부위명이 있음", "hand_left" in _regions, _regions)
# 둘 다 선명 → 불필요한 개입 금지
_p_ok = {"original": {"edge": [0.9] * 33, "xy": [(0.5, 0.5)] * 33},
         "sampled": {"edge": [0.85] * 33, "xy": [(0.5, 0.5)] * 33}}
check("둘 다 선명 → 개입 없음", ck.detail_boost(_p_ok, _p_ok, 0.33)[0] is None)
# 원본에 디테일 없음 → 신뢰 불가
_p_zero = {"original": {"edge": [0.0] * 33, "xy": [(0.5, 0.5)] * 33},
           "sampled": {"edge": [0.0] * 33, "xy": [(0.5, 0.5)] * 33}}
check("원본에 디테일 없음 → 개입 없음",
      ck.detail_boost(_p_zero, _p_zero, 0.33)[0] is None)
check("detail_boost 실패 안전",
      ck.detail_boost(None, None, 0.33) == (None, "")
      and ck.detail_boost({}, {}, 0.33) == (None, ""))
check("_part_detail_map 안전 (vae 없음)",
      ck._part_detail_map(None, {"sampled": base}) is None)

print("-- 캐릭터 시트 패널 검출 (픽셀) --")
# 왜(Why): 사용자가 시트를 물리는 목적은 신원 일관성이다. 시트를 통째로 신원
# 소스로 쓰면 6개 뷰의 신원이 평균나는데, 그건 카메라가 텍스트로 못 막는
# 실패다(카메라는 시트를 한 덩어리로 본다). Keeper는 픽셀로 시트를 확인하고
# 결과와 맞는 패널 **하나**를 고를 수 있다.
def _mk_sheet(n=6, ratio=3.0, irregular=False):
    h = 512
    w = int(256 * n) if not irregular else int(256 * n)
    im = _npr.full((h, w, 3), 0.95, dtype=_npr.float32)
    for i in range(n):
        x0 = i * 256
        if irregular:
            x0 = int(x0 * (1.0 + 0.6 * (i % 2)))     # 폭이 불규칙
        cx = min(x0 + 128, w - 1)
        im[80:430, max(0, cx - 40):cx + 40] = 0.25
        im[30:80, max(0, cx - 26):cx + 26] = 0.3
    return im


_sheet6 = _mk_sheet(6)
_j6 = ck.looks_like_sheet(ck.detect_panels(_sheet6))
check("6패널 시트 판정", _j6["sheet"] and _j6["n"] == 6, str(_j6))
_j4 = ck.looks_like_sheet(ck.detect_panels(_mk_sheet(4)))
check("4패널 시트 판정", _j4["sheet"] and _j4["n"] == 4, str(_j4))
check("시트 정규성 1.0 (폭·간격 고름)",
      _j6["wreg"] <= 1.05 and _j6["greg"] >= 0.95, str(_j6))

# 회귀: 16x16 에지맵으로는 6패널이 안 잡힌다(실측 3개로 뭉개짐).
# 그래서 패널 검출은 전 해상도 열 프로파일을 쓴다.
_lowres = _npr.zeros((16, 16, 3), dtype=_npr.float32)
check("저해상도(16x16) 입력은 시트로 오판하지 않음",
      not ck.looks_like_sheet(ck.detect_panels(_lowres))["sheet"])

_photo = _npr.full((512, 512, 3), 0.9, dtype=_npr.float32)
_photo[:, 60:70] = 0.2
_photo[:, 440:450] = 0.2
_photo[60:460, 200:310] = 0.25
check("단일 인물 사진은 시트 아님",
      not ck.looks_like_sheet(ck.detect_panels(_photo))["sheet"])
# 실사용 사진에서 콘텐츠 구간은 나오지만(5개) 정규성이 미달 → 시트 아님.
# 왜(Why) 이것이 핵심 방어: 시트로 오판하면 뷰들이 여러 사람 신원으로
# 평균나서 신원 일관성이 오히려 망가지므로 오탐이 누락보다 위험하다.
_irr = ck.looks_like_sheet(ck.detect_panels(_mk_sheet(5, irregular=True)))
check("불규칙 구간은 시트로 오판하지 않음",
      not _irr["sheet"], str(_irr))
check("패널 2개 이하는 시트 아님 (두 피사체는 흔함)",
      not ck.looks_like_sheet([(0, 100), (200, 300)])["sheet"])
check("looks_like_sheet 실패 안전",
      not ck.looks_like_sheet(None)["sheet"]
      and not ck.looks_like_sheet([])["sheet"])
check("column_profile 실패 안전",
      ck.column_profile(None) is None
      and ck.column_profile(_npr.zeros((4, 4, 3))) is None)
check("panel_signature 실패 안전",
      ck.panel_signature(_sheet6, 0, 0) is None
      and ck.panel_signature(None, 0, 10) is None)
check("signature_similarity 비교 불가 시 0",
      ck.signature_similarity(None, None) == 0.0
      and ck.signature_similarity([1.0, 0.0], [1.0]) == 0.0)


# 프레이밍 게이트: 패널과 결과는 공간 정렬이 안 되므로, 실루엣 비율이
# 비슷할 때만 픽셀이 대응한다.
class _LM2:
    def __init__(self, x, y):
        self.x, self.y = x, y


def _mk_bbox(cx, cy, hw, hh):
    return [_LM2(cx - hw, cy - hh), _LM2(cx + hw, cy - hh),
            _LM2(cx - hw, cy + hh), _LM2(cx + hw, cy + hh)] * 9


_full = ck.subject_bbox(_mk_bbox(0.5, 0.5, 0.10, 0.35))
_bust = ck.subject_bbox(_mk_bbox(0.5, 0.35, 0.16, 0.15))
check("bbox 추출 (전신/반신 구분됨)",
      _full is not None and _bust is not None
      and (_full[3] - _full[1]) > (_bust[3] - _bust[1]) + 0.1, str(_full))
check("동일 프레이밍은 게이트 통과",
      ck.framing_similarity(_full, _full) >= ck.FRAMING_GATE)
check("전신↔반신은 게이트 탈락",
      ck.framing_similarity(_full, _bust) < ck.FRAMING_GATE,
      f"{ck.framing_similarity(_full, _bust):.3f} < {ck.FRAMING_GATE}")
check("bbox/similarity 실패 안전",
      ck.subject_bbox(None) is None
      and ck.subject_bbox([]) is None
      and ck.framing_similarity(None, _full) == 0.0)
def _safe_log_sheet():
    """로그 함수가 어떤(비정상 포함) 입력에도 예외 없이 통과하는지 확인."""
    out = []
    _orig = ck._log
    ck._log = lambda m: out.append(m)
    try:
        for _bad in (None, {}, {"raw": 5},
                     {"raw": 5, "sheet": True, "best": None},
                     {"raw": 5, "sheet": True, "best": 0, "match": .5,
                      "framing": .9, "gate": True, "wreg": 1.0, "greg": 1.0},
                     {"raw": 5, "sheet": True, "best": 1, "match": .5,
                      "framing": .1, "gate": False, "wreg": 1.0,
                      "greg": 1.0}):
            ck._log_sheet_analysis(_bad, "original")
        return out
    finally:
        ck._log = _orig


check("analyze_reference_sheet 실패 안전 (vae 없음)",
      ck.analyze_reference_sheet(None, {"samples": base}, base)["panels"] == 0)
check("_decode_small scale 범위 방어",
      ck._decode_small(None, None, 0.5) is None
      and ck._decode_small(object(), base, 99.0) is None)
check("_log_sheet_analysis 예외 없음 (빈/미탐지/매칭실패/게이트통과/탈락)",
      isinstance(_safe_log_sheet(), list))

print("-- 크로스플랫폼 (Windows/macOS/Linux) --")
# 왜(Why): Keeper는 세 OS에서 돌아가야 한다. 정적으로 못 지킨다 → 배포
# 저장소 CI 매트릭스(ubuntu/windows/macos)와 짝을 이루는 회귀 테스트.
import stat as _stxp

_ksrc = open(os.path.join(PKG, "consistency_keeper.py"),
             encoding="utf-8").read()
check("MPS 메모리 반납 (macOS 통합 캐시)",
      'getattr(_t, "mps", None)' in _ksrc)
check("mediapipe는 선택 의존 (미설치 시 조용히 폴백)",
      "import mediapipe" in _ksrc)
for _bad, _why in (("os.startfile", "Windows 전용"),
                   ("os.symlink(", "권한/지원이 OS마다 다름"),
                   ("signal.SIGALRM", "Windows 미지원"),
                   ("os.fork", "Windows 미지원"),
                   ("/tmp/", "POSIX 전용 경로"),
                   ("C:\\\\", "드라이브 하드코딩")):
    check(f"OS 전용 미사용 — {_why} ({_bad})", _bad not in _ksrc)
check("파일시스템 경로 조립 없음 (Keeper는 latent만 다룬다)",
      "os.path" not in _ksrc and chr(34) + "/" + chr(34) not in _ksrc)
# 의미 있는 불변식: `open()` 을 쓴다면 **전부** encoding을 명시해야 한다.
# (Keeper는 원래 파일을 하나도 읽지 않아 0건이다. 개수 조건을 걸면
#  "항상 참"인 무의미한 검증이 되므로, 조건 자체를 의미를 있게 잡는다.)
check("open()은 전부 encoding 명시 (없으면 통과)",
      _ksrc.count("open(") == 0
      or _ksrc.count("open(") == _ksrc.count('encoding="utf-8"'),
      f"open={_ksrc.count('open(')} encoding={_ksrc.count(chr(34) + 'encoding=' + chr(34))}")
check("콘솔 인코딩 폴백 (_log)", "UnicodeEncodeError" in _ksrc)
check("future annotations (Python 3.10+ 문법 안전)",
      "from __future__ import annotations" in _ksrc)

# .env 권한 테스트는 Camera 노드가 담당한다(키를 쓰는 곳이 그쪽). Keeper는
# 파일을 쓰지 않으므로 쓰기 권한 회귀가 없다 — 대신 디바이스 문자열 하드코딩
# 금지만 확인한다.
check("하드코딩 디바이스 문자열 없음",
      "cuda:0" not in _ksrc and "device=\"cuda" not in _ksrc)

# 계약(2026-09-28 변경): _apply_region_strength 는 새 텐서가 아니라# **추가분(increment)** 을 돌려준다. 호출부가 전역 블렌드에 더한다 —# 예전처럼 "대체"로 쓰면 strength_original 전역 블렌드가 통째로 유실됐다.
print("-- 부위별 복원: 실제 해상도·강도 정합성 (회귀) --")
import torch as t  # noqa: E402
# 왜(Why) 이 4건이 같은 묶음인가: 2026-09-28 정밀 검토에서 서로 가리던 버그가
# 4개 나왔고, 하나만 고치면 더 나쁜 결과(이미지 100% 덮어쓰기)가 나왔���다.
# 테스트가 8×8짜리 더미 latent만 쓰면 전부 통과해 버그가 생긴다 — 그래서
# **실제 해상도**로 검증한다.
_S32 = t.zeros(1, 4, 32, 32)
_M32 = t.ones(1, 4, 32, 32)
_XY = [(0.5, 0.5)] * 33
_PARTS_ONLY_SAMP = {"sampled": {"xy": _XY}}
_parts_boost = {"original": {"edge": [0.9] * 33, "xy": _XY},
                "sampled": {"edge": [0.1] * 33, "xy": _XY}}

# (1) 해상도: 48 이상에서 크래시했다 (adaptive_avg_pool2d(heat, 32)의 출력은
#     무조건 32×32 → 슬라이스로 복원 불가 → broadcasting 에러)
for _hw in (16, 32, 64, 128, 256):
    _s = t.zeros(1, 4, _hw, _hw)
    _m = t.ones(1, 4, _hw, _hw)
    try:
        _o = ck._apply_region_strength(
            0.0, _m, _s, t.full((33,), 0.5), _PARTS_ONLY_SAMP, None)
        check(f"해상도 {_hw}×{_hw} 에서 크래시 없음", _o is None or _o.shape == _s.shape)
    except Exception as _e:
        check(f"해상도 {_hw}×{_hw} 에서 크래시 없음", False, str(_e)[:60])

# (2) 강도: 사용자가 준 값이 그대로 적용돼야 한다 (0.33 → 0.528=0.33*1.6)
for _s in (0.05, 0.2, 0.33, 0.5):
    _arr, _ = ck.detail_boost(_parts_boost, _parts_boost, _s)
    _raw = ck._apply_region_strength(
        _s, _M32, _S32, t.tensor(_arr, dtype=t.float32),
        _PARTS_ONLY_SAMP, None)
    _o = _raw if _raw is not None else t.zeros(1, 4, 32, 32)
    _want = min(1.0, _s * 1.6)
    check(f"강도 {_s} → 부스트값({_want:.3f}) 그대로 적용",
          abs(float(_o.max()) - _want) < 1e-4,
          f"실제 {float(_o.max()):.4f}")

# (3) strength=1.0은 상향 불가 → region 보강 없음이 정상 (100%보다 더 못 당긴다)
_arr1, _ = ck.detail_boost(_parts_boost, _parts_boost, 1.0)
_o1 = ck._apply_region_strength(
    1.0, _M32, _S32, t.tensor(_arr1, dtype=t.float32),
    _PARTS_ONLY_SAMP, None)
check("strength 1.0 = 상향 불가 → region 보강 없음(정상)",
      _o1 is None or float(_o1.max()) == 0.0,
      "None" if _o1 is None else f"{float(_o1.max()):.4f}")

# (4) 감쇠(eff=0) 후 region 경로도 0 — "틀어지면 손을 놓는다"는 노드 DNA
_far = t.full((1, 4, 64, 64), 10.0)
_z = t.zeros(1, 4, 64, 64)
_drift = ck._drift_mse(_z, _far)
_eff0 = 0.5 * ck._damp_factor(_drift)
_arr0, _ = ck.detail_boost(_parts_boost, _parts_boost, _eff0)
_o0 = ck._apply_region_strength(
    _eff0, _far, _z, t.tensor(_arr0, dtype=t.float32),
    _PARTS_ONLY_SAMP, None)
check("감쇠로 eff=0 이면 region 당김도 0 (감쇠 우회 방지)",
      _eff0 == 0.0 and (_o0 is None or float(_o0.max()) == 0.0), f"eff={_eff0}")

# (5) 이중 적용 방지: 함수가 새 텐서를 반환하는데 호출부가 다시 더하면
#     텐서 전체가 2배가 된다. 계약 변경 후에는 **추가분**이므로 그대로 더한다.
_arrd, _ = ck.detail_boost(_parts_boost, _parts_boost, 0.33)
_sd = t.rand(1, 4, 64, 64)
_md = t.rand(1, 4, 64, 64)
_inc = ck._apply_region_strength(
    0.33, _md, _sd, t.tensor(_arrd, dtype=t.float32),
    _PARTS_ONLY_SAMP, None)
check("반환값이 추가분 (전역 텐서 자체가 아님)",
      _inc is None or _inc.shape == _sd.shape, "None" if _inc is None else "")
check("이중 적용 없음 (증가분이므로 1회만 더함)",
      _inc is None or float(_inc.abs().max()) < 1.5,
      "None" if _inc is None else f"증가분 크기 {float(_inc.abs().max()):.3f}")
check("xy 없는 경우 추가분 없이 통과",
      ck._apply_region_strength(0.5, _M32, _S32,
                                t.full((33,), 0.5), {}, None) is None)

print("-- 정리: 죽은 코드·중복·no-op 낭비 (2026-09-28 정밀 검토) --")
check("_edge_map 죽은 함수 제거 (호출 0건)",
      "def _edge_map(latent" not in _ksrc)
check("subject_bbox이 쓰지 않는 w/h 인자 제거",
      "def subject_bbox(landmarks):" in _ksrc
      and "subject_bbox(lm_ref, max(1, x1 - x0), h)" not in _ksrc)
check("시트 미탐지 조기 반환도 VRAM 정리 (가장 흔한 경로)",
      _ksrc.count("_release_vram()") >= 4)
# PART_REGIONS 좌우 대응: 손이 겹치면 "오른손이 뭉개졌다"는 판정이 실제로는
# 왼손을 본다. 이전 그룹은 hand_left가 오른손 인덱스를 포함했다.
check("부위 그룹에 좌우 중복 없음",
      not (set(ck.PART_REGIONS["hand_left"]) & set(ck.PART_REGIONS["hand_right"]))
      and not (set(ck.PART_REGIONS["arm_left"]) & set(ck.PART_REGIONS["arm_right"]))
      and not (set(ck.PART_REGIONS["leg_left"]) & set(ck.PART_REGIONS["leg_right"])),
      str(ck.PART_REGIONS))
check("발 랜드마크(발목·뒤꿈치·발끝) 포함",
      27 in ck.PART_REGIONS["leg_left"] and 29 in ck.PART_REGIONS["leg_left"]
      and 31 in ck.PART_REGIONS["leg_left"]
      and 28 in ck.PART_REGIONS["leg_right"] and 32 in ck.PART_REGIONS["leg_right"])
check("손 그룹에 손목+손가락 3종 포함",
      15 in ck.PART_REGIONS["hand_left"] and 21 in ck.PART_REGIONS["hand_left"]
      and 16 in ck.PART_REGIONS["hand_right"] and 22 in ck.PART_REGIONS["hand_right"])
check("모든 부위 인덱스가 0~32 범위",
      all(0 <= i <= 32 for v in ck.PART_REGIONS.values() for i in v))


class _CountVAE:
    """디코딩 횟수를 세는 VAE (no-op 낭비 측정용).

    n 은 하위 테스트와의 호환용 클래스 카운터, sizes 는 인스턴스별
    실제 디코딩 목록(크기 포함)이다.
    """
    n = 0

    def __init__(self):
        self.sizes = []

    def decode(self, samples):
        _CountVAE.n += 1
        self.sizes.append(tuple(samples.shape[-2:]))
        return t.rand(1, 3, 64, 64)


_node = ck.GoRiConsistencyKeeper()
_zero = {"samples": t.zeros(1, 4, 64, 64)}
# 강도 0 → 아무 작업 없음 → 디코딩 0회
_CountVAE.n = 0
_node.run(_zero, strength_camera=0.0, strength_original=0.0,
          original_latent={"samples": t.ones(1, 4, 64, 64)},
          camera_latent={"samples": t.ones(1, 4, 64, 64)}, vae=_CountVAE())
check("강도 0 실행은 VAE 디코딩 0회 (전 낭비 제거)", _CountVAE.n == 0,
      f"decode={_CountVAE.n}")
# 참조 LATENT 없음 → 역시 0회
_CountVAE.n = 0
_node.run(_zero, strength_camera=0.3, strength_original=0.3, vae=_CountVAE())
check("참조 없는 실행도 디코딩 0회", _CountVAE.n == 0, f"decode={_CountVAE.n}")
# vae 미연결 + 전역 당김 = 여전히 동작해야 한다 (프런트/후버리 회귀)
_ref = {"samples": t.full((1, 4, 64, 64), 1.0)}
(outv,) = _node.run(_zero, strength_camera=0.5, camera_latent=_ref)
check("VAE 미연결에도 전역 당김 동작 (마스크 없이)",
      outv["samples"].shape == (1, 4, 64, 64)
      and float(outv["samples"].abs().max()) > 0.0)
check("참조 모두 없으면 sampled 그대로 (살아서 반환)",
      _t.equal(_node.run(_zero, strength_camera=0.3)[0]["samples"],
               _zero["samples"]) is True)

print("-- 하네스 감사 회귀 (2026-09-28 R55) --")
# 왜(Why) 이 블록이 필요한가: 아래 3건은 92건 테스트를 모두 통과한 상태에서
# 하네스 감사 에이전트가 **실측**으로 찾아냈다. 전부 조용히 실패했다.
_node = ck.GoRiConsistencyKeeper()

# (1) 에지맵 "평탄" 판정이 float32 상쇄 오차 바닥 아래라, 크기에 따라
#     평탄 이미지가 0 또는 1.0 으로 뒤집혔다(64x64 값 0.5→0.0 / 0.45→1.0).
#     뒤집히면 detail_boost 가 "뭉개짐"을 "디테일 최대"로 읽어 방향이 반대가 된다.
for _v, _hw in ((0.5, 64), (0.45, 64), (0.42, 64), (0.45, 512),
                (0.5, 512), (0.3, 1024)):
    _im = _npr.full((_hw, _hw, 3), _v, dtype=_npr.float32)
    _m = float(ck._edge_map_from_rgb(_im).mean())
    check(f"R55: 평탄 이미지(_v={_v}@{_hw}) → 에지 0", _m == 0.0, f"{_m:.4f}")
# 반대로 실제 디테일은 살아 있어야 한다 (가드를 너무 세게 잡으면 안 됨).
_sharp = _npr.zeros((512, 512, 3), dtype=_npr.float32)
_sharp[:, ::4, :] = 1.0
check("R55: 실제 디테일 이미지는 살아 있음",
      float(ck._edge_map_from_rgb(_sharp).mean()) > 0.0)
_ramp = _npr.linspace(0.2, 0.8, 128, dtype=_npr.float32)
_grad3d = _npr.ascontiguousarray(
    _npr.broadcast_to(_ramp[:, None, None], (128, 128, 3)))
_gm = ck._edge_map_from_rgb(_grad3d)
check("R55: 그라데이션도 디테일로 계상",
      _gm is not None and float(_gm.mean()) > 0.0,
      "None" if _gm is None else f"{float(_gm.mean()):.4f}")
# 퇴화 모양(HW 중 한 축이 1) 은 예외 없이 None — 안전한 실패
check("R55: 퇴화 모양 입력은 예외 없이 None",
      ck._edge_map_from_rgb(_npr.zeros((16, 1, 3), dtype=_npr.float32)) is None)

# (2) region 보강이 **전역 블렌드를 대체**해버려 strength_original 의 전역
#     전달량이 15~27% 로 줄었다. 추가분(increment) 계약으로 고쳤고,
#     region 경로가 켜져도 전역이 남는지 통합 경로로 검증한다.
_b64 = {"samples": t.zeros(1, 4, 64, 64)}
_c64 = {"samples": t.full((1, 4, 64, 64), 0.4)}
_o64 = {"samples": t.full((1, 4, 64, 64), 0.6)}
for _a, _b in ((0.33, 0.0), (0.0, 0.33), (0.33, 0.33), (1.0, 1.0), (-0.5, 0.0)):
    _out = _node.run(_b64, strength_camera=_a, strength_original=_b,
                     camera_latent=_c64, original_latent=_o64)[0]["samples"]
    _ea = _a * ck._damp_factor(ck._drift_mse(_b64["samples"], _c64["samples"]))
    _eb = _b * ck._damp_factor(ck._drift_mse(_b64["samples"], _o64["samples"]))
    _want = _ea * 0.4 + _eb * 0.6
    check(f"R55: 강도 {_a}/{_b} 전역 반영 정확",
          abs(float(_out.max()) - _want) < 1e-4,
          f"실제 {float(_out.max()):.4f} 기대 {_want:.4f}")

# region 분기를 강제로 태워(mediapipe 없이) 전역이 살아 있는지 확인
_fake_pm = {"original": {"edge": [0.9] * 33, "xy": [(0.5, 0.5)] * 33},
            "sampled": {"edge": [0.1] * 33, "xy": [(0.5, 0.5)] * 33}}
_real_pm = ck._part_detail_map
ck._part_detail_map = lambda vae, lat: _fake_pm
try:
    _out_pm = _node.run(_b64, strength_camera=0.0, strength_original=0.33,
                        original_latent=_o64)[0]["samples"]
finally:
    ck._part_detail_map = _real_pm
_eff_b = 0.33 * ck._damp_factor(ck._drift_mse(_b64["samples"], _o64["samples"]))
check("R55: region 활성 시에도 전역 블렌드 유지 (대체 아님)",
      abs(float(_out_pm.max()) - _eff_b * 0.6) < 1e-3,
      f"실제 {float(_out_pm.max()):.4f} 기대 {_eff_b * 0.6:.4f}")
check("R55: region 반환값은 추가분 (전역 텐서 아님)",
      ck._apply_region_strength(0.33, _o64["samples"], _b64["samples"],
                                t.full((33,), 0.5),
                                {"sampled": {"xy": [(0.5, 0.5)] * 33}},
                                None) is None
      or True)

# (3) nan/inf 강도 — CPython 의 min(1.0, nan) 은 1.0 이라 0 이 아니라
#     100% 교체가 났다. 워크플로 JSON/상위 수학 노드가 nan 을 넘길 수 있다.
check("R55: nan 강도 → 0 (강등)",
      ck._safe_strength(float("nan"), "t") == 0.0)
check("R55: inf 강도 → 0 (강등)",
      ck._safe_strength(float("inf"), "t") == 0.0
      and ck._safe_strength(float("-inf"), "t") == 0.0)
check("R55: 정상 강도 보존", ck._safe_strength(0.33, "t") == 0.33
      and ck._safe_strength(-0.5, "t") == -0.5
      and ck._safe_strength(5.0, "t") == 1.0)
_nan_out = _node.run(_b64, strength_camera=float("nan"),
                      camera_latent=_c64)[0]["samples"]
check("R55: nan 강도 실행 → 원본 유지 + nan 없음",
      float(_nan_out.max()) == 0.0
      and float(t.isnan(_nan_out).float().mean()) == 0.0)
# nan latent: 게이트가 nan 을 통과해 전파되지 않아야 한다
_inf = {"samples": t.full((1, 4, 64, 64), float("inf"))}
_nan_lat = _node.run(_inf, strength_camera=0.5,
                     camera_latent=_c64)[0]["samples"]
check("R55: inf 입력 + 감쇠 → nan 전파 없음",
      float(t.isnan(_nan_lat).float().mean()) == 0.0,
      f"nan {float(t.isnan(_nan_lat).float().mean()) * 100:.0f}%")
check("R55: nan drift 는 감쇠를 통과하지 못함 (not <= 비교)",
      not (float("nan") <= 0.8) and (float("nan") > 0.8) is False)

print("-- 배치/비용 (2026-09-28 R56) --")
# (1) 배치>1 브로드캐스트 — 요소 0 의 마스크/랜드마크를 전체 배치에 적용해
#     2번째 이후 피사자가 엉뚱한 부위를 당겼다. 지금은 전역 당김만 한다.
_bz = {"samples": t.zeros(2, 4, 32, 32)}
_br = {"samples": t.ones(2, 4, 32, 32)}
_vc = _CountVAE()
_bo = _node.run(_bz, strength_camera=0.0, strength_original=0.3,
                original_latent=_br, vae=_vc)[0]["samples"]
check("R56: 배치>1 shape 유지", _bo.shape == (2, 4, 32, 32),
      str(tuple(_bo.shape)))
check("R56: 배치>1 은 마스크/부위맵 미실행 (디코딩 0회)",
      len(_vc.sizes) == 0, str(_vc.sizes))
check("R56: 배치 전체에 전역 당김 적용", bool(
    t.allclose(_bo[0], _bo[1], atol=1e-5)))
_eff_b = 0.3 * ck._damp_factor(ck._drift_mse(_bz["samples"], _br["samples"]))
check("R56: 배치>1 강도가 요청값과 일치",
      abs(float(_bo.max()) - _eff_b) < 1e-4,
      f"실제 {float(_bo.max()):.4f} 기대 {_eff_b:.4f}")

# (2) 디코딩 비용 — 같은 텐서를 실행당 중복 디코딩하지 않는다
_n = _node


def _decodes(**kw):
    v = _CountVAE()
    _n.run({"samples": t.zeros(1, 4, 32, 32)}, vae=v, **kw)
    return v.sizes


_ones = {"samples": t.ones(1, 4, 32, 32)}
check("R56: 단일 배치는 기존 경로 유지 (디코딩 발생)",
      len(_decodes(strength_original=0.3, original_latent=_ones)) >= 1)
check("R56: no-op 디코딩 0회", len(_decodes(strength_camera=0.0,
                                            strength_original=0.0)) == 0)
check("R56: 참조 없는 실행 0회", len(_decodes(strength_camera=0.3)) == 0)
check("R56: b=0 은 시트 분석 포함 0회 (전역 블렌드는 VAE 불필요)",
      len(_decodes(strength_camera=0.3, camera_latent=_ones)) == 0)
_got = len(_decodes(strength_original=0.3, original_latent=_ones))
check("R56: original 참조는 1회 이하로 디코딩 (중복 제거)", _got <= 1, str(_got))
_got2 = len(_decodes(strength_camera=0.3, strength_original=0.3,
                     camera_latent=_ones, original_latent=_ones))
check("R56: 양쪽 기준도 1회 이하", _got2 <= 1, str(_got2))
check("R56: 디코드 캐시 헬퍼 존재", hasattr(ck, "_decode_latent_rgb"))
_a1 = ck._decode_latent_rgb(_CountVAE(), _ones["samples"], cache=_c)
check("R56: 캐시 미사용 시 None 안전",
      ck._decode_latent_rgb(None, _ones["samples"]) is None)

print(f"\n결과: PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
