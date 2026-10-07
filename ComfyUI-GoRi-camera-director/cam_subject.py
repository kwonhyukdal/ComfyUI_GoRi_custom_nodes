# -*- coding: utf-8 -*-
"""주제 분류(사람/동물/다인/반사/복장/포즈)와 슬롯 역할 판정."""

from __future__ import annotations

import re

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403


__all__ = [
"HUMAN_SUBJECT_KEYWORDS", "_MODEL_OBJECT_PATTERN", "_is_human_subject", "ANIMAL_SUBJECT_KEYWORDS", "ANIMAL_SPECIES_POSITIVE", "ANIMAL_ANATOMY_NEGATIVE", "_KO_SUFFIX_CHARS", "_ascii_only", "_ko_word_present", "_ASCII_AMBIGUOUS", "_ascii_word_present", "_is_animal_subject", "MULTI_PERSON_KEYWORDS", "REFLECTION_KEYWORDS", "_REFLECTION_ASCII_WORDS", "_is_reflection_scene", "_is_multi_person_request", "SECOND_PERSON_PATTERNS", "_NUMBER_WORDS", "_ORDINAL_WORDS", "_KO_OBJECT_WORDS", "_EN_OBJECT_WORDS", "OBJECT_WORDS", "_TEMPERED_GAP", "_KO_CLOTHING_WORDS", "_EN_CLOTHING_WORDS", "CLOTHING_WORDS", "_role_patterns", "OBJECT_ROLE_PATTERNS", "CLOTHING_ROLE_PATTERNS", "_OUTFIT_VERB", "_OUTFIT_APPLY_SLOT_PATTERNS", "_OUTFIT_TARGET_ROLE", "OUTFIT_TARGET_PATTERNS", "_KO_POSE_STATE", "_EN_POSE_STATE", "_KO_POSE_WORDS", "_EN_POSE_WORDS", "POSE_ROLE_PATTERNS", "_collect_role_slots", "_clothing_role_slots", "_clothing_source_slots", "_has_outfit_apply_verb", "_EN_GARMENT_WORDS", "_is_text_outfit_change", "_is_empty_scene", "_outfit_target_slots", "_pose_role_slots", "_second_person_slots", "_is_second_person_request", "_secondary_role_labels", "_object_role_slots", "_person_object_plan", "_is_multi_person_sheet", "_is_character_sheet_request", "CHARACTER_SHEET_TOPICS", "MULTI_PERSON_SHEET_TOPICS", "_reference_items", "_is_outfit_transfer", "OUTFIT_RELATION_PATTERNS", "NON_OBJECT_SLOT_KEYWORDS"
]


OUTFIT_RELATION_PATTERNS = (
    # English: clothing/outfit explicitly comes from a reference image.
    r"\b(?:outfit|clothing|wardrobe|dress|shirt|coat|apparel|garment)\b.{0,24}\b(?:from|reference|using|with)\s+(?:reference\s+)?(?:image|img)\s*_?\d+",
    r"\b(?:image|img)\s*_?\d+\b.{0,24}\b(?:is|as|contains|shows)\s+(?:the\s+)?(?:outfit|clothing|wardrobe|dress|shirt|coat|apparel|garment)\b",
    # Korean: 이미지 N의 의상/옷을 입히거나/바꾸는 명시적 의도.
    r"(?:image|img|이미지)\s*_?\d+\s*(?:의|에|에서)?\s*(?:의상|옷|패션|드레스|셔츠|블라우스|바지|원피스|코트|아우터|재킷|자켓|슈트|정장|한복|웨딩드레스|구두|신발)",
    r"(?:의상|옷|패션|드레스|셔츠|블라우스|바지|원피스|코트|아우터|재킷|자켓|슈트|정장|한복|웨딩드레스|구두|신발).{0,24}(?:image|img|이미지)\s*_?\d+",
    r"(?:입히|입게|바꾸|사용|적용|참고).{0,28}(?:의상|옷|드레스|패션|(?:image|img|이미지)\s*_?\d+)",
)


def _is_outfit_transfer(text: str) -> bool:
    """단순히 'dress/옷'이 있는 scenes가 아니라, image_N을 의상 참고로 쓰라는 의도만 판별한다."""
    t = (text or "").lower()
    has_ref = bool(re.search(r"\b(?:image|img)\s*_?\d+", t)
                   or re.search(r"이미지\s*_?\d+", t))
    has_slot = bool(_clothing_role_slots(t) or _outfit_target_slots(t))
    if not (has_ref or has_slot):
        return False
    if any(re.search(pattern, t) for pattern in OUTFIT_RELATION_PATTERNS):
        return True
    # 슬롯 번호 + 의상 어휘 + 교체 동사가 함께 있으면 의상 참고 의도다.
    return bool(_clothing_role_slots(t)) and bool(_outfit_target_slots(t))


def _reference_items(image_items=None, image_list=None, image=None):
    """연결된 reference 이미지를 (원래 image_N 번호, 이미지) 목록으로 정규화한다."""
    items = []

    def add(raw, fallback_index):
        if raw is None:
            return
        if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], int):
            items.append((raw[0], raw[1]))
        else:
            items.append((fallback_index, raw))

    if image_items:
        for idx, raw in enumerate(list(image_items), start=1):
            add(raw, idx)
    elif image_list:
        for idx, raw in enumerate(list(image_list), start=1):
            add(raw, idx)
    if image is not None and not items:
        add(image, 1)
    return items


# 인물 주제 판정 어휘. 왜(Why): 실측에서 "1번 캐릭터를 앉힌다"가 인물로
# 잡히지 않아 해부·발란스·디테일 경계 가드가 **전부** 조용히 미작동했다.
# "캐릭터"는 한국어 촬영 씬에서 가장 흔한 인물 지칭인데 빠져 있었다.
# ("인물 " 앞의 공백은 " 인물"이 접두어로 걸리는 것을 막기 위한 잔재 — 정리)
# "model"은 단독으로 넣지 않는다 — "3D model of a car" 같은 사물 모형까지
# 사람으로 잡힌다. 사람이 쓰는 경우만 "fashion model"로 좁힌다. (기존에도
# 단독이 아니라 "fashion model"만 넣었으나, 실측 테스트가 "3D model" 검사를
# 걸도록 이 형태를 유지한다. 아래에서 "model"을 빼면 그 테스트가 깨진다.)
HUMAN_SUBJECT_KEYWORDS = (
    "woman", "women", "female", "girl", "lady", "human", "person", "people",
    "man", "men", "male", "boy", "actor", "actress",
    "fashion model", "portrait", "character", "characters",
    "캐릭터", "인물", "여성", "남성", "여자", "남자", "사람", "아이",
    "소년", "소녀", "남아", "여아", "주인공", "인물체", "모델", "아이돌",
)


# "3D model of a car"처럼 사물 모형을 가리키는 표기. 왜(Why): 영어 "model"
# 단독 키워드가 사물 모형 장면까지 사람 장면으로 오판해 identity 가드를
# 잘못 붙였기 때문이다. 모형 표기가 있으면 모델류 키워드는 무시하고
# 명확한 인물 키워드만 본다.
_MODEL_OBJECT_PATTERN = re.compile(r"(?:3d|3-d|3차원|scale)\s*(?:model|모델)")


