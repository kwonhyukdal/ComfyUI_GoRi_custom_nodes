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
__version__ = "1.9.6"


import json
import os
import re
import sys
import threading
import time
import weakref

try:
    from . import llm_client
except ImportError:  # 스탠드얼론/테스트 실행용
    import llm_client

# 왜(Why) realpath인가: macOS/Linux 개발에서는 `custom_nodes/노드폴더`를 개발
# 폴더로 심볼릭 링크하는 것이 흔하다. abspath는 링크 경로를 그대로 쓰므로
# keywords_ko_en.json·presets.json을 못 찾아 내장 기본값으로 조용히 떨어진다
# (사용자에게는 "설정이 안 먹힌 것처럼" 보인다). realpath는 링크를 따라간다.
HERE = os.path.dirname(os.path.realpath(__file__))


def _log(msg: str) -> None:
    """Windows(cp949 등) 콘솔에서도 인코딩 오류로 노드가 죽지 않게 한다."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(msg.encode(enc, "replace").decode(enc, errors="replace"),
              flush=True)


_ONCE_SEEN = set()


def _note_once(key: str, msg: str) -> None:
    """같은 키의 메시지를 **한 번만** 말한다.

    왜(Why) 조용한 실패에 로그를 붙이면서도 스팸을 피하는가 (2026-10-01):
    `except Exception: return None` 이 이 파일에 **45곳** 있다. 전부 로그를
    남기면 사용자가 읽을 수 없다 — 그래서 "그냥 한 번" 이 정답이다.
    키퍼의 `_note_once` 와 같은 계약이며, 그쪽이 먼저 있었다.

    왜(Why) 조용한 실패가 문제인가: numpy 부재도 `except Exception` 에 걸려
    "시트 아님" 이 되고, 그 결과 시트 참조가 **조용히 withheld** 된다
    (2026-10-01 실측: 카메라 노드가 한 장짜리 사진을 시트로 오판해 기준
    latent 를 의도적으로 뺐고, 키퍼는 "camera 기준 없음" 으로 죽었다).
    """
    if key in _ONCE_SEEN:
        return
    _ONCE_SEEN.add(key)
    _log(msg)


def _load(name: str, fallback):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:  # 파일 손상/누락에도 노드는 뜨게 한다
        _log(f"[Camera Director] {name} 로드 실패: {e} → 내장 기본값 사용")
        return fallback


PRESETS = _load("presets.json", {})
KEYWORDS = _load("keywords_ko_en.json", {})

AUTO = "자동 (auto)"
CUSTOM = "직접 설정 (custom)"

# ---------------------------------------------------------------------------
# 목록 A — 한글 라벨 → 영문 카메라 조항 (드롭다운 표기와 1:1)
# ---------------------------------------------------------------------------

SHOT = {
    "극접 (ECU)": "extreme close-up shot",
    "근접 (CU)": "close-up shot",
    "중근접 (MCU)": "medium close-up shot",
    "중경 (MS)": "medium shot",
    "전신 (FS)": "full body shot",
    "원경 (WS)": "wide shot",
    "극원경 (EWS)": "extreme wide shot",
}

TOPIC_SHOT_PHRASES = {
    "극접 (ECU)": ("extreme close-up shot", "extreme closeup shot", "ecu shot",
                   "극접", "extreme close-up"),
    "근접 (CU)": ("close-up shot", "closeup shot", "close up shot", "cu shot",
                  "근접"),
    "중근접 (MCU)": ("medium close-up shot", "medium closeup shot", "mcu shot",
                    "중근접", "medium close-up"),
    "중경 (MS)": ("medium shot", "mid shot", "중경"),
    "전신 (FS)": ("full-body shot", "full body shot", "full-length shot", "fs shot",
                  "전신", "full body", "full-body"),
    "원경 (WS)": ("wide shot", "ws shot", "원경"),
    "극원경 (EWS)": ("extreme wide shot", "extreme wide-shot", "ews shot",
                    "극원경", "extreme wide"),
}


def _longest_shot_label(text: str, exclude: str = "") -> str:
    """텍스트에서 샷 구문을 찾되, 가장 길게(구체적으로) 일치한 라벨 하나를 반환한다.

    왜(Why): 한글 라벨은 서로를 부분 문자열로 포함한다("중근접"⊃"근접",
    "극원경"⊃"원경"). 단순 any() 순회는 짧은 라벨이 먼저 잡혀 오인한다.
    최장 일치 원칙으로 구체 표현이 이기게 한다. exclude는 최종 확정 샷으로,
    그 라벨의 표현은 무시한다(모순 아님).
    """
    s = (text or "").lower()
    if not s:
        return ""
    best_label, best_len = "", 0
    for label, phrases in TOPIC_SHOT_PHRASES.items():
        if label == exclude:
            continue
        for p in phrases:
            if p in s:
                if len(p) > best_len:
                    best_label, best_len = label, len(p)
            elif p.endswith(" shot"):
                bare = p[:-5]
                if len(bare.split()) >= 2 and bare in s and len(bare) > best_len:
                    best_label, best_len = label, len(bare)
    return best_label

LENS = {
    "14mm 초광각 (ultra-wide)": "shot on a 14mm ultra-wide lens, strong perspective drama",
    "24mm 광각 (wide)": "shot on a 24mm wide-angle lens, deep scene context",
    "35mm 스냅 (snapshot)": "shot on a 35mm lens, natural documentary perspective",
    "50mm 표준 (standard)": "shot on a 50mm lens, natural perspective",
    "85mm f/1.4 (bokeh)": "shot on an 85mm lens at f/1.4, shallow depth of field, creamy bokeh",
    "135mm 망원 (telephoto)": "shot on a 135mm telephoto lens, compressed background",
    "200mm 망원 (super tele)": "shot on a 200mm telephoto lens, strong background compression",
    "100mm 매크로 (macro)": "shot on a 100mm macro lens, crisp fine detail",
}

ANGLE = {
    "수평 (eye-level)": "eye-level camera angle",
    "로우앵글 (low angle)": "low angle looking up, heroic framing",
    "하이앵글 (high angle)": "high angle looking down",
    "편각 (dutch angle)": "Dutch tilt, diagonal horizon",
    "탑다운 (top-down)": "top-down overhead camera",
    "개미눈 (worm's eye)": "worm's-eye view from ground level",
    "어깨뒤 (OTS)": "over-the-shoulder framing",
    "측면 (side profile)": "side profile framing",
    # 아래 5종은 MIT 라이선스 자료를 규격에 맞게 변형한 것이다 (2026-10-02).
    # 출처: xoxxel/camera-prompts (MIT) — 40종 카메라 앵글의 영어 키워드와
    # 효과 서술. 한글 라벨 + 영어 절(clause) 형식으로 맞추고, 서술은 우리
    # 프롬프트 톤(짧은 절, 마침표 없음)에 맞게 줄였다. 원문 예시는 자동차
    # 기준이라 인물·장면에 통용되는 부분만 취했다.
    # 왜(Why) 새로 넣나: POV·반사·파노라마·후면3/4·히어로는 기존 8종에 없고
    # 사용자가 topic 에 써도 매칭이 안 됐다. 드롭다운에 나오게 한다.
    "일인칭 (POV)": "first-person point of view shot, immersive eye-level presence",
    "반사 (reflection)": "reflection shot with mirrored surface, symmetric depth",
    "파노라마 (panoramic)": "ultra-wide panoramic shot, expansive horizon and scale",
    "후면 3/4 (three-quarter rear)": "three-quarter rear view, back and side visible",
    "와이드 히어로 (wide hero)": "wide hero shot from low angle, subject monumental in environment",
}

COMPOSITION = {
    "삼분할 (rule of thirds)": "rule-of-thirds composition, subject on a power third",
    "중앙 대칭 (centered)": "centered symmetric composition",
    "리딩라인 (leading lines)": "leading lines guiding the eye to the subject",
    "대칭 (symmetry)": "balanced symmetrical composition",
    "프레임 인 프레임 (frame-in-frame)": "framed within a natural frame",
    "여백 (negative space)": "generous negative space around the subject",
    "전경 가림 (foreground occlusion)": "foreground element partially occluding, adding depth",
    "대각선 (diagonal)": "dynamic diagonal composition",
}

LIGHTING = {
    "3점 스튜디오 (three-point)": "controlled three-point studio lighting",
    "골든아워 (golden hour)": "warm golden hour light",
    "블루아워 (blue hour)": "cool blue hour light",
    "흐린 부드러움 (soft overcast)": "soft overcast light, no harsh shadows",
    "창가빛 (window light)": "soft directional window light",
    "네온 (neon)": "neon glow with colored rim highlights",
    "림라이트/실루엣 (rim light)": "strong backlight, bright rim light silhouette",
    "램브란트 (Rembrandt)": "dramatic Rembrandt key light",
    "하이키 (high key)": "bright high-key lighting",
    "로우키 (low key)": "moody low-key lighting, deep shadows",
}

GRADE = {
    "시네마틱 필릭 (cinematic)": "cinematic film grade, rich contrast, subtle grain",
    "비비드 포스터 (vivid)": "vivid poster-grade color, deep blacks, punchy highlights",
    "절제된 프리미엄 (premium)": "restrained premium grade, muted tones",
    "틸-오렌지 (teal & orange)": "teal-and-orange color grade",
    "35mm 필름 (film look)": "35mm film look, warm analog grain",
    "클린 커머셜 (commercial)": "clean commercial grade, accurate colors",
    "느와르 (noir)": "high-contrast black-and-white noir look",
    "빈티지 (vintage)": "vintage faded grade",
}

MOTION = {
    "없음 (none)": "",
    "정지 (static)": "locked-off static camera, no camera movement",
    "슬로우 푸시인 (push-in)": "push-in toward the subject",
    "풀백 (pull-back)": "pull-back away from the subject",
    "돌리 인 (dolly in)": "dolly in",
    "돌리 아웃 (dolly out)": "dolly out",
    "트럭 좌 (truck left)": "truck left",
    "트럭 우 (truck right)": "truck right",
    "팬 좌 (pan left)": "pan left",
    "팬 우 (pan right)": "pan right",
    "틸트 상 (tilt up)": "tilt up",
    "틸트 하 (tilt down)": "tilt down",
    "크레인 상 (crane up)": "crane up",
    "크레인 하 (crane down)": "crane down",
    "오빗 (orbit)": "orbit circling around the subject",
    "핸드헬드 (handheld)": "handheld camera with organic drift",
    "스테디캠 (steadicam)": "smooth steadicam glide",
    "홉팬 (whip pan)": "fast whip pan",
    "줌 인 (zoom in)": "slow zoom in",
    "랙포커스 (rack focus)": "rack focus pull between planes",
    "팔로우 (follow)": "follow shot tracking the subject",
}

SPEED = {"느림 (slow)": "slow", "보통 (normal)": "", "빨름 (fast)": "fast"}
AMPLITUDE = {"약간 (subtle)": "subtle", "보통 (normal)": "", "강하게 (dramatic)": "dramatic"}

# 규칙(auto) tier 기본값 — 키워드 미매칭 시 사용
DEFAULTS = {
    "shot": "중경 (MS)", "lens": "50mm 표준 (standard)", "angle": "수평 (eye-level)",
    "composition": "삼분할 (rule of thirds)", "lighting": "흐린 부드러움 (soft overcast)",
    "grade": "시네마틱 필릭 (cinematic)", "motion": "없음 (none)",
    "motion2": "없음 (none)",
    "speed": "보통 (normal)", "amplitude": "약간 (subtle)",
}

_TABLES = {
    "shot": SHOT, "lens": LENS, "angle": ANGLE, "composition": COMPOSITION,
    "lighting": LIGHTING, "grade": GRADE, "motion": MOTION,
    "motion2": MOTION,
    "speed": SPEED, "amplitude": AMPLITUDE,
}


def preset_names() -> list:
    return [AUTO] + list(PRESETS.keys()) + [CUSTOM]


# ---------------------------------------------------------------------------
# B1 — provider ↔ model 불일치 자동 교정
# ---------------------------------------------------------------------------

PROVIDER_DEFAULT_MODELS = {
    "OpenAI": "gpt-4o-mini",
    "Anthropic": "claude-3-5-haiku-latest",
    "Ollama": "llama3.2",
    "Gemini": "gemini-1.5-flash",
    "OpenRouter": "google/gemini-flash-1.5",
    "Groq": "llama-3.2-90b-vision-preview",
    "DeepSeek": "deepseek-chat",
    "Mistral": "pixtral-12b-2409",
}

_MODEL_PREFIX = {
    "OpenAI": ("gpt", "o1", "o3", "chatgpt"),
    "Anthropic": ("claude",),
    "Gemini": ("gemini-",),
}


def resolve_model(provider: str, model: str) -> str:
    """provider와 어긋나는 모델명을 해당 provider 기본 모델로 교정한다.

    왜(Why): model 위젯 기본값은 gpt-4o-mini 하나뿐이라 provider를
    Anthropic/Ollama 등으로 바꿔도 잘못된 모델명이 전송되고, API 오류 후
    조용히 규칙 폰백이 되어 'AI 판단'이 실제로는 규칙 결과로 나오는
    문제가 있었다. 자유 모델명 호환을 위해 위젯은 STRING으로 유지하고
    전송 직전에 한 번만 교정한다.
    """
    provider = provider or ""
    model = (model or "").strip()
    default = PROVIDER_DEFAULT_MODELS.get(provider, model)
    if not model:
        return default
    # LM Studio / OpenRouter는 모델명이 너무 다양해 접두사 검증이 불가능하다.
    # 입력값을 그대로 쓰고, LM Studio는 비우면 llm_client가 자리표시자 처리.
    # Custom (OpenAI 호환)도 사용자가 엔드포인트의 모델명을 직접 넣는다 —
    # 비우면 llm_client가 명확한 안내와 함께 실패한다.
    if provider in ("LM Studio", "OpenRouter") or provider.startswith("Custom"):
        return model
    low = model.lower()
    # Ollama/Groq/DeepSeek/Mistral에 OpenAI/Anthropic 모델명이 그대로 전송되는
    # 실수를 방지한다.
    if provider in ("Ollama", "Groq", "DeepSeek", "Mistral"):
        if low.startswith(("gpt-", "claude-", "chatgpt")):
            _log(f"[Camera Director] provider={provider}에 API 모델명 '{model}' "
                 f"→ '{default}'로 교정")
            return default
        return model
    prefixes = _MODEL_PREFIX.get(provider)
    if prefixes and not low.startswith(prefixes):
        _log(f"[Camera Director] provider={provider}에 부적합 모델명 '{model}' "
             f"→ '{default}'로 교정")
        return default
    return model


def _notify_llm_status(node_id, state: str) -> None:
    """LLM 판정 상태를 프론트엔드에 알려 model 위젯 표시등을 갱신한다.

    state: "busy"(LLM 구동 중 → 초록 점멸) / "on"(성공 → 초록 유지 후 자동 소등)
           / "fail"(실패→규칙 폴백 → 빨강 후 자동 소등) / "off"(즉시 소등)
    ComfyUI 서버 밖(테스트·스탠드얼론)에서는 조용히 무시한다.
    """
    if node_id is None:
        return
    try:
        from server import PromptServer
        ps = PromptServer.instance
        if ps is not None:
            ps.send_sync("gori_llm_status",
                         {"node": str(node_id), "state": state})
    except Exception:
        pass


def _release_vram() -> None:
    """실행 후 GPU 조각 반납. 왜(Why): reference VAE latent 캐시 등 실행 중
    잡은 VRAM 조각이 다음 노드(KSampler 등)에 넘어가기 전 정리된다.
    LRU 캐시 자체는 유지하므로(재실행 속도 불변) 수십 ms 비용뿐이다.
    torch가 없어도 조용히 통과한다.
    왜(Why) MPS도 같이 비우는가: macOS(M1/M2/M3)는 CUDA가 아니라 MPS 메모리
    파서를 쓴다. cuda만 비우면 맥에서는 이 함수가 아무것도 안 해서, 통합
    캐시 정리 의도가 그대로 전달되지 않는다. hasattr 가드로 CPU/MPS 없는
    환경에서도 예외 없이 통과한다.
    왜(Why) gc.collect(0) 인가 (2026-10-02 실측): 풀 collect 는 106ms 걸리고
    0개를 수집한다 — ComfyUI 프로세스 전체 힙(수백만 객체)을 스캔하는 비용만
    낸다. gen 0은 0.5ms에 단기 순환을 잡는다. 장기 순환은 파이썬이 알아서 한다.
    """
    try:
        import gc as _gc
        _gc.collect(0)
        try:
            import torch as _t
            if hasattr(_t, "cuda") and _t.cuda.is_available():
                _t.cuda.empty_cache()
            mps = getattr(_t, "mps", None)
            if mps is not None and hasattr(mps, "empty_cache"):
                try:
                    if mps.is_available():
                        mps.empty_cache()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass


def _free_gpu_for_local_llm() -> bool:
    """로컬 LLM 호출 전 ComfyUI 모델을 내려 GPU 자리를 비운다.

    왜(Why): 로컬 LLM(LM Studio/Ollama)은 ComfyUI와 **별개 프로세스**라,
    ComfyUI가 모델을 GPU에 앉힌 채면 LLM이 9B급 모델을 로드할 자리가 없다.
    요청이 LM Studio 큐에 대기하다 300초 타임아웃 → 빨간불이 된다.
    여기서 내리면 실제로 VRAM이 열리고, 이후 KSampler는 필요할 때 자동
    재로드한다. 큰 값을 요청하되(8GB) 카드가 그만큼 비어 있으면 아무것도
    내리지 않으므로 여유 있는 GPU에서는 비용이 0이다.
    """
    try:
        import comfy.model_management as _mm
        _dev = _mm.get_torch_device()
        _mm.free_memory(1 << 33, _dev)
        _release_vram()
        return True
    except Exception:
        return False


def _scrub_api_key_from_prompt(prompt, unique_id) -> bool:
    """서버 프롬프트 기록에서 이 노드 entry의 api_key만 지운다 (사진 메타데이터 안전).

    왜(Why): SaveImage는 실행 프롬프트 원본 dict를 PNG 메타데이터에 그대로
    박는다. 실행 시점엔 api_key가 이미 지역 변수로 resolve되어 있어 기록을
    지워도 실행에 영향이 없다. 자기 unique_id entry만 건드려 같은 그래프의
    다른 감독 노드 키와는 절대 간섭하지 않는다. 실패해도 실행은 계속된다.
    """
    try:
        if not isinstance(prompt, dict) or unique_id is None:
            return False
        entry = prompt.get(str(unique_id))
        if not isinstance(entry, dict):
            return False
        inputs = entry.get("inputs")
        if not isinstance(inputs, dict):
            return False
        if inputs.get("api_key"):
            inputs["api_key"] = ""
            return True
        return False
    except Exception:
        return False


def _self_workflow_node(extra_pnginfo, unique_id):
    """extra_pnginfo.workflow.nodes 에서 이 노드 entry를 찾아 돌려준다.

    왜(Why) id로 찾는가: `nodes` 는 프론트 스키마에 따라 list일 수도 dict일
    수도 있고, `widgets_values` 의 api_key 위치도 바뀐다. 하지만 항목의
    `id` 는 서버가 주입한 `unique_id` 와 같다(2026-09-30 실측) — 이 대응만
    믿으면 위젯 인덱스 매핑에 얽매이지 않는다.
    """
    try:
        if unique_id is None or not isinstance(extra_pnginfo, dict):
            return None
        workflow = extra_pnginfo.get("workflow")
        if not isinstance(workflow, dict):
            return None
        nodes = workflow.get("nodes")
        seq = list(nodes.values()) if isinstance(nodes, dict) else nodes
        if not isinstance(seq, (list, tuple)):
            return None
        target = str(unique_id)
        for node in seq:
            if isinstance(node, dict) and str(node.get("id")) == target:
                return node
        return None
    except Exception:
        return None


def _scrub_api_key_from_extra_pnginfo(extra_pnginfo, unique_id, api_key) -> bool:
    """PNG 로 나가는 워크플로 스냅샷에서 이 노드 api_key만 지운다.

    왜(Why) 필요한가: SaveImage/PreviewImage 는 `extra_pnginfo` 를 PNG 텍스트
    청크에 통째로 박는다(`nodes.py`). 그 안의 `workflow` 은 프론트가 보낸
    위젯 원본이라 `_scrub_api_key_from_prompt` 이 지우는 실행 기록과 **별개
    dict**다. 그래서 실행 기록만 지우면 저장된 사진에 키가 그대로 남는다
    (2026-09-30 실측: 당일 저장 이미지 전부가 이 경로로 키를 담고 있었다).
    """
    try:
        key = (api_key or "").strip()
        node = _self_workflow_node(extra_pnginfo, unique_id)
        if not key or node is None:
            return False
        hit = False
        named = node.get("widgets_values_named")
        if isinstance(named, dict) and named.get("api_key") == key:
            named["api_key"] = ""
            hit = True
        values = node.get("widgets_values")
        if isinstance(values, list):
            for i, v in enumerate(values):
                if isinstance(v, str) and v == key:
                    values[i] = ""
                    hit = True
        return hit
    except Exception:
        return False


def _api_key_left_in_png(extra_pnginfo, unique_id, api_key) -> bool:
    """이 노드 entry에 api_key 값이 아직 남아 있는지 (경고 판단용).

    왜(Why) scrub의 반환값으로 판단하지 않는가: 프론트가 이미 빈칸인 경우에도
    scrub는 False다. 그건 유출이 아니다. 실제로 값이 남아 있는지만 본다.
    """
    try:
        key = (api_key or "").strip()
        node = _self_workflow_node(extra_pnginfo, unique_id)
        if not key or node is None:
            return False
        named = node.get("widgets_values_named")
        if isinstance(named, dict) and named.get("api_key") == key:
            return True
        values = node.get("widgets_values")
        if isinstance(values, list):
            return any(isinstance(v, str) and v == key for v in values)
        return False
    except Exception:
        return False


# 사진 메타데이터 scrub 실패 경고는 **프로세스당 1회**만 (매 실행마다 찍으면
# 로그가 지저분해져 경고가 눈에 띄지 않는다 → 경고의 목적을 잃는다).
_SCRUB_WARNED = set()


def _warn_scrub_unavailable(api_key, prompt, unique_id,
                             extra_pnginfo=None, png_scrubbed=False) -> None:
    """api_key가 실행 기록이나 사진에 남을 수 있는데 지워지지 않았을 때 1회 경고.

    왜(Why) 이게 조용한 실패인가: 두 scrub 모두 **hidden 입력 주입**에 의존한다
    (ComfyUI가 `unique_id`/`prompt`/`extra_pnginfo`를 hidden으로 넘겨줘야 한다).
    코어가 주입 방식을 바꾸면 노드는 **에러 없이 정상 실행**되고, 대신 저장된
    PNG 메타데이터에 API 키가 그대로 남는다. 사용자가 알 수 있는 단서는 이것뿐이므로,
    못 지웠으면 반드시 말해야 한다.
    """
    try:
        if not (api_key or "").strip():
            return                      # 키가 없으면 남을 것도 없다
        if unique_id is None:
            _scrub_warn_once(
                "no-uid", "hidden 입력으로 unique_id가 주입되지 않음")
            return
        if not isinstance(prompt, dict):
            _scrub_warn_once(
                "bad-prompt",
                f"hidden prompt 입력 형식이 예상과 다름 ({type(prompt).__name__})")
            return
        if isinstance(extra_pnginfo, dict) and not png_scrubbed and \
                _api_key_left_in_png(extra_pnginfo, unique_id, api_key):
            _scrub_warn_once(
                "png-left",
                "extra_pnginfo.workflow 의 자기 entry에서 api_key를 "
                "지우지 못함")
    except Exception:
        pass


def _scrub_warn_once(tag, reason) -> None:
    if tag in _SCRUB_WARNED:
        return
    _SCRUB_WARNED.add(tag)
    _log(f"⚠ [GoRi Camera Director] 사진 메타데이터에서 API 키를 지우지 "
         f"못했습니다 ({reason}). ComfyUI 버전 변경으로 hidden 주입 방식이나 "
         f"워크플로 스키마가 바뀐 것일 수 있습니다. 저장된 이미지(PNG)는 "
         f"공유하기 전에 메타데이터에서 키를 확인해 주세요. 공유용으로는 노드 "
         f"우클릭 → 'api_key 지우기(공유용)' 을 사용하세요.")


def _write_env_file_key(env_name: str, key: str) -> bool:
    """루트 .env에 키 저장/삭제. key가 비면 해당 줄 삭제. 성공 여부 반환.

    왜(Why): 다이얼로그 OK 시점의 의도(저장·삭제·교체)를 그대로 파일에
    반영한다. 주석·순서는 보존하고 해당 제공자 줄만 갱신한다.
    """
    try:
        if env_name not in set(llm_client._API_KEY_ENV.values()):
            return False
        key = (key or "").strip()
        if key and (len(key) > 512 or "\n" in key or "\r" in key):
            return False
        path = llm_client._env_file_path()
        if not path:
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        out, found = [], False
        for line in lines:
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, _, _v = s.partition("=")
                # `export KEY=...` 형태 정규화. 왜(Why): 이 접두사가
                # 붙은 채면 키 이름이 "export OPENAI_API_KEY" 가 돼
                # 1) 읽기가 실패하고 2) 쓰기가 **중복 라인을 추가**한다 →
                # 옛 키가 디스크에 그대로 남는다(비밀 잔존).
                raw_key = k.strip()
                prefix = ""
                if raw_key.lower().startswith("export "):
                    raw_key = raw_key[7:].strip()
                    prefix = "export "
                if raw_key == env_name:
                    found = True
                    if key:
                        out.append(f"{prefix}{env_name}={key}")
                    continue
            out.append(line)
        if key and not found:
            out.append(f"{env_name}={key}")
        _write_env_file(path, out)
        return True
    except (OSError, UnicodeError):
        return False


def _write_env_file(path: str, lines) -> bool:
    """.env를 **원자적으로** 쓰고, POSIX에서는 소유자만 읽도록 권한을 낮춘다.

    왜(Why) 원자적 쓰기인가: 그대로 `open(path, "w")` 하면 truncate 직후
    예외가 나면 **키가 들어 있던 파일이 통째로 사라진다**. 임시 파일에 먼저
    쓰고 os.replace로 교체하면 교체 전까지 기존 파일은 그대로 남는다.
    (os.replace는 Windows에서도 동일 파일에 대해 원자적이며, 대상이 열려
    있어도 Windows가 자체적으로 실패시키므로 안전.)

    왜(Why) chmod인가: 리눅스/macOS의 기본 umask는 022라 `open("w")`로
    쓰면 0644가 되고 **같은 머신의 다른 사용자도 API 키를 읽을 수 있다.**
    Windows는 ACL 모델이라 chmod가 없어 적용하지 않는다(오류도 무시).
    """
    tmp = f"{path}.gori_tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        try:
            os.chmod(tmp, 0o600)
        except (OSError, AttributeError, NotImplementedError):
            pass          # Windows: chmod 의미 없음. 무시해도 안전.
        os.replace(tmp, path)
        return True
    except (OSError, AttributeError):
        # 임시 파일이 남지 않게 정리하고 원본은 건드리지 않는다.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def _valid_api_key_payload(provider, key):
    """다이얼로그 동기화 페이로드 검증. (env 이름, 키) 또는 (None, None).

    왜(Why): 비문자열 JSON(숫자·객체)이 str() 강제 변환으로 그대로 .env에
    기록되는 것을 막는다. Custom/로컬 제공자는 env 매핑이 없어 거부된다.
    """
    try:
        if not isinstance(provider, str) or not isinstance(key, str):
            return None, None
        env_name = llm_client._API_KEY_ENV.get(provider.strip())
        if not env_name:
            return None, None
        return env_name, key
    except Exception:
        return None, None


try:
    from server import PromptServer as _PromptServer

    @_PromptServer.instance.routes.post("/gori_api_key")
    async def _gori_api_key(request):
        """다이얼로그 OK 의도를 루트 .env에 반영 (저장·삭제·교체)."""
        from aiohttp import web as _web
        try:
            data = await request.json()
        except Exception:
            return _web.json_response({"ok": False}, status=400)
        try:
            data = data or {}
            env_name, key = _valid_api_key_payload(
                data.get("provider", ""), data.get("key", ""))
            ok = bool(env_name) and _write_env_file_key(env_name, key)
            if ok:
                _log(f"루트 .env에 {str(data.get('provider', '')).strip()} 키 "
                     f"{'삭제' if not key.strip() else '저장'}")
            return _web.json_response({"ok": ok})
        except Exception:
            return _web.json_response({"ok": False})
except Exception:
    # 서버 밖(테스트·스탠드얼론)에서는 라우트 없이 동작한다.
    pass


# ---------------------------------------------------------------------------
# auto tier — 한/영 병기 키워드 규칙 (최소 백업 사전)
# ---------------------------------------------------------------------------

def image_metrics(image) -> dict:
    """입력 IMAGE(ComfyUI 텐서/배열) → 4개 저비용 수치. 실패 시 {} (노드는 계속 동작).

    - dark        : 평균 밝기 0~1 (어두움)
    - contrast_std: 밝기 표준편차 (대비 척도)
    - vivid       : 색상 채도 평균 (비비드 척도)
    - thirds_bias : 좌/우 ⅓ 밝기 상대차 (삼분할 조감) → {"left"|"right"|"center"}
    """
    out = {}
    try:
        import torch as _t
        import numpy as _np
        px = image[0] if isinstance(image, _t.Tensor) else image
        px = px.detach().cpu() if hasattr(px, "detach") else px
        # 한 번만 float32 배열로 바꾼다. 예전엔 채널마다 asarray 를 따로
        # 불렀는데(3회) 같은 이미지를 세 번 변환했다. 4K 참조 이미지는
        # 채널마다 수 MB 라 세 번 변환한 비용이 그대로 컸다.
        arr = _np.asarray(px, dtype=_np.float32)
        r, g, b = (float(arr[..., i].mean()) for i in range(3))
        lum = arr[..., 0] * .299 + arr[..., 1] * .587 + arr[..., 2] * .114
    except Exception:
        return out
    try:
        h, w = int(lum.shape[0]), int(lum.shape[1])
        if h <= 0 or w <= 0:
            return out
        dark = float(max(0.0, min(1.0, 1.0 - lum.mean() / 255.0 if lum.max() > 1.5 else 1.0 - lum.mean())))
        out["dark"] = round(dark, 3)
        scale = 255.0 if lum.max() > 1.5 else 1.0
        out["contrast_std"] = round(float(lum.std() / scale), 3)
        mx = max(r, g, b, 1e-6)
        mn = min(r, g, b)
        out["vivid"] = round(float((mx - mn) / mx), 3)
        third = max(1, w // 3)
        left = float(lum[:, :third].mean())
        right = float(lum[:, -third:].mean())
        gap = abs(left - right) / max(scale, 1e-6)
        if gap < 0.03:
            out["thirds_bias"] = "center"
        else:
            out["thirds_bias"] = "left" if left > right else "right"
    except Exception:
        return out
    return out


def _reference_lighting_flow(image):
    """reference 1장의 조명 흐름맵 (8x8 정규화). 실패 시 None.

    왜(Why): 2장 이상 믹스 실행에서 참조 간 조명이 충돌하면(한 장은 좌광,
    한 장은 우광) 합성 결과 조명이 깨진다. Keeper의 Retinex 근사와 동일
    원리를 IMAGE 텐서/배열에 적용한다 (numpy만 사용).
    """
    try:
        import numpy as _np
        arr = image
        if getattr(arr, "ndim", 0) == 4:
            arr = arr[0]
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu()
        arr = arr.numpy() if hasattr(arr, "numpy") else _np.asarray(arr)
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.ndim != 3 or arr.shape[-1] < 3:
            return None
        lum = arr[..., :3].mean(axis=-1)
        if lum.max() > 1.5:
            lum = lum / 255.0
        h, w = lum.shape
        sh, sw = max(1, h // 8), max(1, w // 8)
        small = lum[:sh * 8, :sw * 8].reshape(8, sh, 8, sw).mean(axis=(1, 3))
        small = small - small.mean()
        return (small / (float(small.std()) + 1e-6)).astype(_np.float32)
    except Exception:
        return None


def _lighting_clash(flows) -> float | None:
    """조명 흐름맵들 간 최대 MSE. 1장 이하·실패 시 None."""
    try:
        maps = [f for f in (flows or []) if f is not None]
        if len(maps) < 2:
            return None
        worst = 0.0
        for i in range(len(maps)):
            for j in range(i + 1, len(maps)):
                d = float(((maps[i] - maps[j]) ** 2).mean())
                worst = max(worst, d)
        return worst
    except Exception:
        return None


def apply_image_hints(cam: dict, locked: set, metrics: dict) -> dict:
    """이미지 수치로 DEFAULTS인 항목만 조용히 바꾼다.

    우선순위: 명시 드롭다운 > 키워드 매칭 > 이미지 힌트 > DEFAULTS.
    - dark ≥ 0.62 (조명이 아직도 AUTO일 때만) → 로우키
    - vivid ≥ 0.45 (그레이드가 AUTO일 때만) → 비비드 포스터 (저대비면 프리미엄 절제로)
    - thirds_bias left/right (구도가 AUTO일 때만) → 밝은 쪽이 주체가 아니라는 보수 판단으로
      삼분할 유지 표기 → 보수 힌트이므로 바꾸지 않고 로그용 메모만 남긴다.
    반환: 힌트 적용 내역 리스트를 cam['_hints']에 보관.
    """
    cam = dict(cam)
    hints = []
    if not metrics:
        cam["_hints"] = hints
        return cam
    dark = metrics.get("dark")
    if ("lighting" not in locked and dark is not None and dark >= 0.62
            and cam.get("lighting") == DEFAULTS["lighting"]):
        cam["lighting"] = "로우키 (low key)"
        hints.append(f"이미지 어두움({dark}) → 로우키")
    vivid = metrics.get("vivid")
    if "grade" not in locked and vivid is not None and cam.get("grade") == DEFAULTS["grade"]:
        if vivid >= 0.45:
            cam["grade"] = "비비드 포스터 (vivid)"
            hints.append(f"채도 높음({vivid}) → 비비드 포스터")
        elif float(metrics.get("contrast_std", 1.0)) < 0.10:
            cam["grade"] = "절제된 프리미엄 (premium)"
            hints.append(f"저대비({metrics.get('contrast_std')}) → 절제된 프리미엄")
    bias = metrics.get("thirds_bias")
    if bias in ("left", "right"):
        hints.append(f"좌우 밝기 치우침({bias}) 감지 — 구도는 바꾸지 않음")
    cam["_hints"] = hints
    return cam

def topic_shot_label(topic: str) -> str:
    """주제에 사용자가 이미 카메라 샷을 명시했다면 해당 라벨을 반환한다.

    (Why: mismatch 경고와 동일 기준으로 감지해야 한다. 경고는 뜨는데 샷 확정은
    못 하는 상황 — 사용자가 "전신/풀바디"를 명시했는데 규칙이 근접으로 판정해
    스스로 모순을 경고하는 사례가 있었다. 최장 일치로 "중근접"⊃"근접" 오인도 방지.)
    """
    return _longest_shot_label(topic)


def rules(topic: str):
    """주제 문자열에서 키워드를 찾아 카메라 값(한글 라벨)을 결정한다.
    반환: (camera dict, 키워드로 확정된 항목 집합) — 확정 항목은 이미지 힌트가 건드리지 않는다."""
    cam = dict(DEFAULTS)
    matched = set()
    t = (topic or "").lower()
    for cat in ("shot", "lens", "angle", "lighting", "motion"):
        table = _TABLES[cat]
        for entry in KEYWORDS.get(cat, []):
            val = entry.get("value")
            if val not in table:
                continue
            if any(str(k).lower() in t for k in entry.get("keywords", [])):
                cam[cat] = val
                matched.add(cat)
                break
    for entry in KEYWORDS.get("speed", []):
        val = entry.get("value")
        if val in SPEED and any(str(k).lower() in t for k in entry.get("keywords", [])):
            cam["speed"] = val
            matched.add("speed")
            break
    explicit_shot = topic_shot_label(topic)
    if explicit_shot and cam.get("shot") == DEFAULTS["shot"]:
        cam["shot"] = explicit_shot
        matched.add("shot")
    return cam, matched


# 구도(앵글·샷) → 추천 조명 매칭 표 (우선순위 순).
# 왜(Why): LLM 없는 규칙 환경에서는 조명이 주제 키워드에만 의존해
# 구도와 무관한 기본값(흐린 부드러움)으로 남는 경우가 있었다.
# 구도가 드라마틱한 의도를 담을 때 조명도 세트로 따라가도록 한다.
# 주제 키워드/사용자 고정값이 있으면 절대 덮지 않는다.
FRAMING_LIGHTING_RULES = (
    (("angle", "개미눈 (worm's eye)"), "림라이트/실루엣 (rim light)"),
    (("angle", "로우앵글 (low angle)"), "림라이트/실루엣 (rim light)"),
    (("angle", "편각 (dutch angle)"), "로우키 (low key)"),
    (("shot", "극접 (ECU)"), "램브란트 (Rembrandt)"),
    (("shot", "근접 (CU)"), "램브란트 (Rembrandt)"),
    (("shot", "중근접 (MCU)"), "창가빛 (window light)"),
    (("shot", "원경 (WS)"), "골든아워 (golden hour)"),
    (("shot", "극원경 (EWS)"), "골든아워 (golden hour)"),
)


def apply_framing_lighting(cam: dict, locked: set):
    """조명이 아직 확정되지 않았으면(키워드/고정값 없음) 구도에서 추천 조명을 채운다.

    수동 티어와 LLM 성공 경로는 호출하지 않는다 — 사용자/LLM이 정한 조명을
    건드리지 않기 위함이다. 적용 시 lighting을 locked에 넣어 이미지 힌트도
    덮지 못하게 한다.
    """
    if "lighting" in locked or cam.get("lighting") != DEFAULTS["lighting"]:
        return cam, locked
    for (cat, label), lighting in FRAMING_LIGHTING_RULES:
        if cam.get(cat) == label:
            cam = dict(cam)
            cam["lighting"] = lighting
            locked = locked | {"lighting"}
            break
    return cam, locked


def resolve_rules_camera(topic: str, metrics: dict, fixed_cam, locked: set):
    """규칙 판정 + 명시 고정값 병합 + 추천 조명 + 이미지 힌트 — auto/LLM 폴백 공통 경로.

    왜(Why): run()의 auto 분기와 LLM 폴백 분기에서 동일한 규칙·병합·힌트
    블록이 중복되어 한쪽만 수정되는 퇴행 위험이 있었다.
    """
    camera, matched = rules(topic)
    camera.update(fixed_cam or {})
    locked = locked | matched
    camera, locked = apply_framing_lighting(camera, locked)
    if metrics:
        camera = apply_image_hints(camera, locked, metrics)
    return camera, locked, matched


# ---------------------------------------------------------------------------
# 조립 — 카메라 dict → 영문 조항 (혔스필드 하우스 블록 순서를 따름)
# ---------------------------------------------------------------------------

def _motion_clause(cam: dict, key: str) -> str:
    """무빙 1개 분량의 영문 조항. 없음·빈값이면 "" (복합 무빙 공용)."""
    label = cam.get(key, "")
    text = MOTION.get(label, "")
    if not text:
        return ""
    if label == "정지 (static)":
        return text
    bits = [AMPLITUDE.get(cam.get("amplitude"), ""),
            SPEED.get(cam.get("speed"), ""), text]
    return " ".join(b for b in bits if b) + " camera movement"


def build_clauses(cam: dict) -> list:
    parts = [
        SHOT.get(cam.get("shot"), ""),
        LENS.get(cam.get("lens"), ""),
        ANGLE.get(cam.get("angle"), ""),
        COMPOSITION.get(cam.get("composition"), ""),
        LIGHTING.get(cam.get("lighting"), ""),
        _motion_clause(cam, "motion"),
        _motion_clause(cam, "motion2"),
    ]
    # 동일 문구 중복 제거 (예: motion/motion2 둘 다 정지).
    out = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return out


QUALITY_GUARD = (
    "high visual quality, "
    "natural human proportions when people are present, "
    "believable hands with five fingers, natural skin texture, "
     "clear facial features, consistent subject identity"
)

# 동물 전용 주제의 대체 가드. 왜(Why) 별도 상수인가: QUALITY_GUARD 의
# "believable hands with five fingers" 는 "개는 사람처럼 그리지 말라"와
# 같은 프롬프트 안에서 정면 충돌한다(2026-09-28 실측). "when people are present"
# 절은 proportions 에만 걸려 있고 손·피부는 무조건 붙는다.
QUALITY_GUARD_ANIMAL = (
    "high visual quality, "
    "correct animal anatomy and natural species proportions, "
    "detailed fur or feather texture, natural coat pattern, "
    "clear eyes, consistent subject identity"
)

FACE_IDENTITY_GUARD = (
    "facial identity lock, preserve original face structure, same eye shape, same nose and mouth, "
    "same jawline, same facial proportions, same age and ethnicity, do not change face identity"
)

SKIN_COLOR_GUARD = (
    # 카메라 기법으로 피부 질감을 살린다. 왜(Why): "균일·매끈·깨끗" 같은
    # 미화 표현은 모델을 에어브러시 방향으로 밀어 플라스틱 피부가 되므로,
    # 모공·결·지향성 광·그레인 같은 촬영 언어로 현실 질감을 지시한다.
    "natural skin tone, realistic skin texture with visible pores and fine detail, "
    "soft directional lighting that reveals natural skin micro-contrast, subtle film grain, "
    "background color does not tint the skin"
)

NEGATIVE_ANATOMY_GUARD = (
    "bad anatomy, deformed anatomy, extra arms, extra limbs, third arm, duplicate arms, "
    "malformed hands, extra fingers, missing fingers, fused fingers, distorted face, "
    "changed identity, different person, face mismatch, duplicate subject, cloned face, "
    "plastic waxy skin, airbrushed smooth skin, over-smoothed featureless skin"
)

NEGATIVE_COLOR_CONTAMINATION_GUARD = (
    "background color spill on skin, color bleeding into skin, painted skin, "
    "skin color contamination, mismatched skin tone, blue skin tint, green skin tint, "
    "orange color cast on skin"
)

# base run(build_negative) 과 Skills run(build_camera_negative) 이 **공유**하는
# negative 기본 블록. 두 함수가 각자 하드코딩해서 Skills 경로에서 watermark /
# flat lighting / washed out 이 조용히 빠졌다(2026-09-28 실측: base 1669자 →
# Skills 1063자). base 는 CameraDirector 라는 **비등록 내부 클래스**라 사용자에게
# 노출되지 않으므로 Skills 만 고치면 실질적으로 아무것도 고쳐지지 않는다.
# 한 곳에 두면 앞으로 한쪽만 고치는 일이 구조적으로 불가능해진다.
#
# 주의: **사람 전용 가드는 여기 넣지 않는다.** 예전에
# NEGATIVE_ANATOMY_GUARD / NEGATIVE_COLOR_CONTAMINATION_GUARD 를 넣었더니
# 동물 주제에 "plastic waxy skin / different person" 이 붙는 회귀가 생겼다.
# 사람 여부로 게이트되는 항목은 각 함수에서 _is_human_subject 로 판단한다.
_NEGATIVE_BASE_COMMON = (
    "blurry, soft focus, jpeg artifacts, watermark, signature, text, logo",
    "warped geometry, distorted perspective, broken framing",
    "flat lighting, harsh unflattering light",
    "washed out colors, over-saturated colors",
)

OUTFIT_GUARD = (
    "outfit transfer guard: the main person reference image is only the identity and body reference, "
    "the clothing reference image is only a clothing and wardrobe reference, not a body reference, "
    "use the clothing from the clothing reference image as a separate garment layer "
    "placed on the person from the main reference image, preserve the original body shape, body proportions, "
    "skin, face, and hair from the main reference image, pose follows the topic, the garment must follow the existing human "
    "anatomy naturally, no clothing fusion with skin or body parts, no garment becoming "
    "body anatomy, no skin-like fabric on the garment, no melted garment edges, "
    "no body parts merging into clothing"
)

OUTFIT_RELATION_PATTERNS = (
    # English: clothing/outfit explicitly comes from a reference image.
    r"\b(?:outfit|clothing|wardrobe|dress|shirt|coat|apparel|garment)\b.{0,24}\b(?:from|reference|using|with)\s+(?:reference\s+)?(?:image|img)\s*_?\d+",
    r"\b(?:image|img)\s*_?\d+\b.{0,24}\b(?:is|as|contains|shows)\s+(?:the\s+)?(?:outfit|clothing|wardrobe|dress|shirt|coat|apparel|garment)\b",
    # Korean: 이미지 N의 의상/옷을 입히거나/바꾸는 명시적 의도.
    r"(?:image|img|이미지)\s*_?\d+\s*(?:의|에|에서)?\s*(?:의상|옷|패션|드레스|셔츠|블라우스|바지|원피스|코트|아우터|재킷|자켓|슈트|정장|한복|웨딩드레스|구두|신발)",
    r"(?:의상|옷|패션|드레스|셔츠|블라우스|바지|원피스|코트|아우터|재킷|자켓|슈트|정장|한복|웨딩드레스|구두|신발).{0,24}(?:image|img|이미지)\s*_?\d+",
    r"(?:입히|입게|바꾸|사용|적용|참고).{0,28}(?:의상|옷|드레스|패션|(?:image|img|이미지)\s*_?\d+)",
)


def _is_outfit_transfer(text: str) -> bool:
    """단순히 'dress/옷'이 있는 scenes가 아니라, image_N을 의상 참고로 쓰라는 의도만 판별한다."""
    t = (text or "").lower()
    has_ref = bool(re.search(r"\b(?:image|img)\s*_?\d+", t)
                   or re.search(r"이미지\s*_?\d+", t))
    has_slot = bool(_clothing_role_slots(t) or _outfit_target_slots(t))
    if not (has_ref or has_slot):
        return False
    if any(re.search(pattern, t) for pattern in OUTFIT_RELATION_PATTERNS):
        return True
    # 슬롯 번호 + 의상 어휘 + 교체 동사가 함께 있으면 의상 참고 의도다.
    return bool(_clothing_role_slots(t)) and bool(_outfit_target_slots(t))


def _reference_items(image_items=None, image_list=None, image=None):
    """연결된 reference 이미지를 (원래 image_N 번호, 이미지) 목록으로 정규화한다."""
    items = []

    def add(raw, fallback_index):
        if raw is None:
            return
        if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], int):
            items.append((raw[0], raw[1]))
        else:
            items.append((fallback_index, raw))

    if image_items:
        for idx, raw in enumerate(list(image_items), start=1):
            add(raw, idx)
    elif image_list:
        for idx, raw in enumerate(list(image_list), start=1):
            add(raw, idx)
    if image is not None and not items:
        add(image, 1)
    return items


# 인물 주제 판정 어휘. 왜(Why): 실측에서 "1번 캐릭터를 앉힌다"가 인물로
# 잡히지 않아 해부·발란스·디테일 경계 가드가 **전부** 조용히 미작동했다.
# "캐릭터"는 한국어 촬영 씬에서 가장 흔한 인물 지칭인데 빠져 있었다.
# ("인물 " 앞의 공백은 " 인물"이 접두어로 걸리는 것을 막기 위한 잔재 — 정리)
# "model"은 단독으로 넣지 않는다 — "3D model of a car" 같은 사물 모형까지
# 사람으로 잡힌다. 사람이 쓰는 경우만 "fashion model"로 좁힌다. (기존에도
# 단독이 아니라 "fashion model"만 넣었으나, 실측 테스트가 "3D model" 검사를
# 걸도록 이 형태를 유지한다. 아래에서 "model"을 빼면 그 테스트가 깨진다.)
HUMAN_SUBJECT_KEYWORDS = (
    "woman", "women", "female", "girl", "lady", "human", "person", "people",
    "man", "men", "male", "boy", "actor", "actress",
    "fashion model", "portrait", "_character",
    "캐릭터", "인물", "여성", "남성", "여자", "남자", "사람", "아이",
    "소년", "소녀", "남아", "여아", "주인공", "인물체", "모델",
)

# "3D model of a car"처럼 사물 모형을 가리키는 표기. 왜(Why): 영어 "model"
# 단독 키워드가 사물 모형 장면까지 사람 장면으로 오판해 identity 가드를
# 잘못 붙였기 때문이다. 모형 표기가 있으면 모델류 키워드는 무시하고
# 명확한 인물 키워드만 본다.
_MODEL_OBJECT_PATTERN = re.compile(r"(?:3d|3-d|3차원|scale)\s*(?:model|모델)")


def _is_human_subject(text: str) -> bool:
    t = (text or "").lower()
    # **의상 교체** 표현은 사람을 함의한다(2026-09-29 실측 결함 수정).
    # "1 의상, 2 교체" 에는 인물 키워드가 하나도 없어서 이 함수가 False 였다.
    # 결과적으로 identity 앵커·해부·발란스 등 **인물 가드가 전부 조용히
    # 미작동**했다(프롬프트에 사람이 없으니 의도한 것도 아니고). 옷을 입는다는
    # 것은 결국 그 옷을 입을 사람이 있다는 뜻이므로 사람으로 친다.
    # 단, **동물/인물 키워드가 명시됐으면 그쪽이 우선**이다
    # (혼재 장면에서 "강아지" 가 있는데 사람 가드까지 붙으면 오탐).
    if _is_outfit_transfer(t):
        for animal in ANIMAL_SUBJECT_KEYWORDS:
            if animal in t:
                return False
        return True
    if _MODEL_OBJECT_PATTERN.search(t):
        keywords = tuple(k for k in HUMAN_SUBJECT_KEYWORDS
                         if k not in ("fashion model", "모델"))
        return any(keyword in t for keyword in keywords)
    for keyword in HUMAN_SUBJECT_KEYWORDS:
        if keyword in _ASCII_AMBIGUOUS:
            # 원자(holder) 후보: 단어 경계가 없으면 오탐
            if _ascii_word_present(t, keyword):
                return True
        elif keyword in t:
            return True
    return False


# 동물 주제 판별. 왜(Why): 인물 키워드만 있어서 "강아지" 주제는 어떤 가드에도
# 걸리지 않았다. 인체 가드는 그대로 미적용(오탐 없음)하지만 동물 해부·종 보존
# 가드가 전혀 없으니 개가 사람 손을 갖거나 품종 초상화로 변하는 실패를 못 막는다.
ANIMAL_SUBJECT_KEYWORDS = (
    "cat", "kitten", "dog", "puppy", "horse", "bird", "parrot", "owl",
    "rabbit", "bunny", "squirrel", "fox", "deer", "cow", "cattle", "sheep",
    "goat", "pig", "bear", "wolf", "tiger", "lion", "leopard", "elephant",
    "monkey", "panda", "penguin", "eagle", "duck", "swan", "seagull",
    "snake", "turtle", "frog", "fish", "shark", "whale", "dolphin",
    "hamster", "guinea pig", "ferret", "chameleon", "gecko", "parrotlet",
    "고양이", "강아지", "애완동물", "반려동물", "동물", "말", "새", "앵무새",
    "독수리", "앵무", "토끼", "다람쥐", "여우", "사슴", "소", "양", "염소",
    "돼지", "곰", "호랑이", "사자", "원숭이", "판다", "펭귄", "오리", "백조",
    "거북이", "뱀", "개구리", "물고기", "고래", "돌고래", "햄스터",
)
ANIMAL_SPECIES_POSITIVE = (
    "one clearly identifiable animal species, accurate species proportions "
    "(leg count, limb structure, muzzle, tail, ears), full animal body "
    "anatomy, natural fur or feather texture, real animal proportions"
)
ANIMAL_ANATOMY_NEGATIVE = (
    "humanized animal, human hands on an animal, human face on an animal body, "
    "mutated animal anatomy, extra legs, missing legs, deformed paws, "
    "fused limbs, wrong species, part human part animal, "
    "cartoon caricature, exaggerated breed caricature, plastic toy animal, "
    "stuffed animal, taxidermy mount, mascot costume"
)


# 한국어 명사 뒤에 붙는 조사·수량사 어미들만 "그 단어를 썼다"로 인정한다.
# 왜(Why) 이 목록이 필요한가: 한국어는 어절이 공백으로 분리되지 않아
# `keyword in text` 로는 "소파/태양/양옆" 이 "소/양" 으로 잡힌다(2026-09-28 실측).
# 사람이 있는 장면이 동물로 분류되면 인체 가드가 전부 사라진다.
_KO_SUFFIX_CHARS = (
    "가"          # 주격
    "이가을를"    # 목적격/보조격
    "은는"        # 보조사
    "과와"        # 조화
    "의"          # 관형
    "에"          # 방향
    "에서"        # 출발
    "로"          # 방향
    "만"          # 제한
    "도"          # 주제
    "까지"        # 한계
    "부터"        # 기점
    "에게"        # 간접목적
    "한테"        # 간접목적
    "그"          # 관형
    "것"          # 명사화
    "들"          # 복수
    "한"          # 수량
    "두세"        # 수량
    "마리"        # 가축 계수
    "짝"          # 짝
    "층"          # 층
)


def _ascii_only(word: str) -> bool:
    """영문 단어인지 (한글 어휘는 조사 규칙이 다르다)."""
    return all(ord(c) < 128 for c in word)


def _ko_word_present(text: str, word: str) -> bool:
    """한국어 단어가 독립형으로 쓰였는지 판정한다.

    **앞뒤 양쪽**을 본다. 한쪽만 보면 접합을 못 잡는다(2026-09-28 실측):
      - 뒤만 보면: "소파" 의 "소" 를 통과("파" 가 조사 아님 → 이건 OK),
        "고양이" 의 "양" 이 "이"(조사) 때문에 통과 → **오탐**
      - 앞만 보면: "태양" 의 "양"(앞이 "태") → **오탐**
    규칙: 앞 글자는 한글이면 거부(접합), 뒤 글자는 조사/수량사면 인정.
    어휘 목록에 "고양이"/"강아지" 같은 결합형이 이미 들어 있으므로
    정작 그 단어는 앞 글자가 공백이라 정상 통과한다.
    """
    start = 0
    while True:
        i = text.find(word, start)
        if i < 0:
            return False
        if i > 0 and "가" <= text[i - 1] <= "힣":
            start = i + 1          # 앞이 한글 = 앞 단어의 일부
            continue
        nxt = text[i + len(word): i + len(word) + 1]
        if nxt == "" or not ("가" <= nxt <= "힣"):
            return True
        if nxt in _KO_SUFFIX_CHARS:
            return True
        if nxt == "까" and text[i + len(word):i + len(word) + 2] == "까지":
            return True
        if nxt == "부" and text[i + len(word):i + len(word) + 2] == "부터":
            return True
        start = i + 1
    return False


# 영문 어휘는 단어 경계로만 매칭한다. 왜(Why): `man` 이 "romantic/german/
# manicured" 안에서, `cat` 이 "catalogue", `bear` 가 "bearable" 안에서 잡혔다
# (2026-09-28 실측). 풍경·사물 주제가 인물/동물로 분류되면 인물 가드가 붙거나
# 인체 가드가 빠진다.
_ASCII_AMBIGUOUS = frozenset({
    "man", "men", "woman", "women", "cat", "bear", "pig", "dog", "hen", "ewe",
    "goat", "rat", "ram", "ape", "fox", "elk", "gnu", "imp", "kid", "nut",
    "pet", "cod", "boa", "carp", "sole", "hart", "crane", "newt", "toad",
})


def _ascii_word_present(text: str, word: str) -> bool:
    """영문 단어를 단어 경계로만 찾는다 (\b 매칭)."""
    import re as _re
    return bool(_re.search(r"\b" + _re.escape(word) + r"\b", text))


def _is_animal_subject(text: str) -> bool:
    """동물 주제면 True. 인물 키워드가 명시되면 사람 우선(장면 혼재 대응)."""
    t = (text or "").lower()
    if not t:
        return False
    if _is_human_subject(t):
        return False
    for keyword in ANIMAL_SUBJECT_KEYWORDS:
        if _ascii_only(keyword):
            if _ascii_word_present(t, keyword):
                return True
        elif _ko_word_present(t, keyword):
            return True
    return False


def body_proportion_guard(image_count: int, topic: str, image_labels=None) -> str:
    """이미지 reference가 있는 사람/인물 장면에서 원본 골반/힙 비율을 유지한다.

    identity/body 참조는 계획(plan)이 선출한 주 피사체로 둔다 -- 왜(Why):
    첫 연결이 사물(핸드백 등)이면 사물 비율을 신체 비율로 복제하는 오동작이
    생긴다. 실제 인물 슬롯을 참조해야 한다.
    """
    if image_count <= 0 or not _is_human_subject(topic):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    first = str(plan["main"])
    return (f"face and body preservation guard: use reference image {first} as the identity and body reference, "
            f"{FACE_IDENTITY_GUARD}, {SKIN_COLOR_GUARD}, "
            "preserve the original body proportions from the main human reference image, "
            "same hip width, same waist-to-hip ratio, same torso length, same shoulder width, "
            "do not exaggerate hips or pelvis, no widened pelvis, no exaggerated hourglass body, "
            "natural body shape matching the reference image")


def outfit_guard(image_count: int, topic: str) -> str:
    """의상 교체 의도가 명확하고 이미지가 2장 이상일 때만 의상 전용 가드를 넣는다."""
    if image_count < 2 or not _is_outfit_transfer(topic):
        return ""
    return OUTFIT_GUARD



MAX_REFERENCE_IMAGES = 10

# LLM 비전 전송 크기. 왜(Why): 로컬 LLM 비전 추론이 느린 주범은 서버 연산이라
# 노드가 빠르게 할 수 없고, 줄일 수 있는 건 전송 짐뿐이다. 기본값(768)은 기존
# 동작 그대로 — 판단 디테일이 떨어질 수 있어 옵션으로만 제공한다.
VISION_DETAIL = {
    "선명 (768)": 768,
    "균형 (512)": 512,
    "절약 (384)": 384,
}
VISION_DETAIL_DEFAULT = "선명 (768)"


def vision_detail_px(label: str) -> int:
    """vision_detail 라벨 → 전송 한 변 px. 알 수 없으면 768(기존값)."""
    try:
        return int(VISION_DETAIL.get((label or "").strip(), 768))
    except (ValueError, TypeError, AttributeError):
        return 768


def build_identity_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Add a short human-reference identity anchor for text-only conditioning.

    This is intentionally narrower than the legacy guard: it does not modify
    body proportions, anatomy, or negative conditioning. Skin realism is
    included because plastic skin comes from photographic rendering, which
    this camera node can direct.

    identity 소스는 역할 계획(plan)이 선출한 주 피사체로 둔다 -- 왜(Why):
    첫 연결이 사물(핸드백 등)이면 사물을 인물 identity 소스로 지목하는
    오동작이 생긴다(정밀 검토 발견 #1).
    """
    if image_count <= 0 or not _is_human_subject(topic):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    first = str(plan["main"])
    return (f"Use reference image {first} as the exact identity source for the main person. "
            "Preserve the same facial identity and same facial structure, age, ethnicity, hairstyle, "
            "and clothing unless the instruction explicitly changes them. "
            "Render natural realistic skin texture with visible pores and fine detail, "
            "soft directional light, subtle film grain, no airbrushed smoothing.")

