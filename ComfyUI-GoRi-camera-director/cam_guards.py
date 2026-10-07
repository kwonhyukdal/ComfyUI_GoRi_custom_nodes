# -*- coding: utf-8 -*-
"""품질·부위·규모·신원·가구·노출 가드 문구 조립."""

from __future__ import annotations

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
try:
    from .cam_subject import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_subject import *  # noqa: F403
try:
    from .cam_tables import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_tables import *  # noqa: F403
try:
    from .cam_anchors import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_anchors import *  # noqa: F403
try:
    from .cam_sheet import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_sheet import *  # noqa: F403


__all__ = [
"QUALITY_GUARD", "QUALITY_GUARD_ANIMAL", "FACE_IDENTITY_GUARD", "SKIN_COLOR_GUARD", "NEGATIVE_ANATOMY_GUARD", "NEGATIVE_COLOR_CONTAMINATION_GUARD", "_NEGATIVE_BASE_COMMON", "OUTFIT_GUARD", "NUDITY_KEYWORDS", "_is_nudity_request", "nudity_anatomy_guard", "macro_detail_guard", "_camera_failure_modes", "ANATOMY_DETAIL_NEGATIVE", "ANATOMY_COUNT_POSITIVE", "ANATOMY_COUNT_NEGATIVE", "SCALE_SHOTS", "SCALE_COHERENCE_POSITIVE", "SCALE_COHERENCE_NEGATIVE", "_needs_scale_guard", "ETHNICITY_GROUPS", "TRADITIONAL_KEYWORDS", "APPEARANCE_DESCRIBED_KEYWORDS", "ETHNICITY_DIVERSITY_POSITIVE", "ETHNICITY_MODERN_WEAR", "ETHNICITY_STEREOTYPE_NEGATIVE", "_ethnicity_identity_locked", "_ethnicity_guard", "FACE_CRITICAL_SHOTS", "FURNITURE_DNA_POSITIVE", "FURNITURE_DNA_NEGATIVE", "OBJECT_DRIFT_NEGATIVE", "OBJECT_INSTANCE_POSITIVE", "OBJECT_INSTANCE_NEGATIVE", "PARTIAL_OBJECT_NEGATIVE", "_furniture_dna_guard", "_object_dna_slots", "_remove_item_guard", "add_quality_guard", "assemble", "_assemble_negative", "build_camera_negative", "HINT_DEFENSE_NEGATIVE", "MIX_GUARD_POSITIVE", "MIX_GUARD_NEGATIVE", "_pose_reference_guard", "_pose_reference_negative", "build_negative", "APPEARANCE_REF_POSITIVE", "APPEARANCE_REF_NEGATIVE", "APPEARANCE_HAIR_REALISM_POSITIVE", "DETAIL_DEFINITION_POSITIVE", "DETAIL_DEFINITION_NEGATIVE", "BODY_BALANCE_POSITIVE", "BODY_BALANCE_NEGATIVE", "body_proportion_guard", "outfit_guard"
]


QUALITY_GUARD = (
    "high visual quality, "
    "natural human proportions when people are present, "
    "believable hands with five fingers, natural skin texture, "
     "clear facial features, consistent subject identity"
)


# 동물 전용 주제의 대체 가드. 왜(Why) 별도 상수인가: QUALITY_GUARD 의
# "believable hands with five fingers" 는 "개는 사람처럼 그리지 말라"와
# 같은 프롬프트 안에서 정면 충돌한다(2026-09-28 실측). "when people are present"
# 절은 proportions 에만 걸려 있고 손·피부는 무조건 붙는다.
QUALITY_GUARD_ANIMAL = (
    "high visual quality, "
    "correct animal anatomy and natural species proportions, "
    "detailed fur or feather texture, natural coat pattern, "
    "clear eyes, consistent subject identity"
)


FACE_IDENTITY_GUARD = (
    "facial identity lock, preserve original face structure, same eye shape, same nose and mouth, "
    "same jawline, same facial proportions, same age and ethnicity, do not change face identity"
)


SKIN_COLOR_GUARD = (
    # 카메라 기법으로 피부 질감을 살린다. 왜(Why): "균일·매끈·깨끗" 같은
    # 미화 표현은 모델을 에어브러시 방향으로 밀어 플라스틱 피부가 되므로,
    # 모공·결·지향성 광·그레인 같은 촬영 언어로 현실 질감을 지시한다.
    "natural skin tone, realistic skin texture with visible pores and fine detail, "
    "soft directional lighting that reveals natural skin micro-contrast, subtle film grain, "
    "background color does not tint the skin"
)


NEGATIVE_ANATOMY_GUARD = (
    "bad anatomy, deformed anatomy, extra arms, extra limbs, third arm, duplicate arms, "
    "malformed hands, extra fingers, missing fingers, fused fingers, distorted face, "
    "changed identity, different person, face mismatch, duplicate subject, cloned face, "
    "plastic waxy skin, airbrushed smooth skin, over-smoothed featureless skin"
)


NEGATIVE_COLOR_CONTAMINATION_GUARD = (
    "background color spill on skin, color bleeding into skin, painted skin, "
    "skin color contamination, mismatched skin tone, blue skin tint, green skin tint, "
    "orange color cast on skin"
)


