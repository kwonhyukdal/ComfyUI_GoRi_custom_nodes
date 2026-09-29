# -*- coding: utf-8 -*-
"""통합 팩 루트 로더 검증. 실행: python tests/test_pack.py

왜(Why) 이 파일이 필요한가(2026-09-29 실측):
하위 노드 테스트(각 폴더의 tests/test_node.py)는 전부 통과했는데 실제로는
**노드가 하나도 등록되지 않았다.** ComfyUI 콘솔엔 조용히 이 한 줄만 찍혔다:

    [GoRi] 'GoRi-Camera-Director' 로드 실패: No module named 'pack'

원인은 루트 `__init__.py` 의 `importlib.import_module("." + name, __name__)`
였다. ComfyUI 는 폴더 모듈을 경로 기반 이름(`custom_nodes_comfyui-gori-...`
형태, dots 를 _x_ 로 치환)으로 `sys.modules` 에 등록하므로 **패키지 이름이
아니다.** 그래서 상대 임포트가 항상 실패한다.

하위 노드 테스트는 자기 폴더에서 직접 실행하므로 이 경로를 전혀 타지 않는다.
즉 **팩 통합 계층은 테스트가 없었다.** 이 파일이 그 공백을 메운다.

폴더 이름 주의: 로컬 개발 폴더는 `GoRi-Camera-Director` /
`GoRi-Consistency-Keeper` 이고, Registry 배포 폴더는 Registry 매핑 때문에
`ComfyUI-GoRi-camera-director` / `Comfyui-GoRi-Consistency-Keeper` 다.
대소문자가 섞여 있어(일부러 바꾼 것) 이름으로 하드코딩하지 않고
`__init__.py` 를 가진 폴더를 전부 찾는다.

여기서는 ComfyUI 가 실제로 쓰는 로딩 방식(`spec_from_file_location` +
`sys.modules` 등록)으로 재현해 확인한다. 이 재현이 틀리면 이 테스트도
헛돌기 때문에, ComfyUI 의 nodes.py 에서 발췌한 형식을 그대로 쓴다.
"""

import importlib.util
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = FAIL = 0
_print = print


def _say(line):
    try:
        _print(line)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        try:
            _print(line.encode(enc, "replace").decode(enc, errors="replace"))
        except Exception:
            pass


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        _say(f"  PASS  {name}")
    else:
        FAIL += 1
        _say(f"  FAIL  {name}  {detail}")