MULTI_PERSON_KEYWORDS = (
    "two people", "two persons", "two men", "two women",
    "woman and man", "man and woman", "pair of people",
    "each other", "facing each other", "face each other",
    "both people", "both persons", "both of them",
    "group of", "family", "couple",
    "두 명", "두사람", "두 사람", "2명", "서로", "마주",
    "여성과 남성", "남성과 여성", "여러 명", "가족", "커플", "인물 두", "그룹",
)

REFLECTION_KEYWORDS = (
    "reflection", "reflected", "mirror", "mirrored", "glass", "window",
    "유리창", "거울", "반사", "비친", "창문", "유리",
)


def _is_reflection_scene(text: str) -> bool:
    t = (text or "").lower()
    return any(keyword in t for keyword in REFLECTION_KEYWORDS)




def _is_multi_person_request(text: str) -> bool:
    t = (text or "").lower()
    return any(keyword in t for keyword in MULTI_PERSON_KEYWORDS)


def build_single_person_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Prevent a single reference subject from being expanded into a duplicate.

    주 피사체도 역할 계획(plan)이 선출한다 -- 왜(Why): 첫 연결이 사물이고
    유일한 인물이 다른 슬롯에 있으면(1번 핸드백 + 2번 여성) 구버전은
    "유일 인물인데도 억제 문구가 아예 안 붙었다" -- plan 주체로 발화하면
    올바른 슬롯으로 붙는다(정밀 검토 발견 #2). plan에 추가 인물이 있으면
    (duo 이상) 기존처럼 억제한다.
    """
    if (image_count <= 0 or not _is_human_subject(topic)
            or _is_multi_person_request(topic)
            or _is_reflection_scene(topic)):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    if plan["persons"]:
        return ""
    first = str(plan["main"])
    return (f"Exactly one main person in the output, using reference image {first} as the only subject. "
            "Single-person composition. No additional person, copy, or mirrored companion.")


SECOND_PERSON_PATTERNS = (
    # image/이미지 표기 혼용 대응: "Image 3의 남성" 같은 한영 혼합도 잡는다.
    # 주의: 한글 조사(의/에)는 \w 취급이라 2\b 경계가 안 맞으므로 (?![0-9])를 쓴다.
    # 2번 고정이 아니라 2~10번 슬롯을 캡처한다.
    # 비탐욕 창 + 절 차단: 창이 쉼표/식별자를 넘어 다음 슬롯의 단어를 잘못 잡거나
    # (이미지 2번 핸드백, 이미지 3번 남성 → 3번 누락/2번 오검출)
    # finditer의 비중복 소비 때문에 건너뛰는 후보가 생기는 것을 동시에 막는다.
    r"\b(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])[^,，.。;；!！?？\n]{0,40}?\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b",
    r"\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b[^,，.。;；!！?？\n]{0,40}?\b(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])",
    r"(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])[^,，.。;；!！?？\n]{0,20}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)",
    r"(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)[^,，.。;；!！?？\n]{0,20}?(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])",
    r"두\s*번째\s*(?:사람|남자|남성|여자|여성|인물)",
    r"second\s+(?:person|man|woman|male|female)",
    # 번호 선행형: "2번 이미지의 남성이" — 위 4개 패턴은 모두 이미지 표기가
    # 앞에 오는 구문만 커버한다. 자연스러운 "N번 이미지" 표현을 놓치면
    # 두 번째 인물이 보조 역할(배경/소품)로 오분류된다.
    r"([2-9]|10)\s*(?:번|번째)\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*[^,，.。;；!！?？\n]{0,20}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)",
    r"([2-9]|10)\s*(?:번|번째)\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b",
    # 번호 **나열**형: "1번과 2번 인물이", "2번·3번", "image 1 and image 2".
    # 위 패턴들은 "2번 이미지의 남성이"처럼 **한 슬롯만 지칭**하는 구문만
    # 잡는다. 두 슬롯을 함께 나열하는 최상위 표현("1번과 2번 인물이 함께")이
    # 잡히지 않아 duo 앵커가 빈 문자열로 빠지고, 그 결과 두 번째 참조가
    # "소품/배경 역할"로 강등됐다(2026-09-28 실측). 캡처 그룹 2개를 모두 수집.
    r"(?:[1-9]|10)\s*(?:번|번째)\s*(?:와|과|및|그리고|·|,|、|\+)\s*([2-9]|10)\s*(?:번|번째)?[^,，.。;；!！?？\n]{0,16}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람|커플|쌍)",
    r"\b(?:image|img)\s*_?\s*(?:[1-9]|10)\s*(?:and|&|,)\s*(?:image|img)?\s*_?\s*([2-9]|10)\b[^,，.。;；!！?？\n]{0,24}?\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person|people|couple)\b",
)

_NUMBER_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five",
                 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
_ORDINAL_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                  6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}

# 사물/소품 역할 어휘. 의상 계열(옷·의상·원피스 등)은 일부러 넣지 않았다 --
# 의상 참조에는 전용 가드(OUTFIT_GUARD·OUTFIT_RELATION_PATTERNS)가 있어
# 이 분류기가 겹치면 의상 슬롯이 "소품"으로 오인될 수 있다.
# 모호한 짧은 단어(검·총·잔·병)는 뺐다 -- 왜(Why): "검은 머리"의 검은이
# 검(sword)으로 오판되는 오검출이 실측 확인됐다(정밀 검토 발견 #4).
_KO_OBJECT_WORDS = (
    "가방|핸드백|백팩|에코백|숄더백|클러치백|손목시계|시계|목걸이|반지|귀걸이"
    "|안경|선글라스|모자|벨트|스카프|목도리|장갑|우산|책|컵"
    "|방패|꽃다발|소품|오브젝트|제품|물건|구급상자|마네킹"
)
_EN_OBJECT_WORDS = (
    "bag|handbag|backpack|purse|watch|wristwatch|necklace|ring|earrings"
    "|glasses|sunglasses|hat|cap|belt|scarf|gloves|umbrella|book"
    "|prop|object|product"
)
OBJECT_WORDS = _KO_OBJECT_WORDS + "|" + _EN_OBJECT_WORDS

# 어휘가 앞 → 슬롯이 뒤인 순서의 창 차단. 사람 단어가 창 안에 있으면 그 슬롯은
# 사람 절에 속한다 -- 왜(Why): "원피스로 갈아입은 여성과 이미지 3"에서 원피스가
# 3번(남성)을 옷 슬롯으로 침범하는 오검출이 실측 확인됐다(정밀 검토 R23).
_TEMPERED_GAP = (r"(?:(?!남성|남자|여성|여자|인물|사람"
                 r"|man|woman|male|female|person)[^,，.。;；!！?？\n]){0,24}?")

# 의상 역할 어휘 + 슬롯 검출. 왜(Why): outfit 게이트가 "의상 의도 = 모든 duo 소멸"
# (구버전)이 아니라 "의상 슬롯만 제외"로 작동하려면 슬롯 번호를 잡아야 한다
# (정밀 검토 발견 #3).
_KO_CLOTHING_WORDS = (
    "의상|옷|옷차림|의장|생활복|패션|드레스|셔츠|블라우스|바지|원피스"
    "|코트|아우터|재킷|자켓|슈트|정장|한복|웨딩드레스|구두|신발"
)
_EN_CLOTHING_WORDS = "outfit|clothing|wardrobe|dress|shirt|coat|garment|apparel"
CLOTHING_WORDS = _KO_CLOTHING_WORDS + "|" + _EN_CLOTHING_WORDS


def _role_patterns(words: str, en_words: str):
    """역할(사물/의상) 슬롯 검출 4패턴 골격. 단어만 주입한다.

    왜(Why): 사물·의상 패턴은 절 차단 규칙이 동일하다. 형태:
    1) "이미지 2의 핸드백" (조사 혼용 대응)
    2) "핸드백 이미지 3" — 문장부호 차단(쉼표 너머 오인 방지) + 사람 단어
       차단(창 안 사람 단어가 있으면 그 슬롯은 사람 절 소속)
    3) 영문 "bag as image 2"형, 4) 영문 "image 3 shows a book"형.
    """
    return (
        r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])\s*(?:번)?\s*(?:의|에|에서)?\s*(?:" + words + r")",
        r"(?:" + words + r")" + _TEMPERED_GAP + r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])",
        r"\b(?:" + en_words + r")\b" + _TEMPERED_GAP + r"\b(?:from|in|on|as|using|reference)\s+(?:reference\s+)?(?:image|img)\s*_?\s*(\d+)(?![0-9])",
        r"\b(?:image|img)\s*_?\s*(\d+)(?![0-9])\b" + _TEMPERED_GAP + r"\b(?:is|as|shows|contains)\s+(?:a|an|the)?\s*(?:" + en_words + r")\b",
    )


OBJECT_ROLE_PATTERNS = _role_patterns(OBJECT_WORDS, _EN_OBJECT_WORDS)
# 슬롯 번호 + 의상 표현(2026-09-29 추가). 왜(Why): 기존 4패턴은
# "이미지 2의 의상"(라벨 필수)만 잡았다. 사용자가 "2 의상, 1 교체" 처럼
# **숫자만** 쓰면 아무것도 안 잡혔다(전수 확인: 6개 표현 전부 미인식).
# 포즈 슬롯과 같은 취지로 자연스러운 표현을 받아들인다.
#
# 제외 조건: 의상 어휘 뒤에 **착용 동사**가 바로 붙으면 그 슬롯은 의상 소스가
# 아니라 **인물**이다("2번 드레스를 입은 여성" -> 2번은 사람). 의상 소스로
# 잡으면 그 사람이 신원 소스에서 제외돼 사람이 사라진다(2026-09-29 실측 위험).
# 주의(Why): 동사는 어휘에서 **직접** 붙어야 한다. "을/ 를" 까지 보면
# "2번 의장을 1번에 입혀"(= 의상 소스 2번 + 대상 1번)까지 삼켜서 놓친다.
CLOTHING_ROLE_PATTERNS = _role_patterns(CLOTHING_WORDS, _EN_CLOTHING_WORDS) + (
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|에|에서|으로)?\s*(?:" + CLOTHING_WORDS
    + r")(?!\s*(?:을|를|이|가)?\s*(?:입은|입고|입혀|입히|착용|신은|신고))"
      r"(?![^,，]{0,4}(?:wearing|wears|dressed)\b)",
    # 역순: "1번에 2번 의장을 입혀" — 의상 소스 뒤에 **대상** 슬롯이 온다.
    r"(?:\d{1,2}\s*(?:번|번째)?\s*(?:에|에게|한테|의|은|는)\s*)"
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|으로)?\s*(?:" + CLOTHING_WORDS + r")",
)

# **교체 대상** 슬롯 — 의상 소스가 아니라 "이 슬롯에 입히라" 는 뜻.
# 왜(Why) 별도로 둔다(2026-09-29): "2 의상, 1 교체" 에서 1번을 의상 슬롯으로 잡으면
# 1번(주인물)이 신원 소스에서 제외된다 -> 사람이 사라진다. 캡처 그룹을 만든 채로
# "제외 패턴"을 넣으면 **반대로** 슬롯이 추가되므로 빼기 전용으로 분리해야 한다.
# 동사는 슬롯 **앞**(1번에 입혀)이나 **뒤**(1번 교체) 양쪽에 올 수 있다.
# 주의(Why): 접미에 \\b 를 붙이면 안 된다 — 파이썬이 백스페이스(\x08)로
# 해석해 정규식이 깨진다(실측: 한국어 동사 매칭이 전부 실패했다).
_OUTFIT_VERB = (r"(?:교체|바꿔|바꾼|바꾸|바꿜|갈아입|갈아입혀|입혀|입히|입게|적용"
                r"|변경|변하게|옮겨|wear|swap|replace|change|apply)")
# "의상 + 을/를 + 대상 슬롯" — 대상은 소스가 아니다.
# 골격 패턴 2번(의상 → 이미지 N)이 여기서 1번을 의상 소스로 오염시킨다(2026-09-29 실측).
# 주의(Why) 여기서는 "이미지 N(을) V" 형태만 뺀다. 라벨+V 형태를 넣으면
# "이미지 2 의상" 의 **2번(진짜 소스)** 까지 잡혀 소스가 사라진다(실측).
_OUTFIT_APPLY_SLOT_PATTERNS = (
    r"(?:" + CLOTHING_WORDS + r")\s*(?:을|를)?\s*(?:은|는)?\s*"
    r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])",
)
# 슬롯과 조사 사이에 역할명사가 끼는 형태: "1번 인물에게 입히고".
# 실제로는 아주 흔하다(사람을 지칭해야 "입히라" 가 성립하므로).
_OUTFIT_TARGET_ROLE = r"(?:인물|사람|여자|남자|여성|남성|모델|얼굴|신원|여학생|남학생)?"
OUTFIT_TARGET_PATTERNS = (
    # 동사가 슬롯 뒤: "1 교체", "2번 적용"
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는)?\s*(?:에|로|한테)?\s*" + _OUTFIT_VERB + r"(?![0-9])",
    # 동사가 슬롯 앞: "1번에 입혀", "1번 인물에게 입히고"
    r"(\d{1,2})\s*(?:번|번째)?\s*" + _OUTFIT_TARGET_ROLE
    + r"\s*(?:에게|한테|에|으로|로)\s*" + _OUTFIT_VERB,
    # 역순 + 동사까지: "1번에 2번 의장을 입혀" (2026-09-29 실측 결함).
    # 주의(Why): 슬롯과 동사 사이에 **자유 구간**을 두면 안 된다.
    # "2번 의장을 1번 인물에게 입히고" 에서 왼쪽 2번이 먼저 잡혀 소비되고
    # finditer 가 1번까지 못 간다(실측: 대상=[] 로 조용히 실패).
    r"(\d{1,2})\s*(?:번|번째)?\s*" + _OUTFIT_TARGET_ROLE
    + r"\s*(?:에게|한테|에|으로|로)\s*\d{1,2}\s*(?:번|번째)?\s*(?:의|은|는|을|를)?\s*"
    r"(?:" + CLOTHING_WORDS + r")[^,，]{0,14}?" + _OUTFIT_VERB,
)

# 포즈 참조 역할. 왜(Why): 사용자가 "2번 이미지의 포즈를 따라"라고 명시한 슬롯은
# 신원·의상·사물 소스가 아니라 **자세 전용**이다. DNA(=신원·외양)에서 포즈를
# 뺀 이유(의도와 무관한 포즈 고정)와 달리, 여기서는 사용자가 직접 지정했으므로
# 해당 슬롯만 자세 따라하기를 허용한다.
# **자세 표현 어휘**(슬롯 번호 뒤에 바로 오는 자연스러운 표현).
# 왜(Why) 넓혔나(2026-09-29 실측): 기존은 "이미지 2의 포즈" 처럼 **역할
# 명사**(포즈/자세/스탠스/몸매/동작)만 인식했다. 그래서 사용자가
# "2번은 포즈만", "2번 앉은 자세", "2 서 있는 모습" 처럼 **실제 자세를
# 묘사**하는 자연스러운 표현을 쓰면 아무것도 안 잡혔다(전부 미인식 실측).
# 사용자는 "2번" + 무엇을 할지 를 적는 게 자연스럽다. 그래서 자세 묘사
# 어휘까지 받아들인다.
_KO_POSE_STATE = (
    "앉|앉아|앉은|앉는|서있|서 있|선|선상태|서있는|서 있는|서서|누워|누운"
    "|눕는|쪼그|쪼갠|쪼고|무릎|엎드|일어서|숨을|움직임|움직이는|동작"
    "|자세|스탠스|몸매|모습|상태|형태|구도|각도|위치|손|팔|다리|발"
    "|허리|목|고개|뒤통수|엉덩이|골반|어깨"
)
_EN_POSE_STATE = (
    "pose|posture|stance|body ?position|position|angle|leaning|sitting|sit"
    "|standing|stand|kneeling|kneel|crouching|crouch|lying|lie|reaching"
    "|holding|arms?|hands?|legs?|bent|lean|smiling|looking|walking"
)
_KO_POSE_WORDS = ("포즈|자세|스탠스|몸매|동작|"
                   + _KO_POSE_STATE + "|" + _EN_POSE_STATE)
_EN_POSE_WORDS = "pose|posture|stance|body position"
POSE_ROLE_PATTERNS = _role_patterns(_KO_POSE_WORDS, _EN_POSE_WORDS) + (
    # "2번 이미지의 포즈" — 번호가 앞서는 한국어 구문. 기존 4패턴은
    # "이미지 2의 포즈"(뒤에 온다)만 커버해서 자연스러운 표현을 놓쳤다.
    # 슬롯 번호는 반드시 캡처 그룹이어야 한다(_collect_role_slots 계약).
    r"(\d{1,2})\s*(?:번|번째|번의)?\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*(?:" + _KO_POSE_WORDS + r")",
    # "3번과 7번 이미지의 포즈" — 접두·접미로 나열하면 앞 번호가 뒤 번호 창에
    # 밀려 잡히지 않았다. 나열 멤버마다 캡처 그룹을 두어 전부 수집한다.
    r"(\d{1,2})\s*(?:번|번째)\s*(?:와|과|and|,|，)\s*(\d{1,2})\s*(?:번|번째)?\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*(?:" + _KO_POSE_WORDS + r")",
    # 2026-09-29 추가: "2번은 포즈만" / "2번 포즈만" — 이미지 라벨 없이
    # 슬롯 번호 + 포즈 역할명사. 사용자가 가장 자주 쓰는 형태다.
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|에|에서)?\s*(?:"
      + _KO_POSE_WORDS
      + r")\s*(?:만|참고|기준|따라|따라가|그대로)?",
    # "2번은 앉은 자세" / "2 서 있는 모습" / "2번 손에 든 상태" —
    # 슬롯 번호 + **자세 묘사**(역할명사 없이 실제 자세를 적은 형태).
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|이|가|의)?\s*(?:"
      + _KO_POSE_STATE
      + r")",
)


def _collect_role_slots(text: str, patterns) -> set:
    """패턴 집합에서 번호(1~10) 수집. 사물·의상 슬롯 검출 공용 루프."""
    t = (text or "").lower()
    slots = set()
    for pattern in patterns:
        try:
            for m in re.finditer(pattern, t):
                # 캡처 그룹이 여러 개인 패턴(나열형)이 있으므로 전부 수집한다.
                # 기존 4패턴은 그룹이 하나뿐이라 동작이 달라지지 않는다.
                for grp in m.groups():
                    if not grp:
                        continue
                    try:
                        n = int(grp)
                    except ValueError:
                        continue
                    if 1 <= n <= 10:
                        slots.add(n)
        except (ValueError, re.error):
            continue
    return slots


def _clothing_role_slots(text: str) -> set:
    """의상 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): _second_person_slots의 outfit 게이트가 의상 슬롯만 정밀하게
    제외하도록 (구버전은 의상 의도만 있으면 모든 인물 번호를 지웠다).
    그리고 슬롯 N 교체를 쓰면 그 번호는 **교체 대상**이므로 의상 소스에서
    빼준다(OUTFIT_TARGET_PATTERNS).
    """
    slots = _clothing_source_slots(text)
    targets = _outfit_target_slots(text)
    return slots - targets if targets else slots


def _clothing_source_slots(text: str) -> set:
    """의상 소스 슬롯(교체 대상 판정 전 원본)."""
    slots = _collect_role_slots(text, CLOTHING_ROLE_PATTERNS)
    # 구버전 결함 교정(2026-09-29 실측): 골격 패턴 2번은
    # "이미지 2 의상을 이미지 1에 적용" 에서 "의상을 이미지 1" 을 잡아
    # **1번(주인물)까지 의상 소스로** 밀어 넣었다. 의상 슬롯이 늘어나면
    # 1번이 신원 소스에서 제외돼 사람이 사라진다.
    if _has_outfit_apply_verb(text):
        slots -= _collect_role_slots(text, _OUTFIT_APPLY_SLOT_PATTERNS)
    return slots


def _has_outfit_apply_verb(text: str) -> bool:
    """의장 교체/적용 동사가 있는 문장인지(대상 슬롯 오염 교정용)."""
    t = (text or "").lower()
    return bool(re.search(_OUTFIT_VERB, t))


# 텍스트 단독 의상 교체의 영어 의류 어휘. 왜(Why) 슬롯 패턴과 분리하나:
# `_clothing_role_slots` 는 "이미지 N 의 옷" 처럼 슬롯 번호를 요구한다.
# 그런데 "red evening dress 로 교체" 처럼 **옷 자체를 지목**하는 경우는
# 슬롯이 없다. 슬롯을 요구하면 텍스트 단독 교체를 영영 못 잡는다.
_EN_GARMENT_WORDS = (
    r"outfit|clothing|clothes|dress|gown|sweater|skirt|shirt|blouse|"
    r"pants|trousers|jeans|jacket|coat|suit|uniform|wardrobe|garment|"
    r"apparel|top|bottoms|knit|denim"
)


def _is_text_outfit_change(text: str) -> bool:
    """의상 참조 이미지 없이 텍스트만으로 옷 교체를 명시했는가.

    왜(Why) 이 함수가 필요한가 (2026-10-02 실측): 카메라가 명시적 교체 요청에도
    "same outfit" 을 함께 내보냈다. 같은 프롬프트에 "red evening dress" 와
    "same outfit" 이 공존하자 모델은 참조 이미지를 보고 원본을 택했다.
    0.00(키퍼 미동작)에서도 같은 옷이 나와 키퍼 문제가 아님을 확인했다.

    왜(Why) 슬롯을 요구하지 않나: `_is_outfit_transfer` 는 "이미지 N 의 옷" 처럼
    슬롯 번호를 요구한다. "빨간 드레스로 갈아입혀" 처럼 옷 자체를 지목하면
    슬롯이 없어서 영영 못 잡는다. 이 함수는 슬롯 없이 옷 교체 의사만 본다.

    왜(Why) 명시 유지가 우선하나: "same outfit", "keep the outfit" 처럼 유지를
    명시하면 교체로 보지 않는다. 모순된 지시에서 유지를 택한 것은 모델이 아니라
    코드가 먼저 정리해야 한다 — 둘 다 내보내면 모델이 참조 이미지를 보고
    원본을 택한다(실측).
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # 명시 유지는 교체가 아니다 — 먼저 제외한다.
    if re.search(r"\b(?:same|keep|preserve|maintain)\b[^.]{0,24}?\b(?:outfit|clothing|clothes|dress)\b", low):
        return False
    if re.search(r"(?:같은|원래|기존)\s*(?:옷|의상|드레스|차림)", t):
        return False
    # 영어: 교체 동사 + 의류 ("replace A with B dress", "change into ...")
    # 왜(Why) 굴절형을 넣나: `\bwearing\b` 은 `\bwear\b` 에 안 걸린다.
    # "wearing a red dress" 처럼 현재진행형이 가장 흔한 교체 표현이다.
    if re.search(r"\b(?:replac(?:e[sd]?|ing)|chang(?:e[sd]?|ing)|"
                 r"swap(?:ped|ping)?|wear(?:ing|s)?|wore|worn|"
                 r"dress(?:ed)? in)\b", low) and re.search(
            r"\b(?:" + _EN_GARMENT_WORDS + r")\b", low):
        return True
    # 영어: 형용사 + 의류 ("different outfit", "new dress", "red evening dress"
    # 뒤에 교체 맥락이 있을 때 — 단독 "red dress" 는 묘사일 수 있다)
    if re.search(r"\b(?:different|new|another|completely different)\b[^.]{0,32}?\b(?:"
                 + _EN_GARMENT_WORDS + r")\b", low):
        return True
    # 한국어: 교체 동사 + 의류 (슬롯 불필요)
    if re.search(_OUTFIT_VERB, low) and re.search(
            r"(?:의상|옷|옷차림|드레스|셔츠|블라우스|바지|원피스|코트|재킷|자켓|슈트|정장|한복|"
            r"outfit|clothing|dress|clothes)", low):
        return True
    # 한국어: "다른 옷", "새 드레스" (명시 교체)
    if re.search(r"(?:다른|새|새로운|완전히 다른)\s*(?:옷|의상|드레스|차림|outfit|dress)", t):
        return True
    return False