# base run(build_negative) 과 Skills run(build_camera_negative) 이 **공유**하는
# negative 기본 블록. 두 함수가 각자 하드코딩해서 Skills 경로에서 watermark /
# flat lighting / washed out 이 조용히 빠졌다(2026-09-28 실측: base 1669자 →
# Skills 1063자). base 는 CameraDirector 라는 **비등록 내부 클래스**라 사용자에게
# 노출되지 않으므로 Skills 만 고치면 실질적으로 아무것도 고쳐지지 않는다.
# 한 곳에 두면 앞으로 한쪽만 고치는 일이 구조적으로 불가능해진다.
#
# 주의: **사람 전용 가드는 여기 넣지 않는다.** 예전에
# NEGATIVE_ANATOMY_GUARD / NEGATIVE_COLOR_CONTAMINATION_GUARD 를 넣었더니
# 동물 주제에 "plastic waxy skin / different person" 이 붙는 회귀가 생겼다.
# 사람 여부로 게이트되는 항목은 각 함수에서 _is_human_subject 로 판단한다.
_NEGATIVE_BASE_COMMON = (
    "blurry, soft focus, jpeg artifacts, watermark, signature, text, logo",
    "warped geometry, distorted perspective, broken framing",
    "flat lighting, harsh unflattering light",
    "washed out colors, over-saturated colors",
)


OUTFIT_GUARD = (
    "outfit transfer guard: the main person reference image is only the identity and body reference, "
    "the clothing reference image is only a clothing and wardrobe reference, not a body reference, "
    "use the clothing from the clothing reference image as a separate garment layer "
    "placed on the person from the main reference image, preserve the original body shape, body proportions, "
    "skin, face, and hair from the main reference image, pose follows the topic, the garment must follow the existing human "
    "anatomy naturally, no clothing fusion with skin or body parts, no garment becoming "
    "body anatomy, no skin-like fabric on the garment, no melted garment edges, "
    "no body parts merging into clothing"
)


def body_proportion_guard(image_count: int, topic: str, image_labels=None) -> str:
    """이미지 reference가 있는 사람/인물 장면에서 원본 골반/힙 비율을 유지한다.

    identity/body 참조는 계획(plan)이 선출한 주 피사체로 둔다 -- 왜(Why):
    첫 연결이 사물(핸드백 등)이면 사물 비율을 신체 비율로 복제하는 오동작이
    생긴다. 실제 인물 슬롯을 참조해야 한다.
    """
    if image_count <= 0 or not _is_human_subject(topic):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    first = str(plan["main"])
    return (f"face and body preservation guard: use reference image {first} as the identity and body reference, "
            f"{FACE_IDENTITY_GUARD}, {SKIN_COLOR_GUARD}, "
            "preserve the original body proportions from the main human reference image, "
            "same hip width, same waist-to-hip ratio, same torso length, same shoulder width, "
            "do not exaggerate hips or pelvis, no widened pelvis, no exaggerated hourglass body, "
            "natural body shape matching the reference image")


def outfit_guard(image_count: int, topic: str) -> str:
    """의상 교체 의도가 명확하고 이미지가 2장 이상일 때만 의상 전용 가드를 넣는다."""
    if image_count < 2 or not _is_outfit_transfer(topic):
        return ""
    return OUTFIT_GUARD


# 가구·사물 DNA 보존 가드. 왜(Why): 사물 역할 문구가 "prop/product 역할로만
# 써라"까지만 말하면 모델이 **같은 종류의 다른 사물**을 새로 그린다. 실측에서
# 2번 침대 원본(먼 이불·러그·원목 프레임·쿠션 배치)이 3번 생성물에서 다른
# 침대로 바뀌었다. 사물도 인물과 마찬가지로 **참조가 곧 DNA**다.
# 형제 빌더(bass)와는 달리 여기서는 positive/negative를 한 쌍으로 준다.
FURNITURE_DNA_POSITIVE = (
    "prop identity guard: every object, furniture piece and prop keeps the exact "
    "identity of its reference image — same silhouette and construction, same "
    "material and surface texture, same colour and pattern, same proportions and "
    "part count, same placement in the frame. Do not substitute a different "
    "object, a different style, or a cleaner/simpler version of it."
)


FURNITURE_DNA_NEGATIVE = (
    "different furniture, substituted prop, generic furniture, simplified "
    "version, different material, wrong colour, wrong pattern, missing parts, "
    "extra parts, changed silhouette, object moved to a different spot"
)


# "살짝만 달라진 사물" 방어. 왜(Why): 사물 DNA 문구가 "형태를 유지하라"여도
# 모델은 색·무늬·비율을 조금씩 바꾸며 그린다. 실측에서 침대가 원본과 다른
# 침대로 바뀌었지만, 더 흔한 실패는 **비슷하지만 다른** 사물이다.
OBJECT_DRIFT_NEGATIVE = (
    "object replaced by a similar-looking but different object, near-miss "
    "furniture, almost-right prop, different fabric pattern, different wood "
    "tone, different cushion count, tidied-up version, simplified bedding, "
    "generic bedding, recoloured object, reshaped object"
)


OBJECT_INSTANCE_POSITIVE = (
    "single instance guard: exactly one instance of each referenced object "
    "appears in the frame. It keeps the silhouette, proportions and part count "
    "of its reference image, and there is no second copy of it anywhere else "
    "in the frame - not stacked, not repeated, not mirrored."
)


OBJECT_INSTANCE_NEGATIVE = (
    "second copy of the referenced object, unintended duplicate of the same "
    "prop, the object drawn twice, repeated copy of the furniture, stacked "
    "duplicate, mirrored copy of the object, extra instance of the reference "
    "object"
)


# 찌꺼기 방어는 **항상** 켠다 (사용자 지적: topic에 안 써도 자동으로).
# 왜(Why): "벗는다"고 써도 안 써도 잔여물 자체는 언제든 틀린 결과다 — 완전히
# 없거나 그대로여야 하고, 반쪽은 어떤 경우에도 아니다. 트리거를 만들면
# 사용자가 문구를 외워야 하므로 방어 효과가 반감된다. garment·accessory는
# 인물이 거의 항상 있는 장면이므로 텍스트 한 줄이 비용 대비 이득이 크다.
# 다만 인물이 전혀 없는 실행(제품·공간 단독)에는 붙이지 않는다.
PARTIAL_OBJECT_NEGATIVE = (
    "leftover fragment of a removed item, detached shoe, half a shoe, "
    "shoe scrap, floating debris, orphaned object piece, partial object, "
    "cut-off object, object remnant on the floor, ghost object, "
    "debris of something that was taken off, orphaned garment piece, "
    "half a sleeve, floating cuff, detached collar, stray accessory"
)


