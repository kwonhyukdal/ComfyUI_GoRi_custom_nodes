# -*- coding: utf-8 -*-
"""tc-big-ko-en 한국어→영어 번역 어댑터 (카메라 노드 규칙 tier 전용).

왜(Why) 이 파일이 필요한가
--------------------------
규칙(auto) tier 에서는 카메라가 사용자의 한글 prompt_in / topic 을
그대로 샘플러로 보낸다. 그럼 한글이 영문 프롬프트에 섞여 나간다. LLM tier 는
이미 cam_llm.py 가 영문으로 확장하지만, 규칙 tier 에는 번역 주체가 없었다.
이 어댑터가 그 빈칸을 메운다 — 모델은 Helsinki-NLP/opus-mt-tc-big-ko-en (cc-by-4.0).

설계 결정 (실측 기반, 2026-10-13)
---------------------------------
1) **CTranslate2 는 쓰지 않는다.** TransformersConverter 가 만드는
   shared_vocabulary.json 이 영어 전용이라 한글 소스 토큰을 표현 못 해
   추론이 <unk> 폭탄/무한반복으로 퇴행한다. 그래서 **transformers 경로**만 쓴다.
2) **MarianTokenizer 버그 우회.** tokenizer_config.json 의 separate_vocabs:false
   때문에 transformers 5.8 이 vocab.json(영어)을 소스 어휘로 로드해 한글이
   <unk> 처리된다. 그래서 source.spm 으로 강제 인코딩한다 (target.spm 으로 디코딩).
3) **지연 로딩 + 싱글톤.** 840MB 모델은 첫 번역 호출 시 1회만 메모리에 올리고
   캐시한다. 모델 부재/실패 시 None 을 반환해 호출자가 원문을 그대로 쓰게 한다
   (노드가 절대 크래시하지 않아야 함).
4) **비ASCII(한글) 감지 후에만 동작** → 영어 사용자는 영향 0, 불필요한 로딩 없음.

모델 위치 해석 순서
-------------------
1. 환경변수 GORI_TRANSLATE_MODEL (절대경로 디렉토리)
2. 노드 내 models/translation/tc-big-ko-en
3. ComfyUI/models/translation/tc-big-ko-en   (레포 밖, 번들되지 않음)
"""
from __future__ import annotations

import os
import re
import threading
from collections import OrderedDict

try:
    from .cam_util import _log          # noqa: F401
except ImportError:                     # 스탠드얼론/테스트 실행용
    try:
        from cam_util import _log       # noqa: F401
    except ImportError:
        # cam_util 로그를 못 불러온 단독 실행용 폴백 로거
        def _log(msg):                  # type: ignore
            print("[cam_translate]", msg)


# --------------------------------------------------------------------------
# 모델 경로
# --------------------------------------------------------------------------
def _resolve_model_dir() -> "str | None":
    env = os.environ.get("GORI_TRANSLATE_MODEL")
    if env and os.path.isdir(env) and os.path.exists(os.path.join(env, "config.json")):
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        # 2) 노드 번들 위치
        os.path.join(here, "models", "translation", "tc-big-ko-en"),
        # 3) ComfyUI/models (노드 레포 밖)
        os.path.join(here, "..", "..", "..", "models", "translation", "tc-big-ko-en"),
    ]
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isdir(c) and os.path.exists(os.path.join(c, "config.json")):
            return c
    return None


# --------------------------------------------------------------------------
# 비ASCII(한글) 감지
# --------------------------------------------------------------------------
def _has_cjk(text: str) -> bool:
    if not text:
        return False
    for ch in text:
        o = ord(ch)
        # 호환/조합 자모 + 한글 음절 + 가타카나/히라가나 + 한글 호환 자모
        if (0x1100 <= o <= 0x11FF) or (0xAC00 <= o <= 0xD7A3) or \
           (0x3040 <= o <= 0x30FF) or (0x3130 <= o <= 0x318F):
            return True
    return False


