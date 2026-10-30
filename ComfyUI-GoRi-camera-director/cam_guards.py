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
# 배경-참조 감지(_BG_KO_PATTERNS 등)는 cam_translate 가 소유한다 — 패턴을
# 여기로 옮기거나 복사하면 두 벌이 갈라져 한쪽만 고치는 결함을 만든다.
try:
    from .cam_translate import background_ref_slot
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_translate import background_ref_slot
# 손 배치 표지 판정기는 cam_physics 가 이미 갖고 있다(_kw_hit). 복사하면
# "한글은 부분 일치 / 영문은 단어 경계 + 어미" 규칙이 두 벌이 되어 한쪽만
# 고치는 결함을 만든다(tripod→fall 오탐을 막은 그 규칙). cam_physics 는
# cam_util·cam_subject 만 가져오므로 여기서 가져와도 순환이 없다.
try:
    from .cam_physics import _kw_hit
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_physics import _kw_hit


__all__ = [
"QUALITY_GUARD", "QUALITY_GUARD_ANIMAL", "QUALITY_GUARD_SCENE", "quality_guard_text", "FACE_IDENTITY_GUARD", "SKIN_COLOR_GUARD", "NEGATIVE_ANATOMY_GUARD", "NEGATIVE_COLOR_CONTAMINATION_GUARD", "_NEGATIVE_BASE_COMMON", "OUTFIT_GUARD", "NUDITY_KEYWORDS", "NUDITY_PARTIAL_KEYWORDS", "_is_partial_exposure",
    "_is_nudity_request", "nudity_anatomy_guard", "coverage_guard",
    "EXPLICIT_COVER_KEYWORDS", "EXPLICIT_REVEAL_KEYWORDS",
    "_wants_explicit_cover", "_wants_explicit_reveal", "macro_detail_guard", "_camera_failure_modes", "ANATOMY_DETAIL_NEGATIVE", "ANATOMY_COUNT_POSITIVE", "ANATOMY_COUNT_NEGATIVE", "FINGER_SEPARATION_POSITIVE", "SCENE_FINGER_CUE", "scene_finger_cue", "HAND_INTEGRITY_POSITIVE", "LEG_FOOT_INTEGRITY_POSITIVE", "ANATOMY_COUNT_POSITIVE_UPPER", "ANATOMY_COUNT_NEGATIVE_UPPER", "DETAIL_DEFINITION_POSITIVE_UPPER", "DETAIL_DEFINITION_NEGATIVE_UPPER", "SCALE_SHOTS", "SCALE_COHERENCE_POSITIVE", "SCALE_COHERENCE_NEGATIVE", "_needs_scale_guard", "ETHNICITY_GROUPS", "TRADITIONAL_KEYWORDS", "APPEARANCE_DESCRIBED_KEYWORDS", "ETHNICITY_DIVERSITY_POSITIVE", "ETHNICITY_MODERN_WEAR", "ETHNICITY_STEREOTYPE_NEGATIVE", "_ethnicity_identity_locked", "_ethnicity_guard", "FACE_CRITICAL_SHOTS", "FACE_IDENTITY_NEGATIVE", "_topic_requests_pose", "FURNITURE_DNA_POSITIVE", "FURNITURE_DNA_NEGATIVE", "OBJECT_DRIFT_NEGATIVE", "OBJECT_INSTANCE_POSITIVE", "OBJECT_INSTANCE_NEGATIVE", "PARTIAL_OBJECT_NEGATIVE", "_furniture_dna_guard", "_object_dna_slots", "_background_dna_slots", "_furniture_background_guard", "_remove_item_guard", "add_quality_guard", "assemble", "_assemble_negative", "build_camera_negative", "HINT_DEFENSE_NEGATIVE", "MIX_GUARD_POSITIVE", "MIX_GUARD_POSITIVE_BARE", "MIX_GUARD_NEGATIVE", "_pose_reference_guard", "_pose_reference_negative", "build_negative", "APPEARANCE_REF_POSITIVE", "APPEARANCE_REF_NEGATIVE", "APPEARANCE_HAIR_REALISM_POSITIVE", "DETAIL_DEFINITION_POSITIVE", "DETAIL_DEFINITION_NEGATIVE", "BODY_BALANCE_POSITIVE", "BODY_BALANCE_NEGATIVE", "body_proportion_guard", "outfit_guard", "FOOTWEAR_POSITIVE", "FOOTWEAR_POSITIVE_SLOT", "FOOTWEAR_NEGATIVE", "FOOTWEAR_POSITIVE_UPPER", "FOOTWEAR_NEGATIVE_UPPER", "FOOTWEAR_CHANGE_POSITIVE", "FOOTWEAR_BARE_POSITIVE", "FOOTWEAR_BARE_NEGATIVE", "gaze_forward_guard", "color_adherence_guard", "_ITEM_COLOR_POS", "_ITEM_COLOR_NEG", "BODY_OBJECT_BOUNDARY_POSITIVE", "BODY_OBJECT_BOUNDARY_NEGATIVE", "BODY_OBJECT_BOUNDARY_POSITIVE_UPPER", "BODY_OBJECT_BOUNDARY_NEGATIVE_UPPER", "GARMENT_BOUNDARY_POSITIVE", "GARMENT_BOUNDARY_NEGATIVE", "GARMENT_BOUNDARY_POSITIVE_UPPER", "GARMENT_BOUNDARY_NEGATIVE_UPPER", "_garment_boundary_guard",     "_footwear_guard", "_body_object_boundary_guard", "parse_dw_pose_map",
    "FURNITURE_CONTACT_POSITIVE", "GROUND_REF_POSITIVE", "FURNITURE_ORIENTATION_POSITIVE", "FURNITURE_BACKGROUND_POSITIVE", "FURNITURE_SUPPORT_POSITIVE", "FURNITURE_BACKGROUND_NEGATIVE", "SCENERY_BACKGROUND_POSITIVE", "BACKGROUND_LIGHT_RECONCILE_POSITIVE", "BACKGROUND_SCENE_ADOPT_POSITIVE", "_is_mood_only_background", "background_scene_adopt_guard", "background_support_scene_guard", "PLACE_DESCRIPTION_WORDS", "_ascii_word_in", "place_description_present", "scene_metric_slot", "FURNITURE_SURFACE_POSITIVE", "FURNITURE_COLOR_POSITIVE", "FURNITURE_SURFACE_NEGATIVE", "object_appearance_guard", "OBJECT_FEATURE_POSITIVE", "_object_feature_guard", "_object_feature_words", "_OBJECT_FEATURE_WORDS",
    "SEAT_OCCUPANCY_POSITIVE", "SEAT_OCCUPANCY_NEGATIVE", "SEAT_ORIENTATION_POSITIVE", "FURNITURE_PLACEMENT_LOCK_NON_SEAT",
    "GROUND_REF_NEGATIVE", "ground_reference_guard",
    "pose_map_sentence", "ASPECT_LEG_DUPLICATION_NEGATIVE", "_is_risky_aspect_ratio",
    "HAND_PLACEMENT_POSITIVE", "HAND_PLACEMENT_NEGATIVE", "HAND_PLACE_MARKERS",
    "hand_placement_marks",
    "COMPACT_ANATOMY_POSITIVE", "COMPACT_FOOTWEAR_POSITIVE",
    "COMPACT_FOOTWEAR_POSITIVE_SLOT", "COMPACT_BOUNDARY_POSITIVE",
    "compact_footwear_guard"
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


# 사람도 동물도 아닌 주제(풍경·사물) 전용 대체 가드. 왜(Why) 별도 상수인가:
# QUALITY_GUARD 의 "believable hands with five fingers, natural skin texture"
# 는 사람 전용인데, 판정이 "동물 전용인가"(_only_animal) 하나뿐이라 풍경·사물
# 주제에도 손·피부 문구가 붙었다(2026-10-25 감사). 사람 여부로도 갈라 준다.
QUALITY_GUARD_SCENE = (
    "high visual quality, "
    "clear shapes and clean detail, consistent subject identity"
)


def quality_guard_text(topic: str = "") -> str:
    """주제에 맞는 품질 가드 상수 (사람 / 동물 전용 / 비인간 장면).

    왜(Why) 한 곳에 모으나: 이 분기가 base run(assemble -> add_quality_guard)과
    Skills(run_prompt) 두 곳에 흩어져 있었다. 게이트가 "동물 전용인가" 하나뿐이라
    풍경·사물 주제에도 사람 전용 손·피부 문구가 붙었고(2026-10-25 감사),
    두 사본이 갈리면 한쪽만 고쳐진다. 판정을 이 함수 하나로 모은다.
    """
    _topic = topic or ""
    try:
        if _is_human_subject(_topic):
            return QUALITY_GUARD
        if _is_animal_subject(_topic):
            return QUALITY_GUARD_ANIMAL
        return QUALITY_GUARD_SCENE
    except Exception:  # noqa: BLE001
        # 판정 실패는 사람 가드로 폴백한다 — 손·피부 문구가 남는 쪽이
        # 비인간 주제에 붙는 것보다 안전하다(사람 주제 이탈 방지).
        return QUALITY_GUARD


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
    "extra parts, changed silhouette, object moved to a different spot, "
    "floating legs, legs hovering above the ground, object not touching the "
    "ground, warped seat back, deformed furniture edge, mirrored furniture, "
    "flipped object, reversed left-right orientation, object facing the wrong "
    "way, left and right parts swapped"
)


