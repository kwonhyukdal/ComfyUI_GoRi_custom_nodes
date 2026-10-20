# -*- coding: utf-8 -*-
"""카메라 구도·렌즈·앵글·조명·그레이드·무빙 조항 테이블과 조립."""

from __future__ import annotations

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403


__all__ = [
"PRESETS", "KEYWORDS", "AUTO", "CUSTOM", "SHOT", "TOPIC_SHOT_PHRASES", "_longest_shot_label", "LENS", "ANGLE", "COMPOSITION", "LIGHTING", "GRADE", "MOTION", "SPEED", "AMPLITUDE", "DEFAULTS", "_TABLES", "preset_names", "topic_shot_label", "rules", "FRAMING_LIGHTING_RULES", "apply_framing_lighting", "resolve_rules_camera", "_motion_clauses", "split_multi", "normalize_multi_value", "grade_clauses", "build_clauses", "image_metrics", "object_color_name", "_OBJECT_COLOR_PALETTE", "_reference_lighting_flow", "_lighting_clash", "apply_image_hints", "build_camera_conditioning"
]


PRESETS = _load("presets.json", {})


KEYWORDS = _load("keywords_ko_en.json", {})


AUTO = "자동 (auto)"


CUSTOM = AUTO  # deprecated alias (backward compat); use AUTO


# 옛 라벨 → 지금 라벨. 저장된 워크플로가 조용히 "자동" 으로 떨어지지 않게 한다.
# 2026-10-18: speed 의 "빨름 (fast)" 는 오타였다 (바른 표기 "빠름").
# 2026-10-19: grade 의 "시네마틱 필릭" 도 오타였다 — 영문 조항이
#             "cinematic film grade" 이므로 한글은 "필름" 이 맞다.
_LABEL_ALIASES = {
    "빨름 (fast)": "빠름 (fast)",
    "시네마틱 필릭 (cinematic)": "시네마틱 필름 (cinematic)",
}


# ---------------------------------------------------------------------------
# 목록 A — 한글 라벨 → 영문 카메라 조항 (드롭다운 표기와 1:1)
# ---------------------------------------------------------------------------

SHOT = {
    "극접 (ECU)": "extreme close-up shot",
    "근접 (CU)": "close-up shot",
    "중근접 (MCU)": "medium close-up shot",
    "중경 (MS)": "medium shot",
    "전신 (FS)": "full body shot",
    "원경 (WS)": "wide shot",
    "극원경 (EWS)": "extreme wide shot",
}


TOPIC_SHOT_PHRASES = {
    "극접 (ECU)": ("extreme close-up shot", "extreme closeup shot", "ecu shot",
                   "극접", "extreme close-up"),
    "근접 (CU)": ("close-up shot", "closeup shot", "close up shot", "cu shot",
                  "근접"),
    "중근접 (MCU)": ("medium close-up shot", "medium closeup shot", "mcu shot",
                    "중근접", "medium close-up"),
    "중경 (MS)": ("medium shot", "mid shot", "중경"),
    "전신 (FS)": ("full-body shot", "full body shot", "full-length shot", "fs shot",
                  "전신", "full body", "full-body"),
    "원경 (WS)": ("wide shot", "ws shot", "원경"),
    "극원경 (EWS)": ("extreme wide shot", "extreme wide-shot", "ews shot",
                    "극원경", "extreme wide"),
}


def _longest_shot_label(text: str, exclude: str = "") -> str:
    """텍스트에서 샷 구문을 찾되, 가장 길게(구체적으로) 일치한 라벨 하나를 반환한다.

    왜(Why): 한글 라벨은 서로를 부분 문자열로 포함한다("중근접"⊃"근접",
    "극원경"⊃"원경"). 단순 any() 순회는 짧은 라벨이 먼저 잡혀 오인한다.
    최장 일치 원칙으로 구체 표현이 이기게 한다. exclude는 최종 확정 샷으로,
    그 라벨의 표현은 무시한다(모순 아님).
    """
    s = (text or "").lower()
    if not s:
        return ""
    best_label, best_len = "", 0
    for label, phrases in TOPIC_SHOT_PHRASES.items():
        if label == exclude:
            continue
        for p in phrases:
            if p in s:
                if len(p) > best_len:
                    best_label, best_len = label, len(p)
            elif p.endswith(" shot"):
                bare = p[:-5]
                if len(bare.split()) >= 2 and bare in s and len(bare) > best_len:
                    best_label, best_len = label, len(bare)
    return best_label


