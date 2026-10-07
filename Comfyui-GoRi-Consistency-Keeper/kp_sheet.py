# -*- coding: utf-8 -*-
"""캐릭터 시트 패널 탐지·유사도."""

from __future__ import annotations

try:
    from .kp_math import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from kp_math import *  # noqa: F403


__all__ = [
"_PANEL_ON_RATIO", "_PANEL_MIN_W_RATIO", "column_profile", "_panels_from_profile", "SHEET_MIN_PANELS", "SHEET_MAX_WIDTH_RATIO", "SHEET_MIN_SPACING_RATIO", "SHEET_ENFORCE_WIDTH_RATIO", "looks_like_sheet", "detect_panels", "panel_signature", "signature_similarity", "subject_bbox", "_content_crop", "_SHEET_DAMP"
]


# 시트를 통째로 당겼을 때 강도를 얼마나 낮출까 (2단계).
# 왜(Why) 0.5 인가: 시트의 여러 뷰를 한 장의 latent 로 읽으면 신원 신호가
# **평균나고**, 그 평균은 카메라 노드가 텍스트로 못 막는 실패다. 그래도 절반은
# 남긴다 — 시트의 여하 시점/각도 정보가 완전히 버려지는 것도 손실이기 때문.
_SHEET_DAMP = 0.5


# ---------------------------------------------------------------------------
# 캐릭터 시트 패널 검출 (2026-09-28)
#
# 왜(Why): 사용자가 캐릭터 시트를 물리는 목적은 **신원 일관성**이다. 실사용
# 표준 구조는 정면·후면 전신 + 상부얼굴 정면·후면 + 좌우 측면(한 사람)이다.
# 이 참조를 통째로 신원 소스로 쓰면 6개 뷰의 신원 신호가 **평균**나지만,
# 그건 카메라 노드가 텍스트로는 못 막는 실패다(카메라는 시트를 한 덩어리로
# 보기 때문이다). Keeper는 픽셀로 "몇 개인지"를 세지 않는다 — 대신 시트인지
# 확인하고, 결과와 가장 잘 맞는 **패널 하나**를 고른다(상관 계산).
#
# 왜(Why) 한계 — 패널과 결과는 공간 정렬이 되어 있지 않다. 정면 전신 패널을
# 허리 위 반신샷으로 끌어오면 위치가 안 맞아 오히려 나빠진다. 그래서 **프레이밍
# 유사도(인물 bbox 종횡비·상대 크기)**를 재서, 맞을 때만 그 패널을 신원
# 소스로 쓸 수 있게 한다. 이것도 추측이 아니라 산술이다.
#
# 단계(2026-09-28): 1단계는 **검출 + 게이트 + 로그만**. 강도 변경은 하지
# 않는다 — 콘솔로 실제 패널 수와 게이트 값을 확인한 뒤 2단계에서 반영한다.
# (왜 조용히 바꾸지 않는가: 잘못 감지했을 때 조용히 신원 복원이 약해지면
#  원인을 알 수 없다. 경고와 로그가 전부다.)
# ---------------------------------------------------------------------------

# 패널 내 문자(성공) / 패널 사이 공백(실패)의 상대 임계값. 시트는 콘텐츠가
# 조밀하고 사이가 비어 있는 배치를 갖는다.
_PANEL_ON_RATIO = 0.30


# 하나의 패널로 인정할 최소 너비 비율. 너무 좁은 띠(테두리, 텍스트)는 제외.
_PANEL_MIN_W_RATIO = 0.04


