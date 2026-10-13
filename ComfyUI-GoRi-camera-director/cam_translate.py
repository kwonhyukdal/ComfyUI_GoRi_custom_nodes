# -*- coding: utf-8 -*-
"""tc-big-ko-en 한국어→영어 번역 어댑터 (카메라 노드 규칙/수동 tier 전용).

왜(Why) 이 파일이 필요한가
--------------------------
규칙(auto)/수동(manual) tier 에서는 카메라가 사용자의 한글 prompt_in / topic 을
그대로 샘플러로 보낸다. 그럼 한글이 영문 프롬프트에 섞여 나간다. LLM tier 는
이미 cam_llm.py 가 영문으로 확장하지만, 규칙/수동에는 번역 주체가 없었다.
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
import threading

try:
    from .cam_util import _log          # noqa: F401
except ImportError:                     # 스탠드얼론/테스트 실행용
    try:
        from cam_util import _log       # noqa: F401
    except ImportError:
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
    """
    if not text or not _has_cjk(text):
        return None
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
        return en
    except Exception as e:
        _log(f"[Camera Director] ⚠ 번역 추론 오류 — 원문 사용: {e}")
        return None
