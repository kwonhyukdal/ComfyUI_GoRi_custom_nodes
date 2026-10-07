# -*- coding: utf-8 -*-
"""물리·공간 접촉 가드 (FAST_MOTION 포함)."""

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
"PHYSICS_CONTACT_RULES", "PHYSICS_MOTION_POSITIVE", "FAST_MOTION_KEYWORDS", "STATIC_SCENE_KEYWORDS", "physics_contact_guard", "physics_grounding_guard"
]


# ---------------------------------------------------------------------------
# 물리·공간 가드 (2026-09-28)
#
# 왜(Why): topic에 "벽에 밀어붙였다/던진다/붙잡는다"라고 써도 노드가 아무 지시도
# 안 붙이면 모델은 그 단어를 그릴 정보로 못 받아 "나란히 서 있는 두 사람"을
# 그린다. 언어를 **이미지의 물리 상태**로 번역해 붙이는 것이 이 가드의 역할이다.
#
# 범위(정직한 한계): 정확한 관절 각도·타격 프레임은 ControlNet OpenPose 영역이며
# 이 가드가 보장하지 않는다. 대신 모델이 수렴하는 해를 "정지 정면 배치"에서
# "접촉·비행·충격" 쪽으로 밀어 올리는 것이 목적이다.
# ---------------------------------------------------------------------------

# 주의(한국어 활용): 동사 어간이 끝 모음이면 활용 때 음절이 변한다.
# "던지"는 "던진다·던져·던졌다"에 문자열로 들어가지 **않는다**(던지→던진+다).
# 그래서 활용 형태를 여러 개 적거나, 끝 자음이 있는 어간(뛰/달리/당기/끌/잡)을 쓴다.
# 이걸 놓치면 무협 액션 장면이 그대로 "나란히 서 있기"로 수렴한다.
# 물리 접촉/동작 → (positive 물리 상태, negative 되돌림 방지)
PHYSICS_CONTACT_RULES = (
    (("밀어붙", "밀어", "붙여", "붙여넣", "벽에", "누르", "눌러", "가뒀", "가두",
      "붙잡", "붙들", "조인다", "꽉 잡", "press against", "pin against",
      "push against", "pressed against"),
     "physical contact between the people: their bodies are touching with no gap "
     "between them, one person's body braced against a surface while the other "
     "leans into them, overlapping silhouettes, weight visibly transferred",
     "standing apart, empty space between the two people, both standing upright "
     "and separate, no contact"),
    (("안고", "안는", "안은", "안키", "안김", "품에", "감싸", "hold",
      "hug", "embrace", "carried"),
     "close hold: arms wrapped around the other person's body, bodies pressed "
     "together, the held person lifted with feet clear of the ground",
     "standing separately, arms at sides, no embrace, both feet on the ground"),
    (("던지", "던진다", "던져", "던졌", "던짐", "던질", "투척", "채비", "throw",
      "hurl", "toss", "fling"),
     "throwing motion: the thrown figure is airborne with both feet off the "
     "ground and the body rotated, the thrower's weight shifted onto the back "
     "leg with the torso leaning away, limbs trailing",
     "both people standing normally, nobody airborne, static pose, no throwing"),
    (("뛰", "달리", "달렸", "질주", "전력질주", "sprint", "run", "dash",
      "chase", "race"),
     "running motion: the body pitched forward, legs split mid-stride, one foot "
     "off the ground, arms driving, clothing and hair pushed backward by motion",
     "standing still, feet together, static posture, no motion"),
    (("넘어", "넘었", "추락", "쓰러", "쓰러져", "굴러", "무너", "fall",
      "tumble", "collapse", "trip"),
     "falling motion: the body tilted off axis and mid-collapse, limbs flung "
     "outward for balance, the ground plane clearly visible beneath",
     "upright standing, balanced on both feet, no fall"),
    (("부딪", "충돌", "충격", "격돌", "튕겨", "부딪혀", "부딪히", "몰아붙",
      "impact", "collide", "slam", "crash", "strike"),
     "impact moment: the bodies locked together at the point of collision, "
     "compressed posture at the contact point, force visibly transferred "
     "through the limbs, hair and clothing whipping away from the blow",
     "gentle contact, relaxed posture, no impact, calm static scene"),
    (("당기", "끌어", "끌고", "잡아당", "grab", "pull", "rope", "chain",
      "사슬", "줄을"),
     "grappling: a closed grip around the other person, arms locked and bent, "
     "both bodies leaning into the pull with feet braced apart",
     "hands at sides, no grip, relaxed arms, no tension"),
    # 무협·격투·전투 — 사용자가 가장 많이 쓰는 시나리오라 맨 뒤(최저 우선순위)에
    # 둔다. 위 규칙(밀어붙/던지/넘어 등)이 있으면 그쪽이 더 구체적이다.
    # "싸"/"검"/"격" 한 글자는 뺐다 — "검은 머리·격차·격리·싸다" 오탐
    # 실측(2026-10-07). "싸우다" 활용형은 모음 결합으로 "싸운다"에
    # "싸우"가 없다 — "싸운/싸워/싸우/싸웠"(3글자 포함) 네 어간으로
    # 덮는다(실측: "싸우"만 있으면 "싸운다"가, "싸워"만 있으면
    # "싸웠다"(싸+웠+다)가 빠졌다).
    (("공격", "무협", "액션", "격투", "전투", "싸움", "싸운", "싸워",
      "싸우", "싸웠", "정면으로",
      "칼", "무기", "attack", "fight", "combat", "battle",
      "sword", "blade", "duel", "fistfight", "grapple"),
     "combat engagement: the two figures are locked in close-quarters contact "
     "mid-exchange, one figure advancing and the other reacting, limbs "
     "interlocked, bodies angled into each other rather than parallel",
     "the two figures standing side by side, facing the same direction, "
     "relaxed neutral posture, no combat contact"),
)