# 가구 접촉·부위 형태 보존 (2026-10-15 실측, 파란 동그라미): run10 결과물에서
# 의자 다리가 바닥에 붙지 않고 떠 있었고, 등받이 우측 벌지가 뒤틀렸다. DNA
# 문구는 "같은 형태·같은 배치"까지만 말해 모델이 **떠 있는·뒤틀린 같은 종류**
# 의 가구도 합격으로 그렸다. 접촉 상태와 등받이 부위 형태를 따로 못박는다.
# 분위기 전용 슬롯에는 넣지 않는다 (_furniture_dna_guard 전문 분기에서 제외 —
# 분위기만 빌려오는 슬롯에 "참조 위치에 닿아 있어라" 를 강요하면 그 객체가
# 화면에 있을 이유를 만든다).
FURNITURE_CONTACT_POSITIVE = (
    "contact lock: every leg, edge and support of that object rests exactly "
    "where it rests in its reference image, firmly touching the same surface, "
    "with nothing floating or hovering in the air. Seat backs, rails and "
    "frames keep their exact reference shape: no warped, bent, swollen or "
    "deformed parts."
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


# 좌우(미러) 고정 (2026-10-16 실측, 사용자 제보): 참조 `좌.png`(등받이 좌측)로
# 생성했는데 결과는 등받이가 **우측**이었다. 좌우가 뒤집혀 생성됐다.
# /history 로 실제 로드를 확정했으므로 참조 문제가 아니라 **문구에 방향 계약이
# 없어서**다 — FURNITURE_DNA 는 "same silhouette and construction / same
# placement in the frame" 까지만 말하고 좌우를 못박지 않는다. denoise=1.0 에서
# 모델이 방향을 자유롭게 정한다.
# 왜(Why) 접촉 가드와 같은 full 분기에만 넣는가: 분위기만 빌려오는 슬롯에는
# 그 사물이 화면에 있을 이유가 없어 방향을 요구하면 역효과다(접촉 가드와 동일 논리).
FURNITURE_ORIENTATION_POSITIVE = (
    "orientation lock: that object must appear with the exact same left-right "
    "orientation as its reference image — absolutely no mirror, no flip, no "
    "reverse under any circumstance. The side facing the camera in the "
    "reference faces the camera in the result; every left-hand part stays on "
    "the left and every right-hand part stays on the right. Do not mirror, "
    "flip or reverse it."
)


# 좌석 접촉점 (2026-10-24, R226). 왜(Why) 필요한가: 사용자 제보 — 여성이
# **팔걸이에 걸터앉았다**(좌석이 아님). 실측한 최종 프롬프트(영어 8475자)에
# 좌석 접촉 문구가 **0개**였다(`seat·seated·thighs·sitting posture` 0건).
# 기존 body-object boundary 는 "몸이 사물에 녹아들지 말라"는 **경계**일 뿐
# **어디에 앉는가**를 말하지 않는다. 그래서 좌석 슬롯에만 접촉점을 따로 못박는다.
# 경계와 접촉점을 한 상수에 섞지 않는 이유: 경계(비융합)와 접촉점(체중이 좌석에)
# 는 다른 요구라 한쪽만 끌 때 갈라진다.
SEAT_OCCUPANCY_POSITIVE = (
    "seated contact: the seated person's weight rests on the seat cushion — the "
    "pelvis and thighs settle onto the seat surface, the back rests against the "
    "backrest, and both feet reach the floor in front of the seat. The body is "
    "never perched on an armrest, on the top edge of the seat back, or on the "
    "front rail: the seat pan carries the weight, not the frame."
)


SEAT_OCCUPANCY_NEGATIVE = (
    "sitting on the armrest, perched on the seat back edge, perched on the front "
    "rail, sitting on the frame instead of the seat, hips above the armrest "
    "line, floating above the seat, body balanced on an edge of the chair"
)


# 착석 시 좌석 방향 (2026-10-24, R226). 왜(Why) orientation lock 을 갈아 끼우나:
# 참조 2번이 **빈 의자 제품샷**이라 orientation lock 이 "제품샷에서 카메라를
# 향한 면이 결과에서도 카메라를 향한다"를 강제했다. 장면은 "여성이 의자에
# 앉는다"이므로 그 제약이 좌석 개구부와 앉는 사람을 어긋나게 만들었다(실측:
# 의자가 좌측으로 돌아가고 여성이 팔걸이에 걸침). 좌석에서는 **앉는 사람을 받는
# 방향**이 맞다. 형태·접촉·개수는 그대로 두고 방향 조항만 바꾼다 — 그래야
# R158(2026-10-19)·2026-10-22 의 형태 충실 계약이 흔들리지 않는다.
#
# R229 (2026-10-24): 위 R226 문장을 **그대로 둔 채** 뒤에 두 가지를 덧붙인다.
# 왜(Why): R228 뒤 실기에서도 등받이가 인물 **왼쪽 뒤에만** 있고 오른쪽 어깨 뒤에는
# 벽뿐이었다 — 개구부가 앉는 사람 정면을 안 보고 약 40~60도 돌아가 있었다. R228 로
# 배치 고정 조항(`same placement in the frame`·`rests exactly where it rests`)을 다
# 뺐는데도 모델이 참조 2번(3/4 제품샷)의 각도를 붙잡았다. 그래서 방향 지시를
# **그림에서 확인 가능한 형태**(좌석 앞변·앞다리·등받이·윙의 위치)로 적고, 참조의
# 제품샷 카메라각은 따라가지 말라고 **명시적 예외**를 둔다. 기존 문장을 건드리지
# 않으므로 R226/R228 의 부분문자열 검사가 그대로 살아 있다(후보 A).
SEAT_ORIENTATION_POSITIVE = (
    "seat orientation: the chair is turned so its seat opening faces the seated "
    "person — the person sits into the seat, not beside or across it. The chair "
    "keeps its exact construction, legs, armrests, wings and backrest shape from "
    "reference image {slots}, only its turn in the room changes so that the seat "
    "accepts the sitter. The chair faces the seated person squarely: the front "
    "edge of the seat runs parallel to the bottom of the image, the two front "
    "legs stand level and side by side at the bottom, and the backrest stands "
    "directly behind the sitter's back with the wings on both sides of the "
    "sitter — the chair is never swung around to one side. The camera angle of "
    "reference image {slots} does not carry over: even if that reference shows "
    "the chair in a three-quarter product view, the chair here is turned so its "
    "seat opening faces the seated person directly."
)


# 좌석 슬롯에서 배치·참조 위치 고정 표현을 뺀다 (2026-10-24, R228). 왜(Why):
# R226 을 실기로 돌린 결과 좌석 개구부가 앉는 사람 쪽으로 **많이** 돌아왔으나
# 아직 어긋났다(사용자: "많이 좋아졌는데 아직 다른 곳을 보고 있어"). 최종
# 프롬프트(영어 9043자)를 뽑아 보니 방향을 되돌리는 조항이 셋이었다 —
#   prop identity guard: … same placement in the frame.
#   contact lock: … rests exactly where it rests in its reference image …
#   seat orientation: … only its turn in the room changes …
# 돌리라는 조항 1개 대 배치를 참조에 묶는 조항 2개라 모델이 타협했다. 좌석
# 슬롯에서만 **배치·참조 위치 고정 표현을 제거**한다 — 형태·실루엣·재질·개수와
# 바닥 접촉은 그대로 남는다. 문자열은 원본 상수에서 **파생**해 단일 출처를 지킨다
# (손으로 복사하면 한쪽만 고치는 사고가 난다 — R225 `_FOOTWEAR_LOCK_TAIL` 교훈).
_FURNITURE_PLACEMENT_FRAGMENT = (
    "same proportions and part count, same placement in the frame")
_FURNITURE_CONTACT_FRAGMENT = (
    "rests exactly where it rests in its reference image, firmly touching the "
    "same surface")
_FURNITURE_CONTACT_SEAT_FRAGMENT = (
    "stands firmly on the ground on the same legs and supports")
# 섞인 슬롯(좌석 + 비좌석)에서 **비좌석** 사물의 배치 고정을 되돌려 준다.
# 좌석만 있는 실행에서는 나가지 않는다. 문장이 갈라지는 이유: 앞의 DNA·contact
# 문장은 모든 슬롯에 공통이라, 좌석만 면제하려면 비좌석 몫을 따로 적어야 한다.
FURNITURE_PLACEMENT_LOCK_NON_SEAT = (
    "Every other object in reference image(s) {slots} also keeps its exact "
    "placement in the frame and rests exactly where it rests in its reference "
    "image."
)


# 배경 슬롯의 사물 충실 가드 (2026-10-22 실측, 파란 동그라미).
# 왜(Why) R158(2026-10-19) 이후에도 필요한가: 그때는 배경 슬롯의 사물 가드를
# 통째로 껐다(접촉·방향·개수 문구가 없는 사물을 만들어 냈다 — 사용자 제보
# "벽 턱·돌 의자"). 그 부작용으로 **참조한 배경 그대로를 요구하는 문구까지**
# 사라져, 배경 참조가 사물이 찍힌 사진일 때 정체성을 지키는 말이 하나도 남지
# 않았다. 실측(2026-10-22 01:40, 좌.png, seed 42, cfg 1.0): 참조의 검은 원기둥
# 다리 4개가 갈색 목재 각진 다리로 바뀌고 앞다리가 신발 속으로 들어가 바닥에
# 닿지 않았다. positive 에 사물 문구 0개, cfg 1.0 이라 negative 는 무효 —
# lever 자체가 없었다.
# 그래서 **존재를 요구하지 않는 조건문 하나**만 되살린다: 있으면 참조 그대로,
# 없으면 만들지 말 것. 접촉·방향·개수(단일 인스턴스) 강요는 R158 대로 계속
# 끈다 — 그 문구들이 "없는 사물" 을 만든 원인이었다.
# {slots} 자리표시자는 FURNITURE_COLOR_POSITIVE 의 {color} 와 같은 방식이다.
FURNITURE_BACKGROUND_POSITIVE = (
    "background fidelity guard: the frame keeps the exact content of reference "
    "image {slots}. If any furniture, object or prop from that reference is "
    "visible, it stays exactly as it appears there — same silhouette and "
    "construction, the same number of legs and supports with each leg and "
    "support keeping its own shape, section, length and colour, the same "
    "material and surface finish, the same colours and pattern, the same "
    "proportions. Its legs and supports reach the ground the same way as in "
    "the reference, and no part of the furniture passes through, pierces, "
    "cuts into or disappears into a foot, ankle, calf, hand or arm. Do not "
    "substitute a different object, a different material or a different leg "
    "design, and do not add any furniture, object, ledge, platform or prop "
    "that is not present in reference image {slots}."
)


# 배경 가구의 **지지(받침) 구조** (2026-10-30 사용자 실측). 왜(Why) 위 문구와
# 나눠 쓰나: 위 FURNITURE_BACKGROUND_POSITIVE 는 접지를 "참조에서와 같은 방식"
# (reference-relative)으로만 말한다. 사용자 생성물에서 책상이 배경 슬롯(2번)이라
# 이 문구만 나갔고, 참조의 다리는 오른쪽에 있는데 구도에서 그 자리에 인물이 앉아
# 가려졌다 — 왼쪽 다리의 기준이 사라져 상판이 바닥 위에 떠 보였다.
# 그 문구는 "보이면 참조대로" 라는 조건문이라, 상판을 그리되 그 아래 받침을
# **바닥까지 완성해서 연결하라**는 요구가 없었다(재현: _workspace/probe_desk.py).
#
# R158 규칙은 유지한다 — 조건문("if ... appears")으로 쓰고 "none is added" 로
# 존재 요구를 명시적으로 부정한다. 없는 가구를 만들라고 요구하지 않는다.
# R190 과 같은 이유로 문구를 나눈다 — R189 핀이 흔들리지 않고 한쪽만 조정된다.
#
# R253 (2026-10-30, 두 번째 수정): 이 조항이 있어도 다리가 안 보였다. 사용자가
# v1.9.90 로 다시 생성했는데도 상판 아래가 비어 보였고, ComfyUI 로그로 새 코드가
# 실제로 쓰인 것을 확인했다(코드 문제가 아니다). 원인은 조항이 "받침이 상판
# 아래에서 바닥까지 이어진다"고만 말하고 **화면에 보여야 한다**는 요구가 없는
# 것이다 — 그 구간이 사람 다리·러그로 채워지면 "비어 있지 않다"로 통과한다.
# 그래서 "열린 바닥에서 보이는 다리"를 따로 요구한다. 이 워크플로는 cfg 1.0
# (Qwen-Image 2.1 turbo)이라 negative 는 무시되므로 lever 는 이 positive 뿐이다.
#
# R254 (2026-10-30, 세 번째 수정 — 위치): R253 을 넣고도 다리가 안 보였다
# (같은 워크플로·시드 재생성, 새 코드가 돌은 것을 로그로 먼저 확인). 문구는
# 그대로 두고 **위치만 옮긴다** — 꼬리(배경 가드 안)에서 **장면 문장 뒤**로.
# 근거는 R239(좌석 접촉점)·R248(무대 채택)과 같다: 꼬리에서는 뒤 조항 15개에
# 희석된다. 호출은 `background_support_scene_guard` 가 한다.
FURNITURE_SUPPORT_POSITIVE = (
    "support structure lock: if furniture from reference image {slots} appears "
    "in the frame standing on the floor, it keeps its complete load-bearing "
    "structure — its legs, pedestal or frame run as one connected piece from "
    "under the top all the way down to the floor and visibly hold that top up. "
    "At least one of its legs or supports is fully visible in the open floor "
    "area beneath the top: it stands there in plain sight, not cropped by the "
    "edge of the picture and not hidden behind the seated person, the chair or "
    "any other object, so the viewer can see what holds the top up. "
    "The space directly beneath a visible tabletop, desk top or counter top is "
    "never left empty, and such a top is never left hovering with its supports "
    "missing, cut short of the floor or detached from it. If no such furniture "
    "is present in the reference, none is added."
)

# 위 지지 조항의 짝 negative. emit 지점은 _assemble_negative 의
# `if flags.get("furniture_bg")` 블록이다(OBJECT_DRIFT_NEGATIVE 와 함께).
# 실 실행 워크플로는 cfg 1.0 이라 negative 가 약하지만, 저장소 관례대로 다른
# cfg 워크플로를 위해 positive/negative 짝을 만든다.
FURNITURE_BACKGROUND_NEGATIVE = (
    "unsupported tabletop, tabletop with no visible legs, table top hovering "
    "with nothing underneath, missing table leg, missing desk leg, table leg "
    "that stops short of the floor, table leg fading out into the floor, leg "
    "disconnected from the tabletop, tabletop and base detached from each "
    "other, furniture resting on invisible legs, empty unsupported space under "
    "a table, table with no leg in sight, table leg completely hidden behind "
    "the person, table leg cropped out of the picture"
)


# R190 (2026-10-22): 배경으로 지정한 참조의 **방(바닥·러그·벽)** 이 가드 밖이었다.
#
# 왜(Why): 사용자가 시드 7 생성물을 탈락시켰다 — "바닥 타일이 바뀌었다".
# 실측(_workspace/chair_case/floor_cmp.png): 참조와 시드 100·1234·2026 은 나무
# 마루인데 시드 7 만 큼직한 밝은 타일이었다. 바로 위
# FURNITURE_BACKGROUND_POSITIVE 는 "any furniture, object or prop" 만 지명해
# 바닥·러그·벽에는 **구체 요구가 하나도 없었다**(도입부 한 문장뿐).
#
# R158 규칙은 유지한다 — "참조에 **보이는** 표면" 만 말하고 **존재를 요구하지
# 않는다**. 러그를 요구하면 참조에 없는 러그가 생긴다(R158 의 원인이 그것이었다).
# 그래서 조건부로 쓴다: 있으면 그대로, 없으면 만들지 말 것.
#
# {slots} 자리표시자는 위 문구와 같은 방식이다. 배선은 늘리지 않는다 —
# `_furniture_background_guard` 가 이어 붙이므로 플래그(furniture_bg)·plan 키
# (furniture_bg_slots)·짝 negative(OBJECT_DRIFT_NEGATIVE)가 그대로 따라온다.
SCENERY_BACKGROUND_POSITIVE = (
    "surface fidelity guard: the surfaces visible in reference image {slots} "
    "stay as they are there — the same floor or ground surface, the same "
    "material and the same pattern or structure running in the same direction, "
    "the same rug, carpet or mat with the same pattern, texture and colour, "
    "and the same wall, ceiling, window, curtain and door surfaces. Outdoor "
    "ground counts as a surface too — dirt, gravel, stone paving, cobblestones, "
    "sand, grass or rock keeps the ground material, colour, texture and surface "
    "detail it has in reference image {slots}. None of those surfaces is "
    "restyled, recoloured, covered up or swapped for a different material or "
    "pattern — a wood plank floor stays a wood plank floor and does not become "
    "large pale tiles, a stone paving stays stone paving and does not become "
    "smooth pale concrete, and the reverse."
)


# 배경 참조 광원 우선 (2026-10-28, 두 번째 수정). 왜(Why) 이 조항이 필요한가:
# 사용자가 조명을 **자동**으로 두면 카메라가 조명을 스스로 채운다(구도 규칙·
# 이미지 힌트·기본 창가빛). 그 자동 조명이 참조 배경의 광원과 충돌할 수 있다.
# 사용자 결정(2026-10-28): 조명이 자동이면 **참조 배경이 기준**이고, 카메라가
# 자동으로 채운 조명은 **피사체에만** 적용된다. 조명을 직접 고르면 그 설정이
# 1순위이고 이 조항 자체를 붙이지 않는다(카메라 설정 무력화 금지).
#
# 왜(Why) 조명 이름을 나열하지 않나: 위 표면 문구가 "the same light direction and
# colour temperature" 를 **무조건** 말해 사용자가 고른 조명과 충돌했다. 이름을
# 나열하는 대신 "이 프롬프트의 다른 조명은 피사체에만" 이라는 일반 종속을 건다 —
# 창가빛·림라이트·골든아워·이미지 힌트 무엇이든 같은 문장이 덮는다.
# 발동은 **배경 참조가 있고 사용자가 조명을 명시하지 않았을 때만**이다. 판정은
# 라벨이 아니라 `light_explicit` 하나다 — 라벨을 다시 해석하면 한쪽만 뒤처진다
# (직전 커밋이 "스튜디오 라벨이면" 이라는 두 번째 해석으로 정확히 그랬다).
BACKGROUND_LIGHT_RECONCILE_POSITIVE = (
    "background light guard: the light of reference image {slots} is the base "
    "for the scene — its direction, shadow direction and colour temperature "
    "carry into the result. Any other lighting described in this prompt shapes "
    "the subject only: it does not flatten, brighten, even out or recolour the "
    "background, and it does not remove the shadows the reference light casts. "
    "The described mood may still shift the subject's own light without "
    "replacing the reference background light."
)


# 무대 채택 (2026-10-30 사용자 실측). 왜(Why) 이 조항이 필요한가: 사용자가 배경
# 참조(2번)를 지정했는데 **장면 글에 장소 설명이 없으면** 결과가 그 장소가 아니라
# 주제 참조(1번)의 평범한 배경(회색 스튜디오)을 그대로 유지했다. 배경 충실·표면·
# 광원 가드(위 세 문구)는 모두 "보이는 사물·표면·광원을 지켜라" 를 말할 뿐
# **무대가 어디인가**는 말하지 않는다. 사용자가 장소를 한 줄 더 적으면(장면
# 51자 → 157자, 나머지 동일) 같은 실행이 성공했다 — 즉 문구가 아니라 "무대가
# 어디인가" 를 말하는 문장의 부재가 원인이다.
# 위치: 위 문구들처럼 꼬리에 두면 뒤 조항 15개에 희석된다(R239 실측). 그래서
# `background_scene_adopt_guard` 는 run_prompt 가 **장면 문장 바로 뒤**에 둔다.
BACKGROUND_SCENE_ADOPT_POSITIVE = (
    "scene adoption guard: the location of this shot is the place shown in "
    "reference image {slots}, and the whole frame stands in that place. The "
    "background behind the other reference images is not the scene — a plain "
    "studio or plain wall backdrop there does not carry over, and the "
    "background of the result is the place of reference image {slots}."
)


# 장소·배경 설명 어휘 (2026-10-30). ㉡ 경고의 판정에만 쓴다 — 문구 생성에는
# 쓰지 않는다. 왜(Why) 목록을 짧고 분명한 낱말로 제한하나: 이 판정은 "장소
# 설명이 없다" 를 알리는 **로그**라 오탐이 쌓이면 사용자가 경고를 무시하게 된다.
# 그래서 몸·사물·동작·역할 낱말과 겹치는 것은 넣지 않는다:
#   다리(leg/distance) · 방(방법) · 문(문장) · 길(길이) · 산(산들) · 집(집중) ·
#   시장(mayor) · 사원(employee) · 배경/장소/setting/background(역할 선언에 늘 나옴)
# 놓치는 쪽(recall)을 감수하고 틀린 경고(FP)를 줄이는 쪽을 택한다.
PLACE_DESCRIPTION_WORDS = (
    # 한국어 — 실내 공간
    "실내", "실외", "골목", "골목길", "뒷골목", "광장", "마당", "테라스",
    "발코니", "옥상", "부엌", "주방", "침실", "거실", "서재", "복도", "계단",
    "카페", "식당", "상점", "가게", "도서관", "박물관", "사무실", "교실",
    "병원", "성당", "교회", "궁궐", "화장실", "창고", "무대", "부두",
    # 한국어 — 야외·지형
    "바다", "해변", "해안", "해수욕장", "강가", "호수", "계곡", "사막",
    "들판", "초원", "숲", "정글", "항구", "마을", "시골", "도심", "풍경",
    "자연", "공원", "운동장", "경기장", "수영장", "바닷가", "해수면",
    # 영문
    "alley", "street", "plaza", "garden", "yard", "terrace", "balcony",
    "rooftop", "kitchen", "bedroom", "living room", "hallway", "corridor",
    "staircase", "stairs", "cafe", "restaurant", "market", "shop", "store",
    "library", "museum", "office", "classroom", "church", "temple",
    "beach", "shore", "coast", "lake", "valley", "desert", "meadow",
    "forest", "jungle", "harbor", "harbour", "village", "countryside",
    "city", "downtown", "seaside", "scenery", "landscape", "interior",
    "exterior", "indoors", "outdoors", "park", "courtyard", "ruins",
)


def _ascii_word_in(t: str, w: str) -> bool:
    """영문 낱말 w 가 t 안에 **단어 경계**로 있는가 (t 는 소문자 가정).

    왜(Why) re 를 안 쓰나: 이 모듈은 re 를 함수 안에서만 지연 import 한다
    (위 gaze 판정 참조). 여기서도 같은 방식을 유지하려고 경계를 직접 본다 —
    "park" 이 "parking" 에, "shop" 이 "shopping" 에 걸리는 것을 막는다.
    """
    start = 0
    n = len(w)
    while True:
        i = t.find(w, start)
        if i < 0:
            return False
        before = t[i - 1] if i > 0 else ""
        after = t[i + n] if i + n < len(t) else ""
        if not ("a" <= before <= "z") and not ("a" <= after <= "z"):
            return True
        start = i + 1


def place_description_present(text: str) -> bool:
    """장면 글에 장소 설명이 있는가 (㉡ 경고 판정 전용, 2026-10-30).

    한글은 부분 일치, 영문은 **단어 경계**로 본다 — "park" 이 "parking" 에,
    "shop" 이 "shopping" 에 걸리는 것을 막는다. 놓치는 쪽을 감수하고 오탐을
    줄이는 판정이다(위 목록 주석 참조).
    """
    t = (text or "").lower()
    for w in PLACE_DESCRIPTION_WORDS:
        if _ascii_only(w):
            if _ascii_word_in(t, w):
                return True
        elif w in t:
            return True
    return False


def _furniture_dna_guard(text: str, object_slots, seat_slots=None) -> str:
    """가구·사물 DNA positive 문구. 사물 슬롯이 없으면 "".

    기본값(사용자 지적 반영): topic에 "2번 침대 원본"을 **안 써도** 켜져야 한다.
    사물도 참조가 곧 DNA이므로, 참조로 들어온 사물은 사용자가 별도로 지시하지
    않는 한 형태를 그대로 따라야 한다. 오직 style/mood/lighting 전용으로
    명시된 슬롯만 예외로 뺀다.

    seat_slots (2026-10-24, R226): 좌석 관계인 슬롯(의자에 앉는다). 그 슬롯은
    **방향 조항 하나만** 좌석 방향 문구(SEAT_ORIENTATION_POSITIVE)로 갈아 끼운다.
    `prop identity guard`·`contact lock`·`single instance guard` 는 그대로 남겨
    형태·접촉·개수 충실(R158/2026-10-22)을 지킨다. 기본값 None 이면 종전과
    **바이트 동일**하다 — 기존 호출·검사(한 인자)는 아무것도 바뀌지 않는다.

    R228 (2026-10-24): 좌석 슬롯에서는 배치·참조 위치 고정 표현도 뺀다. R226 뒤
    실기에서 좌석 방향이 **부분적으로만** 돌아왔고, 최종 프롬프트에 방향을
    되돌리는 조항이 둘(`same placement in the frame` · `rests exactly where it
    rests in its reference image`) 남아 `seat orientation` 과 경쟁했다. 좌석
    슬롯에서만 그 두 표현을 제거하고 바닥 접촉은 유지한다. 섞인 슬롯이면 비좌석
    몫의 배치 고정을 별도 문장(FURNITURE_PLACEMENT_LOCK_NON_SEAT)으로 되돌린다.
    """
    try:
        slots = sorted(int(x) for x in set(object_slots or []))
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    # 좌석 슬롯은 **대상 사물 슬롯과의 교집합**으로 좁힌다. 좌석 어휘가 있어도
    # 사물 DNA 대상이 아니면(의상·배경 등) 방향을 바꾸지 않는다.
    try:
        seat = set(int(x) for x in set(seat_slots or [])) & set(slots)
    except (TypeError, ValueError):
        seat = set()
    # 배경 슬롯은 사물 DNA 대상이 아니다 (2026-10-19 사용자 제보). 배경은 장면
    # 이라 객체 형태·접촉·방향을 강요하면 안 된다. _object_dna_slots 가 이미
    # 배경 슬롯을 제외하지만, 호출자가 직접 넘기는 경우까지 막는다. **넘어온
    # 사물 슬롯이 전부 배경이면** 문구를 내지 않는다(배경+진짜 가구가 섞인
    # 경우엔 가구 문구를 유지한다 — 배경이 하나 있다고 가구 가드가 통째로
    # 꺼지면 그 가구 DNA 가 사라진다).
    try:
        _bg = _background_role_slots(text or "")
        if _bg and not (set(slots) - _bg):
            return ""
    except Exception:
        pass
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
    # 좌석 슬롯이면 방향 조항만 갈아 끼운다 (2026-10-24, R226). 섞이면 좌석/비좌석
    # 목록을 나눠 각 문구의 지목을 좁힌다 — orientation lock 은 비좌석 슬롯에만,
    # seat orientation 은 좌석 슬롯에만 걸리게 한다.
    _seat_list = ", ".join(str(x) for x in sorted(seat))
    _non_list = ", ".join(str(x) for x in slots if x not in seat)
    if seat and not _non_list:
        orient = SEAT_ORIENTATION_POSITIVE.format(slots=_seat_list)
    elif seat:
        orient = (SEAT_ORIENTATION_POSITIVE.format(slots=_seat_list)
                  + " " + FURNITURE_ORIENTATION_POSITIVE
                  + f" This applies specifically to reference image(s) "
                    f"{_non_list}.")
    else:
        orient = FURNITURE_ORIENTATION_POSITIVE
    # 좌석 슬롯은 배치·참조 위치 고정 표현을 뺀다 (2026-10-24, R228). 좌석이
    # 없으면 원본 상수를 그대로 써서 종전과 바이트 동일하다.
    if seat:
        dna = FURNITURE_DNA_POSITIVE.replace(
            _FURNITURE_PLACEMENT_FRAGMENT, "same proportions and part count")
        contact = FURNITURE_CONTACT_POSITIVE.replace(
            _FURNITURE_CONTACT_FRAGMENT, _FURNITURE_CONTACT_SEAT_FRAGMENT)
    else:
        dna = FURNITURE_DNA_POSITIVE
        contact = FURNITURE_CONTACT_POSITIVE
    parts = [dna + f" This applies specifically to reference image(s) {listed}."]
    # 섞인 슬롯이면 비좌석 몫의 배치 고정을 되돌린다 (좌석만이면 나가지 않는다).
    if seat and _non_list:
        parts.append(FURNITURE_PLACEMENT_LOCK_NON_SEAT.format(slots=_non_list))
    parts.append(contact)
    parts.append(orient)
    parts.append(OBJECT_INSTANCE_POSITIVE)
    return " ".join(parts)


def _is_mood_only_background(text: str) -> bool:
    """배경 슬롯 지정이 분위기·스타일 전용인가 (사물·장소가 아님).

    왜(Why) 헬퍼로 뽑나 (2026-10-30): `_furniture_background_guard` 와
    `background_scene_adopt_guard` 가 **같은 게이트**를 써야 한다 — 두 벌로
    적으면 한쪽만 갱신돼 "배경 충실 가드는 꺼졌는데 무대 채택은 켜지는" 어긋남이
    생긴다(이 저장소가 여러 번 겪은 이음새 결함).
    """
    t = (text or "").lower()
    return any((_ko_word_present(t, k) if not _ascii_only(k) else k in t)
               for k in NON_OBJECT_SLOT_KEYWORDS)


def _furniture_background_guard(text: str, background_slots,
                                light_explicit: bool = False) -> str:
    """배경 슬롯 전용 **조건부** 충실 문구. 대상이 없으면 "".
    두 문구를 이어 붙인다 — 가구·사물(R189) + 표면(R190, 2026-10-22).
    (지지 구조 조항(R252)은 2026-10-30 R254 에서 **장면 문장 뒤**로 옮겼다 —
    `background_support_scene_guard` 참조. 꼬리에서는 뒤 조항 15개에 희석된다.)

    _furniture_dna_guard 와 문구를 나눠 쓰는 이유: 그쪽은 "그 사물이 화면에
    있다" 를 전제하는 접촉·방향·개수 문구를 포함하고, 2026-10-19 사용자 제보
    (R158)로 배경 슬롯에서 통째로 빠졌다. 배경에는 그 전제가 성립하지 않지만
    **참조한 배경 그대로**는 요구되어야 한다 — 그 요구를 말하는 문구가 사라져
    모델이 사전 지식으로 다시 그렸다(2026-10-22 실측). 그래서 선택은
    `_background_dna_slots` 가 따로 하고 문구는 여기서 조건문으로 낸다.

    표면 문구(SCENERY_BACKGROUND_POSITIVE)를 따로 둔 이유: 사용자가 시드 7 을
    탈락시킨 것이 바닥 재질이었고(2026-10-22), R189 문구는 가구만 지명해
    바닥·러그·벽에 구체 요구가 없었다. 문구를 나눠 두면 한쪽만 조정할 수 있고
    R189 핀이 흔들리지 않는다.

    light_explicit (2026-10-28, 선택): 사용자가 조명·그레이드를 **직접** 골랐는가.
    False(기본)면 참조 배경 광원 우선 조항을 붙인다 — 조명이 자동일 때 참조가
    기준이라는 사용자 결정이다. True 면 붙이지 않는다 — 사용자가 고른 설정이
    1순위이고 참조가 그것을 덮으면 안 된다. 생략하면 종전과 **바이트 동일**하다
    (기존 호출·검사가 아무것도 바뀌지 않는다).
    """
    try:
        slots = sorted(int(x) for x in set(background_slots or []))
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    # 분위기 전용 지정이면 형상을 요구하지 않는다 — _furniture_dna_guard 의
    # 완화와 **같은 판정**을 쓴다(두 곳이 갈라지면 한쪽만 발동한다).
    if _is_mood_only_background(text):
        return ""
    listed = ", ".join(str(x) for x in slots)
    out = (FURNITURE_BACKGROUND_POSITIVE.format(slots=listed)
           + " " + SCENERY_BACKGROUND_POSITIVE.format(slots=listed))
    # 조명이 자동일 때만 참조 광원을 기준으로 삼는다. 사용자가 조명을 골랐으면
    # (light_explicit) 그 설정이 1순위다 — 참조가 덮지 않는다.
    if not light_explicit:
        out += " " + BACKGROUND_LIGHT_RECONCILE_POSITIVE.format(slots=listed)
    return out


def background_scene_adopt_guard(text: str, background_slots) -> str:
    """배경 참조의 **장소**를 무대로 채택하는 조항. 대상이 없으면 "".

    왜(Why) 별도 문구인가 (2026-10-30 사용자 실측): 배경 참조(2번)를 지정했는데
    장면 글에 장소 설명이 없으면 결과가 그 장소가 아니라 **주제 참조(1번)의
    평범한 배경**(회색 스튜디오)을 그대로 유지했다. 기존 배경 가드 셋
    (`_furniture_background_guard` 가 내는 문구들)은 모두 "보이는 사물·표면·광원을
    지켜라" 를 말할 뿐 **무대가 어디인가**는 말하지 않는다. 사용자가 장소를 한 줄
    더 적으면(장면 51자 → 157자, 나머지 동일) 같은 실행이 성공했다 — 즉 원인은
    문구가 아니라 그 문장의 부재다.

    위치: 꼬리에 두면 뒤 조항 15개에 희석된다(R239 실측). 그래서 run_prompt 가
    이 조항을 **장면 문장 바로 뒤**에 둔다(`_user_text`).

    판정: `_furniture_background_guard` 와 **같은 게이트**(배경 슬롯 + 분위기 전용
    제외)를 쓴다 — 두 벌이면 한쪽만 갱신돼 어긋난다(이 저장소의 이음새 결함).
    """
    try:
        slots = sorted(int(x) for x in set(background_slots or []))
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    if _is_mood_only_background(text):
        return ""
    return BACKGROUND_SCENE_ADOPT_POSITIVE.format(
        slots=", ".join(str(x) for x in slots))


def background_support_scene_guard(text: str, background_slots) -> str:
    """배경 가구의 **지지(받침)** 조항 — 장면 문장 뒤에 두는 몫. 없으면 "".

    왜(Why) `_furniture_background_guard` 에서 떼어내나 (2026-10-30 R254 실측):
    R252·R253 이 그 조항을 꼬리에 실었는데, 사용자가 같은 워크플로·시드(42)로
    두 번 재생성해도 상판 아래가 비어 있었다. ComfyUI 로그로 새 코드가 돌은 것을
    먼저 확인했으므로(12:38 v1.9.90 loaded → 12:39·12:40 생성) 원인은 코드가 아니라
    **위치**다. 이 저장소는 같은 형태를 이미 두 번 실측했다 — 좌석 접촉점(R239)과
    무대 채택(R248) 모두 **문구는 옳고 위치가 틀렸다**: 꼬리에서는 뒤 조항 15개에
    희석되고 장면 문장 뒤에서는 살아났다(의자 소실 → 회복). 그래서 문구는 한 글자도
    바꾸지 않고 **위치만** 옮긴다.

    판정: `_furniture_background_guard`·`background_scene_adopt_guard` 와 **같은
    게이트**(배경 슬롯 + 분위기 전용 제외)를 쓴다 — 두 벌이면 한쪽만 발동한다.

    호출 지점: run_prompt 는 장면 문장 뒤(scene_adopt 다음)에 두고, base run 은
    꼬리에 둔다 — R248 과 **같은 배치 규칙**이다(실패 경로가 run_prompt 이다).
    """
    try:
        slots = sorted(int(x) for x in set(background_slots or []))
    except (TypeError, ValueError):
        return ""
    if not slots:
        return ""
    if _is_mood_only_background(text):
        return ""
    return FURNITURE_SUPPORT_POSITIVE.format(
        slots=", ".join(str(x) for x in slots))


# 참조 사물 외형 고정 (2026-10-16 실측, 파란 동그라미): 의자 참조(image_2)의
# 등받이 세로 채널 터프팅이 결과물에서 사라지고(등받이 프로파일 std 6.86 ->
# 0.92) 색이 밝아졌다. FURNITURE_DNA 는 "정체성을 유지하라"는 일반 문구라
# **어떤 특징**을 지켜야 하는지 지명하지 못한다. denoise=1.0 에서 참조 픽셀이
# 거의 안 쓰이므로(카메라 자신의 경고) 문구가 유일한 전달 경로다.
# 색은 참조에서 읽는다(object_color_name) — 기존 color_adherence_guard 는
# 주제 **텍스트**만 보므로 주제에 사물 색이 없는 이번 실패를 잡지 못한다.
# 왜(Why) "tufting" 을 positive 에 쓰지 않는가: 매끈한 사물에 터프팅을
# 만들어 넣을 수 있다. 지켜야 할 것은 **있는 그대로**이지 특정 장식이 아니다.
FURNITURE_SURFACE_POSITIVE = (
    "surface structure lock: the referenced object keeps the exact surface "
    "structure and finish of its reference image — the same seams, panel "
    "divisions and surface detail in the same places, with nothing smoothed "
    "away, filled in, flattened or simplified. Its surface is never re-rendered "
    "as a blank, featureless flat panel."
)

FURNITURE_COLOR_POSITIVE = (
    "surface colour lock: that object's surface colour stays exactly "
    "{color}, at the same warmth and saturation as its reference — not "
    "desaturated toward neutral gray, not lightened, not bleached, not shifted "
    "toward white."
)

FURNITURE_SURFACE_NEGATIVE = (
    "smoothed-away surface detail, erased seams, flattened upholstery, plain "
    "unseamed panel, blank featureless flat surface, surface detail filled in, "
    "simplified surface texture, bleached fabric, whitened upholstery, "
    "washed-out colour, colour drifting toward white, neutral gray upholstery, "
    "desaturated off-white, cool gray-white fabric, colour drained toward gray"
)


# 사물 표면 특징어 (2026-10-16, B안). 검출로 특징을 **지명하는** 방식은 실측
# 기각됐다 — 매끈한 좌방석 대조군에서도 세로 봉우리 3개가 나와, 지명하면 매끈한
# 사물에 없는 터프팅을 만들어 넣게 된다(33-4). 안전한 대안은 **사용자가 주제에
# 직접 적는 것**이다. 그러면 번역을 거쳐 프롬프트에 실린다 — 다만 일반 문구들에
# 묻히므로, 특징어가 있으면 가드가 그 특징을 **강조 재진술**한다.
# 왜(Why) "홈" 을 빼는가: 한 글자라 "홈페이지" 같은 단어에 걸린다.
_OBJECT_FEATURE_WORDS = (
    ("tufting", ("터프팅", "tufting", "tufted")),
    ("channel tufting", ("채널", "channel", "channels", "channeled")),
    ("seams", ("이음선", "이음새", "seam", "seams", "seaming")),
    ("quilting", ("퀼팅", "quilting", "quilted")),
    ("piping", ("파이핑", "piping")),
    ("pleats", ("주름", "pleat", "pleats", "pleated")),
    ("surface pattern", ("무늬", "패턴", "pattern", "patterned")),
    ("weave", ("직조", "짜임", "weave", "woven")),
    ("stitching", ("스티치", "박음질", "stitch", "stitches", "stitching")),
)

OBJECT_FEATURE_POSITIVE = (
    "surface feature lock: that object is rendered with the {features} named "
    "for it, clearly and at full strength — each one reads as real relief with "
    "its own shadow on the surface, never as a flat printed mark, and it is "
    "never smoothed away or simplified."
)


def _object_feature_words(text) -> list:
    """주제에서 사물 표면 특징어를 뽑는다 (한글·영문). 없으면 빈 리스트."""
    try:
        t = (text or "").lower()
        found = []
        for canon, keys in _OBJECT_FEATURE_WORDS:
            for k in keys:
                if (_ko_word_present(t, k) if not _ascii_only(k) else k in t):
                    if canon not in found:
                        found.append(canon)
                    break
        # "세로 채널 터프팅" 은 둘 다 잡힌다 — 더 구체적인 쪽만 남긴다
        # (문구가 "the tufting, channel tufting" 으로 겹쳐 읽히는 것을 막는다).
        if "channel tufting" in found and "tufting" in found:
            found.remove("tufting")
        return found
    except Exception:
        return []


def _object_feature_guard(text) -> str:
    """주제에 적힌 사물 표면 특징을 강조 재진술. 없으면 "".

    이 문구는 `object_appearance_guard` 의 **표면 구조 positive 에 붙는다** —
    짝인 negative(FURNITURE_SURFACE_NEGATIVE)는 이미 "erased seams, flattened
    upholstery, blank featureless flat surface" 를 낸다. 그래서 새 키·새 플래그
    없이도 positive/negative 짝이 유지된다(이음새를 늘리지 않는다).
    """
    feats = _object_feature_words(text)
    if not feats:
        return ""
    return OBJECT_FEATURE_POSITIVE.format(features=", ".join(feats))


def object_appearance_guard(text, slot_images, object_slots):
    """참조 사물의 대표색을 읽어 외형 고정 문구를 만든다 → (positive, negative).

    text         : 주제+장면 원문 (분위기 전용 슬롯 완화 판정에 쓴다).
    slot_images  : {라벨(int): IMAGE} — 실제로 연결된 슬롯만.
    object_slots : _object_dna_slots 가 고른 라벨 집합.

    왜(Why) 여기서 색을 이미지에서 읽는가 (2026-10-16): 기존 색상 가드
    (color_adherence_guard)는 주제 **텍스트**에서 색상어+의류명사 인접만 본다.
    이번 실패는 주제에 의자 색이 없었고 참조에만 있었다 — 텍스트 경로로는
    잡히지 않는다.

    색을 못 읽어도 표면 구조 문구는 남긴다 — 그건 참조만 있으면 성립한다.
    슬롯 자체가 없으면 ("", "") 이다.
    """
    try:
        slots = sorted(int(x) for x in set(object_slots or []))
    except (TypeError, ValueError):
        return "", ""
    if not slots or not slot_images:
        return "", ""
    # 배경 슬롯이 지정됐으면 외형·표면 고정도 끈다 (2026-10-19 사용자 제보).
    # _furniture_dna_guard 와 **같은 판정**을 쓴다 — 두 곳이 갈라지면 한쪽만
    # 발동해 배경에 표면 잠금이 남는다.
    try:
        if _background_role_slots(text or ""):
            return "", ""
    except Exception:
        pass
    t = (text or "").lower()
    # 분위기 전용 지정이면 사물 외형을 요구하지 않는다. _furniture_dna_guard 의
    # 완화와 **같은 판정**을 쓴다 — 두 곳이 갈라지면 한쪽만 발동한다.
    if any((_ko_word_present(t, k) if not _ascii_only(k) else k in t)
           for k in NON_OBJECT_SLOT_KEYWORDS):
        return "", ""
    names = []
    for slot in slots:
        img = slot_images.get(slot)
        if img is None:
            continue
        nm = object_color_name(img)
        if nm and nm not in names:
            names.append(nm)
        if len(names) >= 2:
            break
    pos = FURNITURE_SURFACE_POSITIVE
    if names:
        pos = pos + " " + FURNITURE_COLOR_POSITIVE.format(
            color="/".join(names))
    # B안 (2026-10-16): 주제에 적힌 표면 특징을 강조 재진술한다. 짝인 negative
    # 는 아래 FURNITURE_SURFACE_NEGATIVE 가 이미 낸다 — 새 이음새를 만들지 않는다.
    _feat = _object_feature_guard(text)
    if _feat:
        pos = pos + " " + _feat
    return pos, FURNITURE_SURFACE_NEGATIVE


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
        # 선언된 의상 슬롯도 사물 DNA 대상이 **아니다** (2026-10-24, R225).
        # 왜(Why): `3번: 하이 힐` 처럼 선언된 슬롯은 "입을 옷/신을 신발" 이지
        # 화면에 놓인 소품이 아니다. 사물 DNA 는 접촉·방향·개수·배치를 고정
        # 하므로 입는 물건에 붙으면 정반대 지시가 된다 — 실측: 최종 프롬프트에
        # `prop identity guard … applies specifically to reference image(s) 2, 3`
        # 이 나가 신발 참조 3번이 제품샷 자세로 고정됐고, 같은 슬롯을 향하는
        # 문구는 어디에도 없었다. 부수 효과로 사물 표면 대표색 가드도 그 슬롯을
        # 읽지 않는다(제품샷 색을 사물 표면색으로 굳히던 경로가 함께 사라진다).
        # 회귀 위험 낮음: 의상 선언이 없는 입력은 plan["outfits"] 가 빈 집합이다.
        excluded |= set(plan["outfits"])
        # 배경 슬롯은 사물 DNA 대상이 **아니다** (2026-10-19 사용자 제보).
        # 배경은 장면이지 가구·사물이 아니다 — "배경: 2번 이미지" 를 사물로
        # 취급하면 contact lock·seat backs·orientation lock 이 나가 모델이
        # 그 객체를 만들어낸다(실측: 생성물에 벽 턱·돌 의자). 완전 제외한다.
        try:
            excluded |= set(_background_role_slots(topic or ""))
        except Exception:
            pass
        return {x for x in labels if x not in excluded}
    except Exception:
        return set()


def _background_dna_slots(topic: str, image_labels, image_count: int) -> set:
    """배경으로 지정된 슬롯 — 조건부 충실 가드 대상 (2026-10-22).

    왜(Why) _object_dna_slots 와 따로 두나: 개념이 다르다. 사물 DNA 슬롯은
    "그 사물이 화면에 있다" 를 전제하는 접촉·방향·개수 문구를 포함하고,
    2026-10-19 사용자 제보(R158)로 배경 슬롯에서 통째로 빠졌다. 배경은 그
    전제가 성립하지 않지만 **참조한 배경 그대로**는 요구되어야 한다 — R158
    이후 그 요구를 말하는 문구가 사라져 모델이 자기 사전 지식으로 다시
    그렸다(2026-10-22 실측: 의자 다리 4개가 목재로 바뀌고 앞다리가 신발에
    끼어 바닥에 닿지 않았다). 선택은 따로, 문구는 조건문으로.
    """
    try:
        if image_count <= 0:
            return set()
        labels = [int(str(x)) for x in (image_labels
                                       or list(range(1, image_count + 1)))]
        bg = set(_background_role_slots(topic or ""))
        if not bg:
            return set()
        plan = _person_object_plan(topic or "", labels)
        # 주 피사체·추가 인물·포즈 슬롯은 배경일 수 없다 — 배경 어휘가 그
        # 슬롯을 가리키는 오검출을 여기서 막는다(R158 이 줄바꿈 오검출을 막은
        # 것과 같은 이유의 방어선).
        excluded = {plan["main"]} | set(plan["persons"]) | set(plan["poses"])
        return {x for x in labels if x in bg and x not in excluded}
    except Exception:
        return set()


def scene_metric_slot(text: str, image_labels, image_count: int):
    """자동 조명·그레이드 지표를 어느 참조 이미지에서 읽을지 고른다 (2026-10-30, ㉮).

    참조 슬롯 번호(int) 또는 None 을 돌려준다. None 이면 호출자가 종전대로
    1번(주제 참조)에서 읽는다.

    왜(Why) 필요한가 — R248 의 부원인 실측(2026-10-30): 배경 참조(2번)를
    선언해도 자동 조명 지표는 `primary_image`(1번 = 사람)에서 나왔다. 사람
    사진의 어두운 스튜디오 배경이 dark=0.635 (>= 0.62) 로 로우키를 불러 넣는
    동안 정작 장면(2번)은 dark=0.359 로 밝았다. 2026-10-28 사용자 원칙
    ("조명이 자동이면 참조 배경 광원이 기준")은 **문구**에만 적용돼 있었고,
    그 문구가 붙은 판단(로우키)을 만드는 **지표 자체**는 여전히 사람 참조에서
    나왔다 — 문구와 지표가 서로 다른 곳을 가리켰다.

    판정은 `_background_dna_slots`(배경 슬롯 한 벌)에 맡기고, 분위기 전용
    제외도 `_furniture_background_guard` 와 **같은 게이트**를 쓴다 — 두 벌이면
    한쪽만 갱신돼 어긋난다(이 저장소가 여러 번 겪은 이음새 결함).

    배경이 여럿이면 **가장 낮은 번호** 하나를 쓴다. 지금 실패 사례는 배경이
    하나고, 평균은 "무대가 둘" 이라는 뜻이 되어 어느 쪽 톤도 아니게 된다.
    """
    try:
        slots = _background_dna_slots(text or "", image_labels, image_count)
        if not slots:
            return None
        if _is_mood_only_background(text):
            return None
        return min(int(x) for x in slots)
    except Exception:  # noqa: BLE001
        return None


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
    # 의상·역할 감지는 **의도 분석용 코어**로 본다 (2026-10-19). 태그 나열
    # 프롬프트에서 서술 조각("wearing a summer dress")이 교체 동사로 잡혀
    # reference_guard 가 "의상 보존" 분리를 버리는 오탐이 실측으로 확인됐다.
    # **안전 감지기(누드·가림)는 이 함수 밖에서 전체 텍스트를 그대로 보므로**
    # 태그로 날아온 표현이 걸리지 않는다 — 필터는 역할/의상 판정에만 쓴다.
    _intent = intent_core(topic or "")
    _topic = _intent or (topic or "")
    # 동물 전용 주제면 사람 손·피부 품질 문구가 정면 모순이다. 사람/동물
    # 혼재 장면은 사람 가드를 유지한다(사람이 있으면 필요하다). 풍경·사물
    # (사람도 동물도 아님) 은 비인간 장면 가드를 쓴다 — 손·피부 문구를 뺀다
    # (2026-10-25 감사). 판정은 quality_guard_text 한 곳에 모여 있다.
    _quality = quality_guard_text(_topic)
    _only_animal = _quality == QUALITY_GUARD_ANIMAL
    parts = [p for p in [prompt, _quality] if p]
    ref_guard = reference_guard(image_count, image_labels=image_labels, topic=_topic)
    if ref_guard:
        parts.append(ref_guard)
    if not _only_animal:
        # 골반·힙 비율 가드는 사람 전용(동물의 실루엣을 humanoid 비율로
        # 끌고 간다). reference_guard 가 이미 종 보존 문구를 준다.
        body_guard = body_proportion_guard(image_count, _topic,
                                           image_labels=image_labels)
        if body_guard:
            parts.append(body_guard)
    fit_guard = outfit_guard(image_count, topic)
    if fit_guard:
        parts.append(fit_guard)
    # 왜(Why) 조각마다 끝 마침표를 떼고 잇나 (R195, 2026-10-22 실측): 1인
    # reference_guard 가 "…unless the user explicitly requests a clothing
    # change." 처럼 **마침표로 끝난다**. 그대로 ". " 로 이어 붙이면
    # "change.. face and body preservation guard" 처럼 마침표가 두 번 나가고,
    # 마지막 조각이 마침표로 끝나면 끝에도 ".." 가 붙는다. 실측 경로:
    #   positive_text = prompt_out (camera_director.py:2257) — prompt_in 이
    #   비었을 때(topic 만으로 쓰는 정상 사용) 이 함수의 결과가 그대로
    #   사용자 prompt_out 이 된다. 참조 1장 + prompt_in 없음에서 ".." 1곳
    #   재현(ref1-nopin). prompt_in 이 있으면 앵커 재조립 분기라 안 걸린다.
    # 조각이 마침표·공백으로 끝나면 떼고 이어 붙여 마침표를 정확히 한 번만
    # 둔다(빈 조각이 되면 뺀다 — ". . " 같은 구멍을 만들지 않으려는 것).
    _cleaned = [p.strip().rstrip(". ") for p in parts]
    return ". ".join(p for p in _cleaned if p) + "."


def assemble(scene: str, cam: dict, image_count: int = 0, topic: str = "", image_labels=None) -> str:
    """scene + 카메라 + 그레이드 + 범용 품질/정체성 가드 → 영문 prompt_out."""
    scene = (scene or "").strip().rstrip("., ")
    segs = [", ".join(build_clauses(cam)), grade_clauses(cam)]
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
    # 사용자가 직접 지시한 가림. 위험 조합으로 자동 개입하지 않는다
    # (coverage_guard docstring 참고 — 자동 개입이 자세 왜곡을 만든다).
    cover = coverage_guard(topic or scene)
    if cover:
        prompt = prompt.rstrip(". ") + ". " + cover + "."
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

# 한정된 노출 표현 — "이런 모양" 의 요구다. 왜(Why) 별도인가 (2026-10-11):
# "누드/전라" 는 의도 자체를 적는 말이라 노출로 볼 만하다. 하지만 팔을 벌린
# 한 장면이나 다리를 벌린 포즈는 흔한 에디토리얼 구도인데, 그 단어 하나에
# 노출 가드가 붙으면 **가림 자세와 몸 왜곡**이 생긴다(실측). 그래서
# "몸 전체가 드러남" 과 "일부만 드러남" 을 나눠 판정한다.
NUDITY_PARTIAL_KEYWORDS = (
    "bare chest", "bare breasts", "bare back", "bare shoulder", "bare shoulders",
    "open shirt", "unbuttoned", "topless", "bottomless", "leg spread", "legs spread",
    "가슴을 드러", "상체를 드러", "덮이 없", "벗은", "벌린", "벌어선",
)


def _is_partial_exposure(text: str) -> bool:
    """일부만 드러난 구도인가 (팔 전체 노출과는 구분)."""
    t = (text or "").lower()
    return any(keyword in t for keyword in NUDITY_PARTIAL_KEYWORDS)


# 사용자가 "가려줘" 를 직접 지시한 경우 — 판정을 지배한다.
EXPLICIT_COVER_KEYWORDS = (
    "cover", "covering", "hide", "conceal", "shield", "censor", "keep covered",
    "hand over", "hands over", "modest", "keep it covered", "not visible",
    "가려", "가리고", "감춰", "덮어", "보이지 않게", "드러나지",
)

# 사용자가 "드러내줘" 를 직접 지시한 경우 — 가림 가드를 끈다.
EXPLICIT_REVEAL_KEYWORDS = (
    "fully visible", "completely visible", "clearly visible", "fully exposed",
    "uncovered", "exposed",
    "전부 보이", "완전히 보이", "선명하게 보이", "드러나",
)


def _has_any(text: str, keywords) -> bool:
    """키워드 중 하나라도 들어 있으면 True (한글 포함 부분 일치)."""
    t = (text or "").lower()
    return any(keyword in t for keyword in keywords)


# 가림을 직접 요청한 문장인지 — 커버 키워드 포함 여부만 본다
def _wants_explicit_cover(text: str) -> bool:
    return _has_any(text, EXPLICIT_COVER_KEYWORDS)


# 노출을 직접 요청한 문장인지 — 부정형 '드러나지' 를 먼저 지워 오판을 막는다
def _wants_explicit_reveal(text: str) -> bool:
    # 왜(Why) "드러나지" 를 먼저 지우나 (2026-10-11 실측): "드러나지 않게
    # 가려줘" 는 **가림** 요청인데, reveal 키워드 "드러나" 가 그 안에 부분
    # 일치해 노출로 오판됐다 → coverage_guard 가 "" 를 돌려줘 가림 문구가
    # 통째로 사라졌다(실측: "드러나지 않게 가려줘" → ""). 부정형 "드러나지"
    # 를 먼저 제거하면 "드러나게/드러난" 같은 진짜 노출 요청은 그대로 남는다.
    return _has_any((text or "").replace("드러나지", ""),
                    EXPLICIT_REVEAL_KEYWORDS)


def coverage_guard(topic: str) -> str:
    """사용자가 **직접** 가림을 지시했을 때만 가림 문구를 반환한다. 아니면 "".

    왜(Why) 이게 맞는 방향인가 (2026-10-11 실측): 위험 조합(치마 + 다리 벌림)
    에서 가림을 자동으로 넣으면 아까 본 것처럼 **손이 등 뒤로 돌아가는
    부자연스러운 자세**와 몸 왜곡이 생긴다. 모델은 그 자리를 대충 메우려다
    해부물이 망가진다. 그래서 판정 방향을 뒤집었다 — 위험 조합이라도
    **사용자가 지시하지 않으면 아무것도 하지 않는다**(모델이 알아서 결정).
    사용자가 "가려줘" 라고 직접 쓴 경우에만 가림 문구를 붙인다.

    판정: 가림 의도 키워드가 있고, "드러내줘" 지시로 상쇄되지 않았을 때만.
    벌리는 자세나 옷 여부는 판정에 쓰지 않는다 — 지시자의 의도가 우선이다.
    """
    if not _wants_explicit_cover(topic or ""):
        return ""
    if _wants_explicit_reveal(topic or ""):
        return ""
    return ("modest coverage: the clothing drapes and falls closed over the "
            "hips and thighs, the skirt or garment remains in place and fully "
            "covers, the hands rest naturally on the thighs or at the sides, "
            "no gap opens at the hem, no wardrobe malformation, "
            "the pose stays natural and relaxed")


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
    """노출 의도 시 임상적 완성 문구 + 자연스러운 자세 지시를 반환한다.

    왜(Why): 노골적 성적 묘사 요구는 모델의 안전 튜닝에 막혀 프롬프트로
    완전히 극복할 수 없으므로, 노골 표현 대신 완성도 언어로 뭉개짐·변형을
    줄이는 데 그친다. 노출 의도가 없으면 붙지 않는다.

    자세 지시(2026-10-11 실측 추가): 노출 장면에서 모델이 **가리려고 하는
    자세**를 스스로 택하는 오동작이 실제로 반복됐다. 실측 생성물에서 양손이
    등 뒤로 돌아 무릎을 덮고, 다리가 앉은 자세에서 나올 수 없는 각도로
    벌어졌다. 원인은 positive/negative 가 같은 부위를 서로 반대 방향으로
    당긴 것이라 그 압력을 자세로 해소한 결과다. 손·팔·다리가 자연스럽게
    놓이는 자리를 지정해 그 해소 경로를 막는다.

    부분 노출 완화(2026-10-11): 에디토리얼 구도(가슴 상의만 드러남, 다리만
    벌림)도 위 가드가 붙었는데, 이 경우엔 **가림 의도가 아니라 구도 요구**다.
    자세 문구까지 붙으면 오히려 부자연스러운 자세가 유도된다. 그래서 부분
    노출일 때는 자세 지시를 빼고 완성 문구만 남긴다.

    주의: "anatomical/anatomically" 어휘는 학습 데이터 편향상 의학 도판
    풍으로 그려지는 실측 사례가 있어 positive 가드에는 쓰지 않는다.
    negative의 변형 방어는 방향이 반대라 유지한다.
    """
    if not _is_nudity_request(topic or ""):
        return ""
    if _is_partial_exposure(topic or ""):
        return ("natural realistic human body with correct proportions, "
                "soft realistic skin")
    return ("natural realistic human body with correct proportions, "
            "soft realistic skin and clearly defined natural intimate detail, "
            "hands and arms resting naturally on the seat or at the sides, "
            "arms not placed across the body, "
            "legs in a natural relaxed position, natural hip and knee angle")


def macro_detail_guard(topic: str, cam: dict) -> str:
    """매크로 렌즈 + 인물 주제일 때만 미세 결 강조 문구를 반환한다.

    왜(Why): 100mm 매크로는 제품 촬영에도 쓰이므로 렌즈만으로는 모공·솜털
    문구를 붙일 수 없고, 인물 판정이 함께 있어야 제품에 체모 표현이
    들어가는 오작동을 막을 수 있다.
    다중 선택(콤마)이면 **하나라도** 매크로일 때 붙인다 (2026-10-21 감사,
    R181) — 통째로 비교하면 "100mm 매크로 (macro),85mm f/1.4 (bokeh)" 에서
    결 강조가 조용히 사라졌다.
    """
    if (not has_any_label(cam.get("lens"), ("100mm 매크로 (macro)",))
            or not _is_human_subject(topic or "")):
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
        # 왜(Why) "featureless crotch area" 를 뺐나 (2026-10-11 실측):
        # 그 문구는 모델에게 **"그 부위를 뭉개라"** 를 직접 지시한다.
        # 실제 생성물에서 광배근이 비정상적으로 벌어지고 양손이 등 뒤로
        # 돌아 무릎을 덮는 자세가 나왔다 — 모델이 negative 를 문자 그대로
        # 따라간 결과다. 흐림 지시는 제거하고 변형만 막는다.
        out.append("deformed intimate anatomy, distorted body proportions")
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
    "both sides of the body symmetrical, every limb fully formed and whole, "
    "hands and feet drawn as complete "
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
    "extra leg, extra legs, fourth leg, additional leg, duplicate leg, "
    "third leg silhouette, extra limb silhouette, "
    "asymmetric limbs, one arm, one leg"
)


