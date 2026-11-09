# -*- coding: utf-8 -*-
"""신원·단일인물·다인·보조 역할·참조 이미지 가드 문구."""

from __future__ import annotations

import re

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
try:
    from .cam_subject import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_subject import *  # noqa: F403


__all__ = [
"MAX_REFERENCE_IMAGES", "VISION_DETAIL", "VISION_DETAIL_DEFAULT", "vision_detail_px", "GARMENT_RETENTION_POSITIVE", "NO_DUPLICATE_MAIN", "SECONDARY_REF_NO_DUPLICATE", "NO_DUPLICATE_TAIL", "NO_DUPLICATE_POSITIVE", "SINGLE_PERSON_TAIL", "SINGLE_PERSON_POSITIVE", "SINGLE_FRAME_POSITIVE", "_MULTI_PERSON_CONJUNCTIONS", "_MULTI_PERSON_RELATION_NOUNS", "_MULTI_COUNT_PATTERNS", "_has_multi_person_conjunction", "_multi_person_signal", "build_reference_free_anchor", "build_identity_anchor", "build_single_person_anchor", "build_duo_person_anchor", "reference_guard", "build_secondary_role_anchor", "auto_reference_roles_positive"
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


# 의상 보존 상용구 (2026-10-25 C1 실측). 왜(Why) 이 문구가 필요한가:
# denoise 1.0 합성에서 모델이 참조 1번의 **겉옷(카디건)** 을 지우는 실패가
# 실측됐다. 부드러운 유지 문구("의상은 참조 그대로 유지한다")는 3/3 실패해
# 카디건이 사라졌다. 실패 모드는 옷을 *바꾸는* 것이 아니라 *지우는* 것이었다.
# 그래서 "지우지 말라(remove/omit/drop)" 와 "없는 옷을 더하지 말라(add)" 를
# 옷 이름 없이 지시한다. 실측: 이 강한 일반 문구는 옷 이름을 적지 않고도
# 카디건을 3/3 보존했다(seed 42/7/999 — 한국어 2 · 영어 1). 슬롯을 박지 않는
# 이유: 이 문구를 붙이는 앵커가 앞에서 이미 주 참조 슬롯을 지목하므로, 여기서
# 다시 지목하면 오히려 슬롯 하드코딩이 된다. 규칙(C) 경로 전용이며 LLM(A)은
# 이 문구 위에 자신이 읽은 옷 이름을 더한다.
GARMENT_RETENTION_POSITIVE = (
    "Copy the top and bottom garments from the reference image exactly as "
    "they appear. Keep every garment visible on the person in the reference "
    "image, including outer layers such as cardigans, jackets and coats; do "
    "not remove, omit, drop or replace any garment, and do not add clothing "
    "that is not in the reference."
)


# ---------------------------------------------------------------------------
# 슬롯-비의존 가드 조각 (2026-11-10)
#
# 왜(Why) 이 상수들이 따로 있나: 복제·군중 금지와 한 명 고정 문구는 **참조
# 이미지를 지목하지 않는다**. 그래서 참조가 없어도 그대로 쓸 수 있는데,
# 종전에는 참조 전용 함수(reference_guard·build_single_person_anchor)의 문 하나
# (`image_count > 0`) 안에 묶여 있어 **참조가 없으면 같이 죽었다**. 그 결과
# "한 명" 주제에 여러 사람을 막는 문구가 아예 안 나가 3명이 나왔다(실측).
#
# 참조 전용 조각(`SECONDARY_REF_NO_DUPLICATE`)만 "secondary references" 를
# 지목하므로 참조 전용으로 남기고, 나머지는 상수로 뽑아 두 경로가 공유한다.
# 문자열을 나눠도 합치면 **바이트 동일**이라 참조 경로의 동작은 안 바뀐다.
NO_DUPLICATE_MAIN = (
    "do not duplicate the main subject, face, body, outfit, product, or "
    "background subject"
)

SECONDARY_REF_NO_DUPLICATE = (
    "do not turn secondary references into extra people, animals, products, or "
    "props unless explicitly requested"
)

NO_DUPLICATE_TAIL = (
    "no cloned faces, no repeated bodies, no duplicated characters, "
    "no crowd unless requested, no background people unless requested"
)

# 참조가 없어도 나가는 복제·군중 금지 (참조 전용 조각을 뺀 형태).
NO_DUPLICATE_POSITIVE = f"{NO_DUPLICATE_MAIN}, {NO_DUPLICATE_TAIL}"

# 한 명 고정 — 슬롯 지목이 없는 꼬리. 참조 버전(앞에 "using reference image N")
# 과 꼬리를 공유해 복붙을 막는다.
SINGLE_PERSON_TAIL = (
    "Single-person composition. No additional person, copy, or mirrored "
    "companion."
)

# 한 명 주제에서 참조 없이 나가는 한 명 고정 문구 (슬롯 지목 없음).
SINGLE_PERSON_POSITIVE = (
    "Exactly one main person in the output. " + SINGLE_PERSON_TAIL
)

# 한 화면 고정 — 출력이 콜라주·분할 패널로 나오는 것을 막는다 (2026-11-10 R260).
# 왜(Why) 필요한가(사용자 실측): R258 로 "한 명 고정" 을 넣었는데도 같은 주제가
# **3칸 콜라주**(같은 인물이 칸마다 반복)로 나왔다. 그 실행의 부정어에는
# collage/panel/split 계열이 0건이었다. 그 문구는 9·10번 외양 참조 경로에만
# 있어 일반 인물 경로엔 안 나갔다 — 여기서 참조 없이도 쓸 수 있는 조항으로 낸다.
SINGLE_FRAME_POSITIVE = (
    "A single full-frame image. Not a collage, not a multi-panel layout, "
    "no split view or split screen."
)


def build_identity_anchor(image_count: int, topic: str, image_labels=None) -> str:
    """Add a short human-reference identity anchor for text-only conditioning.

    This is intentionally narrower than the legacy guard: it does not modify
    anatomy or negative conditioning. Skin realism is included because plastic
    skin comes from photographic rendering, which this camera node can direct.

    2026-10-21: 'same body proportions, same overall color identity' 를
    포함한다. 종전엔 이 앵커가 base run 의 reference_guard 보다 방어 폭이
    좁아 Qwen prompt_in 경로에서 체형·색 일관성이 빠졌다(감사 발견). base
    run 과 같은 문구를 넣어 두 경로의 신원 방어를 맞춘다.

    identity 소스는 역할 계획(plan)이 선출한 주 피사체로 둔다 -- 왜(Why):
    첫 연결이 사물(핸드백 등)이면 사물을 인물 identity 소스로 지목하는
    오동작이 생긴다(정밀 검토 발견 #1).
    """
    if image_count <= 0 or not _is_human_subject(topic):
        return ""
    labels = [str(i) for i in (image_labels or list(range(1, image_count + 1)))]
    plan = _person_object_plan(topic, labels)
    first = str(plan["main"])
    head = (f"Use reference image {first} as the exact identity source for the main person. "
            "Preserve the same facial identity and same facial structure, age, ethnicity, hairstyle, "
            "same body proportions, same overall color identity")
    tail = ("Render natural realistic skin texture with visible pores and fine detail, "
            "soft directional light, subtle film grain, no airbrushed smoothing.")
    # 왜(Why) 교체 감지면 의상 보존 문구를 바꾸나 (2026-10-13 실측): 종전에는
    # 감지와 무관하게 "Do not change any clothing, shoe ..." 를 **무조건** 내보냈다.
    # 사용자가 지시한 신발 교체("단화를 신고")와 같은 프롬프트에 유지 지시가
    # 공존하자 모델은 둘 중 하나만 반영했다 — 실측에서 신발이 베이지 슬리퍼로
    # 일부만 바뀌었다. 명시 교체가 있으면 **적용 + 나머지 보존**으로 바꾼다.
    # 신원(얼굴·헤어) 문구는 어느 쪽이든 남는다 — reference_guard 2026-10-02
    # 결정과 같은 원칙이다. 이 문구는 그대로 키퍼(camera_prompt)로 전달돼
    # _prompt_intent 가 의도로 읽는다(교체 동사 change + 의류 명사).
    if _is_text_outfit_change(topic or ""):
        return (head
                + ". Apply the clothing change exactly as instructed by the user, "
                "and keep every other garment, shoe, and accessory exactly as in "
                "the reference image. "
                + tail)
    # 선언된 신발 참조 슬롯 (2026-10-24, R225). 왜(Why) 신발만 돌리나: `3번:
    # 하이 힐` 처럼 신발 참조를 선언한 실행에서 아래 기본 문장은 "exact shoes …
    # from the reference image" 로 **주 피사체(1번)** 의 신발을 지목하고, 그
    # 문장과 신발 가드(`FOOTWEAR_POSITIVE_SLOT`, 3번 지목)가 정면 충돌한다.
    # 옷·장신구는 주 피사체 참조에서 오는 것이 맞으므로 신발만 선언 슬롯으로
    # 돌린다. 선언이 없으면 **아래 기본 문장 그대로**(바이트 동일).
    _fw_decl = sorted(_footwear_slots(topic or ""))
    if _fw_decl and str(_fw_decl[0]) != first:
        # 2026-10-24 (R227): `other than the shoes` 를 명시한다. 왜(Why):
        # 종전 문장은 "every garment from reference image 1"(1번의 모든 옷)과
        # "the exact shoes from reference image 3"(3번의 신발)를 나란히 두어,
        # 1번의 신발(흰 슬립온)이 "garment" 로 다시 새어 들어왔다 — 실측
        # 생성물에서 색은 3번(검정)을 따랐지만 구조는 두 참조의 절충이 됐다.
        return (head
                + f", exact outfit including every garment other than the shoes "
                f"from reference image {first}, "
                "exact accessories and jewelry, and the exact shoes from "
                f"reference image {_fw_decl[0]}, unless the instruction explicitly "
                "changes them. "
                + GARMENT_RETENTION_POSITIVE + " "
                "Do not change, replace, or alter any clothing, accessory, or shoe "
                f"other than the shoes from reference image {_fw_decl[0]}. "
                + tail)
    return (head
            + ", exact outfit including every garment, exact shoes, exact accessories and jewelry "
            "unless the instruction explicitly changes them. "
            + GARMENT_RETENTION_POSITIVE + " "
            "Do not change, replace, or alter any clothing, shoe, or accessory from the reference image. "
            + tail)


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
            + SINGLE_PERSON_TAIL)