def _is_human_subject(text: str) -> bool:
    t = (text or "").lower()
    # **의상 교체** 표현은 사람을 함의한다(2026-09-29 실측 결함 수정).
    # "1 의상, 2 교체" 에는 인물 키워드가 하나도 없어서 이 함수가 False 였다.
    # 결과적으로 identity 앵커·해부·발란스 등 **인물 가드가 전부 조용히
    # 미작동**했다(프롬프트에 사람이 없으니 의도한 것도 아니고). 옷을 입는다는
    # 것은 결국 그 옷을 입을 사람이 있다는 뜻이므로 사람으로 친다.
    # 단, **동물/인물 키워드가 명시됐으면 그쪽이 우선**이다
    # (혼재 장면에서 "강아지" 가 있는데 사람 가드까지 붙으면 오탐).
    if _is_outfit_transfer(t):
        # 왜(Why) 한국어 키워드도 경계 판정인가 (2026-10-05 감사): raw `in`
        # 이면 "양옆" 이 "양", "소파" 가 "소", "말풍선" 이 "말" 로 잡혀
        # 동물 우선 분기가 발화해 **인물 가드가 통째로 사라진다**. 문서화된
        # 실측 오탐(2026-09-28)을 이 형제 함수가 그대로 달고 있었다.
        for animal in ANIMAL_SUBJECT_KEYWORDS:
            if _ascii_only(animal):
                if animal in t:
                    return False
            elif _ko_word_present(t, animal):
                return False
        return True
    if _MODEL_OBJECT_PATTERN.search(t):
        keywords = tuple(k for k in HUMAN_SUBJECT_KEYWORDS
                         if k not in ("fashion model", "모델"))
        # 왜(Why) 모호 영문도 경계 판정인가 (2026-10-05 감사 3회 차): raw
        # `in` 이면 "romantic" 안의 "man" 이 잡혀 3D 모델·제품 샷에 인물
        # 가드가 붙는다 — 아래 주 루프의 _ASCII_AMBIGUOUS 처리와 동일하게
        # 맞춘다. 이 분기의 취지("명확한 인물 키워드만 본다")와도 일치.
        return any(_ascii_word_present(t, k) if k in _ASCII_AMBIGUOUS
                   else (k in t if _ascii_only(k)
                         else _ko_word_present(t, k))
                   for k in keywords)
    for keyword in HUMAN_SUBJECT_KEYWORDS:
        if keyword in _ASCII_AMBIGUOUS:
            # 원자(holder) 후보: 단어 경계가 없으면 오탐
            if _ascii_word_present(t, keyword):
                return True
        elif _ascii_only(keyword):
            # 영문은 종전대로 부분 일치. 왜(Why) \b 로 바꾸지 않나:
            # "girlfriend" 안의 "girl" 처럼 합성어가 사람 장면인 경우가
            # 있어 단어 경계로 좁히면 오히려 가드가 사라진다.
            if keyword in t:
                return True
        else:
            # 한국어는 _is_animal_subject 와 같은 경계 판정을 쓴다.
            # raw `in` 이면 "아이스크림/아이패드" 가 "아이" 로 잡혀
            # 제품 샷에 인물 가드가 전부 붙었다. "아이돌" 은 원래 "아이"
            # 부분 일치에 우연히 걸리던 것을 경계 판정 도입과 함께
            # 명시 키워드로 유지한다.
            if _ko_word_present(t, keyword):
                return True
    return False


# 동물 주제 판별. 왜(Why): 인물 키워드만 있어서 "강아지" 주제는 어떤 가드에도
# 걸리지 않았다. 인체 가드는 그대로 미적용(오탐 없음)하지만 동물 해부·종 보존
# 가드가 전혀 없으니 개가 사람 손을 갖거나 품종 초상화로 변하는 실패를 못 막는다.
ANIMAL_SUBJECT_KEYWORDS = (
    "cat", "kitten", "dog", "puppy", "horse", "bird", "parrot", "owl",
    "rabbit", "bunny", "squirrel", "fox", "deer", "cow", "cattle", "sheep",
    "goat", "pig", "bear", "wolf", "tiger", "lion", "leopard", "elephant",
    "monkey", "panda", "penguin", "eagle", "duck", "swan", "seagull",
    "snake", "turtle", "frog", "fish", "shark", "whale", "dolphin",
    "hamster", "guinea pig", "ferret", "chameleon", "gecko", "parrotlet",
    "고양이", "강아지", "애완동물", "반려동물", "동물", "말", "새", "앵무새",
    "독수리", "앵무", "토끼", "다람쥐", "여우", "사슴", "소", "양", "염소",
    "돼지", "곰", "호랑이", "사자", "원숭이", "판다", "펭귄", "오리", "백조",
    "거북이", "뱀", "개구리", "물고기", "고래", "돌고래", "햄스터",
)


ANIMAL_SPECIES_POSITIVE = (
    "one clearly identifiable animal species, accurate species proportions "
    "(leg count, limb structure, muzzle, tail, ears), full animal body "
    "anatomy, natural fur or feather texture, real animal proportions"
)


ANIMAL_ANATOMY_NEGATIVE = (
    "humanized animal, human hands on an animal, human face on an animal body, "
    "mutated animal anatomy, extra legs, missing legs, deformed paws, "
    "fused limbs, wrong species, part human part animal, "
    "cartoon caricature, exaggerated breed caricature, plastic toy animal, "
    "stuffed animal, taxidermy mount, mascot costume"
)


# 한국어 명사 뒤에 붙는 조사·수량사 어미들만 "그 단어를 썼다"로 인정한다.
# 왜(Why) 이 목록이 필요한가: 한국어는 어절이 공백으로 분리되지 않아
# `keyword in text` 로는 "소파/태양/양옆" 이 "소/양" 으로 잡힌다(2026-09-28 실측).
# 사람이 있는 장면이 동물로 분류되면 인체 가드가 전부 사라진다.
_KO_SUFFIX_CHARS = (
    "가"          # 주격
    "이가을를"    # 목적격/보조격
    "은는"        # 보조사
    "과와"        # 조화
    "의"          # 관형
    "에"          # 방향
    "에서"        # 출발
    "로"          # 방향
    "만"          # 제한
    "도"          # 주제
    "까지"        # 한계
    "부터"        # 기점
    "에게"        # 간접목적
    "한테"        # 간접목적
    "그"          # 관형
    "것"          # 명사화
    "들"          # 복수
    "한"          # 수량
    "두세"        # 수량
    "마리"        # 가축 계수
    "짝"          # 짝
    "층"          # 층
)


def _ascii_only(word: str) -> bool:
    """영문 단어인지 (한글 어휘는 조사 규칙이 다르다)."""
    return all(ord(c) < 128 for c in word)


