# -*- coding: utf-8 -*-
"""참조 얼굴 정합 (registration) — 키퍼 1.9.30.

왜(Why) 이 모듈이 필요한가 (2026-10-13 실측):
키퍼의 당김은 `out + eff * mask * (matched - sampled)` — **픽셀 단위 latent
블렌드**다. `_match_spatial` 은 크기만 맞추고 **정합하지 않는다.** 그래서 참조와
결과물의 구도가 다르면(실측: 참조 = 서 있는 전신, 결과 = 벤치에 앉은 자세)
같은 좌표가 서로 다른 부위를 가리키고, 얼굴 영역 정규화 불일치가 0.8151 로 뜬다.
그 값이 무릎(0.50)을 넘어 감쇠가 당김을 0.20 -> 0.07 로 깎는다 — 즉 신원 복원이
거의 꺼진다.

해법: 결과물에서 검출한 얼굴 키포인트로 **참조 얼굴을 결과물 얼굴에 similarity
정합**한 뒤 그 정렬된 참조를 당김 기준으로 쓴다. 실측(2026-10-13, 픽셀 공간):
얼굴 영역 정규화 불일치 0.2212 -> 0.1647 (-25.5%).

계약:
  - 포즈 키포인트가 한쪽이라도 없으면 None (기존 동작 유지).
  - 변환이 비정상(과도한 배율·회전)이면 None.
  - 채택 여부는 **호출자**가 정한다 — 이 모듈은 후보만 만든다. 호출자는 정합
    전후의 드리프트를 재서 좋아질 때만 쓴다(best-keep). 정합이 해가 되지 않게
    하는 방어선이 여기 있다.
"""

from __future__ import annotations

__all__ = [
    "REG_FACE_IDX", "REG_MIN_PTS", "REG_SCALE_LO", "REG_SCALE_HI",
    "REG_MAX_ROT_DEG", "face_points", "similarity_umeyama", "matrix_is_sane",
    "align_rgb",
]


# 포즈 모델 33점 중 얼굴 0~10 의 안정 6점 — 좌안 내/외, 우안 내/외, 입 좌/우.
# 왜(Why) 귀(7/8)를 빼나: 측면에서 한쪽 귀가 가려지면 대응점이 어긋난다.
# 눈·입은 정면/측면 어디서나 잡히고 서로 멀어 similarity 를 잘 결정한다.
REG_FACE_IDX = (1, 2, 4, 5, 9, 10)

# 최소 대응점 수. 2점이면 similarity 가 결정되지만 잡음에 취약하다.
REG_MIN_PTS = 4

# 배율 상한/하한. 참조와 결과물의 인물 크기가 2배 이상 차이 나면 정합이 아니라
# 다른 그림이다 — 그런 변환은 받지 않는다.
REG_SCALE_LO = 0.5
REG_SCALE_HI = 2.0

# 회전 상한(도). 사람 얼굴은 카메라 롤이 크지 않다 — 이 이상은 오검출이다.
REG_MAX_ROT_DEG = 35.0


def face_points(pose_pts, w, h):
    """포즈 33점 -> 얼굴 6점 픽셀 좌표 (6,2) float64. 불가면 None.

    pose_pts 는 `_pose_landmarks_from_tasks` 가 주는 (x, y) 정규화 튜플 목록.
    """
    try:
        import numpy as _np
        if pose_pts is None or w <= 0 or h <= 0:
            return None
        if len(pose_pts) <= max(REG_FACE_IDX):
            return None
        out = []
        for i in REG_FACE_IDX:
            p = pose_pts[i]
            if isinstance(p, (tuple, list)) and len(p) >= 2:
                x, y = float(p[0]), float(p[1])
            else:
                x = getattr(p, "x", None)
                y = getattr(p, "y", None)
                if x is None or y is None:
                    return None
                x, y = float(x), float(y)
            # 0 좌표는 미검출 표식이다(_pose_landmarks_from_tasks 규약).
            if x <= 0.0 or y <= 0.0:
                return None
            out.append((x * w, y * h))
        if len(out) < REG_MIN_PTS:
            return None
        return _np.asarray(out, dtype=_np.float64)
    except Exception:
        return None


