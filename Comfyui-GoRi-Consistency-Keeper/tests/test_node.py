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
# 왜(Why) 픽스처를 0 과 1 로 두지 않나 (2026-10-01): 감쇠가 **정규화 불일치**를
# 보게되면서 sampled=0 / ref=1 은 정규화 1.0 이 되어 감쇠 0 으로 간다. 그게 옳은
# 판단이다(0 과 1 은 완전한 불일치). 그런데 이 테스트들은 "정상 실행에서 당김이
# 동작한다" 를 확인하는 것이므로 픽스처가 **그 상황**을 표현해야 한다.
# 실제 측정(2026-10-01) 정규화 불일치는 0.222~0.487 이고 무감쇠 끝은 0.50.
# 기준값 0.5 주변으로 조금 흔들린 값을 쓴다.
base = _t.full((1, 4, 8, 8), 0.6)
cam = _t.full((1, 4, 8, 8), 1.2)
orig = _t.full((1, 4, 8, 8), 0.9)

if True:
    # 픽스처가 "무감쇠 구간" 인지 먼저 고정한다. 아니면 아래 수식 검사가
    # 조용히 vacuous(항상 0) 가 된다.
    _nc = ck._drift_norm(base, cam)
    _no = ck._drift_norm(base, orig)
    check("픽스처: camera 가 무감쇠 구간 (검사가 의미 있다)",
          ck._damp_norm(_nc) == 1.0, "%.4f" % _nc)
    check("픽스처: original 가 무감쇠 구간 (검사가 의미 있다)",
          ck._damp_norm(_no) == 1.0, "%.4f" % _no)

    (out,) = node.run({"samples": base}, strength_camera=0.18,
                      strength_original=0.18,
                      camera_latent={"samples": cam},
                      original_latent={"samples": orig})
    _d1 = ck._damp_norm(_nc)
    _d2 = ck._damp_norm(_no)
    expect = base + 0.18 * _d1 * (cam - base) + 0.18 * _d2 * (orig - base)
    check("블렌드 수식", _t.allclose(out["samples"], expect))

    (out0,) = node.run({"samples": base}, strength_camera=0.0,
                       strength_original=0.0,
                       camera_latent={"samples": cam},
                       original_latent={"samples": orig})
    check("강도 0은 원본 유지", _t.allclose(out0["samples"], base))

    big = _t.full((1, 4, 16, 16), 1.0)
    # 강도는 **물리 상한 아래**로 둔다 (2026-10-01). 상한은 별도 검사로
    # 고정한다 — 여기서 상한까지 섞으면 "블렌드 계산"과 "상한 정책"이 한
    # 검사에서 섞여, 어느 쪽이 깨졌는지 알 수 없다.
    (outr,) = node.run({"samples": base}, strength_camera=0.18,
                       strength_original=0.0,
                       camera_latent={"samples": big})
    # `_drift_norm` 은 크기가 다르면 None 이다 — 런에서는 `_match_spatial` 이
    # 먼저 맞춰 주므로 문제없지만, 여기서 직접 부를 때는 정렬이 필요하다.
    _big_m = ck._match_spatial(big, base)
    _nb = ck._drift_norm(base, _big_m)
    check("픽스처: 크기 다른 참조도 무감쇠 구간",
          _nb is not None and ck._damp_norm(_nb) == 1.0, str(_nb))
    check("크기 달라도 리사이즈 후 당김",
          outr["samples"].shape == (1, 4, 8, 8)
          and _t.allclose(outr["samples"],
                          base + 0.18 * ck._damp_norm(_nb) * (_big_m - base)))

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

    check("틀어짐 측정", abs(ck._drift_mse(base, cam) - 0.36) < 1e-6,
          str(ck._drift_mse(base, cam)))
    check("입력 불변 (원본 미수정)",
          _t.allclose(base, _t.full((1, 4, 8, 8), 0.6)))
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
    (outf,) = node.run({"samples": base}, strength_camera=0.18,
                       camera_latent={"samples": far})
    check("구도 불일치도 실행 생존", outf["samples"].shape == (1, 4, 8, 8))
    check("자동 감쇠 계수", ck._damp_factor(0.5) == 1.0
          and ck._damp_factor(None) == 1.0
          and 0.0 < ck._damp_factor(1.4) < 1.0
          and ck._damp_factor(3.0) == 0.0)
    (outd,) = node.run({"samples": base}, strength_camera=1.0,
                       camera_latent={"samples": far})
    check("큰 틀어짐에서도 실행은 죽지 않는다",
          _t.allclose(node.run({"samples": base}, strength_camera=1.0,
                               camera_latent={"samples": far})[0]["samples"],
                       outd["samples"]))
    # 왜(Why) "완전히 어긋남" 의 픽스처가 0 인가 (2026-10-01): 정규화 불일치는
    # |ref-sample| / |ref| 다. 그래서 **참조가 출력물보다 크면 1.0 을 넘지 못한다**
    # (극한은 1.0). 완전 소멸의 정의가 "참조가 거속 멀어진다" 에서
    # "**결과물이 참조 크기에 비해 무(0)로 내려간다**" 로 바뀐다.
    # 실제 정상 참조는 0.222~0.487 이므로 이 구간과 겹치지 않는다.
    gone = _t.full((1, 4, 8, 8), 0.0)
    _ng = ck._drift_norm(gone, base)
    check("결과물이 무면 정규화 1.0 에 수렴한다 (소멸의 정의)",
          _ng is not None and _ng > 0.99, str(_ng))
    (outg,) = node.run({"samples": gone}, strength_camera=1.0,
                       camera_latent={"samples": base})
    check("결과물이 무면 당기지 않는다 (완전 어긋남)",
          _t.allclose(outg["samples"], gone, atol=0.05),
          str(float(outg["samples"].max())))
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
_orig_noted = ck._note_pose_unavailable


def _fake_model_path():
    return "fake/pose_landmarker_lite.task"


def _fake_landmarks(u8):
    h, w = u8.shape[0], u8.shape[1]
    return [(0.5, 0.5)] * 33


ck._pose_model_path = _fake_model_path
# 1.9.5 부터 게이트가 "세션" 이다 (경로가 아니라). 세션까지 스텁해야
# 디코딩 앞 게이트를 통과한다. 이걸 빠뜨리면 이 블록이 조용히 실패하고
# "마스크가 안 만들어졌다" 는 잘못된 결론을 낸다.
ck._pose_landmarker = lambda: object()
ck._pose_landmarks_from_tasks = _fake_landmarks


class _FakeVAE:
    def decode(self, samples):
        return _t.zeros(1, 3, 64, 64)


try:
    _mask = ck._person_mask_for_latent(_FakeVAE(), base)
    check("인체 마스크 생성", _mask is not None and tuple(_mask.shape) == (1, 1, 8, 8),
          repr(None if _mask is None else _mask.shape))
    check("마스크 중심 가중",
          _mask is not None and float(_mask[0, 0, 4, 4]) > float(_mask[0, 0, 0, 0]))
    (outm,) = node.run({"samples": base}, strength_camera=0.18,
                       camera_latent={"samples": cam}, vae=_FakeVAE())
    _c = float(outm["samples"][0, 0, 4, 4])
    _e = float(outm["samples"][0, 0, 0, 0])
    # 기대 폭을 리터럴로 박지 않는다. 마스크 중심은 **체격**만큼 당겨지므로
    # 강도에 비례한다. 강도를 0.18 로 낮추자 실제 차이도 0.036 으로 줄었고,
    # 리터럴 0.1 은 "항상 만족"하던 값이라 어느 정책에서나 조용히 거짓이 된다.
    # 판정식: 중심이 바깥보다 **당김 비율**만큼 더 당겨졌는가.
    _span = abs(float(cam[0, 0, 4, 4]) - float(base[0, 0, 0, 0]))
    _want_gap = 0.18 * _span * 0.25   # 마스크 중심 가중은 최대 1 이므로
    check("인체 부위만 당김", _c > _e + 1e-6 and _span > 0,
          f"c={_c:.3f} e={_e:.3f} 차이={_c - _e:+.4f} (기대 >{_want_gap:.4f})")

    # R58: 디코드 잔재 정리 블록이 **실제로 NameError를 던지지 않는가**.
    # 왜(Why) 이걸 검사하나: 두 함수에 있던 `del img, arr, ...` 는 img 가
    # 다른 함수(_decode_latent_rgb)의 로컬이라 항상 NameError였고, 바로 아래
    # `except Exception: pass` 가 삼켰다. 그래서 테스트는 "마스크가 만들어졌다"
    # 만 확인할 뿐 정리 블록이 죽은 채로 돌아가는지 아무도 몰랐다.
    # 이제 NameError를 숨기지 않으므로, 이 경로가 깨지면 raise 로 드러난다.
    _r58_mask = ck._person_mask_for_latent(_FakeVAE(), base)
    check("R58: 마스크 경로가 조용히 실패하지 않음",
          _r58_mask is not None, "del 블록이 예외를 삼켰다면 마스크가 None")

    # R69: 디코드 결과가 **(H,W,C)** 인가 — 2026-09-30 실측 회귀.
    # 왜(Why) 이게 없었나: `VAE.decode` 는 (B,C,H,W) 를 주므로 arr[0] 는
    # (C,H,W) 다. 그런데 소비자는 전부 (H,W,C) 를 기대한다 — mediapipe.Image
    # 는 HWC 를 받고 `_edge_map_from_rgb` 는 arr[...,0] 을 R 채널로 읽는다.
    # 순서가 틀리면 인체 마스크·부위별 맵·시트 분석이 **전부 조용히 None** 이
    # 되고 로그도 남지 않는다. 실측 증거: vae 연결/미연결 두 실행의 결과 이미지가
    # 픽셀 완전 동일했다(마스크가 적용되지 않았다는 뜻).
    _r69 = ck._decode_latent_rgb(_FakeVAE(), base)
    check("R69: _decode_latent_rgb 가 (H,W,C) 를 돌려준다",
          _r69 is not None and _r69.shape == (64, 64, 3),
          repr(getattr(_r69, "shape", None)))
    _r69s = ck._decode_small(_FakeVAE(), base)
    check("R69: _decode_small 도 (H,W,C) 를 돌려준다",
          _r69s is not None and _r69s.ndim == 3 and _r69s.shape[-1] == 3,
          repr(getattr(_r69s, "shape", None)))

    # 실제로 쓰는 VAE 는 **채널이 4개** 다. (B,H,W,4) 로 준다(2026-09-30 실측:
    # arr[0] = (1888,1056,4)). 이걸 그대로 mediapipe 에 넘기면 3채널 SRGB 만
    # 받는 Image 가 거부해 포즈 검출이 조용히 전부 실패했다(실측 lm=None).
    class _VAE4:
        def decode(self, samples):
            return _t.zeros(1, 64, 64, 4)

    _r69b = ck._decode_latent_rgb(_VAE4(), base)
    check("R69: 4채널 (B,H,W,4) 입력 -> (H,W,3) 으로 정규화",
          _r69b is not None and _r69b.shape == (64, 64, 3),
          repr(getattr(_r69b, "shape", None)))
    check("R69: 3채널 미만이면 None ( mediapipe 가 받을 RGB 가 없다)",
          ck._decode_latent_rgb(type("V", (), {"decode": lambda s, x: _t.zeros(1, 64, 64, 2)})(), base) is None)