def _is_empty_scene(text: str) -> bool:
    """참조에 사람이 없음을 명시했는가 (빈 배경·가구·풍경).

    왜(Why) 명시만 보나: 빈 문자열은 사람이 있을 수 있다 (설명 생략).
    "사람 없음" 이라고 써야 identity 문구를 뺀다. 오탐이면 신원 보존이
    꺼져서 더 나쁘다 — 누락은 기존 동작 그대로라 안전하다.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # 영어: empty / no person / background only
    if re.search(r"\b(?:empty|vacant|unoccupied)\b[^.]{0,24}?\b(?:scene|bench|chair|bed|room|background)\b", low):
        return True
    if re.search(r"\bno\s+(?:person|one|people|human)\b", low):
        return True
    if re.search(r"\bbackground\s+only\b|\blandscape\s+only\b|\bstill\s+life\b", low):
        return True
    # 한국어: 빈 / 사람 없음 / 배경만
    if re.search(r"(?:빈|비어\s*있는)\s*(?:벤치|의자|침대|방|배경|풍경|장면)", t):
        return True
    if re.search(r"사람\s*(?:없|없음|없이)|아무도\s*없", t):
        return True
    if re.search(r"(?:배경|풍경)만", t):
        return True
    return False


def _outfit_target_slots(text: str) -> set:
    """교체 대상 슬롯(1~10). 슬롯 N 교체 -> 그 슬롯이 의상 소스가 아니라
    이쪽에 입히는 대상이다.

    왜(Why) 따로 두나(2026-09-29): 이 슬롯을 의상 슬롯으로 잡으면 **주인물
    이미지가 신원 소스에서 제외**돼 사람이 사라진다. 캡처 그룹을 만든
    제외용 패턴을 넣으면 반대로 슬롯이 추가되므로 빼기 전용으로 분리한다.

    왜(Why) 여기서 소스를 다시 빼나(2026-09-29): 슬롯과 동사 사이에 말이 끼면
    "2번 의장을 1번에 입혀" 에서 **2번(소스)도** 대상 후보로 잡힌다. 그대로
    빼면 _clothing_role_slots 에서 소스까지 사라져 의상 가드가 통째로 죽는다.
    순환을 피하려로 _clothing_source_slots(원본) 를 쓴다.
    """
    slots = _collect_role_slots(text, OUTFIT_TARGET_PATTERNS)
    return slots - _clothing_source_slots(text)


def _pose_role_slots(text: str) -> set:
    """포즈 참조 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): 포즈 지정 슬롯은 신원·의상·사물 소스가 아니다. 이걸 분리하지 않으면
    포즈만 빌려오려던 사람이 참조 이미지의 얼굴까지 복사당한다.
    """
    return _collect_role_slots(text, POSE_ROLE_PATTERNS)


def _second_person_slots(text: str) -> list:
    """인물 역할이 명시된 보조 슬롯(2~10) 번호 목록. 없으면 [].

    의상 교체 의도가 있으면 "의상 슬롯"만 인물 번호에서 제외한다 -- 왜(Why):
    의상 의도만 보고 모든 인물 번호를 지우면(구버전 동작) "2번 원피스로 갈아입기
    + 3번 남성 마주보기" 같은 혼합 씬에서 남성 duo 보존이 통째로 죽었다.
    순수 의상 실행("2번 원피스를 여성에게 입히기")은 의상 슬롯만 지우면
    결과가 구버전과 동일하다.
    """
    t = (text or "").lower()
    slots = set()
    for pattern in SECOND_PERSON_PATTERNS:
        try:
            for m in re.finditer(pattern, t):
                groups = [g for g in m.groups() if g]
                if groups:
                    slots.add(int(groups[0]))
                else:
                    slots.add(2)
        except (ValueError, re.error):
            continue
    if _is_outfit_transfer(text):
        slots -= _clothing_role_slots(text)
    return sorted(slots)


def _is_second_person_request(text: str) -> bool:
    """보조 슬롯에 두 번째 이후 인물이 명시됐는지만 판별한다."""
    return bool(_second_person_slots(text))


def _secondary_role_labels(labels, main=None, persons=(), poses=(),
                           clothing=()):
    """보조 역할 목록(주 슬롯·추가 인물·포즈 슬롯 제외)에서 9·10번(외양 참조 전용)을 제외한다.

    왜(Why): 9·10번의 역할은 외양 참조 가드(APPEARANCE_REF_POSITIVE / LLM
    image_note)가 전담한다. 일반 보조 역할 목록("배경·의상·소품…")에 9·10번이
    섞이면 외양 참조 지시와 충돌해 LLM·생성 모델이 외양을 무시하게 된다.

    main을 넘기면 주 피사체를 명시로 제외한다 -- 왜(Why): 첫 연결이 반드시
    주 피사체인 것은 아니다(첫 연결이 핸드백 + 다음이 여성). 넘기지 않으면
    기존 규약(첫 식별 = 주 피사체)대로 첫 슬롯을 제외한다. persons는
    추가 인물로 보존할 번호 -- 추가 인물은 배경/소품 역할 목록에 섞이면 안 된다.
    poses도 동일: 포즈 전용 슬롯을 "배경·의상·소품 중 요청된 역할" 목록에 넣으면
    자세 참고 지시와 충돌해 자세가 무시된다(포즈 참조 가드가 전담한다).
    clothing도 동일(2026-09-29 실측 결함 수정): 의상 소스 슬롯을 일반 보조
    역할 목록에 넣으면 그 슬롯에 "never their clothing or outfit" 이 붙어
    **의상 교체 가드와 정면 충돌**한다(같은 프롬프트 안에서 서로 반대 지시).
    의상 역할은 outfit transfer guard 가 전담한다.
    """
    try:
        main_n = int(str(main)) if main is not None else int(str((labels or ["1"])[0]))
    except (ValueError, TypeError, IndexError):
        main_n = None
    person_ns = set()
    for p in (persons or ()):
        try:
            person_ns.add(int(str(p)))
        except (ValueError, TypeError):
            continue
    for p in (poses or ()):
        try:
            person_ns.add(int(str(p)))
        except (ValueError, TypeError):
            continue
    for p in (clothing or ()):
        try:
            person_ns.add(int(str(p)))
        except (ValueError, TypeError):
            continue
    result = []
    for x in (labels or []):
        try:
            n = int(str(x))
        except (ValueError, TypeError):
            n = None
        if n is not None:
            if n in (9, 10):
                continue
            if n in person_ns:
                continue
            if main_n is not None and n == main_n:
                continue
        result.append(str(x))
    return result


def _object_role_slots(text: str) -> set:
    """사물/소품 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): "이미지 2의 핸드백" 같은 사물 지시가 인물 지시와 섞이는 씬에서
    사물 슬롯을 사람으로 오인하는 것을 막는다(다중 인물 자동 분류).
    """
    return _collect_role_slots(text, OBJECT_ROLE_PATTERNS)


# 가구·사물 DNA 보존 가드. 왜(Why): 사물 역할 문구가 "prop/product 역할로만
# 써라"까지만 말하면 모델이 **같은 종류의 다른 사물**을 새로 그린다. 실측에서
# 2번 침대 원본(먼 이불·러그·원목 프레임·쿠션 배치)이 3번 생성물에서 다른
# 침대로 바뀌었다. 사물도 인물과 마찬가지로 **참조가 곧 DNA**다.
# 형제 빌더(bass)와는 달리 여기서는 positive/negative를 한 쌍으로 준다.
FURNITURE_DNA_POSITIVE = (
    "prop identity guard: every object, furniture piece and prop keeps the exact "
    "identity of its reference image — same silhouette and construction, same "
    "material and surface texture, same colour and pattern, same proportions and "
    "part count, same placement in the frame. Do not substitute a different "
    "object, a different style, or a cleaner/simpler version of it."
)
FURNITURE_DNA_NEGATIVE = (
    "different furniture, substituted prop, generic furniture, simplified "
    "version, different material, wrong colour, wrong pattern, missing parts, "
    "extra parts, changed silhouette, object moved to a different spot"
)

# "살짝만 달라진 사물" 방어. 왜(Why): 사물 DNA 문구가 "형태를 유지하라"여도
# 모델은 색·무늬·비율을 조금씩 바꾸며 그린다. 실측에서 침대가 원본과 다른
# 침대로 바뀌었지만, 더 흔한 실패는 **비슷하지만 다른** 사물이다.
OBJECT_DRIFT_NEGATIVE = (
    "object replaced by a similar-looking but different object, near-miss "
    "furniture, almost-right prop, different fabric pattern, different wood "
    "tone, different cushion count, tidied-up version, simplified bedding, "
    "generic bedding, recoloured object, reshaped object"
)

# 사물 DNA 가드를 **제외**할 슬롯을 지정하는 어휘. 기본은 모든 보조 슬롯에
# DNA 보존을 적용한다(사용자가 topic에 "침대 원본"을 안 써도 켜져야 한다).
# 단, style/lighting/mood 전용으로 명시된 슬롯은 "사물 모양"이 아니라 분위기만
# 빌려오는 것이므로 DNA 보존이 오히려 해롭다.
NON_OBJECT_SLOT_KEYWORDS = (
    "style", "style reference", "mood", "moodboard", "lighting reference",
    "color palette", "colour palette", "grade", "composition reference",
    "style_only", "분위기", "무드", "분위기만", "색감", "색조",
    "조명만", "조명참고", "톤", "레퍼런스분위기",
)

# 찌꺼기 방어는 **항상** 켠다 (사용자 지적: topic에 안 써도 자동으로).
# 왜(Why): "벗는다"고 써도 안 써도 잔여물 자체는 언제든 틀린 결과다 — 완전히
# 없거나 그대로여야 하고, 반쪽은 어떤 경우에도 아니다. 트리거를 만들면
# 사용자가 문구를 외워야 하므로 방어 효과가 반감된다. garment·accessory는
# 인물이 거의 항상 있는 장면이므로 텍스트 한 줄이 비용 대비 이득이 크다.
# 다만 인물이 전혀 없는 실행(제품·공간 단독)에는 붙이지 않는다.
PARTIAL_OBJECT_NEGATIVE = (
    "leftover fragment of a removed item, detached shoe, half a shoe, "
    "shoe scrap, floating debris, orphaned object piece, partial object, "
    "cut-off object, object remnant on the floor, ghost object, "
    "debris of something that was taken off, orphaned garment piece, "
    "half a sleeve, floating cuff, detached collar, stray accessory"
)


def _furniture_dna_guard(text: str, object_slots) -> str:
    """가구·사물 DNA positive 문구. 사물 슬롯이 없으면 "".

    기본값(사용자 지적 반영): topic에 "2번 침대 원본"을 **안 써도** 켜져야 한다.
    사물도 참조가 곧 DNA이므로, 참조로 들어온 사물은 사용자가 별도로 지시하지
    않는 한 형태를 그대로 따라야 한다. 오직 style/mood/lighting 전용으로
    명시된 슬롯만 예외로 뺀다.
    """
    try:
        slots = sorted(int(x) for x in set(object_slots or []))
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    t = (text or "").lower()
    if any(k in t for k in NON_OBJECT_SLOT_KEYWORDS):
        # 분위기 전용 지정이 있으면 DNA 문구에서 "사물 대체 금지"를 약하게 한다
        # (분위기만 빌려오는 슬롯에 "같은 사물로 재현"을 강요하면 역효과).
        return FURNITURE_DNA_POSITIVE.replace(
            "Do not substitute a different object, a different style, or a "
            "cleaner/simpler version of it.",
            "Take only the mood and lighting from it, not the object shape."
        ) + f" This applies specifically to reference image(s) {slots and ', '.join(str(x) for x in slots)}."
    listed = ", ".join(str(x) for x in slots)
    return (FURNITURE_DNA_POSITIVE
            + f" This applies specifically to reference image(s) {listed}.")


def _object_dna_slots(topic: str, image_labels, image_count: int) -> set:
    """가구·사물 DNA를 적용할 슬롯 집합. topic에 아무 말 없어도 채운다.

    왜(Why): 사용자가 "2번 침대 원본을 써라"고 쓰지 않아도 2번에 침대를
    연결했다면 그 침대가 곧 DNA다. 기존 구현은 topic에 사물 역할이 명시될
    때만 발동해서(topic 미작성) DNA 가드가 조용히 꺼졌다.

    판정: **주 피사체·추가 인물·포즈 슬롯을 제외한 모든 연결 슬롯**이 기본
    대상이다. 단 style/mood/lighting 전용으로 명시된 슬롯은 제외한다.
    """
    try:
        if image_count <= 0:
            return set()
        labels = [int(str(x)) for x in (image_labels
                                       or list(range(1, image_count + 1)))]
        plan = _person_object_plan(topic or "", labels)
        excluded = {plan["main"]} | set(plan["persons"]) | set(plan["poses"])
        return {x for x in labels if x not in excluded}
    except Exception:
        return set()


def _remove_item_guard(text: str) -> str:
    """사물 제거 잔여물 negative. **항상** 켠다 (인물 주제 한정).

    왜(Why): 사용자가 "벗는다"고 topic에 쓰지 않아도 잔여물 자체는 틀린 결과다.
    반쪽 물체는 완전 제거도 완전 유지도 아닌 유일한 상태이고, 그것은 언제나
    틀리다. 트리거를 만들면 사용자가 문구를 외워야 하므로 효과가 반감된다.
    """
    try:
        t = (text or "").lower()
        if not _is_human_subject(t):
            return ""
        return PARTIAL_OBJECT_NEGATIVE
    except Exception:
        return ""


def _person_object_plan(text, labels):
    """연결 슬롯의 역할을 토픽 명시에서 분류한다.

    {"main": 주 피사체 번호, "persons": 추가 인물 번호, "objects": 사물 번호}

    왜(Why): 1번이 반드시 주 피사체인 것은 아니라는 실행(1번 핸드백 + 2번 여성)
    을 지원한다. 명시 근거가 없으면 기존 규약(첫 식별 = 주 피사체)을 유지해
    기존 실행과 결과가 완전히 동일하다. 9·10번(외양 참조 전용)은
    인물·사물 번호에서 모두 제외한다 -- 외양 참조는 인물도 사물도 아니다.
    포즈 지정 슬롯도 인물·사물에서 제외하고 주 피사체 후보에서도 뺀다 --
    자세만 빌려오는 슬롯을 신원 소스로 쓰면 참조의 얼굴이 섞인다.
    """
    try:
        label_ns = [int(str(l)) for l in (labels or [])]
    except (ValueError, TypeError):
        label_ns = []
    poses = _pose_role_slots(text) & set(label_ns)
    # 의상 소스 슬롯(교체 대상은 제외됨). 옷은 사람이 아니라 의상 소스이므로
    # 신원 소스 후보가 아니다 -- 아래 주 피사체 교정에서 함께 쓴다.
    outfits = _clothing_role_slots(text) & set(label_ns)
    objects = _object_role_slots(text) & set(label_ns) - {9, 10} - poses
    persons = (set(_second_person_slots(text)) & set(label_ns)
               - objects - {9, 10} - poses)
    # **교체 대상**은 이쪽에 의상을 입는 사람이므로 인물이다(실측 결함 수정).
    # "1 의상, 2 교체" 에서 2번이 persons 에 없으면 main 이 1번(주피사체=옷)으로
    # 남아 프롬프트가 "use reference image 1 as the only main human identity"
    # 라고 역전 지시한다 -> 2026-09-29 실제 실행에서 확인.
    targets = _outfit_target_slots(text) & set(label_ns)
    persons = (persons | targets) - objects - outfits
    main = label_ns[0] if label_ns else 1
    # **교체 대상이 첫 슬롯이면 그 사람이 곧 주 피사체다**(2026-09-29 실측).
    # 라벨 순서와 topic 을 무관하게 일관되게 하려면 여기서 먼저 확정한다.
    if main in targets:
        persons = persons - {main}
    # 첫 식별이 사물로 명시됐고 인물 후보가 있으면 첫 인물이 주 피사체가 된다.
    # 근거 없는 번호로 넘기지 않는다 -- 근거 없으면 기존 규약 유지.
    if main in objects and persons:
        main = min(persons)
        persons = persons - {main}
    # 첫 식별이 **의상 소스**면(옷 사진이 1번) 그 옷을 입을 사람이 주 피사체다.
    # 옷을 신원 소스로 지목하면 사람이 사라진다 -- 실측에서 확인된 결함.
    if main in outfits:
        rest = [x for x in label_ns if x not in outfits and x not in poses]
        if rest:
            # 교체를 명시했으면(rest 안에서 대상이 보이면) 그 사람을 우선한다.
            pick = next((x for x in rest if x in targets), None)
            main = pick if pick is not None else rest[0]
            persons = persons - {main}
    # 첫 식별이 포즈 지정이면(1번 = 자세 참고) 신원 소스를 다음 슬롯으로 넘긴다.
    # 전부 포즈 지정이면 신원 소스가 없으므로 기존 번호를 유지한다(graceful).
    if main in poses:
        rest = [x for x in label_ns if x not in poses]
        if rest:
            main = rest[0]
            if main in persons:
                persons = persons - {main}
    return {"main": main, "persons": sorted(persons), "objects": sorted(objects),
            "poses": sorted(poses), "outfits": sorted(outfits)}


def build_duo_person_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """보조 슬롯 인물 지정 시 해당 정체성을 모두 살린다 (2~10번 일반화).

    인물 간 신체 융합 방지를 포함한다. 왜(Why): 두 정체성을 살리라는 문구만
    있으면 모델이 두 신체를 하나로 녹이거나 팔다리를 뒤섞을 수 있어, 양방향
    (남성→여성, 여성→남성) 융합을 막는 분리 문구가 필요하기 때문이다.
    standalone 경로는 reference_guard의 duo 분기가 이 함수를 그대로 쓴다.
    사물 명시 슬롯(핸드백·시계 등)이 있으면 그 정체성을 살리지 않고
    "사물로만" 제한하는 문구를 덧붙인다 -- 왜(Why): duo 앵커만 던지면
    사물 슬롯이 사람으로 변하거나 복제될 수 있다.
    """
    if image_count < 2:
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    main, wanted, objects = plan["main"], plan["persons"], plan["objects"]
    if (not wanted and _second_person_slots(topic) and len(labels) >= 2
            and int(labels[1]) not in (9, 10) and int(labels[1]) not in objects
            and int(labels[1]) != main):
        # "두 번째 사람"처럼 슬롯 번호 없이 지칭하면 두 번째 연결 이미지를 쓴다.
        # 9·10번은 외양 참조 전용, 사물 명시 슬롯은 사물, 이미 주 피사체인 슬롯은
        # 중복 지정 대상이 아니다.
        wanted = [int(labels[1])]
    # 슬롯 번호 없이 "두 명 / couple / two people" 만 말한 경우.
    # 왜(Why) 이 폴백이 없으면: duo 앵커가 빈 문자열로 빠져서 reference_guard 가
    # 두 번째 참조를 "배경/소품/제품 역할로만" 지시한다(2026-09-28 실측). 사용자가
    # 두 사람의 사진을 붙였는데 두 번째 사람이 **소품으로 강등**되는 정반대 지시가
    # 나간다 — 가장 흔한 표현에서 가장 큰 오작동이다.
    _multi_fallback = False
    if (not wanted and len(labels) >= 2 and _is_multi_person_request(topic)
            and int(labels[1]) not in (9, 10) and int(labels[1]) not in objects
            and int(labels[1]) != main):
        wanted = [int(labels[1])]
        _multi_fallback = True
    persons = [str(main)] + [str(s) for s in wanted if int(str(s)) != main]
    # 마지막 게이트: 슬롯 명시("두 번째 사람") 또는 다인물 표현("두 명") 둘 중.
    if len(persons) < 2 or not (_is_second_person_request(topic)
                                or _multi_fallback):
        return ""
    count_word = _NUMBER_WORDS.get(len(persons), str(len(persons)))
    roles = " and ".join(
        f"person {_ORDINAL_WORDS.get(i + 1, str(i + 1))} from reference image {slot}"
        for i, slot in enumerate(persons))
    anchor = (f"{count_word} main people in the output: {roles}. "
              "Preserve each person's facial identity, hairstyle, and outfit. "
              "Keep each person's body fully separate with its own torso, two arms, and two legs, "
              "no merged or fused bodies, no extra limbs, no limbs swapping between people, "
              "no body parts blending into the other person, "
              "maintain clear personal boundaries unless physical contact is explicitly requested. "
              "No extra people, no cloned faces.")
    if objects:
        anchor += (" Use reference image(s) " + ", ".join(str(s) for s in objects)
                   + " only as props/objects, never as people.")
    return anchor







def reference_guard(image_count: int, image_labels=None, topic: str = "") -> str:
    """단일/다중 레퍼런스 이미지용 positive guard 문구를 반환한다."""
    if image_count <= 0:
        return ""
    # 왜(Why) 빈 장면이면 빈 문자열인가 (2026-10-02 실측): 참조에 사람이 없는데
    # "same person" 을 내보내면 모델이 누구를 만들지 몰라 유령(반투명 인물)을
    # 만든다 — 의자·침대 참조에서 실측. pose 0점으로 게이트는 알지만 카메라는
    # 몰랐다. 명시적 빈 장면 지시가 있으면 identity 문구를 내지 않는다.
    # 빈 문자열 topic 은 해당 없음 (사람 사진에 설명 없을 수 있음) — 명시적
    # 언급만 본다. 오탐보다 누락이 안전하다 (누락이면 기존 동작 그대로).
    if _is_empty_scene(topic or ""):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    main = str(plan["main"])
    # 동물 주제면 "얼굴 구조·헤어스타일"은 정면 모순이다(2026-09-28 실측:
    # "강아지 한 마리" 에 same facial structure/same hairstyle 과
    # 별도 five fingers/human proportions 까지 붙어 충돌했다). 품종명을
    # 하드코딩하지 않고 종·무늬 수준으로 일반화한다.
    if _is_animal_subject(topic or ""):
        if image_count == 1:
            return (f"preserve the same subject identity as reference image "
                    f"{main}, same species, same coat pattern and markings, "
                    "same body proportions, same overall color identity")
        return (f"use reference image {main} as the main subject identity "
                f"(same species, same coat pattern and markings, same body "
                f"proportions), do not humanize it, do not give it human hands "
                f"or facial features")
    if image_count == 1:
        # 왜(Why) 의상 교체 명시면 "same outfit" 을 빼나 (2026-10-02 실측):
        # 명시 요청("red evening dress 로 교체")에도 이 줄이 함께 나가면 같은
        # 프롬프트에 교체 지시와 유지 지시가 공존한다. 모델은 참조 이미지를 보고
        # 원본을 택하므로 교체가 일어나지 않는다 — 0.00(키퍼 미동작)에서도 같은
        # 옷이 나와 키퍼 문제가 아님을 확인했다. 얼굴·헤어·체형 유지는 그대로
        # 두고 옷만 뺀다. 신원은 유지하되 의상은 바꾸는 것이 요청의 의미다.
        if _is_text_outfit_change(topic or ""):
            return (f"preserve the same subject identity as reference image {main}, "
                    "same facial structure, same hairstyle, "
                    "same body proportions, same overall color identity")
        return (f"preserve the same subject identity as reference image {main}, "
                "same facial structure, same hairstyle, same outfit, "
                "same body proportions, same overall color identity")
    duo = build_duo_person_anchor(image_count, topic, image_labels=image_labels)
    if duo:
        # 두 번째 reference가 인물 역할이면 복제 금지 대신 두 정체성 보존을 둔다.
        # 사물 명시 슬롯의 소품 방어는 duo 앵커가 함께 전달한다.
        return duo
    secondary = _secondary_role_labels(labels, main=plan["main"],
                                       persons=plan["persons"],
                                       poses=plan["poses"],
                                       clothing=plan["outfits"])
    head = f"use reference image {main} as the only main human identity, "
    if secondary:
        head += ("use reference image(s) " + ", ".join(secondary)
                 + " only for their explicitly requested roles "
                 "such as background, composition, lighting, mood, or color, "
                 # 왜(Why) outfit 을 기본 목록에서 뺐나(2026-09-28 실측):
                 # topic 이 비면 "explicitly requested role" 이 없어서 모델이
                 # 이 목록에서 **자유롭게** 고른다. 그때 outfit 을 골랐고,
                 # 포즈 참조 이미지의 카디건+청바지가 그대로 복제됐다
                 # (포즈 가드 문구는 정확했는데 그 문구가 실행조차 안 됐다).
                 # 옷은 **명시 요청 시에만** 옮기고, 그 경로는 OUTFIT_GUARD 가
                 # 전담한다. 명시 요청 없는 옷 복사는 항상 실패였다.
                 "never their face, hair, skin tone, body identity, "
                 "clothing or outfit, and never their pose unless it was "
                 "explicitly requested, ")
    return head + (
        "do not duplicate the main subject, face, body, outfit, product, or background subject, "
        "do not turn secondary references into extra people, animals, products, or props "
        "unless explicitly requested, no cloned faces, no repeated bodies, "
        "no duplicated characters, no crowd unless requested, "
        "no background people unless requested"
    )


def build_secondary_role_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Qwen 경로용 다중 reference 역할 가드 (짧은 1문장).

    왜(Why): prompt_in 표준 경로의 positive_text에는 identity/single-person
    anchor만 있고, 보조 reference(배경/의상/소품)의 역할 제한과 주체 복제
    금지 문구가 없었다. standalone 경로의 장문 가드 대신 1문장으로 둔다.
    주 피사체는 계획(plan)이 선출한다 -- 첫 연결이 사물이면 다음 인물이 주체.
    """
    if image_count < 2:
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    secondary = _secondary_role_labels(labels, main=plan["main"],
                                       persons=plan["persons"],
                                       poses=plan["poses"],
                                       clothing=plan["outfits"])
    head = f"Use reference image {plan['main']} as the only main subject, "
    if secondary:
        head += ("use reference image(s) " + ", ".join(secondary)
                 + " only for explicitly requested roles "
                 "such as background, outfit, prop, product, style, lighting, "
                 "composition, or mood, ")
    return head + "do not duplicate the main subject."