# ComfyUI nodes.py 의 load_custom_node 가 폴더에 대해 하는 일과 같은 형태.
# (dots 를 _x_ 로 치환하는 부분까지 재현해야 재현이 정확하다)
def _load_like_comfyui(module_path):
    module_path = os.path.abspath(module_path)
    sys_module_name = module_path.replace(".", "_x_").replace(os.sep, "_").replace(":", "_")
    spec = importlib.util.spec_from_file_location(
        sys_module_name, os.path.join(module_path, "__init__.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sys_module_name] = mod
    spec.loader.exec_module(mod)
    return mod, sys_module_name


_say("-- 통합 팩 로더 (ComfyUI 실제 로딩 방식 재현) --")
# 왜(Why) sys.path 를 비우나(2026-09-29 실측):
# ComfyUI 는 실행 중 `custom_nodes` 를 sys.path 에 넣는다. 그래서 옛 코드의
# `importlib.import_module("." + name, __name__)` 가 **우연히 통한다.**
# 모듈명이 경로 기반이라 상대 임포트는 `No module named 'pack'` 으로 실패하는데,
# 같은 이름이 sys.path 에서 **절대 임포트**로 다시 잡혀 성공한 것처럼 보인다.
#
# 즉 실제로는 세 갈래다:
#   - custom_nodes 가 sys.path 에 있음 → 우연히 동작 (에러 로그만 남음)
#   - cwd('') 가 sys.path 에 있음      → 우연히 동작
#   - 둘 다 없음 (Manager 설치 후 재시작, CI, 패키지 설치) → 노드 0개
# 마지막이 사용자에게 "노드가 안 보인다"로 나타난다. 이 테스트는 그것을
# 만들어 진짜 실패를 재현한다. 앞의 둘 중 하나만 제거하면 구버그가 통과해
# 버린다 — 실제로 둘 다 걸렸고, 하나만 걸었을 때는 검증이 안 됐다.
_saved_path = list(sys.path)
sys.path[:] = [p for p in sys.path
               if p and os.path.abspath(p) != os.path.dirname(PKG)
               and os.path.abspath(p) != PKG]
for _g in list(sys.modules):
    if _g.startswith("GoRi-"):
        del sys.modules[_g]
_pack, _sysname = _load_like_comfyui(PKG)
_say(f"  (sys.modules 이름: {_sysname})")
_nodes = sorted(getattr(_pack, "NODE_CLASS_MAPPINGS", {}))
_display = sorted(getattr(_pack, "NODE_DISPLAY_NAME_MAPPINGS", {}))

check("두 노드가 모두 등록됨", len(_nodes) == 2, str(_nodes))
check("카메라 노드 등록", "GoRi_CameraDirectorEncodeSkills" in _nodes, str(_nodes))
check("키퍼 노드 등록", "GoRi_ConsistencyKeeper" in _nodes, str(_nodes))
check("표시 이름도 등록됨", len(_display) == 2, str(_display))
# 회귀: 로드 실패 시 NODE_CLASS_MAPPINGS 가 빈 dict 로 조용히 통과했던 것.
check("NODE_CLASS_MAPPINGS 가 비어 있지 않음 (조용한 실패 방지)",
      len(_nodes) > 0, "하위 모듈 로드 실패 시 이 검사가 잡는다")

# 웹 폴더. 프런트엔드 JS 가 여기서 로드된다 — 이게 없으면 레퍼런스 슬롯
# 점진 노출(9번·10번 이미지 단자)이 동작하지 않는다.
_wd = getattr(_pack, "WEB_DIRECTORY", None)
check("WEB_DIRECTORY 등록됨", bool(_wd), repr(_wd))
if _wd:
    check("웹 폴더가 실제로 존재함", os.path.isdir(os.path.join(PKG, _wd)),
          _wd)
    check("웹 폴더에 JS 가 들어 있음",
          os.path.isfile(os.path.join(PKG, _wd, "progressive_image_inputs.js")),
          str(os.listdir(os.path.join(PKG, _wd)) if os.path.isdir(os.path.join(PKG, _wd)) else "없음"))

# 상대 임포트가 실제로 동작하는지 — 하위 __init__.py 가
# `from .consistency_keeper import ...` 를 쓰기 때문이다.
# 폴더명을 하드코딩하지 않는다: 로컬은 `GoRi-*`, Registry 배포본은
# `ComfyUI-GoRi-*` / `Comfyui-GoRi-*` 로 대소문자가 섞여 있다(Registry 매핑).
def _subpackage_names():
    return [n for n in sorted(os.listdir(PKG))
            if not n.startswith((".", "_"))
            and os.path.isfile(os.path.join(PKG, n, "__init__.py"))]


_subpkgs = _subpackage_names()
check("하위 모듈이 sys.modules 에 남음 (상대 임포트 경로)",
      len(_subpkgs) == 2 and all(n in sys.modules for n in _subpkgs),
      str([m for m in sys.modules if "GoRi" in m]))
_sub_mods = [m for m in sys.modules
             if any(m.startswith(n + ".") for n in _subpkgs)]
check("하위 모듈의 내부 모듈도 로드됨 (consistency_keeper 등)",
      bool(_sub_mods),
      f"기대: <폴더>.consistency_keeper / 실제: {_sub_mods[:3]}")

# 위 두 건은 **구버그가 우연히 통과하는** 영역이라 더 강한 판정이 필요하다.
# 실측: ComfyUI 가 `__init__.py` 를 경로 기반 이름으로 로드하면 그 모듈에
# `__path__` 가 붙는다. 그러면 Python 은 하위 **디렉터리 이름 자체**를
# 네임스페이스 패키지로 해석해서, sys.path 에 없어도 import 해준다. 즉 옛
# 코드의 `importlib.import_module("."+name)` 는 "상대 임포트 실패 → 절대
# 임포트 → 네임스페이스 패키지" 라는 우연한 경로로 성공한다.
#
# 그래서 **하위 폴더의 docstring(설치 폴더명)으로 판정**한다. 이것은
# `__init__.py` 를 직접 읽어야만 알 수 있어 어떤 우연한 경로로도 우회할 수 없다.
_docs = {}
for _n in _subpkgs:
    _docs[_n] = open(os.path.join(PKG, _n, "__init__.py"), encoding="utf-8").read()
_cam = next((v for v in _docs.values() if "camera-director" in v.lower()), "")
_kep = next((v for v in _docs.values() if "consistency-keeper" in v.lower()), "")
check("Camera docstring 이 설치 폴더명을 안내 (사용자에게 맞는 안내)",
      "GoRi-camera-director" in _cam, _cam[:80].replace("\n", " "))
check("Keeper docstring 이 설치 폴더명을 안내",
      "GoRi-Consistency-Keeper" in _kep, _kep[:80].replace("\n", " "))

# 단독 설치 경로: 하위 폴더만 복사해도 로드돼야 한다(README 방법 B).
for _n in _subpkgs:
    check(f"{_n} 는 단독 설치 가능 (__init__.py 보유)",
          os.path.isfile(os.path.join(PKG, _n, "__init__.py")))

_say(f"\n결과: PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