# --------------------------------------------------------------------------
# 엔진 상태 (지연 로딩 싱글톤)
# --------------------------------------------------------------------------
_LOCK = threading.Lock()
_STATE = {
    "model": None, "src_sp": None, "tgt_sp": None,
    "ready": False, "failed": False,
}
_EOS = 2          # Marian eos_token_id for this model
_PAD = 32000      # decoder_start / pad — 출력에서 제거해야 함

# 번역 결과 캐시 (2026-10-19).
# 왜(Why): 같은 topic 으로 이미지를 여러 장 뽑으면 실행마다 같은 문장을 다시
# 번역했다. 실측 0.22초/회 — 실행 시간의 98% 가 번역이었다 (20회 4.39초).
# 번역은 같은 입력에 같은 출력이라 캐시가 안전하고, 64개면 메모리도 무시할 수준.
# 실패는 캐시하지 않는다 (일시적 OOM 을 영구 실패로 굳히지 않기 위해).
_CACHE_MAX = 64
_CACHE: "OrderedDict[str, str]" = OrderedDict()


def _cache_get(text: str):
    with _LOCK:
        if text in _CACHE:
            _CACHE.move_to_end(text)
            return _CACHE[text]
    return None


def _cache_put(text: str, en: str) -> None:
    with _LOCK:
        _CACHE[text] = en
        _CACHE.move_to_end(text)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def _load() -> bool:
    """_LOCK 보유 상태에서 호출. 성공/실패를 _STATE 에 기록하고 bool 로 반환."""
    if _STATE["ready"] or _STATE["failed"]:
        return _STATE["ready"]
    d = _resolve_model_dir()
    if not d:
        _log("[Camera Director] ⚠ tc-big 번역 모델을 찾지 못해 번역 비활성 "
             "(GORI_TRANSLATE_MODEL 또는 ComfyUI/models/translation/tc-big-ko-en)")
        _STATE["failed"] = True
        return False
    try:
        import torch
        from transformers import MarianTokenizer, MarianMTModel
        import sentencepiece as spm

        tok = MarianTokenizer.from_pretrained(d)        # (경고 무시: encoder=dict 버그와 무관)
        model = MarianMTModel.from_pretrained(d, torch_dtype=torch.float32)
        model.eval()
        src = spm.SentencePieceProcessor()
        src.load(os.path.join(d, "source.spm"))
        tgt = spm.SentencePieceProcessor()
        tgt.load(os.path.join(d, "target.spm"))
        _STATE["model"] = model
        _STATE["src_sp"] = src
        _STATE["tgt_sp"] = tgt
        _STATE["ready"] = True
        _log("[Camera Director] tc-big 번역 엔진 로드 완료 (한글→영어)")
        return True
    except Exception as e:  # 모델/의존성 문제는 번역만 끄고 노드는 정상 동작
        _STATE["failed"] = True
        _log(f"[Camera Director] ⚠ tc-big 번역 엔진 로드 실패 — 번역 비활성: {e}")
        return False


def translate_ko_to_en(text: str) -> "str | None":
    """한글 텍스트를 영어로 번역. 번역 불가/실패 시 None 을 반환(호출자가 원문 유지).

    - 빈 문자열 / 비ASCII 없음 → None (모델 로딩 안 함, 영어 사용자 영향 0)
    - 모델 부재/로딩 실패 → None
    - 추론 오류 → None
    - 같은 문장은 캐시에서 즉시 반환 (모델 재추론 없음)
    """
    if not text or not _has_cjk(text):
        return None
    hit = _cache_get(text)
    if hit is not None:
        return hit
    with _LOCK:
        ok = _load()
    if not ok:
        return None
    try:
        src_sp = _STATE["src_sp"]
        tgt_sp = _STATE["tgt_sp"]
        model = _STATE["model"]
        # source.spm 강제 인코딩 (MarianTokenizer 의 vocab.json 로딩 버그 우회)
        ids = src_sp.encode(text, out_type=int) + [_EOS]
        import torch
        tin = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            out = model.generate(
                input_ids=tin, max_new_tokens=160, num_beams=4,
                decoder_start_token_id=_PAD)
        out_ids = out[0].tolist()
        if _EOS in out_ids:                      # 이오스 이전까지만
            out_ids = out_ids[:out_ids.index(_EOS)]
        out_ids = [i for i in out_ids if i != _PAD]   # 패드(32000) 제거
        en = tgt_sp.decode(out_ids).strip()
        if not en:
            return None
        _cache_put(text, en)
        return en
    except Exception as e:
        _log(f"[Camera Director] ⚠ 번역 추론 오류 — 원문 사용: {e}")
        return None


