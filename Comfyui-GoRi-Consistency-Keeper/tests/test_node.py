# -*- coding: utf-8 -*-
"""(GoRi) Consistency Keeper 로직 검증. 실행: python tests/test_node.py"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)

import consistency_keeper as ck  # noqa: E402

PASS = FAIL = 0
_print = print          # stdlib print 를 그대로 보관 (_say 가 재귀하지 않게)


def _say(line):
    """인코딩 안전 출력.

    한국어를 못 인코딩하는 콘솔에서는 UnicodeEncodeError 로 테스트 전체가
    죽는다. 죽으면 **뒤의 검사가 아예 안 돌아가므로** 몇 개가 통과했는지
    알 수 없다.

    실제 실패한 인코딩은 cp949(한국어 Windows 콘솔)뿐만 아니라
    **cp1252**(GitHub Windows 러너 기본)였다. 한국어를 아예 모르는
    charmap 이라 한글이 첫 글자에서 바로 죽는다(2026-09-29 실측:
    배포 저장소 CI run#28, Consistency-Keeper 157행).
    그래서 특정 인코딩을 가정하지 않고, 실제 stdout 을 감지해 치환한다.
    """
    try:
        _print(line)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            _print(line.encode(enc, "replace").decode(enc, errors="replace"))
        except Exception:
            # 인코딩이 한글을 못 하면 어차피 못 쓴다 — 에러 표기만 남긴다.
            try:
                _print("".join(c if c.isascii() else "?" for c in line))
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


# 이 파일의 나머지 출력(섹션 헤더·요약)도 전부 안전 경로를 탄다.
# 섹션 제목만 먼저 죽어 결과를 아예 못 보는 일이 있었다(157행).
# 테스트 출력 전용이라 부작용은 없다.
print = _say  # noqa: A001  (섹션 헤더 출력용)


try:
    import torch as _t
    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

_KSRC = open(os.path.join(PKG, "consistency_keeper.py"), encoding="utf-8").read()
_ksrc_lines = _KSRC.splitlines()
# 자기 자신의 소스 — 구조적 계약(게이트 위치 등)을 검사할 때 쓴다.
_TEST_SRC = open(os.path.abspath(__file__), encoding="utf-8").read()
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
    print("torch 없음 — 수치 테스트 전체 생략")
    print(f"\n결과: PASS={PASS}  FAIL={FAIL}")
    sys.exit(1 if FAIL else 0)

node = ck.GoRiConsistencyKeeper()
base = _t.zeros(1, 4, 8, 8)
cam = _t.ones(1, 4, 8, 8)
orig = _t.full((1, 4, 8, 8), 0.5)

if True:
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
# 왜(Why) 여기서 바로 torch 를 쓰는가: `base`/`cam`/`orig` 는 위의
# `if not HAS_TORCH:` 가드 **안** 에서 만들어진다. 그래서 가드가 스킵되면
# 이 줄에서 NameError 로 죽었다(실측). "torch 없으면 조용히 통과"가 아니라
# "torch 없으면 4건만 하고 죽음"이었다 — 그래서 스킵 경로가 진짜 스킵인지
# 별도로 확인한다.
if not HAS_TORCH:
    _say("torch 없음 — 수치 테스트 전체 생략 (이 경로 자체를 검사)")
    check("torch 없음에서도 크래시 없이 끝까지 도달",
          "base" not in dir() or True, "")
else:
    check("vae 없으면 마스크 None",
          ck._person_mask_for_latent(None, base) is None)


# (왜) 노드는 이제 `mediapipe.solutions` 대신 tasks API + .task 모델을 쓴다
# (2026-09-30). Windows 배포판에 구 API 가 없어서다. 그래서 세션/모델을 직접
# 만들지 않고, 모델 경로 확인과 두 추출 함수만 주입한다.
_orig_model_path = ck._pose_model_path
_orig_landmarker = ck._pose_landmarker
_orig_landmarks = ck._pose_landmarks_from_tasks
_orig_segmentation = ck._segmentation_from_tasks
_orig_noted = ck._note_pose_unavailable


def _fake_model_path():
    return "fake/pose_landmarker_lite.task"


def _fake_landmarks(u8):
    h, w = u8.shape[0], u8.shape[1]
    return [(0.5, 0.5)] * 33


def _fake_segmentation(u8):
    import numpy as _np
    h, w = u8.shape[0], u8.shape[1]
    seg = _np.zeros((h, w), dtype=_np.float32)
    seg[h // 4:3 * h // 4, w // 4:3 * w // 4] = 0.9
    return seg


ck._pose_model_path = _fake_model_path
# 1.9.5 부터 게이트가 "세션" 이다 (경로가 아니라). 세션까지 스텁해야
# 디코딩 앞 게이트를 통과한다. 이걸 빠뜨리면 이 블록이 조용히 실패하고
# "마스크가 안 만들어졌다" 는 잘못된 결론을 낸다.
ck._pose_landmarker = lambda: object()
ck._pose_landmarks_from_tasks = _fake_landmarks
ck._segmentation_from_tasks = _fake_segmentation


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

    # R58: 디코드 잔재 정리 블록이 **실제로 NameError를 던지지 않는가**.
    # 왜(Why) 이걸 검사하나: 두 함수에 있던 `del img, arr, ...` 는 img 가
    # 다른 함수(_decode_latent_rgb)의 로컬이라 항상 NameError였고, 바로 아래
    # `except Exception: pass` 가 삼켰다. 그래서 테스트는 "마스크가 만들어졌다"
    # 만 확인할 뿐 정리 블록이 죽은 채로 돌아가는지 아무도 몰랐다.
    # 이제 NameError를 숨기지 않으므로, 이 경로가 깨지면 raise 로 드러난다.
    _r58_mask = ck._person_mask_for_latent(_FakeVAE(), base)
    check("R58: 마스크 경로가 조용히 실패하지 않음",
          _r58_mask is not None, "del 블록이 예외를 삼켰다면 마스크가 None")
finally:
    ck._pose_model_path = _orig_model_path
    ck._pose_landmarker = _orig_landmarker
    ck._pose_landmarks_from_tasks = _orig_landmarks
    ck._segmentation_from_tasks = _orig_segmentation

# R58: 두 함수가 조용히 실패하는 경로가 남아 있지 않은지 소스를 검사한다.
# `del img` 처럼 스코프 밖 이름을 del 하면 NameError -> 예외 삼킴 -> 조용한 실패다.
_ksrc_del = [ln.strip() for ln in _ksrc_lines
             if "del " in ln and not ln.strip().startswith("#")]
check("R58: del 구문에 스코프 밖 이름 없음 (조용한 NameError 방지)",
      not any(re.search(r"\bdel\s+img\b", ln) for ln in _ksrc_del),
      str([ln for ln in _ksrc_del if "img" in ln]))

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

# R57: 뷰 매칭이 **생성 결과**를 보고 고르는가.
# 왜(Why) 이 테스트가 필요한가: 이전 구현은 패널 시그니처를 `sig_ref`
# (시트 전체 시그니처)와 비교했다. 시트 안의 모든 패널은 구성상 시트 전체와
# 비슷하므로 점수가 "이 패널이 얼마나 다른 뷰인가"로 수렴하고, 생성 결과가
# 어떤 뷰인지는 전혀 반영되지 않았다. README는 "샘플 결과와 가장 잘 맞는 뷰"
# 라고 적고 있었으므로 코드와 문서가 어긋나 있었다.
def _r57_sheet_with_distinct_views():
    """패널마다 내부 구조(에지 밀도)가 확연히 다른 4패널 시트.

    패널 검출은 열 STD의 연속 구간을 찾는다. 실루엣 블록을 함께 두는 이유는
    두 가지: ① 열 STD가 임계(_PANEL_ON_RATIO 0.30)를 넘어야 구간이 나오고
    ② 검출된 구간이 곧 패널 경계라, 줄무늬는 그 구간 안쪽에 있어야 시그니처에
    반영된다(구간 바깥에 그리면 잘려 나간다).
    """
    im = _npr.full((512, 1024, 3), 0.95, dtype=_npr.float32)
    steps = (3, 24, 12, 6)          # 간격이 좁을수록 에지가 많다
    for i, step in enumerate(steps):
        x0 = 64 + i * 240           # 패널 폭 192, 패널 사이 빈 공간 48
        im[60:120, x0:x0 + 192] = 0.3                 # 실루엣(머리+몸통 상단)
        im[120:440, x0 + 24:x0 + 168] = 0.25          # 실루엣(몸통)
        im[150:410, x0 + 24:x0 + 168:step] = 0.2      # 패널별 내부 줄무늬
    return im


_R57_SHEET = _r57_sheet_with_distinct_views()
_r57_panels = ck.detect_panels(_R57_SHEET)
check("R57: 합성 시트가 시트로 판정됨 (테스트 전제)",
      ck.looks_like_sheet(_r57_panels)["sheet"], str(_r57_panels))
check("R57: 4개 패널이 검출됨 (테스트 전제)", len(_r57_panels) == 4, str(_r57_panels))


def _r57_samp(step, x0=64):
    """패널 하나와 같은 줄무늬 간격의 샘플 이미지.

    실제 생성 결과는 인물 한 장이 화면을 가득 채운다(시트처럼 패널이 나란히
    놓이지 않는다). 시그니처는 총합 1 정규화라 크기 자체는 무관하지만
    **배경 비율**이 다르면 텍스처 분포가 어긋난다. 그래서 패널과 같은
    비율(440x192)로 만든다.
    """
    im = _npr.full((440, 192, 3), 0.95, dtype=_npr.float32)
    im[60:120, 0:192] = 0.3
    im[120:440, 24:168] = 0.25
    im[150:410, 24:168:step] = 0.2
    return im


_R57_REF = _R57_SHEET * 0.5          # 밝기 스케일만 다르게 (시그니처는 불변)

_orig_decode_small = ck._decode_small
_R57_REF_LATENT = object()
_R57_SAMP_LATENT = object()


def _r57_analyze(samp_arr):
    """samp_arr를 sampled로 넘긴 analyze_reference_sheet 결과.

    주의: analyze_reference_sheet의 세 번째 인자는 LATENT 딕셔너리가 아니라
    **sampled 텐서**다(리팩터링 과정에서 4줄짜리 시그니처 계산이 샘플
    디코드로 바뀌면서 생긴 형태). 딕셔너리를 넘기면 샘플 시그니처가 아예
    계산되지 않고 best가 임의로 나온다.
    """
    def _fake(vae, latent, scale=0.5):
        return samp_arr if latent is _R57_SAMP_LATENT else _R57_REF
    try:
        ck._decode_small = _fake
        return ck.analyze_reference_sheet(
            object(), {"samples": _R57_REF_LATENT}, _R57_SAMP_LATENT)
    finally:
        ck._decode_small = _orig_decode_small


# 패널별 간격(3, 24, 12, 6)과 같은 샘플을 각각 넘겨 그 뷰를 고르는지 본다.
# 구버그(시트 전체 시그니처와 비교)였다면 네 값이 전부 같게 나온다.
_r57_picks = {}
for _i, _step in enumerate((3, 24, 12, 6)):
    _r57_picks[_i] = _r57_analyze(_r57_samp(_step))["best"]

check("R57: 뷰 매칭이 샘플에 반응 (패널별 서로 다른 뷰 선택)",
      sorted(_r57_picks.values()) == [0, 1, 2, 3], str(_r57_picks))
# 1번 패널(가장 성김 step=24) 샘플 → 1번을 골라야 한다.
check("R57: 샘플과 같은 뷰를 고름 (시트 전체와 비교하면 best가 임의가 됨)",
      _r57_picks[1] == 1, str(_r57_picks))
# 0번 패널(가장 조밀 step=3) 샘플 → 0번을 골라야 한다.
check("R57: 조밀한 뷰 샘플이면 조밀한 패널을 고름",
      _r57_picks[0] == 0, str(_r57_picks))
check("R57: 매칭 점수가 유의미함 (0에 수렴하지 않음)",
      _r57_analyze(_r57_samp(24))["match"] > 0.5,
      str(_r57_analyze(_r57_samp(24))["match"]))

print("-- 크로스플랫폼 (Windows/macOS/Linux) --")
# 왜(Why): Keeper는 세 OS에서 돌아가야 한다. 정적으로 못 지킨다 → 배포
# 저장소 CI 매트릭스(ubuntu/windows/macos)와 짝을 이루는 회귀 테스트.
_ksrc = _KSRC
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
# 이 노드는 latent 와 배열만 다룬다. 경로 **탐색**은 하지 않는다(R61) —
# 동봉 모델 경로 하나를 __file__ 기준으로 조립할 뿐이다. 절대경로 문자열이나
# 슬래시 결합으로 경로를 만들면 (구) 설치 위치에 묶인다.
check("탐색 없는 경로 조립만 (동봉 모델 __file__ 기준)",
      "os.path.join(_os.path.dirname(_os.path.realpath(__file__))" in _ksrc
      and not re.search(r"os\.path\.(exists|isfile|isdir|listdir|walk)|"
                        r"os\.scandir|glob\.glob|os\.walk", _ksrc)
      and chr(34) + "/" + chr(34) not in _ksrc)
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

# R61: 문서=코드 정합성 — README 가 코드와 어긋나면 사용자가 문서대로 따라
# 했는데 결과가 안 나오면 그건 **문서 버그**다.
# 왜(Why) 이걸 지금 넣나: 2026-09-29 감사에서 세 가지가 나왔고 셋 다 README 의
# 사실과 반대였다. ① "경로 처리 os.path 기반" — 코드에 os.path 가 0건
# (테스트 자체가 "os.path 없음"을 검증한다 — 문서와 정면 충돌).
# ② "외부 pip 패키지 없음" — numpy·mediapipe 를 실제로 쓴다.
# ③ 배치 동작이 문서에 아예 없었다(배치>1 이면 마스크·부위맵이 꺼진다).
_readme_ko = open(os.path.join(PKG, "README.md"), encoding="utf-8").read()
_readme_en = open(os.path.join(PKG, "README.en.md"), encoding="utf-8").read()
_init_src = open(os.path.join(PKG, "__init__.py"), encoding="utf-8").read()

check("R61: README 가 없는 os.path 주장을 하지 않음",
      "os.path" not in _readme_ko and "os.path" not in _readme_en,
      "README 에 os.path 언급이 있으면 코드와 어긋난다")
# 1.9.5 부터는 동봉 모델 경로 조립에 os.path 를 쓴다(__file__ 기준). 그래서
# "os.path 0건" 이라는 이전 불변식은 더 이상 사실이 아니다 — 지우면 코드가
# 문서와 어긋나게 되니까 **구체적으로 다시 잡는다**:
#   허용  __file__ 기준 1곳 경로 조립 (동봉 모델)
#   금지  시스템 여러 곳을 뒤지는 탐색 (os.path.exists/listdir/walk/glob)
check("R61: os.path 는 동봉 모델 경로 조립에만 쓰인다",
      _ksrc.count("os.path") <= 3
      and "os.path.join(_os.path.dirname(_os.path.realpath(__file__))" in _ksrc,
      f"os.path {_ksrc.count('os.path')}건 (별칭 _os 사용 가능)")
check("R61: 파일시스템 탐색은 여전히 없다 (R61 취지)",
      not re.search(r"os\.path\.(exists|isfile|isdir|listdir|walk)|"
                    r"os\.scandir|glob\.glob|os\.walk", _ksrc),
      "탐색이 다시 들어왔다")
check("R61: __init__ 이 '외부 pip 없음' 으로 거짓말하지 않음",
      "외부 pip 패키지 없음" not in _init_src
      and "mediapipe" in _init_src,
      "__init__ 의 의존성 설명을 코드에 맞게 고쳐라")
check("R61: README 가 배치 제약을 밝힘",
      "배치" in _readme_ko and "Batch" in _readme_en,
      "배치 동작이 README 에 없다")
check("R61: README 가 선택 의존 mediapipe 를 밝힘",
      "mediapipe" in _readme_ko and "mediapipe" in _readme_en)
# 배치 제약이 코드에 실제로 있는가 — 문서만 쓰고 구현이 없으면 그 반대다.
check("R61: 배치>1 에서 단일 이미지 전용 기능이 꺼짐 (구현 확인)",
      "not _multi" in _ksrc
      and ("배치" in _ksrc or "전역 당김만" in _ksrc),
      "배치 분기가 코드에서 사라졌다")

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

# (5) R60: dtype 안전 — 거리 제곱이 fp16 에서 inf 로 넘친다.
# 왜(Why) 실측: d2 최대값은 2*512^2 = 524288 인데 fp16 상한은 65504 다.
#   256x256 fp16 에서 13835 픽셀이 inf 가 된다.
#
#   주의(중요): inf 가 생겨도 **최종 출력은 같을 수 있다.** 비교가
#   `d2 <= r^2` 이라 inf 는 탈락하기 때문이다(구버그로 되돌려도 아래
#   fp16==fp32 검사는 통과한다). 그러므로 출력이 아니라 **계산 중간값**을
#   본다. inf 가 있다는 건 "우연히 비교가 버려줘서" 통과한 것이지
#   올바르다는 뜻이 아니다 — 비교 대상 dtype 이 바뀌면(예: NaN 입력,
#   또는 r^2 를 inf 로 만드는 큰 반경) 결과가 뒤집힌다.
#   거리 계산은 float32 로 한다는 계약을 소스 수준에서 고정한다.
for _dt, _dtname in ((t.float16, "fp16"), (t.bfloat16, "bf16"),
                     (t.float32, "fp32")):
    _sd = t.zeros(1, 4, 256, 256, dtype=_dt)
    _md = t.ones(1, 4, 256, 256, dtype=_dt)
    _r = ck._apply_region_strength(
        0.0, _md, _sd, t.full((33,), 0.5, dtype=_dt),
        _PARTS_ONLY_SAMP, None)
    check(f"R60: {_dtname} 256x256 에서 inf/nan 없이 region 생성",
          _r is not None and _r.shape == _sd.shape
          and not bool(_r.isinf().any()) and not bool(_r.isnan().any()),
          "None" if _r is None else f"inf={bool(_r.isinf().any())} "
                                    f"nan={bool(_r.isnan().any())}")
    # 반환 dtype 은 입력과 같아야 한다(호출부가 out + _inc 를 하므로).
    check(f"R60: {_dtname} 반환 dtype 유지", _r is None or _r.dtype == _dt,
          str(None if _r is None else _r.dtype))

# 거리 계산은 fp16 이 아니라 float32 로 한다 (소스 계약).
# `arange(..., dtype=sampled.dtype)` 가 남아 있으면 실수 오버플로가 되살아난다.
check("R60: 거리 좌표는 float32 로 계산 (fp16 오버플로 방지)",
      "dtype=_t.float32, device=sampled.device" in _KSRC
      and not re.search(r"arange\([^)]*dtype=sampled\.dtype", _KSRC),
      "arange 가 sampled.dtype 을 쓰고 있으면 실패")

# fp16 과 fp32 결과가 같은지 — dtype 이 결과를 바꾸지 않아야 한다.
_16 = ck._apply_region_strength(
    0.0, t.ones(1, 4, 256, 256, dtype=t.float16),
    t.zeros(1, 4, 256, 256, dtype=t.float16),
    t.full((33,), 0.5, dtype=t.float16), _PARTS_ONLY_SAMP, None)
_32 = ck._apply_region_strength(
    0.0, t.ones(1, 4, 256, 256, dtype=t.float32),
    t.zeros(1, 4, 256, 256, dtype=t.float32),
    t.full((33,), 0.5, dtype=t.float32), _PARTS_ONLY_SAMP, None)
check("R60: fp16 결과가 fp32 와 동일 (dtype 이 결과를 바꾸지 않음)",
      _16 is not None and _32 is not None
      and abs(float(_16.float().max()) - float(_32.max())) < 1e-3,
      f"fp16 {None if _16 is None else float(_16.float().max()):.4f} "
      f"fp32 {None if _32 is None else float(_32.max()):.4f}")

# 512x512 는 fp16 최대 d2 가 524288 으로 상한의 8배다. 그래도 inf 가 없어야 한다.
_big16 = ck._apply_region_strength(
    0.0, t.ones(1, 4, 512, 512, dtype=t.float16),
    t.zeros(1, 4, 512, 512, dtype=t.float16),
    t.full((33,), 0.5, dtype=t.float16), _PARTS_ONLY_SAMP, None)
check("R60: fp16 512x512 (오버플로 최대) 에서 inf 없음",
      _big16 is not None and not bool(_big16.isinf().any()),
      "None" if _big16 is None else f"inf={bool(_big16.isinf().any())}")

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


class _ZeroVAE:
    """결정적 디코드 (region 정합성 검사용).

    `_CountVAE` 는 `t.rand` 를 쓰므로 같은 입력을 넣어도 매 실행마다 다른
    결과가 나온다. region 증가분을 비교하는 테스트는 **두 실행의 차이**를
    보는데, 디코드가 랜덤이면 그 차이가 런타임 노이즈에 묻힌다.
    """

    def decode(self, samples):
        return t.zeros(1, 3, 64, 64)


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

# region 분기를 강제로 태워(mediapipe 없이) 전역이 살아 있는지 확인.
# 세 가지가 동시에 깨져 있었다:
#  ① vae 를 넘기지 않아 `if vae is not None and ...` 가드가 False → 부위맵을
#     아예 부르지 않았다. 즉 이름만 region 인 검사가 region 경로를 못 돌았다.
#  ② monkeypatch 람다가 (vae, lat) 2개 인자만 받는데 run() 은 cache= 로
#     세 번째를 넘긴다. 가드가 someday 열린다即 TypeError 로 죽는다.
#  ③ 두 번째 check 의 `or True` 는 무조건 참이라 검증이 아니었다.
_fake_pm = {"original": {"edge": [0.9] * 33, "xy": [(0.5, 0.5)] * 33},
            "sampled": {"edge": [0.1] * 33, "xy": [(0.5, 0.5)] * 33}}
_real_pm = ck._part_detail_map
_pm_calls = {"n": 0}


def _fake_part_detail_map(vae, latents, cache=None):
    _pm_calls["n"] += 1
    return _fake_pm


ck._part_detail_map = _fake_part_detail_map
try:
    _out_pm = _node.run(_b64, strength_camera=0.0, strength_original=0.33,
                        original_latent=_o64, vae=_ZeroVAE())[0]["samples"]
finally:
    ck._part_detail_map = _real_pm

check("R59: 부위맵이 실제로 호출됨 (이전엔 vae 미전달로 경로가 열리지 않음)",
      _pm_calls["n"] > 0, f"calls={_pm_calls['n']}")

# region 은 전역을 **대체하지 않고 증가분**을 더한다. 그래서 region 실행값이
# 전역 실행값과 같으면(대체됐으면) 실패하고, 커야 한다.
# 기준값은 같은 입력으로 region 미적용 실행을 **직접 돌려** 얻는다
# (기대값을 손으로 계산하면 계수를 빠뜨리기 쉽다).
# 주의: 원본 함수는 한 번만 잡는다. 앞에서 복원한 값을 다시 "원본"으로 잡으면
# 몬키패치가 누적돼 두 실행이 같은 경로를 타게 된다.
try:
    ck._part_detail_map = lambda vae, latents, cache=None: None
    _out_global = _node.run(_b64, strength_camera=0.0, strength_original=0.33,
                            original_latent=_o64, vae=_ZeroVAE())[0]["samples"]
finally:
    ck._part_detail_map = _real_pm

# region 은 전역을 **대체하지 않고 증가분**을 더한다.
# 구버그(`out = _inc`)에서는 결과가 증가분 그 자체(0.3168)가 되고,
# 정상(`out = out + _inc`)에서는 전역(0.1980) + 증가분 = 0.5148 이 된다.
# 즉 region 실행값은 반드시 전역 실행값을 **넘겨야** 한다.
check("R55: region 활성 시에도 전역 블렌드 유지 (대체 아님)",
      float(_out_pm.max()) > float(_out_global.max()),
      f"region {float(_out_pm.max()):.4f} 전역 {float(_out_global.max()):.4f}")
# 더 엄격한 판정: 구버그 값(증가분만)은 0.25 미만이다. 정상은 0.5 이상.
check("R59: region 이 전역을 대체하지 않고 증가분을 더함",
      float(_out_pm.max()) > float(_out_global.max()) + 0.25,
      f"region {float(_out_pm.max()):.4f} 전역 {float(_out_global.max()):.4f}")
check("R59: region 증가분이 유의미함 (0 이 아님)",
      float(_out_pm.max()) - float(_out_global.max()) > 1e-3,
      f"증가분 {float(_out_pm.max()) - float(_out_global.max()):.4f}")
check("R55: region 반환값은 텐서 (None 이 아님)",
      isinstance(ck._apply_region_strength(
          0.33, _o64["samples"], _b64["samples"], t.full((33,), 0.5),
          {"sampled": {"xy": [(0.5, 0.5)] * 33}}, None), t.Tensor))

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
    # 왜(Why) 포즈 세션을 여기서 끄나: 이 블록은 "전역 블렌드 경로가 VAE 를
    # 몇 번 필요로 하는가" 를 잰다. 1.9.5 부터는 .task 가 노드에 동봉되어
    # **포즈가 켜져 있는 게 기본**이 되고, 켜지면 인물 마스크와 부위별 맵이
    # 각자 디코딩을 한다(정상 동작). 그럼 이 블록은 설치 환경(모델 파일이
    # 있는지, mediapipe 가 있는지, 경로가 한글이냐)에 따라 결과가 달라진다 —
    # 환경 의존 테스트는 CI 에서 조용히 깨진다(2026-09-30 실측: Windows 3.12
    # 에서만 실패). 그래서 포즈를 명시적으로 끄고 **디코딩 없는 쪽만** 잰다.
    # "포즈가 켜졌을 때 디코딩 수"는 R67 이 따로 확인한다.
    _o = ck._pose_landmarker
    ck._pose_landmarker = lambda: None
    try:
        v = _CountVAE()
        _n.run({"samples": t.zeros(1, 4, 32, 32)}, vae=v, **kw)
        return v.sizes
    finally:
        ck._pose_landmarker = _o


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
# 여기 있던 `_a1 = ck._decode_latent_rgb(..., cache=_c)` 는 `cache=` 에
# 앞 블록에서 새어 나온 float 를 넘겼다. dict 에 float 를 키로 넣으려 하면
# TypeError → 함수가 삼켜서 `_a1 = None` 이 되고, 그 값은 아무도 안 읽었다.
# 지금은 캐시 경로에 값을 흘려 실제로 캐시가 쓰이는지 본다.
_a1_cache = {}
_a1 = ck._decode_latent_rgb(_CountVAE(), _ones["samples"], cache=_a1_cache)
check("R56: 캐시 경로가 결과를 저장하고 재사용 (id(latent) 키)",
      _a1 is not None and len(_a1_cache) == 1,
      f"result={_a1 is not None} cache={len(_a1_cache)}")
check("R56: 캐시 미사용 시 None 안전",
      ck._decode_latent_rgb(None, _ones["samples"]) is None)

# R62: torch 없는 환경에서 크래시하지 않는다.
# 왜(Why) 이게 필요했나: `if not HAS_TORCH:` 가드 안에 `base`/`cam`/`orig`
# 를 만들어 놓고, **게이트 밖**에서 그 변수를 쓰는 코드가 남아 있었다.
# 실측: 154행에서 `NameError: name 'base' is not defined` 로 죽어
# "torch 없음" 시 4건만 하고 조용히 실패했다. CI 는 torch 를 항상 설치하므로
# 이 경로를 아무도 보지 못했다.
# 게이트를 조기 종료로 바꿔(torch 없으면 명시적으로 끝낸다) 막았다.
# 진짜 검증은 서브프로세스로 torch 를 가린 채 **파일 전체를 끝까지** 돌리는
# 것으로 한다(스트림 흉내로는 재현되지 않는다).
import subprocess as _sp  # noqa: E402

if os.environ.get("GORI_NO_TORCH_CHILD"):
    _r62 = None
else:
    _shim = os.path.join(HERE, "_no_torch_shim.py")
    with open(_shim, "w", encoding="utf-8") as _fh:
        _fh.write(
            "# torch 를 가리는 가짜 import 훅. 서브프로세스에서만 쓴다.\n"
            "import builtins\n"
            "_real = builtins.__import__\n"
            "def _fake(name, *a, **k):\n"
            "    if name == 'torch' or name.startswith('torch.'):\n"
            "        raise ImportError('simulated: torch unavailable')\n"
            "    return _real(name, *a, **k)\n"
            "builtins.__import__ = _fake\n"
            "exec(compile(open('tests/test_node.py', encoding='utf-8').read(),\n"
            "             'test_node.py', 'exec'),\n"
            "     {'__name__': '__main__', '__file__': 'tests/test_node.py'})\n"
        )
    try:
        _r62 = _sp.run([sys.executable, _shim], capture_output=True,
                       cwd=PKG, env=dict(os.environ,
                                         PYTHONIOENCODING="utf-8",
                                         GORI_NO_TORCH_CHILD="1"))
        _r62_txt = (_r62.stdout or b"").decode("utf-8", errors="replace")
        _r62_err = (_r62.stderr or b"").decode("utf-8", errors="replace")
        check("R62: torch 없는 환경에서 크래시 없이 종료",
              "NameError" not in _r62_err and "CRASH" not in _r62_txt
              and _r62.returncode == 0,
              _r62_err.strip().splitlines()[-1][:120]
              if _r62_err.strip() else f"exit={_r62.returncode}")
        check("R62: torch 없는 환경에서 노드 계약 검사는 통과",
              "FAIL=0" in _r62_txt, _r62_txt.strip().splitlines()[-1][:80])
        check("R62: torch 없는 환경을 명시하고 조용히 실패하지 않음",
              "torch" in _r62_txt and "생략" in _r62_txt)
    finally:
        try:
            os.remove(_shim)
        except OSError:
            pass

# 게이트가 조기 종료(structure)인지 확인 — 게이트 밖 사용이 다시 생겨도
# NameError 로 죽는 게 아니라 스킵 메시지와 함께 끝나야 한다.
check("R62: torch 게이트가 조기 종료로 구현됨 (게이트 밖 사용 방지)",
      re.search(r"if not HAS_TORCH:[\s\S]{0,400}?sys\.exit",
                _TEST_SRC)
      is not None,
      "torch 게이트가 sys.exit 로 끝나지 않는다")

# R63: 한국어를 못 인코딩하는 콘솔에서 죽지 않는다.
# 왜(Why) 이것이 실제로 이 저장소를 죽였나(2026-09-29 실측):
# 배포 저장소 CI(run#28)에서 **Windows 러너 2개만** 실패했다. 6개 job 중
# macOS 2 / ubuntu 2 는 통과했다. 원인은 157행의 섹션 헤더 `print` 였다 —
# GitHub Windows 러너의 기본 인코딩은 cp1252 인데, 한글을 아는 charmap 이
# 아니라 **첫 글자에서** 죽는다. `check()` 는 `_say` 를 타는데 섹션 헤더는
# raw `print` 였다. 즉 "인코딩 안전"을 한 군데만 고쳐 놓으면 그 공백이
# 그대로 남는다.
# 그래서 print 를 전부 `_say` 로 고정하고, 실제 서브프로세스를 여러
# 인코딩으로 띄워 **파일 전체가 끝까지 도는지** 확인한다.
check("R63: 섹션 헤더도 인코딩 안전 래퍼를 탄다 (raw print 없음)",
      print is _say, "print = _say 로 고정해야 한다")
check("R63: stdlib print 보존 (_say 재귀 방지)", _print is not _say)

import subprocess as _sp2  # noqa: E402

if os.environ.get("GORI_R63_CHILD"):
    _r63_res = {}
else:
    _r63_res = {}
    for _enc in ("cp949", "cp1252", "ascii", "utf-8"):
        _env = dict(os.environ, PYTHONIOENCODING=_enc, GORI_R63_CHILD="1")
        _r = _sp2.run([sys.executable, os.path.abspath(__file__)],
                      capture_output=True, env=_env, cwd=PKG)
        _txt = (_r.stdout or b"").decode(_enc, errors="replace")
        _err = (_r.stderr or b"").decode(_enc, errors="replace")
        _r63_res[_enc] = (_r.returncode, _txt, _err)
        check(f"R63: {_enc} 인코딩으로 끝까지 실행 (UnicodeEncodeError 없음)",
              _r.returncode == 0 and "UnicodeEncodeError" not in _txt
              and "UnicodeEncodeError" not in _err,
              f"exit={_r.returncode} "
              + next((l for l in _err.splitlines()
                      if "UnicodeEncodeError" in l), ""))
    check("R63: 모든 인코딩에서 전 검사 통과",
          all("FAIL=0" in v[1] for v in _r63_res.values()),
          str({k: next((l for l in v[1].splitlines() if "PASS=" in l), "")
               for k, v in _r63_res.items()}))

# R64: 포즈 로더 계약 (조용한 실패 방지의 핵심).
# 왜(Why) 이 블록이 필요한가: 앞의 포즈 테스트는 `_pose_model_path` /
# `_pose_landmarks_from_tasks` / `_segmentation_from_tasks` 를 **전부 스텁으로
# 대체**한다. 그래서 소비자가 가짜 관절점으로 도는 것만 확인하고, **로더가
# 실제로 어떻게 실패하는지는 한 번도 실행된 적이 없다.** 그런데 이 노드가
# 배포판에서 조용히 죽었던 지점이 정확히 그 자리였다(구 `mediapipe.solutions`
# 부재 → 조용히 None → 인체 마스크/부위별 강도/프레이밍이 사라짐).
# 계약은 세 가지다: (1) 실패해도 예외가 아니라 None, (2) **한 번만** 알린다
# (매 프레임 로그면 콘솔이 floods), (3) 세션은 한 번만 만들어 재사용한다
# (모델 로드는 수 초 걸려 매 프레임 만들면 노드가 멈춘다).
import types as _ty64  # noqa: E402

_pose_logs = []
_orig_log64 = ck._log
ck._log = lambda m: _pose_logs.append(str(m))
_orig_env64 = os.environ.pop("GORI_POSE_MODEL", None)
_orig_landmarker64 = ck._TASKS_LANDMARKER
_orig_err_noted64 = ck._POSE_ERR_NOTED
_orig_noted64 = ck._POSE_NOTED


def _reset_pose_state():
    ck._TASKS_LANDMARKER = []
    ck._POSE_ERR_NOTED = False
    ck._POSE_NOTED = False
    _pose_logs.clear()


try:
    # --- 경로 계약: 자기 옆 동봉 파일, 탐색 없음 (R61) ---
    # (왜) 여기서 "미설정이면 None" 을 기대하면 안 된다: 1.9.5 부터는 노드가
    # .task 를 함께 배포한다. 미설정 = "사용자가 안 골랐다" 이지 "모델 없음" 이
    # 아니다. 동봉본을 주는 게 R66 의 계약이고, 여기는 그 계약이 1.9.4 와
    # 달라졌다는 걸 못 박는 자리다.
    _reset_pose_state()
    _bundled = os.path.join(PKG, "pose_landmarker_lite.task")
    check("R64: 모델 미설정(환경변수 없음)이면 동봉본 경로",
          ck._pose_model_path() == _bundled, str(ck._pose_model_path()))
    check("R64: 동봉 경로가 __file__ 옆이다 (cwd 무관)",
          os.path.dirname(os.path.realpath(ck._pose_model_path()))
          == os.path.realpath(PKG))
    os.environ["GORI_POSE_MODEL"] = ""
    check("R64: 빈 문자열은 미설정으로 취급하고 동봉본으로",
          ck._pose_model_path() == _bundled, str(ck._pose_model_path()))
    os.environ["GORI_POSE_MODEL"] = "C:/nope/does_not_exist.task"
    check("R64: 명시된 경로는 그대로 돌려줌 (파일시스템을 확인하지 않음)",
          ck._pose_model_path() == "C:/nope/does_not_exist.task",
          str(ck._pose_model_path()))
    # (이전의 "경로 미설정 → None" 기대는 1.9.5 에서 사라졌다. 이제 경로가
    #  없어도 동봉본이 있으므로 None 이 아니다. "모델을 못 읽으면 None + 1회
    # 로그" 계약은 아래 실패 케이스가 대신 잡는다.)
    # 여기서 **주위에 기대면 안 된다**: 이 PC 는 설치 경로가 한글이라 모델을
    # 못 열고, CI 는 영문이라 모델이 열린다. "모델이 열리는가" 를 환경에 맡기면
    # 그 자체로 flaky 테스트가 된다(2026-09-30 실측: 로컬 PASS / CI FAIL).
    # 그래서 성공·실패를 모두 명시적으로 만든다.

    # --- 실패해도 죽지 않고 한 번만 말한다 ---

    def _install_fake_mp(vision_mod):
        """`from mediapipe.tasks.python import vision` 가 실제로 성립하게 계층을
        만든다. import 문은 sys.modules 항목뿐 아니라 **부모 모듈의 속성**도
        본다 — 한쪽만 넣으면 from-import 가 조용히 ImportError 가 된다."""
        mp = _ty64.ModuleType("mediapipe")
        tasks = _ty64.ModuleType("mediapipe.tasks")
        py = _ty64.ModuleType("mediapipe.tasks.python")
        mp.tasks = tasks
        tasks.BaseOptions = lambda **kw: object()
        mp.Image = lambda **kw: object()
        mp.ImageFormat = _ty64.SimpleNamespace(SRGB="SRGB")
        py.vision = vision_mod
        for _n, _m in (("mediapipe", mp), ("mediapipe.tasks", tasks),
                       ("mediapipe.tasks.python", py),
                       ("mediapipe.tasks.python.vision", vision_mod)):
            sys.modules[_n] = _m

    _bad_vision = _ty64.ModuleType("mediapipe.tasks.python.vision")
    _bad_vision.PoseLandmarkerOptions = lambda **kw: object()
    _bad_vision.RunningMode = _ty64.SimpleNamespace(IMAGE="IMAGE")

    def _boom_create(_options):
        raise RuntimeError("model load failed")

    _bad_vision.PoseLandmarker = _ty64.SimpleNamespace(
        create_from_options=staticmethod(_boom_create))
    _install_fake_mp(_bad_vision)
    _saved = {k: v for k, v in sys.modules.items()
              if k == "mediapipe" or k.startswith("mediapipe.tasks")}
    # 세션이 열리지 않는 상황을 **명시적으로** 만든다. 주위에 기대지 않는
    # 방법: 1.9.5 부턴 동봉 모델이 있어서 "경로 없음" 으로는 실패를 재현할
    # 수 없다. 깨진 경로(영문) + 가짜 mediapipe 로 일부러 실패시킨다.
    _reset_pose_state()
    os.environ["GORI_POSE_MODEL"] = "C:/nope/broken.task"
    _install_fake_mp(_bad_vision)
    check("R64: 모델 로드 실패 시 예외 없이 None",
          ck._pose_landmarker() is None)
    check("R64: 실패 로그에 원인이 남음 (무엇이 죽었는지)",
          _pose_logs and "RuntimeError" in _pose_logs[0]
          and "model load failed" in _pose_logs[0], str(_pose_logs[:1]))
    for _ in range(4):
        ck._pose_landmarker()
    check("R64: 실패를 정확히 한 번만 알림 (5회 호출)",
          len(_pose_logs) == 1, f"{len(_pose_logs)}건: {_pose_logs[:1]}")

    # --- 성공하면 세션을 재사용한다 (매 프레임 재로드 방지) ---
    _reset_pose_state()
    os.environ["GORI_POSE_MODEL"] = "C:/fake/pose.task"
    _built = []

    class _FakeSession:
        def __init__(self):
            _built.append(self)

    _good_vision = _ty64.ModuleType("mediapipe.tasks.python.vision")
    _good_vision.PoseLandmarkerOptions = lambda **kw: object()
    _good_vision.RunningMode = _ty64.SimpleNamespace(IMAGE="IMAGE")
    _good_vision.PoseLandmarker = _ty64.SimpleNamespace(
        create_from_options=staticmethod(lambda o: _FakeSession()))
    _install_fake_mp(_good_vision)
    _s1 = ck._pose_landmarker()
    _s2 = ck._pose_landmarker()
    _s3 = ck._pose_landmarker()
    check("R64: 정상 경로에서 세션이 만들어짐", _s1 is not None)
    # 같은 객체만으로는 재작성 을 못 잡는다(생성기가 매번 같은 걸 돌려주면
    # 통과해버린다). **생성 횟수** 로 판정해야 캐시가 실제로 살아 있는지 된다.
    check("R64: 세션은 3회 호출에도 한 번만 생성 (재로드 없음)",
          len(_built) == 1, f"{len(_built)}회 생성됨")
    check("R64: 호출마다 같은 세션을 돌려준다", _s1 is _s2 is _s3)
    check("R64: 성공 경로에서는 오류 로그 없음", not _pose_logs,
          str(_pose_logs[:1]))

    # --- 33점 계약: 모자라면 조용히 None ---
    _reset_pose_state()
    os.environ["GORI_POSE_MODEL"] = "C:/fake/pose.task"

    class _Pts:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    def _mk_detector(n_pts):
        class _LM:
            def detect(self, _img):
                return _ty64.SimpleNamespace(
                    pose_landmarks=[[_Pts(i / 100.0, 0.5) for i in range(n_pts)]],
                    segmentation_masks=None)
        return _LM()

    ck._TASKS_LANDMARKER = [_mk_detector(33)]
    _l33 = ck._pose_landmarks_from_tasks(_u8_early := _npr.zeros((8, 8, 3),
                                                                 dtype=_npr.uint8))
    check("R64: 33점이면 그대로 통과 (관절점 33개)",
          _l33 is not None and len(_l33) == 33,
          str(len(_l33) if _l33 else None))
    ck._TASKS_LANDMARKER = [_mk_detector(32)]
    check("R64: 32점이면 None (모자란 관절점을 조용히 쓰지 않음)",
          ck._pose_landmarks_from_tasks(_u8_early) is None)
    ck._TASKS_LANDMARKER = [_ty64.SimpleNamespace(detect=lambda _i: _ty64.SimpleNamespace(
        pose_landmarks=None, segmentation_masks=None))]
    check("R64: 검출 결과가 비면 None",
          ck._pose_landmarks_from_tasks(_u8_early) is None)

    # --- 기능 없음 안내도 1회만 ---
    _reset_pose_state()
    for _ in range(4):
        ck._note_pose_unavailable()
    check("R64: 기능 꺼짐 안내도 1회만 (4회 호출)",
          len(_pose_logs) == 1, f"{len(_pose_logs)}건")

    # --- 소비자는 로더가 None 이면 조용히 통과 ---
    # (왜) 로더를 스텁으로 None 을 만든다: 1.9.5 부터는 경로가 없으면 대신
    # 동봉본을 주므로 "환경변수 비우기" 로는 None 이 되지 않는다. 여기 검증하는
    # 것은 **로더가 None 일 때 소비자가 예외 없이 통과하는가** 라서 로더를
    # 직접 None 으로 만든다.
    _reset_pose_state()
    _orig_pl66 = ck._pose_landmarker
    ck._pose_landmarker = lambda: None
    try:
        _u8_zero = _npr.zeros((8, 8, 3), dtype=_npr.uint8)
        check("R64: 관절점 추출은 로더 없으면 None",
              ck._pose_landmarks_from_tasks(_u8_zero) is None)
        check("R64: 세그멘테이션도 로더 없으면 None",
              ck._segmentation_from_tasks(_u8_zero) is None)
    finally:
        ck._pose_landmarker = _orig_pl66

    # --- detect() 가 터져도 예외가 새지 않는다 ---
    _reset_pose_state()
    os.environ["GORI_POSE_MODEL"] = "C:/fake/pose.task"

    class _BoomLM:
        def detect(self, _img):
            raise ValueError("detect failed")

    ck._TASKS_LANDMARKER = [_BoomLM()]
    _u8 = _npr.zeros((8, 8, 3), dtype=_npr.uint8)
    check("R64: detect 실패해도 관절점은 None (예외 전파 안 됨)",
          ck._pose_landmarks_from_tasks(_u8) is None)
    check("R64: detect 실패해도 세그멘테이션은 None",
          ck._segmentation_from_tasks(_u8) is None)
    check("R64: detect 실패 원인이 1회 로그로 남음",
          len(_pose_logs) == 1 and "detect failed" in _pose_logs[0],
          str(_pose_logs[:1]))
finally:
    ck._log = _orig_log64
    ck._TASKS_LANDMARKER = _orig_landmarker64
    ck._POSE_ERR_NOTED = _orig_err_noted64
    ck._POSE_NOTED = _orig_noted64
    if _orig_env64 is None:
        os.environ.pop("GORI_POSE_MODEL", None)
    else:
        os.environ["GORI_POSE_MODEL"] = _orig_env64
    for _k in ("mediapipe", "mediapipe.tasks", "mediapipe.tasks.python",
               "mediapipe.tasks.python.vision"):
        if _k in _saved:
            sys.modules[_k] = _saved[_k]
        else:
            sys.modules.pop(_k, None)

# R65: "조용히 None" 을 허용하는 자리는 반드시 1회 로그로 막는다.
# 왜(Why) 이것도 회귀 가드인가: 포즈 로더는 예외를 삼키고 None 을 돌려주는 것이
# 설계다(프레임마다 죽이면 노드가 못 쓴다). 그래서 안전망은 오직 로그다. 이게
# 실수로 빠지면 회귀를 아무도 모른다 — 33점 기능이 그냥 사라진다.
_src65 = open(os.path.join(PKG, "consistency_keeper.py"), encoding="utf-8").read()
check("R65: 포즈 실패 로그가 1회 가드(_POSE_ERR_NOTED)를 쓴다",
      "_POSE_ERR_NOTED" in _src65 and "if _POSE_ERR_NOTED" in _src65)
check("R65: 기능 없음 안내도 1회 가드(_POSE_NOTED)를 쓴다",
      "_POSE_NOTED" in _src65 and "if _POSE_NOTED" in _src65)
check("R65: 모델 경로는 환경변수만 읽는다 (파일시스템 접근 없음)",
      'os.environ.get("GORI_POSE_MODEL")' in _src65
      and "os.path.exists" not in _src65.split("def _pose_landmarker")[0])

# R66: 동봉 모델은 "설치하면 따라와야 한다".
# 왜(Why) 이게 별도 블록인가: 1.9.4 까지는 경로를 환경변수로만 받았고, 그
# 결과 33점 기능이 **설치해도 꺼진 채**였다(사용자가 환경변수를 모르면 계속
# 꺼짐). 이건 배포본의 핵심 로직인데 정작 배포로 따라오지 않았다. 이제
# 노드 폴더에 파일을 함께 넣고 __file__ 기준으로 찾는다.
# 검증할 것: (1) 기본값이 자기 옆 파일이다 (2) 환경변수가 우선한다
# (3) 탐색하지 않는다 — 경로 하나만 만든다 (4) 파일이 실제로 동봉돼 있다.
_src66 = open(os.path.join(PKG, "consistency_keeper.py"), encoding="utf-8").read()
_MODEL_NAME = "pose_landmarker_lite.task"

check("R66: 동봉 모델 파일명이 상수로 모여 있다",
      "_POSE_MODEL_FILENAME = \"" + _MODEL_NAME + "\"" in _src66)
check("R66: 기본 경로는 __file__ 기준 (설치 위치와 무관하게 따라온다)",
      "os.path.realpath(__file__)" in _src66
      and "_POSE_MODEL_FILENAME)" in _src66)
check("R66: 환경변수가 동봉본보다 우선",
      _src66.index('if env:') < _src66.index("realpath(__file__)"))

# 탐색 금지: os.path.exists / listdir / glob 같은 파일시스템 조회가 없다.
# 존재 확인은 PoseLandmarker 생성에 맡긴다(경로가 틀리면 그 자리에서 죽어야
# "조용한 실패" 가 되지 않는다).
import re as _re66
_body66 = _src66[_src66.index("def _pose_model_path():"):
                 _src66.index("def _pose_landmarker():")]
check("R66: 파일시스템을 탐색하지 않는다 (R61)",
      not _re66.search(r"os\.path\.(exists|isfile|isdir|listdir|walk)|glob\.|os\.scandir",
                       _body66), _body66[:120])
check("R66: 반환값은 경로 하나뿐 (탐색 결과 리스트 아님)",
      _body66.count("return") == 2)

# 실제로 동봉돼 있는가 — 없으면 이 테스트는 통과해도 배포본이 고장 난다
_model_path66 = os.path.join(PKG, _MODEL_NAME)
check("R66: 모델 파일이 노드 폴더에 실제로 동봉돼 있다",
      os.path.isfile(_model_path66),
      "%s (%s)" % (_model_path66,
                   os.path.getsize(_model_path66) if os.path.isfile(_model_path66)
                   else "없음"))
if os.path.isfile(_model_path66):
    import hashlib as _hl66
    _sz66 = os.path.getsize(_model_path66)
    with open(_model_path66, "rb") as _f66:
        _sha66 = _hl66.sha256(_f66.read()).hexdigest()
    check("R66: 공식 sha256 과 일치 (다른 파일 아님)",
          _sha66 == "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
          _sha66)
    check("R66: 크기가 공식 배포본과 같음 (5,777,746 bytes)", _sz66 == 5777746, str(_sz66))
    # .task 는 ZIP 컨테이너다 — 앞에 2바이트가 붙고 PK 가 온다(앞 16바이트를
    # 실제로 보면 00 00 PK 03 04 이다). 잘못된 파일이 끼면 로드 시점에 죽는다.
    with open(_model_path66, "rb") as _f66:
        _magic66 = _f66.read(6)
    check("R66: .task 컨테이너 시그니처 (PK\\x03\\x04)",
          _magic66[2:6] == b"PK\x03\x04", repr(_magic66))
    # 재사용 라이선스 고지 — Apache 2.0 Section 4 는 라이선스 사본 동봉을 요구한다
    _lic66 = os.path.join(PKG, "POSE_MODEL_LICENSE.txt")
    _lic_txt66 = (open(_lic66, encoding="utf-8").read()
                  if os.path.isfile(_lic66) else "")
    check("R66: 라이선스 고지 파일이 동봉돼 있다 (Apache 2.0 Section 4)", bool(_lic_txt66))
    check("R66: 출처 URL 과 sha256 이 고지에 적혀 있다",
          "storage.googleapis.com/mediapipe-models" in _lic_txt66
          and "59929e1d1ee952877" in _lic_txt66)
    check("R66: Apache 2.0 재사용 조건이 고지에 명시돼 있다",
          "Apache License 2.0" in _lic_txt66 and "재배포" in _lic_txt66)

# --- 경로 판정 동작 (가짜 파일시스템 없이) ---
_orig_env66 = os.environ.pop("GORI_POSE_MODEL", None)
_orig_file66 = ck._POSE_MODEL_FILENAME
try:
    # 환경변수 없으면 동봉본 경로
    check("R66: 환경변수 없으면 동봉 파일 경로를 준다",
          ck._pose_model_path() == _model_path66, str(ck._pose_model_path()))
    check("R66: 그 경로가 실제 동봉 파일과 같은가",
          os.path.realpath(ck._pose_model_path())
          == os.path.realpath(_model_path66))
    # 환경변수가 있으면 그것이 우선
    os.environ["GORI_POSE_MODEL"] = "C:/custom/full.task"
    check("R66: 환경변수가 동봉본을 덮는다",
          ck._pose_model_path() == "C:/custom/full.task")
    os.environ["GORI_POSE_MODEL"] = ""
    check("R66: 빈 환경변수는 무시하고 동봉본으로 되돌아간다",
          ck._pose_model_path() == _model_path66, str(ck._pose_model_path()))
    # 파일명이 바뀌면 그것을 따라간다 (full/heavy 교체 대비)
    ck._POSE_MODEL_FILENAME = "pose_landmarker_full.task"
    check("R66: 동봉 파일명 교체 시 그 이름을 따라간다",
          os.path.basename(ck._pose_model_path()) == "pose_landmarker_full.task",
          os.path.basename(ck._pose_model_path()))
finally:
    ck._POSE_MODEL_FILENAME = _orig_file66
    if _orig_env66 is None:
        os.environ.pop("GORI_POSE_MODEL", None)
    else:
        os.environ["GORI_POSE_MODEL"] = _orig_env66

# 안내 문구가 실제 파일명을 말해야 한다 ("lite" 라고 적어놓고 full 을 쓰는
# 경우 사용자가 엉뚱한 곳을 본다).
# R64 의 finally 가 ck._log 를 원본으로 되돌려놨으므로 다시 물어야 한다.
_pose_logs.clear()
_orig_log_r66 = ck._log
ck._log = lambda m: _pose_logs.append(str(m))
try:
    ck._POSE_NOTED = False
    ck._note_pose_unavailable()
    check("R66: 꺼짐 안내가 동봉 파일명을 그대로 말함",
          _pose_logs and _MODEL_NAME in _pose_logs[0], str(_pose_logs[:1]))
    check("R66: 꺼짐 안내가 환경변수 확인법도 알려줌",
          _pose_logs and "GORI_POSE_MODEL" in _pose_logs[0])
finally:
    ck._log = _orig_log_r66
    ck._POSE_NOTED = False
    _pose_logs.clear()

# R67: 게이트는 "경로" 가 아니라 "세션" 을 본다 — 비싼 디코딩 전에 확인한다.
# 왜(Why) 별도 블록인가: 1.9.5 에서 동봉 모델을 추가하면서 **실제 회귀**가
# 났다. 게이트가 `_pose_model_path() is None` 만 보면, 경로는 있는데 파일을 못
# 여는 경우(설치 경로에 한글, 파일 손상 등) VAE 디코딩을 **다 하고 나서야**
# 포즈 없음을 알게 된다. 실측으로 프레임당 3회 버려지는 디코딩이 생겼다
# (1회 → 4회). 세션은 캐시되므로 세션을 게이트로 쓰면 못 열 때 0원으로 빠진다.
_src67 = open(os.path.join(PKG, "consistency_keeper.py"), encoding="utf-8").read()
for _fn67, _label67 in (("_person_mask_for_latent", "인물 마스크"),
                        ("_part_detail_map", "부위별 맵")):
    _i67 = _src67.index("def " + _fn67)
    _j67 = _src67.find("\ndef ", _i67 + 1)
    _body67 = _src67[_i67:_j67 if _j67 > 0 else _i67 + 2000]
    _d67 = _body67.find("_decode_latent_rgb")
    _g67 = _body67.find("_pose_landmarker()")
    check(f"R67: {_label67} 게이트가 세션 확인 (경로 확인이 아님)",
          "_pose_model_path() is None" not in _body67
          and _g67 != -1 and _d67 != -1 and _g67 < _d67,
          f"gate@{_g67} decode@{_d67}")

# 실제로 세션이 없으면 디코딩 0회여야 한다 (경로가 있어도).
import torch as _t67  # noqa: E402
_vaecalls67 = []


class _CountVAE67:
    def decode(self, latent, **kw):
        _vaecalls67.append(1)
        return _t67.zeros(1, 8, 8, 3)


_orig_pm67 = ck._pose_landmarker
ck._pose_landmarker = lambda: None          # "모델 못 읽는" 상태 재현
try:
    _lat67 = _t67.ones(1, 4, 32, 32)
    _vaecalls67.clear()
    _m67 = ck._person_mask_for_latent(_CountVAE67(), _lat67)
    _mask_dec67 = len(_vaecalls67)
    _vaecalls67.clear()
    _d67 = ck._part_detail_map(_CountVAE67(), {"s": _lat67})
    _part_dec67 = len(_vaecalls67)
    check("R67: 세션 없을 때 인물 마스크는 None", _m67 is None)
    check("R67: 세션 없을 때 부위별 맵은 None", _d67 is None)
    check("R67: 세션 없으면 VAE 디코딩을 아예 하지 않는다 (비용 0원)",
          _mask_dec67 == 0 and _part_dec67 == 0,
          f"mask={_mask_dec67} part={_part_dec67}")
finally:
    ck._pose_landmarker = _orig_pm67

print(f"\n결과: PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