# 손가락 분리 단서 (2026-10-22 사용자 실측, R192). 왜(Why) 별도 상수인가:
# 같은 단서를 전신 가드(손 문장 안)와 상반신 가드(CU/ECU)가 함께 쓴다. 정의를
# 하나로 두어야 한쪽만 고쳐 짝이 어긋나는 사고를 막는다(2026-09-28 실측).
#
# 왜(Why) 이 문구인가: 기존 손 문구는 "경계 또렷 / 뭉갬 없음"이라 **"X가 아니다"**
# 쪽이었다. cfg=1.0 워크플로는 negative conditioning 을 계산조차 하지 않으므로
# (comfy/samplers.py 실측) positive 문구가 유일한 방어인데, diffusion 은 부정문보다
# 그려질 서술에 잘 반응한다. 실측(토픽 위치, 시드 42/43/1234 짝지음): 손가락 구간의
# 피부 run 평균이 3.09→3.48, 2.41→3.13, 2.46→3.04 로 늘고, 확대 사진에서 회색으로
# 번지던 손가락이 분리됐다(3/3). 같은 실측에서 팔·긴 청바지·방·신발 회귀는 없었다.
# 한계(정직): "조금 벌어져 있다"(실측에서 효과를 본 표현)를 그대로 쓰지 않았다 —
# 잡는 손(가방 손잡이·컵)과 충돌하기 때문이다. 그래서 **자세와 무관하게 그릴 수
# 있는** 모양·경계 서술로 적었다. 확률을 올릴 뿐 보장하지 않는다.
FINGER_SEPARATION_POSITIVE = (
    "each finger a separate shape with its own outline and a clear gap "
    "between neighbouring fingers"
)