# 두 인물을 잇는 접속 표기. 영어는 앞뒤 공백으로 단어 경계를 대신한다
# ("and" 가 다른 단어 안에서 잡히지 않게).
_MULTI_PERSON_CONJUNCTIONS = (
    " and ", " & ", " plus ", " with ",
    "와 ", "과 ", "랑 ", "이랑 ", "하고 ", "그리고 ",
)


# 관계·역할 명사 (다인 판정 전용, 2026-11-10). 왜(Why) 공용
# HUMAN_SUBJECT_KEYWORDS 에 안 넣나: 그 목록은 `_is_human_subject` 등 사람 가드
# 12종이 함께 읽는다. 관계 명사를 거기 넣으면 "딸기"(딸)·"형광등"(형) 같은 사물
# 주제가 사람으로 번질 위험이 다른 가드로 퍼진다. 여기서는 **접속 판정에서
# 낱말을 세는 데만** 쓴다. 왜(Why) 필요한가(2026-11-10 실측): "여성과 딸"·
# "a man and his son" 은 사람 낱말이 하나뿐이라 다인으로 안 잡혀, 한 명 주제가
# 아닌데도 "Exactly one main person" 이 나갔다(정반대 지시).
_MULTI_PERSON_RELATION_NOUNS = (
    "son", "daughter", "mother", "father", "mom", "dad", "wife", "husband",
    "sister", "brother", "friend", "friends", "colleague", "partner", "guy",
    "guys", "cousin", "nephew", "niece", "parent", "parents", "sibling",
    "siblings", "grandmother", "grandfather",
    "딸", "아들", "어머니", "아버지", "엄마", "아빠", "아내", "남편", "부인",
    "언니", "누나", "오빠", "형", "동생", "친구", "동료", "부모", "가족",
)


