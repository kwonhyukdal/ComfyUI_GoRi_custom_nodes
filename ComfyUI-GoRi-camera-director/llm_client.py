# -*- coding: utf-8 -*-
"""llm_client.py — Camera Director용 LLM 호출 클라이언트.

표준 라이브러리 중심(urllib). vision 입력 변환은 ComfyUI 환경의 PIL/torch/numpy를 사용한다.
- provider: OpenAI / Anthropic / Gemini / OpenRouter / Groq / DeepSeek / Mistral /
            Ollama(로컬) / LM Studio(로컬)
- 응답에서 JSON만 추출 (code-fence 허용)
- 프로세스 내 캐시: 같은 입력 → 네트워크 호출 0회
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 45  # 초 (클우드 API 기준)
# 로컬 LLM(Ollama/LM Studio)은 RTX 8GB급 GPU에서 비전 추론만 수십 초~수분
# 걸릴 수 있다. 클라우드용 기본 타임아웃으로 끊기면 LLM 판정이 항상 실패해
# 규칙 폰백(빨간불)으로 떨어지므로, 로컬 provider는 넉넉한 상한을 쓴다.
LOCAL_TIMEOUT = 300  # 초

_LOCAL_PROVIDERS = ("Ollama", "LM Studio")
# OpenAI / LM Studio / OpenRouter / Groq / DeepSeek / Mistral은
# 메시지 규격이 OpenAI chat completions과 동일하다.
_OPENAI_COMPATIBLE_PROVIDERS = (
    "OpenAI", "LM Studio", "OpenRouter", "Groq", "DeepSeek", "Mistral")

_API_KEY_ENV = {
    "OpenAI": "OPENAI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "Gemini": "GEMINI_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
    "Groq": "GROQ_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "Mistral": "MISTRAL_API_KEY",
}

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 256  # LLM 응답 캐시 상한 (장시간 세션의 무제한 성장 방지)
# 캐시 히트 횟수. `cache_stats()` 가 이걸 돌려준다.
# 미스 카운터는 두지 않는다 — 읽는 곳이 없어 write-only 가 된다(2026-10-02 실측).
_cache_hits = 0
# 캐시 히트 로그를 **키마다 한 번만** 찍기 위한 집합. 같은 입력이 스텝 수만큼
# 되풀이돼도 로그가 한 줄로 유지된다.
_cache_logged = set()

# ComfyUI 루트 .env 폴백 (표준 방식). 노드 폴더 밖이라 폴더째 압축 공유에도
# 키가 딸려가지 않는다. 우선순위: 위젯 입력 > .env 파일 > OS 환경변수.
_ENV_FILE_OVERRIDE = None  # 테스트 주입용 (None이면 자동 탐색)


# ComfyUI 루트를 몇 단계까지 위로 찾을지. 예전엔 **정확히 2단계**로 고정했는데,
# Registry 배포는 `custom_nodes/<팩>/<노드>/llm_client.py` 로 한 단계 더 깊다.
# 2단계로는 `custom_nodes` 까지만 올라가서 .env 를 못 찾고, 키 저장·조회가
# 조용히 죽었다(2026-09-30 실측). 깊이를 세는 대신 main.py 를 찾는다.
_ENV_ROOT_SEARCH_DEPTH = 6


def _env_file_path():
    """ComfyUI 루트의 .env 경로. 못 찾으면 None (조용히 미사용).

    왜(Why) realpath인가: macOS/Linux 개발에서는 `custom_nodes/노드폴더`를
    개발 폴더로 **심볼릭 링크**하는 것이 흔하다. abspath는 링크 경로를 그대로
    쓰기 때문에 ComfyUI 루트를 잘못 올라가 .env를 못 찾는다 →
    사용자는 "키가 저장 안 된다"는 메시지만 보고 원인을 알 수 없다.
    realpath는 링크를 따라가 실제 위치를 준다.

    왜(Why) 깊이를 세지 않는가: 노드 폴더 깊이는 배포 형태에 따라 달라진다
    (단독 설치 = 1단계, Registry 팩 = 2단계). 고정 깊이는 형태가 바뀔 때마다
    조용히 깨진다. **main.py 를 처음 만나는 폴더**가 루트라는 성질로 바꿨다.
    """
    if _ENV_FILE_OVERRIDE is not None:
        return _ENV_FILE_OVERRIDE
    try:
        root = os.path.dirname(os.path.realpath(__file__))
        for _ in range(_ENV_ROOT_SEARCH_DEPTH):
            root = os.path.dirname(root)
            if os.path.isfile(os.path.join(root, "main.py")):
                return os.path.join(root, ".env")
        # 압축(portable) 설치는 ComfyUI 루트에 main.py가 없을 수 있다.
        # 조용히 실패하면 "설정이 안 먹힌 것처럼" 보이므로 이유를 남긴다.
        _warn_env_root_once(root)
    except Exception:
        pass
    return None


_ENV_ROOT_WARNED = set()


def _log(msg: str) -> None:
    """Windows(cp949 등) 콘솔에서도 인코딩 오류로 프로세스가 죽지 않게 한다.

    왜(Why) 이 파일에 자체 로거가 없었나: 카메라 노드의 `_log` 을 빌려 쓰면
    순환 임포트(카메라 → llm_client → 카메라)가 생긴다. 표준 print 한 줄로
    처리한다 — `UnicodeEncodeError` 는 이 저장소가 가장 자주 만나는 죽음 원인이다.
    """
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            print(msg.encode(enc, "replace").decode(enc, errors="replace"),
                  flush=True)
        except Exception:
            pass
    except Exception:
        pass


def _warn_env_root_once(root):
    """ComfyUI 루트를 못 찾았다는 사실을 1회만 로그한다(경고)."""
    if not root or root in _ENV_ROOT_WARNED:
        return
    _ENV_ROOT_WARNED.add(root)
    msg = (f"[GoRi Camera Director] ComfyUI 루트를 찾지 못해 .env에 API 키를 "
           f"저장할 수 없습니다 (확인한 경로: {root}). 키는 노드 칸에 직접 "
           f"입력하거나 환경변수로 지정하세요. 원인이면 ComfyUI 루트에 main.py가 "
           f"있는지 확인하세요.")
    try:
        print(msg, flush=True)
    except Exception:
        pass


def _read_env_file_key(env_name: str) -> str:
    """루트 .env에서 지정 키를 읽는다. 없으면 "" (stdlib만 사용)."""
    if not env_name:
        return ""
    path = _env_file_path()
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                # `export KEY=...` 형태도 읽는다 (쓰기 쪽과 대칭).
                if k.strip().lower().startswith("export "):
                    k = k.strip()[7:]
                if k.strip() == env_name:
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                        v = v[1:-1]
                    return v.strip()
    except (OSError, UnicodeError):
        pass
    return ""


class LLMError(RuntimeError):
    """LLM 호출 실패 — 호출자는 이 예외를 잡고 규칙(auto) 티어로 폰백한다."""


# ---------------------------------------------------------------------------
# JSON 추출
# ---------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    """응답 문자열에서 JSON 객첼만 골라 dict로 반환한다."""
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


def _flatten_content(value) -> str:
    """content 가 문자열이 아닐 때 텍스트만 뽑는다 (게이트웨이 방어).

    왜(Why) 필요한가: 일부 OpenAI 호환 게이트웨이(vLLM/Together/NewAPI 계열)는
    `content` 를 `[{"type":"text","text":"..."}]` **배열**로 돌려준다. 예전 코드는
    `or ""` 만 걸었는데 리스트는 truthy 라 그대로 반환됐고, 그 결과
    `extract_json` 의 `text.strip()` 에서 AttributeError 가 났다. AttributeError 는
    run() 의 `except LLMError` 를 **통과**하므로 LLM 폴백도, 빨간불 표시도 없이
    **노드 실행 자체가 실패**했다 (2026-09-28 실측).
    """
    try:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            value = [value]
        if isinstance(value, (list, tuple)):
            out = []
            for part in value:
                if isinstance(part, str):
                    out.append(part)
                elif isinstance(part, dict):
                    txt = part.get("text")
                    if isinstance(txt, str):
                        out.append(txt)
                    elif isinstance(txt, dict):
                        val = txt.get("value")
                        if isinstance(val, str):
                            out.append(val)
            return "".join(out)
    except Exception:
        pass
    return ""


def _content_from(provider: str, raw: dict) -> str:
    provider = provider or ""
    try:
        if provider in _OPENAI_COMPATIBLE_PROVIDERS or provider.startswith("Custom"):
            return _flatten_content(
                raw["choices"][0]["message"].get("content"))
        if provider == "Anthropic":
            blocks = raw.get("content") or []
            if isinstance(blocks, dict):
                blocks = [blocks]
            return _flatten_content(blocks)
        if provider == "Ollama":
            return _flatten_content(raw["message"].get("content"))
        if provider == "Gemini":
            parts = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            return _flatten_content(parts)
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise LLMError(f"응답 형식 해석 실패: {e}") from e
    raise LLMError(f"알 수 없는 provider: {provider}")


# ---------------------------------------------------------------------------
# 이미지 (PIL → PNG base64). 비전 전달용. 실패 시 None (폰백은 규칙 티어가 담당)
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


def _build_openai_messages(system: str, user: str, image_list: list) -> list:
    """OpenAI chat completions 메시지 규격을 구성한다."""
    if image_list:
        user_block = [{"type": "text", "text": user}]
        for b64 in image_list:
            user_block.append(
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + b64}})
        return [{"role": "system", "content": system},
                {"role": "user", "content": user_block}]
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def _openai_compatible_chat(endpoint: str, model: str, api_key: str,
                            system: str, user: str, image_list: list,
                            timeout: int, extra_headers: dict | None = None) -> dict:
    """OpenAI 호환 엔드포인트에 요청한다."""
    msgs = _build_openai_messages(system, user, image_list)
    # 키가 없는 로컬 서버(LM Studio)는 Authorization 헤더를 아예 보내지 않는다.
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if extra_headers:
        headers.update(extra_headers)
    return _post(
        endpoint,
        {"model": model, "messages": msgs, "temperature": 0.4},
        headers, timeout)


def _normalize_custom_endpoint(base_url: str) -> str:
    """사용자가 입력한 Base URL을 chat/completions 엔드포인트로 정규화한다.

    허용 입력: `https://api.example.com/v1`, 끝 슬래시 포함, 이미
    `/chat/completions`가 붙은 전체 URL. URL이 비면 명확한 안내와 함께 실패한다.
    """
    u = (base_url or "").strip().rstrip("/")
    if not u:
        raise LLMError(
            "Custom (OpenAI 호환): Base URL이 비어 있음 — 노드의 custom_base_url 칸에 "
            "예: https://api.example.com/v1 (규칙으로 폰백)")
    if u.endswith("/chat/completions"):
        return u
    return u + "/chat/completions"


def is_local_provider(provider: str, base_url: str = "") -> bool:
    """로컬(같은 머신) LLM인지. GPU 경합 판정·타임아웃 판정에 쓴다."""
    if (provider or "") in _LOCAL_PROVIDERS:
        return True
    return bool((provider or "").startswith("Custom")
                and not _is_remote_endpoint(base_url))


def _is_remote_endpoint(url: str) -> bool:
    """주소가 같은 머신 밖인가. 로컬 엔드포인트는 키 없이도 되므로 구분한다.

    왜(Why) 필요한가 (2026-10-01 실측): `is_local_provider` 가 "Custom + 키 없음"
    을 그냥 통과시켰다. 그 결과 base_url=https://openrouter.ai/api/v1 로
    **키 없는 요청이 그대로 나갔다**(401 No cookie auth credentials found).
    로컬 대 Custom 는 키가 필요 없으므로, "로컬인가" 로 갈라야 한다.
    """
    u = (url or "").lower()
    if not u:
        return False
    return not any(h in u for h in ("localhost", "127.0.0.1", "0.0.0.0",
                                   "::1", "[::1]", "host.docker.internal"))


def _host_of(url: str) -> str:
    """사람이 읽을 수 있는 호스트명. 실패하면 원본을 짧게."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url or "").hostname
        return host or (url or "")[:48]
    except Exception:
        return (url or "")[:48]