def add_quality_guard(prompt: str, image_count: int = 0, topic: str = "", image_labels=None) -> str:
    """모델 공통 positive 품질 가드. negative 프롬프트는 건드리지 않는다."""
    prompt = (prompt or "").strip().rstrip(". ")
    # 동물 전용 주제면 사람 손·피부 품질 문구가 정면 모순이다. 사람/동물
    # 혼재 장면은 사람 가드를 유지한다(사람이 있으면 필요하다).
    _only_animal = _is_animal_subject(topic or "") and not _is_human_subject(
        topic or "")
    parts = [p for p in [prompt, QUALITY_GUARD_ANIMAL if _only_animal
                         else QUALITY_GUARD] if p]
    ref_guard = reference_guard(image_count, image_labels=image_labels, topic=topic)
    if ref_guard:
        parts.append(ref_guard)
    if not _only_animal:
        # 골반·힙 비율 가드는 사람 전용(동물의 실루엣을 humanoid 비율로
        # 끌고 간다). reference_guard 가 이미 종 보존 문구를 준다.
        body_guard = body_proportion_guard(image_count, topic,
                                           image_labels=image_labels)
        if body_guard:
            parts.append(body_guard)
    fit_guard = outfit_guard(image_count, topic)
    if fit_guard:
        parts.append(fit_guard)
    return ". ".join(parts) + "."