LENS = {
    "14mm 초광각 (ultra-wide)": "shot on a 14mm ultra-wide lens, strong perspective drama",
    "24mm 광각 (wide)": "shot on a 24mm wide-angle lens, deep scene context",
    "35mm 스냅 (snapshot)": "shot on a 35mm lens, natural documentary perspective",
    "50mm 표준 (standard)": "shot on a 50mm lens, natural perspective",
    "85mm f/1.4 (bokeh)": "shot on an 85mm lens at f/1.4, shallow depth of field, creamy bokeh",
    "135mm 망원 (telephoto)": "shot on a 135mm telephoto lens, compressed background",
    "200mm 망원 (super tele)": "shot on a 200mm telephoto lens, strong background compression",
    "100mm 매크로 (macro)": "shot on a 100mm macro lens, crisp fine detail",
}


ANGLE = {
    "수평 (eye-level)": "eye-level camera angle",
    "로우앵글 (low angle)": "low angle looking up, heroic framing",
    "하이앵글 (high angle)": "high angle looking down",
    "편각 (dutch angle)": "Dutch tilt, diagonal horizon",
    "탑다운 (top-down)": "top-down overhead camera",
    "개미눈 (worm's eye)": "worm's-eye view from ground level",
    "어깨뒤 (OTS)": "over-the-shoulder framing",
    "측면 (side profile)": "side profile framing",
    # 아래 5종은 MIT 라이선스 자료를 규격에 맞게 변형한 것이다 (2026-10-02).
    # 출처: xoxxel/camera-prompts (MIT) — 40종 카메라 앵글의 영어 키워드와
    # 효과 서술. 한글 라벨 + 영어 절(clause) 형식으로 맞추고, 서술은 우리
    # 프롬프트 톤(짧은 절, 마침표 없음)에 맞게 줄였다. 원문 예시는 자동차
    # 기준이라 인물·장면에 통용되는 부분만 취했다.
    # 왜(Why) 새로 넣나: POV·반사·파노라마·후면3/4·히어로는 기존 8종에 없고
    # 사용자가 topic 에 써도 매칭이 안 됐다. 드롭다운에 나오게 한다.
    "일인칭 (POV)": "first-person point of view shot, immersive eye-level presence",
    "반사 (reflection)": "reflection shot with mirrored surface, symmetric depth",
    "파노라마 (panoramic)": "ultra-wide panoramic shot, expansive horizon and scale",
    "후면 3/4 (three-quarter rear)": "three-quarter rear view, back and side visible",
    "와이드 히어로 (wide hero)": "wide hero shot from low angle, subject monumental in environment",
}


COMPOSITION = {
    "삼분할 (rule of thirds)": "rule-of-thirds composition, subject on a power third",
    "중앙 대칭 (centered)": "centered symmetric composition",
    "리딩라인 (leading lines)": "leading lines guiding the eye to the subject",
    "대칭 (symmetry)": "balanced symmetrical composition",
    "프레임 인 프레임 (frame-in-frame)": "framed within a natural frame",
    "여백 (negative space)": "generous negative space around the subject",
    "전경 가림 (foreground occlusion)": "foreground element partially occluding, adding depth",
    "대각선 (diagonal)": "dynamic diagonal composition",
}


LIGHTING = {
    "3점 스튜디오 (three-point)": "controlled three-point studio lighting",
    "골든아워 (golden hour)": "warm golden hour light",
    "블루아워 (blue hour)": "cool blue hour light",
    "흐린 부드러움 (soft overcast)": "soft overcast light, no harsh shadows",
    "창가빛 (window light)": "soft directional window light",
    "네온 (neon)": "neon glow with colored rim highlights",
    "림라이트/실루엣 (rim light)": "strong backlight, bright rim light silhouette",
    "램브란트 (Rembrandt)": "dramatic Rembrandt key light",
    "하이키 (high key)": "bright high-key lighting",
    "로우키 (low key)": "moody low-key lighting, deep shadows",
}