def _ko_word_present(text: str, word: str) -> bool:
    """한국어 단어가 독립형으로 쓰였는지 판정한다.

    **앞뒤 양쪽**을 본다. 한쪽만 보면 접합을 못 잡는다(2026-09-28 실측):
      - 뒤만 보면: "소파" 의 "소" 를 통과("파" 가 조사 아님 → 이건 OK),
        "고양이" 의 "양" 이 "이"(조사) 때문에 통과 → **오탐**
      - 앞만 보면: "태양" 의 "양"(앞이 "태") → **오탐**
    규칙: 앞 글자는 한글이면 거부(접합), 뒤 글자는 조사/수량사면 인정.
    어휘 목록에 "고양이"/"강아지" 같은 결합형이 이미 들어 있으므로
    정작 그 단어는 앞 글자가 공백이라 정상 통과한다.
    """
    start = 0
    while True:
        i = text.find(word, start)
        if i < 0:
            return False
        if i > 0 and "가" <= text[i - 1] <= "힣":
            start = i + 1          # 앞이 한글 = 앞 단어의 일부
            continue
        nxt = text[i + len(word): i + len(word) + 1]
        if nxt == "" or not ("가" <= nxt <= "힣"):
            return True
        if nxt in _KO_SUFFIX_CHARS:
            return True
        if nxt == "까" and text[i + len(word):i + len(word) + 2] == "까지":
            return True
        if nxt == "부" and text[i + len(word):i + len(word) + 2] == "부터":
            return True
        start = i + 1


# 영문 어휘는 단어 경계로만 매칭한다. 왜(Why): `man` 이 "romantic/german/
# manicured" 안에서, `cat` 이 "catalogue", `bear` 가 "bearable" 안에서 잡혔다
# (2026-09-28 실측). 풍경·사물 주제가 인물/동물로 분류되면 인물 가드가 붙거나
# 인체 가드가 빠진다. 2026-10-07 감사 실측: `lady` 가 "ladybug", `boy` 가
# "boycott" 안에서 잡혀 무당벌레 장면에 인체 가드가 붙었다. 같은 날
# `person` 이 "personal belongings", `character` 가 "characteristic" 에서도
# 잡혀 사물 장면에 인간 가드+음성 텍스트가 붙었다 — 단어 경계로 함께 막는다.
# 단수/복수 모두 커버하려고 characters 를 별도 키워드로도 넣었다
# (\bcharacter\b 는 "characters" 를 못 잡는다).
_ASCII_AMBIGUOUS = frozenset({
    "man", "men", "woman", "women", "cat", "bear", "pig", "dog", "hen", "ewe",
    "goat", "rat", "ram", "ape", "fox", "elk", "gnu", "imp", "kid", "nut",
    "pet", "cod", "boa", "carp", "sole", "hart", "crane", "newt", "toad",
    "lady", "boy", "person", "character", "characters",
})


def _ascii_word_present(text: str, word: str) -> bool:
    """영문 단어를 단어 경계로만 찾는다 (\b 매칭)."""
    import re as _re
    return bool(_re.search(r"\b" + _re.escape(word) + r"\b", text))


def _is_animal_subject(text: str) -> bool:
    """동물 주제면 True. 인물 키워드가 명시되면 사람 우선(장면 혼재 대응)."""
    t = (text or "").lower()
    if not t:
        return False
    if _is_human_subject(t):
        return False
    for keyword in ANIMAL_SUBJECT_KEYWORDS:
        if _ascii_only(keyword):
            if _ascii_word_present(t, keyword):
                return True
        elif _ko_word_present(t, keyword):
            return True
    return False


MULTI_PERSON_KEYWORDS = (
    "two people", "two persons", "two men", "two women",
    "woman and man", "man and woman", "pair of people",
    "each other", "facing each other", "face each other",
    "both people", "both persons", "both of them",
    "group of", "family", "couple",
    "두 명", "두사람", "두 사람", "2명", "서로", "마주",
    "여성과 남성", "남성과 여성", "여러 명", "가족", "커플", "인물 두", "그룹",
)


# "glass"는 단어 경계로만 매칭한다 — "sunglasses"/"glasses" 안에서
# 잡혔다(2026-10-07 감사 실측). "유리"는 뺐다 — "유리잔"/"유리컵" 같은
# 물건 장면에서 반사 장면으로 오판해 단일 인물 앵커가 억제됐다. "유리창"은
# 그대로 둔다.
REFLECTION_KEYWORDS = (
    "reflection", "reflected", "mirror", "mirrored", "window",
    "유리창", "거울", "반사", "비친", "창문",
)


_REFLECTION_ASCII_WORDS = ("glass",)


def _is_reflection_scene(text: str) -> bool:
    t = (text or "").lower()
    if any(_ascii_word_present(t, word)
           for word in _REFLECTION_ASCII_WORDS):
        return True
    return any(keyword in t for keyword in REFLECTION_KEYWORDS)


def _is_multi_person_request(text: str) -> bool:
    t = (text or "").lower()
    return any(keyword in t for keyword in MULTI_PERSON_KEYWORDS)


SECOND_PERSON_PATTERNS = (
    # image/이미지 표기 혼용 대응: "Image 3의 남성" 같은 한영 혼합도 잡는다.
    # 주의: 한글 조사(의/에)는 \w 취급이라 2\b 경계가 안 맞으므로 (?![0-9])를 쓴다.
    # 2번 고정이 아니라 2~10번 슬롯을 캡처한다.
    # 비탐욕 창 + 절 차단: 창이 쉼표/식별자를 넘어 다음 슬롯의 단어를 잘못 잡거나
    # (이미지 2번 핸드백, 이미지 3번 남성 → 3번 누락/2번 오검출)
    # finditer의 비중복 소비 때문에 건너뛰는 후보가 생기는 것을 동시에 막는다.
    r"\b(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])[^,，.。;；!！?？\n]{0,40}?\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b",
    r"\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b[^,，.。;；!！?？\n]{0,40}?\b(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])",
    r"(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])[^,，.。;；!！?？\n]{0,20}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)",
    r"(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)[^,，.。;；!！?？\n]{0,20}?(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])",
    r"두\s*번째\s*(?:사람|남자|남성|여자|여성|인물)",
    r"second\s+(?:person|man|woman|male|female)",
    # 번호 선행형: "2번 이미지의 남성이" — 위 4개 패턴은 모두 이미지 표기가
    # 앞에 오는 구문만 커버한다. 자연스러운 "N번 이미지" 표현을 놓치면
    # 두 번째 인물이 보조 역할(배경/소품)로 오분류된다.
    r"([2-9]|10)\s*(?:번|번째)\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*[^,，.。;；!！?？\n]{0,20}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)",
    r"([2-9]|10)\s*(?:번|번째)\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b",
    # 번호 **나열**형: "1번과 2번 인물이", "2번·3번", "image 1 and image 2".
    # 위 패턴들은 "2번 이미지의 남성이"처럼 **한 슬롯만 지칭**하는 구문만
    # 잡는다. 두 슬롯을 함께 나열하는 최상위 표현("1번과 2번 인물이 함께")이
    # 잡히지 않아 duo 앵커가 빈 문자열로 빠지고, 그 결과 두 번째 참조가
    # "소품/배경 역할"로 강등됐다(2026-09-28 실측). 캡처 그룹 2개를 모두 수집.
    # 왜(Why) 첫 번호도 캡처하는가 (2026-10-05 감사 2회 차): 예전엔 첫 번호가
    # (?:...) 비캡처라 "2번과 3번 인물이" 에서 3번만 잡히고 **2번이 소실**했다
    # — 2번은 다른 패턴으로도 못 잡는다(이미지 표기 없음). 2번이 persons 에
    # 없으면 보조 역할(배경/신원 억제)로 강등되고 duo 앵커가 2번을 빼고
    # 인용한다. 주석은 "2개를 모두 수집" 이라 써 두고 코드는 한 개만
    # 수집하는 주석-코드 불일치였다.
    r"([1-9]|10)\s*(?:번|번째)\s*(?:와|과|및|그리고|·|,|、|\+)\s*([2-9]|10)\s*(?:번|번째)?[^,，.。;；!！?？\n]{0,16}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람|커플|쌍)",
    r"\b(?:image|img)\s*_?\s*([1-9]|10)\s*(?:and|&|,)\s*(?:image|img)?\s*_?\s*([2-9]|10)\b[^,，.。;；!！?？\n]{0,24}?\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person|people|couple)\b",
)