def assemble(scene: str, cam: dict, image_count: int = 0, topic: str = "", image_labels=None) -> str:
    """scene + 카메라 + 그레이드 + 범용 품질/정체성 가드 → 영문 prompt_out."""
    scene = (scene or "").strip().rstrip("., ")
    segs = [", ".join(build_clauses(cam)), GRADE.get(cam.get("grade"), "")]
    segs = [s for s in segs if s]
    if scene and segs:
        prompt = scene + ". " + ". ".join(segs) + "."
    elif scene:
        prompt = scene + "."
    else:
        prompt = ". ".join(segs) + "." if segs else ""
    detail = macro_detail_guard(topic or scene, cam)
    if detail:
        prompt = prompt.rstrip(". ") + ". " + detail + "."
    nudity = nudity_anatomy_guard(topic or scene)
    if nudity:
        prompt = prompt.rstrip(". ") + ". " + nudity + "."
    if _needs_scale_guard(topic or scene, cam):
        prompt = prompt.rstrip(". ") + ". " + SCALE_COHERENCE_POSITIVE + "."
    _eth_pos, _ = _ethnicity_guard(topic or scene, image_count, image_labels)
    if _eth_pos:
        prompt = prompt.rstrip(". ") + ". " + _eth_pos + "."
    if _is_animal_subject(topic or scene):
        prompt = prompt.rstrip(". ") + ". " + ANIMAL_SPECIES_POSITIVE + "."
    return add_quality_guard(prompt, image_count=image_count, topic=topic or scene,
                             image_labels=image_labels)


NUDITY_KEYWORDS = (
    "nude", "naked", "undressed", "bare body",
    "누드", "나체", "알몸", "전라", "옷을 벗",
)


def _is_nudity_request(text: str) -> bool:
    """노출 의도가 명시됐는지만 판별한다 (임상 가드 트리거용)."""
    t = (text or "").lower()
    return any(keyword in t for keyword in NUDITY_KEYWORDS)


def nudity_anatomy_guard(topic: str) -> str:
    """노출 의도 시 임상적 해부학 완성 문구를 반환한다.

    왜(Why): 노골적 성적 묘사 요구는 모델의 안전 튜닝에 막혀 프롬프트로
    완전히 극복할 수 없으므로, 노골 표현 대신 임상적 완성도 언어로
    뭉개짐·변형을 줄이는 데 그친다. 노출 의도가 없으면 붙지 않는다.

    주의: "anatomical/anatomically" 어휘는 학습 데이터 편향상 의학 도판·
    해부도 풍으로 그려지는 실측 사례가 있어 positive 가드에는 쓰지 않는다
    (사용자 실측 — "성기가 진짜 해부된다"). negative의 "deformed anatomy"
    는 변형을 막는 방향이라 유지한다.
    """
    if not _is_nudity_request(topic or ""):
        return ""
    return ("natural realistic human body with correct proportions, "
            "soft realistic skin and clearly defined natural intimate detail")


def macro_detail_guard(topic: str, cam: dict) -> str:
    """매크로 렌즈 + 인물 주제일 때만 미세 결 강조 문구를 반환한다.

    왜(Why): 100mm 매크로는 제품 촬영에도 쓰이므로 렌즈만으로는 모공·솜털
    문구를 붙일 수 없고, 인물 판정이 함께 있어야 제품에 체모 표현이
    들어가는 오작동을 막을 수 있다.
    """
    if cam.get("lens") != "100mm 매크로 (macro)" or not _is_human_subject(topic or ""):
        return ""
    return ("macro detail emphasis: extreme fine detail, sharp micro-contrast, "
            "visible pores, fine vellus hair, and natural skin texture")


def build_camera_conditioning(cam: dict) -> str:
    """Build only the camera direction used by the public conditioning node.

    This intentionally excludes scene identity, anatomy, skin, outfit, and
    quality guard text. The public conditioning path combines it with an
    upstream prompt string before a single final CLIP encode.
    """
    parts = [", ".join(build_clauses(cam)), GRADE.get(cam.get("grade"), "")]
    return ". ".join(part for part in parts if part) + "."


def _camera_failure_modes(cam: dict, topic: str = "") -> list:
    """렌즈·모션·노출 분기 negative 조각 (공용). 왜(Why): standalone과
    Skills negative가 같은 6분기를 따로 들고 있어 한쪽만 바뀌는 퇴행이
    있었다. 순서는 양쪽 기존 출력과 동일하게 유지한다."""
    out = []
    lens = cam.get("lens", "")
    if "초광각" in lens:
        out.append("unwanted wide-angle distortion")
    if "f/1.4" in lens:
        out.append("busy distracting background")
    if "매크로" in lens:
        out.append("soft detail, muddy texture")
    _m1, _m2 = cam.get("motion"), cam.get("motion2")
    if (_m1 not in ("없음 (none)", "", None)
            or _m2 not in ("없음 (none)", "", None)):
        out.append("shaky jitter, motion smear, frame warping")
    if _is_nudity_request(topic or ""):
        out.append("deformed intimate anatomy, blurred anatomy, featureless crotch area")
    return out


# 해부 디테일 negative 팩 (눈·치아·귀·발·관절). 왜(Why): 기존 anatomy 가드가
# 팔·손가락·얼굴 부위를 커버하지만 눈·치아 어긋남은 빠져 있었다. 인물 주제에만
# 양쪽 negative(standalone + Skills)에 자동 첨부한다.
ANATOMY_DETAIL_NEGATIVE = (
    "cross-eyed, asymmetrical eyes, misaligned pupils, "
    "deformed teeth, extra teeth, "
    "deformed ears, malformed feet, extra toes, "
    "broken joints, twisted knees"
)

# 인체 부위 **개수** 명시. 왜(Why): 기존 negative는 "6손가락 금지"만 강하게
# 있고 positive는 범용 품질 가드에 "believable hands with five fingers" 한 줄
# 묻혀 있었다. diffusion은 "X가 아니다"보다 "Y가 있다"에 잘 반응하므로
# 개수를 positive에 직접 박는다. 발가락·팔·다리는 positive가 아예 없었다.
# 한계(정직): 텍스트는 **부드러운 사전확률**이라 개수를 강제하지 못한다.
# 진짜 픽셀 강제는 참조 latent + 낮은 denoise로 원본 손을 보존하는 경로다
# (KSampler denoise 0.4~0.6, 노드 밖 설정).
ANATOMY_COUNT_POSITIVE = (
    "correct limb and digit count, clearly readable anatomy: exactly five "
    "fingers on each hand (one thumb plus four fingers), five toes on each "
    "foot, two arms ending in two hands, two legs ending in two feet, "
    "both sides of the body symmetrical, every limb fully formed and "
    "separated from its neighbour, hands and feet drawn as complete "
    "unambiguous shapes"
)
# 개수가 틀릴 때의 실제 형태. 왜(Why): 6손가락은 "6개가 추가"되는 게 아니라
# 손가락 2개가 붙거나(6→5로 보이게) 한 개가 갈라져 나오는 경우가 대부분이다.
# 그래서 "갯수 초과"가 아니라 **"붙음·갈라짐"** 형태를 막는다.
ANATOMY_COUNT_NEGATIVE = (
    "fused fingers, webbed fingers, mitten hands, fingers split down the "
    "middle, double thumbs, extra fingers, missing fingers, fingers merging "
    "into the palm, fused toes, split toes, extra toes, missing toes, "
    "feet merged into a single blob, arms fused to the torso, legs fused "
    "together, three arms, three legs, three feet, extra feet, "
    "asymmetric limbs, one arm, one leg"
)


# 스케일 일관 샷 — 인물 전신·주변이 함께 보이는 샷에서만 사물 스케일 점검.
SCALE_SHOTS = ("중근접 (MCU)", "중경 (MS)", "전신 (FS)", "원경 (WS)")

# 인물-사물 스케일 일관 문구. 왜(Why): 침대 같은 배경 사물이 인체 대비
# 너무 작거나 크게 그려지는 원근·스케일 prior 흔들림을 프롬프트층에서 잡는다.
# latent 당김으로는 스케일을 못 고치므로 이 가드가 담당한다.
SCALE_COHERENCE_POSITIVE = (
    "consistent proportional scale between the person and surrounding "
    "furniture and background, natural perspective")
SCALE_COHERENCE_NEGATIVE = (
    "inconsistent object scale, miniature background, oversized person")


def _needs_scale_guard(topic: str, cam: dict) -> bool:
    """인물 + 전신·주변 가시 샷이면 스케일 가드 대상."""
    try:
        return bool(_is_human_subject(topic or "")
                    and (cam or {}).get("shot", "") in SCALE_SHOTS)
    except Exception:
        return False


# 국가·출신지 표현형 반영.
# 왜(Why): "아랍"만 넣으면 수염·갈피·전통의상으로, "한국"만 넣으면 서구화로
# 수렴한다(SDXL 인종 동질화 실증, Sci Rep 2025). 두 실패는 프롬프트 레벨에서
# 막을 수 있다. 근거 3가지:
#  1) 출처: EMNLP Findings 2023 "person from X" 문맥이 국가명 직접 표기보다
#     고정관념·동질화가 적다 → 인종 본질 표현("East Asian facial features")
#     대신 출신지 문맥을 쓴다.
#  2) 분산: 같은 나라를 넣어도 사람마다 다른 얼굴이어야 한다. 집합 내 개별
#     변이 문구를 positive에, "한 나라가 한 얼굴" 고정을 negative에 넣는다.
#  3) 교차축: 인종 축만 건드리면 성별 등 다른 축이 29%에서 악화된다
#     (EMNLP Findings 2025 InterMit) → 성별어는 절대 넣지 않는다.
# 지역 묶음은 FairFace 7분류(CC BY 4.0, bias measurement 용)의 구획을 빌려
# 국가→지역 대응에만 쓴다. 데이터셋 라벨이나 이미지를 동봉·복제하지 않는다.
# 형식: 키워드튜플 → (지역, 영문 출신지 표기)
ETHNICITY_GROUPS = (
    (("한국", "korea", "korean"), "Korea"),
    (("일본", "japan", "japanese"), "Japan"),
    (("중국", "china", "chinese"), "China"),
    (("태국", "thailand", "thai"), "Thailand"),
    (("베트남", "vietnam", "vietnamese"), "Vietnam"),
    (("인도", "india", "indian"), "India"),
    (("미국", "america", "usa", "u.s"), "the United States"),
    (("영국", "british", "england", "u.k", "united kingdom"),
     "the United Kingdom"),
    (("프랑스", "france", "french"), "France"),
    (("독일", "germany", "german"), "Germany"),
    (("브라질", "brazil", "brazilian"), "Brazil"),
    (("멕시코", "mexico", "mexican"), "Mexico"),
    (("이집트", "egypt", "egyptian"), "Egypt"),
    (("아랍", "arab"), "an Arab country"),
    (("나이지리아", "nigeria", "nigerian"), "Nigeria"),
    (("케냐", "kenya", "kenyan"), "Kenya"),
)
TRADITIONAL_KEYWORDS = (
    "한복", "기모노", "kimono", "hanfu", "traditional", "전통",
    "사리", "sari", "히잡", "hijab", "터번", "turban",
)
# 주제에 이미 외양·얼굴 서술이 있으면 국가 표현형보다 그 서술이 우선이다.
APPEARANCE_DESCRIBED_KEYWORDS = (
    "얼굴", "외모", "외양", "이목구비", "얼굴형", "피부색", "피부톤",
    "모발", "머리색", "얼박살",
    "face", "facial features", "appearance", "complexion", "skin tone",
    "hair color", "eye color", "freckle",
)
ETHNICITY_DIVERSITY_POSITIVE = "varied individual facial features within the group"
ETHNICITY_MODERN_WEAR = "modern everyday clothing"
ETHNICITY_STEREOTYPE_NEGATIVE = (
    "westernized facial features, forced traditional costume, "
    "historical costume by default, exotic stereotype, "
    "every person from the same country looking identical, "
    "one homogenized face type for a whole country"
)


def _ethnicity_identity_locked(topic: str, image_count: int,
                               image_labels=None) -> bool:
    """참조 이미지가 이미 신원을 고정했거나 주제가 외양을 서술하면 국가 표현형은 미첨부.

    왜(Why): DNA(신원·외양)는 사용자가 준 픽셀 근거가 1순위다. 그 위에 국가
    표현형을 덮으면 사용자가 정한 인물이 밀린다.
    """
    try:
        text = (topic or "").lower()
        if any(k in text for k in APPEARANCE_DESCRIBED_KEYWORDS):
            return True
        if image_count <= 0:
            return False
        plan = _person_object_plan(topic or "", image_labels)
        return plan["main"] not in plan["objects"] or bool(plan["persons"])
    except Exception:
        return False


def _ethnicity_guard(topic: str, image_count: int = 0,
                     image_labels=None) -> tuple:
    """(positive 조각, negative 조각). 조건 불충족이면 ("", "")."""
    try:
        t = (topic or "").lower()
        if not _is_human_subject(topic or ""):
            return "", ""
        if _ethnicity_identity_locked(topic or "", image_count, image_labels):
            return "", ""
        for keywords, origin in ETHNICITY_GROUPS:
            if any(k in t for k in keywords):
                pos = f"a person from {origin}, {ETHNICITY_DIVERSITY_POSITIVE}"
                neg = ""
                if not any(k in t for k in TRADITIONAL_KEYWORDS):
                    pos += ", " + ETHNICITY_MODERN_WEAR
                    neg = ETHNICITY_STEREOTYPE_NEGATIVE
                return pos, neg
        return "", ""
    except Exception:
        return "", ""


# 얼굴 클로즈업 샷 — latent가 작으면 얼굴 뭉개짐 확정이라 출발 점검 대상.
FACE_CRITICAL_SHOTS = ("극접 (ECU)", "근접 (CU)")


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