def column_profile(arr) -> "object | None":
    """RGB 배열 → 열별 "평탄하지 않은 정도" 프로파일 (W,). 실패 시 None.

    왜(Why) 에지맵(16x16)이 아니라 **전 해상도**인가: 실사용 시트는 6뷰를
    일자로 늘어놓는데, 16x16으로 줄이면 패널 하나가 2~3칸에 불과해 세 개만
    잡히는 문제가 실제로 발생했다(합성 시트에서 검출됨). 패널 경계는 원본
    해상도에서만 의미가 있다.
    프로파일 = 각 열의 표준편차. 패널 사이 빈 공간은 균일(STD≈0)이고,
    실루엣이 있는 패널 열은 값이 크다. 그래서 "평탄하지 않은 연속 구간"이
    곧 패널이다.
    """
    try:
        import numpy as _np
        if arr is None or getattr(arr, "ndim", 0) != 3:
            return None
        a = _np.clip(_np.asarray(arr, dtype=_np.float32), 0.0, 1.0)
        if a.shape[0] < 2 or a.shape[1] < 8:
            return None
        lum = (a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114)
        return lum.std(axis=0).astype(_np.float32)
    except Exception:
        return None


def _panels_from_profile(profile, width: int, on_ratio: float = _PANEL_ON_RATIO,
                         min_w_ratio: float = _PANEL_MIN_W_RATIO) -> list:
    """열 프로파일 → 연속 콘텐츠 구간 [(x0, x1), ...]."""
    try:
        import numpy as _np
        p = _np.asarray(profile, dtype=_np.float32)
        if p.ndim != 1 or p.size < 8:
            return []
        peak = float(p.max())
        if peak <= 1e-6:
            return []                               # 전부 평탄 → 시트 아님
        on = p >= peak * on_ratio
        min_w = max(1, int(round(width * min_w_ratio)))
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


# 시트 판별 임계값. 왜(Why) 실측 보정값이다.
#   실사용 시트 3장 : n=4 / 간격비 0.77~0.95
#   실사용 사진 10장: n=1~2
#
# ⚠ `SHEET_MIN_PANELS` 는 카메라 노드의 것과 **같은 값이어야 한다.**
# 2026-10-01 실측: 키퍼만 `SHEET_MIN_PANELS=3`,
# `SHEET_MAX_WIDTH_RATIO=1.60` 이었고 그 결과 시트 3장 중 **2장**이 "시트 아님"
# 으로 판정되어 강도 감쇠와 패널 대체가 통째로 건너뛰어졌다. 카메라만 고쳤던
# 것이었다(8d2fd86 이전). 두 판정이 어긋나면 키퍼만 잘못 동작한다.
# 간격비(`SHEET_MIN_SPACING_RATIO`)는 **일부러 다르다**(키퍼 0.60 / 카메라
# 0.45, 2026-10-01 실측 근거) — `tests/test_pack.py` 가 두 관계를 함께 고정한다.
# 크로스 폴더 공용 모듈은 만들지 않는다 — 각 폴더가 **단독 배포 단위**라
# (CI 가 `cd 폴더 && python tests/test_node.py` 로 독립 실행하고 __init__.py
# docstring 도 "이 폴더를 복사 후 재시작" 이라고 적었다) 공용 모듈을 두면
# 단독 설치가 깨진다. 대신 `tests/test_pack.py` 에 교차 검사를 둔다.
#
# 왜(Why) 간격만 보는가 (2026-10-01 실측): 예전엔 폭 균일성(`wreg`)까지
# 요구했는데 **진짜 시트 2장을 놓쳤다.** 원본 시트는 2신세(좁은 패널 2개) +
# 4얼굴(넓은 패널 4개) 구성이라 패널 폭이 원래 다르다 — 실측 wreg 이
# 2.47 / 3.22 로 컸고 1.60 선에 걸렸다. 패널 폭은 시트 구성에 따라 본질적으로
# 다르므로 판정 근거로 쓸 수 없다. 그런데도 반환 dict 와 로그에는 남긴다 —
# 근거가 사라지면 또 "왜 3이었나" 를 되짚게 된다.
SHEET_MIN_PANELS = 4


SHEET_MAX_WIDTH_RATIO = 1.60


# 왜(Why) 간격선은 카메라(0.45)가 아니라 **0.60 그대로인가**: 카메라와 같게
# 낮추려면 근거가 있어야 한다. 13장 전수에서 `n>=4` 를 만족하면서 `greg<0.45`
# 인 표본이 **0개**다 — 즉 낮춰도 이 표본에서 오탐이 늘지 않지만, 그렇다고
# 낮출 근거가 생긴 것도 아니다. 근거 없는 완화를 하지 않는다(WORK_STATUS 10-6
# 원칙: 실측이 받쳐주지 않으면 값을 바꾸지 않는다). 실사용 사진이 더 쌓이면
# 그때 다시 잰다.
SHEET_MIN_SPACING_RATIO = 0.60


