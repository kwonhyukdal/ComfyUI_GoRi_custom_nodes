# -*- coding: utf-8 -*-
"""신원·단일인물·다인·보조 역할·참조 이미지 가드 문구."""

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
"MAX_REFERENCE_IMAGES", "VISION_DETAIL", "VISION_DETAIL_DEFAULT", "vision_detail_px", "build_identity_anchor", "build_single_person_anchor", "build_duo_person_anchor", "reference_guard", "build_secondary_role_anchor"
]


MAX_REFERENCE_IMAGES = 10


# LLM 비전 전송 크기. 왜(Why): 로컬 LLM 비전 추론이 느린 주범은 서버 연산이라
# 노드가 빠르게 할 수 없고, 줄일 수 있는 건 전송 짐뿐이다. 기본값(768)은 기존
# 동작 그대로 — 판단 디테일이 떨어질 수 있어 옵션으로만 제공한다.
VISION_DETAIL = {
    "선명 (768)": 768,
    "균형 (512)": 512,
    "절약 (384)": 384,
}


VISION_DETAIL_DEFAULT = "선명 (768)"


def vision_detail_px(label: str) -> int:
    """vision_detail 라벨 → 전송 한 변 px. 알 수 없으면 768(기존값)."""
    try:
        return int(VISION_DETAIL.get((label or "").strip(), 768))
    except (ValueError, TypeError, AttributeError):
        return 768