# 수량 + 사람 (다인 판정, 2026-11-10). 왜(Why) 필요한가: "three women"·
# "세 명의 여성" 은 공용 MULTI_PERSON_KEYWORDS 의 "two women"/"두 명" 에 안 걸려
# 한 명으로 오판됐다(실측). 수량 낱말이 **사람 낱말에 붙을 때만** 다인으로 본다 —
# "두 그루 나무"·"two cats" 같은 사물 수량은 안 잡아 한 명 주제의 고정 문구를
# 지키지 않는다.
_MULTI_COUNT_PATTERNS = (
    re.compile(
        r"\b(?:two|three|four|five|six|seven|eight|nine|ten|[2-9]|\d{2,})\s+"
        r"(?:women|men|people|persons|girls|boys|ladies|children|kids|"
        r"characters|models|figures|adults|babies)\b", re.I),
    re.compile(
        r"(?:두|세|네|다섯|여섯|일곱|여덟|아홉|열|[2-9]|\d{2,})\s*(?:명|사람)"),
)


def _has_multi_person_conjunction(text: str) -> bool:
    """접속 표기가 있고 **사람 낱말이 둘 이상**이면 True.

    왜(Why) 사람 낱말 개수까지 보나: 접속만 보면 "a woman with a hat"·
    "여성과 의자" 처럼 사람 하나 + 사물을 다인물로 오판한다. 오판하면 한 명
    주제에 "혼자 아님" 전제를 만들 수 있어 낱말 수로 제한한다.

    낱말은 공용 목록(HUMAN_SUBJECT_KEYWORDS)에 관계·역할 명사
    (`_MULTI_PERSON_RELATION_NOUNS`)를 더해 센다. 왜(Why) 더하나(2026-11-10
    실측): "여성과 딸"·"a man and his son" 은 관계 명사가 공용 목록에 없어
    낱말이 하나로 세어져 다인을 놓쳤다 — 설계의 "확신 없으면 안 내는 쪽" 과
    어긋났다. 새 공용 목록을 만들지 않고 여기서만 더해 파급을 막는다.
    영문은 `_ascii_word_present` 로만 본다("men" 이 "women" 안에서, "man" 이
    "woman" 안에서 잡히는 것을 막는다).
    """
    t = (text or "").lower()
    if not any(c in t for c in _MULTI_PERSON_CONJUNCTIONS):
        return False
    words = set()
    for kw in HUMAN_SUBJECT_KEYWORDS + _MULTI_PERSON_RELATION_NOUNS:
        try:
            if _ascii_only(kw):
                if _ascii_word_present(t, kw):
                    words.add(kw)
            elif _ko_word_present(t, kw):
                words.add(kw)
        except Exception:  # noqa: BLE001
            continue
    return len(words) >= 2