_NUMBER_WORDS = {2: "Two", 3: "Three", 4: "Four", 5: "Five",
                 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


_ORDINAL_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                  6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


# 사물/소품 역할 어휘. 의상 계열(옷·의상·원피스 등)은 일부러 넣지 않았다 --
# 의상 참조에는 전용 가드(OUTFIT_GUARD·OUTFIT_RELATION_PATTERNS)가 있어
# 이 분류기가 겹치면 의상 슬롯이 "소품"으로 오인될 수 있다.
# 모호한 짧은 단어(검·총·잔·병)는 뺐다 -- 왜(Why): "검은 머리"의 검은이
# 검(sword)으로 오판되는 오검출이 실측 확인됐다(정밀 검토 발견 #4).
_KO_OBJECT_WORDS = (
    "가방|핸드백|백팩|에코백|숄더백|클러치백|손목시계|시계|목걸이|반지|귀걸이"
    "|안경|선글라스|모자|벨트|스카프|목도리|장갑|우산|책|컵"
    "|방패|꽃다발|소품|오브젝트|제품|물건|구급상자|마네킹"
)


_EN_OBJECT_WORDS = (
    "bag|handbag|backpack|purse|watch|wristwatch|necklace|ring|earrings"
    "|glasses|sunglasses|hat|cap|belt|scarf|gloves|umbrella|book"
    "|prop|object|product"
)


OBJECT_WORDS = _KO_OBJECT_WORDS + "|" + _EN_OBJECT_WORDS


# 어휘가 앞 → 슬롯이 뒤인 순서의 창 차단. 사람 단어가 창 안에 있으면 그 슬롯은
# 사람 절에 속한다 -- 왜(Why): "원피스로 갈아입은 여성과 이미지 3"에서 원피스가
# 3번(남성)을 옷 슬롯으로 침범하는 오검출이 실측 확인됐다(정밀 검토 R23).
_TEMPERED_GAP = (r"(?:(?!남성|남자|여성|여자|인물|사람"
                 r"|man|woman|male|female|person)[^,，.。;；!！?？\n]){0,24}?")


# 의상 역할 어휘 + 슬롯 검출. 왜(Why): outfit 게이트가 "의상 의도 = 모든 duo 소멸"
# (구버전)이 아니라 "의상 슬롯만 제외"로 작동하려면 슬롯 번호를 잡아야 한다
# (정밀 검토 발견 #3).
_KO_CLOTHING_WORDS = (
    "의상|옷|옷차림|의장|생활복|패션|드레스|셔츠|블라우스|바지|원피스"
    "|코트|아우터|재킷|자켓|슈트|정장|한복|웨딩드레스|구두|신발"
)


_EN_CLOTHING_WORDS = "outfit|clothing|wardrobe|dress|shirt|coat|garment|apparel"


CLOTHING_WORDS = _KO_CLOTHING_WORDS + "|" + _EN_CLOTHING_WORDS


def _role_patterns(words: str, en_words: str):
    """역할(사물/의상) 슬롯 검출 4패턴 골격. 단어만 주입한다.

    왜(Why): 사물·의상 패턴은 절 차단 규칙이 동일하다. 형태:
    1) "이미지 2의 핸드백" (조사 혼용 대응)
    2) "핸드백 이미지 3" — 문장부호 차단(쉼표 너머 오인 방지) + 사람 단어
       차단(창 안 사람 단어가 있으면 그 슬롯은 사람 절 소속)
    3) 영문 "bag as image 2"형, 4) 영문 "image 3 shows a book"형.
    """
    return (
        r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])\s*(?:번)?\s*(?:의|에|에서)?\s*(?:" + words + r")",
        r"(?:" + words + r")" + _TEMPERED_GAP + r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])",
        r"\b(?:" + en_words + r")\b" + _TEMPERED_GAP + r"\b(?:from|in|on|as|using|reference)\s+(?:reference\s+)?(?:image|img)\s*_?\s*(\d+)(?![0-9])",
        r"\b(?:image|img)\s*_?\s*(\d+)(?![0-9])\b" + _TEMPERED_GAP + r"\b(?:is|as|shows|contains)\s+(?:a|an|the)?\s*(?:" + en_words + r")\b",
    )


OBJECT_ROLE_PATTERNS = _role_patterns(OBJECT_WORDS, _EN_OBJECT_WORDS)


# 슬롯 번호 + 의상 표현(2026-09-29 추가). 왜(Why): 기존 4패턴은
# "이미지 2의 의상"(라벨 필수)만 잡았다. 사용자가 "2 의상, 1 교체" 처럼
# **숫자만** 쓰면 아무것도 안 잡혔다(전수 확인: 6개 표현 전부 미인식).
# 포즈 슬롯과 같은 취지로 자연스러운 표현을 받아들인다.
#
# 제외 조건: 의상 어휘 뒤에 **착용 동사**가 바로 붙으면 그 슬롯은 의상 소스가
# 아니라 **인물**이다("2번 드레스를 입은 여성" -> 2번은 사람). 의상 소스로
# 잡으면 그 사람이 신원 소스에서 제외돼 사람이 사라진다(2026-09-29 실측 위험).
# 주의(Why): 동사는 어휘에서 **직접** 붙어야 한다. "을/ 를" 까지 보면
# "2번 의장을 1번에 입혀"(= 의상 소스 2번 + 대상 1번)까지 삼켜서 놓친다.
CLOTHING_ROLE_PATTERNS = _role_patterns(CLOTHING_WORDS, _EN_CLOTHING_WORDS) + (
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|에|에서|으로)?\s*(?:" + CLOTHING_WORDS
    + r")(?!\s*(?:을|를|이|가)?\s*(?:입은|입고|입혀|입히|착용|신은|신고))"
      r"(?![^,，]{0,4}(?:wearing|wears|dressed)\b)",
    # 역순: "1번에 2번 의장을 입혀" — 의상 소스 뒤에 **대상** 슬롯이 온다.
    r"(?:\d{1,2}\s*(?:번|번째)?\s*(?:에|에게|한테|의|은|는)\s*)"
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|으로)?\s*(?:" + CLOTHING_WORDS + r")",
)