# 장면 문장 위치에 한 번 더 두는 같은 단서 (2026-10-22 R194 실측).
# 왜(Why) 가드 위치에 더해 장면 문장에도 두나: 실기 A/B(1.9.75 vs 1.9.76, 시드
# 42/43/1234)에서 **가드 위치 단독은 엇갈렸다**(-0.14 / +0.08 / +0.36). 그래서
# 시드를 8개로 늘려 "장면 문장 끝에도 같은 단서를 둔 팔"과 짝지어 재니 평균
# 손가락 구간 피부 run 차이 +0.33(5승 2패 1무)이었고, 뚜렷 개선 3쌍 · 비슷 3쌍 ·
# 소폭 하락 1쌍, 해부 붕괴 0 이었다. 장면 문장은 카메라가 조립하는 텍스트의
# **맨 앞**이라 가드 묶음(끝)보다 먼저 읽힌다.
# 왜(Why) 실측에 쓴 문장 그대로인가: 다른 문장으로 다듬으면 그 측정이 전이되지
# 않는다. 뒤 절 "no fingers merged or blurred together" 는 부정문이라 cfg=1.0 에서
# 효과가 없지만(샘플러가 negative 를 계산조차 하지 않는다), 실측한 문장이므로
# 그대로 쓴다 — 빼면 "측정한 것과 다른 것"이 된다.
# 한계(정직): 이 실측은 팔 **전체**(가드 + 장면 + 사용자 텍스트)의 것이고, 이
# 구현은 사용자 텍스트 쪽을 카메라가 대신 넣을 수 없어 **장면 문장 사본 1개**만
# 넣는다. 그래서 기대 효과는 0 과 +0.33 사이이며 보장이 아니다. 붙인 코드로
# 다시 8시드 재측정하는 것이 맞다(재시작 필요).
SCENE_FINGER_CUE = (
    FINGER_SEPARATION_POSITIVE
    + ", no fingers merged or blurred together"
)


def scene_finger_cue(subject_text: str) -> str:
    """장면 문장 뒤에 붙일 손가락 단서 (사람 주제일 때만).

    왜(Why) 사람 게이트인가: 이 문구는 사람 손가락 서술이다. 동물·사물·풍경
    주제에 붙으면 **없는 손을 그리게 한다** — R192 가드와 같은 게이트를 쓴다.
    왜(Why) 힌트까지 보나: resolve_guard_plan 의 is_human 과 **같은 규칙**이어야
    한다(텍스트 판정 + 참조에서 검출된 사람). 다르면 한쪽만 붙어 방어가 조용히
    어긋난다(2026-09-28 실측과 같은 형태).
    """
    if (subject_text or "").strip() and _is_human_subject(subject_text):
        return SCENE_FINGER_CUE
    try:
        return SCENE_FINGER_CUE if _hint_person_slots() else ""
    except Exception:  # noqa: BLE001
        return ""


# 손 무결성 positive (2026-10-22 R192). 왜(Why) 분리했나: 이 문장이
# LEG_FOOT_INTEGRITY_POSITIVE 안에 "; hands are fully formed …" 로 묻혀 있었다.
# 가드 이름도 주석도 다리·발·종아리 중심이라, 다리 문구를 손보는 사람이 손 문장을
# 통째로 지워도 아무도 모른다(2026-10-07 분리 모듈 누락과 같은 형태). 그래서 손
# 이름을 가진 상수로 빼고 전신·상반신 두 경로가 같은 정의를 참조하게 한다.
HAND_INTEGRITY_POSITIVE = (
    "hands are fully formed with five distinct fingers on each hand, "
    "finger boundaries clear, " + FINGER_SEPARATION_POSITIVE + ", "
    "no fingers merged or blurred together"
)


# 손 배치 가드 (2026-10-24 실측, R220).
# 왜(Why) 새 문구가 필요한가: 손 계열 상수 네 개가 **전부 "한 손 안에서 손가락
# 다섯 개·경계 분리"** 만 말한다(FINGER_SEPARATION_POSITIVE, HAND_INTEGRITY_
# POSITIVE, ANATOMY_COUNT_POSITIVE_UPPER, LEG_FOOT_INTEGRITY_POSITIVE 안의 손
# 문장). 앉아서 "양 손을 무릎에" 올린 실패는 **두 손 사이**에서 났다 — 좌우 손이
# 겹치고 한 덩어리로 합쳐지고 손가락이 서로 넘어갔다. 어느 상수도 그 실패를
# 덮지 않았다.
# 왜(Why) positive 인가: 이 워크플로의 KSampler 는 cfg=1.0 이라 ComfyUI 샘플러가
# negative conditioning 을 계산조차 하지 않는다(LEG_FOOT_INTEGRITY_POSITIVE 와
# 같은 실측). 게다가 denoise=1.0 이라 참조 픽셀이 폐기되어 손의 픽셀 근거가 없다.
# 그래서 **positive 문구가 유일한 방어**다.
# 한계(정직): 확률을 올릴 뿐 보장하지 않는다. 효과는 같은 시드 A/B 로만 잴 수
# 있다(오프라인에서 샘플러 추종을 잴 수 없다).
HAND_PLACEMENT_POSITIVE = (
    "hand placement: where the left hand and the right hand rest, each one "
    "keeps its own place and its own outline, the left hand and the right "
    "hand never overlap and never stack on top of one another and never "
    "merge into a single shape, no finger of one hand reaches across onto "
    "the other hand, the thumbs stay on the outer sides, the palms and the "
    "backs of the hands stay clearly readable where they rest"
)

# 짝 negative. cfg=1.0 에서는 전달되지 않지만(샘플러가 계산하지 않는다),
# cfg>1 워크플로와 식별기 경로를 위해 짝을 함께 둔다 — 한쪽만 붙이면 짝인
# 방어가 조용히 사라진다(2026-09-28 실측).
HAND_PLACEMENT_NEGATIVE = (
    "overlapping hands, one hand stacked on top of the other, the two hands "
    "merged into a single shape, a finger reaching across onto the other "
    "hand, extra long fingers, too many fingers on one hand"
)

# 손 배치 표지 (2026-10-24). 왜(Why) 넓은 "손" 이 아니라 **배치 구문**인가:
# 손이 화면에 있는 것만으로는 두 손이 붙을 위험이 없다. 위험은 손이 **한 곳에
# 모이거나 표면에 놓일 때**다. 넓게 잡으면 관계없는 장면의 결과가 함께 흔들린다.
# 그래서 "손등을·손바닥을" 처럼 위치를 말하지 않는 구문은 넣지 않는다 —
# "손등을 내밀었다" 는 두 손이 붙는 장면이 아니다.
HAND_PLACE_MARKERS = (
    # 한글 — 손이 한 곳에 모이거나 표면에 놓이는 구문
    "무릎에", "무릎 위", "무릎을", "품에", "품 안", "가슴 앞",
    "양손을", "양 손을", "두 손을", "두손을", "한 손을",
    "손을 무릎", "손을 올", "손을 얹", "손을 대", "손을 짚",
    "손을 포개", "손을 겹", "손을 모",
    # 영문 — 같은 뜻 (판정은 단어 경계 + 어미라 "hands"·"her knees" 를 잡는다)
    "on the knees", "on her knees", "on his knees", "on the lap",
    "on her lap", "on his lap", "in her lap", "in his lap",
    "hands on", "both hands", "hands resting", "hands folded",
    "folded hands", "hands together", "hands clasped", "palms down",
)


def hand_placement_marks(text) -> bool:
    """장면이 손을 한 곳에 모으거나 표면에 놓는가 (사람 판정은 호출부 몫).

    왜(Why) 사람 판정을 여기서 안 하나: `resolve_guard_plan` 이 이미 텍스트
    판정과 참조 픽셀 힌트를 합쳐 사람 여부를 정한다. 여기서 다시 판정하면 두
    벌이 갈라져 한쪽만 붙는 사고가 난다(scene_finger_cue 와 같은 규칙).
    왜(Why) 소문자로 넘기나: `_kw_hit` 의 영문 정규식은 단어 경계 + 어미만
    허용하고 대소문자를 구분하지 않는다. cam_physics 도 같은 방식이다.
    """
    try:
        t = (text or "").lower()
        if not t:
            return False
        return _kw_hit(t, HAND_PLACE_MARKERS)
    except Exception:  # noqa: BLE001
        return False



# 다리·발·종아리 무결성 positive (2026-10-21 사용자 실측). 왜(Why) positive 인가:
# 이 워크플로의 KSampler 는 cfg=1.0 이라 ComfyUI 샘플러가 uncond_=None 으로 두고
# **negative conditioning 을 계산조차 하지 않는다**(comfy/samplers.py 실측). 그래서
# ANATOMY_COUNT_NEGATIVE 의 "extra feet/third leg" 는 이 워크플로에서 **전달되지
# 않는다.** 사용자 제보(발 하나 더 생성·종아리 휨·손 이상)는 그 무효를 드러냈다.
# cfg=1.0 에서 실효 방어는 positive 뿐이므로, 개수·형태를 positive 로 못박는다.
#   - 발: 정확히 두 발, 발가락 5개, 추가·복제·갈라짐 없음 (앉은 자세에서 종아리
#     ->발이 하나 더 생기는 경로를 정면으로 막는다)
#   - 종아리: 곧고 자연스러운 형태, 무릎-발목 정렬, 휘거나 꺾이지 않음
#   - 손: HAND_INTEGRITY_POSITIVE 를 그대로 잇는다 (정의는 손 이름을 가진 상수 쪽)
# 샷 인지: 얼굴·상반신(CU/ECU)은 다리·발이 화면에 없어 넣으면 없는 발을 그린다
# (ANATOMY_COUNT_UPPER 와 같은 이유). 그래서 _limb_visible 일 때만 붙인다.
LEG_FOOT_INTEGRITY_POSITIVE = (
    "limb integrity: exactly two legs and exactly two feet in total, "
    "one foot at the end of each leg, each foot complete with five toes; "
    "no third foot, no extra foot, no duplicated or cloned leg, no foot "
    "splitting from the calf, no limb growing from the shin; "
    "each calf and shin is straight and naturally shaped with the knee and "
    "ankle in line, not bent or kinked, natural calf muscle outline, "
    "legs the correct length and not warped; "
    + HAND_INTEGRITY_POSITIVE
)


# 얼굴·상반신 샷(극접 ECU / 근접 CU)용 개수 가드. 왜(Why) 다리를 빼나
# (2026-10-11 실측): CU/ECU 는 다리·발이 화면에 없다. 그런데 전신 가드를
# 그대로 넣으면 "두 다리·발가락 5개·다리 균형"을 요구해 모델이 **화면에
# 없는 사지를 만들어 넣는다** — 사용자가 본 "발이 하나 더 생긴다"의 직접
# 경로다. 손·손가락·팔은 CU 에서도 보이므로 남기고, 다리·발 문구만 뺀다.
# 2026-10-22 (R192): 손가락 분리 단서를 이 경로에도 붙인다. 종전에는 이 가드에
# 손 모양 서술이 "complete unambiguous shapes" 하나뿐이라, 손이 화면에 크게
# 나오는 샷인데도 분리 단서가 없었다. 전신 가드와 **같은 상수**를 쓴다.
# 한계(정직): 전신 경로(짝지음 3시드)만 실측했다. 이 경로의 효과는 별도 실측이
# 없다 — 손이 더 크게 잡혀 뭉갬 위험이 낮다고 보지만 그것은 추정이다.
ANATOMY_COUNT_POSITIVE_UPPER = (
    "correct digit count, clearly readable hands: exactly five fingers on "
    "each hand (one thumb plus four fingers), two arms ending in two hands, "
    "every arm fully formed and whole, hands drawn as complete "
    "unambiguous shapes, " + FINGER_SEPARATION_POSITIVE
)

ANATOMY_COUNT_NEGATIVE_UPPER = (
    "fused fingers, webbed fingers, mitten hands, fingers split down the "
    "middle, double thumbs, extra fingers, missing fingers, fingers merging "
    "into the palm, arms fused to the torso, three arms, extra arms, "
    "duplicate arms, asymmetric arms, one arm"
)


# 화면비 인지형 다리 복제 에스컬레이션 (2026-10-16 실측, 2026-10-21 확장).
# 왜(Why): 13개 가로 화면비 스윕(시드 42 고정)에서 종아리->발 다리가 하나 더
# 생기는 버그가 16:9(1.78)·19:6(3.17) 에서 재현됐다. 2026-10-21 사용자 실측으로
# 세로 프레임(848x1232 = 0.688)에서도 같은 버그가 확인됐다. denoise=1.0 이라
# 참조가 픽셀로 기여를 못 해 텍스트로만 전달되는데, 긴 축의 빈 공간을 모델이
# 사지 복제로 채우는 잔여(denoise=1.0 한계)다. 위험 비율일 때 기존
# ANATOMY_COUNT_NEGATIVE 위에 더 강한 "정확히 두 다리" 문구를 한 번 더 얹는다
# (기존 negative 는 유지 — 짝이므로). positive 짝은 LEG_FOOT_INTEGRITY_POSITIVE.
ASPECT_LEG_DUPLICATION_NEGATIVE = (
    "exactly two legs total: one leg on the left and one leg on the right, "
    "each complete from hip to ankle with both feet present, separate and "
    "fully formed; absolutely no third leg, no extra leg, no duplicate leg, "
    "no mirrored or cloned leg, no second pair of legs, no leg splitting "
    "into two"
)

