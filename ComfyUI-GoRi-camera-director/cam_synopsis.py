# -*- coding: utf-8 -*-
"""규칙/수동 tier용 베스트-에포트 한글 시놉시스 → 영문 장면 구조화.

왜(Why) 따로 두나 (2026-10-13): 규칙/수동 tier는 topic 을 통째로 tc-big 에
넘겨 번역만 했지, 문장 단위 구조/서사 이해를 하지 않았다. LLM tier(`AI 판단`)는
cam_llm.py 가 시놉시스를 영문 장면으로 확장해 깊은 이해를 이미 담당한다.
그래서 이 모듈은 **LLM 없이 할 수 있는 한계** 내에서만 동작한다:

  1) 한국어 문장 분할
  2) 문장별 번역(응집된 영문 장면 재조립 — 한 문장이 누락/합쳐지는 것 방지)
  3) 경량 힌트 추출(인물/동물/야간/비/네온 등 — 로그로 이해 내용 가시화 +
     기존 키워드 가드 판정 보강용 시그널)

인과·캐릭터 일관성 같은 **깊은 서사 이해는 이 모듈이 하지 않는다** — 그것이
못 하는 부분은 `automation = AI 판단 (llm)` 일 때 LLM 이 채운다. 본 모듈은
llm tier 에서 절대 호출되지 않도록 호출부에서 게이팅한다(카메라 run()/run_prompt()).

setup_pt: tc-big 모델이 없으면 translate_ko_to_en 가 None 을 반환하고,
이 모듈은 원문을 그대로 되돌려 준다(우아한 폴백 — 기존 단일 번역 동작과 동등).
"""

from __future__ import annotations

import re

try:
    from .cam_translate import translate_ko_to_en, _has_cjk
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_translate import translate_ko_to_en, _has_cjk


__all__ = [
    "split_ko_sentences",
    "_looks_like_synopsis",
    "structure_ko_synopsis",
    "_extract_hints",
    "_en_normalize",
]


# tc-big 가 도메인어를 로마자화하는 경우를 보정하는 경량 사전 (아이템1: 번역 품질).
# 번역 결과(영문)에만 적용 — 원문 한글에는 영향 없음.
# 측정된 오탐: 로우앵글→Roengle, 크롭탑→kloptops(사전 실측).
_EN_NORMALIZE = {
    "roengle": "low angle",
    "kloptops": "crop tops",
    "chgbot": "change bot",
}


def _en_normalize(text: str) -> str:
    """tc-big 번역 결과의 로마자화 아티팩트를 영문 규범어로 보정(아이템1)."""
    if not text:
        return text
    out = text
    for bad, good in _EN_NORMALIZE.items():
        out = re.sub(r"(?i)\b" + re.escape(bad) + r"\b", good, out)
    return out


# 한국어/영문 문장 종결 부호. 말줄임(…) 도 포함.
_SENT_PUNCT = r"[.!\?…]"


def split_ko_sentences(text: str) -> list:
    """한글/영문 혼용 텍스트를 문장 단위로 분할.

    종결 부호(. ! ? …) 와 줄바꿈으로 분할한다. 종결 부호가 없는 단일 문장은
    그대로 1개로 반환된다(통번역과 동등).
    """
    if not text or not text.strip():
        return []
    # 명시적 종결 부호 또는 줄바꿈에서 분할
    raw = re.split(r"(?:" + _SENT_PUNCT + r"\s*|\n+)", text.strip())
    out = []
    for part in raw:
        part = (part or "").strip()
        if part:
            out.append(part)
    return out


def _looks_like_synopsis(text: str) -> bool:
    """다문장 시놉시스인가(구조화 분기 판별).

    종결 부호가 2개 이상이면 다문장으로 본다. 단문(부호 0~1개)은 기존 단일
    번역 경로를 그대로 쓰게 해 기본 동작을 보존한다(조립 로직 비변경).
    """
    if not text or not text.strip():
        return False
    return len(re.findall(_SENT_PUNCT, text)) >= 2


# 경량 힌트 추출용 한국어/영문 키워드. 서사 이해의 '신호'일 뿐, 가드 판정은
# 기존 _is_human_subject / _is_multi_person_request 등이 담당(중복 회피).
_HINT_PATTERNS = {
    "char_refs": r"그녀|그는|그\s*남자|그\s*여자|남자|여자|부부|두\s*사람|아이|아기|노인|소년|소녀",
    "multi_person": r"두\s*명|둘|커플|couple|두\s*사람|여러\s*명|군중|crowd|일행",
    "animal": r"강아지|고양이|개\b|새\b|말\b|동물|강아|고양|반려",
    "night": r"밤|야간|심야|한밤|night|midnight",
    "rain": r"비|우산|빗물|rain|umbrella|rainy",
    "neon": r"네온|neon",
    "indoor": r"실내|방\b|집\b|interior|room|indoor",
    "outdoor": r"거리|골목|길\b|공원|해변|산\b|street|alley|park|outdoor",
}


def _extract_hints(ko_text: str, sentences: list) -> dict:
    """원문(한글)에서 경량 서사 힌트를 추출 — 로그 가시화 + 가드 판정 보강 시그널."""
    t = (ko_text or "").lower()
    hints = {}
    for key, pat in _HINT_PATTERNS.items():
        hints[key] = bool(re.search(pat, t))
    # 문장 수로 '서사 길이'도 표시
    hints["sentence_count"] = len(sentences)
    return hints


def structure_ko_synopsis(text, translate=translate_ko_to_en) -> dict:
    """한글 시놉시스 → {scene_en, sentences, hints}.

    - 영문만 들어오면 그대로 반환(번역 불필요).
    - 한글이면 문장별로 번역해 응집된 영문 장면으로 재조립.
    - 번역 실패(모델 없음/오류) 문장은 원문을 유지해 전체가 깨지지 않게 한다.
    - `_en_normalize` 로 로마자화 아티팩트 보정.

    반환값은 항상 dict 이며, scene_en 이 비어도 호출부가 원문으로 폴백하게
    scene_en 에 원문을 채워둔다.
    """
    raw = (text or "").strip()
    out = {"scene_en": raw, "sentences": [], "hints": {}}
    if not raw:
        return out

    # 영문만: 번역 불필요
    if not _has_cjk(raw):
        sents = split_ko_sentences(raw)
        out["scene_en"] = raw
        out["sentences"] = sents
        out["hints"] = _extract_hints(raw, sents)
        return out

    sents = split_ko_sentences(raw)
    translated = []
    for s in sents:
        if not _has_cjk(s):
            translated.append(s)
            continue
        t = translate(s) if callable(translate) else None
        if t:
            translated.append(_en_normalize(t))
        else:
            # 번역 실패 → 원문 유지(폴백). 전체 장면이 누락되지 않게 한다.
            translated.append(s)
    scene_en = " ".join(x for x in translated if x).strip()
    if not scene_en:
        scene_en = raw
    out["scene_en"] = scene_en
    out["sentences"] = translated
    out["hints"] = _extract_hints(raw, sents)
    return out