# 왜(Why) wreg 를 통과 조건에서 빼고 **기록만** 하는가: 위 실측처럼 패널 폭은
# 시트 구성에 따라 본질적으로 다르므로 판정 근거로 쓸 수 없다. 그런데도
# 로그와 반환 dict 에는 남긴다 — 근거가 사라지면 또 "왜 3이었나" 를 되짚게 된다.
SHEET_ENFORCE_WIDTH_RATIO = False


def looks_like_sheet(panels) -> dict:
    """패널 구간이 시트인지 판정. {"sheet": bool, "n": int, "wreg": float,
    "greg": float}. 패널이 최소 수보다 적으면 시트로 보지 않는다.
    """
    out = {"sheet": False, "n": len(panels or []), "wreg": 0.0, "greg": 0.0}
    try:
        pn = panels or []
        out["n"] = len(pn)
        if len(pn) < SHEET_MIN_PANELS:
            return out
        ws = [max(1, x1 - x0) for x0, x1 in pn]
        cs = [(x0 + x1) / 2.0 for x0, x1 in pn]
        gaps = [cs[i + 1] - cs[i] for i in range(len(cs) - 1)]
        wreg = max(ws) / min(ws)
        greg = (min(gaps) / max(gaps)) if gaps and max(gaps) > 0 else 0.0
        out["wreg"] = round(wreg, 2)
        out["greg"] = round(greg, 2)
        out["sheet"] = (greg >= SHEET_MIN_SPACING_RATIO
                        and (not SHEET_ENFORCE_WIDTH_RATIO
                             or wreg <= SHEET_MAX_WIDTH_RATIO))
        return out
    except Exception:
        return out


def detect_panels(arr) -> list:
    """RGB 배열 → 세로 패널 구간 [(x0, x1), ...]. 시트가 아니면 [].

    왜(Why) 열 방향만 보는가: 실사용 표준 시트는 정면·후면·측면을 **일자로**
    늘어놓은 형태다(사용자 실사용 구조). 최종 시트 판정은 `looks_like_sheet` 가
    하며 패널 4개 이상 + 간격 정규성(≥0.60)을 요구한다 — 이 함수는 구간 후보만
    만든다. 세로로 쌓인 시트는 이번 단계에서 다루지 않는다(미검출 시 조용히
    기존 동작 — 오탐보다 누락이 안전하다).
    """
    prof = column_profile(arr)
    if prof is None:
        return []
    return _panels_from_profile(prof, len(prof))


