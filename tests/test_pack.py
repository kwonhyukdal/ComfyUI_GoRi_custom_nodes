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

# 회귀(2026-09-30): 하위 모듈 로드 실패 로그는 `except` 안에서 나온다. 그 로그가
# 가드 없는 print 면, cp1252 콘솔에서 print 자체가 UnicodeEncodeError 를 던져
# load 실패를 덮어쓴다 → **팩 전체가 조용히 로드되지 않는다**(노드 0개). 실측했다.
# 그래서 정적 문자열 검사 대신, 실제로 깨진 하위 모듈을 붙여 cp1252 로 돌려본다.
# 로딩 방식은 ComfyUI 의 load_custom_node 와 같은 spec_from_file_location +
# submodule_search_locations 다(python <디렉터리> 로는 __main__ 이 없다고 실패한다).
import shutil as _sh
import subprocess as _sp
import tempfile as _tf

_DRIVE = """import importlib.util, sys
d = sys.argv[1].rstrip("\\\\/")
spec = importlib.util.spec_from_file_location(
    "gori_pack_probe", d + "/__init__.py", submodule_search_locations=[d])
m = importlib.util.module_from_spec(spec)
sys.modules["gori_pack_probe"] = m
spec.loader.exec_module(m)
print("NODES=" + ",".join(sorted(m.NODE_CLASS_MAPPINGS)))
"""

_td = _tf.mkdtemp(prefix="gori_pack_")
try:
    _sh.copyfile(os.path.join(PKG, "__init__.py"), os.path.join(_td, "__init__.py"))
    # AAbroken 이 ZZgood 보다 정렬상 먼저 온다. 즉 실패가 먼저 나도 뒤 패키지가
    # 등록돼야 한다 — "하위 모듈 로더가 한 곳에서 멈추지 않는다" 의 진짜 증거.
    for _name, _body in (("AAbroken", "raise RuntimeError('intentional failure')\n"),
                         ("ZZgood", "NODE_CLASS_MAPPINGS = {'GoRi_Probe_Ok': object}\n")):
        _d = os.path.join(_td, _name)
        os.makedirs(_d)
        with open(os.path.join(_d, "__init__.py"), "w", encoding="utf-8") as _fh:
            _fh.write(_body)
    _drive = os.path.join(_td, "_drive.py")
    with open(_drive, "w", encoding="utf-8") as _fh:
        _fh.write(_DRIVE)
    _env = dict(os.environ, PYTHONIOENCODING="cp1252")
    _cp = _sp.run([sys.executable, _drive, _td], capture_output=True, env=_env)
    _txt = ((_cp.stdout or b"").decode("cp1252", errors="replace")
            + ( _cp.stderr or b"").decode("cp1252", errors="replace"))
    check("cp1252 콘솔에서 실패 로그가 죽지 않는다 (팩 무음 로드 방지)",
          _cp.returncode == 0 and "AAbroken" in _txt,
          f"exit={_cp.returncode} " + _txt.strip()[-160:])
    check("깨진 하위 모듈 뒤에도 나머지 노드가 등록된다",
          "GoRi_Probe_Ok" in _txt, _txt.strip()[-160:])
finally:
    _sh.rmtree(_td, ignore_errors=True)

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
# 왜(Why) 이름이 아니라 docstring 으로 폴더를 찾나: 배포 폴더명과 개발 폴더명의
# 대소문자가 일부러 다르다(`ComfyUI-GoRi-camera-director` vs `GoRi-Camera-Director`).
# 문자열로 하드코딩하면 조용히 엉뚱한 곳을 본다 — 이 파일 전체가 그 실측 기록이다.
_cam_dir = next((n for n, v in _docs.items() if "camera-director" in v.lower()), None)
_kep_dir = next((n for n, v in _docs.items() if "consistency-keeper" in v.lower()), None)
_cam = _docs.get(_cam_dir, "")
_kep = _docs.get(_kep_dir, "")
check("Camera docstring 이 설치 폴더명을 안내 (사용자에게 맞는 안내)",
      "GoRi-camera-director" in _cam, _cam[:80].replace("\n", " "))
check("Keeper docstring 이 설치 폴더명을 안내",
      "GoRi-Consistency-Keeper" in _kep, _kep[:80].replace("\n", " "))

# 단독 설치 경로: 하위 폴더만 복사해도 로드돼야 한다(README 방법 B).
for _n in _subpkgs:
    check(f"{_n} 는 단독 설치 가능 (__init__.py 보유)",
          os.path.isfile(os.path.join(PKG, _n, "__init__.py")))

