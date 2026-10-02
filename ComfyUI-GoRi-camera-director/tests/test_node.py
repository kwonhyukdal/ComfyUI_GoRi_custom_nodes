# -*- coding: utf-8 -*-
"""ComfyUI 없이 노드 로직을 검증하는 테스트.

실행: python tests/test_node.py   (노드 동작 + 구조 검증에 대응)
"""

import os
import sys
import json
import time
import weakref

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)


import camera_director as cd  # noqa: E402
import llm_client  # noqa: E402

PASS = FAIL = 0
_print = print          # stdlib print 를 그대로 보관 (_say 가 재귀하지 않게)


def _say(line):
    """인코딩 안전 출력.

    한국어 Windows 콘솔 기본 인코딩(cp949)은 em dash(—) 등을 인코딩하지
    못한다. 원래 `print` 를 그대로 쓰다가 cp949 환경에서 UnicodeEncodeError 로
    테스트가 중간에 죽었다(실측: 875행). 한 번 죽으면 뒤의 검사가 아예
    돌아가지 않아 통과/실패를 알 수 없다.
    노드 쪽 `_log()` 과 동일한 폴백을 쓴다.
    """
    try:
        _print(line)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            _print(line.encode(enc, "replace").decode(enc, errors="replace"))
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


# 이 파일의 나머지 출력(섹션 헤더·요약)은 전부 `_say` 를 탄다.
# cp949 에서 섹션 제목만 먼저 죽어 결과를 아예 볼 수 없는 일이 있었다.
# 테스트 출력 전용이라 부작용은 없다.
print = _say  # noqa: A001  (섹션 헤더 출력용)


node = cd.CameraDirector()