def panel_signature(arr, x0: int, x1: int) -> "object | None":
    """패널 구간의 에지 시그니처(정규화 8-bin 히스토그램). 비교용.

    왜(Why) 실루엣 경계를 잘라내고 내부만 보는가(2026-09-29 실측):
    원래 16x16 축소 에지맵(`_edge_map_from_rgb`)에 정규화 히스토그램을 얹었는데
    두 가지가 겹쳐 **모든 패널의 시그니처가 정확히 같아졌다**.

    ① 16x16 축소가 패널 내부 구조를 평균으로 지웠다. 줄무늬 간격을 5/40/16/9로
       갈라 만든 4개 패널이 전부 [0.984, 0.008, 0.008, 0...] 로 같았다.
    ② `mag / mx` 정규화가 문제였다. mx는 실루엣 경계의 최대 기울기인데 패널마다
       거의 동률이라, 정규화 후 **가장 강한 에지 하나가 항상 1.0** 이 되고
       나머지는 0으로 뭉개진다 → 히스토그램이 [1, 0, 0, ...] 로 붕괴.

    그래서 (a) 원본 해상도에서 Sobel을 직접 내고 (b) 실루엣 외곽 한 칸을


    잘라내 **내부 텍스처**만 본다. 패널 검출은 별도 함수(`column_profile`,
    전 해상도 열 프로파일)가 이미 담당하므로 축소를 다시 할 이유가 없다.
    """
    try:
        import numpy as _np
        import torch as _t
        import torch.nn.functional as _f
        a = _np.asarray(arr, dtype=_np.float32)
        if a.ndim != 3:
            return None
        w = a.shape[1]
        x0 = max(0, int(x0))
        x1 = min(w, int(x1))
        if x1 - x0 < 6:
            return None
        # 실루엣 외곽 1픽셀(패널 경계 = 가장 큰 기울기)을 제외한다.
        seg = _np.clip(a[:, x0 + 1:x1 - 1], 0.0, 1.0)
        if seg.shape[1] < 4 or seg.shape[0] < 4:
            return None
        lum = seg[..., 0] * .299 + seg[..., 1] * .587 + seg[..., 2] * .114
        t = _t.from_numpy(lum[None, None])
        kx = _t.tensor([[-1., 0., 1.], [-2., 0., 2.], [-1., 0., 1.]])
        ky = kx.t().contiguous()
        gx = _f.conv2d(t, kx[None, None])
        gy = _f.conv2d(t, ky[None, None])
        mag = (gx * gx + gy * gy).sqrt()[0, 0].numpy()
        if mag.size == 0:
            return None
        # mx 정규화는 버린다 — 내부 텍스처의 **분포**가 시그니처이므로
        # 자체 정규화(총합 1)만 하면 크기 차이와 무관해진다.
        mean = float(mag.mean())
        # 왜(Why) kp_math 와 같은 함수를 쓰나 (2026-10-07 감사): 이 공식은
        # kp_math `_edge_mag_from_rgb` 와 한글자도 다르게 복붙돼 있었다 —
        # 이제 한 곳(_noise_floor)에서만 정의된다.
        if mean <= _noise_floor(lum):
            return None                              # 평탄 패널 → 근거 없음
        # 로그 압축: 강한 에지 하나가 전체를 지배하지 않게 한다.
        em = _np.log1p(mag / mean).astype(_np.float32)
        # 시그니처는 **텍스처 밀도**를 본다. 히스토그램 총합 1 정규화는
        # "평탄한 픽셀이 몇 개인가"를 지워버려, 배경이 넓은 샘플과 배경이 좁은
        # 패널을 비교하면 밀도가 **반대로** 읽힌다(실측: 조밀한 줄무늬 샘플이
        # 성긴 패널에 더 높게 매칭됨). 그러므로 상위 절반만 잘라 **에지가 있는
        # 픽셀의 분포**만 남긴다. 그 분포 자체는 총합 1 정규화로 크기 무관하다.
        cut = _np.percentile(em, 60.0)
        em = _np.where(em > cut, em, 0.0)
        peak = float(em.max())
        if peak <= 1e-6:
            return None
        em = em / peak
        hist, _ = _np.histogram(em, bins=8, range=(0.0, 1.0), density=False)
        tot = float(hist.sum())
        if tot <= 1e-6:
            return None
        return hist / tot
    except Exception:
        return None


def signature_similarity(a, b) -> float:
    """두 시그니처의 코사인 유사도 0~1. 비교 불가면 0.0."""
    try:
        import numpy as _np
        if a is None or b is None:
            return 0.0
        va = _np.asarray(a, dtype=_np.float32).ravel()
        vb = _np.asarray(b, dtype=_np.float32).ravel()
        if va.size == 0 or va.size != vb.size:
            return 0.0
        na = float(_np.linalg.norm(va))
        nb = float(_np.linalg.norm(vb))
        if na <= 1e-8 or nb <= 1e-8:
            return 0.0
        # 왜(Why) min 이 바깥에 있나 (2026-10-04 감사 56차): `max(0.0, nan)`
        # 은 0.0 이지만 `min(1.0, nan)` 은 1.0 이다(_safe_strength
        # docstring 참조). 바깥을
        # min 으로 두면 NaN 입력이 docstring 대로 0.0(비교 불가)로 떨어진다.
        # 유한 입력에는 순서와 무관하게 같은 값.
        return min(1.0, max(0.0, float(_np.dot(va, vb) / (na * nb))))
    except Exception:
        return 0.0


