# -*- coding: utf-8 -*-
"""카메라 구도·렌즈·앵글·조명·그레이드·무빙 조항 테이블과 조립."""

from __future__ import annotations

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403


__all__ = [
"PRESETS", "KEYWORDS", "AUTO", "CUSTOM", "SHOT", "TOPIC_SHOT_PHRASES", "_longest_shot_label", "LENS", "ANGLE", "COMPOSITION", "LIGHTING", "GRADE", "MOTION", "SPEED", "AMPLITUDE", "DEFAULTS", "_TABLES", "preset_names", "topic_shot_label", "rules", "FRAMING_LIGHTING_RULES", "apply_framing_lighting", "resolve_rules_camera", "_motion_clause", "build_clauses", "image_metrics", "_reference_lighting_flow", "_lighting_clash", "apply_image_hints", "build_camera_conditioning"
]


PRESETS = _load("presets.json", {})


KEYWORDS = _load("keywords_ko_en.json", {})


AUTO = "자동 (auto)"


CUSTOM = "직접 설정 (custom)"


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
    "시네마틱 필릭 (cinematic)": "cinematic film grade, rich contrast, subtle grain",
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


SPEED = {"느림 (slow)": "slow", "보통 (normal)": "", "빨름 (fast)": "fast"}


AMPLITUDE = {"약간 (subtle)": "subtle", "보통 (normal)": "", "강하게 (dramatic)": "dramatic"}


# 규칙(auto) tier 기본값 — 키워드 미매칭 시 사용
DEFAULTS = {
    "shot": "중경 (MS)", "lens": "50mm 표준 (standard)", "angle": "수평 (eye-level)",
    "composition": "삼분할 (rule of thirds)", "lighting": "흐린 부드러움 (soft overcast)",
    "grade": "시네마틱 필릭 (cinematic)", "motion": "없음 (none)",
    "motion2": "없음 (none)",
    "speed": "보통 (normal)", "amplitude": "약간 (subtle)",
}


_TABLES = {
    "shot": SHOT, "lens": LENS, "angle": ANGLE, "composition": COMPOSITION,
    "lighting": LIGHTING, "grade": GRADE, "motion": MOTION,
    "motion2": MOTION,
    "speed": SPEED, "amplitude": AMPLITUDE,
}


def preset_names() -> list:
    return [AUTO] + list(PRESETS.keys()) + [CUSTOM]


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
        px = image[0] if isinstance(image, _t.Tensor) else image
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

def _motion_clause(cam: dict, key: str) -> str:
    """무빙 1개 분량의 영문 조항. 없음·빈값이면 "" (복합 무빙 공용)."""
    label = cam.get(key, "")
    text = MOTION.get(label, "")
    if not text:
        return ""
    if label == "정지 (static)":
        return text
    bits = [AMPLITUDE.get(cam.get("amplitude"), ""),
            SPEED.get(cam.get("speed"), ""), text]
    return " ".join(b for b in bits if b) + " camera movement"


def build_clauses(cam: dict) -> list:
    parts = [
        SHOT.get(cam.get("shot"), ""),
        LENS.get(cam.get("lens"), ""),
        ANGLE.get(cam.get("angle"), ""),
        COMPOSITION.get(cam.get("composition"), ""),
        LIGHTING.get(cam.get("lighting"), ""),
        _motion_clause(cam, "motion"),
        _motion_clause(cam, "motion2"),
    ]
    # 동일 문구 중복 제거 (예: motion/motion2 둘 다 정지).
    out = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return out


def build_camera_conditioning(cam: dict) -> str:
    """Build only the camera direction used by the public conditioning node.

    This intentionally excludes scene identity, anatomy, skin, outfit, and
    quality guard text. The public conditioning path combines it with an
    upstream prompt string before a single final CLIP encode.
    """
    parts = [", ".join(build_clauses(cam)), GRADE.get(cam.get("grade"), "")]
    return ". ".join(part for part in parts if part) + "."
