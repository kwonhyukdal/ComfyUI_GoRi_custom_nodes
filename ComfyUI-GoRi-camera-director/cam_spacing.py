# -*- coding: utf-8 -*-
"""피사체 간격 측정과 간격 가드."""

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
"SPACING_GRID", "SPACING_SKIN_CHROMA", "SPACING_RG", "SPACING_TOUCH_RATIO", "SPACING_APART_RATIO", "SPACING_FAR_RATIO", "SPACING_HEAD_BAND", "_skin_score", "subject_spacing", "spacing_guard", "spacing_log_text"
]


# ---------------------------------------------------------------------------
# 픽셀 기반 공간 측정 (2026-09-28)
#
# 왜(Why): topic에 "벽에 밀어붙였다"를 사용자가 직접 써야만 접촉 가드가 켜졌다.
# 그런데 접촉/간격은 기하 사실이므로 픽셀에서 읽는 것이 정확하다. 노드에 이미
# 있는 _reference_lighting_flow와 같은 numpy 저해상도 접근을 재사용한다.
#
# 원리: 저해상도 명암 격자 → "전경으로 보이는" 열 밀도 프로파일 → 봉우리(피사체)
# 사이 골짜기(간격) 폭. 골짜기가 없으면 실루엣이 겹친 것 = 접촉/밀착.
#
# 정직한 한계(중요):
#  1) "붙어 있다"까지만 읽는다. 그게 격투인지 포옹인지는 모른다 — topic 텍스트와
#     합쳐져야 한다.
#  2) 배경(나무·건물)이 봉우리로 잡힐 수 있다. 그래서 보수적으로만 발동시키고
#     측정값을 로그에 남겨 사용자가 확인할 수 있게 한다.
#  3) 새 의존성 없음 (numpy만). MediaPipe를 넣지 않는다.
# ---------------------------------------------------------------------------
SPACING_GRID = 48          # 저해상도 격자 (세로 기준, 가로는 2배 해상도)


# 피부색 임계는 노드가 다루는 HDR/명암 이미지와 맞아야 한다. headshot 텐서는
# 0~1 스케일이고 배경(바=The Rock, 하늘)은 채도가 낮다. 채도 조건을
# 느슨하게 두면 회색 배경까지 "머리"로 잡혀 오탐이 된다(실측 확인).
SPACING_SKIN_CHROMA = 0.12  # 최소 채도


SPACING_RG = 0.05           # 최소 R-G 차이


SPACING_TOUCH_RATIO = 0.03  # 간격이 이보다 작으면 "근접"으로 판단


SPACING_APART_RATIO = 0.05  # 간격이 이보다 크면 "확연히 떨어짐"으로 판단


SPACING_FAR_RATIO = 0.28   # 간격이 이보다 크면 "크게 떨어짐"(화면 양끝 수준)


SPACING_HEAD_BAND = 0.18    # 머리 분리 판정용 상단 밴드 비율 (어깨 위까지만)


def _skin_score(rgb_small):
    """저해상도 RGB 격자 → 피부색 가능성(0~1) 맵. 실패 시 None.

    왜(Why): 머리 검출을 명암 차이로만 하면 어깨선·난간·울타리도 "머리"로
    잡힌다. 사람은 피부색 덩어리로 구분하는 것이 가장 싼 신호다.
    규칙은 고전 RGB 임계(Kovacic et al.)를 0~1 스케일로 옮긴 것으로 새
    의존성이 없다.
    """
    try:
        import numpy as _np
        a = _np.asarray(rgb_small, dtype=_np.float32)
        if a.ndim != 3 or a.shape[2] < 3:
            return None
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        mx = a.max(axis=2)
        mn = a.min(axis=2)
        chroma = mx - mn
        cond = ((r > g) & (r > b) & (chroma > SPACING_SKIN_CHROMA)
                & (_np.abs(r - g) > SPACING_RG))
        return cond.astype(_np.float32)
    except Exception:
        return None


