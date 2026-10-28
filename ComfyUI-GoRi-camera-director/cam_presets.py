# -*- coding: utf-8 -*-
"""사용자 프리셋 저장소 — 설치한 카메라 노드 폴더 안 `user_presets/` 의 JSON 파일.

왜(Why) 서버가 필요한가: 브라우저는 파일을 쓸 수 없다. "저장 버튼을 누르면
노드 안 폴더에 저장" 은 서버만 할 수 있으므로 라우트 두 개를 연다.
패턴은 cam_llm.py 의 `PromptServer.instance.routes` 와 같다(새로 만들지 않는다).

왜(Why) 파일 하나 = 프리셋 하나인가: 하나가 깨져도 나머지가 살고, 사용자가
폴더에서 파일을 지우면 그 프리셋이 지워진다("그 안에 저장을 해 관리" 요구).
파일 안에 표시 이름을 함께 적어 두어, 이름이 파일 이름 규칙 때문에 바뀌어도
화면에는 원래 이름이 나온다.

이 모듈은 표준 라이브러리만 쓴다. 프로젝트의 다른 모듈을 import 하지 않으므로
분리 모듈의 크로스 이름 검사(R99) 대상이 없다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

__all__ = [
    "USER_PRESET_DIR_NAME",
    "USER_PRESET_ROUTE",
    "MAX_PRESET_NAME_LEN",
    "MAX_PRESET_FIELDS",
    "MAX_PRESET_BYTES",
    "user_preset_dir",
    "normalize_preset_name",
    "preset_file_stem",
    "preset_file_path",
    "clean_preset_fields",
    "load_user_presets",
    "save_user_preset",
    "delete_user_preset",
]

#: 노드 폴더 안에 만들어지는 사용자 프리셋 폴더 이름.
USER_PRESET_DIR_NAME = "user_presets"

#: 프런트엔드와 주고받는 경로. 프런트의 USER_PRESET_ROUTE 와 같아야 한다.
USER_PRESET_ROUTE = "/gori_user_presets"

#: 표시 이름 길이 상한. 파일 이름이 무한정 길어지는 것을 막는다.
MAX_PRESET_NAME_LEN = 64

#: 한 프리셋의 필드 개수 상한. 카메라 기능 칸은 10개다 — 넘치면 잘라 저장한다.
MAX_PRESET_FIELDS = 64

#: 저장 파일 하나의 상한(바이트). 넘으면 저장을 거부한다.
MAX_PRESET_BYTES = 262144

#: Windows 파일 이름 금지 문자 + 제어문자.
_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Windows 예약 장치 이름 — 파일로 만들 수 없다(확장자를 붙여도 안 된다).
_RESERVED_STEMS = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + ["COM%d" % i for i in range(1, 10)]
    + ["LPT%d" % i for i in range(1, 10)]
)


def user_preset_dir() -> str:
    """프리셋 폴더의 절대 경로.

    realpath 를 쓰는 이유: 개발 폴더가 custom_nodes 에 심볼릭 링크로 걸려 있을
    때, 저장은 **사용자가 실제로 고치는 폴더**에 떨어져야 한다. abspath 는
    링크 경로를 그대로 돌려주므로 그때와 다른 곳에 쓰게 된다(R52 와 같은 이유).
    """
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(here, USER_PRESET_DIR_NAME)


def normalize_preset_name(raw) -> str:
    """사용자가 입력한 이름 → 표시 이름. 쓸 수 없으면 None.

    거부하는 것: 문자열이 아님, 공백뿐, `.`, `..`. 앞뒤 공백은 지우고
    MAX_PRESET_NAME_LEN 자로 자른다. 자르는 쪽을 고른 이유: 너무 긴 이름 때문에
    저장 자체가 실패하는 것보다, 저장되고 화면에 잘린 이름이 보이는 편이 낫다.
    """
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not name or name in (".", ".."):
        return None
    if len(name) > MAX_PRESET_NAME_LEN:
        name = name[:MAX_PRESET_NAME_LEN].strip()
    if not name or name in (".", ".."):
        return None
    return name


def preset_file_stem(name: str) -> str:
    """표시 이름 → 파일 이름(확장자 제외). 경로를 벗어나지 못하게 만든다.

    왜(Why) 글자를 바꾸는가: `<` `>` `:` `"` `/` `\\` `|` `?` `*` 는 Windows 에서
    파일 이름에 쓸 수 없고, `/` 와 `\\` 는 경로 구분자라 폴더 밖을 가리킬 수 있다.

    왜(Why) 바뀐 이름에만 짧은 해시를 붙이는가: 글자를 지우면 `a/b` 와 `a_b` 가
    **같은 파일**이 되어 두 번째 저장이 첫 번째를 조용히 덮어쓴다. 바뀐 경우에만
    꼬리를 붙이면 평범한 이름(한글 포함)은 그대로 남아 사용자가 파일을 알아보고,
    바뀐 이름끼리는 서로 달라진다. 같은 입력은 항상 같은 결과다(멱등).
    """
    safe = _FORBIDDEN_CHARS.sub("_", str(name))
    safe = safe.strip().rstrip(".")          # Windows 가 조용히 지우는 끝 문자
    if not safe:
        safe = "_"
    if safe.split(".")[0].upper() in _RESERVED_STEMS:
        safe = "_" + safe
    if safe != name:
        digest = hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:8]
        safe = "%s-%s" % (safe, digest)
    return safe


def preset_file_path(name: str) -> str:
    """표시 이름 → 저장 파일의 전체 경로."""
    return os.path.join(user_preset_dir(), preset_file_stem(name) + ".json")


def clean_preset_fields(fields) -> dict:
    """저장할 필드만 남긴다. 순수 함수.

    None 값은 뺀다(프런트가 "값 없음" 을 None 으로 보내는 경우가 있다).
    키와 값은 문자열로 만든다 — JSON 으로만 오가므로 다른 형이 필요 없다.
    개수 상한을 넘으면 잘라 낸다.
    """
    out = {}
    if not isinstance(fields, dict):
        return out
    for key, value in fields.items():
        if value is None:
            continue
        out[str(key)] = str(value)
        if len(out) >= MAX_PRESET_FIELDS:
            break
    return out


def _read_preset_file(path: str):
    """파일 하나를 읽어 (이름, 필드) 로 돌려준다. 읽을 수 없으면 (None, None)."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, UnicodeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    name = normalize_preset_name(data.get("name"))
    fields = data.get("fields")
    if not name or not isinstance(fields, dict):
        return None, None
    return name, clean_preset_fields(fields)