# --------------------------------------------------------------------------
# 포즈 절 보정 + 포즈 분기 문장 (2026-10-13)
# --------------------------------------------------------------------------
# 왜(Why) 필요한가: tc-big 가 포즈 절을 뭉갠다. 실측:
#   "의자에 정면을 바라보고 앉아있다." -> "Sitting in front of the chair."
#   (`정면` 탈락 + `의자에 앉아` 가 `in front of` 로 flatten).
# 참조 사진 1장 통째 vs 앉음 한 절이라 앉음 지시가 참조 포즈를 못 이긴다.
# 한글 원문을 근거로 영문 절을 바로잡는다. 해당 없으면 입력 그대로.
_POSE_FACING_KO = ("정면", "앞을 보", "앞 보고", "정면으로", "앞모습")
_POSE_SIT_VERB = ("앉",)


def fix_pose_clause(ko_text, en_text):
    """번역기가 뭉갠 포즈 절을 한글 원문 근거로 바로잡는다. 실패해도
    원문을 돌려준다 (절대 크래시 금지).

    규칙:
      ON  — 한글에 "앉 + 장소에" + "앞에" 없음 + 영문에
            "in front of the <장소>" → "on the <장소>" 로 교체.
            ("의자 앞에 앉아" 는 진짜 in-front 라서 건드리지 않는다.
            장소는 앉을 수 있는 것만 — "TV 앞" 같은 오폭 방지.)
      정면 — 한글에 정면 markers + 영문에 facing|forward 없음 →
            ", facing forward" 추가.
      동사 — 한글에 앉 + 영문에 sit 계열 없음 → " Sitting." 추가.
    """
    try:
        if not ko_text or not en_text or not isinstance(en_text, str):
            return en_text
        out = en_text
        if (any(v in ko_text for v in _POSE_SIT_VERB)
                and "앞에" not in ko_text):
            _m = re.search(r"in front of the (\w+)", out, flags=re.I)
            if _m and _m.group(1).lower() in (
                    "chair", "bench", "bed", "sofa", "stool", "floor",
                    "stairs", "ground", "couch", "seat"):
                out = (out[:_m.start()] + "on the " + _m.group(1)
                       + out[_m.end():])
        if (any(m in ko_text for m in _POSE_FACING_KO)
                and not re.search(r"facing|forward", out, flags=re.I)):
            out = out.rstrip().rstrip(".") + ", facing forward."
        if (any(v in ko_text for v in _POSE_SIT_VERB)
                and not re.search(r"\bsit\w*|seated\b", out, flags=re.I)):
            out = out.rstrip()
            if not out.endswith("."):
                out += "."
            out += " Sitting."
        if out != en_text:
            _log("[Camera Director] 포즈 절 보정 — 번역이 뭉갠 포즈 절을 한글 원문으로 "
                 "바로잡았습니다")
        return out
    except Exception:
        return en_text


