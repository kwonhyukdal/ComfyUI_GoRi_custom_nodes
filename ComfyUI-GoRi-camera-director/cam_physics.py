# -*- coding: utf-8 -*-
"""물리·공간 접촉 가드 (FAST_MOTION 포함)."""

from __future__ import annotations

import functools
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
# 물리 접촉/동작 → (positive 물리 상태, negative 되돌림 방지, object_veto)
# object_veto (2026-11-10, R263): 영어 동사가 무생물 사물을 목적어로 가질 때 이
# 규칙을 끌지 여부다. 왜(Why) 규칙 밖 인덱스가 아니라 튜플 안인가: 인덱스로 두면
# 규칙 순서를 바꿀 때 조용히 어긋난다. PHYSICS_CONTACT_RULES 를 푸는 곳은 이
# 파일뿐이다(리포 전체 확인: 다른 사용처 0). True 는 "안기" 규칙 하나다 — 그
# 긍정문이 전부 "사람을 안는" 상태라 무생물 목적어면 통째로 틀린다.
# 던지기 규칙(throw)은 object_veto=False 다: 물건을 던질 때도 주체의 자세
# (thrower's weight shifted onto the back leg)는 유효해 단순 차단이 손실을 낳는다.
PHYSICS_CONTACT_RULES = (
    (("밀어붙", "밀어", "붙여", "붙여넣", "벽에", "누르", "눌러", "가뒀", "가두",
      "붙잡", "붙들", "조인다", "꽉 잡", "press against", "pin against",
      "push against", "pressed against"),
     "physical contact between the people: their bodies are touching with no gap "
     "between them, one person's body braced against a surface while the other "
     "leans into them, overlapping silhouettes, weight visibly transferred",
     "standing apart, empty space between the two people, both standing upright "
     "and separate, no contact", False),
    (("안고", "안는", "안은", "안키", "안김", "품에", "감싸", "hold",
      "hug", "embrace", "carried"),
     "close hold: arms wrapped around the other person's body, bodies pressed "
     "together, the held person lifted with feet clear of the ground",
     "standing separately, arms at sides, no embrace, both feet on the ground",
     True),
    (("던지", "던진다", "던져", "던졌", "던짐", "던질", "투척", "채비", "throw",
      "hurl", "toss", "fling"),
     "throwing motion: the thrown figure is airborne with both feet off the "
     "ground and the body rotated, the thrower's weight shifted onto the back "
     "leg with the torso leaning away, limbs trailing",
     "both people standing normally, nobody airborne, static pose, no throwing",
     False),
    # "race" 는 넣지 않는다 (2026-11-11 사용자 실측). 어미 허용 정규식이
    # `race` 를 `racing` 으로 확장해 **서 있는 주제**에도 달리기 자세가 붙었다.
    # 실측: "standing ... like a racing girl"(레이싱걸) · "a racing helmet" ·
    # "NASCAR racing" 이 전부 이 규칙을 켰다. 부작용으로 아래 시간·속도 축이
    # 켜져 physics_grounding_guard 의 "feet firmly on the ground" 도 억제됐다 —
    # 정지 주제에 정반대 문구가 나갔다. 걸음걸이 뜻의 레이스는 run/sprint/
    # dash/chase 가 이미 덮으므로 빼도 회수 손실이 없다. 경주를 뜻하는
    # racing(자동차·말)은 사람 보행이 아니므로 애초에 이 규칙의 대상이 아니다.
    (("뛰", "달리", "달렸", "질주", "전력질주", "sprint", "run", "dash",
      "chase"),
     "running motion: the body pitched forward, legs split mid-stride, one foot "
     "off the ground, arms driving, clothing and hair pushed backward by motion",
     "standing still, feet together, static posture, no motion",
     False),
    (("넘어", "넘었", "추락", "쓰러", "쓰러져", "굴러", "무너", "fall",
      "tumble", "collapse", "trip"),
     "falling motion: the body tilted off axis and mid-collapse, limbs flung "
     "outward for balance, the ground plane clearly visible beneath",
     "upright standing, balanced on both feet, no fall",
     False),
    (("부딪", "충돌", "충격", "격돌", "튕겨", "부딪혀", "부딪히", "몰아붙",
      "impact", "collide", "slam", "crash", "strike"),
     "impact moment: the bodies locked together at the point of collision, "
     "compressed posture at the contact point, force visibly transferred "
     "through the limbs, hair and clothing whipping away from the blow",
     "gentle contact, relaxed posture, no impact, calm static scene",
     False),
    (("당기", "끌어", "끌고", "잡아당", "grab", "pull", "rope", "chain",
      "사슬", "줄을"),
     "grappling: a closed grip around the other person, arms locked and bent, "
     "both bodies leaning into the pull with feet braced apart",
     "hands at sides, no grip, relaxed arms, no tension",
     False),
    # 무협·격투·전투 — 사용자가 가장 많이 쓰는 시나리오라 맨 뒤(최저 우선순위)에
    # 둔다. 위 규칙(밀어붙/던지/넘어 등)이 있으면 그쪽이 더 구체적이다.
    # "싸"/"검"/"격" 한 글자는 뺐다 — "검은 머리·격차·격리·싸다" 오탐
    # 실측(2026-10-07). "싸우다" 활용형은 모음 결합으로 "싸운다"에
    # "싸우"가 없다 — "싸운/싸워/싸우/싸웠"(3글자 포함) 네 어간으로
    # 덮는다(실측: "싸우"만 있으면 "싸운다"가, "싸워"만 있으면
    # "싸웠다"(싸+웠+다)가 빠졌다).
    (("공격", "무협", "액션", "격투", "전투", "싸움", "싸운", "싸워",
      "싸우", "싸웠",
      # "정면으로" 를 뺐다 (R269, 2026-11-11). 정면 응시는 전투가 아니라
      # 구도다 — "정면으로 서 있는 여성"(1인 정지)이 전투 격돌 문구를 받았다
      # (실측). 방향 표기는 카메라·구도 가드가 맡는다.
      "칼", "무기", "attack", "fight", "combat", "battle",
      "sword", "blade", "duel", "fistfight", "grapple"),
     "combat engagement: the two figures are locked in close-quarters contact "
     "mid-exchange, one figure advancing and the other reacting, limbs "
     "interlocked, bodies angled into each other rather than parallel",
     "the two figures standing side by side, facing the same direction, "
     "relaxed neutral posture, no combat contact",
     False),
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
    # "race" 제외 이유는 running 규칙 옆 주석 참조 (2026-11-11). 여기 남으면
    # "racing girl" 이 정지 장면인데도 속도 표현을 붙이고 접지 문구를 막는다.
    "fling", "뛰", "달리", "달렸", "질주", "sprint", "dash", "chase",
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


@functools.lru_cache(maxsize=None)
def _kw_regex(kw: str):
    """영문 키워드 1개의 판정 정규식을 **한 번만** 만든다.

    왜(Why) 캐시인가 (2026-10-11 검토): 키워드 목록은 모듈 상수라 고정인데,
    예전 `_kw_hit` 은 호출마다 `"|".join(alts)` 로 패턴 문자열을 새로 만들었다.
    물리 가드는 실행당 최대 8규칙 × 키워드 수십 개를 훑으므로 그 재구성이
    전부 낭비다. 키워드 문자열이 곧 캐시 키라 결과가 항상 같다.

    왜(Why) `len(kw) > 1`·`if kw` 가드인가: kw="e" 면 `kw[:-1]` 이 빈 문자열이라
    정규식에 **빈 대안**이 생겨 아무 단어 경계나 매치된다(오탐). 빈 kw 는
    `kw[-1]` 에서 IndexError 다. 둘 다 막는다.
    """
    alts = [re.escape(kw)]
    if kw.endswith("e") and len(kw) > 1:
        alts.append(re.escape(kw[:-1]))
    if kw[-1].isalpha():
        alts.append(re.escape(kw + kw[-1]))
    return re.compile(r"\b(?:" + "|".join(alts) + r")" + _EN_INFLECT + r"\b")


# 한글 오탐 차단 (R269, 2026-11-11). 왜(Why) 필요한가: 한글은 어절 경계가
# 없어 `kw in text` 로 훑는데, 키워드가 **다른 낱말 안의 글자**로 걸린다.
# 실측 8건(전부 사용자가 쓸 수 있는 문장, 가드가 한글 원문을 보는 규칙 tier):
#   뛰어난 미모의 여성   -> "뛰"(달리기)   : 뛰어나다는 훌륭하다는 뜻이다
#   달리 말하면 ...      -> "달리"(달리기) : 달리는 다르게라는 뜻이다
#   빨간 칼라 셔츠       -> "칼"(전투)     : 칼라는 옷깃이다
#   무기력한 표정        -> "무기"(전투)   : 무기력은 힘없음이다
#   누르스름한 노란 ...  -> "누르"(접촉)   : 누르스름은 노르스름이다
#   이름을 붙여 놓은 벽  -> "붙여"(접촉)   : 붙여는 이름을 정한다는 뜻이다
#   당기순이익을 ...     -> "당기"(잡아당김) : 회계 기간이다
#   정면으로 서 있는 ... -> "정면으로"(전투): 정면은 구도이지 전투가 아니다
# 처방은 두 갈래다 — ① 목록에서 뜻이 틀린 키워드(`정면으로`)는 아예 뺐다,
# ② 나머지는 **관찰된 오탐 표기만** 같은 길이 공백으로 가린다(같은 저장소
# cam_subject 의 _ANIMAL_FALSE_FRIEND_RE 와 같은 방식). 낱말 경계 규칙
# (cam_subject 의 _ko_word_present)은 여기 못 쓴다 — 이 파일의 한글 키워드는
# **어간**이라("밀어붙/붙여/뛰") 뒤에 어미가 붙는 것이 정상이고("밀어붙였다"
# 는 맞다), 경계 규칙을 그대로 대면 정상 발동까지 막힌다(실측).
_KO_FALSE_FRIEND_RE = re.compile(
    # 뛰어나다(훌륭하다)의 활용형. "뛰어난"/"뛰어남" 은 어간 "뛰어나" 의
    # 마지막 음절이 줄어든 형태라(나+ㄴ -> 난) 부분 문자열로 안 잡힌다 —
    # 그래서 세 형태를 함께 적는다. 동사 "뛰어간다"(진짜 달리기)는 건드리지
    # 않는다("뛰어" 만으로 가리면 그쪽이 막힌다).
    r"뛰어나|뛰어난|뛰어남"
    r"|달리\s*(?:말하|표현하|생각하|보면|이야기하|얘기하)"  # = 바꿔 말하면
    r"|칼라"                      # 칼라 = 옷깃
    r"|무기력"                    # 무기력 = 힘없음
    r"|누르스름"                  # 누르스름 = 노르스름
    r"|이름\s*(?:을|이)?\s*붙여"  # 이름을 붙여 = 이름을 정해
    r"|당기\s*(?:순|말|손)"       # 당기순이익 = 회계 기간
)


# 영어 오탐 차단 (R269, 2026-11-11). "dashing" 은 **형용사(멋진)** 로도 쓰여
# "a dashing young man"(멋진 남성)이 달리기 규칙을 켰다(실측). 동사 dashing 은
# 방향 전치사가 뒤따르므로(across/through/into...) 그 형태는 그대로 둔다 —
# "a man dashing across the street" 는 진짜 달리기다(R268-3 계약 유지).
_EN_FALSE_FRIEND_RE = re.compile(
    r"\bdashing\b(?!\s+(?:across|through|into|onto|along|down|up|over|past|"
    r"toward|towards|out|away|off|around|round|to|for|at)\b)"
)


def _mask_kw_false_friends(text: str) -> str:
    """어미·조사 없이 걸리는 오탐 표기를 같은 길이 공백으로 가린다.

    같은 길이로 가리는 이유: 가림 뒤에도 글자 위치가 변하지 않아야 부정어
    판정(_negated_at)의 위치 계산이 어긋나지 않는다(cam_subject 의
    _mask_animal_false_friends 와 같은 규약). 실패해도 원문을 돌려준다.
    """
    try:
        t = text or ""
        out = _EN_FALSE_FRIEND_RE.sub(lambda m: " " * len(m.group(0)), t)
        return _KO_FALSE_FRIEND_RE.sub(lambda m: " " * len(m.group(0)), out)
    except Exception:
        return text or ""


# 부정어 판정 (R269, 2026-11-11). 왜(Why) 필요한가: "뛰지 않고 일자로 서 있다"
# 를 번역기가 정확히 "standing up without running" 으로 옮겨도, 가드는
# "running" 만 보고 달리기 자세를 붙였다 — **뜻을 부정한 문장에 정반대 자세**다
# (실측 7문장 중 6문장 발동). 처방은 두 갈래다. 한국어 부정은 어간 **뒤**에
# 붙고(뛰+지 않/지 못/지 말), 영어 부정은 키워드 **앞**에 온다(without/not/
# never/no). 어절을 넘어가면 다른 절의 부정어를 끌어오므로(예: "not standing
# but running") 가장 가까운 절 조각만 본다.
_EN_NEG_RE = re.compile(r"\b(?:not|never|without|no|nor|none|cannot|can't|"
                       r"avoid\w*|n['\u2019]t)\b")
_KO_NEG_AFTER_RE = re.compile(r"^(?:지|하)?\s*(?:않|못|말고|말라|말아|아니)")
_EN_CLAUSE_SPLIT_RE = re.compile(
    r"[,;.!?\n]|\b(?:but|yet|however|then|and)\b", flags=re.I)


def _negated_at(text: str, start: int, end: int, korean: bool) -> bool:
    """키워드가 부정문 안에 있는가 (start/end 는 매치 위치).

    실패해도 False — 부정 판정이 안 되면 종전대로 발동한다(가드가 조용히
    사라지는 쪽보다 낫다).
    """
    try:
        if korean:
            return bool(_KO_NEG_AFTER_RE.match(text[end:end + 8]))
        before = text[max(0, start - 40):start]
        parts = _EN_CLAUSE_SPLIT_RE.split(before)
        return bool(_EN_NEG_RE.search(parts[-1].lower()))
    except Exception:
        return False


def _kw_hit(text: str, keywords) -> bool:
    """키워드가 실제 자리에 쓰였는지 판정한다.

    한글은 부분 일치를 그대로 둔다 — 어절 경계가 없어 영문 \\b 규칙을 쓸 수
    없다. 영어는 단어 경계 + 어미만 허용한다:
      - 어간: trip → trips/tripped(자음 중복 trip+ped)/tripping
      - e 제거: collapse → collapsed(collaps+ed)/collapsing
      - 단어 경계가 막는 것: tripod/waterfall/Europe/threshold/graceful
    """
    text = _mask_kw_false_friends(text)
    for kw in keywords:
        if not kw:
            continue
        if not _ascii_only(kw):
            start = 0
            while True:
                i = text.find(kw, start)
                if i < 0:
                    break
                if not _negated_at(text, i, i + len(kw), True):
                    return True
                start = i + 1
            continue
        for m in _kw_regex(kw).finditer(text):
            if not _negated_at(text, m.start(), m.end(), False):
                return True
    return False


# 무생물 목적어 목록 (2026-11-10, R263). 왜(Why) 목록인가: 오탐이 규칙 수보다
# 중요하므로 좁게 둔다. 넓히면 "holding a sword"(전투 규칙과 얽힌다) 처럼 다른
# 규칙의 동작까지 바꾸고, 좁히면 "holding a parasol" 만 못 잡는다. 들고 다니는
# 개인 사물만 넣고 무기·동물은 넣지 않는다(종전 동작을 바꾸지 않기 위해).
_INANIMATE_OBJECTS = frozenset((
    "parasol", "umbrella", "bag", "handbag", "purse", "backpack", "suitcase",
    "briefcase", "phone", "smartphone", "tablet", "cup", "glass", "mug",
    "bottle", "vase", "flower", "flowers", "bouquet", "book", "books",
    "magazine", "camera", "tray", "box", "basket", "fan", "cane", "balloon",
    "lamp", "lantern", "sign", "placard", "newspaper", "letter", "card",
    "ticket", "microphone", "mic", "pen", "pencil", "notebook", "wallet",
    "gift", "present", "plate", "bowl", "spoon", "fork", "pillow", "cushion",
    "blanket", "teddy", "doll", "plush", "toy", "candle", "brush", "comb",
    "door",
))

# 안기 동사 + (관사·소유격을 건너뛴) 목적어 첫 명사.
_HOLD_VERB_EN = (r"(?:hold|holds|holding|held|carry|carries|carrying|carried|"
                 r"hug|hugs|hugging|hugged|embrace|embraces|embracing|embraced)")
_HOLD_OBJECT_RE = re.compile(
    r"\b" + _HOLD_VERB_EN + r"\b\s+"
    r"(?:(?:a|an|the|his|her|their|its|my|your|our|this|that|these|those|"
    r"one|two|\d+)\s+)?([a-z]+)")


def _hold_object_only(text: str) -> bool:
    """영문 안기 동사의 목적어가 **전부** 무생물 사물이면 True.

    왜(Why): "holding a parasol"(양산을 들고) 의 holding 이 어미 허용 정규식으로
    "사람을 안고 있다" 로 오탐해 긍정문에 "the other person" 을 넣었다. 그래서
    1인 주제가 2인으로 렌더됐다(2026-11-10 사용자 실측 — 번역 노드가 "들고" 를
    "holding" 으로 바꾼 뒤 영문 가드가 잡았다). 목적어를 보고 무생물이면 사람을
    안는 장면이 아니라고 판정한다.

    목적어 패턴이 하나도 없으면 False 다 — 근거 없이 규칙을 끄지 않는다.
    하나라도 사람 목적어(목록 밖 명사)가 있으면 False 다.
    """
    objs = [m.group(1) for m in _HOLD_OBJECT_RE.finditer(text)]
    if not objs:
        return False
    for obj in objs:
        if (obj not in _INANIMATE_OBJECTS
                and obj.rstrip("s") not in _INANIMATE_OBJECTS):
            return False
    return True


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
        # 동물 주제에는 사람 관절·보행 문장을 붙이지 않는다 (2026-10-30 감사 F2).
        # 아래 규칙 문장은 전부 사람 해부를 전제한다("legs split mid-stride,
        # arms driving"). 같은 파일 physics_grounding_guard 는 _is_human_subject
        # 로 막는데 이 접촉·동작 경로는 안 막아, "달리는 말" 에 사람 다리 문장이
        # 붙었다(실측: "a horse running along the beach" -> human-motion text).
        # 사람이 함께 명시되면 _is_animal_subject 가 False 이므로(사람 우선)
        # 사람 장면은 그대로 둔다.
        if _is_animal_subject(t):
            return "", ""
        for keywords, pos, neg, object_veto in PHYSICS_CONTACT_RULES:
            if _kw_hit(t, keywords):
                # 무생물 목적어면 이 규칙만 건너뛴다 (R263). 다음 규칙은 그대로 본다.
                if object_veto and _hold_object_only(t):
                    continue
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