def load_user_presets() -> dict:
    """폴더의 모든 프리셋 → {표시 이름: {필드: 값}}.

    깨진 파일·이름 없는 파일·`.json` 이 아닌 파일은 건너뛴다. 하나가 깨졌다고
    전체 목록이 비면 사용자는 프리셋을 모두 잃은 것으로 오해한다.
    """
    out = {}
    directory = user_preset_dir()
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return out
    for entry in entries:
        if not entry.endswith(".json"):
            continue
        name, fields = _read_preset_file(os.path.join(directory, entry))
        if name:
            out[name] = fields
    return out


def _write_atomic(path: str, text: str) -> None:
    """임시 파일에 쓰고 교체한다.

    왜(Why): 그대로 `open(path, "w")` 하면 truncate 직후 예외가 났을 때
    **이미 저장해 둔 프리셋이 통째로 사라진다.** 교체 전까지 기존 파일은 그대로다
    (cam_llm._write_env_file 과 같은 방식, 같은 이유).
    """
    tmp = path + ".gori_tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_user_preset(name, fields):
    """프리셋 하나를 저장하고 **전체 목록**을 돌려준다. 저장 못 하면 None.

    같은 이름이면 같은 파일을 덮어쓴다 — 사용자 결정(값을 바꾸고 같은 이름으로
    다시 저장할 수 있어야 한다). 전체 목록을 함께 돌려주는 이유: 화면이 저장
    직후 창을 다시 그릴 때 목록을 따로 받아오지 않아도 되게 한다.
    """
    nm = normalize_preset_name(name)
    if not nm:
        return None
    if not isinstance(fields, dict):
        return None
    payload = {"name": nm, "fields": clean_preset_fields(fields)}
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    except (TypeError, ValueError):
        return None
    if len(text.encode("utf-8")) > MAX_PRESET_BYTES:
        return None
    directory = user_preset_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        _write_atomic(preset_file_path(nm), text)
    except OSError:
        return None
    return load_user_presets()