# 신발 문장 보정 (2026-10-15 실측). 구글 번역(사용자 그래프의
# GoogleTranslateTextNode)은 "끊이 없고 앞이 막혀 있는 흰색 단화" 를
# "open-toed white sandals" 로 — 정반대로 뱉었다. 한글 원문의 닫힘/열림
# 표지를 보고 영문 신발 어휘를 같은 방향으로 되돌린다. 한글 표지가 없으면
# (영문 원문 입력 등) 손대지 않는다 — 바꿔야 할 근거가 없다.
# 2026-10-16 오딧: 무앵커 키워드(열린/오픈/노출/덮인/덮여 있/막혀 있)가 신발과
# 무관한 문장에 오폭했다 — 실측: "가슴이 노출된 검은 힐" -> open-toe 삽입,
# "창문이 열린" -> open-toe 삽입, "담요에 덮여 있는" -> closed-toe 삽입(무보정
# 문장에 없는 지시가 생김). 신발 부위(앞/발등/발가락)에 묶거나 "앞이 열/막"
# 처럼 신발 앞코를 직접 가리키는 표지만 인정한다.
_SHOE_CLOSED_KO = (r"앞이\s*막|끊이\s*없|폐쇄|"
                   r"발가락\s*(?:이|가)?\s*(?:안|못)\s*보|"
                   r"발가락\s*(?:이|가)\s*보이지\s*않|"
                   r"(?:앞|발등|발가락)\s*(?:이|을|가)?\s*덮")
_SHOE_OPEN_KO = (r"앞이\s*열|오픈\s*토|"
                 r"(?:앞|발등|발가락)\s*(?:이|가|을)?\s*노출|"
                 r"발가락\s*(?:이|가)\s*보(?!이지)")
_SHOE_NOUN_EN = (r"shoes?|sandals?|pumps|flats|heels?|boots?|sneakers?|"
                 r"slippers?|loafers?|footwear")


def fix_footwear_clause(ko_text, en_text):
    """번역이 뒤집은 신발 지시(열림/닫힘)를 한글 원문으로 바로잡는다.

    규칙:
      영문에 열림 표지(open-toe 계열) + 한글이 닫힘 → 닫힘 표지로 교체.
      영문에 닫힘 표지 + 한글이 열림 → 열림 표지로 교체.
      양쪽에 표지가 없으면 한글 방향의 표지를 신발 명사 앞에 삽입.
      한글 표지가 없거나 영문 표지가 이미 한글과 같으면 입력 그대로.
    실패해도 원문을 돌려준다 (절대 크래시 금지).
    """
    try:
        if not ko_text or not en_text or not isinstance(en_text, str):
            return en_text
        ko_closed = bool(re.search(_SHOE_CLOSED_KO, ko_text))
        ko_open = bool(re.search(_SHOE_OPEN_KO, ko_text))
        if not (ko_closed or ko_open):
            return en_text
        out = en_text
        want = "closed-toe" if ko_closed else "open-toe"
        have_open = re.search(r"open[\s-]?toed?", out, flags=re.I)
        have_closed = re.search(r"closed[\s-]?toed?", out, flags=re.I)
        if ko_closed and have_open:
            out = (out[:have_open.start()] + "closed-toe"
                   + out[have_open.end():])
        elif ko_open and have_closed:
            out = (out[:have_closed.start()] + "open-toe"
                   + out[have_closed.end():])
        elif not (have_open or have_closed):
            noun = re.search(r"\b(?:" + _SHOE_NOUN_EN + r")\b", out,
                              flags=re.I)
            if not noun:
                return en_text
            out = out[:noun.start()] + want + " " + out[noun.start():]
        else:
            # 영문 표지가 이미 있고 방향도 한글과 같다 — 그대로.
            return en_text
        if out != en_text:
            _log("[Camera Director] 신발 절 보정 — 번역이 뒤집은 신발 지시를 "
                 "한글 원문으로 바로잡았습니다")
        return out
    except Exception:
        return en_text