# **교체 대상** 슬롯 — 의상 소스가 아니라 "이 슬롯에 입히라" 는 뜻.
# 왜(Why) 별도로 둔다(2026-09-29): "2 의상, 1 교체" 에서 1번을 의상 슬롯으로 잡으면
# 1번(주인물)이 신원 소스에서 제외된다 -> 사람이 사라진다. 캡처 그룹을 만든 채로
# "제외 패턴"을 넣으면 **반대로** 슬롯이 추가되므로 빼기 전용으로 분리해야 한다.
# 동사는 슬롯 **앞**(1번에 입혀)이나 **뒤**(1번 교체) 양쪽에 올 수 있다.
# 주의(Why): 접미에 \\b 를 붙이면 안 된다 — 파이썬이 백스페이스(\x08)로
# 해석해 정규식이 깨진다(실측: 한국어 동사 매칭이 전부 실패했다).
_OUTFIT_VERB = (r"(?:교체|바꿔|바꾼|바꾸|바꿜|갈아입|갈아입혀|입혀|입히|입게|적용"
                r"|변경|변하게|옮겨|wear|swap|replace|change|apply)")


# "의상 + 을/를 + 대상 슬롯" — 대상은 소스가 아니다.
# 골격 패턴 2번(의상 → 이미지 N)이 여기서 1번을 의상 소스로 오염시킨다(2026-09-29 실측).
# 주의(Why) 여기서는 "이미지 N(을) V" 형태만 뺀다. 라벨+V 형태를 넣으면
# "이미지 2 의상" 의 **2번(진짜 소스)** 까지 잡혀 소스가 사라진다(실측).
_OUTFIT_APPLY_SLOT_PATTERNS = (
    r"(?:" + CLOTHING_WORDS + r")\s*(?:을|를)?\s*(?:은|는)?\s*"
    r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])",
)


# 슬롯과 조사 사이에 역할명사가 끼는 형태: "1번 인물에게 입히고".
# 실제로는 아주 흔하다(사람을 지칭해야 "입히라" 가 성립하므로).
_OUTFIT_TARGET_ROLE = r"(?:인물|사람|여자|남자|여성|남성|모델|얼굴|신원|여학생|남학생)?"


OUTFIT_TARGET_PATTERNS = (
    # 동사가 슬롯 뒤: "1 교체", "2번 적용"
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는)?\s*(?:에|로|한테)?\s*" + _OUTFIT_VERB + r"(?![0-9])",
    # 동사가 슬롯 앞: "1번에 입혀", "1번 인물에게 입히고"
    r"(\d{1,2})\s*(?:번|번째)?\s*" + _OUTFIT_TARGET_ROLE
    + r"\s*(?:에게|한테|에|으로|로)\s*" + _OUTFIT_VERB,
    # 역순 + 동사까지: "1번에 2번 의장을 입혀" (2026-09-29 실측 결함).
    # 주의(Why): 슬롯과 동사 사이에 **자유 구간**을 두면 안 된다.
    # "2번 의장을 1번 인물에게 입히고" 에서 왼쪽 2번이 먼저 잡혀 소비되고
    # finditer 가 1번까지 못 간다(실측: 대상=[] 로 조용히 실패).
    r"(\d{1,2})\s*(?:번|번째)?\s*" + _OUTFIT_TARGET_ROLE
    + r"\s*(?:에게|한테|에|으로|로)\s*\d{1,2}\s*(?:번|번째)?\s*(?:의|은|는|을|를)?\s*"
    r"(?:" + CLOTHING_WORDS + r")[^,，]{0,14}?" + _OUTFIT_VERB,
)


# 포즈 참조 역할. 왜(Why): 사용자가 "2번 이미지의 포즈를 따라"라고 명시한 슬롯은
# 신원·의상·사물 소스가 아니라 **자세 전용**이다. DNA(=신원·외양)에서 포즈를
# 뺀 이유(의도와 무관한 포즈 고정)와 달리, 여기서는 사용자가 직접 지정했으므로
# 해당 슬롯만 자세 따라하기를 허용한다.
# **자세 표현 어휘**(슬롯 번호 뒤에 바로 오는 자연스러운 표현).
# 왜(Why) 넓혔나(2026-09-29 실측): 기존은 "이미지 2의 포즈" 처럼 **역할
# 명사**(포즈/자세/스탠스/몸매/동작)만 인식했다. 그래서 사용자가
# "2번은 포즈만", "2번 앉은 자세", "2 서 있는 모습" 처럼 **실제 자세를
# 묘사**하는 자연스러운 표현을 쓰면 아무것도 안 잡혔다(전부 미인식 실측).
# 사용자는 "2번" + 무엇을 할지 를 적는 게 자연스럽다. 그래서 자세 묘사
# 어휘까지 받아들인다.
_KO_POSE_STATE = (
    "앉|앉아|앉은|앉는|서있|서 있|선|선상태|서있는|서 있는|서서|누워|누운"
    "|눕는|쪼그|쪼갠|쪼고|무릎|엎드|일어서|숨을|움직임|움직이는|동작"
    "|자세|스탠스|몸매|모습|상태|형태|구도|각도|위치|손|팔|다리|발"
    "|허리|목|고개|뒤통수|엉덩이|골반|어깨"
)


_EN_POSE_STATE = (
    "pose|posture|stance|body ?position|position|angle|leaning|sitting|sit"
    "|standing|stand|kneeling|kneel|crouching|crouch|lying|lie|reaching"
    "|holding|arms?|hands?|legs?|bent|lean|smiling|looking|walking"
)


_KO_POSE_WORDS = ("포즈|자세|스탠스|몸매|동작|"
                   + _KO_POSE_STATE + "|" + _EN_POSE_STATE)


_EN_POSE_WORDS = "pose|posture|stance|body position"


POSE_ROLE_PATTERNS = _role_patterns(_KO_POSE_WORDS, _EN_POSE_WORDS) + (
    # "2번 이미지의 포즈" — 번호가 앞서는 한국어 구문. 기존 4패턴은
    # "이미지 2의 포즈"(뒤에 온다)만 커버해서 자연스러운 표현을 놓쳤다.
    # 슬롯 번호는 반드시 캡처 그룹이어야 한다(_collect_role_slots 계약).
    r"(\d{1,2})\s*(?:번|번째|번의)?\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*(?:" + _KO_POSE_WORDS + r")",
    # "3번과 7번 이미지의 포즈" — 접두·접미로 나열하면 앞 번호가 뒤 번호 창에
    # 밀려 잡히지 않았다. 나열 멤버마다 캡처 그룹을 두어 전부 수집한다.
    r"(\d{1,2})\s*(?:번|번째)\s*(?:와|과|and|,|，)\s*(\d{1,2})\s*(?:번|번째)?\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*(?:" + _KO_POSE_WORDS + r")",
    # 2026-09-29 추가: "2번은 포즈만" / "2번 포즈만" — 이미지 라벨 없이
    # 슬롯 번호 + 포즈 역할명사. 사용자가 가장 자주 쓰는 형태다.
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|에|에서)?\s*(?:"
      + _KO_POSE_WORDS
      + r")\s*(?:만|참고|기준|따라|따라가|그대로)?",
    # "2번은 앉은 자세" / "2 서 있는 모습" / "2번 손에 든 상태" —
    # 슬롯 번호 + **자세 묘사**(역할명사 없이 실제 자세를 적은 형태).
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|이|가|의)?\s*(?:"
      + _KO_POSE_STATE
      + r")",
)