def subject_spacing(image) -> dict:
    """참조 이미지 1장의 피사체 공간 상태를 **기하만** 측정한다. 실패 시 {}.

    반환: {"gap_ratio": 두 덩어리 사이 저밀도 열 비율, "peaks": 덩어리 수,
           "heads": 상단 밴드에서 센 머리 수, "close"/"apart"/"far": bool,
           "v_separate": bool, "bottom_margin": 하단 여백, "subject_ratio": 전경 비율}

    왜 인원수는 여기서 판정하지 않는가:
    실측에서 "1인물"도 접촉으로 오검출됐다. 세그멘테이션 없이 픽셀만으로
    "1명인가 2명인가"를 구분하는 것은 신뢰할 수 없다. 그래서 **픽셀은 공간
    (간격·하단 여백)만 측정하고, 인원수는 topic 텍스트가 맡는다.**
    """
    out = {}
    try:
        import numpy as _np
        import torch as _t
        # 왜(Why) ndim 을 보나 (2026-10-07 라운드 2): 배치 차원이 있을 때만
        # [0] 으로 뺀다. 3D 텐서에 [0] 을 쓰면 첫 행이 잘려 측정이 틀어진다.
        px = (image[0] if isinstance(image, _t.Tensor) and image.ndim == 4
              else image)
        px = px.detach().cpu() if hasattr(px, "detach") else px
        arr = _np.asarray(px, dtype=_np.float32)
        if arr.ndim == 4:
            arr = arr[0]  # (B,H,W,C) → (H,W,C). IMAGE 텐서·배열 모두 허용
        if arr.ndim != 3 or arr.shape[0] < 4 or arr.shape[1] < 4:
            return out
        h, w = arr.shape[0], arr.shape[1]
        if arr.max() > 1.5:
            arr = arr / 255.0
        # 저해상도 격자로 축소 (평균 풀링). 가로를 세로보다 2배 해상도로 둔다
        # — 간격이 작으므로 가로 해상도가 곧 측정 정밀도다.
        # 주의: gh/gw 는 **셀 개수**, rows/cols 는 **셀 픽셀 크기**다.
        # (실측에서 둘을 뒤바꾸어 8x16 격자로 간격을 못 잰 결함 발생)
        # 저해상도 격자: 인덱스 표본(linspace)으로 줄인다. reshape 풀링은
        # 픽셀 수가 격자로 안 나누어떨어지면 잘라 먹거나(실측 256px에 96열 →
        # 5x2 격자로 붕괴) reshape가 실패한다. linspace는 어떤 크기도 정확히
        # gh x gw 격자로 만들고 원본 픽셀도 빠짐없이 쓴다.
        gh = max(1, min(SPACING_GRID, h))
        gw = max(1, min(SPACING_GRID * 2, w))
        yi = _np.linspace(0, h - 1, gh).astype(_np.int64)
        xi = _np.linspace(0, w - 1, gw).astype(_np.int64)
        # RGB와 명암을 같은 격자로 함께 만든다(셀 경계가 어긋나면 안 됨)
        small_rgb = arr[yi][:, xi]
        small = (small_rgb[..., 0] * .299 + small_rgb[..., 1] * .587
                 + small_rgb[..., 2] * .114)
        skin = _skin_score(small_rgb)
        border = _np.concatenate([small[0, :], small[-1, :], small[:, 0], small[:, -1]])
        bg = float(border.mean())
        fg = _np.abs(small - bg)
        cx = _np.linspace(-1, 1, gw, dtype=_np.float32)
        weight = 1.0 - 0.55 * _np.abs(cx)[None, :]
        fg = fg * weight
        thr = float(fg.mean()) + 0.6 * float(fg.std())
        mask = fg > thr
        col = mask.sum(axis=0).astype(_np.float32)
        out["subject_ratio"] = round(float(mask.mean()), 3)
        if out["subject_ratio"] < 0.02:
            return out  # 피사체가 거의 없으면 측정 불가
        cmax = float(col.max())
        if cmax <= 0:
            return out
        # 두 겹 기준: core(50%)는 덩어리 중심, edge(15%)는 덩어리 경계.
        # 간격은 core가 아니라 **edge 기준으로 끊긴 두 덩어리 사이의 폭**으로 잰다.
        # (core로 재면 경계 셀이 통과해 간격이 0으로 계산된다 — 실측 오류)
        edge_thr = max(0.4, cmax * 0.15)
        runs, cur = [], None
        for i, v in enumerate(col):
            if v >= edge_thr:
                cur = [i, i] if cur is None else [cur[0], i]
            elif cur is not None:
                runs.append(tuple(cur))
                cur = None
        if cur is not None:
            runs.append(tuple(cur))
        if not runs:
            return out
        out["peaks"] = len(runs)
        # 실루엣 폭은 **측정하지 않는다** — 실측에서 근경 1인(0.50)이 붙은 2인
        # (0.44)보다 넓게 나와 "몇 명인가" 판정에 쓸 수 없었다. 판정 근거로 쓰면
        # 오탐이 되므로 아예 계산하지 않는다(과잉 계산 제거).
        # 간격: 인접한 덩어리 사이에서 밀도가 낮게 떨어진 열 수
        gap_cells = 0
        for ri in range(len(runs) - 1):
            between = col[runs[ri][1] + 1:runs[ri + 1][0]]
            if between.size == 0:
                continue
            low = int((between < edge_thr).sum())
            if low > gap_cells:
                gap_cells = low
        out["gap_ratio"] = round(gap_cells / float(gw), 3)
        # 접촉은 "서로 다른 덩어리 2개 + 간격 0"일 때만 판정한다.
        # 왜: 두 사람이 맞닿으면 실루엣이 하나로 뭉쳐서 세그멘테이션 없이는
        # 구분할 수 없다. 폭 추정은 근경 1인과 붙은 2인을 구분하지 못해
        # 실측에서 폐기했다(오탐). 모르는 건 말하지 않는 편이 낫다.
        out["close"] = bool(len(runs) >= 2
                            and out["gap_ratio"] <= SPACING_TOUCH_RATIO)
        out["apart"] = bool(len(runs) >= 2
                            and out["gap_ratio"] >= SPACING_APART_RATIO)
        out["far"] = bool(len(runs) >= 2
                          and out["gap_ratio"] >= SPACING_FAR_RATIO)
        # 붙어 있는 경우의 보완 신호: 상단 프로파일의 "머리 개수".
        # 왜(Why): 두 사람이 맞닿으면 몸 실루엣이 하나로 뭉쳐서 간격 측정으로
        # 잡을 수 없다. 하지만 머리 둘은 별개로 세어진다 — 세그멘테이션 없이도
        # 2인 근접을 판별할 수 있는 유일한 신뢰 신호다.
        heads = 0
        try:
            # 상단 밴드는 **어깨 위**로 좁게 잡아야 한다. 넓으면 몸통까지 포함돼
            # 머리 둘이 하나로 뭉개진다(실측: 25% 이상에서 머리 분리 실패).
            top_rows = max(2, int(gh * SPACING_HEAD_BAND))
            top = mask[:top_rows, :]
            tcol = top.sum(axis=0).astype(_np.float32)
            # 머리는 피부색이다. 명암 톤만 보면 어깨선·난간도 "머리"로 잡힌다
            # (실측 오탐). MIX_GUARD의 plastic skin 방어가 이미 피부색을 근거로
            # 쓰고 있으므로 그 근거를 재사용한다. skin 은 위에서 small_rgb로
            # 계산한 값(명암 small 이 아니라 RGB 격자 기준)이다.
            if skin is not None:
                skin_top = skin[:top_rows, :]
                if skin_top.size:
                    tcol = tcol * (1.0 + 0.8 * skin_top.mean(axis=0))
            tmax = float(tcol.max())
            if tmax >= 0.5:
                truns, cur = [], None
                for i, v in enumerate(tcol):
                    if v >= max(0.5, tmax * 0.35):
                        cur = [i, i] if cur is None else [cur[0], i]
                    elif cur is not None:
                        truns.append(tuple(cur))
                        cur = None
                if cur is not None:
                    truns.append(tuple(cur))
                heads = len(truns)
        except Exception:
            heads = 0
        out["heads"] = heads
        # 머리 둘이면서 몸 실루엣이 하나로 뭉친 경우 = 서로 붙어 있는 2인
        if not out["close"] and heads >= 2 and len(runs) == 1:
            out["close"] = True
        row = mask.sum(axis=1)
        nz = _np.nonzero(row)[0]
        if nz.size:
            out["bottom_margin"] = round(float((gh - 1 - int(nz[-1])) / gh), 3)
        else:
            out["bottom_margin"] = None
        # 세로 방향: 위아래로 늘어선 피사체. 행(세로) 밀도 프로파일에
        # "이중 봉우리"가 있는지 본다 — 상단(머리·상체)과 하단(하체)이 서로
        # 떨어진 채 존재하면 세로로 늘어선 배치다.
        # 왜(Why): 누운 자세·계단·상단 부감처럼 화면 상하로 배치된 구도에서
        # 세로 간격이 공간 관계의 핵심인데, 가로만 재면 이 구도를 놓친다.
        # row 는 위에서 이미 1회 계산했다 — 같은 마스크를 두 번 세지 않는다
        # (2026-10-07 라운드 2).
        rowc = row.astype(_np.float32)
        rmax = float(rowc.max()) if rowc.size else 0.0
        v_two = False
        if rmax > 0.5:
            rt = max(0.5, rmax * 0.35)
            rvals = [v >= rt for v in rowc]
            # 연속 True 구간 개수
            runs_n, prev = 0, False
            for on in rvals:
                if on and not prev:
                    runs_n += 1
                prev = on
            v_two = runs_n >= 2
        out["v_separate"] = bool(v_two)
    except Exception:
        return out
    return out