# 위험 비율 판정. 2026-10-16 가로 스윕에서 16:9(1.7778)·19:6(3.1667) 이
# 다리 복제를 냈다. 2026-10-21 사용자 실측: 세로 프레임(848x1232 = 0.688)에서도
# 종아리->발 다리가 하나 더 생기고 종아리가 휘었다. 원인은 같은 잔여다 —
# denoise=1.0 이라 참조가 픽셀로 기여하지 못하고, 긴 축의 빈 공간을 사지
# 복제로 채운다. 그래서 **가로로 긴 비율과 세로로 긴 비율을 모두** 위험으로 본다
# (정사각 근처는 제외 — 빈 공간이 적다).
_RISKY_ASPECT_RATIOS = (16.0 / 9.0, 19.0 / 6.0)   # 가로로 긴 (2026-10-16)
# 세로로 긴 비율의 하한/상한 (2026-10-21). 9:16 ≈ 0.5625, 3:4 = 0.75.
# 이보다 좁으면(더 세로로 길면) 위험으로 본다.
_PORTRAIT_RISKY_MAX = 0.80
_ASPECT_RATIO_TOL = 0.05


def _is_risky_aspect_ratio(aspect_ratio) -> bool:
    """출력 가로세로비가 실측으로 다리 복제 버그가 난 비율이면 True.

    latent(또는 픽셀) 가로/세로를 받아 비교한다. 가로로 긴 비율(16:9·19:6)은
    2026-10-16 스윕 실측이고, 세로로 긴 비율(0.80 이하)은 2026-10-21 사용자
    실측(848x1232=0.688 에서 종아리에서 발이 하나 더 생김)이다. 둘 다
    denoise=1.0 에서 긴 축 빈 공간을 사지 복제로 채우는 같은 잔여다.
    """
    try:
        r = float(aspect_ratio)
    except (TypeError, ValueError):
        return False
    if r <= 0:
        return False
    if any(abs(r - ref) <= _ASPECT_RATIO_TOL for ref in _RISKY_ASPECT_RATIOS):
        return True
    return r <= _PORTRAIT_RISKY_MAX


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
                    and has_any_label((cam or {}).get("shot", ""), SCALE_SHOTS))
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

# 얼굴 정체성 negative (2026-10-20 실측). 왜(Why) 포즈 지시가 있을 때만
# 켜나: 참조의 자세를 그대로 쓰는 실행(토픽에 포즈 없음)은 모델이 참조를
# 거의 복사하므로 얼굴이 유지된다(실측 상관 0.953). 반대로 토픽이 자세를
# 바꾸면 모델이 인물을 **새로 그려** 다른 사람이 된다(같은 조건에서 상관
# 0.064). 이때 얼굴 변형을 negative 로 눌러 주면 눈·헤어·얼굴형이 참조로
# 돌아온다(실측: 눈 가로/세로 2.829 -> 2.531, 원본 2.389, 상관 0.064 ->
# 0.826). 항상 켜면 기존 결과가 전부 바뀌므로 **포즈 지시가 있을 때만** 켠다.
FACE_IDENTITY_NEGATIVE = (
    "different person, changed facial features, different eye shape, "
    "different eyelids, different nose, different lips, face swap, "
    "older face, younger face"
)

# 강한 포즈 상태 어휘만 쓴다. cam_subject 의 _KO_POSE_STATE 는 "손·팔·각도·
# 위치" 처럼 흔한 단어까지 포함해 거의 모든 토픽에서 발동한다 — 그걸 쓰면
# "항상 켜는" 것과 같아져 기존 결과를 흔든다.
_POSE_STATE_STRONG = (
    "앉", "서있", "서 있", "서서", "누워", "누운", "눕는", "쪼그", "엎드",
    "일어서", "무릎 꿇", "기어", "뛰", "걷", "점프",
    "sitting", "seated", "sit ", "standing", "stand ", "kneel", "lying",
    "lie ", "crouch", "squat", "jump", "walk", "run ",
)


def _topic_requests_pose(topic) -> bool:
    """토픽이 몸의 자세를 바꾸라고 지시하는가 (보수적 — 강한 어휘만)."""
    try:
        t = (topic or "").lower()
        if not t:
            return False
        return any(w in t for w in _POSE_STATE_STRONG)
    except Exception:
        return False


def _assemble_negative(cam, topic, image_count, image_labels, flags,
                       noir_phrase, extras=(), physics_neg="",
                       pose_ref=False, prevent_duplicates=False,
                       aspect_ratio=None) -> str:
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
    if has_any_label(cam.get("grade"), ("느와르 (noir)",)):
        neg.append(noir_phrase)
    if _is_human_subject(topic or ""):
        neg.append(ANATOMY_DETAIL_NEGATIVE)
    # positive(ANATOMY_COUNT_POSITIVE) 는 붙는데 negative 짝이 없으면
    # "5개여야 한다" 는 지시가 방향 없는 한쪽_only 가 된다(2026-09-28 발견).
    if flags.get("anatomy_count"):
        # 얼굴·상반신 샷(anatomy_count_upper)이면 다리·발 문구를 뺀 짝을 쓴다.
        # positive 가 upper 변형이면 negative 도 upper 여야 짝이 맞는다
        # (2026-10-11).
        if flags.get("anatomy_count_upper"):
            neg.append(ANATOMY_COUNT_NEGATIVE_UPPER)
        else:
            neg.append(ANATOMY_COUNT_NEGATIVE)
    # 화면비 인지형 다리 복제 에스컬레이션 (2026-10-16 실측). 풀바디(full)이고
    # 위험 비율(16:9·19:6)일 때만 기존 ANATOMY_COUNT_NEGATIVE 위에 더 강한
    # "정확히 두 다리" 문구를 한 번 더 얹는다. upper(CU/ECU) 는 다리·발이 화면에
    # 없어 의도적으로 제외.
    if (flags.get("anatomy_count") and not flags.get("anatomy_count_upper")
            and _is_risky_aspect_ratio(aspect_ratio)):
        neg.append(ASPECT_LEG_DUPLICATION_NEGATIVE)
    if flags.get("character_sheet"):
        neg.append(CHARACTER_SHEET_NEGATIVE)
        # 시트 뷰가 별개 인물로 세어지는 것까지 막는다 (신원 일관성이 목적이므로).
        # **다인물 시트는 제외** — 토픽 어휘 또는 LLM 판정(sheet_kind). 픽셀만으로는
        # 같은 사람 반복과 다른 캐릭터 나열을 가를 수 없다(실측 sim 0.415 대 0.216).
        if not (_is_multi_person_sheet(topic)
                or flags.get("sheet_kind") == "multi"):
            neg.append(CHARACTER_SHEET_PEOPLE_NEGATIVE)
    _, _eth_neg = _ethnicity_guard(topic or "", image_count, image_labels)
    if _eth_neg:
        neg.append(_eth_neg)
    if _is_animal_subject(topic or ""):
        neg.append(ANIMAL_ANATOMY_NEGATIVE)
    # 포즈 negative: 빈 문자열을 넣지 않는다 (빈 조각이 ", " 꼬리를 남긴다)
    # topic 포즈 + **힌트 포즈**(LLM 이 선언한 슬롯, 2026-10-19). positive 가드와
    # 같은 슬롯을 가리켜야 한다 — positive 만 힌트를 보고 negative 가 topic 만
    # 보면 "얼굴은 버려라"는 부호가 한쪽에만 붙는다.
    _pose_neg = _pose_reference_negative(
        (_pose_role_slots(topic or "") | set(_hint_pose_slots()))
        & set(image_labels or [])) if pose_ref else ""
    if _pose_neg:
        neg.append(_pose_neg)
    if physics_neg:
        neg.append(physics_neg)
    if flags.get("detail_def"):
        # CU/ECU 면 다리·발 문구를 뺀 짝을 쓴다 (anatomy_count_upper 와 동일).
        if flags.get("detail_def_upper"):
            neg.append(DETAIL_DEFINITION_NEGATIVE_UPPER)
        else:
            neg.append(DETAIL_DEFINITION_NEGATIVE)
    if flags.get("furniture"):
        neg.append(FURNITURE_DNA_NEGATIVE)
        neg.append(OBJECT_DRIFT_NEGATIVE)
        neg.append(OBJECT_INSTANCE_NEGATIVE)
    # 좌석 접촉점 (2026-10-24, R226) — positive(SEAT_OCCUPANCY_POSITIVE)의 짝이다.
    # cfg=1.0 워크플로에서는 negative 가 무효지만, 다른 cfg 워크플로에서 lever 가
    # 되도록 저장소 관례대로 짝을 만든다.
    if flags.get("seat"):
        neg.append(SEAT_OCCUPANCY_NEGATIVE)
    if flags.get("furniture_bg"):
        # 배경 참조의 사물 충실 가드와 짝 (2026-10-22). 존재를 요구하는
        # OBJECT_INSTANCE_NEGATIVE 는 넣지 않는다 — 우리가 요구하지 않은
        # "단일 인스턴스" 의 짝이라 맞지 않는다.
        neg.append(OBJECT_DRIFT_NEGATIVE)
        # 지지 구조 조항의 짝 (2026-10-30) — 받쳐지지 않은 상판·끊긴 다리.
        neg.append(FURNITURE_BACKGROUND_NEGATIVE)
    if flags.get("remove_item"):
        # 빈 문자열을 세면 join 이 ", " 꼬리를 남긴다(2026-10-07 라운드 2 —
        # _remove_item_guard 는 비인물 topic 에 "" 를 돌려준다).
        _rm = _remove_item_guard(topic)
        if _rm:
            neg.append(_rm)
    if flags.get("footwear_bare"):
        # 맨발 주제면 신발 negative 가 아니라 **신발 등장**을 막는 짝을 쓴다
        # (2026-10-25 F3). 종전 FOOTWEAR_NEGATIVE 는 "bare feet, barefoot" 를
        # 금지하므로 맨발 요구와 정면 충돌한다.
        neg.append(FOOTWEAR_BARE_NEGATIVE)
    elif flags.get("footwear"):
        neg.append(FOOTWEAR_NEGATIVE_UPPER if flags.get("footwear_upper") else FOOTWEAR_NEGATIVE)
    if flags.get("body_object_boundary"):
        neg.append(BODY_OBJECT_BOUNDARY_NEGATIVE_UPPER if flags.get("body_object_boundary_upper") else BODY_OBJECT_BOUNDARY_NEGATIVE)
    # 의복 경계 (2026-10-16) — positive 와 짝이다.
    if flags.get("garment_boundary"):
        neg.append(GARMENT_BOUNDARY_NEGATIVE_UPPER if flags.get("garment_boundary_upper") else GARMENT_BOUNDARY_NEGATIVE)
    # 손 배치 (2026-10-24) — positive(HAND_PLACEMENT_POSITIVE)와 짝이다.
    # cfg=1.0 이면 전달되지 않지만 cfg>1 워크플로와 식별기 경로를 위해 둔다.
    if flags.get("hand_placement"):
        neg.append(HAND_PLACEMENT_NEGATIVE)
    if _needs_scale_guard(topic or "", cam):
        neg.append(SCALE_COHERENCE_NEGATIVE)
    # 얼굴 정체성 negative (2026-10-20). 포즈 지시가 있으면 모델이 인물을
    # 새로 그려 얼굴이 바뀐다 — 그때만 켠다(위 상수 주석의 실측 참조).
    # 사람이 없는 장면(사물·배경)에는 의미가 없으므로 인물 게이트를 건다.
    if (image_count > 0 and _is_human_subject(topic or "")
            and _topic_requests_pose(topic)):
        neg.append(FACE_IDENTITY_NEGATIVE)
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
                          furniture_bg: bool = False,
                          remove_item: bool = False,
                          anatomy_count: bool = False,
                          character_sheet: bool = False,
                          sheet_kind: str = "",
                          anatomy_count_upper: bool = False,
                          detail_def_upper: bool = False,
                          footwear: bool = False,
                          footwear_upper: bool = False,
                          footwear_bare: bool = False,
                          body_object_boundary: bool = False,
                          body_object_boundary_upper: bool = False,
                          garment_boundary: bool = False,
                          garment_boundary_upper: bool = False,
                          hand_placement: bool = False,
                          seat: bool = False,
                          aspect_ratio: float = None) -> str:
    """카메라/영상 실패 모드 + 인물 해부 디테일 방어 (신원·신체 비율 가드 제외)."""
    return _assemble_negative(
        cam, topic, image_count, image_labels,
        {"anatomy_count": anatomy_count, "character_sheet": character_sheet,
         "sheet_kind": sheet_kind,
         "detail_def": detail_def, "furniture": furniture,
         "furniture_bg": furniture_bg,
         "remove_item": remove_item,
         "anatomy_count_upper": anatomy_count_upper,
         "detail_def_upper": detail_def_upper,
         "footwear": footwear, "footwear_upper": footwear_upper,
         "footwear_bare": footwear_bare,
         "body_object_boundary": body_object_boundary,
         "body_object_boundary_upper": body_object_boundary_upper,
         "garment_boundary": garment_boundary,
         "garment_boundary_upper": garment_boundary_upper,
         "hand_placement": hand_placement, "seat": seat},
        "unwanted color cast", physics_neg=physics_neg, pose_ref=pose_ref,
        prevent_duplicates=prevent_duplicates, aspect_ratio=aspect_ratio)


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
    # 왜(Why) 역할 목록에서 "outfit" 을 뺐나 (2026-10-13 실측): 이 목록은 보조
    # 참조가 **무엇을 제공할 수 있는지**를 나열한다. "outfit" 이 들어 있으면
    # 보조 참조가 **사물(의자·벤치)인 실행**에서도 "그 참조에서 옷을 가져올 수
    # 있다" 는 허가로 읽힌다 — 지시하지 않은 의상 변경의 유도가 된다.
    # 실측: image_2 = 벤치 인 실행에서 하의가 청바지 -> 스커트로 바뀌었다.
    # 의상 전용 경로는 그대로 남는다 — 바로 뒤 "Garments from a clothing
    # reference ..." 문장(테스트 R? 가 "separate clothing layer" 로 고정)과
    # outfit_guard / _is_outfit_transfer 가 명시 교체를 담당한다.
    # (같은 파일의 MIX_GUARD_POSITIVE_BARE 는 노출 요청용으로 의상 문장까지 뺀 변형이다.)
    "Reference mixing guard: the main person reference image is the only identity source "
    "(face, body shape, proportions); the other reference image(s) contribute "
    "only their requested role such as background, prop, product, "
    "style, lighting, composition, or mood. Garments from a clothing reference "
    "are a separate clothing layer placed over the main person's body, "
    "following the existing anatomy, preserving the main person's body shape, "
    "skin, face, and hair; pose follows the topic. No blending of two people into one, no mixed "
    "facial features between references."
)


MIX_GUARD_NEGATIVE = ("clothing fusion with skin, melted garment edges, "
                      "body parts merging into clothing, mixed facial features, "
                      "identity blending, duplicated person")


# 노출 요청용 믹스 가드 (2026-10-11 실측 결함). 왜(Why) 따로 두나:
# 위 MIX_GUARD_POSITIVE 의 "Garments from a clothing reference are a separate
# clothing layer **placed over the main person's body**" 는 **옷을 덧입히라는
# 지시**다. 사용자가 "의상을 모두 제거한 누드" 를 요청한 실행에서 이 문장이
# 같은 positive 에 함께 들어가면, nudity_anatomy_guard 의 "…clearly defined
# natural intimate detail" 과 **정면으로 충돌**한다(실측: 노출 요청 + 참조 2장
# → 두 문구가 동시에 positive 에 들어감). 모델은 그 충돌을 옷으로 해소하므로
# 요청이 뒤집히고 결과가 뭉개진다.
# 그래서 신원 고정·중복 방지 부분은 그대로 두고 **의상 문장만** 뺀 뒤, 의상은
# 주제문이 정한다는 한 줄로 바꾼다.
MIX_GUARD_POSITIVE_BARE = (
    "Reference mixing guard: the main person reference image is the only identity source "
    "(face, body shape, proportions); the other reference image(s) contribute "
    "only their requested role such as background, prop, product, style, lighting, "
    "composition, or mood. Clothing is determined solely by the topic — do not add "
    "garments the topic does not ask for; pose follows the topic. No blending of two "
    "people into one, no mixed facial features between references."
)


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
    "boundary against the background — each leg keeps its own clean "
    "silhouette without inventing additional limbs, arms separate from the "
    "torso, shoulders keep a defined line, fabric keeps its weave and seams, "
    "skin keeps natural texture and fine surface detail, hands keep distinct "
    "fingers, knees and elbows keep a visible joint line"
)


DETAIL_DEFINITION_NEGATIVE = (
    "melted body boundaries, legs blending into each other, extra leg, "
    "additional leg, third leg, duplicate leg, arm merging into "
    "torso, smeared fabric, waxy skin, featureless limbs, indistinct fingers, "
    "boots melting into the foot, foot blending into the floor, "
    "soft shapeless body parts, plastic doll skin, blanket-like skin folds"
)


# 얼굴·상반신 샷(극접 ECU / 근접 CU)용 경계 가드. 왜(Why) 따로 두나
# (2026-10-11 실측): detail_def 는 denoise=1.0 뭉개짐 방어라 CU 에서도
# 필요하지만, 전신 문구("legs blending", "extra leg", "foot blending")가
# 다리·발을 화면에 없는 샷에 끌어들인다. 경계·질감 방어만 남기고
# 다리·발 문구를 뺀다. anatomy_count_upper 와 같은 짝 맞춤이다.
DETAIL_DEFINITION_POSITIVE_UPPER = (
    "anatomical edge definition: every body part keeps a clear readable "
    "boundary against the background — arms separate from the "
    "torso, shoulders keep a defined line, fabric keeps its weave and seams, "
    "skin keeps natural texture and fine surface detail, hands keep distinct "
    "fingers, visible joints keep a clean line"
)

DETAIL_DEFINITION_NEGATIVE_UPPER = (
    "melted body boundaries, arm merging into "
    "torso, smeared fabric, waxy skin, featureless limbs, indistinct fingers, "
    "soft shapeless body parts, plastic doll skin, blanket-like skin folds"
)


# 인물 신체 발란스 가드. (Why: 전신·신체 중심 장면에서 팔/다리 길이 불균형,
# 머리-몸 비율 붕괴, 부위별 스케일 불일치가 자주 발생. 사지가 보이는 샷에만
# 첨부한다 — CU/ECU 처럼 얼굴만 보이는 샷에 "arms and legs" 를 요구하면
# 화면에 없는 다리를 만들어낸다(2026-10-11 실측). 샷 게이트는
# resolve_guard_plan 의 body_balance 판정이 든다.)
BODY_BALANCE_POSITIVE = (
    "body balance: natural human proportions, head-to-body ratio consistent "
    "with a real person, full-length arms and legs with natural thigh and "
    "calf proportions, natural shoulder-hip line, relaxed upright posture, "
    "all body parts at one consistent scale"
)


BODY_BALANCE_NEGATIVE = ("disproportionate limbs, elongated arms, shortened legs, "
                         "oversized head, twisted torso, body parts of different scale")


# 신발 유지 가드. 왜(Why): 참조에 신발이 있어도 생성에서 맨발이 됐다.
# PARTIAL_OBJECT_NEGATIVE 는 벗긴 뒤 반쪽 찌꺼기만 막고, 신발 존재 자체를
# positive 로 지키는 문구가 없었다. 인물 + 참조 실행에만 붙는다.
#
# 2026-10-24 (R225) — 지목 대상 분리. 문구 내용은 그대로 두고 **어느 참조를
# 가리키는가**만 뗄 수 있게 꼬리를 상수로 뽑았다. 왜(Why) 필요한가: 사용자가
# `3번: 하이 힐` 로 신발 참조를 선언해도 이 문구가 "the main person reference
# image"(1번)를 가리켜, 참조 3번의 힐이 쓰이지 않고 1번의 흰 슬립온이 샜다
# (실측: 최종 프롬프트 8418자에 `… from the main person reference image …`).
# 2026-10-24 (R227) — 꼬리 내용 자체를 중립화. 왜(Why) R225 로 부족했나:
# 지목이 3번으로 맞아도 문구가 **참조에 없는 구조를 단정**하고 있었다.
#  · `same strap style and arrangement` — 펌프스에는 스트랩이 없다. "같은
#    스트랩"을 요구하면 모델이 스트랩을 만들어낸다.
#  · `in open-toe shoes all five toes are bare … toes sit clear of the straps`
#    — 무조건 오픈토를 전제하고, 스트랩이 있다는 가정이 또 들어 있다.
# 실측(2026-10-24 04:57 생성물, 참조 3번 = 검은 뾰족코 클로즈드토 스틸레토):
# 결과는 **검은 오픈토 보우 스트랩 샌들**이었다 — 색만 따라왔고 구조는 문구가
# 이겼다. 같은 실행에서 1번 참조의 흰 슬립온이 나오지 않은 것이 그 증거다
# (문구 > 이미지). 그래서 앞코 구조를 **조건문**으로 바꾸고(닫힘이면 가려진
# 게 맞다고 명시해 해부 가드의 "five toes" 와의 충돌을 푼다), 없는 장식 추가
# 금지와 다른 참조에서의 신발 유입 금지를 더한다. 열린 앞코의 발가락 융합
# 방지(R165 계약)는 조건문 안에 그대로 남는다.
_FOOTWEAR_LOCK_TAIL = (
    "same colour, same silhouette, same toe shape and upper design as the "
    "reference, same heel height, same material, "
    "same shoes on both feet, laces and soles intact, do not change the shoe colour, "
    "do not swap to a different shoe style, do not make the person barefoot, "
    "take no footwear from any other reference image, "
    "keep the reference toe construction exactly: if the reference shoes have a "
    "closed toe the toe is fully covered with no bare toes showing (a closed toe "
    "hides the toes and that is correct), if they have an open toe all five toes "
    "are bare, individually outlined and clear of the shoe edge, never fused with "
    "the shoe upper or wrapped in fabric, "
    "do not add any strap, buckle, bow or lace that the reference shoes do not have")

