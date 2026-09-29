# -*- coding: utf-8 -*-
"""comfyui-gori-custom-nodes — GoRi 커스텀 노드 통합 팩 로더.

Manager/Registry로 이 저장소 전체를 설치했을 때 하위 노드 폴더(GoRi-*)를
스캔해 NODE_CLASS_MAPPINGS를 통합 등록한다. 각 하위 폴더를 단독 복사
설치해도 그 폴더의 __init__.py가 직접 로드된다.

왜(Why) 여기서 importlib 로 직접 로드하는가 (2026-09-29 실측):
ComfyUI 의 `init_external_custom_nodes` 는 `custom_nodes` 의 각 항목만
스캔하고 **하위 폴더를 재귀 탐색하지 않는다.** 그래서 이 팩의
`GoRi-Camera-Director/` 와 `GoRi-Consistency-Keeper/` 는 단독으로는
아예 로드되지 않는다 — 그 안에 등록된 노드가 없어도 조용하다.

또한 ComfyUI 는 폴더 모듈을 `__init__.py` 만 실행하고
`sys.modules[sys_module_name] = module` 로 등록하는데, `sys_module_name` 은
경로 기반(`custom_nodes_comfyui-gori-custom-nodes` 처럼 dots 를 _x_ 로
 바꾼 것)이라 **패키지 이름이 아니다.** 그래서 `importlib.import_module("."
+ name, __name__)` 의 상대 임포트는 항상 `No module named 'pack'` 으로
실패한다. 실제로 확인:
    [GoRi] 'GoRi-Camera-Director' 로드 실패: No module named 'pack'
    [GoRi] 'GoRi-Consistency-Keeper' 로드 실패: No module named 'pack'
결과적으로 NODE_CLASS_MAPPINGS 가 비고 WEB_DIRECTORY 도 None 이었다.

그래서 하위 폴더를 파일 경로로 직접 로드한다(submodule_search_locations 로
패키지화하므로 하위의 `from .camera_director import ...` 가 동작한다).
"""

import importlib.util
import os
import sys

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
_web_dirs = []


def _load_subpackage(name):
    """하위 폴더를 패키지로 로드한다. 실패하면 예외."""
    sub_dir = os.path.join(_PKG_DIR, name)
    init_file = os.path.join(sub_dir, "__init__.py")
    spec = importlib.util.spec_from_file_location(
        name, init_file, submodule_search_locations=[sub_dir])
    if spec is None or spec.loader is None:
        raise ImportError(f"'{name}' 의 로더를 만들지 못했다")
    mod = importlib.util.module_from_spec(spec)
    # 하위 모듈이 `from .xxx import` 로 상대 임포트할 수 있도록 먼저 등록한다.
    # 이 순서가 없으면 submodule_search_locations 가 있어도 실행 시점에
    # 패키지가 sys.modules 에 없어서 실패한다.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


for _name in sorted(os.listdir(_PKG_DIR)):
    if _name.startswith((".", "_")):
        continue
    _sub = os.path.join(_PKG_DIR, _name)
    if not os.path.isdir(_sub) or not os.path.isfile(os.path.join(_sub, "__init__.py")):
        continue
    try:
        _mod = _load_subpackage(_name)
    except Exception as e:  # 한 노드가 실패해도 다른 노드는 로드된다
        print(f"[GoRi] '{_name}' 로드 실패: {type(e).__name__}: {e}")
        sys.modules.pop(_name, None)
        continue
    NODE_CLASS_MAPPINGS.update(getattr(_mod, "NODE_CLASS_MAPPINGS", {}) or {})
    NODE_DISPLAY_NAME_MAPPINGS.update(getattr(_mod, "NODE_DISPLAY_NAME_MAPPINGS", {}) or {})
    _wd = getattr(_mod, "WEB_DIRECTORY", None)
    if _wd and os.path.isdir(os.path.join(_sub, str(_wd).lstrip("./").lstrip("/"))):
        _web_dirs.append(f"{_name}/{str(_wd).lstrip('./').lstrip('/')}")

# ComfyUI는 팩당 웹 폴더 하나만 지원하므로 첫 항목을 사용한다.
WEB_DIRECTORY = _web_dirs[0] if _web_dirs else None
if len(_web_dirs) > 1:
    print(f"[GoRi] 웹 폴더가 여러 개({', '.join(_web_dirs)}) — 첫 항목만 등록됨")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