def _multi_person_signal(topic: str) -> bool:
    """여러 명 신호가 하나라도 있으면 True. 판정 실패도 True(안전한 쪽).

    왜(Why) 판정 실패를 True 로 두나: 이 함수는 "한 명 고정 문구를 낼지"만
    가른다. 실패를 False 로 두면 다인물 주제에 "Exactly one person" 이 나가
    **정반대 지시**가 된다. 그래서 못 미더우면 여러 명으로 본다.

    왜(Why) 접속·수량까지 보나: 기존 `_is_multi_person_request` 는 "a woman and
    a man" 같은 **관사형 접속**과 "three women"·"세 명의 여성" 같은 **수량+사람**
    을 못 잡는다(실측 False). 그 구멍을 여기서 막는다.
    """
    t = topic or ""
    try:
        if _is_multi_person_request(t):
            return True
        if _is_second_person_request(t):
            return True
        if _is_reflection_scene(t):
            return True
        if any(p.search(t) for p in _MULTI_COUNT_PATTERNS):
            return True
    except Exception:  # noqa: BLE001
        return True
    return _has_multi_person_conjunction(t)


def build_reference_free_anchor(image_count: int, topic: str = "") -> str:
    """참조 이미지가 없어도 나가야 하는 슬롯-비의존 긍정 문구.

    왜(Why) 필요한가 (2026-11-10 실측): 복제·군중 금지와 한 명 고정 문구는
    참조를 지목하지 않아 참조 없이도 쓸 수 있는데, 참조 전용 함수
    (reference_guard·build_single_person_anchor)의 `image_count > 0` 문 안에
    묶여 있어 **참조가 없으면 같이 죽었다**. 그 결과 "한 명" 주제에 여러 사람을
    막는 문구가 아예 안 나가 3명이 나왔다.

    반환:
      참조가 있으면 ""            — 참조 경로는 기존 함수가 담당한다(무변화).
      사람 주제가 아니면 ""       — 사물·풍경에 "사람 복제 금지" 는 무의미하다.
      그 외 → (a) 복제·군중 금지, 한 명 주제면 (b) 한 명 고정, 그리고 항상
              (c) 한 화면 고정(콜라주·분할 패널 방지, 2026-11-10 R260).

    (c) 는 한 명·여러 명 **모두**에 낸다 — 여러 명 장면도 콜라주로 쪼개지면
    실패이므로, R258 의 (b)(여러 명에선 정반대라 제한)와 조건이 다르다.
    """
    if image_count and image_count > 0:
        return ""
    if not _is_human_subject(topic or ""):
        return ""
    parts = [NO_DUPLICATE_POSITIVE]
    if not _multi_person_signal(topic or ""):
        parts.append(SINGLE_PERSON_POSITIVE)
    parts.append(SINGLE_FRAME_POSITIVE)
    return " ".join(parts)


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
            and int(labels[1]) not in appearance_ref_slots(topic, labels)
            and int(labels[1]) not in objects
            and int(labels[1]) != main):
        # "두 번째 사람"처럼 슬롯 번호 없이 지칭하면 두 번째 연결 이미지를 쓴다.
        # 외양 참조로 남은 9·10번(선언이 없는 슬롯)은 제외, 사물 명시 슬롯은 사물,
        # 이미 주 피사체인 슬롯은 중복 지정 대상이 아니다. 선언된 9·10번은
        # 1~8번과 같이 두 번째 인물이 될 수 있다 (2026-10-23, AC-19).
        wanted = [int(labels[1])]
    # 슬롯 번호 없이 "두 명 / couple / two people" 만 말한 경우.
    # 왜(Why) 이 폴백이 없으면: duo 앵커가 빈 문자열로 빠져서 reference_guard 가
    # 두 번째 참조를 "배경/소품/제품 역할로만" 지시한다(2026-09-28 실측). 사용자가
    # 두 사람의 사진을 붙였는데 두 번째 사람이 **소품으로 강등**되는 정반대 지시가
    # 나간다 — 가장 흔한 표현에서 가장 큰 오작동이다.
    _multi_fallback = False
    if (not wanted and len(labels) >= 2 and _is_multi_person_request(topic)
            and int(labels[1]) not in appearance_ref_slots(topic, labels)
            and int(labels[1]) not in objects
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


def auto_reference_roles_positive(kinds, image_labels=None) -> str:
    """자동 분류된 역할을 positive 문장으로. 토픽이 슬롯을 지목했으면 호출하지 않는다.

    왜(Why) 조건문인가: 픽셀만으로 옷과 사물을 가를 수 없다(실측). '아이템'은
    단색 배경 위 물건이라는 뜻이므로, 입을지 놓을지는 모델이 이미지를 보고
    정하게 한다. 대신 **단색 배경**만 아이템으로 인정해, 포즈 참조의 옷이
    딸려 오던 예전 회귀(2026-09-28)와는 경로가 겹치지 않는다.
    """
    if not kinds:
        return ""
    try:
        labels = [int(l) for l in (image_labels or sorted(kinds))]
    except (TypeError, ValueError):
        return ""
    persons = [l for l in labels if kinds.get(l) == "person"]
    main = persons[0] if persons else None
    parts = []
    for l in labels:
        r = kinds.get(l)
        if r == "outfit" and main:
            parts.append(
                f"dress the person from reference image {main} in the garment "
                f"shown in reference image {l}, keeping its exact colour, cut, "
                "material and pattern; the garment must be worn on the body, "
                "not held or placed beside it")
        elif r == "outfit":
            parts.append(
                f"use the garment in reference image {l} exactly as shown, "
                "keeping its colour, cut, material and pattern")
        elif r == "object":
            parts.append(
                f"include the object from reference image {l} with its exact "
                "silhouette, material and colour, placed naturally in the scene")
        elif r == "item" and main:
            parts.append(
                f"reference image {l} is an isolated item: if it is a garment, "
                f"put it on the person from reference image {main} with its exact "
                "colour, cut and material; if it is an object or product, keep "
                "its exact shape, material and colour and place it in the scene")
        elif r == "item":
            parts.append(
                f"reference image {l} is an isolated item: keep its exact shape, "
                "material and colour")
        elif r == "background":
            parts.append(
                f"use the environment of reference image {l} as the background, "
                "with its lighting and colour palette; do not include its people "
                "or foreground objects as the subject")
        elif r == "style":
            parts.append(
                f"borrow only the mood, colour palette and lighting of "
                f"reference image {l}")
    return ". ".join(parts)


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
    # 사람도 동물도 아닌 주제(풍경·사물·제품)이면서 참조에 사람이 하나도 없으면
    # 사람 신원 조항을 내지 않는다. 왜(Why) 위의 유령 인물 실측과 같은 이유다:
    # 사람이 없는 참조에 "same facial structure, same hairstyle, same exact
    # outfit" 을 내보내면 모델이 그 사물에서 사람을 만들어낸다. 실측 — 토픽
    # "나무 의자 제품 샷" + 단색 배경 참조 1장에서 사물 보존 문장("is an
    # isolated item") 과 사람 신원 조항이 한 프롬프트에 나란히 붙어 모순됐다.
    #
    # 참조 분류가 object/item 이든 **unknown 이든** 똑같이 적용한다 (2026-10-30
    # 감사 F1). unknown 은 "사람이 있다" 가 아니라 "모른다" 이고, 기본 경로
    # (automation=규칙 + vision 없음)의 참조 1장은 늘 unknown 또는 item 이다 —
    # 종전 조건은 object/item 만 봐서 unknown 인 참조에서 사람 조항이 새어
    # 나갔다 (실측: 노이즈 참조 1장 + "a red sports car parked on the street").
    # 사람이 검출된 참조(_hint_person_slots 가 비어 있지 않음)나 사람·동물 주제는
    # 그대로 둔다. 빈 topic 은 제외한다 — 설명이 없는 사람 사진일 수 있어 종전
    # 동작(사람 조항 유지, R82)을 보존한다. 의상 교체를 요청하는 topic 도
    # 제외한다 — 옷을 갈아입는 대상은 사람이므로 얼굴·체형 유지를 남겨야 한다
    # (R82 "교체해도 얼굴 유지는 남김"). 그리고 분류가 **아예 돌지 않은** 직접
    # 호출은 건드리지 않는다(`_hint_no_person_classified` 가 False).
    _non_human_topic = (bool((topic or "").strip())
                        and not _is_human_subject(topic or "")
                        and not _is_animal_subject(topic or ""))
    if (_non_human_topic
            and not _hint_person_slots()
            and not _is_text_outfit_change(topic or "")
            and _hint_no_person_classified()):
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
                "same facial structure, same hairstyle, same exact outfit including every garment, "
                "same exact shoes, same exact accessories and jewelry, "
                "same body proportions, same overall color identity. "
                + GARMENT_RETENTION_POSITIVE + " "
                "Do not change, replace, or alter any clothing, shoe, or accessory "
                "unless the user explicitly requests a clothing change.")
    duo = build_duo_person_anchor(image_count, topic, image_labels=image_labels)
    if duo:
        # 두 번째 reference가 인물 역할이면 복제 금지 대신 두 정체성 보존을 둔다.
        # 사물 명시 슬롯의 소품 방어는 duo 앵커가 함께 전달한다.
        return duo
    secondary = _secondary_role_labels(labels, main=plan["main"],
                                       persons=plan["persons"],
                                       poses=plan["poses"],
                                       clothing=plan["outfits"],
                                       appearance=appearance_ref_slots(topic, labels))
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
        f"{NO_DUPLICATE_MAIN}, {SECONDARY_REF_NO_DUPLICATE}, {NO_DUPLICATE_TAIL}"
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
                                       clothing=plan["outfits"],
                                       appearance=appearance_ref_slots(topic, labels))
    head = f"Use reference image {plan['main']} as the only main subject, "
    if secondary:
        head += ("use reference image(s) " + ", ".join(secondary)
                 + " only for explicitly requested roles "
                 "such as background, outfit, prop, product, style, lighting, "
                 "composition, or mood, ")
    return head + "do not duplicate the main subject."