# 배경 지정 문장 보정 (2026-10-15 실측). 구글 번역은 "배경은 이미지3 번의
# 배경으로 사용한다." 를 "The background is used as the background for
# image 3." 로 — 자기참조 어색 문장으로 뱉는다. 그 문장은 배경 지시력을
# 잃어 생성 배경이 이미지3 를 따르지 않았다 (실측 run9). 아래 artifact
# 패턴은 관찰된 형태만 다루고, 관찰되지 않은 번역은 건드리지 않는다.
# tc-big 은 또 다른 형태를 냈다 (run10 실측): "The background is used as
# the background of the image 3 times." — "for image 3" 만 잡으면
# 잔재가 문장 끝까지 살아남아 artifact+정식 문장이 병존한다. 그래서
# 머리("The background is used as the background")는 고정하고 꼬리(for/
# of image N + 남은 조사·어미)는 문장 끝까지 먹인다. 머리가 관찰된
# 자기참조 형태라 오판 여지는 없다. 번호는 숫자·단어 둘 다 잡는다 —
# tc-big 은 "image 3" 을 "image three" 로 뱉는 경우도 있다.
_BG_ARTIFACT_EN = (r"(?:the\s+)?background\s+is\s+used\s+as\s+the\s+"
                   r"background\s+(?:for|of)\s+(?:the\s+)?image\s*"
                   r"(?:(\d+)|(one|two|three|four|five|six|seven|eight|nine|ten))\b"
                   r"[^.\n]*")
_BG_NUM_WORD = {"one": "1", "two": "2", "three": "3", "four": "4",
                "five": "5", "six": "6", "seven": "7", "eight": "8",
                "nine": "9", "ten": "10"}
_BG_KO_PATTERNS = (r"배경[^.\n]{0,40}이미지\s*(\d+)\s*번",
                   r"이미지\s*(\d+)\s*번[^.\n]{0,12}배경")
# 영문 배경-참조 언급 감지 (캡처: 이미지 번호). fix_background_clause 의
# 중복 억제와 ground_reference_guard 의 발동 판정이 같은 한 줄을 쓴다 —
# 개념을 두 벌로 만들면 한쪽만 갱신돼 짝이 어긋난다 (같은 저장소의 이음새
# 결함 실측 다수와 같은 종류). 번호가 없는 언급도 groups 포함 패턴으로
# 참이므로 기존 중복 억제 동작은 그대로다.
_BG_REF_EN = (r"background[^.]{0,80}reference\s+image\s*(\d+)|"
              r"reference\s+image\s*(\d+)[^.]{0,80}background")


def background_ref_slot(text):
    """배경-참조 지정이 있으면 그 이미지 번호(int), 없으면 None.

    한글("배경은 이미지3 번의 배경으로")과 영문("Background matches
    reference image 2") 둘 다 본다. 지면 고정 가드
    (cam_guards.ground_reference_guard) 가 발동 근거로 쓴다.
    관찰된 형태만 — 배경 지정 없이 번호만 나오는 문장은 건드리지 않는다.
    """
    try:
        if not text or not isinstance(text, str):
            return None
        for p in _BG_KO_PATTERNS:
            km = re.search(p, text)
            if km:
                return int(km.group(1))
        em = re.search(_BG_REF_EN, text, flags=re.I)
        if em:
            return int(em.group(1) or em.group(2))
        return None
    except Exception:
        return None


def fix_background_clause(ko_text, en_text):
    """번역이 뭉갠 배경 지정 문장을 한글 원문 근거로 바로잡는다.

    규칙:
      artifact — 영문에 "The background is used as the background for
            image N" 패턴이 있으면 그 문장(선행 The·후행 마침표 포함)을
            정식 배경 문장으로 교체.
      누락 — 한글에 배경 지정(배경…이미지 N 번)이 있는데 영문에 배경·
            참조 이미지 언급이 없으면 정식 문장을 덧붙인다.
    둘 다 아니면 입력 그대로. 실패해도 원문을 돌려준다.
    """
    try:
        if not en_text or not isinstance(en_text, str):
            return en_text
        out = en_text
        m = re.search(_BG_ARTIFACT_EN, out, flags=re.I)
        if m:
            # 캡처는 숫자·단어 중 하나만 — canon 문장은 숫자가 필요하다.
            n = m.group(1) or _BG_NUM_WORD[m.group(2).lower()]
            canon = (f"Use reference image {n} as the exact background "
                     f"environment, identical to reference image {n}.")
            # 문장 전체를 치환한다 — 부분 치환하면 "The Use reference …"
            # 가 된다 (선행 "The " 와 후행 구두점까지 범위에 넣는다).
            start = m.start()
            if out[max(0, start - 4):start].lower() == "the ":
                start -= 4
            end = m.end()
            # 마침표만 먹는다 — 공백까지 먹으면 다음 문장이 붙어 버린다
            # ("…image 3.The woman …").
            if end < len(out) and out[end] == ".":
                end += 1
            out = out[:start] + canon + out[end:]
        ko = (ko_text or "").strip()
        if ko:
            n2 = None
            for p in _BG_KO_PATTERNS:
                km = re.search(p, ko)
                if km:
                    n2 = km.group(1)
                    break
            # 영문에 이미 배경·참조 이미지 언급이 있으면 덧붙이지 않는다
            # (artifact 교체 직후 상태도 여기서 걸러진다). 감지 한 줄은
            # background_ref_slot 와 공유 (_BG_REF_EN).
            if n2 and not re.search(_BG_REF_EN, out, flags=re.I):
                tail = (f" Use reference image {n2} as the exact background "
                        f"environment.")
                out = out.rstrip()
                if out and not out.endswith("."):
                    out += "."
                out = out + tail
        if out != en_text:
            _log("[Camera Director] 배경 절 보정 — 배경 지정 문장을 한글 "
                 "원문으로 되돌렸습니다")
        return out
    except Exception:
        return en_text