def _furniture_dna_guard(text: str, object_slots) -> str:
    """가구·사물 DNA positive 문구. 사물 슬롯이 없으면 "".

    기본값(사용자 지적 반영): topic에 "2번 침대 원본"을 **안 써도** 켜져야 한다.
    사물도 참조가 곧 DNA이므로, 참조로 들어온 사물은 사용자가 별도로 지시하지
    않는 한 형태를 그대로 따라야 한다. 오직 style/mood/lighting 전용으로
    명시된 슬롯만 예외로 뺀다.
    """
    try:
        slots = sorted(int(x) for x in set(object_slots or []))
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    t = (text or "").lower()
    # 왜(Why) 한국어는 경계 판정인가 (2026-10-07 라운드 2): raw `in` 이면
    # "블루스톤 테이블" 이 "톤" 으로 잡혀 분위기 전용 판정이 곳곳에서 발동한다.
    # 영문은 종전대로 부분 일치를 쓴다(짧은 어휘가 합성어에 걸리는 일이 없다).
    if any((_ko_word_present(t, k) if not _ascii_only(k) else k in t)
           for k in NON_OBJECT_SLOT_KEYWORDS):
        # 분위기 전용 지정이 있으면 DNA 문구에서 "사물 대체 금지"를 약하게 한다
        # (분위기만 빌려오는 슬롯에 "같은 사물로 재현"을 강요하면 역효과).
        return FURNITURE_DNA_POSITIVE.replace(
            "Do not substitute a different object, a different style, or a "
            "cleaner/simpler version of it.",
            "Take only the mood and lighting from it, not the object shape."
        ) + f" This applies specifically to reference image(s) {slots and ', '.join(str(x) for x in slots)}."
    listed = ", ".join(str(x) for x in slots)
    return (FURNITURE_DNA_POSITIVE
            + f" This applies specifically to reference image(s) {listed}."
            + " " + OBJECT_INSTANCE_POSITIVE)


def _object_dna_slots(topic: str, image_labels, image_count: int) -> set:
    """가구·사물 DNA를 적용할 슬롯 집합. topic에 아무 말 없어도 채운다.

    왜(Why): 사용자가 "2번 침대 원본을 써라"고 쓰지 않아도 2번에 침대를
    연결했다면 그 침대가 곧 DNA다. 기존 구현은 topic에 사물 역할이 명시될
    때만 발동해서(topic 미작성) DNA 가드가 조용히 꺼졌다.

    판정: **주 피사체·추가 인물·포즈 슬롯을 제외한 모든 연결 슬롯**이 기본
    대상이다. style/mood/lighting 전용 슬롯도 여기서 빠지지는 **않는다** —
    그 완화는 _furniture_dna_guard 가 NON_OBJECT_SLOT_KEYWORDS 로 문구
    수준에서 따로 한다(이 문서가 예전엔 "제외한다" 라고 적혀 있었고 코드와
    어긋나 있었다 — 2026-10-07 라운드 2에서 정정).
    """
    try:
        if image_count <= 0:
            return set()
        labels = [int(str(x)) for x in (image_labels
                                       or list(range(1, image_count + 1)))]
        plan = _person_object_plan(topic or "", labels)
        excluded = {plan["main"]} | set(plan["persons"]) | set(plan["poses"])
        return {x for x in labels if x not in excluded}
    except Exception:
        return set()


def _remove_item_guard(text: str) -> str:
    """사물 제거 잔여물 negative. **항상** 켠다 (인물 주제 한정).

    왜(Why): 사용자가 "벗는다"고 topic에 쓰지 않아도 잔여물 자체는 틀린 결과다.
    반쪽 물체는 완전 제거도 완전 유지도 아닌 유일한 상태이고, 그것은 언제나
    틀리다. 트리거를 만들면 사용자가 문구를 외워야 하므로 효과가 반감된다.
    """
    try:
        t = (text or "").lower()
        if not _is_human_subject(t):
            return ""
        return PARTIAL_OBJECT_NEGATIVE
    except Exception:
        return ""


def add_quality_guard(prompt: str, image_count: int = 0, topic: str = "", image_labels=None) -> str:
    """모델 공통 positive 품질 가드. negative 프롬프트는 건드리지 않는다."""
    prompt = (prompt or "").strip().rstrip(". ")
    # 동물 전용 주제면 사람 손·피부 품질 문구가 정면 모순이다. 사람/동물
    # 혼재 장면은 사람 가드를 유지한다(사람이 있으면 필요하다).
    _only_animal = _is_animal_subject(topic or "") and not _is_human_subject(
        topic or "")
    parts = [p for p in [prompt, QUALITY_GUARD_ANIMAL if _only_animal
                         else QUALITY_GUARD] if p]
    ref_guard = reference_guard(image_count, image_labels=image_labels, topic=topic)
    if ref_guard:
        parts.append(ref_guard)
    if not _only_animal:
        # 골반·힙 비율 가드는 사람 전용(동물의 실루엣을 humanoid 비율로
        # 끌고 간다). reference_guard 가 이미 종 보존 문구를 준다.
        body_guard = body_proportion_guard(image_count, topic,
                                           image_labels=image_labels)
        if body_guard:
            parts.append(body_guard)
    fit_guard = outfit_guard(image_count, topic)
    if fit_guard:
        parts.append(fit_guard)
    return ". ".join(parts) + "."