def _collect_role_slots(text: str, patterns) -> set:
    """패턴 집합에서 번호(1~10) 수집. 사물·의상 슬롯 검출 공용 루프."""
    t = (text or "").lower()
    slots = set()
    for pattern in patterns:
        try:
            for m in re.finditer(pattern, t):
                # 캡처 그룹이 여러 개인 패턴(나열형)이 있으므로 전부 수집한다.
                # 기존 4패턴은 그룹이 하나뿐이라 동작이 달라지지 않는다.
                for grp in m.groups():
                    if not grp:
                        continue
                    try:
                        n = int(grp)
                    except ValueError:
                        continue
                    if 1 <= n <= 10:
                        slots.add(n)
        except (ValueError, re.error):
            continue
    return slots


def _clothing_role_slots(text: str) -> set:
    """의상 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): _second_person_slots의 outfit 게이트가 의상 슬롯만 정밀하게
    제외하도록 (구버전은 의상 의도만 있으면 모든 인물 번호를 지웠다).
    그리고 슬롯 N 교체를 쓰면 그 번호는 **교체 대상**이므로 의상 소스에서
    빼준다(OUTFIT_TARGET_PATTERNS).
    """
    # 소스를 한 번만 계산해 목표 판정에도 같은 값을 넘긴다(2026-10-07 라운드 2
    # — 원래는 _outfit_target_slots 안에서 같은 계산을 또 했다).
    src = _clothing_source_slots(text)
    targets = _outfit_target_slots(text, src)
    return src - targets if targets else src


def _clothing_source_slots(text: str) -> set:
    """의상 소스 슬롯(교체 대상 판정 전 원본)."""
    slots = _collect_role_slots(text, CLOTHING_ROLE_PATTERNS)
    # 구버전 결함 교정(2026-09-29 실측): 골격 패턴 2번은
    # "이미지 2 의상을 이미지 1에 적용" 에서 "의상을 이미지 1" 을 잡아
    # **1번(주인물)까지 의상 소스로** 밀어 넣었다. 의상 슬롯이 늘어나면
    # 1번이 신원 소스에서 제외돼 사람이 사라진다.
    if _has_outfit_apply_verb(text):
        slots -= _collect_role_slots(text, _OUTFIT_APPLY_SLOT_PATTERNS)
    return slots


def _has_outfit_apply_verb(text: str) -> bool:
    """의장 교체/적용 동사가 있는 문장인지(대상 슬롯 오염 교정용)."""
    t = (text or "").lower()
    return bool(re.search(_OUTFIT_VERB, t))


# 텍스트 단독 의상 교체의 영어 의류 어휘. 왜(Why) 슬롯 패턴과 분리하나:
# `_clothing_role_slots` 는 "이미지 N 의 옷" 처럼 슬롯 번호를 요구한다.
# 그런데 "red evening dress 로 교체" 처럼 **옷 자체를 지목**하는 경우는
# 슬롯이 없다. 슬롯을 요구하면 텍스트 단독 교체를 영영 못 잡는다.
_EN_GARMENT_WORDS = (
    r"outfit|clothing|clothes|dress|gown|sweater|skirt|shirt|blouse|"
    r"pants|trousers|jeans|jacket|coat|suit|uniform|wardrobe|garment|"
    r"apparel|top|bottoms|knit|denim"
)


