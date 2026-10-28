# -*- coding: utf-8 -*-
"""LLM tier 연동·API 키 스크럽·env 저장·장면 정제."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache

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
"PROVIDER_DEFAULT_MODELS", "_MODEL_PREFIX", "resolve_model", "_notify_llm_status", "_release_vram", "_free_gpu_for_local_llm", "_scrub_api_key_from_prompt", "_self_workflow_node", "_scrub_api_key_from_extra_pnginfo", "_api_key_left_in_png", "_SCRUB_WARNED", "_warn_scrub_unavailable", "_scrub_warn_once", "_write_env_file_key", "_write_env_file", "_valid_api_key_payload", "llm_system", "llm_user", "_SCENE_META_PAT", "clean_scene_text", "scene_camera_mismatch", "fix_scene_shot_clause", "detect_video_pipeline", "notify_pipeline_type"
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


# ft: = 파인튜닝 모델 접두사, o1~o4 = OpenAI 추론 계열 (2026-10-16 오딧):
# 실측에서 "o4-mini"·"ft:gpt-4o-mini:..." 가 접두사 불일치로 조용히
# gpt-4o-mini 로 교체됐다 — 사용자가 고른 모델이 무시된다.
_MODEL_PREFIX = {
    "OpenAI": ("gpt", "o1", "o2", "o3", "o4", "chatgpt", "ft:"),
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


# 비디오 파이프라인 표식 (2026-10-21). 왜(Why) 부분 일치 화이트리스트인가:
# 비디오 샘플러·I2V 노드는 계속 늘어나므로 정확한 class_type 열거는 곧 낡는다.
# 알려진 계열 이름 조각을 대소문자 무시하고 찾는다. **못 찾으면 이미지로
# 간주**한다 — 안전한 기본이다: 이미지 파이프라인에 motion 이 들어가면 왜곡을
# 유발하지만, 영상 파이프라인에서 motion 이 빠지는 것은 덜 해롭다.
# 비디오 파이프라인 표식 (class_type 부분 일치, 소문자 비교).
# 왜(Why) 낱말 경계를 보나 (2026-10-21 감사, R181): 예전에는 "ade_"·"v2v"·
# "hunyu"·"minimax" 같은 짧은 조각이 들어 있었고 `in` 이라 경계가 없었다.
# 그래서 Stable**Cade_**StageC_VAEEncode(이미지), Wa**v2V**ecModelLoader(음성),
# CLIPTextEncode**Hunyu**anDiT(이미지), MiniMax**Music**3TextEncode(음악) 이
# 영상으로 오인됐다 — 설치된 노드 4,252개 대조에서 10종이 오탐이었다.
# 오탐이면 정지 이미지에서 무빙이 제거되지 않아 왜곡이 그대로 발생한다.
_VIDEO_MARKERS = (
    "svd", "videolinearcfg", "animatediff", "wanvideo", "wanimage",
    "i2v", "hunyuanvideo", "imagetovideo", "latentvideo", "ltxv", "ltx",
    "cosmos", "mochi", "cogvideo", "opensora", "opensoraplan", "svd_img2vid",
    "kling", "hailuo", "minimaxh3", "minimaxhailuo", "minimaxtexttovideo",
    "minimaximagetovideo", "minimaxallinone", "vhs_", "videomodel",
    "video_", "sv3d", "stablevideo", "seedance", "framepack", "gimmvfi",
    "temporaldiff",
)
# 이름 **앞**에만 유효한 표식. "ade_" 를 부분 일치로 두면 "StableCascade_..." 의
# "cade_" 에 걸리고, "v2v" 는 "Wav2Vec" 한가운데에 걸린다.
_VIDEO_PREFIXES = ("ade_", "v2v_")
# 이름에 image 가 있어도 영상인 경우 (이미지→영상 변환). 이 힌트가 없는데
# 이름에 image 가 있으면 이미지 노드로 본다 (KlingImageGenerationNode,
# WanImageToImageApi, HunyuanImageEditApi 등).
_VIDEO_IMAGE_HINTS = ("imagetovideo", "image2video", "image-to-video",
                      "img2vid", "i2v")


def detect_video_pipeline(prompt) -> bool:
    """실행 프롬프트 그래프에 비디오 샘플러/모델 노드가 있으면 True.

    왜(Why) 그래프를 보나 (2026-10-21): 이 노드의 하류가 정지 이미지인지 영상인지
    에 따라 motion 지시를 넣을지 정해야 한다(정지 이미지에 'push-in camera
    movement' 는 왜곡을 유발한다). hidden 입력 `prompt` 에 실행 그래프 전체가
    들어오므로 class_type 을 훑어 판정한다.

    반환: True=비디오(또는 비디오 표식 발견), False=이미지/불명.
    불명은 False 로 둔다 — 안전 기본(위 주석 참조). 실패도 False.
    """
    try:
        if not isinstance(prompt, dict):
            return False
        for entry in prompt.values():
            if not isinstance(entry, dict):
                continue
            ct = str(entry.get("class_type", "") or "").lower()
            if not ct:
                continue
            if ("image" in ct
                    and not any(h in ct for h in _VIDEO_IMAGE_HINTS)):
                continue
            if ct.startswith(_VIDEO_PREFIXES):
                return True
            for marker in _VIDEO_MARKERS:
                if marker in ct:
                    return True
        return False
    except Exception:
        return False


def notify_pipeline_type(node_id, is_video) -> None:
    """하류 파이프라인이 이미지인지 영상인지 프론트엔드에 알린다.

    프론트는 이 신호로 motion/motion2 위젯에 '영상 전용' 표시를 한다 —
    프리셋이 채운 motion 값이 있어도 정지 이미지 파이프라인이면 실행에
    반영되지 않음을 UI 로 보여준다(백엔드/UI 어긋남 방지, 사용자 지시).

    ComfyUI 서버 밖(테스트·스탠드얼론)에서는 조용히 무시한다.
    """
    if node_id is None:
        return
    try:
        from server import PromptServer
        ps = PromptServer.instance
        if ps is not None:
            ps.send_sync("gori_pipeline_type",
                         {"node": str(node_id), "is_video": bool(is_video)})
    except Exception:
        pass



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


# 같은 tag 의 메타데이터 scrub 실패 경고를 프로세스당 1회만 (로그 스팸 방지)
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

# LLM 시스템 프롬프트 — 허용 라벨 목록과 JSON 출력 규격을 담는다
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
        ' "outfit": "<English description of the visible garments worn by the'
        ' main person in the attached person reference image (top, bottom, dress),'
        ' with concrete colour, material, pattern and cut,'
        ' e.g. \'a cream knit cardigan over a floral-print dress\'.'
        ' EXCLUDE footwear (shoes are governed separately).'
        ' OMIT this key when no person reference image is attached>",'
        ' "anatomy": "<ONLY if you see wrong limb counts in the attached image(s):'
        ' e.g. three feet, extra hand, six fingers, missing leg. Otherwise OMIT this key>",'
        ' "references": [{"slot": <image number>, "role":'
        ' "person|outfit|object|background|style|pose"}],'
        ' "sheet_kind": "<ONLY when one of the attached images is a character'
        ' sheet (one panel per view): "single" if every panel shows the SAME'
        ' person, "multi" if the panels show DIFFERENT characters. Omit this key'
        ' when no character sheet is attached>"}\n'
        "Rules:\n"
        "- Every camera value MUST be copied EXACTLY from the allowed labels below "
        "(or \"자동 (auto)\" when unsure).\n"
        "- scene in English. If the topic contains Korean text that must appear "
        "inside the image (sign/caption), keep it verbatim in double quotes and add "
        "'on-image text' to negative only if the model cannot render it.\n"
        "- Keep the topic's intent; do not invent facts.\n"
        "- Environment and props: describe ONLY the setting, floor, furniture, "
        "and objects that the topic states OR that are visibly present in a "
        "background/prop reference image. NEVER invent a floor material, "
        "furniture, room, or prop that the topic does not mention and no "
        "reference establishes. If the topic delegates the background to a "
        "reference image (e.g. \"배경: 2번 이미지\" / \"background: image 2\"), "
        "the environment comes from that reference — do NOT write a different "
        "floor, room, or furniture of your own; keep the environment "
        "unspecified so the reference governs it.\n"
        "- Landscape detail: do not add terrain or ground texture (dirt, grass, "
        "sand, cobblestone, snow) unless the topic or a reference shows it.\n"
        "- references: one entry per attached image, using the slot number printed "
        "in the user message. role = what the image is FOR: person (a human), "
        "outfit (a garment to put on a person), object (prop/product/furniture), "
        "background (environment), style (mood/palette/lighting only), pose (a "
        "body pose to copy). Leave the list empty when unsure — never guess.\n"
        "- sheet_kind: only when a character sheet is attached. Judge from the "
        "faces, hair and outfits you actually see: same person repeated = "
        "\"single\", different people = \"multi\". When unsure, omit the key — "
        "a wrong guess flips a lineup into \"everyone is one person\".\n"
        "- Outfit handling (priority order):\n"
        "  1. If the topic or user directives EXPLICITLY request an outfit change "
        "and a clothing reference image is provided: describe the garment "
        "CONCRETELY in the scene (color, material, cut, notable details) from what "
        "you actually see, and direct the replacement from that reference. The "
        "replacement MUST happen — do not fall back to the original outfit.\n"
        "  2. If NO explicit outfit change was requested (or no clothing reference): "
        "the person keeps their original outfit. When a person reference image is "
        "attached, ALSO copy that person's visible garments into outfit with "
        "concrete colour, material, pattern and cut, EXCLUDING footwear — the "
        "outfit is re-rendered from this text, so a vague description makes the "
        "garments disappear.\n"
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


# LLM 사용자 메시지 — topic 문장 + 사용자가 고정한 카메라 라벨(있으면)을 붙인다
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


def _unallowed_shot_label(scene: str, allowed_labels) -> str:
    """장면에 있으면서 allowed_labels 에 없는 샷 라벨 하나(최장 일치)를 반환.

    왜(Why) _longest_shot_label 대신 이걸 쓰나 (2026-10-21): 최종 shot 이 다중
    선택이면 고른 샷이 **여러 개**다. 단일 exclude 로 보면 나머지 고른 샷을
    "모순"으로 오판한다 — 사용자가 중근접+중경을 골랐는데 장면이 중경을 말하면
    중경을 걷어내는 버그가 있었다. allowed 는 고른 라벨 **집합**이다.

    **최장 일치 원칙을 먼저 지킨다**: 장면에서 가장 길게 일치한 라벨이
    allowed 안이면 모순 아님(빈 문자열). 한국어·영어 라벨은 서로 부분 문자열로
    겹치므로("medium close-up shot" ⊃ "close-up shot", 중근접 ⊃ 근접) 이 순서가
    없으면 고른 MCU 를 CU 로 오판한다.
    """
    allowed = {str(x) for x in (allowed_labels or []) if x}
    if not allowed:
        return ""
    longest = _longest_shot_label(scene, exclude="")
    if not longest:
        return ""
    return "" if longest in allowed else longest


def scene_camera_mismatch(scene: str, camera: dict) -> str | None:
    """장면 문장이 최종 카메라 라벨과 어긋나면 경고 문구를 반환한다.

    (Why: 장면 prose는 LLM이 쓰고 카메라 블록은 라벨 기반으로 조립되어,
     LLM이 prose에 다른 샷을 적으면 최종 프롬프트에 모순이 실린 실측 사례가
     있었다. 이 함수는 **탐지·경고**만 하고 문장은 건드리지 않는다 — 실제
     교정은 fix_scene_shot_clause 가 한다. 탐지와 교정을 나눈 이유: 로그
     문구는 그대로 두고(기존 계약), 교정 규칙만 따로 시험할 수 있다.)
    topic_shot_label과 동일 최장 일치 기준을 쓴다 — 경고 기준과 샷 확정 기준이
    어긋나면 "경고만 뜨고 모순은 그대로"가 되기 때문이다.

    다중 선택(콤마) shot 은 **고른 라벨 전부**를 정상으로 본다 (2026-10-21 수정).
    첫 값만 보면 두 번째로 고른 샷을 모순으로 오판했다.
    """
    shot_labels = split_multi(camera.get("shot"))
    other = _unallowed_shot_label(scene, shot_labels)
    if other:
        final_shot = camera.get("shot")
        return (f"장면 문장에 '{other}' 표현이 있는데 최종 shot은 "
                f"'{final_shot}' — 프롬프트가 모순될 수 있음")
    return None


@lru_cache(maxsize=256)
def _shot_phrase_re(form: str):
    """샷 표현 제거용 정규식 (패턴 캐시).

    왜(Why) 캐시하나 (2026-10-28 감사): 종전엔 이 정규식을 루프 안에서 매번
    `re.compile` 했다. 표현 수 × 반복(6) 만큼, 같은 form 을 매 실행 다시
    컴파일했다. 패턴은 form 만의 함수라 캐시하면 결과는 같고 비용만 줄어든다.
    lru_cache 는 스레드 안전하며 maxsize 를 넘으면 오래된 것부터 버린다.
    """
    return re.compile(
        r"(?:\b(?:a|an|the|in|with|using|at|from)\s+)?"
        + re.escape(form) + r"(?:\s+of)?[,]?\s*",
        re.I)


def fix_scene_shot_clause(scene: str, camera: dict) -> str:
    """장면 문장에서 최종 shot 과 어긋나는 샷 표현을 제거한다 (자동 교정).

    왜(Why) 자동 교정인가 (2026-10-21 사용자 지시): scene_camera_mismatch 가
    경고만 남기면 모순이 **최종 프롬프트에 그대로 실린다.** 사용자는 프롬프트에
    명시한 것과 다른 결과가 나오는 경로라며 자동 수정을 요구했다. 샷 확정은
    카메라 블록(라벨 기반)이 정본이므로, 장면 글에 남은 다른 샷 표현은 걷어낸다.

    규칙 (fix_footwear_clause 와 같은 철학 — 실패하면 원문 유지):
      - 최종 shot 라벨의 표현은 그대로 둔다 (모순 아님).
      - 다른 샷 라벨의 표현이 장면에 있으면 그 표현을 지운다. 표현 앞뒤의
        대표 관사·전치사("a ", "an ", "the ", "of a ")가 고아로 남으면 함께
        정리한다.
      - 지운 뒤 생긴 이중 공백·고아 쉼표를 정리한다.
      - 확정 shot 이 AUTO/빈값이면 손대지 않는다 (판정 불가).

    반환: 교정된 장면 문자열. 변경이 없거나 계산 실패면 입력 그대로.
    """
    try:
        if not isinstance(scene, str) or not scene:
            return scene
        shot_labels = split_multi(camera.get("shot"))
        # 고른 라벨이 하나도 없거나(자동) 알 수 없는 라벨뿐이면 손대지 않는다.
        known = [l for l in shot_labels if l in TOPIC_SHOT_PHRASES]
        if not known:
            return scene
        out = scene
        # 어긋나는 샷 표현이 여러 개일 수 있다 — 고른 라벨의 표현만 남을
        # 때까지 반복한다 (예: "medium shot ... close-up shot" 둘 다 제거).
        # 다중 선택이면 **고른 라벨 전부**를 남긴다 (2026-10-21 수정).
        for _ in range(6):
            other = _unallowed_shot_label(out, known)
            if not other:
                break
            for phrase in TOPIC_SHOT_PHRASES.get(other, ()):
                if not phrase:
                    continue
                # " shot" 로 끝나는 표현은 bare 형태("medium")까지 함께 본다.
                forms = [phrase]
                if phrase.endswith(" shot"):
                    bare = phrase[:-5]
                    if len(bare.split()) >= 2:
                        forms.append(bare)
                for form in forms:
                    # 앞 관사·전치사 + 표현 + 뒤 "of" 를 한 덩어리로 흡수해
                    # 고아 단어가 남지 않게 한다.
                    out = _shot_phrase_re(form).sub(" ", out)
        # 변경이 없으면 원문 그대로 반환한다 — 정리 정규식이 멀쩡한 문장의
        # 선행 관사·공백까지 건드리지 않게 한다 (2026-10-21 회귀 방지).
        if out == scene:
            return scene
        # 정리: 이중 공백, 문장부호 앞 공백, 고아 쉼표, 시작 쉼표.
        out = re.sub(r"\s{2,}", " ", out)
        out = re.sub(r"\s+([.,;])", r"\1", out)
        out = re.sub(r",\s*,", ", ", out)
        out = re.sub(r"^\s*(?:in|with|of|at|from|using|a|an|the)\s+", "", out,
                     flags=re.I)
        out = out.strip().lstrip(",; ").strip()
        return out or scene
    except Exception:
        return scene

