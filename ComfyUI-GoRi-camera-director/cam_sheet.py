# -*- coding: utf-8 -*-
"""캐릭터 시트 픽셀 판별과 가드."""

from __future__ import annotations

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
try:
    from .cam_subject import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_subject import *  # noqa: F403


__all__ = [
"CHARACTER_SHEET_NEGATIVE", "CHARACTER_SHEET_PEOPLE_NEGATIVE", "CHARACTER_SHEET_VIEWS", "_SHEET_MIN_PANELS", "_SHEET_MIN_SPACING_RATIO", "_SHEET_MIN_CELL_SIMILARITY", "_SHEET_PROFILE_W", "_SHEET_SIG_GRID", "_column_profile", "_row_profile", "_panels_from_profile", "_axis_spacing_ratio", "_best_axis", "_sheet_cell_boxes", "_cell_signature", "_cell_similarity", "_sheet_normalize", "_looks_like_sheet", "sheet_like_slots", "_np_as_rgb", "character_sheet_guard"
]


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
            except Exception as _e:
                # 왜(Why) 말하나 (2026-10-07 라운드 2): 변환이 죽으면 그 슬롯의
                # 시트 판정만 조용히 빠진다 — "연결은 됐는데 판정이 없다" 의
                # 원인이 로그에 없었다. 한 번만 말하고 다음 슬롯으로 간다.
                _note_once("camera.sheet_slot_rgb",
                           "[Camera Director] 시트 검사 중 이미지 변환 실패"
                           f"(슬롯 {label} 건너뜀): "
                           f"{type(_e).__name__}: {str(_e)[:80]}")
                continue
            if arr is None:
                continue
            if _looks_like_sheet(arr).get("sheet"):
                slots.append(str(label))
    except Exception as _e:
        # 루프 자체가 죽으면 앞서 본 슬롯까지만 결과가 남는다 — 그 사실을
        # 남긴다(조용한 부분 결과가 원인 없는 오판을 만든다).
        _note_once("camera.sheet_slots_loop",
                   "[Camera Director] 시트 슬롯 검사 중단 — 연결된 참조를 "
                   f"전부 검사하지 못했습니다: {type(_e).__name__}: "
                   f"{str(_e)[:80]}")
    return slots


def _np_as_rgb(img):
    """PIL 이미지·torch 텐서·numpy 배열 → numpy(H,W,3) float32 0~1. 실패 시 None.

    계약 (2026-10-05): 반환 배열은 입력 텐서와 **메모리를 공유할 수 있다**
    (범위 내 clip 생략 최적화 — 0~1 입력에선 뷰를 돌려준다). 호출자는
    반드시 **읽기 전용**으로 다룬다 — 제자리 수정하면 LoadImage 원본
    텐서가 오염된다. 현 소비자(_sheet_normalize→_looks_like_sheet,
    sheet_like_slots)는 전부 읽기 전용임을 실측으로 확인했다.
    """
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
            if a.ndim != 3 or a.shape[2] < 3:
                return None
            a = _np.clip(a[..., :3], 0.0, 1.0)
        else:
            a = _np.asarray(img, dtype=_np.float32)
            if a.ndim == 2:
                a = a[..., None].repeat(3, axis=2)
            if a.ndim == 4:
                a = a[0]
            if a.ndim != 3 or a.shape[2] < 3:
                return None
            _mx = float(a.max())
            if _mx > 1.5:
                a = a / 255.0
                _mx = 1.0
            a = a[..., :3]
            # 왜(Why) 범위가 정해져 있으면 clip 을 생략하나 (2026-10-05 실측
            # 재측정, ComfyUI 런타임): 위 3659 의 축소-금지 설계는 그대로고
            # 이 최적화는 **값을 하나도 바꾸지 않는다**. ComfyUI LoadImage
            # 텐서는 이미 0~1 float32 라 clip 이 항등연산인데, 예전엔 무조건
            # 복사했다. 실측: 4296x7696 에서 103ms->43ms(2.4배), 10896x6800
            # 에서 234ms->126ms(1.9배), 일시 복사 889MB 제거. 출력은
            # np.array_equal 로 bit 단위 동일을 확인했고, 최대치가 1.0~1.5
            # 사이이거나 음수가 있으면(드문 0~1 초과 데이터) 종전대로 clip
            # 한다. uint8 HWC 경로도 299ms->219ms(4296x7696).
            if _mx <= 1.0 and float(a.min()) >= 0.0:
                pass
            else:
                a = _np.clip(a, 0.0, 1.0)
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