# ── 노드별 독립 버전: 각 하위 패키지는 __version__ 을 둔다 ──
# 왜(Why) 팩 버전(pyproject.toml)만으로는 안 되나 (2026-10-02):
# 팩은 여러 노드를 한 번에 배포하는 관리 단위일 뿐이다. 카메라만 고쳤는데
# 팩 버전을 올리면 키퍼도 바뀐 것처럼 보인다. 각 노드는 자기 변경에만
# 버전을 올린다. 새 노드를 만들면 첫날부터 __version__ 을 둔다 —
# 이 검사가 없으면 빠뜨리고 지나간다.
_say("-- 노드별 독립 버전 --")
for _n in _subpkgs:
    _mod = sys.modules.get(_n)
    _ver = getattr(_mod, "__version__", None) if _mod is not None else None
    import re as _re
    _ok = isinstance(_ver, str) and bool(_re.match(r"^\d+\.\d+\.\d+$", _ver))
    check(f"{_n} 는 독립 버전 보유 (__version__ x.y.z)",
          _ok, str(_ver)[:20])
# 팩 버전과 노드 버전이 같은 출발선에 있는지 (발산 감지용, 강제 아님)
# 팩이 릴리스될 때 노드 버전을 따라잡는다. 어긋나면 로그로만 남긴다.

# ── 크로스 폴더 교차 검사: 시트 판정 임계값이 두 노드에서 어긋나면 안 된다 ──
# 왜(Why) 여기서 하나만 같게 강제하는가 (2026-10-01 실측): 두 노드는 **각각
# 단독 배포 단위**다(CI 가 `cd 폴더 && python tests/test_node.py` 로 각자 돌고,
# `__init__.py` docstring 도 "이 폴더를 복사 후 재시작" 이라고 명시한다). 그래서
# 크로스 폴더 공용 모듈을 만들면 단독 설치가 깨진다 — 그래서 **복제**하고,
# 어긋나는 것을 여기서 잡는다.
#
# 실제로 어긋난 적이 있다: 키퍼만 `SHEET_MIN_PANELS=3` + 폭 균일성 통과 조건을
# 갖고 있어서, 카메라가 시트로 보는 시트 3장 중 **2장**을 키퍼는 "시트 아님"
# 으로 놓쳤다. 강도 감쇠와 패널 대체가 통째로 건너뛰어진다. 한쪽만 고친
# 사고였고, 아무도 눈치채지 못했다 — 그래서 이 검사를 둔다.
_say("-- 시트 판정 임계값 교차 검사 (두 노드가 같은 판정을 내야 한다) --")


def _consts_of(relpath, names):
    """대상 파일을 **ast** 로 파싱해 모듈 수준 상수만 뽑는다.

    왜(Why) import 하지 않고 ast 인가 (2026-10-01 실측, WORK_STATUS 10-24):
    import 하면 mediapipe·torch 로드를 유발하고, 이 파일은 "환경 없이도" 돌아야
    한다. ast 는 값을 문장으로 읽을 뿐 부작용이 없다.
    """
    import ast
    tree = ast.parse(open(os.path.join(PKG, relpath), encoding="utf-8").read())
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id in names:
                try:
                    found[t.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return found


try:
    _cam_c = _consts_of(
        os.path.join(_cam_dir, "camera_director.py"),
        {"_SHEET_MIN_PANELS", "_SHEET_MIN_SPACING_RATIO"})
    _kep_c = _consts_of(
        os.path.join(_kep_dir, "consistency_keeper.py"),
        {"SHEET_MIN_PANELS", "SHEET_MIN_SPACING_RATIO"})
    check("카메라 시트 최소 패널 수를 읽었다", bool(_cam_c), str(_cam_c))
    check("키퍼 시트 최소 패널 수를 읽었다", bool(_kep_c), str(_kep_c))
    if _cam_c and _kep_c:
        # 최소 패널 수: 3장 전수에서 진짜 시트 3장이 전부 n=4 이고 오탐은
        # n=1~2 였다. 한쪽만 다르면 그쪽만 시트를 놓친다.
        check("시트 최소 패널 수가 두 노드에서 같다 (2026-10-01 회귀)",
              _cam_c["_SHEET_MIN_PANELS"] == _kep_c["SHEET_MIN_PANELS"],
              "camera=%s keeper=%s" % (_cam_c.get("_SHEET_MIN_PANELS"),
                                       _kep_c.get("SHEET_MIN_PANELS")))
        # 간격선: 의도적으로 0.60 vs 0.45 다름. 근거 없는 완화를 막기 위해
        # **차이가 낫다** 를 고정한다 — 13장에 greg<0.45 표본이 0개라 낮출 근거가
        # 없다. 나중에 실사용 사진이 쌓여 값을 바꾸려면 이 검사를 함께 고친다.
        check("시트 간격선 차이가 키퍼 0.60 / 카메라 0.45 로 유지된다 "
              "(근거 없이 낮추지 않기)",
              _kep_c["SHEET_MIN_SPACING_RATIO"] == 0.60
              and _cam_c["_SHEET_MIN_SPACING_RATIO"] == 0.45,
              "camera=%s keeper=%s" % (_cam_c.get("_SHEET_MIN_SPACING_RATIO"),
                                       _kep_c.get("SHEET_MIN_SPACING_RATIO")))
except Exception as _e:
    check("시트 임계값 교차 검사 (구문 오류 없음)", False,
          "%s: %s" % (type(_e).__name__, _e))

_say(f"\n결과: PASS={PASS}  FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