def _preset_payload(data):
    """POST 본문 → (이름, 필드). 모양이 아니면 (None, None)."""
    if not isinstance(data, dict):
        return None, None
    fields = data.get("fields")
    if not isinstance(fields, dict):
        return None, None
    return data.get("name"), fields


def delete_user_preset(name):
    """프리셋 하나를 지우고 **남은 전체 목록**을 돌려준다. 못 지우면 None.

    왜(Why) 없는 이름도 실패로 답하나: 화면이 "지웠습니다" 라고 잘못 안내하면
    사용자는 파일이 남아 있는 줄 모른다. 그래서 지운 것이 없으면 조용히
    성공하지 않는다. 서버가 준 목록으로 화면을 다시 그리므로 목록도 함께 준다.

    왜(Why) 폴더 안인지 한 번 더 보나: 이름 → 파일 이름 변환(_FORBIDDEN_CHARS)
    이 이미 경로 구분자를 막지만, 지우기는 되돌릴 수 없다. 저장과 달리 실수하면
    사용자 파일이 사라지므로 여기서 한 번 더 확인한다.
    """
    nm = normalize_preset_name(name)
    if not nm:
        return None
    path = preset_file_path(nm)
    root = os.path.realpath(user_preset_dir())
    if os.path.dirname(os.path.realpath(path)) != root:
        return None
    if not os.path.isfile(path):
        return None
    try:
        os.unlink(path)
    except OSError:
        return None
    return load_user_presets()


try:
    from server import PromptServer as _PromptServer

    @_PromptServer.instance.routes.get(USER_PRESET_ROUTE)
    async def _gori_user_presets_get(request):
        """저장된 사용자 프리셋 전체 목록."""
        from aiohttp import web as _web
        try:
            return _web.json_response({"ok": True, "presets": load_user_presets()})
        except Exception:
            return _web.json_response({"ok": False, "presets": {}})

    @_PromptServer.instance.routes.post(USER_PRESET_ROUTE)
    async def _gori_user_presets_post(request):
        """사용자 프리셋 하나를 저장한다 (같은 이름은 덮어쓰기)."""
        from aiohttp import web as _web
        try:
            data = await request.json()
        except Exception:
            return _web.json_response({"ok": False}, status=400)
        try:
            name, fields = _preset_payload(data)
            presets = save_user_preset(name, fields)
            if presets is None:
                # 이름이 비었거나 본문 모양이 틀렸다. 조용히 성공하지 않는다 —
                # 프런트가 실패를 알아야 사용자에게 안내를 보여줄 수 있다.
                return _web.json_response({"ok": False}, status=400)
            return _web.json_response({"ok": True, "presets": presets})
        except Exception:
            return _web.json_response({"ok": False})

    @_PromptServer.instance.routes.delete(USER_PRESET_ROUTE)
    async def _gori_user_presets_delete(request):
        """사용자 프리셋 하나를 지운다 (폴더의 파일도 함께).

        이름은 질의 문자열로 받는다 — 한글·공백·기호가 들어올 수 있고, 경로
        조각이면 URL 을 한 번 더 풀어야 한다(aiohttp 가 query 를 대신 풀어 준다).
        """
        from aiohttp import web as _web
        try:
            name = request.query.get("name")
        except Exception:
            name = None
        try:
            presets = delete_user_preset(name)
            if presets is None:
                # 없는 이름·빈 이름·폴더 밖. 지운 것이 없으니 성공이라고 하지 않는다.
                return _web.json_response({"ok": False}, status=400)
            return _web.json_response({"ok": True, "presets": presets})
        except Exception:
            return _web.json_response({"ok": False})
except Exception:
    # 서버 밖(테스트·스탠드얼론)에서는 라우트 없이 동작한다.
    pass
