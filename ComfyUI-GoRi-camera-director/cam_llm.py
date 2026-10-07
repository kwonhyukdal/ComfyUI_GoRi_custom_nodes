# -*- coding: utf-8 -*-
"""LLM tier 연동·API 키 스크럽·env 저장·장면 정제."""

from __future__ import annotations

import json
import os
import re

try:
    from . import llm_client
except ImportError:  # 스탠드얼론/테스트 실행용
    import llm_client

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
try:
    from .cam_tables import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_tables import *  # noqa: F403


__all__ = [
"PROVIDER_DEFAULT_MODELS", "_MODEL_PREFIX", "resolve_model", "_notify_llm_status", "_release_vram", "_free_gpu_for_local_llm", "_scrub_api_key_from_prompt", "_self_workflow_node", "_scrub_api_key_from_extra_pnginfo", "_api_key_left_in_png", "_SCRUB_WARNED", "_warn_scrub_unavailable", "_scrub_warn_once", "_write_env_file_key", "_write_env_file", "_valid_api_key_payload", "llm_system", "llm_user", "_SCENE_META_PAT", "clean_scene_text", "scene_camera_mismatch"
]


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
        # 왜(Why) 반환값을 그대로 돌려주나 (2026-10-05 감사): _write_env_file
        # 은 OSError(Windows 파일 잠금·권한·디스크) 시 False 를 돌려주지만
        # 예외로는 알리지 않는다. 무시하고 True 를 돌려주면 다이얼로그에
        # {"ok": true} 가 가고 로그도 "키 저장" 이라고 찍는다 — 실제로는
        # 저장이 실패해 옛 키가 디스크에 남는다.
        return _write_env_file(path, out)
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
