# -*- coding: utf-8 -*-
"""llm_client.py — Camera Director용 LLM 호출 클라이언트.

표준 라이브러리 중심(urllib). vision 입력 변환은 ComfyUI 환경의 PIL/torch/numpy를 사용한다.
- provider: OpenAI / Anthropic / Ollama(로컬)
- 응답에서 JSON만 추출 (code-fence 허용)
- 프로세스 내 캐시: 같은 입력 → 네트워크 호출 0회
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 45  # 초

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 256  # LLM 응답 캐시 상한 (장시간 세션의 무제한 성장 방지)


class LLMError(RuntimeError):
    """LLM 호출 실패 — 호출자는 이 예외를 잡고 규칙(auto) 티어로 폴백한다."""


# ---------------------------------------------------------------------------
# JSON 추출
# ---------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """응답 문자열에서 JSON 객체만 골라 dict로 반환한다."""
    if not text:
        raise LLMError("빈 응답")
    t = text.strip()
    # ```json ... ``` 허용
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if fence:
        t = fence.group(1)
    if not t.startswith("{"):
        start, end = t.find("{"), t.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("JSON 객체를 찾을 수 없음")
        t = t[start:end + 1]
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(obj, dict):
        raise LLMError("JSON 최상위가 객체가 아님")
    return obj


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise LLMError(f"HTTP {e.code}: {body}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise LLMError(f"네트워크 오류: {e}") from e
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 응답 디코딩 실패: {e}") from e


def _content_from(provider: str, raw: dict) -> str:
    try:
        if provider == "OpenAI":
            return raw["choices"][0]["message"]["content"] or ""
        if provider == "Anthropic":
            blocks = raw.get("content") or []
            return "".join(b.get("text", "") for b in blocks)
        if provider == "Ollama":
            return raw["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise LLMError(f"응답 형식 해석 실패: {e}") from e
    raise LLMError(f"알 수 없는 provider: {provider}")


# ---------------------------------------------------------------------------
# 이미지 (PIL → PNG base64). 비전 전달용. 실패 시 None (폴백은 규칙 티어가 담당)
# ---------------------------------------------------------------------------

def image_to_b64(image, max_side: int = 768):
    try:
        from PIL import Image as _Image
        import base64 as _b64
        import io as _io

        import torch as _t
        px = image[0] if isinstance(image, _t.Tensor) else image
        if hasattr(px, "detach"):
            px = px.detach().cpu()
        arr = px.numpy() if hasattr(px, "numpy") else px
        import numpy as _np
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.max() <= 1.5:
            arr = (arr * 255.0).clip(0, 255).astype(_np.uint8)
        else:
            arr = arr.clip(0, 255).astype(_np.uint8)
        if arr.shape[-1] == 1:
            arr = _np.repeat(arr, 3, axis=-1)
        elif arr.shape[-1] >= 4:
            arr = arr[..., :3]
        im = _Image.fromarray(arr, "RGB")
        r = max_side / max(im.size)
        if r < 1.0:
            im = im.resize((int(im.width * r), int(im.height * r)))
        buf = _io.BytesIO()
        im.save(buf, format="PNG")
        return _b64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def _cache_key(provider: str, model: str, system: str, user: str,
               image_b64=None, image_sig=None, image_b64s=None) -> str:
    if image_b64s:
        parts = []
        for item in image_b64s:
            blob = item.encode("ascii") if isinstance(item, str) else item
            parts.append(hashlib.sha1(blob).hexdigest())
        img_ref = "b64s:" + ",".join(parts)
    elif image_b64:
        blob = image_b64.encode("ascii") if isinstance(image_b64, str) else image_b64
        img_ref = "b64:" + hashlib.sha1(blob).hexdigest()
    elif image_sig:
        img_ref = "sig:" + str(image_sig)
    else:
        img_ref = "none"
    return hashlib.sha1(
        "\n".join([provider, model, system, user, img_ref]).encode("utf-8")).hexdigest()


def chat(provider: str, model: str, api_key: str,
         system: str, user: str, timeout: int = DEFAULT_TIMEOUT,
         image_b64=None, image_sig=None, image_b64s=None) -> dict:
    """LLM에 질의하고 JSON 객체를 돌려준다. 실패 시 LLMError.

    - OpenAI/Anthropic: 키가 없으면 즉시 실패(네트워크 호출 없음)
    - Ollama: 로컬(localhost:11434), 키 불필요
    - image_b64: PNG base64 1장 — 비전 전달 (지원 모델만). 캐시 키에 이미지 서명 포함
    - image_b64s: PNG base64 여러 장 — OpenAI/Anthropic/Ollama 다중 비전 전달
    """
    image_list = [b for b in (image_b64s or []) if b]
    if not image_list and image_b64:
        image_list = [image_b64]
    key = _cache_key(provider, model, system, user, image_b64, image_sig, image_list)
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    api_key = (api_key or "").strip()
    if not api_key and provider != "Ollama":
        env = "OPENAI_API_KEY" if provider == "OpenAI" else "ANTHROPIC_API_KEY"
        api_key = os.environ.get(env, "").strip()
        if not api_key:
            raise LLMError(f"API 키 없음 ({env} 환경변수 또는 노드 api_key 필요 — 규칙으로 폴백)")

    if provider == "OpenAI":
        if image_list:
            user_block = [{"type": "text", "text": user}]
            for b64 in image_list:
                user_block.append(
                    {"type": "image_url",
                     "image_url": {"url": "data:image/png;base64," + b64}})
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": user_block}]
        else:
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        raw = _post(
            "https://api.openai.com/v1/chat/completions",
            {"model": model or "gpt-4o-mini", "messages": msgs,
             "temperature": 0.4},
            {"Authorization": f"Bearer {api_key}"}, timeout)
    elif provider == "Anthropic":
        if image_list:
            user_block = [{"type": "text", "text": user}]
            for b64 in image_list:
                user_block.append(
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/png",
                                "data": b64}})
        else:
            user_block = user
        raw = _post(
            "https://api.anthropic.com/v1/messages",
            {"model": model or "claude-3-5-haiku-latest",
             "max_tokens": 1024,
             "system": system,
             "messages": [{"role": "user", "content": user_block}]},
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout)
    elif provider == "Ollama":
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        if image_list:
            # /api/chat 규격: images는 메시지별 필드다. 최상위 "images"는
            # /api/generate용이라 chat에서는 조용히 무시되므로 여기에 둔다.
            messages[1]["images"] = image_list
        payload = {"model": model or "llama3.2", "stream": False,
                   "messages": messages}
        raw = _post("http://localhost:11434/api/chat", payload, {}, timeout)
    else:
        raise LLMError(f"알 수 없는 provider: {provider}")

    obj = extract_json(_content_from(provider, raw))
    with _cache_lock:
        if key not in _cache and len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)), None)  # 가장 오래된 항목 퇴거
        _cache[key] = obj
    return obj


def cache_stats() -> tuple[int, int]:
    """(캐시 항목 수, 히트 판정용 총 호출 시도 횟수는 별도) — 디버그용."""
    with _cache_lock:
        return len(_cache), len(_cache)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