def assemble(scene: str, cam: dict, image_count: int = 0, topic: str = "", image_labels=None) -> str:
    """scene + 카메라 + 그레이드 + 범용 품질/정체성 가드 → 영문 prompt_out."""
    scene = (scene or "").strip().rstrip("., ")
    segs = [", ".join(build_clauses(cam)), GRADE.get(cam.get("grade"), "")]
    segs = [s for s in segs if s]
    if scene and segs:
        prompt = scene + ". " + ". ".join(segs) + "."
    elif scene:
        prompt = scene + "."
    else:
        prompt = ". ".join(segs) + "." if segs else ""
    detail = macro_detail_guard(topic or scene, cam)
    if detail:
        prompt = prompt.rstrip(". ") + ". " + detail + "."
    nudity = nudity_anatomy_guard(topic or scene)
    if nudity:
        prompt = prompt.rstrip(". ") + ". " + nudity + "."
    if _needs_scale_guard(topic or scene, cam):
        prompt = prompt.rstrip(". ") + ". " + SCALE_COHERENCE_POSITIVE + "."
    _eth_pos, _ = _ethnicity_guard(topic or scene, image_count, image_labels)
    if _eth_pos:
        prompt = prompt.rstrip(". ") + ". " + _eth_pos + "."
    if _is_animal_subject(topic or scene):
        prompt = prompt.rstrip(". ") + ". " + ANIMAL_SPECIES_POSITIVE + "."
    return add_quality_guard(prompt, image_count=image_count, topic=topic or scene,
                             image_labels=image_labels)


NUDITY_KEYWORDS = (
    "nude", "naked", "undressed", "bare body",
    "누드", "나체", "알몸", "전라", "옷을 벗",
)


def _is_nudity_request(text: str) -> bool:
    """노출 의도가 명시됐는지만 판별한다 (임상 가드 트리거용)."""
    t = (text or "").lower()
    for keyword in NUDITY_KEYWORDS:
        # 왜(Why) 지명 제외인가: "전라"는 "전라도/전라북도/전라남도" 안에
        # 그대로 들어간다(2026-10-07 감사 실측: "전라도 출신 여성"이 노출
        # 가드에 걸렸다). 지명이 있으면 이 키워드만 건너뛴다.
        if keyword == "전라" and any(p in t for p in
                                     ("전라도", "전라북도", "전라남도")):
            continue
        if keyword in t:
            return True
    return False


def nudity_anatomy_guard(topic: str) -> str:
    """노출 의도 시 임상적 해부학 완성 문구를 반환한다.

    왜(Why): 노골적 성적 묘사 요구는 모델의 안전 튜닝에 막혀 프롬프트로
    완전히 극복할 수 없으므로, 노골 표현 대신 임상적 완성도 언어로
    뭉개짐·변형을 줄이는 데 그친다. 노출 의도가 없으면 붙지 않는다.

    주의: "anatomical/anatomically" 어휘는 학습 데이터 편향상 의학 도판·
    해부도 풍으로 그려지는 실측 사례가 있어 positive 가드에는 쓰지 않는다
    (사용자 실측 — "성기가 진짜 해부된다"). negative의 "deformed anatomy"
    는 변형을 막는 방향이라 유지한다.
    """
    if not _is_nudity_request(topic or ""):
        return ""
    return ("natural realistic human body with correct proportions, "
            "soft realistic skin and clearly defined natural intimate detail")


def macro_detail_guard(topic: str, cam: dict) -> str:
    """매크로 렌즈 + 인물 주제일 때만 미세 결 강조 문구를 반환한다.

    왜(Why): 100mm 매크로는 제품 촬영에도 쓰이므로 렌즈만으로는 모공·솜털
    문구를 붙일 수 없고, 인물 판정이 함께 있어야 제품에 체모 표현이
    들어가는 오작동을 막을 수 있다.
    """
    if cam.get("lens") != "100mm 매크로 (macro)" or not _is_human_subject(topic or ""):
        return ""
    return ("macro detail emphasis: extreme fine detail, sharp micro-contrast, "
            "visible pores, fine vellus hair, and natural skin texture")


def _camera_failure_modes(cam: dict, topic: str = "") -> list:
    """렌즈·모션·노출 분기 negative 조각 (공용). 왜(Why): standalone과
    Skills negative가 같은 6분기를 따로 들고 있어 한쪽만 바뀌는 퇴행이
    있었다. 순서는 양쪽 기존 출력과 동일하게 유지한다."""
    out = []
    lens = cam.get("lens", "")
    if "초광각" in lens:
        out.append("unwanted wide-angle distortion")
    if "f/1.4" in lens:
        out.append("busy distracting background")
    if "매크로" in lens:
        out.append("soft detail, muddy texture")
    _m1, _m2 = cam.get("motion"), cam.get("motion2")
    if (_m1 not in ("없음 (none)", "", None)
            or _m2 not in ("없음 (none)", "", None)):
        out.append("shaky jitter, motion smear, frame warping")
    if _is_nudity_request(topic or ""):
        out.append("deformed intimate anatomy, blurred anatomy, featureless crotch area")
    return out


# 해부 디테일 negative 팩 (눈·치아·귀·발·관절). 왜(Why): 기존 anatomy 가드가
# 팔·손가락·얼굴 부위를 커버하지만 눈·치아 어긋남은 빠져 있었다. 인물 주제에만
# 양쪽 negative(standalone + Skills)에 자동 첨부한다.
ANATOMY_DETAIL_NEGATIVE = (
    "cross-eyed, asymmetrical eyes, misaligned pupils, "
    "deformed teeth, extra teeth, "
    "deformed ears, malformed feet, extra toes, "
    "broken joints, twisted knees"
)