GRADE = {
    "시네마틱 필름 (cinematic)": "cinematic film grade, rich contrast, subtle grain",
    "비비드 포스터 (vivid)": "vivid poster-grade color, deep blacks, punchy highlights",
    "절제된 프리미엄 (premium)": "restrained premium grade, muted tones",
    "틸-오렌지 (teal & orange)": "teal-and-orange color grade",
    "35mm 필름 (film look)": "35mm film look, warm analog grain",
    "클린 커머셜 (commercial)": "clean commercial grade, accurate colors",
    "느와르 (noir)": "high-contrast black-and-white noir look",
    "빈티지 (vintage)": "vintage faded grade",
}


MOTION = {
    "없음 (none)": "",
    "정지 (static)": "locked-off static camera, no camera movement",
    "슬로우 푸시인 (push-in)": "push-in toward the subject",
    "풀백 (pull-back)": "pull-back away from the subject",
    "돌리 인 (dolly in)": "dolly in",
    "돌리 아웃 (dolly out)": "dolly out",
    "트럭 좌 (truck left)": "truck left",
    "트럭 우 (truck right)": "truck right",
    "팬 좌 (pan left)": "pan left",
    "팬 우 (pan right)": "pan right",
    "틸트 상 (tilt up)": "tilt up",
    "틸트 하 (tilt down)": "tilt down",
    "크레인 상 (crane up)": "crane up",
    "크레인 하 (crane down)": "crane down",
    "오빗 (orbit)": "orbit circling around the subject",
    "핸드헬드 (handheld)": "handheld camera with organic drift",
    "스테디캠 (steadicam)": "smooth steadicam glide",
    "홉팬 (whip pan)": "fast whip pan",
    "줌 인 (zoom in)": "slow zoom in",
    "랙포커스 (rack focus)": "rack focus pull between planes",
    "팔로우 (follow)": "follow shot tracking the subject",
}


SPEED = {"느림 (slow)": "slow", "보통 (normal)": "", "빠름 (fast)": "fast"}


AMPLITUDE = {"약간 (subtle)": "subtle", "보통 (normal)": "", "강하게 (dramatic)": "dramatic"}


# 규칙(auto) tier 기본값 — 키워드 미매칭 시 사용
DEFAULTS = {
    "shot": "중경 (MS)", "lens": "50mm 표준 (standard)", "angle": "수평 (eye-level)",
    "composition": "삼분할 (rule of thirds)", "lighting": "창가빛 (window light)",
    "grade": "클린 커머셜 (commercial)", "motion": "없음 (none)",
    "motion2": "없음 (none)",
    "speed": "보통 (normal)", "amplitude": "약간 (subtle)",
}


_TABLES = {
    "shot": SHOT, "lens": LENS, "angle": ANGLE, "composition": COMPOSITION,
    "lighting": LIGHTING, "grade": GRADE, "motion": MOTION,
    "motion2": MOTION,
    "speed": SPEED, "amplitude": AMPLITUDE,
}


# preset 위젯 목록 — 자동 + 프리셋 키들 + 직접 설정
def preset_names() -> list:
    return [AUTO] + list(PRESETS.keys())


# ---------------------------------------------------------------------------
# auto tier — 한/영 병기 키워드 규칙 (최소 백업 사전)
# ---------------------------------------------------------------------------

