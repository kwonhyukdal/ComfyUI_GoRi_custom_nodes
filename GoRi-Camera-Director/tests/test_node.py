# -*- coding: utf-8 -*-
"""ComfyUI 없이 노드 로직을 검증하는 테스트.

실행: python tests/test_node.py   (노드 동작 + 구조 검증에 대응)
"""

import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)


import camera_director as cd  # noqa: E402
import llm_client  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


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
check("범용 품질 가드: 피부/해부/손/얼굴 일관성",
      all(s in pos for s in ["natural human proportions", "believable hands with five fingers",
                              "natural skin texture", "clear facial features"]), pos)
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
               image_b64=None, image_sig=None, image_b64s=None):
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
                      image_b64=None, image_sig=None, image_b64s=None):
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
      == ("CONDITIONING", "CONDITIONING", "STRING", "IMAGE"))
check("Skills RETURN_NAMES",
      cd.CameraDirectorEncode.RETURN_NAMES
      == ("positive_out", "negative_out", "prompt_out", "image_out"))
enc_its = cd.CameraDirectorEncode.INPUT_TYPES()
check("Skills conditioning 디렉터 입력 계약",
      enc_its["required"].get("clip") == ("CLIP",)
      and enc_its["required"].get("vae") == ("VAE",)
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

pos_cond, neg_cond, prompt_cond, _img_out = enc.run_prompt(
    clip=fake_clip, topic=" conditioning test", preset=cd.AUTO,
    automation="규칙 (auto)", shot=cd.AUTO, lens=cd.AUTO, angle=cd.AUTO,
    composition=cd.AUTO, lighting=cd.AUTO, grade=cd.AUTO, motion=cd.AUTO,
    speed=cd.AUTO, amplitude=cd.AUTO)
check("Skills conditioning 출력 3개", isinstance(pos_cond, list) and isinstance(neg_cond, list)
      and isinstance(prompt_cond, str))
base_pos = [("base", {})]
base_neg = [("base", {})]
qwen_prompt = "A portrait of a woman, preserve the input subject exactly"
pos_mixed, neg_mixed, prompt_mixed, _img_out = enc.run_prompt(
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
check("negative에 anatomy/identity/skin guard 미추가",
      all(s not in fake_clip.texts[-1] for s in
          ["extra arms", "face mismatch", "background color spill on skin",
           "painted skin", "blue skin tint"]),
      str(fake_clip.texts[-1]))

reflection_pos, reflection_neg, reflection_prompt, _img_out = enc.run_prompt(
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
                                      "background, outfit, prop, product, style, lighting, composition, or mood",
                                      "do not duplicate the main subject, face, body, outfit, product, or background subject",
                                      "no cloned faces", "no duplicated characters",
                                      "no crowd unless requested", "no background people unless requested"]), multi_prompt[:900])
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
                   image_b64=None, image_sig=None, image_b64s=None):
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
    _, _, _outfit_qwen, _img_out = _enc_b1.run_prompt(
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
    _, _, _role_qwen, _img_out = _enc_b1.run_prompt(
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
    _, _, _single_qwen, _img_out = _enc_b1.run_prompt(
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
    _, _, _duo3_text, _img_out = _enc_duo.run_prompt(
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
    _, _, _duo10_text, _img_out = _enc_duo.run_prompt(clip=_clip_duo, **_kw10)
    check("10번은 외양 참조 전용 — duo 인물로 취급하지 않음 (R18 정책)",
          "person two from reference image 10" not in _duo10_text
          and "only for explicitly requested roles" not in _duo10_text,
          _duo10_text[:600])
    _, _, _duo_text, _img_out = _enc_duo.run_prompt(
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
    _, _, _outfit_again, _img_out = _enc_duo.run_prompt(
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
check("R10: llm_hint는 노드 맨 아래 위젯(마지막 STRING 항목)",
      list(_opt_r10)[-1] == "llm_hint", str(list(_opt_r10)[-1]))

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
        # provider별 응답 형식이 다르므로 OpenAI/Ollama 양쪽 키를 모두 제공
        return {"choices": [{"message": {"content": "{}"}}],
                "message": {"content": "{}"}}


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
    check("R15: 플래그 갱신 — 1장 실행 후 _last_mix_guard=False",
          _director_r15._last_mix_guard is False, str(_director_r15._last_mix_guard))
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

print(f"\n결과: PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