# 인체 부위 **개수** 명시. 왜(Why): 기존 negative는 "6손가락 금지"만 강하게
# 있고 positive는 범용 품질 가드에 "believable hands with five fingers" 한 줄
# 묻혀 있었다. diffusion은 "X가 아니다"보다 "Y가 있다"에 잘 반응하므로
# 개수를 positive에 직접 박는다. 발가락·팔·다리는 positive가 아예 없었다.
# 한계(정직): 텍스트는 **부드러운 사전확률**이라 개수를 강제하지 못한다.
# 진짜 픽셀 강제는 참조 latent + 낮은 denoise로 원본 손을 보존하는 경로다
# (KSampler denoise 0.4~0.6, 노드 밖 설정).
ANATOMY_COUNT_POSITIVE = (
    "correct limb and digit count, clearly readable anatomy: exactly five "
    "fingers on each hand (one thumb plus four fingers), five toes on each "
    "foot, two arms ending in two hands, two legs ending in two feet, "
    "both sides of the body symmetrical, every limb fully formed and "
    "separated from its neighbour, hands and feet drawn as complete "
    "unambiguous shapes"
)


# 개수가 틀릴 때의 실제 형태. 왜(Why): 6손가락은 "6개가 추가"되는 게 아니라
# 손가락 2개가 붙거나(6→5로 보이게) 한 개가 갈라져 나오는 경우가 대부분이다.
# 그래서 "갯수 초과"가 아니라 **"붙음·갈라짐"** 형태를 막는다.
ANATOMY_COUNT_NEGATIVE = (
    "fused fingers, webbed fingers, mitten hands, fingers split down the "
    "middle, double thumbs, extra fingers, missing fingers, fingers merging "
    "into the palm, fused toes, split toes, extra toes, missing toes, "
    "feet merged into a single blob, arms fused to the torso, legs fused "
    "together, three arms, three legs, three feet, extra feet, "
    "asymmetric limbs, one arm, one leg"
)


# 스케일 일관 샷 — 인물 전신·주변이 함께 보이는 샷에서만 사물 스케일 점검.
SCALE_SHOTS = ("중근접 (MCU)", "중경 (MS)", "전신 (FS)", "원경 (WS)")


# 인물-사물 스케일 일관 문구. 왜(Why): 침대 같은 배경 사물이 인체 대비
# 너무 작거나 크게 그려지는 원근·스케일 prior 흔들림을 프롬프트층에서 잡는다.
# latent 당김으로는 스케일을 못 고치므로 이 가드가 담당한다.
SCALE_COHERENCE_POSITIVE = (
    "consistent proportional scale between the person and surrounding "
    "furniture and background, natural perspective")


SCALE_COHERENCE_NEGATIVE = (
    "inconsistent object scale, miniature background, oversized person")


def _needs_scale_guard(topic: str, cam: dict) -> bool:
    """인물 + 전신·주변 가시 샷이면 스케일 가드 대상."""
    try:
        return bool(_is_human_subject(topic or "")
                    and (cam or {}).get("shot", "") in SCALE_SHOTS)
    except Exception:
        return False


# 국가·출신지 표현형 반영.
# 왜(Why): "아랍"만 넣으면 수염·갈피·전통의상으로, "한국"만 넣으면 서구화로
# 수렴한다(SDXL 인종 동질화 실증, Sci Rep 2025). 두 실패는 프롬프트 레벨에서
# 막을 수 있다. 근거 3가지:
#  1) 출처: EMNLP Findings 2023 "person from X" 문맥이 국가명 직접 표기보다
#     고정관념·동질화가 적다 → 인종 본질 표현("East Asian facial features")
#     대신 출신지 문맥을 쓴다.
#  2) 분산: 같은 나라를 넣어도 사람마다 다른 얼굴이어야 한다. 집합 내 개별
#     변이 문구를 positive에, "한 나라가 한 얼굴" 고정을 negative에 넣는다.
#  3) 교차축: 인종 축만 건드리면 성별 등 다른 축이 29%에서 악화된다
#     (EMNLP Findings 2025 InterMit) → 성별어는 절대 넣지 않는다.
# 지역 묶음은 FairFace 7분류(CC BY 4.0, bias measurement 용)의 구획을 빌려
# 국가→지역 대응에만 쓴다. 데이터셋 라벨이나 이미지를 동봉·복제하지 않는다.
# 형식: 키워드튜플 → (지역, 영문 출신지 표기)
ETHNICITY_GROUPS = (
    (("한국", "korea", "korean"), "Korea"),
    (("일본", "japan", "japanese"), "Japan"),
    (("중국", "china", "chinese"), "China"),
    (("태국", "thailand", "thai"), "Thailand"),
    (("베트남", "vietnam", "vietnamese"), "Vietnam"),
    (("인도", "india", "indian"), "India"),
    (("미국", "america", "usa", "u.s"), "the United States"),
    (("영국", "british", "england", "u.k", "united kingdom"),
     "the United Kingdom"),
    (("프랑스", "france", "french"), "France"),
    (("독일", "germany", "german"), "Germany"),
    (("브라질", "brazil", "brazilian"), "Brazil"),
    (("멕시코", "mexico", "mexican"), "Mexico"),
    (("이집트", "egypt", "egyptian"), "Egypt"),
    (("아랍", "arab"), "an Arab country"),
    (("나이지리아", "nigeria", "nigerian"), "Nigeria"),
    (("케냐", "kenya", "kenyan"), "Kenya"),
)


TRADITIONAL_KEYWORDS = (
    "한복", "기모노", "kimono", "hanfu", "traditional", "전통",
    "사리", "sari", "히잡", "hijab", "터번", "turban",
)


# 주제에 이미 외양·얼굴 서술이 있으면 국가 표현형보다 그 서술이 우선이다.
APPEARANCE_DESCRIBED_KEYWORDS = (
    "얼굴", "외모", "외양", "이목구비", "얼굴형", "피부색", "피부톤",
    "모발", "머리색", "얼박살",
    "face", "facial features", "appearance", "complexion", "skin tone",
    "hair color", "eye color", "freckle",
)


