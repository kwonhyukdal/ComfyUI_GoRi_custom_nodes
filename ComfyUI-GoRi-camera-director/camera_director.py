# -*- coding: utf-8 -*-
"""camera_director.py — Camera Director 노드 본체.

주제 한 줄(한글 OK) + 프리셋/자동화(tier) → 카메라 조항이 포함된
영문 prompt_out 문자열과 positive/negative conditioning을 출력한다.

합의된 규칙:
- 텍스트 경로만 관여 (model/latent 경로 무관)
- 자동화 tier: auto(규칙, **기본**) / llm(AI 판단) / manual(수동) — llm 실패 시 auto 폴백
  왜(Why) 기본이 auto 인가: LLM 을 쓰면 키가 필요하고 원본 이미지가 외부로
  나간다. 기본값을 llm 으로 두면 API 키 없는 사람이 매 실행마다 실패한다.
- 프리셋 우선순위: 특정 프리셋 > 직접 설정(드롭다운) > 자동(auto: tier 판정)
- 출력 영문, 라벨 한글, 콘솔 로그 한글
"""

from __future__ import annotations

# 이 노드의 독립 버전. 팩(pyproject.toml) 버전과 별개로 간다.
# 왜(Why) future import 다음인가: `from __future__` 는 docstring 바로 다음에
# 와야 한다 (SyntaxError). 버전 상수는 그 뒤 첫 코드다.
# 왜(Why) 노드마다 따로인가 (2026-10-02): 팩은 여러 노드를 한 번에 배포하는
# 관리 단위일 뿐이다. 카메라만 고쳤는데 팩 버전을 올리면 키퍼도 바뀐 것처럼
# 보인다. 각 노드는 자기 변경에만 버전을 올린다. 새 노드를 만들면 첫날부터
# __version__ 을 둔다 (test_pack.py 가 강제한다).
# 버전 상수는 **이 한 곳에만** 둔다 (2026-10-07 라운드 2): 이 파일에 같은
# 값이 두 번 대입돼 있었고, 갱신 때 한쪽만 올리면 어긋난 채로 배포된다.
__version__ = "1.9.16"


import json
import os
import re
import sys
import threading
import time
import uuid
import weakref

try:
    from . import llm_client
except ImportError:  # 스탠드얼론/테스트 실행용
    import llm_client

# ---------------------------------------------------------------------------
# 기능별 분리 모듈 (2026-10-07 refactor)
#   cam_util    공용 로그·로더 / cam_tables 카메라 조항 테이블
#   cam_subject 주제 분류·역할 판정 / cam_anchors 앵커 문구
#   cam_guards  가드 문구 / cam_physics 물리 가드 / cam_spacing 간격
#   cam_sheet   시트 판별 / cam_llm LLM·키
# 아래 * import 는 이 파일의 공개 표면을 그대로 유지한다 (테스트·호출자가
# camera_director.<이름> 으로 접근하는 계약).
# ---------------------------------------------------------------------------
try:
    from .cam_util import *  # noqa: F403
    from .cam_tables import *  # noqa: F403
    from .cam_subject import *  # noqa: F403
    from .cam_anchors import *  # noqa: F403
    from .cam_guards import *  # noqa: F403
    from .cam_physics import *  # noqa: F403
    from .cam_spacing import *  # noqa: F403
    from .cam_sheet import *  # noqa: F403
    from .cam_llm import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
    from cam_tables import *  # noqa: F403
    from cam_subject import *  # noqa: F403
    from cam_anchors import *  # noqa: F403
    from cam_guards import *  # noqa: F403
    from cam_physics import *  # noqa: F403
    from cam_spacing import *  # noqa: F403
    from cam_sheet import *  # noqa: F403
    from cam_llm import *  # noqa: F403


def _latent_mp(latent_image) -> float | None:
    """sampling latent의 메가픽셀. 알 수 없으면 None (점검 생략)."""
    try:
        samples = latent_image.get("samples") if isinstance(latent_image, dict) else None
        if samples is None or getattr(samples, "ndim", None) != 4:
            return None
        h, w = int(samples.shape[-2]) * 16, int(samples.shape[-1]) * 16
        return (h * w) / 1e6
    except Exception:
        return None


def _num_or_zero(v) -> float:
    """위젯 수치 정규화. NaN·비수치는 0(검사 안 함)으로."""
    try:
        f = float(v)
        if f != f:  # NaN
            return 0
        return f
    except (ValueError, TypeError):
        return 0


def preflight_warnings(_topic: str, camera: dict, latent_mp=None,
                       steps: int = 0, cfg: float = 0.0,
                       denoise: float = 0.0) -> list:
    """출발 전 점검. 깨질 조합이면 경고 문구 목록 (0·빈값은 검사 안 함).

    왜(Why) 첫 인자가 `_topic` 인가: 시그니처 호환용으로 받지만 본문에서 쓰지
    않는다 (경고는 카메라·수치 조합만 본다). 호출부가 전부 positional 이라
    안전하다. 지우면 호출부 14곳을 함께 고쳐야 해서 남긴다.

    왜(Why): 얼굴 클로즈업+저해상도, 극단 CFG/스텝, 과다 denoise는 실행 전에
    알 수 있는 확정 실패다. 모델 천장·시드 운은 여기서 못 잡는다.
    순수 함수라 테스트가 직접 검증한다.
    """
    msgs = []
    try:
        steps = _num_or_zero(steps)
        cfg = _num_or_zero(cfg)
        denoise = _num_or_zero(denoise)
        shot = (camera or {}).get("shot", "")
        if (latent_mp is not None and shot in FACE_CRITICAL_SHOTS
                and latent_mp < 1.0):
            msgs.append(
                f"얼굴 클로즈업({shot})인데 latent가 작음({latent_mp:.1f}MP) — "
                "얼굴 뭉개짐 주의, 1MP 이상 권장")
        if steps and (steps < 8 or steps > 150):
            msgs.append(f"steps={steps} 범위 이탈 (8~150 권장) — 결과 불안정 가능")
        if cfg and (cfg < 1.0 or cfg > 12.0):
            msgs.append(f"cfg={cfg} 범위 이탈 (1.0~12.0 권장) — 파손·뻣뻣함 주의")
        if denoise and not 0.0 < denoise <= 1.0:
            msgs.append(f"denoise={denoise} 범위 이탈 (0 초과 1 이하)")
        elif denoise and denoise > 0.9:
            # 왜(Why): "주의"만으로는 사용자가 무엇을 바꿔야 하는지 모른다.
            # 실측에서 denoise=1.0 + 참조 이미지 조합은 다리·팔·어깨 같은
            # 세부가 필요한 부위부터 뿌옇게 뭉개졌다. denoise는 "얼마나 다시
            # 그릴 것인가"이므로 낮을수록 원본 픽셀을 보존한다.
            msgs.append(
                f"denoise={denoise} 과다 — 원본 픽셀을 거의 안 써서 다시 그립니다. "
                "참조 이미지의 형태·색·디테일이 살아남으려면 0.6~0.8을 권장 "
                "(1.0은 완전히 새로 생성 → 다리·팔·어깨·손 같은 세부가 "
                "먼저 뭉개지고 가구 형태도 원본에서 벗어납니다)")
    except Exception:
        pass
    return msgs


# ---------------------------------------------------------------------------
# 노드
# ---------------------------------------------------------------------------

def resolve_guard_plan(subject_text, _camera, image_count, image_labels,
                       image_items, primary_image, _reference_images,
                       tier="", llm_hint=""):
    """한 실행의 가드 판정을 **한 곳에서** 모아서 돌려준다.

    왜(Why) `_camera`·`_reference_images` 는 받기만 하나: 예전 리팩터 전에는
    여기서 썼다. 지금 본문은 subject_text·개수·라벨·tier·hint 만 본다.
    호출부가 전부 positional 이라 안전하다. 시그니처를 줄이면 호출부 2곳과
    테스트 5곳을 함께 고쳐야 해서 남긴다.

    왜(Why) 이 함수를 만드는가(2026-09-29):
    `run()` 과 `run_prompt()` 가 같은 가드 판정을 각자 반복하면서 결과를
    `self._last_*` 속성으로 넘겨 받아 쓰고 있었다. 판정식이 두 벌이었고,
    **한쪽만 갱신되면 positive/negative 짝이 어긋나** 짝인 방어가 조용히
    사라졌다(2026-09-28 실측: 국가 표현형·동물 가드가 positive 에만 붙고
    negative 에 사라짐). CLAUDE.md 에도 "둘을 손으로 동기화한다"고 적혀 있었다.

    이제 판정은 여기 한 벌이고, 호출부는 이 dict 의 positive/negative 조각을
    그대로 합치기만 한다. 갱신 누락이 구조적으로 불가능해진다.

    반환 dict 의 조각은 모두 문자열이고, 빈 문자열은 "미적용"을 뜻한다.
    로그는 이 함수가 아니라 호출부가 낸다 — 로그 문구는 경로마다 다르다.
    """
    text = subject_text or ""
    is_human = _is_human_subject(text)
    labels = list(image_labels or [])

    # 다중 참조(2장 이상)면 믹스 변형 가드를 양쪽에 자동 첨부.
    mix_guard = image_count >= 2
    # 인물 신체 발란스: 인물 주제면 참조 유무와 무관하게 상시.
    body_balance = is_human
    # 부위별 디테일 경계: 인물 + 참조 이미지 실행일 때만.
    detail_def = is_human and image_count >= 1
    # 부위 개수(손가락 5·발가락 5·양팔·양다리) 명시. 인물 주제면 항상.
    anatomy_count = is_human
    # llm_hint 방어어는 LLM 판정이 실제로 이뤄진 실행에만.
    hint_defense = tier == "llm" and bool((llm_hint or "").strip())

    # 포즈 참조: topic에 포즈 역할이 명시된 슬롯.
    pose_slots = _pose_role_slots(text) & set(labels)
    pose_pos = _pose_reference_guard(pose_slots)
    # 물리·공간: topic의 접촉/동작 동사 → 이미지의 물리 상태.
    phys_pos, phys_neg = physics_contact_guard(text)
    # 픽셀 공간 측정: topic에 접촉 동사가 없어도 참조에서 거리를 읽는다.
    # 거리 지사는 topic 동사가 있을 때 중복되므로 생략하고 negative 만 보강.
    # 왜(Why) spacing_neg 이 없는가(2026-10-02 실측): 거리 negative 는 이미
    # phys_neg 에 합쳐진다(아래 3줄). 여기 다시 담으면 같은 문구가 두 벌로
    # 들어가고, 반환 dict 에는 조각이 없어 읽을 곳이 없다 — write-only 였다.
    spacing_pos = ""
    spacing_measure = None
    if image_count >= 2:
        spacing_measure = subject_spacing(primary_image)
        _sp_pos, _sp_neg = spacing_guard(spacing_measure, text)
        if phys_pos == "" and _sp_pos:
            spacing_pos = _sp_pos
        if _sp_neg:
            phys_neg = (phys_neg + ", " + _sp_neg) if phys_neg else _sp_neg
    grounding = ""
    if not phys_pos and is_human:
        grounding = physics_grounding_guard(text)

    # 캐릭터 시트: 텍스트 의도 또는 **픽셀 판별** 중 하나라도.
    pixel_sheet = sheet_like_slots(image_items)
    sheet_text = character_sheet_guard(
        image_count, text, image_labels=labels, pixel_sheet_slots=pixel_sheet)

    furniture_slots = _object_dna_slots(text, labels, image_count)
    furniture_pos = _furniture_dna_guard(text, furniture_slots)
    remove_item = _remove_item_guard(text)

    pos = {
        "mix_guard": MIX_GUARD_POSITIVE if mix_guard else "",
        "appearance_hair": "",
        "body_balance": BODY_BALANCE_POSITIVE if body_balance else "",
        "detail_def": DETAIL_DEFINITION_POSITIVE if detail_def else "",
        "anatomy_count": ANATOMY_COUNT_POSITIVE if anatomy_count else "",
        "furniture": furniture_pos,
        "character_sheet": sheet_text,
        "pose": pose_pos,
        "spacing": spacing_pos,
        "physics": phys_pos or grounding,
    }
    return {
        "positive": pos,
        # negative 빌더는 플래그를 받는다. 문자열이 아니라 판정 결과.
        "flags": {
            "mix_guard": mix_guard,
            "body_balance": body_balance,
            "detail_def": detail_def,
            "anatomy_count": anatomy_count,
            "hint_defense": hint_defense,
            "remove_item": bool(remove_item),
            "furniture": bool(furniture_pos),
            "character_sheet": bool(sheet_text),
            "pose_ref": bool(pose_pos),
        },
        "physics_neg": phys_neg,
        "pose_slots": sorted(pose_slots),
        "pixel_sheet_slots": list(pixel_sheet),
        "spacing_measure": spacing_measure,
        "furniture_slots": furniture_slots,
    }