def spacing_guard(measure: dict, topic: str) -> tuple:
    """(positive, negative). 픽셀 측정(거리) × topic(인원수)을 합쳐 판단.

    왜 둘을 합치는가: 픽셀은 "얼마나 떨어져 있는가"를 신뢰성 있게 읽지만
    "몇 명인가/붙었는가"를 세그멘테이션 없이 구분하지 못한다(실측 오검출 확인).
    반대로 인원수는 topic이 정확히 안다. 그래서 **거리는 픽셀이, 인원수는 topic이**
    맡고, 둘이 합의할 때만 문구를 붙인다.

    픽셀이 확실히 아는 것은 "떨어진 거리" 하나뿐이다. 그래서 부각은 "떨어져 있든
    붙어 있든 **측정된 거리를 유지하라**"로 통일한다 — 모델이 참조의 공간 관계를
    깨뜨리는(포옹인데 떨어지게, 떨어져 있는데 겹치게) 실패를 막는 것이 목적.
    """
    try:
        m = measure or {}
        if not m:
            return "", ""
        if not (_is_human_subject(topic or "") or _is_multi_person_request(topic or "")):
            return "", ""
        pos, neg = "", ""
        if m.get("close"):
            pos = ("spatial fidelity: keep the two subjects in contact as in "
                   "the reference — bodies touching with no gap between them")
            neg = "the subjects standing apart with empty space between them"
        elif m.get("far"):
            # 화면 양끝 수준으로 떨어진 구도. "가까이 떨어짐"과 구분한다 --
            # 실측에서 좌우 끝에 선 두 사람(간격 50%)에도 가까운 문구가 붙었다.
            pos = ("spatial fidelity: the two subjects stay far apart at the "
                   "opposite sides of the frame as in the reference, the wide "
                   "empty space between them preserved")
            neg = ("the subjects pulled close together, the wide empty space "
                   "between them filled in")
        elif m.get("apart"):
            pos = ("spatial fidelity: keep the same separation between the "
                   "subjects as the reference — the space between them stays "
                   "the same size, they do not crowd together")
            neg = ("the subjects pushed together into overlapping silhouettes, "
                   "merged into one mass")
        if m.get("v_separate"):
            # 세로로 늘어선 구도 — 가로 거리만 재면 이 배치를 놓친다.
            pos = (pos + ", " if pos else "") + (
                "spatial fidelity: keep the same vertical arrangement as the "
                "reference, one subject higher in the frame than the other, "
                "do not align them on the same level")
        if m.get("bottom_margin") is not None and m.get("bottom_margin", 0) > 0.03:
            # 접지 여부는 한 장에서 확정할 수 없다(바닥이 보이는 게 정상이라
            # 전경이 최하단에 닿는지만 보면 근거가 없다). 대신 **측정 가능한
            # 사실**인 "피사체 아래 남은 여백(=보이는 바닥 비율)"만 유지시킨다.
            # 스케일 가드(인물-사물 비율)와 같은 축의 사실이라 서로 보강된다.
            pos = (pos + ", " if pos else "") + (
                "spatial fidelity: keep the same amount of floor and ground "
                "visible below the subject as in the reference, subject seated "
                "at the same height in the frame")
        return pos, neg
    except Exception:
        return "", ""


def spacing_log_text(measure: dict) -> str:
    """측정값 로그 문자열. 실패 시 ""."""
    try:
        m = measure or {}
        if not m:
            return ""
        bits = []
        if "gap_ratio" in m:
            bits.append(f"간격 {int(m['gap_ratio'] * 100)}%")
        if "peaks" in m:
            bits.append(f"영역 {m['peaks']}개")
        if m.get("close"):
            bits.append("근접")
        elif m.get("far"):
            bits.append("크게 떨어짐")
        elif m.get("apart"):
            bits.append("떨어짐")
        if m.get("v_separate"):
            bits.append("세로 분리")
        if m.get("heads"):
            bits.append(f"머리 {m['heads']}")
        if m.get("bottom_margin") is not None:
            bits.append(f"하단 여백 {int(m['bottom_margin'] * 100)}%")
        return " · ".join(bits)
    except Exception:
        return ""