ETHNICITY_DIVERSITY_POSITIVE = "varied individual facial features within the group"


ETHNICITY_MODERN_WEAR = "modern everyday clothing"


ETHNICITY_STEREOTYPE_NEGATIVE = (
    "westernized facial features, forced traditional costume, "
    "historical costume by default, exotic stereotype, "
    "every person from the same country looking identical, "
    "one homogenized face type for a whole country"
)


def _ethnicity_identity_locked(topic: str, image_count: int,
                               image_labels=None) -> bool:
    """참조 이미지가 이미 신원을 고정했거나 주제가 외양을 서술하면 국가 표현형은 미첨부.

    왜(Why): DNA(신원·외양)는 사용자가 준 픽셀 근거가 1순위다. 그 위에 국가
    표현형을 덮으면 사용자가 정한 인물이 밀린다.
    """
    try:
        text = (topic or "").lower()
        # "face"는 단어 경계로만 매칭한다 — "surface" 안에서 잡혀
        # 국가 표현형이 억제됐다(2026-10-07 감사 실측).
        if (any(_ascii_word_present(text, k) for k in ("face",))
                or any(k in text for k in APPEARANCE_DESCRIBED_KEYWORDS
                       if k != "face")):
            return True
        if image_count <= 0:
            return False
        plan = _person_object_plan(topic or "", image_labels)
        return plan["main"] not in plan["objects"] or bool(plan["persons"])
    except Exception:
        return False


def _ethnicity_guard(topic: str, image_count: int = 0,
                     image_labels=None) -> tuple:
    """(positive 조각, negative 조각). 조건 불충족이면 ("", "")."""
    try:
        t = (topic or "").lower()
        if not _is_human_subject(topic or ""):
            return "", ""
        if _ethnicity_identity_locked(topic or "", image_count, image_labels):
            return "", ""
        for keywords, origin in ETHNICITY_GROUPS:
            # 왜(Why) 한국어만 경계 판정인가 (2026-10-05 감사 2회 차): raw `in`
            # 이면 "인도네시아" 안의 "인도" 가 잡혀 인도네시아 주제에 인도
            # 표현형(현대 복장 지시 + 고정관념 negative)이 붙었다. _ko_word_present
            # 는 뒤 글자가 조사가 아닌 한글이면 거부하므로 "인도네시아" 는 통과
            # 못 한다. 영문은 종전대로 부분 일치 — "indian" 이 키워드라
            # "indian" 자체는 같은 그룹으로 정상 매칭된다.
            if any(k in t if _ascii_only(k) else _ko_word_present(t, k)
                   for k in keywords):
                pos = f"a person from {origin}, {ETHNICITY_DIVERSITY_POSITIVE}"
                neg = ""
                if not any(k in t for k in TRADITIONAL_KEYWORDS):
                    pos += ", " + ETHNICITY_MODERN_WEAR
                    neg = ETHNICITY_STEREOTYPE_NEGATIVE
                return pos, neg
        return "", ""
    except Exception:
        return "", ""


# 얼굴 클로즈업 샷 — latent가 작으면 얼굴 뭉개짐 확정이라 출발 점검 대상.
FACE_CRITICAL_SHOTS = ("극접 (ECU)", "근접 (CU)")


def _assemble_negative(cam, topic, image_count, image_labels, flags,
                       noir_phrase, extras=(), physics_neg="",
                       pose_ref=False, prevent_duplicates=False) -> str:
    """두 negative 빌더가 공유하는 조립 로직.

    왜(Why) 하나인가(2026-09-29): `build_negative` 와
    `build_camera_negative` 가 40줄을 복붙하고 있었다. 같은 상수를 같은
    순서로 넣는데 한쪽만 고치면 **양쪽이 어긋나** 짝인 방어가 조용히
    사라진다 — 실제로 `_camera_failure_modes` 로 일부를 이미 합친 뒤에도
    시트·포즈·부위·가구 블록이 그대로 두 벌이었다.

    유일한 차이가 `noir_phrase` 이었다("unwanted color cast" vs
    "color tint"). 그 차이는 **호출부가 준다** — 함수 안에서 guessing 하지
    않는다.
    """
    neg = list(_NEGATIVE_BASE_COMMON)
    # topic 이 비면(판단 근거 없음) 사람 기본값을 쓴다. ComfyUI 사용의
    # 대부분이 인물이고, 비었을 때 가드를 빼는 쪽이 더 위험하다.
    if not (topic or "").strip() or _is_human_subject(topic):
        neg.append(NEGATIVE_ANATOMY_GUARD)
        neg.append(NEGATIVE_COLOR_CONTAMINATION_GUARD)
    neg.extend(_camera_failure_modes(cam, topic))
    if cam.get("grade") == "느와르 (noir)":
        neg.append(noir_phrase)
    if _is_human_subject(topic or ""):
        neg.append(ANATOMY_DETAIL_NEGATIVE)
    # positive(ANATOMY_COUNT_POSITIVE) 는 붙는데 negative 짝이 없으면
    # "5개여야 한다" 는 지시가 방향 없는 한쪽_only 가 된다(2026-09-28 발견).
    if flags.get("anatomy_count"):
        neg.append(ANATOMY_COUNT_NEGATIVE)
    if flags.get("character_sheet"):
        neg.append(CHARACTER_SHEET_NEGATIVE)
        # 시트 뷰가 별개 인물로 세어지는 것까지 막는다 (신원 일관성이 목적이므로).
        if not _is_multi_person_sheet(topic):
            neg.append(CHARACTER_SHEET_PEOPLE_NEGATIVE)
    _, _eth_neg = _ethnicity_guard(topic or "", image_count, image_labels)
    if _eth_neg:
        neg.append(_eth_neg)
    if _is_animal_subject(topic or ""):
        neg.append(ANIMAL_ANATOMY_NEGATIVE)
    # 포즈 negative: 빈 문자열을 넣지 않는다 (빈 조각이 ", " 꼬리를 남긴다)
    _pose_neg = _pose_reference_negative(
        _pose_role_slots(topic or "") & set(image_labels or [])) if pose_ref else ""
    if _pose_neg:
        neg.append(_pose_neg)
    if physics_neg:
        neg.append(physics_neg)
    if flags.get("detail_def"):
        neg.append(DETAIL_DEFINITION_NEGATIVE)
    if flags.get("furniture"):
        neg.append(FURNITURE_DNA_NEGATIVE)
        neg.append(OBJECT_DRIFT_NEGATIVE)
        neg.append(OBJECT_INSTANCE_NEGATIVE)
    if flags.get("remove_item"):
        # 빈 문자열을 세면 join 이 ", " 꼬리를 남긴다(2026-10-07 라운드 2 —
        # _remove_item_guard 는 비인물 topic 에 "" 를 돌려준다).
        _rm = _remove_item_guard(topic)
        if _rm:
            neg.append(_rm)
    if _needs_scale_guard(topic or "", cam):
        neg.append(SCALE_COHERENCE_NEGATIVE)
    if prevent_duplicates:
        neg.extend(["multiple people", "duplicate person", "cloned person",
                    "mirrored twin", "background person"])
    for src in extras:
        if src and src.strip():
            neg.append(src.strip())
    return ", ".join(neg)