FOOTWEAR_POSITIVE = ("footwear identity lock: preserve the exact shoes from the main person reference image — "
                     + _FOOTWEAR_LOCK_TAIL)

# 선언된 신발 참조 슬롯을 지목하는 변형 (2026-10-24, R225). `_footwear_guard` 가
# `slots` 를 받았을 때만 `{slot}` 을 채워 쓴다. 꼬리는 위 상수와 **같은 출처**라
# 두 변형이 갈릴 수 없다 — 문구를 늘릴 때 한쪽만 고치는 사고를 막는다.
FOOTWEAR_POSITIVE_SLOT = ("footwear identity lock: preserve the exact shoes from reference image {slot} — "
                           + _FOOTWEAR_LOCK_TAIL)


# 신발 교체 가드. 왜(Why) 별도 상수인가 (2026-10-15 실측): FOOTWEAR_POSITIVE 는
# "keep that footwear(reference)" — 참조 신발 유지를 말한다. 사용자가 신발을
# 바꾸라고 쓴 문장(예: "앞이 막혀 있는 흰색 단화")과 같은 positive 에서
# 정면 충돌하면 모델은 참조 쪽을 택한다 (의상 교체 실측 2026-10-02 와 같은
# 경로 — 갈아입히다 지시와 "same outfit" 이 공존하면 참조를 택했다).
# resolve_guard_plan 이 교체 의도(_topic_changes_shoes)를 감지하면 이
# 변형으로 갈아탄다. negative 는 FOOTWEAR_NEGATIVE 그대로 쓴다 — 방어 대상
# (맨발·신발 소실)이 같고 "참조 신발 유지" 라는 지시가 없을 뿐이다.
# 2026-10-24 (R227): 유지 변형과 **같은 조건문**으로 바꿨다. 기준이 참조가
# 아니라 프롬프트 서술이라 "the prompt describes" 를 쓴다. 왜(Why) 무조건
# 오픈토를 뺐나: 이 경로에서도 "앞이 막힌 단화" 를 서술하면 같은 충돌이 났다.
FOOTWEAR_CHANGE_POSITIVE = ("footwear change guard: the footwear described in the prompt takes "
                            "priority — wear exactly the described shoes on both feet, do not copy "
                            "the reference image footwear, do not keep the reference shoes, "
                            "keep the toe construction the prompt describes exactly: if the "
                            "described shoes are closed-toe the toe is fully covered with no bare "
                            "toes showing (a closed toe hides the toes and that is correct), if "
                            "they are open-toe all five toes are bare, individually outlined and "
                            "clear of the shoe edge, never fused with the shoe upper or wrapped "
                            "in fabric, do not add any strap, buckle, bow or lace that the "
                            "described shoes do not have")


# 신발 negative 짝. 2026-10-24 (R227) — 유지 변형이 앞코 조건문이 되면서
# 뒤집힘(닫힌 신발의 샌들화)과 없는 장식 추가를 명시적으로 막는다.
# 왜(Why) cfg=1.0 인데도 고치나: 이 저장소는 positive/negative 를 손으로
# 동기화한다 — cfg 를 올린 실행에서 짝이 어긋나면 방어가 조용히 사라진다.
FOOTWEAR_NEGATIVE = ("bare feet, barefoot, missing shoes, missing footwear, lost shoes, "
                     "invisible footwear, deformed footwear, melted shoes, feet without shoes, "
                     "shoes disappearing, one shoe missing, half a shoe, "
                     "shoes in a different colour, changed shoe colour, different shoe style, "
                     "different heel, different straps, footwear swap, wrong shoe colour, "
                     "sandals where the reference shows closed shoes, closed shoes turned into "
                     "sandals, open-toe conversion of a closed shoe, added straps, "
                     "extra straps, added bows, bows not present in the reference, "
                     "bare toes in closed-toe shoes, toes visible through a closed shoe, "
                     "toe covered by fabric, single toe wrapped in cloth, toe sock, "
                     "rubber sleeve over one toe, fabric strap fused with a toe, "
                     "toe merged into the shoe upper, big toe hidden by the shoe, "
                     "extra fabric over the toes")


# 얼굴·상반신 샷(극접 ECU / 근접 CU)용 신발 가드. 왜(Why) 다리 문구를 빼나:
# CU/ECU 는 발이 화면에 없는데 "both feet" 를 요구하면 모델이 없는 발을
# 만들어낸다. 맨발 방지만 남긴다 (anatomy_count_upper 와 같은 짝 맞춤).
FOOTWEAR_POSITIVE_UPPER = ("footwear presence guard: do not make the person barefoot, keep natural feet")


FOOTWEAR_NEGATIVE_UPPER = FOOTWEAR_NEGATIVE


# 맨발 가드 (2026-10-25 감사 F3). 왜(Why) 새로 두나: 사용자가 "A barefoot woman
# standing on the beach" 처럼 **맨발을 요구**하면, 종전에는 참조 유지 가드가
# 그대로 나가 "keep the exact shoes" 와 짝 negative 의 "bare feet, barefoot" 이
# **같은 실행에서 사용자 문장과 정면 충돌**했다(실측: positive 에 신발 유지 문구
# 와 함께 맨발 요구가, negative 에 bare feet 금지가 동시에 들어갔다). 맨발 주제
# 에서는 신발 잠금을 끄고 이 가드로 갈아탄다 — 참조에 신발이 있어도 벗긴다.
# 뒤쪽 "five separate toes" 는 해부 가드(ANATOMY_COUNT)의 발가락 문구와 **같은
# 방향**이라 서로 밀어내지 않는다.
FOOTWEAR_BARE_POSITIVE = (
    "bare feet guard: the person is barefoot as described — both feet are bare "
    "with no shoes and no socks, bare skin on the feet, five separate toes on "
    "each foot with individual outlines, natural heel and sole, do not keep, "
    "copy or restore any footwear from a reference image")


# 맨발 negative 짝. FOOTWEAR_NEGATIVE 와 달리 "bare feet, barefoot" 를 금지하지
# **않는다** — 그것이 바로 요구된 상태다. 대신 신발·양말이 나타나는 쪽을 막는다.
# cfg=1.0 워크플로에서는 전달되지 않지만, 저장소 관례대로 positive 와 짝을
# 맞춰 둔다 — cfg 를 올린 실행에서도 방어가 어긋나지 않는다.
FOOTWEAR_BARE_NEGATIVE = (
    "shoes appearing on bare feet, unexpected footwear, shoes added to bare "
    "feet, socks appearing, slippers on bare feet, bare toes covered by a shoe, "
    "footwear restored from a reference image, bare feet becoming shod")


# 신체-사물 접촉 경계 가드. 왜(Why): FURNITURE_DNA 는 사물 쪽 형태만 지키고
# 신체 쪽 경계는 안 지켜서, 앉으면 몸이 침대·의자에 꺼져 박히며 눌린 모습이
# 됐다. 접촉면에서 몸과 사물이 분리되도록 신체 쪽에서 잡는다.
BODY_OBJECT_BOUNDARY_POSITIVE = ("body-object boundary: where the body meets an object (sitting on a chair, "
                                 "lying on a bed, leaning against a surface), keep a clear boundary between "
                                 "the body and the object — body does not sink into or merge with the object, "
                                 "clothing and body keep separate from the object surface, weight is supported "
                                 "on top of the object with visible contact pressure, no blending of body into "
                                 "fabric")


BODY_OBJECT_BOUNDARY_NEGATIVE = ("body sinking into furniture, body merging into the surface, body blending "
                                 "into fabric, body absorbed into the object, flat contact with no pressure, "
                                 "limbs disappearing into furniture, body parts fusing with the surface")


# 얼굴·상반신 샷용 접촉 경계 가드. 하반신 접촉 문구를 빼고 상반신 접촉만 남긴다.
BODY_OBJECT_BOUNDARY_POSITIVE_UPPER = ("body-object boundary: where the upper body meets an object (sitting on a chair, "
                                        "leaning against a surface), keep a clear boundary between the body and the "
                                        "object — body does not sink into or merge with the object, clothing and "
                                        "body keep separate from the object surface, weight is supported on top of "
                                        "the object with visible contact pressure, no blending of body into fabric")


BODY_OBJECT_BOUNDARY_NEGATIVE_UPPER = ("upper body sinking into furniture, body merging into the surface, body blending "
                                        "into fabric, flat contact with no pressure, body parts fusing with the surface")


# 의복 경계 가드 (2026-10-16 실측, 파란 동그라미): 생성물에서 손이 치마 자락에
# 삼켜져 보이지 않았다(파란 동그라미 내부 x 468-623, y 1047-1169). 키퍼는
# 감지했으나 고치지 못했다 — 손 물리 66.7/100(끝점 뭉침 sep=0.012), 미세 당김은
# 정체 중단으로 포기, 포즈 게이트가 사지 복원을 얼굴로 제한(hand_right 53% 손실
# 미복원). 그리고 **카메라에는 이 경우를 덮는 가드가 없었다** — 위
# BODY_OBJECT_BOUNDARY 는 전부 furniture 문구이고 PARTIAL_OBJECT_NEGATIVE 는
# 제거된 사물용이다. 사지가 **의복**에 잠기는 경우를 따로 못박는다.
# 왜(Why) 방향("옷 앞에 있어라")을 쓰지 않는가: 손을 옷 뒤에 두는 자세(주머니 등)
# 가 정당하게 존재한다. 지켜야 할 것은 **손이 읽히고 분리돼 있는 것**이다.
GARMENT_BOUNDARY_POSITIVE = (
    "garment boundary: every hand and finger stays readable and separate — "
    "each hand keeps its own silhouette and is never merged with, swallowed by "
    "or lost inside the fabric of the clothing. Wrists, forearms and legs stay "
    "distinct from the garment they rest against, and the garment keeps its own "
    "unbroken outline."
)

GARMENT_BOUNDARY_NEGATIVE = (
    "hand merged with clothing, hand swallowed by the dress, fingers fused into "
    "the fabric, hand sinking into the skirt, wrist buried in the cloth, arm "
    "disappearing inside the garment, hand and fabric becoming one shape, hand "
    "not visible, garment outline broken by a limb"
)

GARMENT_BOUNDARY_POSITIVE_UPPER = (
    "garment boundary: every hand and finger stays readable and separate — "
    "each hand keeps its own silhouette and is never merged with, swallowed by "
    "or lost inside the fabric of the clothing. Wrists and forearms stay "
    "distinct from the garment they rest against, and the garment keeps its own "
    "unbroken outline."
)

GARMENT_BOUNDARY_NEGATIVE_UPPER = (
    "hand merged with clothing, hand swallowed by the dress, fingers fused into "
    "the fabric, wrist buried in the cloth, arm disappearing inside the "
    "garment, hand and fabric becoming one shape, hand not visible"
)


def _footwear_guard(shot, slots=None):
    """샷별 신발 가드 (positive, negative). CU/ECU 면 upper 변형.

    다중 선택(콤마)이면 하나라도 CU/ECU 일 때 upper 를 쓴다 (2026-10-21 감사,
    R181) — 통째로 비교하면 전신 변형이 나와 화면에 없는 발 문구가 붙었다.

    `slots` 는 토픽이 **신발 참조로 선언한 슬롯**(`_footwear_slots`)이다.
    주면 문구가 그 슬롯을 지목하고, 안 주면 종전 문구 그대로다(2026-10-24,
    R225) — 선언 없는 실행의 프롬프트는 **바이트 동일**해야 한다.
    여럿이면 작은 번호 하나만 쓴다(먼저 선언된 것).
    """
    try:
        if has_any_label(shot, FACE_CRITICAL_SHOTS):
            return FOOTWEAR_POSITIVE_UPPER, FOOTWEAR_NEGATIVE_UPPER
        try:
            _s = sorted(int(x) for x in (slots or ()))
        except (TypeError, ValueError):
            # 방어용이다 — `_footwear_slots` 는 1~10 정수만 돌려준다. 값이
            # 이상하면 슬롯을 모르므로 종전 문구로 물러선다.
            _s = []
        if _s:
            return FOOTWEAR_POSITIVE_SLOT.format(slot=_s[0]), FOOTWEAR_NEGATIVE
        return FOOTWEAR_POSITIVE, FOOTWEAR_NEGATIVE
    except Exception:
        return FOOTWEAR_POSITIVE, FOOTWEAR_NEGATIVE


# 정면 응시 가드 (2026-10-15 실측): 주제에 "정면을 바라보며" 가 있어도
# 생성 결과는 시선을 옆으로 돌렸다. 원문·영문 어느쪽이든 정면 markers 가
# 있는 **사람** 주제에만 (positive 보강문, negative 회피어) 짝을 준다.
# positive 를 "directly into the camera" 로 굳히는 이유: "looking straight
# ahead" 하나로는 모델이 옆을 보는 쪽을 골랐다(실측). dedupe 마커도 우리
# 문구의 "directly into the camera" 다 — 사용자 문장의 "straight ahead" 는
# 지시가 먹지 않은 경우라 막으면 절대 안 된다.
_GAZE_POSITIVE = ("gaze forward: eyes looking straight ahead directly into "
                  "the camera, head facing the camera, both eyes aimed at "
                  "the viewer")
_GAZE_NEGATIVE = ("averted gaze, looking away, eyes off camera, side glance, "
                  "looking sideways, profile view, head turned away, gaze "
                  "directed elsewhere")
# 정면 markers (한글). "바라보며" 같은 광범위 표지는 빈다 — "의자를
# 바라보며" 까지 사람 시선 지시로 오인한다.
_GAZE_FACING_KO = ("정면", "앞을 보", "앞을 향", "카메라를 보", "카메라를 향")


def gaze_forward_guard(text, en_text):
    """정면 응시 (positive 보강문, negative 회피어) — 조건 불충족이면 ("", "").

    text: 원문(한글 가능) — 마커 판정과 사람 판정에 쓴다.
    en_text: 최종 영문 프롬프트 — 영문 마커와 중복 제거에 쓴다.
    """
    try:
        src = (text or "").strip()
        if not src or not en_text or not isinstance(en_text, str):
            return "", ""
        if not _is_human_subject(src):
            return "", ""
        import re as _re
        low_en = en_text.lower()
        hit = (any(m in src for m in _GAZE_FACING_KO)
               or bool(_re.search(r"straight ahead|facing (?:forward|the camera)"
                                  r"|eyes (?:on|to|toward) the camera"
                                  r"|looking at (?:the )?camera", low_en)))
        if not hit:
            return "", ""
        pos = "" if "directly into the camera" in low_en else _GAZE_POSITIVE
        return pos, _GAZE_NEGATIVE
    except Exception:
        return "", ""


# 지면 고정 가드 (2026-10-15 실측, 파란 동그라미 + 바닥 픽셀). 참조 배경은
# 흙바닥 한옥 마당(RGB 98,89,50, 표준편차 54.8 — 거친 흙·돌·이끼)이었는데
# 결과물 바닥은 매끈한 콘크리트(RGB 191,172,150, 표준편차 8.6~21)로 나왔다.
# 모델이 "background" 를 피사체 뒤 배경(backdrop)으로만 읽어, 피사체가 딛은
# 전경 지면은 참조와 무관하게 따로 그린 결과다 — 프롬프트에 지면 고정이 없었다.
# 배경-참조가 지정된 실행에서만 발동한다: 지면을 참조와 같다고 못박지 않은
# 실행(새 배경 창작 등)에 개입하지 않는다. negative 는 실측된 실패(콘크리트/
# 실내 매끈 바닥) 위주로만 적는다 — 다른 소재는 추측이라 넣지 않는다.
GROUND_REF_POSITIVE = (
    "ground continuity guard: the ground under and around the subject is the "
    "exact ground of reference image {n}, same dirt, stones, moss and surface "
    "texture, one continuous ground plane running from the foreground under "
    "the subject's feet straight into the far background, foreground floor "
    "identical to the background floor"
)
GROUND_REF_NEGATIVE = (
    "concrete floor, cement floor, smooth polished indoor floor, flat "
    "man-made flooring, foreground floor different from the background floor, "
    "ground not matching the reference ground"
)


def ground_reference_guard(text, background_slots=None):
    """배경-참조 지정이 있으면 (positive, negative), 아니면 ("", "").

    text: 판정 소스(한글 가능).
    background_slots: 배경 충실 가드가 판정한 슬롯 집합(선택). 주어지면 그
    최솟값을 쓰고, 비어 있으면 종전대로 cam_translate 의 background_ref_slot
    로 문장형 배경 지정("배경은 이미지4번의 배경으로")을 본다 — 번역 보정
    (fix_background_clause)과 같은 감지 한 줄을 쓴다.

    왜(Why) background_slots 를 받나 (2026-10-28 사용자 실측): 배경 슬롯을
    알아보는 판정이 두 벌이었다. 배경 충실 가드는 `_background_dna_slots`
    (= `_background_role_slots`) 로 **슬롯 목록형**("4번: 배경")을 알아보는데,
    이 지면 가드만 문장형 감지기로 발동해 목록형을 놓쳤다. 그래서 같은 실행
    에서 "배경 참조 사물 충실 가드 활성(4번)" 은 켜지고 "배경 지면 고정 가드
    활성" 은 **없었다** — 발밑 지면을 참조에 묶는 문구가 통째로 빠져 앞쪽
    바닥만 밝은 사각 타일로 바뀌었다. 호출부가 배경 충실 가드와 **같은 슬롯
    집합**을 넘기면 둘이 어긋날 수 없다.

    우선순위 — background_slots 가 비어 있지 않으면 그 최솟값, 아니면
    background_ref_slot(text). 한 인자로 부르는 기존 호출은 슬롯이 None 이라
    종전과 같다(R137 핀).
    """
    try:
        slots = []
        try:
            slots = sorted(int(x) for x in set(background_slots or []))
        except (TypeError, ValueError):
            slots = []
        slot = slots[0] if slots else background_ref_slot(text or "")
        if not slot:
            return "", ""
        return GROUND_REF_POSITIVE.format(n=slot), GROUND_REF_NEGATIVE
    except Exception:
        return "", ""


# 의류 색상 고정 가드 (2026-10-15 실측): "앞이 막혀 있는 흰색 단화" 지시에도
# 결과물의 신발은 크림/베이지색이 나왔다. positive 에는 "white" 가 살아
# 있었으므로 모델 준수 실패다 — 색상어가 의류 명사에 인접한 주제에서만
# 해당 색을 positive 로 굳히고, 흔히 갈리는 오색을 negative 에 넣는다.
# negative 는 실측된 실패(흰색->크림/베이지 계열) 위주로만 적는다 —
# 나머지 색의 오색 목록은 추측이라 넣지 않는다.
_ITEM_COLOR_POS = "pure {color} {item}, bright clean {color}, {color} kept true to the requested shade"
_ITEM_COLOR_NEG = {
    "white": ("cream shoes, beige shoes, ivory shoes, nude shoes, tan shoes, "
              "off-white shoes, cream-colored clothing, beige clothing"),
    "black": "brown shoes, dark gray shoes, off-black shoes, faded black",
    "gray": "white shoes, black shoes, beige shoes, brown shoes",
}


def color_adherence_guard(text, en_text):
    """주제가 지정한 의류 색상 고정 (positive 보강문, negative 오색) —
    미지정이면 ("", "").

    text: 원문(한글 가능) — _topic_item_color 가 인접성 판정에 쓴다.
    en_text: 최종 영문 프롬프트 — positive 중복 제거에 쓴다.
    """
    try:
        hit = _topic_item_color(text or "")
        if not hit:
            return "", ""
        color, item = hit
        low_en = (en_text or "").lower() if isinstance(en_text, str) else ""
        pos = ("" if f"pure {color}" in low_en
               else _ITEM_COLOR_POS.format(color=color, item=item))
        neg = _ITEM_COLOR_NEG.get(color, "")
        if not pos and not neg:
            return "", ""
        return pos, neg
    except Exception:
        return "", ""