def _assemble_negative(cam, topic, image_count, image_labels, flags,
                       noir_phrase, extras=(), physics_neg="",
                       pose_ref=False, prevent_duplicates=False) -> str:
    """두 negative 빌더가 공유하는 조립 로직.

    왜(Why) 하나인가(2026-09-29): `build_negative` 와
    `build_camera_negative` 가 40줄을 복붙하고 있었다. 같은 상수를 같은
    순서로 넣는데 한쪽만 고치면 **양쪽이 어긋나** 짝인 방어가 조용히
    사라진다 — 실제로 `_camera_failure_modes` 로 일부를 이미 합친 뒤에도
    시트·포즈·부위·가구 블록이 그대로 두 벌이었다.

    유일한 차이가 `noir_phrase` 이었다("unwanted color cast" vs
    "color tint"). 그 차이는 **호출부가 준다** — 함수 안에서 guessing 하지
    않는다.
    """
    neg = list(_NEGATIVE_BASE_COMMON)
    # topic 이 비면(판단 근거 없음) 사람 기본값을 쓴다. ComfyUI 사용의
    # 대부분이 인물이고, 비었을 때 가드를 빼는 쪽이 더 위험하다.
    if not (topic or "").strip() or _is_human_subject(topic):
        neg.append(NEGATIVE_ANATOMY_GUARD)
        neg.append(NEGATIVE_COLOR_CONTAMINATION_GUARD)
    neg.extend(_camera_failure_modes(cam, topic))
    if cam.get("grade") == "느와르 (noir)":
        neg.append(noir_phrase)
    if _is_human_subject(topic or ""):
        neg.append(ANATOMY_DETAIL_NEGATIVE)
    # positive(ANATOMY_COUNT_POSITIVE) 는 붙는데 negative 짝이 없으면
    # "5개여야 한다" 는 지시가 방향 없는 한쪽_only 가 된다(2026-09-28 발견).
    if flags.get("anatomy_count"):
        neg.append(ANATOMY_COUNT_NEGATIVE)
    if flags.get("character_sheet"):
        neg.append(CHARACTER_SHEET_NEGATIVE)
        # 시트 뷰가 별개 인물로 세어지는 것까지 막는다 (신원 일관성이 목적이므로).
        if not _is_multi_person_sheet(topic):
            neg.append(CHARACTER_SHEET_PEOPLE_NEGATIVE)
    _, _eth_neg = _ethnicity_guard(topic or "", image_count, image_labels)
    if _eth_neg:
        neg.append(_eth_neg)
    if _is_animal_subject(topic or ""):
        neg.append(ANIMAL_ANATOMY_NEGATIVE)
    # 포즈 negative: 빈 문자열을 넣지 않는다 (빈 조각이 ", " 꼬리를 남긴다)
    _pose_neg = _pose_reference_negative(
        _pose_role_slots(topic or "") & set(image_labels or [])) if pose_ref else ""
    if _pose_neg:
        neg.append(_pose_neg)
    if physics_neg:
        neg.append(physics_neg)
    if flags.get("detail_def"):
        neg.append(DETAIL_DEFINITION_NEGATIVE)
    if flags.get("furniture"):
        neg.append(FURNITURE_DNA_NEGATIVE)
        neg.append(OBJECT_DRIFT_NEGATIVE)
    if flags.get("remove_item"):
        neg.append(_remove_item_guard(topic))
    if _needs_scale_guard(topic or "", cam):
        neg.append(SCALE_COHERENCE_NEGATIVE)
    if prevent_duplicates:
        neg.extend(["multiple people", "duplicate person", "cloned person",
                    "mirrored twin", "background person"])
    for src in extras:
        if src and src.strip():
            neg.append(src.strip())
    return ", ".join(neg)


def build_camera_negative(cam: dict, prevent_duplicates: bool = False,
                          topic: str = "", image_count: int = 0,
                          image_labels=None, pose_ref: bool = False,
                          physics_neg: str = "", detail_def: bool = False,
                          furniture: bool = False,
                          remove_item: bool = False,
                          anatomy_count: bool = False,
                          character_sheet: bool = False) -> str:
    """카메라/영상 실패 모드 + 인물 해부 디테일 방어 (신원·신체 비율 가드 제외)."""
    return _assemble_negative(
        cam, topic, image_count, image_labels,
        {"anatomy_count": anatomy_count, "character_sheet": character_sheet,
         "detail_def": detail_def, "furniture": furniture,
         "remove_item": remove_item},
        "unwanted color cast", physics_neg=physics_neg, pose_ref=pose_ref,
        prevent_duplicates=prevent_duplicates)



# llm_hint 사용 시 검열 아티팩트 방어어. (Why: 모델이 학습 편향으로
# 스스로 순화·블러·모자이크를 그리는 사례 방지. "blurred"는 bokeh와
# 충돌하므로 의도적으로 제외했다. base run()과 Skills run_prompt 양쪽에서
# 동일한 문구를 쓰므로 상수로 공유한다.)
HINT_DEFENSE_NEGATIVE = "censored, mosaic, bar censor, pixelated"


# 다중 참조(2장 이상) 실행의 "믹스 변형" 방어어. (Why: 얼굴+의상 등 둘 이상의
# 참조 이미지를 섞는 실행에서는 옷-피부 융합, 신원 혼합, 인물 복제 같은
# 합성 변형이 잘 일어난다. 연결된 이미지 개수는 픽셀 근거라 오검출이 낮다.
# 첫 번째 연결 이미지가 신원 소스라는 규약은 image_note/신원 앵커와 동일하다.
# base run()과 Skills run_prompt 양쪽에서 공유한다.)
MIX_GUARD_POSITIVE = (
    "Reference mixing guard: the main person reference image is the only identity source "
    "(face, body shape, proportions); the other reference image(s) contribute "
    "only their requested role such as outfit, background, prop, product, "
    "style, lighting, composition, or mood. Garments from a clothing reference "
    "are a separate clothing layer placed over the main person's body, "
    "following the existing anatomy, preserving the main person's body shape, "
    "skin, face, and hair; pose follows the topic. No blending of two people into one, no mixed "
    "facial features between references."
)
MIX_GUARD_NEGATIVE = ("clothing fusion with skin, melted garment edges, "
                      "body parts merging into clothing, mixed facial features, "
                      "identity blending, duplicated person")

# 포즈 참조 가드. 왜(Why): Qwen reference 경로는 이미지 전체를 latent로 주입하므로
# 자세만 빌려오게 해도 참조 인물의 얼굴·피부·머리·의상이 함께 유입된다. 텍스트
# 가드만으로는 이미지 모델이 텍스트보다 시각 근거를 더 강하게 따르는 특성상
# 막기 어렵기 때문에, LLM 비전에서는 아예 빼고(픽셀 경로로만 전달) + 여기서
# "자세 전용"을 명시한다.
def _pose_reference_guard(pose_slots) -> str:
    """포즈 참조 positive 문구. 지정 슬롯이 없으면 ""."""
    try:
        slots = [int(x) for x in sorted(set(pose_slots or []))]
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    listed = ", ".join(str(x) for x in slots)
    return (f"Pose reference guard: reproduce the body pose and limb angles of "
            f"reference image(s) {listed} and nothing else from them. Take ONLY "
            f"the posture from those images — never their face, facial features, "
            f"skin tone, hair, body identity, clothing, or background. The "
            f"subject's identity and wardrobe come from the main reference and "
            f"the topic, not from the pose reference.")


def _pose_reference_negative(pose_slots) -> str:
    """포즈 참조 negative 문구. 지정 슬롯이 없으면 ""."""
    try:
        slots = [int(x) for x in sorted(set(pose_slots or []))]
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    listed = ", ".join(str(x) for x in slots)
    return (f"face of the pose reference image {listed}, "
            f"clothing of the pose reference image {listed}, "
            f"body identity of the pose reference image {listed}, "
            f"background of the pose reference image {listed}, "
            f"face swap with the pose reference, identity blending between "
            f"the pose reference and the subject")


# ---------------------------------------------------------------------------
# 물리·공간 가드 (2026-09-28)
#
# 왜(Why): topic에 "벽에 밀어붙였다/던진다/붙잡는다"라고 써도 노드가 아무 지시도
# 안 붙이면 모델은 그 단어를 그릴 정보로 못 받아 "나란히 서 있는 두 사람"을
# 그린다. 언어를 **이미지의 물리 상태**로 번역해 붙이는 것이 이 가드의 역할이다.
#
# 범위(정직한 한계): 정확한 관절 각도·타격 프레임은 ControlNet OpenPose 영역이며
# 이 가드가 보장하지 않는다. 대신 모델이 수렴하는 해를 "정지 정면 배치"에서
# "접촉·비행·충격" 쪽으로 밀어 올리는 것이 목적이다.
# ---------------------------------------------------------------------------

# 주의(한국어 활용): 동사 어간이 끝 모음이면 활용 때 음절이 변한다.
# "던지"는 "던진다·던져·던졌다"에 문자열로 들어가지 **않는다**(던지→던진+다).
# 그래서 활용 형태를 여러 개 적거나, 끝 자음이 있는 어간(뛰/달리/당기/끌/잡)을 쓴다.
# 이걸 놓치면 무협 액션 장면이 그대로 "나란히 서 있기"로 수렴한다.
# 물리 접촉/동작 → (positive 물리 상태, negative 되돌림 방지)
PHYSICS_CONTACT_RULES = (
    (("밀어붙", "밀어", "붙여", "붙여넣", "벽에", "누르", "눌러", "가뒀", "가두",
      "붙잡", "붙들", "조인다", "꽉 잡", "press against", "pin against",
      "push against", "pressed against"),
     "physical contact between the people: their bodies are touching with no gap "
     "between them, one person's body braced against a surface while the other "
     "leans into them, overlapping silhouettes, weight visibly transferred",
     "standing apart, empty space between the two people, both standing upright "
     "and separate, no contact"),
    (("안고", "안는", "안은", "안키", "안김", "품에", "감싸", "拥抱", "hold",
      "hug", "embrace", "carried"),
     "close hold: arms wrapped around the other person's body, bodies pressed "
     "together, the held person lifted with feet clear of the ground",
     "standing separately, arms at sides, no embrace, both feet on the ground"),
    (("던지", "던진다", "던져", "던졌", "던짐", "던질", "투척", "채비", "throw",
      "hurl", "toss", "fling"),
     "throwing motion: the thrown figure is airborne with both feet off the "
     "ground and the body rotated, the thrower's weight shifted onto the back "
     "leg with the torso leaning away, limbs trailing",
     "both people standing normally, nobody airborne, static pose, no throwing"),
    (("뛰", "달리", "달렸", "질주", "전력질주", "sprint", "run", "dash",
      "chase", "race"),
     "running motion: the body pitched forward, legs split mid-stride, one foot "
     "off the ground, arms driving, clothing and hair pushed backward by motion",
     "standing still, feet together, static posture, no motion"),
    (("넘어", "넘었", "추락", "쓰러", "쓰러져", "굴러", "무너", "fall",
      "tumble", "collapse", "trip"),
     "falling motion: the body tilted off axis and mid-collapse, limbs flung "
     "outward for balance, the ground plane clearly visible beneath",
     "upright standing, balanced on both feet, no fall"),
    (("부딪", "충돌", "충격", "격돌", "튕겨", "부딪혀", "부딪히", "몰아붙",
      "impact", "collide", "slam", "crash", "strike"),
     "impact moment: the bodies locked together at the point of collision, "
     "compressed posture at the contact point, force visibly transferred "
     "through the limbs, hair and clothing whipping away from the blow",
     "gentle contact, relaxed posture, no impact, calm static scene"),
    (("당기", "끌어", "끌고", "잡아당", "grab", "pull", "rope", "chain",
      "사슬", "줄을"),
     "grappling: a closed grip around the other person, arms locked and bent, "
     "both bodies leaning into the pull with feet braced apart",
     "hands at sides, no grip, relaxed arms, no tension"),
    # 무협·격투·전투 — 사용자가 가장 많이 쓰는 시나리오라 맨 뒤(최저 우선순위)에
    # 둔다. 위 규칙(밀어붙/던지/넘어 등)이 있으면 그쪽이 더 구체적이다.
    (("공격", "무협", "액션", "격투", "전투", "싸움", "싸", "정면으로",
      "칼", "검", "무기", "격", "attack", "fight", "combat", "battle",
      "sword", "blade", "duel", "fistfight", "grapple"),
     "combat engagement: the two figures are locked in close-quarters contact "
     "mid-exchange, one figure advancing and the other reacting, limbs "
     "interlocked, bodies angled into each other rather than parallel",
     "the two figures standing side by side, facing the same direction, "
     "relaxed neutral posture, no combat contact"),
)

# 빠른 동작 → 시간/속도 표현. 접지·무게중심은 전 인물의 기본값(각주 아님).
PHYSICS_MOTION_POSITIVE = (
    "frozen mid-action at the peak of the motion, believable center of gravity, "
    "correct contact shadows where the body meets the ground, no floating "
    "subjects, no missing weight"
)
# 빠른 동작 키워드 — 이게 있을 때만 속도 표현을 붙인다(정지 장면 오탐 방지).
FAST_MOTION_KEYWORDS = (
    "던지", "던진다", "던져", "던졌", "투척", "채비", "throw", "hurl", "toss",
    "fling", "뛰", "달리", "달렸", "질주", "sprint", "dash", "chase", "race",
    "넘어", "넘었", "추락", "쓰러", "굴러", "무너", "fall", "tumble",
    "collapse", "trip", "부딪", "충돌", "충격", "격돌", "튕겨", "몰아붙",
    "impact", "collide", "slam", "crash", "strike", "싸", "전투", "격투",
    "무협", "fight", "battle", "공격", "방어", "검", "칼", "무기", "sword",
    "combat", "attack", "밀어붙", "붙잡", "당기", "안고", "고수", "액션",
    "action",
)
# 정적 장면 — 오히려 "노 motion blur"를 붙여 인물이 뭉개지는 걸 막는다.
STATIC_SCENE_KEYWORDS = (
    "정지", "멈춰", "조용한", "정숙", "수목도", "물결", "고요",
    "still", "static", "serene", "calm", "quiet", "peaceful", "motionless",
)


def physics_contact_guard(topic: str) -> tuple:
    """(positive, negative). 접촉/동작 신호가 없으면 ("", "").

    왜(Why): 사용자가 topic에 쓴 물리 동사는 이미 의도다. 그걸 이미지의
    물리 상태로 번역해 붙이는 것이 이 노드가 실제로 기여할 수 있는 부분이다.
    정밀 각도는 ControlNet 영역이므로 여기서는 수렴 지점을 올리는 데 그친다.
    """
    try:
        t = (topic or "").lower()
        if not t:
            return "", ""
        for keywords, pos, neg in PHYSICS_CONTACT_RULES:
            if any(k in t for k in keywords):
                # 시간·속도 축: 빠른 동작일 때만 중간 프레임을 명시한다.
                if any(k in t for k in FAST_MOTION_KEYWORDS):
                    pos = pos + ", " + PHYSICS_MOTION_POSITIVE
                elif any(k in t for k in STATIC_SCENE_KEYWORDS):
                    neg = neg + ", motion blur on the subject"
                return pos, neg
        return "", ""
    except Exception:
        return "", ""


def physics_grounding_guard(topic: str) -> str:
    """정적 인물 장면에도 붙는 최소 물리(접지·무게중심) 문구. 없으면 ""."""
    try:
        t = (topic or "").lower()
        if not t or not _is_human_subject(t):
            return ""
        if any(k in t for k in FAST_MOTION_KEYWORDS):
            return ""
        return ("believable center of gravity, correct contact shadows under the "
                "feet, feet firmly on the ground, no floating subjects")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 픽셀 기반 공간 측정 (2026-09-28)
#
# 왜(Why): topic에 "벽에 밀어붙였다"를 사용자가 직접 써야만 접촉 가드가 켜졌다.
# 그런데 접촉/간격은 기하 사실이므로 픽셀에서 읽는 것이 정확하다. 노드에 이미
# 있는 _reference_lighting_flow와 같은 numpy 저해상도 접근을 재사용한다.
#
# 원리: 저해상도 명암 격자 → "전경으로 보이는" 열 밀도 프로파일 → 봉우리(피사체)
# 사이 골짜기(간격) 폭. 골짜기가 없으면 실루엣이 겹친 것 = 접촉/밀착.
#
# 정직한 한계(중요):
#  1) "붙어 있다"까지만 읽는다. 그게 격투인지 포옹인지는 모른다 — topic 텍스트와
#     합쳐져야 한다.
#  2) 배경(나무·건물)이 봉우리로 잡힐 수 있다. 그래서 보수적으로만 발동시키고
#     측정값을 로그에 남겨 사용자가 확인할 수 있게 한다.
#  3) 새 의존성 없음 (numpy만). MediaPipe를 넣지 않는다.
# ---------------------------------------------------------------------------
SPACING_GRID = 48          # 저해상도 격자 (세로 기준, 가로는 2배 해상도)
# 피부색 임계는 노드가 다루는 HDR/명암 이미지와 맞아야 한다. headshot 텐서는
# 0~1 스케일이고 배경(바=The Rock, 하늘)은 채도가 낮다. 채도 조건을
# 느슨하게 두면 회색 배경까지 "머리"로 잡혀 오탐이 된다(실측 확인).
SPACING_SKIN_CHROMA = 0.12  # 최소 채도
SPACING_RG = 0.05           # 최소 R-G 차이
SPACING_TOUCH_RATIO = 0.03  # 간격이 이보다 작으면 "근접"으로 판단
SPACING_APART_RATIO = 0.05  # 간격이 이보다 크면 "확연히 떨어짐"으로 판단
SPACING_FAR_RATIO = 0.28   # 간격이 이보다 크면 "크게 떨어짐"(화면 양끝 수준)
SPACING_HEAD_BAND = 0.18    # 머리 분리 판정용 상단 밴드 비율 (어깨 위까지만)


def _skin_score(rgb_small):
    """저해상도 RGB 격자 → 피부색 가능성(0~1) 맵. 실패 시 None.

    왜(Why): 머리 검출을 명암 차이로만 하면 어깨선·난간·울타리도 "머리"로
    잡힌다. 사람은 피부색 덩어리로 구분하는 것이 가장 싼 신호다.
    규칙은 고전 RGB 임계(Kovacic et al.)를 0~1 스케일로 옮긴 것으로 새
    의존성이 없다.
    """
    try:
        import numpy as _np
        a = _np.asarray(rgb_small, dtype=_np.float32)
        if a.ndim != 3 or a.shape[2] < 3:
            return None
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        mx = a.max(axis=2)
        mn = a.min(axis=2)
        chroma = mx - mn
        cond = ((r > g) & (r > b) & (chroma > SPACING_SKIN_CHROMA)
                & (_np.abs(r - g) > SPACING_RG))
        return cond.astype(_np.float32)
    except Exception:
        return None


def subject_spacing(image) -> dict:
    """참조 이미지 1장의 피사체 공간 상태를 **기하만** 측정한다. 실패 시 {}.

    반환: {"gap_ratio": 두 덩어리 사이 저밀도 열 비율, "peaks": 덩어리 수,
           "heads": 상단 밴드에서 센 머리 수, "close"/"apart"/"far": bool,
           "v_separate": bool, "bottom_margin": 하단 여백, "subject_ratio": 전경 비율}

    왜 인원수는 여기서 판정하지 않는가:
    실측에서 "1인물"도 접촉으로 오검출됐다. 세그멘테이션 없이 픽셀만으로
    "1명인가 2명인가"를 구분하는 것은 신뢰할 수 없다. 그래서 **픽셀은 공간
    (간격·하단 여백)만 측정하고, 인원수는 topic 텍스트가 맡는다.**
    """
    out = {}
    try:
        import numpy as _np
        import torch as _t
        px = image[0] if isinstance(image, _t.Tensor) else image
        px = px.detach().cpu() if hasattr(px, "detach") else px
        arr = _np.asarray(px, dtype=_np.float32)
        if arr.ndim == 4:
            arr = arr[0]  # (B,H,W,C) → (H,W,C). IMAGE 텐서·배열 모두 허용
        if arr.ndim != 3 or arr.shape[0] < 4 or arr.shape[1] < 4:
            return out
        h, w = arr.shape[0], arr.shape[1]
        if arr.max() > 1.5:
            arr = arr / 255.0
        # 저해상도 격자로 축소 (평균 풀링). 가로를 세로보다 2배 해상도로 둔다
        # — 간격이 작으므로 가로 해상도가 곧 측정 정밀도다.
        # 주의: gh/gw 는 **셀 개수**, rows/cols 는 **셀 픽셀 크기**다.
        # (실측에서 둘을 뒤바꾸어 8x16 격자로 간격을 못 잰 결함 발생)
        # 저해상도 격자: 인덱스 표본(linspace)으로 줄인다. reshape 풀링은
        # 픽셀 수가 격자로 안 나누어떨어지면 잘라 먹거나(실측 256px에 96열 →
        # 5x2 격자로 붕괴) reshape가 실패한다. linspace는 어떤 크기도 정확히
        # gh x gw 격자로 만들고 원본 픽셀도 빠짐없이 쓴다.
        gh = max(1, min(SPACING_GRID, h))
        gw = max(1, min(SPACING_GRID * 2, w))
        yi = _np.linspace(0, h - 1, gh).astype(_np.int64)
        xi = _np.linspace(0, w - 1, gw).astype(_np.int64)
        # RGB와 명암을 같은 격자로 함께 만든다(셀 경계가 어긋나면 안 됨)
        small_rgb = arr[yi][:, xi]
        small = (small_rgb[..., 0] * .299 + small_rgb[..., 1] * .587
                 + small_rgb[..., 2] * .114)
        skin = _skin_score(small_rgb)
        border = _np.concatenate([small[0, :], small[-1, :], small[:, 0], small[:, -1]])
        bg = float(border.mean())
        fg = _np.abs(small - bg)
        cx = _np.linspace(-1, 1, gw, dtype=_np.float32)
        weight = 1.0 - 0.55 * _np.abs(cx)[None, :]
        fg = fg * weight
        thr = float(fg.mean()) + 0.6 * float(fg.std())
        mask = fg > thr
        col = mask.sum(axis=0).astype(_np.float32)
        out["subject_ratio"] = round(float(mask.mean()), 3)
        if out["subject_ratio"] < 0.02:
            return out  # 피사체가 거의 없으면 측정 불가
        cmax = float(col.max())
        if cmax <= 0:
            return out
        # 두 겹 기준: core(50%)는 덩어리 중심, edge(15%)는 덩어리 경계.
        # 간격은 core가 아니라 **edge 기준으로 끊긴 두 덩어리 사이의 폭**으로 잰다.
        # (core로 재면 경계 셀이 통과해 간격이 0으로 계산된다 — 실측 오류)
        edge_thr = max(0.4, cmax * 0.15)
        runs, cur = [], None
        for i, v in enumerate(col):
            if v >= edge_thr:
                cur = [i, i] if cur is None else [cur[0], i]
            elif cur is not None:
                runs.append(tuple(cur))
                cur = None
        if cur is not None:
            runs.append(tuple(cur))
        if not runs:
            return out
        out["peaks"] = len(runs)
        # 실루엣 폭은 **측정하지 않는다** — 실측에서 근경 1인(0.50)이 붙은 2인
        # (0.44)보다 넓게 나와 "몇 명인가" 판정에 쓸 수 없었다. 판정 근거로 쓰면
        # 오탐이 되므로 아예 계산하지 않는다(과잉 계산 제거).
        # 간격: 인접한 덩어리 사이에서 밀도가 낮게 떨어진 열 수
        gap_cells = 0
        for ri in range(len(runs) - 1):
            between = col[runs[ri][1] + 1:runs[ri + 1][0]]
            if between.size == 0:
                continue
            low = int((between < edge_thr).sum())
            if low > gap_cells:
                gap_cells = low
        out["gap_ratio"] = round(gap_cells / float(gw), 3)
        # 접촉은 "서로 다른 덩어리 2개 + 간격 0"일 때만 판정한다.
        # 왜: 두 사람이 맞닿으면 실루엣이 하나로 뭉쳐서 세그멘테이션 없이는
        # 구분할 수 없다. 폭 추정은 근경 1인과 붙은 2인을 구분하지 못해
        # 실측에서 폐기했다(오탐). 모르는 건 말하지 않는 편이 낫다.
        out["close"] = bool(len(runs) >= 2
                            and out["gap_ratio"] <= SPACING_TOUCH_RATIO)
        out["apart"] = bool(len(runs) >= 2
                            and out["gap_ratio"] >= SPACING_APART_RATIO)
        out["far"] = bool(len(runs) >= 2
                          and out["gap_ratio"] >= SPACING_FAR_RATIO)
        # 붙어 있는 경우의 보완 신호: 상단 프로파일의 "머리 개수".
        # 왜(Why): 두 사람이 맞닿으면 몸 실루엣이 하나로 뭉쳐서 간격 측정으로
        # 잡을 수 없다. 하지만 머리 둘은 별개로 세어진다 — 세그멘테이션 없이도
        # 2인 근접을 판별할 수 있는 유일한 신뢰 신호다.
        heads = 0
        try:
            # 상단 밴드는 **어깨 위**로 좁게 잡아야 한다. 넓으면 몸통까지 포함돼
            # 머리 둘이 하나로 뭉개진다(실측: 25% 이상에서 머리 분리 실패).
            top_rows = max(2, int(gh * SPACING_HEAD_BAND))
            top = mask[:top_rows, :]
            tcol = top.sum(axis=0).astype(_np.float32)
            # 머리는 피부색이다. 명암 톤만 보면 어깨선·난간도 "머리"로 잡힌다
            # (실측 오탐). MIX_GUARD의 plastic skin 방어가 이미 피부색을 근거로
            # 쓰고 있으므로 그 근거를 재사용한다. skin 은 위에서 small_rgb로
            # 계산한 값(명암 small 이 아니라 RGB 격자 기준)이다.
            if skin is not None:
                skin_top = skin[:top_rows, :]
                if skin_top.size:
                    tcol = tcol * (1.0 + 0.8 * skin_top.mean(axis=0))
            tmax = float(tcol.max())
            if tmax >= 0.5:
                truns, cur = [], None
                for i, v in enumerate(tcol):
                    if v >= max(0.5, tmax * 0.35):
                        cur = [i, i] if cur is None else [cur[0], i]
                    elif cur is not None:
                        truns.append(tuple(cur))
                        cur = None
                if cur is not None:
                    truns.append(tuple(cur))
                heads = len(truns)
        except Exception:
            heads = 0
        out["heads"] = heads
        # 머리 둘이면서 몸 실루엣이 하나로 뭉친 경우 = 서로 붙어 있는 2인
        if not out["close"] and heads >= 2 and len(runs) == 1:
            out["close"] = True
        row = mask.sum(axis=1)
        nz = _np.nonzero(row)[0]
        if nz.size:
            out["bottom_margin"] = round(float((gh - 1 - int(nz[-1])) / gh), 3)
        else:
            out["bottom_margin"] = None
        # 세로 방향: 위아래로 늘어선 피사체. 행(세로) 밀도 프로파일에
        # "이중 봉우리"가 있는지 본다 — 상단(머리·상체)과 하단(하체)이 서로
        # 떨어진 채 존재하면 세로로 늘어선 배치다.
        # 왜(Why): 누운 자세·계단·상단 부감처럼 화면 상하로 배치된 구도에서
        # 세로 간격이 공간 관계의 핵심인데, 가로만 재면 이 구도를 놓친다.
        rowc = mask.sum(axis=1).astype(_np.float32)
        rmax = float(rowc.max()) if rowc.size else 0.0
        v_two = False
        if rmax > 0.5:
            rt = max(0.5, rmax * 0.35)
            rvals = [v >= rt for v in rowc]
            # 연속 True 구간 개수
            runs_n, prev = 0, False
            for on in rvals:
                if on and not prev:
                    runs_n += 1
                prev = on
            v_two = runs_n >= 2
        out["v_separate"] = bool(v_two)
    except Exception:
        return out
    return out