def build_camera_negative(cam: dict, prevent_duplicates: bool = False,
                          topic: str = "", image_count: int = 0,
                          image_labels=None, pose_ref: bool = False,
                          physics_neg: str = "", detail_def: bool = False,
                          furniture: bool = False,
                          remove_item: bool = False,
                          anatomy_count: bool = False,
                          character_sheet: bool = False) -> str:
    """카메라/영상 실패 모드 + 인물 해부 디테일 방어 (신원·신체 비율 가드 제외)."""
    return _assemble_negative(
        cam, topic, image_count, image_labels,
        {"anatomy_count": anatomy_count, "character_sheet": character_sheet,
         "detail_def": detail_def, "furniture": furniture,
         "remove_item": remove_item},
        "unwanted color cast", physics_neg=physics_neg, pose_ref=pose_ref,
        prevent_duplicates=prevent_duplicates)


# llm_hint 사용 시 검열 아티팩트 방어어. (Why: 모델이 학습 편향으로
# 스스로 순화·블러·모자이크를 그리는 사례 방지. "blurred"는 bokeh와
# 충돌하므로 의도적으로 제외했다. base run()과 Skills run_prompt 양쪽에서
# 동일한 문구를 쓰므로 상수로 공유한다.)
HINT_DEFENSE_NEGATIVE = "censored, mosaic, bar censor, pixelated"


# 다중 참조(2장 이상) 실행의 "믹스 변형" 방어어. (Why: 얼굴+의상 등 둘 이상의
# 참조 이미지를 섞는 실행에서는 옷-피부 융합, 신원 혼합, 인물 복제 같은
# 합성 변형이 잘 일어난다. 연결된 이미지 개수는 픽셀 근거라 오검출이 낮다.
# 첫 번째 연결 이미지가 신원 소스라는 규약은 image_note/신원 앵커와 동일하다.
# base run()과 Skills run_prompt 양쪽에서 공유한다.)
MIX_GUARD_POSITIVE = (
    "Reference mixing guard: the main person reference image is the only identity source "
    "(face, body shape, proportions); the other reference image(s) contribute "
    "only their requested role such as outfit, background, prop, product, "
    "style, lighting, composition, or mood. Garments from a clothing reference "
    "are a separate clothing layer placed over the main person's body, "
    "following the existing anatomy, preserving the main person's body shape, "
    "skin, face, and hair; pose follows the topic. No blending of two people into one, no mixed "
    "facial features between references."
)


MIX_GUARD_NEGATIVE = ("clothing fusion with skin, melted garment edges, "
                      "body parts merging into clothing, mixed facial features, "
                      "identity blending, duplicated person")


# 포즈 참조 가드. 왜(Why): Qwen reference 경로는 이미지 전체를 latent로 주입하므로
# 자세만 빌려오게 해도 참조 인물의 얼굴·피부·머리·의상이 함께 유입된다. 텍스트
# 가드만으로는 이미지 모델이 텍스트보다 시각 근거를 더 강하게 따르는 특성상
# 막기 어렵기 때문에, LLM 비전에서는 아예 빼고(픽셀 경로로만 전달) + 여기서
# "자세 전용"을 명시한다.
def _pose_reference_guard(pose_slots) -> str:
    """포즈 참조 positive 문구. 지정 슬롯이 없으면 ""."""
    try:
        slots = [int(x) for x in sorted(set(pose_slots or []))]
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    listed = ", ".join(str(x) for x in slots)
    return (f"Pose reference guard: reproduce the body pose and limb angles of "
            f"reference image(s) {listed} and nothing else from them. Take ONLY "
            f"the posture from those images — never their face, facial features, "
            f"skin tone, hair, body identity, clothing, or background. The "
            f"subject's identity and wardrobe come from the main reference and "
            f"the topic, not from the pose reference.")


def _pose_reference_negative(pose_slots) -> str:
    """포즈 참조 negative 문구. 지정 슬롯이 없으면 ""."""
    try:
        slots = [int(x) for x in sorted(set(pose_slots or []))]
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    listed = ", ".join(str(x) for x in slots)
    return (f"face of the pose reference image {listed}, "
            f"clothing of the pose reference image {listed}, "
            f"body identity of the pose reference image {listed}, "
            f"background of the pose reference image {listed}, "
            f"face swap with the pose reference, identity blending between "
            f"the pose reference and the subject")