def build_identity_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Add a short human-reference identity anchor for text-only conditioning.

    This is intentionally narrower than the legacy guard: it does not modify
    body proportions, anatomy, or negative conditioning. Skin realism is
    included because plastic skin comes from photographic rendering, which
    this camera node can direct.

    identity 소스는 역할 계획(plan)이 선출한 주 피사체로 둔다 -- 왜(Why):
    첫 연결이 사물(핸드백 등)이면 사물을 인물 identity 소스로 지목하는
    오동작이 생긴다(정밀 검토 발견 #1).
    """
    if image_count <= 0 or not _is_human_subject(topic):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    first = str(plan["main"])
    return (f"Use reference image {first} as the exact identity source for the main person. "
            "Preserve the same facial identity and same facial structure, age, ethnicity, hairstyle, "
            "and clothing unless the instruction explicitly changes them. "
            "Render natural realistic skin texture with visible pores and fine detail, "
            "soft directional light, subtle film grain, no airbrushed smoothing.")


def build_single_person_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Prevent a single reference subject from being expanded into a duplicate.

    주 피사체도 역할 계획(plan)이 선출한다 -- 왜(Why): 첫 연결이 사물이고
    유일한 인물이 다른 슬롯에 있으면(1번 핸드백 + 2번 여성) 구버전은
    "유일 인물인데도 억제 문구가 아예 안 붙었다" -- plan 주체로 발화하면
    올바른 슬롯으로 붙는다(정밀 검토 발견 #2). plan에 추가 인물이 있으면
    (duo 이상) 기존처럼 억제한다.
    """
    if (image_count <= 0 or not _is_human_subject(topic)
            or _is_multi_person_request(topic)
            or _is_reflection_scene(topic)):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    if plan["persons"]:
        return ""
    first = str(plan["main"])
    return (f"Exactly one main person in the output, using reference image {first} as the only subject. "
            "Single-person composition. No additional person, copy, or mirrored companion.")


def build_duo_person_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """보조 슬롯 인물 지정 시 해당 정체성을 모두 살린다 (2~10번 일반화).

    인물 간 신체 융합 방지를 포함한다. 왜(Why): 두 정체성을 살리라는 문구만
    있으면 모델이 두 신체를 하나로 녹이거나 팔다리를 뒤섞을 수 있어, 양방향
    (남성→여성, 여성→남성) 융합을 막는 분리 문구가 필요하기 때문이다.
    standalone 경로는 reference_guard의 duo 분기가 이 함수를 그대로 쓴다.
    사물 명시 슬롯(핸드백·시계 등)이 있으면 그 정체성을 살리지 않고
    "사물로만" 제한하는 문구를 덧붙인다 -- 왜(Why): duo 앵커만 던지면
    사물 슬롯이 사람으로 변하거나 복제될 수 있다.
    """
    if image_count < 2:
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    main, wanted, objects = plan["main"], plan["persons"], plan["objects"]
    if (not wanted and _second_person_slots(topic) and len(labels) >= 2
            and int(labels[1]) not in (9, 10) and int(labels[1]) not in objects
            and int(labels[1]) != main):
        # "두 번째 사람"처럼 슬롯 번호 없이 지칭하면 두 번째 연결 이미지를 쓴다.
        # 9·10번은 외양 참조 전용, 사물 명시 슬롯은 사물, 이미 주 피사체인 슬롯은
        # 중복 지정 대상이 아니다.
        wanted = [int(labels[1])]
    # 슬롯 번호 없이 "두 명 / couple / two people" 만 말한 경우.
    # 왜(Why) 이 폴백이 없으면: duo 앵커가 빈 문자열로 빠져서 reference_guard 가
    # 두 번째 참조를 "배경/소품/제품 역할로만" 지시한다(2026-09-28 실측). 사용자가
    # 두 사람의 사진을 붙였는데 두 번째 사람이 **소품으로 강등**되는 정반대 지시가
    # 나간다 — 가장 흔한 표현에서 가장 큰 오작동이다.
    _multi_fallback = False
    if (not wanted and len(labels) >= 2 and _is_multi_person_request(topic)
            and int(labels[1]) not in (9, 10) and int(labels[1]) not in objects
            and int(labels[1]) != main):
        wanted = [int(labels[1])]
        _multi_fallback = True
    persons = [str(main)] + [str(s) for s in wanted if int(str(s)) != main]
    # 마지막 게이트: 슬롯 명시("두 번째 사람") 또는 다인물 표현("두 명") 둘 중.
    if len(persons) < 2 or not (_is_second_person_request(topic)
                                or _multi_fallback):
        return ""
    count_word = _NUMBER_WORDS.get(len(persons), str(len(persons)))
    roles = " and ".join(
        f"person {_ORDINAL_WORDS.get(i + 1, str(i + 1))} from reference image {slot}"
        for i, slot in enumerate(persons))
    anchor = (f"{count_word} main people in the output: {roles}. "
              "Preserve each person's facial identity, hairstyle, and outfit. "
              "Keep each person's body fully separate with its own torso, two arms, and two legs, "
              "no merged or fused bodies, no extra limbs, no limbs swapping between people, "
              "no body parts blending into the other person, "
              "maintain clear personal boundaries unless physical contact is explicitly requested. "
              "No extra people, no cloned faces.")
    if objects:
        anchor += (" Use reference image(s) " + ", ".join(str(s) for s in objects)
                   + " only as props/objects, never as people.")
    return anchor


def reference_guard(image_count: int, image_labels=None, topic: str = "") -> str:
    """단일/다중 레퍼런스 이미지용 positive guard 문구를 반환한다."""
    if image_count <= 0:
        return ""
    # 왜(Why) 빈 장면이면 빈 문자열인가 (2026-10-02 실측): 참조에 사람이 없는데
    # "same person" 을 내보내면 모델이 누구를 만들지 몰라 유령(반투명 인물)을
    # 만든다 — 의자·침대 참조에서 실측. pose 0점으로 게이트는 알지만 카메라는
    # 몰랐다. 명시적 빈 장면 지시가 있으면 identity 문구를 내지 않는다.
    # 빈 문자열 topic 은 해당 없음 (사람 사진에 설명 없을 수 있음) — 명시적
    # 언급만 본다. 오탐보다 누락이 안전하다 (누락이면 기존 동작 그대로).
    if _is_empty_scene(topic or ""):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    main = str(plan["main"])
    # 동물 주제면 "얼굴 구조·헤어스타일"은 정면 모순이다(2026-09-28 실측:
    # "강아지 한 마리" 에 same facial structure/same hairstyle 과
    # 별도 five fingers/human proportions 까지 붙어 충돌했다). 품종명을
    # 하드코딩하지 않고 종·무늬 수준으로 일반화한다.
    if _is_animal_subject(topic or ""):
        if image_count == 1:
            return (f"preserve the same subject identity as reference image "
                    f"{main}, same species, same coat pattern and markings, "
                    "same body proportions, same overall color identity")
        return (f"use reference image {main} as the main subject identity "
                f"(same species, same coat pattern and markings, same body "
                f"proportions), do not humanize it, do not give it human hands "
                f"or facial features")
    if image_count == 1:
        # 왜(Why) 의상 교체 명시면 "same outfit" 을 빼나 (2026-10-02 실측):
        # 명시 요청("red evening dress 로 교체")에도 이 줄이 함께 나가면 같은
        # 프롬프트에 교체 지시와 유지 지시가 공존한다. 모델은 참조 이미지를 보고
        # 원본을 택하므로 교체가 일어나지 않는다 — 0.00(키퍼 미동작)에서도 같은
        # 옷이 나와 키퍼 문제가 아님을 확인했다. 얼굴·헤어·체형 유지는 그대로
        # 두고 옷만 뺀다. 신원은 유지하되 의상은 바꾸는 것이 요청의 의미다.
        if _is_text_outfit_change(topic or ""):
            return (f"preserve the same subject identity as reference image {main}, "
                    "same facial structure, same hairstyle, "
                    "same body proportions, same overall color identity")
        return (f"preserve the same subject identity as reference image {main}, "
                "same facial structure, same hairstyle, same outfit, "
                "same body proportions, same overall color identity")
    duo = build_duo_person_anchor(image_count, topic, image_labels=image_labels)
    if duo:
        # 두 번째 reference가 인물 역할이면 복제 금지 대신 두 정체성 보존을 둔다.
        # 사물 명시 슬롯의 소품 방어는 duo 앵커가 함께 전달한다.
        return duo
    secondary = _secondary_role_labels(labels, main=plan["main"],
                                       persons=plan["persons"],
                                       poses=plan["poses"],
                                       clothing=plan["outfits"])
    head = f"use reference image {main} as the only main human identity, "
    if secondary:
        head += ("use reference image(s) " + ", ".join(secondary)
                 + " only for their explicitly requested roles "
                 "such as background, composition, lighting, mood, or color, "
                 # 왜(Why) outfit 을 기본 목록에서 뺐나(2026-09-28 실측):
                 # topic 이 비면 "explicitly requested role" 이 없어서 모델이
                 # 이 목록에서 **자유롭게** 고른다. 그때 outfit 을 골랐고,
                 # 포즈 참조 이미지의 카디건+청바지가 그대로 복제됐다
                 # (포즈 가드 문구는 정확했는데 그 문구가 실행조차 안 됐다).
                 # 옷은 **명시 요청 시에만** 옮기고, 그 경로는 OUTFIT_GUARD 가
                 # 전담한다. 명시 요청 없는 옷 복사는 항상 실패였다.
                 "never their face, hair, skin tone, body identity, "
                 "clothing or outfit, and never their pose unless it was "
                 "explicitly requested, ")
    return head + (
        "do not duplicate the main subject, face, body, outfit, product, or background subject, "
        "do not turn secondary references into extra people, animals, products, or props "
        "unless explicitly requested, no cloned faces, no repeated bodies, "
        "no duplicated characters, no crowd unless requested, "
        "no background people unless requested"
    )


def build_secondary_role_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Qwen 경로용 다중 reference 역할 가드 (짧은 1문장).

    왜(Why): prompt_in 표준 경로의 positive_text에는 identity/single-person
    anchor만 있고, 보조 reference(배경/의상/소품)의 역할 제한과 주체 복제
    금지 문구가 없었다. standalone 경로의 장문 가드 대신 1문장으로 둔다.
    주 피사체는 계획(plan)이 선출한다 -- 첫 연결이 사물이면 다음 인물이 주체.
    """
    if image_count < 2:
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    secondary = _secondary_role_labels(labels, main=plan["main"],
                                       persons=plan["persons"],
                                       poses=plan["poses"],
                                       clothing=plan["outfits"])
    head = f"Use reference image {plan['main']} as the only main subject, "
    if secondary:
        head += ("use reference image(s) " + ", ".join(secondary)
                 + " only for explicitly requested roles "
                 "such as background, outfit, prop, product, style, lighting, "
                 "composition, or mood, ")
    return head + "do not duplicate the main subject."