def similarity_umeyama(src, dst):
    """src(N,2) -> dst(N,2) similarity (Umeyama). 반환 (M 2x3, rms) 또는 (None, None).

    왜(Why) cv2.estimateAffinePartial2D 를 안 쓰나: RANSAC 계열은 난수라
    같은 입력에 같은 답이 나오지 않는다. 이 노드는 결정성이 계약이고(같은
    입력 = 같은 출력), 대응점이 6개뿐이라 최소자승으로 충분하다.
    """
    try:
        import numpy as _np
        if src is None or dst is None:
            return None, None
        s = _np.asarray(src, dtype=_np.float64)
        d = _np.asarray(dst, dtype=_np.float64)
        if s.ndim != 2 or d.ndim != 2 or s.shape != d.shape:
            return None, None
        n = int(s.shape[0])
        if n < REG_MIN_PTS or s.shape[1] != 2:
            return None, None
        mu_s = s.mean(axis=0)
        mu_d = d.mean(axis=0)
        sc = s - mu_s
        dc = d - mu_d
        var_s = float((sc ** 2).sum()) / n
        if var_s <= 1e-9:
            return None, None                     # 모든 점이 같은 자리 -> 퇴화
        cov = (dc.T @ sc) / n
        try:
            u, sv, vt = _np.linalg.svd(cov)
        except Exception:
            return None, None
        # 반사 방지: det 가 음수면 마지막 특이벡터의 부호를 뒤집는다.
        dsign = _np.sign(_np.linalg.det(u @ vt))
        if dsign < 0:
            u = u.copy()
            u[:, -1] *= -1.0
        r = u @ vt
        c = float(sv.sum() * (dsign if dsign != 0 else 1.0)) / var_s
        if not (c == c) or abs(c) <= 1e-12:
            return None, None
        t = mu_d - c * (r @ mu_s)
        m = _np.zeros((2, 3), dtype=_np.float64)
        m[:, :2] = c * r
        m[:, 2] = t
        # 잔차 RMS — 정합이 실제로 맞았는지 호출자가 볼 수 있게 함께 준다.
        proj = (c * (r @ s.T)).T + t
        rms = float(_np.sqrt(((proj - d) ** 2).sum(axis=1).mean()))
        return m, rms
    except Exception:
        return None, None


def matrix_is_sane(m):
    """변환이 사람 얼굴 정합으로 납득 가능한 범위인지. 부적합이면 False.

    배율(scale)과 회전(rotation)을 본다. 이동은 제한하지 않는다 — 구도가
    다른 것이 이 기능의 전제라 이동이 큰 것은 정상이다.
    """
    try:
        import math as _m
        import numpy as _np
        if m is None:
            return False
        a = _np.asarray(m, dtype=_np.float64)
        if a.shape != (2, 3):
            return False
        if not _np.all(_np.isfinite(a)):
            return False
        scale = _m.hypot(float(a[0, 0]), float(a[1, 0]))
        if not (REG_SCALE_LO <= scale <= REG_SCALE_HI):
            return False
        deg = abs(_m.degrees(_m.atan2(float(a[1, 0]), float(a[0, 0]))))
        if deg > 360.0:
            deg = abs(deg - 360.0)
        if deg > REG_MAX_ROT_DEG:
            return False
        return True
    except Exception:
        return False


def align_rgb(ref_u8, m, size):
    """ref_u8(HWC uint8)를 변환 m 으로 size=(W,H) 에 워핑. 실패하면 None.

    cv2 가 없으면 None — 호출자는 기존 경로로 떨어진다.
    """
    try:
        import cv2
        if ref_u8 is None or m is None or size is None:
            return None
        w, h = int(size[0]), int(size[1])
        if w <= 0 or h <= 0:
            return None
        return cv2.warpAffine(ref_u8, m, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return None