def spacing_guard(measure: dict, topic: str) -> tuple:
    """(positive, negative). 픽셀 측정(거리) × topic(인원수)을 합쳐 판단.

    왜 둘을 합치는가: 픽셀은 "얼마나 떨어져 있는가"를 신뢰성 있게 읽지만
    "몇 명인가/붙었는가"를 세그멘테이션 없이 구분하지 못한다(실측 오검출 확인).
    반대로 인원수는 topic이 정확히 안다. 그래서 **거리는 픽셀이, 인원수는 topic이**
    맡고, 둘이 합의할 때만 문구를 붙인다.

    픽셀이 확실히 아는 것은 "떨어진 거리" 하나뿐이다. 그래서 부각은 "떨어져 있든
    붙어 있든 **측정된 거리를 유지하라**"로 통일한다 — 모델이 참조의 공간 관계를
    깨뜨리는(포옹인데 떨어지게, 떨어져 있는데 겹치게) 실패를 막는 것이 목적.
    """
    try:
        m = measure or {}
        if not m:
            return "", ""
        if not (_is_human_subject(topic or "") or _is_multi_person_request(topic or "")):
            return "", ""
        pos, neg = "", ""
        if m.get("close"):
            pos = ("spatial fidelity: keep the two subjects in contact as in "
                   "the reference — bodies touching with no gap between them")
            neg = "the subjects standing apart with empty space between them"
        elif m.get("far"):
            # 화면 양끝 수준으로 떨어진 구도. "가까이 떨어짐"과 구분한다 --
            # 실측에서 좌우 끝에 선 두 사람(간격 50%)에도 가까운 문구가 붙었다.
            pos = ("spatial fidelity: the two subjects stay far apart at the "
                   "opposite sides of the frame as in the reference, the wide "
                   "empty space between them preserved")
            neg = ("the subjects pulled close together, the wide empty space "
                   "between them filled in")
        elif m.get("apart"):
            pos = ("spatial fidelity: keep the same separation between the "
                   "subjects as the reference — the space between them stays "
                   "the same size, they do not crowd together")
            neg = ("the subjects pushed together into overlapping silhouettes, "
                   "merged into one mass")
        if m.get("v_separate"):
            # 세로로 늘어선 구도 — 가로 거리만 재면 이 배치를 놓친다.
            pos = (pos + ", " if pos else "") + (
                "spatial fidelity: keep the same vertical arrangement as the "
                "reference, one subject higher in the frame than the other, "
                "do not align them on the same level")
        if m.get("bottom_margin") is not None and m.get("bottom_margin", 0) > 0.03:
            # 접지 여부는 한 장에서 확정할 수 없다(바닥이 보이는 게 정상이라
            # 전경이 최하단에 닿는지만 보면 근거가 없다). 대신 **측정 가능한
            # 사실**인 "피사체 아래 남은 여백(=보이는 바닥 비율)"만 유지시킨다.
            # 스케일 가드(인물-사물 비율)와 같은 축의 사실이라 서로 보강된다.
            pos = (pos + ", " if pos else "") + (
                "spatial fidelity: keep the same amount of floor and ground "
                "visible below the subject as in the reference, subject seated "
                "at the same height in the frame")
        return pos, neg
    except Exception:
        return "", ""


def spacing_log_text(measure: dict) -> str:
    """측정값 로그 문자열. 실패 시 ""."""
    try:
        m = measure or {}
        if not m:
            return ""
        bits = []
        if "gap_ratio" in m:
            bits.append(f"간격 {int(m['gap_ratio'] * 100)}%")
        if "peaks" in m:
            bits.append(f"영역 {m['peaks']}개")
        if m.get("close"):
            bits.append("근접")
        elif m.get("far"):
            bits.append("크게 떨어짐")
        elif m.get("apart"):
            bits.append("떨어짐")
        if m.get("v_separate"):
            bits.append("세로 분리")
        if m.get("heads"):
            bits.append(f"머리 {m['heads']}")
        if m.get("bottom_margin") is not None:
            bits.append(f"하단 여백 {int(m['bottom_margin'] * 100)}%")
        return " · ".join(bits)
    except Exception:
        return ""


# 9·10번 슬롯 전용 "외양 참조" 가드 (사용자 전용 기능 — 2026-09-27).
# (Why: 9·10번에 신체 외양 클로즈업(예: 성기 디테일)을 연결하면 LLM은 외양을
# 판단 근거로 쓰고 Qwen은 픽셀을 참고하게 되는데, 이때 클로즈업 컷 자체가
# 콜라주/패널로 삽입되는 오동작을 막아야 한다. "anatomical" 어휘는 학습
# 편향상 의학 도판 풍으로 그려지는 실측 사례가 있어 positive에는 쓰지 않는다.
# 2026-09-27 후속: 9·10번에 어떤 부위(가슴/성기)가 어떤 순서로 와도
# 참조 픽셀을 실제 묘사 부위에 매칭하도록 "부위 식별 + 교차 금지" 문구로 강화.)
APPEARANCE_REF_POSITIVE = (
    "Appearance reference: the slot 9/10 image(s) are body appearance "
    "references — each one depicts a specific body region (such as chest or "
    "breasts, or intimate region). Visually match each reference to the body "
    "region it actually depicts and apply its depicted appearance naturally to "
    "that exact region only, with realistic soft skin texture and natural "
    "shape. Never swap, merge, or misplace the regions — do not copy one "
    "reference's appearance onto a different body region. Do not include the "
    "reference crops themselves in the image, no panel, no collage, no split view."
)
APPEARANCE_REF_NEGATIVE = "collage, inset panel, split view, split screen, duplicated crop, clumped hair patches, sticker-like body hair, floating hair decals"

# 외양 참조(9·10번) 실행의 체모 실사감 문구. (Why: 음모 등 체모가 뭉치거나
# 피부 위에 스티커처럼 떠 있는 실측 사례 — 모근에서 자라는 입체 디테일,
# 굵기 불균일, 신체 곡선을 따라 눕는 물리감을 명시해야 자연스럽다.
# appearance_ref 실행에만 붙는 사용자 전용 기능이라 README 비공개.)
APPEARANCE_HAIR_REALISM_POSITIVE = (
    "natural realistic body hair detail: individual strands growing from the "
    "skin with visible follicle roots, tapering tips, slightly irregular "
    "thickness, hairs lying and bending along the body's curves, layered "
    "strands creating natural depth, soft density gradient — no clumped "
    "patches, no sticker-like or floating hair"
)


# 부위별 디테일 뭉개짐 방어. (Why: 실측에서 참조 이미지를 쓰는 실행의 결과물이
# 다리·팔·어깨부터 뿌옇게 뭉개졌다. "blurry"는 초점 문제라 별개이고,
# 여기선 **부위 경계가 지워지는** 문제다 — 살갗/원단 경계, 무릎·팔꿈치 관절 선,
# 손가락 마디 같은 구조 경계가 사라져 보솜처럼 뭉개진다. denoise가 높은
# 실행일수록 심해진다.)
DETAIL_DEFINITION_POSITIVE = (
    "anatomical edge definition: every body part keeps a clear readable "
    "boundary against what surrounds it — legs separate from each other and "
    "from the background, arms separate from the torso, shoulders keep a "
    "defined line, fabric keeps its weave and seams, skin keeps natural "
    "texture, hands keep distinct fingers, knees and elbows keep a visible "
    "joint line"
)
DETAIL_DEFINITION_NEGATIVE = (
    "melted body boundaries, legs blending into each other, arm merging into "
    "torso, smeared fabric, waxy skin, featureless limbs, indistinct fingers, "
    "boots melting into the foot, foot blending into the floor, "
    "soft shapeless body parts, plastic doll skin, blanket-like skin folds"
)

# 인물 신체 발란스 가드. (Why: 전신·신체 중심 장면에서 팔/다리 길이 불균형,
# 머리-몸 비율 붕괴, 부위별 스케일 불일치가 자주 발생. 인물 주제면 참조 이미지
# 유무와 무관하게 항상 첨부한다 — 비율 문구는 장면 훼손이 없어 상시 붙여도 안전.)
BODY_BALANCE_POSITIVE = (
    "body balance: natural human proportions, head-to-body ratio consistent "
    "with a real person, arms and legs of even realistic length, natural "
    "shoulder-hip line, relaxed upright posture, all body parts at one "
    "consistent scale"
)
BODY_BALANCE_NEGATIVE = ("disproportionate limbs, elongated arms, shortened legs, "
                         "oversized head, twisted torso, body parts of different scale")

# 캐릭터 시트 참조 가드. (Why: 참조 이미지가 캐릭터 시트(여러 각도 동일 인물
# 나열)일 때 시트 레이아웃 자체(격자·라벨·멀티패널)가 출력으로 복제되는 실측
# 사례 — 시트는 신원 소스로만 쓰고 출력은 요청된 카메라 구도 한 컷이어야 한다.)
CHARACTER_SHEET_TOPICS = ("캐릭터 시트", "캐릭터시트", "캐릭터시", "캐릭터 시",
                          "character sheet", "charactersheet", "character_sheet",
                          "턴어라운드", "turnaround", "삼면도", "다면도",
                          "다각도", "정면후면", "전신 다각도",
                          "multiple angles of the same", "reference sheet",
                          "model sheet", "모델 시트", "시트 참고")
# **다인물 시트**(얼굴·옷이 전부 다른 여러 캐릭터가 한 장에)는 위 시트와
# 의미가 반대다 — "전부 같은 한 사람"으로 말하면 틀린 지시가 된다. 두 종류를
# 먼저 나눠 판정한다.
MULTI_PERSON_SHEET_TOPICS = (
    "여러 캐릭터", "여러캐릭터", "인물 시트", "인물시트", "다캐릭터", "다 캐릭터",
    "라인업", "lineup", "cast sheet", "ensemble sheet", "오디션 시트",
    "여러 인물", "복수 캐릭터", "여명", "다인물 시트",
)
CHARACTER_SHEET_NEGATIVE = ("grid layout, contact sheet, sprite sheet, "
                            "multi-panel layout, annotated sheet, "
                            "character sheet layout in output, "
                            # 2026-09-29 실측: 시트 용어만 금지하면 레이아웃이
                            # 그대로 렌더링됐다(실제 생성 확인). negative 는
                            # "무엇이 아닌지"만 말하므로 **결과 형태**로
                            # 지목해야 한다 — "the same person repeated several
                            # times" 가 실제로 렌더링되는 것을 막는다.
                            "the same person repeated several times in one "
                            "image, several copies of the same figure, "
                            "figure shown from multiple angles side by side, "
                            "front view and back view both visible at once, "
                            "full body and close-up shown together, "
                            "reference sheet reproduced in output")
# 동일인 다중 뷰를 **여러 사람으로 세는** 실패. 왜(Why): 사용자가 캐릭터 시트를
# 쓰는 목적은 신원 일관성이다. 기존 negative는 레이아웃(격자·패널)만 막았고
# "뷰가 여러 명으로 복제된다"는 방향은 duo/멀티 인물 가드에만 있었는데, 그
# 가드는 시트 참조 실행에서 plan["persons"]가 비어 걸리지 않는다.
CHARACTER_SHEET_PEOPLE_NEGATIVE = (
    "the reference sheet's views counted as separate people, multiple people "
    "from one reference, a second person, extra person, cloned faces, "
    "identical duplicated faces, mirrored duplicates, crowd, group of people, "
    "background people, a lineup of different characters"
)
# 시트 뷰 구성 — 실사용 표준 구조(정면·후면·상부 얼굴·좌우 측면)를 명시한다.
CHARACTER_SHEET_VIEWS = (
    "front full-body view, back full-body view, close-up head front, "
    "close-up head back, left profile close-up, right profile close-up"
)


def _is_multi_person_sheet(text: str) -> bool:
    """여러 캐릭터가 한 장에 있는 시트인가. 동일인 다중 뷰 시트와 구분한다."""
    t = (text or "").lower()
    return any(k in t for k in MULTI_PERSON_SHEET_TOPICS)


def _is_character_sheet_request(text: str) -> bool:
    """캐릭터 시트 참조 의도가 명시됐는지 판별한다."""
    t = (text or "").lower()
    return any(keyword in t for keyword in CHARACTER_SHEET_TOPICS)


# ---------------------------------------------------------------------------
# 참조 이미지에서 캐릭터 시트를 **픽셀로** 판별 (2026-09-28)
#
# 왜(Why) 이게 필요한가: 시트 가드는 topic 텍스트("캐릭터 시트" 등)로만
# 발동했다. 사용자가 topic 을 비워 두면(테스트 조건을 러프하게 두는 습관)
# **6뷰 시트를 연결해 놓고도 아무 지시도 안 나간다** → 실측으로 시트가 1명인데
# 결과에 2명이 나왔다. 정보는 이미 **픽셀에** 있는데 쓰지 않았다.
#
# 판별 원리(Consistency Keeper 의 proven 알고리즘과 동일 — 2026-09-28 검증):
#   1) 각 열의 표준편차 프로파일 → "평탄하지 않은 열"이 콘텐츠
#   2) 콘텐츠가 **3개 이상** 연속 구간으로 반복 = 패널
#   3) 패널 폭이 고르고(폭비 ≤1.6) 간격이 고르면(간격비 ≥0.6) 시트로 인정
#
# 오탐이 누락보다 위험한 이유: 시트로 잘못 보면 6개 뷰가 6명 신원으로
# 평균나 **신원 일관성이 망가지며**, 그건 조용히 일어난다.
# 그래서 이렇게 빡빡한 기준을 쓴다(실사용 사진 7장으로 보정: 폭비 1.55~6.48
# 인 사진은 전부 탈락, 합성 시트는 1.00).
# ---------------------------------------------------------------------------
# 참조 이미지에서 캐릭터 시트를 **픽셀로** 판별 (2026-09-28)
#
# 왜(Why) 텍스트만 믿으면 안 된다(실측): topic 이 비어 있으면 시트 가드의
# 텍스트 조건이 거짓이 되어 **아예 발동하지 않는다** → 1인 6뷰 시트가 결과에서
# **2명**으로 복제됐다. 정보는 이미 픽셀에 있었다.
#
# 판별 기준 = 구조(격자) + 내용(같은 피사체 반복) 두 가지의 교집합:
#   1) 프로파일 표준편차로 콘텐츠 연속 구간을 찾는다 (패널 사이 빈 공간은
#      STD≈0, 실루엣이 있는 열/행은 값이 크다)
#   2) 간격 균일성(중심 간격의 min/max) >= 0.45 — 격자 구조 확인
#   3) 패널끼리 나눈 셀의 평균 유사도 >= 0.20 — **같은 사람의 반복** 확인
#
# 왜 폭 균일성(wreg)을 버렸나: 실제 사용자 시트(10896x6800, 전신 2 + 얼굴 4)를
# 재측정하니 wreg=2.50 으로 탈락했다. 전신 뷰와 얼굴 클로즈업은 **구조적으로
# 폭이 다르다** — 폭이 고른다는 건 시트의 조건이 아니라 우연일 뿐이다. 그
# 조건을 버리고 "같은 피사체가 반복된다"는 시트의 진짜 정의를 직접 썼다.
#
# 한계를 정직하게: 실제 시트 표본이 1장뿐이다. 실측치는 시트 0.41~0.42 vs
# 일반 사진 최대 0.11 로 약 4배 격차라 0.20 을 하한으로 잡았지만, 시트가
# 배경을 크게 바꾸면(예: 어두운 배경) 유사도는 내려갈 수 있다. 그래서
# 텍스트 경로(_is_character_sheet_request)와 **병존**시키고, 텍스트가 명시하면
# 픽셀 판정이 틀려도 그걸 따른다.
#
# 오탐이 누락보다 위험한 이유: 시트로 잘못 보면 여러 뷰를 여러 신원으로
# 평균내며 **신원 일관성이 조용히** 망가지기 때문이다.
#
# 2026-09-29 실측 교정 (ComfyUI 실제 실행): stride 샘플링(a[::step, ::step])
# 은 원본 해상도에 따라 **다른 픽셀을 본다**. 세로로 긴 사진(4296x7696)은
# 행 경계가 1~2px 어긋나 "1열짜리 거대한 셀"이 만들어졌고, 그 결과
# 포즈 사진이 sim=0.209 로 **시트로 오인**됐다(PIL resize 경로는 0.023).
# 같은 파일인데 경로에 따라 다른 판정이 나오는 상태였다. 그래서 프로파일은
# 고정 격자 블록 평균(linspace 인덱스)으로 바꾼다 — 해상도 무관하게 같은
# 결과를 낸다.
# ---------------------------------------------------------------------------
# 최소 패널 밴드 수. 왜 4인가 (2026-10-01 실측): 3 은 **세로 문틀 2개 +
# 사람** 같은 등간격 세로 3구조를 시트로 잡았다. 실측 표:
#   케릭터 시트1 n=4 sim=0.422 / 시트2 n=4 sim=0.587 / 시트3 n=4 sim=0.263
#   인물 서있는 자세1(문 앞 한 장) n=3 sim=0.243  ← 오탐
# sim 은 0.24 vs 0.26 으로 겹쳐서 올릴 수 없다(시트3 이 깨진다). n 만 확실히
# 갈리므로 여기서 선을 긋는다.
_SHEET_MIN_PANELS = 4
# 간격 균일성 하한 0.45: 사용자 실제 시트는 0.95, 실사용 사진은 0.38~0.71.
_SHEET_MIN_SPACING_RATIO = 0.45
# 셀 평균 유사도 하한 0.20: 실제 시트 0.414, 실사용 사진 0.109 이하.
_SHEET_MIN_CELL_SIMILARITY = 0.20
# 프로파일의 크기. 512면 충분하고 더 볼 필요 없다(비용 대비 정보량 낮음).
_SHEET_PROFILE_W = 512
# 셀 서명의 격자 크기. 8x8 은 색/명도 구조를 남기면서 노이즈는 줄인다.
_SHEET_SIG_GRID = 8