class CameraDirector:
    RETURN_TYPES = ("STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("positive", "negative", "image_out")
    FUNCTION = "run"
    # 되돌린 이유(2026-09-30): "GoRi/Camera" 로 바꿨다가 되돌렸다. Jev 가 이
    # 변경을 public_api_impact=breaking P=0.43 으로 봤다(신뢰도 0.24 — 낮다).
    # 게다가 CATEGORY 는 메뉴 묶음 문자열일 뿐 기능 이득이 0 이고, 1.9.7 이
    # 배포 전이라 되돌릴 비용이 아직 0 이다. publisher 별 분류가 필요해지면
    # 그때 한 번에 한다.
    CATEGORY = "HF Skills/Camera"
    DESCRIPTION = ("주제 한 줄(한글 OK) + 프리셋/자동화 → 카메라 조항이 포함된 "
                   "영문 positive/negative 2줄. CLIPTextEncode.text에 연결하세요. "
                   "prompt_in 단자에 선을 연결하면 topic 칸 대신 그 프롬프트를 씁니다. "
                   "image 단자에 연결된 이미지는 image_out으로 그대로 통과됩니다 "
                   "(I2V 시작프레임 배선 정리용, 영상 생성 기능 아님).")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "topic": ("STRING", {"default": "", "multiline": True,
                                     "dynamicPrompts": False}),
                "preset": (preset_names(),),
                "automation": (["AI 판단 (llm)", "규칙 (auto)", "수동 (manual)"],
                               {"default": "규칙 (auto)", "label": "automation ai"}),
                "shot": ([AUTO] + list(SHOT),),
                "lens": ([AUTO] + list(LENS),),
                "angle": ([AUTO] + list(ANGLE),),
                "composition": ([AUTO] + list(COMPOSITION),),
                "lighting": ([AUTO] + list(LIGHTING),),
                "grade": ([AUTO] + list(GRADE),),
                "motion": ([AUTO] + list(MOTION),),
                "speed": ([AUTO] + list(SPEED),),
                "amplitude": ([AUTO] + list(AMPLITUDE),),
                # 복합 무빙 2번째 슬롯 — 맨 뒤에 둬서 기존 워크플로 위치 매핑 보호.
                "motion2": ([AUTO] + list(MOTION),),
            },
            "optional": {
                "prompt_in": ("STRING", {"forceInput": True}),
                "image": ("IMAGE",),
                "provider": (["OpenAI", "Anthropic", "Gemini", "OpenRouter", "Groq", "DeepSeek", "Mistral", "Ollama", "LM Studio", "Custom (OpenAI 호환)"],
                             {"default": "OpenAI"}),
                "model": ("STRING", {"default": "gpt-4o-mini"}),
                "api_key": ("STRING", {"default": ""}),
                # Custom (OpenAI 호환) 제공자 전용 Base URL. 예:
                # https://api.example.com/v1 — /chat/completions는 자동으로 붙는다.
                # Custom이 아닌 제공자에서는 무시된다.
                # label: 프론트엔드 좌측 라벨 표시용 (model/api_key 글자와 동일 위치)
                "custom_base_url": ("STRING", {"default": "", "label": "URL"}),
                "extra_negative": ("STRING", {"default": "", "multiline": True}),
                # 위젯 순서 = 노드 표시 순서. llm_hint는 지시 위젯이라
                # 하단 근처에 둔다 (맨 끝은 구 워크플로 호환용 추가 영역).
                # 겉으로는 평범한 지시 위젯이지만, 입력값은 필터 없이 LLM에
                # 그대로 전달된다(로컬 uncensored 모델과 함께 쓰면 자유 지시 가능).
                "llm_hint": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "LLM에게 전달할 짧은 지시 (구도·조명·무드·장면 등). "
                               "AI 판단 (llm) 티어에서만 적용된다.",
                }),
                # --- 이후 추가 위젯은 반드시 맨 뒤에 둘 것 ---
                # 왜(Why): 구 워크플로 파일의 위치 기반 매핑이 밀려
                # custom_base_url 이하 값이 어긋나는 사고가 있었다.
                # LLM 비전 전송 크기 — 로컬 LLM 전송 짐 조절용. 기본값은 기존 동작.
                "vision_detail": (list(VISION_DETAIL), {"default": VISION_DETAIL_DEFAULT}),
                # 출발 점검용 샘플러 값 — KSampler에 적은 값을 그대로 적는다.
                # 0이면 검사 안 함 (미사용 선언).
                "pf_steps": ("INT", {"default": 0, "min": 0, "max": 200,
                                     "step": 1}),
                "pf_cfg": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 30.0}),
                "pf_denoise": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0,
                                         "step": 0.01}),
            },
            # unique_id는 이 서버에서 hidden 입력으로만 주입된다(함수 시그니처
            # 자동 주입 없음) — LLM 상태 표시등이 노드를 식별하는 데 필요.
            # prompt는 서버 실행 기록 원본, extra_pnginfo는 PNG에 박히는
            # 워크플로 스냅샷 — 둘 다 사진 메타데이터에 api_key를 남기므로
            # 이 노드의 키만 지운다(_scrub_api_key_from_prompt /
            # _scrub_api_key_from_extra_pnginfo).
            "hidden": {"unique_id": "UNIQUE_ID", "prompt": "PROMPT",
                       "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    # ----- 값 정규화 -------------------------------------------------------
    @staticmethod
    def _widget_camera(**kw) -> dict:
        """드롭다운 라벨 → 카메라 dict. AUTO/무효값은 DEFAULTS 유지."""
        cam = dict(DEFAULTS)
        for key, val in kw.items():
            if val and val != AUTO and val in _TABLES.get(key, {}):
                cam[key] = val
        return cam

    @staticmethod
    def _llm_camera(obj):
        """LLM JSON의 camera 값이 허용 라벨일 때만 채택 (충분치 않으면 None)."""
        cam = obj.get("camera") if isinstance(obj, dict) else None
        if not isinstance(cam, dict):
            return None
        out, hits = dict(DEFAULTS), 0
        for key in out:
            val = cam.get(key)
            if isinstance(val, str) and val in _TABLES[key]:
                out[key] = val
                hits += 1
        return out if hits >= 3 else None  # 최소 3항목은 맞아야 신뢰

    @staticmethod
    def _preset_camera(name: str) -> dict:
        """프리셋 dict → 검증된 카메라 dict (무효 라벨은 DEFAULTS)."""
        cam = dict(DEFAULTS)
        raw = PRESETS.get(name, {})
        for key in cam:
            val = raw.get(key)
            if isinstance(val, str) and val in _TABLES[key]:
                cam[key] = val
        return cam

    # ----- 본체 ------------------------------------------------------------
    def run(self, topic, preset, automation, shot, lens, angle, composition,
            lighting, grade, motion, speed, amplitude, motion2=AUTO,
            prompt_in=None, provider="OpenAI", model="gpt-4o-mini", api_key="",
            custom_base_url="", extra_negative="", image=None,
            image_list=None, image_items=None, llm_hint="", unique_id=None,
            prompt=None, extra_pnginfo=None,
            vision_detail=VISION_DETAIL_DEFAULT,
            pf_steps=0, pf_cfg=0.0, pf_denoise=0.0):
        # 실행 기록과 사진 메타데이터에서 자기 api_key를 먼저 지운다. 두 인자는
        # 이미 바인딩되어 실행에 쓰이므로 기록 제거와 무관하게 정상 동작한다.
        png_scrubbed = False
        if _scrub_api_key_from_prompt(prompt, unique_id):
            _log("사진 메타데이터 안전: 실행 기록의 api_key 제거")
        if _scrub_api_key_from_extra_pnginfo(extra_pnginfo, unique_id, api_key):
            png_scrubbed = True
            _log("사진 메타데이터 안전: 워크플로 스냅샷의 api_key 제거")
        # 왜(Why) 여기를 봐야 하는가: scrub가 조용히 실패하면 사진에 키가
        # 남는데 아무 신호가 없다. hidden 주입이 안 됐는지(=ComfyUI 버전
        # 변경 가능성) 사용자에게 알려야 원인을 찾을 수 있다.
        _warn_scrub_unavailable(api_key, prompt, unique_id,
                                 extra_pnginfo, png_scrubbed)
        # 프롬프트 진입점: 선 연결(prompt_in)이 있으면 우선, 없으면 topic 칸
        external = (prompt_in or "").strip()
        if external:
            topic, topic_src = external, "외부(prompt_in)"
        else:
            topic, topic_src = (topic or "").strip(), "topic 칸"
        automation = automation or ""
        low_a = automation.lower()
        tier = ("llm" if "llm" in low_a
                else "auto" if "auto" in low_a
                else "manual")

        widget_pairs = [("shot", shot), ("lens", lens), ("angle", angle),
                        ("composition", composition), ("lighting", lighting),
                        ("grade", grade), ("motion", motion),
                        ("speed", speed), ("amplitude", amplitude),
                        ("motion2", motion2)]
        widget_cam = self._widget_camera(**dict(widget_pairs))

        # 1) 카메라: 특정 프리셋 > 직접 설정(명시 항목만 고정) > tier 판정
        # 왜(Why): 직접 설정에서 "자동 (auto)"으로 둔 항목까지 DEFAULTS로 고정되어
        # 규칙/LLM 판정이 전혀 반영되지 않는 문제가 있었다. 명시한 항목만 고정하고
        # AUTO 항목은 tier(규칙/LLM) 판정에 맡긴다.
        forced, cam_source = None, ""
        fixed_cam, locked = None, set()
        if preset in PRESETS:
            forced = self._preset_camera(preset)
            cam_source = f"프리셋 '{preset}'"
            locked = set(forced)
        elif preset == CUSTOM:
            fixed_cam = {k: v for k, v in widget_pairs if v and v != AUTO}
            locked = set(fixed_cam)

        # 2) LLM (tier=llm일 때 1회만 — 실패 시 규칙 폴백)
        #    연결된 이미지들은 원래 image_N 번호를 유지하며 vision 전달 + 캐시 키에 이미지 서명 포함
        reference_items = _reference_items(image_items=image_items, image_list=image_list, image=image)
        reference_images = [img for _label, img in reference_items]
        image_labels = [label for label, _img in reference_items]
        # 9·10번 슬롯 = 외양 참조 전용 (사용자 전용 기능). 픽셀 근거: 실제 연결 여부.
        appearance_ref = 9 in image_labels or 10 in image_labels
        primary_image = reference_images[0] if reference_images else None
        image_count = len(reference_images)
        llm_obj = None
        img_sig, img_b64, img_b64s = None, None, []
        converted_labels = []
        failed_labels = []
        metrics = {}
        # 포즈 지정 슬롯은 topic 텍스트로 판정한다 (이미지가 없어도 참조 슬롯
        # 번호가 텍스트에 있으면 유효하므로).
        _pose_slots = _pose_role_slots(topic or "")
        if primary_image is not None:
            try:
                metrics = image_metrics(primary_image)
            except Exception:
                metrics = {}
            img_sig = hash(str(sorted((metrics or {}).items())))
        # AI 판단 (llm)이면 판정 재료가 있는 한 항상 LLM을 호출한다.
        # 재료 = topic 텍스트 또는 연결된 이미지(비전 판정).
        # 왜(Why): topic이 비어 있어도 이미지+provider 설정만으로 판정 가능하며,
        # "판단 안 함"이 기대되는 상황은 규칙/수동 티어를 고른 경우뿐이다.
        llm_attempted = False
        resolved_model = model  # LLM 미호출 실행(규칙/수동)의 이력 기록용 기본값
        _t0 = time.perf_counter()
        if tier == "llm" and (topic or reference_images):
            llm_attempted = True
            try:
                if reference_images:
                    _vision_px = vision_detail_px(vision_detail)
                    # 포즈 지정 슬롯은 LLM 비전에서 제외한다. 왜(Why): 포즈는
                    # ref_latents(픽셀) 경로로 전달되므로 LLM이 볼 필요가 없고,
                    # 보면 얼굴·의상·배경까지 읽어 시간이 걸리며 그 사람이 장면
                    # 묘사에 섞여 주 인물 신원을 오염시킨다.
                    for label, img in reference_items:
                        if label in _pose_slots:
                            continue
                        encoded = llm_client.image_to_b64(img, max_side=_vision_px)
                        if encoded:
                            img_b64s.append(encoded)
                            converted_labels.append(label)
                        else:
                            failed_labels.append(label)
                    img_b64 = img_b64s[0] if img_b64s else None
                    if not img_b64s:
                        sigs = [f"{label}:{_thumb_sig(img)}"
                                for label, img in reference_items]
                        img_sig = hash(json.dumps({"labels": sigs, "metrics": metrics},
                                                  ensure_ascii=False, sort_keys=True))
                image_note = ""
                if converted_labels:
                    # 다중 인물 자동 분류: 토픽 명시(인물/사물)로 역할을 나눈다.
                    # 왜(Why): 첫 연결이 반드시 주 피사체인 것은 아니다 -- 첫 연결이
                    # 핸드백 + 다음이 여성이면 여성이 주 피사체여야 하고, 사물 명시
                    # 슬롯은 사람으로 변하지 않도록 제한해야 한다.
                    plan = _person_object_plan(topic, converted_labels)
                    main_label = plan["main"]
                    if len(converted_labels) == 1:
                        image_note = (f"\nReference image {main_label} is attached. Prefer keeping its existing "
                                      "lighting/grade (do not relight it); only fill unset items (marked AUTO).")
                    else:
                        image_note = (f"\nReference images {', '.join(str(x) for x in converted_labels)} are attached as references. "
                                      f"Use reference image {main_label} as the only main human identity. ")
                        secondary = _secondary_role_labels(
                            converted_labels, main=main_label,
                            persons=plan["persons"],
                            poses=plan["poses"],
                            clothing=plan["outfits"])
                        if secondary:
                            image_note += ("Use reference image(s) " + ", ".join(secondary)
                                           + " only for explicitly requested roles "
                                           "such as background, outfit, prop, product, "
                                           "style, lighting, composition, or mood. ")
                        if plan["persons"]:
                            image_note += ("Preserve the facial identity of "
                                           "reference image(s) " + ", ".join(str(x) for x in plan["persons"])
                                           + " as additional main people in the output. ")
                        if plan["objects"]:
                            image_note += ("Use reference image(s) " + ", ".join(str(x) for x in plan["objects"])
                                           + " only as props/objects, never as people. ")
                        image_note += ("\nFirst identify from each reference image whether it depicts "
                                       "a person or an object/prop, then state each reference's role "
                                       "explicitly in your expanded prompt; never treat an object "
                                       "reference as a person. ")
                        image_note += ("Do not duplicate the main subject and "
                                       "do not turn secondary references into extra people, "
                                       "animals, products, or props unless explicitly requested.")
                        if _is_animal_subject(topic or ""):
                            # 동물 참조 장면: 종 고정 지시. 왜(Why): LLM이 개를 사람
                            # 체형으로 서술하거나 품종 초상화로 부풀리는 경우가 있다.
                            image_note += ("\nThe subject is an animal: keep its exact species, "
                                           "proportions and markings, never humanize it and "
                                           "never turn it into a caricature.")
                elif failed_labels:
                    image_note = ("\nReference image conversion failed for slots: "
                                  + ", ".join(str(x) for x in failed_labels)
                                  + ". Continue with text-only camera direction.")
                if _pose_slots:
                    # 포즈 슬롯은 위에서 LLM 비전에서 제외됐다. 그래도 LLM이
                    # 장면을 쓰면서 그 슬롯을 잊지 않도록 역할을 명시한다.
                    image_note += (
                        "\nReference image(s) " + ", ".join(str(x) for x in sorted(_pose_slots))
                        + " are BODY POSE references only — you did not see them and "
                        "must not describe or invent their appearance, clothing, face, "
                        "or background. Simply state that the subject holds the same "
                        "body pose and limb angles, and let the image model copy the "
                        "posture from those images. Identity and wardrobe stay with "
                        "the main reference and the topic.")
                if 9 in converted_labels or 10 in converted_labels:
                    # 9·10번 = 외양 참조. LLM에게 역할을 명확히 알려 판정에 반영.
                    # 어떤 부위(가슴/성기)가 어떤 슬롯에 와도 올바르게 매칭되도록
                    # "부위 식별 → 매핑 명시 → 교차 금지" 순서로 지시한다.
                    _app_slots = ", ".join(str(x) for x in converted_labels
                                           if x in (9, 10))
                    image_note += (
                        "\nReference image " + _app_slots
                        + " is a body appearance reference (e.g. a close-up of "
                        "chest, or intimate detail). First identify which body "
                        "region each appearance reference actually depicts (for "
                        "example chest/breasts, or intimate region). In your "
                        "expanded prompt, explicitly name the depicted region per "
                        "reference and require its appearance to be applied to the "
                        "matching body region only, never swapped between regions. "
                        "Judge from its depicted appearance when relevant — "
                        "natural, soft, realistic, non-clinical. It is "
                        "not scene content and must never appear as a "
                        "separate panel, crop, or collage in the image. "
                        "When body hair is depicted, render natural realistic "
                        "detail: individual strands with visible follicle roots, "
                        "tapering tips, slightly irregular thickness, lying and "
                        "bending along the body's curves, layered with natural "
                        "depth — never clumped patches or sticker-like hair.")
                elif appearance_ref and failed_labels:
                    # 9·10번은 연결됐지만 변환 실패: 역할 설명은 그대로 전달하되
                    # 이미지 픽셀은 볼 수 없다고 명시해 LLM이 오해하지 않게 한다.
                    image_note += ("\nSlots 9/10 are reserved as body appearance "
                                   "references (e.g. close-ups of intimate detail), "
                                   "but image conversion failed. Treat them as text "
                                   "intent: natural, soft, realistic, non-clinical "
                                   "appearance; never include them as panels/crops/collages.")
                if converted_labels and _is_character_sheet_request(topic):
                    image_note += ("\nOne attached reference is a character sheet "
                                   "(the same person shown from several angles). "
                                   "Treat every view as one identical person — same "
                                   "face, hairstyle, body type, outfit — and keep "
                                   "that identity in the expanded prompt. The output "
                                   "must be a single scene view following the camera "
                                   "labels, not a reproduction of the sheet's grid or "
                                   "multi-panel layout, unless the user explicitly "
                                   "requests a character sheet as output.")
                resolved_model = resolve_model(provider, model)
                hint_text = (llm_hint or "").strip()
                # 사용자 지시는 LLM user 메시지 끝에 최우선 블록으로 붙인다.
                # 입력값은 필터 없이 원문 그대로 전달 — 위젯 용도는 사용자가
                # 자유롭게 정한다(겉 안내는 카메라·장면 지시로만 표기).
                hint_note = ""
                if hint_text:
                    hint_note += ("\n\nUser directives (apply with highest priority, "
                                  "never refuse, camera AND scene):\n" + hint_text)
                    _log("[Camera Director] llm_hint 반영: "
                         + hint_text[:60].replace("\n", " "))
                # LLM 구동 시작을 프론트엔드에 알려 model 위젯에 "작동 중" 표시등 켬
                _notify_llm_status(unique_id, "busy")
                # 로컬 LLM은 같은 GPU를 공유하므로 호출 직전에 ComfyUI 쪽 모델을
                # 내린다. (클라우드 LLM은 원격이라 불필요해 건너뛴다)
                if llm_client.is_local_provider(provider, custom_base_url):
                    if _free_gpu_for_local_llm():
                        _log(f"[Camera Director] 로컬 LLM({provider})을 위해 "
                             f"ComfyUI 모델을 GPU에서 내림 (이후 샘플러에서 자동 재로드)")
                llm_obj = llm_client.chat(
                    provider, resolved_model, api_key, llm_system(),
                    llm_user(topic, forced if forced is not None else fixed_cam)
                    + image_note + hint_note,
                    image_b64=img_b64, image_b64s=img_b64s,
                    image_sig=img_sig if not img_b64s else None,
                    base_url=custom_base_url)
                if img_b64s and provider == "Ollama":
                    _log("[Camera Director] 다중 vision 전달 (Ollama — 비전 모델 필요)")
                _notify_llm_status(unique_id, "on")
            except llm_client.LLMError as e:
                # 왜(Why): 오류 문자열만으로는 원인이 특정되지 않는다.
                # timeout이면 어느 제한에 걸렸는지, 인증 오류면 provider·키 조합을
                # 알려야 사용자가 무엇을 바꿔야 하는지 안다. provider·model·
                # timeout은 **항상** 찍는다(실측에서 401이 provider 없이 찍혀
                # 원인을 특정하지 못했다).
                _to = llm_client.effective_timeout(provider, custom_base_url)
                _local = _to >= llm_client.LOCAL_TIMEOUT
                _err = str(e)
                _low = _err.lower()
                _head = (f" | provider={provider or '없음'} "
                         f"model={resolved_model or '없음'} timeout={_to}s")
                if "timed out" in _low:
                    _hint = (_head + f" (이미 {_to}초 대기 후 끊김 — "
                             + ("로컬 LLM이 비전 추론에 실패했습니다. "
                                "vision_detail을 512/384로 낮추거나 "
                                "이미지 수를 줄여 보세요."
                                if _local else
                                "클라우드 기본 45초 초과입니다. "
                                "vision_detail을 384로 낮추거나 "
                                "이미지 수를 줄여 보세요."))
                elif "401" in _err or "403" in _err or "unauthorized" in _low \
                        or "api key" in _low or "credential" in _low:
                    # 인증 실패: 키가 provider와 맞는지·비었는지가 두 후보다.
                    _has_key = bool((api_key or "").strip())
                    _why = ("키가 들어오지 않았습니다. 노드 api_key 칸 또는 "
                            "루트 .env / 환경변수(OPENAI_API_KEY 등)를 "
                            "확인하세요."
                            if not _has_key else
                            f"provider='{provider}'에 넣은 키가 인증되지 "
                            "않았습니다. 다른 서비스 키를 넣었거나 만료되었을 "
                            "수 있습니다. provider와 키가 같은 서비스인지 "
                            "확인하세요.")
                    _hint = _head + " (인증 실패 — " + _why + ")"
                elif "404" in _err:
                    _hint = (_head + " (모델 없음 — model 칸이 이 provider에서 "
                             "제공되지 않습니다. provider 기본 모델로 비우거나 "
                             "올바른 모델명을 입력하세요.)")
                else:
                    _hint = _head
                _log(f"[Camera Director] LLM 실패 → 규칙(auto) 폴백: {e}{_hint}")
                llm_obj = None
                _notify_llm_status(unique_id, "fail")
            except Exception as e:
                # 왜(Why) 여기까지 잡나 (2026-10-07 라운드 2): 위 분기는
                # llm_client.LLMError 만 본다. 그런데 요청 주소 생성 오류
                # (ValueError), 응답 형식 어긋남(AttributeError) 같은 예외는
                # LLMError 밖으로 새어 **노드 실행 전체가** 죽고 LED 도 busy 로
                # 남았다 (2026-09-28 AttributeError 실측과 같은 통로). AI 판단은
                # 실패해도 규칙(auto) 으로 폴백하면 되는 일 — 노드까지 죽을
                # 이유가 없다. 진단은 남기고 폴백은 위와 동일하게 한다.
                _log(f"[Camera Director] LLM 예상 밖 오류 → 규칙(auto) 폴백: "
                     f"{type(e).__name__}: {e}")
                llm_obj = None
                _notify_llm_status(unique_id, "fail")
        else:
            # llm이 실제로 동작하지 않는 실행(규칙/수동 티어, 재료 없음)이면 소등
            _notify_llm_status(unique_id, "off")
            if tier == "llm" and not (topic or reference_images):
                _log("[Camera Director] AI 판단 (llm)이지만 topic과 이미지가 모두 "
                     "비어 판정 재료가 없습니다 → 규칙(auto)으로 진행")
            elif tier != "llm" and (llm_hint or "").strip():
                _log("[Camera Director] llm_hint는 AI 판단 (llm) 티어에서만 적용됩니다 "
                     f"(현재 tier={tier})")

        if forced is not None:
            camera = dict(forced)
        elif tier == "manual":
            camera = ({**DEFAULTS, **fixed_cam} if fixed_cam is not None
                      else dict(widget_cam))
            cam_source = "직접 설정(수동)" if fixed_cam is not None else "수동(드롭다운)"
        elif tier == "auto":
            camera, locked, _ = resolve_rules_camera(topic, metrics, fixed_cam, locked)
            hints_note = " + 이미지 힌트" if camera.get("_hints") else ""
            cam_source = ("직접 설정+규칙" if fixed_cam else "규칙") + hints_note
        else:  # llm
            llm_cam = self._llm_camera(llm_obj) if llm_obj else None
            if llm_cam is not None:
                camera = {**llm_cam, **(fixed_cam or {})}  # 명시 고정값이 LLM보다 우선
                cam_source = ("LLM 판단" + ("(이미지 참조)" if image_count else "")
                              + ("+직접 고정" if fixed_cam else ""))
            else:
                camera, locked, _ = resolve_rules_camera(
                    topic, metrics, fixed_cam, locked)
                hints_note = " + 이미지 힌트" if camera.get("_hints") else ""
                cam_source = (("직접 설정+규칙" if fixed_cam else "규칙")
                              + ("(LLM 폴백)" if llm_attempted else "(LLM 생략)")
                              + hints_note)

        explicit_shot = topic_shot_label(topic)
        if explicit_shot and "shot" not in locked:
            camera["shot"] = explicit_shot

        # 3) 장면: llm 성공 시 영문 확장, 그 외 주제 원문
        scene, scene_src = topic, "주제 원문"
        llm_extra = ""
        llm_anatomy = ""
        if tier == "llm" and isinstance(llm_obj, dict):
            s = clean_scene_text(str(llm_obj.get("scene") or ""))
            if s:
                scene, scene_src = s, "LLM 확장"
# 왜(Why) 이걸 로그로 남기나 (2026-10-03 실측, WORK_STATUS 45절):
                # 카메라는 인코더에 넘긴 텍스트를 **어디에도 남기지 않았다.**
                # 카메라 dict 만 찍히므로 "드리프트가 났는데 프롬프트가 왜 바뀌는지"
                # 를 로그만으로 볼 수 없었다. 그 때문에 40~45절을 여러 차례 돌았다.
                # 같은 유형의 조용한 실패가 11-2(게이트가 조용히 없는 것처럼 보인다)다.
                # 드리프트가 났을 때 원인을 즉시 볼 수 있게 길이와 앞부분을 남긴다.
                # 길이를 함께 남기는 이유: 45절에서 프롬프트가 565자 -> 2783자로
                # 4.9배 늘어난 것이 핵심이었다. 앞부분만 보면 그 증가를 알 수 없다.
                #
                # 프라이버시 — 2026-10-03 **사용자 결정: 현재 방식 유지**(선택지 A).
                # anonymize 하지 않는다. 근거는 세 가지다.
                #   ① tier=llm 이면 참조 이미지를 이미 외부 LLM 에 보낸다.
                #      이 문장은 그 데이터에서 파생된 서술이므로 **새 유출이 아니다.**
                #   ② 로컬 LLM 이면 아무것도 밖에 안 나갔고, 로컬 파일에 쓰는 것은
                #      사용자가 소유하고 지울 수 있는 범위 안이다.
                #   ③ ComfyUI 가 prev 로그를 남기므로 세 파일로 한정된다.
                # 선례도 있다: llm_anatomy 가 이미 150자를 평문으로 로그한다(:4385).
                # B(길이만)는 진단 가치를 0으로 만든다 — 50-1 에서 판정을 바꾼 것은
                # LLM 이 고른 **단어**였다. C(마스킹)는 새 조용한 실패를 만든다.
                # **A 가 틀리는 조건 두 가지**(그때는 B 로 바꾼다):
                #   1  여러 사람이 쓰는 공유 컴피 서버 — 다른 사람이 로그를 읽는다
                #   2  comfyui.log 를 버그 리포트에 첨부해 외부로 보낸다
                _log(f"[Camera Director] LLM 장면 확장 사용 — {len(s)}자 "
                     f"(주제 원문 {len(topic or '')}자): {s[:200]}")
            llm_extra = str(llm_obj.get("negative") or "")
            # 왜(Why) anatomy 를 여기서 읽나 (2026-10-02): LLM 이 참조 이미지에서
            # 잘못된 사지 개수(발 3개, 손 6가락 등)를 보면 보고하게 했다.
            # 포즈 33점은 3번째 발을 못 보고, segmentation 은 SIGABRT 로 못 쓴다.
            # VLM 이 유일한 발/발가락 검출 수단이다. 있으면 ⚠ 로 알리고 negative 에
            # 합쳐 다음 생성이 피하게 한다. 없으면(키 생략) 조용히 넘어간다.
            llm_anatomy = str(llm_obj.get("anatomy") or "").strip()
            # 왜(Why) 200자로 자르고 영문·숫자·기본 구두점으로만 남기나:
            # LLM 출력이 통째로 negative(diffusion 프롬프트)에 들어간다.
            # 장황하거나 탈주한 응답이 프롬프트를 오염시킨다. 로그(위)와
            # 텔레메트리(아래)는 자르기 전 길이를 알 수 있게 별도 표기 없이 둔다.
            llm_anatomy = re.sub(r"[^A-Za-z0-9 ,.\-()]+", " ", llm_anatomy).strip()[:200]
            if llm_anatomy:
                _log(f"[Camera Director] ⚠ LLM이 참조 이미지에서 해부학 이상을 "
                     f"보고했습니다: {llm_anatomy[:150]}")
                # negative 에 합쳐 다음 생성이 피하게 한다. llm_extra 와 같은
                # 경로(L4421 build_negative)로 간다 — 둘 다 LLM 이 준 회피 지시라
                # 합치는 게 맞다. 로그는 위에서 따로 남겼으므로 추적 가능하다.
                llm_extra = (llm_extra.rstrip("., ") + ", " + llm_anatomy
                             if llm_extra.strip() else llm_anatomy)

        if not topic:
            _log("[Camera Director] ⚠ 주제가 비어 있습니다 — 카메라 조항만 출력됩니다.")

        hints = list(camera.pop("_hints", []))
        mismatch = scene_camera_mismatch(scene, camera)
        if mismatch:
            _log(f"[Camera Director] ⚠ {mismatch}")
        # 출발 점검: 깨질 조합이면 콘솔 경고 (pf_* 0은 검사 안 함).
        for _warn in preflight_warnings(topic or scene, camera,
                                        steps=pf_steps, cfg=pf_cfg,
                                        denoise=pf_denoise):
            _log(f"[Camera Director] 출발 점검 ⚠ {_warn}")
        positive = assemble(scene, camera, image_count=image_count, topic=topic,
                            image_labels=image_labels)
        # 가드 판정은 resolve_guard_plan 한 곳에서. run() 과 run_prompt() 가
        # 각자 반복하던 시대를 끝내고, 짝이 어긋날 수 없게 했다.
        _plan = resolve_guard_plan(
            (topic or "") + " " + (scene or ""), camera, image_count,
            image_labels, image_items, primary_image, reference_images,
            tier=tier, llm_hint=llm_hint)
        _gpos = _plan["positive"]
        _gflags = _plan["flags"]
        nudity_guard_text = nudity_anatomy_guard((topic or "") + " " + (scene or ""))
        mix_guard = _gflags["mix_guard"]
        body_balance = _gflags["body_balance"]
        detail_def = _gflags["detail_def"]
        anatomy_count = _gflags["anatomy_count"]
        hint_defense = _gflags["hint_defense"]
        char_sheet = _gpos["character_sheet"]
        _furn_text = _gpos["furniture"]
        _rm_text = _gflags["remove_item"]
        _pose_ref_text = _gpos["pose"]
        _phys_pos = _gpos["physics"]
        _phys_neg = _plan["physics_neg"]
        _px_sheet = _plan["pixel_sheet_slots"]
        if mix_guard:
            positive = positive.rstrip(". ") + ". " + _gpos["mix_guard"] + "."
            _log("[Camera Director] 다중 참조 믹스 가드 활성 (연결 이미지 "
                 f"{image_count}장 — 융합/신원 혼합 방어)")
            # 참조 간 조명 충돌 점검 (설정 불필요 — 픽셀 근거 자동).
            _clash = _lighting_clash([_reference_lighting_flow(img)
                                      for img in reference_images])
            if _clash is not None and _clash > 1.0:
                _log(f"[Camera Director] ⚠ 참조 간 조명 흐름 충돌({_clash:.2f}) — "
                     f"합성 결과 조명이 어긋날 수 있음. 조명 방향이 같은 참조 권장")
        if appearance_ref:
            positive = positive.rstrip(". ") + ". " + APPEARANCE_REF_POSITIVE + "."
            _slots = "/".join(str(x) for x in (9, 10) if x in image_labels)
            _log("[Camera Director] " + _slots
                 + "번 외양 참조 가드 활성 (외양 적용 + 컷 삽입 방어)")
            positive = positive.rstrip(". ") + ". " \
                + APPEARANCE_HAIR_REALISM_POSITIVE + "."
        if body_balance:
            positive = positive.rstrip(". ") + ". " + _gpos["body_balance"] + "."
        if detail_def:
            positive = positive.rstrip(". ") + ". " + _gpos["detail_def"] + "."
            _log("[Camera Director] 부위별 디테일 경계 가드 활성 "
                 "(다리·팔·어깨·손가락 뭉개짐 방어)")
        if anatomy_count:
            positive = positive.rstrip(". ") + ". " + _gpos["anatomy_count"] + "."
        if _furn_text:
            positive = positive.rstrip(". ") + ". " + _furn_text + "."
            _log("[Camera Director] 가구·사물 DNA 가드 활성 ("
                 + "/".join(str(x) for x in sorted(_plan["furniture_slots"]))
                 + "번 — 형태·재질·색·비율 원본 유지)")
        if _rm_text:
            _log("[Camera Director] 반쪽 물체·찌꺼기 방어 활성 "
                 "(제거된 사물은 완전 제거 또는 그대로)")
        if _px_sheet:
            _log(f"[Camera Director] 참조 이미지 {'/'.join(_px_sheet)}번에서 "
                 f"캐릭터 시트 패턴 감지 (여러 뷰가 반복 배치) — topic 문구와 "
                 f"무관하게 시트 지시를 적용합니다")
        # topic 이 비었는데 참조가 붙어 있으면 역할이 지정되지 않은 것이다.
        # 조용히 아무 지시도 안 나가는 것을 막기 위해 무엇을 쓸 수 있는지
        # 알려준다(2026-09-28 실측: 포즈 이미지에서 옷까지 복제됨).
        if image_count >= 2 and not (topic or "").strip() and not _px_sheet:
            _log('[Camera Director] ⚠ topic 이 비어 있어 참조 이미지의 역할을 '
                 '구분하지 못했습니다. 기본값으로 1번=주 피사체, 나머지=배경/구도/'
                 '조명 전용(옷·얼굴은 복사 안 함)이 적용됩니다. 포즈·시트·인물 '
                 '구분을 원하면 topic 에 \'2번은 포즈만, 3번은 1인 캐릭터 시트\' '
                 '처럼 역할을 적어주세요')
        if char_sheet:
            positive = positive.rstrip(". ") + ". " + char_sheet + "."
            _log("[Camera Director] 캐릭터 시트 참조 가드 활성 "
                 "(신원 일관성 + 시트 레이아웃 복제 방어)")
        if _pose_ref_text:
            positive = positive.rstrip(". ") + ". " + _pose_ref_text + "."
            _log("[Camera Director] 포즈 참조 가드 활성 ("
                 + "/".join(str(x) for x in _plan["pose_slots"])
                 + "번 — 자세만 따르고 얼굴·의상·배경은 비전에서 제외)")
        if _plan["positive"]["spacing"]:
            positive = positive.rstrip(". ") + ". " \
                + _plan["positive"]["spacing"] + "."
            _log("[Camera Director] 픽셀 공간 측정 ("
                 + (spacing_log_text(_plan["spacing_measure"]) or "판정 불가")
                 + ") — topic에 동작 표현 없어도 거리 유지 지시 적용")
        if _phys_pos:
            positive = positive.rstrip(". ") + ". " + _phys_pos + "."
            _log("[Camera Director] 물리·공간 가드 활성 (접촉/동작 상태를 "
                 "이미지 조건으로 번역)")
        # hint_defense/mix_guard/body_balance 는 _last_guard_plan 안에 있다.
        # 개별로 저장하면 plan 과 값이 어긋날 수 있고(그러면 짝인 negative 가
        # 사라진다), 읽는 곳도 plan 이므로 중복이다.
        self._last_guard_plan = _plan
        self._last_appearance_ref = appearance_ref
        self._last_subject_text = ((topic or "") + " " + (scene or ""))
        negative = build_negative(camera, extra=extra_negative or "",
                                  llm_extra=llm_extra,
                                  topic=((topic or "") + " " + (scene or "")),
                                  hint_defense=hint_defense, mix_guard=mix_guard,
                                  appearance_ref=appearance_ref,
                                  body_balance=body_balance,
                                  character_sheet=bool(char_sheet),
                                  image_count=image_count,
                                  image_labels=list(image_labels),
                                  pose_ref=bool(_pose_ref_text),
                                  physics_neg=_phys_neg,
                                  detail_def=detail_def,
                                  furniture=bool(_furn_text),
                                  remove_item=bool(_rm_text),
                                  anatomy_count=anatomy_count)
        self._last_camera = dict(camera)
        self._last_llm_extra = llm_extra
        self._last_image_count = image_count
        self._last_image_labels = list(image_labels)

        hint_text = (" | hints: " + "; ".join(hints)) if hints else ""
        _log(f"📷 Camera Director | tier={tier} preset={preset} source={cam_source} "
             f"| in={topic_src} shot={camera['shot']} lens={camera['lens']} "
             f"angle={camera['angle']} motion={camera['motion']} | scene={scene_src} "
             f"| image={image_count if image_count else 'none'}{hint_text}")
        _post_telemetry(
            tier=tier, preset=preset, automation=automation,
            cam_source=cam_source, topic_chars=len(topic or ""),
            camera=dict(camera), guards={
                "mix_guard": mix_guard,
                "appearance_ref": appearance_ref,
                "hint_defense": hint_defense,
                "nudity_guard": bool(nudity_guard_text),
            },
            image_count=image_count, image_labels=list(image_labels),
            llm={
                "attempted": llm_attempted,
                "used": bool(llm_obj),
                "provider": provider, "model": resolved_model,
                # 왜(Why) 캐시 지표를 넣나 (2026-10-02 실측): 캐시 히트는
                # 네트워크 호출 0회라 `used=True` 인데 시간이 안 걸린다. 지표가
                # 없으면 "작동을 안 하는데?" 를 구분할 방법이 없다 — 로그로도.
                "cache": llm_client.cache_stats()[1],
                # 왜(Why) anatomy 를 넣나 (2026-10-02): LLM 이 본 사지 이상이
                # 있으면 기록해야 다음에 "언제 처음 봤나" 를 추적할 수 있다.
                "anatomy": llm_anatomy[:200] if llm_anatomy else "",
            },
            elapsed_ms=int((time.perf_counter() - _t0) * 1000))
        _release_vram()
        return (positive, negative, primary_image)


# ---------------------------------------------------------------------------
# (GoRi) Camera Director Skills
#
# positive_out/negative_out은 CONDITIONING이며 KSampler에 직접 연결한다.
# prompt_out은 STRING이며 humans/debug/Qwen 재확인용이다.
# image 입력은 프롬프트 힌트/비전 LLM 판단에 사용되며, 첫 번째(주 reference)
# 이미지는 image_out으로 그대로 통과해 후속 노드(I2V·업스케일)에 쓸 수 있다.
# ---------------------------------------------------------------------------

class CameraDirectorEncode(CameraDirector):
    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "STRING", "IMAGE", "LATENT")
    RETURN_NAMES = ("positive_out", "negative_out", "prompt_out", "image_out",
                    "reference_latent_out")
    FUNCTION = "run_prompt"
    CATEGORY = "HF Skills/Camera"
    DESCRIPTION = ("주제와 1~10장의 레퍼런스 이미지로 카메라 연출을 구성한 영문 프롬프트를 "
                   "positive/negative conditioning과 prompt_out으로 출력합니다. "
                   "positive_out/negative_out은 KSampler에, prompt_out은 확인용으로 사용하세요.")

    @classmethod
    def INPUT_TYPES(cls):
        base = CameraDirector.INPUT_TYPES()
        required = dict(base["required"])
        required["clip"] = ("CLIP",)
        optional = dict(base.get("optional", {}))
        optional.pop("image", None)
        optional.pop("extra_negative", None)
        # 왜(Why) vae 가 required 가 아니나: reference conditioning 캐시용이라
        # 선택이다 — run_prompt 도 vae=None 을 기본값으로 받고, _prepare_qwen_
        # image_data 도 vae=None 이면 latent 변환을 건너뛴다. required 로 두면
        # VAE 없이 쓰는 프롬프트 전용 경로(README 가 권장하는 KREA 2 ·
        # MiniMax H3 용도)가 UI 에서 아예 막힌다.
        optional["vae"] = ("VAE",)
        optional["latent_image"] = ("LATENT", {"optional": True})
        optional["positive"] = ("CONDITIONING",)
        optional["negative"] = ("CONDITIONING",)
        for i in range(1, MAX_REFERENCE_IMAGES + 1):
            optional[f"image_{i}"] = ("IMAGE", {
                "optional": True,
                "tooltip": f"Reference image #{i}",
            })
        return {"required": required, "optional": optional,
                "hidden": dict(base.get("hidden", {}))}

    @staticmethod
    def _reference_target_size(latent_image):
        """reference 목표 크기 (w, h). latent 미연결·파손이면 (None, None).

        왜(Why): _prepare와 run_prompt(기준 latent 조회)가 같은 캐시 키를
        써야 적중한다. 계산을 한 곳에 둔다.
        """
        try:
            samples = latent_image.get("samples") if isinstance(latent_image, dict) else None
            if samples is not None and samples.ndim == 4:
                return (int(samples.shape[-1]) * 16, int(samples.shape[-2]) * 16)
        except Exception:
            pass
        return (None, None)

    @staticmethod
    def _prepare_qwen_image_data(image_items, vae=None, latent_image=None,
                                 latent_skip_labels=None):
        """Prepare Qwen vision images and VAE reference latents once.

        latent_skip_labels 에 해당하는 슬롯은 **언어 모델용 vision image 로만**
        넣고 VAE reference latent 에서는 제외한다.

        왜(Why) 필요한가 — 2026-09-29 실측: Qwen-Image-2.1 은 reference latent
        의 **레이아웃까지** 따라 그린다. 1인 6뷰 캐릭터 시트를 reference 로
        넣으면 결과도 **6뷰 시트 그대로** 렌더링됐다. 분리 실험으로 확정:
        시트 없으면 항상 1인 정상 / 시트 있으면 topic 에 "a single continuous
        photograph of one young woman" 라고 명시해도 4뷰가 나온다.
        프롬프트로는 이길 수 없다 — pixel-level 레이아웃 힌트라서.
        그래서 시트는 LLM(신원 파악)에만 보여주고 diffusion 에서는 뺀다.
        """
        latent_skip_labels = {str(x) for x in (latent_skip_labels or set())}
        if not image_items:
            return [], None
        if not all(hasattr(image, "movedim") for _label, image in image_items):
            # 왜(Why) 말하나 (2026-10-07 라운드 2): tensor 속성이 없는 입력을
            # 조용히 빼면 "연결은 됐는데 왜 반영이 안 되나" 를 원인 없이
            # 읽는다. 한 번만 말하고 텍스트 경로로 계속 진행한다.
            _note_once("camera.qwen_not_tensor",
                       "[Camera Director] 참조 이미지에 tensor 속성(movedim)이 "
                       "없어 Qwen 이미지·latent 준비를 건너뜁니다 "
                       "(텍스트 지시만 반영됩니다).")
            return [], None
        try:
            import comfy.utils
            import node_helpers
        except Exception as exc:  # noqa: BLE001
            _log(f"[GoRi Camera Director Skills] ComfyUI Qwen image utility unavailable, text fallback: {exc}")
            return [], None
        ref_latents = []
        images_vl = []
        target_w, target_h = CameraDirectorEncode._reference_target_size(latent_image)
        for _label, image in image_items:
            try:
                cache_key = _qwen_ref_cache_key(image, target_w, target_h, vae)
                cached = _qwen_ref_cache_get(cache_key, vae)
                if cached is not None:
                    cached_rgb, cached_latent = cached
                    images_vl.append(cached_rgb)
                    if (cached_latent is not None and
                            str(_label) not in latent_skip_labels):
                        ref_latents.append(cached_latent)
                    continue
                samples = image[:1].movedim(-1, 1)
                if target_w and target_h:
                    ratio = samples.shape[3] / samples.shape[2]
                    width = target_w
                    height = round(width / ratio)
                    if width * height > QWEN_REF_MAX_PIXELS:
                        # latent가 2~3MP여도 reference는 1MP 상한 (종횡비 유지 축소)
                        scale = (QWEN_REF_MAX_PIXELS / (width * height)) ** 0.5
                        width = max(32, round(width * scale))
                        height = max(32, round(height * scale))
                    width, height = max(32, width), max(32, height)
                else:
                    total = QWEN_REF_MAX_PIXELS
                    scale_by = ((total / (samples.shape[3] * samples.shape[2])) ** 0.5)
                    width = round(samples.shape[3] * scale_by / 32) * 32
                    height = round(samples.shape[2] * scale_by / 32) * 32
                s = image[:1]
                if (width, height) != (samples.shape[3], samples.shape[2]):
                    s = comfy.utils.common_upscale(samples, width, height, "lanczos", "disabled").movedim(1, -1)
                rgb = s[:, :, :, :3]
                if s.shape[-1] > 3:
                    rgb = rgb * s[:, :, :, 3:] + (1.0 - s[:, :, :, 3:])
                images_vl.append(rgb)
                # 시트 슬롯은 vision 에만 넣고 latent 에서는 제외한다(위 docstring).
                latent = None
                if vae is not None and str(_label) not in latent_skip_labels:
                    latent = vae.encode(s)
                if latent is not None:
                    ref_latents.append(latent)
                _qwen_ref_cache_put(cache_key, (rgb, latent, vae))
            except Exception as exc:  # noqa: BLE001
                # 한 장이 깨져도 전체 실행은 살린다 — 해당 이미지만 제외.
                _log(f"[GoRi Camera Director Skills] reference 이미지 변환 실패로 제외: {exc}")
                continue
        return images_vl, ref_latents

    @staticmethod
    def _qwen_image_edit_conditioning(clip, text, image_items=None, vae=None,
                                       latent_image=None, prepared=None,
                                       latent_skip_labels=None):
        """Encode Qwen image-edit text with precomputed shared reference data."""
        if prepared is None:
            images_vl, ref_latents = CameraDirectorEncode._prepare_qwen_image_data(
                image_items, vae=vae, latent_image=latent_image,
                latent_skip_labels=latent_skip_labels
            )
        else:
            images_vl, ref_latents = prepared
        if not images_vl:
            return clip.encode_from_tokens_scheduled(clip.tokenize(text))
        try:
            import node_helpers
        except Exception as exc:  # noqa: BLE001
            _log(f"[GoRi Camera Director Skills] ComfyUI conditioning helper unavailable: {exc}")
            return clip.encode_from_tokens_scheduled(clip.tokenize(text))
        tokens = clip.tokenize(
            text,
            images=images_vl,
            keep_vision=len(ref_latents) == 0,
            prevent_empty_text=True,
        )
        conditioning = clip.encode_from_tokens_scheduled(tokens)
        if ref_latents:
            conditioning = node_helpers.conditioning_set_values(
                conditioning, {"reference_latents": ref_latents}, append=True
            )
        return conditioning

    @staticmethod
    def _combine_conditioning(base_conditioning, director_conditioning):
        if base_conditioning is None:
            return director_conditioning
        return base_conditioning + director_conditioning

    @staticmethod
    def _combine_prompt_text(base_text: str, camera_text: str) -> str:
        base = (base_text or "").strip().rstrip("., ")
        camera = (camera_text or "").strip()
        if not base:
            return camera
        if not camera:
            return base + "."
        return base + ". " + camera

    def run_prompt(self, clip, topic, preset, automation, shot, lens, angle,
                   composition, lighting, grade, motion, speed, amplitude,
                   motion2=AUTO,
                   prompt_in=None, provider="OpenAI", model="gpt-4o-mini",
                   api_key="", custom_base_url="", positive=None, negative=None,
                   vae=None, latent_image=None,
                   image_1=None, image_2=None, image_3=None, image_4=None,
                   image_5=None, image_6=None, image_7=None, image_8=None,
                   image_9=None, image_10=None, llm_hint="", unique_id=None,
                   prompt=None, extra_pnginfo=None,
                   vision_detail=VISION_DETAIL_DEFAULT,
                   pf_steps=0, pf_cfg=0.0, pf_denoise=0.0):
        image_items = [
            (1, image_1), (2, image_2), (3, image_3), (4, image_4), (5, image_5),
            (6, image_6), (7, image_7), (8, image_8), (9, image_9), (10, image_10),
        ]
        image_items = [(label, img) for label, img in image_items if img is not None]
        prompt_out, negative_text, _ = CameraDirector.run(
            self, topic=topic, preset=preset, automation=automation,
            shot=shot, lens=lens, angle=angle, composition=composition,
            lighting=lighting, grade=grade, motion=motion,
            speed=speed, amplitude=amplitude, motion2=motion2, prompt_in=prompt_in,
            provider=provider, model=model, api_key=api_key,
            custom_base_url=custom_base_url,
            image_items=image_items, llm_hint=llm_hint, unique_id=unique_id,
            prompt=prompt, extra_pnginfo=extra_pnginfo,
            vision_detail=vision_detail,
            pf_steps=pf_steps, pf_cfg=pf_cfg, pf_denoise=pf_denoise)
        camera = getattr(self, "_last_camera", dict(DEFAULTS))
        camera_text = build_camera_conditioning(camera)
        external_prompt = (prompt_in or "").strip()
        # latent 크기 점검 (base run에는 latent가 없어 여기서만 가능).
        for _warn in preflight_warnings(external_prompt or (topic or ""),
                                        camera, latent_mp=_latent_mp(latent_image)):
            _log(f"[Camera Director] 출발 점검 ⚠ {_warn}")
        # 국가 표현형·포즈 참조 가드는 참조 슬롯 정보를 함께 봐야 하므로
        # 바깥에서 확보한다 (negative 생성도 이 블록 밖에서 일어난다).
        last_count = getattr(self, "_last_image_count", 0)
        # **폴백 필수(2026-09-29 실측 결함 수정)**: Skills 는 base run() 을
        # 거치지 않으므로 _last_image_labels 가 항상 None 이었다. 그래서
        # 슬롯 정보가 필요한 가드(포즈 참조·캐릭터 시트·가구 DNA·국가 표현형)가
        # 전부 "슬롯 교집합 = 공집합" 이 되어 조용히 미작동했다.
        # 실제 실행에서 "3번은 포즈만" 인데 포즈 가드가 붙지 않은 것이 이 결함이다.
        # image_items 로 직접 폴백해야 한다(아래쪽 image_out 블록은 같은 폴백 사용).
        last_labels = (getattr(self, "_last_image_labels", None)
                       or [l for l, _ in (image_items or [])])
        if not last_count:
            last_count = len(image_items or [])
        # positive·negative가 **같은 텍스트 소스**를 본다. 이음새가 어긋나면
        # positive 지시의 짝인 negative가 조용히 사라진다(리뷰로 실제 확인).
        # base run 이 저장한 판정 소스(topic + LLM 확장 scene)를 재사용한다.
        # 예전엔 (prompt_in + topic) 뿐이라 LLM 확장이 negative 판정에서
        # 사라졌다 — positive 지시만 있고 짝인 negative 가 없는 상태(2026-09-28).
        _subject_pi = (getattr(self, "_last_subject_text", "") or "").strip()
        _eth_text_pi = " ".join(
            x for x in (external_prompt, topic, _subject_pi) if x)
        # 가드 판정은 base run() 이 resolve_guard_plan 으로 한 번만 한다.
        # 예전엔 여기서 같은 판정을 다시 돌렸는데(포즈·물리·시트·가구·부위),
        # **텍스트 소스가 달랐다** — 여기는 prompt_in 을 앞에 붙인
        # _eth_text_pi 를 쓴다. 그래서 양쪽이 어긋나 짝인 negative 가
        # 조용히 사라졌다(2026-09-28 실측: 지시가 한쪽_only 가 됨).
        # 이제 plan 하나로 양쪽이 같은 판정을 쓴다.
        _plan_pi = getattr(self, "_last_guard_plan", None)
        if _plan_pi is None:
            # run() 없이 단독 호출된 경우(테스트·재사용). 같은 함수로 판정한다.
            # 왜(Why) 인자에서 다시 유도하나 (2026-10-05 감사): 예전엔
            # _last_tier/_last_llm_hint 를 읽었지만 이 속성을 쓰는 곳이
            # 저장소에 하나도 없어 폴백이 항상 tier=""/llm_hint="" 로
            # 판정했다 — 유령 속성. run() 이 automation 에서 tier 를
            # 유도하는 것과 같은 식을 이 함수의 인자로 재현한다.
            _low_a_pi = (automation or "").lower()
            _tier_pi = ("llm" if "llm" in _low_a_pi
                        else "auto" if "auto" in _low_a_pi
                        else "manual")
            _plan_pi = resolve_guard_plan(
                _eth_text_pi, camera, last_count, last_labels, image_items,
                (image_items[0][1] if image_items else None), [],
                tier=_tier_pi, llm_hint=llm_hint)
        _gpos_pi = _plan_pi["positive"]
        _gflags_pi = _plan_pi["flags"]
        _px_sheet_pi = _plan_pi["pixel_sheet_slots"]
        if _px_sheet_pi:
            _log(f"[Camera Director] 참조 이미지 {'/'.join(_px_sheet_pi)}번에서 "
                 "캐릭터 시트 패턴 감지 (topic 문구와 무관)")
        _cs_text_pi = _gpos_pi["character_sheet"]
        _furn_pos_pi = _gpos_pi["furniture"]
        _remove_item_pi = _gflags_pi["remove_item"]
        _detail_def_pi = _gflags_pi["detail_def"]
        _anatomy_count_pi = _gflags_pi["anatomy_count"]
        _pose_pos_pi = _gpos_pi["pose"]
        _phys_pos_pi = _gpos_pi["physics"]
        _phys_neg_pi = _plan_pi["physics_neg"]
        if external_prompt:
            identity_anchor = build_identity_anchor(
                last_count, external_prompt, image_labels=last_labels)
            single_person_anchor = build_single_person_anchor(
                last_count, external_prompt, image_labels=last_labels)
            # Qwen 표준 경로에도 의상 교체 의도가 명확하면 의상 전용 가드를 둔다.
            # 왜(Why): 이 가드는 standalone 경로(assemble)에만 있어 prompt_in
            # 사용 시 의상 융합 방지 문구가 전혀 안 들어갔기 때문이다.
            outfit_anchor = outfit_guard(last_count, external_prompt)
            duo_anchor = build_duo_person_anchor(
                last_count, external_prompt, image_labels=last_labels)
            # duo(2인)일 때는 보조-role 제한 가드를 빼고 duo 정체성 보존을 둔다.
            # 왜(Why): role 제한은 image_2의 인물 역할을 금지해 남성이 사라지기 때문이다.
            role_anchor = "" if duo_anchor else build_secondary_role_anchor(
                last_count, external_prompt, image_labels=last_labels)
            base_text = self._combine_prompt_text(identity_anchor, single_person_anchor)
            base_text = self._combine_prompt_text(base_text, outfit_anchor)
            base_text = self._combine_prompt_text(base_text, duo_anchor)
            base_text = self._combine_prompt_text(base_text, role_anchor)
            base_text = self._combine_prompt_text(base_text, external_prompt)
            positive_text = self._combine_prompt_text(base_text, camera_text)
        else:
            positive_text = prompt_out
            single_person_anchor = ""
        # 아래 가드 병합은 prompt_in 경로에만 적용한다.
        # 왜(Why): standalone 경로의 prompt_out(assemble 결과)에는 매크로·노출·
        # 믹스·외양·발란스·시트 가드가 이미 들어 있어, 그대로 다시 붙이면
        # 같은 문구가 2회 중복되기 때문이다. prompt_in 경로는 앵커를 다시
        # 조립하므로 여기서 붙여야 한다.
        if external_prompt:
            detail_guard = macro_detail_guard(external_prompt or topic, camera)
            if detail_guard:
                positive_text = self._combine_prompt_text(positive_text, detail_guard)
            nudity_guard = nudity_anatomy_guard(external_prompt or topic)
            if nudity_guard:
                positive_text = self._combine_prompt_text(positive_text, nudity_guard)
            # 다중 참조 실행이면 믹스 가드도 Skills positive에 병합한다.
            # 왜(Why): base run()의 믹스 가드는 standalone assemble 결과에만 붙고,
            # prompt_in 경로는 앵커를 다시 조립하므로 유실되기 때문이다.
            if _gflags_pi["mix_guard"]:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _gpos_pi["mix_guard"])
            # 10번 외양 참조 실행이면 외양 가드도 Skills positive에 병합한다.
            if getattr(self, "_last_appearance_ref", False):
                positive_text = self._combine_prompt_text(positive_text,
                                                          APPEARANCE_REF_POSITIVE)
                positive_text = self._combine_prompt_text(
                    positive_text, APPEARANCE_HAIR_REALISM_POSITIVE)
            if _gflags_pi["body_balance"]:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["body_balance"])
            # 부위별 디테일 경계·가구 DNA도 Skills positive에 병합한다
            # (base run과 **동일 판정** — 하나만 갱신되면 positive/negative가
            #  어긋나 짝인 방어가 사라진다).
            if _detail_def_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["detail_def"])
            if _anatomy_count_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["anatomy_count"])
            if _cs_text_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _cs_text_pi)
            if _furn_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _furn_pos_pi)
            # (캐릭터 시트 문구는 위에서 _cs_text_pi 로 이미 병합했다.
            # 실행 간 캐시로 같은 문구를 또 붙이면 110단어어 positive 가 두 번
            # 들어가 token 을 중복 소비한다. 2026-09-28 실행 간 캐시 제거,
            # 2026-09-29 죽은 속성까지 정리)
            # 스케일 일관 가드도 prompt_in 경로에 병합한다.
            # (standalone는 assemble에 이미 포함. 외부 프롬프트 기준 판정)
            if _needs_scale_guard(external_prompt or topic, camera):
                positive_text = self._combine_prompt_text(positive_text,
                                                          SCALE_COHERENCE_POSITIVE)
            # 국가 표현형 가드도 prompt_in 경로에 병합한다.
            # (국가명은 한글 위젯 topic에만 있을 수 있어 양쪽 다 본다)
            # 참조 이미지가 신원을 고정하는 실행은 억제된다 (positive/negative 동일 판정).
            _eth_pos_pi, _ = _ethnicity_guard(_eth_text_pi, last_count, last_labels)
            if _eth_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _eth_pos_pi)
            # 동물 종 보존 가드도 prompt_in 경로에 병합한다.
            if _is_animal_subject(_eth_text_pi):
                positive_text = self._combine_prompt_text(
                    positive_text, ANIMAL_SPECIES_POSITIVE)
            # 포즈 참조 가드도 prompt_in 경로에 병합한다 (base run과 동일 판정).
            if _pose_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _pose_pos_pi)
            # 물리·공간 가드도 prompt_in 경로에 병합한다.
            if _phys_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _phys_pos_pi)
            # 품질 가드도 prompt_in 경로에 병합한다 (base run의
            # assemble → add_quality_guard 에 해당. 왜(Why): 이 경로에만
            # 빠져 있어 prompt_in 실행에서 품질 지시가 없었다
            # 2026-10-07 감사). 동물 전용 주제면 동물용 가드를 쓴다
            # (add_quality_guard 와 동일 분기 — 사람 손가락 지시가
            # 동물 그림과 정면 충돌한다).
            _only_animal_pi = (_is_animal_subject(_eth_text_pi)
                               and not _is_human_subject(_eth_text_pi))
            positive_text = self._combine_prompt_text(
                positive_text,
                QUALITY_GUARD_ANIMAL if _only_animal_pi else QUALITY_GUARD)
        prevent_duplicates = bool(single_person_anchor) if external_prompt else False
        # negative도 positive와 **같은 텍스트 소스**를 본다 (topic + prompt_in).
        # 왜(Why): 이음새가 어긋나면 positive에 붙은 지시의 짝인 negative가
        # 조용히 사라진다 — 실측으로 국가 표현형(브라질)·동물 가드에서 확인됨.
        # 국가명은 한글 topic 칸에만 있을 수 있어 prompt_in만 보면 놓친다.
        negative_text = build_camera_negative(
            camera, prevent_duplicates=prevent_duplicates,
            topic=_eth_text_pi, image_count=last_count,
            image_labels=last_labels,
            pose_ref=bool(_pose_pos_pi), physics_neg=_phys_neg_pi,
            detail_def=_detail_def_pi, furniture=bool(_furn_pos_pi),
            remove_item=_remove_item_pi, anatomy_count=_anatomy_count_pi,
            character_sheet=bool(_cs_text_pi))
        # LLM이 제안한 extra negative가 있으면 카메라 negative 뒤에 병합한다.
        # 왜(Why): base run()은 llm_extra를 build_negative에 넣지만, 위에서
        # 카메라 전용 negative로 덮어쓰면서 조용히 버려졌기 때문이다.
        llm_extra_text = (getattr(self, "_last_llm_extra", "") or "").strip().rstrip("., ")
        if llm_extra_text:
            negative_text = negative_text.rstrip("., ") + ", " + llm_extra_text
        # llm_hint 사용 실행이면 검열 방어어도 Skills negative에 병합한다.
        # 왜(Why): Skills 경로는 negative를 build_camera_negative로 다시 만들어
        # base run()의 방어어가 유실되기 때문이다.
        if _gflags_pi["hint_defense"]:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + HINT_DEFENSE_NEGATIVE)
        # 다중 참조 실행이면 믹스 가드 방어어도 Skills negative에 병합한다.
        if _gflags_pi["mix_guard"]:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + MIX_GUARD_NEGATIVE)
        # 10번 외양 참조 실행이면 컷 삽입 방어어도 Skills negative에 병합한다.
        if getattr(self, "_last_appearance_ref", False):
            negative_text = (negative_text.rstrip("., ")
                             + ", " + APPEARANCE_REF_NEGATIVE)
        # 인물 신체 발란스 방어어도 병합한다.
        if _gflags_pi["body_balance"]:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + BODY_BALANCE_NEGATIVE)
        # (캐릭터 시트 negative 는 build_camera_negative(character_sheet=) 가
        # 두 상수를 이미 넣는다. 수동 병합은 중복. 2026-09-28 제거)
        try:
            # 시트 슬롯은 **언어 모델(vision) 에만** 넣고 VAE reference
            # latent 에서는 제외한다 — 그래야 diffusion 이 시트
            # 레이아웃(6뷰 배치)을 따라 그리지 않는다.
            # 왜(Why) 실측 2026-09-29: 시트를 reference 로 넣으면
            # 결과가 **시트 그대로** 렌더링됐다. 분리 실험으로 확정 —
            # 시트 없으면 항상 1인 정상, 시트 있으면 topic 에 장면을
            # 명시해도 4뷰. 프롬프트로는 이길 수 없다(pixel 힌트).
            prepared = self._prepare_qwen_image_data(
                image_items, vae=vae, latent_image=latent_image,
                latent_skip_labels=_px_sheet_pi
            )
        except Exception as exc:  # noqa: BLE001
            # reference 준비 실패해도 실행은 살린다 — 텍스트 전용으로 폴백.
            _log(f"[GoRi Camera Director Skills] reference 준비 실패, 텍스트 폴백: {exc}")
            prepared = ([], None)
        try:
            positive_out = self._qwen_image_edit_conditioning(
                clip, positive_text, prepared=prepared
            )
        except Exception as exc:  # noqa: BLE001
            # vision 인코딩 실패 시 텍스트만으로 재시도 (reference 없이도 동작).
            _log(f"[GoRi Camera Director Skills] vision 인코딩 실패, 텍스트 폴백: {exc}")
            positive_out = self._qwen_image_edit_conditioning(
                clip, positive_text, prepared=([], None)
            )
        # negative는 텍스트만 인코딩한다. 왜(Why): negative 문구는 카메라/영상
        # 실패 모드라 vision 참조가 불필요하고, 이미지 포함 인코딩을 반복하면
        # Qwen Vision 인코딩이 2회 실행 + reference_latents가 positive/negative
        # 양쪽에 첨부돼 KSampler가 reference를 이중 처리하기 때문이다.
        negative_cond = self._qwen_image_edit_conditioning(
            clip, negative_text, prepared=([], None)
        )
        negative_out = self._combine_conditioning(negative, negative_cond)
        if positive is not None:
            _log("[GoRi Camera Director Skills] positive conditioning 입력은 새 문자열 경로에서 무시됩니다. "
                 "Qwen positive_prompt 문자열을 prompt_in에 연결하세요.")
        _log("[GoRi Camera Director Skills] positive_out/negative_out/prompt_out 출력 "
              f"(single_encode={bool(external_prompt or positive is None)})")
        # image_out: 역할 계획(plan)이 선출한 주 reference 이미지를 그대로 통과.
        # I2V 시작 프레임·업스케일 등 후속 노드에 연결할 수 있다. 미연결이면 None.
        # 왜(Why): 항상 첫 연결을 통과하면(구버전) 첫 연결이 사물인 워크플로
        # (1번 핸드백 + 2번 여성)에서 핸드백이 나갔다(정밀 검토 발견 #5).
        last_labels = getattr(self, "_last_image_labels", None) or [l for l, _ in image_items]
        image_out = None
        main_slot = None
        main_img = None
        try:
            main_slot = _person_object_plan(
                external_prompt or (topic or ""), last_labels)["main"]
        except Exception:
            main_slot = None
        if image_items:
            # 주 슬롯 이미지는 image_out과 reference_latent_out이 **같은 픽셀**을
            # 써야 짝이 맞는다. 한 번만 찾고 두 출력에 함께 쓴다 (리뷰로 확인된 복붙).
            for label, img in image_items:
                if label == main_slot:
                    main_img = img
                    break
            if main_img is None:
                main_img = image_items[0][1]
            image_out = main_img
        # 기준 latent 출력 (3번 교정 노드용). _prepare가 이미 인코딩한 결과를
        # 캐시 키로 조회만 한다 — 재인코딩 없음. vae 미연결이면 None.
        reference_latent_out = None
        try:
            if vae is not None and main_img is not None:
                _tw, _th = CameraDirectorEncode._reference_target_size(latent_image)
                _cached = _qwen_ref_cache_get(
                    _qwen_ref_cache_key(main_img, _tw, _th, vae), vae)
                if _cached is not None and _cached[1] is not None:
                    reference_latent_out = {"samples": _cached[1]}
        except Exception as e:
            # 왜(Why) 말하나 (2026-10-07 라운드 2): 기준 latent 가 조용히
            # None 이 되면 3번 교정 노드가 "camera 기준 없음" 으로 죽고
            # 원인을 찾을 수 없다. 한 번만 말한다.
            _note_once("camera.ref_latent_lookup",
                       "[Camera Director] 기준 latent 조회 실패 — 캐시 키 계산"
                       "또는 이동 중 오류 (기준 latent 없이 진행): "
                       f"{type(e).__name__}: {str(e)[:80]}")
            reference_latent_out = None
        _release_vram()
        return (positive_out, negative_out, positive_text, image_out,
                reference_latent_out)