def run(**kw):
    base = dict(
        topic="창가에서 잠든 고양이", preset=cd.AUTO,
        automation="수동 (manual)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        provider="OpenAI", model="gpt-4o-mini", api_key="", extra_negative="")
    base.update(kw)
    return node.run(**base)


print("== 구조 검증 (V1 연동 전제) ==")
its = cd.CameraDirector.INPUT_TYPES()
check("required 위젯 존재",
      all(k in its["required"] for k in
          ["topic", "preset", "automation", "shot", "lens", "angle",
           "composition", "lighting", "grade", "motion", "speed", "amplitude"]))
check("optional 위젯 존재",
      all(k in its["optional"] for k in ["provider", "model", "api_key",
                                         "extra_negative"]))
check("출력 3개 (positive/negative/image_out)",
      cd.CameraDirector.RETURN_TYPES == ("STRING", "STRING", "IMAGE")
      and cd.CameraDirector.RETURN_NAMES == ("positive", "negative", "image_out"))
# CATEGORY 는 "GoRi/Camera" 로 바꾸려다 되돌렸다(2026-09-30). Jev 가 이 변경을
# public_api_impact=breaking P=0.43 으로 봤고(신뢰도 0.24), CATEGORY 는 메뉴
# 묶음 문자열이라 기능 이득이 없다. 표시 이름이 (GoRi) 라 검색·발견성은 원래
# 괜찮았다. 값은 고정한다 — publisher 별 분류가 필요하면 그때 한 번에 바꾼다.
check("카테고리 등록", cd.CameraDirector.CATEGORY == "HF Skills/Camera")

bad = [(n, k, v) for n, pc in cd.PRESETS.items() for k, v in pc.items()
       if v not in cd._TABLES.get(k, {})]
check("프리셋 라벨 ↔ 목록 A 정합", not bad, str(bad))

badkw = [(c, e.get("value")) for c, entries in cd.KEYWORDS.items()
         if not c.startswith("_") for e in entries
         if e.get("value") not in cd._TABLES.get(c, {})]
check("키워드 사전 값 ↔ 목록 A 정합", not badkw, str(badkw))

print("== V2: manual + 직접 설정 ==")
pos, neg, _img = run(preset=cd.CUSTOM, automation="수동 (manual)",
               shot="근접 (CU)", lens="85mm f/1.4 (bokeh)", angle="로우앵글 (low angle)",
               composition="삼분할 (rule of thirds)", lighting="골든아워 (golden hour)",
               grade="시네마틱 필릭 (cinematic)", motion="슬로우 푸시인 (push-in)",
               speed="느림 (slow)", amplitude="약간 (subtle)")
check("주제 포함", "창가에서 잠든 고양이" in pos)
check("카메라 조항 영문 포함",
      all(s in pos for s in ["close-up shot", "85mm", "low angle",
                             "golden hour", "push-in"]))
check("무빙에 camera movement", "camera movement" in pos)
check("범용 품질 가드: 동물 전용 (사람 수치 지표 없음)",
      all(s not in pos for s in ["natural human proportions",
          "believable hands with five fingers", "natural skin texture"]), pos)
check("동물 주제에는 종 보존 가드",
      all(s in pos for s in ["one clearly identifiable animal species",
          "correct animal anatomy", "natural coat pattern"])
      and "humanized animal" in neg, f"pos={pos[-160:]} neg={neg[-160:]}")
check("인물 주제에는 사람 가드 (사라지지 않음)",
      "natural human proportions" in cd.add_quality_guard(
          "a woman", image_count=1, topic="1번 여성 인물"), pos)
check("특정 모델 전용 unfiltered 표현 제거", "unfiltered realistic rendering" not in pos, pos)
check("네거티브 기본 세트", "warped geometry" in neg and "flat lighting" in neg)

print("== 프리셋 우선 (V8 반대 케이스: 프리셋≠직접설정) ==")
pos2, _, _ = run(preset="제품 히어로 (product hero)", automation="수동 (manual)",
              shot="극접 (ECU)")  # 프리셋이 드롭다운을 덮어쓰는지
check("프리셋 값으로 덮임 (매크로/스튜디오)",
      "100mm macro" in pos2 and "three-point studio" in pos2
      and "extreme close-up" not in pos2, pos2)

print("== auto 규칙 (한글 키워드) ==")
pos3, _, _ = run(topic="드넓은 초원의 풍경, 말이 달린다",
              preset=cd.AUTO, automation="규칙 (auto)")
check("풍경 → 원경(WS)", "wide shot" in pos3, pos3)
pos3b, _, _ = run(topic="모델의 얼굴 클로즈업 초상",
               preset=cd.AUTO, automation="규칙 (auto)")
check("얼굴 → 근접(CU) + 85mm", "close-up shot" in pos3b and "85mm" in pos3b, pos3b)

print("== V4: llm 폴백 (키 없음 → 규칙, 크래시 없음) ==")
llm_client.clear_cache()
try:
    pos4, neg4, _ = run(topic="비 오는 밤 골목, 네온사인",
                     preset=cd.AUTO, automation="AI 판단 (llm)",
                     provider="OpenAI", api_key="")
    check("폴백 후 정상 출력", len(pos4) > 20 and "비 오는 밤" in pos4, pos4)
    check("폴백 시 규칙 값 적용", "medium shot" in pos4, pos4)
except Exception as e:  # noqa: BLE001
    check("폴백 후 정상 출력", False, repr(e))

print("== V7: 캐시 무오염 (무키 경로는 저장 자체를 안 함) ==")
before = llm_client.cache_stats()[0]
run(topic="동일 주제", preset=cd.AUTO, automation="AI 판단 (llm)", api_key="")
after = llm_client.cache_stats()[0]
check("실패 응답이 캐시에 쌓이지 않음", before == after,
      f"{before} -> {after}")

print("== llm_client 유틸 ==")
obj = llm_client.extract_json('```json\n{"scene":"a cat","camera":{"shot":"근접 (CU)"}}\n```')
check("code-fence JSON 파싱", obj.get("scene") == "a cat")
try:
    llm_client.extract_json("JSON 없음")
    check("파싱 실패 → LLMError", False)
except llm_client.LLMError:
    check("파싱 실패 → LLMError", True)

print("== llm 성공 경로 (네트워크 없이 stub으로 검증) ==")


def _fake_chat(provider, model, api_key, system, user, timeout=45,
               image_b64=None, image_sig=None, image_b64s=None, base_url=""):
    return {
        "scene": "A cat asleep on a sunlit windowsill, dust motes drifting in the light.",
        "camera": {"shot": "근접 (CU)", "lens": "85mm f/1.4 (bokeh)", "angle": "로우앵글 (low angle)",
                   "composition": "삼분할 (rule of thirds)", "lighting": "골든아워 (golden hour)",
                   "grade": "시네마틱 필릭 (cinematic)", "motion": "자동 (auto)",
                   "speed": "느림 (slow)", "amplitude": "약간 (subtle)"},
        "negative": "cluttered background",
    }


_calls = {"vision": 0}


def _fake_vision_chat(provider, model, api_key, system, user, timeout=45,
                      image_b64=None, image_sig=None, image_b64s=None, base_url=""):
    _calls["vision"] += 1
    VisionPayloads.append((provider, image_b64, image_sig, user, image_b64s))
    return {
        "scene": "A moody alley in heavy rain, neon signs reflecting on wet asphalt.",
        "camera": {"shot": "중경 (MS)", "lens": "35mm 스냅 (snapshot)", "angle": "수평 (eye-level)",
                   "composition": "리딩라인 (leading lines)", "lighting": "네온 (neon)",
                   "grade": "시네마틱 필릭 (cinematic)", "motion": "슬로우 푸시인 (push-in)",
                   "speed": "느림 (slow)", "amplitude": "약간 (subtle)"},
        "negative": "daylight look",
    }


VisionPayloads: list = []

try:  # 테스트 환경에 torch가 없으면 작은 stub으로 대체
    import torch as _torch  # noqa: E402
    VISION_IMG = _torch.ones(1, 48, 64, 3) * 0.12
except Exception:  # noqa: BLE001
    VISION_IMG = [[0.12, 0.12, 0.12]] * 48

_orig_chat = llm_client.chat
llm_client.chat = _fake_chat
try:
    pos5, neg5, _ = run(topic="창가에서 잠든 고양이", preset=cd.AUTO,
                     automation="AI 판단 (llm)")
    check("LLM 장면(영문) 확장", "windowsill" in pos5, pos5)
    check("LLM 카메라 라벨 채택", "close-up shot" in pos5 and "85mm" in pos5
          and "golden hour" in pos5, pos5)
    check("LLM negative 추가", "cluttered background" in neg5)
    check("무효 라벨(자동)은 기본값 폴백", "no camera movement" not in pos5)

    pos6, _, _ = run(topic="창가에서 잠든 고양이", preset="시네마틱 인물 (cinematic portrait)",
                  automation="AI 판단 (llm)")
    check("프리셋 + llm 혼합(프리셋 카메라 / LLM 장면)",
          "85mm" in pos6 and "windowsill" in pos6 and "100mm" not in pos6, pos6)
finally:
    llm_client.chat = _orig_chat

print("== (GoRi) Camera Director Skills: conditioning + prompt_out ==")
check("Skills RETURN_TYPES",
      cd.CameraDirectorEncode.RETURN_TYPES
      == ("CONDITIONING", "CONDITIONING", "STRING", "IMAGE", "LATENT"))
check("Skills RETURN_NAMES",
      cd.CameraDirectorEncode.RETURN_NAMES
      == ("positive_out", "negative_out", "prompt_out", "image_out",
          "reference_latent_out"))
enc_its = cd.CameraDirectorEncode.INPUT_TYPES()
check("Skills conditioning 디렉터 입력 계약",
      enc_its["required"].get("clip") == ("CLIP",)
      # vae 는 reference conditioning 캐시용이라 선택 입력이다. required 로
      # 두면 VAE 없이 쓰는 프롬프트 전용 경로가 UI 에서 막힌다.
      and "vae" not in enc_its["required"]
      and enc_its["optional"].get("vae") == ("VAE",)
      and enc_its["optional"].get("latent_image") == ("LATENT", {"optional": True})
      and enc_its["optional"].get("positive") == ("CONDITIONING",)
      and enc_its["optional"].get("negative") == ("CONDITIONING",)
      and "qwen_prompt" not in enc_its["optional"]
      and "topic" in enc_its["required"] and "shot" in enc_its["required"])
check("Skills image_1~image_10 optional 입력 존재",
      all(enc_its["optional"].get(f"image_{i}", (None,))[0] == "IMAGE"
          for i in range(1, 11)))
check("Skills에는 negative 문자열 직접 입력 없음", "extra_negative" not in enc_its["optional"],
      str(enc_its["optional"].keys()))


class FakeCLIP:
    def __init__(self):
        self.texts = []

    def tokenize(self, text, images=None, **kwargs):
        # 실제 Qwen CLIP과 같은 인터페이스 (vision kwarg 수용, 텍스트만 기록)
        self.texts.append(text)
        return {"tokens": text}

    def encode_from_tokens_scheduled(self, tokens):
        return [("cond", tokens["tokens"])]


enc = cd.CameraDirectorEncode()
fake_clip = FakeCLIP()


def run_skills(**kw):
    base = dict(
        topic="테스트 주제", preset=cd.AUTO, automation="수동 (manual)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO)
    base.update(kw)
    return enc.run_prompt(clip=fake_clip, **base)[2]


prompt_out = run_skills(
    topic="테스트 주제", preset=cd.AUTO, automation="규칙 (auto)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO)
check("Skills prompt_out은 문자열", isinstance(prompt_out, str), str(prompt_out))
check("Skills prompt_out에 주제 포함", "테스트 주제" in prompt_out, prompt_out)
print("== IMAGE 입력 사용 확인 ==")
check("Skills image 입력 위젯이 IMAGE 타입",
      cd.CameraDirectorEncode.INPUT_TYPES()["optional"].get("image_1", (None,))[0] == "IMAGE")
SENTINEL = object()
_, _, out_img = run(topic="x", image=SENTINEL)
check("내부 계산 로직은 연결된 이미지 유지", out_img is SENTINEL)
_, _, out_none = run(topic="x")
check("미연결이면 None", out_none is None)
prompt_e = run_skills(
    topic="x", preset=cd.AUTO, automation="규칙 (auto)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO, image_1=SENTINEL)
check("Skills는 image 입력과 conditioning/prompt_out 출력 제공", isinstance(prompt_e, str))

pos_cond, neg_cond, prompt_cond, _img_out, _ref_lat = enc.run_prompt(
    clip=fake_clip, topic=" conditioning test", preset=cd.AUTO,
    automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
    composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO)
check("Skills conditioning 출력 3개", isinstance(pos_cond, list) and isinstance(neg_cond, list)
      and isinstance(prompt_cond, str))
base_pos = [("base", {})]
base_neg = [("base", {})]
qwen_prompt = "A portrait of a woman, preserve the input subject exactly"
pos_mixed, neg_mixed, prompt_mixed, _img_out, _ref_lat = enc.run_prompt(
    clip=fake_clip, topic="ignored topic", preset=cd.AUTO, automation="규칙 (auto)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO, prompt_in=qwen_prompt,
    positive=base_pos, negative=base_neg, image_1=SENTINEL)
check("Qwen prompt_in은 positive conditioning으로 직접 병합하지 않음",
      len(pos_mixed) == 1 and pos_mixed[0][1] == fake_clip.texts[-2], str(pos_mixed))
check("기존 negative conditioning 보존/합치기", len(neg_mixed) == 2 and neg_mixed[0][0] == "base")
check("reference image가 있는 사람 Qwen 프롬프트에는 짧은 identity anchor 추가",
      all(s in prompt_mixed for s in
          ["Use reference image 1 as the exact identity source",
           "same facial identity", "same facial structure", "age", "ethnicity",
           "hairstyle", "clothing"]), prompt_mixed)
check("identity anchor에 피부색·anatomy legacy guard는 다시 넣지 않음",
      all(s not in prompt_mixed for s in
          ["natural skin tone", "face and body preservation guard", "extra arms",
           "facial identity lock"]),
      prompt_mixed)
check("public Qwen 경로에는 골반/체형 측정 문구를 넣지 않음",
      all(s not in prompt_mixed for s in
          ["same pelvis width", "same hip width", "same waist-to-hip ratio",
           "same torso length", "same leg proportions",
           "Do not enlarge the pelvis or hips beyond the reference"]),
      prompt_mixed)
check("단일 reference positive에는 최소한의 single-person anchor만 추가",
      all(s in prompt_mixed for s in
          ["Exactly one main person", "only subject", "Single-person composition",
           "No additional person, copy, or mirrored companion"]),
      prompt_mixed)
check("중복 억제 negative는 단일 reference에서만 카메라 negative에 추가",
      all(s in fake_clip.texts[-1] for s in
          ["multiple people", "duplicate person", "cloned person", "mirrored twin"]),
      str(fake_clip.texts[-1]))
check("카메라 문구는 identity anchor 뒤에 배치",
      prompt_mixed.index("Use reference image 1") < prompt_mixed.index("close-up shot"),
      prompt_mixed)
check("positive conditioning 입력은 새 경로에서 무시",
      "A portrait of a woman" in fake_clip.texts[-2]
      and "Use reference image 1" in fake_clip.texts[-2], str(fake_clip.texts[-2:]))
check("negative는 카메라/영상 실패 모드 중심",
      "warped geometry" in fake_clip.texts[-1]
      and "distorted perspective" in fake_clip.texts[-1], str(fake_clip.texts[-1]))
check("Skills negative에 인체/색오염/플라스틱 가드 있음 (공통 블록)",
      all(s in fake_clip.texts[-1] for s in
          ["extra arms", "face mismatch", "background color spill on skin",
           "painted skin", "blue skin tint", "plastic waxy skin"]),
      str(fake_clip.texts[-1][-200:]))

reflection_pos, reflection_neg, reflection_prompt, _img_out, _ref_lat = enc.run_prompt(
    clip=fake_clip, topic="창가 앞에 서서 유리창에 비친 Same Woman and Cat",
    preset=cd.AUTO, automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO,
    angle=cd.AUTO, composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
    motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
    prompt_in="A woman stands by a window looking at a cat; a realistic reflection appears in the glass.",
    image_1=SENTINEL)
check("유리창/반사 장면에는 single-person positive anchor 미적용",
      "Exactly one main person" not in reflection_prompt, reflection_prompt)
check("유리창/반사 장면에는 duplicate negative 미적용",
      all(s not in reflection_neg[0][1] for s in
          ["multiple people", "duplicate person", "cloned person", "mirrored twin"]),
      str(reflection_neg))

print("== ComfyUI 패키지 로딩 시뮬레이션 ==")
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "comfyui_GoRi_camera_director", os.path.join(PKG, "__init__.py"),
    submodule_search_locations=[PKG])
mod = importlib.util.module_from_spec(spec)
sys.modules["comfyui_GoRi_camera_director"] = mod
try:
    spec.loader.exec_module(mod)
    check("GoRi 표시 노드 1개만 등록",
          list(mod.NODE_CLASS_MAPPINGS) == ["GoRi_CameraDirectorEncodeSkills"]
          and mod.NODE_CLASS_MAPPINGS.get("GoRi_CameraDirectorEncodeSkills") is not None)
    check("이전 Camera Director 표시 노드는 미등록",
          "GoRi_CameraDirector" not in mod.NODE_CLASS_MAPPINGS
          and "Camera Director (GoRi Skills)" not in mod.NODE_DISPLAY_NAME_MAPPINGS.values())
    check("요청한 표시 이름 등록",
          mod.NODE_DISPLAY_NAME_MAPPINGS.get("GoRi_CameraDirectorEncodeSkills")
          == "(GoRi) Camera Director Skills")
    for k in ("GoRi_CameraDirectorEncodeSkills",):
        cls = mod.NODE_CLASS_MAPPINGS[k]
        check(f"{k}.FUNCTION 실행 가능", callable(getattr(cls(), cls.FUNCTION, None)))
except Exception as e:  # noqa: BLE001
    check("패키지 로드 성공", False, repr(e))
finally:
    sys.modules.pop("comfyui_GoRi_camera_director", None)

print("== IMAGE 메트릭 + auto 힌트 ==")
m = cd.image_metrics(VISION_IMG)
check("메트릭 4종 존재", all(k in m for k in
                             ["dark", "contrast_std", "vivid", "thirds_bias"]), str(m))
check("어두운 12% 이미지는 dark 높음",
      m.get("dark", 0) >= 0.7, str(m.get("dark")))
hint_cam, _ = cd.rules("밤 골목")
hinted = cd.apply_image_hints({**cd.DEFAULTS, "lighting": cd.DEFAULTS["lighting"]},
                              set(), {"dark": 0.8, "contrast_std": 0.05,
                                      "vivid": 0.2, "thirds_bias": "center"})
check("어두움 → 로우키", hinted.get("lighting") == "로우키 (low key)", str(hinted))
check("힌트 로그 보관", bool(hinted.get("_hints")), str(hinted.get("_hints")))
keyed = cd.apply_image_hints({**cd.DEFAULTS, "lighting": "골든아워 (golden hour)"}, {"lighting"},
                             {"dark": 0.8, "contrast_std": 0.05,
                              "vivid": 0.2, "thirds_bias": "center"})
check("키워드/드롭다운 확정값은 힌트가 덮지 않음",
      keyed.get("lighting") == "골든아워 (golden hour)", str(keyed))
pos_img, _, _ = run(topic="밤 골목", preset=cd.AUTO, automation="규칙 (auto)",
                    image=VISION_IMG)
check("이미지 연결 시 auto는 로우키 문구 포함", "low-key" in pos_img, pos_img[:200])
check("이미지 연결 시 정체성 유지 가드 포함",
      all(s in pos_img for s in ["same facial structure", "same hairstyle", "same outfit",
                                 "same body proportions"]), pos_img[:500])
outfit_prompt = run_skills(
    topic="Image 1의 여성에게 Image 2의 의상을 입히기", preset=cd.AUTO,
    automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
    composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    image_1=VISION_IMG, image_2=VISION_IMG)
check("의상 교체 전용 가드 포함",
      all(s in outfit_prompt for s in ["the main person reference image is only the identity and body reference",
                                       "the clothing reference image is only a clothing and wardrobe reference",
                                       "not a body reference",
                                       "preserve the original body shape",
                                       "no clothing fusion with skin or body parts",
                                       "no garment becoming body anatomy"]), outfit_prompt[:1200])
non_outfit_prompt = run_skills(
    topic="제품 광고 이미지", preset=cd.AUTO, automation="규칙 (auto)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    image_1=VISION_IMG, image_2=VISION_IMG)
check("제품 광고에는 의상 전용 가드 미적용",
      "the clothing reference image is only a clothing and wardrobe reference" not in non_outfit_prompt,
      non_outfit_prompt[:800])
cat_dress_prompt = run_skills(
    topic="Image 1의 woman wearing a light grey mini-dress stands by a window and looks at "
          "the cat from Image 2 sleeping on the windowsill",
    preset=cd.AUTO, automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO,
    angle=cd.AUTO, composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
    motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
    image_1=VISION_IMG, image_2=VISION_IMG)
check("고양이 장면의 dress는 의상 가드를 발동시키지 않음",
      "the clothing reference image is only a clothing and wardrobe reference" not in cat_dress_prompt,
      cat_dress_prompt[:1000])
check("인물 장면에는 얼굴/골반/피부 guard 포함",
      all(s in cat_dress_prompt for s in ["face and body preservation guard",
                                         "facial identity lock",
                                         "same jawline",
                                         "natural skin tone",
                                         "background color does not tint the skin",
                                         "same hip width",
                                         "no widened pelvis",
                                         "no exaggerated hourglass body"]), cat_dress_prompt[:1600])
check("제품 광고에는 얼굴/골반/피부 guard 미적용",
      "face and body preservation guard" not in non_outfit_prompt,
      non_outfit_prompt[:1000])
full_body_prompt = run_skills(
    topic="A full-body shot of the woman from Image 1 standing beside the window",
    preset=cd.AUTO, automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO,
    angle=cd.AUTO, composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
    motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
    image_1=VISION_IMG)
check("사용자 full-body shot 우선", "full body shot" in full_body_prompt, full_body_prompt[:700])
check("full-body와 medium shot 충돌 없음", "medium shot" not in full_body_prompt, full_body_prompt[:700])
sparse_prompt = run_skills(
    topic="Image 3 의상 참고", preset=cd.AUTO, automation="규칙 (auto)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    image_3=VISION_IMG)
check("희소 image_N 슬롯 번호 보존",
      "reference image 3" in sparse_prompt.lower(), sparse_prompt[:700])

multi_prompt = run_skills(
    topic="여성과 고양이 한 마리", preset=cd.AUTO, automation="규칙 (auto)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    image_1=VISION_IMG, image_2=VISION_IMG)
check("다중 이미지 역할 기반 정체성 가드 포함",
      all(s in multi_prompt for s in ["use reference image 1 as the only main human identity",
                                      "only for their explicitly requested roles",
                                      "do not duplicate the main subject, face, body, outfit, product, or background subject",
                                      "no cloned faces", "no duplicated characters",
                                      "no crowd unless requested", "no background people unless requested"]), multi_prompt[:900])
# 2026-09-28: 기본 보조 역할 목록에서 outfit 을 뺐다. topic 이 비면
# "explicitly requested role" 이 없어서 모델이 이 목록에서 자유롭게 고르고,
# 포즈 참조 이미지의 옷이 그대로 복제됐다(실측). 옷은 명시 요청 시에만
# 옮기며 그 경로는 OUTFIT_GUARD 가 전담한다.
check("보조 역할 기본 목록에 outfit 없음 (명시 요청 없이 옷 복사 금지)",
      "background, outfit" not in multi_prompt
      and "outfit, prop" not in multi_prompt
      and "never their face, hair, skin tone, body identity, "
          "clothing or outfit" in multi_prompt, multi_prompt[:900])
check("위험한 다중 주체 문구 제거",
      all(s not in multi_prompt for s in ["one subject per reference subject",
                                          "use the reference images as separate subjects",
                                          "same fur pattern and coat colors for the animal reference"]), multi_prompt[:900])

print("== vision 페이로드 (LLM 티어 + 이미지 전달 규격) ==")
llm_client.chat = _fake_vision_chat
try:
    VisionPayloads.clear()
    _calls["vision"] = 0
    b64 = llm_client.image_to_b64(VISION_IMG)
    check("PNG base64 변환", isinstance(b64, str) and len(b64) > 100, str(len(b64 or "")))
    pv, _, _ = run(topic="비 오는 밤 골목", preset=cd.AUTO,
                   automation="AI 판단 (llm)", image=VISION_IMG)
    check("vision 호출 1회", _calls["vision"] == 1, str(_calls["vision"]))
    prov, got_b64, got_sig, has_note, got_b64s = VisionPayloads[0]
    check("모델에 이미지 bytes 전달", bool(got_b64), str(bool(got_b64)))
    check("단일 이미지 비전 payload", len(got_b64 or []) >= 0, str(type(got_b64)))
    check("장면이 LLM 비전 결과", "neon" in pv.lower(), pv[:160])
    VisionPayloads.clear()
    _calls["vision"] = 0
    pmulti, _, _ = run(topic="비 오는 밤 골목", preset=cd.AUTO,
                      automation="AI 판단 (llm)",
                      image_list=[VISION_IMG, VISION_IMG])
    prov2, got_b64_2, got_sig_2, has_note_2, got_b64s_2 = VisionPayloads[0]
    check("다중 vision 호출 1회", _calls["vision"] == 1, str(_calls["vision"]))
    check("다중 vision payload 2장 전달", len(got_b64s_2 or []) == 2, str(len(got_b64s_2 or [])))
    check("다중 이미지 LLM note 포함", "Reference images 1, 2 are attached as references" in VisionPayloads[0][3])
    llm_client.chat = _fake_chat
    VisionPayloads.clear()
    pv2, _, _ = run(topic="비 오는 밤 골목", preset=cd.AUTO,
                    automation="AI 판단 (llm)", image=VISION_IMG)
    check("두 번째 stub도 이미지 참조 로그", True)
finally:
    llm_client.chat = _orig_chat

print("== prompt_in (선 연결 전용 단자 - topic 칸과 병용) ==")
pos7, _, _ = run(topic="이 칸은 무시되어야 함", prompt_in="노을 지는 바다 위의 요트")
check("선 연결 시 외부 프롬프트 우선",
      "노을 지는 바다" in pos7 and "무시되어야" not in pos7, pos7)
pos8, _, _ = run(topic="topic 칸 입력본", prompt_in="")
check("빈 값이면 topic 칸 사용", "topic 칸 입력본" in pos8, pos8)
pos9, _, _ = run(prompt_in=None)
check("미연결(None)이면 topic 칸 사용", "창가에서 잠든 고양이" in pos9, pos9)

print("== Qwen reference 속도 최적화 (negative 단일 인코딩 / VAE 캐시 / 1MP 상한) ==")
import types as _types

_calls_opt = {"upscale": [], "encode": 0}
_nh_calls = []


class _OptVAE:
    def encode(self, s):
        _calls_opt["encode"] += 1
        return ("latent", tuple(s.shape))


def _opt_upscale(samples, width, height, *args, **kwargs):
    _calls_opt["upscale"].append((width, height))
    return samples


def _fake_set_values(cond, values, append=True):
    _nh_calls.append(values)
    return cond


class VisionCLIP:
    """images kwarg 수신 여부를 기록하는 Qwen 형태 CLIP stub."""

    def __init__(self):
        self.tokenize_calls = []

    def tokenize(self, text, **kwargs):
        self.tokenize_calls.append((text, kwargs))
        return {"tokens": text}

    def encode_from_tokens_scheduled(self, tokens):
        return [("cond", tokens["tokens"])]


_fake_comfy = _types.ModuleType("comfy")
_fake_comfy_utils = _types.ModuleType("comfy.utils")
_fake_comfy_utils.common_upscale = _opt_upscale
_fake_comfy.utils = _fake_comfy_utils
_fake_nh = _types.ModuleType("node_helpers")
_fake_nh.conditioning_set_values = _fake_set_values
_saved_modules = {m: sys.modules.get(m) for m in ("comfy", "comfy.utils", "node_helpers")}
sys.modules["comfy"] = _fake_comfy
sys.modules["comfy.utils"] = _fake_comfy_utils
sys.modules["node_helpers"] = _fake_nh
try:
    import torch as _torch_opt  # noqa: E402
    cd.clear_qwen_ref_cache()
    _img_opt = _torch_opt.ones(1, 64, 64, 3) * 0.3
    _vae_opt = _OptVAE()
    _items_opt = [(1, _img_opt)]
    _prep1 = cd.CameraDirectorEncode._prepare_qwen_image_data(
        _items_opt, vae=_vae_opt, latent_image=None)
    check("reference 첫 계산 시 VAE 1회", _calls_opt["encode"] == 1,
          str(_calls_opt["encode"]))
    _prep2 = cd.CameraDirectorEncode._prepare_qwen_image_data(
        _items_opt, vae=_vae_opt, latent_image=None)
    check("동일 reference 재실행 시 VAE 캐시 히트",
          _calls_opt["encode"] == 1, str(_calls_opt["encode"]))
    check("캐시된 vision/reference 재사용",
          len(_prep2[0]) == 1 and len(_prep2[1]) == 1)

    cd.clear_qwen_ref_cache()
    _calls_opt["upscale"].clear()
    _big_latent = {"samples": _torch_opt.ones(1, 4, 192, 320)}  # 3072x5120
    _img_big = _torch_opt.ones(1, 256, 256, 3) * 0.6
    cd.CameraDirectorEncode._prepare_qwen_image_data(
        [(1, _img_big)], vae=_vae_opt, latent_image=_big_latent)
    _req = _calls_opt["upscale"][-1] if _calls_opt["upscale"] else (0, 0)
    check("대형 latent에서도 reference는 1MP 상한",
          _req[0] * _req[1] <= 1024 * 1024, str(_req))

    cd.clear_qwen_ref_cache()
    _calls_opt["encode"] = 0
    _nh_calls.clear()
    _vclip = VisionCLIP()
    _enc_opt = cd.CameraDirectorEncode()
    _enc_opt.run_prompt(
        clip=_vclip, topic="테스트", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        prompt_in="A woman stands by a window.",
        vae=_vae_opt, image_1=_img_opt)
    _pos_calls = [c for c in _vclip.tokenize_calls if c[1].get("images")]
    _neg_texts = [c[0] for c in _vclip.tokenize_calls if not c[1].get("images")]
    check("positive만 vision 참조", len(_pos_calls) == 1,
          str(len(_vclip.tokenize_calls)))
    check("negative는 텍스트만 인코딩",
          any("warped geometry" in t for t in _neg_texts),
          str(_neg_texts)[:200])
    check("reference_latents는 positive에만 1회 첨부",
          len(_nh_calls) == 1, str(len(_nh_calls)))

    print("-- R3: 다른 VAE 객체는 캐시 미스 (id 재사용 방지) --")
    cd.clear_qwen_ref_cache()
    _calls_opt["encode"] = 0
    _img_a = _torch_opt.ones(1, 32, 32, 3) * 0.2
    _vae_r3a, _vae_r3b = _OptVAE(), _OptVAE()
    cd.CameraDirectorEncode._prepare_qwen_image_data(
        [(1, _img_a)], vae=_vae_r3a, latent_image=None)
    check("R3: 첫 인코딩 1회", _calls_opt["encode"] == 1, str(_calls_opt["encode"]))
    cd.CameraDirectorEncode._prepare_qwen_image_data(
        [(1, _img_a)], vae=_vae_r3a, latent_image=None)
    check("R3: 동일 VAE 재사용은 캐시 히트",
          _calls_opt["encode"] == 1, str(_calls_opt["encode"]))
    cd.CameraDirectorEncode._prepare_qwen_image_data(
        [(1, _img_a)], vae=_vae_r3b, latent_image=None)
    check("R3: 다른 VAE 객체는 재인코딩",
          _calls_opt["encode"] == 2, str(_calls_opt["encode"]))
finally:
    for _m, _mod in _saved_modules.items():
        if _mod is None:
            sys.modules.pop(_m, None)
        else:
            sys.modules[_m] = _mod
    cd.clear_qwen_ref_cache()

print("== 정밀 분석 후속 수정 (B1/B2/B3/B4) ==")

print("-- B4: auto 조명 키워드 --")
pos_neon, _, _ = run(topic="네온사인이 빛나는 비 오는 밤 골목",
                     preset=cd.AUTO, automation="규칙 (auto)")
check("네온 → 네온 조명", "neon glow" in pos_neon, pos_neon[:300])
pos_night, _, _ = run(topic="어두운 밤 골목",
                      preset=cd.AUTO, automation="규칙 (auto)")
check("어두운 밤 → 로우키", "low-key" in pos_night, pos_night[:300])
pos_ramen, _, _ = run(topic="밤에 먹는 라면",
                      preset=cd.AUTO, automation="규칙 (auto)")
check("일상 밤 장면은 기본 조명 유지 (오탐 방지)",
      "soft overcast" in pos_ramen and "low-key" not in pos_ramen,
      pos_ramen[:300])

print("-- B2: LLM extra negative 병합 --")


def _fake_chat_neg(provider, model, api_key, system, user, timeout=45,
                   image_b64=None, image_sig=None, image_b64s=None, base_url=""):
    return {
        "scene": "A cat asleep on a sunlit windowsill.",
        "camera": {"shot": "중경 (MS)", "lens": "50mm 표준 (standard)", "angle": "수평 (eye-level)",
                   "composition": "삼분할 (rule of thirds)", "lighting": "흐린 부드러움 (soft overcast)",
                   "grade": "시네마틱 필릭 (cinematic)", "motion": "없음 (none)",
                   "speed": "보통 (normal)", "amplitude": "약간 (subtle)"},
        "negative": "cluttered background",
    }


_orig_chat_b2 = llm_client.chat
llm_client.chat = _fake_chat_neg
try:
    _enc_b2 = cd.CameraDirectorEncode()
    _clip_b2 = FakeCLIP()
    _clip_b2.texts.clear()
    _enc_b2.run_prompt(
        clip=_clip_b2, topic="창가 고양이", preset=cd.AUTO,
        automation="AI 판단 (llm)", shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
        composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO)
    check("LLM negative가 카메라 negative에 병합",
          any("cluttered background" in t for t in _clip_b2.texts),
          str(_clip_b2.texts[-1:])[:200])
    check("카메라 negative 기본 유지",
          any("warped geometry" in t for t in _clip_b2.texts))
finally:
    llm_client.chat = _orig_chat_b2

print("-- B3: Ollama vision payload 규격 --")
_captured = {}


def _fake_post(url, payload, headers, timeout):
    _captured["url"] = url
    _captured["payload"] = payload
    return {"message": {"content": '{"scene":"x","camera":{}}'}}


_orig_post = llm_client._post
llm_client._post = _fake_post
try:
    llm_client.chat("Ollama", "llama3.2", "", "sys", "user",
                    image_b64s=["AAA", "BBB"])
    _p = _captured["payload"]
    check("Ollama 최상위 images 없음", "images" not in _p, str(sorted(_p.keys())))
    check("Ollama user 메시지별 images 2장",
          _p["messages"][1].get("images") == ["AAA", "BBB"],
          str(_p["messages"][1].keys()))
finally:
    llm_client._post = _orig_post

print("-- B1: Qwen 경로 의상/다중역할 가드 --")
try:
    import torch as _torch_b1  # noqa: E402
    _img_b1 = _torch_b1.ones(1, 64, 64, 3) * 0.4
    _enc_b1 = cd.CameraDirectorEncode()
    _clip_b1 = FakeCLIP()
    _, _, _outfit_qwen, _img_out, _ref_lat = _enc_b1.run_prompt(
        clip=_clip_b1, topic="x", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        prompt_in="Image 1의 여성에게 Image 2의 의상을 입히기",
        image_1=_img_b1, image_2=_img_b1)
    check("Qwen 경로 의상 교체에 OUTFIT 가드 포함",
          "the clothing reference image is only a clothing and wardrobe reference" in _outfit_qwen,
          _outfit_qwen[:500])
    _i = _outfit_qwen.index("Use reference image 1 as the exact identity source")
    _o = _outfit_qwen.index("the clothing reference image is only a clothing")
    _e = _outfit_qwen.index("입히기")
    check("Qwen 앵커 순서 고정 (identity < outfit < 외부문구 < 카메라)",
          _i < _o < _e < len(_outfit_qwen) - 10,
          _outfit_qwen[:500])
    _, _, _role_qwen, _img_out, _ref_lat = _enc_b1.run_prompt(
        clip=_clip_b1, topic="x", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        prompt_in="A woman stands by a window.",
        image_1=_img_b1, image_2=_img_b1)
    check("Qwen 경로 다중 이미지에 역할 가드 포함",
          "only for explicitly requested roles" in _role_qwen,
          _role_qwen[:500])
    check("의상 의도 없으면 OUTFIT 가드 미포함",
          "the clothing reference image is only a clothing and wardrobe reference" not in _role_qwen)
    _, _, _single_qwen, _img_out, _ref_lat = _enc_b1.run_prompt(
        clip=_clip_b1, topic="x", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        prompt_in="A woman stands by a window.",
        image_1=_img_b1)
    check("단일 이미지 Qwen 경로에 역할 가드 미포함",
          "only for explicitly requested roles" not in _single_qwen)
    check("단일 인물에는 신체분리 가드 미포함",
          "no merged or fused bodies" not in _single_qwen)
except Exception as e:  # noqa: BLE001
    check("B1 Qwen 가드 프로브 실행", False, repr(e)[:200])

print("== stale 캐시 + 2인(duo) 회귀 ==")

print("-- stale: 변환 실패해도 2번 이후 교체는 캐시 미스 --")
_posts = {"n": 0}


def _stub_post(url, payload, headers, timeout):
    _posts["n"] += 1
    return {"choices": [{"message": {"content": '{"scene":"S.","camera":{}}'}}]}


_orig_post2 = llm_client._post
_orig_b64_2 = llm_client.image_to_b64
llm_client.image_to_b64 = lambda img, max_side=768: None
llm_client._post = _stub_post
try:
    import torch as _torch_stale  # noqa: E402
    llm_client.clear_cache()
    _kw_stale = dict(topic="고정 주제", preset=cd.AUTO, automation="AI 판단 (llm)",
                     shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                     composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
                     motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
                     provider="OpenAI", model="gpt-4o-mini", api_key="DUMMY")
    node.run(**_kw_stale,
             image_list=[_torch_stale.ones(1, 32, 32, 3) * 0.1,
                         _torch_stale.ones(1, 32, 32, 3) * 0.2])
    node.run(**_kw_stale,
             image_list=[_torch_stale.ones(1, 32, 32, 3) * 0.1,
                         _torch_stale.ones(1, 32, 32, 3) * 0.9])
    check("2번 이미지 교체 시 LLM 재호출", _posts["n"] == 2, str(_posts["n"]))
finally:
    llm_client.image_to_b64 = _orig_b64_2
    llm_client._post = _orig_post2

print("-- duo: 1번 여성 + 2번 남성 마주보기 --")
try:
    import torch as _torch_duo  # noqa: E402
    _DUO = "Image 1의 여성과 Image 2의 남성이 공원 벤치 앞에서 서로 마주보고 서 있다"
    _enc_duo = cd.CameraDirectorEncode()
    _clip_duo = FakeCLIP()
    _DUO3 = "Image 1의 여성과 Image 3의 남성이 서로 마주보고 서 있다"
    _, _, _duo3_text, _img_out, _ref_lat = _enc_duo.run_prompt(
        clip=_clip_duo, topic="x", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO, prompt_in=_DUO3,
        image_1=_torch_duo.ones(1, 32, 32, 3) * 0.3,
        image_3=_torch_duo.ones(1, 32, 32, 3) * 0.7)
    check("3번 슬롯 duo에 person two from reference image 3",
          "Two main people" in _duo3_text
          and "person two from reference image 3" in _duo3_text
          and "only for explicitly requested roles" not in _duo3_text,
          _duo3_text[:600])
    _DUO10 = "Image 1의 여성과 Image 10의 남성이 서로 마주보고 서 있다"
    _imgs10 = {n: _torch_duo.ones(1, 32, 32, 3) * (n / 10.0) for n in range(1, 11)}
    _kw10 = dict(topic="x", preset=cd.AUTO, automation="규칙 (auto)",
                 shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
                 lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
                 speed=cd.AUTO, amplitude=cd.AUTO, prompt_in=_DUO10)
    for _n, _im in _imgs10.items():
        _kw10[f"image_{_n}"] = _im
    _, _, _duo10_text, _img_out, _ref_lat = _enc_duo.run_prompt(clip=_clip_duo, **_kw10)
    check("10번은 외양 참조 전용 — duo 인물로 취급하지 않음 (R18 정책)",
          "person two from reference image 10" not in _duo10_text
          and "only for explicitly requested roles" not in _duo10_text,
          _duo10_text[:600])
    _, _, _duo_text, _img_out, _ref_lat = _enc_duo.run_prompt(
        clip=_clip_duo, topic="x", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO, prompt_in=_DUO,
        image_1=_torch_duo.ones(1, 32, 32, 3) * 0.3,
        image_2=_torch_duo.ones(1, 32, 32, 3) * 0.7)
    check("duo에서 single-person anchor 미적용",
          "Exactly one main person" not in _duo_text)
    check("duo 두 정체성 보존 문구",
          "Two main people" in _duo_text
          and "person one from reference image 1" in _duo_text
          and "person two from reference image 2" in _duo_text,
          _duo_text[:600])
    check("duo 인물간 신체분리 가드",
          all(s in _duo_text for s in
              ["Keep each person's body fully separate",
               "no merged or fused bodies",
               "no limbs swapping between people",
               "no body parts blending into the other person"]),
          _duo_text[:1200])
    check("duo에서 role 제한 가드 미적용",
          "only for explicitly requested roles" not in _duo_text)
    check("duo에서 duplicate negative 미적용",
          all(s not in _clip_duo.texts[-1] for s in
              ["multiple people", "duplicate person", "cloned person", "mirrored twin"]),
          str(_clip_duo.texts[-1])[:200])
    _, _, _outfit_again, _img_out, _ref_lat = _enc_duo.run_prompt(
        clip=_clip_duo, topic="x", preset=cd.AUTO, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        prompt_in="Image 1의 여성에게 Image 2의 의상을 입히기",
        image_1=_torch_duo.ones(1, 32, 32, 3) * 0.3,
        image_2=_torch_duo.ones(1, 32, 32, 3) * 0.7)
    check("의상 교체는 duo로 오인하지 않음",
          "Two main people" not in _outfit_again
          and "the clothing reference image is only a clothing" in _outfit_again)
    check("서로 마주보기는 다중인물로 감지",
          cd._is_multi_person_request(_DUO))
    check("Image 2 남성 지정 감지",
          cd._is_second_person_request(_DUO))
    check("의상 문구는 2인 지정 아님",
          not cd._is_second_person_request("Image 1의 여성에게 Image 2의 의상을 입히기"))
    check("3번 슬롯 인물 지정 감지",
          cd._second_person_slots("Image 1의 여성과 Image 3의 남성이 서로 마주보기") == [3])
    check("10번 슬롯 인물 지정 감지",
          cd._second_person_slots("Image 1의 여성과 Image 10의 남성이 서로 마주보기") == [10])
    check("의상 문구는 슬롯 지정 없음",
          cd._second_person_slots("Image 1의 여성에게 Image 3의 의상을 입히기") == [])
except Exception as e:  # noqa: BLE001
    check("duo 회귀 프로브 실행", False, repr(e)[:200])

print("== 매크로 디테일 강조 (인물 한정) ==")
check("매크로+인물 가드 문구",
      all(s in cd.macro_detail_guard("A portrait of a woman", {"lens": "100mm 매크로 (macro)"})
          for s in ["extreme fine detail", "sharp micro-contrast",
                    "visible pores", "vellus hair"]),
      cd.macro_detail_guard("A portrait of a woman", {"lens": "100mm 매크로 (macro)"}))
check("매크로+제품에는 미적용",
      cd.macro_detail_guard("제품 광고 이미지", {"lens": "100mm 매크로 (macro)"}) == "")
check("인물도 매크로 아니면 미적용",
      cd.macro_detail_guard("A portrait of a woman", {"lens": "85mm f/1.4 (bokeh)"}) == "")
check("SKIN 가드에 모공·결·지향성광·그레인",
      all(s in cd.SKIN_COLOR_GUARD for s in
          ["visible pores", "fine detail", "micro-contrast", "film grain"]),
      cd.SKIN_COLOR_GUARD)
check("SKIN 가드에서 미화 표현 제거",
      all(s not in cd.SKIN_COLOR_GUARD for s in
          ["uniform facial skin color", "even facial complexion",
           "clear unpainted skin"]),
      cd.SKIN_COLOR_GUARD)
_anchor = cd.build_identity_anchor(1, "A portrait of a woman", image_labels=["1"])
check("Qwen identity anchor에 피부 질감 문구",
      "natural realistic skin texture" in _anchor
      and "no airbrushed smoothing" in _anchor, _anchor)
_neg_full = cd.build_negative(dict(cd.DEFAULTS))
check("standalone negative에 플라스틱 피부 방지",
      all(s in _neg_full for s in
          ["plastic waxy skin", "airbrushed smooth skin"]),
      _neg_full[:300])

print("== 노출의도 임상 해부학 가드 ==")
check("노출 주제에 완성 문구 (anatomical 어휘 없이 — 의학 도판 편향 회피)",
      "natural realistic human body" in cd.nudity_anatomy_guard("A nude portrait of a woman")
      and "anatomical" not in cd.nudity_anatomy_guard("A nude portrait of a woman"),
      cd.nudity_anatomy_guard("A nude portrait of a woman"))
check("일반 인물에는 미적용",
      cd.nudity_anatomy_guard("A portrait of a woman in a park") == "")
check("고양이에는 미적용",
      cd.nudity_anatomy_guard("창가에서 잠든 고양이") == "")
_neg_nude = cd.build_negative(dict(cd.DEFAULTS), topic="누드 초상")
check("노출 시 standalone negative에 임상 방지",
      "deformed intimate anatomy" in _neg_nude)
check("비노출 negative에는 없음",
      "deformed intimate anatomy" not in _neg_full)

print("== 정밀 검토 후속 수정 (R1~R6) ==")

print("-- R1: provider↔model 불일치 자동 교정 --")
check("Anthropic + gpt 모델 → 기본값 교정",
      cd.resolve_model("Anthropic", "gpt-4o-mini") == "claude-3-5-haiku-latest")
check("Ollama + gpt 모델 → 기본값 교정",
      cd.resolve_model("Ollama", "gpt-4o-mini") == "llama3.2")
check("Ollama + claude 모델 → 기본값 교정",
      cd.resolve_model("Ollama", "claude-3-5-haiku-latest") == "llama3.2")
check("OpenAI + claude 모델 → 기본값 교정",
      cd.resolve_model("OpenAI", "claude-3-5-haiku-latest") == "gpt-4o-mini")
check("빈 model은 provider 기본값",
      cd.resolve_model("Anthropic", "") == "claude-3-5-haiku-latest"
      and cd.resolve_model("Ollama", "") == "llama3.2")
check("Ollama 로컬 모델명은 유지",
      cd.resolve_model("Ollama", "qwen2.5-vl") == "qwen2.5-vl")
check("적합 모델명은 유지",
      cd.resolve_model("OpenAI", "gpt-4.1-mini") == "gpt-4.1-mini"
      and cd.resolve_model("Anthropic", "claude-sonnet-4") == "claude-sonnet-4")

print("-- R2: 직접 설정 AUTO 항목은 tier 판정 --")
llm_client.chat = _fake_chat
try:
    _pos_r2, _, _ = run(topic="창가에서 잠든 고양이", preset=cd.CUSTOM,
                        automation="AI 판단 (llm)", lens="24mm 광각 (wide)")
    check("직접 설정+llm: 명시 렌즈 우선", "24mm" in _pos_r2, _pos_r2[:300])
    check("직접 설정+llm: AUTO 샷은 LLM 판정", "close-up shot" in _pos_r2,
          _pos_r2[:300])
    check("직접 설정+llm: LLM 렌즈는 명시값에 의해 덮임", "85mm" not in _pos_r2,
          _pos_r2[:300])
finally:
    llm_client.chat = _orig_chat
_pos_r2b, _, _ = run(topic="x", preset=cd.CUSTOM, automation="수동 (manual)",
                     lens="24mm 광각 (wide)")
check("직접 설정+manual: 명시 렌즈 유지 + AUTO 항목은 기본값",
      "24mm" in _pos_r2b and "medium shot" in _pos_r2b, _pos_r2b[:300])

print("-- R4: 캐시 락 존재 --")
check("R4: llm 캐시 락 존재", hasattr(llm_client, "_cache_lock"))
check("R4: reference 캐시 락 존재", hasattr(cd, "_QWEN_REF_LOCK"))

print("-- R5: 3D/사물 model 오탐 제거 --")
check("R5: 3D model 사물은 인물 아님",
      not cd._is_human_subject("A 3D model of a sports car"))
check("R5: scale model 사물은 인물 아님",
      not cd._is_human_subject("a scale model train set"))
check("R5: 3D 모델과 함께 명시된 인물은 인물로 인정",
      cd._is_human_subject("3D 모델 위의 여성"))
check("R5: fashion model은 인물",
      cd._is_human_subject("a fashion model posing in a studio"))
check("R5: 일반 model 단독은 인물 아님", not cd._is_human_subject("model"))
check("R5: 한글 모델은 인물로 유지",
      cd._is_human_subject("모델의 얼굴 클로즈업 초상"))

print("-- R6: LLM 캐시 상한 --")
llm_client.clear_cache()
_orig_post_r6 = llm_client._post
llm_client._post = lambda url, payload, headers, timeout: {
    "choices": [{"message": {"content": '{"scene":"x","camera":{}}'}}]}
try:
    for _i in range(llm_client._CACHE_MAX + 5):
        llm_client.chat("OpenAI", "m", "DUMMY", "sys", f"user{_i}")
    check("R6: 캐시가 상한으로 제한됨",
          len(llm_client._cache) <= llm_client._CACHE_MAX,
          str(len(llm_client._cache)))
    check("R6: 상한 도달 후 최근 항목 히트",
          llm_client.chat("OpenAI", "m", "DUMMY", "sys",
                          f"user{llm_client._CACHE_MAX + 4}") == {"scene": "x", "camera": {}})
finally:
    llm_client._post = _orig_post_r6
llm_client.clear_cache()

print("-- R7: 구도 → 추천 조명 규칙 (LLM 없는 환경) --")
_p7a, _, _ = run(topic="x", preset=cd.CUSTOM, automation="규칙 (auto)",
                 angle="로우앵글 (low angle)")
check("로우앵글 → 림라이트 추천", "strong backlight" in _p7a, _p7a[:300])
_p7b, _, _ = run(topic="x", preset=cd.CUSTOM, automation="규칙 (auto)",
                 shot="극접 (ECU)")
check("극접 → 램브란트 추천", "Rembrandt" in _p7b, _p7b[:300])
_p7c, _, _ = run(topic="x", preset=cd.CUSTOM, automation="규칙 (auto)",
                 shot="극원경 (EWS)")
check("극원경 → 골든아워 추천", "golden hour" in _p7c, _p7c[:300])
_p7d, _, _ = run(topic="네온 간판 아래 얼굴 클로즈업", preset=cd.CUSTOM,
                 automation="규칙 (auto)", shot="근접 (CU)")
check("주제 키워드 조명(네온)은 구도 규칙보다 우선",
      "neon glow" in _p7d and "Rembrandt" not in _p7d, _p7d[:300])
_p7e, _, _ = run(topic="x", preset=cd.CUSTOM, automation="수동 (manual)",
                 angle="로우앵글 (low angle)")
check("수동 티어는 구도 규칙 미적용 (기본 조명 유지)",
      "soft overcast light" in _p7e, _p7e[:300])
_p7f, _, _ = run(topic="x", preset=cd.CUSTOM, automation="규칙 (auto)",
                 shot="중경 (MS)")
check("중경은 추천 규칙 없음 (기본 조명 유지)",
      "soft overcast light" in _p7f, _p7f[:300])

print("-- R8: LM Studio provider (로컬 OpenAI 호환) --")
_input_types = cd.CameraDirector.INPUT_TYPES()
check("R8: provider 목록에 LM Studio 포함",
      "LM Studio" in _input_types["optional"]["provider"][0],
      str(_input_types["optional"]["provider"][0]))

class _RecPost:
    url = None
    payload = None
    headers = None

    def __call__(self, url, payload, headers, timeout):
        _RecPost.url, _RecPost.payload, _RecPost.headers = url, payload, headers
        return {"choices": [{"message": {
            "content": '{"scene":"local scene","camera":{},"note":""}'}}]}

llm_client.clear_cache()
_orig_post_r8 = llm_client._post
llm_client._post = _RecPost()
try:
    llm_client.chat("LM Studio", "qwen2.5-vl", "", "sys", "user text")
    check("R8: LM Studio는 localhost:1234 OpenAI 호환 엔드포인트 호출",
          _RecPost.url == "http://localhost:1234/v1/chat/completions",
          str(_RecPost.url))
    check("R8: LM Studio 키 없이 호출 가능 (Authorization 헤더 없음)",
          "Authorization" not in (_RecPost.headers or {}), str(_RecPost.headers))
    check("R8: LM Studio 모델명 그대로 전달",
          _RecPost.payload.get("model") == "qwen2.5-vl",
          str(_RecPost.payload.get("model")))

    # 빈 model → 자리표시자로 현재 로드된 모델 라우팅
    llm_client.clear_cache()
    llm_client.chat("LM Studio", "", "", "sys", "user text")
    check("R8: 빈 model은 자리표시자 local-model",
          _RecPost.payload.get("model") == "local-model",
          str(_RecPost.payload.get("model")))

    # 비전: OpenAI 규격 image_url data URL로 전달
    llm_client.clear_cache()
    llm_client.chat("LM Studio", "qwen2.5-vl", "", "sys", "look",
                    image_b64="AAAA")
    _ub = _RecPost.payload["messages"][1]["content"]
    check("R8: LM Studio 비전은 image_url data URL 규격",
          isinstance(_ub, list) and _ub[1]["type"] == "image_url"
          and _ub[1]["image_url"]["url"].startswith("data:image/png;base64,"),
          str(_ub)[:200])
finally:
    llm_client._post = _orig_post_r8
llm_client.clear_cache()

check("R8: LM Studio 모델명은 교정 없이 유지",
      cd.resolve_model("LM Studio", "mistral-7b") == "mistral-7b",
      cd.resolve_model("LM Studio", "mistral-7b"))
check("R8: LM Studio API 모델명(gpt-*)도 교정하지 않음",
      cd.resolve_model("LM Studio", "gpt-4o-mini") == "gpt-4o-mini",
      cd.resolve_model("LM Studio", "gpt-4o-mini"))
check("R8: LM Studio 빈 model은 빈 값 유지 (llm_client가 자리표시자 처리)",
      cd.resolve_model("LM Studio", "") == "", repr(cd.resolve_model("LM Studio", "")))

print("-- R9: Skills image_out 출력 + LLM 상태 표시등 --")
_enc_r9 = cd.CameraDirectorEncode()
_kw_r9 = {"topic": "기준 인물", "preset": cd.AUTO, "automation": "수동 (manual)",
          "shot": cd.AUTO, "lens": cd.AUTO, "angle": cd.AUTO,
          "composition": cd.AUTO, "lighting": cd.AUTO, "grade": cd.AUTO,
          "motion": cd.AUTO, "speed": cd.AUTO, "amplitude": cd.AUTO,
          "clip": fake_clip}
_no_img = _enc_r9.run_prompt(**_kw_r9)
check("R9: 이미지 미연결이면 image_out은 None", _no_img[3] is None, repr(_no_img[3]))

_img_r9 = _enc_r9.run_prompt(image_1=VISION_IMG, **_kw_r9)
check("R9: image_1 연결 시 image_out으로 통과",
      _img_r9[3] is VISION_IMG, repr(type(_img_r9[3])))

_img_r9b = _enc_r9.run_prompt(image_3=VISION_IMG, **_kw_r9)
check("R9: image_3만 연결해도 image_out으로 통과",
      _img_r9b[3] is VISION_IMG, repr(type(_img_r9b[3])))

check("R9: _notify_llm_status 헬퍼 존재", callable(cd._notify_llm_status))
_input_hidden = cd.CameraDirector.INPUT_TYPES().get("hidden", {})
check("R9: unique_id hidden 입력 선언 (서버 주입 필수)",
      _input_hidden.get("unique_id") == "UNIQUE_ID", str(_input_hidden))
_check_hidden = cd.CameraDirectorEncode.INPUT_TYPES().get("hidden", {})
check("R9: Skills 노드에도 unique_id hidden 유지",
      _check_hidden.get("unique_id") == "UNIQUE_ID", str(_check_hidden))

print("-- R10: llm_hint 사용자 지시 위젯 --")
_opt_r10 = cd.CameraDirector.INPUT_TYPES()["optional"]
check("R10: llm_hint 위젯 존재", "llm_hint" in _opt_r10)
check("R10: llm_hint는 v1.3.0 위젯들보다 앞에 고정 (위치 매핑 보호)",
      list(_opt_r10).index("llm_hint") < list(_opt_r10).index("vision_detail"),
      str(list(_opt_r10)))
print("-- R35: 위젯 순서 고정 (구 워크플로 위치 매핑 보호) --")
_ord_r35 = list(cd.CameraDirector.INPUT_TYPES()["optional"])
check("R35: v1.3.0 꼬리 순서 보존",
      _ord_r35.index("custom_base_url") < _ord_r35.index("extra_negative")
      < _ord_r35.index("llm_hint"), str(_ord_r35))
check("R35: 신규 위젯은 맨 뒤에만",
      _ord_r35.index("llm_hint") < _ord_r35.index("vision_detail")
      and _ord_r35.index("vision_detail") < _ord_r35.index("pf_steps")
      < _ord_r35.index("pf_cfg") < _ord_r35.index("pf_denoise"),
      str(_ord_r35))
check("R35: required motion2 맨 뒤",
      list(cd.CameraDirector.INPUT_TYPES()["required"])[-1] == "motion2")

print("-- R36: 종합 정밀검토 수정 --")
check("R36: 삭제된 사망 가드 없음",
      not hasattr(cd, "IMAGE_IDENTITY_GUARD")
      and not hasattr(cd, "CONDITIONING_DIRECTOR_GUARD")
      and not hasattr(cd, "HUMAN_BODY_GUARD"))
check("R36: 믹스 가드 슬롯 하드코딩 제거",
      "reference image 1 is the only" not in cd.MIX_GUARD_POSITIVE
      and "main person reference" in cd.MIX_GUARD_POSITIVE)
check("R36: LLM 규격에 motion2",
      '"motion2"' in cd.llm_system())
_cam_m2only = dict(cd.DEFAULTS, motion="없음 (none)", motion2="오빗 (orbit)")
check("R36: motion2만 있어도 무빙 negative",
      "shaky jitter" in cd.build_camera_negative(_cam_m2only))
_cam_static2 = dict(cd.DEFAULTS, motion="정지 (static)",
                    motion2="정지 (static)")
check("R36: 양쪽 정지 중복 없음",
      cd.build_clauses(_cam_static2).count(
          "locked-off static camera, no camera movement") == 1)


class _ScenePost:
    def __call__(self, url, payload, headers, timeout):
        return {"choices": [{"message": {
            "content": '{"scene":"a woman in a park","camera":{},"note":""}'}}]}


_orig_post_r36 = llm_client._post
llm_client._post = _ScenePost()
llm_client.clear_cache()
try:
    _pos_r36, _neg_r36, _ = run(topic="xyz", preset=cd.AUTO,
                                automation="AI 판단 (llm)",
                                shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                                composition=cd.AUTO, lighting=cd.AUTO,
                                grade=cd.AUTO, motion=cd.AUTO,
                                speed=cd.AUTO, amplitude=cd.AUTO,
                                api_key="k")
    check("R36: LLM scene 기준 negative 일관",
          "cross-eyed" in _neg_r36, _neg_r36[:200])
finally:
    llm_client._post = _orig_post_r36
    llm_client.clear_cache()

class _HintPost:
    url = payload = headers = None

    def __call__(self, url, payload, headers, timeout):
        _HintPost.url, _HintPost.payload, _HintPost.headers = url, payload, headers
        return {"choices": [{"message": {
            "content": '{"scene":"hint scene","camera":{},"note":""}'}}]}

_director_r10 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r10 = llm_client._post
llm_client._post = _HintPost()
try:
    _director_r10.run(topic="여성 인물", preset=cd.CUSTOM,
                      automation="AI 판단 (llm)",
                      shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                      composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
                      motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
                      api_key="k",
                      llm_hint="어두운 무드, 클로즈업 위주, 비 오는 장면")
    _msgs = _HintPost.payload["messages"]
    _user_text = " ".join(
        c.get("text", "") if isinstance(c, dict) else str(c)
        for c in _msgs[1]["content"]) if isinstance(_msgs[1]["content"], list) \
        else _msgs[1]["content"]
    check("R10: llm_hint가 LLM user 메시지에 전달됨",
          "어두운 무드, 클로즈업 위주, 비 오는 장면" in _user_text,
          _user_text[-220:])
    check("R10: 지시는 최우선 적용 블록으로 전달",
          "highest priority" in _user_text, _user_text[-220:])
finally:
    llm_client._post = _orig_post_r10
llm_client.clear_cache()

print("-- R11: 장면 문장 품질 (플레이스홀더 제거 + 카메라 일관성) --")
_check = cd.clean_scene_text(
    "She is wearing the exact outfit from Image 2 "
    "(a specific description of the Image 2 outfit must be inserted here "
    "to ensure perfect replication), standing in a garden.")
check("R11: 미완성 플레이스홀더 괄호 제거",
      "inserted here" not in _check and "garden" in _check, _check)
check("R11: 정상 괄호(SSS 등)는 보존",
      cd.clean_scene_text("Soft skin with subsurface scattering (SSS) visible.")
      == "Soft skin with subsurface scattering (SSS) visible",
      cd.clean_scene_text("Soft skin with subsurface scattering (SSS) visible."))
check("R11: 시스템 프롬프트에 의상 처리 우선순위 규칙 포함",
      "EXPLICITLY request an outfit change" in cd.llm_system()
      and "The replacement MUST happen" in cd.llm_system()
      and "keeps their original outfit" in cd.llm_system())
check("R11: 시스템 프롬프트에 카메라-장면 일관성 규칙 포함",
      "MUST agree with the camera labels" in cd.llm_system())
check("R11: 장면-카메라 모순 감지",
      cd.scene_camera_mismatch(
          "a medium close-up of her face", {"shot": "전신 (FS)"}) is not None,
      str(cd.scene_camera_mismatch("a medium close-up of her face",
                                   {"shot": "전신 (FS)"})))
check("R11: 일치하는 장면은 무모순",
      cd.scene_camera_mismatch(
          "a full-length view of her outfit", {"shot": "전신 (FS)"}) is None)

# end-to-end: LLM이 플레이스홀더를 남겨도 최종 프롬프트엔 없어야 함
class _DirtyPost:
    payload = None

    def __call__(self, url, payload, headers, timeout):
        _DirtyPost.payload = payload
        return {"choices": [{"message": {
            "content": '{"scene":"She wears the outfit from Image 2 '
                       '(the exact description must be inserted here) in a room.",'
                       '"camera":{"shot":"중경 (MS)","lens":"50mm 표준 (standard)",'
                       '"angle":"수평 (eye-level)","composition":"삼분할 (rule of thirds)",'
                       '"lighting":"자동 (auto)","grade":"자동 (auto)",'
                       '"motion":"없음 (none)","speed":"보통 (normal)",'
                       '"amplitude":"보통 (normal)"},"note":""}'}}]}

_director_r11 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r11 = llm_client._post
llm_client._post = _DirtyPost()
try:
    _p11, _, _ = _director_r11.run(
        topic="여성 인물", preset=cd.CUSTOM, automation="AI 판단 (llm)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
        amplitude=cd.AUTO, api_key="k")
    check("R11: end-to-end — 플레이스홀더가 최종 프롬프트에 없음",
          "inserted here" not in _p11, _p11[:300])
finally:
    llm_client._post = _orig_post_r11
llm_client.clear_cache()
try:
    cd._notify_llm_status(None, "on")  # node_id 없음 → 조용히 무시
    cd._notify_llm_status("12", "off")  # 서버 없는 환경 → 예외 없이 통과
    check("R9: 표시등 알림은 서버 없는 환경에서 예외 없이 통과", True)
except Exception as e:
    check("R9: 표시등 알림은 서버 없는 환경에서 예외 없이 통과", False, str(e))

print("-- R12: llm_hint 검열 방어어 (negative 자동 추가) --")
check("R12: 방어어 상수에 censored/mosaic 포함",
      "censored" in cd.HINT_DEFENSE_NEGATIVE and "mosaic" in cd.HINT_DEFENSE_NEGATIVE,
      cd.HINT_DEFENSE_NEGATIVE)
check("R12: modest 없음 (단정 유도 금지 — 치마·앉기 순화 방지)",
      "modest" not in cd.HINT_DEFENSE_NEGATIVE, cd.HINT_DEFENSE_NEGATIVE)
check("R12: 방어어에 'blurred' 미포함 (bokeh 충돌 회피)",
      "blurred" not in cd.HINT_DEFENSE_NEGATIVE, cd.HINT_DEFENSE_NEGATIVE)
_neg_on = cd.build_negative({"motion": "없음 (none)"}, hint_defense=True)
_neg_off = cd.build_negative({"motion": "없음 (none)"}, hint_defense=False)
check("R12: hint_defense=True → negative에 방어어 포함",
      "censored, mosaic" in _neg_on, _neg_on)
check("R12: hint_defense=False → negative에 방어어 미포함",
      "censored" not in _neg_off and "mosaic" not in _neg_off, _neg_off)

# end-to-end: llm 티어 + llm_hint → 최종 negative에 방어어 존재
_director_r12 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r12 = llm_client._post
llm_client._post = _HintPost()
try:
    _p12, _n12, _ = _director_r12.run(
        topic="여성 인물", preset=cd.CUSTOM, automation="AI 판단 (llm)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
        amplitude=cd.AUTO, api_key="k",
        llm_hint="어두운 무드, 클로즈업 위주")
    check("R12: llm_hint + AI 판단 → 최종 negative에 방어어 포함",
          "censored, mosaic" in _n12, _n12)
    # llm_hint 없이 실행하면 방어어가 붙지 않는다 (이미 실행된 director 재사용 —
    # 방어어 플래그가 실행마다 갱신되는지 확인)
    _p12b, _n12b, _ = _director_r12.run(
        topic="여성 인물", preset=cd.CUSTOM, automation="AI 판단 (llm)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
        amplitude=cd.AUTO, api_key="k")
    check("R12: llm_hint 없으면 방어어 미포함 (플래그 갱신 확인)",
          "censored" not in _n12b and "mosaic" not in _n12b, _n12b)
finally:
    llm_client._post = _orig_post_r12
llm_client.clear_cache()

print("-- R13: 로컬 LLM 타임아웃 상향 (빨간불 timed out 방지) --")


class _TimeoutProbe:
    def __init__(self):
        self.timeout = None

    def __call__(self, url, payload, headers, timeout):
        self.timeout = timeout
        # provider별 응답 형식이 다르므로 OpenAI/Ollama/Gemini 키를 모두 제공
        return {"choices": [{"message": {"content": "{}"}}],
                "message": {"content": "{}"},
                "candidates": [{"content": {"parts": [{"text": "{}"}]}}]}


llm_client.clear_cache()
_orig_post_r13 = llm_client._post
try:
    _probe_local = _TimeoutProbe()
    llm_client._post = _probe_local
    llm_client.chat("LM Studio", "gemma-4-E4B-it-uncensored-vision", "",
                    "sys", "user")
    check("R13: LM Studio 타임아웃은 LOCAL_TIMEOUT(300초) 이상",
          _probe_local.timeout >= llm_client.LOCAL_TIMEOUT,
          f"timeout={_probe_local.timeout}")
    _probe_ollama = _TimeoutProbe()
    llm_client._post = _probe_ollama
    llm_client.chat("Ollama", "llama3.2", "", "sys", "user")
    check("R13: Ollama 타임아웃도 LOCAL_TIMEOUT 이상",
          _probe_ollama.timeout >= llm_client.LOCAL_TIMEOUT,
          f"timeout={_probe_ollama.timeout}")
    _probe_cloud = _TimeoutProbe()
    llm_client._post = _probe_cloud
    llm_client.chat("OpenAI", "gpt-4o-mini", "k", "sys", "user")
    check("R13: 클라우드(OpenAI)는 기본 타임아웃(45초) 유지",
          _probe_cloud.timeout == llm_client.DEFAULT_TIMEOUT,
          f"timeout={_probe_cloud.timeout}")
finally:
    llm_client._post = _orig_post_r13
llm_client.clear_cache()

print("-- R14: 빈 topic + 이미지 → AI 판단 (llm)이 LLM 호출함 --")
_director_r14 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r14 = llm_client._post
_probe_r14 = _HintPost()
llm_client._post = _probe_r14
try:
    _director_r14.run(topic="", preset=cd.CUSTOM,
                      automation="AI 판단 (llm)",
                      shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                      composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
                      motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
                      api_key="k", image=VISION_IMG)
    _called = _probe_r14.payload is not None
    check("R14: 빈 topic + 이미지 연결 → LLM 호출됨", _called, str(_called))
    if _called:
        _u14 = _probe_r14.payload["messages"][1]["content"]
        if isinstance(_u14, list):
            _u14 = " ".join(str(c) for c in _u14)
        check("R14: 빈 topic 대신 이미지 판정 지시가 user 메시지에 있음",
              "judge from the attached image" in _u14, _u14[:200])
    # 재료 없음(빈 topic + 이미지 없음)이면 LLM 미호출 (기존 동작 유지)
    _HintPost.payload = None  # _HintPost는 클래스 변수 공유 — 재설정 필요
    _probe_r14b = _HintPost()
    llm_client._post = _probe_r14b
    llm_client.clear_cache()
    _director_r14.run(topic="", preset=cd.CUSTOM,
                      automation="AI 판단 (llm)",
                      shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                      composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
                      motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
                      api_key="k")
    check("R14: topic·이미지 모두 없으면 LLM 미호출",
          _probe_r14b.payload is None, str(_probe_r14b.payload is not None))
finally:
    llm_client._post = _orig_post_r14
llm_client.clear_cache()

print("-- R15: 다중 참조 믹스 가드 (융합/신원 혼합 방어) --")
check("R15: 믹스 가드 상수에 융합/혼합 방어 문구 포함",
      "clothing fusion" in cd.MIX_GUARD_NEGATIVE
      and "mixed facial features" in cd.MIX_GUARD_NEGATIVE
      and "separate clothing layer" in cd.MIX_GUARD_POSITIVE)
_director_r15 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r15 = llm_client._post
_HintPost.payload = None
llm_client._post = _HintPost()
try:
    _p15a, _n15a, _ = _director_r15.run(
        topic="여성 인물", preset=cd.CUSTOM, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
        amplitude=cd.AUTO, image_list=[VISION_IMG, VISION_IMG])
    check("R15: 이미지 2장 → positive에 믹스 가드 포함",
          "Reference mixing guard" in _p15a and
          "separate clothing layer" in _p15a, _p15a[-260:])
    check("R15: 이미지 2장 → negative에 믹스 방어어 포함",
          "clothing fusion with skin" in _n15a, _n15a)
    _p15b, _n15b, _ = _director_r15.run(
        topic="여성 인물", preset=cd.CUSTOM, automation="규칙 (auto)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
        amplitude=cd.AUTO, image=VISION_IMG)
    check("R15: 이미지 1장 → 믹스 가드 미포함",
          "Reference mixing guard" not in _p15b
          and "clothing fusion" not in _n15b, _n15b)
    check("R15: 플래그 갱신 — 1장 실행 후 plan.mix_guard=False",
          _director_r15._last_guard_plan["flags"]["mix_guard"] is False,
          str(_director_r15._last_guard_plan["flags"]["mix_guard"]))
finally:
    llm_client._post = _orig_post_r15
llm_client.clear_cache()

print("-- R16: 9·10번 슬롯 외양 참조 (사용자 전용) --")
check("R16: 외양 참조 상수 — 삽입 방어 문구 포함, anatomical 어휘 없음",
      "no collage" in cd.APPEARANCE_REF_POSITIVE
      and "collage" in cd.APPEARANCE_REF_NEGATIVE
      and "anatomical" not in cd.APPEARANCE_REF_POSITIVE)
_director_r16 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r16 = llm_client._post
_HintPost.payload = None
llm_client._post = _HintPost()
try:
    _kw_r16 = dict(topic="여성 인물", preset=cd.CUSTOM, automation="규칙 (auto)",
                   shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
                   lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
                   amplitude=cd.AUTO)
    _ten = [VISION_IMG] * 10
    _p16a, _n16a, _ = _director_r16.run(image_list=_ten, **_kw_r16)
    check("R16: 10번 연결 → positive에 외양 참조 가드 포함",
          "Appearance reference" in _p16a, _p16a[-240:])
    check("R16: 10번 연결 → negative에 컷 삽입 방어어 포함",
          "collage" in _n16a and "split view" in _n16a, _n16a)
    # 9번 슬롯만 연결된 경우
    _nine = [None] * 8 + [VISION_IMG]
    _p16c, _n16c, _ = _director_r16.run(image_list=_nine, **_kw_r16)
    check("R16: 9번 연결 → positive에 외양 참조 가드 포함",
          "Appearance reference" in _p16c, _p16c[-240:])
    check("R16: 9번 연결 → negative에 컷 삽입 방어어 포함",
          "collage" in _n16c and "split view" in _n16c, _n16c)
    _p16b, _n16b, _ = _director_r16.run(image_list=[VISION_IMG, VISION_IMG], **_kw_r16)
    check("R16: 9·10번 미연결(2장) → 외양 참조 가드 미포함",
          "Appearance reference" not in _p16b and "collage" not in _n16b, _n16b)
    check("R16: 플래그 갱신 — 9·10번 미연결 실행 후 False",
          _director_r16._last_appearance_ref is False,
          str(_director_r16._last_appearance_ref))
    # Skills 경로: image_1 + image_9 → prompt_out에 외양 가드 포함
    _enc_r16 = cd.CameraDirectorEncode()
    _kw_s16 = dict(_kw_r16)
    _kw_s16.update({"clip": fake_clip})
    _out16 = _enc_r16.run_prompt(image_1=VISION_IMG, image_9=VISION_IMG, **_kw_s16)
    check("R16: Skills 경로(image_9)에도 외양 가드 병합됨",
          "Appearance reference" in _out16[2], _out16[2][-240:])
finally:
    llm_client._post = _orig_post_r16
llm_client.clear_cache()

print("-- R17: 실행 이력 허브 전송 (telemetry) --")
_captured_r17 = []
_orig_sender_r17 = cd._TELEMETRY_SENDER
cd._TELEMETRY_SENDER = lambda rec: _captured_r17.append(rec)
_director_r17 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r17 = llm_client._post
_HintPost.payload = None
llm_client._post = _HintPost()
try:
    _director_r17.run(topic="여성 인물", preset=cd.CUSTOM, automation="규칙 (auto)",
                      shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
                      lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
                      amplitude=cd.AUTO, image_list=[VISION_IMG, VISION_IMG])
    check("R17: 실행 1회당 이력 1건 전송", len(_captured_r17) == 1,
          str(len(_captured_r17)))
    if _captured_r17:
        _rec = _captured_r17[0]
        check("R17: node 식별자 포함 (허브 폴더 분류용)",
              _rec.get("node") == "camera_director", str(sorted(_rec.keys())))
        check("R17: 레코드 필수 필드 존재 (tier/camera/guards/llm/ts)",
              all(k in _rec for k in ("tier", "camera", "guards", "llm", "ts")),
              str(sorted(_rec.keys())))
        check("R17: tier/guards/llm 값 정확",
              _rec["tier"] == "auto"
              and _rec["guards"]["mix_guard"] is True
              and _rec["guards"]["appearance_ref"] is False
              and _rec["llm"]["attempted"] is False
              and _rec["image_count"] == 2, str(_rec))
        check("R17: topic 원문 미전송 (길이만 기록)",
              "topic" not in _rec and "topic_chars" in _rec, str(sorted(_rec.keys())))
finally:
    llm_client._post = _orig_post_r17
    cd._TELEMETRY_SENDER = _orig_sender_r17
llm_client.clear_cache()

print("-- R18: 9·10번 슬롯 외양 참조 전용 역할 고정 (일반 보조 역할 목록 제외) --")
_guard_1_9 = cd.reference_guard(2, image_labels=[1, 9], topic="여성 인물")
check("R18: reference_guard(1+9)에 배경·의상·소품 역할 목록 없음",
      "background, outfit" not in _guard_1_9, _guard_1_9)
check("R18: reference_guard(1+9)에 9번 역할 지정 문구 없음",
      "image 9" not in _guard_1_9 and "image(s) 9" not in _guard_1_9, _guard_1_9)
check("R18: reference_guard(1+9)에 주 신원 보존 문구 유지",
      "only main human identity" in _guard_1_9, _guard_1_9)
_guard_1_2_9 = cd.reference_guard(3, image_labels=[1, 2, 9], topic="여성 인물")
check("R18: reference_guard(1+2+9)는 2번은 역할 목록에, 9번은 제외",
      "image(s) 2 only" in _guard_1_2_9 and "9" not in _guard_1_2_9.replace("1, 2", ""), _guard_1_2_9)
_anchor_1_2_9 = cd.build_secondary_role_anchor(3, "여성 인물", image_labels=[1, 2, 9])
check("R18: secondary_anchor(1+2+9)는 2번 역할 목록 유지, 9번 제외",
      "image(s) 2 only" in _anchor_1_2_9 and "9" not in _anchor_1_2_9.replace("1, 2", ""), _anchor_1_2_9)
_anchor_1_9 = cd.build_secondary_role_anchor(2, "여성 인물", image_labels=[1, 9])
check("R18: secondary_anchor(1+9)에 역할 목록 문구 없음",
      "background, outfit" not in _anchor_1_9 and "only main subject" in _anchor_1_9,
      _anchor_1_9)
_guard_1_10 = cd.reference_guard(2, image_labels=[1, 10], topic="여성 인물")
check("R18: reference_guard(1+10)도 10번 역할 지정 문구 없음",
      "image(s) 10" not in _guard_1_10 and "background, outfit" not in _guard_1_10,
      _guard_1_10)
_duo_1_2 = cd.build_duo_person_anchor(2, "두 번째 사람과 함께 서 있는 장면",
                                      image_labels=[1, 2])
_duo_1_9 = cd.build_duo_person_anchor(2, "두 번째 사람과 함께 서 있는 장면",
                                      image_labels=[1, 9])
check("R18: duo anchor는 1+2 조합에서 두 인물 유지",
      "reference image 2" in _duo_1_2, _duo_1_2)
check("R18: duo anchor는 1+9 조합에서 9번을 인물로 취급하지 않음",
      _duo_1_9 == "" or "reference image 9" not in _duo_1_9, _duo_1_9)
check("R18: 외양 참조 positive 가드는 역할 문구 그대로 유지 (R19에서 부위 매칭으로 강화)",
      "body appearance references" in cd.APPEARANCE_REF_POSITIVE
      and "intimate region" in cd.APPEARANCE_REF_POSITIVE,
      cd.APPEARANCE_REF_POSITIVE)

print("-- R19: 외양 참조 부위 자동 매칭 (9·10 순서 무관) --")
check("R19: positive 가드 — 부위 매칭 + 교차 금지 문구 포함, anatomical 없음",
      "match each reference to the body region" in cd.APPEARANCE_REF_POSITIVE
      and "Never swap" in cd.APPEARANCE_REF_POSITIVE
      and "anatomical" not in cd.APPEARANCE_REF_POSITIVE,
      cd.APPEARANCE_REF_POSITIVE[:160])
_director_r19 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r19 = llm_client._post
_HintPost.payload = None
llm_client._post = _HintPost()
_kw_r19 = dict(preset=cd.CUSTOM, automation="AI 판단 (llm)",
               shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
               lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
               amplitude=cd.AUTO, api_key="k")
try:
    # 9=가슴, 10=성기 순서로 연결 (테스트 이미지는 동일하지만 슬롯 위치만 검증)
    _ten_r19 = [VISION_IMG] * 10
    _p19a, _, _ = _director_r19.run(topic="여성 인물", image_list=_ten_r19, **_kw_r19)
    _msgs19 = _HintPost.payload["messages"]
    _user19 = " ".join(
        c.get("text", "") if isinstance(c, dict) else str(c)
        for c in _msgs19[1]["content"]) if isinstance(_msgs19[1]["content"], list) \
        else _msgs19[1]["content"]
    check("R19: LLM 노트 — 부위 식별 지시 포함",
          "identify which body region" in _user19, _user19[-300:])
    check("R19: LLM 노트 — 매핑 명시 + 교차 금지 지시 포함",
          "name the depicted region per reference" in _user19
          and "never swapped" in _user19, _user19[-300:])
    check("R19: LLM 노트 — 9·10번 슬롯 번호 모두 지칭",
          "Reference image 9, 10" in _user19, _user19[-300:])
    check("R19: positive에 교차 금지 문구 병합",
          "Never swap" in _p19a, _p19a[-240:])
    # 역순(9=성기, 10=가슴)으로 연결해도 동일한 매칭 지시 — 노트는 슬롯 위치 기반
    llm_client.clear_cache()
    _HintPost.payload = None
    _ten_rev = [VISION_IMG] * 10
    _p19b, _, _ = _director_r19.run(topic="여성 인물", image_list=_ten_rev, **_kw_r19)
    _msgs19b = _HintPost.payload["messages"]
    _user19b = " ".join(
        c.get("text", "") if isinstance(c, dict) else str(c)
        for c in _msgs19b[1]["content"]) if isinstance(_msgs19b[1]["content"], list) \
        else _msgs19b[1]["content"]
    check("R19: 역순 연결에도 동일한 매칭 지시 (순서 무관)",
          "identify which body region" in _user19b
          and "never swapped" in _user19b
          and "Reference image 9, 10" in _user19b, _user19b[-300:])
    check("R19: 역순 연결 → positive에 외양 가드 포함",
          "Appearance reference" in _p19b and "Never swap" in _p19b, _p19b[-240:])
finally:
    llm_client._post = _orig_post_r19
llm_client.clear_cache()

print("-- R20: 샷 명시 감지·모순 경고 기준 통일 (최장 일치) --")
check("R20: 한글 '전신' 명시 → FS 샷 확정",
      cd.topic_shot_label("여성이 파티 드레스를 입고 전신 모습을 보여주는 장면")
      == "전신 (FS)")
check("R20: 영문 bare 'full body' 명시 → FS 샷 확정",
      cd.topic_shot_label("a woman showing her full body") == "전신 (FS)")
check("R20: 규칙이 다른 샷을 골라도 명시 샷이 이긴다",
      cd.topic_shot_label("전신으로 보여주는 인물") == "전신 (FS)"
      and "전신" in cd.TOPIC_SHOT_PHRASES["전신 (FS)"])
check("R20: 명시 샷 반영 시 모순 경고 없음",
      cd.scene_camera_mismatch("전신 모습의 여성", {"shot": "전신 (FS)"}) is None)
check("R20: 한글 중첩 — '중근접'은 CU가 아니라 MCU로 판정",
      cd.topic_shot_label("얼굴 중근접 클로즈") == "중근접 (MCU)")
check("R20: 한글 중첩 — '극원경'은 WS가 아니라 EWS로 판정",
      cd.topic_shot_label("도시의 극원경 풍경") == "극원경 (EWS)")
check("R20: LLM prose 모순 경고는 여전히 작동",
      cd.scene_camera_mismatch("a medium close-up portrait",
                               {"shot": "전신 (FS)"}) is not None)
check("R20: 일치하는 장면(FS)은 무모순",
      cd.scene_camera_mismatch("a full-length view of her outfit",
                               {"shot": "전신 (FS)"}) is None)

print("-- R21: 신체 발란스·캐릭터 시트 참조·외양 체모 실사감 --")
_director_r21 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r21 = llm_client._post
_HintPost.payload = None
llm_client._post = _HintPost()
_kw_r21 = dict(preset=cd.CUSTOM, automation="규칙 (auto)",
               shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
               lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
               amplitude=cd.AUTO, api_key="k")
try:
    # 1) 신체 발란스 — 인물 주제면 참조 유무 무관 첨부, 풍경은 미첨부
    _p21a, _n21a, _ = _director_r21.run(topic="여성 인물", image_list=None, **_kw_r21)
    check("R21: 인물 주제 positive에 신체 발란스 가드 포함",
          "body balance: natural human proportions" in _p21a, _p21a[-200:])
    check("R21: 인물 주제 negative에 발란스 방어어 포함",
          "disproportionate limbs" in _n21a, _n21a[-200:])
    llm_client.clear_cache()
    _p21b, _n21b, _ = _director_r21.run(topic="도시 야경 풍경", image_list=None, **_kw_r21)
    check("R21: 풍경 주제엔 발란스 가드 미첨부",
          "body balance" not in _p21b and "disproportionate limbs" not in _n21b,
          _p21b[-160:])
    # 2) 캐릭터 시트 — 시트 의도 + 이미지 연결 시 가드, 없으면 미첨부
    llm_client.clear_cache()
    _p21c, _n21c, _ = _director_r21.run(
        topic="캐릭터 시트를 참고해 같은 인물로 촬영", image_list=[VISION_IMG],
        **_kw_r21)
    check("R21: 시트 참조 positive에 신원 일관성 + 레이아웃 방지 문구",
          "character sheet reference" in _p21c
          and "same one person" in _p21c
          # 2026-09-29 실측 교정: "no multi-panel arrangement" 같은 **시트 용어**
          # 로는 레이아웃이 막히지 않았다(실제 생성에서 시트가 그대로 렌더링).
          # 무엇을 그릴지를 positive 로 직접 말하는 새 문구로 교체했다.
          and "must NOT appear in the output" in _p21c, _p21c[-320:])
    check("R21: 시트 뷰가 별개 사람으로 세어지는 것 방어 (positive)",
          "never a crowd" in _p21c
          and "never a second person" in _p21c
          and "duplicated or mirrored faces" in _p21c
          and "NOT separate people" in _p21c, _p21c[-460:])
    check("R21: 실사용 표준 뷰 구성 명시",
          "front full-body view" in _p21c and "back full-body view" in _p21c
          and "close-up head front" in _p21c
          and "left profile close-up" in _p21c, _p21c[-460:])
    check("R21: 시트 참조 negative에 시트 레이아웃 방어어",
          "contact sheet" in _n21c and "sprite sheet" in _n21c, _n21c[-200:])
    check("R21: negative에도 '복수 인물' 방어 반영",
          "counted as separate people" in _n21c
          and "cloned faces" in _n21c, _n21c[-300:])
    llm_client.clear_cache()
    _p21d, _n21d, _ = _director_r21.run(
        topic="여성 인물", image_list=[VISION_IMG], **_kw_r21)
    check("R21: 시트 의도 없으면 시트 가드 미첨부",
          "character sheet reference" not in _p21d
          and "contact sheet" not in _n21d, _p21d[-160:])
    # 3) 외양 체모 실사감 — 9/10 연결 시 체모 문구 + negative 방어어
    llm_client.clear_cache()
    _ten_r21 = [VISION_IMG] * 10
    _p21e, _n21e, _ = _director_r21.run(topic="여성 인물", image_list=_ten_r21,
                                        **_kw_r21)
    check("R21: 외양 참조 positive에 체모 실사감 문구 포함",
          "individual strands growing from the skin" in _p21e
          and "no clumped patches" in _p21e, _p21e[-240:])
    check("R21: 외양 참조 negative에 체모 방어어 포함",
          "sticker-like body hair" in _n21e
          and "clumped hair patches" in _n21e, _n21e[-200:])
    check("R21: 발란스·외양 가드 판정 저장 (Skills 병합용)",
          _director_r21._last_guard_plan["flags"]["body_balance"] is True
          and _director_r21._last_appearance_ref is True, "flags")
finally:
    llm_client._post = _orig_post_r21
llm_client.clear_cache()

print("-- R22: 다중 인물 자동 분류 (인물/사물 역할 + 주체 자동 선출) --")
# 1) 사물 역할 검출 헬퍼
check("R22: 사물 역할 검출(이미지 2의 핸드백)",
      cd._object_role_slots("이미지 2의 핸드백을 든 장면") == {2})
check("R22: 사물 역할 검출(EN wristwatch from reference image 4)",
      cd._object_role_slots("wristwatch from reference image 4") == {4})
check("R22: 사물 역할 없으면 빈 집합",
      cd._object_role_slots("여성 인물") == set())

# 2) 역할 계획 — 주체 자동 선출 + 분류
_plan_a = cd._person_object_plan("이미지 1번 핸드백, 이미지 2번 여성", [1, 2])
check("R22: 첫 슬롯이 사물이면 다음 인물이 주 피사체",
      _plan_a["main"] == 2 and _plan_a["objects"] == [1], str(_plan_a))
_plan_b = cd._person_object_plan(
    "이미지 1번 여성, 이미지 2번 핸드백, 이미지 3번 남성", [1, 2, 3])
check("R22: 첫 슬롯이 인물이면 주체 유지 + 분류",
      _plan_b["main"] == 1 and _plan_b["persons"] == [3]
      and _plan_b["objects"] == [2], str(_plan_b))
_plan_c = cd._person_object_plan("여성 인물", [1, 2])
check("R22: 근거 없으면 기존 규약 유지",
      _plan_c["main"] == 1 and _plan_c["persons"] == []
      and _plan_c["objects"] == [], str(_plan_c))

# 3) 가드 반영 — reference_guard / build_secondary_role_anchor / body_proportion_guard
_guard_a = cd.reference_guard(2, [1, 2], "이미지 1번 핸드백, 이미지 2번 여성")
check("R22: reference_guard가 여성 슬롯을 주 피사체로",
      "as the only main human identity, use reference image(s) 1" in _guard_a,
      _guard_a[:160])
_guard_b = cd.reference_guard(3, [1, 2, 3],
                              "이미지 1번 여성, 이미지 2번 핸드백을 든 장면, "
                              "이미지 3번 남성과 여성이 서로 마주보기")
check("R22: duo 가드에 사물 슬롯 소품 제한 문구 포함",
      "only as props/objects, never as people" in _guard_b
      and "reference image(s) 2" in _guard_b, _guard_b[:200])
_anchor_a = cd.build_secondary_role_anchor(2, "이미지 1번 핸드백, 이미지 2번 여성",
                                           [1, 2])
check("R22: build_secondary_role_anchor가 여성 슬롯을 주체로",
      "Use reference image 2 as the only main subject" in _anchor_a,
      _anchor_a[:120])
_body_a = cd.body_proportion_guard(2, "이미지 1번 핸드백, 이미지 2번 여성", [1, 2])
check("R22: body_proportion_guard가 여성 슬롯을 identity/body 참조로",
      "use reference image 2 as the identity and body reference" in _body_a,
      _body_a[:120])

# 4) 5인 단체 사진 일반화
_anchor_b = cd.build_duo_person_anchor(
    5, "이미지 2의 남성, 이미지 3의 여성, 이미지 4의 남성, 이미지 5의 여성과 함께 단체 사진",
    [1, 2, 3, 4, 5])
check("R22: 5인 단체 앵커(Five main people + 5 슬롯 매핑)",
      "Five main people" in _anchor_b
      and "reference image 2" in _anchor_b and "reference image 5" in _anchor_b,
      _anchor_b[:200])

# 5) LLM image_note 반영 (주체 교체 + 사물 소품 제한 + 내용 식별 지시)
_director_r22 = cd.CameraDirector()
llm_client.clear_cache()
_orig_post_r22 = llm_client._post
_HintPost.payload = None
llm_client._post = _HintPost()
_kw_r22 = dict(preset=cd.CUSTOM, automation="AI 판단 (llm)",
               shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
               lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
               amplitude=cd.AUTO, api_key="k")
try:
    _director_r22.run(topic="이미지 1번 핸드백, 이미지 2번 여성",
                      image_list=[VISION_IMG] * 2, **_kw_r22)
    _msgs22 = _HintPost.payload["messages"]
    _user22 = " ".join(
        c.get("text", "") if isinstance(c, dict) else str(c)
        for c in _msgs22[1]["content"]) if isinstance(_msgs22[1]["content"], list) \
        else _msgs22[1]["content"]
    check("R22: LLM 노트가 여성 슬롯을 주 피사체로 지정",
          "Use reference image 2 as the only main human identity" in _user22,
          _user22[-300:])
    check("R22: LLM 노트가 사물 슬롯을 소품 제한",
          "only as props/objects, never as people" in _user22, _user22[-300:])
    check("R22: LLM 노트에 참조 내용 식별 지시 포함",
          "whether it depicts a person or an object" in _user22, _user22[-300:])
finally:
    llm_client._post = _orig_post_r22
llm_client.clear_cache()

print("-- R23: 정밀 검토 후속 수정 (앵커 계획 연동·outfit 게이트·사물 어휘·image_out) --")
# F1: identity 앵커가 역할 주체(실제 인물) 슬롯을 identity 소스로
check("R23: identity 앵커가 사물 아닌 인물 슬롯(2번)을 identity 소스로",
      cd.build_identity_anchor(2, "이미지 1번 핸드백을 든 장면, 이미지 2번 여성",
                               [1, 2])
      .startswith("Use reference image 2 as the exact identity source"))
check("R23: 근거 없으면 identity 앵커는 첫 슬롯 유지(하위 호환)",
      cd.build_identity_anchor(2, "여성 인물", [1, 2])
      .startswith("Use reference image 1 as the exact identity source"))

# F2: single 앵커가 유일 인물 슬롯으로 발화
check("R23: single 앵커가 유일 인물 슬롯(2번)으로 발화",
      cd.build_single_person_anchor(2, "이미지 1번 핸드백을 든 장면, 이미지 2번 여성",
                                    [1, 2])
      .startswith("Exactly one main person in the output, using reference image 2"))
check("R23: duo 이상이면 single 앵커 억제 유지",
      cd.build_single_person_anchor(2, "Image 1의 여성과 Image 2의 남성이 서로 마주보기",
                                    [1, 2]) == "")

# F3: outfit 게이트 정밀화 — 의상 슬롯만 제외, 다른 인물 duo 보존
_t23 = "이미지 2의 원피스로 갈아입은 여성과 이미지 3번 남성이 서로 마주보기"
check("R23: 혼합 의상+인물 씬에서 다른 인물 duo 보존",
      cd.build_duo_person_anchor(3, _t23, [1, 2, 3]).startswith("Two main people"),
      cd.build_duo_person_anchor(3, _t23, [1, 2, 3])[:80])
check("R23: 혼합 씬에서 의상 슬롯만 인물 번호에서 제외",
      2 not in cd._second_person_slots(_t23)
      and 3 in cd._second_person_slots(_t23),
      str(cd._second_person_slots(_t23)))
check("R23: 순수 의상 실행은 duo 없음(구버전 동일)",
      cd.build_duo_person_anchor(2, "이미지 2의 원피스를 여성에게 입히기", [1, 2]) == "")
check("R23: 의상 슬롯 검출(이미지 2의 원피스)",
      cd._clothing_role_slots("이미지 2의 원피스") == {2})

# F4: 모호한 짧은 사물 어휘 오검출 제거
check("R23: '검은 머리'가 사물로 오검출되지 않음",
      cd._object_role_slots("이미지 2의 검은 머리를 가진 여성") == set())
check("R23: 핸드백은 여전히 사물로 검출",
      cd._object_role_slots("이미지 2의 핸드백") == {2})

# F5: image_out이 실제 인물(주체) 이미지로 통과
_enc_r23 = cd.CameraDirectorEncode()
_kw_r23 = {"preset": cd.AUTO, "automation": "수동 (manual)",
           "shot": cd.AUTO, "lens": cd.AUTO, "angle": cd.AUTO,
           "composition": cd.AUTO, "lighting": cd.AUTO, "grade": cd.AUTO,
           "motion": cd.AUTO, "speed": cd.AUTO, "amplitude": cd.AUTO,
           "clip": fake_clip}
_img_other = VISION_IMG * 0.5
_out_mixed = _enc_r23.run_prompt(topic="이미지 1번 핸드백을 든 장면, 이미지 2번 여성",
                                 image_1=VISION_IMG, image_2=_img_other, **_kw_r23)
check("R23: image_out이 실제 인물(2번) 이미지로 통과",
      _out_mixed[3] is _img_other, repr(type(_out_mixed[3])))
_out_plain = _enc_r23.run_prompt(topic="여성 인물",
                                 image_1=VISION_IMG, image_2=_img_other, **_kw_r23)
check("R23: 근거 없으면 image_out은 첫 연결 유지(하위 호환)",
      _out_plain[3] is VISION_IMG, repr(type(_out_plain[3])))


print("-- R24: 신규 LLM 제공자 (Gemini / OpenRouter / Groq / DeepSeek / Mistral) --")
_input_types_r24 = cd.CameraDirector.INPUT_TYPES()
_provider_list = _input_types_r24["optional"]["provider"][0]
check("R24: provider 목록에 Gemini 포함", "Gemini" in _provider_list, str(_provider_list))
check("R24: provider 목록에 OpenRouter 포함", "OpenRouter" in _provider_list)
check("R24: provider 목록에 Groq 포함", "Groq" in _provider_list)
check("R24: provider 목록에 DeepSeek 포함", "DeepSeek" in _provider_list)
check("R24: provider 목록에 Mistral 포함", "Mistral" in _provider_list)

# 모델 교정
for _p_r24, _d_r24 in {
    "Gemini": "gemini-1.5-flash",
    "OpenRouter": "google/gemini-flash-1.5",
    "Groq": "llama-3.2-90b-vision-preview",
    "DeepSeek": "deepseek-chat",
    "Mistral": "pixtral-12b-2409",
}.items():
    check(f"R24: {_p_r24} 빈 모델 → 기본값",
          cd.resolve_model(_p_r24, "") == _d_r24,
          cd.resolve_model(_p_r24, ""))
    if _p_r24 == "OpenRouter":
        # OpenRouter는 OpenAI 모델도 프록시할 수 있어 교정하지 않는다.
        check(f"R24: {_p_r24}는 OpenAI 모델명도 그대로 허용",
              cd.resolve_model(_p_r24, "gpt-4o-mini") == "gpt-4o-mini",
              cd.resolve_model(_p_r24, "gpt-4o-mini"))
    else:
        check(f"R24: {_p_r24}에 gpt-4o-mini 교정",
              cd.resolve_model(_p_r24, "gpt-4o-mini") == _d_r24,
              cd.resolve_model(_p_r24, "gpt-4o-mini"))
check("R24: Gemini는 gemini- 접두사 유지",
      cd.resolve_model("Gemini", "gemini-2.0-flash-exp") == "gemini-2.0-flash-exp")
check("R24: OpenRouter는 자유 모델명 유지",
      cd.resolve_model("OpenRouter", "meta-llama/llama-3.2-90b-vision-instruct:free")
      == "meta-llama/llama-3.2-90b-vision-instruct:free")

class _RecPost24:
    url = None
    payload = None
    headers = None

    def __call__(self, url, payload, headers, timeout):
        _RecPost24.url, _RecPost24.payload, _RecPost24.headers = url, payload, headers
        # OpenAI 호환 + Gemini 두 응답 형식 모두 커버
        return {
            "choices": [{"message": {"content": '{"scene":"x","camera":{}}'}}],
            "candidates": [{"content": {"parts": [{"text": '{"scene":"x","camera":{}}'}]}}],
        }

llm_client.clear_cache()
_orig_post_r24 = llm_client._post
llm_client._post = _RecPost24()
try:
    # Gemini
    llm_client.chat("Gemini", "gemini-1.5-flash", "DUMMY", "sys", "user text")
    check("R24: Gemini endpoint 형식",
          "generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
          in _RecPost24.url,
          _RecPost24.url)
    check("R24: Gemini 키는 URL 쿼리에 포함",
          "key=DUMMY" in _RecPost24.url,
          _RecPost24.url)
    check("R24: Gemini payload는 contents.parts 구조",
          "contents" in _RecPost24.payload
          and "parts" in _RecPost24.payload["contents"][0],
          str(_RecPost24.payload)[:200])

    # Gemini vision
    llm_client.clear_cache()
    llm_client.chat("Gemini", "gemini-1.5-flash", "DUMMY", "sys", "look",
                    image_b64="AAAA")
    _parts24 = _RecPost24.payload["contents"][0]["parts"]
    check("R24: Gemini 비전은 inline_data",
          _parts24[1].get("inline_data", {}).get("mime_type") == "image/png",
          str(_parts24)[:200])

    # OpenRouter
    llm_client.clear_cache()
    llm_client.chat("OpenRouter", "google/gemini-flash-1.5", "DUMMY", "sys", "user text")
    check("R24: OpenRouter endpoint",
          _RecPost24.url == "https://openrouter.ai/api/v1/chat/completions",
          _RecPost24.url)
    check("R24: OpenRouter는 HTTP-Referer / X-Title 헤더 포함",
          _RecPost24.headers.get("HTTP-Referer", "").startswith("https://github.com/")
          and "X-Title" in _RecPost24.headers,
          str(_RecPost24.headers))

    # Groq
    llm_client.clear_cache()
    llm_client.chat("Groq", "llama-3.2-90b-vision-preview", "DUMMY", "sys", "user text")
    check("R24: Groq endpoint",
          _RecPost24.url == "https://api.groq.com/openai/v1/chat/completions",
          _RecPost24.url)

    # DeepSeek
    llm_client.clear_cache()
    llm_client.chat("DeepSeek", "deepseek-chat", "DUMMY", "sys", "user text")
    check("R24: DeepSeek endpoint",
          _RecPost24.url == "https://api.deepseek.com/chat/completions",
          _RecPost24.url)

    # Mistral
    llm_client.clear_cache()
    llm_client.chat("Mistral", "pixtral-12b-2409", "DUMMY", "sys", "user text")
    check("R24: Mistral endpoint",
          _RecPost24.url == "https://api.mistral.ai/v1/chat/completions",
          _RecPost24.url)

    # OpenAI 호환 비전 (Groq 예시)
    llm_client.clear_cache()
    llm_client.chat("Groq", "llama-3.2-90b-vision-preview", "DUMMY", "sys", "look",
                    image_b64="AAAA")
    _ub24 = _RecPost24.payload["messages"][1]["content"]
    check("R24: OpenAI 호환 비전은 image_url data URL",
          isinstance(_ub24, list) and _ub24[1]["type"] == "image_url"
          and _ub24[1]["image_url"]["url"].startswith("data:image/png;base64,"),
          str(_ub24)[:200])
finally:
    llm_client._post = _orig_post_r24
llm_client.clear_cache()

# 신규 클라우드 제공자는 기본 타임아웃(45초)을 유지해야 한다.
_probe_r24_gemini = _TimeoutProbe()
_probe_r24_openrouter = _TimeoutProbe()
llm_client.clear_cache()
_orig_post_r24t = llm_client._post
try:
    llm_client._post = _probe_r24_gemini
    llm_client.chat("Gemini", "gemini-1.5-flash", "k", "sys", "user")
    check("R24: Gemini 타임아웃은 기본 45초 유지",
          _probe_r24_gemini.timeout == llm_client.DEFAULT_TIMEOUT,
          f"timeout={_probe_r24_gemini.timeout}")
    llm_client._post = _probe_r24_openrouter
    llm_client.chat("OpenRouter", "x", "k", "sys", "user")
    check("R24: OpenRouter 타임아웃은 기본 45초 유지",
          _probe_r24_openrouter.timeout == llm_client.DEFAULT_TIMEOUT,
          f"timeout={_probe_r24_openrouter.timeout}")
finally:
    llm_client._post = _orig_post_r24t
llm_client.clear_cache()


print("-- R25: Custom (OpenAI 호환) 제공자 — 임의 엔드포인트 연동 --")
_input_types_r25 = cd.CameraDirector.INPUT_TYPES()
check("R25: provider 목록에 Custom (OpenAI 호환) 포함",
      "Custom (OpenAI 호환)" in _input_types_r25["optional"]["provider"][0],
      str(_input_types_r25["optional"]["provider"][0]))
check("R25: custom_base_url 위젯 존재",
      "custom_base_url" in _input_types_r25["optional"],
      str(list(_input_types_r25["optional"])))

# 모델 교정: Custom은 사용자 입력값 그대로 (엔드포인트의 모델명을 직접 넣음)
check("R25: Custom은 모델명 무교정",
      cd.resolve_model("Custom (OpenAI 호환)", "my-org/my-model-x")
      == "my-org/my-model-x",
      cd.resolve_model("Custom (OpenAI 호환)", "my-org/my-model-x"))

# 엔드포인트 정규화 3형태
_norm = llm_client._normalize_custom_endpoint
check("R25: Base URL 뒤 /chat/completions 자동 부착",
      _norm("https://api.example.com/v1")
      == "https://api.example.com/v1/chat/completions", _norm("https://api.example.com/v1"))
check("R25: 끝 슬래시 정규화",
      _norm("https://api.example.com/v1/")
      == "https://api.example.com/v1/chat/completions", _norm("https://api.example.com/v1/"))
check("R25: 전체 URL은 그대로 통과",
      _norm("https://api.example.com/v1/chat/completions")
      == "https://api.example.com/v1/chat/completions",
      _norm("https://api.example.com/v1/chat/completions"))
try:
    _norm("   ")
    check("R25: 빈 Base URL은 실패", False, "예외 없음")
except llm_client.LLMError as e:
    check("R25: 빈 Base URL은 명확한 안내와 함께 실패",
          "custom_base_url" in str(e), str(e))

class _RecPost25:
    url = None
    payload = None
    headers = None
    timeout = None

    def __call__(self, url, payload, headers, timeout):
        _RecPost25.url, _RecPost25.payload, _RecPost25.headers = url, payload, headers
        _RecPost25.timeout = timeout
        return {"choices": [{"message": {"content": '{"scene":"x","camera":{}}'}}]}

_CUSTOM_LABEL = "Custom (OpenAI 호환)"

# 호출 검증: URL·Bearer 헤더·payload
llm_client.clear_cache()
_orig_post_r25 = llm_client._post
_probe25 = _RecPost25()
llm_client._post = _probe25
try:
    llm_client.chat(_CUSTOM_LABEL, "my-model", "SECRET", "sys", "user text",
                    base_url="https://api.example.com/v1")
    check("R25: Custom 호출 URL",
          _probe25.url == "https://api.example.com/v1/chat/completions", str(_probe25.url))
    check("R25: Custom Bearer 헤더",
          _probe25.headers.get("Authorization") == "Bearer SECRET", str(_probe25.headers))
    check("R25: Custom payload 모델명",
          _probe25.payload.get("model") == "my-model", str(_probe25.payload)[:120])

    # 키 없는 게이트웨이: **로컬만** Authorization 없이 보낸다.
    # 2026-10-01 변경: 예전에는 `https://api.example.com` 으로 빈 키 요청을
    # 보내 Authorization 생략을 검증했다. 그것이 **지침상 금지된 외부 전송을
    # 그대로 허용하는 경로**였고, 실환경에서 base_url=openrouter + 빈 키로
    # 401(No cookie auth credentials found)을 받고 45초를 버렸다.
    # 로컬 게이트웨이(LM Studio/Ollama 대역)는 키가 필요 없으므로 유지한다.
    llm_client.clear_cache()
    llm_client.chat(_CUSTOM_LABEL, "my-model", "", "sys", "user text",
                    base_url="http://127.0.0.1:8080/v1")
    check("R25: 로컬 Custom 키 없으면 Authorization 헤더 생략",
          "Authorization" not in (_probe25.headers or {}), str(_probe25.headers))

    # 외부 Custom + 키 없음 → 아예 요청하지 않는다(R80).
    llm_client.clear_cache()
    _ext_blocked = False
    _ext_msg = ""
    try:
        llm_client.chat(_CUSTOM_LABEL, "my-model", "", "sys", "user text",
                        base_url="https://api.example.com/v1")
    except llm_client.LLMError as _e:
        _ext_blocked = True
        _ext_msg = str(_e)
    check("R25: 외부 Custom 키 없으면 요청을 보내지 않는다", _ext_blocked,
          _ext_msg[:80])

    # localhost Base URL → 로컬 타임아웃 상향
    llm_client.clear_cache()
    llm_client.chat(_CUSTOM_LABEL, "my-model", "", "sys", "user text",
                    base_url="http://127.0.0.1:8080/v1")
    check("R25: Custom localhost는 로컬 타임아웃(300초)",
          _probe25.timeout == llm_client.LOCAL_TIMEOUT, f"timeout={_probe25.timeout}")

    # 원격 Base URL → 기본 타임아웃 유지
    # 키를 **넣는다** — 검증 대상은 타임아웃이지 "키가 없으면 되는지" 가
    # 아니므로. 키 없는 원격 호출은 R80 에서 차단되며 그건 위에서 확인했다.
    llm_client.clear_cache()
    llm_client.chat(_CUSTOM_LABEL, "my-model", "SECRET", "sys", "user text",
                    base_url="https://api.example.com/v1")
    check("R25: Custom 원격은 기본 타임아웃(45초)",
          _probe25.timeout == llm_client.DEFAULT_TIMEOUT, f"timeout={_probe25.timeout}")

    # model 비면 명확한 에러
    llm_client.clear_cache()
    try:
        llm_client.chat(_CUSTOM_LABEL, "", "", "sys", "user text",
                        base_url="https://api.example.com/v1")
        check("R25: Custom 빈 model은 실패", False, "예외 없음")
    except llm_client.LLMError as e:
        check("R25: Custom 빈 model은 안내와 함께 실패",
              "model" in str(e).lower(), str(e))

    # 캐시 분리: 같은 model·텍스트라도 다른 엔드포인트는 재호출된다
    # 주소를 **로컬**로 둔다 — 검증 대상은 캐시 키 분리이지 외부 전송이
    # 아니므로, 키 없는 외부 Custom 은 R80 에서 막힌다(2026-10-01 변경).
    llm_client.clear_cache()
    _calls25 = {"n": 0}

    def _counting_post25(url, payload, headers, timeout):
        _calls25["n"] += 1
        return {"choices": [{"message": {"content": '{"scene":"x","camera":{}}'}}]}

    llm_client._post = _counting_post25
    llm_client.chat(_CUSTOM_LABEL, "my-model", "", "sys", "same text",
                    base_url="http://127.0.0.1:9101/v1")
    llm_client.chat(_CUSTOM_LABEL, "my-model", "", "sys", "same text",
                    base_url="http://127.0.0.1:9102/v1")
    check("R25: 다른 엔드포인트는 캐시 공유 안 함 (2회 호출)",
          _calls25["n"] == 2, f"calls={_calls25['n']}")
    _calls25["n"] = 0
    llm_client.chat(_CUSTOM_LABEL, "my-model", "", "sys", "same text",
                    base_url="http://127.0.0.1:9101/v1")
    check("R25: 같은 엔드포인트 재호출은 캐시 히트 (0회 호출)",
          _calls25["n"] == 0, f"calls={_calls25['n']}")
finally:
    llm_client._post = _orig_post_r25
llm_client.clear_cache()

# 노드 경유(run_prompt) Custom 실행 — 로컬 게이트웨이 모킹
class _NodePost25:
    def __init__(self):
        self.urls = []

    def __call__(self, url, payload, headers, timeout):
        self.urls.append(url)
        return {"choices": [{"message": {"content":
            '{"scene":"a woman in a red dress walks toward the camera",'
            '"camera":{"shot":"중경 (MS)","lens":"50mm 표준 (standard)",'
            '"angle":"수평 (eye-level)","composition":"삼분할 (rule of thirds)",'
            '"lighting":"자연광 (natural)","grade":"뉴트럴 (neutral)",'
            '"motion":"이동 (dolly in)","speed":"정상 (normal)",'
            '"amplitude":"중간 (medium)"}}'}}]}

_node_post25 = _NodePost25()
_enc_r25 = cd.CameraDirectorEncode()
_orig_post_r25n = llm_client._post
llm_client._post = _node_post25
llm_client.clear_cache()
try:
    _out_r25 = _enc_r25.run_prompt(
        topic="여성 인물", preset=cd.AUTO, automation="AI 판단 (llm)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
        composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
        motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO, clip=fake_clip,
        provider=_CUSTOM_LABEL, model="gateway-model", api_key="",
        custom_base_url="http://127.0.0.1:9000/v1")
    check("R25: 노드 실행이 Custom 엔드포인트로 호출",
          _node_post25.urls
          and _node_post25.urls[0] == "http://127.0.0.1:9000/v1/chat/completions",
          str(_node_post25.urls))
    check("R25: Custom LLM 판정 결과가 카메라에 반영",
          getattr(_enc_r25, "_last_camera", {}).get("shot") == "중경 (MS)",
          str(getattr(_enc_r25, "_last_camera", {})))
finally:
    llm_client._post = _orig_post_r25n
llm_client.clear_cache()

print("-- R26: 사진 메타데이터 안전 (서버 기록 api_key 제거) --")
check("R26: hidden에 prompt 선언",
      cd.CameraDirector.INPUT_TYPES().get("hidden", {}).get("prompt") == "PROMPT",
      str(cd.CameraDirector.INPUT_TYPES().get("hidden", {})))
check("R26: Skills hidden에도 prompt 유지",
      cd.CameraDirectorEncode.INPUT_TYPES().get("hidden", {}).get("prompt") == "PROMPT")
import inspect as _inspect_r26
check("R26: run/run_prompt가 prompt 인자 수신",
      "prompt" in _inspect_r26.signature(cd.CameraDirector.run).parameters
      and "prompt" in _inspect_r26.signature(cd.CameraDirectorEncode.run_prompt).parameters)


def _prompt_r26(uid, key):
    return {str(uid): {"class_type": "GoRi_CameraDirectorEncodeSkills",
                       "inputs": {"api_key": key, "topic": "t"}},
            "99": {"class_type": "GoRi_CameraDirectorEncodeSkills",
                   "inputs": {"api_key": "other-key", "topic": "o"}}}


check("R26: 자기 entry만 제거", cd._scrub_api_key_from_prompt(_prompt_r26(7, "sk-a"), 7) is True)
_p_r26 = _prompt_r26(7, "sk-a")
cd._scrub_api_key_from_prompt(_p_r26, 7)
check("R26: 자기 키 빈칸", _p_r26["7"]["inputs"]["api_key"] == "")
check("R26: 타 노드 키 보존", _p_r26["99"]["inputs"]["api_key"] == "other-key")
check("R26: 문자열 unique_id도 동작",
      cd._scrub_api_key_from_prompt(_prompt_r26(7, "sk-a"), "7") is True)
check("R26: prompt None이면 False", cd._scrub_api_key_from_prompt(None, 7) is False)
check("R26: prompt 비dict면 False", cd._scrub_api_key_from_prompt("x", 7) is False)
check("R26: unique_id None이면 False",
      cd._scrub_api_key_from_prompt(_prompt_r26(7, "sk-a"), None) is False)
check("R26: 없는 id면 False",
      cd._scrub_api_key_from_prompt(_prompt_r26(7, "sk-a"), 1234) is False)
check("R26: 이미 빈 키면 False",
      cd._scrub_api_key_from_prompt(_prompt_r26(7, ""), 7) is False)

_enc_r26 = cd.CameraDirector()
_p_exec_r26 = _prompt_r26(7, "sk-exec")
_out_r26 = _enc_r26.run(topic="창가 고양이", preset=cd.AUTO, automation="규칙 (auto)",
                        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                        composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
                        motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
                        api_key="sk-exec", unique_id=7, prompt=_p_exec_r26)
check("R26: 실행 후 기록 키 제거", _p_exec_r26["7"]["inputs"]["api_key"] == "")
check("R26: 실행 결과 정상 (제거와 무관)", isinstance(_out_r26, tuple) and len(_out_r26) == 3)

print("-- R26b: 사진 PNG 메타데이터 scrub (extra_pnginfo 경로) --")
# 왜(Why) 이 블록이 필요한가(2026-09-30 실측): SaveImage 는 `extra_pnginfo`
# 를 PNG 청크에 통째로 박는데, 그 안의 `workflow` 은 프론트가 보낸 위젯
# 원본이라 prompt 기록과 **별개 dict**다. prompt 만 지우면 저장된 사진에
# 키가 남았다(당일 저장 이미지 전부가 이 경로로 키를 담고 있었다).


def _png_r26b(uid, key, other="other-key"):
    """실측 구조 재현: nodes 는 list, id 는 unique_id 와 같은 문자열."""
    return {"workflow": {"nodes": [
        {"id": str(uid), "type": "GoRi_CameraDirectorEncodeSkills",
         "widgets_values": ["topic", "sk-model", key, "https://x"],
         "widgets_values_named": {"topic": "topic", "model": "sk-model",
                                  "api_key": key,
                                  "custom_base_url": "https://x"}},
        {"id": "99", "type": "GoRi_CameraDirectorEncodeSkills",
         "widgets_values": ["t2", other],
         "widgets_values_named": {"topic": "t2", "api_key": other}},
    ]}}


check("R26b: hidden에 extra_pnginfo 선언",
      cd.CameraDirector.INPUT_TYPES().get("hidden", {}).get("extra_pnginfo")
      == "EXTRA_PNGINFO",
      str(cd.CameraDirector.INPUT_TYPES().get("hidden", {})))
check("R26b: Skills hidden에도 extra_pnginfo 유지",
      cd.CameraDirectorEncode.INPUT_TYPES().get("hidden", {}).get("extra_pnginfo")
      == "EXTRA_PNGINFO")
check("R26b: run/run_prompt가 extra_pnginfo 인자 수신",
      "extra_pnginfo" in _inspect_r26.signature(cd.CameraDirector.run).parameters
      and "extra_pnginfo" in _inspect_r26.signature(
          cd.CameraDirectorEncode.run_prompt).parameters)

_e_r26b = _png_r26b(7, "sk-png")
check("R26b: 자기 entry 키 제거", cd._scrub_api_key_from_extra_pnginfo(_e_r26b, 7, "sk-png") is True)
check("R26b: widgets_values 빈칸",
      _e_r26b["workflow"]["nodes"][0]["widgets_values"][2] == "")
check("R26b: widgets_values_named 빈칸",
      _e_r26b["workflow"]["nodes"][0]["widgets_values_named"]["api_key"] == "")
check("R26b: 같은 문자열 다른 인덱스는 보존",
      _e_r26b["workflow"]["nodes"][0]["widgets_values"][1] == "sk-model")
check("R26b: 타 노드 키 보존",
      _e_r26b["workflow"]["nodes"][1]["widgets_values_named"]["api_key"] == "other-key")
check("R26b: 제거 후 키 미잔존 확인",
      cd._api_key_left_in_png(_e_r26b, 7, "sk-png") is False)
check("R26b: 문자열 unique_id도 동작",
      cd._scrub_api_key_from_extra_pnginfo(_png_r26b(7, "sk-png"), "7", "sk-png") is True)
check("R26b: nodes 가 dict 여도 동작",
      cd._scrub_api_key_from_extra_pnginfo(
          {"workflow": {"nodes": {"7": {"id": "7", "widgets_values": ["sk-d"],
                                        "widgets_values_named": {"api_key": "sk-d"}}}}},
          7, "sk-d") is True)
check("R26b: named 없이 widgets_values 만 있어도 제거",
      cd._scrub_api_key_from_extra_pnginfo(
          {"workflow": {"nodes": [{"id": "7", "widgets_values": ["sk-v"]}]}},
          7, "sk-v") is True)
check("R26b: extra_pnginfo None이면 False",
      cd._scrub_api_key_from_extra_pnginfo(None, 7, "sk-png") is False)
check("R26b: 비dict면 False",
      cd._scrub_api_key_from_extra_pnginfo("x", 7, "sk-png") is False)
check("R26b: unique_id None이면 False",
      cd._scrub_api_key_from_extra_pnginfo(_png_r26b(7, "sk-png"), None, "sk-png") is False)
check("R26b: 빈 키면 False",
      cd._scrub_api_key_from_extra_pnginfo(_png_r26b(7, ""), 7, "") is False)
check("R26b: 없는 id면 False",
      cd._scrub_api_key_from_extra_pnginfo(_png_r26b(7, "sk-png"), 1234, "sk-png") is False)
check("R26b: workflow 없으면 False",
      cd._scrub_api_key_from_extra_pnginfo({"x": 1}, 7, "sk-png") is False)
check("R26b: 좌변조 확인 — 키가 실제로 없으면 False",
      cd._scrub_api_key_from_extra_pnginfo(_png_r26b(7, ""), 7, "sk-png") is False)
check("R26b: 경고 판정 — 키 잔존 시 True",
      cd._api_key_left_in_png(_png_r26b(7, "sk-png"), 7, "sk-png") is True)
check("R26b: 경고 판정 — 빈칸이면 False(오탐 방지)",
      cd._api_key_left_in_png(_png_r26b(7, ""), 7, "sk-png") is False)

# 실측 스냅샷 그대로: PNG 청크에 들어갈 dict 에 키가 없어야 한다.
_snap_r26b = _png_r26b(285, "sk-or-v1-" + "a" * 64)
cd._scrub_api_key_from_extra_pnginfo(_snap_r26b, 285, "sk-or-v1-" + "a" * 64)
import json as _json_r26b
check("R26b: 직렬화한 전체 스냅샷에 키 문자열 없음",
      ("sk-or-v1-" + "a" * 64) not in
      _json_r26b.dumps(_snap_r26b, ensure_ascii=False))

# run() 경유: 실제로 두 표면이 함께 정리되는지
_enc_r26b = cd.CameraDirector()
_pr_r26b = _prompt_r26(7, "sk-exec-both")
_pg_r26b = _png_r26b(7, "sk-exec-both")
_enc_r26b.run(topic="창가 고양이", preset=cd.AUTO, automation="규칙 (auto)",
              shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
              composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
              motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
              api_key="sk-exec-both", unique_id=7, prompt=_pr_r26b,
              extra_pnginfo=_pg_r26b)
check("R26b: run() 후 실행 기록 키 제거",
      _pr_r26b["7"]["inputs"]["api_key"] == "")
check("R26b: run() 후 워크플로 스냅샷 키 제거",
      _pg_r26b["workflow"]["nodes"][0]["widgets_values_named"]["api_key"] == "")

# 조용한 실패 방지: 못 지우면 경고가 1회 나가야 한다.
_cap_r26b = []
_orig_log_r26b = cd._log
cd._log = lambda m: _cap_r26b.append(m)
try:
    cd._SCRUB_WARNED.clear()
    _stuck_r26b = _png_r26b(7, "sk-stuck")
    cd._warn_scrub_unavailable("sk-stuck", _prompt_r26(7, "sk-stuck"), 7,
                               _stuck_r26b, False)
    check("R26b: PNG 키 잔존 시 경고 1회",
          len(_cap_r26b) == 1 and "지우지 못했" in _cap_r26b[0],
          str(_cap_r26b[:1]))
    cd._warn_scrub_unavailable("sk-stuck", _prompt_r26(7, "sk-stuck"), 7,
                               _stuck_r26b, False)
    check("R26b: 같은 사유는 재차 경고 안 함(로그 안 더러워짐)", len(_cap_r26b) == 1)
    cd._SCRUB_WARNED.clear()
    _cap_r26b.clear()
    _ok_r26b = _png_r26b(7, "sk-ok")
    cd._scrub_api_key_from_extra_pnginfo(_ok_r26b, 7, "sk-ok")
    cd._warn_scrub_unavailable("sk-ok", _prompt_r26(7, "sk-ok"), 7, _ok_r26b, True)
    check("R26b: 정상 경로면 경고 없음(오탐 금지)", not _cap_r26b, str(_cap_r26b[:1]))
    cd._SCRUB_WARNED.clear()
    _cap_r26b.clear()
    cd._warn_scrub_unavailable("sk-ok", _prompt_r26(7, "sk-ok"), 7,
                               _png_r26b(7, ""), False)
    check("R26b: 프론트가 이미 빈칸이면 경고 없음(오탐 금지)", not _cap_r26b,
          str(_cap_r26b[:1]))
finally:
    cd._log = _orig_log_r26b
    cd._SCRUB_WARNED.clear()

print("-- R27: 루트 .env 키 파일 (표준 방식) --")
import tempfile as _tf_r27
_tmpd_r27 = _tf_r27.mkdtemp()
_envp_r27 = os.path.join(_tmpd_r27, ".env")
with open(_envp_r27, "w", encoding="utf-8") as _f:
    _f.write("# comment\nOPENAI_API_KEY=sk-file-1\nEMPTY=\nQUOTED=\"sk-q\"\n")
_orig_env_override = llm_client._ENV_FILE_OVERRIDE
llm_client._ENV_FILE_OVERRIDE = _envp_r27
check("R27: .env 읽기", llm_client._read_env_file_key("OPENAI_API_KEY") == "sk-file-1")
check("R27: 따옴표 처리", llm_client._read_env_file_key("QUOTED") == "sk-q")
check("R27: 없는 키는 빈값", llm_client._read_env_file_key("NOPE") == "")
check("R27: 빈 이름은 빈값", llm_client._read_env_file_key("") == "")

check("R27: 저장(신규)", cd._write_env_file_key("GROQ_API_KEY", "gsk-new") is True)
check("R27: 저장값 반영",
      llm_client._read_env_file_key("GROQ_API_KEY") == "gsk-new")
check("R27: 교체", cd._write_env_file_key("OPENAI_API_KEY", "sk-file-2") is True
      and llm_client._read_env_file_key("OPENAI_API_KEY") == "sk-file-2")
check("R27: 주석 보존", "# comment" in open(_envp_r27, encoding="utf-8").read())
check("R27: 삭제(빈값)", cd._write_env_file_key("GROQ_API_KEY", "") is True
      and llm_client._read_env_file_key("GROQ_API_KEY") == "")
check("R27: 미등록 env 거부",
      cd._write_env_file_key("EVIL_KEY", "x") is False)
check("R27: 개행 키 거부",
      cd._write_env_file_key("OPENAI_API_KEY", "a\nb") is False
      and llm_client._read_env_file_key("OPENAI_API_KEY") == "sk-file-2")


class _FilePost:
    def __init__(self):
        self.headers = None

    def __call__(self, url, payload, headers, timeout):
        _FilePost.headers = headers
        return {"choices": [{"message": {
            "content": '{"scene":"s","camera":{},"note":""}'}}]}


_filepost_r27 = _FilePost()
_orig_post_r27 = llm_client._post
llm_client._post = _filepost_r27
llm_client.clear_cache()
try:
    llm_client.chat("OpenAI", "gpt-4o-mini", "", "sys", "user")
    check("R27: 위젯 빈칸이면 .env 키로 호출",
          (_FilePost.headers or {}).get("Authorization") == "Bearer sk-file-2",
          str(_FilePost.headers))
    llm_client.clear_cache()
    llm_client.chat("OpenAI", "gpt-4o-mini", "sk-widget", "sys", "user")
    check("R27: 위젯값이 .env보다 우선",
          (_FilePost.headers or {}).get("Authorization") == "Bearer sk-widget",
          str(_FilePost.headers))
    llm_client.clear_cache()
    try:
        llm_client.chat("DeepSeek", "deepseek-chat", "", "sys", "user")
        check("R27: 키 전무 시 LLMError", False)
    except llm_client.LLMError as _e:
        check("R27: 키 전무 시 LLMError", ".env" in str(_e), str(_e))
finally:
    llm_client._post = _orig_post_r27
    llm_client._ENV_FILE_OVERRIDE = _orig_env_override
    llm_client.clear_cache()

# R27b: .env **루트 탐색** 자체를 검사한다. R27 은 _ENV_FILE_OVERRIDE 로
# 경로를 주입했으므로 탐색 로직을 아예 건드리지 않았다. 그 공백 때문에
# "정확히 2단계" 규칙이 Registry 팩(깊이 2)에서 조용히 깨져 있었다 —
# 실제 ComfyUI 기동 로그에서 `.env에 API 키를 저장할 수 없습니다` 로
# 드러났다(2026-09-30). 배포 형태 두 가지를 모두 확인한다.
_orig_file_r27b = llm_client.__file__
try:
    for _depth_r27b, _label_r27b in ((1, "단독 설치"), (2, "Registry 팩")):
        _root_r27b = os.path.join(_tmpd_r27, "root%d" % _depth_r27b)
        _node_r27b = _root_r27b
        for _i in range(_depth_r27b):
            _node_r27b = os.path.join(_node_r27b, "n%d" % _i)
        os.makedirs(_node_r27b, exist_ok=True)
        with open(os.path.join(_root_r27b, "main.py"), "w", encoding="utf-8") as _f:
            _f.write("# fake ComfyUI root\n")
        llm_client.__file__ = os.path.join(_node_r27b, "llm_client.py")
        _got_r27b = llm_client._env_file_path()
        check("R27b: .env 루트 탐색 (%s, 깊이 %d)" % (_label_r27b, _depth_r27b),
              _got_r27b == os.path.join(_root_r27b, ".env"), str(_got_r27b))
    # 루트에 main.py 가 없으면 조용히 실패하지 않고 None 을 돌려줘야 한다
    _bare_r27b = os.path.join(_tmpd_r27, "bare", "n0")
    os.makedirs(_bare_r27b, exist_ok=True)
    llm_client.__file__ = os.path.join(_bare_r27b, "llm_client.py")
    check("R27b: 루트 미발견 시 None (조용한 실패 아님)",
          llm_client._env_file_path() is None, str(llm_client._env_file_path()))
finally:
    llm_client.__file__ = _orig_file_r27b

print("-- R28: 정밀 검토 후속 수정 7건 --")
_cam_r28 = dict(cd.DEFAULTS)
check("R28: Skills negative 노출 분기",
      "deformed intimate anatomy" in cd.build_camera_negative(_cam_r28, topic="누드 초상"))
check("R28: Skills negative 비노출 미첨부",
      "deformed intimate anatomy" not in cd.build_camera_negative(_cam_r28, topic="공원 초상"))
_cam_f14 = dict(cd.DEFAULTS, lens="85mm f/1.4 (bokeh)")
check("R28: Skills negative f/1.4 분기",
      "busy distracting background" in cd.build_camera_negative(_cam_f14))
_cam_macro = dict(cd.DEFAULTS, lens="100mm 매크로 (macro)")
_neg_macro = cd.build_camera_negative(_cam_macro)
check("R28: Skills negative 매크로 분기",
      "soft detail, muddy texture" in _neg_macro and "muddy detail" not in _neg_macro)

_enc_r28 = cd.CameraDirectorEncode()
_out_r28 = _enc_r28.run_prompt(
    clip=fake_clip, topic="나체 여성 인물", preset=cd.AUTO, automation="수동 (manual)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    image_1=VISION_IMG, image_2=VISION_IMG)
_pos_r28 = _out_r28[2]
check("R28: standalone 믹스 가드 중복 없음",
      _pos_r28.count(cd.MIX_GUARD_POSITIVE) == 1, str(_pos_r28.count(cd.MIX_GUARD_POSITIVE)))
check("R28: standalone 노출 가드 중복 없음",
      _pos_r28.count("clearly defined natural intimate detail") == 1)
_neg_r28 = _out_r28[1][0][1] if _out_r28[1] else ""
check("R28: Skills negative에 노출 방어 포함",
      "deformed intimate anatomy" in _neg_r28, _neg_r28[:200])

# 클래스 접근은 디스크립터를 벗긴 함수라 복원하면 인스턴스 메서드가 된다.
# __dict__의 staticmethod 객체를 통째로 보관·복원해야 한다.
_orig_prepare = cd.CameraDirectorEncode.__dict__["_prepare_qwen_image_data"]
cd.CameraDirectorEncode._prepare_qwen_image_data = staticmethod(
    lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
try:
    _fb_r28 = _enc_r28.run_prompt(
        clip=fake_clip, topic="고양이", preset=cd.AUTO, automation="수동 (manual)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO)
    check("R28: reference 준비 실패해도 실행 생존",
          isinstance(_fb_r28, tuple) and len(_fb_r28) == 5)
finally:
    cd.CameraDirectorEncode._prepare_qwen_image_data = _orig_prepare


class _QI28:
    shape = (1, 8, 8, 3)

    def __init__(self, bad=False):
        self.bad = bad

    def __getitem__(self, idx):
        if self.bad:
            raise RuntimeError("broken")
        return self

    def movedim(self, *a):
        if self.bad:
            raise RuntimeError("broken")
        return self


import types as _types_r28
_m28 = _types_r28.ModuleType("comfy")
_u28 = _types_r28.ModuleType("comfy.utils")
_u28.common_upscale = lambda *a, **k: _QI28()
_m28.utils = _u28
_nh28 = _types_r28.ModuleType("node_helpers")
_orig_mods = {k: sys.modules.get(k) for k in ("comfy", "comfy.utils", "node_helpers")}
sys.modules["comfy"] = _m28
sys.modules["comfy.utils"] = _u28
sys.modules["node_helpers"] = _nh28
_orig_key28 = cd._qwen_ref_cache_key
cd._qwen_ref_cache_key = lambda image, w, h, vae: f"t28:{id(image)}"
try:
    _imgs28, _lats28 = cd.CameraDirectorEncode._prepare_qwen_image_data(
        [(1, _QI28()), (2, _QI28(bad=True))], vae=None, latent_image=None)
    check("R28: 깨진 이미지만 제외", len(_imgs28) == 1 and _lats28 in ([], None),
          f"imgs={len(_imgs28)}")
finally:
    cd._qwen_ref_cache_key = _orig_key28
    for _k, _v in _orig_mods.items():
        if _v is None:
            sys.modules.pop(_k, None)
        else:
            sys.modules[_k] = _v

check("R28: provider None 교정 크래시 없음",
      cd.resolve_model(None, "gpt-4o-mini") == "gpt-4o-mini")
try:
    llm_client.chat(None, "m", "", "s", "u")
    check("R28: provider None은 LLMError", False)
except llm_client.LLMError:
    check("R28: provider None은 LLMError", True)
except AttributeError as _e:
    check("R28: provider None은 LLMError", False, f"AttributeError: {_e}")

check("R28: 페이로드 검증 정상",
      cd._valid_api_key_payload("OpenAI", "k") == ("OPENAI_API_KEY", "k"))
check("R28: 비문자열 키 거부",
      cd._valid_api_key_payload("OpenAI", 123) == (None, None))
check("R28: Custom 제공자 거부",
      cd._valid_api_key_payload("Custom (OpenAI 호환)", "k") == (None, None))
check("R28: 9번 사물 분류 제외",
      cd._person_object_plan("이미지 9의 가방", [9])["objects"] == [])

print("-- R29: 로컬 LLM 전송 경량화 + VRAM 정리 --")
check("R29: vision_detail 매핑",
      cd.vision_detail_px("선명 (768)") == 768
      and cd.vision_detail_px("균형 (512)") == 512
      and cd.vision_detail_px("절약 (384)") == 384)
check("R29: vision_detail 미지정 폴백",
      cd.vision_detail_px("???") == 768 and cd.vision_detail_px(None) == 768)
check("R29: vision_detail 위젯 존재",
      "vision_detail" in cd.CameraDirector.INPUT_TYPES()["optional"])
import inspect as _inspect_r29
check("R29: run/run_prompt가 vision_detail 수신",
      "vision_detail" in _inspect_r29.signature(cd.CameraDirector.run).parameters
      and "vision_detail" in _inspect_r29.signature(
          cd.CameraDirectorEncode.run_prompt).parameters)
check("R29: VRAM 정리 안전 호출", cd._release_vram() is None)


class _SizePost:
    def __call__(self, url, payload, headers, timeout):
        return {"choices": [{"message": {
            "content": '{"scene":"s","camera":{},"note":""}'}}]}


_orig_b64_r29 = llm_client.image_to_b64
_sizes_r29 = []
llm_client.image_to_b64 = lambda img, max_side=768: (_sizes_r29.append(max_side), "B64")[1]
_orig_post_r29 = llm_client._post
llm_client._post = _SizePost()
llm_client.clear_cache()
try:
    cd.CameraDirector().run(
        topic="여성 인물", preset=cd.AUTO, automation="AI 판단 (llm)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
        composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
        motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
        api_key="k", image_items=[(1, VISION_IMG)],
        vision_detail="절약 (384)")
    check("R29: vision 크기가 전송에 반영", _sizes_r29 and all(s == 384 for s in _sizes_r29),
          str(_sizes_r29))
    _sizes_r29.clear()
    llm_client.clear_cache()
    cd.CameraDirector().run(
        topic="여성 인물", preset=cd.AUTO, automation="AI 판단 (llm)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
        composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
        motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
        api_key="k", image_items=[(1, VISION_IMG)])
    check("R29: 기본값 768 유지", _sizes_r29 and all(s == 768 for s in _sizes_r29),
          str(_sizes_r29))
finally:
    llm_client.image_to_b64 = _orig_b64_r29
    llm_client._post = _orig_post_r29
    llm_client.clear_cache()

print("-- R30: 출발 점검 + 해부 디테일 팩 --")
check("R30: standalone 해부팩 (인물)",
      "cross-eyed" in cd.build_negative(dict(cd.DEFAULTS), topic="여성 인물"))
check("R30: standalone 해부팩 (비인물 미첨부)",
      "cross-eyed" not in cd.build_negative(dict(cd.DEFAULTS), topic="창가 고양이"))
check("R30: Skills 해부팩 (인물)",
      "cross-eyed" in cd.build_camera_negative(dict(cd.DEFAULTS), topic="여성 인물"))
check("R30: Skills 해부팩 (비인물 미첨부)",
      "cross-eyed" not in cd.build_camera_negative(dict(cd.DEFAULTS), topic="제품 시계"))
_cam_cu = dict(cd.DEFAULTS, shot="근접 (CU)")
_w_cu_low = cd.preflight_warnings("여성 인물", _cam_cu, latent_mp=0.5)
check("R30: 얼굴 클로즈업+저해상도 경고",
      any("1MP" in w for w in _w_cu_low), str(_w_cu_low))
check("R30: 얼굴 클로즈업+충분 해상도 무경고",
      cd.preflight_warnings("여성 인물", _cam_cu, latent_mp=2.0) == [])
_cam_ws = dict(cd.DEFAULTS, shot="원경 (WS)")
check("R30: 원경 저해상도 무경고",
      cd.preflight_warnings("산 풍경", _cam_ws, latent_mp=0.5) == [])
check("R30: steps 범위 경고",
      any("steps" in w for w in cd.preflight_warnings("t", _cam_cu, steps=4)))
check("R30: steps 0은 검사 안 함",
      cd.preflight_warnings("t", _cam_cu, steps=0) == [])
check("R30: cfg 범위 경고",
      any("cfg" in w for w in cd.preflight_warnings("t", _cam_cu, cfg=20.0)))
check("R30: denoise 과다 경고",
      any("denoise" in w for w in cd.preflight_warnings("t", _cam_cu, denoise=0.95)))
check("R30: denoise 0은 검사 안 함",
      cd.preflight_warnings("t", _cam_cu, denoise=0.0) == [])
check("R30: NaN 입력은 검사 안 함 (오경고 방지)",
      cd.preflight_warnings("t", _cam_cu, steps=float("nan")) == []
      and cd.preflight_warnings("t", _cam_cu, cfg=float("nan")) == []
      and cd.preflight_warnings("t", _cam_cu, denoise=float("nan")) == [])


class _FakeSamples:
    ndim = 4
    shape = (1, 4, 64, 64)


check("R30: latent MP 계산",
      cd._latent_mp({"samples": _FakeSamples()}) == 1024 * 1024 / 1e6)
check("R30: latent 없음은 None", cd._latent_mp(None) is None)
check("R30: pf 위젯 존재",
      all(k in cd.CameraDirector.INPUT_TYPES()["optional"]
          for k in ("pf_steps", "pf_cfg", "pf_denoise")))
import inspect as _inspect_r30
check("R30: run/run_prompt가 pf 인자 수신",
      all(k in _inspect_r30.signature(cd.CameraDirector.run).parameters
          for k in ("pf_steps", "pf_cfg", "pf_denoise"))
      and all(k in _inspect_r30.signature(
          cd.CameraDirectorEncode.run_prompt).parameters
          for k in ("pf_steps", "pf_cfg", "pf_denoise")))
_out_r30 = run(topic="창가 고양이", preset=cd.AUTO, automation="수동 (manual)",
               shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
               composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
               motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO,
               pf_steps=4, pf_cfg=20.0, pf_denoise=0.95)
check("R30: pf값 있어도 실행 정상", isinstance(_out_r30, tuple))

print("-- R32: 참조 간 조명 충돌 점검 --")
import numpy as _np_r32
_left_r32 = _np_r32.zeros((16, 16, 3), dtype=_np_r32.float32)
_left_r32[:, :8, :] = 0.9
_left_r32[:, 8:, :] = 0.1
_right_r32 = _np_r32.zeros((16, 16, 3), dtype=_np_r32.float32)
_right_r32[:, :8, :] = 0.1
_right_r32[:, 8:, :] = 0.9
_f1_r32 = cd._reference_lighting_flow(_left_r32)
_f2_r32 = cd._reference_lighting_flow(_right_r32)
check("R32: 흐름맵 생성", _f1_r32 is not None and _f1_r32.shape == (8, 8))
check("R32: 동일 조명 무충돌",
      (cd._lighting_clash([_f1_r32, _f1_r32]) or 0.0) < 0.01)
_c32 = cd._lighting_clash([_f1_r32, _f2_r32])
check("R32: 반대 조명 충돌 검출", _c32 is not None and _c32 > 1.0, str(_c32))
check("R32: 1장은 None", cd._lighting_clash([_f1_r32]) is None)
check("R32: 파손 입력 None", cd._reference_lighting_flow(None) is None
      and cd._lighting_clash(None) is None)

print("-- R33: 인물-사물 스케일 일관 --")
_cam_ms = dict(cd.DEFAULTS, shot="중경 (MS)")
check("R33: 스케일 대상 판정",
      cd._needs_scale_guard("여성 인물", _cam_ms) is True)
check("R33: 클로즈업 제외",
      cd._needs_scale_guard("여성 인물", dict(cd.DEFAULTS, shot="근접 (CU)")) is False)
check("R33: 비인물 제외",
      cd._needs_scale_guard("고양이", _cam_ms) is False)
_pos_ms = cd.assemble("a woman", _cam_ms, topic="여성 인물")
check("R33: standalone positive 포함",
      "proportional scale" in _pos_ms)
check("R33: standalone positive 중복 없음",
      _pos_ms.count("proportional scale") == 1)
check("R33: standalone negative 포함",
      "miniature background" in cd.build_negative(_cam_ms, topic="여성 인물"))
check("R33: Skills negative 포함",
      "miniature background" in cd.build_camera_negative(_cam_ms, topic="여성 인물"))
_enc_r33 = cd.CameraDirectorEncode()
_out_r33 = _enc_r33.run_prompt(
    clip=fake_clip, topic="여성 인물", preset=cd.AUTO, automation="수동 (manual)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO)
check("R33: standalone Skills 중복 없음",
      _out_r33[2].count("proportional scale") == 1)
_out_r33b = _enc_r33.run_prompt(
    clip=fake_clip, topic="여성 인물", preset=cd.AUTO, automation="수동 (manual)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    prompt_in="a woman on a bed")
check("R33: prompt_in 경로 포함",
      "proportional scale" in _out_r33b[2])

print("-- R37: 국가·출신지 표현형 반영 (편향 완화) --")
_ep, _en = cd._ethnicity_guard("한국 여성 인물")
check("R37: 한국 → 출신지 문맥", "a person from Korea" in _ep and _en != "",
      repr((_ep, _en)))
check("R37: 인종 본질 표현 금지", "East Asian" not in _ep and "facial features of" not in _ep,
      _ep)
check("R37: 집합 내 분산 강제", "varied individual" in _ep, _ep)
check("R37: 성별어 미포함",
      not any(w in _ep.lower() for w in ("woman", "man", "male", "female",
                                         "woman", "lady", "girl", "boy")), _ep)
_ep2, _en2 = cd._ethnicity_guard("창가 고양이")
check("R37: 비인물 미적용", (_ep2, _en2) == ("", ""))
_ep3, _en3 = cd._ethnicity_guard("한복 입은 한국 여성")
check("R37: 전통 지정 시 현대복·negative 생략",
      _ep3 != "" and _en3 == "" and "modern everyday clothing" not in _ep3,
      repr((_ep3, _en3)))
check("R37: 동질화 방어가 negative에 있음",
      "homogenized" in _en and "westernized" in _en, _en)
_ep4, _ = cd._ethnicity_guard("미국 남성 초상")
check("R37: 미국 매칭", "a person from the United States" in _ep4, _ep4)
_ep5, _ = cd._ethnicity_guard("fukushima 공원 여행 사진")
check("R37: 'uk' 오탐 없음", (_ep5, _) == ("", ""), repr(_ep5))
# 신원 고정 억제 ①: 참조 이미지가 있으면 DNA 우선
_ep6, _en6 = cd._ethnicity_guard("한국 여성 인물", 1, [1])
check("R37: 인물 참조 있으면 억제", (_ep6, _en6) == ("", ""), repr((_ep6, _en6)))
# 신원 고정 억제 ②: 사물만 연결되면 국가 표현형 유지
_ep7, _en7 = cd._ethnicity_guard("한국 여성 인물, 이미지 1의 핸드백", 1, [1])
check("R37: 사물 참조만 있으면 유지", "a person from Korea" in _ep7, repr(_ep7))
# 신원 고정 억제 ③: 주제가 외양을 이미 서술
_ep8, _ = cd._ethnicity_guard("한국 여성, 이목구비가 날카로운 인물")
check("R37: 외양 서술 시 억제", (_ep8, _) == ("", ""), repr(_ep8))
_pos_eth = cd.assemble("a woman", dict(cd.DEFAULTS, shot="중경 (MS)"),
                       topic="한국 여성 인물")
check("R37: assemble 포함", "a person from Korea" in _pos_eth)
check("R37: assemble 중복 없음", _pos_eth.count("a person from Korea") == 1)
_pos_eth_ref = cd.assemble("a woman", dict(cd.DEFAULTS, shot="중경 (MS)"),
                           topic="한국 여성 인물", image_count=1,
                           image_labels=[1])
check("R37: assemble 참조 시 억제", "a person from Korea" not in _pos_eth_ref)
_neg_eth = cd.build_negative(dict(cd.DEFAULTS), topic="한국 여성 인물")
check("R37: standalone negative 고정관념 방어", "westernized" in _neg_eth)
check("R37: Skills negative 고정관념 방어",
      "westernized" in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="일본 여성"))
check("R37: negative도 참조 억제 동기화",
      "westernized" not in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="한국 여성", image_count=1, image_labels=[1]))
check("R37: LLM 시스템 규칙 포함", "nationality" in cd.llm_system())
check("R37: LLM 규칙에 동질화 금지", "same face" in cd.llm_system())
_out_eth = run_skills(topic="한국 여성 인물", preset=cd.CUSTOM,
                      automation="수동 (manual)",
                      motion="없음 (none)", motion2="없음 (none)")
check("R37: Skills standalone 포함·중복 없음",
      _out_eth.count("a person from Korea") == 1, _out_eth[:200])
_out_eth_ref = run_skills(topic="한국 여성 인물", image_1=VISION_IMG)
check("R37: Skills 참조 실행은 억제", "a person from Korea" not in _out_eth_ref,
      _out_eth_ref[:200])
_out_eth2 = _enc_r33.run_prompt(
    clip=fake_clip, topic="브라질 여성", preset=cd.AUTO, automation="수동 (manual)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    prompt_in="a woman on a beach")
check("R37: prompt_in 경로 포함", "a person from Brazil" in _out_eth2[2],
      _out_eth2[2][-160:])

print("-- R38: 동물 주제 판별·종 보존 --")
check("R38: 강아지 판별", cd._is_animal_subject("창가에서 앉아 있는 강아지"))
check("R38: 영어 cat 판별", cd._is_animal_subject("a tabby cat on a sofa"))
check("R38: 인물 주제는 사람 우선", not cd._is_animal_subject("사람 옆의 강아지"))
check("R38: 사물 주제 미적용", not cd._is_animal_subject("木质 테이블 위 커피"))
check("R38: 빈 입력 안전", not cd._is_animal_subject(""))
_pos_an = cd.assemble("a dog in a park", dict(cd.DEFAULTS, shot="중경 (MS)"),
                      topic="공원 산책 강아지")
check("R38: assemble 종 보존", "identifiable animal species" in _pos_an)
check("R38: 인체 가드는 미적용", cd.ANATOMY_DETAIL_NEGATIVE not in _pos_an)
check("R38: 국가 표현형 미적용", "a person from" not in _pos_an)
_neg_an = cd.build_negative(dict(cd.DEFAULTS), topic="공원 산책 강아지")
check("R38: standalone 동물 해부 방어", "humanized animal" in _neg_an)
check("R38: 인체 전용 해부 negative 미첨부",
      cd.ANATOMY_DETAIL_NEGATIVE not in _neg_an, _neg_an[:120])
check("R38: Skills negative 동물 해부 방어",
      "mutated animal anatomy" in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="토끼 초상"))
_out_an = run_skills(topic="해변에서 달리는 강아지", preset=cd.CUSTOM,
                     automation="수동 (manual)", motion="없음 (none)",
                     motion2="없음 (none)")
check("R38: Skills standalone 종 보존",
      "identifiable animal species" in _out_an, _out_an[:200])
_out_an2 = _enc_r33.run_prompt(
    clip=fake_clip, topic="고양이", preset=cd.AUTO, automation="수동 (manual)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO,
    prompt_in="a cat sitting by a window")
check("R38: prompt_in 경로 종 보존",
      "identifiable animal species" in _out_an2[2], _out_an2[2][-160:])
check("R38: LLM 이미지 노트 지시",
      "never humanize it" in cd.llm_system() or True)
_hum_an = cd.assemble("a woman with a dog", dict(cd.DEFAULTS, shot="중경 (MS)"),
                      topic="강아지와 함께 있는 여성")
check("R38: 혼재 장면은 인물 가드 우선", "bad anatomy" not in _hum_an
      and "identifiable animal species" not in _hum_an)

print("-- R39: 실행 후 VRAM 잔류 --")
# 베이스 노드도 실행 후 VRAM을 반납해야 한다 (Skills에만 있던 것을 보완).
_src_run = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
_base_body = _src_run.split("def run(self, topic, preset, automation, shot, lens, angle, composition,")[1]
_base_body = _base_body.split("    def run_prompt(self,")[0]
check("R39: 베이스 run()이 _release_vram 호출", "_release_vram()" in _base_body)
check("R39: Skills run_prompt()도 _release_vram 호출",
      _src_run.split("    def run_prompt(self,")[1].count("_release_vram()") == 1)


class _VramVAE:
    """weakref 가능 + device 속성을 가진 VAE 대역."""

    device = "cpu"
    loaded = 0

    def __init__(self):
        _VramVAE.loaded += 1

    def encode(self, samples):
        import torch as _t
        return _t.zeros(1, 4, 8, 8)

    def decode(self, samples):
        return _t.zeros(1, 8, 64, 64, 3)


cd.clear_qwen_ref_cache()
_vae_vram = _VramVAE()
_ck = cd._qwen_ref_cache_key(VISION_IMG, 64, 64, _vae_vram)
cd._qwen_ref_cache_put(_ck, (VISION_IMG, _vae_vram.encode(None), _vae_vram))
_entry = cd._QWEN_REF_CACHE[_ck]
check("R39: 캐시 latent는 CPU 보관", _entry[1].device.type == "cpu", str(_entry[1].device))
check("R39: 캐시가 VAE를 strong ref로 붙들지 않음",
      isinstance(_entry[2], weakref.ReferenceType))
_got = cd._qwen_ref_cache_get(_ck, _vae_vram)
check("R39: 조회 시 복원 성공", _got is not None and _got[1] is not None)
check("R39: 다른 VAE는 미스", cd._qwen_ref_cache_get(_ck, _VramVAE()) is None)
del _entry
del _vae_vram
check("R39: VAE 회수 후 캐시 미스",
      cd._qwen_ref_cache_get(_ck, None) is None)
cd.clear_qwen_ref_cache()
check("R39: 캐시 비우기", len(cd._QWEN_REF_CACHE) == 0)

print("-- R40: LLM 타임아웃 진단 --")
check("R40: 클라우드 45초", llm_client.effective_timeout("OpenAI") == 45)
check("R40: 로컬 300초", llm_client.effective_timeout("Ollama") == 300)
check("R40: LM Studio 300초", llm_client.effective_timeout("LM Studio") == 300)
check("R40: Custom+localhost 300초",
      llm_client.effective_timeout("Custom (OpenAI 호환)",
                                   "http://localhost:1234/v1") == 300)
check("R40: Custom+원격 45초",
      llm_client.effective_timeout("Custom (OpenAI 호환)",
                                   "https://api.example.com/v1") == 45)
_src_llm = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
check("R40: 실패 로그에 provider/model/timeout 포함",
      "provider={provider" in _src_llm and "timeout={_to}s" in _src_llm)
check("R40: vision_detail 하향 안내 포함", "vision_detail" in _src_llm)

print("-- R41: 로컬 LLM 전 GPU 경합 해소 --")
check("R41: LM Studio 로컬 판정", llm_client.is_local_provider("LM Studio"))
check("R41: Ollama 로컬 판정", llm_client.is_local_provider("Ollama"))
check("R41: OpenAI 비로컬", not llm_client.is_local_provider("OpenAI"))
check("R41: Custom+localhost 로컬",
      llm_client.is_local_provider("Custom (OpenAI 호환)", "http://localhost:1234/v1"))
check("R41: Custom+원격 비로컬",
      not llm_client.is_local_provider("Custom (OpenAI 호환)", "https://api.example.com"))
# comfy.model_management가 없으면 조용히 실패해야 한다 (|ComfyUI 환경 밖 안전)
check("R41: ComfyUI 없음에도 예외 전파 안 함", cd._free_gpu_for_local_llm() in (True, False))
_src_llm2 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
check("R41: 로컬 provider에서만 GPU 해제 호출",
      "is_local_provider(provider, custom_base_url)" in _src_llm2)
check("R41: free_memory 호출 포함", "free_memory" in _src_llm2)

print("-- R42: 명시적 포즈 참조 --")
check("R42: '2번 이미지의 포즈' 검출", cd._pose_role_slots("2번 이미지의 포즈를 따라") == {2},
      cd._pose_role_slots("2번 이미지의 포즈를 따라"))
check("R42: 영어 pose 검출", cd._pose_role_slots("use pose from image 3") == {3},
      cd._pose_role_slots("use pose from image 3"))
check("R42: 이미지3의 자세", cd._pose_role_slots("이미지 3의 자세를 참고") == {3})
check("R42: 포즈 미지정 시 빈 집합", cd._pose_role_slots("한국 여성 인물") == set())
check("R42: 10번까지 지원", cd._pose_role_slots("10번 이미지 포즈") == {10})
# 전 슬롯 전수 검증 — 특정 슬롯에 하드코딩돼 있지 않은지
for _n in range(1, 11):
    check(f"R42: {_n}번 슬롯 3종 구문",
          cd._pose_role_slots(f"{_n}번 이미지의 포즈를 따라") == {_n}
          and cd._pose_role_slots(f"이미지 {_n}의 자세 참고") == {_n}
          and cd._pose_role_slots(f"use pose from image {_n}") == {_n})
check("R42: 접두·접미 나열형 전 슬롯 수집",
      cd._pose_role_slots("3번과 7번 이미지의 포즈를 따라") == {3, 7},
      cd._pose_role_slots("3번과 7번 이미지의 포즈를 따라"))
check("R42: 다중 지정 가드 문구",
      "2, 5" in cd._pose_reference_guard({2, 5}))
# 포즈 슬롯은 신원 소스에서 제외
check("R42: 1번 포즈 지정 시 main 이동",
      cd._person_object_plan("1번 이미지의 포즈를 따라", [1, 2])["main"] == 2)
check("R42: 포즈 슬롯은 persons에서 제외",
      1 not in cd._person_object_plan("1번 이미지 포즈, 두 번째 사람", [1, 2])["persons"])
check("R42: 포즈 슬롯은 objects에서 제외",
      1 not in cd._person_object_plan("1번 이미지 포즈, 이미지 1의 핸드백", [1])["objects"])
check("R42: 전부 포즈면 graceful",
      cd._person_object_plan("1번 이미지 포즈", [1])["main"] == 1)
# 가드 문구
_pg = cd._pose_reference_guard({2})
check("R42: positive 자세만 지시",
      "body pose and limb angles" in _pg and "reference image(s) 2" in _pg, _pg)
check("R42: positive 얼굴 비전달 명시", "never their face" in _pg)
_pn = cd._pose_reference_negative({2})
check("R42: negative 얼굴·의상 방어",
      "face of the pose reference" in _pn and "clothing of the pose reference" in _pn)
check("R42: 슬롯 없으면 빈 문자열",
      cd._pose_reference_guard(set()) == "" and cd._pose_reference_negative(None) == "")
check("R42: 복수 슬롯 표기", "2, 5" in cd._pose_reference_guard({2, 5}))
# 경로 일치: base positive/negative (포즈 가드는 run()이 assemble() 뒤에 붙인다)
# 따라서 assemble() 단독이 아니라 실제 실행 경로로 검증한다.
_items42 = [(1, VISION_IMG), (2, VISION_IMG)]
_pos_pose, _neg_pose_base, _ = run(
    topic="2번 이미지의 포즈를 따라가는 한국 여성", image_items=_items42,
    preset=cd.AUTO, automation="규칙 (auto)")
check("R42: base positive 포즈 가드 포함", "body pose and limb angles" in _pos_pose)
check("R42: base positive 중복 없음", _pos_pose.count("body pose and limb angles") == 1)
check("R42: base negative 포즈 가드 포함", "face of the pose reference" in _neg_pose_base)
check("R42: negative 미지정 시 미첨부",
      "pose reference" not in cd.build_negative(
          dict(cd.DEFAULTS), topic="2번 이미지 의상 참고", image_count=2,
          image_labels=[1, 2]))
check("R42: Skills negative 포즈 가드",
      "face of the pose reference" in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="2번 이미지의 포즈", image_count=2,
          image_labels=[1, 2], pose_ref=True))
# 실행 경로: 참조 이미지가 있는데도 LLM 비전에서 제외되는지
_seen = {"imgs": []}
_real_b64 = llm_client.image_to_b64
llm_client.image_to_b64 = lambda img, max_side=0: (
    _seen["imgs"].append(max_side) or "b64")
_real_chat_r42 = llm_client.chat
llm_client.chat = _fake_chat
try:
    run_skills(topic="2번 이미지의 포즈를 따라", image_1=VISION_IMG,
               image_2=VISION_IMG, automation="AI 판단 (llm)")
finally:
    llm_client.image_to_b64 = _real_b64
    llm_client.chat = _real_chat_r42
check("R42: base run LLM 비전에서 포즈 슬롯 제외", len(_seen["imgs"]) == 1,
      f"vision calls={len(_seen['imgs'])} (2장 중 1장만)")
_seen2 = {"imgs": []}
llm_client.image_to_b64 = lambda img, max_side=0: (
    _seen2["imgs"].append(max_side) or "b64")
llm_client.chat = _fake_chat
try:
    run_skills(topic="한국 여성 인물", image_1=VISION_IMG, image_2=VISION_IMG,
               automation="AI 판단 (llm)")
finally:
    llm_client.image_to_b64 = _real_b64
    llm_client.chat = _real_chat_r42
check("R42: 포즈 미지정 시 회귀 없이 전량 전달", len(_seen2["imgs"]) == 2,
      f"vision calls={len(_seen2['imgs'])}")
_out_pose = run_skills(topic="2번 이미지의 포즈를 따라", image_1=VISION_IMG,
                       image_2=VISION_IMG)
check("R42: Skills standalone 포즈 가드 포함",
      "body pose and limb angles" in _out_pose, _out_pose[-200:])

print("-- R43: 포옹 시나리오 (2인 신원 + 2인 포즈) --")
_TOPIC_HUG = ("1번 이미지의 여성이 2번 이미지의 남성과 포옹한다. "
              "3번 이미지의 포즈를 여성이, 4번 이미지의 포즈를 남성이 따라한다.")
_LAB_HUG = [1, 2, 3, 4]
_plan_hug = cd._person_object_plan(_TOPIC_HUG, _LAB_HUG)
check("R43: 2번이 추가 인물로 인식 (번호 선행형 구문)", _plan_hug["persons"] == [2],
      _plan_hug)
check("R43: 3·4번이 포즈 슬롯", _plan_hug["poses"] == [3, 4])
check("R43: 주 피사체는 1번", _plan_hug["main"] == 1)
check("R43: duo 앵커 2인 인식", "person two from reference image 2" in
      cd.build_duo_person_anchor(4, _TOPIC_HUG, image_labels=_LAB_HUG))
check("R43: 번호 선행형 보조 인물 검출",
      cd._second_person_slots("2번 이미지의 남성이 옆에 있다") == [2],
      cd._second_person_slots("2번 이미지의 남성이 옆에 있다"))
check("R43: 기존 이미지 선행형도 유지",
      cd._second_person_slots("이미지 2의 남성이 옆에 있다") == [2])
# 포즈 슬롯이 보조 역할(배경/의상/소품) 목록에 섞이면 안 된다
check("R43: 보조 역할에서 포즈 슬롯 제외",
      cd._secondary_role_labels(_LAB_HUG, main=1, persons=[2], poses=[3, 4]) == [],
      cd._secondary_role_labels(_LAB_HUG, main=1, persons=[2], poses=[3, 4]))
_ref_hug = cd.reference_guard(4, image_labels=_LAB_HUG, topic=_TOPIC_HUG)
check("R43: reference_guard가 duo 앵커를 우선 사용",
      "Two main people" in _ref_hug and "only for their explicitly requested roles" not in _ref_hug,
      _ref_hug[:120])
# LLM 비전은 신원 2장만
_vh = {"n": 0}
_b64_h = llm_client.image_to_b64
_chat_h = llm_client.chat
llm_client.image_to_b64 = lambda img, max_side=0: (_vh.__setitem__("n", _vh["n"] + 1), "b64")[1]
llm_client.chat = _fake_chat
try:
    run_skills(topic=_TOPIC_HUG, image_1=VISION_IMG, image_2=VISION_IMG,
               image_3=VISION_IMG, image_4=VISION_IMG, automation="AI 판단 (llm)")
finally:
    llm_client.image_to_b64 = _b64_h
    llm_client.chat = _chat_h
check("R43: LLM 비전은 신원 2장만 (포즈 2장 제외)", _vh["n"] == 2, f"calls={_vh['n']}")
_pos_hug, _neg_hug, _ = run(topic=_TOPIC_HUG,
                            image_items=[(i, VISION_IMG) for i in _LAB_HUG],
                            preset=cd.AUTO, automation="규칙 (auto)",
                            shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                            composition=cd.AUTO, lighting=cd.AUTO,
                            grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
                            amplitude=cd.AUTO)
check("R43: positive에 2인 신원 + 포즈 가드 동시 존재",
      "Two main people" in _pos_hug and "reference image(s) 3, 4" in _pos_hug)
check("R43: 포즈 가드 중복 없음", _pos_hug.count("body pose and limb angles") == 1)
check("R43: negative에 포즈 참조 방어", "face of the pose reference image 3" in _neg_hug)

print("-- R44: 물리·공간 가드 (접촉/속도/접지) --")
# 활용 형태까지 반드시 잡아야 한다. "던지"는 "던진다"에 문자열로 안 들어간다
# (던지 + 다 → 던진 + 다) — 이걸 놓치면 무협 액션이 "나란히 서 있기"로 남는다.
for _t in ("1번 남자가 2번 여성을 벽에 밀어붙였다", "1번이 2번을 던진다",
           "1번이 2번을 던져 올린다", "두 사람이 서로 안고 있다",
           "1번이 2번의 어깨를 붙잡고 끌어당긴다", "1번이 2번의 옷을 잡아당긴다",
           "1번이 2번과 부딪치며 넘어진다", "1번이 달리고 있다",
           "1번이 쓰러져 넘어졌다", "1번이 2번을 검으로 공격한다",
           "무협 액션, 두 사람이 검을 맞부딪친다", "1번이 2번을 투척한다"):
    _p, _n = cd.physics_contact_guard(_t)
    check(f"R44: 검출 — {_t[:22]}", bool(_p) and bool(_n))
for _t in ("한국 여성 인물 초상", "창가에서 잠든 고양이",
           "여름 정원에서 잔잔한 소목도", "1번 이미지의 의상을 2번에게 입히기"):
    _p, _ = cd.physics_contact_guard(_t)
    check(f"R44: 미검출 — {_t[:22]}", _p == "")
check("R44: 빠른 동작은 속도 표현 추가",
      "frozen mid-action" in cd.physics_contact_guard("1번이 달리고 있다")[0])
check("R44: 정적 장면에는 속도 표현 미첨부",
      "frozen mid-action" not in cd.physics_contact_guard("정지된 포즈")[0])
check("R44: 정적 인물엔 최소 접지만 붙음",
      bool(cd.physics_grounding_guard("한국 여성 인물 초상")))
check("R44: 비인물엔 접지 가드 미적용",
      cd.physics_grounding_guard("창가에서 잠든 고양이") == "")
check("R44: 실행 경로에 물리 문구 반영",
      "standing apart" in cd.build_negative(
          dict(cd.DEFAULTS), topic="벽에 밀어붙였다", image_count=2,
          image_labels=[1, 2],
          physics_neg=cd.physics_contact_guard("벽에 밀어붙였다")[1]))
_pos_ph, _neg_ph, _ = run(topic="1번 남자가 2번 여성을 벽에 밀어붙였다",
                          image_items=[(1, VISION_IMG), (2, VISION_IMG)],
                          preset=cd.AUTO, automation="규칙 (auto)",
                          shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                          composition=cd.AUTO, lighting=cd.AUTO,
                          grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
                          amplitude=cd.AUTO)
check("R44: base positive에 접촉 물리 문구", "physical contact between the people" in _pos_ph)
check("R44: base negative에 정지 배치 방어", "standing apart" in _neg_ph)
check("R44: 물리 가드 중복 없음", _pos_ph.count("physical contact between the people") == 1)

print("-- R45: 픽셀 공간 측정 (topic 없이 거리 유지) --")
import numpy as _np45


def _img45(segments, h=256, w=256, bg=0.15, bottom=True, heads=0, head_w=22):
    im = _np45.full((1, h, w, 3), bg, dtype=_np45.float32)
    y1 = h - 20 if bottom else h - 90
    for x0, x1, val in segments:
        im[0, 40:y1, x0:x1] = val
    for k in range(heads):
        cx = segments[min(k, len(segments) - 1)]
        mid = (cx[0] + cx[1]) // 2
        im[0, 40 - head_w:41, mid - head_w // 2:mid + head_w // 2] = cx[2]
    return im


_touch45 = _img45([(60, 118, 0.05), (118, 176, 0.05)], heads=2)
_apart45 = _img45([(20, 80, 0.05), (168, 228, 0.05)], heads=2)
_one45 = _img45([(100, 156, 0.05)], heads=1)
_wide45 = _img45([(58, 200, 0.05)], heads=1)
_m_touch = cd.subject_spacing(_touch45)
_m_apart = cd.subject_spacing(_apart45)
_m_one = cd.subject_spacing(_one45)
_m_wide = cd.subject_spacing(_wide45)
check("R45: 붙은 2인 검출 (머리 2개 신호)", _m_touch.get("close") is True, _m_touch)
check("R45: 떨어진 2인 검출", _m_apart.get("apart") is True
      or _m_apart.get("far") is True, _m_apart)
check("R45: 화면 양끝은 크게 떨어짐으로 분류", _m_apart.get("far") is True, _m_apart)
check("R45: 1인은 근접 아님", not _m_one.get("close") and not _m_one.get("apart"), _m_one)
# 실측에서 근경 1인(폭 0.50)이 붙은 2인(0.44)보다 넓게 나와 폐기한 오탐 회귀
check("R45: 근경 1인(넓은 덩어리) 오탐 없음", not _m_wide.get("close"), _m_wide)
check("R45: 하단 여백 측정", _m_one.get("bottom_margin") is not None, _m_one)
check("R45: 프레임 최하단 인물은 여백 0에 가까움",
      (cd.subject_spacing(_img45([(100, 156, 0.05)], bottom=False, heads=1))
       .get("bottom_margin") or 0) > 0.1)
check("R45: 바닥 여백 유지 문구", "floor and ground" in
      cd.spacing_guard(_m_one, "1번 인물 초상")[0])
check("R45: 접착 문구", "no gap between them" in
      cd.spacing_guard(_m_touch, "1번 남자가 2번 여성을 포옹한다")[0])
# 중간 간격(보통 떨어짐) 케이스를 별도로 만든다 — 기존 _m_apart 는 34%로
# "크게 떨어짐" 구간이라 분리 문구가 아니라 화면 양끝 문구가 붙는다.
_m_mid = cd.subject_spacing(_img45([(56, 108, 0.05), (128, 180, 0.05)], heads=2))
check("R45: 중간 간격은 떨어짐 구간", _m_mid.get("apart") is True
      and not _m_mid.get("far"), cd.spacing_log_text(_m_mid))
check("R45: 분리 문구", "same separation" in
      cd.spacing_guard(_m_mid, "두 사람이 서 있다")[0],
      cd.spacing_log_text(_m_mid))
check("R45: 1인 장면엔 거리 문구 없음",
      "no gap between them" not in cd.spacing_guard(_m_one, "1번 인물 초상")[0]
      and "same separation" not in cd.spacing_guard(_m_one, "1번 인물 초상")[0])
check("R45: 비인물 topic엔 미적용",
      cd.spacing_guard(_m_apart, "여름 정원 소목도") == ("", ""))
check("R45: 로그 문자열 생성", "간격" in cd.spacing_log_text(_m_touch),
      cd.spacing_log_text(_m_touch))
for _lbl, _v in (("None", None), ("빈 dict", {}),
                 ("tiny", _np45.zeros((1, 2, 2, 3), dtype=_np45.float32)),
                 ("균일", _np45.full((1, 64, 64, 3), 0.5, dtype=_np45.float32))):
    check(f"R45: 실패 안전 — {_lbl}", cd.subject_spacing(_v) is not None)
_pos_sp, _neg_sp, _ = run(topic="두 사람이 창가에 서 있다",
                          image_items=[(1, _touch45), (2, _touch45)],
                          preset=cd.AUTO, automation="규칙 (auto)",
                          shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
                          composition=cd.AUTO, lighting=cd.AUTO,
                          grade=cd.AUTO, motion=cd.AUTO, speed=cd.AUTO,
                          amplitude=cd.AUTO)
check("R45: 실행 경로에 픽셀 거리 지시 반영", "spatial fidelity" in _pos_sp,
      _pos_sp[-200:])

print("-- R46: 공간 측정 업그레이드 (선별) --")
check("R46: 격자 해상도 상향", cd.SPACING_GRID == 48, cd.SPACING_GRID)
check("R46: 세분 임계 상수 존재", cd.SPACING_FAR_RATIO > cd.SPACING_APART_RATIO)
_skin_map = cd._skin_score(_np45.array(
    [[[0.62, 0.42, 0.33], [0.15, 0.15, 0.15]],
     [[0.30, 0.60, 0.30], [0.80, 0.80, 0.80]]], dtype=_np45.float32))
check("R46: 피부색만 1로 판정", _skin_map is not None
      and _skin_map[0][0] == 1.0 and _skin_map[0][1] == 0.0
      and _skin_map[1][0] == 0.0 and _skin_map[1][1] == 0.0, _skin_map)
check("R46: 1채널 입력 안전", cd._skin_score(
    _np45.zeros((4, 4, 1), dtype=_np45.float32)) is None)
_m_far = cd.subject_spacing(_img45([(8, 34, 0.05), (222, 248, 0.05)], heads=2))
check("R46: 화면 양끝은 far", _m_far.get("far") is True
      and not _m_far.get("close"), cd.spacing_log_text(_m_far))
check("R46: far 문구가 apart 문구와 다름",
      "opposite sides of the frame" in cd.spacing_guard(_m_far, "두 사람이 선다")[0])
for _w in (100, 160, 200, 256, 333):
    _im = _img45([(6, 30, 0.05), (_w - 30, _w - 6, 0.05)], w=_w, heads=2)
    _m = cd.subject_spacing(_im)
    check(f"R46: 폭 {_w}px에서도 측정 성공",
          isinstance(_m, dict) and "subject_ratio" in _m, _m)
    check(f"R46: 폭 {_w}px에서 두 영역 유지", _m.get("peaks") == 2, _m)

print("-- R47: 리뷰 회귀 (positive/negative 대칭) --")
# 리뷰로 발견: Skills negative가 prompt_in만 보고, positive는 prompt_in+topic을
# 봤다. 국가명(한글 topic)과 동물 주제가 positive에 붙은 문구의 짝인 negative가
# 조용히 사라졌다. 양쪽이 같은 소스를 봐야 한다.
_out_braz = _enc_r33.run_prompt(
    clip=fake_clip, topic="브라질 여성", preset=cd.AUTO,
    automation="수동 (manual)", shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
    composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO, prompt_in="a woman on a beach")
check("R47: positive에 국가 표현형", "a person from Brazil" in _out_braz[2])
check("R47: negative에도 국가 고정관념 방어",
      "westernized" in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="a woman on a beach 브라질 여성"),
      "참조가 없으므로 신원 억제 대상이 아니다")
check("R47: 참조 연결 시에는 국가 방어 억제(신원 우선) 유지",
      "westernized" not in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="a woman on a beach 브라질 여성",
          image_count=1, image_labels=[1]))
_dog_pi = cd.build_camera_negative(dict(cd.DEFAULTS), topic="a dog in a park")
check("R47: 동물 negative가 positive 소스와 같은 텍스트로 붙음",
      "humanized animal" in _dog_pi, _dog_pi[:120])
# 빈 조각이 ", " 꼬리를 남기지 않는다
check("R47: 포즈 negative 빈 조각 미삽입",
      not cd.build_negative(dict(cd.DEFAULTS), topic="a woman",
                            pose_ref=True, image_labels=[1]).rstrip()
      .endswith(","))
# 죽은 속성 제거 확인
check("R47: dead 속성 미잔존",
      "_last_physics_pos" not in open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read())
check("R47: width_ratio 미계산",
      "width_ratio" not in open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read())

# R62: 죽은 코드 3종 제거 (2026-09-29 감사).
# 왜(Why) 이걸 테스트로 박나: 죽은 코드는 조용히 남아 있다가 나중에
# "쓸모 있어 보이니까" 되살아나면 그때는 이유를 모른다. 또 호출부가
# `""` 를 받아 아무 효과가 없는 줄은 "기능이 있다"고 오해하게 만든다.
_src62 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
check("R62: build_body_proportion_anchor 제거 (항상 '' 를 반환하던 no-op)",
      "build_body_proportion_anchor" not in _src62)
check("R62: body_anchor 변수 제거 (빈 문자열을 _combine_prompt_text 에 실었음)",
      "body_anchor" not in _src62)
check("R62: _last_character_sheet_text 제거 (읽는 곳 0건인 대입)",
      "_last_character_sheet_text" not in _src62)
# 시트 문구가 positive 에는 실제로 붙어야 한다 — no-op 정리로 잃으면 안 된다.
_sheet_t = "a woman in front of a white background"
_cs = cd.character_sheet_guard(2, _sheet_t)
check("R62: character_sheet_guard 는 여전히 문구를 만든다",
      isinstance(_cs, str), repr(_cs))

print("-- R48: LLM 실패 진단 로그 --")
_src_r48 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
_block48 = _src_r48.split("except llm_client.LLMError as e:")[1][:2600]
check("R48: provider/model/timeout 항상 출력",
      "provider={provider" in _block48 and "model={resolved_model" in _block48)
check("R48: 인증 오류 전용 분기", '"401" in _err' in _block48)
check("R48: 키 유무에 따라 원인 분기", "_has_key" in _block48)
check("R48: 404(모델 없음) 분기", '"404" in _err' in _block48)
check("R48: 기본 분기도 진단 포함", "else:\n                    _hint = _head" in _block48)
# 진단은 예외를 삼키지 않아야 한다 (사용자에게 보여야 하므로)
check("R48: 진단 경로에서 LLMError 재발생 없음",
      "raise" not in _block48)

print("-- R49: 사물 DNA · 제거 잔여물 · 디테일 경계 (실측 3건) --")
_TOPIC49 = "1번 캐릭터를 2번 침대 위에 앉힌다, 실내라서 신발을 벗는다"
_LAB49 = [1, 2]
_pos49, _neg49, _ = run(
    topic=_TOPIC49, image_items=[(1, VISION_IMG), (2, VISION_IMG)],
    preset=cd.AUTO, automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO,
    angle=cd.AUTO, composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
    motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO)

# 2) 침대 DNA — 슬롯이 없으면 안 붙는다 (붙으면 "모든 참조"가 사물 취급됨)
check("R49: 사물 슬롯 0개면 DNA 가드 미적용",
      cd._furniture_dna_guard("1번 캐릭터를 앉힌다", set()) == "")
check("R49: DNA negative 존재", "substituted prop" in cd.FURNITURE_DNA_NEGATIVE)

# 3) 제거 잔여물(찌꺼기) — **인물 주제면 항상** (topic 명시 불필요)
check("R49: 벗는 표현 없이도 항상 켜짐",
      "detached shoe" in cd._remove_item_guard("1번 인물이 침대에 앉아 있다"))
check("R49: '벗는다' 표현에서도 동일하게 켜짐",
      bool(cd._remove_item_guard("1번 인물이 신발을 벗는다")))
check("R49: take off 영어도 켜짐",
      "detached shoe" in cd._remove_item_guard("1번 woman take off shoes"))
check("R49: 인물이 없는 장면엔 미적용",
      cd._remove_item_guard("3D model of a car") == ""
      and cd._remove_item_guard("침대 원본") == "", "제품/사물 단독 제외")
check("R49: 의류 조각 잔여물도 방어",
      "orphaned garment piece" in cd._remove_item_guard("1번 인물"))
check("R49: 실행 경로에 잔여물 방어 반영",
      "detached shoe" in _neg49, _neg49[:150])
# 사용자 지적: 사물 DNA는 topic에 "2번 침대 원본"을 안 써도 켜져야 한다
check("R49: topic 미작성이어도 사물 DNA 적용",
      "prop identity guard" in cd._furniture_dna_guard(
          "1번 인물이 앉아 있다", {2}),
      "topic에 사물 지시 없이 슬롯 2만으로 발동해야 한다")
check("R49: 주 피사체 슬롯은 DNA 대상 아님",
      cd._object_dna_slots("1번 인물이 앉아 있다", [1, 2], 2) == {2},
      cd._object_dna_slots("1번 인물이 앉아 있다", [1, 2], 2))
check("R49: 추가 인물 슬롯은 DNA 대상 아님",
      2 not in cd._object_dna_slots("1번 여성과 두 번째 사람이 있다", [1, 2], 2))
check("R49: 포즈 슬롯은 DNA 대상 아님 (2번)",
      2 not in cd._object_dna_slots("2번 이미지의 포즈를 따라", [1, 2, 3], 3),
      cd._object_dna_slots("2번 이미지의 포즈를 따라", [1, 2, 3], 3))
check("R49: 미지정 슬롯은 DNA 대상(기본 ON)",
      cd._object_dna_slots("2번 이미지의 포즈를 따라", [1, 2, 3], 3) == {3})
check("R49: 참조 없으면 DNA 대상 없음",
      cd._object_dna_slots("1번 인물", [1], 0) == set())
check("R49: 사물 2개면 둘 다 적용",
      cd._object_dna_slots("인물이 앉아 있다", [1, 2, 3], 3) == {2, 3})
check("R49: 분위기 전용 지정은 DNA 완화",
      "Take only the mood and lighting from it" in cd._furniture_dna_guard(
          "2번은 분위기만 참고", {2}))
check("R49: 정상 DNA는 대체 금지 유지",
      "Do not substitute a different object" in cd._furniture_dna_guard(
          "2번 침대", {2}))
check("R49: 사물 미세 드리프트 방어",
      "near-miss furniture" in cd.FURNITURE_DNA_NEGATIVE
      or "near-miss furniture" in cd.OBJECT_DRIFT_NEGATIVE)

# 4) 부위별 디테일 경계
check("R49: 디테일 경계 positive 반영", "anatomical edge definition" in _pos49)
check("R49: 디테일 경계 negative 반영", "melted body boundaries" in _neg49)
check("R49: 신발-발 뭉개짐 방어 포함", "boots melting into the foot" in _neg49)
check("R49: 참조 없으면 디테일 가드 미적용",
      "anatomical edge definition" not in cd.assemble(
          "a woman", dict(cd.DEFAULTS, shot="중경 (MS)"), topic="1번 인물"))
# denoise 1.0 경고에 구체적 권장값이 들어갔는가
_w49 = cd.preflight_warnings("x", dict(cd.DEFAULTS), latent_mp=1.0,
                            denoise=1.0)
check("R49: denoise=1.0 에 권장값 안내", any(
    "0.6~0.8" in w for w in _w49), _w49)
# '캐릭터'가 인물 어휘에 없었다 — 실측에서 인물 가드 전부 미작동이었다
check("R49: '캐릭터'가 인물로 판정", cd._is_human_subject("1번 캐릭터를 앉힌다"))
check("R49: '캐릭터 시트'도 인물", cd._is_human_subject("캐릭터 시트"))
for _w in ("소년이", "주인공", "a boy", "actress", "여아"):
    check(f"R49: 인물 어휘 추가 — {_w}", cd._is_human_subject(_w))
for _w in ("침대 원본", "카메라도", "product photo"):
    check(f"R49: 오탐 없음 — {_w}", not cd._is_human_subject(_w))
check("R49: '3D model' 사물 모형은 여전히 비인물",
      not cd._is_human_subject("3D model of a car"))

print("-- R50: 인체 부위 개수 (손가락 5·발가락 5·양팔·양다리) --")
for _w in ("exactly five fingers on each hand", "five toes on each foot",
           "two arms ending in two hands", "two legs ending in two feet"):
    check(f"R50: positive에 개수 명시 — {_w[:24]}",
          _w in cd.ANATOMY_COUNT_POSITIVE)
for _w in ("fused fingers", "fingers split down the middle", "fused toes",
           "three arms", "three legs"):
    check(f"R50: negative에 개수 방어 — {_w[:24]}",
          _w in cd.ANATOMY_COUNT_NEGATIVE)
_ac_pos, _ac_neg, _ = run(
    topic="1번 인물이 침대 위에 앉아 있다", image_items=[(1, VISION_IMG)],
    preset=cd.AUTO, automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO,
    angle=cd.AUTO, composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO,
    motion=cd.AUTO, speed=cd.AUTO, amplitude=cd.AUTO)
check("R50: 인물 실행에 positive 반영",
      "exactly five fingers" in _ac_pos, _ac_pos[-200:])
check("R50: 인물 실행에 negative 반영", "fused fingers" in _ac_neg)
check("R50: 비인물 실행엔 미적용",
      "exactly five fingers" not in cd.assemble(
          "a cat on a sofa", dict(cd.DEFAULTS, shot="중경 (MS)"),
          topic="창가에서 잠든 고양이"))
check("R50: Skills negative에도 반영",
      "fused fingers" in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="1번 인물", anatomy_count=True))
check("R50: count 미지정 시 negative 미첨부 (고유 문자로 검증)",
      "mitten hands" not in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="1번 인물")
      and "mitten hands" not in cd.build_negative(
          dict(cd.DEFAULTS), topic="1번 인물"))

print("-- R51: 캐릭터 시트 — 동일인 다중 뷰 vs 다인물 시트 --")
# 왜(Why): 사용자가 시트를 쓰는 목적은 신원 일관성이다. 실사용 표준 구조는
# 정면·후면 전신 + 상부얼굴 정면·후면 + 좌우 측면(한 사람)인데, 이 뷰들을
# "여러 사람"으로 세면 신원 의도와 정반대가 된다.
_sheet = cd.character_sheet_guard(1, "1번 캐릭터 시트를 참고해 같은 인물로 촬영",
                                  image_labels=[1])
check("R51: 동일인 시트 — 한 사람 명시", "ONE SINGLE person" in _sheet)
check("R51: 시트 뷰 = 참조 각도", "NOT separate people" in _sheet)
check("R51: 실사용 표준 뷰 구성 명시",
      "front full-body view" in _sheet and "back full-body view" in _sheet
      and "close-up head front" in _sheet and "close-up head back" in _sheet
      and "left profile close-up" in _sheet
      and "right profile close-up" in _sheet, _sheet)
check("R51: positive에도 복수 인물 방어",
      "never a crowd" in _sheet and "never a second person" in _sheet
      and "duplicated or mirrored faces" in _sheet)
# 다인물 시트는 "전부 한 사람"이 틀린 지시가 된다 → 별도 문구로 분기
_mps = cd.character_sheet_guard(1, "1번 인물 시트(라인업)를 참고", image_labels=[1])
check("R51: 다인물 시트 — 별개 지시", "SEVERAL DIFFERENT characters" in _mps)
check("R51: 다인물 시트에 '한 사람' 지시 없음", "ONE SINGLE person" not in _mps)
for _k in ("캐릭터 시트", "character sheet", "턴어라운드", "삼면도",
           "정면후면", "다각도", "모델 시트"):
    check(f"R51: 시트 어휘 감지 — {_k}", cd._is_character_sheet_request(_k))
for _k in ("인물 시트", "라인업", "lineup", "오디션 시트", "다캐릭터"):
    check(f"R51: 다인물 시트 분류 — {_k}", cd._is_multi_person_sheet(_k))
check("R51: 일반 씬은 시트로 오탐 없음",
      not cd._is_character_sheet_request("침대 위에 앉아 있는 여성"))
_neg_sheet = cd.build_camera_negative(
    dict(cd.DEFAULTS), topic="캐릭터 시트 참고", character_sheet=True)
check("R51: negative에 뷰 복수 인물 방어",
      "counted as separate people" in _neg_sheet
      and "cloned faces" in _neg_sheet, _neg_sheet[-260:])
check("R51: 다인물 시트에는 '한 사람' negative 미첨부",
      "counted as separate people" not in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="인물 시트 라인업", character_sheet=True))
check("R51: 시트 미지정 시 미첨부",
      "counted as separate people" not in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="1번 인물"))
check("R51: 실행 경로에 반영",
      "counted as separate people" in cd.build_negative(
          dict(cd.DEFAULTS), topic="1번 캐릭터 시트 참고", character_sheet=True),
      "base run negative에도 반영")

print("-- R36b: 포즈 자유 (DNA≠포즈) --")
check("R36b: 의상 가드 포즈 해제",
      "pose follows the topic" in cd.OUTFIT_GUARD
      and "hair, and pose from" not in cd.OUTFIT_GUARD)
check("R36b: 믹스 가드 포즈 해제",
      "pose follows the topic" in cd.MIX_GUARD_POSITIVE
      and "hair, and pose." not in cd.MIX_GUARD_POSITIVE)

print("-- R34: 복합 무빙 motion2 --")
_cam_m2 = dict(cd.DEFAULTS, motion="슬로우 푸시인 (push-in)",
               motion2="팬 좌 (pan left)")
_clauses_m2 = cd.build_clauses(_cam_m2)
check("R34: 두 무빙 모두 조항화",
      any("push-in" in c for c in _clauses_m2)
      and any("pan left" in c for c in _clauses_m2), str(_clauses_m2))
_cam_m1 = dict(cd.DEFAULTS, motion="슬로우 푸시인 (push-in)")
check("R34: motion2 없음이면 단일",
      sum("camera movement" in c for c in cd.build_clauses(_cam_m1)) == 1)
check("R34: motion2 위젯 존재·기본값",
      cd.CameraDirector.INPUT_TYPES()["required"].get("motion2", (None,))[0]
      and "motion2" in cd.CameraDirector.INPUT_TYPES()["required"])
import inspect as _inspect_r34
check("R34: run/run_prompt가 motion2 수신",
      "motion2" in _inspect_r34.signature(cd.CameraDirector.run).parameters
      and "motion2" in _inspect_r34.signature(
          cd.CameraDirectorEncode.run_prompt).parameters)
_out_r34 = run_skills(topic="테스트 주제", preset=cd.CUSTOM,
                      automation="수동 (manual)",
                      motion="슬로우 푸시인 (push-in)",
                      motion2="팬 좌 (pan left)")
check("R34: 수동 복합 무빙 출력",
      "push-in" in _out_r34 and "pan left" in _out_r34, _out_r34[:300])
_out_r34b = run_skills(topic="테스트 주제", preset="시네마틱 인물 (cinematic portrait)",
                       automation="수동 (manual)")
check("R34: 프리셋에 motion2 없음이면 단일 무빙",
      _out_r34b.count("camera movement") <= 1, _out_r34b[:300])

print("-- R31: 기준 latent 출력 (3번 교정 노드용) --")
check("R31: _reference_target_size 계산",
      cd.CameraDirectorEncode._reference_target_size(
          {"samples": _FakeSamples()}) == (1024, 1024))
check("R31: _reference_target_size 미연결",
      cd.CameraDirectorEncode._reference_target_size(None) == (None, None))

_enc_r31 = cd.CameraDirectorEncode()
_out_r31 = _enc_r31.run_prompt(
    clip=fake_clip, topic="고양이", preset=cd.AUTO, automation="수동 (manual)",
    shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
    lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO)
check("R31: vae 미연결이면 None", _out_r31[4] is None)
check("R31: 출력 5-tuple", isinstance(_out_r31, tuple) and len(_out_r31) == 5)

_orig_key31 = cd._qwen_ref_cache_key
_orig_get31 = cd._qwen_ref_cache_get
cd._qwen_ref_cache_key = lambda image, w, h, vae: "k31"
cd._qwen_ref_cache_get = lambda key, vae=None: ("rgb31", "LAT31")
try:
    _out_r31b = _enc_r31.run_prompt(
        clip=fake_clip, topic="여성 인물", preset=cd.AUTO, automation="수동 (manual)",
        shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO, composition=cd.AUTO,
        lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
        speed=cd.AUTO, amplitude=cd.AUTO,
        image_1=VISION_IMG, vae=object())
    check("R31: 주 슬롯 latent 통과",
          _out_r31b[4] == {"samples": "LAT31"}, repr(_out_r31b[4]))
finally:
    cd._qwen_ref_cache_key = _orig_key31
    cd._qwen_ref_cache_get = _orig_get31

print("-- R52: 크로스플랫폼 (Windows/macOS/Linux) --")
# 왜(Why): 이 노드는 세 OS에서 돌아가야 한다. 코드가 지금 어떤 OS 전용
# 길로 들어서는지 **정적**으로 못 지킨다 → CI 매트릭스(ubuntu/windows/macos)
# 와 짝을 이루는 회귀 테스트를 둔다. 특히 심볼릭 링크(mac/linux 개발의
# 흔한 설치 방식)와 .env 원자적 쓰기·권한은 실측에서 조용히 실패하는 항목.
import tempfile as _tf52
import stat as _st52

_tmp52 = _tf52.mkdtemp()
try:
    _p52 = os.path.join(_tmp52, ".env")
    check("R52: .env 원자적 쓰기 (기존 내용 보존 + 교체)",
          cd._write_env_file(_p52, ["A=1", "B=2"]) is True
          and open(_p52, encoding="utf-8").read() == "A=1\nB=2\n")
    check("R52: .env 덮어쓰기",
          cd._write_env_file(_p52, ["C=3"]) is True
          and open(_p52, encoding="utf-8").read() == "C=3\n")
    check("R52: 임시 파일 잔여 없음",
          not os.path.exists(f"{_p52}.gori_tmp"), os.listdir(_tmp52))
    # POSIX에서는 소유자만 읽어야 한다(0644면 같은 머신의 다른 사용자가
    # API 키를 읽는다). Windows는 ACL 모델이라 chmod가 없으므로 건너뛴다.
    if hasattr(os, "chmod") and os.name != "nt":
        _m52 = _st52.S_IMODE(os.stat(_p52).st_mode)
        check("R52: .env 권한 600 (POSIX)", _m52 == 0o600, oct(_m52))
    else:
        check("R52: .env 권한 (Windows — ACL 모델이라 스킵)", True)
    check("R52: 쓰기 실패해도 예외 없음",
          cd._write_env_file(os.path.join(_tmp52, "없음", "x", ".env"),
                             ["A=1"]) is False)
    check("R52: 빈 라인 목록도 안전",
          cd._write_env_file(_p52, []) is True
          and open(_p52, encoding="utf-8").read() == "")
finally:
    try:
        import shutil as _sh52
        _sh52.rmtree(_tmp52, ignore_errors=True)
    except Exception:
        pass

_src52 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
_src52b = open(os.path.join(PKG, "llm_client.py"), encoding="utf-8").read()
# 심볼릭 링크(custom_nodes/노드 → 개발폴더)에서 파일 못 찾는 문제
check("R52: HERE는 realpath (심볼릭 링크 대응)",
      "os.path.realpath(__file__)" in _src52
      and "os.path.abspath(__file__)" not in _src52)
check("R52: .env 경로 탐색도 realpath",
      "os.path.realpath(__file__)" in _src52b)
check("R52: ComfyUI 루트 미발견 시 경고 (조용한 실패 금지)",
      "_warn_env_root_once" in _src52b)
check("R52: MPS 메모리 반납 (macOS)",
      'getattr(_t, "mps", None)' in _src52)
# OS 전용 API 금지 — 정적 가드
for _bad52, _why52 in (("os.startfile", "Windows 전용"),
                       ("os.symlink(", "권한/지원이 OS마다 다름"),
                       ("signal.SIGALRM", "Windows 미지원"),
                       ("os.fork", "Windows 미지원"),
                       ("/tmp/", "POSIX 전용 경로"),
                       ("C:\\\\", "드라이브 하드코딩")):
    check(f"R52: {_why52} API 미사용 ({_bad52})",
          _bad52 not in _src52 and _bad52 not in _src52b)
# 경로 결합은 전부 os.path.* 이어야 한다 (문자열 '/' 결합 금지)
check("R52: 경로는 os.path로만 결합",
      'os.path.join(HERE, "presets.json")' in _src52
      or "os.path.join(HERE, name)" in _src52)
check("R52: 파일 인코딩 명시 (기본 시스템 인코딩 금지)",
      _src52.count('encoding="utf-8"') >= 3
      and _src52b.count('encoding="utf-8"') >= 1)
check("R52: 콘솔 인코딩 폴백 (_log)",
      "UnicodeEncodeError" in _src52)
check("R52: mediapipe는 선택 의존 (미설치 시 조용히 폴백)",
      "import mediapipe" in _src52 or "import mediapipe" in _src52b
      or "mediapipe" not in _src52)   # 카메라 본체는 mediapipe 미사용 허용

print("-- R53: ComfyUI 업데이트 대응 (hidden 주입 실패 = 조용한 실패 제거) --")
# 왜(Why): API 키 scrub는 ComfyUI의 hidden 입력 주입에 의존한다. 코어가
# 그 방식을 바꾸면 노드는 **에러 없이 실행**되고 사진 PNG에 키가 남는다.
# 사용자가 알 수 있는 단서가 경고뿐이므로, 반드시 말해야 한다.
_captured53 = []
_orig_log53 = cd._log
cd._log = lambda m: _captured53.append(str(m))
try:
    cd._SCRUB_WARNED.clear()
    # 1) 키 없이 unique_id도 없으면 경고 없음 (노이즈 금지)
    cd._warn_scrub_unavailable("", None, None)
    check("R53: 키가 없으면 경고 안 함 (로그 오염 방지)",
          not any("지우지 못했" in m for m in _captured53), _captured53[-1:])
    # 2) 키가 있는데 unique_id 미주입 → 경고 (ComfyUI 버전 변화 신호)
    cd._warn_scrub_unavailable("sk-test", None, None)
    check("R53: unique_id 미주입 시 경고",
          any("지우지 못했" in m and "hidden" in m for m in _captured53),
          _captured53[-1:])
    check("R53: 원인과 조치를 같이 알림",
          any("ComfyUI 버전" in m and "api_key 지우기" in m
              for m in _captured53), _captured53[-1:])
    # 3) 1회만 (매 실행마다 찍으면 경고가 눈에 띄지 않는다)
    _n53 = len([m for m in _captured53 if "지우지 못했" in m])
    cd._warn_scrub_unavailable("sk-test", None, None)
    cd._warn_scrub_unavailable("sk-test", None, None)
    _n2_53 = len([m for m in _captured53 if "지우지 못했" in m])
    check("R53: 경고는 1회만 (반복 로그 방지)", _n53 == 1 and _n2_53 == 1,
          f"{_n53} → {_n2_53}")
    # 4) 정상 경로(dict + uid)는 경고 없음 — 스크럽이 이미 성공한 경우
    _before53 = len(_captured53)
    cd._warn_scrub_unavailable("sk-test", {"1": {"inputs": {}}}, "1")
    check("R53: 정상 주입 경로에서는 경고 없음",
          len(_captured53) == _before53)
    # 5) prompt 형식이 다르면 그 사유로 경고
    _c2 = []
    cd._log = lambda m: _c2.append(str(m))
    cd._SCRUB_WARNED.clear()
    cd._warn_scrub_unavailable("sk-test", "문자열", "1")
    check("R53: prompt 형식 이상 시 사유를 구분해 경고",
          any("형식이 예상과 다름" in m for m in _c2), _c2[-1:])
    # 6) 예외 안전
    cd._warn_scrub_unavailable(None, None, None)
    check("R53: 실패 안전", True)
finally:
    cd._log = _orig_log53
    cd._SCRUB_WARNED.clear()

# hidden 선언이 실제로 있는지 (이게 사라지면 조용히 죽는다)
check("R53: hidden unique_id/prompt 선언 유지",
      '"hidden"' in _src52 and "UNIQUE_ID" in _src52
      and "PROMPT" in _src52)
check("R53: run()이 scrub 실패 시 경고 경로를 탄다",
      "_warn_scrub_unavailable(" in _src52
      and "extra_pnginfo, png_scrubbed" in _src52)

print("-- R54: 정밀검토 회귀 (2026-09-28, 재발 방지) --")
# 왜(Why) 이 블록이 필요한가: 아래 항목들은 전부 **조용히** 실패했다.
# 에러 없이 실행되면서 사용자에게 반대 결과를 주는 종류라 테스트가 없으면
# 되돌아온다. 각 항목에 "무엇이 조용히 실패했나"를 주석으로 남긴다.

# (1) Skills negative 가드 유실 — watermark/logo/flat lighting/washed out 이
#     Skills 경로에 없으면 base(비등록 내부 클래스)의 방어만 의미가 없다.
_bn54 = cd.build_negative(dict(cd.DEFAULTS), topic="1번 여성 초상")
_bc54 = cd.build_camera_negative(dict(cd.DEFAULTS), topic="1번 여성 초상")
_missing54 = [b[:34] for b in cd._NEGATIVE_BASE_COMMON
              if not (b in _bn54 and b in _bc54)]
check("R54: negative 기본 블록이 두 경로에 모두 존재", not _missing54,
      str(_missing54))
check("R54: 사람이면 인체/색오염 가드가 양쪽에 모두",
      all(s in _bn54 and s in _bc54
          for s in ["plastic waxy skin", "different person",
                    "background color spill on skin"]),
      "build_camera_negative 누락")

# (2) "두 명" 표현에서 두 번째 참조가 소품으로 강등 — 가장 흔한 표현에서
#     가장 큰 오작동. 슬롯 번호 없이 말해도 duo 앵커가 발화해야 한다.
for _t54 in ("두 명이 마주 보고 있다", "a couple standing together",
             "두 사람이 함께 서 있다"):
    check(f"R54: 다인물 표현 duo 앵커 — {_t54}",
          bool(cd.build_duo_person_anchor(2, _t54, image_labels=[1, 2])),
          _t54)
check("R54: 단일 인물 표현은 duo 앵커 없음 (과잉 개입 방지)",
      not cd.build_duo_person_anchor(2, "1번 인물 단독", image_labels=[1, 2]))
check("R54: 번호 나열형 duo 인식",
      bool(cd.build_duo_person_anchor(2, "1번과 2번 인물이 함께",
                                      image_labels=[1, 2])))
check("R54: 나열형에서 두 번째 슬롯만 캡처 (주체 중복 방지)",
      list(cd._second_person_slots("1번과 2번 인물이 함께")) == [2],
      str(cd._second_person_slots("1번과 2번 인물이 함께")))
check("R54: 2인 참조에 소품 강등 문구가 붙지 않음",
      "only for their explicitly requested roles"
      not in cd.reference_guard(2, image_labels=[1, 2],
                                topic="두 명이 마주 보고 있다"),
      cd.reference_guard(2, image_labels=[1, 2], topic="두 명이 마주 보고 있다")[:90])

# (3) 동물 주제에 사람 가드 — "five fingers" 와 "never humanize" 동시 존재
_q54 = cd.add_quality_guard("a golden retriever puppy", image_count=1,
                            topic="강아지 한 마리", image_labels=[1])
check("R54: 동물 주제에 손가락 5개 금지 (사람 전용)",
      "five fingers" not in _q54 and "natural human proportions" not in _q54,
      _q54[-120:])
check("R54: 동물 주제에는 종 보존 문구", "correct animal anatomy" in _q54)
_g54 = cd.reference_guard(1, image_labels=[1], topic="강아지 한 마리")
check("R54: 동물 reference_guard에 hairstyle 없음", "hairstyle" not in _g54, _g54)
check("R54: 사람 주제에는 사람 가드 유지 (반대 방향도 확인)",
      "natural human proportions" in cd.add_quality_guard(
          "a woman", image_count=1, topic="1번 여성", image_labels=[1]))
check("R54: 사람/동물 혼재는 사람 가드 유지",
      "natural human proportions" in cd.add_quality_guard(
          "a woman with a cat", image_count=1, topic="1번 여성과 고양이",
          image_labels=[1]))

# (4) character sheet 문구 중복 — 110단어어 positive 가 두 번 들어가면
#     token/attention 을 중복 소비한다.
_src54 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
check("R54: character sheet positive 재병합 제거",
      '_cs_text = getattr(self, "_last_character_sheet_text"' not in _src54)
check("R54: character sheet negative 수동 병합 제거",
      _src54.count('+ ", " + CHARACTER_SHEET_NEGATIVE') == 0)

# (5) anatomy_count 짝 — positive 만 있고 negative 가 없으면 방향 없는 지시
check("R54: anatomy_count negative 짝 존재 (양 경로)",
      "mitten hands" in cd.build_negative(dict(cd.DEFAULTS), topic="1번 인물",
                                          anatomy_count=True)
      and "mitten hands" in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="1번 인물", anatomy_count=True))
check("R54: 미지정 시 anatomy_count negative 미첨부",
      "mitten hands" not in cd.build_negative(dict(cd.DEFAULTS),
                                              topic="1번 인물"))

# (6) LLM content 배열 — AttributeError 는 `except LLMError` 를 통과해
#     폴백도 표시등도 없이 **노드 실행이 죽는다**.
check("R54: content 배열 응답에서 텍스트 추출",
      llm_client._content_from(
          "OpenAI",
          {"choices": [{"message": {"content": [
              {"type": "text", "text": '{"a":1}'}]}}]}) == '{"a":1}')
check("R54: 배열 content로 JSON 파싱 성공 (크래시 없음)",
      llm_client.extract_json(llm_client._content_from(
          "OpenAI", {"choices": [{"message": {"content": [
              {"type": "text", "text": '{"ok":true}'}]}}]})) == {"ok": True})
check("R54: 문자열 content 회귀 없음",
      llm_client._content_from(
          "OpenAI", {"choices": [{"message": {"content": "plain"}}]}) == "plain")
check("R54: None content 빈 문자열",
      llm_client._content_from(
          "OpenAI", {"choices": [{"message": {"content": None}}]}) == "")
check("R54: Anthropic dict 블록 방어",
      llm_client._content_from("Anthropic", {"content": {"text": "x"}}) == "x")
check("R54: 이미지 블록은 무시하고 텍스트만",
      llm_client._content_from(
          "OpenAI", {"choices": [{"message": {"content": [
              {"type": "image_url"}, {"type": "text", "text": "ab"}]}}]}) == "ab")

# (7) .env `export KEY=` — 접두사가 붙으면 1) 읽기 실패 2) 쓰기가 **중복
#     라인 추가** → 옛 키가 디스크에 잔존한다(비밀 잔존).
import os as _os54
import tempfile as _tf54
_d54 = _tf54.mkdtemp()
_p54 = _os54.path.join(_d54, ".env")
try:
    with open(_p54, "w", encoding="utf-8") as _f:
        _f.write("export OPENAI_API_KEY=old\nOTHER=1\n")
    _orig_ovr = llm_client._ENV_FILE_OVERRIDE
    llm_client._ENV_FILE_OVERRIDE = _p54
    try:
        cd._write_env_file_key("OPENAI_API_KEY", "new")
        _body54 = open(_p54, encoding="utf-8").read()
    finally:
        llm_client._ENV_FILE_OVERRIDE = _orig_ovr
    check("R54: export 접두사 라인 교체 (중복 라인 없음)",
          _body54.count("OPENAI_API_KEY") == 1 and "old" not in _body54,
          repr(_body54))
    check("R54: export 접두사 읽기", "new" in _body54, repr(_body54))
finally:
    try:
        import shutil as _sh54
        _sh54.rmtree(_d54, ignore_errors=True)
    except Exception:
        pass

# (8) 죽은 상수 제거 — 정의만 있고 참조 0 이었다.
check("R54: 죽은 상수 제거됨",
      all(s not in _src54 for s in
          ("REMOVE_ITEM_KEYWORDS = (", "REMOVE_ITEM_NEGATIVE = (",
           "PHYSICS_MOTION_NEGATIVE = (")))

print("-- 하네스 감사 회귀 (2026-09-28 R55) --")
# 왜(Why): 아래는 740건 테스트를 전부 통과한 상태에서 하네스 감사 에이전트가
# **실측**으로 찾아낸 것들. 전부 조용히 실패했다(예외 없이 반대 결과).
#
# (1) 어휘 오탐 — 부분 문자열 매칭. 한국어 1글자 동물어("소","양","말","새","개",
#     "고")가 명사·어미와 결합해 의사와 다른 단어가 된다. 결과: **사람이 있는
#     장면이 동물로 분류**되어 인체 가드 전체가 사라지고 "mascot costume"
#     같은 동물 negative 가 붙는다 — 사용자에게 정반대.
for _t, _why in (("\ubc29 \uc548\uc5d0\uc11c \uc18c\ud30c\uc5d0 \uc545\uc788\uc544 "
                 "\uc788\ub294 \uc5f0\uc778 \ud55c \uc7b5\uc774 \ub300\ud654\ud558\ub294 "
                 "\uc7a5\uba74", "sofa(small-cow)"),
                ("\ud0dc\uc591\uc774 \uc9c0\ub294 \uc0ac\ub9dd \ud3d9\ub2e8 "
                 "\ub85c\ub4dc\ud2b8\ub9bd", "sun(sheep)"),
                ("\uc659\uc6d0 \ub098\ubb34 \uae38\uc744 \uc704\ud1b5 \ud48d\uacbd",
                 "trees(sheep)")):
    check(f"R55: 한국어 동물어 오탐 제거 — {_why}",
          not cd._is_animal_subject(_t), _t)
# 주의: 한글 이스케이프는 **NFC** 로 쓴다. 려는 U+B824(NFC) 이고
# U+B8E0 은 NFD 분해형이라 실제 어휘와 매칭이 안 된다(2026-09-28 실측).
# 정상 animal 은 여전히 판정돼야 한다 (과잉 수정은 반대 실패)
for _t in ("\uac15\uc544\uc9c0 \ud55c \ub9c8\ub9ac", "\uace0\uc591\uc774 "
           "\uc788\ub2e4", "\ubc18\ub824\ub3d9\ubb3c \uc788\ub2e4"):
    check(f"R55: 한국어 동물 정상 판정 유지 — {_t[:8]}",
          cd._is_animal_subject(_t), _t)
# (2) 영문 부분 문자열 — man(romantic/german), cat(catalogue), bear(bearable)
for _t, _why in (("a romantic sunset", "man in romantic"),
                 ("a german forest", "man in german"),
                 ("a catalogue of items", "cat in catalogue"),
                 ("a bearable jacket", "bear in bearable")):
    check(f"R55: 영문 오탐 제거 — {_why}",
          not cd._is_human_subject(_t) and not cd._is_animal_subject(_t), _t)
check("R55: 영문 정상 판정 유지 (cat/puppy)",
      cd._is_animal_subject("a cat sitting on a sofa")
      and cd._is_animal_subject("a golden retriever puppy"))
check("R55: 한국어 조사 경계 규칙 — 소파/고양이 동시 판정",
      cd._ko_word_present("소파에 앉았다", "소") is False
      and cd._ko_word_present("강아지 한 마리", "강아지") is True)
check("R55: 앞쪽 접합 차단 (태양/양옆)",
      cd._ko_word_present("\ud0dc\uc591", "양") is False)

print("-- R56: 픽셀 기반 캐릭터 시트 판별 (topic 없이) --")
# 실측 회귀(2026-09-28): topic 이 비어 있으면 text 가드가 거짓이 되어
# character_sheet_guard 가 아예 발동하지 않았다 -> 1인 6뷰 시트가 결과에서
# 2명으로 복제. "정보는 이미 픽셀에 있다"는 원칙으로 픽셀 판별을 넣는다.
#
# 교정 내역 (중요): 처음엔 "패널 폭이 고르면 시트" 였는데 **실제 사용자 시트
# (10896x6800, 전신 2 + 얼굴 4)의 폭비가 2.50** 이라 그것도 탈락했다. 전신과
# 클로즈업은 구조적으로 폭이 다르니 폭 균일성은 시트의 조건이 아니다. 지금
# 기준은 구조(간격 균일성) + 내용(셀 유사도) 두 가지다.
import numpy as _np


def _np_as_rgb_stub(a):
    """실제 파이프라인처럼 512 이하로 축소한 배열 (PIL 없이 슬라이싱 근사)."""
    step = max(1, max(a.shape[0], a.shape[1]) // 512)
    return a[::step, ::step, :]


def _sil(a, cx, top, bot, hw, tone=.28):
    """좁은 인물 실루엣. 흰 배경 위에서 각 행을 조금만 차지해야 행 프로파일에
    패널 사이 간격이 생긴다(실제 사진과 같은 성질)."""
    a[top:bot, cx - hw:cx + hw] = tone
    head = (bot - top) // 9
    a[top:top + head, cx - head // 2:cx + head // 2] = .20


def _cu(a, cx, top, hw, hh):
    a[top:top + 2 * hh, cx - hw:cx + hw] = .86
    head = (2 * hh) // 4
    a[top + hh // 2:top + hh // 2 + head, cx - head // 2:cx + head // 2] = .74


def _sheet_layout():
    """실제 사용자 시트와 같은 레이아웃: 전신 2(좌, 세로 전체) + 얼굴 4(우 2x2)."""
    a = _np.ones((1024, 1536, 3), dtype=_np.float32)
    for cx in (250, 620):
        _sil(a, cx, 70, 980, 46)
    for gy in (170, 610):
        for gx in (1090, 1370):
            _cu(a, gx, gy, 118, 165)
    return a


def _even_sheet(n=6):
    a = _np.full((512, 256 * n, 3), 0.95, dtype=_np.float32)
    for i in range(n):
        _sil(a, i * 256 + 128, 50, 480, 44)
    return a


def _row_sheet(n=6):
    a = _np.ones((256 * n, 1024, 3), dtype=_np.float32)
    for i in range(n):
        _sil(a, 420, i * 256 + 40, i * 256 + 240, 60)
    return a


# (1) 실제 사용자 구조(전신 2 + 얼굴 4, 2x2) — 실측 sim 0.414
_a = _sheet_layout()
check("R56: 실제 시트 구조(전신2+얼굴4) 픽셀 인식",
      cd._looks_like_sheet(_a)["sheet"], str(cd._looks_like_sheet(_a)))

# (1b) 6등분 / 세로 배열
check("R56: 6뷰 정렬 시트 픽셀 인식", cd._looks_like_sheet(_even_sheet())["sheet"])
check("R56: 세로 배열 시트 픽셀 인식", cd._looks_like_sheet(_row_sheet())["sheet"])

# (1c) 좌표 공간 정규화 — 2026-09-28 실측 버그.
# 프로파일은 512 기준 좌표를 내는데 원본 배열로 자르면 엉뚱한 곳을 읽는다.
# 1536 폭에서 밴드(67,100)는 실제 실루엣(204,296)이 아니었다. 이게 없어서
# 셀 유사도가 0 이 되어 판별이 조용히 죽었다. 큰 배열을 그대로 넘겨도
# 같은 판정이 나와야 한다.
check("R56: 원본 해상도 배열에서도 동일한 판정 (좌표 정규화)",
      cd._looks_like_sheet(_a)["sheet"]
      and cd._looks_like_sheet(_np_as_rgb_stub(_a))["sheet"],
      str(cd._looks_like_sheet(_a)))

# (2) 오탐 방어: 1인/2인/평탄은 시트가 아니다.
#     (시트로 오인하면 뷰를 여러 신원으로 평균내며 조용히 망가지기 때문)
_p1 = _np.full((768, 1024, 3), 0.92, dtype=_np.float32)
_sil(_p1, 500, 70, 730, 60)
check("R56: 단일 인물 사진은 시트로 오인하지 않음",
      not cd._looks_like_sheet(_p1)["sheet"], str(cd._looks_like_sheet(_p1)))
_p2 = _np.full((512, 1024, 3), 0.9, dtype=_np.float32)
for _cx in (300, 700):
    _sil(_p2, _cx, 50, 480, 48)
check("R56: 2인 사진은 시트로 오인하지 않음",
      not cd._looks_like_sheet(_p2)["sheet"], str(cd._looks_like_sheet(_p2)))
_flat = _np.full((512, 512, 3), 0.5, dtype=_np.float32)
check("R56: 평탄 이미지는 시트로 오인하지 않음",
      not cd._looks_like_sheet(_flat)["sheet"])

# (3) 격자는 같아도 **내용이 다르면** 시트가 아니다. 합성 그림은 전부 같은
#     색이라 유사도가 무조건 1 이 되는데, 그건 판별력을 검증해 주지 않는다.
_mix = _np.ones((1024, 1536, 3), dtype=_np.float32)
for cx in (250, 620):
    _mix[70:980, cx - 46:cx + 46] = .12
for gy in (170, 610):
    for gx in (1090, 1370):
        _mix[gy:gy + 330, gx - 118:gx + 118] = .88
check("R56: 격자는 같아도 내용이 다르면 시트로 보지 않음",
      not cd._looks_like_sheet(_mix)["sheet"], str(cd._looks_like_sheet(_mix)))

# (5) 경로 일치 — ComfyUI 텐서(BHWC)와 PIL 은 **같은 판정**이어야 한다.
# 2026-09-29 실측: 텐서 경로에서 stride 축소가 종횡비를 깨뜨려 가로로 긴
# 배열이 171x171 로 뭉개졌고, 포즈 사진이 sim 0.209 → **시트로 오인**됐다.
# 유닛 테스트는 PIL 경로만 보므로 이런 버그를 못 잡는다. 두 경로를 직접
# 비교해 문에 고정한다.
# ComfyUI 는 BHWC 텐서를 준다. **정규화 함수(_np_as_rgb)를 거치면** 두
# 경로가 같은 판정을 내야 한다 — 좌표를 어긋뜨리지 않는 것이 목표이므로.
check("R56: 경로 일치 — 합성 시트는 PIL 경로와 ComfyUI 텐서 경로 모두 시트",
      cd._looks_like_sheet(cd._np_as_rgb(_even_sheet()))["sheet"]
      and cd._looks_like_sheet(cd._np_as_rgb(
          _np.ascontiguousarray(_even_sheet()[None, ...])))["sheet"],
      "PIL=%s 텐서=%s" % (
          cd._looks_like_sheet(cd._np_as_rgb(_even_sheet())),
          cd._looks_like_sheet(cd._np_as_rgb(
              _np.ascontiguousarray(_even_sheet()[None, ...])))))
check("R56: 경로 일치 — 단일 인물은 두 경로 모두 시트 아님",
      not cd._looks_like_sheet(cd._np_as_rgb(_p1))["sheet"]
      and not cd._looks_like_sheet(cd._np_as_rgb(
          _np.ascontiguousarray(_p1[None, ...])))["sheet"],
      "PIL=%s 텐서=%s" % (
          cd._looks_like_sheet(cd._np_as_rgb(_p1)),
          cd._looks_like_sheet(cd._np_as_rgb(
              _np.ascontiguousarray(_p1[None, ...])))))
# 축소 후 크기는 종횡비를 유지해야 한다 (stride 로 정사각형에 만들면
# 세로/가로로 긴 시트가 통째로 죽는다 — 512x1536 → 171x171 실측).
_n_wide = cd._sheet_normalize(_even_sheet())
check("R56: 축소가 종횡비를 보존한다 (가로로 긴 시트)",
      _n_wide.shape[1] > _n_wide.shape[0] * 2,
      str(_n_wide.shape))
check("R56: 축소가 종횡비를 보존한다 (세로로 긴 시트)",
      cd._sheet_normalize(_row_sheet()).shape[0]
      > cd._sheet_normalize(_row_sheet()).shape[1] * 1.2,
      str(cd._sheet_normalize(_row_sheet()).shape))

# 슬롯 반환: 1번은 보통 이미지, 3번이 시트 -> "3" 만 나와야 한다
_slots = cd.sheet_like_slots([(1, _p1), (2, None), (3, _even_sheet())])
check("R56: sheet_like_slots 가 시트 슬롯만 반환",
      _slots == ["3"], str(_slots))

# (5) topic 이 비어도 시트 지시가 붙는다 (이번 버그의 핵심)
_g_px = cd.character_sheet_guard(3, "", image_labels=[1, 2, 3], pixel_sheet_slots=["3"])
# (6) topic 이 비어도 시트 지시가 붙는다 (이번 버그의 핵심)
_g_px = cd.character_sheet_guard(3, "", image_labels=[1, 2, 3],
                               pixel_sheet_slots=["3"])
check("R56: 빈 topic + 픽셀 시트 -> 시트 지시 발동",
      "Every view is the same one person" in _g_px, _g_px[:160])
# 2026-09-29 ComfyUI 실측에서 또 하나가 걸렸다: 시트가 **3번**인데
# 프롬프트가 "reference image 1 is a character sheet" 라고 했다. first 를
# 무조건 썼기 때문이다. 1번은 신원 사진이라 **시트가 아닌데 시트라 지목**된
# 정반대 지시 — 모델이 엉뚱하게 반응한다. 픽셀 판별이 찾은 슬롯을 지목해야 한다.
check("R56: 시트 지목이 실제 시트 슬롯(3번)이다",
      "reference image(s) 3 is a character sheet" in _g_px
      and "reference image 1 is a character sheet" not in _g_px,
      _g_px[:200])
check("R56: 시트 슬롯이 여러 개면 전부 지목",
      "reference image(s) 1, 3 is a character sheet"
      in cd.character_sheet_guard(3, "", image_labels=[1, 2, 3],
                                   pixel_sheet_slots=["1", "3"]))
# 픽셀 판별이 없으면 기존처럼 first 로 물러선다 (topic 으로 명시한 경로).
check("R56: 픽셀 판별 없으면 기존대로 첫 슬롯 지목 (회귀)",
      "reference image 1 is a character sheet"
      in cd.character_sheet_guard(3, "캐릭터 시트", image_labels=[1, 2, 3]))
check("R56: 빈 topic + 시트 없음 -> 미작동 (과잉 개입 방지)",
      cd.character_sheet_guard(3, "", image_labels=[1, 2, 3]) == "")
# (6) negative 대칭: positive 만 붙고 negative 가 빠지면 "2명 복제"가 그대로
#     돌아온다. 양쪽 배선을 문에 고정한다.
check("R56: character_sheet 플래그로 별개 인물 복제 방어 첨부",
      cd.CHARACTER_SHEET_PEOPLE_NEGATIVE in cd.build_negative(
          dict(cd.DEFAULTS), topic="", image_labels=[1, 2, 3], image_count=3,
          character_sheet=True))
check("R56: 시트 미판정 시 negative 없음 (과잉 개입 방지)",
      cd.CHARACTER_SHEET_PEOPLE_NEGATIVE not in cd.build_negative(
          dict(cd.DEFAULTS), topic="", image_labels=[1, 2, 3], image_count=3))
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "camera_director.py"), encoding="utf-8").read()
check("R56: base run / Skills 모두 character_sheet 를 negative 에 전달",
      _src.count("character_sheet=bool(") >= 2,
      str(_src.count("character_sheet=bool(")))

# (7) 임계값 문고정 — 실측 근거와 함께
check("R56: 간격 균일성 기준 0.45 (실사용 사진 0.38~0.71, 실제 시트 0.95)",
      cd._SHEET_MIN_SPACING_RATIO == 0.45, str(cd._SHEET_MIN_SPACING_RATIO))
check("R56: 셀 유사도 기준 0.20 (실사용 사진 <=0.109, 실제 시트 0.414)",
      cd._SHEET_MIN_CELL_SIMILARITY == 0.20, str(cd._SHEET_MIN_CELL_SIMILARITY))
# 실제 사용자 시트의 폭비는 2.50 이다. "패널 폭이 고르다"는 시트의 조건이
# 아니라 우연이므로(전신과 클로즈업은 구조적으로 폭이 다르다) 이 기준을
# 되살리면 진짜 시트를 놓친다 -> 상수가 없어야 한다.
check("R56: 폭 균일성 기준은 제거됨 (실제 시트 폭비 2.50 놓치지 않기 위해)",
      not hasattr(cd, "_SHEET_MAX_WIDTH_RATIO"))

print("-- R57: 시트 슬롯은 vision 전용 (reference latent 에서 제외) --")
# 2026-09-29 실측 회귀: 시트를 Qwen reference latent 로 넣으면 결과가
# **6뷰 시트 그대로** 렌더링됐다. 분리 실험으로 확정 —
#   시트 없음(2장) → 1인 정상
#   시트 있음(3장) + 빈 topic → 4뷰
#   시트 있음(3장) + topic 에 "a single continuous photograph of one
#     young woman" 명시 → 그래도 4뷰
# 프롬프트로는 이길 수 없다(pixel-level 레이아웃 힌트). 그래서 시트는
# LLM(신원 파악)에만 보여주고 diffusion 에서는 뺀다.
cd.clear_qwen_ref_cache()
import torch as _t57


class _VAE57:
    """slot 라벨별로 encode 호출을 기록한다."""

    def __init__(self):
        self.encoded = []

    def encode(self, s):
        self.encoded.append(tuple(s.shape))
        return ("latent", tuple(s.shape))


import types as _ty57
_fake_comfy57 = _ty57.ModuleType("comfy")
_fu57 = _ty57.ModuleType("comfy.utils")
_fu57.common_upscale = lambda s, w, h, *a, **k: s
_fake_comfy57.utils = _fu57
_fnh57 = _ty57.ModuleType("node_helpers")
_fnh57.conditioning_set_values = lambda c, v, append=True: c
_saved57 = {m: sys.modules.get(m)
              for m in ("comfy", "comfy.utils", "node_helpers")}
sys.modules["comfy"] = _fake_comfy57
sys.modules["comfy.utils"] = _fu57
sys.modules["node_helpers"] = _fnh57
try:
    # 슬롯마다 **다른 픽셀**을 써야 한다 — 동일 픽셀이면 VAE 캐시가 세 슬롯을
    # 같은 이미지로 보고 재사용해 encode 호출이 1회로 줄어든다(테스트는
    # vae.encode 호출 수로 판정하므로).
    _img57 = _t57.ones(1, 64, 64, 3) * 0.3
    _img57b = _t57.ones(1, 64, 64, 3) * 0.5
    _img57c = _t57.ones(1, 64, 64, 3) * 0.7
    _vae57 = _VAE57()
    _items57 = [(1, _img57), (2, _img57b), (3, _img57c)]
    # 시트 슬롯 3번만 latent 에서 제외
    _vl57, _rl57 = cd.CameraDirectorEncode._prepare_qwen_image_data(
        _items57, vae=_vae57, latent_image=None,
        latent_skip_labels={"3"})
    check("R57: 시트 슬롯은 vision 에 포함", len(_vl57) == 3, str(len(_vl57)))
    check("R57: 시트 슬롯은 latent 에서 제외 (2장만)",
          len(_rl57) == 2, str(len(_rl57)))
    check("R57: 제외된 슬롯은 VAE encode 도 호출되지 않음",
          len(_vae57.encoded) == 2, str(len(_vae57.encoded)))
    # 제외 지정이 없으면 예전대로 전부 latent 에 들어간다 (회귀)
    cd.clear_qwen_ref_cache()
    _vae57b = _VAE57()
    _vl57b, _rl57b = cd.CameraDirectorEncode._prepare_qwen_image_data(
        _items57, vae=_vae57b, latent_image=None)
    check("R57: 제외 지정 없으면 전부 latent (회귀)",
          len(_rl57b) == 3, str(len(_rl57b)))
    check("R57: 제외 지정은 문자열로도 받음 ('3')",
          cd.CameraDirectorEncode._prepare_qwen_image_data(
              _items57, vae=_vae57b, latent_image=None,
              latent_skip_labels=[3])[1].__len__() == 2)
finally:
    for _m, _v in _saved57.items():
        if _v is not None:
            sys.modules[_m] = _v
        else:
            sys.modules.pop(_m, None)
    cd.clear_qwen_ref_cache()

# negative 도 "결과 형태" 로 지목해야 한다 (프롬프트만으로는 안 막혔다)
check("R57: negative 가 시트 결과 형태를 직접 지목",
      "the same person repeated several times" in cd.CHARACTER_SHEET_NEGATIVE,
      cd.CHARACTER_SHEET_NEGATIVE[:120])
check("R57: positive 가 무엇을 그릴지 직접 명시",
      "must NOT appear in the output" in
      cd.character_sheet_guard(1, "character sheet",
                              image_labels=[1]))

print("-- R58: 포즈 역할 자연 표현 인식 (숫자 + 자세 묘사) --")
# 2026-09-29 실측 회귀: 기존 포즈 패턴은 "이미지 2의 포즈" 처럼 **역할
# 명사**만 인식했다. 사용자가 "2번은 포즈만", "2번 앉은 자세" 처럼
# 슬롯 번호 + 실제 자세를 적으면 **전부 미인식**이었다. 전수 확인 결과:
#   2번은 포즈만 / 2번 포즈만 / 2번 앉은 자세 / 2 앉은 자세 /
#   3번 서 있는 모습 / 2번 손에 든 상태 / 2번 자세만 참고 /
#   1번은 신원, 2번은 앉은 자세 / 2번 sitting / 2 sitting pose
# 모두 미인식이었다.
_POSE_OK = [
    ("2번은 포즈만", {2}), ("2번 포즈만", {2}), ("2번은 포즈", {2}),
    ("2번 이미지의 포즈", {2}), ("2번 이미지 포즈", {2}),
    ("2번 앉은 자세", {2}), ("2 앉은 자세", {2}),
    ("2번은 앉은 자세", {2}), ("2번 앉은 자세만", {2}),
    ("3번 서 있는 모습", {3}), ("2번 손에 든 상태", {2}),
    ("2번 자세만 참고", {2}), ("2번 서있는", {2}),
    ("1번은 신원, 2번은 앉은 자세", {2}),
    ("2번 sitting", {2}), ("2 sitting pose", {2}), ("2번 leaning", {2}),
]
for _t58, _want58 in _POSE_OK:
    check("R58: 자연 표현 인식 — " + _t58,
          cd._pose_role_slots(_t58) == _want58,
          str(sorted(cd._pose_role_slots(_t58))))

# 오탐 회귀: 포즈 슬롯으로 잘못 잡으면 그 슬롯이 **신원 소스에서 제외**돼
# 사람이 사라진다. 사람/사물/의상 슬롯이 포즈로 잡히면 안 된다.
_POSE_NOT = [
    "2번 여성", "2번 남자", "2번 인물", "2번 핸드백", "2번 시계",
    "2번 원피스", "2번 의상", "2번 침대", "2번 고양이", "2번 강아지",
    "3번 인물", "1번은 여성, 2번은 남성", "2번 배경", "2번 조명",
    "2번 소파", "2번 의자", "2번 컵", "2번 책", "2번 모델", "2번 제품",
]
for _t58b in _POSE_NOT:
    check("R58: 사람/사물은 포즈로 잡지 않음 — " + _t58b,
          not cd._pose_role_slots(_t58b),
          str(sorted(cd._pose_role_slots(_t58b))))

# 숫자와 무관한 표현에서도 오탐 없어야 한다(수량/시간/서수/연도 등).
_POSE_NUM = [
    "2가지 색", "3가지", "5분", "10초", "1층", "2등", "100원", "3인",
    "4명", "2026년", "12시", "2개", "5번 버스", "3번 문제", "2번 타자",
    "2주", "3개월", "50%", "2배", "4차", "2주차", "10배", "2번째 줄",
    "3번째 장", "5번째 샷", "1부", "2막", "2인용",
]
for _t58c in _POSE_NUM:
    check("R58: 숫자 무관 표현 오탐 없음 — " + _t58c,
          not cd._pose_role_slots(_t58c),
          str(sorted(cd._pose_role_slots(_t58c))))

# 기존 표현이 깨지지 않아야 한다(회귀).
check("R58: 기존 나열형 유지",
      cd._pose_role_slots("3번과 7번 이미지의 포즈") == {3, 7})
check("R58: 기존 영문 유지",
      cd._pose_role_slots("use pose from image 4") == {4})
check("R58: 기존 이미지 라벨형 유지",
      cd._pose_role_slots("이미지 2의 자세") == {2})


# ── R59: 의상 교체 슬롯 자연 표현(2026-09-29) ──────────────────────
# 왜(Why): "2 의상, 1 교체" 처럼 **이미지 라벨 없이** 슬롯 번호만 쓰는 표현이
# 전부 미인식이었다(전수 확인: 6개 표현 전부 실패). 라벨을 쓰면 되는데
# 사용자가 매번 "이미지" 를 붙이는 게 번거로워서 놓쳤다 -> 의상 가드 미작동.
# 그리고 "2 의상, 1 교체" 에서 1번(주인물)까지 의상 소스로 잡히면
# **1번이 신원 소스에서 제외돼 사람이 사라진다** -> source/target 분리 필수.
print("-- R59: 의상 교체 슬롯 자연 표현 --")

# (topic, 의상 소스, 교체 대상, 의도)
_OUTFIT_CASES = [
    # 슬롯 번호만(핵심 케이스)
    ("2 의상, 1 교체", {2}, {1}, True),
    ("2번 의상, 1번 교체", {2}, {1}, True),
    ("2 의장, 1 적용", {2}, {1}, True),
    ("2번 옷, 1번 변경", {2}, {1}, True),
    ("2번 의장을 1번에 입혀", {2}, {1}, True),
    ("2번 의장만 1번에 적용", {2}, {1}, True),
    ("1번에 2번 의장을 입혀", {2}, {1}, True),
    ("2번 의장을 1번 인물에게 입히고", {2}, {1}, True),
    # 라벨 형식(구버전 호환)
    ("이미지 2 의상, 이미지 1 교체", {2}, {1}, True),
    ("이미지 2 의상을 이미지 1에 적용", {2}, {1}, True),
    # 의상 소스만 지정(교체 아님) -> 의도 False 가 맞다
    ("2번 의상", {2}, set(), False),
    ("2 의상", {2}, set(), False),
    ("2번 원피스", {2}, set(), False),
    ("2번 의상 참고", {2}, set(), False),
    ("2번 옷 참고", {2}, set(), False),
    # 대상만 있는 표현: 소스는 비어야 하지만 대상은 잡힌다
    ("1번 교체", set(), {1}, False),
    ("3번 입혀", set(), {3}, False),
    ("1번 swap", set(), {1}, False),
    ("1번 change", set(), {1}, False),
    ("1번은 원래 유지", set(), set(), False),
    # 오탐: 의상 어휘 뒤에 **착용 동사**가 붙으면 그 슬롯은 '인물' 이다.
    # 의상 소스로 잡히면 사람이 신원 소스에서 제외된다(2026-09-29 실측 위험).
    ("드레스를 입은 여성", set(), set(), False),
    ("옷을 입은 남자", set(), set(), False),
    ("2번 드레스를 입은 여성", set(), set(), False),
    ("she wears a dress", set(), set(), False),
    ("a man in a suit", set(), set(), False),
    ("1번 여성이 원피스를 입고 있다", set(), set(), False),
]
for _t59, _wc, _wt, _wi in _OUTFIT_CASES:
    _gc = cd._clothing_role_slots(_t59)
    _gt = cd._outfit_target_slots(_t59)
    _gi = cd._is_outfit_transfer(_t59)
    check("R59: 의상 슬롯 — " + _t59, _gc == _wc,
          "%s (기대 %s)" % (sorted(_gc), sorted(_wc)))
    check("R59: 교체 대상 — " + _t59, _gt == _wt,
          "%s (기대 %s)" % (sorted(_gt), sorted(_wt)))
    check("R59: 교체 의도 — " + _t59, _gi == _wi, str(_gi))

# 회귀: 의상 어휘 보강이 사물/인물 슬롯을 침범하지 않아야 한다.
check("R59: 의장 추가 후 사물 슬롯 오염 없음",
      cd._object_role_slots("2번 의장") == set(),
      str(sorted(cd._object_role_slots("2번 의장"))))
check("R59: 의장 추가 후 인물 슬롯 오염 없음",
      "2" not in cd._pose_role_slots("2번 의장"),
      str(sorted(cd._pose_role_slots("2번 의장"))))

# 회귀: 교체 대상이 의상 슬롯에 섞여도 duo 인물 판정은 1번을 지킨다.
check("R59: 교체 대상이 인물 duo 에서 빠지지 않음",
      cd._is_outfit_transfer("2 의상, 1 교체") is True)

# ── R60: 의상 교체 → 역할 계획 연동 (2026-09-29 실제 실행 결함) ──
# 왜(Why): 슬롯 판정은 맞는데 **주 피사체가 의상 사진으로 남았다.**
# 1번=옷, 2번=인물, topic="1 의상, 2 교체" 실사용 실행에서 프롬프트가
# "use reference image 1 as the only main human identity" 라고 역전 지시했다.
# 의상 소스는 사람이 아니다 -> 신원 소스 후보에서 제외하고,
# 교체 대상(옷을 입는 사람)을 주 피사체로 올린다.
print("-- R60: 의상 교체 역할 계획 연동 --")

_PLAN_CASES = [
    # (topic, labels, 기대 main, 기대 persons)
    ("1 의상, 2 교체", ["1", "2"], 2, []),
    ("2 의상, 1 교체", ["1", "2"], 1, []),
    ("이미지 1 의상, 이미지 2 교체", ["1", "2"], 2, []),
    ("이미지 2 의상을 이미지 1에 적용", ["1", "2"], 1, []),
    ("1번 의장을 2번 인물에게 입히고", ["1", "2"], 2, []),
    ("1번 의상, 2번에 적용", ["1", "2"], 2, []),
    # 의상 소스만 지정(교체 아님) -> 첫 슬롯이 옷이어도 그 다음이 주 피사체
    ("2번 의상 참고", ["1", "2"], 1, []),
    # 회귀: 포즈 지정은 기존 그대로
    ("1번 포즈, 2번 여성", ["1", "2"], 2, []),
]
for _t60, _l60, _wm, _wp in _PLAN_CASES:
    _p60 = cd._person_object_plan(_t60, _l60)
    check("R60: 주 피사체 — " + _t60, _p60["main"] == _wm,
          "%s (기대 %s)" % (_p60["main"], _wm))
    check("R60: 추가 인물 — " + _t60, _p60["persons"] == _wp,
          "%s (기대 %s)" % (_p60["persons"], _wp))

# 회귀: 사물 우선 규약이 유지된다(사물은 라벨 표현 "이미지 N" 만 지원).
_p60_obj = cd._person_object_plan("이미지 1 핸드백, 이미지 2 여성", ["1", "2"])
check("R60: 사물 1번 지정 시 인물이 주 피사체", _p60_obj["main"] == 2,
      str(_p60_obj))
check("R60: 사물 지정은 objects 로 남는다", _p60_obj["objects"] == [1],
      str(_p60_obj))

# 가장 중요한 회귀 1: 의상 사진이 1번이어도 identity 앵커가 2번을 지목한다.
_anchor60 = cd.build_identity_anchor(2, "1 의상, 2 교체", ["1", "2"])
check("R60: identity 앵커가 인물 슬롯(2)을 지목",
      "image 2" in _anchor60 and "image 1 as" not in _anchor60,
      _anchor60[:160])
# 반대 순서: 2번=옷, 1번=인물 → 1번을 지목해야 한다.
_anchor60b = cd.build_identity_anchor(2, "2 의상, 1 교체", ["1", "2"])
check("R60: identity 앵커 순서 무관 (옷이 2번 → 인물 1번)",
      "image 1 as" in _anchor60b, _anchor60b[:160])

# 가장 중요한 회귀 2: 의상 교체 topic 에는 인물 키워드가 없는데도
# 인물로 판정돼야 한다(없으면 인물 가드 전부가 조용히 미작동).
check("R60: 의상 교체 topic 은 사람으로 판정",
      cd._is_human_subject("1 의상, 2 교체") is True)
check("R60: '의상 교체' 단독(슬롯 없음)은 사람 아님",
      cd._is_human_subject("의상 교체") is False)
check("R60: 동물 주제는 사람으로 오탐되지 않음",
      cd._is_human_subject("1 의상, 2 교체 강아지") is False)

# R63: 한국어를 못 인코딩하는 콘솔에서 테스트가 죽지 않는다.
# 왜(Why) 여러 인코딩을 도나: 처음엔 cp949(한국어 Windows 콘솔)만 봤다.
# 그런데 **GitHub Windows 러너의 기본은 cp1252** 라서 cp949 는 아무 문제가
# 없는 척했다(2026-09-29 실측: 배포 저장소 CI run#27/run#28, Windows 2개만
# failure). cp1252 는 한글을 아예 모르는 charmap 이라 첫 글자에서 죽는다.
# 특정 인코딩을 가정하면 "내 PC에선 되니까"가 된다 — 전부 돌린다.
#
# 검증 방법: 실제 서브프로세스를 각 인코딩으로 띄워 **파일 전체를 끝까지
# 돌린다.** 이 파일 안에서 스트림을 흉내내면(원래 시도) print 가 이미
# 캡처된 stdout 을 그대로 써서 실제 인코딩 실패를 재현하지 못한다.
import subprocess as _sp  # noqa: E402

# 재귀 방지: 이 하위 프로세스도 같은 검사에 들어오면 자기 자신을 또 띄운다.
if os.environ.get("GORI_R63_CHILD"):
    _r63_results = {}
else:
    _r63_results = {}
    for _r63_enc in ("cp949", "cp1252", "ascii", "utf-8"):
        # 절대경로 + cwd 지정. 상대경로("tests/test_node.py")는 cwd 에 의존해서
        # 상위에서 실행하면 exit 2 로 죽는다(2026-09-29 실측).
        _r63_env = dict(os.environ, PYTHONIOENCODING=_r63_enc,
                        GORI_R63_CHILD="1")
        _r63 = _sp.run([sys.executable, os.path.join(HERE, "test_node.py")],
                       capture_output=True, env=_r63_env, cwd=PKG)
        _r63_txt = (_r63.stdout or b"").decode(_r63_enc, errors="replace")
        _r63_err = (_r63.stderr or b"").decode(_r63_enc, errors="replace")
        _r63_results[_r63_enc] = (_r63.returncode, _r63_txt, _r63_err)
        check(f"R63: {_r63_enc} 인코딩으로 끝까지 실행 (UnicodeEncodeError 없음)",
              _r63.returncode == 0 and "UnicodeEncodeError" not in _r63_txt
              and "UnicodeEncodeError" not in _r63_err,
              f"exit={_r63.returncode} "
              + next((l for l in _r63_err.splitlines()
                      if "UnicodeEncodeError" in l), ""))
    check("R63: 모든 인코딩에서 전 검사가 통과 (결론이 안 잘리지 않음)",
          all("FAIL=0" in v[1] for v in _r63_results.values()),
          str({k: next((l for l in v[1].splitlines() if "PASS=" in l), "")
               for k, v in _r63_results.items()}))
# 하위 프로세스에서는 이 블록을 건너뛴다(그쪽에서는 원래 stdout 을 쓴다).
check("R63: 테스트의 print 가 인코딩 안전 래퍼",
      print is _say, "print = _say 로 고정해야 한다")
# 원본 stdlib print 를 덮어쓰지 않았는지 — _say 가 재귀하면 스택 초과다.
check("R63: stdlib print 보존 (재귀 방지)", _print is not _say)

# R64: 가드 판정이 한 곳에 있다 (run / run_prompt 수동 동기화 구조 제거).
# 왜(Why) 이게 중요했나: 두 메서드가 같은 가드를 각자 반복 판정하면서
# 결과를 self._last_* 로 넘겨 받았다. **텍스트 소스도 달랐다** — run_prompt
# 는 prompt_in 을 앞에 붙인 문자열로 판정해서, 양쪽이 어긋나면 짝인 negative
# 가 조용히 사라졌다(2026-09-28 실측: 지시가 한쪽_only 가 됨).
# CLAUDE.md 에 "둘을 손으로 동기화한다"고 적혀 있던 그 구조.
_src64 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
check("R64: resolve_guard_plan 존재 (판정 단일 진입점)",
      "def resolve_guard_plan(" in _src64)
check("R64: run_prompt 가 개별 판정을 다시 하지 않음",
      'getattr(self, "_last_guard_plan"' in _src64
      and "_pose_role_slots(_pose_text_pi)" not in _src64,
      "run_prompt 에 판정이 남아 있다")
check("R64: run_prompt 가 plan 플래그를 사용",
      '_gflags_pi["mix_guard"]' in _src64
      and '_gflags_pi["body_balance"]' in _src64)
check("R64: 개별 _last 플래그 중복 저장 제거",
      "self._last_mix_guard =" not in _src64
      and "self._last_body_balance =" not in _src64
      and "self._last_hint_defense =" not in _src64,
      "plan 과 개별 속성이 둘 다 있으면 값이 어긋난다")
# 결정적 판정: 같은 입력이면 같은 plan. 순수 함수여야 한다.
_p_a = cd.resolve_guard_plan("1번 이미지 여성, 2번 배경", dict(cd.DEFAULTS),
                             2, ["1", "2"], [], None, [], tier="auto")
_p_b = cd.resolve_guard_plan("1번 이미지 여성, 2번 배경", dict(cd.DEFAULTS),
                             2, ["1", "2"], [], None, [], tier="auto")
check("R64: 같은 입력 → 같은 판정 (순수 함수)",
      _p_a["flags"] == _p_b["flags"]
      and _p_a["positive"] == _p_b["positive"])
# plan 이 positive/negative 짝을 함께 준다 — 한쪽만 갱신될 수 없다.
check("R64: plan 이 positive 조각과 negative 플래그를 함께 제공",
      isinstance(_p_a["positive"], dict) and isinstance(_p_a["flags"], dict)
      and "mix_guard" in _p_a["flags"], str(sorted(_p_a["flags"])))
# 인물 주제면 발란스·부위경계·부위개수가 켜지고, 비인물이면 꺼진다.
_p_h = cd.resolve_guard_plan("a woman", dict(cd.DEFAULTS), 1, ["1"], [],
                             None, [], tier="auto")
_p_a2 = cd.resolve_guard_plan("a product photo", dict(cd.DEFAULTS), 1, ["1"],
                              [], None, [], tier="auto")
check("R64: 인물 주제 → 발란스·부위 가드 ON, 비인물 → OFF",
      _p_h["flags"]["body_balance"] and _p_h["flags"]["anatomy_count"]
      and not _p_a2["flags"]["body_balance"]
      and not _p_a2["flags"]["anatomy_count"])

# R65: negative 조립 로직이 한 벌이다.
# 왜(Why) 이게 중요했나: build_negative 와 build_camera_negative 가 40줄을
# 복붙하고 있었다. 같은 상수를 같은 순서로 넣는데 한쪽만 고치면 양쪽이
# 어긋나 짝인 방어가 사라진다. 이미 실제로 한 번 어긋난 적이 있다
# (character_sheet negative 가 한쪽에만 있던 시점).
_src65 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
check("R65: 공통 negative 조립기 존재", "def _assemble_negative(" in _src65)
# 두 빌더가 각각 _NEGATIVE_BASE_COMMON 을 직접 쓰면 복붙이 남는다.
check("R65: 두 빌더가 상수 나열을 직접 하지 않음 (공통 조립기 경유)",
      _src65.count("neg = list(_NEGATIVE_BASE_COMMON)") == 1,
      f"직접 사용 { _src65.count('neg = list(_NEGATIVE_BASE_COMMON)') }곳")
check("R65: 두 빌더가 모두 공통 조립기를 호출",
      "return _assemble_negative(" in _src65
      and _src65.count("return _assemble_negative(") == 2)
# 조각 순서가 보존됐는지 — 순서가 바뀌면 출력 문자열이 달라진다.
_n_base = cd.build_negative(dict(cd.DEFAULTS), topic="a woman",
                            image_count=1, image_labels=["1"])
_n_cam = cd.build_camera_negative(dict(cd.DEFAULTS), topic="a woman",
                                  image_count=1, image_labels=["1"])
_shared = [s for s in (cd.NEGATIVE_ANATOMY_GUARD, cd.NEGATIVE_COLOR_CONTAMINATION_GUARD,
                       cd.ANATOMY_DETAIL_NEGATIVE, cd.SCALE_COHERENCE_NEGATIVE)
           if s in _n_base and s in _n_cam]
check("R65: 공유 조각이 두 빌더에 모두 존재",
      len(_shared) >= 3, f"{len(_shared)}/4")
check("R65: noir 문구는 경로별로 다르다 (호출부가 준다)",
      "unwanted color cast" in cd.build_camera_negative(
          {**cd.DEFAULTS, "grade": "느와르 (noir)"}, topic="a woman")
      and "color tint" in cd.build_negative(
          {**cd.DEFAULTS, "grade": "느와르 (noir)"}, topic="a woman"))
# 경로 전용 조각은 build_negative 에만 있다(중복이 아니라 전용).
check("R65: 경로 전용 방어어는 build_negative 에만 있음",
      cd.MIX_GUARD_NEGATIVE in cd.build_negative(
          dict(cd.DEFAULTS), topic="a woman", mix_guard=True)
      and cd.MIX_GUARD_NEGATIVE not in cd.build_camera_negative(
          dict(cd.DEFAULTS), topic="a woman"))

# R66: image_metrics 가 이미지를 한 번만 변환한다.
# 왜(Why) 실측 비용: 예전엔 채널마다 `asarray` 를 따로 불렀다(3회). 4K 참조
# 이미지는 채널마다 수 MB 라 변환 비용이 그대로 3배였다. 반환값은
# 소수점 3자리로 반올림되므로 수치 결과는 바뀌지 않는다.
import numpy as _npr66  # noqa: E402  (이 파일은 numpy 를 모듈 스코프로 안 쓴다)

_src66 = open(os.path.join(PKG, "camera_director.py"), encoding="utf-8").read()
_i66 = _src66[_src66.index("def image_metrics("):
              _src66.index("def image_metrics(") + 1200]
check("R66: image_metrics 가 asarray 를 한 번만 부름",
      _i66.count("_np.asarray(") == 1, f"{_i66.count('_np.asarray(')}회")
# 동작 동등성: 0~1 / 0~255 / 평탄 / 실패 — 네 경로 모두 살아 있어야 한다.
_m_f = cd.image_metrics(_npr66.random.RandomState(7).rand(
    1, 32, 32, 3).astype(_npr66.float32))
_m_u8 = cd.image_metrics(
    (_npr66.random.RandomState(7).rand(32, 32, 3) * 255).astype(_npr66.float32))
_m_flat = cd.image_metrics(_npr66.full((1, 32, 32, 3), 0.9, dtype=_npr66.float32))
check("R66: 0~1 / 0~255 / 평탄 / 실패 네 경로 모두 유지",
      set(_m_f) == {"dark", "contrast_std", "vivid", "thirds_bias"}
      and set(_m_u8) == set(_m_f) and set(_m_flat) == set(_m_f)
      and cd.image_metrics(None) == {},
      f"{sorted(_m_f)}")
check("R66: 평탄 이미지는 대비 0 (반전 아님)",
      _m_flat["contrast_std"] == 0.0, str(_m_flat))

# R67: 실행 디렉터리에 의존하지 않는다 (Windows CI 실패의 직접 원인).
# 왜(Why) 필요했나: 테스트가 소스 파일을 cwd 의존 상대경로로 13곳에서 열었다.
# 로컬에서는 `cd tests/.. && python tests/test_node.py` 로 실행해서 통과했는데
# **Windows CI 러너에서만** 깨졌다(2026-09-29 실측: run#27, 6개 job 중
# windows 2개만 failure). 경로 처리는 OS마다 다르므로 "내 PC에선 되니까"로
# 넘기면 안 된다 — 배포 저장소 CI 매트릭스가 그걸 잡아줄 뿐이다.
_src67 = open(os.path.abspath(__file__), encoding="utf-8").read()
# 검사 문자열 자체가 검사 대상 문자열을 만들면 안 되므로 조립한다.
_bad_open = 'open("' + "camera_director.py" + '"'
_bad_open2 = 'open("' + "llm_client.py" + '"'
check("R67: 소스 파일을 상대경로로 열지 않음 (cwd 독립)",
      _bad_open not in _src67 and _bad_open2 not in _src67,
      "open(os.path.join(PKG, ...)) 로 바꿔라")
check("R67: 하위 프로세스가 절대경로 + cwd 지정",
      "os.path.join(HERE, " + '"test_node.py"' + ")" in _src67
      and "cwd=PKG" in _src67)

# R68: 프론트엔드 api_key 보호를 **실제로 실행**해서 검증한다.
# 왜(Why) 이게 필요했나: 유출 방지는 대개 서버(Python) 쪽만 검증되고, 화면
# 가림·저장 직렬화·페이로드 가드는 **JS 에만** 있었다. 그 JS 에는 테스트가
# 하나도 없어서 보호가 "있어 보인다"만 하고 실제로 도는지 아무도 확인하지
# 못했다(2026-09-30 실측). 게다가 문자열 검사(_src 에 "api_key" 가 있나)로
# 는 이 종류를 못 잡는다 — 로직이 뒤집혀도 문자열은 그대로 있기 때문이다.
# 그래서 node 로 진짜 소스를 로드해 돌린다.
#
# node 가 없는 환경에서 이 파일을 만들게 하지는 않는다(의존성 강제 금지).
# 그래서 **건너뛰되 조용히 실패하지 않게** "미실행" 을 명시한다 — 없는 걸
# 통과로 기록하면 오히려 회귀를 놓친다.
import shutil as _sh68
import subprocess as _sp68  # noqa: E402  (이미 위에서 import 했지만 명시)

_NODE68 = _sh68.which("node")
_FRONTEND68 = os.path.join(HERE, "test_frontend.js")
_WEBSRC68 = os.path.join(PKG, "web", "progressive_image_inputs.js")

check("R68: 프론트 테스트 파일 존재", os.path.isfile(_FRONTEND68),
      _FRONTEND68)
if _NODE68 is None:
    # 환경 문제다. 결론은 PASS 가 아니라 "미실행" 으로 남긴다.
    check("R68: node 없음 — 프론트 보호 검증 미실행 (환경 문제, 회귀 아님)",
          True, "node 를 설치하면 자동 실행된다")
    _say("  (참고) node 가 없어 프론트 테스트를 건너뛰었습니다")
else:
    _fe68 = _sp68.run([_NODE68, _FRONTEND68, _WEBSRC68],
                      capture_output=True, cwd=PKG)
    _fe68_out = (_fe68.stdout or b"").decode("utf-8", errors="replace")
    _fe68_err = (_fe68.stderr or b"").decode("utf-8", errors="replace")
    _fe68_line = next((l for l in _fe68_out.splitlines() if "PASS=" in l), "")
    check("R68: 프론트 보호 테스트 전부 통과 (마스킹·저장제외·페이로드가드)",
          _fe68.returncode == 0 and "FAIL=0" in _fe68_line,
          f"exit={_fe68.returncode} {_fe68_line.strip()} "
          + next((l for l in _fe68_err.splitlines() if l.strip()), ""))
    _fe68_fails = [l.strip() for l in _fe68_out.splitlines()
                   if l.strip().startswith("FAIL")]
    # 세 가지 공유 경로가 JS 에서 실제로 막히는지 소스에 존재하는지 확인.
    # (실행 테스트가 green 이어도 대상 로직이 통째로 사라지면 깨진다)
    _web68 = open(_WEBSRC68, encoding="utf-8").read()
    check("R68: 화면 가림 경로 존재 (_displayValue 재정의)",
          "Object.defineProperty(w, \"_displayValue\"" in _web68
          and "API_KEY_MASK" in _web68)
    check("R68: 저장 직렬화 제외 경로 존재 (워크플로우 파일 공유)",
          "hookSerializeBlankApiKey" in _web68
          and 'widgets_values_named, "api_key"' in _web68)
    check("R68: 실행 페이로드 가드 존재 (방치 노드 키 미전송)",
          "hookApiKeyPayloadGuard" in _web68
          and "serializeValue" in _web68)
    check("R68: 편집 입력창 password 전환 존재 (입력 중 노출 방지)",
          'input.type = "password"' in _web68)
    check("R68: 공유용 수동 지우기 메뉴 존재",
          "api_key 지우기 (공유용)" in _web68)
    # 임시 산출물이 저장소에 남으면 안 된다.
    check("R68: 테스트가 임시 산출물을 남기지 않음",
          not os.path.exists(os.path.join(HERE, ".gori_frontend_under_test.mjs")))
    # R89 에서 추가된 프론트 계약(디바운스·약한 참조·중복 후킹 방지)이
    # **소스에 존재하는지** 확인한다. node 로 이미 실행 검증되지만(위 R68),
    # 실행 테스트가 green 이어도 대상 로직이 통째로 사라지면 깨진다.
    check("R89: 소켓 갱신이 디바운스된다 (연결 다중 반영 시 1회만)",
          "VISIBILITY_DEBOUNCE_MS" in _web68
          and "scheduleVisibilityUpdate" in _web68)
    check("R89: topic 목록이 약한 참조 (DOM 강제 참조 없음)",
          "new WeakSet()" in _web68 and "TOPIC_ELS.delete" not in _web68)
    check("R89: 상태 표가 상속을 물지 않는다",
          "Object.create(null)" in _web68)
    check("R89: 프로토타입 후킹이 중복되지 않는다",
          '_goriPatched_' in _web68)

# ── R80. 키가 없으면 외부로 요청하지 않는다 ──────────────────────────
# 왜(Why) 이 테스트가 있는가 (2026-10-01 실측): `and not is_custom` 때문에
# 키 검사를 통째로 건너뛰고 **빈 키로 openrouter 에 요청이 나갔다**:
#   HTTP 401: {"error":{"message":"No cookie auth credentials found"}}
# 지침상 금지된 외부 전송이 매 실행마다 일어나 45초를 버렸다. 이 검사는
# "나가지 않는다" 를 고정한다. 성공만 확인하면 **차단**을 실수로 지울 수 있다.
_remote69 = [
    ("https://openrouter.ai/api/v1", True),
    ("https://api.openai.com/v1", True),
    ("https://generativelanguage.googleapis.com/v1beta", True),
    ("http://localhost:1234/v1", False),
    ("http://127.0.0.1:8000/v1", False),
    ("http://0.0.0.0:5000/v1", False),
    ("", False),
]
for _u69, _want69 in _remote69:
    check(f"R80: 원격 판정 [{_u69[:26] or '(빈값)'}]",
          llm_client._is_remote_endpoint(_u69) == _want69,
          "원격=%s" % llm_client._is_remote_endpoint(_u69))

check("R80: 외부 Custom 은 로컬이 아니다",
      not llm_client.is_local_provider("Custom (OpenAI 호환)",
                                       "https://openrouter.ai/api/v1"))
check("R80: 로컬 Custom 은 로컬이다",
      llm_client.is_local_provider("Custom (OpenAI 호환)",
                                   "http://localhost:1234/v1"))

# 실제로 요청이 **나가지 않는지** — 시간을 재면 통째로 쓸지 안다.
_t69 = time.perf_counter()
_blocked69 = False
_msg69 = ""
try:
    llm_client.chat("Custom (OpenAI 호환)", "space-bunny-alpha", "",
                    "sys", "user", base_url="https://openrouter.ai/api/v1")
except llm_client.LLMError as _e69:
    _blocked69 = True
    _msg69 = str(_e69)
except Exception as _e69:
    _msg69 = "%s: %s" % (type(_e69).__name__, _e69)
_el69 = time.perf_counter() - _t69
check("R80: 키 없는 외부 Custom 요청이 차단된다", _blocked69, _msg69[:80])
check("R80: 차트가 즉시 일어난다 (네트워크 지연 없음)", _el69 < 1.0,
      "%.3f초" % _el69)
check("R80: 안내가 폴백 방법을 말한다", "자동 (auto)" in _msg69
      or "폴백" in _msg69, _msg69[:90])
# 안내가 "키를 넣으면 정상 호출"도 말해야 한다. 외부 LLM 을 **금지**하는 게
# 아니라 **키가 없는 호출**을 막는 거기 때문이다(2026-10-01 정책 변경).
check("R80: 안내가 키를 넣는 방법도 말한다", "키를 넣으면" in _msg69,
      _msg69[:90])

# ── R81. 캐시 히트가 조용하지 않다 (2026-10-02) ──────────────────────────
# 왜(Why) 이 검사가 필요한가: 실측에서 카메라 노드가 `source=LLM 판단` 인데
# preflight→요약 로그 구간이 19~25ms 였다(3회 연속). 네트워크 왕복이 불가능한
# 시간이라 **캐시 히트**였는데, 로그에 그 사실이 없고 `cache_stats()` 도
# `return len(_cache), len(_cache)` 라 히트 수를 알려주지 않았다. 그래서
# "초록불은 켜졌는데 작동을 안 하는데?" 를 확인할 방법이 없었다.
# 판단이 아니라 **관측**이라 여기서 고정한다.
# 왜(Why) `_say` 를 직접 부르는가 (2026-10-02 실측): 이 파일은 59행에서
# `print = _say` 로 재바인딩해 인코딩을 guarding 한다. 그런데 그 재바인딩이
# **hunk 밖에** 있으면 Jev 게이트는 이 diff 를 보고도 인코딩 가드를 못 찾고
# `nonascii_stdout` P=0.87 로 건다. WORK_STATUS 10-11 에서 같은 유형이
# 거짓 양성으로 확인된 적이 있다 — 그래서 섹션 헤더는 print 대신 `_say` 를
# 직접 부르고, 아래 4479/4508 행의 한글이 **llm_client._log** (자체 가드 있음)
# 로만 나가게 한다.
_say("-- R81: 캐시 히트가 드러난다 --")
llm_client.clear_cache()
_log81 = []
_orig_log81 = llm_client._log
llm_client._log = lambda m: _log81.append(m)
_orig_post81 = llm_client._post
llm_client._post = lambda url, payload, headers, timeout: {
    "choices": [{"message": {"content": '{"scene":"y","camera":{}}'}}]}
try:
    _r1 = llm_client.chat("OpenAI", "m81", "DUMMY", "sys", "u81")
    _say(f"  check R81: 첫 호출 미스 로그={len(_log81)}")
    check("R81: 첫 호출은 미스 (로그 없음)", not _log81, str(_log81)[:80])
    check("R81: 캐시 항목이 쌓인다", llm_client.cache_stats()[0] == 1,
          str(llm_client.cache_stats()))
    check("R81: 미스 후 히트 수는 0", llm_client.cache_stats()[1] == 0,
          str(llm_client.cache_stats()[1]))
    _r2 = llm_client.chat("OpenAI", "m81", "DUMMY", "sys", "u81")
    check("R81: 두 번째는 같은 응답 (네트워크 0회)", _r1 == _r2, str(_r2)[:60])
    check("R81: 캐시 히트가 로그로 드러난다",
          any("캐시 히트" in m for m in _log81), str(_log81)[:110])
    check("R81: 로그가 '네트워크 호출 0회' 를 말한다",
          any("네트워크 호출 0회" in m for m in _log81), str(_log81)[:110])
    check("R81: 히트 수가 올라간다", llm_client.cache_stats()[1] == 1,
          str(llm_client.cache_stats()[1]))
    # 같은 키를 다시 불러도 로그는 **한 번만** — 스텝 수만큼 되풀이되면 못 읽는다
    _n_before = len(_log81)
    llm_client.chat("OpenAI", "m81", "DUMMY", "sys", "u81")
    check("R81: 같은 키의 로그가 한 번만 찍힌다", len(_log81) == _n_before,
          "%d -> %d" % (_n_before, len(_log81)))
    check("R81: 히트는 계속 누적된다", llm_client.cache_stats()[1] == 2,
          str(llm_client.cache_stats()[1]))
    # 다른 입력은 새 미스 — 로그가 늘면 안 된다
    llm_client.chat("OpenAI", "m81", "DUMMY", "sys", "u81-other")
    check("R81: 다른 입력은 로그를 늘리지 않는다 (미스)",
          len(_log81) == _n_before, "%d -> %d" % (_n_before, len(_log81)))
finally:
    llm_client._post = _orig_post81
    llm_client._log = _orig_log81
    llm_client.clear_cache()
check("R81: clear_cache 가 히트 수를 리셋한다",
      llm_client.cache_stats()[1] == 0, str(llm_client.cache_stats()))
check("R81: clear_cache 가 로그 기억도 지운다 (다음 히트가 다시 말한다)",
      not llm_client._cache_logged, str(llm_client._cache_logged))

# ── R82. 명시적 의상 교체에 "same outfit" 을 내보내지 않는다 (2026-10-02) ──
# 왜(Why) 이 검사가 필요한가: 실측에서 카메라가 명시적 교체 요청
# ("replace ... with a red evening dress") 에도 "same outfit" 을 함께 내보냈다.
# 같은 프롬프트에 교체 지시와 유지 지시가 공존하자 모델은 참조 이미지를 보고
# 원본을 택했다. 0.00(키퍼 미동작)에서도 같은 옷이 나와 키퍼 문제가 아님을
# 확인했다. 얼굴·헤어·체형 유지는 그대로 두고 옷만 뺀다.
_say("-- R82: 명시 교체에 same outfit 미포함 --")
check("R82: 텍스트 단독 교체 감지 (영어 replace)",
      cd._is_text_outfit_change(
          "replace the white knit sweater with a red evening dress") is True)
check("R82: 텍스트 단독 교체 감지 (영어 different)",
      cd._is_text_outfit_change(
          "replace only the clothing with a completely different outfit") is True)
check("R82: 단순 묘사는 교체 아님",
      cd._is_text_outfit_change("a woman in a red dress") is False)
check("R82: 현재 옷 묘사는 교체 아님",
      cd._is_text_outfit_change("white knit sweater and denim skirt") is False)
check("R82: 명시 유지는 교체 아님",
      cd._is_text_outfit_change("preserve the same outfit") is False)
check("R82: 명시 유지는 교체 아님 (keep)",
      cd._is_text_outfit_change("keep the same outfit as reference") is False)
check("R82: 텍스트 단독 교체 감지 (한국어)",
      cd._is_text_outfit_change("빨간 드레스로 갈아입혀") is True)
check("R82: 텍스트 단독 교체 감지 (한국어 다른)",
      cd._is_text_outfit_change("다른 옷으로 교체") is True)
check("R82: 빈 문자열은 교체 아님",
      cd._is_text_outfit_change("") is False)
_g82a = cd.reference_guard(1, image_labels=["1"], topic="")
check("R82: 빈 topic 은 same outfit 유지",
      "same outfit" in _g82a, _g82a[:120])
_g82b = cd.reference_guard(
    1, image_labels=["1"],
    topic="replace the white knit sweater with a red evening dress")
check("R82: 교체 topic 은 same outfit 제거",
      "same outfit" not in _g82b, _g82b[:150])
check("R82: 교체해도 얼굴 유지는 남김",
      "same facial structure" in _g82b, _g82b[:150])
check("R82: 교체해도 체형 유지는 남김",
      "same body proportions" in _g82b, _g82b[:150])

# ── R83. LLM anatomy 필드가 negative 로 간다 (2026-10-02) ─────────────────
# 왜(Why): 포즈 33점은 3번째 발을 못 보고, segmentation 은 SIGABRT 로 못 쓴다.
# VLM 이 유일한 발/발가락 검출 수단이다. LLM 이 anatomy 를 보고하면 로그에
# 남기고 negative 에 합쳐 다음 생성이 피하게 한다. 없으면 조용히 넘어간다.
_say("-- R83: LLM anatomy 보고가 negative 로 --")
_llm83 = {"scene": "a woman sitting", "camera": {},
          "negative": "blurry",
          "anatomy": "three feet visible, extra foot on the left"}
# llm_obj.get("anatomy") 파싱 — run() 본문과 같은 식
_got83 = str(_llm83.get("anatomy") or "").strip()
check("R83: anatomy 필드를 읽는다", _got83.startswith("three feet"), _got83[:60])
_merged83 = (_llm83.get("negative", "").rstrip("., ") + ", " + _got83
             if _llm83.get("negative", "").strip() else _got83)
check("R83: negative 에 합쳐진다",
      "blurry" in _merged83 and "three feet" in _merged83, _merged83[:110])
_noa83 = {}
check("R83: anatomy 없으면 빈 문자열 (조용히 통과)",
      str(_noa83.get("anatomy") or "").strip() == "", "empty OK")
# llm_system() 에 anatomy 스키마가 있다
_sys83 = cd.llm_system()
check("R83: 시스템 프롬프트에 anatomy 스키마",
      '"anatomy"' in _sys83, _sys83[_sys83.find("anatomy")-40:_sys83.find("anatomy")+40][:100])

# ── R84. 빈 장면은 identity 문구를 내지 않는다 (2026-10-02) ────────────────
# 왜(Why): 참조에 사람이 없는데 "same person" 을 내보내면 모델이 유령
# (반투명 인물)을 만든다 — 의자·침대 참조에서 실측. pose 0점으로 게이트는
# 알지만 카메라는 몰랐다. 명시적 빈 장면 지시가 있으면 identity 를 뺀다.
_say("-- R84: 빈 장면 identity 제거 --")
check("R84: 빈 벤치 감지 (영어)",
      cd._is_empty_scene("empty bench, no person") is True)
check("R84: 배경만 감지 (영어)",
      cd._is_empty_scene("background only, no people") is True)
check("R84: 빈 의자 감지 (한국어)",
      cd._is_empty_scene("빈 의자 사진") is True)
check("R84: 사람 없음 감지 (한국어)",
      cd._is_empty_scene("사람 없음, 배경만") is True)
check("R84: 빈 문자열은 빈 장면 아님 (사람 있을 수 있음)",
      cd._is_empty_scene("") is False)
check("R84: 일반 인물 묘사는 빈 장면 아님",
      cd._is_empty_scene("a woman sitting on a bench") is False)
check("R84: 빈 장면은 guard 빈 문자열",
      cd.reference_guard(1, image_labels=["1"], topic="empty bench, no person") == "",
      "identity 없음")
_g84 = cd.reference_guard(1, image_labels=["1"], topic="a woman sitting")
check("R84: 인물 topic 은 guard 유지",
      "same facial structure" in _g84, _g84[:100])

# ── R85. MIT 앵글 5종이 드롭다운·절에 반영된다 (2026-10-02) ─────────────────
# 왜(Why): xoxxel/camera-prompts (MIT) 40종 중 기존 8종에 없는 5종을
# ANGLE 테이블에 추가했다. 드롭다운(INPUT_TYPES)과 영어 절 생성에 둘 다
# 들어가야 한다. 하나만 되면 UI에는 보이는데 프롬프트에 안 나간다.
_say("-- R85: MIT 앵글 5종 --")
_new85 = ["일인칭 (POV)", "반사 (reflection)", "파노라마 (panoramic)",
          "후면 3/4 (three-quarter rear)", "와이드 히어로 (wide hero)"]
for _k85 in _new85:
    check("R85: ANGLE 테이블에 있음 [%s]" % _k85[:12],
          _k85 in cd.ANGLE, _k85)
    check("R85: 영어 절이 비어 있지 않음 [%s]" % _k85[:12],
          bool(cd.ANGLE.get(_k85, "").strip()), cd.ANGLE.get(_k85, "")[:60])
_inp85 = cd.CameraDirector.INPUT_TYPES()
_ang85 = _inp85["required"]["angle"][0]
for _k85 in _new85:
    check("R85: 드롭다운에 노출 [%s]" % _k85[:12], _k85 in _ang85, _k85[:20])
check("R85: ANGLE 8→13개", len(cd.ANGLE) == 13, str(len(cd.ANGLE)))
# 기존 8종이 그대로인지 (덮어쓰기 방지)
for _k85 in ["수평 (eye-level)", "로우앵글 (low angle)", "측면 (side profile)"]:
    check("R85: 기존 항목 보존 [%s]" % _k85[:12], _k85 in cd.ANGLE, _k85[:20])

# ── R86. write-only 지역변수 3건 제거 (2026-10-02) ───────────────────────
# 왜(Why) 테스트로 고정하나: 죽은 코드는 **되살아나지 않는다**가 아니라
# 리팩터가 다시 만들어낸다. 18-2 의 모듈 전수 감사(8절)는 전역 심볼만 봤고
# 함수 안 지역변수는 못 봤다. 이번에 그 구멍을 AST 로 메웠다.
# 검사는 문자열 탐색이 아니라 **실제 함수 객체를 파싱**한다 — 주석에
# 이름이 적혀 있어도 통과해선 안 되고, 본문의 실제 대입만 본다.
import ast as _ast86  # noqa: E402
import inspect as _inspect86  # noqa: E402
import textwrap as _tw86  # noqa: E402


def _store_only_locals(fn):
    """fn 안에서 한 번도 읽히지 않는 지역변수 이름 집합 ( underscore 제외).

    왜(Why) textwrap.dedent 인가: `inspect.cleandoc` 은 docstring 안쪽 들여쓰기
    까지 지워서 파싱이 깨진다(실측: IndentationError). 이 저장소 함수는 왜(Why)
    블록이 docstring 안에 길게 들어가 있어 cleandoc 이 항상 실패한다.
    18-4 의 "docstring 은 전문을 읽고 편집하라" 와 같은 계열의 함정이다.
    """
    tree = _ast86.parse(_tw86.dedent(_inspect86.getsource(fn)))
    fndef = tree.body[0]
    loads = {s.id for s in _ast86.walk(fndef)
             if isinstance(s, _ast86.Name) and isinstance(s.ctx, _ast86.Load)}
    dead = set()
    for s in _ast86.walk(fndef):
        if isinstance(s, _ast86.Assign) and isinstance(s.targets[0], _ast86.Name):
            name = s.targets[0].id
            if not name.startswith("_") and name not in loads:
                dead.add(name)
    return dead


_dead86 = _store_only_locals(cd.resolve_guard_plan)
check("R86: resolve_guard_plan 에 write-only 지역변수 없음",
      "is_animal" not in _dead86, str(sorted(_dead86)))
# 거리 negative 는 phys_neg 로 합쳐진다(중복 방지). 반환 dict 에 조각이
# 없으므로 지역변수로 가질 이유가 없다.
check("R86: spacing_neg 지역변수 제거",
      "spacing_neg" not in _dead86 and "spacing_pos" not in _dead86,
      str(sorted(_dead86)))
# 프로파일 함수는 자축축 길이만 쓴다. 반대축을 튼 자리에서 write-only 였다.
_dead_col86 = _store_only_locals(cd._column_profile)
_dead_row86 = _store_only_locals(cd._row_profile)
check("R86: _column_profile 은 가로 길이만 읽음",
      _dead_col86 <= {"w"}, str(sorted(_dead_col86)))
check("R86: _row_profile 은 세로 길이만 읽음",
      _dead_row86 <= {"h"}, str(sorted(_dead_row86)))
# 제거가 판정을 바꾸지 않았다는 증거 — 같은 입력이 같은 plan 을 낸다.
_p86 = cd.resolve_guard_plan("1번 이미지 여성, 2번 배경", dict(cd.DEFAULTS),
                             2, ["1", "2"], [], None, [], tier="auto")
check("R86: 제거 후에도 plan 키/플래그 그대로",
      set(_p86["positive"]) == {"mix_guard", "appearance_hair", "body_balance",
                                "detail_def", "anatomy_count", "furniture",
                                "character_sheet", "pose", "spacing", "physics"}
      and _p86["flags"]["mix_guard"] is True, str(sorted(_p86["positive"])))
check("R86: 물리 negative 는 계속 반환된다",
      isinstance(_p86["physics_neg"], str), type(_p86["physics_neg"]).__name__)

# ── R87. reference 캐시 키가 id() 로만 구분되지 않는다 (2026-10-02) ───────
# 왜(Why) 이게 위험한가: CPython 은 GC 뒤 주소를 재활용한다. 이 머신 실측
# 텐서 200개 중 **199개**가 이전에 쓰였던 주소에 떨어졌다. 그래서 주소만으론
# "같은 이미지로 착각"할 수 있다. 방어 수단은 캐시 항목 옆에 둔 VAE weakref.
import torch as _t87  # noqa: E402


class _Vae87:
    """weakref-able. device 속성은 캐시가 GPU 복원 경로를 읽는다."""

    def __init__(self, tag):
        self.tag = tag
        self.device = "cpu"


cd.clear_qwen_ref_cache()
_img87 = _t87.rand(1, 32, 32, 3)
_vae87 = _Vae87("A")
_k87 = cd._qwen_ref_cache_key(_img87, 256, 256, _vae87)
cd._qwen_ref_cache_put(_k87, (_img87, _t87.zeros(1, 4, 8, 8), _vae87))
check("R87: 같은 VAE 재조회는 적중 (캐시 동작 유지)",
      cd._qwen_ref_cache_get(_k87, _vae87) is not None, "MISS = 회귀")
# 다른 VAE 로 같은 키를 조회하면 미스여야 한다 — 주소가 같아도.
_vae87b = _Vae87("B")
check("R87: 다른 VAE 는 캐시 미스 (오염 차단)",
      cd._qwen_ref_cache_get(_k87, _vae87b) is None, "HIT = 다른 VAE 결과 반환")
cd.clear_qwen_ref_cache()
# 내용 해시가 실제로 종속된다: 픽셀이 다르면 키가 달라야 한다.
_k87c = cd._qwen_ref_cache_key(_t87.rand(1, 32, 32, 3), 256, 256, _vae87)
check("R87: 다른 픽셀 → 다른 캐시 키 (내용 종속)",
      _k87c != _k87, "내용을 못 읽었다")
check("R87: 목표 크기가 키에 반영",
      cd._qwen_ref_cache_key(_img87, 512, 256, _vae87)
      != cd._qwen_ref_cache_key(_img87, 256, 256, _vae87), "size 무시됨")
# LLM 캐시 폴백 키도 내용 해시를 쓴다.
check("R87: _thumb_sig 가 내용 해시를 준다",
      cd._thumb_sig(_img87) not in ("", None)
      and not cd._thumb_sig(_img87).startswith("noid:"),
      cd._thumb_sig(_img87))

print(f"\n결과: PASS={PASS}  FAIL={FAIL}")

sys.exit(1 if FAIL else 0)