def _column_profile(arr, width: int = _SHEET_PROFILE_W):
    """RGB 배열 → 열별 표준편차 프로파일. 실패 시 None.

    왜(Why) 표준편차인가: 패널 **사이 빈 공간**은 균일해서 STD≈0 이고,
    실루엣이 있는 패널 열은 값이 크다. 그래서 "평탄하지 않은 연속 구간"이
    곧 패널이다. 에지맵(16x16)이 아니라 **전 해상도**를 본다 — 16x16 으로
    줄이면 패널 하나가 2~3칸에 불과해 세 개만 잡히는 문제가 실제로 발생했다.
    """
    try:
        import numpy as _np
        if arr is None or getattr(arr, "ndim", 0) != 3:
            return None
        a = _np.asarray(arr, dtype=_np.float32)
        if a.shape[0] < 8 or a.shape[1] < 8:
            return None
        w = a.shape[1]
        if w > width:                       # 축소해 비용을 제한한다
            step = max(1, w // width)
            a = a[:, ::step, :]
        lum = (a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114)
        prof = lum.std(axis=0)
        if prof.size < 8:
            return None
        return prof.astype(_np.float32)
    except Exception as _e:
        # 왜(Why) 여기서 말하나 (2026-10-01): 이 함수가 None 을 주면 `_looks_like_sheet`
        # 가 `{"sheet": False}` 로 조용히 물러난다. numpy 미설치·입력 타입 불일치가
        # **환경 문제** 인데 **판정 결과(시트 아님)** 로 보이므로, 원인 찾기가 이틀
        # 걸렸다. 원인은 로그로만 알 수 있다.
        _note_once("camera.column_profile",
                   "[Camera Director] 열 프로파일 계산 실패 — 시트를 "
                   "판정하지 못했습니다(환경 문제일 수 있음): "
                   f"{type(_e).__name__}: {str(_e)[:80]}")
        return None


def _row_profile(arr, height: int = _SHEET_PROFILE_W):
    """행(=세로) 기준 프로파일. 세로로 쌓인 시트를 놓치지 않기 위함."""
    try:
        import numpy as _np
        if arr is None or getattr(arr, "ndim", 0) != 3:
            return None
        a = _np.asarray(arr, dtype=_np.float32)
        if a.shape[0] < 8 or a.shape[1] < 8:
            return None
        h = a.shape[0]
        if h > height:
            step = max(1, h // height)
            a = a[::step, :, :]
        lum = (a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114)
        prof = lum.std(axis=1)
        if prof.size < 8:
            return None
        return prof.astype(_np.float32)
    except Exception as _e:
        _note_once("camera.row_profile",
                   "[Camera Director] 행 프로파일 계산 실패 — 세로 시트를 "
                   "판정하지 못했습니다(환경 문제일 수 있음): "
                   f"{type(_e).__name__}: {str(_e)[:80]}")
        return None


def _panels_from_profile(prof, min_w_ratio: float = 0.04):
    """프로파일 → 콘텐츠 연속 구간 [(x0, x1), ...]."""
    try:
        import numpy as _np
        p = _np.asarray(prof, dtype=_np.float32)
        if p.ndim != 1 or p.size < 8:
            return []
        peak = float(p.max())
        if peak <= 1e-6:
            return []                      # 전부 평탄 → 시트 아님
        on = p >= peak * 0.30
        min_w = max(1, int(round(p.size * min_w_ratio)))
        panels = []
        start = None
        for i, v in enumerate(on):
            if v and start is None:
                start = i
            elif not v and start is not None:
                if i - start >= min_w:
                    panels.append((start, i))
                start = None
        if start is not None and len(on) - start >= min_w:
            panels.append((start, len(on)))
        return panels
    except Exception:
        return []


def _axis_spacing_ratio(bands) -> float:
    """밴드 중심 간격의 균일성(min/max). 격자면 1.0 에 가깝다."""
    if len(bands) < 2:
        return 0.0
    try:
        centers = [(x0 + x1) / 2.0 for x0, x1 in bands]
        gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
        if not gaps or max(gaps) <= 0:
            return 0.0
        return min(gaps) / max(gaps)
    except Exception:
        return 0.0


def _best_axis(arr):
    """가로/세로 중 격자 구조가 더 뚜렷한 축의 밴드와 간격 균일성."""
    best = ([], 0.0)
    for prof in (_column_profile(arr), _row_profile(arr)):
        if prof is None:
            continue
        bands = _panels_from_profile(prof)
        if len(bands) < _SHEET_MIN_PANELS:
            continue
        g = _axis_spacing_ratio(bands)
        if g > best[1]:
            best = (bands, g)
    return best


def _sheet_cell_boxes(arr):
    """패널 셀 = 열 밴드 × 행 밴드. 한 축만 있으면 그 축을 쓴다."""
    # 주의: `prof or []` 로 쓰면 numpy 배열의 진릿값 평가가 ValueError 를
    # 던진다. except 에 삼켜져 **조용히** 0 이 되어 시트를 놓친다(실측).
    cp = _column_profile(arr)
    rp = _row_profile(arr)
    cols = _panels_from_profile(cp) if cp is not None else []
    rows = _panels_from_profile(rp) if rp is not None else []
    if len(cols) >= 2 and len(rows) >= 2:
        return cols, rows
    if len(cols) >= 2:
        return cols, [(0, int(arr.shape[0]))]
    if len(rows) >= 2:
        return [(0, int(arr.shape[1]))], rows
    return [], []


def _cell_signature(arr, y0, y1, x0, x1, g: int = _SHEET_SIG_GRID):
    """셀 → 길이 1로 정규화된 색/명도 서명. 종횡비와 무관하게 같은 크기.

    **내용 없는 셀(평탄)은 None 을 돌려준다.** 서명이 영벡터가 되면 셀
    간 내적이 0 이 되어, 빈 셀이 하나만 섞여도 평균 유사도가 0 으로 내려가
    판별이 통째로 죽는다(합성 케이스에서 실측). 빈 셀은 피사체에 대한 정보가
    없으므로 평균에서 제외하는 게 옳다.
    """
    try:
        import numpy as _np
        cell = arr[y0:y1, x0:x1]
        if cell.size == 0 or cell.shape[0] < 1 or cell.shape[1] < 1:
            return None
        h, w = cell.shape[0], cell.shape[1]
        ys = _np.linspace(0, h - 1, g).astype(int)
        xs = _np.linspace(0, w - 1, g).astype(int)
        s = cell[_np.ix_(ys, xs)].reshape(-1, 3).astype(_np.float32)
        s = s - s.mean(axis=0, keepdims=True)      # 전역 밝기 차 제거
        n = float(_np.linalg.norm(s))
        return s / n if n > 1e-6 else None
    except Exception:
        return None


def _cell_similarity(arr) -> float:
    """셀 간 평균 유사도(0~1). 같은 인물 반복이면 크고, 다른 장면이면 0 근처."""
    try:
        import numpy as _np
        cols, rows = _sheet_cell_boxes(arr)
        if not cols or not rows:
            return 0.0
        sigs = []
        for (y0, y1) in rows:
            for (x0, x1) in cols:
                s = _cell_signature(arr, y0, y1, x0, x1)
                if s is not None:
                    sigs.append(s)
        if len(sigs) < 3:
            return 0.0
        dots = [(sigs[i] * sigs[j]).sum()
                for i in range(len(sigs)) for j in range(i + 1, len(sigs))]
        return float(_np.mean(dots))
    except Exception as _e:
        # 왜(Why) 예외만 남기고 0.0 은 그대로인가 (2026-10-01): 0.0 은 **정상적인
        # 판정 결과** 이기도 하다(다른 장면이면 실제로 0 근처다). 그래서 "0.0 이라
        # 판정과 실패를 구분 못 한다" 는 문제지만, 값을 바꾸면 임계값 비교가
        # 깨진다. 해법은 로그다 — 실패는 예외 종류로 드러낸다.
        _note_once("camera.cell_similarity",
                   "[Camera Director] 셀 유사도 계산 실패 — 시트 판정이 "
                   "0 근처로 내려가 '시트 아님' 이 됩니다(환경 문제일 수 있음): "
                   f"{type(_e).__name__}: {str(_e)[:80]}")
        return 0.0


def _sheet_normalize(arr):
    """분석용 배열로 축소(최대 변 512). **좌표 공간을 통일하기 위해 필수.**

    왜(Why) 필수인가(2026-09-28 실측): 프로파일은 512 기준으로 좌표를 내는데
    그 좌표를 원본 배열로 자르면 **엉뚱한 곳**을 읽는다. 1536 폭 배열에서
    밴드가 (67,100) 이면 실제 실루엣은 (204,296) 이었고, 잘라낸 셀은 전부
    흰 배경이었다 → 셀 유사도가 0 이 되어 판별이 조용히 죽는다.
    이제 _looks_like_sheet 는 자기 입력의 크기와 무관하게 동작한다.
    """
    try:
        import numpy as _np
        if arr is None or getattr(arr, "ndim", 0) != 3:
            return None
        a = _np.asarray(arr, dtype=_np.float32)
        h, w = a.shape[0], a.shape[1]
        if h < 8 or w < 8:
            return None
        if max(h, w) <= _SHEET_PROFILE_W:
            return a
        # **정수 스트라이드를 쓰면 안 된다 (2026-10-01 실측).**
        # 왜(Why): `max(h, w) // _SHEET_PROFILE_W` 는 정수 나눗셈이라 정규화
        # 크기가 입력 크기에 따라 1.5배까지 흔들렸다 —
        #   1019x1544 -> step 3 -> 514x339   (시트로 오인)
        #    995x1508 -> step 2 -> 754x497   (정상으로 판정)
        # 같은 사진이 1024x1024 로 늘리기만 해도 '시트' 로 뒤집혔다. 프로파일
        # 분석이 정규화 배열 크기에 의존하므로 판정까지 뒤집혔다. 그래서
        # **최대 변을 정확히 _SHEET_PROFILE_W 로 맞춘다**: 정규화 크기가
        # 종횡비만의 함수가 되고, 같은 사진이면 크기와 무관하게 같은 판정이 나온다.
        _ratio = max(h, w) / float(_SHEET_PROFILE_W)
        _nh = max(1, int(h / _ratio))
        _nw = max(1, int(w / _ratio))
        if (_nh, _nw) != (h, w):
            # 실수 비율 근삿값 인덱스로 줄인다. 컴피 의존 없이 항상 동작한다.
            _yy = _np.clip((_np.arange(_nh) * (h / float(_nh))).astype(int), 0, h - 1)
            _xx = _np.clip((_np.arange(_nw) * (w / float(_nw))).astype(int), 0, w - 1)
            a = a[_yy][:, _xx, :]
        return a
    except Exception as _e:
        # 왜(Why) 여기서 말하나 (2026-10-01): 이 함수가 None 을 주면
        # `_looks_like_sheet` 는 즉시 `{"sheet": False}` 를 돌려준다. 즉 **환경
        # 문제가 판정 결과처럼 보인다.** 시트인지 아닌지를 결정하는 첫 관문이라
        # 조용히 넘어가면 원인 없이 "시트 아님" 이 굳는다.
        _note_once("camera.sheet_normalize",
                   "[Camera Director] 시트 정규화 실패 — 시트 여부를 판정하지 "
                   "못했습니다(환경 문제일 수 있음): "
                   f"{type(_e).__name__}: {str(_e)[:80]}")
        return None


def _looks_like_sheet(arr) -> dict:
    """패널 격자 + 내용 유사도로 캐릭터 시트인지 판정.

    반환: {"sheet", "n", "greg", "sim"} — n 은 판별 근거가 된 축의 밴드 수.
    """
    out = {"sheet": False, "n": 0, "greg": 0.0, "sim": 0.0}
    try:
        a = _sheet_normalize(arr)
        if a is None:
            # `_sheet_normalize` 가 이미 사유를 남겼다. 여기서 또 남기지 않는다.
            return out
        bands, greg = _best_axis(a)
        out["n"] = len(bands)
        if len(bands) < _SHEET_MIN_PANELS:
            # 왜(Why) 이 탈락을 말하나 (2026-10-01 실측): 이 줄이 **조용한
            # 실패의 중심**이었다. "시트가 아닌데 기준 latent 를 뺐다" 는 결론만
            # 남고, 그 원인이 패널 개수 부족인지 간격 불일치인지 아무도 알 수 없었다.
            # 그래서 탈락 조건을 **그대로 문장으로** 남긴다. 판단은 하지 않는다 —
            # sim 이 낮아서인지 n 이 부족한지만 사용자가 읽고 결정한다.
            _note_once("camera.sheet_bands_%d" % len(bands),
                       f"[Camera Director] 시트로 판정하지 않음 — 패널 {len(bands)}개"
                       f"(최소 {_SHEET_MIN_PANELS}개 필요). 이미지 안에 반복 뷰가 "
                       "보이지 않습니다.")
            return out
        sim = _cell_similarity(a)
        out["greg"] = round(greg, 2)
        out["sim"] = round(sim, 3)
        out["sheet"] = (greg >= _SHEET_MIN_SPACING_RATIO
                        and sim >= _SHEET_MIN_CELL_SIMILARITY)
        if not out["sheet"]:
            # 여기서도 **어느 선에 걸렸는지**를 말한다. 둘 다 0 에 가까우면
            # "패널은 잡혔지만 내용이 서로 다르다" 즉 시트가 아니다.
            # 왜(Why) 키가 고정인가: 실수(float)로 키를 만들면 서로 다른 값마다
            # 새 키가 생겨 "한 번만" 계약이 깨지고 _ONCE_SEEN 이 무제한으로 큰다.
            # 값은 메시지 안에 넣는다.
            _note_once("camera.sheet_reject",
                       f"[Camera Director] 시트로 판정하지 않음 — 간격 균일도 "
                       f"{round(greg, 2)}(기준 {_SHEET_MIN_SPACING_RATIO}) / "
                       f"내용 유사도 {round(sim, 3)}(기준 "
                       f"{_SHEET_MIN_CELL_SIMILARITY}). 패널은 "
                       f"{len(bands)}개 잡혔지만 시트 조건을 못 채웠습니다.")
        return out
    except Exception as _e:
        _note_once("camera.looks_like_sheet",
                   "[Camera Director] 시트 판정 실패 — 환경 문제일 수 있음: "
                   f"{type(_e).__name__}: {str(_e)[:80]}")
        return out


def sheet_like_slots(image_items) -> list:
    """연결된 참조 중 캐릭터 시트로 판별된 슬롯 번호 목록.

    왜(Why) 이미지에서 찾나: 사람이 "시트"라고 쓴다는 보장은 없다. 실제로도
    안 썼다. 픽셀에 6뷰 반복이 보이면 그게 시트다.
    """
    slots = []
    try:
        for label, img in (image_items or []):
            if img is None:
                continue
            try:
                arr = _np_as_rgb(img)
            except Exception:
                continue
            if arr is None:
                continue
            if _looks_like_sheet(arr).get("sheet"):
                slots.append(str(label))
    except Exception:
        pass
    return slots


def _np_as_rgb(img):
    """PIL 이미지 → numpy(H,W,3) float32 0~1. 실패 시 None."""
    try:
        import numpy as _np
        if img is None:
            return None
        if hasattr(img, "mode") and hasattr(img, "convert"):
            img = img.convert("RGB")
            w, h = img.size
            if w < 8 or h < 8:
                return None
            step = max(1, max(w, h) // 512)
            img = img.resize((max(1, w // step), max(1, h // step)))
            a = _np.asarray(img, dtype=_np.float32) / 255.0
        else:
            a = _np.asarray(img, dtype=_np.float32)
            if a.ndim == 2:
                a = a[..., None].repeat(3, axis=2)
            if a.ndim == 4:
                a = a[0]
            if a.ndim != 3:
                return None
            if a.max() > 1.5:
                a = a / 255.0
        if a.ndim != 3 or a.shape[2] < 3:
            return None
        a = _np.clip(a[..., :3], 0.0, 1.0)
        # **분석 전에 축소한다 (ComfyUI 텐서 경로 실측 2026-09-29).**
        # 왜(Why) 필수인가: ComfyUI LoadImage 는 원본 해상도(BHWC) 텐서를
        # 넘긴다. 10896x6800 을 그대로 프로파일/서명 분석하면 픽셀 경로와
        # **다른 판정**이 나왔다 — 같은 파일인데 PIL 경로는 sim=0.414(시트),
        # 텐서 경로는 0.422(시트)로 시트는 같았지만, 포즈 이미지(4296x7696)는
        # PIL sim=0.023(아님) vs 텐서 sim=0.209(**시트로 오인**) 로 갈렸다.
        # 원인은 해상도 의존적인 세부 판정(패널 경계·셀 서명 샘플링)이
        # 원본/축소본에서 어긋나는 것. PIL 경로가 이미 512 기준으로
        # 축소하므로, 여기서 **항상 같은 해상도로 맞춘다** → 두 경로의 판정이
        # 일치하고 입력 크기에 무관해진다. 분석 전용이므로 정보 손실은 무관.
        # 이 함수는 변환만 한다. **축소는 하지 않는다** — 아래 주석.
        #
        # 왜(Why) 여기서 축소하지 않는가(2026-09-29 실측): 이 축소를 남기면
        # **가로로 긴 배열(512x1536 등)이 171x171 로 뭉개졌다**. 위 PIL
        # 경로의 resize() 는 종횡비를 보존하는데(512x1536 유지), stride
        # 는 두 축을 같은 step 으로 잘라 정사각형에 가깝게 만들기 때문이다.
        # 6등분 시트 합성 이미지(1536x512)가 통째로 판별 실패했고, 더 나쁘게는
        # PIL 경로와 판정이 갈렸다. 축소는 전부 _sheet_normalize() 가
        # **종횡비 보존 방식**으로 담당한다(시그니처가 `_np_as_rgb` 와 같다).
        return a
    except Exception:
        return None


def character_sheet_guard(image_count: int, topic: str, image_labels=None, pixel_sheet_slots=None) -> str:
    """캐릭터 시트 참조 가드 — 시트는 신원 소스, 출력은 카메라 구도 한 컷.

    왜(Why): 사용자가 시트를 연결하는 목적은 **신원 일관성**이다. 실사용 표준
    구조는 정면·후면 전신 + 상부 얼굴 정면·후면 + 좌우 측면(한 사람)인데,
    이 뷰들을 "여러 사람"으로 세면 신원 의도와 정반대가 된다. 실측으로
    시트 참조 실행에서 뷰가 별개 인물로 복제되는 문제가 있었다.
    """
    # 다인물 시트 어휘("인물 시트"·"라인업" 등)는 CHARACTER_SHEET_TOPICS에
    # 없어서 여기서 걸러지면 아래 분기에 도달하지 못한다 → 둘 다 시트로 인정.
    # 픽셀 판별 결과(슬롯 목록)를 받는다. topic 에 "시트" 라고 안 써도
    # 6뷰 반복 구조가 보이면 발동한다 (2026-09-28 실측: topic 이 비어
    
    # 있어 1인 시트가 결과에 2명으로 복제됨). 정보는 이미 픽셀에 있다.
    px_slots = [str(s) for s in (pixel_sheet_slots or [])]
    if image_count <= 0 or not (_is_character_sheet_request(topic)
                                or _is_multi_person_sheet(topic)
                                or px_slots):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    first = labels[0] if labels else "1"
    # **시트로 지목할 슬롯.** 픽셀 판별이 찾아냈으면 그 슬롯(들)을 쓴다.
    # 왜(Why) 실측(2026-09-29 ComfyUI 실행): 시트가 연결된 3번인데 프롬프트가
    # "reference image 1 is a character sheet" 라고 했다. first(=labels[0])를
    # 무조건 썼기 때문이고, 1번은 신원 사진이라 **시트가 아닌데 시트라 지목**
    # 됐다 — 정반대 지시라 모델이 엉뚱하게 반응한다. 시트 슬롯이 있으면
    # 그걸 지목하고, 없을 때만 first 로 물러선다.
    if px_slots:
        sheet_slot = ", ".join(px_slots)
        sheet_ref = f"reference image(s) {sheet_slot}"
    else:
        sheet_slot = first
        sheet_ref = f"reference image {first}"
    # 다인물 시트(라인업·오디션)는 "전부 한 사람"이 틀린 지시가 된다.
    if _is_multi_person_sheet(topic):
        return (f"multi-person reference sheet: {sheet_ref} is a "
                "sheet showing SEVERAL DIFFERENT characters side by side, each "
                "one a distinct individual with their own face, hair and "
                "outfit. Use the sheet for per-character identity "
                "consistency. Do not merge the characters into one person, and "
                "do not copy the sheet layout: no grid, no borders, no labels, "
                "no multi-panel arrangement; unless multiple characters are "
                "explicitly requested, render one single scene view.")
    return (f"character sheet reference: {sheet_ref} is a character "
            "sheet of ONE SINGLE person shown from several angles ("
            f"{CHARACTER_SHEET_VIEWS}). Every view is the same one person — "
            "identical face, identical hairstyle, identical body type, "
            "identical outfit, identical height and build. The repeated views "
            "are reference angles of one identity, NOT separate people. "
            # 2026-09-29 실측 교정: 여기가 "한 컷을 그려라" 고치지 않으면
            # **시트가 그대로 렌더링**된다(실제 생성으로 확인). 위 문구는
            # 시트를 *설명*하고 "one single scene view" 를 *권하기만* 한다.
            # 시트 이미지가 지배적이라 모델이 그 사이에서 6뷰 배치를 최선으로
            # 해석한다. negative 로 막는 것도 실패했다(시트 용어 금지만으로는
            # 통과). 그래서 **무엇을 그릴지**를 positive 로 직접 박는다.
            "Use the sheet ONLY to copy this person's identity. The output is "
            "ONE photograph: a single continuous scene showing that one "
            "person once, shot with the camera described above. The reference "
            "sheet's multi-view arrangement must NOT appear in the output. "
            "Render a single scene view, never a crowd, never a second "
            "person, never duplicated or mirrored faces, never a lineup of "
            "different characters.")


def build_negative(cam: dict, extra: str = "", llm_extra: str = "", topic: str = "",
                   hint_defense: bool = False, mix_guard: bool = False,
                   appearance_ref: bool = False, body_balance: bool = False,
                   character_sheet: bool = False, image_count: int = 0,
                   image_labels=None, pose_ref: bool = False,
                   physics_neg: str = "", detail_def: bool = False,
                   furniture: bool = False, remove_item: bool = False,
                   anatomy_count: bool = False) -> str:
    # 힌트·믹스·외양·발란스 방어는 base 경로 전용이라 조립기가 아니라
    # 여기서 덧붙인다(중복이 아니라 경로별 전용).
    tail = []
    if hint_defense:
        tail.append(HINT_DEFENSE_NEGATIVE)
    if mix_guard:
        tail.append(MIX_GUARD_NEGATIVE)
    if appearance_ref:
        tail.append(APPEARANCE_REF_NEGATIVE)
    if body_balance:
        tail.append(BODY_BALANCE_NEGATIVE)
    return _assemble_negative(
        cam, topic, image_count, image_labels,
        {"anatomy_count": anatomy_count, "character_sheet": character_sheet,
         "detail_def": detail_def, "furniture": furniture,
         "remove_item": remove_item},
        "color tint", extras=tuple(tail) + (llm_extra, extra),
        physics_neg=physics_neg, pose_ref=pose_ref)


# ---------------------------------------------------------------------------
# LLM tier — 시스템 프롬프트 (허용 라벨을 그대로 전달해 JSON 규격을 강제)
# ---------------------------------------------------------------------------

def llm_system() -> str:
    allowed = {k: list(v) for k, v in _TABLES.items()}
    allowed.setdefault("speed", list(SPEED))
    return (
        "You are a cinematography prompt engineer for image/video generation models.\n"
        "Return ONLY a JSON object, no prose, no markdown:\n"
        '{"scene": "<English scene description, 1-3 sensory sentences, NO camera terms>",'
        ' "camera": {"shot": "<label>", "lens": "<label>", "angle": "<label>",'
        ' "composition": "<label>", "lighting": "<label>", "grade": "<label>",'
        ' "motion": "<label>", "motion2": "<label>", "speed": "<label>", "amplitude": "<label>"},'
        ' "negative": "<optional extra English negative phrases>",'
        ' "anatomy": "<ONLY if you see wrong limb counts in the attached image(s):'
        ' e.g. three feet, extra hand, six fingers, missing leg. Otherwise OMIT this key>"}\n'
        "Rules:\n"
        "- Every camera value MUST be copied EXACTLY from the allowed labels below "
        "(or \"자동 (auto)\" when unsure).\n"
        "- scene in English. If the topic contains Korean text that must appear "
        "inside the image (sign/caption), keep it verbatim in double quotes and add "
        "'on-image text' to negative only if the model cannot render it.\n"
        "- Keep the topic's intent; do not invent facts.\n"
        "- Outfit handling (priority order):\n"
        "  1. If the topic or user directives EXPLICITLY request an outfit change "
        "and a clothing reference image is provided: describe the garment "
        "CONCRETELY in the scene (color, material, cut, notable details) from what "
        "you actually see, and direct the replacement from that reference. The "
        "replacement MUST happen — do not fall back to the original outfit.\n"
        "  2. If NO explicit outfit change was requested (or no clothing reference): "
        "the person keeps their original outfit.\n"
        "  3. In either case NEVER leave meta placeholders like '(insert "
        "description here)' — write a real description or no replacement at all.\n"
        "- The scene prose MUST agree with the camera labels you return (shot, lens, "
        "angle, composition). Do not contradict them.\n"
        "- If the topic names a nationality/country, describe the person as a "
        "person from that country with varied individual features; never give "
        "everyone from one country the same face, never default to westernized "
        "features, and never add traditional costume unless requested. Do not "
        "mention the person's gender or ethnicity label explicitly.\n"
        f"Allowed labels: {json.dumps(allowed, ensure_ascii=False)}"
    )


def llm_user(topic: str, forced_camera: dict | None) -> str:
    msg = f"Topic: {topic.strip() or '(no topic text — judge from the attached image(s))'}"
    if forced_camera:
        msg += ("\nThese camera labels are already fixed by the chosen preset/user — "
                "copy them into camera as-is:\n"
                + json.dumps(forced_camera, ensure_ascii=False))
    return msg


# 장면 문장에 남는 "미완성 템플릿 지시문" 정리용.
# (Why: LLM이 "(a specific description of the outfit must be inserted here)"
#  같은 플레이스홀더를 채우지 않고 그대로 출력하는 실측 사례가 있었다.
#  이런 문장은 최종 프롬프트의 노이즈라 제거한다.)
_SCENE_META_PAT = re.compile(
    r"\((?:[^()]*(?:insert|inserted|describe|described|placeholder|specify|"
    r"fill in|to be added|must be|TBD)[^()]*)\)", re.I)


def clean_scene_text(text: str) -> str:
    """장면 문장에서 미완성 템플릿 지시문(괄호 플레이스홀더)을 제거한다."""
    t = (text or "").strip()
    if not t:
        return t
    cleaned = _SCENE_META_PAT.sub("", t)
    # 제거 후 남은 이중 공백/끝 단독 쉼표 정리
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip().rstrip(".,; ")
    return cleaned


def scene_camera_mismatch(scene: str, camera: dict) -> str | None:
    """장면 문장이 최종 카메라 라벨과 어긋나면 경고 문구를 반환한다 (자동 수정은 안 함).

    (Why: 장면 prose는 LLM이 쓰고 카메라 블록은 라벨 기반으로 조립되어,
     LLM이 prose에 다른 샷을 적으면 최종 프롬프트에 모순이 실린 실측 사례가
     있었다. 자동 교정은 오검출 리스크가 커서 로그로만 알린다.)
    topic_shot_label과 동일 최장 일치 기준을 쓴다 — 경고 기준과 샷 확정 기준이
    어긋나면 "경고만 뜨고 모순은 그대로"가 되기 때문이다.
    """
    other = _longest_shot_label(scene, exclude=camera.get("shot") or "")
    if other:
        final_shot = camera.get("shot")
        return (f"장면 문장에 '{other}' 표현이 있는데 최종 shot은 "
                f"'{final_shot}' — 프롬프트가 모순될 수 있음")
    return None


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
                    _hint = (_head + " (이미 {_to}초 대기 후 끊김 — "
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
_QWEN_REF_CACHE_MAX = 8
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
    """
    try:
        shape = tuple(int(d) for d in image.shape)
        h, w = shape[-3], shape[-2]
        step_h, step_w = max(1, h // 16), max(1, w // 16)
        thumb = image[0, ::step_h, ::step_w, :3] if len(shape) == 4 else image[::step_h, ::step_w, :3]
        import hashlib as _hl
        import numpy as _np
        raw = thumb.detach().cpu() if hasattr(thumb, "detach") else thumb
        return shape, _hl.sha1(_np.asarray(raw, dtype=_np.float32).tobytes()).hexdigest()[:length]
    except Exception:
        return None, None


def _thumb_sig(image) -> str:
    """이미지 내용 식별용 짧은 해시 (LLM 캐시 폴백 키용).

    왜(Why): base64 변환 실패 시 대체 키가 1번 이미지 수치에만 의존해
    2번 이후 교체가 캐시에 미반영되는 stale 문제가 있었기 때문이다.
    """
    _shape, digest = _thumb_digest(image, length=12)
    return digest if digest else f"noid:{id(image)}"


def _qwen_ref_cache_key(image, target_w, target_h, vae) -> str:
    """reference 캐시 키: 내용 썸네일 해시 + 목표 크기 + VAE 식별자."""
    shape, digest = _thumb_digest(image, length=16)
    if digest is None:
        return f"noid:{id(image)}|{target_w}x{target_h}|vae:{id(vae)}"
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
        if not image_items or not all(hasattr(image, "movedim") for _label, image in image_items):
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
            _plan_pi = resolve_guard_plan(
                _eth_text_pi, camera, last_count, last_labels, image_items,
                (image_items[0][1] if image_items else None), [],
                tier=getattr(self, "_last_tier", ""),
                llm_hint=getattr(self, "_last_llm_hint", ""))
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
        except Exception:
            reference_latent_out = None
        _release_vram()
        return (positive_out, negative_out, positive_text, image_out,
                reference_latent_out)