# 부채 보유 문장 복구 (2026-10-15 실측, 파란 동그라미 좌측 빈 손). tc-big 은
# "왼손은 이미지4 번의 부체를 들고" 를 "her left hand is on the side of the
# image, she has four sub-bodys" 로 — 부채를 통째로 없애고 잔재 문장만
# 남겼다. 결과물에서는 왼손이 빈 채 시트에 놓였고 부채 자체가 그려지지
# 않았다. 한글 원문에 부채 보유 지시가 있고 영문에 fan 이 없으면 정식
# 문장을 되붙인다. 잔재("four sub-bodys")는 같은 문장의 찌꺼기라 함께
# 지운다 — "she has four sub-bodys" 는 몸통 개수 오해를 낳을 수 있다.
# 관찰된 형태만: 손(왼손/오른손)이 앞에 오는 문장과 부[채체] 표기(사용자
# 원문의 오탈자 '부체' 포함)만 다룬다.
_FAN_KO = (r"(왼손|오른손|왼쪽\s*손|오른쪽\s*손)[^.\n]{0,40}?"
           r"이미지\s*(\d+)\s*번의\s*부[채체]")
# 끝 마침표만 함께 지운다 (문장 끝 잔재 → "…image.." 이중 마침표 방지).
# 쉼표는 남긴다 — 중간 삽입형(", and she sits…")의 문장 경계를 지키기 위해.
_FAN_SUBBODY_EN = (r"[,\s]*(?:she|he|the woman|the man|they)\s+has\s+"
                   r"four\s+sub-bodys?\.?")


def fix_fan_clause(ko_text, en_text):
    """번역이 없앤 부채 보유 지시를 한글 원문 근거로 되붙인다.

    규칙:
      한글에 "왼손은 이미지 N 번의 부채|부체를 들고" 가 있으면
        영문에 fan 언급이 없을 때 정식 문장을 덧붙이고,
        "…has four sub-bodys" 잔재는 지운다.
      fan 언급이 이미 있으면 잔재만 지우고 문장은 더하지 않는다.
      한글 지시가 없으면 입력 그대로. 실패해도 원문을 돌려준다.
    """
    try:
        if not ko_text or not en_text or not isinstance(en_text, str):
            return en_text
        m = re.search(_FAN_KO, ko_text)
        if not m:
            return en_text
        out = re.sub(_FAN_SUBBODY_EN, "", en_text, flags=re.I)
        if re.search(r"\bfan\b", out, flags=re.I):
            if out != en_text:
                _log("[Camera Director] 부채 절 보정 — 번역 잔재(몸통 개수)만 "
                     "지웠습니다 (fan 문장은 이미 있음)")
            return out
        side = "left" if m.group(1).startswith("왼") else "right"
        tail = (f"The {side} hand holds the hand fan from reference "
                f"image {m.group(2)}.")
        out = out.rstrip()
        if out:
            if not out.endswith("."):
                out += "."
            out = out + " " + tail
        else:
            out = tail
        _log("[Camera Director] 부채 절 보정 — 번역이 없앤 부채 보유 지시를 "
             "한글 원문으로 되돌렸습니다")
        return out
    except Exception:
        return en_text