# ---------------------------------------------------------------------------
# Qwen reference conditioning 속도 최적화용 캐시/상한.
#
# 왜(Why): 같은 reference 이미지는 프롬프트를 바꿔도 매 실행마다
# common_upscale(lanczos) + vae.encode()를 반복했다. VAE encode 1회가
# 수초대라 반복 실행 체감 속도를 지배하므로, 내용 해시+목표 크기 키로
# 재사용한다. latent가 2~3MP여도 reference는 1MP 상한으로 묶어
# upscale/VAE/KSampler 부하가 해상도 비례로 불어나는 것을 막는다.
# ---------------------------------------------------------------------------

QWEN_REF_MAX_PIXELS = 1024 * 1024  # reference conditioning 1MP 상한


_QWEN_REF_CACHE: dict = {}


_QWEN_REF_CACHE_ORDER: list = []


# (왜) 12 인가 (2026-10-02 실측): 노드가 받는 참조 이미지는 `image_1` ~ `image_10`
# 으로 **최대 10장**(L4906-4915)인데 용량이 8 이었다. L4805 가 라벨 순서로
# 매 실행 순차 접근하므로, working set(10) > 용량(8) 이면 LRU 이 매 실행
# 전부 미스가 된다 — 순차 스캔은 LRU 최악 패턴이다. 측정한 계단:
#   1~8장  → 매 실행 0 encodes (정상 동작)
#   9장    → 매 실행 9/9 encodes  (적중률 0%)
#   10장   → 매 실행 10/10 encodes (적중률 0%)
# 즉 지원 설정 10개 중 2개에서 캐시가 영영 이득이 없다. 용량은 한 실행의
# 서로 다른 키 수(10) 이상이어야 한다. 여유 2칸은 이미지를 갈아끼운 직후의
# 혼합 구간용이다.
# (왜) 12 면 되는가: latent 는 put 에서 `.cpu()` 로 내려간다(L4695) — 그래서
# VRAM 이 아니라 시스템 RAM 을 쓴다. 1MP 기준 한 장 0.25MB, 12장 3MB.
# (왜) 무한대 는 아닌가: 키가 VAE weakref 로 검증되므로 죽은 VAE 항목은
# 걸러지지만, dict 는 자라기만 하므로 상한이 있어야 evict 규칙이 성립한다.
_QWEN_REF_CACHE_MAX = 12