def subject_bbox(landmarks):
    """MediaPipe pose landmark → 인물 bbox (x0, y0, x1, y1) 정규화. 실패 None.

    왜(Why) bbox를 쓰는가: "패널이 결과와 맞는지"를 재려면 각 뷰 안에서
    인물이 차지하는 **프레이밍**을 비교해야 한다. 세그멘테이션이 없어도
    랜드마크 33점의 외곽으로 재는 것이면 충분하다.

    왜(Why) w, h 인자를 뺐나:landmark 좌표는 이미 **정규화(0~1)** 라서
    픽셀 크기가 필요 없다. 받던 인자는 `w < 1` 가드에만 쓰였고 실제로는
    `box_s`에 ref_arr의 너비를 넘기는 실수도 있었다(의도 뒤섞임).

    왜(Why) 튜플과 객체 둘 다 받는가: landmark 의 모양이 **경로마다 다르다.**
    구 `mediapipe.solutions` 는 `.x`/`.y` 속성 있는 객체를 줬고, tasks API
    경로(`_pose_landmarks_from_tasks`)는 `(x, y)` 튜플을 준다. 속성만 보면
    튜플에서는 전부 None 이 되어 조용히 **bbox=None** 이 되고, 그 결과 프레이밍
    판정이 tasks 전환(2026-09-30) 이후 조용히 죽어 있었다 — 실측으로 확인했다
    (33점은 제대로 나오는데 bbox만 None). 한쪽만 받던 어느 쪽이든 조용히 죽으므로
    둘 다 받는다.
    """
    try:
        import numpy as _np
        if landmarks is None:
            return None
        xs, ys = [], []
        for lm in landmarks:
            if isinstance(lm, (tuple, list)) and len(lm) >= 2:
                x, y = lm[0], lm[1]
            else:
                x = getattr(lm, "x", None)
                y = getattr(lm, "y", None)
            if x is None or y is None:
                continue
            if float(x) <= 0.0 or float(y) <= 0.0:
                continue
            xs.append(float(x))
            ys.append(float(y))
        if len(xs) < 8:
            return None
        arr = _np.asarray([xs, ys], dtype=_np.float32)
        # 머리 위쪽(0.02)·발 아래쪽(1.02)로 약간 여유 → 어깨만 나온 뷰가
        # 극단적으로 작아지는 것을 방지.
        x0 = max(0.0, float(arr[0].min()) - 0.02)
        x1 = min(1.0, float(arr[0].max()) + 0.02)
        y0 = max(0.0, float(arr[1].min()) - 0.02)
        y1 = min(1.0, float(arr[1].max()) + 0.02)
        if x1 - x0 < 0.02 or y1 - y0 < 0.02:
            return None
        return (x0, y0, x1, y1)
    except Exception:
        return None


def _content_crop(arr, tol=0.06):
    """균일한 배경을 잘라 내용만 남긴다. 실패하면 원본 그대로.

    왜(Why) 필요한가 (2026-09-30 실측): 시트 패널은 세로로 흰 여백이 크다.
    패널을 x 로만 자르면 185x1888 이 남는데, 그 흰 띠 때문에 33점 검출이
    불안정해진다(실측: 4개 중 1개가 미검출). 여백을 잘라 185x711 로 만들면
    전 패널이 검출되고 프레이밍 게이트도 통과한다(0.747).
    """
    try:
        import numpy as _np
        a = _np.asarray(arr, dtype=_np.float32)
        if a.ndim != 3 or a.shape[0] < 4 or a.shape[1] < 4:
            return arr
        lum = a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114
        m = _np.abs(lum - float(_np.median(lum))) > float(tol)
        rows = _np.nonzero(m.any(axis=1))[0]
        cols = _np.nonzero(m.any(axis=0))[0]
        if not len(rows) or not len(cols):
            return arr
        out = a[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
        return out if out.size else arr
    except Exception:
        return arr