# 포즈 분기 문장 (2026-10-13, PROVISIONAL).
# 왜(Why): 참조 포즈 prior 가 앉음 지시를 이긴다 (실측: 앉음 한 절 vs
# 기대앉음 참조 사진 통째). 포즈 동사가 있는 영문 장면 뒤에 이 문장을
# 붙여 묘사 쪽으로 당긴다. 샘플러가 실제로 따르는지는 오프라인에서 잴
# 방법이 없어 사용자 A/B 로 확인한다 — 그래서 PROVISIONAL.
# 조건: 영문 장면에 포즈 동사가 있고 이미지가 1장 이상 연결됐을 때만.
# 참조와 같은 포즈를 묘사해도 무해하다 (묘사와 일치하므로).
_POSE_VERBS_EN = (r"sitting", r"seated", r"sit\s+down", r"standing",
                  r"stand\s+up", r"lying", r"kneeling", r"running",
                  r"walking", r"dancing")
_POSE_DIVERGENCE = ("Body pose and limb placement follow the description "
                    "above, not the reference photo.")


# 포즈 상태 한글 표지 (divergence 조건용 — 영문 동사 검출의 쌍).
# 번역 없이도 한국어 주제에서 포즈 지시를 안다 (모델 부재 테스트 포함).
_POSE_STATE_KO = ("앉", "서 있", "서있", "선 채", "눕", "누워", "엎드",
                  "무릎 꿇", "무릎꿇", "꿇어", "뛰다", "달리기", "걷기",
                  "춤추")


# 앉기 자세 보강 문장 (R257, 2026-10-30). 왜(Why) 필요한가: 약한 "앉아" 표현만
# 으로는 서 있는 참조의 포즈 prior 를 못 이긴다(실측: 같은 시드·3MP 에서 4번 중
# 3번 섰음). 한글 원문에 엉덩이·무릎·발의 역학까지 쓴 강한 문장은 **참조 사진을
# 그대로 둔 채** 같은 조건에서 4번 모두 앉았다(코드 변경 0). 그래서 약한 입력에만
# 그 역학을 장면 문장 위치에 대신 채워 준다.
# 표면(의자·바닥)에 중립적인 말로 쓴다 — 좌석을 선언하지 않는 바닥 앉기도 덮고,
# 문형이 의자 전용이 되어 바닥 앉기가 어긋나는 것을 막는다.
# positive 전용: 이 워크플로는 cfg 1.0 이라 negative 가 무효다(같은 파일의
# _POSE_DIVERGENCE 와 cam_guards R226·R255 관례).
_SIT_POSTURE_EN = (
    "Sitting posture: the person's hips are lowered and their weight settles "
    "down onto the surface they sit on, the knees bent at a clear angle and "
    "both feet resting on the ground — an unmistakably seated pose, clearly "
    "sitting, not standing and not hovering above the surface."
)

# 앉기 지시 검출 표지 — 한글·영문을 함께 본다(번역 부재 환경 포함).
# 한글 표지는 위 `_POSE_SIT_VERB`("앉")를 **그대로 쓴다** — 같은 사실을 두 곳에
# 두면 한쪽만 늘어나 판정이 갈라진다(저장소 관례). "site"·"visit"·"situated"
# 오탐은 영문 쪽 \b 로 막는다.
_SIT_MARKERS_KO = _POSE_SIT_VERB
_SIT_MARKERS_EN = (r"\bsitting\b", r"\bseated\b", r"\bsits?\b",
                   r"\bsat\b", r"\bsit\s+down\b")