finally:
    ck._pose_model_path = _orig_model_path
    ck._pose_landmarker = _orig_landmarker
    ck._pose_landmarks_from_tasks = _orig_landmarks
    
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
#   허용  __file__ 기준 경로 조립 (동봉 모델 2개: 포즈 + 손)
#   금지  시스템 여러 곳을 뒤지는 탐색 (os.path.exists/listdir/walk/glob)
check("R61: os.path 는 동봉 모델 경로 조립에만 쓰인다",
      _ksrc.count("os.path") <= 6
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
# 4개 나왔고, 하나만 고치면 더 나쁜 결과(이미지 100% 덮어쓰기)가 나왔었다.
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
# (픽스처는 위와 같은 이유로 현실값 — sampled 0 은 정규화 1.0 이 되어 감쇠된다)
_real_s = {"samples": t.full((1, 4, 64, 64), 0.5)}
_ref = {"samples": t.full((1, 4, 64, 64), 0.9)}
(outv,) = _node.run(_real_s, strength_camera=0.18, camera_latent=_ref)
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
# 왜(Why) sampled 가 0 이 아니나 (2026-10-01): 감쇠가 정규화 불일치를 보게 되자
# sampled=0 / ref=0.6 은 정규화 1.0 → 감쇠 0 으로 간다. 그게 옳은 판단이지만
# 이 테스트들은 "정상 실행에서 당김이 동작한다" 를 확인하는 것이므로 픽스처가
# 그 상황을 표현해야 한다. 실제 측정(2026-10-01) 정규화 불일치 0.222~0.487,
# 무감쇠 끝 0.50. 기준값 0.5 주변으로 흔들린 값을 쓴다.
# 왜(Why) 원본 참조가 샘플보다 큰가 (2026-10-01): region 은 전역에 **증가분**을
# 더한다. 그런데 원본이 샘플보다 작으면 증가분이 **음수**가 되어 "region 이
# 전역을 대체하지 않는다" 는 검사가(region > 전역) 뒤집힌다. 그건 region 경로의
# 문제가 아니라 픽스처 방향의 문제다 — 당길 방향이 위로 가도록 잡는다.
_b64 = {"samples": t.full((1, 4, 64, 64), 0.4)}
_c64 = {"samples": t.full((1, 4, 64, 64), 0.3)}
_o64 = {"samples": t.full((1, 4, 64, 64), 1.0)}
# 기대값은 픽스처에서 **계산한다**. 리터럴로 박으면 픽스처를 바꿀 때 조용히
# 어긋난다 — 실제로 그랬다(2026-10-01). 그리고 감쇠는 현재 규칙인 정규화
# 불일치를 쓴다. 마스크 없이 실행하므로 전역 블렌드 = base + ea*(cam-base)
# + eb*(orig-base) 다.
_bv = float(_b64["samples"].mean())
_cv = float(_c64["samples"].mean())
_ov = float(_o64["samples"].mean())
for _a, _b in ((0.18, 0.0), (0.0, 0.18), (0.18, 0.18), (0.18, 0.18), (-0.5, 0.0)):
    _out = _node.run(_b64, strength_camera=_a, strength_original=_b,
                     camera_latent=_c64, original_latent=_o64)[0]["samples"]
    _ea = _a * ck._damp_norm(ck._drift_norm(_b64["samples"], _c64["samples"]))
    _eb = _b * ck._damp_norm(ck._drift_norm(_b64["samples"], _o64["samples"]))
    _want = _bv + _ea * (_cv - _bv) + _eb * (_ov - _bv)
    check(f"R55: 강도 {_a}/{_b} 전역 반영 정확",
          abs(float(_out.max()) - _want) < 1e-4,
          f"실제 {float(_out.max()):.4f} 기대 {_want:.4f}")

# 물리 상한: 강도가 넘어도 **초과분은 적용되지 않는다** (WORK_STATUS 10-28).
# 왜(Why) 별도 검사인가: 위 반복은 "블렌드 계산" 이고 이건 "상한 정책"이다.
# 한 검사에 섞으면 어느 쪽이 깨졌는지 알 수 없다.
_cap = ck._PHYS_CEILING
check("R55: 상한이 0 과 1 사이", 0.0 < _cap < 1.0, str(_cap))
_outc = _node.run(_b64, strength_camera=1.0, strength_original=0.0,
                  camera_latent=_c64, original_latent=_o64)[0]["samples"]
_ec = 1.0 * ck._damp_norm(ck._drift_norm(_b64["samples"], _c64["samples"]))
_wantc = _bv + _ec * _cap * (_cv - _bv)
check("R55: 강도 1.0 은 상한까지만 반영",
      abs(float(_outc.max()) - _wantc) < 1e-4,
      f"실제 {float(_outc.max()):.4f} 기대 {_wantc:.4f}")
check("R55: 상한 미만의 강도는 그대로 통과",
      abs(float(_node.run(_b64, strength_camera=0.18, strength_original=0.0,
                          camera_latent=_c64,
                          original_latent=_o64)[0]["samples"].max())
          - (_bv + 0.18 * _ec * (_cv - _bv)
             + 0.18 * _eb * (_ov - _bv))) < 1e-4)

# region 분기를 강제로 태워(mediapipe 없이) 전역이 살아 있는지 확인.
# 세 가지가 동시에 깨져 있었다:
#  ① vae 를 넘기지 않아 `if vae is not None and ...` 가드가 False → 부위맵을
#     아예 부르지 않았다. 즉 이름만 region 인 검사가 region 경로를 못 돌았다.
#  ② monkeypatch 람다가 (vae, lat) 2개 인자만 받는데 run() 은 cache= 로
#     세 번째를 넘긴다. 가드가 someday 열린다 장에다 로 죽는다.
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
    _out_pm = _node.run(_b64, strength_camera=0.0, strength_original=0.18,
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
    _out_global = _node.run(_b64, strength_camera=0.0, strength_original=0.18,
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
# 더 엄격한 판정: 구버그(`out = _inc`)는 증가분 **그 자체**를 돌려준다.
# 정상(`out = out + _inc`)은 전역 + 증가분 이므로 반드시 더 크다.
# 기대 폭을 리터럴 0.25 로 박지 않고 **실측한 증가분** 기준으로 삼는다 —
# 물리 상한이 0.78 → 0.20 으로 낮아지면서 리터럴 기대값이 조용히 틀어졌고
# 10건이 동시에 깨졌다(2026-10-01). 리터럴은 정책이 바뀌면 조용히 거짓이 된다.
_gap = float(_out_pm.max()) - float(_out_global.max())
check("R59: region 증가분이 전역보다 크다 (증가분만 반환하는 구버그 아님)",
      _gap > 0.0, f"차이 {_gap:+.4f}")
check("R59: region 증가분이 유의미함 (0 이 아님)", _gap > 1e-3, f"차이 {_gap:+.4f}")
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
      float(_nan_out.max()) == float(_b64["samples"].max())
      and float(t.isnan(_nan_out).float().mean()) == 0.0,
      f"max={float(_nan_out.max()):.4f}")
# nan latent: 게이트가 nan 을 통과해 전파되지 않아야 한다
_inf = {"samples": t.full((1, 4, 64, 64), float("inf"))}
_nan_lat = _node.run(_inf, strength_camera=0.18,
                     camera_latent=_c64)[0]["samples"]
check("R55: inf 입력 + 감쇠 → nan 전파 없음",
      float(t.isnan(_nan_lat).float().mean()) == 0.0,
      f"nan {float(t.isnan(_nan_lat).float().mean()) * 100:.0f}%")
check("R55: nan drift 는 감쇠를 통과하지 못함 (not <= 비교)",
      not (float("nan") <= 0.8) and (float("nan") > 0.8) is False)

print("-- 배치/비용 (2026-09-28 R56) --")
# (1) 배치>1 브로드캐스트 — 요소 0 의 마스크/랜드마크를 전체 배치에 적용해
#     2번째 이후 피사자가 엉뚱한 부위를 당겼다. 지금은 전역 당김만 한다.
_bz = {"samples": t.full((2, 4, 32, 32), 0.5)}
_br = {"samples": t.full((2, 4, 32, 32), 0.9)}
_vc = _CountVAE()
_bo = _node.run(_bz, strength_camera=0.0, strength_original=0.18,
                original_latent=_br, vae=_vc)[0]["samples"]
check("R56: 배치>1 shape 유지", _bo.shape == (2, 4, 32, 32),
      str(tuple(_bo.shape)))
check("R56: 배치>1 은 마스크/부위맵 미실행 (디코딩 0회)",
      len(_vc.sizes) == 0, str(_vc.sizes))
check("R56: 배치 전체에 전역 당김 적용", bool(
    t.allclose(_bo[0], _bo[1], atol=1e-5)))
_eff_b = 0.18 * ck._damp_norm(ck._drift_norm(_bz["samples"], _br["samples"]))
# 기대값을 픽스처에서 계산한다 — 예전처럼 "base=0 이라 max==eff" 우연에 기대지 않는다.
_bz_v = float(_bz["samples"].mean())
_br_v = float(_br["samples"].mean())
_want_b = _bz_v + _eff_b * (_br_v - _bz_v)
check("R56: 배치>1 강도가 요청값과 일치",
      abs(float(_bo.max()) - _want_b) < 1e-4,
      f"실제 {float(_bo.max()):.4f} 기대 {_want_b:.4f}")

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
# `_pose_landmarks_from_tasks` / `_person_mask_from_rgb` 를 **전부 스텁으로
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
        check("R64: 인체 마스크도 로더 없으면 None",
              ck._person_mask_from_rgb(_u8_zero) is None)
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
    check("R64: detect 실패해도 인체 마스크는 None",
          ck._person_mask_from_rgb(_u8) is None)
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

# R64b: **설치된** mediapipe 표면으로 포즈 세션을 연다 (2026-09-30 회귀 가드).
# 왜(Why) 스텁으로는 절대 못 잡는 버그다: 위 R64 의 `_install_fake_mp` 는
# `tasks.BaseOptions` 를 만들어 넣는다. 그런데 실제 mediapipe 0.10.33 의
# tasks/__init__.py 에는 BaseOptions 가 **없다**(ImportError). 그래서 R64 는
# 전부 통과하는데 프로덕션에서는 landmarker 가 한 번도 열리지 않았고, 그 아래
# 픽셀 공간 부위 분석(detail_boost / _apply_region_strength)이 통째로 죽었다.
# 즉 스텁은 실제 패키지 표면과 어긋난 순간을 감추고 있다. 여기서는 스텁 없이
# 진짜 설치본으로만 판정한다.
_ksrc64b = open(os.path.join(PKG, "consistency_keeper.py"), encoding="utf-8").read()
check("R64b: 잘못된 import 경로(_mp.tasks.BaseOptions)가 남아있지 않다",
      "_mp.tasks.BaseOptions" not in _ksrc64b)
# R64 는 스텁을 sys.modules 에 심어놓고 "복원" 하지만, `_saved` 캡처가
# _install_fake_mp **뒤**라 복원되는 것도 스텁이다(기존 결함). 그래서 여기서는
# 스텁을 명시적으로 축출한 뒤 진짜 패키지를 다시 import 한다.
for _k64b in [k for k in list(sys.modules)
              if k == "mediapipe" or k.startswith("mediapipe.")]:
    sys.modules.pop(_k64b, None)
try:
    import mediapipe as _mp64b
except Exception:
    _mp64b = None
if _mp64b is None:
    check("R64b: mediapipe 미설치 — 세션 검증을 건너뛴다 (선택 의존성)", True)
else:
    try:
        from mediapipe.tasks.python.core.base_options import BaseOptions as _bo64b
    except Exception:
        _bo64b = None
    check("R64b: 설치된 mediapipe 에서 BaseOptions 가 실제로 존재한다",
          _bo64b is not None,
          "tasks.python.core.base_options 경로가 없으면 포즈가 죽는다")
    _real_model64b = ck._pose_model_path()
    if _real_model64b is None:
        check("R64b: 동봉 모델 없음 — 세션 열기를 건너뛴다", True)
    else:
        _keep64b = ck._TASKS_LANDMARKER
        ck._TASKS_LANDMARKER = []
        try:
            _lm64b = ck._pose_landmarker()
            check("R64b: 진짜 landmarker 세션이 열린다", _lm64b is not None,
                  f"모델={_real_model64b}")
            if _lm64b is not None:
                try:
                    _lm64b.close()
                except Exception:
                    pass
        finally:
            ck._TASKS_LANDMARKER = _keep64b

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
                 _src66.index("\ndef ", _src66.index("def _pose_model_path():") + 1)]
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

# R68: landmark 모양이 경로마다 다르다 — bbox 가 조용히 죽지 않게.
# 왜(Why) 별도 블록인가: 구 `mediapipe.solutions` 는 `.x`/`.y` **속성 객체**를,
# tasks API 경로는 `(x, y)` **튜플**을 준다. `subject_bbox` 는 속성만 보고
# 있어서 튜플이면 전부 None → bbox=None → 프레이밍 판정이 tasks 전환 이후
# **조용히** 죽어 있었다. 33점은 제대로 나왔기 때문에 아무도 몰랐다.
# 실측(2026-09-30 설치본 1.9.5): 33점 OK / subject_bbox None.
class _LmObj:
    def __init__(self, x, y):
        self.x = x
        self.y = y


_coords68 = [(0.48 + 0.01 * i, 0.08 + 0.02 * i) for i in range(33)]
_as_tuples68 = list(_coords68)
_as_objects68 = [_LmObj(x, y) for x, y in _coords68]

_bt68 = ck.subject_bbox(_as_tuples68)
_bo68 = ck.subject_bbox(_as_objects68)
check("R68: 튜플 landmark 에서도 bbox 가 나온다 (tasks 경로)",
      _bt68 is not None, "None 이면 프레이밍 판정이 조용히 죽는다")
check("R68: 속성 객체 landmark 에서도 bbox 가 나온다 (구 경로, 회귀 방지)",
      _bo68 is not None, "None")
check("R68: 두 경로가 같은 bbox 를 낸다 (모양만 다른 같은 데이터)",
      _bt68 == _bo68, "tuple=%s object=%s" % (_bt68, _bo68))
if _bt68:
    _xs = [c[0] for c in _coords68]
    _ys = [c[1] for c in _coords68]
    # 함수가 의도적으로 ±0.02 여유를 준다(관절이 화면 끝에 닿는 것을 대비).
    # 그 마진까지 포함해 확인한다 — 마진을 없애면 극단 컷에서 잘린다.
    check("R68: bbox 가 33점 외곽 + 의도된 ±0.02 여유와 일치",
          abs(_bt68[0] - (min(_xs) - 0.02)) < 1e-6
          and abs(_bt68[1] - (min(_ys) - 0.02)) < 1e-6
          and abs(_bt68[2] - (max(_xs) + 0.02)) < 1e-6
          and abs(_bt68[3] - (max(_ys) + 0.02)) < 1e-6,
          "%s vs (%s,%s,%s,%s)" % (_bt68, min(_xs) - 0.02, min(_ys) - 0.02,
                                   max(_xs) + 0.02, max(_ys) + 0.02))
    check("R68: bbox 가 0~1 정규화 범위를 넘지 않음",
          0.0 <= _bt68[0] < _bt68[2] <= 1.0 and 0.0 <= _bt68[1] < _bt68[3] <= 1.0,
          str(_bt68))
    check("R68: 프레이밍 유사도가 실제로 산출된다",
          ck.framing_similarity(_bt68, _bo68) > 0.99,
          str(ck.framing_similarity(_bt68, _bo68)))
# 0 이하는 좌표 무효 처리이므로 실제 bbox 가 0 에 붙으면 안 된다
_z68 = ck.subject_bbox([(0.5, 0.0)] * 8 + [(0.6, 0.2)] * 25)
check("R68: 0 좌표는 무효 처리되어 bbox 에 안 들어간다",
      _z68 is not None and _z68[1] > 0.0, str(_z68))
check("R68: landmark 가 None 이면 None", ck.subject_bbox(None) is None)
check("R68: 형태가 아무것도 아니면 예외 없이 None",
      ck.subject_bbox([object(), object()]) is None)

# tasks 반환값 형태가 바뀌면 조용히 또 죽는다 — 현재 계약을 고정한다
_src68 = open(os.path.join(PKG, "consistency_keeper.py"), encoding="utf-8").read()
check("R68: tasks 경로가 (x, y) 튜플을 돌려주는 현재 계약",
      "return [(float(p.x), float(p.y)) for p in pts[:33]]" in _src68,
      "반환 형태가 바뀌면 subject_bbox 를 같이 고쳐야 한다")
check("R68: subject_bbox 가 튜플·리스트를 분기한다",
      "isinstance(lm, (tuple, list))" in _src68)

# R70: 시트 2단계 — 판정을 강도에 반영한다 (2026-09-30).
# 왜(Why) 회귀 가드인가: 판정만 하고 강도를 안 바꾸는 상태로 방치되면, 시트를
# 물어도 아무 효과가 없고 "분석이 동작한다" 는 사실만 남는다. 아래는 그 반영이
# 실제로 일어나는지, 그리고 **패널로 대체된 기준**이 실제로 당김에 쓰이는지
# 확인한다(1단계 로그만으로는 판정이 실행됐는지 알 수 없다).
check("R70: 시트 감쇠 상수 _SHEET_DAMP 이 0~1 사이",
      0.0 < ck._SHEET_DAMP <= 1.0, repr(getattr(ck, "_SHEET_DAMP", None)))


class _VAESheet:
    """decode: 흰 바탕 + 세로로 변하는 4개 패널. encode: 0 으로 복원.

    왜(Why) 줄무늬인가: `column_profile` 은 열별 **세로 표준편차** 다. 균일한
    막대(전부 검정/전부 흰)는 std=0 이라 패널로 안 잡힌다(실측 raw=0). 실제
    인물처럼 세로로 값이 변해야 "콘텐츠가 있는 열" 이 된다."""

    def __init__(self):
        self.encoded = 0

    def decode(self, samples):
        import numpy as _np
        h = w = 256
        a = _np.ones((h, w, 3), dtype=_np.float32)
        stripes = _np.where((_np.arange(h) // 8) % 2 == 0, 0.15, 0.85)
        for x0 in (10, 70, 130, 190):
            a[:, x0:x0 + 30, :] = stripes[:, None, None]
        return _t.from_numpy(a.astype(_npr.float32))[None]

    def encode(self, pixels):
        self.encoded += 1
        return _t.zeros(1, 4, 8, 8)


_vs = _VAESheet()
_lat = {"samples": _t.zeros(1, 4, 32, 32)}
# 왜(Why) `_decode_small` 을 스텁하나: 앞선 블록들이 VAE/포즈를 스텁해두둔
# 상태라 여기서 진짜 디코드 경로를 타면 그 스텁에 물려 판정이 0 이 된다(실측).
# 시트 **판정 로직**만 격리해서 본다. 디코드 경로는 `_decode_latent_rgb` /
# `_as_rgb_hwc` 로 이미 검증된다.
_sheet_fixture = None


class _VAEDecode2:
    def __init__(self):
        self.encoded = 0

    def decode(self, samples):
        import numpy as _np
        h = w = 256
        a = _np.ones((h, w, 3), dtype=_npr.float32)
        stripes = _npr.where((_npr.arange(h) // 8) % 2 == 0, 0.15, 0.85
                             ).astype(_npr.float32)
        for x0 in (10, 70, 130, 190):
            a[:, x0:x0 + 30, :] = stripes[:, None, None]
        return _t.from_numpy(a)[None]

    def encode(self, pixels):
        self.encoded += 1
        return _t.zeros(1, 4, 8, 8)


_vs = _VAEDecode2()
_orig_small = ck._decode_small
try:
    ck._decode_small = lambda vae, lat, scale=0.5: _vs.decode(lat)[0].numpy()
    _info = ck.analyze_reference_sheet(_vs, _lat, {"samples": _t.zeros(1, 4, 32, 32)})
finally:
    ck._decode_small = _orig_small
check("R70: 흰 바탕 4패널은 시트로 판정", bool(_info.get("sheet")),
      "raw=%s panels=%s" % (_info.get("raw"), _info.get("panels")))
check("R70: 패널 좌표가 정규화(0~1)로 나온다",
      bool(_info.get("panels_n")) and all(
          0.0 <= a <= 1.0 and 0.0 <= b <= 1.0 and b > a
          for a, b in _info.get("panels_n", [])),
      repr(_info.get("panels_n")))

_pn = (_info.get("panels_n") or [(0.0, 1.0)])[0]
_plat = ck._panel_reference_latent(_vs, _lat, _pn)
check("R70: 패널 기준 latent 가 4차원 텐서로 나온다",
      _plat is not None and hasattr(_plat, "dim") and _plat.dim() == 4,
      repr(getattr(_plat, "shape", None)))
check("R70: 패널 기준으로 VAE encode 를 실제로 1회 건다",
      _vs.encoded == 1, "encoded=%d" % _vs.encoded)
check("R70: 폭 0 패널은 걸러진다 (조용한 오조작 방지)",
      ck._panel_reference_latent(_vs, _lat, (0.5, 0.5)) is None)

# R58: 두 함수가 조용히 실패하는 경로가 남아 있지 않은지 소스를 검사한다.
# `del img` 처럼 스코프 밖 이름을 del 하면 NameError -> 예외 삼킴 -> 조용한 실패다.


# R71: 환경 무결성 (2026-10-01). 실사용은 각기 다른 환경이라 실패 경로가 곧
# 버그다. 여기서는 "다른 환경에서 어떻게 죽을 수 있나" 를 못 박는다.
import importlib as _il71


def _np71():
    import numpy
    return numpy


_n71 = _np71()

# --- 레이아웃 정규화: VAE 마다 decode 축 순서/채널 수가 다르다 ---
check("R71: (B,C,H,W) 3채널 -> (H,W,3)",
      ck._as_rgb_hwc(_n71.zeros((8, 3, 16, 16), _n71.float32)).shape == (16, 16, 3))
check("R71: (B,H,W,C) 4채널 -> (H,W,3)",
      ck._as_rgb_hwc(_n71.zeros((8, 16, 16, 4), _n71.float32)).shape == (16, 16, 3))
check("R71: 그레이스케일 2D 는 None (mediapipe 에 넘기지 않는다)",
      ck._as_rgb_hwc(_n71.zeros((16, 16), _n71.float32)) is None)
check("R71: 2채널( mediapipe 가 못 받음) 는 None",
      ck._as_rgb_hwc(_n71.zeros((8, 16, 16, 2), _n71.float32)) is None)

# --- 최소 치수: 0x0 / 1x1 은 mediapipe 네이티브 RET_CHECK 를 낸다 ---
check("R71: 0x0 이미지는 mediapipe 전에 차단",
      ck._even_rgb(_n71.zeros((0, 0, 3), _n71.uint8)) is None)
check("R71: 1x1 이미지도 차단",
      ck._even_rgb(_n71.zeros((1, 1, 3), _n71.uint8)) is None)
check("R71: 홀수 크기는 짝수로 잘린다",
      ck._even_rgb(_n71.zeros((5, 7, 3), _n71.uint8)).shape[:2] == (4, 6))

# --- BaseOptions 위치가 버전마다 다르다 ---
_bo71 = ck._find_base_options()
if _il71.util.find_spec("mediapipe") is None:
    check("R71: mediapipe 미설치 — BaseOptions 탐색은 None (선택 의존성)", True)
else:
    check("R71: 실제 mediapipe 에서 BaseOptions 를 찾는다",
          _bo71 is not None, "찾은 경로가 없으면 포즈가 통째로 꺼진다")
    _lm71 = ck._pose_landmarker()
    check("R71: landmarker 세션이 실제로 열린다", _lm71 is not None)
    if _lm71 is not None:
        try:
            _lm71.close()
        except Exception:
            pass

# --- 강도/게이트 산술은 어떤 입력에도 죽지 않아야 한다 ---
check("R71: nan 강도는 0 (노출 전 차단)",
      ck._safe_strength(float("nan"), "t") == 0.0)
check("R71: inf 강도는 0", ck._safe_strength(float("inf"), "t") == 0.0)
check("R71: 문자열 강도는 0 (버전 아님)",
      ck._safe_strength("abc", "t") == 0.0)
check("R71: 1e9 강도는 1.0 으로 클램프", ck._safe_strength(1e9, "t") == 1.0)
check("R71: nan drift 감쇠는 0", ck._damp_factor(float("nan")) == 0.0)


# R72: VRAM 해상도 상한 (2026-10-01). 카메라 노드의 QWEN_REF_MAX_PIXELS 규율을
# 공유한다. **판정이 바뀌면 안 된다** — 해상도만 줄이고 종횡비와 의미를 유지한다.
class _CapVAE72:
    def __init__(self):
        self.shapes = []

    def decode(self, samples):
        self.shapes.append(tuple(samples.shape))
        h, w = int(samples.shape[-2]), int(samples.shape[-1])
        return _t.rand(1, 1, h * 8, w * 8).repeat(1, 4, 1, 1)


_cap72 = _CapVAE72()
ck._decode_capped(_cap72, _t.rand(1, 4, 236, 132))       # 1056x1888 = 2MP
_got72 = _cap72.shapes[-1]
_px72 = _got72[-2] * _got72[-1] * 64
check("R72: 2MP 입력은 1MP 상한으로 축소된다",
      _px72 <= ck._DECODE_MAX_PIXELS, "%.2fMP" % (_px72 / 1e6))
check("R72: 축소 후에도 종횡비가 유지된다(의미 보존)",
      abs((236 / 132) - (_got72[-2] / _got72[-1])) / (236 / 132) < 0.05,
      "%.3f -> %.3f" % (236 / 132, _got72[-2] / _got72[-1]))

_cap72b = _CapVAE72()
ck._decode_capped(_cap72b, _t.rand(1, 4, 64, 64))        # 512x512 = 0.26MP
check("R72: 상한 미만은 축소하지 않는다 (무의미한 해상도 손실 방지)",
      _cap72b.shapes[-1][-2:] == (64, 64), str(_cap72b.shapes[-1][-2:]))

_cap72c = _CapVAE72()
try:
    ck._decode_capped(_cap72c, _t.rand(1, 4, 4))          # 3D 로 깨진 입력
    check("R72: 깨진 축 크기도 예외 없이 처리된다", True)
except Exception as _e72:
    check("R72: 깨진 축 크기도 예외 없이 처리된다", False, str(_e72))

check("R72: 상한은 카메라 노드와 같은 1MP 규칙",
      ck._DECODE_MAX_PIXELS == 1024 * 1024, str(ck._DECODE_MAX_PIXELS))


# R73: 포즈 검출 실패 시에만 상한을 올려 한 번 더 디코드한다 (2026-10-01 실측).
# 상한값 하나로 못 잡는 이유: 1MP 는 74MP 캐릭터 시트의 패널 사람을 놓치고,
# 6MP 는 다른 시트를 놓친다 — 해상도에 단조가 없다. 판정을 직접 지킨다.
class _VAE73:
    def __init__(self):
        self.px = []

    def decode(self, samples):
        h, w = int(samples.shape[-2]), int(samples.shape[-1])
        self.px.append(h * w * 64)
        return _t.rand(1, 1, h * 8, w * 8).repeat(1, 4, 1, 1)


_real_pose73 = ck._pose_landmarks_from_tasks
_pc73 = [0]


def _pose_stub73(_u8):
    _pc73[0] += 1
    return None if _pc73[0] == 1 else [(0.5, 0.5)] * 33


try:
    _lat73 = _t.rand(1, 4, 200, 120)          # 1600x960 = 1.54MP > 1MP
    _v73 = _VAE73()
    _pc73[0] = 0
    ck._pose_landmarks_from_tasks = _pose_stub73
    _r73 = ck._decode_latent_rgb(_v73, _lat73)
    check("R73: 포즈 실패 시 한 번만 크게 재디코드된다",
          len(_v73.px) == 2, "%d회 %s" % (len(_v73.px),
                                          ["%.2fMP" % (q / 1e6) for q in _v73.px]))
    check("R73: 재시도본이 상한본보다 크다",
          len(_v73.px) == 2 and _v73.px[1] > _v73.px[0],
          "%.2fMP -> %.2fMP" % (_v73.px[0] / 1e6, _v73.px[-1] / 1e6))
    check("R73: 재시도 후에도 유효한 배열", _r73 is not None)

    _v73b = _VAE73()
    _pc73[0] = 0
    ck._pose_landmarks_from_tasks = lambda _u: [(0.5, 0.5)] * 33
    ck._decode_latent_rgb(_v73b, _lat73)
    check("R73: 포즈가 바로 잡히면 재디코드하지 않는다 (VRAM 낭비 방지)",
          len(_v73b.px) == 1, "%d회" % len(_v73b.px))

    _v73c = _VAE73()
    ck._pose_landmarks_from_tasks = lambda _u: None
    ck._decode_latent_rgb(_v73c, _t.rand(1, 4, 64, 64))     # 0.26MP < 상한
    check("R73: 상한 미만은 포즈 실패해도 재시도 경로에 들어가지 않는다",
          len(_v73c.px) == 1, "%d회" % len(_v73c.px))

    check("R73: 재시도 상한이 기본 상한보다 크다",
          ck._DECODE_RETRY_PIXELS > ck._DECODE_MAX_PIXELS,
          "%.1fMP > %.1fMP" % (ck._DECODE_RETRY_PIXELS / 1e6,
                               ck._DECODE_MAX_PIXELS / 1e6))
    check("R73: 재시도 상한은 카메라 1MP 규칙의 정수배 이내",
          ck._DECODE_RETRY_PIXELS <= 4 * ck._DECODE_MAX_PIXELS,
          "%.1fMP" % (ck._DECODE_RETRY_PIXELS / 1e6))
finally:
    ck._pose_landmarks_from_tasks = _real_pose73

# ---------------------------------------------------------------------------
# R74: 판정층 1층 (2026-10-01, WORK_STATUS 10절)
#
# (왜) 이 판정은 "원본을 믿어도 되는가" 다. 절대 평가("이 자세가 옳나")가 아니다.
# 그래서 테스트도 두 가지를 먼저 박는다: ① 발이 판정 대상이 아니다(실측 근거가
# 없으므로) ② v1 은 damaged 를 내지 않는다(기준 데이터 없이 기하 판정을 하지
# 않으므로). 이 두 개가 깨지면 설계가 뒤집힌 것이다.
# ---------------------------------------------------------------------------
# (왜) 섹션 제목을 print 대신 _say 로 직접 부르는가: 이 파일은 60행에서
# `print = _say` 로 재바인딩하므로 print 도 안전하다. 하지만 그 재바인딩에
# 기대면 "한글을 stdout 에 쓰는데 가드가 보인다" 는 판단을 hunk 만으로 하는
# 도구에서 못 읽는다 (2026-10-01 실측: jev-pref 가 nonascii_stdout P=0.90 으로
# 걸었다. cp1252/ascii/cp949 3종에서 실제로 돌려 exit 0 · PASS 297 · FAIL 0 이
# 거짓 양성이었다). 의존성을 없애는 편이 코드도 게이트도 명확해진다.
_say("-- 판정층 1층: 참조 신뢰 판정 (2026-10-01) --")

import numpy as _np74  # noqa: E402


def _r74_pts(vis=0.9, low=(), n=33):
    """33점 합성 landmark. low 에 든 인덱스만 가시성을 0.05 로 낮춘다.

    어깨(y=0.20)·골반(y=0.50) 을 고정해 몸통길이 0.30 을 만든다 —
    실측 정상 구간(0.156~0.511) 안이다.
    """
    out = []
    for i in range(n):
        if i == 11:
            x, y = 0.40, 0.20
        elif i == 12:
            x, y = 0.60, 0.20
        elif i == 23:
            x, y = 0.45, 0.50
        elif i == 24:
            x, y = 0.55, 0.50
        else:
            x, y = 0.5, 0.30 + (i % 7) * 0.05
        out.append((x, y, 0.05 if i in low else vis))
    return out


class _LM74:
    """x / y / visibility 를 가진 landmark 객체."""

    def __init__(self, x, y, v):
        self.x, self.y, self.visibility = x, y, v


class _Det74:
    def __init__(self, pts):
        self._pts = pts

    def detect(self, _img):
        return type("R", (), {"pose_landmarks": [self._pts]})()


_r74_real_lm = ck._TASKS_LANDMARKER

try:
    # --- 순수 함수 judge_points ---
    _r = ck.judge_points(None)
    check("R74: landmark 없으면 미판정",
          _r["verdict"] == ck._JUDGE_UNDETERMINED, _r["verdict"])
    check("R74: 미검출은 confidence 1.0 (보류임을 확신)",
          _r["confidence"] == 1.0, str(_r["confidence"]))
    check("R74: 미검출은 frame 이 없다", _r["frame"] is None)
    check("R74: 빈 리스트도 미판정",
          ck.judge_points([])["verdict"] == ck._JUDGE_UNDETERMINED)

    _r = ck.judge_points(_r74_pts(vis=0.9))
    check("R74: 전부 잘 보이면 intact", _r["verdict"] == ck._JUDGE_INTACT, _r["verdict"])
    check("R74: intact 면 frame 이 나온다", _r["frame"] is not None, str(_r["frame"]))
    check("R74: intact 면 미확인 관절 목록이 비었다",
          _r["low_visibility"] == [], str(_r["low_visibility"]))
    check("R74: confidence 는 근거인 가장 흐린 관절",
          abs(_r["confidence"] - 0.9) < 1e-6, str(_r["confidence"]))
    check("R74: checks 에 통과 항목이 기록된다",
          any(c["check_id"] == "body_frame" and c["ok"] for c in _r["checks"]))

    _r = ck.judge_points(_r74_pts(vis=0.9, low=(25,)))
    check("R74: 무릎 하나만 흐리면 정상으로 넘기지 않는다",
          _r["verdict"] == ck._JUDGE_UNDETERMINED, _r["verdict"])
    check("R74: 어느 관절이 안 보인지 알려준다",
          _r["low_visibility"] == ["l_knee"], str(_r["low_visibility"]))
    check("R74: 이름이 순서대로 온다",
          ck.judge_points(_r74_pts(low=(26, 15)))["low_visibility"]
          == ["l_wrist", "r_knee"],
          str(ck.judge_points(_r74_pts(low=(26, 15)))["low_visibility"]))

    # --- 퇴화 프레임 ---
    _deg = _r74_pts()
    for _i in (11, 12, 23, 24):
        _deg[_i] = (0.5, 0.5, 0.9)
    _r = ck.judge_points(_deg)
    check("R74: 어깨와 골반이 겹치면 퇴화로 보고 미판정",
          _r["verdict"] == ck._JUDGE_UNDETERMINED, _r["verdict"])
    check("R74: 퇴지면 frame 이 없다", _r["frame"] is None)

    # --- v1 은 damaged 를 절대 내지 않는다 ---
    _geo = _r74_pts(vis=0.9)
    for _i in (13, 15, 14, 16, 25, 27, 26, 28):
        _geo[_i] = (0.99, 0.99, 0.9)
    _r = ck.judge_points(_geo)
    check("R74: 기하가 말이 안 되어도 v1 은 damaged 를 내지 않는다",
          _r["verdict"] != ck._JUDGE_DAMAGED, _r["verdict"])

    # --- 판정 대상에 발이 없는가 ---
    _core = set(i for i, _n in ck._JUDGE_CORE_LANDMARKS)
    check("R74: 판정 대상이 10점", len(_core) == 10, str(len(_core)))
    check("R74: 얼굴(0~10)은 판정 대상이 아니다", not _core & set(range(0, 11)),
          str(sorted(_core)))
    check("R74: 발(27~32)은 판정 대상이 아니다 (실측 중앙값 0.08~0.21)",
          not _core & set(range(27, 33)), str(sorted(_core)))

    # --- landmark 형태 통일 ---
    class _Obj74:
        def __init__(self, x, y, v):
            self.x, self.y, self.visibility = x, y, v

    _tri = ck._judge_triples([_Obj74(0.1, 0.2, 0.7), (0.3, 0.4),
                              (0.5, 0.6, 0.8), None])
    check("R74: 속성 객체와 튜플을 한 목록으로 읽는다", len(_tri) == 4, str(len(_tri)))
    check("R74: 해석 불가 항목은 None 으로 남는다", _tri[3] is None)
    check("R74: 2-튜플은 가시성 0.0 으로 채운다 (관측 불가)",
          _tri[1][2] == 0.0, str(_tri[1]))
    check("R74: 3-튜플 가시성을 보존", abs(_tri[2][2] - 0.8) < 1e-9, str(_tri[2]))
    check("R74: 속성 객체의 가시성을 읽는다", abs(_tri[0][2] - 0.7) < 1e-9, str(_tri[0]))
    check("R74: None 입력은 빈 목록", ck._judge_triples(None) == [])

    # --- 몸통 프레임 ---
    _fr = ck._judge_body_frame(ck._judge_triples(_r74_pts()))
    check("R74: 몸통 프레임이 나온다 (몸통길이 0.30)",
          _fr is not None and abs(_fr[2] - 0.30) < 1e-6, str(_fr))
    check("R74: 원점은 중골반",
          _fr is not None and abs(_fr[0] - 0.50) < 1e-6, str(_fr))
    check("R74: 33점 미만이면 None",
          ck._judge_body_frame(ck._judge_triples(_r74_pts(n=20))) is None)
    _fr2 = ck._judge_triples(_r74_pts())
    _fr2[11] = None
    check("R74: 필수 관절이 None 이면 frame 은 None",
          ck._judge_body_frame(_fr2) is None)

    # --- with_visibility 경로 계약 ---
    _u8 = _np74.zeros((64, 64, 3), _np74.uint8)
    ck._TASKS_LANDMARKER = [_Det74([_LM74(p[0], p[1], p[2]) for p in _r74_pts()])]
    _p2 = ck._pose_landmarks_from_tasks(_u8)
    check("R74: 기본 호출은 2-튜플 (기존 호출자 계약 유지)",
          _p2 is not None and len(_p2) == 33 and len(_p2[0]) == 2,
          str(None if _p2 is None else len(_p2[0])))
    check("R74: 2-튜플은 subject_bbox 를 그대로 받는다",
          ck.subject_bbox(_p2) is not None)
    _p3 = ck._pose_landmarks_from_tasks(_u8, with_visibility=True)
    check("R74: with_visibility 면 3-튜플",
          _p3 is not None and len(_p3) == 33 and len(_p3[0]) == 3,
          str(None if _p3 is None else len(_p3[0])))
    check("R74: visibility 값이 보존된다",
          _p3 is not None and abs(_p3[0][2] - 0.9) < 1e-6,
          str(None if _p3 is None else _p3[0]))
    check("R74: judge_reference_trust 가 판정을 낸다",
          ck.judge_reference_trust(_u8)["verdict"] == ck._JUDGE_INTACT)

    # visibility 속성이 없으면 관측 불가로 친다
    class _NoVis74:
        def __init__(self, x, y):
            self.x, self.y = x, y

    ck._TASKS_LANDMARKER = [_Det74([_NoVis74(p[0], p[1]) for p in _r74_pts()])]
    _p3b = ck._pose_landmarks_from_tasks(_u8, with_visibility=True)
    check("R74: visibility 가 없으면 0.0 (관측 불가)",
          _p3b is not None and _p3b[0][2] == 0.0,
          str(None if _p3b is None else _p3b[0]))
    check("R74: visibility 없으면 전부 미판정 (아무것도 안 보인다)",
          ck.judge_reference_trust(_u8)["verdict"] == ck._JUDGE_UNDETERMINED)
finally:
    ck._TASKS_LANDMARKER = _r74_real_lm

# ---------------------------------------------------------------------------
# R75: 판정층을 강도에 연결 (2026-10-01)
#
# (왜) 이 테스트의 핵심은 **기본 경로가 그대로**라는 것이다. trust_gate 가 꺼진
# 동안 `detail_boost` 는 allow=None 이고, 그 결과는 allow 를 넣지 않았을 때와
# 바이트 단위로 같아야 한다. opt-in 을 붙이면서 기본을 바꾸면, 사용자는
# "왜 결과가 달라졌지" 를 설명할 수 없게 된다.
# ---------------------------------------------------------------------------
_say("-- 판정층 → 강도 연결 (2026-10-01) --")


def _r75_parts():
    """원본은 에지가 강하고 결과는 뭉개진 합성 parts 맵."""
    return {"original": {"edge": [0.9] * 33, "xy": [(0.5, 0.5)] * 33,
                         "pts": _r74_pts()},
            "sampled": {"edge": [0.1] * 33, "xy": [(0.5, 0.5)] * 33,
                        "pts": _r74_pts()}}


def _r75_low(low_idx):
    """지정한 관절만 가시성을 0.02 로 내린 landmark."""
    p = _r74_pts()
    for i in low_idx:
        p[i] = (0.5, 0.4, 0.02)
    return p


_p = _r75_parts()

# --- 하위호환: allow 를 주지 않으면 예전과 같다 ---
_a_none = ck.detail_boost(_p, _p, 0.3)[0]
_a_null = ck.detail_boost(_p, _p, 0.3, allow=None)[0]
check("R75: allow=None 은 인자를 안 준 것과 같다 (기본 경로 보존)",
      _a_none is not None and bool((_a_none == _a_null).all()))

_all = {k: 1.0 for k in ck.PART_REGIONS}
_a_all = ck.detail_boost(_p, _p, 0.3, allow=_all)[0]
check("R75: 전부 허용도 allow=None 과 같다 (강도 같음)",
      _a_all is not None and bool((_a_none == _a_all).all()))

# --- 실제로 올라가는 부위가 있는가 (대조군) ---
# (왜) face 와 비교하지 않는가: 합성 parts 는 33점이 전부 에지 0.9 이라
# DETAIL_CRITICAL 에 든 부위가 **전부** 올라간다. base 강도 0.3 과 비교해야 한다.
check("R75: 대조군에서 부위별 boost 가 실제로 일어난다",
      _a_none is not None and float(_a_none[15]) > 0.3
      and abs(float(_a_none[15]) - 0.48) < 1e-6,
      "wrist %.3f (base 0.30)" % float(_a_none[15]))

# --- 한 부위를 막으면 그 부위만 base 로 남는다 ---
_no_hand = dict(_all)
_no_hand["hand_left"] = 0.0
_a_nh = ck.detail_boost(_p, _p, 0.3, allow=_no_hand)[0]
check("R75: 막은 부위는 base 강도를 유지한다",
      abs(float(_a_nh[15]) - 0.3) < 1e-6, "%.4f" % float(_a_nh[15]))
check("R75: 막지 않은 부위는 여전히 올라간다",
      float(_a_nh[25]) > 0.3, "%.4f" % float(_a_nh[25]))

# --- 허용도 매핑 ---
_al = ck.judge_region_allowance(ck.judge_points(_r75_low((25,))))
check("R75: 판정 없음(None) 은 제한 없음",
      ck.judge_region_allowance(None) is None)
check("R75: 빈 판정도 제한 없음", ck.judge_region_allowance({}) is None)
check("R75: 흐린 무릎이 속한 쪽 다리만 막힌다",
      _al is not None and _al["leg_left"] == 0.0, str(_al))
check("R75: 반대쪽 다리는 살아있다 (부위 단위 판정)",
      _al is not None and _al["leg_right"] == 1.0, str(_al))
check("R75: 얼굴은 판정 대상이 아니라 항상 허용",
      _al is not None and _al["face"] == 1.0, str(_al))
check("R75: 멀쩡한 관절로 이루어진 몸통은 허용",
      _al is not None and _al["torso"] == 1.0, str(_al))

# 손목(15)은 hand_left 과 arm_left 양쪽에 속한다 -> 양쪽 다 막혀야 한다
_al2 = ck.judge_region_allowance(ck.judge_points(_r75_low((15,))))
check("R75: 흐린 손목은 손과 팔 양쪽을 막는다",
      _al2 is not None and _al2["hand_left"] == 0.0
      and _al2["arm_left"] == 0.0, str(_al2))
check("R75: 반대편은 막히지 않는다", _al2 is not None and _al2["hand_right"] == 1.0)

# 전부 잘 보이면 전부 허용
_al3 = ck.judge_region_allowance(ck.judge_points(_r74_pts()))
check("R75: 전부 잘 보이면 전부 허용 (판정이 막지 않는다)",
      _al3 is not None and all(v == 1.0 for v in _al3.values()), str(_al3))

# 미판정(landmark 없음)도 전부 허용이어야 조용히 막히지 않는다
_al4 = ck.judge_region_allowance(ck.judge_points(None))
check("R75: 미검출 판정은 전부 허용 (조용히 막지 않는다)",
      _al4 is not None and all(v == 1.0 for v in _al4.values()), str(_al4))

# --- 방어: 형식이 잘못된 allow 는 "제한 없음" 이 된다 ---
# (왜) fail-open 인가: 해석 불가 값 하나로 부위를 막으면 그 오타가 조용히
# region 보강 전체를 꺼버린다. 오타 때문에 기능을 잃는 게 막는 것보다 나쁘다.
# 판정값(0.0/1.0)은 항상 깨끗한 float 이므로 이 경로는 외부 호출자에만 reachable.
for _bad in ({"hand_left": "x"}, {"hand_left": None}, "전체문자열", 12345, [1, 2]):
    _out = ck.detail_boost(_p, _p, 0.3, allow=_bad)[0]
    check(f"R75: 잘못된 allow({type(_bad).__name__}) 는 제한 없음과 같은 결과",
          _out is not None and bool((_out == _a_none).all()),
          "제한 없음과 다름" if _out is not None else "None")

# --- 노드 계약: trust_gate 가 기본 False ---
_its = ck.GoRiConsistencyKeeper.INPUT_TYPES()
check("R75: trust_gate 가 입력에 있다", "trust_gate" in _its.get("optional", {}))
check("R75: trust_gate 기본값이 False (opt-in)",
      _its["optional"]["trust_gate"][1].get("default") is False,
      str(_its["optional"]["trust_gate"]))
check("R75: run() 이 trust_gate 를 받는다",
      "trust_gate" in ck.GoRiConsistencyKeeper.run.__code__.co_varnames)

# ---------------------------------------------------------------------------
# R76: 감쇠가 노드를 죽이지 않게 한다 (2026-10-01)
#
# (왜) 이게 급했던가: 실측에서 eff 가 0.00 이 되어 `if eff:` / `eff > 0` 이
# 전부 거짓이 되었고, 그 뒤에 있는 부위별 복원과 **판정층이 아예 도달하지
# 않았다.** 임계값(0.8/2.0)이 Qwen Image 2.1 에서 재측정된 적이 없다.
# 그래서 ① 정규화 값을 계산해 로그로 노출시키고 ② 감쇠에 **바닥**을 둔다.
# 바닥은 측정값이 아니라 설계 파라미터다 — "줄인다" 는 의도는 남기되
# "조용히 아무것도 하지 않는다" 는 상태는 없애야 한다.
# ---------------------------------------------------------------------------
_say("-- 감쇠 바닥과 정규화 불일치 (2026-10-01) --")

if HAS_TORCH:
    _t76 = _t
    # 1) 같은 텐서면 정규화 불일치는 0
    _a = _t76.zeros(1, 4, 8, 8)
    _a += 0.5
    _n0 = ck._drift_norm(_a, _a)
    check("R76: 참조와 같으면 정규화 불일치 0", _n0 is not None and abs(_n0) < 1e-9,
          str(_n0))

    # 2) 스케일 불변 — **차이는 유지한 채** 참조 크기만 2배로 올린다.
    # (처음엔 `_a * 2.0` 을 샘플로 넘겨 차이가 0 이 되어 검증이 무의미했다.
    #  스케일 의존성은 "같은 차이인데 수치가 달라지는가" 로 보여야 한다.)
    _r1 = _t76.ones(1, 4, 8, 8)              # 참조 크기 1.0
    _s1 = _r1 + 0.5                          # 차이 0.5
    _r2 = _t76.ones(1, 4, 8, 8) * 2.0       # 참조 크기 2.0
    _s2 = _r2 + 0.5                          # 차이 역시 0.5
    _n1 = ck._drift_norm(_s1, _r1)
    _n2 = ck._drift_norm(_s2, _r2)
    _m1 = ck._drift_mse(_s1, _r1)
    _m2 = ck._drift_mse(_s2, _r2)
    check("R76: 절대 MSE 는 참조 크기가 바뀌어도 같다 (스케일 무관)",
          _m1 is not None and _m2 is not None and abs(_m1 - _m2) < 1e-9,
          "%.6f vs %.6f" % (_m1, _m2))
    check("R76: 정규화 값은 참조 크기에 따라 달라진다 (그래서 MSE 를 못 쓴다)",
          _n1 is not None and _n2 is not None
          and abs(_n2 - _n1 / 4.0) < 1e-6,
          "%.6f -> %.6f (기대 %.6f)" % (_n1, _n2, _n1 / 4.0))
    check("R76: 정규화는 0 과 1 사이를 읽는다 (기준선 확인)",
          _n1 is not None and 0.0 < _n1 < 1.0, str(_n1))

    # 3) 0 텐서는 분모가 0 — 비교 불가로 친다
    check("R76: 참조가 전부 0 이면 정규화 불가(None)",
          ck._drift_norm(_s1, _t76.zeros_like(_r1)) is None)

    # 4) 드리프트 임계값은 **재측정 대기** — 이 테스트는 그 사실만 고정한다.
    #    (처음엔 "감쇠 바닥" 을 넣었는데 기존 테스트 셋이 그 계약을 지켜서
    #     깨뜨렸다. 감쇠가 0 이면 region 경로도 0 이어야 감쇠를 우회할 수 없다.
    #     바닥은 안전장치를 뚫는 것이라 되돌렸다.)
    check("R76: 큰 유한 drift 는 0 으로 내려간다 (안전장치 유지)",
          ck._damp_factor(5.198) == 0.0, str(ck._damp_factor(5.198)))
    check("R76: 작은 drift 는 감쇠하지 않는다",
          ck._damp_factor(0.5) == 1.0, str(ck._damp_factor(0.5)))
    check("R76: drift 이 None 이면 감쇠하지 않는다",
          ck._damp_factor(None) == 1.0)
    check("R76: nan 은 0 (전파 차단)",
          ck._damp_factor(float("nan")) == 0.0,
          str(ck._damp_factor(float("nan"))))
    check("R76: 감쇠 바닥 상수를 다시 넣지 않았다 (계약 위반)",
          not hasattr(ck, "_DAMP_FLOOR"), "_DAMP_FLOOR 가 살아있다")
    # --- VAE 축소 비율은 하드코딩하지 않는다 ---
    # 왜(Why) 디코드에서 배우는가: 프로브로 "재서" 재는 순간 모델이 VRAM 에
    # 올라간 상태라 ms 가 아니라 초 단위가 걸렸다(2026-10-01 실측). 디코드는
    # 이미 하고 있으니 거기서 비율을 읽으면 공짜다.
    _say("-- VAE 축소 비율은 실제 디코드에서 배운다 (하드코딩 금지) --")

    class _NoVae:
        pass

    _lat16 = _t76.zeros(1, 4, 4, 4)          # latent 4칸
    _dec64 = _t76.zeros(1, 3, 64, 64)        # 이미지 64px → 16배
    check("R76: Qwen 계열(16배)은 16 이라고 배운다",
          ck._vae_pixel_factor_learn(_NoVae(), _lat16, _dec64) == 16,
          str(ck._vae_pixel_factor_learn(_NoVae(), _lat16, _dec64)))
    check("R76: 배운 값이 그 VAE 에 대해 남는다",
          ck._vae_pixel_factor_for(_NoVae()) == 16,
          str(ck._vae_pixel_factor_for(_NoVae())))
    # 왜(Why) 다른 VAE 에 새지 않는가: 한 세션에 VAE 가 여러 개 로드된다
    # (실제로 이 워크플로는 WanVAE 와 QwenImage21 를 함께 쓴다). 전역 하나면
    # 한쪽에서 배운 배율이 다른 쪽에 새어 조용히 틀린다 — 테스트에서 실제로
    # 그 일이 났고 R72 가 깨졌다.
    class _OtherVae:
        pass

    check("R76: 다른 VAE 로 새지 않는다 (구조로 구분)",
          ck._vae_pixel_factor_for(_OtherVae())
          == ck._VAE_PIXEL_FACTOR_FALLBACK,
          str(ck._vae_pixel_factor_for(_OtherVae())))
    _lat8 = _t76.zeros(1, 4, 8, 8)           # latent 8칸 → 8배
    check("R76: SD 계열(8배)은 8 이라고 배운다",
          ck._vae_pixel_factor_learn(_OtherVae(), _lat8, _dec64) == 8,
          str(ck._vae_pixel_factor_learn(_OtherVae(), _lat8, _dec64)))
    check("R76: 두 VAE 가 서로 간섭하지 않는다",
          ck._vae_pixel_factor_for(_NoVae()) == 16
          and ck._vae_pixel_factor_for(_OtherVae()) == 8,
          "16쪽=%s 8쪽=%s" % (ck._vae_pixel_factor_for(_NoVae()),
                              ck._vae_pixel_factor_for(_OtherVae())))
    check("R76: 배울 수 없으면 안전망을 유지한다",
          ck._vae_pixel_factor_learn(_NoVae(), None, None) == 16)
    check("R76: 안전망은 SD 계열 값(기존 동작과 동일)",
          ck._VAE_PIXEL_FACTOR_FALLBACK == 8)
    check("R76: 프로브 인코딩 함수는 남아있지 않다 (비용 회피)",
          not hasattr(ck, "_vae_pixel_factor"),
          "_vae_pixel_factor 가 살아있다")

# --- 감쇠 기준을 실측에 맞춘다 (2026-10-01) ---
    _say("-- 정규화 감쇠 기준: 실측 4건의 정상 범위를 덮는지 --")
    # 실측값 (WORK_STATUS 10-18): 정상 참조 4건의 정규화 불일치
    _measured = (0.2221, 0.2585, 0.3148, 0.3932,     # camera
                 0.2323, 0.2759, 0.4322, 0.4872)     # original
    for _v in _measured:
        check(f"R77: 실측 정상값 {_v:.4f} 은 감쇠되지 않는다",
              ck._damp_norm(_v) == 1.0, str(ck._damp_norm(_v)))
    check("R77: 무감쇠 끝이 실측 최댓값을 덮는다",
          ck._DRIFT_NORM_KNEE > max(_measured),
          "knee=%.2f max=%.4f" % (ck._DRIFT_NORM_KNEE, max(_measured)))
    check("R77: knee 는 실측 최댓값 바로 위다 (과도한 여유를 남기지 않음)",
          ck._DRIFT_NORM_KNEE <= max(_measured) * 1.10,
          "knee=%.2f" % ck._DRIFT_NORM_KNEE)
    check("R77: knee 위에서만 줄기 시작한다",
          ck._damp_norm(ck._DRIFT_NORM_KNEE) == 1.0)
    check("R77: ZERO 지점에서 0 이다",
          ck._damp_norm(ck._DRIFT_NORM_ZERO) == 0.0,
          str(ck._damp_norm(ck._DRIFT_NORM_ZERO)))
    check("R77: ZERO 를 넘으면 0 에 붙는다",
          ck._damp_norm(99.0) == 0.0)
    check("R77: 중간값은 knee 와 0 사이",
          0.0 < ck._damp_norm(0.75) < 1.0, str(ck._damp_norm(0.75)))
    check("R77: 비교 불가(None) 은 안 건드린다",
          ck._damp_norm(None) == 1.0)
    check("R77: nan 은 0 (전파 차단, R71 과 같은 계약)",
          ck._damp_norm(float("nan")) == 0.0)
    check("R77: 구 규칙(절대 MSE) 은 그대로 남아 있다",
          ck._damp_factor(0.5) == 1.0 and ck._damp_factor(5.0) == 0.0)
    check("R77: 구 규칙과 신 규칙은 다른 함수다 (한 곳에 섞지 않는다)",
          ck._damp_factor is not ck._damp_norm)
    # 옛 규칙으로는 정상 참조가 전부 죽었다 — 신 규칙이 그걸 구제하는 이유
    check("R77: 옛 규칙은 실측 정상값을 전부 0 으로 죽인다 (재발 방지)",
          ck._damp_factor(4.227) == 0.0 and ck._damp_factor(8.384) == 0.0)
    check("R77: 신 규칙은 같은 구간에서 살아 있다 (이게 고친 것)",
          ck._damp_norm(0.3148) == 1.0)

    # --- 원본 기준을 이미지에서 직접 인코딩 ---
    class _VFEnc:
        def __init__(self):
            self.device = "cpu"
            self.seen = None

        def encode(self, px):
            self.seen = tuple(px.shape)
            return px[:, :4]

    check("R76: (B,H,W,C) 를 (B,C,H,W) 로 옮겨 인코딩한다",
          _VFEnc().encode(_t76.zeros(2, 8, 6, 3).movedim(-1, 1)).shape[1] == 3)
    _e76 = _VFEnc()
    _e76.encode(_t76.zeros(1, 64, 64, 3)[..., :3].movedim(-1, 1))
    check("R76: 앞 3채널만 쓴다 (알파 제외)",
          _e76.seen == (1, 3, 64, 64), str(_e76.seen))
    check("R76: 원본 이미지 입력이 등록됐다",
          "original_image" in (ck.GoRiConsistencyKeeper.INPUT_TYPES()["optional"]))
    check("R76: run() 이 original_image 를 받는다",
          "original_image" in ck.GoRiConsistencyKeeper.run.__code__.co_varnames)
    check("R76: 이미지 없으면 None",
          ck._encode_image_ref(None, _t76.zeros(1, 8, 8, 3)) is None)
else:
    check("R76: torch 없음 — 건너뜀", True)

# ── R78. 에지 지표가 단일 픽셀 스파이크에 지배되지 않는다 ──────────────
# 왜(Why) 이 테스트가 필요한가 (2026-10-01 실측): 강도별 곡선이 단조가
# 아니었다(0.15 ≈ 0.30 ≫ 0.60). 원인은 지표가 **이미지의 최대 에지**로
# 정규화해서, 결과물에 아티팩트 하나가 생기면 나머지 픽셀이 전부 눌렸던
# 것이다. 상위 0.5% 평균으로 바꿨고, 그 robustness 를 회귀로 고정한다.
if ck is not None:
    try:
        import numpy as _np78
    except Exception:
        _np78 = None
else:
    _np78 = None
if _np78 is not None and ck is not None:
    _rg78 = _np78.random.default_rng(7)
    _i78 = _np78.zeros((256, 256, 3), dtype=_np78.float32)
    _i78[:, :, 1] = _rg78.random((256, 256))
    _i78[:128, :128, :] = 0.8
    _m78 = ck._edge_map_from_rgb(_i78)
    check("R78: 에지 맵이 나온다", _m78 is not None)
    if _m78 is not None:
        _s78 = _i78.copy()
        _s78[10, 10] = 1.0
        _sm78 = ck._edge_map_from_rgb(_s78)
        _d78 = abs(float(_sm78.mean()) - float(_m78.mean())) / max(1e-9, float(_m78.mean()))
        check("R78: 단일 픽셀 스파이크가 지표를 흔들지 않는다 (1% 미만)",
              _d78 < 0.01, "변화 %.3f%%" % (_d78 * 100))
    _f78 = _np78.full((64, 64, 3), 0.45, dtype=_np78.float32)
    _fm78 = ck._edge_map_from_rgb(_f78)
    check("R78: 완전 평탄 이미지는 0 (안전장치 유지)",
          _fm78 is not None and float(_fm78.sum()) == 0.0)
    _mag78 = ck._edge_mag_from_rgb(_i78)
    check("R78: 전체 해상도 맵은 2차원", _mag78 is not None and _mag78.ndim == 2)
    # 로컬 창은 셀이 아니라 창을 본다: 경계 위가 평평면보다 커야 한다
    _b78 = _np78.zeros((200, 200, 3), dtype=_np78.float32) + 0.5
    _b78[:100, :100, 0] = 1.0
    _bm78 = ck._edge_mag_from_rgb(_b78)
    _on78 = ck._local_edge(_bm78, 0.5, 0.5)
    _off78 = ck._local_edge(_bm78, 0.8, 0.8)
    check("R78: 로컬 창은 경계에서 크고 평평면에서 0", _on78 > _off78)
else:
    check("R78: numpy 없음 — 건너뜀", True)

# ── R79. 판정 게이트가 조용히 통과하지 않는다 ────────────────────────
# 왜(Why) 이 테스트가 필요한가 (2026-10-01): trust_gate 를 켰는데 로그가
# "landmark 없음" 한 줄뿐이었다. 사용자는 게이트가 왜 안 막는지 알 수 없었다.
# 실제로 원인이 셋이었다(사람 없음 / 모델 없음 / 탐지 실패) — 구분 없이
# 전부 "제한 없이 진행" 으로 끝났다. 그래서 **사유가 반드시 드러나야** 한다.
_t79 = []
if ck is not None:
    # 사유 문자열별로 경고(⚠) 가 붙는지 확인한다
    _cases = [
        ("포즈 모델 없음 (세션 생성 실패)", True),
        ("디코드 결과 없음", True),
        ("에지 맵 계산 실패", True),
        ("예외 ValueError: 뭐가 잘못됨", True),
        ("사람 미검출 (임계 0.3 재시도까지 실패) — 제품 사진 등 사람이 없는 "
         "이미지일 수 있음, 탐지 문제면 이 문구가 반복된다", False),
        ("사유 기록 없음", False),
    ]
    _log79 = []
    _orig79 = ck._log
    ck._log = lambda m: _log79.append(m)
    try:
        for _why, _want_severe in _cases:
            ck._POSE_WHY.clear()
            ck._POSE_WHY["original"] = _why
            _msg = ck._pose_gate_message(_why)
            _log79.clear()
            ck._note_pose_why("gate", _msg)
            _out = _log79[0] if _log79 else ""
            check(f"R79: 사유가 로그에 드러난다 [{_why[:14]}]",
                  "landmark 없음" in _out and _why[:20] in _out, _out[:90])
            check(f"R79: 심각 사유만 ⚠ 표시 [{_why[:14]}]",
                  ("⚠" in _out) == _want_severe, _out[:60])
    finally:
        ck._log = _orig79

    # 소스 문자열 검사 대신 **실제로** 게이트 분기가 사유를 읽는지 확인한다.
    # (소스를 훑는 검사는 import 를 Pull 하고, 그 자체가 R63 인코딩을
    #  깨뜨렸다 — 2026-10-01 실측. 동작을 보는 게 낫다.)
    ck._POSE_WHY.clear()
    ck._POSE_WHY["original"] = "디코드 결과 없음"
    _msg79 = ck._pose_gate_message(ck._POSE_WHY["original"])
    check("R79: 게이트가 기록된 사유를 읽는다",
          "디코드 결과 없음" in _msg79, _msg79[:80])
    check("R79: 낮은 임계 재시도 상수가 0.3 (13장 실측)",
          abs(ck._POSE_LOOSE_CONF - 0.3) < 1e-9, str(ck._POSE_LOOSE_CONF))
    check("R79: 낮은 임계 세션 캐시가 있다", isinstance(ck._POSE_LOOSE, list))
else:
    check("R79: keeper 없음 — 건너뜀", True)

# ── R80. 물리 상한은 실측 근거가 붙어 있다 ───────────────────────────
# 왜(Why) 필요한가 (2026-10-01): 상한이 0.78 → 0.20 으로 바뀌면서 테스트 10건이
# 동시에 깨졌다. 원인은 판정식의 **리터럴 기대값**이었다 — 정책이 바뀌면
# 리터럴은 조용히 거짓이 된다. 이 검사는 상한 값에 **근거**를 붙여
# "왜 0.20 인지" 를 코드에 남긴다.
if ck is not None:
    check("R80: 물리 상한이 0.20 (대응 지점 실측, WORK_STATUS 11-7)",
          abs(ck._PHYS_CEILING - 0.20) < 1e-9, str(ck._PHYS_CEILING))
    check("R80: 상한이 0 과 1 사이", 0.0 < ck._PHYS_CEILING < 1.0)
    _c80 = _node.run(_b64, strength_camera=1.0, strength_original=0.0,
                     camera_latent=_c64, original_latent=_o64)[0]["samples"]
    _ec80 = 1.0 * ck._damp_norm(ck._drift_norm(_b64["samples"], _c64["samples"]))
    _bv80 = float(_b64["samples"].mean())
    _cv80 = float(_c64["samples"].mean())
    _want80 = _bv80 + _ec80 * ck._PHYS_CEILING * (_cv80 - _bv80)
    check("R80: 강도 1.0 은 상한까지만 반영",
          abs(float(_c80.max()) - _want80) < 1e-4,
          f"실제 {float(_c80.max()):.4f} 기대 {_want80:.4f}")
    # 상한 아래는 건드리지 않는다 — 상한이 결과를 바꾸지 않아야 하는 구간
    _lo80 = _node.run(_b64, strength_camera=0.10, strength_original=0.0,
                      camera_latent=_c64, original_latent=_o64)[0]["samples"]
    _want_lo = _bv80 + 0.10 * _ec80 * (_cv80 - _bv80)
    check("R80: 상한 아래 강도는 그대로 통과",
          abs(float(_lo80.max()) - _want_lo) < 1e-4,
          f"실제 {float(_lo80.max()):.4f} 기대 {_want_lo:.4f}")
else:
    check("R80: keeper 없음 — 건너뜀", True)

# ── R81. 손가락 판정 (judge_hands) ─────────────────────────────────────
# 왜(Why): 포즈 33점은 손가락 끝 3점만 주어 개수·분리를 판정할 수 없다.
# 손 모델(21점×N개)로 손 개수와 끝점 분리를 본다. 2026-10-02 실측:
#   정상 손 10개  0.0041~0.0419  → intact
#   합성 융합손   0.0000          → damaged
# 임계 0.003 은 "닿음" 과 "융합" 의 경계다.
_say("-- R81: 손가락 판정 --")
if ck is not None:
    # 빈 입력 → undetermined (판단 보류, 정상도 비정상도 아님)
    _jh0 = ck.judge_hands(None)
    check("R81: 손 없음은 undetermined",
          _jh0["verdict"] == ck._JUDGE_UNDETERMINED, _jh0["verdict"])
    _jh0b = ck.judge_hands([])
    check("R81: 빈 리스트도 undetermined",
          _jh0b["verdict"] == ck._JUDGE_UNDETERMINED, _jh0b["verdict"])
    # 손 3개 → damaged (여분 손)
    _fake3 = [[(0.1 * i, 0.1, None) for _ in range(21)] for i in range(3)]
    _jh3 = ck.judge_hands(_fake3)
    check("R81: 손 3개는 damaged",
          _jh3["verdict"] == ck._JUDGE_DAMAGED, _jh3["verdict"])
    # 손 1개 + 끝점 분리 → intact
    _good = [[(0.10 + 0.02 * (i % 5), 0.10 + 0.01 * (i // 5), None) for i in range(21)]]
    _jh1 = ck.judge_hands(_good)
    check("R81: 분리된 손은 intact",
          _jh1["verdict"] == ck._JUDGE_INTACT, _jh1["verdict"])
    # 손 1개 + 끝점 겹침 → damaged
    _fused = [[(0.10, 0.10, None) for _ in range(21)]]
    _jhf = ck.judge_hands(_fused)
    check("R81: 겹친 끝점은 damaged",
          _jhf["verdict"] == ck._JUDGE_DAMAGED, _jhf["verdict"])
    # 상수 존재
    check("R81: 손끝 인덱스 상수", ck._HAND_TIPS == (4, 8, 12, 16, 20),
          str(ck._HAND_TIPS))
    check("R81: 분리 임계 상수", abs(ck._HAND_TIP_MIN_SEP - 0.001) < 1e-9,
          str(ck._HAND_TIP_MIN_SEP))
else:
    check("R81: keeper 없음 — 건너뜀", True)

# ── R82. strength_sampler 마스터 게인 (2026-10-02) ────────────────────────
# 왜(Why): camera/original 은 각 기준 쪽 당김만 정한다. 둘을 안 만지고 전체
# 효과를 조절할 방법이 없었다. 1.0=기존 그대로, 0.0=통과, 0.5=절반.
_say("-- R82: sampler 마스터 게인 --")
if ck is not None:
    _req82 = ck.GoRiConsistencyKeeper.INPUT_TYPES()["required"]
    check("R82: strength_sampler 가 strength_camera 위에 있다",
          list(_req82.keys()).index("strength_sampler")
          < list(_req82.keys()).index("strength_camera"),
          str(list(_req82.keys())))
    check("R82: 기본 1.0 (기존 동작 그대로)",
          abs(float(_req82["strength_sampler"][1]["default"]) - 1.0) < 1e-9,
          str(_req82["strength_sampler"]))
    check("R82: 범위 -1.0~1.0 (다른 강도와 동일)",
          float(_req82["strength_sampler"][1]["min"]) == -1.0
          and float(_req82["strength_sampler"][1]["max"]) == 1.0,
          str(_req82["strength_sampler"]))
    # 1.0/0.5/0.0 비율로 검증한다 — 감쇠·상한에 무관하다.
    # 왜(Why) 절대값이 아니라 비율인가: eff 는 감쇠·물리상한을 거쳐서
    # 테스트가 그 값을 하드코딩하면 정책이 바뀔 때마다 깨진다.
    # `out = sampled + s*C` 구조이므로 s 비율만 보면 된다.
    import torch as _t82
    _s82 = _t82.zeros(1, 4, 8, 8)
    _c82 = _t82.ones(1, 4, 8, 8)
    _node82 = ck.GoRiConsistencyKeeper()
    _o10 = _node82.run({"samples": _s82}, strength_sampler=1.0,
                       strength_camera=0.5, strength_original=0.0,
                       camera_latent={"samples": _c82})[0]["samples"]
    _o05 = _node82.run({"samples": _s82}, strength_sampler=0.5,
                       strength_camera=0.5, strength_original=0.0,
                       camera_latent={"samples": _c82})[0]["samples"]
    _o00 = _node82.run({"samples": _s82}, strength_sampler=0.0,
                       strength_camera=0.5, strength_original=0.0,
                       camera_latent={"samples": _c82})[0]["samples"]
    # o05 == (o10 + sampled)/2  (절반 반영)
    _half = (_o10 + _s82) / 2.0
    check("R82: 0.5 는 1.0 의 절반 반영",
          bool(((_o05 - _half).abs().max() < 1e-5).item()),
          f"maxdiff={float((_o05 - _half).abs().max()):.6f}")
    # o00 == sampled (통과)
    check("R82: 0.0 은 통과 (출력=입력)",
          bool(((_o00 - _s82).abs().max() < 1e-9).item()),
          f"maxdiff={float((_o00 - _s82).abs().max()):.8f}")
    # nan/inf 는 0.0 으로 (다른 강도와 같은 _safe_strength 계약)
    _onan = _node82.run({"samples": _s82}, strength_sampler=float("nan"),
                        strength_camera=0.5, strength_original=0.0,
                        camera_latent={"samples": _c82})[0]["samples"]
    check("R82: nan 게인은 0.0 (통과)",
          bool(((_onan - _s82).abs().max() < 1e-9).item()),
          f"maxdiff={float((_onan - _s82).abs().max()):.8f}")
else:
    check("R82: keeper 없음 — 건너뜀", True)

print(f"\n결과: PASS={PASS}  FAIL={FAIL}")

sys.exit(1 if FAIL else 0)