def _body_object_boundary_guard(shot):
    """샷별 신체-사물 경계 가드 (positive, negative). CU/ECU 면 upper 변형."""
    try:
        if has_any_label(shot, FACE_CRITICAL_SHOTS):
            return BODY_OBJECT_BOUNDARY_POSITIVE_UPPER, BODY_OBJECT_BOUNDARY_NEGATIVE_UPPER
        return BODY_OBJECT_BOUNDARY_POSITIVE, BODY_OBJECT_BOUNDARY_NEGATIVE
    except Exception:
        return BODY_OBJECT_BOUNDARY_POSITIVE, BODY_OBJECT_BOUNDARY_NEGATIVE


def _garment_boundary_guard(shot):
    """샷별 의복 경계 가드 (positive, negative). CU/ECU 면 upper 변형."""
    try:
        if has_any_label(shot, FACE_CRITICAL_SHOTS):
            return GARMENT_BOUNDARY_POSITIVE_UPPER, GARMENT_BOUNDARY_NEGATIVE_UPPER
        return GARMENT_BOUNDARY_POSITIVE, GARMENT_BOUNDARY_NEGATIVE
    except Exception:
        return GARMENT_BOUNDARY_POSITIVE, GARMENT_BOUNDARY_NEGATIVE


# ── 참조 충실 모드용 압축 가드 (2026-10-25, E3) ────────────────────────────
# 왜(Why) 별도 상수인가: 참조 4장 워크플로에서 붉은 방(참조 4번)이 사라지는
# 원인은 프롬프트 **길이가 아니라 내용**이다. 해부·손·발을 지시하는 문장이
# 참조를 이긴다 — 같은 길이의 무해한 텍스트는 붉은 벽을 지키는데(33.74% 대
# 1.42%), 해부 문장은 249~652자만으로 붉은 벽을 무너뜨린다(30.97 -> 0.78%).
# 측정 기록: docs/dev-loop/2026-10-25-compact-body-guards/spec.md.
#
# 왜(Why) 원본 상수를 줄이지 않나: tests/test_node.py 가 `"same colour" in
# FOOTWEAR_POSITIVE` 같은 문자열을 66곳에서 잠그고 있다. 상수를 줄이면 그
# 잠금이 "그 문구가 실제로 나간다"는 뜻을 잃는다. 그래서 원본은 그대로 두고
# **켤 때만** 압축본으로 치환한다.
#
# 아래 문장은 E3-1 측정에 쓴 문자열과 **문자 단위로 같다.** 다르게 고치면
# 붉은 벽 수치(2.18 -> 39.50)가 그 판에 이전되지 않는다.
COMPACT_ANATOMY_POSITIVE = (
    "Anatomy stays correct and readable: natural proportions, two arms, two legs, "
    "two feet with one foot at the end of each leg, five fingers per hand, one "
    "thumb and four fingers, fingers and limbs separate and whole, no extra or "
    "missing limb, no joined or blended limbs."
)

# 신발은 선언 슬롯이 있으면 그 번호를 지목한다(원본 FOOTWEAR_POSITIVE_SLOT 과
# 같은 이유 — R225). 측정에 쓴 문자열은 슬롯 판(slot=3)이다.
COMPACT_FOOTWEAR_POSITIVE = (
    "The shoes keep the exact colour, silhouette and heel of the footwear "
    "reference image."
)
COMPACT_FOOTWEAR_POSITIVE_SLOT = (
    "The shoes keep the exact colour, silhouette and heel of reference image {slot}."
)

COMPACT_BOUNDARY_POSITIVE = (
    "Hands keep their own place and their own outline. Wrists, forearms and legs "
    "stay distinct from the garment and from any object they rest against."
)


def compact_footwear_guard(slots=None) -> str:
    """압축 신발 가드. 선언 슬롯이 있으면 그 번호를 지목한다.

    원본 `_footwear_guard` 와 달리 CU/ECU upper 변형을 두지 않는다 — 압축본은
    화면에 없는 사지를 요구하지 않으므로 upper 분기가 필요 없다(측정은 전신에서
    했다. 상반신 샷에서의 효과는 미측정).
    """
    try:
        _s = sorted(int(x) for x in (slots or ()))
    except (TypeError, ValueError):
        _s = []
    if _s:
        return COMPACT_FOOTWEAR_POSITIVE_SLOT.format(slot=_s[0])
    return COMPACT_FOOTWEAR_POSITIVE


# 최종 negative 조립 — 공용 조립기에 힌트/믹스/외양/발란스 방어와 extra 를 덧붙인다
def build_negative(cam: dict, extra: str = "", llm_extra: str = "", topic: str = "",
                   hint_defense: bool = False, mix_guard: bool = False,
                   appearance_ref: bool = False, body_balance: bool = False,
                   character_sheet: bool = False, image_count: int = 0,
                   image_labels=None, pose_ref: bool = False,
                   physics_neg: str = "", detail_def: bool = False,
                   furniture: bool = False, furniture_bg: bool = False,
                   remove_item: bool = False,
                   anatomy_count: bool = False,
                   anatomy_count_upper: bool = False,
                   detail_def_upper: bool = False,
                   footwear: bool = False,
                   footwear_upper: bool = False,
                   footwear_bare: bool = False,
                   body_object_boundary: bool = False,
                   body_object_boundary_upper: bool = False,
                   garment_boundary: bool = False,
                   garment_boundary_upper: bool = False,
                   hand_placement: bool = False,
                   seat: bool = False,
                   sheet_kind: str = "") -> str:
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
         "sheet_kind": sheet_kind,
         "detail_def": detail_def, "furniture": furniture,
         "furniture_bg": furniture_bg,
         "remove_item": remove_item,
         "anatomy_count_upper": anatomy_count_upper,
         "detail_def_upper": detail_def_upper,
         "footwear": footwear, "footwear_upper": footwear_upper,
         "footwear_bare": footwear_bare,
         "body_object_boundary": body_object_boundary,
         "body_object_boundary_upper": body_object_boundary_upper,
         "garment_boundary": garment_boundary,
         "garment_boundary_upper": garment_boundary_upper,
         "hand_placement": hand_placement, "seat": seat},
        "color tint", extras=tuple(tail) + (llm_extra, extra),
        physics_neg=physics_neg, pose_ref=pose_ref)


# ---------------------------------------------------------------------------
# DW 포즈 맵 판독 (2026-10-14, pose_image 소켓용).
#
# 왜(Why): pose_image 로 들어오는 DWPreprocessor 결과(검은 배경 + 색 뼈대)에서
# 목표 포즈를 읽는다. 텍스트 의도 파싱은 번역 뭉갬·모호 표현에 약하고, 참조
# 사진 포즈 검출은 시트 분절·복잡 배경에 약하다. 맵은 기하 확정값이다.
# 신경망 검출을 다시 돌리지 않고 색 파싱만 한다 (막대인간에는 신경망 검출이
# 안 먹는다).
#
# aux 렌더 규격 (controlnet_aux dwpose/util.py + wholebody.py 실측):
# - 검은 배경 + 18색 사이클(빨강→...→마젠타)을 OpenPose 순서로 zip.
# - 팔다리: 0.6 밝기 타원. 관절 도트: 전채도 r=4 원.
# - 관절 순서 (wholebody.py openpose_idx/mmpose_idx 재배열 실측):
#   0 nose, 1 neck, 2 R어깨, 3 R팔꿈치, 4 R손목, 5 L어깨, 6 L팔꿈치,
#   7 L손목, 8 R엉덩이, 9 R무릎, 10 R발목, 11 L엉덩이, 12 L무릎,
#   13 L발목, 14 R눈, 15 L눈, 16 R귀, 17 L귀.
#   **midhip 은 없다** (limbSeq [2,9] = neck→RHip). 몸통 길이는 양 엉덩이
#   중점으로 가상 midhip 을 만든다.
# - 팔다리 색 (0.6배): 몸통R neck-RHip 색6, 몸통L neck-LHip 색9,
#   넙다리R 색7, 정강이R 색8, 넙다리L 색10, 정강이L 색11.
# - 손 도트 전부 순청색 [0,0,255] = L무릎 도트와 동색 → 팔다리 연결
#   검증으로 걸러낸다 (연결 없는 동색 도트는 버린다).
# - 사용처 제한: 목표 포즈 분류(sitting|standing)만. 당김 대상으로 쓰면
#   뼈대 유령이 생기므로 측정 전용이다 (image_3 오용 재발 방지).
# ---------------------------------------------------------------------------
_DW_PALETTE = (
    (255, 0, 0), (255, 85, 0), (255, 170, 0), (255, 255, 0),
    (170, 255, 0), (85, 255, 0), (0, 255, 0), (0, 255, 85),
    (0, 255, 170), (0, 255, 255), (0, 170, 255), (0, 85, 255),
    (0, 0, 255), (85, 0, 255), (170, 0, 255), (255, 0, 255),
    (255, 0, 170), (255, 0, 85),
)
# OpenPose 순서 (aux zip 순서와 동일 — wholebody.py 재배열 실측).
# midhip 은 렌더에 없다. 몸통 길이는 양 엉덩이 중점으로 만든다.
_DW_NECK = 1
_DW_RSHO = 2
_DW_LSHO = 5
_DW_RHIP = 8
_DW_RKNEE = 9
_DW_RANKLE = 10
_DW_LHIP = 11
_DW_LKNEE = 12
_DW_LANKLE = 13
# 검증 팔다리: (이름, 관절A, 관절B, 팔레트색 인덱스) — 칠해질 땐 0.6배.
# 엉덩이 붙임용 짧은 팔다리는 쓰지 않는다: 28px급이라 양끝 도트(r=4)가
# 샘플 구간을 먹어버린다 (실측). 엉덩이는 몸통 팔다리(neck→각 엉덩이,
# aux limbSeq k6/k9 실측)로 직접 검증한다.
_DW_LIMBS = (
    ("torsoR", 1, 8, 6),
    ("torsoL", 1, 11, 9),
    ("thighR", 8, 9, 7),
    ("shinR", 9, 10, 8),
    ("thighL", 11, 12, 10),
    ("shinL", 12, 13, 11),
)
_DW_DOT_TOL = 40        # JPEG 재저장 흔들림 허용 (도트 전채도 기준)
_DW_LIMB_TOL = 48
_DW_DOT_AREA = (12, 400)  # r=4 도트 ≈ 50px (반지름 고정이라 해상도 무관).
  # 합쳐진 덩어리(무릎 도트 + 손 도트)는 더 크다 — 무릎/발목 후보는 별도
  # 상한(_DW_MERGE_AREA)으로 살린다. 중심은 어긋나지만 팔다리 검증이 걸러준다.
  # 주의(2026-10-14 실측): "해상도 무관" 은 **1:1 렌더일 때만** 참이다.
  # DW 는 원본 해상도 캔버스에 그린 뒤 resolution 크기로 줄여 반환하므로,
  # 원본이 크면 도트가 1px 로 뭉개져 이 하한에 전부 걸린다 — 실측 4296x7696
  # 입력에서 검출 0개. 그때는 몸통·넙다리 덩어리 경로가 받는다.
_DW_MERGE_AREA = 1500
_DW_MAX_DOTS = 4        # 색당 후보 상한 (다인원 대비)
_DW_MAX_JOINT_DOTS = 6  # 무릎/발목 후보 상한 (합쳐진 덩어리 포함)
_DW_LIMB_NEED = 4       # 7샘플 중 일치 필요 수
_DW_BG_MAX = 48         # 테두리 평균 밝기 상한 (DW 배경은 검정)
_DW_MIN_LIMBS = 3       # 채택 최소 검증 수 (몸통 2개 + 넙다리 1개).
  # 발목은 DW도 자주 놓친다(앉은 사진 R발목 s=0.00 실측) — 정강이·발목은
  # 가점이다. 한쪽 다리만으로 분류하되 deadband(20~40도)가 단일측
  # 오차를 흡수한다.
_DW_MASS_MAX_W = 14.0   # 덩어리 선 폭 상한 (뭉친 얼룩 제외).
  # 실측 2026-10-14: 같은 맵에서 팔다리 폭은 1.59~1.67px(축소본) 였고
  # 1MP 미리축소 입력은 ~11px 였다 — 상한만 절대값으로 두고 하한은 없앴다.
_DW_MASS_MIN_LEN = 0.05  # 팔다리 최소 길이 = 맵 긴 변의 5%.
  # 손 윤곽선 가닥(짧다)을 길이로 거른다. 폭 하한이 하던 일을 대신한다 —
  # 폭 하한은 팔다리(얇고 길다)까지 같이 죽였다(실측 no-torso-mass).


def _dw_dots(u8):
    """필요 9색의 도트 중심 dict {색인덱스: [(x, y)...]} (정규화 좌표)."""
    import cv2
    import numpy as _np
    found = {}
    H, W = int(u8.shape[0]), int(u8.shape[1])
    # 색 루프 9회마다 int32 전화면 변환을 반복하지 않는다 (2026-10-16 오딧).
    _u8i = u8.astype(_np.int32)
    for ci in (_DW_NECK, _DW_RSHO, _DW_LSHO,
               _DW_RHIP, _DW_RKNEE, _DW_RANKLE,
               _DW_LHIP, _DW_LKNEE, _DW_LANKLE):
        c = _np.array(_DW_PALETTE[ci], _np.int32)
        d = _np.abs(_u8i - c)
        m = (d.max(axis=2) <= _DW_DOT_TOL).astype(_np.uint8)
        if int(m.sum()) == 0:
            continue
        n, _lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
        _is_joint = ci in (_DW_RKNEE, _DW_RANKLE, _DW_LKNEE, _DW_LANKLE)
        _amax = _DW_MERGE_AREA if _is_joint else _DW_DOT_AREA[1]
        _cap = _DW_MAX_JOINT_DOTS if _is_joint else _DW_MAX_DOTS
        pts = []
        for k in range(1, n):
            area = float(stats[k, cv2.CC_STAT_AREA])
            if _DW_DOT_AREA[0] <= area <= _amax:
                pts.append((float(cent[k][0]) / W, float(cent[k][1]) / H,
                            area))
        # 컴팩트니스로 가닥을 걸러내지 않는다 — 가려져 잘린 도트 초승달도
        # 살려야 하고 (실측: 서 있는 사진 무릎 도트가 손 도트에 덮임),
        # 선분 조각은 팔다리 연결 검증에서 탈락한다. 면적 순으로 둔다.
        pts.sort(key=lambda p: -p[2])
        if pts:
            found[ci] = [(x, y) for x, y, _ in pts[:_cap]]
    return found


def _dw_limb_score(u8, p1, p2, palette_idx):
    """팔다리 일치 샘플 수 (0~7). 후보 고르기에 쓴다.

    2026-10-16 오딧: 예전엔 호출마다 전화면을 float64 로 변환했다
    (1024x1462 에서 회당 ~34MB, 후보 조합 수백~1600회). 샘플 좌표만
    같은 식으로 변환한다 — 판정 값은 동일하다.
    """
    import numpy as _np
    c = _np.array(_DW_PALETTE[palette_idx], _np.float64) * 0.6
    H, W = int(u8.shape[0]), int(u8.shape[1])
    hit = 0
    for t in (0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85):
        x = int((p1[0] + (p2[0] - p1[0]) * t) * W)
        y = int((p1[1] + (p2[1] - p1[1]) * t) * H)
        if 0 <= x < W and 0 <= y < H:
            px = _np.asarray(u8[y, x], dtype=_np.float64)
            if _np.abs(px - c).max() <= _DW_LIMB_TOL:
                hit += 1
    return hit


def _dw_limb_ok(u8, p1, p2, palette_idx):
    """두 도트 사이가 해당 팔다리색으로 이어지면 True (7샘플 중 4)."""
    return _dw_limb_score(u8, p1, p2, palette_idx) >= _DW_LIMB_NEED


def _dw_limb_masses(u8):
    """팔다리색 덩어리 dict {색인덱스: [(각도, cx, cy, 면적, 끝점1, 끝점2)...]}.

    도트가 뭉개져도 팔다리 타원은 남는다 — 도트 경로가 막히면 이쪽으로
    폴백한다. 각도는 무향 PCA 주축 (0~180), 끝점은 축 투영 5·95퍼센타일
    (튀는 픽셀에 강건). 길쭉함(λ1/λ0 ≥ 4) + 길이(맵 긴 변의 5% 이상)
    + 폭 상한(_DW_MASS_MAX_W)으로 손 윤곽선 가닥을 거른다.
    폭 **하한은 없다** — 축소된 맵에서 팔다리가 1.6px 까지 얇아진다
    (2026-10-14 실측). 중심·끝점은 정규화 좌표.
    """
    import cv2
    import math as _m
    import numpy as _np
    out = {}
    H, W = int(u8.shape[0]), int(u8.shape[1])
    _arr = u8.astype(_np.int32)
    for ci in (6, 9, 7, 8, 10, 11):
        c = (_np.array(_DW_PALETTE[ci], _np.float64) * 0.6).astype(_np.int32)
        d = _np.abs(_arr - c)
        m = (d.max(axis=2) <= _DW_LIMB_TOL).astype(_np.uint8)
        if int(m.sum()) < 120:
            continue
        n, _lab, stats, _cent = cv2.connectedComponentsWithStats(m, 8)
        found = []
        for k in range(1, n):
            area = float(stats[k, cv2.CC_STAT_AREA])
            if area < 120:
                continue
            ys, xs = _np.where(_lab == k)
            if len(xs) < 10:
                continue
            _X = xs.astype(_np.float64)
            _Y = ys.astype(_np.float64)
            _X -= _X.mean()
            _Y -= _Y.mean()
            _cxx = (_X * _X).mean()
            _cxy = (_X * _Y).mean()
            _cyy = (_Y * _Y).mean()
            _tr = _cxx + _cyy
            _det = _cxx * _cyy - _cxy * _cxy
            _disc = max(0.0, _tr * _tr - 4.0 * _det)
            _l1 = (_tr + _m.sqrt(_disc)) / 2.0
            _l0 = (_tr - _m.sqrt(_disc)) / 2.0
            if _l0 < 1e-9 or _l1 / _l0 < 4.0:
                continue
            _length = _m.sqrt(12.0 * _l1)
            _width = area / max(1.0, _length)
            # 폭 **하한을 두지 않는다** (2026-10-14 실측). DW 는 원본 해상도
            # 캔버스에 그린 뒤 resolution 크기로 줄여 반환하므로 원본이 크면
            # 선이 얇아진다 — 4296x7696 입력의 맵에서 팔다리 17개가 전부
            # 1.59~1.67px 이었고 2.5px 하한이 **하나도 빠짐없이** 거부해
            # no-torso-mass 로 떨어졌다(로그 4회). 손 윤곽선 가닥은 폭이
            # 아니라 **길이**(아래)로 거른다 — 가닥은 짧고 팔다리는 길다.
            if _width > _DW_MASS_MAX_W:
                continue
            if _length < _DW_MASS_MIN_LEN * max(H, W):
                continue
            _ang = _m.degrees(_m.atan2(2.0 * _cxy, _cxx - _cyy)) / 2.0
            _t = (_X * _m.cos(_m.radians(_ang))
                  + _Y * _m.sin(_m.radians(_ang)))
            _lo, _hi = _np.percentile(_t, 5), _np.percentile(_t, 95)
            _fx, _fy = _m.cos(_m.radians(_ang)), _m.sin(_m.radians(_ang))
            _mx, _my = float(_cent[k][0]) / W, float(_cent[k][1]) / H
            found.append((_ang % 180.0, _mx, _my, area,
                          (_mx + _fx * _lo / W, _my + _fy * _lo / H),
                          (_mx + _fx * _hi / W, _my + _fy * _hi / H)))
        found.sort(key=lambda t: -t[3])
        if found:
            out[ci] = found[:3]
    return out


def _dw_mass_pose(u8):
    """덩어리 경로 포즈 분류 → (pose|None, 사유). 도트 경로 실패 시 폴백.

    몸통 덩어리 아래끝 = 엉덩이 줄기. 넙다리 덩어리 중 엉덩이 줄에 닿은
    것의 먼 끝 = 무릎 쪽. 방향이 정해지므로 굴곡각이 산다 (덩어리 중심
    상대가 아니라 실제 맞닿음으로 방향을 잡는다 — 접힘 다리에서 중심
    상대는 뒤집힌다). 한쪽 다리만 보여도 비대칭 규칙으로 판정한다.
    어긋난 덩어리(손 가닥 등)는 엉덩이 줄에 못 닿아 탈락한다 — 정밀도
    쪽으로만 틀어진다 (애매하면 None이지 오판이 아니다).
    """
    import math as _m
    try:
        masses = _dw_limb_masses(u8)
    except ImportError:
        return None, "no-cv2-mass"
    H, W = int(u8.shape[0]), int(u8.shape[1])
    _tops = []
    _bots = []
    for ci in (6, 9):
        for (_ang, _cx, _cy, _area, _e1, _e2) in masses.get(ci, [])[:1]:
            if _e1[1] < _e2[1]:
                _tops.append(_e1)
                _bots.append(_e2)
            else:
                _tops.append(_e2)
                _bots.append(_e1)
    if not masses:
        # 팔다리 덩어리가 하나도 없다 — 선이 너무 얇거나(축소된 맵) 사람이
        # 없다. 진단 가능하게 사유를 나눈다 (2026-10-14 실측: 4296x7696
        # 원본을 그대로 DW 에 넣으면 0개, 1MP 로 미리 줄이면 4개).
        return None, "no-limb-mass"
    if not _tops:
        return None, "no-torso-mass"
    _tx = sum(p[0] for p in _tops) / len(_tops)
    _ty = sum(p[1] for p in _tops) / len(_tops)
    _hx = sum(p[0] for p in _bots) / len(_bots)
    _hy = sum(p[1] for p in _bots) / len(_bots)
    _tdx, _tdy = _hx - _tx, _hy - _ty
    _tn = _m.hypot(_tdx, _tdy) or 1.0
    tilt = _m.degrees(_m.acos(max(-1.0, min(1.0, _tdy / _tn))))
    if tilt > 50.0:
        return "lying", "torso-tilt-mass"
    flexes = []
    for _ci in (7, 10):
        for (_ang, _cx, _cy, _area, _e1, _e2) in masses.get(_ci, []):
            _d1 = _m.hypot(_e1[0] - _hx, _e1[1] - _hy)
            _d2 = _m.hypot(_e2[0] - _hx, _e2[1] - _hy)
            if min(_d1, _d2) > 0.12:
                continue
            _knee = _e2 if _d2 > _d1 else _e1
            _vx = _knee[0] - _hx
            _vy = _knee[1] - _hy
            _vn = _m.hypot(_vx, _vy) or 1.0
            _cos = max(-1.0, min(1.0,
                                 (_tdx * _vx + _tdy * _vy) / (_tn * _vn)))
            flexes.append(_m.degrees(_m.acos(_cos)))
            break
    if not flexes:
        return None, "no-thigh-mass"
    if max(flexes) > 75.0 and min(flexes) >= 25.0:
        return "sitting", "hip-flexion-mass"
    if max(flexes) < 20.0:
        return "standing", "legs-extended-mass"
    return None, "ambiguous-mass"