# 사용자가 이미 구체 자세를 쓴 표지 (강한 표현 → 보강 생략).
# 왜(Why) 생략하나: 강한 문장은 이미 4/4 로 검증된 입력이다. 여기에 자동 문장을
# 겹치면 검증되지 않은 조합이 되어 괜한 변동만 만든다.
_EXPLICIT_POSTURE_KO = ("무릎", "엉덩이", "골반", "허벅지")
_EXPLICIT_POSTURE_EN = (r"\bknees?\b", r"\bhips?\b", r"\bpelvis\b", r"\bthighs?\b")


def _sit_requested(ko_text, en_low) -> bool:
    """앉기 지시가 있는가 (약한 "앉아" 포함). en_low 는 소문자 영문 장면.

    실패해도 False (절대 크래시 금지 — 보강은 있으면 좋은 것이지 필수가 아니다).
    """
    try:
        if ko_text and any(m in ko_text for m in _SIT_MARKERS_KO):
            return True
        e = en_low or ""
        return any(re.search(p, e) for p in _SIT_MARKERS_EN)
    except Exception:
        return False


def _explicit_posture_present(ko_text, en_low) -> bool:
    """사용자가 이미 구체 자세(무릎·엉덩이 등)를 썼는가 — 보강 생략 판정.

    실패해도 False (보강을 한다). 판정이 안 되면 도움이 되는 쪽으로 기운다.
    """
    try:
        if ko_text and any(w in ko_text for w in _EXPLICIT_POSTURE_KO):
            return True
        e = en_low or ""
        return any(re.search(p, e) for p in _EXPLICIT_POSTURE_EN)
    except Exception:
        return False


def add_pose_divergence(en_text, image_count, ko_text=""):
    """포즈 분기 문장 추가 (+ 앉기 자세 보강). 조건 불충족이면 입력 그대로.

    한 함수가 둘을 함께 하는 이유(R257, 2026-10-30): 호출 지점이 둘(base run·
    prompt_in run)이라, 앉기 보강을 **별도 함수로 두면 두 경로가 각자 판정**하게
    되고 한쪽만 갱신되면 방어가 조용히 어긋난다(저장소가 R255 에서 겪은 실패
    유형). 그러니 조립 지점 하나를 유지하고, 판정만 작은 헬퍼로 나눈다.
    """
    try:
        if not en_text or not isinstance(en_text, str):
            return en_text
        try:
            _n = int(image_count or 0)
        except Exception:
            _n = 0
        if _n < 1:
            return en_text
        low = en_text.lower()
        _en_hit = any(re.search(r"\b" + w + r"\b", low)
                      for w in _POSE_VERBS_EN)
        _ko_hit = bool(ko_text) and any(
            m in ko_text for m in _POSE_STATE_KO)
        if not (_en_hit or _ko_hit):
            return en_text
        if "not the reference photo" in low:
            return en_text
        out = en_text.rstrip()
        if not out.endswith("."):
            out += "."
        # 앉기 자세 보강 (R257, 2026-10-30). 약한 "앉아" 표현은 서 있는 참조의
        # 포즈 prior 를 못 이긴다 — 구체 역학(엉덩이·무릎·발)을 장면 문장 위치에
        # 대신 채운다. 이미 구체 자세를 쓴 입력은 건드리지 않는다(검증된 강한
        # 입력 보존). 멱등: 같은 문장이 있으면 다시 붙이지 않는다.
        if (_sit_requested(ko_text, low)
                and not _explicit_posture_present(ko_text, low)
                and _SIT_POSTURE_EN not in out):
            out = out + " " + _SIT_POSTURE_EN
            _log("[Camera Director] 앉기 자세 보강 문장 추가 — 약한 '앉아' 표현을 "
                 "구체 자세(엉덩이·무릎·발)로 보강합니다 (서 있는 참조의 "
                 "포즈 우선 방어)")
        out = out + " " + _POSE_DIVERGENCE
        _log("[Camera Director] 포즈 분기 문장 추가 — 묘사 쪽으로 당깁니다 "
             "(PROVISIONAL: 샘플러 추종은 사용자 A/B 확인)")
        return out
    except Exception:
        return en_text