def _is_text_outfit_change(text: str) -> bool:
    """의상 참조 이미지 없이 텍스트만으로 옷 교체를 명시했는가.

    왜(Why) 이 함수가 필요한가 (2026-10-02 실측): 카메라가 명시적 교체 요청에도
    "same outfit" 을 함께 내보냈다. 같은 프롬프트에 "red evening dress" 와
    "same outfit" 이 공존하자 모델은 참조 이미지를 보고 원본을 택했다.
    0.00(키퍼 미동작)에서도 같은 옷이 나와 키퍼 문제가 아님을 확인했다.

    왜(Why) 슬롯을 요구하지 않나: `_is_outfit_transfer` 는 "이미지 N 의 옷" 처럼
    슬롯 번호를 요구한다. "빨간 드레스로 갈아입혀" 처럼 옷 자체를 지목하면
    슬롯이 없어서 영영 못 잡는다. 이 함수는 슬롯 없이 옷 교체 의사만 본다.

    왜(Why) 명시 유지가 우선하나: "same outfit", "keep the outfit" 처럼 유지를
    명시하면 교체로 보지 않는다. 모순된 지시에서 유지를 택한 것은 모델이 아니라
    코드가 먼저 정리해야 한다 — 둘 다 내보내면 모델이 참조 이미지를 보고
    원본을 택한다(실측).
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # 명시 유지는 교체가 아니다 — 먼저 제외한다.
    if re.search(r"\b(?:same|keep|preserve|maintain)\b[^.]{0,24}?\b(?:outfit|clothing|clothes|dress)\b", low):
        return False
    if re.search(r"(?:같은|원래|기존)\s*(?:옷|의상|드레스|차림)", t):
        return False
    # 영어: 교체 동사 + 의류 ("replace A with B dress", "change into ...")
    # 왜(Why) 굴절형을 넣나: `\bwearing\b` 은 `\bwear\b` 에 안 걸린다.
    # "wearing a red dress" 처럼 현재진행형이 가장 흔한 교체 표현이다.
    if re.search(r"\b(?:replac(?:e[sd]?|ing)|chang(?:e[sd]?|ing)|"
                 r"swap(?:ped|ping)?|wear(?:ing|s)?|wore|worn|"
                 r"dress(?:ed)? in)\b", low) and re.search(
            r"\b(?:" + _EN_GARMENT_WORDS + r")\b", low):
        return True
    # 영어: 형용사 + 의류 ("different outfit", "new dress", "red evening dress"
    # 뒤에 교체 맥락이 있을 때 — 단독 "red dress" 는 묘사일 수 있다)
    if re.search(r"\b(?:different|new|another|completely different)\b[^.]{0,32}?\b(?:"
                 + _EN_GARMENT_WORDS + r")\b", low):
        return True
    # 한국어: 교체 동사 + 의류 (슬롯 불필요)
    if re.search(_OUTFIT_VERB, low) and re.search(
            r"(?:의상|옷|옷차림|드레스|셔츠|블라우스|바지|원피스|코트|재킷|자켓|슈트|정장|한복|"
            r"outfit|clothing|dress|clothes)", low):
        return True
    # 한국어: "다른 옷", "새 드레스" (명시 교체)
    if re.search(r"(?:다른|새|새로운|완전히 다른)\s*(?:옷|의상|드레스|차림|outfit|dress)", t):
        return True
    return False


def _is_empty_scene(text: str) -> bool:
    """참조에 사람이 없음을 명시했는가 (빈 배경·가구·풍경).

    왜(Why) 명시만 보나: 빈 문자열은 사람이 있을 수 있다 (설명 생략).
    "사람 없음" 이라고 써야 identity 문구를 뺀다. 오탐이면 신원 보존이
    꺼져서 더 나쁘다 — 누락은 기존 동작 그대로라 안전하다.
    """
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    # 영어: empty / no person / background only
    if re.search(r"\b(?:empty|vacant|unoccupied)\b[^.]{0,24}?\b(?:scene|bench|chair|bed|room|background)\b", low):
        return True
    if re.search(r"\bno\s+(?:person|one|people|human)\b", low):
        return True
    if re.search(r"\bbackground\s+only\b|\blandscape\s+only\b|\bstill\s+life\b", low):
        return True
    # 한국어: 빈 / 사람 없음 / 배경만
    if re.search(r"(?:빈|비어\s*있는)\s*(?:벤치|의자|침대|방|배경|풍경|장면)", t):
        return True
    if re.search(r"사람\s*(?:없|없음|없이)|아무도\s*없", t):
        return True
    if re.search(r"(?:배경|풍경)만", t):
        return True
    return False


def _outfit_target_slots(text: str, source_slots=None) -> set:
    """교체 대상 슬롯(1~10). 슬롯 N 교체 -> 그 슬롯이 의상 소스가 아니라
    이쪽에 입히는 대상이다.

    왜(Why) 따로 두나(2026-09-29): 이 슬롯을 의상 슬롯으로 잡으면 **주인물
    이미지가 신원 소스에서 제외**돼 사람이 사라진다. 캡처 그룹을 만든
    제외용 패턴을 넣으면 반대로 슬롯이 추가되므로 빼기 전용으로 분리한다.

    왜(Why) 여기서 소스를 다시 빼나(2026-09-29): 슬롯과 동사 사이에 말이 끼면
    "2번 의장을 1번에 입혀" 에서 **2번(소스)도** 대상 후보로 잡힌다. 그대로
    빼면 _clothing_role_slots 에서 소스까지 사라져 의상 가드가 통째로 죽는다.
    순환을 피하려로 _clothing_source_slots(원본) 를 쓴다.

    source_slots(2026-10-07 라운드 2): 이미 계산한 소스를 넘기면 같은 정규식
    두 번을 다시 돌리지 않는다. 안 넘기면 원래대로 직접 계산한다.
    """
    slots = _collect_role_slots(text, OUTFIT_TARGET_PATTERNS)
    src = (_clothing_source_slots(text) if source_slots is None
           else source_slots)
    return slots - src


def _pose_role_slots(text: str) -> set:
    """포즈 참조 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): 포즈 지정 슬롯은 신원·의상·사물 소스가 아니다. 이걸 분리하지 않으면
    포즈만 빌려오려던 사람이 참조 이미지의 얼굴까지 복사당한다.
    """
    return _collect_role_slots(text, POSE_ROLE_PATTERNS)


def _second_person_slots(text: str) -> list:
    """인물 역할이 명시된 보조 슬롯(2~10) 번호 목록. 없으면 [].

    의상 교체 의도가 있으면 "의상 슬롯"만 인물 번호에서 제외한다 -- 왜(Why):
    의상 의도만 보고 모든 인물 번호를 지우면(구버전 동작) "2번 원피스로 갈아입기
    + 3번 남성 마주보기" 같은 혼합 씬에서 남성 duo 보존이 통째로 죽었다.
    순수 의상 실행("2번 원피스를 여성에게 입히기")은 의상 슬롯만 지우면
    결과가 구버전과 동일하다.
    """
    t = (text or "").lower()
    slots = set()
    for pattern in SECOND_PERSON_PATTERNS:
        try:
            for m in re.finditer(pattern, t):
                groups = [g for g in m.groups() if g]
                if groups:
                    # 나열형 패턴은 그룹 2개(첫·둘 번호)를 모두 수집한다
                    # (2026-10-05 감사 2회 차 — groups[0] 만 수집하면
                    # "2번과 3번" 의 2번이 소실됐다).
                    for g in groups:
                        slots.add(int(g))
                else:
                    slots.add(2)
        except (ValueError, re.error):
            continue
    if _is_outfit_transfer(text):
        slots -= _clothing_role_slots(text)
    return sorted(slots)


def _is_second_person_request(text: str) -> bool:
    """보조 슬롯에 두 번째 이후 인물이 명시됐는지만 판별한다."""
    return bool(_second_person_slots(text))


def _secondary_role_labels(labels, main=None, persons=(), poses=(),
                           clothing=()):
    """보조 역할 목록(주 슬롯·추가 인물·포즈 슬롯 제외)에서 9·10번(외양 참조 전용)을 제외한다.

    왜(Why): 9·10번의 역할은 외양 참조 가드(APPEARANCE_REF_POSITIVE / LLM
    image_note)가 전담한다. 일반 보조 역할 목록("배경·의상·소품…")에 9·10번이
    섞이면 외양 참조 지시와 충돌해 LLM·생성 모델이 외양을 무시하게 된다.

    main을 넘기면 주 피사체를 명시로 제외한다 -- 왜(Why): 첫 연결이 반드시
    주 피사체인 것은 아니다(첫 연결이 핸드백 + 다음이 여성). 넘기지 않으면
    기존 규약(첫 식별 = 주 피사체)대로 첫 슬롯을 제외한다. persons는
    추가 인물로 보존할 번호 -- 추가 인물은 배경/소품 역할 목록에 섞이면 안 된다.
    poses도 동일: 포즈 전용 슬롯을 "배경·의상·소품 중 요청된 역할" 목록에 넣으면
    자세 참고 지시와 충돌해 자세가 무시된다(포즈 참조 가드가 전담한다).
    clothing도 동일(2026-09-29 실측 결함 수정): 의상 소스 슬롯을 일반 보조
    역할 목록에 넣으면 그 슬롯에 "never their clothing or outfit" 이 붙어
    **의상 교체 가드와 정면 충돌**한다(같은 프롬프트 안에서 서로 반대 지시).
    의상 역할은 outfit transfer guard 가 전담한다.
    """
    try:
        main_n = int(str(main)) if main is not None else int(str((labels or ["1"])[0]))
    except (ValueError, TypeError, IndexError):
        main_n = None
    person_ns = set()
    for p in (persons or ()):
        try:
            person_ns.add(int(str(p)))
        except (ValueError, TypeError):
            continue
    for p in (poses or ()):
        try:
            person_ns.add(int(str(p)))
        except (ValueError, TypeError):
            continue
    for p in (clothing or ()):
        try:
            person_ns.add(int(str(p)))
        except (ValueError, TypeError):
            continue
    result = []
    for x in (labels or []):
        try:
            n = int(str(x))
        except (ValueError, TypeError):
            n = None
        if n is not None:
            if n in (9, 10):
                continue
            if n in person_ns:
                continue
            if main_n is not None and n == main_n:
                continue
        result.append(str(x))
    return result


def _object_role_slots(text: str) -> set:
    """사물/소품 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): "이미지 2의 핸드백" 같은 사물 지시가 인물 지시와 섞이는 씬에서
    사물 슬롯을 사람으로 오인하는 것을 막는다(다중 인물 자동 분류).
    """
    return _collect_role_slots(text, OBJECT_ROLE_PATTERNS)


# 사물 DNA 가드를 **제외**할 슬롯을 지정하는 어휘. 기본은 모든 보조 슬롯에
# DNA 보존을 적용한다(사용자가 topic에 "침대 원본"을 안 써도 켜져야 한다).
# 단, style/lighting/mood 전용으로 명시된 슬롯은 "사물 모양"이 아니라 분위기만
# 빌려오는 것이므로 DNA 보존이 오히려 해롭다.
NON_OBJECT_SLOT_KEYWORDS = (
    "style", "style reference", "mood", "moodboard", "lighting reference",
    "color palette", "colour palette", "grade", "composition reference",
    "style_only", "분위기", "무드", "분위기만", "색감", "색조",
    "조명만", "조명참고", "톤", "레퍼런스분위기",
    # (2026-10-07 라운드 2) "스타일" 만 단독으로는 넣지 않는다 — "스타일이
    # 살아있는 소파" 같은 일반 서술까지 DNA 완화로 잡는다. 전용 표현만 넣는다.
    "스타일 참고", "스타일참고", "스타일만", "스타일 참고용",
)


def _person_object_plan(text, labels):
    """연결 슬롯의 역할을 토픽 명시에서 분류한다.

    {"main": 주 피사체 번호, "persons": 추가 인물 번호, "objects": 사물 번호}

    왜(Why): 1번이 반드시 주 피사체인 것은 아니라는 실행(1번 핸드백 + 2번 여성)
    을 지원한다. 명시 근거가 없으면 기존 규약(첫 식별 = 주 피사체)을 유지해
    기존 실행과 결과가 완전히 동일하다. 9·10번(외양 참조 전용)은
    인물·사물 번호에서 모두 제외한다 -- 외양 참조는 인물도 사물도 아니다.
    포즈 지정 슬롯도 인물·사물에서 제외하고 주 피사체 후보에서도 뺀다 --
    자세만 빌려오는 슬롯을 신원 소스로 쓰면 참조의 얼굴이 섞인다.
    """
    try:
        label_ns = [int(str(l)) for l in (labels or [])]
    except (ValueError, TypeError):
        label_ns = []
    poses = _pose_role_slots(text) & set(label_ns)
    # 의상 소스 슬롯(교체 대상은 제외됨). 옷은 사람이 아니라 의상 소스이므로
    # 신원 소스 후보가 아니다 -- 아래 주 피사체 교정에서 함께 쓴다.
    outfits = _clothing_role_slots(text) & set(label_ns)
    objects = _object_role_slots(text) & set(label_ns) - {9, 10} - poses
    persons = (set(_second_person_slots(text)) & set(label_ns)
               - objects - {9, 10} - poses)
    # **교체 대상**은 이쪽에 의상을 입는 사람이므로 인물이다(실측 결함 수정).
    # "1 의상, 2 교체" 에서 2번이 persons 에 없으면 main 이 1번(주피사체=옷)으로
    # 남아 프롬프트가 "use reference image 1 as the only main human identity"
    # 라고 역전 지시한다 -> 2026-09-29 실제 실행에서 확인.
    targets = _outfit_target_slots(text) & set(label_ns)
    persons = (persons | targets) - objects - outfits
    main = label_ns[0] if label_ns else 1
    # **교체 대상이 첫 슬롯이면 그 사람이 곧 주 피사체다**(2026-09-29 실측).
    # 라벨 순서와 topic 을 무관하게 일관되게 하려면 여기서 먼저 확정한다.
    if main in targets:
        persons = persons - {main}
    # 첫 식별이 사물로 명시됐고 인물 후보가 있으면 첫 인물이 주 피사체가 된다.
    # 근거 없는 번호로 넘기지 않는다 -- 근거 없으면 기존 규약 유지.
    if main in objects and persons:
        main = min(persons)
        persons = persons - {main}
    # 첫 식별이 **의상 소스**면(옷 사진이 1번) 그 옷을 입을 사람이 주 피사체다.
    # 옷을 신원 소스로 지목하면 사람이 사라진다 -- 실측에서 확인된 결함.
    if main in outfits:
        rest = [x for x in label_ns if x not in outfits and x not in poses]
        if rest:
            # 교체를 명시했으면(rest 안에서 대상이 보이면) 그 사람을 우선한다.
            pick = next((x for x in rest if x in targets), None)
            main = pick if pick is not None else rest[0]
            persons = persons - {main}
    # 첫 식별이 포즈 지정이면(1번 = 자세 참고) 신원 소스를 다음 슬롯으로 넘긴다.
    # 전부 포즈 지정이면 신원 소스가 없으므로 기존 번호를 유지한다(graceful).
    if main in poses:
        rest = [x for x in label_ns if x not in poses]
        if rest:
            main = rest[0]
            if main in persons:
                persons = persons - {main}
    return {"main": main, "persons": sorted(persons), "objects": sorted(objects),
            "poses": sorted(poses), "outfits": sorted(outfits)}


# 캐릭터 시트 참조 가드. (Why: 참조 이미지가 캐릭터 시트(여러 각도 동일 인물
# 나열)일 때 시트 레이아웃 자체(격자·라벨·멀티패널)가 출력으로 복제되는 실측
# 사례 — 시트는 신원 소스로만 쓰고 출력은 요청된 카메라 구도 한 컷이어야 한다.)
CHARACTER_SHEET_TOPICS = ("캐릭터 시트", "캐릭터시트", "캐릭터시", "캐릭터 시",
                          "character sheet", "charactersheet", "character_sheet",
                          "턴어라운드", "turnaround", "삼면도", "다면도",
                          "다각도", "정면후면", "전신 다각도",
                          "multiple angles of the same", "reference sheet",
                          "model sheet", "모델 시트", "시트 참고")


# **다인물 시트**(얼굴·옷이 전부 다른 여러 캐릭터가 한 장에)는 위 시트와
# 의미가 반대다 — "전부 같은 한 사람"으로 말하면 틀린 지시가 된다. 두 종류를
# 먼저 나눠 판정한다.
# (2026-10-07 라운드 2) "여명" 은 여기서 뺐다 — "강남 야경 여명"(새벽빛) 같은
# 풍경 topic 에서 다인물 시트로 오탐했다. "여러 인물" 등 나머지 어휘가 대신한다.
MULTI_PERSON_SHEET_TOPICS = (
    "여러 캐릭터", "여러캐릭터", "인물 시트", "인물시트", "다캐릭터", "다 캐릭터",
    "라인업", "lineup", "cast sheet", "ensemble sheet", "오디션 시트",
    "여러 인물", "복수 캐릭터", "다인물 시트",
)


def _is_multi_person_sheet(text: str) -> bool:
    """여러 캐릭터가 한 장에 있는 시트인가. 동일인 다중 뷰 시트와 구분한다."""
    t = (text or "").lower()
    return any(k in t for k in MULTI_PERSON_SHEET_TOPICS)


def _is_character_sheet_request(text: str) -> bool:
    """캐릭터 시트 참조 의도가 명시됐는지 판별한다."""
    t = (text or "").lower()
    return any(keyword in t for keyword in CHARACTER_SHEET_TOPICS)
