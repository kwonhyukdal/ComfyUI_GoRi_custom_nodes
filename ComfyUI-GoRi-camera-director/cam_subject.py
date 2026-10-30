# -*- coding: utf-8 -*-
"""주제 분류(사람/동물/다인/반사/복장/포즈)와 슬롯 역할 판정."""

from __future__ import annotations

import re
import threading
from functools import lru_cache

try:
    from .cam_util import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403


__all__ = [
"HUMAN_SUBJECT_KEYWORDS", "_MODEL_OBJECT_PATTERN", "_is_human_subject", "HUMAN_PRONOUN_KEYWORDS", "_human_pronoun_present", "ANIMAL_SUBJECT_KEYWORDS", "_animal_keyword_present", "ANIMAL_SPECIES_POSITIVE", "ANIMAL_ANATOMY_NEGATIVE", "_KO_SUFFIX_CHARS", "_ascii_only", "_ko_word_present", "_ASCII_AMBIGUOUS", "_ascii_word_present", "_is_animal_subject", "MULTI_PERSON_KEYWORDS", "REFLECTION_KEYWORDS", "_REFLECTION_ASCII_WORDS", "_is_reflection_scene", "_is_multi_person_request", "SECOND_PERSON_PATTERNS", "_NUMBER_WORDS", "_ORDINAL_WORDS", "_KO_OBJECT_WORDS", "_EN_OBJECT_WORDS", "OBJECT_WORDS", "_TEMPERED_GAP", "_KO_CLOTHING_WORDS", "_EN_CLOTHING_WORDS", "CLOTHING_WORDS", "_role_patterns", "OBJECT_ROLE_PATTERNS", "CLOTHING_ROLE_PATTERNS", "_OUTFIT_VERB", "_OUTFIT_APPLY_SLOT_PATTERNS", "_OUTFIT_TARGET_ROLE", "OUTFIT_TARGET_PATTERNS", "_KO_POSE_STATE", "_EN_POSE_STATE", "_KO_POSE_WORDS", "_EN_POSE_WORDS", "POSE_ROLE_PATTERNS", "_collect_role_slots", "_clothing_role_slots", "_clothing_declared_slots", "_CLOTHING_COLON_PATTERN", "_has_outfit_apply_verb", "_EN_GARMENT_WORDS", "_is_text_outfit_change", "_topic_changes_shoes", "_topic_wants_barefoot", "_topic_item_color", "_is_empty_scene", "_outfit_target_slots", "_pose_role_slots", "_second_person_slots", "_is_second_person_request", "_secondary_role_labels", "_object_role_slots", "_person_object_plan", "_is_multi_person_sheet", "_is_character_sheet_request", "CHARACTER_SHEET_TOPICS", "MULTI_PERSON_SHEET_TOPICS", "_reference_items", "_is_outfit_transfer", "OUTFIT_RELATION_PATTERNS", "NON_OBJECT_SLOT_KEYWORDS", "BACKGROUND_ROLE_PATTERNS", "_background_role_slots", "set_reference_kinds", "clear_reference_kinds",
"_hint_person_slots", "_hint_pose_slots", "_hint_object_slots", "_hint_no_person_classified", "_text_names_slots", "intent_core",
"_normalize_slots",
"footwear_noun_mismatch", "_KO_WEAR_ITEMS", "_KO_CLOTHING_ROLE_WORDS",
"_KO_WEAR_BASIC_WORDS", "_KO_WEAR_ACCESSORIES", "_WEAR_NOUN_KO",
"_WEAR_GENERIC_KO", "_loose_alt", "verb_stem_present", "_WEAR_STEMS",
"_VERB_ENDINGS_CHANGE", "_VERB_ENDINGS_STATE", "scene_text",
"_SCENE_MARKER_RE", "_EN_SLOT_DECL_RE", "_person_role_slots", "_subject_decl_slots",
"_HUMAN_WORDS_KO", "_HUMAN_WORDS_EN", "guess_pos",
"_axis_consults_role_lexicon", "_decl_verb_slots",
"_declared_role_slots", "appearance_ref_slots",
"colon_less_role_hint",
"_footwear_slots", "_KO_FOOTWEAR_WORDS", "_EN_FOOTWEAR_WORDS",
"_FOOTWEAR_ROLE_PATTERNS",
"_KO_SEAT_WORDS", "_EN_SEAT_WORDS", "SEAT_WORDS", "_SEAT_VERBS",
"_SEAT_ROLE_PATTERNS", "_seat_slots", "_background_seat_slots",
]


# ---------------------------------------------------------------------------
# 참조 자동 분류 힌트 (2026-10-19)
#
# 왜(Why) 전역 힌트인가: 슬롯 역할을 쓰는 함수가 12곳(cam_anchors 6 ·
# cam_guards 4 · camera_director 2)이다. 전부에 인자를 하나씩 더하면 호출부와
# 테스트를 함께 고쳐야 하고, 하나를 빠뜨리면 그 가드만 조용히 옛 규약(첫 연결 =
# 주 피사체)으로 돌아간다. 대신 실행 시작에 한 번 심고 끝에 지운다 —
# ComfyUI 는 프롬프트를 한 번에 하나씩 실행하므로 thread-local 이면 충분하다.
#
# 힌트는 **토픽이 슬롯 번호를 하나도 말하지 않을 때만** 쓰인다. 사용자가
# "2번 의상" 이라고 적었으면 그 판정이 언제나 이긴다.
# ---------------------------------------------------------------------------
_KIND_HINT = threading.local()
# 픽셀 검출 인물 슬롯 (2026-10-23). 왜(Why) kind 지도와 **따로** 두나: `_KIND_HINT`
# 는 LLM 역할까지 병합된 지도라, 그 안의 "person" 만 보면 "픽셀이 사람을 찾았다"
# 와 "LLM 이 사람이라고 분석했다" 를 가를 수 없다. 그 둘은 9·10번에서 결론이
# 다르다 — 픽셀은 자세 랜드마크 + 몸 크기 게이트를 통과한 실측이고, LLM 의
# person 은 몸 근접 참조까지 사람으로 볼 수 있다(작업 9 의 경계). 그래서 픽셀
# 근거만 따로 심는다.
_PIXEL_HINT = threading.local()


def set_reference_kinds(kinds, persons=None) -> None:
    """{슬롯번호: 'person'|'unknown'|...} 을 이번 실행의 힌트로 심는다.

    `persons` 는 **픽셀이** 사람을 찾은 슬롯이다. 넘기지 않으면 `kinds` 에서
    person 인 슬롯을 그대로 쓴다(분류 직후처럼 픽셀 근거뿐인 호출). LLM 역할을
    병합한 **뒤** 다시 부를 때는 앞서 구한 집합을 반드시 넘긴다 — 안 넘기면
    LLM 의 person 이 픽셀 근거로 둔갑해 9·10번 경계가 풀린다.
    """
    try:
        clean = {int(k): str(v) for k, v in (kinds or {}).items()}
    except (TypeError, ValueError):
        clean = {}
    _KIND_HINT.kinds = clean or None
    if persons is None:
        _PIXEL_HINT.persons = {k for k, v in clean.items() if v == "person"} or None
    else:
        try:
            _PIXEL_HINT.persons = {int(x) for x in persons} or None
        except (TypeError, ValueError):
            _PIXEL_HINT.persons = None


def clear_reference_kinds() -> None:
    """실행이 끝나면 지운다 (다음 실행에 새지 않게)."""
    _KIND_HINT.kinds = None
    _PIXEL_HINT.persons = None


def _pixel_person_slots() -> set:
    """**픽셀이** 사람을 찾은 슬롯(근거 종류를 가르는 내부용)."""
    return set(getattr(_PIXEL_HINT, "persons", None) or ())


def _hint_person_slots() -> list:
    """힌트가 말하는 인물 슬롯 — 9·10번은 **픽셀 근거가 있을 때만** 든다.

    왜(Why) 9·10번만 근거를 나누나 (2026-10-23 실측, README 5-1·5-5 대조):
    공개 사용설명서는 "어느 칸이든 주 피사체가 될 수 있고, 역할은 번호가 아니라
    내용으로 정해지며, **사람이 있는 칸은 픽셀로 찾아** 주 피사체 후보로 삼는다"
    고 약속한다. 실측: 의자 1번 + 한국 여성 9번 + 빈 topic 에서 프롬프트가
    `use reference image 1 as the only main human identity` 를 내보냈다 —
    의자가 사람 신원이 됐다(같은 실행의 콘솔 로그는 `인물 슬롯 9` 라고 말하고
    있었다: 로그와 프롬프트가 서로 달랐다).

    반대로 **LLM 분석만으로** 승격하지는 않는다: 몸 근접 외양 참조를 LLM 이
    person 이라고 보는 일이 흔하고(작업 9 의 경계), 그 값으로 승격하면 사용자
    전용 기능이 조용히 주 피사체를 바꾼다. 몸 근접은 자세 랜드마크가 안 잡혀
    픽셀로는 person 이 아니다 — 그래서 픽셀 근거를 기준으로 삼는다.
    """
    kinds = getattr(_KIND_HINT, "kinds", None) or {}
    px = _pixel_person_slots()
    return sorted(int(k) for k, v in kinds.items()
                  if v == "person" and (int(k) not in (9, 10) or int(k) in px))



def _hint_pose_slots() -> list:
    """힌트가 말하는 포즈 슬롯 (2026-10-19 · 9·10번 포함 2026-10-23).

    왜(Why) topic 전용이던 것을 여는가: LLM 이 이미지를 보고 "이 칸은 포즈"라고
    알려 줘도 plan 의 pose_slots 는 topic 텍스트(_pose_role_slots)만 봐서
    포즈 가드가 안 나갔다 — topic 을 비운 사용자에게만 해당하던 구멍이다.

    **9·10번 제외를 2026-10-23 에 풀었다 (사용자 결정 "이제 빼면 안 되지").**
    제외의 근거는 "외양 참조 기본값이 남은 슬롯을 포즈로 읽으면 두 가드가 반대
    지시를 낸다" 였는데, 그 근거가 이미 사라져 있었다:
      1) pose kind 는 픽셀이 못 만든다(어휘 person/item/unknown). LLM 역할이 만든다.
      2) 그 LLM 역할이 같은 실행에서 외양 참조 기본값을 **이미 해제**한다
         (appearance_ref_slots 는 비-person 역할을 버린다).
    실측: appearance_ref_slots("", [9,10], {9:"pose",10:"pose"}) == set().
    게다가 `_person_object_plan` 은 같은 kinds 를 읽으면서 9·10번을 빼지 않는다
    (poses=[9] 를 돌려주고 그 값이 제외 집합·보조 역할 계산에 들어간다) — 포즈
    가드만 그 값을 안 봐서 **한쪽 가드만 꺼진** 상태였다. 이 변경은 새 동작을
    만드는 것이 아니라 있던 판정을 끝까지 보낸다(실측: gori_pose9_plan_probe.txt).
    남는 위험: 몸 근접 크롭을 LLM 이 pose 로 오라벨하면 그 슬롯이 포즈 참조가
    된다 — 다만 외양 기본값은 **같은 라벨로 이미 꺼져** 있으므로 이 변경이 새로
    만드는 차이는 "포즈 지시가 붙는 것" 하나다(design 4).
    """
    kinds = getattr(_KIND_HINT, "kinds", None) or {}
    return sorted(int(k) for k, v in kinds.items() if v == "pose")


def _hint_object_slots() -> list:
    """힌트가 사물/제품으로 분류한 슬롯 (2026-10-25 감사).

    왜(Why) 필요한가: reference_guard 가 "참조에 사람이 없고 주 슬롯이 사물이면
    사람 신원 조항을 내지 않는다" 를 판정하려면 힌트의 object/item 슬롯을 직접
    봐야 한다. `_person_object_plan` 은 main 을 objects 에서 **빼 버려서**(주
    슬롯이 사물일 때 objects 가 빈 리스트가 된다) 그 값만으로는 가를 수 없다.
    """
    kinds = getattr(_KIND_HINT, "kinds", None) or {}
    return sorted(int(k) for k, v in kinds.items() if v in ("object", "item"))


def _hint_no_person_classified() -> bool:
    """분류가 돌았고(kinds 가 있음) 사람 슬롯이 **하나도 없으면** True (2026-10-30).

    왜(Why) object/item 만 보던 것을 넓히나 (F1): 참조 자동 분류는 사람도 사물도
    못 찾으면 `unknown` 을 낸다. 그때 종전 판정(`_hint_object_slots`)은 빈 목록이라
    "사람이 없다" 는 근거를 못 읽었고, 사람도 동물도 아닌 주제(풍경·차량·정물)에
    사람 신원 조항("same facial structure ...")이 새어 나갔다 — 실측: 노이즈 참조
    1장 + "a red sports car parked on the street" 에서 붙었다. unknown 은 "사람이
    있다" 가 아니라 "모른다" 이므로 object/item 과 같은 근거로 본다.

    **kinds 가 아예 없으면 False** 를 돌려준다. 분류가 돌지 않은 직접 호출(테스트·
    텍스트 단독 경로)에서 사람 신원 조항을 함부로 빼지 않기 위해서다 — 의상 교체
    주제처럼 사람이 있다는 신호가 따로 있는 경우도 있다(R82).
    """
    kinds = getattr(_KIND_HINT, "kinds", None) or {}
    if not kinds:
        return False
    return not any(v == "person" for v in kinds.values())


def _text_names_slots(text: str) -> bool:
    """토픽이 슬롯 번호를 직접 지목했는가 ("2번", "image 3", "이미지 4", "No. 2:").

    2026-10-24: 영어 선언도 같은 입구(`_normalize_slots`)를 지나 `N번:` 이 되므로
    **새 목록을 만들지 않는다** — 목록이 둘이면 또 갈린다(역할 어휘 드리프트와 같은 이유).
    """
    return bool(re.search(r"(?:이미지|image|img)\s*_?\d+|\d+\s*번",
                          _normalize_slots(text or ""), re.IGNORECASE))


# 의상 어휘의 **단일 출처** (2026-10-11 검토). OUTFIT_RELATION_PATTERNS 와
def _loose_alt(words) -> str:
    """낱말 목록 -> 정규식 대안 문자열. 한글 낱말은 음절 사이에 `\\s*` 를 넣는다.

    왜(Why) (2026-10-23 실측): 사용자가 "3번: 하이 힐" 처럼 띄어 쓴다. 음절 간
    간격을 허용하지 않으면 품목을 등록해도 표기가 어긋나면 미인식이다.
    영어는 건드리지 않는다 — 쪼개면 패턴만 길어지고 단어 경계(`\\b`) 판정이 흔들린다.
    """
    out = []
    for _w in words:
        if len(_w) > 1 and all("\uac00" <= _c <= "\ud7a3" for _c in _w):
            out.append(r"\s*".join(_w))
        else:
            out.append(_w)
    return "|".join(out)


# 의상 **개념** 어휘(역할 판정용)와 착용 **품목**(물건)을 나눠 둔다. 품목은
# 착용 교체 사전(_WEAR_NOUN_KO, 아래)과 **한 목록**을 공유한다 — 두 목록이 따로
# 자라면 한쪽에만 품목이 생겨 슬롯 인식과 교체 판정이 어긋난다(아래 참조).
#
# 왜(Why) 역할 어휘에 의장·생활복이 있어야 하나: CLOTHING_ROLE_PATTERNS(아래)가
# 같은 목록을 써야 한다. 실측: 패턴 쪽에 "의장·생활복" 이 없어 "이미지 2의
# 생활복으로 갈아입혀" 가 outfit_transfer=False 로 떨어졌고, 그 결과
# _is_human_subject 가 False 가 되어 **인물 가드가 전부 사라졌다.**
_KO_CLOTHING_ROLE_WORDS = "의상|옷|옷차림|의장|생활복|패션|아우터"


# 착용 품목 단일 목록 (2026-10-23). 왜(Why) 한 곳으로 모으나: 역할 사전과 착용
# 의도 사전이 따로 자라면서 드리프트가 났다 — 실측: 착용 쪽에만 하이힐·부츠·
# 샌들·운동화·플랫·로퍼·웨지·뮬·하이탑·단화·치마·스커트가 있어 "3번: 하이힐" 이
# 의상 역할로 인식되지 않았다(구두로 시험하면 통과해 구멍이 가려졌다).
# 품목을 추가할 때는 **여기 한 줄만** 늘리면 역할 사전과 교체 사전이 함께 받는다.
_KO_WEAR_ITEMS = (
    "드레스", "셔츠", "블라우스", "바지", "원피스", "코트", "재킷", "자켓",
    "슈트", "정장", "한복", "웨딩드레스",
    "구두", "신발", "샌들", "단화", "운동화", "하이힐", "부츠", "슬리퍼",
    "플랫", "로퍼", "웨지", "뮬", "하이탑", "치마", "스커트",
)


# 착용 교체 판정(_WEAR_NOUN_KO)에서 "일반 명사" 로 보는 낱말과, 옷이 아니지만
# 착용 교체로 읽어야 하는 소품. 역할 사전에는 넣지 않는다 — 가방은 사물 슬롯이다.
_KO_WEAR_BASIC_WORDS = ("의상", "옷차림", "옷")
_KO_WEAR_ACCESSORIES = ("모자", "가방")


_KO_CLOTHING_WORDS = (
    _KO_CLOTHING_ROLE_WORDS + "|" + _loose_alt(_KO_WEAR_ITEMS)
)