def effective_timeout(provider: str, base_url: str = "",
                      timeout: int = DEFAULT_TIMEOUT) -> int:
    """이 조합에서 실제 적용되는 타임아웃(초). 진단 로그용.

    왜(Why): "timed out"만으로는 45초 클라우드 기본값으로 끊긴 것인지,
    300초 로컬 상한까지 버틴 것인지 구분할 수 없어 원인 파악이 불가능했다.
    """
    if is_local_provider(provider, base_url):
        return max(timeout, LOCAL_TIMEOUT)
    return timeout


def chat(provider: str, model: str, api_key: str,
         system: str, user: str, timeout: int = DEFAULT_TIMEOUT,
         image_b64=None, image_sig=None, image_b64s=None,
         base_url: str = "") -> dict:
    """LLM에 질의하고 JSON 객체를 돌려준다. 실패 시 LLMError.

    - OpenAI/Anthropic/Gemini/OpenRouter/Groq/DeepSeek/Mistral: 위젯 키가
      비면 루트 .env → OS 환경변수 순으로 찾고, 없으면 즉시 실패(네트워크
      호출 없음). 환경변수 이름은 _API_KEY_ENV 참조.
    - Custom (OpenAI 호환): base_url로 지정한 임의 엔드포인트에 OpenAI
      chat/completions 규격으로 호출. 키는 선택(키 없는 게이트웨이 허용),
      model 칸은 필수. Base URL이 localhost면 로컬 타임아웃 적용.
    - Ollama: 로컬(localhost:11434), 키 불필요
    - LM Studio: 로컬 OpenAI 호환 서버(localhost:1234/v1), 키 불필요
    - image_b64: PNG base64 1장 — 비전 전달 (지원 모델만). 캐시 키에 이미지 서명 포함
    - image_b64s: PNG base64 여러 장 — OpenAI/Anthropic/Ollama/LM Studio/Gemini
      등 다중 비전 전달
    """
    provider = provider or ""
    is_custom = provider.startswith("Custom")
    image_list = [b for b in (image_b64s or []) if b]
    if not image_list and image_b64:
        image_list = [image_b64]
    if is_custom:
        # 캐시 키/타임아웃 판정에 엔드포인트가 필요하므로 캐시 조회 전에 정규화.
        endpoint = _normalize_custom_endpoint(base_url)
    # 로컬 provider는 호출자가 짧은 타임아웃을 넘겨도 LOCAL_TIMEOUT 이하로
    # 날려가지 않게 상향한다. (Why: 로컬 비전 추론이 기본 45초를 초과해
    # 항상 timed out → 빨간불 폰백이 되는 사례 방지)
    # 로컬 판정은 is_local_provider() 하나만 쓴다 (리뷰로 확인된 중복).
    # 여기서 따로 판정하면 규칙이 바뀌었을 때 타임아웃과 camera_director의
    # GPU 경합 해소가 어긋난다 — 두 곳이 같은 규칙을 공유해야 한다.
    if is_local_provider(provider, base_url):
        timeout = max(timeout, LOCAL_TIMEOUT)
    # Custom은 엔드포인트별로 캐시를 분리해야 한다(같은 model·텍스트라도
    # 다른 게이트웨이의 응답은 다를 수 있다).
    cache_provider = f"Custom|{endpoint}" if is_custom else provider
    key = _cache_key(cache_provider, model, system, user, image_b64, image_sig, image_list)
    global _cache_hits
    with _cache_lock:
        hit = key in _cache
        if hit:
            _cache_hits += 1
        if hit:
            obj = _cache[key]
            # 왜(Why) 여기에 로그가 있나 (2026-10-02 실측): 캐시 히트는 네트워크
            # 호출 0회라 **몇 초 만에 끝난다.** 초록불은 켜지는데 시스템 자원도
            # 시간도 안 쓰는 현상을 사용자가 "작동을 안 하는데?" 로 읽었다.
            # `cam_source` 가 "LLM 판단" 인데 20ms 만에 찍힌 실측이 그 근거다
            # (카메라 노드 preflight→요약 로그 구간 19~25ms × 3회).
            # 히트/미스 수가 telemetry 로도 보고되므로 여기서 같은 사실을 한 번만
            # 말해둔다. **같은 키는 한 번만** — 스텝 수만큼 되풀이되면 못 읽는다.
            if key not in _cache_logged:
                _cache_logged.add(key)
                try:
                    _log(f"[GoRi Camera Director] LLM 캐시 히트 — 같은 입력의 "
                         f"이전 응답을 재사용했습니다 (네트워크 호출 0회). "
                         f"provider={cache_provider} model={model or '없음'}")
                except Exception:
                    pass
            return obj

    api_key = (api_key or "").strip()
    if not api_key and provider not in ("Ollama", "LM Studio") and not is_custom:
        env = _API_KEY_ENV.get(provider)
        # 우선순위: 위젯 입력 > 루트 .env 파일 > OS 환경변수
        api_key = _read_env_file_key(env) if env else ""
        if not api_key:
            api_key = os.environ.get(env, "").strip() if env else ""
        if not api_key:
            raise LLMError(
                f"API 키 없음 ({env or provider} 환경변수·루트 .env 또는 노드 api_key 필요 — 규칙으로 폰백)")

    if is_custom:
        if not (model or "").strip():
            raise LLMError(
                "Custom (OpenAI 호환): model 칸이 비어 있음 — 엔드포인트가 제공하는 "
                "모델명을 입력하세요 (예: qwen2.5-vl)")
        # 왜(Why) 여기서 막는가 (2026-10-01 실측): `and not is_custom` 때문에
        # 키 검사를 통째로 건너뛰고 **빈 키로 외부 서버에 요청을 보냈다.**
        # 실측 로그:
        #   HTTP 401: {"error":{"message":"No cookie auth credentials found"}}
        # provider=Custom (OpenAI 호환)  base_url=https://openrouter.ai/api/v1
        # 즉 키가 없는데 45초를 버리고 실패했다. **키가 없으면 애초에 요청하지
        # 않는 게 옳다.** 로컬 엔드포인트는 키가 필요 없을 수 있으니 "주소가
        # 같은 머신인가" 로 구분한다.
        #
        # **중요**: 외부 LLM 자체를 금지하는 게 아니다. 키를 넣으면 정상 호출한다.
        # 막는 것은 "키가 없는 채로 나가는 요청" 뿐이다. 같은 머신으로 되돌릴
        # 방법이 없는 실수이므로, 관측 가능성을 남기는 게 낫다.
        # 순서는 model 검사 다음이다 — 더 구체적인 안내를 먼저 준다.
        if not api_key and _is_remote_endpoint(endpoint):
            raise LLMError(
                "API 키 없음 — 외부 엔드포인트로는 요청하지 않습니다 "
                f"({_host_of(endpoint)}). 키를 넣으면 정상 호출되고, "
                # 왜(Why) 여기 라벨을 그대로 적나 (2026-10-01 실측): `automation`
                # 위젯의 실제 옵션 문자열은 "규칙 (auto)" 다. "자동 (auto)" 는
                # **프리셋** 위젯의 라벨이라 사용자가 찾으면 없는 값을 고르게 된다.
                # 상수를 하드코딩하지 않고 노드가 쓰는 값을 그대로 안내한다.
                "automation 을 '규칙 (auto)' 로 두면 규칙으로 폴백합니다")
        raw = _openai_compatible_chat(
            endpoint, model.strip(), api_key, system, user, image_list, timeout)
    elif provider in _OPENAI_COMPATIBLE_PROVIDERS:
        # OpenAI 호환 엔드포인트별 매핑
        endpoints = {
            "OpenAI": "https://api.openai.com/v1/chat/completions",
            "LM Studio": "http://localhost:1234/v1/chat/completions",
            "OpenRouter": "https://openrouter.ai/api/v1/chat/completions",
            "Groq": "https://api.groq.com/openai/v1/chat/completions",
            "DeepSeek": "https://api.deepseek.com/chat/completions",
            "Mistral": "https://api.mistral.ai/v1/chat/completions",
        }
        defaults = {
            "OpenAI": "gpt-4o-mini",
            "LM Studio": "local-model",
            "OpenRouter": "google/gemini-flash-1.5",
            "Groq": "llama-3.2-90b-vision-preview",
            "DeepSeek": "deepseek-chat",
            "Mistral": "pixtral-12b-2409",
        }
        extra_headers = {}
        if provider == "OpenRouter":
            # OpenRouter는 출처 헤더를 권장한다.
            extra_headers = {
                "HTTP-Referer": "https://github.com/kwonhyukdal/ComfyUI_GoRi_custom_nodes",
                "X-Title": "GoRi Camera Director",
            }
        raw = _openai_compatible_chat(
            endpoints[provider],
            model or defaults[provider],
            api_key, system, user, image_list, timeout,
            extra_headers=extra_headers)
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
    elif provider == "Gemini":
        # Gemini는 system 분리가 없고 URL에 키를 담는다.
        parts = [{"text": system + "\n\n" + user}]
        for b64 in image_list:
            parts.append({"inline_data": {"mime_type": "image/png", "data": b64}})
        raw = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model or 'gemini-1.5-flash'}:generateContent?key={api_key}",
            {"contents": [{"role": "user", "parts": parts}],
             "generationConfig": {"temperature": 0.4}},
            {}, timeout)
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
    """(캐시 항목 수, **캐시 히트 횟수**) — 디버그용.

    왜(Why) 둘째 값을 '히트'가 아니라 예전엔 len 을 그대로 돌려줬다 (2026-10-02):
    docstring 이 "히트 판정용 총 호출 시도 횟수는 별도" 라고 적어놓고 실제로는
    `return len(_cache), len(_cache)` 였다. 즉 **히트 수를 알 방법이 없었다.**
    그래서 "초록불이 켜졌는데 안 도는 거냐" 를 로그로 확인할 수 없었다.
    테스트는 `cache_stats()[0]` (항목 수)만 사용하므로 둘째 값은 안전하다.
    """
    with _cache_lock:
        return len(_cache), _cache_hits


def clear_cache() -> None:
    # 왜(Why) `global` 이 필수인가: 없으면 아래 두 줄이 **함수 지역변수** 가 되어
    # 모듈 수준 카운터가 리셋되지 않는다. 테스트가 `clear_cache()` 를 수십 번
    # 호출하므로 카운터가 누적되면 히트 수가 뒤섞인다(2026-10-02 실측).
    global _cache_hits
    with _cache_lock:
        _cache.clear()
        _cache_hits = 0
        _cache_logged.clear()
