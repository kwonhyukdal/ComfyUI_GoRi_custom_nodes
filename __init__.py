# -*- coding: utf-8 -*-
"""ComfyUI_GoRi_custom_nodes — GoRi 커스텀 노드 통합 팩 로더.

Manager/Registry로 이 저장소 전체를 설치했을 때 하위 노드 폴더(GoRi-*)를
스캔해 NODE_CLASS_MAPPINGS를 통합 등록한다. ComfyUI는 custom_nodes의
하위 폴더를 재귀 탐색하지 않으므로 이중 로딩은 발생하지 않고, 각 하위
폴더를 단독 복사 설치해도 그 폴더의 __init__.py가 직접 로드된다.
"""

import importlib
import os

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
_web_dirs = []

for _name in sorted(os.listdir(_PKG_DIR)):
    if _name.startswith((".", "_")):
        continue
    _sub = os.path.join(_PKG_DIR, _name)
    if not os.path.isdir(_sub) or not os.path.isfile(os.path.join(_sub, "__init__.py")):
        continue
    try:
        _mod = importlib.import_module("." + _name, __name__)
    except Exception as e:  # 한 노드가 실패해도 다른 노드는 로드된다
        print(f"[GoRi] '{_name}' 로드 실패: {e}")
        continue
    NODE_CLASS_MAPPINGS.update(getattr(_mod, "NODE_CLASS_MAPPINGS", {}) or {})
    NODE_DISPLAY_NAME_MAPPINGS.update(getattr(_mod, "NODE_DISPLAY_NAME_MAPPINGS", {}) or {})
    _wd = getattr(_mod, "WEB_DIRECTORY", None)
    if _wd and os.path.isdir(os.path.join(_sub, str(_wd).strip("./"))):
        _web_dirs.append(f"{_name}/{str(_wd).strip('./')}")

# ComfyUI는 팩당 웹 폴더 하나만 지원하므로 첫 항목을 사용한다.
WEB_DIRECTORY = _web_dirs[0] if _web_dirs else None
if len(_web_dirs) > 1:
    print(f"[GoRi] 웹 폴더가 여러 개({', '.join(_web_dirs)}) — 첫 항목만 등록됨")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