# 영어 의상 **품목**의 단일 출처 (2026-10-24). 왜(Why) 한 곳인가: 역할 패턴용
# 목록(`_EN_CLOTHING_WORDS`)과 텍스트 단독 교체 목록(`_EN_GARMENT_WORDS`)이 따로
# 자라면서 갈렸다 — 실측: 영어 선언 `No. 3: High heels` 가 역할 목록에 heels 가
# 없어 **의상 슬롯으로 인식되지 않았다**(한국어 `하이힐` 은 등록돼 있었다).
# 이제 이름 하나(`_EN_GARMENT_WORDS`)만 늘리면 역할 사전과 교체 사전이 함께 받는다.
_EN_GARMENT_WORDS = (
    r"high\s*heels?|outfit|clothing|clothes|dress|gown|sweater|skirt|shirt|blouse|"
    r"pants|trousers|jeans|jacket|coat|suit|uniform|wardrobe|garment|"
    r"apparel|top|bottoms|knit|denim|shoe|shoes|sandal|sandals|boot|boots|"
    r"heel|heels|sneaker|sneakers|slipper|slippers|loafers?|flats|footwear"
)

_EN_CLOTHING_WORDS = _EN_GARMENT_WORDS


CLOTHING_WORDS = _KO_CLOTHING_WORDS + "|" + _EN_CLOTHING_WORDS


OUTFIT_RELATION_PATTERNS = (
    # English: clothing/outfit explicitly comes from a reference image.
    r"\b(?:outfit|clothing|wardrobe|dress|shirt|coat|apparel|garment)\b.{0,24}\b(?:from|reference|using|with)\s+(?:reference\s+)?(?:image|img)\s*_?\d+",
    r"\b(?:image|img)\s*_?\d+\b.{0,24}\b(?:is|as|contains|shows)\s+(?:the\s+)?(?:outfit|clothing|wardrobe|dress|shirt|coat|apparel|garment)\b",
    # Korean: 이미지 N의 의상/옷을 입히거나/바꾸는 명시적 의도.
    # 의상 어휘는 _KO_CLOTHING_WORDS 하나만 본다(드리프트 방지).
    r"(?:image|img|이미지)\s*_?\d+\s*(?:의|에|에서)?\s*(?:" + _KO_CLOTHING_WORDS + r")",
    r"(?:" + _KO_CLOTHING_WORDS + r").{0,24}(?:image|img|이미지)\s*_?\d+",
    r"(?:입히|입게|바꾸|사용|적용|참고).{0,28}(?:의상|옷|드레스|패션|(?:image|img|이미지)\s*_?\d+)",
)


def _is_outfit_transfer(text: str) -> bool:
    """단순히 'dress/옷'이 있는 scenes가 아니라, image_N을 의상 참고로 쓰라는 의도만 판별한다."""
    return _is_outfit_transfer_cached((text or "").lower())


@lru_cache(maxsize=64)
def _is_outfit_transfer_cached(t: str) -> bool:
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

    # 슬롯 원소를 (번호, 값) 쌍으로 items 에 넣는다 — 번호가 없으면 순번으로 대체
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
    # 가족·연령·직업 명사 (2026-10-25 감사 F1). 왜(Why) 추가하나: 이 함수
    # 하나로 게이트되는 사람 가드가 12종인데, "a baby lying on a blanket" 처럼
    # 흔한 명사가 목록에 없어 **가드가 통째로 사라졌다**(실측 5157자 -> 762자).
    # "model" 은 넣지 않는다(위 주석의 "3D model" 오탐). "kid" 는
    # _ASCII_AMBIGUOUS 라 단어 경계로만 본다("kidney" 오탐 방지).
    "baby", "child", "kid", "toddler", "teenager", "infant",
    "grandmother", "grandfather", "guy", "bride", "groom",
    "nun", "dancer", "soldier", "nurse", "chef",
    "캐릭터", "인물", "여성", "남성", "여자", "남자", "사람", "아이",
    "소년", "소녀", "남아", "여아", "주인공", "인물체", "모델", "아이돌",
    "아기", "할머니", "할아버지", "노인", "청년", "어린이",
    "여자아이", "남자아이",
)


# 동물 종이 함께 명시되면 **양보하는** 사람 명사 (2026-10-25 감사 F1).
# 왜(Why) 필요한가: "baby elephant" 는 사람이 아니라 새끼 코끼리다. "kid goat"
# 는 새끼 염소다(영어 "kid" 자체가 새끼 염소다). 이 낱말들이 동물 종 명사와
# 함께 나오면 사람 신호로 세지 않는다 — 대명사 단계의 동물 양보(아래 ③)와
# 같은 판단이다. 반대로 "a baby"(단독)·"a baby girl" 은 그대로 사람이다.
_HUMAN_WEAK_KEYWORDS = frozenset({
    "baby", "child", "kid", "toddler", "infant", "아기",
})


# 사람이 아닌 관용구 — "baby blue"(색) 처럼 사람 명사를 색·분위기 수식으로
# 쓰는 표기. 마스킹해 오탐을 막는다(2026-10-25 감사 F1). "baby blue 배경의
# 제품샷" 에 사람 해부 가드(손가락 다섯 개 등)가 붙으면 **없던 손을 그린다**.
_BABY_COLOR_IDIOM_RE = re.compile(
    r"\bbaby\s+(?:blue|pink|green|blue-?gr[ae]y)\b")


def _mask_human_false_friends(text: str) -> str:
    """사람으로 오인되는 관용구를 같은 길이 공백으로 가린다."""
    return _BABY_COLOR_IDIOM_RE.sub(lambda m: " " * len(m.group(0)), text)


# "3D model of a car"처럼 사물 모형을 가리키는 표기. 왜(Why): 영어 "model"
# 단독 키워드가 사물 모형 장면까지 사람 장면으로 오판해 identity 가드를
# 잘못 붙였기 때문이다. 모형 표기가 있으면 모델류 키워드는 무시하고
# 명확한 인물 키워드만 본다.
_MODEL_OBJECT_PATTERN = re.compile(r"(?:3d|3-d|3차원|scale)\s*(?:model|모델)")


# 인물 대명사 (2026-10-22, R193). 왜(Why) 필요한가(실측): 사용자 토픽이 그래프
# 안의 번역 노드를 지나 "He is wearing jeans, his hands on his knees, and is
# sitting on a chair indoors, looking straight ahead." 가 되자 인물 키워드가
# 하나도 없어 `_is_human_subject` 가 False 였고, **인물 가드 22문장이 통째로
# 사라졌다**(같은 문장을 "The woman is …" 로 쓰면 붙는다. 프롬프트 3,334자 vs
# 7,024자). 대명사는 사람을 가리키는 가장 흔한 표기인데 목록에 없었다.
#
# 왜(Why) 두 단계인가: 대명사는 **문맥 없이는 약한 신호**다. 실측 —
# "The cat is licking his paw" 는 동물 장면인데 "his" 하나로 사람이 되어버린다.
# 그래서 동물 종이 명시됐으면 대명사만으로는 사람으로 보지 않는다(위 의상 교체
# 분기의 동물 양보와 같은 판단). 동물 낱말 스캔은 `_animal_keyword_present`
# 하나만 쓴다 — `_is_animal_subject` 를 부르면 그 함수가 다시 이 함수를 불러
# **무한 재귀**가 된다(그 함수 첫 줄이 `_is_human_subject` 다).
#
# 왜(Why) 단어 경계인가: 영문 부분 일치로 하면 "the" 안의 "he" 가 잡혀
# **모든 영문 토픽**이 사람이 된다. `_ascii_word_present` 로만 본다.
HUMAN_PRONOUN_KEYWORDS = (
    "he", "she", "him", "her", "hers", "his", "they", "them", "their",
    "theirs", "himself", "herself", "themselves",
    "그녀", "그들",
)


def _human_pronoun_present(text: str) -> str:
    """사람을 가리키는 대명사. 있으면 그 낱말을, 없으면 빈 문자열을 돌려준다."""
    t = (text or "").lower()
    for word in HUMAN_PRONOUN_KEYWORDS:
        if _ascii_only(word):
            if _ascii_word_present(t, word):
                return word
        elif _ko_word_present(t, word):
            return word
    return ""


# 사람 주제인지 — 의상 교체 표현도 사람으로 보고, 동물/사물 명시가 있으면 양보한다
def _is_human_subject(text: str) -> bool:
    t = (text or "").lower()
    # 토픽이 비었는데 참조에서 사람이 검출됐으면 사람 주제로 본다 (2026-10-19).
    # 인물 가드가 전부 이 함수 하나로 게이트되므로 여기서 힌트를 읽으면
    # 12개 호출부를 고치지 않아도 일관되게 켜진다.
    # 빈 토픽은 스레드 로컬 힌트에 따라 달라지므로 캐시하지 않는다.
    if not t.strip():
        return bool(_hint_person_slots())
    return _is_human_subject_cached(t)


@lru_cache(maxsize=64)
def _is_human_subject_cached(t: str) -> bool:
    # 사람으로 오인되는 관용구("baby blue" 등)를 먼저 가린다 (2026-10-25 F1).
    # 순수 함수이고 길이를 바꾸지 않으므로 다른 판정에 영향이 없다.
    t = _mask_human_false_friends(t)
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
        #
        # 2026-10-22 (R193): 낱말 스캔은 `_animal_keyword_present` 하나로 합쳤다.
        # 대명사 단계가 같은 스캔을 써야 하는데 `_is_animal_subject` 는 첫 줄에서
        # 이 함수를 다시 불러 무한 재귀가 된다(실측: 그대로 넣으면 RecursionError).
        if _animal_keyword_present(t):
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
            hit = _ascii_word_present(t, keyword)
        elif _ascii_only(keyword):
            # 영문은 종전대로 부분 일치. 왜(Why) \b 로 바꾸지 않나:
            # "girlfriend" 안의 "girl" 처럼 합성어가 사람 장면인 경우가
            # 있어 단어 경계로 좁히면 오히려 가드가 사라진다.
            hit = keyword in t
        else:
            # 한국어는 _is_animal_subject 와 같은 경계 판정을 쓴다.
            # raw `in` 이면 "아이스크림/아이패드" 가 "아이" 로 잡혀
            # 제품 샷에 인물 가드가 전부 붙었다. "아이돌" 은 원래 "아이"
            # 부분 일치에 우연히 걸리던 것을 경계 판정 도입과 함께
            # 명시 키워드로 유지한다.
            hit = _ko_word_present(t, keyword)
        if not hit:
            continue
        # 약한 사람 명사는 **동물 종이 함께 명시되면 양보한다** (2026-10-25 F1).
        # "baby elephant" / "kid goat" 는 사람 장면이 아니다 — 여기서 사람으로
        # 세면 코끼리·염소에 사람 해부 가드가 붙는다. 동물 스캔은 약한 명사가
        # 실제로 맞았을 때만 돈다(매 호출 비용을 늘리지 않는다).
        if keyword in _HUMAN_WEAK_KEYWORDS and _animal_keyword_present(t):
            continue
        return True
    # ③ 대명사 단계 (2026-10-22, R193). 명사가 없어도 사람을 가리키는 대명사가
    #    있으면 사람으로 본다 — 단, **동물 종이 명시됐으면 양보한다.**
    #    왜(Why) 양보인가(실측): "The cat is licking his paw" 를 사람으로 보면
    #    고양이 그림에 사람 해부·정체성 가드가 붙는다. 대명사는 문맥 없이는
    #    약한 신호이므로 동물 명시를 이긴다고 보지 않는다.
    if _human_pronoun_present(t) and not _animal_keyword_present(t):
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
    # 새끼·품종 (2026-10-25 감사 F2). 왜(Why) 추가하나: 종 보존·인간화 방어
    # 가드가 이 함수 하나로 게이트되는데, 새끼 동물은 부모 낱말을 포함하지
    # 않아("calf" 에 "cow" 가 없다) 전부 놓쳤다(실측: "a calf" animal=False).
    # 새끼 개·고양이("puppy"/"kitten")는 이미 있었다 — 그 목록을 새끼
    # 소·양·말·닭·오리·돼지·야생동물로 넓힌다. "goldfish" 는 "fish" 를
    # 포함하지만 \b 경계라 종전엔 놓쳤다(단어 경계의 부작용).
    "calf", "lamb", "foal", "chick", "duckling", "piglet", "cub", "joey",
    "fawn", "goldfish", "collie",
    "고양이", "강아지", "애완동물", "반려동물", "동물", "말", "새", "앵무새",
    "독수리", "앵무", "토끼", "다람쥐", "여우", "사슴", "소", "양", "염소",
    "돼지", "곰", "호랑이", "사자", "원숭이", "판다", "펭귄", "오리", "백조",
    "거북이", "뱀", "개구리", "물고기", "고래", "돌고래", "햄스터",
    "송아지", "새끼양", "어린양", "망아지", "병아리", "새끼오리", "새끼돼지",
    "금붕어",
)


# 동물 낱말이지만 **사람 신체**로도 쓰는 표기 (2026-10-25 감사 F2).
# 왜(Why) 필요한가: "calf" 는 새끼 소이자 종아리 근육이다. "the runner's
# calf muscles" 를 동물 장면으로 보면 사람 장면에 동물 가드가 붙는다.
# 뒤에 muscle 이 붙은 표기만 가린다("a calf in the meadow" 는 그대로 동물).
_ANIMAL_FALSE_FRIEND_RE = re.compile(r"\b(?:calf|calves)\s+muscles?\b")


def _mask_animal_false_friends(text: str) -> str:
    """동물로 오인되는 사람 신체 표기를 같은 길이 공백으로 가린다."""
    return _ANIMAL_FALSE_FRIEND_RE.sub(lambda m: " " * len(m.group(0)), text)


def _animal_keyword_present(text: str) -> bool:
    """동물 낱말이 문맥에 있는지만 본다 (사람 판정을 부르지 않는다).

    왜(Why) 따로 있나 (2026-10-22, R193): `_is_animal_subject` 는 첫 줄에서
    `_is_human_subject` 를 부른다. 사람 판정의 대명사 단계가 동물 양보를 보려고
    그 함수를 부르면 **서로를 불러 무한 재귀**가 된다. 스캔만 여기로 뺀다.

    왜(Why) 영문도 경계 판정인가 (2026-10-11 실측): raw `in` 이면 "dog" 이
    "dogmatic", "owl" 이 "bowl", "lion" 이 "rebellious", "rat" 이 "pirate" 안에서
    잡혀 **사람 장면이 동물로 뒤집히고** 인물 가드가 통째로 사라진다. 실측:
    "wear the outfit from image 2, a dogmatic pose" → human=False 이고 animal 도
    False 라 어느 가드도 안 붙었다. 형제 함수와 같은 `_ascii_word_present` 를 쓴다.
    """
    t = _mask_animal_false_friends((text or "").lower())
    for keyword in ANIMAL_SUBJECT_KEYWORDS:
        if _ascii_only(keyword):
            if _ascii_word_present(t, keyword):
                return True
        elif _ko_word_present(t, keyword):
            return True
    return False


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
    "으로"        # 방향 (2026-10-16 오딧: 없어서 "사람으로" 가 미인식)
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


@lru_cache(maxsize=512)
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
        # _KO_SUFFIX_CHARS 는 음절 나열 **문자열**이다(괄호 안 인접 문자열
        # 연결) — 한 글자가 그 안에 있으면 조사 첫 글자다. "까지"/"부터" 는
        # 각각 "까"/"부" 로 이미 포함되므로 별도 분기가 필요 없다(2026-10-16
        # 오딧: 도달 불가 분기 2개 제거).
        if nxt in _KO_SUFFIX_CHARS:
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
    # 2026-10-25 감사 F1 — 부분 일치하면 다른 낱말에 걸리는 사람 명사.
    #   groom  -> "grooming"(손질) / "groomed"
    #   nurse  -> "nursery"(육아방)
    #   nun    -> "nunchaku" 등
    #   baby   -> "babysitter" 는 사람이지만 경계로 좁혀도 잃지 않는다
    "groom", "nurse", "nun", "baby",
})


@lru_cache(maxsize=512)
def _ascii_word_re(word: str):
    return re.compile(r"\b" + re.escape(word) + r"\b")


def _ascii_word_present(text: str, word: str) -> bool:
    """영문 단어를 단어 경계로만 찾는다 (\\b 매칭)."""
    return bool(_ascii_word_re(word).search(text))


def _is_animal_subject(text: str) -> bool:
    """동물 주제면 True. 인물 키워드가 명시되면 사람 우선(장면 혼재 대응)."""
    t = (text or "").lower()
    if not t:
        return False
    if _is_human_subject(t):
        return False
    return _animal_keyword_present(t)


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


# 거울/반사 장면인지 — ASCII 단어는 경계 검사, 한글 키워드는 포함 검사
def _is_reflection_scene(text: str) -> bool:
    t = (text or "").lower()
    if any(_ascii_word_present(t, word)
           for word in _REFLECTION_ASCII_WORDS):
        return True
    return any(keyword in t for keyword in REFLECTION_KEYWORDS)


# 여러 인물을 요청한 문장인지 — 다인 키워드 포함 여부만 본다
def _is_multi_person_request(text: str) -> bool:
    t = (text or "").lower()
    return any(keyword in t for keyword in MULTI_PERSON_KEYWORDS)