def image_metrics(image) -> dict:
    """입력 IMAGE(ComfyUI 텐서/배열) → 4개 저비용 수치. 실패 시 {} (노드는 계속 동작).

    - dark        : 평균 밝기 0~1 (어두움)
    - contrast_std: 밝기 표준편차 (대비 척도)
    - vivid       : 색상 채도 평균 (비비드 척도)
    - thirds_bias : 좌/우 ⅓ 밝기 상대차 (삼분할 조감) → {"left"|"right"|"center"}
    """
    out = {}
    try:
        import torch as _t
        import numpy as _np
        # 3D 텐서(H,W,C)를 image[0] 으로 자르면 (W,C) 가 되어 채널이 사라진다 —
        # 2026-10-16 오딧 실측: 3D torch 텐서 입력에서 메트릭 4개가 전부 비었다
        # ({}). 배치 축이 있을 때(4D)만 첫 장을 꺼낸다.
        px = (image[0] if isinstance(image, _t.Tensor) and image.ndim == 4
              else image)
        px = px.detach().cpu() if hasattr(px, "detach") else px
        # 한 번만 float32 배열로 바꾼다. 예전엔 채널마다 asarray 를 따로
        # 불렀는데(3회) 같은 이미지를 세 번 변환했다. 4K 참조 이미지는
        # 채널마다 수 MB 라 세 번 변환한 비용이 그대로 컸다.
        arr = _np.asarray(px, dtype=_np.float32)
        if arr.ndim == 4:
            arr = arr[0]  # (B,H,W,C) → (H,W,C) — 텐서 경로와 같은 1장 기준
        r, g, b = (float(arr[..., i].mean()) for i in range(3))
        lum = arr[..., 0] * .299 + arr[..., 1] * .587 + arr[..., 2] * .114
        # 왜(Why) NaN 을 여기서 막나 (2026-10-07 라운드 2): 손상 픽셀 하나로
        # 평균이 NaN 이 되면 아래 max/min 이 NaN 을 통과시켜 dark=1.0(최대
        # 어둠)이 된다 — 규칙이 조차 조명 없는 야간으로 오판한다. 계산할 수
        # 없는 입력은 수치를 만들지 말고 {} 로 남긴다(노드는 계속 동작).
        if not _np.isfinite(lum).all():
            return out
    except Exception:
        return out
    try:
        h, w = int(lum.shape[0]), int(lum.shape[1])
        if h <= 0 or w <= 0:
            return out
        lmax = float(lum.max())
        scale = 255.0 if lmax > 1.5 else 1.0
        dark = float(max(0.0, min(1.0, 1.0 - lum.mean() / scale)))
        out["dark"] = round(dark, 3)
        out["contrast_std"] = round(float(lum.std() / scale), 3)
        mx = max(r, g, b)
        # 왜(Why) 0 이면 vivid=0 인가: 예전은 max(r,g,b, 1e-6) 로 clamp 해
        # 검정 프레임(0,0,0)에서 (1e-6-0)/1e-6 = 1.0, 즉 "완전 비비드"로
        # 오판했다. 색이 없으면 색 척도도 0 이다.
        out["vivid"] = 0.0 if mx <= 1e-6 else round(
            float((mx - min(r, g, b)) / mx), 3)
        third = max(1, w // 3)
        left = float(lum[:, :third].mean())
        right = float(lum[:, -third:].mean())
        gap = abs(left - right) / max(scale, 1e-6)
        if gap < 0.03:
            out["thirds_bias"] = "center"
        else:
            out["thirds_bias"] = "left" if left > right else "right"
    except Exception:
        return out
    return out


# 참조 사물 대표색 이름표 (2026-10-16). 참조 이미지에서 읽은 색을 프롬프트
# 단어로 바꾼다.
# 왜(Why) 굵은 가족 단위인가: 모델은 hex/RGB 를 이해하지 못하고, 세분 팔레트는
# 경계에서 오판한다 — 의자 참조 실측 크림 (197,191,177) 이 "beige"(거리 22)와
# "light gray"(25) 사이였다. 실제 실패는 "크림이 흰색으로 표백됐다" 수준이라
# 가족 단위로 충분하다.
_OBJECT_COLOR_PALETTE = (
    ("white",       246, 246, 246),
    ("ivory",       236, 230, 212),
    ("cream",       224, 210, 186),
    ("beige",       205, 190, 165),
    ("tan",         190, 160, 120),
    ("brown",       130,  95,  62),
    ("dark brown",   82,  58,  40),
    ("light gray",  198, 198, 200),
    ("gray",        150, 150, 152),
    ("dark gray",    95,  95,  98),
    ("black",        32,  32,  34),
    ("red",         186,  52,  48),
    ("pink",        228, 172, 180),
    ("orange",      224, 138,  58),
    ("yellow",      222, 202,  92),
    ("olive",       128, 128,  72),
    ("green",        80, 138,  80),
    ("dark green",   46,  84,  56),
    ("teal",         68, 138, 138),
    ("blue",         70, 110, 188),
    ("navy",         42,  56, 100),
    ("purple",      118,  84, 158),
    ("burgundy",    118,  40,  56),
)


def object_color_name(image) -> str:
    """참조 1장 → 사물 대표색 이름. 실패 시 "" (노드는 계속 동작).

    왜(Why) 이 규칙인가 (2026-10-16 실측): 의자 참조에서 밝기 150~225 ·
    채도 <45 인 픽셀만 고르면 RGB(197,191,177) 이 나왔고, 같은 이미지에서 손으로
    잰 의자 등받이 (202.7,197.3,183.3) 과 사실상 같다. 흰 벽(밝기>225)과 어두운
    그림자(<150)가 함께 빠진다.

    고른 픽셀이 8% 미만이면(어두운 사물 등) 중앙 60% 의 중앙값으로 폴백한다 —
    임계가 안 맞아 "" 를 내면 방어가 조용히 사라진다. 그래도 못 읽으면 "" 다.
    """
    try:
        import numpy as _np
        arr = image
        if getattr(arr, "ndim", 0) == 4:
            arr = arr[0]
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu()
        arr = arr.numpy() if hasattr(arr, "numpy") else _np.asarray(arr)
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.ndim != 3 or arr.shape[-1] < 3:
            return ""
        arr = arr[..., :3]
        # 입력이 0~1 텐서인지 0~255 배열인지 여기서 한 번만 정한다.
        if float(arr.max()) <= 1.5:
            arr = arr * 255.0
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h <= 0 or w <= 0:
            return ""
        # 64x64 블록 평균. PIL 을 쓰지 않는다 — 이 모듈은 numpy 만 쓴다.
        gh, gw = min(64, h), min(64, w)
        bh, bw = max(1, h // gh), max(1, w // gw)
        small = arr[:gh * bh, :gw * bw].reshape(gh, bh, gw, bw, 3).mean(
            axis=(1, 3))
        flat = small.reshape(-1, 3)
        if not _np.isfinite(flat).all():
            return ""
        bright = flat.mean(axis=1)
        sat = flat.max(axis=1) - flat.min(axis=1)
        m = (bright > 150.0) & (bright < 225.0) & (sat < 45.0)
        if int(m.sum()) >= max(8, flat.shape[0] // 12):
            col = flat[m].mean(axis=0)
        else:
            y0, y1 = int(gh * .2), max(int(gh * .8), int(gh * .2) + 1)
            x0, x1 = int(gw * .2), max(int(gw * .8), int(gw * .2) + 1)
            col = _np.median(small[y0:y1, x0:x1].reshape(-1, 3), axis=0)
        r, g, b = (float(v) for v in col)
        if not _np.isfinite([r, g, b]).all():
            return ""
        best, bd = "", None
        for nm, pr, pg, pb in _OBJECT_COLOR_PALETTE:
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if bd is None or d < bd:
                best, bd = nm, d
        return best
    except Exception:
        return ""


def _reference_lighting_flow(image):
    """reference 1장의 조명 흐름맵 (8x8 정규화). 실패 시 None.

    왜(Why): 2장 이상 믹스 실행에서 참조 간 조명이 충돌하면(한 장은 좌광,
    한 장은 우광) 합성 결과 조명이 깨진다. Keeper의 Retinex 근사와 동일
    원리를 IMAGE 텐서/배열에 적용한다 (numpy만 사용).
    """
    try:
        import numpy as _np
        arr = image
        if getattr(arr, "ndim", 0) == 4:
            arr = arr[0]
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu()
        arr = arr.numpy() if hasattr(arr, "numpy") else _np.asarray(arr)
        arr = _np.asarray(arr, dtype=_np.float32)
        if arr.ndim != 3 or arr.shape[-1] < 3:
            return None
        lum = arr[..., :3].mean(axis=-1)
        if lum.max() > 1.5:
            lum = lum / 255.0
        h, w = lum.shape
        sh, sw = max(1, h // 8), max(1, w // 8)
        small = lum[:sh * 8, :sw * 8].reshape(8, sh, 8, sw).mean(axis=(1, 3))
        small = small - small.mean()
        return (small / (float(small.std()) + 1e-6)).astype(_np.float32)
    except Exception:
        return None


def _lighting_clash(flows) -> float | None:
    """조명 흐름맵들 간 최대 MSE. 1장 이하·실패 시 None."""
    try:
        maps = [f for f in (flows or []) if f is not None]
        if len(maps) < 2:
            return None
        worst = 0.0
        for i in range(len(maps)):
            for j in range(i + 1, len(maps)):
                d = float(((maps[i] - maps[j]) ** 2).mean())
                worst = max(worst, d)
        return worst
    except Exception:
        return None


def apply_image_hints(cam: dict, locked: set, metrics: dict) -> dict:
    """이미지 수치로 DEFAULTS인 항목만 조용히 바꾼다.

    우선순위: 명시 드롭다운 > 키워드 매칭 > 이미지 힌트 > DEFAULTS.
    - dark ≥ 0.62 (조명이 아직도 AUTO일 때만) → 로우키
    - vivid ≥ 0.45 (그레이드가 AUTO일 때만) → 비비드 포스터 (저대비면 프리미엄 절제로)
    - thirds_bias left/right (구도가 AUTO일 때만) → 밝은 쪽이 주체가 아니라는 보수 판단으로
      삼분할 유지 표기 → 보수 힌트이므로 바꾸지 않고 로그용 메모만 남긴다.
    반환: 힌트 적용 내역 리스트를 cam['_hints']에 보관.
    """
    cam = dict(cam)
    hints = []
    if not metrics:
        cam["_hints"] = hints
        return cam
    dark = metrics.get("dark")
    if ("lighting" not in locked and dark is not None and dark >= 0.62
            and cam.get("lighting") == DEFAULTS["lighting"]):
        cam["lighting"] = "로우키 (low key)"
        hints.append(f"이미지 어두움({dark}) → 로우키")
    vivid = metrics.get("vivid")
    if "grade" not in locked and vivid is not None and cam.get("grade") == DEFAULTS["grade"]:
        if vivid >= 0.45:
            cam["grade"] = "비비드 포스터 (vivid)"
            hints.append(f"채도 높음({vivid}) → 비비드 포스터")
        elif float(metrics.get("contrast_std", 1.0)) < 0.10:
            cam["grade"] = "절제된 프리미엄 (premium)"
            hints.append(f"저대비({metrics.get('contrast_std')}) → 절제된 프리미엄")
    bias = metrics.get("thirds_bias")
    if bias in ("left", "right"):
        hints.append(f"좌우 밝기 치우침({bias}) 감지 — 구도는 바꾸지 않음")
    cam["_hints"] = hints
    return cam


def topic_shot_label(topic: str) -> str:
    """주제에 사용자가 이미 카메라 샷을 명시했다면 해당 라벨을 반환한다.

    (Why: mismatch 경고와 동일 기준으로 감지해야 한다. 경고는 뜨는데 샷 확정은
    못 하는 상황 — 사용자가 "전신/풀바디"를 명시했는데 규칙이 근접으로 판정해
    스스로 모순을 경고하는 사례가 있었다. 최장 일치로 "중근접"⊃"근접" 오인도 방지.)
    """
    return _longest_shot_label(topic)


def rules(topic: str):
    """주제 문자열에서 키워드를 찾아 카메라 값(한글 라벨)을 결정한다.
    반환: (camera dict, 키워드로 확정된 항목 집합) — 확정 항목은 이미지 힌트가 건드리지 않는다."""
    cam = dict(DEFAULTS)
    matched = set()
    t = (topic or "").lower()
    for cat in ("shot", "lens", "angle", "lighting", "motion"):
        table = _TABLES[cat]
        for entry in KEYWORDS.get(cat, []):
            val = entry.get("value")
            if val not in table:
                continue
            if any(str(k).lower() in t for k in entry.get("keywords", [])):
                cam[cat] = val
                matched.add(cat)
                break
    for entry in KEYWORDS.get("speed", []):
        val = entry.get("value")
        if val in SPEED and any(str(k).lower() in t for k in entry.get("keywords", [])):
            cam["speed"] = val
            matched.add("speed")
            break
    explicit_shot = topic_shot_label(topic)
    if explicit_shot and cam.get("shot") == DEFAULTS["shot"]:
        cam["shot"] = explicit_shot
        matched.add("shot")
    return cam, matched


# 구도(앵글·샷) → 추천 조명 매칭 표 (우선순위 순).
# 왜(Why): LLM 없는 규칙 환경에서는 조명이 주제 키워드에만 의존해
# 구도와 무관한 기본값(흐린 부드러움)으로 남는 경우가 있었다.
# 구도가 드라마틱한 의도를 담을 때 조명도 세트로 따라가도록 한다.
# 주제 키워드/사용자 고정값이 있으면 절대 덮지 않는다.
FRAMING_LIGHTING_RULES = (
    (("angle", "개미눈 (worm's eye)"), "림라이트/실루엣 (rim light)"),
    (("angle", "로우앵글 (low angle)"), "림라이트/실루엣 (rim light)"),
    (("angle", "편각 (dutch angle)"), "로우키 (low key)"),
    (("shot", "극접 (ECU)"), "램브란트 (Rembrandt)"),
    (("shot", "근접 (CU)"), "램브란트 (Rembrandt)"),
    (("shot", "중근접 (MCU)"), "창가빛 (window light)"),
    (("shot", "원경 (WS)"), "골든아워 (golden hour)"),
    (("shot", "극원경 (EWS)"), "골든아워 (golden hour)"),
)


def apply_framing_lighting(cam: dict, locked: set):
    """조명이 아직 확정되지 않았으면(키워드/고정값 없음) 구도에서 추천 조명을 채운다.

    수동 티어와 LLM 성공 경로는 호출하지 않는다 — 사용자/LLM이 정한 조명을
    건드리지 않기 위함이다. 적용 시 lighting을 locked에 넣어 이미지 힌트도
    덮지 못하게 한다.
    """
    if "lighting" in locked or cam.get("lighting") != DEFAULTS["lighting"]:
        return cam, locked
    for (cat, label), lighting in FRAMING_LIGHTING_RULES:
        if cam.get(cat) == label:
            cam = dict(cam)
            cam["lighting"] = lighting
            locked = locked | {"lighting"}
            break
    return cam, locked


def resolve_rules_camera(topic: str, metrics: dict, fixed_cam, locked: set):
    """규칙 판정 + 명시 고정값 병합 + 추천 조명 + 이미지 힌트 — auto/LLM 폴백 공통 경로.

    왜(Why): run()의 auto 분기와 LLM 폴백 분기에서 동일한 규칙·병합·힌트
    블록이 중복되어 한쪽만 수정되는 퇴행 위험이 있었다.
    """
    camera, matched = rules(topic)
    camera.update(fixed_cam or {})
    locked = locked | matched
    camera, locked = apply_framing_lighting(camera, locked)
    if metrics:
        camera = apply_image_hints(camera, locked, metrics)
    return camera, locked, matched


# ---------------------------------------------------------------------------
# 조립 — 카메라 dict → 영문 조항 (혔스필드 하우스 블록 순서를 따름)
# ---------------------------------------------------------------------------

def split_multi(val) -> list:
    """위젯 값 -> 라벨 리스트. 드롭다운의 다중 선택(콤마 구분)을 지원한다.

    '자동 (auto)'/빈값/None 은 [] (선택 없음). 단일 라벨은 [라벨].
    왜(Why) 콤마인가: ComfyUI 위젯은 문자열 하나만 담는다. 드롭다운이 다중
    선택을 내려면 한 문자열에 담아야 하므로 콤마로 구분한다.
    """
    if not val:
        return []
    return [v.strip() for v in str(val).split(",")
            if v.strip() and v.strip() != AUTO]


def normalize_multi_value(val, table) -> str:
    """위젯 값이 전부 유효 라벨이면 정규화한 콤마 문자열, 아니면 "".

    유효하지 않은 라벨이 하나라도 섞이면 그 기능 전체를 고정하지 않는다
    (규칙/LLM 판정을 막지 않기 위해). 중복은 순서를 유지하며 제거한다.

    옛 라벨은 _LABEL_ALIASES 로 먼저 바꾼다. 왜(Why): 라벨 오타를 고치면
    그 값으로 저장된 워크플로가 조용히 "자동" 으로 떨어져 사용자가 고른
    속도가 사라진다 (2026-10-18 speed 라벨 수정).
    """
    vals = split_multi(val)
    if not vals:
        return ""
    vals = [_LABEL_ALIASES.get(v, v) for v in vals]
    if any(v not in table for v in vals):
        return ""
    seen, out = set(), []
    for v in vals:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return ",".join(out)


def _motion_clauses(cam: dict, key: str) -> list:
    """무빙 슬롯의 영문 조항 목록. 다중 선택이면 각 값의 조항을 순서대로.

    speed/amplitude 는 무빙과 조합되는 보조값이라 첫 값만 쓴다 (다중 선택해도
    한 무빙에 붙는 수식은 하나여야 문장이 성립한다).
    """
    speed = (split_multi(cam.get("speed")) or [""])[0]
    amp = (split_multi(cam.get("amplitude")) or [""])[0]
    out = []
    for label in split_multi(cam.get(key)):
        text = MOTION.get(label, "")
        if not text:
            continue
        if label == "정지 (static)":
            out.append(text)
            continue
        bits = [AMPLITUDE.get(amp, ""), SPEED.get(speed, ""), text]
        out.append(" ".join(b for b in bits if b) + " camera movement")
    return out


def _label_clauses(cam: dict, key: str, table: dict) -> list:
    """라벨 테이블 슬롯의 영문 조항 목록. 다중 선택이면 모두."""
    return [table.get(v, "") for v in split_multi(cam.get(key))]


# 카메라 dict → 영문 절 목록 (샷/렌즈/앵글/구도/조명/무브), 중복 문구 제거
def build_clauses(cam: dict) -> list:
    parts = []
    parts.extend(_label_clauses(cam, "shot", SHOT))
    parts.extend(_label_clauses(cam, "lens", LENS))
    parts.extend(_label_clauses(cam, "angle", ANGLE))
    parts.extend(_label_clauses(cam, "composition", COMPOSITION))
    parts.extend(_label_clauses(cam, "lighting", LIGHTING))
    parts.extend(_motion_clauses(cam, "motion"))
    parts.extend(_motion_clauses(cam, "motion2"))
    # 동일 문구 중복 제거 (예: motion/motion2 둘 다 정지, 다중 선택의 중복).
    out = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return out


def grade_clauses(cam: dict) -> str:
    """그레이드 조항 문자열. 다중 선택이면 콤마로 이어 붙인다.

    왜(Why) build_clauses 와 분리하나: 그레이드는 조항 순서가 아니라 마지막
    색맛 문장으로 따로 붙는 자리가 두 곳(assemble · build_camera_conditioning)
    이라, 다중 지원을 한 함수에 모아 둔다.
    """
    return ", ".join(
        g for g in (GRADE.get(v, "") for v in split_multi(cam.get("grade"))) if g)


def build_camera_conditioning(cam: dict) -> str:
    """Build only the camera direction used by the public conditioning node.

    This intentionally excludes scene identity, anatomy, skin, outfit, and
    quality guard text. The public conditioning path combines it with an
    upstream prompt string before a single final CLIP encode.
    """
    parts = [", ".join(build_clauses(cam)), grade_clauses(cam)]
    return ". ".join(part for part in parts if part) + "."