# 9·10번 슬롯 전용 "외양 참조" 가드 (사용자 전용 기능 — 2026-09-27).
# (Why: 9·10번에 신체 외양 클로즈업(예: 성기 디테일)을 연결하면 LLM은 외양을
# 판단 근거로 쓰고 Qwen은 픽셀을 참고하게 되는데, 이때 클로즈업 컷 자체가
# 콜라주/패널로 삽입되는 오동작을 막아야 한다. "anatomical" 어휘는 학습
# 편향상 의학 도판 풍으로 그려지는 실측 사례가 있어 positive에는 쓰지 않는다.
# 2026-09-27 후속: 9·10번에 어떤 부위(가슴/성기)가 어떤 순서로 와도
# 참조 픽셀을 실제 묘사 부위에 매칭하도록 "부위 식별 + 교차 금지" 문구로 강화.)
APPEARANCE_REF_POSITIVE = (
    "Appearance reference: the slot 9/10 image(s) are body appearance "
    "references — each one depicts a specific body region (such as chest or "
    "breasts, or intimate region). Visually match each reference to the body "
    "region it actually depicts and apply its depicted appearance naturally to "
    "that exact region only, with realistic soft skin texture and natural "
    "shape. Never swap, merge, or misplace the regions — do not copy one "
    "reference's appearance onto a different body region. Do not include the "
    "reference crops themselves in the image, no panel, no collage, no split view."
)


APPEARANCE_REF_NEGATIVE = "collage, inset panel, split view, split screen, duplicated crop, clumped hair patches, sticker-like body hair, floating hair decals"


# 외양 참조(9·10번) 실행의 체모 실사감 문구. (Why: 음모 등 체모가 뭉치거나
# 피부 위에 스티커처럼 떠 있는 실측 사례 — 모근에서 자라는 입체 디테일,
# 굵기 불균일, 신체 곡선을 따라 눕는 물리감을 명시해야 자연스럽다.
# appearance_ref 실행에만 붙는 사용자 전용 기능이라 README 비공개.)
APPEARANCE_HAIR_REALISM_POSITIVE = (
    "natural realistic body hair detail: individual strands growing from the "
    "skin with visible follicle roots, tapering tips, slightly irregular "
    "thickness, hairs lying and bending along the body's curves, layered "
    "strands creating natural depth, soft density gradient — no clumped "
    "patches, no sticker-like or floating hair"
)


# 부위별 디테일 뭉개짐 방어. (Why: 실측에서 참조 이미지를 쓰는 실행의 결과물이
# 다리·팔·어깨부터 뿌옇게 뭉개졌다. "blurry"는 초점 문제라 별개이고,
# 여기선 **부위 경계가 지워지는** 문제다 — 살갗/원단 경계, 무릎·팔꿈치 관절 선,
# 손가락 마디 같은 구조 경계가 사라져 보솜처럼 뭉개진다. denoise가 높은
# 실행일수록 심해진다.)
DETAIL_DEFINITION_POSITIVE = (
    "anatomical edge definition: every body part keeps a clear readable "
    "boundary against what surrounds it — legs separate from each other and "
    "from the background, arms separate from the torso, shoulders keep a "
    "defined line, fabric keeps its weave and seams, skin keeps natural "
    "texture, hands keep distinct fingers, knees and elbows keep a visible "
    "joint line"
)


DETAIL_DEFINITION_NEGATIVE = (
    "melted body boundaries, legs blending into each other, arm merging into "
    "torso, smeared fabric, waxy skin, featureless limbs, indistinct fingers, "
    "boots melting into the foot, foot blending into the floor, "
    "soft shapeless body parts, plastic doll skin, blanket-like skin folds"
)


# 인물 신체 발란스 가드. (Why: 전신·신체 중심 장면에서 팔/다리 길이 불균형,
# 머리-몸 비율 붕괴, 부위별 스케일 불일치가 자주 발생. 인물 주제면 참조 이미지
# 유무와 무관하게 항상 첨부한다 — 비율 문구는 장면 훼손이 없어 상시 붙여도 안전.)
BODY_BALANCE_POSITIVE = (
    "body balance: natural human proportions, head-to-body ratio consistent "
    "with a real person, arms and legs of even realistic length, natural "
    "shoulder-hip line, relaxed upright posture, all body parts at one "
    "consistent scale"
)


BODY_BALANCE_NEGATIVE = ("disproportionate limbs, elongated arms, shortened legs, "
                         "oversized head, twisted torso, body parts of different scale")


def build_negative(cam: dict, extra: str = "", llm_extra: str = "", topic: str = "",
                   hint_defense: bool = False, mix_guard: bool = False,
                   appearance_ref: bool = False, body_balance: bool = False,
                   character_sheet: bool = False, image_count: int = 0,
                   image_labels=None, pose_ref: bool = False,
                   physics_neg: str = "", detail_def: bool = False,
                   furniture: bool = False, remove_item: bool = False,
                   anatomy_count: bool = False) -> str:
    # 힌트·믹스·외양·발란스 방어는 base 경로 전용이라 조립기가 아니라
    # 여기서 덧붙인다(중복이 아니라 경로별 전용).
    tail = []
    if hint_defense:
        tail.append(HINT_DEFENSE_NEGATIVE)
    if mix_guard:
        tail.append(MIX_GUARD_NEGATIVE)
    if appearance_ref:
        tail.append(APPEARANCE_REF_NEGATIVE)
    if body_balance:
        tail.append(BODY_BALANCE_NEGATIVE)
    return _assemble_negative(
        cam, topic, image_count, image_labels,
        {"anatomy_count": anatomy_count, "character_sheet": character_sheet,
         "detail_def": detail_def, "furniture": furniture,
         "remove_item": remove_item},
        "color tint", extras=tuple(tail) + (llm_extra, extra),
        physics_neg=physics_neg, pose_ref=pose_ref)