# 창 안에 **다른 슬롯 참조**가 끼면 그 인물 단어는 그 슬롯의 것이다 (2026-10-13 실측).
# 왜(Why) 필요한가: "The woman in image 1 is sitting on a chair in image 2." 가
# 창(40자)이 "image 1" 을 넘어가면서 **"image 2 에 여자가 있다"** 로 오판됐다.
# 참조는 image_1=인물 / image_2=의자였고, 그 결과 프롬프트에
# "person two from reference image 2" 와 "sitting on a chair in image 2" 가
# **동시에** 들어가 정면 모순이 됐다(실측 거리 37자 < 40자 창).
# 규칙: 인물 단어와 슬롯 참조 사이에 다른 슬롯 참조가 있으면 그 쌍은 버린다.
# 재현: "The woman in image 1 sits on a chair in image 2." -> 이제 [] (오판 해소).
#       "woman in image 1 and woman in image 2" -> 여전히 [2] (정상 유지).
_NO_SLOT_REF = (r"(?:(?!\b(?:image|img|이미지)\s*_?\s*\d"
                r"|\d+\s*(?:번|번째)\s*(?:image|img|이미지))"
                r"[^,，.。;；!！?？\n])")


SECOND_PERSON_PATTERNS = (
    # image/이미지 표기 혼용 대응: "Image 3의 남성" 같은 한영 혼합도 잡는다.
    # 주의: 한글 조사(의/에)는 \w 취급이라 2\b 경계가 안 맞으므로 (?![0-9])를 쓴다.
    # 2번 고정이 아니라 2~10번 슬롯을 캡처한다.
    # 비탐욕 창 + 절 차단: 창이 쉼표/식별자를 넘어 다음 슬롯의 단어를 잘못 잡거나
    # (이미지 2번 핸드백, 이미지 3번 남성 → 3번 누락/2번 오검출)
    # finditer의 비중복 소비 때문에 건너뛰는 후보가 생기는 것을 동시에 막는다.
    # 창은 `_NO_SLOT_REF` — 다른 슬롯 참조를 넘지 않는다(2026-10-13).
    r"\b(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])" + _NO_SLOT_REF + r"{0,40}?\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b",
    r"\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person)\b" + _NO_SLOT_REF + r"{0,40}?\b(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])",
    r"(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])" + _NO_SLOT_REF + r"{0,20}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)",
    r"(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)" + _NO_SLOT_REF + r"{0,20}?(?:image|img|이미지)\s*_?\s*([2-9]|10)(?![0-9])",
    r"두\s*번째\s*(?:사람|남자|남성|여자|여성|인물)",
    r"second\s+(?:person|man|woman|male|female)",
    # 번호 선행형: "2번 이미지의 남성이" — 위 4개 패턴은 모두 이미지 표기가
    # 앞에 오는 구문만 커버한다. 자연스러운 "N번 이미지" 표현을 놓치면
    # 두 번째 인물이 보조 역할(배경/소품)로 오분류된다.
    r"([2-9]|10)\s*(?:번|번째)\s*(?:image|img|이미지)\s*(?:의|에|에서|은|는)?\s*" + _NO_SLOT_REF + r"{0,20}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람)",
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
    r"([1-9]|10)\s*(?:번|번째)\s*(?:와|과|및|그리고|·|,|\+)\s*([2-9]|10)\s*(?:번|번째)?[^,，.。;；!！?？\n]{0,16}?(?:남성|남자|신랑|아버지|소년|여성|여자|신부|어머니|소녀|인물|사람|커플|쌍)",
    r"\b(?:image|img)\s*_?\s*([1-9]|10)\s*(?:and|&|,)\s*(?:image|img)?\s*_?\s*([2-9]|10)\b" + _NO_SLOT_REF + r"{0,24}?\b(?:man|male|guy|gentleman|boy|woman|female|lady|girl|person|people|couple)\b",
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
    # 가구 (2026-10-13 실측). 왜(Why) 없으면 안 되나: "이미지 2의 의자" 처럼
    # 정확히 지정해도 사물로 분류되지 않아 **그 슬롯이 두 번째 인물로 남는다**.
    # 실측: "The woman in image 1 is sitting on a chair in image 2." 에서
    # image_2(의자)가 persons 에 들어가 프롬프트에 "person two from reference
    # image 2" 가 나갔다 — 같은 프롬프트의 "sitting on a chair in image 2" 와
    # 정면 모순. 같은 파일 715/722 줄은 bench/chair 를 이미 알고 있었다(목록 불일치).
    "|의자|벤치|침대|소파|테이블|책상|스툴|탁자|선반|가구"
)


_EN_OBJECT_WORDS = (
    "bag|handbag|backpack|purse|watch|wristwatch|necklace|ring|earrings"
    "|glasses|sunglasses|hat|cap|belt|scarf|gloves|umbrella|book"
    "|prop|object|product"
    # 가구 (2026-10-13). 위 한글 목록과 같은 이유 — 짝을 맞춰 둔다.
    "|chair|bench|bed|sofa|couch|table|desk|stool|shelf|furniture"
)


OBJECT_WORDS = _KO_OBJECT_WORDS + "|" + _EN_OBJECT_WORDS


# 슬롯 간격: 줄바꿈을 넘지 않는 공백. 왜(Why) `\s` 를 안 쓰나: 문자 클래스의 `\s`
# 는 `\n` 을 포함해 "피사체: 1번 이미지\n배경: 2번 이미지" 에서 줄을 넘어 매칭한다
# (2026-10-19 실측: 배경 슬롯이 {1} 로 오검출). 역할 패턴과 배경 패턴이 **같은
# 상수 하나**를 쓴다 — 두 벌로 두면 한쪽만 좁아지는 드리프트가 난다.
_S = r"[^\S\n]*"


# 의상 어휘 **뒤에** 착용 동사가 붙으면 그 슬롯은 의상 소스가 아니라 사람이다
# ("2번 드레스를 입은 여성" -> 2번은 사람. 2026-09-29 실측 위험: 그 사람이 신원
# 소스에서 빠져 사라진다). 상수로 뽑은 이유(2026-10-23): 콜론 선언 패턴에도 같은
# 보호가 필요해졌는데, 같은 정규식 조각을 두 곳에 손으로 두면 한쪽만 고친다.
_WEAR_VERB_AFTER = (
    r"(?!\s*(?:을|를|이|가)?\s*(?:입은|입고|입혀|입히|착용|신은|신고))"
    r"(?![^,，]{0,4}(?:wearing|wears|dressed)\b)"
)


# 어휘가 앞 → 슬롯이 뒤인 순서의 창 차단. 사람 단어가 창 안에 있으면 그 슬롯은
# 사람 절에 속한다 -- 왜(Why): "원피스로 갈아입은 여성과 이미지 3"에서 원피스가
# 3번(남성)을 옷 슬롯으로 침범하는 오검출이 실측 확인됐다(정밀 검토 R23).
# 사람 낱말 — **한 곳에서만** 정의한다 (2026-10-23, AC-4). 두 곳이 같은 목록을
# 써야 한다: ① 아래 `_TEMPERED_GAP`(창 차단 — 사람 단어가 창 안에 있으면 그 슬롯은
# 사람 절에 속한다) ② `_person_role_slots`(역할 선언 `1번: 한국 여성`). 목록이
# 갈리면 같은 문장을 한쪽만 사람으로 읽는 조용한 불일치가 생긴다.
# **목록을 넓히지 않은 이유**: 넓히면 창이 더 일찍 끊겨 기존 판정이 바뀐다(회귀).
# SECOND_PERSON_PATTERNS 의 넓은 목록(신랑·아버지·소년·신부…)은 이미지 표기
# 판정 전용이라 여기 합치지 않는다.
_HUMAN_WORDS_KO = ("남성", "남자", "여성", "여자", "인물", "사람")
_HUMAN_WORDS_EN = ("man", "woman", "male", "female", "person")
_TEMPERED_GAP = ("(?:(?!" + "|".join(_HUMAN_WORDS_KO + _HUMAN_WORDS_EN)
                 + r")[^,，.。;；!！?？\n]){0,24}?")


# 의상 역할 어휘 + 슬롯 검출. 왜(Why): outfit 게이트가 "의상 의도 = 모든 duo 소멸"
# (구버전)이 아니라 "의상 슬롯만 제외"로 작동하려면 슬롯 번호를 잡아야 한다
# (정밀 검토 발견 #3). 어휘(_KO_CLOTHING_WORDS·_EN_CLOTHING_WORDS·CLOTHING_WORDS)는
# 모듈 위쪽 OUTFIT_RELATION_PATTERNS 앞에서 한 번만 정의한다(2026-10-11 드리프트 수정).


def _role_patterns(words: str, en_words: str, colon_guard: str = ""):
    """역할(사물/의상) 슬롯 검출 6패턴 골격. 단어만 주입한다. (5패턴 + 콜론 1)

    colon_guard: 6번(콜론) 패턴 뒤에 붙일 제외 조각. 의상은 착용 동사 제외를
    넘겨 "2번: 옷을 입혀"(사람)를 의상 소스로 잡지 않는다.

    왜(Why): 사물·의상 패턴은 절 차단 규칙이 동일하다. 형태:
    1) "이미지 2의 핸드백" (조사 혼용 대응)
    2) "핸드백 이미지 3" — 문장부호 차단(쉼표 너머 오인 방지) + 사람 단어
       차단(창 안 사람 단어가 있으면 그 슬롯은 사람 절 소속)
    3) 영문 "bag as image 2"형, 4) 영문 "image 3 shows a book"형.
    5) "2번 이미지 의자" — 숫자가 먼저 오는 형태(2026-10-13 실측).
       왜(Why) 추가: 사용자가 "2번 이미지 의자에 앉아있다"처럼 쓰면
       기존 4패턴은 "이미지"가 앞에 와야 매칭돼서 놓친다. 그 결과 의자
       슬롯이 사물로 분류되지 않고 두 번째 인물로 남아 프롬프트에
       "person two from reference image 2" 가 나가 의도와 정면 모순.
    """
    return (
        r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])\s*(?:번)?\s*(?:의|에|에서)?\s*(?:" + words + r")",
        r"(?:" + words + r")" + _TEMPERED_GAP + r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])",
        r"\b(?:" + en_words + r")\b" + _TEMPERED_GAP + r"\b(?:from|in|on|as|using|reference)\s+(?:reference\s+)?(?:image|img)\s*_?\s*(\d+)(?![0-9])",
        r"\b(?:image|img)\s*_?\s*(\d+)(?![0-9])\b" + _TEMPERED_GAP + r"\b(?:is|as|shows|contains)\s+(?:a|an|the)?\s*(?:" + en_words + r")\b",
        r"(\d{1,2})\s*(?:번|번째)?\s*(?:image|img|이미지)\s*(?:의|에|에서)?\s*(?:" + words + r")",
        # 6) "2번: 의자" — 줄 선언 표기(2026-10-23 사용자 실측). 왜(Why) 콜론이
        #    있어야 하나: 콜론 없이 "2번 의자" 까지 열면 의상 패턴의 착용 동사
        #    제외를 우회해 "2번 의상을 입혀"(사람)를 의상 소스로 잘못 잡는다
        #    -> 그 사람이 신원 소스에서 빠져 사라진다. 콜론은 "이 번호는 이
        #    역할" 이라는 명시 표지이므로 그때만 번호를 역할에 묶는다.
        #    주의(Why) `(?:번|번째)` 를 **필수**로 둔다: 선택으로 두면 "16:9"
        #    같은 비율 표기가 슬롯 16 으로 오인된다 (R203-9 가 막는다).
        (r"(\d{1,2})" + _S + r"(?:번|번째)" + _S + r"[:：]" + _S
         + r"(?:의|에|에서|은|는|이|가)?" + _S + r"(?:" + words + r")"
         + colon_guard),
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
_CLOTHING_BASE_PATTERNS = _role_patterns(
    CLOTHING_WORDS, _EN_CLOTHING_WORDS, _WEAR_VERB_AFTER)


# 콜론 선언 조각(`3번: 하이 힐`) — `_role_patterns` 6번째(마지막) 패턴이다.
# 왜(Why) 이름을 주나: `_clothing_declared_slots` 가 **같은 조각**을 써야 한다.
# 인덱스로 꺼내면 패턴 순서가 바뀔 때 조용히 어긋난다.
_CLOTHING_COLON_PATTERN = _CLOTHING_BASE_PATTERNS[-1]