_QWEN_REF_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# 실행 이력 전송 — GoRi 텔레메트리 허브 연동.
#
# 왜(Why): 실행 이력은 custom_nodes/ComfyUI_workflows_MY_data_save 허브에서
# 일원 관리한다(노드별 하위 폴더 분류). 노드는 파일에 직접 쓰지 않고 허브
# 서버 엔드포인트(POST /gori_telemetry/write)로 기록을 넘긴다.
#
# 개인정보/프라이버시 원칙 (사용자 요구, 2026-09-27):
#   - 모든 데이터는 로컬 허브의 data/ 안에만 저장된다. 외부 전송 없음.
#   - topic 원문은 전송하지 않는다(길이만 기록) — 내용 유출 표면 최소화.
#   - 전송은 백그라운드 스레드로 수행되며 실패해도 조용히 무시된다 —
#     노드 실행을 절대 막지 않는다.
# ---------------------------------------------------------------------------
TELEMETRY_URL = "http://127.0.0.1:8188/gori_telemetry/write"


_TELEMETRY_SENDER = None  # 테스트 주입 지점(None이면 표준 전송기 사용)


def _default_telemetry_sender(record: dict) -> None:
    """허브 엔드포인트로 실행 이력 전송. 실패해도 조용히 무시한다."""
    try:
        import urllib.request as _u
        req = _u.Request(
            TELEMETRY_URL,
            data=json.dumps(record, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        _u.urlopen(req, timeout=3).close()
    except Exception:
        pass


def _post_telemetry(**record) -> None:
    """실행 1회를 허브로 전송. 절대 노드 실행을 막지 않는다.

    왜(Why) 기본 꺼짐인가 (2026-10-02 실측): 매 실행마다 데몬 스레드 1개 +
    DNS(getaddrinfo 74ms) + 소켓을 쓰고 받는 서버가 없다. ComfyUI 로그에
    엔드포인트가 없고, 이 저장소에도 수신 코드가 없다. 켜려면
    `GORI_TELEMETRY=1` 환경변수를 둔다. 테스트 주입(`_TELEMETRY_SENDER`)은
    환경변수와 무관하게 항상 동작한다.
    """
    try:
        if _TELEMETRY_SENDER is None and os.environ.get("GORI_TELEMETRY", "0") != "1":
            return
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        record["node"] = "camera_director"
        if _TELEMETRY_SENDER is not None:
            _TELEMETRY_SENDER(record)  # 테스트: 동기 호출로 결정적 검증
        else:
            threading.Thread(target=_default_telemetry_sender,
                             args=(record,), daemon=True).start()
    except Exception:
        pass


def _thumb_digest(image, length: int = 16):
    """이미지 썸네일 sha1 공통 헬퍼. (shape, digest) 반환, 실패 시 (None, None).

    왜(Why): _thumb_sig와 _qwen_ref_cache_key가 동일한 축소+해시 블록을
    중복로 가지고 있어 한쪽만 수정되는 퇴행 위험이 있었다.
    (..., H, W, C) 형태의 ComfyUI IMAGE 텐서/배열을 전제로 한다.

    (왜) **블록 평균**인가, 점 샘플이 아닌가 (2026-10-02 실측): 이전에는
    `image[::h//16, ::w//16]` 로 **점**을 골랐다. 1024x1024 면 64px 간격이라
    샘플 사이 63x63 px 가 해시에서 사라진다. 실측 결과 8x8 워터마크 200개 중
    **199개(100%)가 해시를 못 바꿨다** — 1024px 이미지 위 8px 표식은 흔한
    작업이다. 캐시가 "바뀐 이미지에 옛 latent" 를 조용히 돌려주므로 캐시가
    없느니 나빴다. 오프셋 그리드 3장은 100% → 98%로effect가 거의 없었다
    (격자가 너무 성깁니다). 블록 평균(adaptive_avg_pool2d, 64x64)은 **0/200**.
    비용은 이미지당 약 1.4ms — VAE 인코딩 1회(수십~수백 ms)보다 작고,
    첫 캐시 적중에서 회수된다.
    (왜) 64 인가: 16/32/64 모두 0/200 이라 가장 싼 16 을 고르면 되지만,
    그물코가 촘촘할수록 국소 변경이 여러 셀에 걸려 더 안전하다. 64x64x3 =
    12KB 해시. 32 는 측정값이 같아도 여유를 두지 않았다 — 근거 없는 상수
    늘리기를 피했다.

    (왜) list 같은 입력도 해시를 얻나: 이전엔 실패해 `noid:{id(image)}`
    키로 내려갔고, CPython 은 GC 뒤 주소를 재배정한다(실측 299/300 = 100%).
    그 키로 서로 다른 입력이 같은 캐시 항목을 맞는다. numpy 로 한 번 더
    변환해 해시를 얻도록 했고, 이제 `noid` 로 내려가는 것은 shape 조회가
    불가능한 값(예: None)뿐이다.
    """
    try:
        import hashlib as _hl
        import numpy as _np
        import torch as _t
        import torch.nn.functional as _tf
        # (왜) shape 를 원본에서 읽지 않는가: list 를 넘기면 `.shape` 가 없어
        # 여기서 죽는다. numpy 로 먼저 바꿔야 list·numpy·tensor 가 한 갈래로
        # 합쳐진다 — 이전엔 list 가 `noid:` 키로 내려갔다.
        raw = image.detach().cpu() if hasattr(image, "detach") else image
        x = _np.asarray(raw, dtype=_np.float32)
        shape = tuple(int(d) for d in x.shape)
        if x.ndim == 4:
            x = x[0]
        if x.ndim != 3 or x.shape[0] < 4 or x.shape[1] < 4:
            if x.ndim < 3:
                # 3차원이 아닌 값(예: None, 스칼라)은 식별할 수 없다.
                return shape, None
            # 너무 작아 블록 평균이 불가능하면 있는 범위만 해시한다.
            return shape, _hl.sha1(_np.ascontiguousarray(
                x[:, :, :3]).tobytes()).hexdigest()[:length]
        t = _t.from_numpy(_np.ascontiguousarray(x[:, :, :3]))
        pooled = _tf.adaptive_avg_pool2d(
            t.permute(2, 0, 1)[None], (64, 64))[0]
        return shape, _hl.sha1(
            _np.ascontiguousarray(
                pooled.permute(1, 2, 0).numpy()).tobytes()
        ).hexdigest()[:length]
    except Exception:
        return None, None


def _thumb_sig(image) -> str:
    """이미지 내용 식별용 짧은 해시 (LLM 캐시 폴백 키용).

    왜(Why): base64 변환 실패 시 대체 키가 1번 이미지 수치에만 의존해
    2번 이후 교체가 캐시에 미반영되는 stale 문제가 있었기 때문이다.
    """
    _shape, digest = _thumb_digest(image, length=12)
    if digest:
        return digest
    # 왜(Why) id(object) 가 아니라 매번 새 키인가 (2026-10-07 라운드 2):
    # `noid:{id(image)}` 는 CPython 이 GC 뒤 주소를 재활용하면 서로 다른
    # 입력이 같은 캐시를 맞는다(실측 50회 중 35회 재사용). 식별을 못 했으면
    # **매번 새 키 = 항상 미스 = 재계산**이 정답이다 — 재계산은 틀리지 않는다.
    return f"noid:{uuid.uuid4().hex}"


def _qwen_ref_cache_key(image, target_w, target_h, vae) -> str:
    """reference 캐시 키: 내용 썸네일 해시 + 목표 크기 + VAE 식별자."""
    shape, digest = _thumb_digest(image, length=16)
    if digest is None:
        # 식별 불가 — 새 키로 항상 미스시킨다(_thumb_sig 와 같은 이유:
        # id 재활용 충돌 방지). 캐시는 상한 12 로 정리된다.
        return f"noid:{uuid.uuid4().hex}|{target_w}x{target_h}|vae:{id(vae)}"
    return f"{shape}|{target_w}x{target_h}|vae:{id(vae)}|{digest}"


def _qwen_ref_cache_get(key, vae=None):
    with _QWEN_REF_LOCK:
        cached = _QWEN_REF_CACHE.get(key)
    if cached is None:
        return None
    rgb, latent, vae_ref = cached
    # 왜(Why): 캐시가 VAE 객체를 강한 참조로 들면 그 VAE가 ComfyUI에서
    # 영영 회수되지 않아 작업 끝난 뒤에도 VRAM을 붙잡는다. weakref로만
    # 동일성 비교에 쓴다. 죽은 VAE면 캐시 미스로 보고 재인코딩한다.
    try:
        if vae_ref() is None:
            # VAE가 회수됨 → 미스(재인코딩). 살아 있는 객체만 재사용한다.
            return None
        if vae_ref() is not vae:
            return None
    except TypeError:
        # weakref 불가 객체면 강한 참조로 되돌린다(동작 동일, 단 만료 안 됨).
        if vae_ref is not vae:
            return None
    if latent is not None:
        # 캐시는 CPU에 둔다. GPU 텐서를 상주시키면 empty_cache()로도 안 풀린다.
        # 조회할 때만 원래 VAE 디바이스로 되돌린다 (이동 비용 << VAE encode).
        _dev = getattr(vae, "device", None) if vae is not None else None
        if _dev is not None and hasattr(latent, "to"):
            try:
                latent = latent.to(_dev)
            except Exception:
                pass
    return rgb, latent


def _qwen_ref_cache_put(key, value) -> None:
    rgb, latent, vae = value
    # 캐시에는 CPU latent + VAE weakref만 남긴다 (GPU 점유·VAE 상주 방지).
    if latent is not None and hasattr(latent, "cpu"):
        try:
            latent = latent.cpu()
        except Exception:
            pass
    try:
        vae_ref = weakref.ref(vae)
    except TypeError:
        vae_ref = vae
    with _QWEN_REF_LOCK:
        if key in _QWEN_REF_CACHE:
            _QWEN_REF_CACHE_ORDER.remove(key)
        _QWEN_REF_CACHE[key] = (rgb, latent, vae_ref)
        _QWEN_REF_CACHE_ORDER.append(key)
        while len(_QWEN_REF_CACHE_ORDER) > _QWEN_REF_CACHE_MAX:
            _QWEN_REF_CACHE.pop(_QWEN_REF_CACHE_ORDER.pop(0), None)


def clear_qwen_ref_cache() -> None:
    """reference 캐시 비우기 (테스트/디버그용)."""
    with _QWEN_REF_LOCK:
        _QWEN_REF_CACHE.clear()
        _QWEN_REF_CACHE_ORDER.clear()