def _dw_skeleton_class(j):
    """관절 dict → sitting|standing|lying|None (정규화 좌표, y 아래 증가).

    midhip 키는 없다 — 양 엉덩이 중점으로 만든다.
    판정은 **두 신호의 교차 검증** (2026-10-14 수치 특징 강화):
      (1) 고관절 굴곡각 = 목→엉덩이 벡터 vs 엉덩이→무릎 벡터 (기존)
      (2) 무릎 굽힘각 = 허벅지 vs 정강이 벡터 (신규, 발목 10/13 사용)
    (2)는 (1)만으로는 정면/3-4 앉음과 서 있음이 겹치는 빈칸을 메운다 —
    앉으면 무릎이 ~90° 굽히고 서 있으면 다리가 곧게 펴져 ~0° 이다. 단
    순수 정면 앉음은 (2)도 2D 투영상 0° 로 죽으므로 여전히 ambiguous 로
    폴백 (정직 — 절대 추측 분류를 내지 않는다). 3-4·측면 참조면 (2)가
    명확히 살아나 앉음을 확정한다.
    비대칭 규칙 (2026-10-14 실제 DW 6장 실측):
      앉음 폴딩 118/62, 앉음2 118/?, 다리뻗은앉음 23/86,
      직립 9.7/3.9, 콩트라포스토 33/63.
    2026-10-15 실측 4장 보강: 앉은1 22.3/84.3, 앉은2 116.3/63.9,
      서있는3 16.5/11.1, 서있는4 34.0/63.6.
    - sitting:
        (A) 깊은 접힘: max(굴곡)>75 & min(굴곡)>=20   (2026-10-15 하한
            25→20 — 참조(kt_인물 앉은 자세1)가 min 22.3 으로 2.7° 미달이라
            "sitting" 이 아예 안 나왔다. 서 있음 실측 최대는 63.6(서있는4)
            으로 다른 축인 max>75 쪽에서 걸러진다. 질량 경로의 같은 규칙
            (1399행)은 실측 표본이 없어 25 그대로 — 임의로 못 건드린다.
        (B) 무릎 굽힘 게이트: 양쪽 굴곡>=45 & 한쪽 무릎굽힘>50 &
            무릎이 엉덩이 아래 — 3-4·측면 중간 앉음을 잡는다.
            min>=45 는 2026-10-15 회귀 수정에서 필수가 됐다: "서 있음은
            무릎이 곧아 안 걸린다" 는 2026-10-14 주석이 틀렸다 —
            콩트라포스토(무릎굽힘 62°)가 rule B 로 앉음에 뒤집혔다
            (R134 회귀, HEAD 실측 sitting/knee-bent). 실측 그룹은
            앉음 최소 굴곡 58~64 (threequarter 59.7, 폴딩 62, 앉은2 63.9)
            vs 서 있음 계열 33~34 (콩트라포스토 33, 서있는4 34) — 45 는
            두 그룹 사이(양쪽 마진 11)에 놓인다.
    - standing: 회복된 쪽 전부 폄 (<20) 이고 무릎도 곧음.
    - 그 외·모호는 None — 텍스트 경로가 커버하므로 추측 분류를 내지 않는다.
    """
    import math as _m
    try:
        if 1 not in j or 8 not in j or 11 not in j:
            return None, "no-torso-hips"
        nx, ny = j[1]
        mx = (j[8][0] + j[11][0]) / 2.0
        my = (j[8][1] + j[11][1]) / 2.0
        torso = (mx - nx, my - ny)
        tn = _m.hypot(*torso)
        if tn < 1e-6:
            return None, "degenerate-torso"
        tilt = _m.degrees(_m.acos(max(-1.0, min(1.0, torso[1] / tn))))
        if tilt > 50.0:
            return "lying", "torso-tilt"
        if not (ny < my - 0.02):
            return None, "incoherent-torso"

        # 다리별 특징: (1) 고관절 굴곡각, (2) 무릎 굽힘각, 무릎이 엉덩이보다 아래
        legs = []
        for hj, kj, aj in ((8, 9, 10), (11, 12, 13)):
            if hj not in j or kj not in j:
                continue
            hx, hy = j[hj]
            kx, ky = j[kj]
            fv = (kx - hx, ky - hy)
            fn = _m.hypot(*fv)
            flex = 0.0
            if fn > 1e-9:
                cosang = max(-1.0, min(1.0,
                                       (torso[0] * fv[0] + torso[1] * fv[1])
                                       / (tn * fn)))
                flex = _m.degrees(_m.acos(cosang))
            bend = None
            knee_below = ky > hy + 1e-4
            if aj in j:
                ax, ay = j[aj]
                # 무릎 내각 = (무릎→엉덩이) 와 (무릎→발목) 사이각.
                # 다리 곧음(두 뼈 평행) → 내각 180 → bend=0, 굽힘 → bend 커짐.
                tv = (hx - kx, hy - ky)
                sv = (ax - kx, ay - ky)
                tl = _m.hypot(*tv)
                sl = _m.hypot(*sv)
                if tl > 1e-9 and sl > 1e-9:
                    cosb = max(-1.0, min(1.0,
                                         (tv[0] * sv[0] + tv[1] * sv[1])
                                         / (tl * sl)))
                    bend = 180.0 - _m.degrees(_m.acos(cosb))
            legs.append({"flex": flex, "bend": bend, "below": knee_below})
        if not legs:
            return None, "no-legs"

        flexes = [l["flex"] for l in legs]
        # (A) 깊은 접힘 — 하한 20 (2026-10-15 실측: 참조 min 22.3, 서 있음
        #     실측 최대 63.6 은 max>75 축에서 걸러진다. 근거는 docstring)
        if max(flexes) > 75.0 and min(flexes) >= 20.0:
            return "sitting", "hip-flexion-deep"
        # (B) 무릎 굽힘 게이트 — 3-4·측면 중간 앉음. min(굴곡)>=45 게이트는
        #     콩트라포스토(무릎굽힘 62°)가 앉음에 뒤집히던 회귀를 막는다
        #     (근거·실측치는 docstring rule B).
        if min(flexes) >= 45.0:
            for l in legs:
                if (l["bend"] is not None and l["bend"] > 50.0
                        and l["below"]):
                    return "sitting", "knee-bent"
        # standing: 모든 다리가 곧음 (무릎도 곧게)
        if max(flexes) < 20.0:
            if all((l["bend"] is None or l["bend"] < 20.0) for l in legs):
                return "standing", "legs-extended"
        return None, "ambiguous"
    except Exception:
        return None, "exception"


def parse_dw_pose_map(image):
    """DW 스켈레톤 맵 → {"pose": sitting|standing|None, "detail": {...}}.

    입력: ComfyUI IMAGE 텐서(B,H,W,C) 또는 numpy HWC uint8. 첫 배치만 본다.
    실패(일반 사진·빈 맵·다인원 모호·판독 불가)는 항상 pose None + 사유 —
    호출자는 기존 방식으로 폴백한다. 절대 추측 분류를 내지 않는다.
    """
    import numpy as _np
    bad = lambda why: {"pose": None, "detail": {"reason": why}}
    try:
        arr = image
        if hasattr(arr, "detach"):
            arr = arr.detach().cpu().numpy()
        arr = _np.asarray(arr)
        if arr.ndim == 4:
            if arr.shape[0] < 1:
                return bad("empty-batch")
            arr = arr[0]
        if arr.ndim != 3 or arr.shape[2] < 3:
            return bad("bad-shape")
        u8 = arr[:, :, :3]
        if u8.dtype != _np.uint8:
            mx = float(_np.nanmax(u8)) if u8.size else 0.0
            u8 = (_np.clip(u8, 0.0, 1.0) * 255.0).astype(_np.uint8) \
                if mx <= 1.0 else u8.astype(_np.uint8)
        H, W = int(u8.shape[0]), int(u8.shape[1])
        if H < 64 or W < 64:
            return bad("too-small")
        edge = _np.concatenate([u8[0:4, :, :].reshape(-1, 3),
                                u8[-4:, :, :].reshape(-1, 3),
                                u8[:, 0:4, :].reshape(-1, 3),
                                u8[:, -4:, :].reshape(-1, 3)], axis=0)
        if float(edge.mean()) > _DW_BG_MAX:
            return bad("not-dw-map")
        try:
            dots = _dw_dots(u8)
        except ImportError:
            return bad("no-cv2")
        best = None
        if _DW_NECK in dots:
            # 몸통 색·사슬 사상은 _DW_LIMBS 표에서 온다 (2026-10-16 오딧:
            # 표와 리터럴이 따로 존재해 관절 상수 6개가 사장되고
            # 6/9·(9,7) 패턴 같은 값이 세 곳에 중복돼 있었다 — 값은 동일).
            _torso_ci = {_nm: _ci for _nm, _a, _b, _ci in _DW_LIMBS}
            for _nk in dots.get(_DW_NECK, [])[:_DW_MAX_DOTS]:
                for _rh in dots.get(_DW_RHIP, [])[:_DW_MAX_DOTS]:
                    if not _dw_limb_ok(u8, _nk, _rh, _torso_ci["torsoR"]):
                        continue
                    for _lh in dots.get(_DW_LHIP, [])[:_DW_MAX_DOTS]:
                        if not _dw_limb_ok(u8, _nk, _lh, _torso_ci["torsoL"]):
                            continue
                        joints = {_DW_NECK: _nk, _DW_RHIP: _rh,
                                  _DW_LHIP: _lh}
                        score = 2
                        for _nm, _par, _jnt, _lci in _DW_LIMBS[2:]:
                            if _par not in joints:
                                continue
                            # 동색 후보가 여럿이면(손 도트 충돌·합쳐진 덩어리)
                            # 팔다리 일치 점수가 가장 높은 것을 고른다.
                            _best_cand, _best_hit = None, _DW_LIMB_NEED
                            for _cand in dots.get(
                                    _jnt, [])[:_DW_MAX_JOINT_DOTS]:
                                _hit = _dw_limb_score(
                                    u8, joints[_par], _cand, _lci)
                                if _hit >= _DW_LIMB_NEED and (
                                        _best_cand is None
                                        or _hit > _best_hit):
                                    _best_cand, _best_hit = _cand, _hit
                            if _best_cand is not None:
                                joints[_jnt] = _best_cand
                                score += 1
                        if score < _DW_MIN_LIMBS:
                            continue
                        if best is None or score > best[0]:
                            best = (score, joints)
        if best is None:
            # 도트 경로 실패 → 덩어리 경로 폴백 (도트가 뭉개져도 팔다리
            # 타원은 남는다 — 실측: 손·얼굴 렌더에 목 도트가 덮인 맵).
            _mcls, _mwhy = _dw_mass_pose(u8)
            if _mcls is None:
                return bad(_mwhy)
            return {"pose": _mcls,
                    "detail": {"reason": "ok-mass:" + _mwhy,
                               "size": [int(W), int(H)]}}
        cls, why = _dw_skeleton_class(best[1])
        if cls is None:
            return bad(why)
        # size: 맵 픽셀 크기. 각도 보정용 (2026-10-15) — 정규화 좌표는
        # 가로·세로가 각각 0~1 로 나눠져 있어 픽셀 비율이 없으면 각도가
        # 어긋난다 (실측 1024x1462 맵에서 thigh_v 평균 53.9 -> 48.0).
        return {"pose": cls,
                "detail": {"reason": "ok", "size": [int(W), int(H)],
                           "joints": {
                    k: [round(float(v[0]), 4), round(float(v[1]), 4)]
                    for k, v in best[1].items()}}}
    except Exception as _e:
        return {"pose": None,
                "detail": {"reason": "exception:%s" % type(_e).__name__}}


def _pose_angles_from_detail(detail):
    """detail({"joints": .., "size": [W, H]}) → 다리별 수치 각도 dict 또는 None.

    반환: {"knee_bend": [다리별 무릎굽힘각...], "thigh_v": [다리별 허벅지-
    수직각...]}. **평균을 내지 않는다** (2026-10-15 실측): 참조 맵에서 좌우
    허벅지각이 20/76 도로 갈렸는데 평균 54 도는 어느 다리도 아니었다 — 두
    값을 그대로 방출한다. size 가 있으면 픽셀 비율로 보정한다 — 정규화
    좌표는 가로·세로가 각각 0~1 로 나눠져 있어 보정 없이는 각도가
    어긋난다 (실측 1024x1462 맵: thigh_v 평균 53.9 -> 48.0,
    knee_bend 53.7 -> 56.7). 발목(10/13)이 없는 다리는 knee_bend 에서
    빠진다 (허벅지는 엉덩이+무릎만으로 성립하므로 두 목록 길이가 다를 수
    있다). size 가 없으면(구 detail·합성 fixture) 정규화 좌표 그대로 —
    기존 동작 유지.
    """
    import math as _m
    j = (detail or {}).get("joints")
    if not j or 8 not in j or 11 not in j:
        return None
    sx = sy = 1.0
    size = (detail or {}).get("size")
    if size and len(size) == 2:
        try:
            sx, sy = float(size[0]), float(size[1])
            if sx <= 0.0 or sy <= 0.0:
                sx = sy = 1.0
        except Exception:
            sx = sy = 1.0
    bends, thigh_vs = [], []
    for hj, kj, aj in ((8, 9, 10), (11, 12, 13)):
        if hj not in j or kj not in j:
            continue
        hx, hy = j[hj]
        kx, ky = j[kj]
        dx, dy = (kx - hx) * sx, (ky - hy) * sy
        if _m.hypot(dx, dy) > 1e-9:
            # 허벅지가 수직에서 기울어진 각 (0=수직=서있음, 90=수평=앉음)
            thigh_vs.append(90.0 - _m.degrees(_m.atan2(abs(dy), abs(dx))))
        if aj in j:
            ax, ay = j[aj]
            # 무릎 내각 기준 (무릎→엉덩이 vs 무릎→발목). 곧음→0, 굽힘→큼.
            tv = ((hx - kx) * sx, (hy - ky) * sy)
            sv = ((ax - kx) * sx, (ay - ky) * sy)
            tl = _m.hypot(*tv)
            sl = _m.hypot(*sv)
            if tl > 1e-9 and sl > 1e-9:
                cosb = max(-1.0, min(1.0,
                                     (tv[0] * sv[0] + tv[1] * sv[1])
                                     / (tl * sl)))
                bends.append(180.0 - _m.degrees(_m.acos(cosb)))
    out = {}
    if bends:
        out["knee_bend"] = bends
    if thigh_vs:
        out["thigh_v"] = thigh_vs
    return out or None


def _leg_layout_from_detail(detail):
    """detail(관절) → 다리 배치 dict({"knee_crossed","ankle_crossed"}) 또는 None.

    왜(Why) 2026-10-15 실측 (input/kt_인물 앉은 자세1 = 사용자 참조):
    교차 자세에서 무릎 x순서가 엉덩이 x순서와 뒤집힌다 (부호 곱 < 0).
    실측 4장 전수: 앉은1(교차)만 뒤집힘(-0.0235), 앉은2·서있는3·서있는4
    는 전부 순서 유지(+0.004~+0.026). 거울 반전에는 부호 곱이 불변이라
    좌우 뒤집힘이 문제가 안 된다.
    발목(10/13)은 9장 중 2장만 검출된다 — comfyui_controlnet_aux 의
    wholebody score>=0.3 게이트가 발목을 떨어뜨리고 제3자 노드라 패치가
    불가라서, 판정은 엉덩이+무릎만으로 성립하도록 설계했다.
    임계값 라벨(모았다/벌렸다, 발 높이)은 표본이 서로 겹쳐서
    (knee/hip 폭비 서 있음 0.13~0.33 vs 앉음 0.39~0.50) 넣지 않는다 —
    부호 검사(교차)만 임계값이 없다. 앉음 분류에서만 부른다.
    """
    j = (detail or {}).get("joints")
    if not j or 8 not in j or 11 not in j:
        return None
    hip_dx = j[8][0] - j[11][0]
    out = {}
    if hip_dx != 0.0 and 9 in j and 12 in j:
        out["knee_crossed"] = hip_dx * (j[9][0] - j[12][0]) < 0.0
    if hip_dx != 0.0 and 10 in j and 13 in j:
        out["ankle_crossed"] = hip_dx * (j[10][0] - j[13][0]) < 0.0
    return out or None


def _fmt_deg(values):
    """다리별 각도 목록 → "~48°" / "~20° and ~76°" 문자열."""
    parts = [f"~{v:.0f}°" for v in values]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return parts[0] + " and " + parts[1]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def pose_map_sentence(map_class, detail=None):
    """목표 포즈 문장 (맵 판독 결과 → positive용 한 줄). None 입력은 "".

    왜(Why) "포즈 맵" 을 문장에 쓰지 않는가 (2026-10-14 실측 A/B): 맵은
    샘플러의 **이미지 conditioning 에 들어가지 않는다** — 모델에게 "포즈 맵"
    은 존재하지 않는 물건이라 그 문장은 지시력이 약하다. 대상의 신체를
    직접 묘사해야 먹는다. 같은 그래프에서 image_1(서 있는 사진)을 그대로
    두고 구체 묘사 문장만 넣었더니 벤치에 앉은 결과가 나왔다
    (`The woman ... is sitting on a park bench, seated posture, thighs
    horizontal and knees bent forward`). 실측 대조:
      base(문장 없음) / pose3(참조만 추가)  -> 서 있음
      text(구체 묘사 문장)                  -> 앉음
    2026-10-14 수치 강화: detail(관절)이 있으면 실측 각도를 문장에 박아
    "sitting" 한 단어보다 훨씬 모호하지 않은 제어를 한다 (신체 오류 덤
    잡기와도 연동 — 키퍼 부위 복원의 기준 시그널이 된다).
    2026-10-15 다리 배치: detail 에서 _leg_layout_from_detail 로 교차
    여부를 뽑아 절을 덧붙인다 — 참조를 따라 앉기는 되는데 다리 배치는
    안 따라가던 빈칸 (실측: 참조는 굴곡 22.3/84.3 + 무릎 x순서 반전).
    2026-10-15 다리별 값: 각도를 평균하지 않고 다리별로 방출한다 — 좌우가
    20/76 도로 갈리는 참조에서 평균 54 도는 어느 다리도 아니라 문장이
    거짓이었다. detail 에 size 가 있으면 픽셀 비율 보정 각도를 쓴다.
    angle 절이 하나라도 있으면 수치 문장, 없으면(발목·관절 부족) 기존
    서술 문장으로 — 배치 절은 어느 쪽에도 덧붙인다.
    """
    if map_class == "sitting":
        ang = _pose_angles_from_detail(detail) if detail else None
        lay = _leg_layout_from_detail(detail) if detail else None
        bits = []
        if ang:
            if ang.get("knee_bend"):
                bits.append(f"knees bent {_fmt_deg(ang['knee_bend'])}")
            if ang.get("thigh_v"):
                bits.append(f"thighs {_fmt_deg(ang['thigh_v'])} "
                            "from vertical")
        if lay:
            if lay.get("knee_crossed"):
                bits.append("legs crossed at the knee")
            elif lay.get("ankle_crossed"):
                bits.append("ankles crossed")
        if bits:
            return ("The subject is seated — " + ", ".join(bits)
                    + ", weight resting on the seat.")
        return ("The subject is seated: hips flexed, thighs roughly "
                "horizontal and knees bent forward, weight resting on the "
                "seat.")
    if map_class == "standing":
        return ("The subject is standing upright: legs extended and "
                "vertical, hips level, weight on both feet.")
    if map_class == "lying":
        return ("The subject is lying down: torso horizontal and reclined, "
                "body resting on the surface.")
    return ""