# 빠른 동작 → 시간/속도 표현. 접지·무게중심은 전 인물의 기본값(각주 아님).
PHYSICS_MOTION_POSITIVE = (
    "frozen mid-action at the peak of the motion, believable center of gravity, "
    "correct contact shadows where the body meets the ground, no floating "
    "subjects, no missing weight"
)


# 빠른 동작 키워드 — 이게 있을 때만 속도 표현을 붙인다(정지 장면 오탐 방지).
FAST_MOTION_KEYWORDS = (
    "던지", "던진다", "던져", "던졌", "투척", "채비", "throw", "hurl", "toss",
    "fling", "뛰", "달리", "달렸", "질주", "sprint", "dash", "chase", "race",
    "넘어", "넘었", "추락", "쓰러", "굴러", "무너", "fall", "tumble",
    "collapse", "trip", "부딪", "충돌", "충격", "격돌", "튕겨", "몰아붙",
    "impact", "collide", "slam", "crash", "strike", "싸운", "싸워",
    "싸우", "싸웠", "전투", "격투",
    "무협", "fight", "battle", "공격", "방어", "칼", "무기", "sword",
    "combat", "attack", "밀어붙", "붙잡", "당기", "안고", "고수", "액션",
    "action",
)


# 정적 장면 — 오히려 "노 motion blur"를 붙여 인물이 뭉개지는 걸 막는다.
STATIC_SCENE_KEYWORDS = (
    "정지", "멈춰", "조용한", "정숙", "수목도", "물결", "고요",
    "still", "static", "serene", "calm", "quiet", "peaceful", "motionless",
)


# 영어 어미 표(단어 경계 판정용). 왜(Why) 필요한가: 부분 일치는 tripod→fall,
# dashboard→dash, waterfall→fall, Europe→rope, threshold→hold,
# graceful→grace 로 오탐해 정지 장면에 동작 가드가 붙었다 (2026-10-07 실측).
_EN_INFLECT = r"(?:s|es|ed|d|ing|en|er|ers|est|ness|ly)?"


def _kw_hit(text: str, keywords) -> bool:
    """키워드가 실제 자리에 쓰였는지 판정한다.

    한글은 부분 일치를 그대로 둔다 — 어절 경계가 없어 영문 \\b 규칙을 쓸 수
    없다. 영어는 단어 경계 + 어미만 허용한다:
      - 어간: trip → trips/tripped(자음 중복 trip+ped)/tripping
      - e 제거: collapse → collapsed(collaps+ed)/collapsing
      - 단어 경계가 막는 것: tripod/waterfall/Europe/threshold/graceful
    """
    for kw in keywords:
        if not _ascii_only(kw):
            if kw in text:
                return True
            continue
        alts = [re.escape(kw)]
        if kw.endswith("e"):
            alts.append(re.escape(kw[:-1]))
        if kw[-1].isalpha():
            alts.append(re.escape(kw + kw[-1]))
        if re.search(r"\b(?:" + "|".join(alts) + r")" + _EN_INFLECT + r"\b",
                     text):
            return True
    return False


def physics_contact_guard(topic: str) -> tuple:
    """(positive, negative). 접촉/동작 신호가 없으면 ("", "").

    왜(Why): 사용자가 topic에 쓴 물리 동사는 이미 의도다. 그걸 이미지의
    물리 상태로 번역해 붙이는 것이 이 노드가 실제로 기여할 수 있는 부분이다.
    정밀 각도는 ControlNet 영역이므로 여기서는 수렴 지점을 올리는 데 그친다.
    """
    try:
        t = (topic or "").lower()
        if not t:
            return "", ""
        for keywords, pos, neg in PHYSICS_CONTACT_RULES:
            if _kw_hit(t, keywords):
                # 시간·속도 축: 빠른 동작일 때만 중간 프레임을 명시한다.
                if _kw_hit(t, FAST_MOTION_KEYWORDS):
                    pos = pos + ", " + PHYSICS_MOTION_POSITIVE
                elif _kw_hit(t, STATIC_SCENE_KEYWORDS):
                    neg = neg + ", motion blur on the subject"
                return pos, neg
        return "", ""
    except Exception:
        return "", ""


def physics_grounding_guard(topic: str) -> str:
    """정적 인물 장면에도 붙는 최소 물리(접지·무게중심) 문구. 없으면 ""."""
    try:
        t = (topic or "").lower()
        if not t or not _is_human_subject(t):
            return ""
        if _kw_hit(t, FAST_MOTION_KEYWORDS):
            return ""
        return ("believable center of gravity, correct contact shadows under the "
                "feet, feet firmly on the ground, no floating subjects")
    except Exception:
        return ""