CLOTHING_ROLE_PATTERNS = _CLOTHING_BASE_PATTERNS + (
    r"(\d{1,2})\s*(?:번|번째)?\s*(?:은|는|의|에|에서|으로)?\s*(?:" + CLOTHING_WORDS
    + r")" + _WEAR_VERB_AFTER,
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


# 포즈 **역할명사**만 모은 집합. 상태·동작 어휘(앉/sitting/서/standing …)는 뺀다.
# 왜(Why) 따로 두나 (2026-10-11 실측 결함): "포즈 … 이미지 N" 처럼 **라벨이 뒤에
# 오는** 패턴에 상태·동작 어휘까지 허용하면, 영문 어순에서 사용자의 **행동 서술**
# ("… is sitting on the chair in image 2.") 이 "그 이미지에서 자세를 가져오라" 는
# **역할 지정으로 오판**된다. 그러면 의자 같은 사물 슬롯에 "reproduce the body
# pose … never their clothing" 이 나가 **옷 없는 인체를 그리라는 지시**가 되고,
# 결과가 인물 2명 융합으로 무너졌다(실측). 역할 지정은 역할명사로만 온다.
_POSE_ROLE_NOUNS = ("포즈|자세|스탠스|몸매|동작"
                    "|pose|posture|stance|body ?position")


# _role_patterns 는 4패턴을 한 벌로 만든다(1=라벨앞, 2=라벨뒤, 3·4=영문).
# 포즈는 2번만 어휘를 좁혀야 해서 골격을 나눠 받는다.
_POSE_BASE_PATTERNS = _role_patterns(_KO_POSE_WORDS, _EN_POSE_WORDS)


POSE_ROLE_PATTERNS = (
    # 1) "이미지 2의 포즈" / "이미지 2의 앉은 자세" — 라벨이 **앞선다**. 라벨과
    #    역할어 사이에 자유 구간이 없어 오탐 위험이 낮으므로 상태 묘사까지 허용한다.
    _POSE_BASE_PATTERNS[0],
    # 2) "포즈 … 이미지 2" — 라벨이 **뒤에** 온다. 사이에 최대 24자 자유 구간이
    #    있어 행동 서술을 역할 지정으로 삼켰다(위 주석). 여기만 역할명사로 좁힌다.
    r"(?:" + _POSE_ROLE_NOUNS + r")" + _TEMPERED_GAP
    + r"(?:image|img|이미지)\s*_?\s*(\d+)(?![0-9])",
    # 3·4) 영문 전용 — 이미 역할명사(_EN_POSE_WORDS)만 쓴다.
    _POSE_BASE_PATTERNS[2],
    _POSE_BASE_PATTERNS[3],
) + (
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
    # "2번: 포즈" / "No. 2: Pose" — 줄 선언 표기(2026-10-24 사용자 실측).
    # 왜(Why) 역할명사만 받나: `1번: 앉아 있는 여성` 은 **인물 선언**이다. 상태
    # 어휘까지 받으면 그 슬롯이 포즈 참조로 오분류돼 신원 소스에서 빠진다(패턴 2
    # 와 같은 이유). `2번: 앉은 자세` 처럼 상태어 **뒤에** 역할명사가 오는 형태만
    # 상태어 한 낱말을 허용한다. `번` 을 필수로 두어 `16:9` 비율 표기를 막는다.
    r"(\d{1,2})" + _S + r"(?:번|번째)" + _S + r"[:：]" + _S
    + r"(?:의|에|에서|은|는|이|가)?" + _S
    + r"(?:(?:" + _KO_POSE_STATE + r")" + _S + r")?"
    + r"(?:" + _POSE_ROLE_NOUNS + r")",
)


# 한글 수사 슬롯 표기 (2026-10-23). 왜(Why) 입력을 바꾸나: 역할 패턴 15개가
# 슬롯 번호를 **숫자 캡처**로 수집한다(_collect_role_slots 계약 — int(grp) 가
# 실패하면 조용히 버려진다). "둘째: 의자" 가 그래서 미인식이었다. 캡처 그룹을
# 한글 수사로 넓히면 패턴 15개를 전부 고치고 int() 변환도 곳곳에 붙여야 한다.
# 입구에서 표준 표기로 한 번 바꾸면 사물·의상·배경·포즈가 함께 혜택을 받는다.
_SLOT_ORDINAL_MAP = (
    ("첫번째", "1번"), ("첫 번째", "1번"), ("첫째", "1번"),
    ("두번째", "2번"), ("두 번째", "2번"), ("둘째", "2번"),
    ("세번째", "3번"), ("세 번째", "3번"), ("셋째", "3번"),
    ("네번째", "4번"), ("네 번째", "4번"), ("넷째", "4번"),
    ("다섯번째", "5번"), ("다섯 번째", "5번"), ("다섯째", "5번"),
)


# 영어 선언 표기 -> 표준형 (2026-10-24). 왜(Why) 입구에서 하나: 역할 패턴 15개가
# 전부 "N번:" 을 본다. 워크플로가 토픽을 **영어로 미리 번역**해 넣으면
# `No. 2: Chair` · `Number 1: Korean woman` · `#4: Background` 가 되어 사물·인물·
# 배경·의상 슬롯이 **전부** 사라졌다(실측: 같은 실행에서 배경 가드 3종 소실,
# 신발 유지가 신발 교체로 역전, 사진 평균색 오지시).
# 콜론을 **필수**로 둔다 — 없으면 "no. 5 is missing" · "number of people is 2" 를
# 선언으로 오인한다(실측 오탐 후보). `#` 는 앞에 `\b` 가 성립하지 않아 분리한다.
# 간격은 `_S`(줄바꿈 제외) — 배경 패턴과 같은 이유로 줄을 넘지 않는다.
_EN_SLOT_DECL_RE = re.compile(
    r"(?:#|(?:\bno\.?|\bnumber\b))" + _S + r"_?" + _S + r"(\d{1,2})"
    + _S + r"(?:번|번째)?" + _S + r"(?:image|img|이미지)?" + _S + r"[:：]",
    re.IGNORECASE,
)


@lru_cache(maxsize=256)
def _normalize_slots(text: str) -> str:
    """슬롯 표기만 표준형("N번")으로 바꾼다. 다른 글자는 건드리지 않는다.

    한글 수사(`둘째`)와 영어 선언(`No. 2:`)을 같은 표준형으로 모은다(2026-10-24).
    """
    t = text or ""
    for _ko, _std in _SLOT_ORDINAL_MAP:
        t = t.replace(_ko, _std)
    return _EN_SLOT_DECL_RE.sub(r"\1번:", t)


# 비율 표기(`16:9` · `4:3`)를 역할 판정 전에 가린다 (2026-10-23, 작업 14).
# 왜(Why): 포즈·의상 패턴은 "숫자 + 낱말" 형태를 받는다(자연스러운 표기를 살리려고).
# 그래서 `16:9 구도` 의 `9 구도` 가 "9번 구도" 로 읽혀 9번이 포즈 참조가 되고, 선언이
# 기본값을 이기므로 그 슬롯이 외양 참조에서도 빠졌다. 콜론은 막지 못한다 — 콜론이
# 앞에 있고 패턴은 뒤 조각을 본다. 실측: `16:9 구도` -> {9} · `4:3 구도` -> {3} ·
# `16:9 옷` -> 의상 {9}. 진짜 선언(`9번 구도` · `9번 자세`)은 그대로 살아야 하므로
# 낱말 목록을 좁히지 않고 **비율 토큰만** 가린다.
_RATIO_TOKEN_RE = re.compile(r"(?<![0-9])\d{1,3}\s*:\s*\d{1,3}(?![0-9])")


@lru_cache(maxsize=256)
def _mask_ratio_tokens(text: str) -> str:
    """비율 표기를 같은 길이의 공백으로 바꾼다. 다른 글자는 건드리지 않는다.

    같은 길이인 이유: 역할 패턴에는 자유 구간 길이를 제한하는 조각이 있어 길이를
    줄이면 그 창의 거리 계산이 밀린다. 문자 위치를 그대로 두면 그 위험이 없다.

    캐시(2026-10-25 최적화): 순수 함수이고 입력은 문자열 하나뿐이라 결과가
    결정적이다. 실측 2.06us -> 0.05us (약 40배). 역할 슬롯 판정이 실행당
    여러 번 이 함수를 지나므로 마진이 쌓인다. 출력은 완전히 동일하다.
    """
    return _RATIO_TOKEN_RE.sub(lambda m: " " * len(m.group(0)), text or "")


# 장면 표지 — 이 낱말 뒤가 **그림 내용**이다. 사용자 표기와 R189 원문이 실제로
# 쓴다: "피사체: 1번 이미지\n배경: 2번 이미지\n\n연출: \n\n<문장>".
# 영어 표지(2026-10-24): 워크플로가 토픽을 영어로 미리 번역하면 `연출:` 이
# `Directed by:` 가 된다. 표지가 없으면 선언 줄이 장면 문장으로 남아 최종
# 프롬프트에 그대로 실린다(한국어 경로는 걷어낸다 — 실측). `scene`·`setting`
# 같은 일반 낱말은 넣지 않는다: 산문에서 흔해 표지 없는 문장을 잘라낸다.
# `director` 는 실측한 번역형이다(2026-10-24): prompt_in 에 한국어를 넣으면
# tc-big 이 `연출:` 을 `Director:` 로 옮기고 줄바꿈까지 공백으로 합쳤다 —
# 이 낱말이 없으면 그 경로에서만 `No. 1: ... No. 4: Background` 가 남았다.
_SCENE_MARKER_RE = re.compile(
    r"(?:연출|장면|상황|분위)\s*[:：]|(?:directed\s+by|directing|director)\s*[:：]",
    re.IGNORECASE)
# 역할 선언 — "N번: <역할어>" · "피사체: N번 이미지" · "배경: N번". 장면이 아니다.
# `번` 을 필수로 둔다(2026-10-23 T1 과 같은 이유): 없으면 "16:9 비율" 을 삼킨다.
_LABEL_DECL_RE = re.compile(
    r"\d{1,2}\s*(?:번|번째)\s*[:：]\s*[^\n/;,]*"
    r"|(?:피사체|주인공|인물|사물|의상|배경|포즈)\s*[:：]\s*[^\n/;,]*")


@lru_cache(maxsize=128)
def scene_text(topic: str) -> str:
    """역할 선언 줄을 걷어낸 **장면 서술**을 돌려준다 (2026-10-23, AC-10~AC-12).

    왜(Why) 필요한가: 사용자 표기 `1번: 한국 여성 / 2번: 의자 / 연출: <장면>` 에서
    선언부는 슬롯 배정용이지 그림 내용이 아니다. 그대로 번역·조립하면 번역기가
    "1번:" 을 문장으로 읽는다(실측: R189 원문이 이 표기다).

    규칙 — ① 장면 표지(`연출:` 등)가 있으면 그 **뒤**가 장면이다(선언 줄 제거).
    ② 표지가 없으면 **종전과 완전히 동일**해야 한다(AC-11): 원문 그대로.
    ③ 잘라낸 결과가 비면 원문으로 되돌린다(spec 미해결 3).

    영어 선언 줄은 `_normalize_slots` 로 `N번:` 표준형이 된 뒤 한국어 패턴 하나로
    걷힌다(2026-10-24) — 패턴을 언어별로 두 벌 두면 또 갈린다.

    **판정·보정 근거에는 이 함수를 쓰지 않는다.** `fix_background_clause` 가
    `배경: 2번` 선언을 한국어 원문에서 읽어 배경 절을 복원한다(design 4절, AC-18).
    """
    t = (topic or "").strip()
    if not t:
        return t
    m = _SCENE_MARKER_RE.search(t)
    if not m:
        return t
    rest = _LABEL_DECL_RE.sub(" ", _normalize_slots(t[m.end():]))
    rest = re.sub(r"[ \t\r\n]+", " ", rest).strip(" /;,·")
    return rest or t


@lru_cache(maxsize=256)
def _compile_re(pattern):
    """문자열(또는 이미 컴파일된) 정규식을 컴파일해 캐시한다 (2026-10-25 최적화).

    왜(Why): _collect_role_slots 는 모듈 상수 패턴(문자열)을 매 호출
    re.finditer 에 그대로 넘긴다. re 모듈에도 내부 캐시가 있지만 그 경로
    (캐시 딕셔너리 조회 + 인자 검증)를 없애면 역할 슬롯 수집이
    실측 26.6us -> 22.5us (약 15%) 빨라진다. re.compile 은 이미 컴파일된
    패턴을 받으면 그대로 돌려주므로 문자열/컴파일 객체 둘 다 안전하다.
    """
    return re.compile(pattern)


def _collect_role_slots(text: str, patterns) -> set:
    """패턴 집합에서 번호(1~10) 수집. 사물·의상 슬롯 검출 공용 루프."""
    # 여덟 역할이 모두 이 입구를 지난다 — 가리기도 여기 한 곳에 둔다(작업 14).
    t = _mask_ratio_tokens(_normalize_slots((text or "").lower()))
    slots = set()
    for pattern in patterns:
        try:
            for m in _compile_re(pattern).finditer(t):
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
    return set(_clothing_role_slots_cached(text))


@lru_cache(maxsize=64)
def _clothing_role_slots_cached(text: str) -> frozenset:
    # 소스를 한 번만 계산해 목표 판정에도 같은 값을 넘긴다(2026-10-07 라운드 2
    # — 원래는 _outfit_target_slots 안에서 같은 계산을 또 했다).
    src = _clothing_source_slots_cached(text)
    targets = _outfit_target_slots_cached(text)
    return frozenset(src - targets if targets else src)


def _clothing_declared_slots(text: str) -> set:
    """콜론으로 **참조 지정**된 의상 슬롯(예: `3번: 하이 힐`). 없으면 set().

    왜(Why) `_clothing_source_slots_cached` 를 쓰지 않나: 그쪽은 `이미지 2의 옷` 처럼
    이미지 슬롯 참조까지 포함한다. 그 형태는 **교체 지시**다(`wear the outfit from
    image 2` -> 교체, R164 계약). 반면 `N번: <품목>` 은 토픽이 참조 슬롯을
    **선언**한 것이므로, 같은 품목을 서술하는 문장은 참조 재진술이지 교체가 아니다
    (2026-10-24 실측: 선언이 있는데도 `wearing heels` 가 교체로 읽혀 신발 보존
    가드가 꺼지고 하이힐이 바뀌었다). 판정은 `_wear_nouns_mean_change` 가 쓴다.
    """
    return _collect_role_slots(text, (_CLOTHING_COLON_PATTERN,))


@lru_cache(maxsize=64)
def _clothing_source_slots_cached(text: str) -> frozenset:
    # 품사 게이트(2026-10-23, AC-16): 선언 자리에 동사가 온 슬롯은 의상이
    # 아니다(`_decl_verb_slots`). 오늘 사전에서는 이 뺄셈이 항상 빈 집합이다.
    slots = (_collect_role_slots(text, CLOTHING_ROLE_PATTERNS)
             - _decl_verb_slots(text))
    # 구버전 결함 교정(2026-09-29 실측): 골격 패턴 2번은
    # "이미지 2 의상을 이미지 1에 적용" 에서 "의상을 이미지 1" 을 잡아
    # **1번(주인물)까지 의상 소스로** 밀어 넣었다. 의상 슬롯이 늘어나면
    # 1번이 신원 소스에서 제외돼 사람이 사라진다.
    if _has_outfit_apply_verb(text):
        slots -= _collect_role_slots(text, _OUTFIT_APPLY_SLOT_PATTERNS)
    return frozenset(slots)


def _has_outfit_apply_verb(text: str) -> bool:
    """의장 교체/적용 동사가 있는 문장인지(대상 슬롯 오염 교정용)."""
    t = (text or "").lower()
    return bool(re.search(_OUTFIT_VERB, t))


# 텍스트 단독 의상 교체의 영어 의류 어휘. 왜(Why) 슬롯 패턴과 분리하나:
# `_clothing_role_slots` 는 "이미지 N 의 옷" 처럼 슬롯 번호를 요구한다.
# 그런데 "red evening dress 로 교체" 처럼 **옷 자체를 지목**하는 경우는
# 슬롯이 없다. 슬롯을 요구하면 텍스트 단독 교체를 영영 못 잡는다.
# 목록 자체는 위쪽 `_EN_GARMENT_WORDS` 한 곳에 있다(2026-10-24 단일 출처).


# ---------------------------------------------------------------------------
# 의도 분석용 코어 — 태그형 프롬프트 필터 (2026-10-19)
#
# 왜(Why) 필요한가: prompt_in 으로 들어오는 실제 사용자 프롬프트는 **태그 나열**
# 이다("masterpiece, best quality, 1girl, ..."). 역할·의상·시트·다인물 감지는
# 짧은 자연어 문장을 기준으로 설계돼 있어 태그 잡음에 오탐한다. 실측:
#   서술 조각 "wearing a summer dress" → `_is_text_outfit_change` True
#   → 신원 앵커가 "same exact outfit" 보존 분기를 버리고
#     "same overall color identity" 분기로 바뀐다 — **참조 의상 보존이 조용히
#     사라진다**(사용자는 교체를 요청한 적 없음). 문장형 대조 실험으로 확인.
#
# 규칙: **출력 텍스트는 건드리지 않는다.** 의도 감지에만 쓰는 필터다.
#   - 쉼표 4개 미만 = 문장형으로 보고 그대로 돌려준다(기존 동작 100% 보존.
#     테스트 말뭉치 35개 중 쉼표 4개 이상은 0개라 회귀 여지가 없다)
#   - 태그형이면 조각별로 보는데, 다섯 중 하나라도 걸리면 살리고 나머지는 버린다:
#     1) 슬롯 번호 (이미지 2 / image 3 / 2번) — 역할 지정은 절대 놓치면 안 된다
#     2) 지시 동사 — _OUTFIT_VERB 보다 좁은 목록. "wearing" 은 **서술**이라
#        넣지 않는다(오탐의 출발점)
#     3) 역할 어휘 (포즈·의상·배경/pose·outfit·background) — 역할 문장 근거
#     4) 피사체 지시어 (1girl·solo·여성/character) — 사람 가드 근거.
#        버리면 가드가 꺼지므로 넣는다
#     5) 시트 어휘 (시트·turnaround·lineup) — 시트 분기 근거
#   - 전부 버려지면 "" — 감지 대상이 없는 깨끗한 텍스트(오탐 0)
# ---------------------------------------------------------------------------
_INTENT_SLOT_RE = re.compile(
    r"(?:이미지|image|img)\s*_?\s*\d+|\d+\s*번", re.IGNORECASE)
_INTENT_VERB_KO = ("입혀", "입히", "갈아입", "교체", "바꿔", "바꾸", "바뀌",
                   "적용", "변경", "착용", "벗기")
_INTENT_VERB_EN = ("apply", "replace", "swap", "change into", "put on",
                   "dress her", "dress him", "dress the")
_INTENT_ROLE_KO = ("포즈", "자세", "의상", "옷", "옷차림", "배경", "화풍",
                   "스타일", "소품", "제품", "사물", "촬영", "구도", "조명")
_INTENT_ROLE_EN = ("pose", "outfit", "garment", "background", "style",
                   "object", "prop", "product", "composition", "lighting",
                   "camera", "reference")
_INTENT_SUBJECT = ("girl", "boy", "woman", "man", "lady", "guy", "person",
                   "people", "solo", "character", "여성", "남성", "여자",
                   "남자", "사람", "인물", "소녀", "소년")


def intent_core(text: str) -> str:
    """태그형 프롬프트에서 의도 조각만 남긴 분석용 텍스트. 출력엔 쓰지 않는다.

    쉼표가 4개 미만이면 문장형으로 보고 원문을 그대로 돌려준다.
    """
    t = text or ""
    if t.count(",") < 4:
        return t
    # 시트·동물 어휘는 모듈 뒤편에 정의돼 있어 여기서 합친다(모듈 로드 후 호출).
    # 왜(Why) 동물 어휘를 합치나 (2026-10-19 실측): _INTENT_SUBJECT 에는
    # 고양이·강아지·동물 세 개뿐이라, 태그형 프롬프트("...a cat sitting,
    # animal, detailed fur...")에서 동물 조각이 전부 버려져 동물 감지가
    # 소실됐다(_is_animal_subject 가 원문 True → 코어 False). 전체 동물
    # 어휘를 담은 ANIMAL_SUBJECT_KEYWORDS 를 그대로 재사용해 중복을 피한다.
    _subject_vocab = _INTENT_SUBJECT + ANIMAL_SUBJECT_KEYWORDS
    _sheet_vocab = CHARACTER_SHEET_TOPICS + MULTI_PERSON_SHEET_TOPICS
    kept = []
    for frag in t.split(","):
        f = frag.strip()
        if not f:
            continue
        low = f.lower()
        if (_INTENT_SLOT_RE.search(low)
                or any(w in low for w in _INTENT_VERB_KO)
                or any(w in low for w in _INTENT_VERB_EN)
                or any(w in low for w in _INTENT_ROLE_KO)
                or any(w in low for w in _INTENT_ROLE_EN)
                or any(w in low for w in _subject_vocab)
                or any(w in low for w in _sheet_vocab)):
            kept.append(f)
    return ", ".join(kept)


# 착용 서술은 상태 묘사일 수 있다. 특히 "신발을 신고 있다" 처럼 **일반 명사**만
# 있으면 참조 이미지의 신발을 그대로 두어야 한다(2026-10-20 실측: 이 경우
# _is_text_outfit_change 가 True 가 되어 FOOTWEAR_CHANGE_POSITIVE 가 나가고
# 1.9.58 신발 보존 가드가 우회됐다). 구체 품목(단화·구두)이나 색·재질
# 수식어가 붙으면 사용자가 그 신발을 지정한 것이므로 교체로 본다.
_WEAR_GENERIC_KO = re.compile(
    r"(?:" + _loose_alt(_KO_WEAR_BASIC_WORDS + ("신발",)) + r")")
_WEAR_GENERIC_EN = re.compile(
    r"\b(?:shoes?|footwear|outfit|clothing|clothes|garment|apparel|"
    r"wardrobe)\b")
_WEAR_NOUN_KO = re.compile(
    r"(?:" + "|".join(_KO_WEAR_BASIC_WORDS + _KO_WEAR_ACCESSORIES)
    + r"|" + _loose_alt(_KO_WEAR_ITEMS) + r")")
_WEAR_NOUN_EN = re.compile(r"\b(?:" + _EN_GARMENT_WORDS + r")\b")
_WEAR_MATERIAL_KO = (
    "가죽", "스웨이드", "새틴", "실크", "린넨", "니트", "벨벳", "시폰",
    "레이스", "메시", "캔버스", "고무", "에나멜", "캐시미어", "트위드",
    "코듀로이", "퍼",
)
_WEAR_MATERIAL_EN = re.compile(
    r"\b(?:leather|suede|satin|silk|linen|cotton|wool|knit|velvet|chiffon|"
    r"lace|mesh|canvas|rubber|patent|cashmere|tweed|corduroy|fur)\b")
_WEAR_IMPERATIVE_KO = re.compile(
    r"(?:입는다|신는다|입어라|신어라|입으세요|신으세요|입어|신어)")


# 착용 동사 **어간** + 허용 어미 (2026-10-23). 왜(Why) 어간으로 보나: 완전형을
# 나열하면("신어"·"입혀") 자연스러운 활용을 놓친다 — 실측: "3번 하이힐을 신겨"
# 가 미인식이었다. 어간 `신` 을 그냥 찾으면 "신발·신원·신체·신경" 이 전부 걸리므로
# 어미를 제한한다. 어미 집합에 발·원·체·경이 없어 그 낱말들은 걸리지 않는다.
_WEAR_STEMS = ("입", "신", "착용")
# 상태·관형 어미 — **교체 판정에 쓰지 않는다**. "신발을 신고 앉아" 를 교체로
# 뒤집으면 2026-10-20 규칙(일반 명사만 있으면 상태)이 깨진다.
_VERB_ENDINGS_STATE = ("고", "은", "을", "는", "던", "며", "면", "다", "지")
# 교체성 어미 — 명령·청유·과거·연결. 접두가 겹치는 긴 형태는 넣지 않는다
# ("혀서" 는 "혀" 가 이미 덮는다). 짧은 어미의 오탐은 착용 명사 요구가 막는다.
_VERB_ENDINGS_CHANGE = ("혀", "혔", "히", "겨", "겼", "기고",
                        "어", "었", "게", "으세요", "으라", "하", "해", "했")
_VERB_ENDINGS_ALL = _VERB_ENDINGS_STATE + _VERB_ENDINGS_CHANGE

# --- 품사 라우터 (2026-10-23, AC-14~AC-16) ------------------------------------
# 왜(Why) 이 자리인가: 설계 3절은 품사 규칙을 `_KO_SUFFIX_CHARS` 옆에 두라고
# 정했고 그 뜻은 "조사·어미 지식이 한 파일에 있다" 였다. 실제로는 **공유하는
# 표**(`_KO_SUFFIX_CHARS`·`_VERB_ENDINGS_*`·역할 사전)보다 뒤에 와야 해서 어미
# 표 바로 뒤에 둔다. 파일은 설계대로 `cam_subject.py` 하나다(편차 기록).
#
# 품사가 정하는 것은 **축**뿐이다. 역할은 사전이 정한다(설계 2절):
#   명사·수사          -> 역할 사전 조회 (사물·의상·배경·인물)
#   동사               -> 상태/지시 판정 (착용·교체·자세·응시)
#   형용사·부사·관형사  -> 수식 판정 (색·재질·크기·방향, 같은/다른)
#   대명사·감탄사·미상  -> 판정하지 않는다. 종전 경로 그대로 (AC-16)
# 한계(정직하게 남긴다): 어미만으로 동사와 형용사를 가를 수 없다. `-다` 로 끝나는
# 형태는 `predicate` 로 돌려주고 구분은 어휘가 한다. 그래서 형용사는 **목록 +
# 특징 접미(스럽다·롭다·답다)** 로만 잡는다.
_POS_NOUN = "명사"
_POS_PRONOUN = "대명사"
_POS_NUMERAL = "수사"
_POS_PARTICLE = "조사"
_POS_VERB = "동사"
_POS_ADJECTIVE = "형용사"
_POS_DETERMINER = "관형사"
_POS_ADVERB = "부사"
_POS_INTERJECTION = "감탄사"
_POS_PREDICATE = "predicate"
_POS_UNKNOWN = "미상"

# 조사 — 낱말 하나가 조사인 경우. `_KO_SUFFIX_CHARS` 는 **낱말 뒤에 붙는 조각**
# 이라 여기서는 홀로 쓰인 형태를 나열한다. `이`·`가`·`나` 는 관형사·접속과
# 겹쳐 뺐다(`guess_pos("이")` 는 관형사다 — 동형은 한 축으로 고정한다).
_POS_PARTICLES = frozenset((
    "은", "는", "을", "를", "의", "에서", "에게", "한테", "으로", "로",
    "와", "과", "도", "부터", "까지", "보다", "처럼", "만큼", "밖에", "뿐",
    "이나", "이며", "하고", "께", "께서",
))
# 수사 — 숫자(`isdigit`), 한글 수사, 서수 표기(`_SLOT_ORDINAL_MAP` 의 키).
# `한·두·세` 는 수량 관형사와 동형이라 수사 한 축으로 고정한다.
_POS_NUMERALS = frozenset((
    "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉", "열",
    "한", "두", "세",
))
_POS_ORDINALS = frozenset(_ko for _ko, _std in _SLOT_ORDINAL_MAP)
# 관형사 — 명사를 수식한다. `같은`(유지)/`다른`(교체) 판정이 여기 산다.
_POS_DETERMINERS = frozenset((
    "이", "그", "어떤", "무슨", "어느", "새", "헌", "옛", "같은", "다른",
    "모든", "온갖", "각", "여러", "몇", "웬", "첫", "다음", "지난", "요",
    "어떠한", "온",
))
# 대명사 — 지시 대상이 낱말 밖에 있어 역할 사전 조회로 이어지지 않는다(통과).
_POS_PRONOUNS = frozenset((
    "나", "너", "우리", "저", "저희", "너희", "당신", "그녀", "그들",
    "이것", "그것", "저것", "여기", "거기", "저기", "누구", "무엇", "어디",
    "언제", "얼마", "자기", "여러분",
))
# 부사 — 목록 + 특징 접미. 조사 검사가 **먼저**라 `에게` 같은 조사가 접미
# `게` 로 새지 않는다.
_POS_ADVERBS = frozenset((
    "매우", "아주", "너무", "정말", "진짜", "잘", "못", "더", "덜", "가장",
    "조금", "약간", "많이", "빨리", "천천히", "살짝", "살며시", "이미", "아직",
    "벌써", "다시", "또", "함께", "같이", "서로", "곧", "방금", "항상", "자주",
    "가끔", "드디어", "마침내", "점점", "훨씬", "거의", "바로", "일부러",
    "무심코", "함부로", "살그머니",
))
_POS_ADVERB_SUFFIXES = ("히", "게", "씩", "도록")
# 감탄사 — 문장 밖의 느낌. 판정하지 않는다(통과).
_POS_INTERJECTIONS = frozenset((
    "아", "어", "오", "와", "우와", "아이고", "어머", "어머나", "헉", "음",
    "아하", "예", "네", "야", "얏", "호", "쉿", "글쎄", "아니", "천만에",
    "자", "얘", "이봐", "어이",
))
# 형용사 — 어미로 동사와 가를 수 없어 **목록 + 특징 접미**로만 잡는다.
_POS_ADJECTIVES = frozenset((
    "예쁜", "밝은", "어두운", "귀여운", "큰", "작은", "긴", "짧은", "붉은",
    "푸른", "하얀", "검은", "맑은", "따뜻한", "차가운", "좋은", "나쁜",
    "높은", "낮은", "넓은", "좁은", "깊은", "얇은", "두꺼운", "가벼운",
    "무거운", "조용한", "고요한", "잔잔한", "아름다운", "우아한", "단정한",
    "화려한", "수수한", "엷은", "짙은", "옅은", "새로운", "젊은", "늙은",
    "조그만", "큼직한",
))
_POS_ADJ_SUFFIXES = ("스러운", "스럽다", "롭다", "로운", "답다", "답게")
# 동사 어간 — 착용 어간(`_WEAR_STEMS`)에 자세·시선 어간을 더한다. 어미는 T3 의
# 표에 구어 어미(아·어·워·여)를 더한 것을 쓴다 — 어간 + 어미 조합이라야
# "신발·신원·신체" 가 걸리지 않는다(AC-15). 어간 목록이 좁은 것은 의도다:
# 놓친 동사는 게이트가 안 서는 것뿐이고 판정을 뒤집지 않는다.
_POS_VERB_STEMS = _WEAR_STEMS + (
    "앉", "누", "걷", "달리", "기대", "바라보", "응시", "쳐다보", "웃", "울",
)
_POS_VERB_ENDINGS = _VERB_ENDINGS_ALL + ("아", "어", "워", "여")
# 이 축만 역할 사전을 조회한다. 동사·형용사·부사·관형사는 동작·수식이라 사물·
# 의상 사전을 볼 이유가 없고, 대명사·감탄사는 지시 대상이 없다. **미상은 종전
# 경로**(AC-16) — 모르면 예전과 똑같이 사전을 본다.
_POS_ROLE_AXES = frozenset((_POS_NOUN, _POS_NUMERAL, _POS_UNKNOWN))


def _hangul_only(word: str) -> bool:
    """한글로만 된 낱말인지 (영문은 사전 조회로만 명사가 된다)."""
    return bool(word) and all("가" <= c <= "힣" for c in word)


@lru_cache(maxsize=1)
def _pos_role_nouns() -> frozenset:
    """역할 사전에 등록된 낱말을 한 집합으로 모은 것.

    왜(Why) 함수로 두나: 배경 어휘가 파일 **아래쪽**에 있어 모듈 상수로 묶으면
    정의 위치가 강제된다. 한 번만 계산해 캐시한다.
    """
    words = set()
    for _src in (_KO_OBJECT_WORDS, _EN_OBJECT_WORDS, BACKGROUND_ROLE_WORDS,
                 _EN_BACKGROUND_WORDS):
        words.update(_w for _w in _src.split("|") if _w)
    words.update(_KO_WEAR_ITEMS)
    words.update(_KO_WEAR_BASIC_WORDS)
    words.update(_KO_WEAR_ACCESSORIES)
    words.update(_HUMAN_WORDS_KO)
    words.update(_HUMAN_WORDS_EN)
    return frozenset(words)


def guess_pos(token) -> str:
    """낱말 하나의 품사 **축**을 어미·조사 규칙으로 추정한다 (2026-10-23, AC-14).

    돌려주는 축은 9품사(명사·대명사·수사·조사·동사·형용사·관형사·부사·감탄사)
    에 `predicate`(서술어 — 동사/형용사 구분 불가)와 미상을 더한 11종이다.
    검사 순서가 곧 결정 규칙이다(동형 낱말을 한 축으로 고정한다):
    조사 -> 수사 -> 관형사 -> 대명사 -> 부사 -> 감탄사 -> 동사 -> 형용사
    -> `-다`(predicate) -> 명사 -> 미상.
    `명사` 는 "역할 사전에 있거나 한글로만 된 낱말" 이다 — 한글 낱말 대부분이
    명사이고 어미·조사 신호가 없으면 그 판단이 맞다. 영문은 사전에 있을 때만
    명사이고 아니면 미상이다(모르면 종전 경로 — AC-16).
    """
    tok = (token or "").strip().lower()
    if not tok:
        return _POS_UNKNOWN
    if tok in _POS_PARTICLES:
        return _POS_PARTICLE
    if tok.isdigit() or tok in _POS_NUMERALS or tok in _POS_ORDINALS:
        return _POS_NUMERAL
    if tok in _POS_DETERMINERS:
        return _POS_DETERMINER
    if tok in _POS_PRONOUNS:
        return _POS_PRONOUN
    if tok in _POS_ADVERBS or tok.endswith(_POS_ADVERB_SUFFIXES):
        return _POS_ADVERB
    if tok in _POS_INTERJECTIONS:
        return _POS_INTERJECTION
    if verb_stem_present(tok, _POS_VERB_STEMS, _POS_VERB_ENDINGS):
        return _POS_VERB
    if tok in _POS_ADJECTIVES or tok.endswith(_POS_ADJ_SUFFIXES):
        return _POS_ADJECTIVE
    if tok.endswith("다"):
        return _POS_PREDICATE
    if tok in _pos_role_nouns() or _hangul_only(tok):
        return _POS_NOUN
    return _POS_UNKNOWN


def _axis_consults_role_lexicon(axis: str) -> bool:
    """이 품사 축이 역할 사전을 조회하는가 (라우터의 게이트)."""
    return axis in _POS_ROLE_AXES


# 선언 자리의 낱말 — `N번:` 뒤 첫 낱말. 창을 좁게(한 낱말) 잡는다: 넓히면
# 선언 뒤 **문장**의 동사를 끌어와 물건 선언을 동사로 오인한다.
_DECL_TOKEN_RE = re.compile(
    r"(?<![0-9])(\d{1,2})\s*(?:번|번째)\s*[:：]\s*"
    r"([^\s\n/;,，.。|·]{1,16})")


def _decl_verb_slots(text: str) -> set:
    """선언 자리에 **동사 활용형**이 온 슬롯 (`2번: 신겨`). 없으면 set().

    왜(Why) 게이트로 두나: 선언은 "이 슬롯이 무엇인가" 를 말한다. 자리에 동사가
    오면 그것은 물건이 아니라 동작이다. 오늘 사전(사물 39 · 착용 26)에는 동사
    축 낱말이 하나도 없어 이 게이트가 **판정을 바꾸지 않는다**(R208-13 drift).
    목적은 사전이 커질 때 동형 동사가 사물·의상으로 새지 않게 하는 것이다.
    **포즈는 예외다**: `앉은`·`기대는` 처럼 동사 활용형이 정식 등록어라 포즈
    사전에는 이 게이트를 걸지 않는다.
    """
    t = _normalize_slots(text or "").lower()
    slots = set()
    for m in _DECL_TOKEN_RE.finditer(t):
        tok = m.group(2)
        if not tok or guess_pos(tok) != _POS_VERB:
            continue
        # 창 안에 물건·사람 낱말이 있으면 그 선언은 그 낱말의 선언이다
        # ("2번: 걸린 소파" 는 소파 선언이지 동사 선언이 아니다).
        if any(w in t[m.start(2):m.start(2) + 16] for w in _pos_role_nouns()):
            continue
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        if 1 <= n <= 10:
            slots.add(n)
    return slots


def verb_stem_present(text, stems=_WEAR_STEMS, endings=None) -> bool:
    """동사 어간이 허용 어미와 붙어 있는가 (기본은 상태+교체 전체 어미).

    왜(Why) 어미를 제한하나: 어간 `신` 을 그냥 찾으면 "신발"·"신원"·"신체"·
    "신경" 이 전부 동사로 걸린다. 어미 집합에 `발|원|체|경` 이 없으므로
    걸리지 않는다(2026-10-23 실측).
    """
    t = text or ""
    ends = _VERB_ENDINGS_ALL if endings is None else endings
    for _stem in stems:
        for _end in ends:
            if _stem + _end in t:
                return True
    return False


def _wear_stem_change(text: str) -> bool:
    """착용 동사 어간 + **교체성** 어미 + 착용 명사면 교체 지시다.

    상태 어미(고·은)는 여기서 보지 않는다 — 그 경우는 아래 착용 묘사 분기가
    일반 명사/구체 품목을 가려 판정한다(2026-10-20 규칙 유지).
    """
    return (verb_stem_present(text, _WEAR_STEMS, _VERB_ENDINGS_CHANGE)
            and bool(_WEAR_NOUN_KO.search(text or "")))


def _wear_cue_ko(window: str) -> bool:
    if any(color in window for color, _ in _ITEM_COLOR_KO):
        return True
    return any(word in window for word in _WEAR_MATERIAL_KO)


def _wear_cue_en(window: str) -> bool:
    if re.search(r"\b(?:" + _ITEM_COLOR_EN + r")\b", window):
        return True
    if _WEAR_MATERIAL_EN.search(window):
        return True
    return "-" in window


def _wear_nouns_mean_change(text, noun_re, generic_re, cue) -> bool:
    """착용 동사 뒤 의류 명사가 교체 지시인지 판정한다.

    일반 명사(옷·신발·outfit)만 있으면 상태 묘사로 보고 참조를 유지한다.
    구체 품목이거나 색·재질 수식어가 명사 앞뒤에 붙으면 교체로 본다.
    이미지 슬롯 참조("image 2", "이미지 2")가 있으면 명시 참조이므로 교체다.
    다만 토픽이 `3번: 하이 힐` 처럼 그 품목을 **참조 슬롯으로 선언**했으면 서술은
    참조 재진술이므로 교체가 아니다 — 위 이미지 슬롯 참조(교체)보다 **뒤**에
    두어, 둘이 함께 오면 교체가 이기게 한다(R164 계약 보존).
    """
    if re.search(r"(?:image|img)\s*_?\d+|이미지\s*_?\d+", text):
        return True
    if _clothing_declared_slots(text):
        return False
    for m in noun_re.finditer(text):
        if not generic_re.match(text, m.start()):
            return True
        window = text[max(0, m.start() - 24):m.end() + 16]
        if cue(window):
            return True
    return False


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
    return _is_text_outfit_change_cached(t)


@lru_cache(maxsize=64)
def _is_text_outfit_change_cached(t: str) -> bool:
    low = t.lower()
    # 명시 유지는 교체가 아니다 — 먼저 제외한다.
    if re.search(r"\b(?:same|keep|preserve|maintain)\b[^.]{0,24}?\b(?:outfit|clothing|clothes|dress|shoes|footwear)\b", low):
        return False
    if re.search(r"(?:같은|원래|기존)\s*(?:옷|의상|드레스|차림|신발|구두|단화|샌들)", t):
        return False
    # 영어: 명시 교체 동사 + 의류 ("replace A with B dress", "change into ...")
    if re.search(r"\b(?:replac(?:e[sd]?|ing)|chang(?:e[sd]?|ing)|"
                 r"swap(?:ped|ping)?)\b", low) and _WEAR_NOUN_EN.search(low):
        return True
    # 영어: 착용 동사 + 의류. 진행형·3인칭은 상태 묘사일 수 있으므로 일반
    # 명사만 있으면 참조 유지, 구체 품목이나 수식어가 있으면 교체다.
    if re.search(r"\b(?:wear(?:ing|s)?|wore|worn|dress(?:ed)? in)\b", low) \
            and _WEAR_NOUN_EN.search(low):
        return _wear_nouns_mean_change(
            low, _WEAR_NOUN_EN, _WEAR_GENERIC_EN, _wear_cue_en)
    # 영어: 형용사 + 의류 ("different outfit", "new dress", "red evening dress"
    # 뒤에 교체 맥락이 있을 때 — 단독 "red dress" 는 묘사일 수 있다)
    if re.search(r"\b(?:different|new|another|completely different)\b[^.]{0,32}?\b(?:"
                 + _EN_GARMENT_WORDS + r")\b", low):
        return True
    # 한국어: 교체 동사 + 의류 (슬롯 불필요)
    if re.search(_OUTFIT_VERB, low) and (
            _WEAR_NOUN_KO.search(low) or _WEAR_NOUN_EN.search(low)):
        return True
    # 한국어: 명령형 착용("신는다", "입어라") + 의류. 명령은 수식어가 없어도
    # 교체 지시다.
    if _WEAR_IMPERATIVE_KO.search(t) and _WEAR_NOUN_KO.search(t):
        return True
    # 한국어: 착용 동사 어간 + 교체성 어미 (2026-10-23). 위 두 분기가 명시 동사와
    # 완전형(신어·입혀)을 보고, 여기서 **자연스러운 활용**(신겨·입혀서)을 받는다.
    # 상태 어미는 보지 않으므로 "신발을 신고 앉아" 는 여기서 안 잡히고 아래
    # 묘사 분기가 2026-10-20 규칙대로 판정한다.
    if _wear_stem_change(t):
        return True
    # 한국어: 착용 묘사("입고", "신고") + 의류·신발. 영어와 같은 규칙으로
    # 일반 명사만 있으면 상태 묘사로 보고 참조를 유지한다. 구체 품목이나
    # 수식어가 있으면 교체다(2026-10-13 흰샌 단화 지시는 구체 품목이라 유지).
    if re.search(r"(?:입고|입은|신고|신은)", t) and _WEAR_NOUN_KO.search(t):
        return _wear_nouns_mean_change(
            t, _WEAR_NOUN_KO, _WEAR_GENERIC_KO, _wear_cue_ko)
    # 한국어: "다른 옷", "새 드레스" (명시 교체)
    if re.search(r"(?:다른|새|새로운|완전히 다른)\s*(?:옷|의상|드레스|차림|신발|구두|단화|샌들|outfit|dress)", t):
        return True
    return False


# 신발 교체 지시 판별. 왜(Why) 별도 함수인가 (2026-10-15 실측): footwear 가드는
# 인물 + 참조 실행이면 무조건 "keep that footwear(reference)" 를 보낸다
# (camera_director resolve_guard_plan 의 footwear 플락). 그런데 사용자가
# "앞이 막혀 있는 흰색 단화" 처럼 신발을 바꾸라고 하면 두 문구가 같은
# positive 에서 정면 충돌한다 — 2026-10-13 에 identity anchor 는 교체
# 인식으로 고쳤는데 이 가드는 그대로 남아 있었다. 교체 의도
# (=_is_text_outfit_change)면서 신발 어휘가 있는 문장에만 변형을 쓴다.
_SHOE_TOPIC_EN = (r"shoes|shoe|sandals|sandal|boots|boot|heels|heel|"
                  r"sneakers|sneaker|slippers|slipper|loafers|loafer|"
                  r"flats|footwear")
_SHOE_TOPIC_KO = r"단화|구두|샌들|운동화|신발|하이힐|부츠|슬리퍼|플랫"


# 신발 **품목**의 단일 출처 (2026-10-24, R225). 왜(Why) 의상 목록에서 파생하지
# 않나: `_KO_WEAR_ITEMS` 에는 치마·원피스가 함께 있어 "이 선언이 신발인가" 를
# 그 목록만으로 가릴 수 없다. 위 `_SHOE_TOPIC_*` 는 신발 **교체 판정**용으로
# 이미 있으므로 그것을 출처로 삼는다. 다만 아래 두 형태는 실측으로 고정한
# 것이다(프로브 14건, 한영 동등):
#   ① 콜론 패턴은 한영을 **합친** 목록(`FOOTWEAR_WORDS`)을 봐야 한다 — 콜론
#      패턴(6번)은 `words` 만 보는데 `_normalize_slots` 가 `No. 3:` 을 `3번:`
#      으로 바꾸므로, 한국어 목록만 넘기면 `3번: High heels` 가 빈 집합이 된다.
#   ② `high\s*heels?` 를 **먼저** 둔다 — 콜론 뒤는 낱말이 바로 와야 하므로
#      `High heels` 는 `heels` 단독 대안으로는 잡히지 않는다(앞 낱말 때문에
#      매칭 시작 위치가 어긋난다). 실측: 이 항이 없으면 빈 집합, 있으면 {3}.
# 목록이 의상 목록과 갈리지 않게 하는 검사가 테스트에 있다(R225 AC-7):
# `_KO_FOOTWEAR_WORDS` 는 `_KO_WEAR_ITEMS` 의 부분집합이어야 한다.
_KO_FOOTWEAR_WORDS = ("구두", "신발", "샌들", "단화", "운동화", "하이힐",
                      "부츠", "슬리퍼", "플랫", "로퍼", "웨지", "뮬", "하이탑")
_EN_FOOTWEAR_WORDS = r"high\s*heels?|" + _SHOE_TOPIC_EN
FOOTWEAR_WORDS = _loose_alt(_KO_FOOTWEAR_WORDS) + "|" + _EN_FOOTWEAR_WORDS
# 역할 패턴 6종(사물·의상과 **같은 골격**). 착용 동사 제외를 그대로 넘겨
# "2번: 하이힐을 신은 여성"(그 슬롯은 사람이다)을 신발 슬롯으로 잡지 않는다.
_FOOTWEAR_ROLE_PATTERNS = _role_patterns(
    FOOTWEAR_WORDS, _EN_FOOTWEAR_WORDS, _WEAR_VERB_AFTER)


def _footwear_slots(text: str) -> set:
    """신발 참조로 **선언된** 슬롯(예: `3번: 하이 힐`). 없으면 set().

    왜(Why) 의상 슬롯(`_clothing_declared_slots`)과 따로 두나: 그쪽은 "무엇을
    입는가" 를 말하고 이쪽은 "**신발이 어느 참조인가**" 를 말한다. 신발 가드가
    지목할 대상을 알려면 후자가 필요하다(2026-10-24 실측: 선언이 있는데도 신발
    가드가 1번 인물 참조를 지목해 참조 3번의 힐이 쓰이지 않았다).

    산문("힐을 신고 앉아 있다")만으로는 묶지 않는다 — 슬롯 근거가 없다.
    """
    return _collect_role_slots(text, _FOOTWEAR_ROLE_PATTERNS)


# 좌석 어휘 (2026-10-24, R226). 왜(Why) 사물 어휘와 따로 두나: 착석 관계는
# "좌석 위에 앉는다" 는 **관계**다. 사물 어휘(`OBJECT_WORDS`)에 의자가 있어도
# "앉는다" 는 동사와의 결합은 판정하지 않는다. 형태·접촉·방향을 요구하는 사물
# DNA 와 달리 좌석에는 **접촉점**(체중이 좌석 쿠션에)과 **좌석 방향**(개구부가
# 앉는 사람을 향한다)이 별도로 필요하다.
# 범위: 의자·소파·벤치·스툴·안락의자 계열만. 바닥·침대·계단 착석은 범위 밖이다.
_KO_SEAT_WORDS = ("의자", "소파", "벤치", "스툴", "안락의자", "암체어", "좌석")
# `seat(?!t)` 로 "seats" 는 잡되 "seated" 는 잡지 않는다 — "seated" 는 착석
# **동사**(아래 `_SEAT_VERBS`)로만 본다. 좌석 명사와 착석 동사를 갈라야
# "2번: 의자"(빈 의자)와 "여성이 앉아 있다"(좌석 없음)를 구분할 수 있다.
_EN_SEAT_WORDS = r"chair|sofa|couch|bench|stool|armchair|seat(?!t)"
SEAT_WORDS = _loose_alt(_KO_SEAT_WORDS) + "|" + _EN_SEAT_WORDS


# 착석 동사 — 좌석 어휘와 **함께** 있어야 관계가 성립한다. 한국어는 어미가
# 다양해 "앉" 어간 하나로 앉아·앉은·앉는다·걸터앉다를 모두 잡는다. 영문은
# `sits?\b`("sit"/"sits") 와 `sitting`/`seated`/`sit on` 을 따로 둔다.
_SEAT_VERBS = (r"앉|걸터앉|앉히|sits?\b|sitting|seated|sit on|sitting on")


# 좌석 역할 패턴 6종(사물·의상·신발과 **같은 골격**). 착용 동사 제외를 그대로
# 넘겨 "2번: 의자를 입은 여성" 같은 오검출을 막는다.
_SEAT_ROLE_PATTERNS = _role_patterns(
    SEAT_WORDS, _EN_SEAT_WORDS, _WEAR_VERB_AFTER)


def _seat_slots(text: str) -> set:
    """좌석 어휘 + 착석 동사가 함께 있는 절의 사물 슬롯. 없으면 set().

    왜(Why) 둘 다 요구하나 (2026-10-24, R226): "2번: 의자" 만으로는 착석이
    아니다(빈 의자 제품샷). "여성이 앉아 있다" 만으로는 좌석 참조가 아니다.
    둘이 함께 있어야 "그 좌석에 앉는다" 는 관계다. 배경 슬롯은 제외한다 —
    의자를 배경으로만 쓴 입력에 접촉점 문구를 내면 없는 사물을 요구한다.

    반환은 좌석 **어휘** 슬롯이다. 호출자(`resolve_guard_plan`)가 사물 DNA 대상
    (`furniture_slots`)과 교집합을 내 최종 좌석 슬롯으로 좁힌다.
    """
    slots = _collect_role_slots(text, _SEAT_ROLE_PATTERNS)
    if not slots:
        return set()
    try:
        # 착석 동사 판정에는 비율 토큰 가리기가 필요 없다(`16:9` 에 "앉"/"sit" 이
        # 들어갈 수 없다). 가리기는 역할 슬롯 입구(`_collect_role_slots`) 한 곳에만
        # 두는 불변식(R213-13)을 지키려고 여기서는 `_mask_ratio_tokens` 를 부르지
        # 않는다 — 두 번째 입구를 만들면 한쪽만 갱신되는 드리프트가 난다.
        _nt = _normalize_slots((text or "").lower())
        if not re.search(_SEAT_VERBS, _nt):
            return set()
        return slots - _background_role_slots(text)
    except (ValueError, re.error):
        return set()
    except Exception:
        # 배경 슬롯 판정 실패는 좌석 관계를 뒤집지 않는다 — 어휘 슬롯만 유지.
        return slots


# 배경 슬롯에 **함께 선언된** 좌석 (2026-10-30, R255). 왜(Why) `_seat_slots` 로는
# 못 잡나: 6번 콜론 패턴은 `N번:` **바로 뒤**에 좌석 어휘를 요구한다. 사용자가
# `2번: 배경, 의자` 로 쓰면 그 자리에 "배경" 이 오고 쉼표 뒤에 "의자" 가 오므로
# 매칭되지 않는다(_collect_role_slots == set()). 그래서 배경 사진 속 의자에 사람이
# 앉는 장면(패턴 B)에서 좌석 접촉점·가구 DNA 가드가 통째로 꺼졌다(2026-10-30 실측:
# 등받이 판자 분리·부유, 참조에 없는 짚 지붕 생성, 가구 정면 회전).
# 판정: `N번:` 선언 한 줄에 배경 어휘와 좌석 어휘가 **함께** 있으면 그 슬롯이다.
# 쉼표 목록(`배경, 의자`)까지 잡되, 좌석 어휘가 없는 배경 슬롯(`배경, 바다`)은 잡지
# 않는다 — 잡으면 참조에 없는 의자를 만들어낸다(R158 이 배경 사물 가드를 끈 이유).
# 착석 동사도 요구한다(`_seat_slots` 와 같은 규칙 — 명사만으로는 "빈 의자 옆에 선
# 사람" 이다). `.lower()` 를 먼저 태우는 이유도 `_collect_role_slots` 와 같다:
# 영문 `Background` 는 대문자라 소문자화 없이는 배경 어휘에 안 잡힌다(실측).
_BG_SEAT_DECL_RE = re.compile(r"(\d{1,2})\s*(?:번|번째)\s*[:：]\s*([^\n]*)")


def _background_seat_slots(text: str) -> set:
    """좌석 어휘가 **배경 슬롯에 함께 선언된** 번호(예: `2번: 배경, 의자`). 없으면 set()."""
    t = _normalize_slots((text or "").lower())
    if not t:
        return set()
    try:
        if not re.search(_SEAT_VERBS, t):
            return set()
        seat_re = _compile_re(SEAT_WORDS)
        bg_re = _compile_re(_BACKGROUND_WORDS)
        slots = set()
        for m in _BG_SEAT_DECL_RE.finditer(t):
            body = m.group(2) or ""
            if not (seat_re.search(body) and bg_re.search(body)):
                continue
            try:
                n = int(m.group(1))
            except ValueError:
                continue
            if 1 <= n <= 10:
                slots.add(n)
        return slots
    except (ValueError, re.error):
        return set()
    except Exception:
        return set()


def _topic_changes_shoes(text: str) -> bool:
    """텍스트가 신발을 바꾸는 지시인지 (의상 교체 의도 + 신발 어휘).

    명시 유지("keep the same shoes", "원래 단화를")는
    _is_text_outfit_change 가 먼저 False 를 돌려 여기까지 오지 않는다.
    한국어는 \\b 가 글자 경계를 못 만든다(단화|를 둘 다 \\w) — 한국어 쪽은
    경계 없이 부분 문자열로 본다.
    """
    t = (text or "").strip()
    if not t:
        return False
    if not _is_text_outfit_change(t):
        return False
    return bool(re.search(_SHOE_TOPIC_KO, t)
                or re.search(r"\b(?:" + _SHOE_TOPIC_EN + r")\b", t.lower()))


# 맨발 표현 (2026-10-25 감사 F3). 왜(Why) 새로 두나: 신발 유지 가드
# (FOOTWEAR_POSITIVE)는 "참조 신발을 그대로 유지하라"고 지시하고, 짝인
# FOOTWEAR_NEGATIVE 는 "bare feet, barefoot" 를 **금지**한다. 그런데 사용자가
# "A barefoot woman standing on the beach" 라고 쓰면 두 지시가 그 문장과 정면
# 충돌한다(실측: 같은 실행에서 신발 유지 문구와 bare feet 금지가 동시에 나갔다).
# 맨발 주제에서는 신발 잠금을 끄고 맨발을 지시하는 가드로 갈아탄다.
_BAREFOOT_EN_RE = re.compile(
    r"\b(?:bare\s?feet|bare\s?foot|barefoot|shoeless|without\s+shoes|"
    r"no\s+shoes)\b")
_BAREFOOT_KO_RE = re.compile(r"맨발|맨\s*발|발이\s*맨|신발\s*없이|신발을\s*벗")


def _topic_wants_barefoot(text: str) -> bool:
    """주제가 맨발을 요구하는지. 신발 교체 지시(단화 등)면 양보한다."""
    t = (text or "").strip()
    if not t:
        return False
    if not (_BAREFOOT_EN_RE.search(t.lower()) or _BAREFOOT_KO_RE.search(t)):
        return False
    # 신발을 **명시적으로 바꾸라**는 지시가 함께 있으면 그쪽이 구체적이다
    # ("맨발 대신 단화를 신겨" 같은 문장). 그때는 맨발 가드를 켜지 않는다.
    return not _topic_changes_shoes(t)


# 신발 형용사가 **신발이 아닌** 옷 명사에 붙은 입력 감지 (2026-10-22 실측).
#
# 왜(Why) 필요한가: 사용자 토픽의 오타("단환")를 그래프 안의 구글 번역 노드가
# "closed-toed shorts" 로 옮겼고, 그 문장이 프롬프트에 그대로 실려 긴 청바지가
# 청반바지로 잘렸다. 카메라 규칙 폴더에서 "shorts" 는 0건이었다 — 밖에서 들어온
# 문장이다. 카메라가 고칠 수 있는 것이 아니다(원문에 근거가 없다). 사람이 고칠
# 수 있게 **사실만 알린다** — 프롬프트 문구는 건드리지 않는다(2026-10-21 참조
# 잘림 경고와 같은 판단: 문구를 바꾸면 멀쩡한 입력의 결과도 함께 흔들린다).
#
# 어휘는 두 벌만 새로 둔다. 신발 어휘는 _SHOE_TOPIC_EN(이 파일에 이미 있다)을
# 그대로 쓰고, 옷 어휘만 _NON_FOOTWEAR_EN 을 따로 둔다 — _EN_GARMENT_WORDS 는
# 신발류를 **포함**하므로 "신발이 아닌 것" 판정에는 쓸 수 없다.
_FOOTWEAR_ADJ_EN = re.compile(
    r"\b(?:open|closed|peep|round|pointed|square)[\s-]?toe(?:d|s)?\b",
    re.I)
_NON_FOOTWEAR_EN = re.compile(
    r"\b(?:shorts|pants|trousers|jeans|skirt|dress|gown|sweater|shirt|"
    r"blouse|jacket|coat|suit|uniform|bottoms|leggings|tights)\b", re.I)
_SHOE_NOUN_RE = re.compile(r"\b(?:" + _SHOE_TOPIC_EN + r")\b", re.I)
# 형용사와 명사 사이 수식어(색·재질)를 넘길 창. 실측 최장은
# "closed-toed white cotton summer shorts" 37자다.
_FOOTWEAR_MISMATCH_WINDOW = 40


def footwear_noun_mismatch(text):
    """신발 형용사가 신발이 아닌 옷 명사에 붙은 자리를 돌려준다 (로그 전용).

    돌려주는 것은 **원문 표기 그대로의 조각** 목록이다(예: "closed-toed
    shorts"). 판정: 형용사 뒤 창(문장 경계에서 자름) 안에서 처음 만나는 옷
    어휘가
      신발 어휘   -> 정상. 아무것도 돌려주지 않는다.
      그 밖의 옷  -> 그 자리를 돌려준다.
      아는 어휘 없음 -> 침묵한다. 모르는 낱말에 근거를 지어내지 않는다.
    양쪽이 다 있으면 **앞에 온 쪽**이 명사를 수식한다("closed-toed sandals
    and jeans" 는 정상, "closed-toed shorts and shoes" 는 지목).

    한계: 영문 판정이다. 한글 원문만 있고 영문이 없으면 잡지 못한다(한글
    신발 명사 목록이 열려 있어 "신발이 아닌 것" 을 단정할 수 없다). 사용자
    파이프라인은 토픽이 이미 영문이라 이 경로로 잡힌다.
    """
    out = []
    if not text or not isinstance(text, str):
        return out
    for m in _FOOTWEAR_ADJ_EN.finditer(text):
        tail = text[m.end():m.end() + _FOOTWEAR_MISMATCH_WINDOW]
        cut = re.search(r"[.\n;!?]", tail)
        if cut:
            tail = tail[:cut.start()]
        other = _NON_FOOTWEAR_EN.search(tail)
        if not other:
            continue
        shoe = _SHOE_NOUN_RE.search(tail)
        if shoe and shoe.start() < other.start():
            continue
        phrase = text[m.start():m.end() + other.end()]
        if phrase not in out:
            out.append(phrase)
    return out


# 의류 색상 감지 (2026-10-15 실측): "흰색 단화" 지시에도 결과물의 신발은
# 크림/베이지색이 나왔다. 색상어가 의류·신발 명사에 **인접**할 때만
# (색상, 품목) 쌍을 돌려준다 — "흰색 벽" 같은 배경·가구 색은 건드리지
# 않는다. 한글은 명사 위치에서 뒤쪽 8자 window, 영문은 색상어+품목
# (사이 16자 이내, 같은 문장). off-white 는 영문 lookbehind 로 뺀다.
_ITEM_COLOR_KO = (
    ("하얀색", "white"), ("하얀", "white"),
    ("흰색", "white"), ("흰", "white"),
    ("검은색", "black"), ("검정색", "black"),
    ("검은", "black"), ("검정", "black"),
    ("빨간색", "red"), ("빨간", "red"), ("빨강", "red"),
    ("파란색", "blue"), ("파란", "blue"), ("파랑", "blue"),
    ("초록색", "green"), ("초록", "green"),
    ("노란색", "yellow"), ("노란", "yellow"),
    ("분홍색", "pink"), ("분홍", "pink"),
    ("회색", "gray"), ("잿빛", "gray"),
    ("갈색", "brown"),
    ("베이지", "beige"),
    ("아이보리", "ivory"),
    ("보라색", "purple"), ("보라", "purple"),
)
_ITEM_NOUN_KO = (
    r"단화|구두|신발|샌들|운동화|부츠|하이힐|슬리퍼|플랫|로퍼"
    r"|드레스|원피스|셔츠|블라우스|스웨터|코트|재킷|자켓"
    r"|바지|치마|스커트|모자|가방|의상"
)
_ITEM_COLOR_EN = ("white|black|red|blue|green|yellow|pink|gray|grey"
                  "|brown|beige|ivory|purple|orange")
_ITEM_NOUN_EN = (
    r"shoes|shoe|sandals|sandal|boots|boot|heels|heel|flats|sneakers"
    r"|slippers|loafers|dress|skirt|shirt|blouse|sweater|coat|jacket"
    r"|pants|hat|bag|outfit"
)
# 영문 단수 -> 복수 정규화 (프롬프트 문구는 복수로 굳힌다).
_ITEM_NOUN_EN_MAP = {
    "shoe": "shoes", "sandal": "sandals", "boot": "boots", "heel": "heels",
}
_KO_ITEM_EN = {
    "단화": "shoes", "구두": "shoes", "신발": "shoes", "운동화": "sneakers",
    "슬리퍼": "slippers", "플랫": "flats", "로퍼": "loafers",
    "샌들": "sandals", "부츠": "boots", "하이힐": "high heels",
    "드레스": "dress", "원피스": "dress", "셔츠": "shirt",
    "블라우스": "blouse", "스웨터": "sweater", "코트": "coat",
    "재킷": "jacket", "자켓": "jacket", "바지": "pants",
    "치마": "skirt", "스커트": "skirt", "모자": "hat", "가방": "bag",
    "의상": "outfit",
}


def _topic_item_color(text):
    """(색상 영문, 품목 영문) — 색상어가 의류·신발 명사에 인접할 때만.

    없으면 None. 오판이 더 나쁘다(무의미한 색상 보강) — 조건은 인접성
    하나로만 본다. 영문은 같은 문장 안에서 색상어+품목 16자 이내,
    한글은 명사 앞 8자 window 에 색상어.
    """
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    m = re.search(
        r"(?<![\w-])(" + _ITEM_COLOR_EN + r")\b[^.]{0,16}?\b("
        + _ITEM_NOUN_EN + r")\b", low)
    if m:
        color = "gray" if m.group(1) == "grey" else m.group(1)
        noun = m.group(2)
        return color, _ITEM_NOUN_EN_MAP.get(noun, noun)
    for m in re.finditer(_ITEM_NOUN_KO, t):
        window = t[max(0, m.start() - 8):m.start()]
        for ko_color, en_color in _ITEM_COLOR_KO:
            if ko_color in window:
                return en_color, _KO_ITEM_EN.get(m.group(0), "items")
    return None


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
    순환을 피하려고 _clothing_source_slots_cached(원본) 를 쓴다.

    source_slots(2026-10-07 라운드 2): 이미 계산한 소스를 넘기면 같은 정규식
    두 번을 다시 돌리지 않는다. 안 넘기면 원래대로 직접 계산한다.
    """
    if source_slots is not None:
        return _outfit_target_slots_uncached(text, source_slots)
    return set(_outfit_target_slots_cached(text))


@lru_cache(maxsize=64)
def _outfit_target_slots_cached(text: str) -> frozenset:
    return frozenset(_outfit_target_slots_uncached(text, None))


def _outfit_target_slots_uncached(text: str, source_slots) -> set:
    slots = _collect_role_slots(text, OUTFIT_TARGET_PATTERNS)
    src = (_clothing_source_slots_cached(text) if source_slots is None
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


# 역할 선언 — 사용자가 실제로 쓰는 표기 (2026-10-23, AC-4). 두 형태를 읽는다.
#   ① `1번: 한국 여성` — 슬롯 + 콜론 + **사람 낱말**. 콜론을 필수로 둔다: 없으면
#      산문("여성 2명")을 선언으로 오인할 수 있고, 사물 편에서 콜론 없는 형을
#      일부러 열지 않은 것과 같은 이유다(T1 편차 기록).
#   ② `인물: 3번` · `사람: 3번` — 사람 낱말 + 콜론 + 슬롯.
# 사람 낱말은 위 `_HUMAN_WORDS_KO`/`_HUMAN_WORDS_EN` 을 그대로 쓴다(한 곳 정의).
# 창(12자)은 `한국 여성`·`젊은 여성` 정도를 담고, 줄·구분자를 넘지 않는다 —
# 넘으면 다음 선언의 낱말을 끌어온다.
_PERSON_DECL_GAP = r"[^\n/;,，.。|·]{0,12}?"
_PERSON_DECL_PATTERNS = (
    r"(\d{1,2})\s*(?:번|번째)\s*[:：]\s*" + _PERSON_DECL_GAP
    + r"(?:" + "|".join(_HUMAN_WORDS_KO) + r")",
    r"(\d{1,2})\s*(?:번|번째)\s*[:：]\s*" + _PERSON_DECL_GAP
    + r"\b(?:" + "|".join(_HUMAN_WORDS_EN) + r")\b",
    r"(?:인물|사람|person|model)\s*[:：]\s*(?:image|img|이미지)?\s*_?\s*"
    r"(\d{1,2})\s*(?:번|번째)?(?![0-9])",
)
# 주 피사체 선언 — `피사체: 2번 이미지` · `주인공: 2번` (AC-5). 슬롯 번호를 이렇게
# 직접 밝히면 첫 식별 규약보다 그 선언이 이긴다(`_person_object_plan` 참조).
_SUBJECT_DECL_PATTERNS = (
    r"(?:피사체|주인공|subject)\s*[:：]\s*(?:image|img|이미지)?\s*_?\s*"
    r"(\d{1,2})\s*(?:번|번째)?(?![0-9])",
)


def _subject_decl_slots(text: str) -> set:
    """주 피사체로 **선언**한 슬롯 집합 (`피사체: 2번`). 없으면 set()."""
    return _collect_role_slots(text, _SUBJECT_DECL_PATTERNS)


def _person_role_slots(text: str) -> set:
    """인물로 **선언**한 슬롯 집합 (2026-10-23, AC-4 · AC-5).

    왜(Why) 필요한가: 기존 인물 판정(`_second_person_slots`)은 `2번 이미지의 여성`
    처럼 **이미지 표기**를 요구한다. 선언 표기에는 그 낱말이 없어서
    `1번: 의자 / 2번: 한국 여성` 이 주 피사체를 1번(의자) 으로 남겼다(실측).
    주 피사체 선언(`피사체: 2번`)도 그 슬롯은 사람이므로 함께 센다.
    """
    return (_collect_role_slots(text, _PERSON_DECL_PATTERNS)
            | _subject_decl_slots(text))


def _secondary_role_labels(labels, main=None, persons=(), poses=(),
                           clothing=(), appearance=None):
    """보조 역할 목록(주 슬롯·추가 인물·포즈 슬롯·외양 참조 슬롯 제외).

    왜(Why) 9·10번을 빼나: 9·10번의 **기본값**은 외양 참조 가드
    (APPEARANCE_REF_POSITIVE / LLM image_note)가 전담한다. 일반 보조 역할
    목록("배경·의상·소품…")에 9·10번이 섞이면 외양 참조 지시와 충돌해
    LLM·생성 모델이 외양을 무시하게 된다.

    2026-10-23 정정 (AC-19·AC-22): 9·10번도 **선언하면** 1~8번과 똑같은 슬롯이다.
    그래서 "무조건 9·10번 제외"가 아니라 **외양 참조로 남은 슬롯만 제외**한다.
    appearance 인자가 그 집합이다(cam_subject.appearance_ref_slots 로 계산).

    appearance 기본값은 `None` = 종전과 같다(연결된 9·10번 전부 제외). 왜(Why)
    보수적으로 두나: 이 함수 호출부가 인자를 빠뜨렸을 때 9·10번이 외양 가드와
    보조 역할 목록에 **동시에** 들어가면 같은 프롬프트가 서로 반대 지시를 낸다.
    빠뜨림은 조용한 충돌이 아니라 종전 동작이 되게 한다.

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
    label_ns = set()
    for x in (labels or []):
        try:
            label_ns.add(int(str(x)))
        except (ValueError, TypeError):
            continue
    if appearance is None:
        appearance_ns = {n for n in label_ns if n in (9, 10)}
    else:
        appearance_ns = set()
        for a in appearance:
            try:
                appearance_ns.add(int(str(a)))
            except (ValueError, TypeError):
                continue
    result = []
    for x in (labels or []):
        try:
            n = int(str(x))
        except (ValueError, TypeError):
            n = None
        if n is not None:
            if n in appearance_ns:
                continue
            if n in person_ns:
                continue
            if main_n is not None and n == main_n:
                continue
        result.append(str(x))
    return result


def _declared_role_slots(text: str) -> set:
    """토픽이 역할을 **선언**한 슬롯 전부 (`1번: 의자` · `피사체: 2번` …).

    왜(Why) 한 곳에 모으나 (2026-10-23, AC-19): 9·10번만 역할 판정에서 빠져
    있었다. "선언이 이긴다"를 한 함수로 표현해 두면 그 예외를 다시 심을 자리가
    줄어든다 -- 예외는 규칙이 아니라 목록으로 남겨야 눈에 띈다.

    인물·사물·의상·배경·포즈·교체 대상(의상을 입는 사람)을 모두 센다. 이 집합에
    든 슬롯은 외양 참조 **기본값**이 아니라 선언된 역할로 판정된다.
    """
    return (_object_role_slots(text) | _clothing_role_slots(text)
            | _person_role_slots(text) | _background_role_slots(text)
            | _pose_role_slots(text) | _outfit_target_slots(text))


# ---------------------------------------------------------------------------
# 콜론 없는 역할 표기 **안내** (2026-10-23, 사용자 지시).
#
# 왜(Why) 판정을 안 바꾸나: 콜론은 "이 번호는 이 역할" 이라는 **표지**다. 없으면
# `2번 의자`(선언)와 `2번 여성이 웃는다`(문장)를 가를 근거가 사라진다 — 열면
# 문장이 선언으로 읽히고 그 사람이 신원 소스에서 빠진다(2026-09-29 실측 결함
# 경로: "2번 드레스를 입은 여성" -> 2번이 사람이어야 하는데 옷으로 읽혔다).
# 그래서 **읽지 못한 표기를 읽지 못한 채로** 콘솔에만 알려 준다. 사용자 지시:
# "분류는 건드리지 않는 길".
#
# 왜(Why) 사물·인물만 보나 (2026-10-23 실측, 표기 21종 전수 —
# gori_colon2_probe.py):
#   "3번 하이힐" -> 의상 [3]      "4번 배경" -> 배경 [4]
#   "2번 앉은 자세" -> 포즈 [2]
#   위 셋은 **콜론 없이도 이미 읽힌다.** 여기서 안내하면 거짓 안내가 된다.
#   "2번 의자" -> 빈 집합        "1번 한국 여성" -> 빈 집합
#   실제로 읽히지 않는 표기는 이 둘뿐이다(의상·배경·포즈는 각자의 숫자 패턴이
#   이미 숫자만으로 슬롯을 잡는다). 그래서 안내 어휘 = 사물 + 사람.
#
# 알려진 한계(거짓 안내): 사람 낱말은 문장의 **주어**로도 온다
# ("2번 여성이 웃는다"). 그래서 판정이 아니라 안내이고(프롬프트가 안 바뀐다),
# 문구도 조건부("역할로 쓰려면")로 적는다. 아래 두 조건이 그 문장들을 걸러 낸다.
_COLON_LESS_ROLE_WORDS = (OBJECT_WORDS + "|" + "|".join(_HUMAN_WORDS_KO)
                          + "|" + "|".join(_HUMAN_WORDS_EN))
# 역할 낱말 **앞** 수식어 창 (2026-10-23 실측 보정): `1번 한국 여성` 처럼 수식어가
# 한 낱말 끼는 것이 실제 사용 표기다. 창은 같은 줄 안에서 12자까지 열되 ① 문장부호·
# `/` 를 넘지 않고(선언 단위를 지킨다) ② 착용 동사 형태를 품지 않는다.
# 왜(Why) ② 가 필요한가: `2번 드레스를 입은 여성` 은 **문장**이고, 창이 열리면서
# 그 문장의 "여성" 이 걸린다 — 그것이 2026-09-29 실측 결함의 모양이다(그 사람이
# 옷으로 읽혀 신원 소스에서 빠졌다). 안내만 하는 함수라도 그 문장을 안내하면
# "여기서는 콜론을 붙여라" 는 잘못된 조언이 된다.
_WEAR_FORM_IN_GAP = r"입은|입고|입혀|입히|착용|신은|신고|신겨|신어|벗겨"
_COLON_LESS_GAP = ("(?:(?!(?:" + _WEAR_FORM_IN_GAP
                   + r"))[^,，.。;；!！?？\n/]){0,12}?")
# 역할 낱말 **뒤**는 그 줄(조각)의 끝이어야 한다 (2026-10-23 실측 보정).
# 왜(Why) 필요한가: 콜론 없는 선언은 줄이나 `/` 단위로 적는다(`2번 의자`,
# `1번 한국 여성`). 이 조건이 목적어·주어 문장을 통째로 걸러 낸다 —
# `2번 의자를 밀어`(문장) · `2번 여성이 웃는다`(주어) · `2번 의자에 앉아` 가 조용해진다.
_COLON_LESS_SEGMENT_END = r"(?=" + _S + r"(?:$|[\n/;,]))"
_COLON_LESS_ROLE_PATTERN = re.compile(
    # 왜(Why) `번째` 를 `번` 보다 **앞**에 두나: 교대는 순서대로 시도하므로
    # `번` 이 먼저면 "2번째 소파" 에서 남은 "째 소파" 가 수식어 창으로 샌다
    # (2026-10-23 프로브 실측: 제안이 "2번: 째 소파" 로 나왔다).
    r"(\d{1,2})" + _S + r"(?:번째|번)" + _S
    + r"(?!" + _S + r"[:：])"                  # 콜론 표기 = 이미 읽힌다
    + r"(?!" + _S + r"(?:image|img|이미지))"    # "2번 이미지 의자" 도 읽힌다
    + r"(?:의|에|에서|은|는|이|가|을|를)?" + _S
    + r"(" + _COLON_LESS_GAP + r"(?:" + _COLON_LESS_ROLE_WORDS + r"))"
    + r"(?![A-Za-z])"                           # "2번 manager" 의 man 오검출 방지
    + _COLON_LESS_SEGMENT_END
)
# 숫자 **앞**에 이미지 표기가 있으면("이미지 2번 의자") 그쪽 패턴이 읽는다.
# 가변 길이 lookbehind 를 못 쓰므로 접두를 잘라 확인한다. 여기만 `\s`(줄바꿈 포함)
# 인 이유: 역할 패턴 1번은 `\s*` 로 줄을 넘어 "이미지\n2번 의자" 도 읽는다 —
# 이 검사만 좁히면 그 형태가 거짓 안내가 된다.
_IMAGE_MARKER_BEFORE = re.compile(r"(?:image|img|이미지)\s*$")


def colon_less_role_hint(text: str) -> str:
    """콜론 없이 적힌 역할 표기를 찾으면 안내 문장을, 없으면 `""` 을 돌려준다.

    **판정에는 쓰지 않는다** (R211-5 가 그 계약을 고정한다). 이 함수가 하는 일은
    로그 문장 하나를 만드는 것뿐이고, 슬롯 분류 결과는 이 함수가 있든 없든 같다.

    걸러 내는 것(전부 실측): 콜론 표기 · `N번 이미지 <말>` · `이미지 N <말>` ·
    콜론 없이도 읽히는 의상·배경·포즈 · 착용 동사가 붙은 문장 · 역할 낱말 뒤로
    줄이 이어지는 문장. 남는 것이 "선언처럼 보이는데 읽히지 않은 표기" 다.

    문구를 조건부("역할로 쓰려면")로 쓰는 이유는 위 모듈 주석 참조 — 사람 낱말은
    문장의 주어일 수 있으므로, 안내가 틀려도 읽는 사람이 한 줄로 판단할 수 있다.
    """
    t = text or ""
    for m in _COLON_LESS_ROLE_PATTERN.finditer(t):
        if _IMAGE_MARKER_BEFORE.search(t[:m.start()]):
            continue
        return ('[Camera Director] 콜론 없는 역할 표기 "' + m.group(0).strip()
                + '" — 역할로 읽지 않습니다. '
                + "그 칸을 역할로 쓰려면 " + m.group(1) + "번: "
                + m.group(2).strip()
                + " 처럼 콜론을 붙여 주세요 (문장의 일부였다면 그대로 두세요)")
    return ""


def appearance_ref_slots(text: str, labels, llm_roles=None) -> set:
    """외양 참조 **기본값**이 남는 슬롯 = {9,10} ∩ labels - 선언/분석된 슬롯.

    왜(Why) 필요한가 (2026-10-23, AC-19·AC-21·AC-24): 9·10번은 사용자 전용
    '외양 참조' 기능이라 연결만으로 가드가 섰다. 그래서 사용자가 `9번: 의자`
    라고 선언해도 그 선언이 조용히 사라지고(실측: plan objects=[]) 외양 가드가
    그대로 붙었다 — 같은 프롬프트가 "이 칸은 몸 외양" 과 "이 칸은 소품" 을
    동시에 말했다. 규칙을 하나로 접는다:

        선언이 있으면 선언이 이기고, 없을 때만 외양 참조 기본값이다.

    llm_roles 는 **검증을 통과한** LLM 역할 분석(`_reference_roles_from_llm` —
    연결된 슬롯 + 6단어 화이트리스트)이다. 사용자 지시(2026-10-23)대로
    "분석은 LLM, 반영은 우리 규칙" 이므로 역할 분석은 선언과 같은 무게로
    반영하되, `person` 은 해제하지 않는다: 몸 근접 참조도 사람으로 보이므로
    그 값으로 기본값을 끄면 사용자 전용 기능이 조용히 꺼진다.

    **픽셀 item/unknown 은 해제 근거로 쓰지 않는다.** 픽셀로는 옷과 사물을 가를
    수 없다(실측 기록). 픽셀이 몸 근접을 item 으로 보면 기능이 꺼진다.

    다만 **픽셀이 사람을 찾은 슬롯은 해제한다** (2026-10-23 실측 추가). 왜(Why):
    그 슬롯은 `_hint_person_slots` 를 통해 주 피사체·보조 인물이 된다. 같은
    슬롯을 몸 외양 참조로도 남기면 한 프롬프트가 "이 칸이 신원" 과 "이 칸은 몸
    부위" 를 동시에 말한다. 실측(의자 1번 + 여성 9번 + 빈 topic): 픽셀은
    `인물 슬롯 9` 를 찾았는데 그 값이 여기서 빠지지 않아 9번이 승격되지 못했고,
    1번(의자)이 `the only main human identity` 가 됐다. 픽셀 person 은 자세
    랜드마크 + 몸 크기 게이트를 통과한 실측이므로 이 한 가지에는 근거로 쓴다.
    """
    slots = set()
    for x in (labels or []):
        try:
            n = int(str(x))
        except (ValueError, TypeError):
            continue
        if n in (9, 10):
            slots.add(n)
    if not slots:
        return set()
    slots -= _declared_role_slots(text)
    # 픽셀이 사람을 찾은 슬롯은 인물로 쓰이므로 외양 참조가 아니다 (위 설명).
    slots -= _pixel_person_slots()
    for k, v in (llm_roles or {}).items():
        try:
            n = int(str(k))
        except (ValueError, TypeError):
            continue
        role = str(v or "").strip().lower()
        if n in slots and role and role != "person":
            slots.discard(n)
    return slots


def _object_role_slots(text: str) -> set:
    """사물/소품 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): "이미지 2의 핸드백" 같은 사물 지시가 인물 지시와 섞이는 씬에서
    사물 슬롯을 사람으로 오인하는 것을 막는다(다중 인물 자동 분류).
    품사 게이트(2026-10-23, AC-16): 선언 자리에 동사가 온 슬롯은 사물이
    아니다(`_decl_verb_slots`). 오늘 사전에서는 이 뺄셈이 항상 빈 집합이다.
    """
    return (_collect_role_slots(text, OBJECT_ROLE_PATTERNS)
            - _decl_verb_slots(text))


# 배경 역할 어휘 (2026-10-19 사용자 제보). 왜(Why) 사물과 분리하나:
# "배경: 2번 이미지" 로 배경을 지정했는데 image_2 가 **가구·사물 슬롯**으로
# 분류돼 `_furniture_dna_guard` 가 "prop identity guard / contact lock /
# Seat backs, rails and frames / orientation lock" 을 통째로 내보냈다. 그
# 결과 사용자가 어떤 사물도 지시하지 않았는데 16:9 는 우측 벽 아래 턱,
# 9:16 은 사각 돌 의자가 생겨 피사체가 그 위에 앉았다(실측: 생성물 2장).
# 배경은 사물이 아니라 **장면**이다 — 참조의 배경을 배경으로 쓸 뿐, 특정
# 객체의 형태·접촉·방향을 강요하면 모델이 그 객체를 만들어낸다. 그래서
# 사물 DNA 대상에서 **완전히 제외**한다(분위기 슬롯의 "완화"와도 다르다 —
# 완화 문구조차 객체 존재를 암시한다).
BACKGROUND_ROLE_WORDS = (
    "배경|배경지|뒷배경|백그라운드|공간배경|배경화면"
)
_EN_BACKGROUND_WORDS = (
    "background|backdrop|setting|environment"
)
_BACKGROUND_WORDS = BACKGROUND_ROLE_WORDS + "|" + _EN_BACKGROUND_WORDS
# 왜(Why) _role_patterns 를 그대로 안 쓰나 (2026-10-19 실측): 공용 패턴의
# `\s*` 간격이 **줄바꿈을 넘어** 매칭해 "피사체: 1번 이미지\n배경: 2번 이미지"
# 에서 1번을 배경 슬롯으로 잘못 잡았다(실측: background_role_slots == {1}).
# 줄바꿈을 넘지 않도록 간격을 `[ \t]*` 로 좁히고, 배경 어휘가 **앞**에 오는
# 형태("배경: 2번 이미지")와 **뒤**에 오는 형태("2번 이미지 배경")를 모두 잡는다.
_BG_GAP = r"[^\S\n]{0,8}"          # 줄바꿈 제외한 좁은 간격 (`_S` 는 위쪽 공용 정의)
# 슬롯 표기 두 형태: "N번 이미지"(숫자 먼저) 또는 "이미지 N"(단어 먼저).
_BG_SLOT_A = r"(\d{1,2})" + _S + r"(?:번|번째)?" + _S + r"(?:의|에|에서)?" + _S
_BG_SLOT_B = r"(?:image|img|이미지)" + _S + r"_?" + _S + r"(\d+)(?![0-9])"
_BG_CONNECT = r"(?:으로|로|는|은|는요|:)?" + _S
BACKGROUND_ROLE_PATTERNS = (
    # "배경: 2번 이미지" / "배경으로 쓸 이미지 2" / "background image 2"
    r"(?:" + _BACKGROUND_WORDS + r")" + _BG_GAP + _BG_CONNECT
    + r"(?:" + _BG_SLOT_A + r"(?:image|img|이미지)|" + _BG_SLOT_B + r")",
    # "배경 2번" / "background 2" / "배경은 2"
    r"(?:" + _BACKGROUND_WORDS + r")" + _BG_GAP + _BG_CONNECT
    + r"(\d{1,2})" + _S + r"(?:번|번째)?(?![0-9])",
    # "2번 이미지 배경" / "이미지 2를 배경" / "image 2 as background"
    r"(?:" + _BG_SLOT_A + r"(?:image|img|이미지)|" + _BG_SLOT_B + r")"
    + _BG_GAP + r"(?:을|를|은|는|이|가|의|에|에서|으로|로|as|for)?" + _S
    + r"(?:" + _BACKGROUND_WORDS + r")",
    # "2번 배경" / "2 background"
    r"(\d{1,2})" + _S + r"(?:번|번째)" + _BG_GAP + _BG_CONNECT
    + r"(?:" + _BACKGROUND_WORDS + r")",
)


def _background_role_slots(text: str) -> set:
    """배경 역할이 명시된 번호(1~10) 집합. 없으면 set().

    왜(Why): "배경: 2번 이미지", "2번은 배경" 같은 지정을 잡아 image_2 를
    사물 DNA 대상에서 뺀다(위 BACKGROUND_ROLE_WORDS 주석 참조).
    """
    return _collect_role_slots(text, BACKGROUND_ROLE_PATTERNS)


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
    기존 실행과 결과가 완전히 동일하다.

    2026-10-23 정정 (AC-19·AC-23): 9·10번의 `- {9, 10}` 하드코딩을 제거했다.
    그 제외 때문에 `9번: 의자` 선언이 조용히 사라졌다(실측: `_object_role_slots`
    는 {9} 인데 여기 objects 는 []). 선언이 있으면 1~8번과 **같은 사다리**를
    탄다. 외양 참조 기본값은 이 함수가 아니라 `appearance_ref_slots` 가
    판정한다 — 역할 판정과 가드 판정을 분리한다.

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
    objects = _object_role_slots(text) & set(label_ns) - poses
    # 역할 선언(`1번: 한국 여성` · `피사체: 2번`)도 인물 근거다 (2026-10-23,
    # AC-4·AC-5). 위 `_second_person_slots` 는 **이미지 표기**를 요구하므로
    # 선언 표기를 놓친다 — 그 결과 `1번: 의자 / 2번: 한국 여성` 이 주 피사체를
    # 1번(의자) 으로 남겼다(실측). 아래 `main in objects and persons` 가지가
    # 그때 첫 인물을 주 피사체로 올린다(기존 규칙 그대로).
    declared_persons = _person_role_slots(text) & set(label_ns)
    persons = (((set(_second_person_slots(text)) | declared_persons)
                & set(label_ns)) - objects - poses)
    # **교체 대상**은 이쪽에 의상을 입는 사람이므로 인물이다(실측 결함 수정).
    # "1 의상, 2 교체" 에서 2번이 persons 에 없으면 main 이 1번(주피사체=옷)으로
    # 남아 프롬프트가 "use reference image 1 as the only main human identity"
    # 라고 역전 지시한다 -> 2026-09-29 실제 실행에서 확인.
    targets = _outfit_target_slots(text) & set(label_ns)
    persons = (persons | targets) - objects - outfits
    main = label_ns[0] if label_ns else 1
    # `피사체: 2번` 처럼 **주 피사체를 직접 선언**하면 그 슬롯이 주 피사체다
    # (2026-10-23, AC-5). 선언이 없으면 종전 규약(첫 식별 = 주 피사체) 그대로라
    # 기존 실행과 결과가 완전히 동일하다. 기존 교정 사다리(대상·사물·의상·포즈·
    # 힌트)는 손대지 않는다 — 이 가지는 그 앞에 서는 선언 전용이다.
    _decl_main = _subject_decl_slots(text) & set(label_ns)
    if _decl_main:
        main = min(_decl_main)
        persons = persons - {main}
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
    # 사물 슬롯은 후보에서 뺀다 -- 2026-10-16 오딧 실측: "1 의상, 2 의자" 에서
    # 의자가 주 피사체로 지정돼 "use reference image 2 as the main identity"
    # 지시가 나갔다(의자를 사람 신원으로 쓰라는 뜻이 된다).
    if main in outfits:
        rest = [x for x in label_ns
                if x not in outfits and x not in poses and x not in objects]
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
    # 참조 자동 분류 힌트 — 토픽이 슬롯 번호를 하나도 말하지 않았을 때만.
    # 왜(Why) 여기서 덮어쓰나: main 은 지금까지 "첫 연결"이었다. 1번이 옷
    # 사진이면 프롬프트가 그 옷을 사람 신원으로 지목한다. 픽셀에서 사람을
    # 찾았으면 그 칸이 주 피사체다. 토픽이 번호를 말했으면 사용자 판정이 이긴다.
    # 2026-10-19: person 뿐 아니라 outfit/object/item/pose 까지 받는다
    # (LLM 이 역할을 알려 주면 그 값이 픽셀 판정을 덮는다).
    if not _text_names_slots(text):
        _kinds = getattr(_KIND_HINT, "kinds", None) or {}
        _hp = [x for x in _hint_person_slots() if x in set(label_ns)]
        _h_out = sorted(l for l in label_ns if _kinds.get(l) == "outfit")
        _h_obj = sorted(l for l in label_ns
                        if _kinds.get(l) in ("object", "item"))
        _h_pose = sorted(l for l in label_ns if _kinds.get(l) == "pose")
        if _hp or _h_out or _h_obj or _h_pose:
            if _hp:
                main = _hp[0]
                persons = sorted(set(_hp[1:]) - {main})
            outfits = sorted(set(_h_out) - {main})
            objects = sorted(set(_h_obj) - {main} - set(outfits))
            poses = sorted(set(_h_pose) - {main} - set(objects) - set(outfits))
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
# (2026-10-19) 영어 "multiple characters" 가 없어서 명세의 다인물 키워드가
# 빗나갔다 — topic 에 그 단어를 쓰면 어느 분기도 못 타고, 이어서 픽셀 감지가
# 시트로 잡으면 **"Every view is the same ONE SINGLE person"** 이 라인업에
# 들어가는 정반대 지시가 나갔다(실측: 1인=False, 다인=False). 그래서 영어
# 변형("multiple·several·different characters")과 한국어 조합을 함께 넣었다.
# 고의로 뺀 것: "cast" 단독 — "cast shadow"(그림자)에 걸린다. "cast sheet" 만.
MULTI_PERSON_SHEET_TOPICS = (
    "여러 캐릭터", "여러캐릭터", "인물 시트", "인물시트", "다캐릭터", "다 캐릭터",
    "라인업", "lineup", "cast sheet", "ensemble sheet", "오디션 시트",
    "여러 인물", "복수 캐릭터", "다인물 시트",
    "multiple characters", "several characters", "different characters",
    "여러 명의 캐릭터", "여러명의 캐릭터", "다른 캐릭터", "다른캐릭터",
)


def _is_multi_person_sheet(text: str) -> bool:
    """여러 캐릭터가 한 장에 있는 시트인가. 동일인 다중 뷰 시트와 구분한다."""
    t = (text or "").lower()
    return any(k in t for k in MULTI_PERSON_SHEET_TOPICS)


def _is_character_sheet_request(text: str) -> bool:
    """캐릭터 시트 참조 의도가 명시됐는지 판별한다."""
    t = (text or "").lower()
    return any(keyword in t for keyword in CHARACTER_SHEET_TOPICS)
