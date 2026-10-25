# -*- coding: utf-8 -*-
"""camera_director.py — Camera Director 노드 본체.

주제 한 줄(한글 OK) + 프리셋/자동화(tier) → 카메라 조항이 포함된
영문 prompt_out 문자열과 positive/negative conditioning을 출력한다.

합의된 규칙:
- 텍스트 경로만 관여 (model/latent 경로 무관)
- 자동화 tier: auto(규칙, **기본**) / llm(AI 판단) — llm 실패 시 auto 폴백
  왜(Why) 기본이 auto 인가: LLM 을 쓰면 키가 필요하고 원본 이미지가 외부로
  나간다. 기본값을 llm 으로 두면 API 키 없는 사람이 매 실행마다 실패한다.
- 프리셋 우선순위: 프리셋은 **칸별 기준값**이고 드롭다운은 그 위의 가감이다.
  값을 넣은 칸은 그 값(프리셋 + 추가 - 제거)으로 고정되고, '자동'으로 되돌린
  칸만 프리셋에서 빠져 tier(규칙/LLM) 판정을 받는다. 모든 칸이 자동이면
  프리셋 전체를 쓴다(API·구 워크플로 경로).
- 출력 영문, 라벨 한글, 콘솔 로그 한글
"""

from __future__ import annotations

# 이 노드의 독립 버전. 팩(pyproject.toml) 버전과 별개로 간다.
# 왜(Why) future import 다음인가: `from __future__` 는 docstring 바로 다음에
# 와야 한다 (SyntaxError). 버전 상수는 그 뒤 첫 코드다.
# 왜(Why) 노드마다 따로인가 (2026-10-02): 팩은 여러 노드를 한 번에 배포하는
# 관리 단위일 뿐이다. 카메라만 고쳤는데 팩 버전을 올리면 다른 노드도 바뀐 것처럼
# 보인다. 각 노드는 자기 변경에만 버전을 올린다. 새 노드를 만들면 첫날부터
# __version__ 을 둔다 (test_pack.py 가 강제한다).
# 버전 상수는 **이 한 곳에만** 둔다 (2026-10-07 라운드 2): 이 파일에 같은
# 값이 두 번 대입돼 있었고, 갱신 때 한쪽만 올리면 어긋난 채로 배포된다.
__version__ = "1.9.87"


import json
import os
import re
import threading
import time
import uuid
import weakref

try:
    from . import llm_client
except ImportError:  # 스탠드얼론/테스트 실행용
    import llm_client

# ---------------------------------------------------------------------------
# 기능별 분리 모듈 (2026-10-07 refactor)
#   cam_util    공용 로그·로더 / cam_tables 카메라 조항 테이블
#   cam_subject 주제 분류·역할 판정 / cam_anchors 앵커 문구
#   cam_guards  가드 문구 / cam_physics 물리 가드 / cam_spacing 간격
#   cam_sheet   시트 판별 / cam_llm LLM·키
# 아래 * import 는 이 파일의 공개 표면을 그대로 유지한다 (테스트·호출자가
# camera_director.<이름> 으로 접근하는 계약).
# ---------------------------------------------------------------------------
try:
    from .cam_util import *  # noqa: F403
    from .cam_tables import *  # noqa: F403
    from .cam_subject import *  # noqa: F403
    from .cam_anchors import *  # noqa: F403
    from .cam_guards import *  # noqa: F403
    from .cam_physics import *  # noqa: F403
    from .cam_spacing import *  # noqa: F403
    from .cam_sheet import *  # noqa: F403
    from .cam_classify import *  # noqa: F403
    from .cam_llm import *  # noqa: F403
    from .cam_translate import *  # noqa: F403
    from .cam_translate import _has_cjk
    from .cam_synopsis import *  # noqa: F403
except ImportError:  # 스탠드얼론/테스트 실행용
    from cam_util import *  # noqa: F403
    from cam_tables import *  # noqa: F403
    from cam_subject import *  # noqa: F403
    from cam_anchors import *  # noqa: F403
    from cam_guards import *  # noqa: F403
    from cam_physics import *  # noqa: F403
    from cam_spacing import *  # noqa: F403
    from cam_sheet import *  # noqa: F403
    from cam_classify import *  # noqa: F403
    from cam_llm import *  # noqa: F403
    from cam_translate import *  # noqa: F403
    from cam_translate import _has_cjk
    from cam_synopsis import *  # noqa: F403


def _latent_declared_ratio(latent_image):
    """latent 가 스스로 선언한 한 칸의 픽셀 배수. 못 쓰면 None.

    왜(Why) 모델 비율보다 먼저 보나 (2026-10-23 실측): 빈 latent 노드
    (`EmptyLatentImage`)는 `height//8, width//8` 격자를 만들고
    `downscale_ratio_spacial: 8` 을 함께 보낸다. 즉 **격자 x 선언 = 사용자가
    고른 픽셀 수** 다. ComfyUI 자신도 그 둘의 비(선언/모델비율)만큼만 보정한다
    (`fix_empty_latent_channels` — comfy/sample.py:53~56). 모델 비율만 곱하면
    8 배 선언 격자를 16 배로 읽어 **정확히 4 배** 과대해진다.

    실측 (2026-10-23): 캔버스 768x1344(1.03MP)가 1536x2688(4.13MP)로 읽혀
    참조 1장이 4배로 인코딩됐고(참조 4장 = 16.5MP) 8B 텍스트 인코더가 58초를
    썼다 — 같은 실행에서 같은 4장을 1MP 로 인코딩한 `#55` 는 7초였다.

    양의 정수가 아니면 None 을 돌려 모델 비율 폴백을 쓰게 한다. bool 은
    정수의 하위형이라 따로 막는다(True 가 1 로 읽히면 격자가 1배가 된다).
    """
    try:
        _d = (latent_image.get("downscale_ratio_spacial")
              if isinstance(latent_image, dict) else None)
        if isinstance(_d, bool) or not isinstance(_d, int) or _d <= 0:
            return None
        return _d
    except Exception:
        return None


def _vae_ratio(vae, fallback=16):
    """vae.downscale_ratio 가 양의 정수면 그 값, 아니면 fallback.

    왜(Why) 폴백이 있나 (2026-10-22): 정수가 아닌 비율(비디오 VAE 의
    callable/tuple)은 한 변 환산을 단정할 수 없다. vae 미연결·비정수는
    전부 폴백이다(기존 동작 16 유지). bool 은 정수의 하위형이라 따로 막는다.
    """
    _r = getattr(vae, "downscale_ratio", None)
    if isinstance(_r, bool) or not isinstance(_r, int) or _r <= 0:
        return fallback
    return _r


def _latent_mp(latent_image, vae=None) -> float | None:
    """sampling latent의 메가픽셀. 알 수 없으면 None (점검 생략).

    왜(Why) 배수를 어디서 읽나 (2026-10-23): **latent 가 선언한 배수가 먼저**
    (`_latent_declared_ratio`)다. 선언이 없으면 종전대로 vae.downscale_ratio
    (2026-10-22 실측: Qwen-Image-2.1 = 16, SDXL·Flux = 8), 그것도 없으면 16 이다
    — 즉 선언 없는 입력(다른 노드의 native 격자·기존 테스트)의 결과가 하나도
    안 바뀐다.
    """
    try:
        samples = latent_image.get("samples") if isinstance(latent_image, dict) else None
        if samples is None or getattr(samples, "ndim", None) != 4:
            return None
        _ratio = _latent_declared_ratio(latent_image)
        if _ratio is None:
            _ratio = _vae_ratio(vae)
        h, w = int(samples.shape[-2]) * _ratio, int(samples.shape[-1]) * _ratio
        return (h * w) / 1e6
    except Exception:
        return None


def _num_or_zero(v) -> float:
    """위젯 수치 정규화. NaN·비수치는 0(검사 안 함)으로."""
    try:
        f = float(v)
        if f != f:  # NaN
            return 0
        return f
    except (ValueError, TypeError):
        return 0


def preflight_warnings(_topic: str, camera: dict, latent_mp=None,
                       steps: int = 0, cfg: float = 0.0,
                       denoise: float = 0.0) -> list:
    """출발 전 점검. 깨질 조합이면 경고 문구 목록 (0·빈값은 검사 안 함).

    왜(Why) 첫 인자가 `_topic` 인가: 시그니처 호환용으로 받지만 본문에서 쓰지
    않는다 (경고는 카메라·수치 조합만 본다). 호출부가 전부 positional 이라
    안전하다. 지우면 호출부 14곳을 함께 고쳐야 해서 남긴다.

    왜(Why): 얼굴 클로즈업+저해상도, 극단 CFG/스텝, 과다 denoise는 실행 전에
    알 수 있는 확정 실패다. 모델 천장·시드 운은 여기서 못 잡는다.
    순수 함수라 테스트가 직접 검증한다.
    """
    msgs = []
    try:
        steps = _num_or_zero(steps)
        cfg = _num_or_zero(cfg)
        denoise = _num_or_zero(denoise)
        shot = (camera or {}).get("shot", "")
        # 다중 선택(R169)은 콤마 문자열이라 통째로 비교하면 CU 가 있어도
        # 경고가 사라진다 (2026-10-21 감사, R181). 얼굴 샷만 골라 문구에 쓴다.
        face_shots = [s for s in split_multi(shot) if s in FACE_CRITICAL_SHOTS]
        if (latent_mp is not None and face_shots
                and latent_mp < 1.0):
            msgs.append(
                f"얼굴 클로즈업({', '.join(face_shots)})인데 latent가 작음"
                f"({latent_mp:.1f}MP) — "
                "얼굴 뭉개짐 주의, 1MP 이상 권장")
        if steps and (steps < 8 or steps > 150):
            msgs.append(f"steps={steps} 범위 이탈 (8~150 권장) — 결과 불안정 가능")
        if cfg and (cfg < 1.0 or cfg > 12.0):
            msgs.append(f"cfg={cfg} 범위 이탈 (1.0~12.0 권장) — 파손·뻣뻣함 주의")
        # 경계 1e-9 는 comfy/samplers.py:610 의 math.isclose(cond_scale, 1.0)
        # (rel_tol 기본 1e-9) 과 같은 값이다 — 여기서 넓게 잡으면 샘플러가
        # uncond 를 계산하는 구간(예: 1.001)까지 "죽었다"고 잘못 말하게 된다.
        elif cfg and abs(cfg - 1.0) <= 1e-9 and steps and steps > 12:
            # 왜(Why) cfg=1.0 을 따로 경고하나 (2026-10-21 실측): ComfyUI 의
            # comfy/samplers.py 는 math.isclose(cond_scale, 1.0) 이면 uncond_=None
            # 으로 두고 negative conditioning 을 **계산조차 하지 않는다.** 그러면
            # 이 노드가 내보내는 negative 가 통째로 사라진다 — 부위 개수
            # (ANATOMY_COUNT_NEGATIVE 의 "extra feet/third leg"), 위험 비율 다리
            # 복제 에스컬레이션(ASPECT_LEG_DUPLICATION_NEGATIVE), 물리·접촉까지.
            # 사용자 제보("자동 프리셋에서 다리 3개", 848x1232=0.688, cfg=1.0)가
            # 정확히 이 상태였다: 에스컬레이션은 켜졌는데 채널이 죽어 무효였다.
            # 노드는 denoise=1.0 은 경고하면서 cfg=1.0 은 침묵했고, 사용자는
            # negative 가드가 살아 있다고 믿었다. 그 믿음을 깬다.
            # 저스텝(<=12)이면 증류 스케줄이라 cfg=1.0 이 의도된 정상값이고 올리면
            # 오히려 burn 한다 — denoise 경고(R30b)와 같은 분기로 뺀다.
            msgs.append(
                f"cfg={cfg} — ComfyUI 기본 경로는 cfg 가 1.0 이면 uncond 를 계산하지 않아 "
                "negative conditioning 이 통째로 무효입니다. 이 노드의 negative "
                "가드(부위 개수·다리 복제·여분 발·접촉)가 생성에 전달되지 않고 "
                "positive 가드만 방어합니다. negative 를 쓰려면 cfg 2.0~4.0 을 "
                "권장합니다 — 단 일부 환경은 1.0 초과에서 샘플러가 크래시하므로"
                "(실측 2026-10-13: aimdo malloc_graph_pop NULL) 그때는 런처에 "
                "--disable-comfy-compiler 를 넣거나, positive 가드만으로 쓰고 "
                "negative 가 필요한 부위는 프롬프트로 직접 지정하십시오")
        if denoise and not 0.0 < denoise <= 1.0:
            msgs.append(f"denoise={denoise} 범위 이탈 (0 초과 1 이하)")
        elif denoise and denoise > 0.9:
            # 왜(Why) steps 로 분기하나 (2026-10-11 실측): 8스텝 증류 LoRA
            # (Qwen Image 2.1 등)는 부분 denoise 를 못 견뎌 denoise=1.0 이
            # 의도된 정상값이다. 0.6~0.8 로 낮추면 원본이 아니라 **텍스처
            # 노이즈만** 가득한 이미지가 나온다(WORK_STATUS 2-3 실측). 반면
            # 일반(비증류) 스케줄에서는 denoise=1.0 이 참조 픽셀을 버려
            # 다리·팔·어깨가 뭉개진다. 둘은 처방이 정반대라 같은 문구를
            # 쓰면 한쪽 사용자를 반드시 망친다. 스텝이 낮으면 증류로 보고
            # "1.0 이 정상"으로 안내한다.
            _distill = bool(steps) and steps <= 12
            if _distill:
                msgs.append(
                    f"denoise={denoise} — steps={steps} 저스텝 증류 스케줄은 "
                    "denoise=1.0 이 정상값입니다 (참조 이미지는 조건부 "
                    "경로로 들어갑니다). denoise 를 낮추면 부분 denoise 를 "
                    "못 견뎌 텍스처 노이즈만 남습니다 — 이 워크플로는 그대로 두십시오")
            else:
                # 왜(Why): "주의"만으로는 사용자가 무엇을 바꿔야 하는지 모른다.
                # 실측에서 denoise=1.0 + 참조 이미지 조합은 다리·팔·어깨 같은
                # 세부가 필요한 부위부터 뿌옇게 뭉개졌다. denoise는 "얼마나 다시
                # 그릴 것인가"이므로 낮을수록 원본 픽셀을 보존한다.
                # 갱신 (2026-10-13 실측): 처방(0.6~0.8)이 **모든 모델에 통하지
                # 않는다.** 사용자가 이 안내대로 0.8 을 넣었더니 이미지가 완전히
                # 붕괴했다(인물 다중 겹침·다리 부유) — WORK_STATUS 2-3 의 증류
                # 실패 모드와 같다. 이 노드는 모델이 증류인지 알 수 없다
                # (UNETLoader·LoRA 는 이 노드의 입력이 아니다). 그래서 처방을
                # 단정하지 않고 **붕괴 시 되돌릴 곳**까지 함께 말한다.
                msgs.append(
                    f"denoise={denoise} 과다 — 원본 픽셀을 거의 안 써서 다시 그립니다. "
                    "참조 이미지의 형태·색·디테일이 살아남으려면 0.6~0.8을 권장 "
                    "(1.0은 완전히 새로 생성 -> 다리·팔·어깨·손 같은 세부가 "
                    "먼저 뭉개지고 가구 형태도 원본에서 벗어납니다). "
                    "단 증류 모델(저스텝 LoRA)이면 0.6~0.8 에서 이미지가 "
                    "붕괴합니다(실측 2026-10-13: 인물 다중 겹침·다리 부유). "
                    "이 노드는 모델이 증류인지 알 수 없으니 한 장씩 비교해 "
                    "정하십시오 — 붕괴하면 1.0 으로 되돌리고 steps 를 12 이하로 "
                    "낮추는 쪽이 맞습니다")
    except Exception:
        pass
    return msgs


# ---------------------------------------------------------------------------
# 노드
# ---------------------------------------------------------------------------

def _reference_roles_from_llm(obj, labels) -> dict:
    """LLM JSON 의 references[] → {슬롯: 역할}. 잘못된 값은 버린다.

    역할 어휘는 여기서 닫는다 — LLM 이 임의 문자열을 보내면 plan 이 오염된다.
    """
    allowed = {"person", "outfit", "object", "background", "style", "pose"}
    try:
        valid = {int(str(l)) for l in (labels or [])}
    except (TypeError, ValueError):
        valid = set()
    refs = obj.get("references") if isinstance(obj, dict) else None
    out = {}
    if not isinstance(refs, list):
        return out
    for item in refs:
        if not isinstance(item, dict):
            continue
        try:
            slot = int(item.get("slot"))
        except (TypeError, ValueError):
            continue
        role = str(item.get("role") or "").strip().lower()
        if slot in valid and role in allowed:
            out[slot] = role
    return out


def _sheet_kind_from_llm(obj) -> str:
    """LLM JSON 의 sheet_kind → "" | "single" | "multi". 그 밖은 버린다.

    왜(Why) 화이트리스트인가: 이 값은 다인물 시트 분기를 뒤집는다. "multi" 가
    날아오면 "전부 한 사람" 지시 대신 "패널마다 다른 인물" 지시가 나가므로,
    임의 문자열을 통과시키면 사용자가 시트 어휘도 없이 분기가 뒤집힌다.
    """
    if not isinstance(obj, dict):
        return ""
    kind = str(obj.get("sheet_kind") or "").strip().lower()
    return kind if kind in ("single", "multi") else ""


def _object_log_text(dets) -> str:
    """사물 검출 목록 → "chair 0.72, cup 0.55". 없으면 "".

    왜(Why) 이름과 점수를 함께 찍나: 점수만 보면 무엇이 잡혔는지 알 수 없고,
    이름만 보면 얼마나 확신하는지 알 수 없다. 오탐을 사람이 판단하려면 둘 다
    필요하다 — 이 줄은 그 판단의 근거로 남긴다.
    """
    try:
        parts = []
        for d in (dets or []):
            if not isinstance(d, dict):
                continue
            nm = str(d.get("name") or "").strip()
            if not nm:
                continue
            parts.append("%s %.2f" % (nm, float(d.get("score") or 0.0)))
        return ", ".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def _slot_analysis_text(label, poses, dets) -> str:
    """슬롯 1개 → "1번: person 1 / 사물 chair 0.72, cup 0.55".

    AC-2 의 예시가 이 형식이다. 사람 수는 포즈 모델이, 사물은 객체 검출기가
    낸다 — 두 근거를 한 줄에 나란히 둬서 서로 어긋나는지 눈으로 볼 수 있다.
    """
    parts = []
    n = int(poses or 0)
    if n > 0:
        parts.append("person %d" % n)
    obj_txt = _object_log_text(dets)
    if obj_txt:
        parts.append("사물 " + obj_txt)
    return "%d번: %s" % (int(label), " / ".join(parts) if parts else "검출 없음")


def _reference_analysis_text(items) -> str:
    """참조 항목들 → 슬롯별 요약 한 줄. 볼 게 없으면 "".

    왜(Why) `classify_reference` 를 다시 부르나: `classify_references` 는
    {슬롯: kind} 만 준다. 사물까지 보려면 분류 결과 전체가 필요한데, 분류는
    `_sig` 내용 지문으로 캐시되므로 **추가 추론 비용이 0** 이다.
    슬롯 하나가 실패해도 그 칸만 건너뛰고 나머지는 남긴다 — 진단용 줄이
    진단 대상 때문에 사라지면 안 된다.
    """
    segs = []
    for pair in (items or []):
        try:
            label, img = pair
            n = int(str(label))
        except (TypeError, ValueError):
            continue
        try:
            info = classify_reference(img)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(info, dict):
            continue
        segs.append(_slot_analysis_text(n, info.get("poses"),
                                        info.get("objects")))
    return " | ".join(segs)


def resolve_guard_plan(subject_text, _camera, image_count, image_labels,
                       image_items, primary_image, _reference_images,
                       tier="", llm_hint="", weak_sheet_slots=None,
                       sheet_kind="", declared_topic=None):
    """한 실행의 가드 판정을 **한 곳에서** 모아서 돌려준다.

    왜(Why) `_reference_images` 는 받기만 하나: 예전 리팩터 전에는 여기서
    썼다. 지금 본문은 subject_text·개수·라벨·tier·hint 와 `_camera`(샷 인지
    게이트가 읽는 `shot`) 만 본다. `_reference_images` 는 어디서도 쓰지
    않는다. 호출부가 전부 positional 이라 안전하다. 시그니처를 줄이면
    호출부 2곳과 테스트 5곳을 함께 고쳐야 해서 남긴다.

    왜(Why) 이 함수를 만드는가(2026-09-29):
    `run()` 과 `run_prompt()` 가 같은 가드 판정을 각자 반복하면서 결과를
    `self._last_*` 속성으로 넘겨 받아 쓰고 있었다. 판정식이 두 벌이었고,
    **한쪽만 갱신되면 positive/negative 짝이 어긋나** 짝인 방어가 조용히
    사라졌다(2026-09-28 실측: 국가 표현형·동물 가드가 positive 에만 붙고
    negative 에 사라짐). CLAUDE.md 에도 "둘을 손으로 동기화한다"고 적혀 있었다.

    이제 판정은 여기 한 벌이고, 호출부는 이 dict 의 positive/negative 조각을
    그대로 합치기만 한다. 갱신 누락이 구조적으로 불가능해진다.

    반환 dict 의 조각은 모두 문자열이고, 빈 문자열은 "미적용"을 뜻한다.
    로그는 이 함수가 아니라 호출부가 낸다 — 로그 문구는 경로마다 다르다.
    """
    text = subject_text or ""
    is_human = _is_human_subject(text)
    # 참조 이미지에 사람이 검출됐으면 사람으로 본다 (2026-10-21 사용자 실측).
    # 왜(Why) 텍스트만으로 부족한가: topic 을 비우고 참조 사진만 넣는 정상
    # 사용에서 text 에 사람 언급이 없어 is_human=False 가 된다. 그러면 다리·
    # 발 무결성(leg limb_integrity)·부위 개수·신발 가드가 **전부 꺼져**,
    # 사람이 있는 장면인데 다리 3개가 나온다(사용자 실측: topic 빈칸 + 참조
    # 2장 + 16:9). 참조 자동 분류가 픽셀로 사람을 찾았으면 그 사실을 반영한다.
    # _hint_person_slots 는 classify_references 가 심은 사람 슬롯이다(없으면
    # 빈 리스트 → 참조에 사람이 없는 제품·풍경 장면은 종전과 동일). run_prompt
    # 경로는 run() 뒤 힌트가 살아 있어 반영되고, 힌트가 없는 테스트·단독 호출은
    # 영향받지 않는다.
    if not is_human:
        try:
            is_human = bool(_hint_person_slots())
        except Exception:  # noqa: BLE001
            pass
    labels = list(image_labels or [])
    # 왜(Why) 샷 인지 게이트가 필요한가 (2026-10-11 실측): 근접(CU)·극접(ECU)
    # 샷은 다리·발이 화면에 없다. 그런데 anatomy_count("두 다리, 발가락 5개")·
    # body_balance("팔·다리 균형")·detail_def("다리 경계")를 그대로 넣으면
    # 모델이 **화면에 없는 사지를 그려 넣으려 한다** — 사용자가 겪은 "발이
    # 하나 더 생긴다"의 실제 경로다. 해부 문구는 전신·중경처럼 실제로 그
    # 부위가 보이는 샷에만 걸어야 한다. 샷이 AUTO거나 비어 있으면(판정 불가)
    # 보수적으로 켠다 — 꺼서 방어가 사라지는 것보다 낫다.
    _shot = (_camera if isinstance(_camera, dict) else {}).get("shot", "")
    # 다중 선택(R169)은 "근접 (CU),중경 (MS)" 같은 콤마 문자열이다. 통째로
    # 비교하면 어떤 표에도 없으므로 분기가 조용히 꺼진다 (2026-10-21 감사,
    # R181): 화면에 없는 다리 문구가 다시 붙어 여분의 다리를 만들었다.
    # 하나라도 얼굴 클로즈업이면 상반신(다리·발 없음) 변형을 고른다 — 문구가
    # 화면에 없는 사지를 설명하는 쪽이 실제 손실이었다(2026-10-11 실측).
    _limb_visible = not has_any_label(_shot, FACE_CRITICAL_SHOTS)
    # 다중 참조(2장 이상)면 믹스 변형 가드를 양쪽에 자동 첨부.
    mix_guard = image_count >= 2
    # 인물 신체 발란스: 인물 주제 + 사지가 보이는 샷. 왜(Why) 샷을 보나
    # (2026-10-11 실측): 전에는 인물 주제면 상시였는데, 문구에 "arms and
    # legs of even realistic length" 가 있어 CU/ECU 에서 화면에 없는 다리를
    # 요구했다. 전신 비율 가드는 사지가 보이는 샷에만 건다.
    body_balance = is_human and _limb_visible
    # 부위별 디테일 경계: 인물 + 참조 이미지 실행일 때만. CU/ECU 에서도 켜되
    # upper 변형(다리·발 문구 제외)을 쓴다 — denoise=1.0 뭉개짐 방어라 끄면
    # 얼굴·손 질감이 무너진다.
    detail_def = is_human and image_count >= 1
    # 부위 개수(손가락 5·발가락 5·양팔·양다리) 명시. 인물 주제면 항상.
    anatomy_count = is_human
    # 신발 유지 + 신체-사물 경계: 인물 + 참조 실행이면 항상. CU/ECU 면
    # upper 변형(화면에 없는 발·다리 문구 제외)을 쓴다.
    footwear = is_human and image_count >= 1
    body_object_boundary = is_human and image_count >= 1
    # 의복 경계 (2026-10-16 실측, 파란 동그라미): 생성물에서 손이 치마 자락에
    # 삼켜졌다. 카메라에는 이 경우를 덮는 가드가 없었다(가구 경계는 furniture
    # 전용). 가구 경계와 **같은 게이트**를 쓴다 — 인물 + 참조 실행. 게이트를
    # 넓히면 다른 경로의 문구가 함께 늘어나므로 기존 계약 범위로 시작한다.
    garment_boundary = is_human and image_count >= 1
    # 손 배치 (2026-10-24 실측, R220): 앉아서 "양 손을 무릎에" 올린 장면에서
    # 두 손이 겹쳐 한 덩어리로 합쳐지고 손가락이 서로 넘어갔다. 손 계열 문구가
    # 전부 "한 손 안에서 손가락 다섯 개·경계 분리" 라 **두 손 사이**를 덮는 문구가
    # 없었다. 넓은 "손" 이 아니라 **배치 구문**(무릎에·양 손을·품에·hands resting…)
    # 에만 켠다 — 손이 화면에 있는 것만으로는 둘이 붙을 위험이 없다.
    # 참조 실행 여부를 게이트에 넣지 않는다: 위험은 참조 유무가 아니라 자세에서
    # 온다(참조가 손을 공급하지 못하는 denoise=1.0 에서 더 크다).
    hand_placement = is_human and hand_placement_marks(text)
    # 신발 교체 지시면 유지 가드를 교체 가드로 갈아탄다 (2026-10-15 실측):
    # "앞이 막혀 있는 흰색 단화" 지시와 "keep that footwear(reference)" 가
    # 같은 positive 에서 정면 충돌했다 (2026-10-13 에 identity anchor 는
    # 고쳤는데 이 가드는 남아 있었다). CU/ECU 에서는 발이 화면에 없으므로
    # 기존 upper 변형 그대로 — 교체 문구가 없는 발을 그려 넣는다.
    footwear_change = (footwear and _limb_visible
                       and _topic_changes_shoes(text))
    # 맨발 요구 (2026-10-25 감사 F3). 왜(Why) 필요한가: "A barefoot woman on
    # the beach" 처럼 맨발을 요구하면 참조 유지 가드가 그대로 나가 "keep the
    # exact shoes" 와 짝 negative 의 "bare feet" 금지가 **사용자 문장과 정면
    # 충돌**했다(같은 실행에서 셋이 동시에 나갔다). 맨발 주제에서는 신발 잠금
    # 자체를 끄고(아래 `footwear = False`) 맨발 가드로 갈아탄다. `_topic_wants_
    # barefoot` 이 `_topic_changes_shoes` 에 양보하므로 위 교체 경로와 배타다.
    _barefoot_topic = bool(footwear and _topic_wants_barefoot(text))
    footwear = footwear and not _barefoot_topic
    # 맨발 가드는 발이 화면에 보이는 샷에서만 의미가 있다(위 _limb_visible).
    # CU/ECU 맨발은 문구가 없다 — "do not make barefoot"(upper)도 내지 않는다.
    footwear_bare = _barefoot_topic and _limb_visible
    # llm_hint 방어어는 LLM 판정이 실제로 이뤄진 실행에만.
    hint_defense = tier == "llm" and bool((llm_hint or "").strip())

    # 포즈 참조: topic에 포즈 역할이 명시된 슬롯 + **힌트가 말하는 포즈 슬롯**.
    # 왜(Why) 힌트도 보나 (2026-10-19): LLM 이 이미지를 보고 "이 칸은 포즈"라고
    # 알려 줘도 topic 전용으로만 돌리면 포즈 가드가 안 나갔다. topic 을 비운
    # 사용자에게만 해당하던 구멍이라 힌트를 합친다. 힌트의 pose 는 병합 지점에서
    # "픽셀이 사람을 찾은 슬롯"을 걸러냈으므로 여기서는 그대로 신뢰한다.
    pose_slots = (_pose_role_slots(text) | set(_hint_pose_slots())) & set(labels)
    pose_pos = _pose_reference_guard(pose_slots)
    # 물리·공간: topic의 접촉/동작 동사 → 이미지의 물리 상태.
    phys_pos, phys_neg = physics_contact_guard(text)
    # 픽셀 공간 측정: topic에 접촉 동사가 없어도 참조에서 거리를 읽는다.
    # 거리 지사는 topic 동사가 있을 때 중복되므로 생략하고 negative 만 보강.
    # 왜(Why) spacing_neg 이 없는가(2026-10-02 실측): 거리 negative 는 이미
    # phys_neg 에 합쳐진다(아래 3줄). 여기 다시 담으면 같은 문구가 두 벌로
    # 들어가고, 반환 dict 에는 조각이 없어 읽을 곳이 없다 — write-only 였다.
    spacing_pos = ""
    spacing_measure = None
    # 하단 잘림 측정 (2026-10-21): 간격 가드(spacing_guard)는 참조 2장 이상에서만
    # 프롬프트 문구를 만든다. 그러나 "참조 피사체가 하단에서 잘려 있는가" 는
    # 1장에서도 읽을 수 있고(오히려 1장 워크플로에서 더 흔하다), 재는 값은 같다.
    # 그래서 측정 게이트만 primary_image 기준으로 넓히고 **문구 게이트는 그대로
    # 둔다** — 문구 생성 조건을 넓히면 다른 조건의 결과가 함께 흔들린다.
    if primary_image is not None:
        spacing_measure = subject_spacing(primary_image)
    if image_count >= 2:
        _sp_pos, _sp_neg = spacing_guard(spacing_measure, text)
        if phys_pos == "" and _sp_pos:
            spacing_pos = _sp_pos
        if _sp_neg:
            phys_neg = (phys_neg + ", " + _sp_neg) if phys_neg else _sp_neg
    # 참조 인물이 화면 하단에서 잘려 하반신을 새로 그려야 하는 상태인가.
    # 왜(Why) 이 판정을 만드나 (2026-10-21 사용자 실측): 참조에 하반신이 없는데
    # 전신 샷을 요구하면 모델이 화면에 없는 다리·발을 **새로 그려야 하고**, 그
    # 과정에서 다리·발이 하나 더 생긴다. 사용자 제보 "프리셋 자동에서 다리 3개"
    # 의 워크플로 참조(2026-09-27 17 42 22.png)가 허벅지 중간에서 잘려 하단
    # 여백이 0% 였다. subject_spacing 은 그 값을 이미 재고 있었지만 로그에만
    # 쓰였고, 가드는 반대 방향("바닥이 보이면 그대로 유지")뿐이었다 — 노드는
    # 이 조건을 침묵했고 사용자는 원인을 알 수 없었다.
    # 사지가 화면에 없는 근접·극접은 하반신을 그릴 필요가 없어 제외한다.
    # 경계는 spacing_guard 와 **같은** SPACING_BOTTOM_CROP 을 쓴다 — 두 판정이
    # 다른 값을 쓰면 어떤 여백에서 서로 반대를 말하게 된다.
    _bm = (spacing_measure or {}).get("bottom_margin")
    ref_bottom_cropped = bool(is_human and _limb_visible
                              and _bm is not None
                              and _bm <= SPACING_BOTTOM_CROP)
    grounding = ""
    if not phys_pos and is_human:
        grounding = physics_grounding_guard(text)
    # 지면 고정 (2026-10-15 실측, 파란 동그라미): 배경-참조 지정이면 피사체가
    # 딛은 지면도 그 참조여야 한다 — run10 에서 참조 배경(흙바닥)과 달리 바닥이
    # 콘크리트로 나왔다. negative 는 물리 negative 채널(phys_neg)로 함께 흘린다
    # — 짝인 방어를 한곳에서 만들어 어긋날 수 없게 한다.
    ground_pos, ground_neg = ground_reference_guard(text)
    if ground_neg:
        phys_neg = (phys_neg + ", " + ground_neg) if phys_neg else ground_neg

    # 캐릭터 시트: 텍스트 의도 또는 **픽셀 판별** 중 하나라도.
    # declared_topic 은 사용자가 원래 쓴 topic — 시트 가드 발동 근거.
    # subject_text 는 topic + LLM scene 으로 더 넓지만(분기 판정용),
    # 발동에는 쓰지 않는다(2026-10-19 거짓 발동 실측).
    pixel_sheet = sheet_like_slots(image_items)
    sheet_text = character_sheet_guard(
        image_count, text, image_labels=labels, pixel_sheet_slots=pixel_sheet,
        sheet_kind=sheet_kind, weak_sheet_slots=weak_sheet_slots,
        declared_topic=declared_topic)

    furniture_slots = _object_dna_slots(text, labels, image_count)
    # 좌석 관계 (2026-10-24, R226): 좌석 어휘 + 착석 동사가 있는 슬롯 ∩ 사물 DNA
    # 대상. 좌석 어휘가 있어도 사물 DNA 대상이 아니면(의상·배경 등) 좌석 문구를
    # 내지 않는다. 좌석 슬롯은 `_furniture_dna_guard` 안에서 방향 조항만 갈아
    # 끼운다 — 형태·접촉·개수 충실은 그대로 남는다.
    seat_slots = _seat_slots(text) & set(furniture_slots)
    furniture_pos = _furniture_dna_guard(text, furniture_slots,
                                         seat_slots=seat_slots)
    # 배경 참조의 사물 충실 (2026-10-22 실측, 파란 동그라미). 사물 정식 슬롯과
    # 달리 **존재를 요구하지 않는다** — 조건문 하나만 낸다. 왜 필요한지는
    # cam_guards 의 FURNITURE_BACKGROUND_POSITIVE 주석 참조(실측: 좌.png 의 검은
    # 원기둥 다리 4개가 갈색 목재로 바뀌고 앞다리가 신발에 끼었다).
    furniture_bg_slots = _background_dna_slots(text, labels, image_count)
    furniture_bg_pos = _furniture_background_guard(text, furniture_bg_slots)
    # 참조 사물 외형 고정 (2026-10-16 실측, 파란 동그라미): 의자 등받이 채널
    # 터프팅이 사라지고 색이 밝아졌다. FURNITURE_DNA 는 "정체성 유지"라 어떤
    # 특징인지 지명하지 못하고, denoise=1.0 에서 참조 픽셀은 거의 안 쓰인다 —
    # 문구가 유일한 전달 경로다. 참조에서 대표색을 읽어 따로 굳힌다.
    # 슬롯 이미지는 라벨로 찾을 수 있어야 하므로 여기서 한 번만 만든다.
    _slot_images = {}
    for _pair in (image_items or []):
        try:
            _lbl, _img = _pair
            _slot_images[int(str(_lbl))] = _img
        except (TypeError, ValueError):
            continue
    furn_surface_pos, furn_surface_neg = object_appearance_guard(
        text, _slot_images, furniture_slots)
    remove_item = _remove_item_guard(text)

    pos = {
        # 노출 요청이면 의상 문장이 빠진 변형을 쓴다 (2026-10-11 실측 결함).
        # 원문의 "Garments … placed over the main person's body" 는 옷을
        # 덧입히라는 지시라, 같은 positive 에 함께 붙는 nudity_anatomy_guard
        # ("…clearly defined natural intimate detail") 와 **정면 충돌**한다.
        # 실측: 노출 요청 + 참조 2장 → 두 문구가 동시에 positive 에 들어갔다.
        "mix_guard": ((MIX_GUARD_POSITIVE_BARE if _is_nudity_request(text)
                       else MIX_GUARD_POSITIVE) if mix_guard else ""),
        "appearance_hair": "",
        "body_balance": BODY_BALANCE_POSITIVE if body_balance else "",
        "detail_def": ((DETAIL_DEFINITION_POSITIVE if _limb_visible
                        else DETAIL_DEFINITION_POSITIVE_UPPER)
                       if detail_def else ""),
        "anatomy_count": ((ANATOMY_COUNT_POSITIVE if _limb_visible
                           else ANATOMY_COUNT_POSITIVE_UPPER)
                          if anatomy_count else ""),
        # 다리·발·종아리 무결성 positive (2026-10-21). cfg=1.0 이라 negative 가
        # 무효인 워크플로에서 유일하게 작동하는 층. _limb_visible(다리·발이
        # 화면에 보이는 샷)일 때만 붙인다 — CU/ECU 는 없는 발을 그린다.
        "limb_integrity": (LEG_FOOT_INTEGRITY_POSITIVE
                           if (anatomy_count and _limb_visible) else ""),
        "footwear": (FOOTWEAR_BARE_POSITIVE if footwear_bare
                     else FOOTWEAR_CHANGE_POSITIVE if footwear_change
                     else (_footwear_guard(_shot, _footwear_slots(text))[0]
                           if footwear else "")),
        "body_object_boundary": (_body_object_boundary_guard(_shot)[0]
                                 if body_object_boundary else ""),
        "garment_boundary": (_garment_boundary_guard(_shot)[0]
                             if garment_boundary else ""),
        # 손 배치 (2026-10-24, R220) — 두 손이 겹치거나 합쳐지는 실패 방어.
        # 샷 변형이 없다: 손은 전신·중경·상반신 어디서나 두 손이 함께 나올 수 있다.
        # CU/ECU 에서도 손이 크게 잡히면 두 손이 붙을 수 있어 upper 분기를 두지
        # 않는다(문구 자체가 두 손 사이 서술이라 없는 손을 요구하지 않는다).
        "hand_placement": HAND_PLACEMENT_POSITIVE if hand_placement else "",
        "furniture": furniture_pos,
        "furniture_bg": furniture_bg_pos,
        # 좌석 접촉점 (2026-10-24, R226) — 좌석 슬롯이 있을 때만 나간다.
        # run() 은 body-object 경계 **뒤에** 이 조각을 붙인다(경계 → 접촉점).
        # run_prompt() 는 2026-10-25 R239 부터 **장면 문장 바로 뒤**에 붙인다 —
        # 꼬리에서는 뒤따르는 조항에 희석돼 의자가 소실됐다(실측 A/B).
        "seat": (SEAT_OCCUPANCY_POSITIVE if seat_slots else ""),
        "character_sheet": sheet_text,
        "pose": pose_pos,
        "spacing": spacing_pos,
        "physics": phys_pos or grounding,
        "ground": ground_pos,
    }
    # 참조 충실 — 해부·경계 계열 positive 를 압축본으로 치환한다 (2026-10-25 E3,
    # 2026-10-26 항상 적용으로 내부화).
    # 왜(Why) 항상인가: 기본이 꺼짐이던 동안 그 위젯을 모르는 사용자가 계속
    # 참조를 잃었다(실측 2026-10-26: 규칙 경로 3.26% 대 17.51%). 옳은 동작을
    # 기본으로 올리고 외부 스위치를 없앴다 — 스위치가 있으면 기본 동작이 두
    # 계약으로 갈린다. 설계: docs/dev-loop/2026-10-26-ref-fidelity-internal/.
    # 왜(Why) 다리·발이 보이는 샷에서만 하나 (`_limb_visible`): 압축본은
    # "two legs, two feet" 를 담는다. CU/ECU 는 발이 화면에 없어 그 문구가
    # 오히려 없는 사지를 그리게 한다 — 그래서 상반신 샷은 종전 upper 변형을
    # 그대로 둔다. 압축 효과(E3)도 전신 장면에서만 측정했다.
    # 왜(Why) 원본 상수를 안 줄이나: tests/test_node.py 가 그 문자열을 66곳에서
    # 잠그고 있다. 상수를 줄이면 잠금이 "그 문구가 실제로 나간다"는 뜻을 잃는다.
    # 게다가 원문은 negative 빌더가 (pos, neg) 쌍으로 계속 쓴다 — 지우면
    # cfg 2~4 사용자의 해부 방어가 함께 사라진다.
    # 왜(Why) 원본 상수가 아니라 `pos` 를 덮나: 조립 순서 코드(run_prompt 의 if)는
    # 그대로 두는 편이 되돌리기 쉽다 — 빈 문자열은 자연히 빠진다.
    if _limb_visible:
        # 해부 계열 — 원문 4조각(body_balance·detail_def·anatomy_count·
        # limb_integrity)을 압축 1조각으로 합친다. 조각이 하나도 안 켜진
        # 장면(예: 풍경)에는 넣지 않는다.
        if body_balance or detail_def or anatomy_count:
            pos["body_balance"] = COMPACT_ANATOMY_POSITIVE
            pos["detail_def"] = ""
            pos["anatomy_count"] = ""
            pos["limb_integrity"] = ""
        # 경계 계열 — 원문 2조각(body_object_boundary·garment_boundary)을
        # 압축 1조각으로 합친다.
        # 왜(Why) hand_placement 는 합치지 않나 (사용자 결정 2026-10-26): 그 문구는
        # 앉아서 "양 손을 무릎에" 올린 두 손이 한 덩어리로 합쳐지는 실패를 막는
        # **따로 측정된** 방어다(R220, "never merge into a single shape"). 압축
        # 경계문은 그 조항을 담지 않으므로, 합치면 사용자 장면(무릎에 손)에서
        # 측정된 방어가 사라진다. 그래서 손 배치는 원문 그대로 남긴다.
        if body_object_boundary or garment_boundary:
            pos["body_object_boundary"] = COMPACT_BOUNDARY_POSITIVE
            pos["garment_boundary"] = ""
        # 신발은 세 분기 중 **동일성 잠금**일 때만 압축한다. 맨발·교체 지시는
        # 사용자가 명시한 요구라 그대로 둔다.
        if footwear and not footwear_bare and not footwear_change:
            pos["footwear"] = compact_footwear_guard(_footwear_slots(text))
    return {
        "positive": pos,
        # negative 빌더는 플래그를 받는다. 문자열이 아니라 판정 결과.
        "flags": {
            "mix_guard": mix_guard,
            "body_balance": body_balance,
            "detail_def": detail_def,
            "detail_def_upper": (detail_def and not _limb_visible),
            "anatomy_count": anatomy_count,
            "anatomy_count_upper": (anatomy_count and not _limb_visible),
            "footwear": footwear,
            "footwear_upper": (footwear and not _limb_visible),
            "footwear_bare": footwear_bare,
            "body_object_boundary": body_object_boundary,
            "body_object_boundary_upper": (body_object_boundary
                                           and not _limb_visible),
            "garment_boundary": garment_boundary,
            "garment_boundary_upper": (garment_boundary and not _limb_visible),
            "hand_placement": bool(hand_placement),
            "hint_defense": hint_defense,
            "remove_item": bool(remove_item),
            "furniture": bool(furniture_pos),
            "furniture_bg": bool(furniture_bg_pos),
            "seat": bool(seat_slots),
            "character_sheet": bool(sheet_text),
            "pose_ref": bool(pose_pos),
            "ref_bottom_cropped": ref_bottom_cropped,
        },
        "physics_neg": phys_neg,
        "pose_slots": sorted(pose_slots),
        "pixel_sheet_slots": list(pixel_sheet),
        # 약한 시트 슬롯 — latent 제외 보조용. 엄격 pixel_sheet_slots 과 달리
        # **시트 가드 발동에는 쓰지 않는다**(오탐 방지). Skills 경로가
        # _last_guard_plan 으로 이 값을 물고 간다.
        "weak_sheet_slots": [str(s) for s in (weak_sheet_slots or [])],
        "spacing_measure": spacing_measure,
        "furniture_slots": furniture_slots,
        "furniture_bg_slots": furniture_bg_slots,
        "seat_slots": seat_slots,
        "furniture_surface_pos": furn_surface_pos,
        "furniture_surface_neg": furn_surface_neg,
    }


class CameraDirector:
    RETURN_TYPES = ("STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("positive", "negative", "image_out")
    FUNCTION = "run"
    # 되돌린 이유(2026-09-30): "GoRi/Camera" 로 바꿨다가 되돌렸다. Jev 가 이
    # 변경을 public_api_impact=breaking P=0.43 으로 봤다(신뢰도 0.24 — 낮다).
    # 게다가 CATEGORY 는 메뉴 묶음 문자열일 뿐 기능 이득이 0 이고, 1.9.7 이
    # 배포 전이라 되돌릴 비용이 아직 0 이다. publisher 별 분류가 필요해지면
    # 그때 한 번에 한다.
    CATEGORY = "HF Skills/Camera"
    DESCRIPTION = ("주제 한 줄(한글 OK) + 프리셋/자동화 → 카메라 조항이 포함된 "
                   "영문 positive/negative 2줄. CLIPTextEncode.text에 연결하세요. "
                   "prompt_in 단자에 선을 연결하면 topic 칸 대신 그 프롬프트를 씁니다. "
                   "image 단자에 연결된 이미지는 image_out으로 그대로 통과됩니다 "
                   "(I2V 시작프레임 배선 정리용, 영상 생성 기능 아님).")

    # 내부용 베이스 클래스 입력 정의 — 노출 노드는 이걸 상속해 확장한다
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "topic": ("STRING", {"default": "", "multiline": True,
                                     "dynamicPrompts": False}),
                "preset": (preset_names(),),
                "automation": (["AI 판단 (llm)", "규칙 (auto)"],
                               {"default": "규칙 (auto)", "label": "automation ai"}),
                "shot": ([AUTO] + list(SHOT),),
                "lens": ([AUTO] + list(LENS),),
                "angle": ([AUTO] + list(ANGLE),),
                "composition": ([AUTO] + list(COMPOSITION),),
                "lighting": ([AUTO] + list(LIGHTING),),
                "grade": ([AUTO] + list(GRADE),),
                "motion": ([AUTO] + list(MOTION),),
                "speed": ([AUTO] + list(SPEED),),
                "amplitude": ([AUTO] + list(AMPLITUDE),),
                # 복합 무빙 2번째 슬롯 — 맨 뒤에 둬서 기존 워크플로 위치 매핑 보호.
                "motion2": ([AUTO] + list(MOTION),),
            },
            "optional": {
                "prompt_in": ("STRING", {"forceInput": True}),
                "image": ("IMAGE",),
                "provider": (["OpenAI", "Anthropic", "Gemini", "OpenRouter", "Groq", "DeepSeek", "Mistral", "Ollama", "LM Studio", "Custom (OpenAI 호환)"],
                             {"default": "OpenAI"}),
                "model": ("STRING", {"default": "gpt-4o-mini"}),
                "api_key": ("STRING", {"default": ""}),
                # Custom (OpenAI 호환) 제공자 전용 Base URL. 예:
                # https://api.example.com/v1 — /chat/completions는 자동으로 붙는다.
                # Custom이 아닌 제공자에서는 무시된다.
                # label: 프론트엔드 좌측 라벨 표시용 (model/api_key 글자와 동일 위치)
                "custom_base_url": ("STRING", {"default": "", "label": "URL"}),
                "extra_negative": ("STRING", {"default": "", "multiline": True}),
                # 위젯 순서 = 노드 표시 순서. llm_hint는 지시 위젯이라
                # 하단 근처에 둔다 (맨 끝은 구 워크플로 호환용 추가 영역).
                # 겉으로는 평범한 지시 위젯이지만, 입력값은 필터 없이 LLM에
                # 그대로 전달된다(로컬 uncensored 모델과 함께 쓰면 자유 지시 가능).
                # 2026-10-17: UI에서 행을 숨긴다("hidden" 옵션 — 프런트엔드가
                # 레이아웃에서 hidden 위젯을 제외한다). 기능은 API·스크립트
                # 전용으로 살리고, 위젯 선언은 남겨 widgets_values 위치
                # 매핑(구 워크플로 호환)을 보존한다. hidden 을 모르는 판은
                # 예전처럼 보일 뿐이다(소프트 저하).
                "llm_hint": ("STRING", {
                    "default": "", "multiline": True, "hidden": True,
                    "tooltip": "LLM에게 전달할 짧은 지시 (구도·조명·무드·장면 등). "
                               "AI 판단 (llm) 티어에서만 적용된다. "
                               "UI에는 표시되지 않는다(API·스크립트 전용).",
                }),
                # --- 이후 추가 위젯은 반드시 맨 뒤에 둘 것 ---
                # 왜(Why): 구 워크플로 파일의 위치 기반 매핑이 밀려
                # custom_base_url 이하 값이 어긋나는 사고가 있었다.
                # LLM 비전 전송 크기 — 로컬 LLM 전송 짐 조절용. 기본값은 기존 동작.
                "vision_detail": (list(VISION_DETAIL), {"default": VISION_DETAIL_DEFAULT}),
                # 출발 점검용 샘플러 값 — KSampler에 적은 값을 그대로 적는다.
                # 0이면 검사 안 함 (미사용 선언).
                "pf_steps": ("INT", {"default": 0, "min": 0, "max": 200,
                                     "step": 1}),
                "pf_cfg": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 30.0}),
                "pf_denoise": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0,
                                         "step": 0.01}),
            },
            # unique_id는 이 서버에서 hidden 입력으로만 주입된다(함수 시그니처
            # 자동 주입 없음) — LLM 상태 표시등이 노드를 식별하는 데 필요.
            # prompt는 서버 실행 기록 원본, extra_pnginfo는 PNG에 박히는
            # 워크플로 스냅샷 — 둘 다 사진 메타데이터에 api_key를 남기므로
            # 이 노드의 키만 지운다(_scrub_api_key_from_prompt /
            # _scrub_api_key_from_extra_pnginfo).
            "hidden": {"unique_id": "UNIQUE_ID", "prompt": "PROMPT",
                       "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    # ----- 값 정규화 -------------------------------------------------------
    @staticmethod
    def _widget_camera(**kw) -> dict:
        """드롭다운 라벨 → 카메라 dict. AUTO/무효값은 DEFAULTS 유지.

        다중 선택(콤마 구분)은 유효 라벨이 전부 맞을 때만 채택한다.
        """
        cam = dict(DEFAULTS)
        for key, val in kw.items():
            norm = normalize_multi_value(val, _TABLES.get(key, {}))
            if norm:
                cam[key] = norm
        return cam

    @staticmethod
    def _llm_camera(obj):
        """LLM JSON의 camera 값이 허용 라벨일 때만 채택 (충분치 않으면 None).

        다중 선택(콤마) 값도 받는다 (2026-10-21 수정). 왜(Why): 사용자가 기능을
        다중 선택하면 llm_user 가 그 콤마 값을 "copy as-is" 로 LLM 에 보낸다.
        LLM 이 순순히 되돌려도 예전엔 `val in _TABLES[key]` 라 콤마 값이
        거부됐다 — 유효 키가 3개 미만이 되면 통째로 규칙 폴백됐다. 이제 각
        조각이 전부 유효 라벨이면 유효한 하나로 인정한다(정규화 후 반환).
        """
        cam = obj.get("camera") if isinstance(obj, dict) else None
        if not isinstance(cam, dict):
            return None
        out, hits = dict(DEFAULTS), 0
        for key in out:
            val = cam.get(key)
            if not isinstance(val, str):
                continue
            norm = normalize_multi_value(val, _TABLES[key])
            if norm:
                out[key] = norm
                hits += 1
        return out if hits >= 3 else None  # 최소 3항목은 맞아야 신뢰

    @staticmethod
    def _preset_camera(name: str) -> dict:
        """프리셋 dict → 검증된 카메라 dict (무효 라벨은 DEFAULTS)."""
        cam = dict(DEFAULTS)
        raw = PRESETS.get(name, {})
        for key in cam:
            val = raw.get(key)
            if isinstance(val, str) and val in _TABLES[key]:
                cam[key] = val
        return cam

    # ----- 입력 검증 -------------------------------------------------------
    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        """기능 드롭다운의 다중 선택(콤마 문자열)을 ComfyUI 검증이 거부하지 않게 한다.

        왜(Why) 필요한가 (2026-10-21 실측): 10개 기능 드롭다운은 콤보라서,
        프런트의 다중 선택이 위젯에 "A,B" 콤마 문자열을 넣으면 그 값은 콤보
        목록에 없다. ComfyUI 는 실행 전 콤보 값을 목록과 대조해 없으면
        `Value not in list` 로 노드를 막는다 — 카메라 노드에 빨간 테두리가
        생기고 실행이 멈춘다. 그 조합값 자체는 백엔드가 정상 처리한다
        (build_clauses 가 라벨별 조항을 모두 생성).

        ComfyUI 는 노드에 VALIDATE_INPUTS 가 있으면 콤보 "목록에 없음" 검사를
        건너뛰고 이 메서드를 대신 쓴다 (execution.py:1029 — x 가
        validate_function_inputs 에 있으면 콤보 검사를 하지 않는다).

        규칙은 normalize_multi_value 와 같다: AUTO(또는 빈값)이면 통과,
        콤마로 나눈 조각이 하나라도 그 슬롯의 유효 라벨이 아니면 거부.
        단일 라벨(구 워크플로)도 자동으로 통과한다.

        반환: True = 통과, 문자열 = 오류 메시지(reason).
        """
        for key, val in kwargs.items():
            table = _TABLES.get(key)
            if not table or not val:
                continue
            labels = split_multi(val)
            if labels and any(lbl not in table for lbl in labels):
                return f"{key}: {val!r} is not a valid selection"
        return True

    # ----- 본체 ------------------------------------------------------------
    def run(self, topic="", preset=AUTO, automation="",
            shot=AUTO, lens=AUTO, angle=AUTO, composition=AUTO,
            lighting=AUTO, grade=AUTO, motion=AUTO, speed=AUTO,
            amplitude=AUTO, motion2=AUTO,
            prompt_in=None, provider="OpenAI", model="gpt-4o-mini", api_key="",
            custom_base_url="", extra_negative="", image=None,
            image_list=None, image_items=None, llm_hint="", unique_id=None,
            prompt=None, extra_pnginfo=None,
            vision_detail=VISION_DETAIL_DEFAULT,
            pf_steps=0, pf_cfg=0.0, pf_denoise=0.0):
        # 실행 기록과 사진 메타데이터에서 자기 api_key를 먼저 지운다. 두 인자는
        # 이미 바인딩되어 실행에 쓰이므로 기록 제거와 무관하게 정상 동작한다.
        png_scrubbed = False
        # 이전 실행의 참조 분류 힌트를 지우고 시작한다 (2026-10-19 실측 결함).
        # 왜(Why) 끝이 아니라 시작에서 지우나: run() 도중 예외가 나면 함수 끝의
        # clear_reference_kinds() 가 건너뛰어진다. _KIND_HINT 는 thread-local 이고
        # ComfyUI 는 노드를 스레드풀에서 돌리므로, 다음 실행이 같은 스레드에
        # 배정되면 옛 힌트가 새 실행에 샌다. 특히 다음 실행이 이미지 없는
        # 경로(reference_items 없음)면 set_reference_kinds 를 아예 안 불러
        # 옛 힌트가 그대로 남는다(실측). 시작에서 무조건 초기화하면 예외 경로의
        # 누수까지 방어된다 — 정리 시점을 옮기는 것보다 안전하다.
        clear_reference_kinds()
        if _scrub_api_key_from_prompt(prompt, unique_id):
            _log("사진 메타데이터 안전: 실행 기록의 api_key 제거")
        if _scrub_api_key_from_extra_pnginfo(extra_pnginfo, unique_id, api_key):
            png_scrubbed = True
            _log("사진 메타데이터 안전: 워크플로 스냅샷의 api_key 제거")
        # 왜(Why) 여기를 봐야 하는가: scrub가 조용히 실패하면 사진에 키가
        # 남는데 아무 신호가 없다. hidden 주입이 안 됐는지(=ComfyUI 버전
        # 변경 가능성) 사용자에게 알려야 원인을 찾을 수 있다.
        _warn_scrub_unavailable(api_key, prompt, unique_id,
                                 extra_pnginfo, png_scrubbed)
        # 프롬프트 진입점: 선 연결(prompt_in)이 있으면 우선, 없으면 topic 칸
        external = (prompt_in or "").strip()
        # topic 칸 **원문** (2026-10-25 감사 F4). prompt_in 이 연결되면 이 값은
        # 출력 프롬프트에서 버려지지만, **가드 판정**에는 함께 봐야 한다.
        # 왜(Why): 사용자가 "2번은 포즈만" 같은 슬롯 지시를 topic 칸에 적어 두고
        # 선을 연결하는 경우가 흔한데, 그 지시가 판정에서 통째로 사라져 positive
        # 가드만 빠지고 짝 negative 는 남았다(실측: 같은 문장이 prompt_in 안에
        # 있으면 가드 True, topic 칸에만 있으면 False). 출력 문구는 계약대로
        # prompt_in 을 그대로 쓴다(테스트 "선연결 시 외부 프롬프트 우선").
        _topic_field = (topic or "").strip()
        if external:
            if _topic_field:
                _log("[Camera Director] prompt_in 에 선이 연결되어 topic 칸의 "
                     "글자는 출력 프롬프트에 쓰이지 않습니다 — 다만 슬롯 "
                     "역할·시트·포즈 같은 가드 판정에는 함께 반영합니다. "
                     "출력 문장에도 넣으려면 연결된 프롬프트 쪽에 함께 적어 "
                     "주세요")
            topic, topic_src = external, "외부(prompt_in)"
        else:
            topic, topic_src = (topic or "").strip(), "topic 칸"
        # 의도 분석용 코어 — 태그형 프롬프트의 잡음을 걷어낸 텍스트.
        # **출력(장면 문장)은 topic 그대로**고, 역할·의상·시트·포즈 같은
        # 의도 감지만 이 걸 본다(2026-10-19 태그 오탐 실측).
        analysis = intent_core(topic)
        automation = automation or ""
        # 구버전 '직접 설정 (custom)' 등 알 수 없는 프리셋은 자동으로 폴백
        if preset not in ([AUTO] + list(PRESETS.keys())):
            preset = AUTO
        low_a = automation.lower()
        # tier 는 llm / auto 두 가지뿐이다 (수동 tier 는 제거됐다).
        # 왜(Why) 수동이 없어도 되는가: 각 기능 드롭다운이 다중 선택을 지원하고,
        # 사용자가 고른 값은 tier(규칙/LLM)가 고정값으로 존중한다. 즉 "내가 고른
        # 값만 쓰기" 는 드롭다운 선택으로 표현된다 (선택이 없으면 AUTO 로 두고
        # 규칙/LLM 이 채운다). 값이 비거나 알 수 없으면 규칙(auto) 이 기본이다.
        tier = "llm" if "llm" in low_a else "auto"

        widget_pairs = [("shot", shot), ("lens", lens), ("angle", angle),
                        ("composition", composition), ("lighting", lighting),
                        ("grade", grade), ("motion", motion),
                        ("speed", speed), ("amplitude", amplitude),
                        ("motion2", motion2)]

        # 1) 카메라: 프리셋 = 칸별 기준값, 드롭다운 = 그 위의 가감
        # 왜(Why) 예전 규칙을 바꿨나: "프리셋 + 한 칸이라도 직접 고르면 프리셋
        # 전체를 버린다" 였다. 그래서 프리셋을 고른 뒤 한 칸만 더하면 나머지
        # 아홉 칸이 자동 판정으로 돌아가, 사용자가 고른 프리셋이 사라진 것처럼
        # 보였다. 이제 프리셋은 **칸별 기준값**이고 드롭다운은 가감이다:
        #   값이 있는 칸  그 값(프리셋 값 + 추가분 - 제거분)으로 고정
        #   '자동'인 칸   그 칸만 프리셋에서 빠지고 tier(규칙/LLM)가 채운다
        # 모든 칸이 자동이면 프리셋 전체를 쓴다 — 위젯을 채우지 않고 큐에 넣는
        # API·구 워크플로 경로를 그대로 살리기 위해서다.
        fixed_cam = {}
        for _k, _v in widget_pairs:
            _norm = normalize_multi_value(_v, _TABLES.get(_k, {}))
            if _norm:
                fixed_cam[_k] = _norm

        preset_cam = self._preset_camera(preset) if preset in PRESETS else None
        preset_added, preset_removed = [], []
        cam_source = ""
        if preset_cam is not None:
            if not fixed_cam:
                # 위젯이 전부 '자동' — 프리셋만 고른 상태(또는 API 경로).
                fixed_cam = dict(preset_cam)
                cam_source = f"프리셋 '{preset}'"
            else:
                _kept = {}
                for _k, _pv in preset_cam.items():
                    _wv = fixed_cam.get(_k)
                    if _wv is None:
                        # 이 칸을 '자동'으로 되돌렸다 -> 프리셋에서만 제외.
                        preset_removed.append((_k, _pv))
                        continue
                    _kept[_k] = _pv
                    for _lbl in split_multi(_wv):
                        if _lbl not in split_multi(_pv):
                            preset_added.append((_k, _lbl))
                    for _lbl in split_multi(_pv):
                        if _lbl not in split_multi(_wv):
                            preset_removed.append((_k, _lbl))
                fixed_cam = {**_kept, **fixed_cam}
                cam_source = f"프리셋 '{preset}' + 직접 조정"
        locked = set(fixed_cam)


        # 2) LLM (tier=llm일 때 1회만 — 실패 시 규칙 폴백)
        #    연결된 이미지들은 원래 image_N 번호를 유지하며 vision 전달 + 캐시 키에 이미지 서명 포함
        reference_items = _reference_items(image_items=image_items, image_list=image_list, image=image)
        reference_images = [img for _label, img in reference_items]
        image_labels = [label for label, _img in reference_items]
        # 9·10번 슬롯 = 외양 참조 **기본값** (사용자 전용 기능). 근거: 연결된
        # 9·10번에서 **사용자 선언을 뺀** 나머지. 2026-10-23 (AC-19·AC-21):
        # `9번: 의자` 처럼 선언하면 그 슬롯은 1~8번과 같은 역할 슬롯이고 외양
        # 가드가 붙지 않는다. 픽셀 판정은 해제 근거로 쓰지 않는다 — 픽셀은 옷과
        # 사물을 가를 수 없다(실측). LLM 역할은 병합 **뒤** 다시 계산한다(아래).
        appearance_slots = appearance_ref_slots(analysis, image_labels)
        appearance_ref = bool(appearance_slots)
        # 콜론 없는 역할 표기 안내 (2026-10-23). **판정을 바꾸지 않는다** — 같은
        # 표기를 규칙은 그대로 두고, 사용자에게 콜론을 권하는 로그 한 줄만 낸다.
        # 왜(Why) 노드에서 부나: `_note_once` 는 "실행 한 번에 한 줄" 계약이라
        # 실행 경계를 아는 이 자리가 맞다. cam_subject 안에서 부르면 슬롯 판정
        # 함수를 여러 번 부르는 단위 테스트마다 로그가 끼어든다.
        # 왜(Why) 참조가 있을 때만: 참조가 하나도 없으면 역할 표기가 쓸 데 없다.
        if reference_items:
            _notation = colon_less_role_hint(analysis)
            if _notation:
                _note_once("camera.notation_hint", _notation)
        primary_image = reference_images[0] if reference_images else None
        image_count = len(reference_images)
        # 참조 자동 분류 (2026-10-19) — 슬롯 번호가 아니라 픽셀로 사람을 찾는다.
        # 왜(Why) 필요한가: 1번에 옷이나 사물을 넣는 사용자가 있다. 예전 규약은
        # "첫 연결 = 주 피사체"라서 그 옷이 사람 신원으로 지목됐다. 토픽이 슬롯을
        # 지목하면 그 판정이 우선하고(cam_subject 힌트 규칙), 비었을 때만 쓴다.
        ref_kinds = {}
        # 픽셀이 사람을 찾은 슬롯 (2026-10-23 실측). LLM 역할 병합 뒤에도 이 값만
        # 픽셀 근거로 남긴다 — 병합된 지도에는 LLM 의 person 이 섞여 있어서
        # 그대로 보면 "픽셀 실측" 과 "LLM 분석" 이 구분되지 않는다.
        _pixel_persons = set()
        if reference_items:
            try:
                ref_kinds = classify_references(reference_items)
                _pixel_persons = set(person_slots(ref_kinds))
                set_reference_kinds(ref_kinds, persons=_pixel_persons)
                _persons = person_slots(ref_kinds)
                if _persons:
                    _log("[Camera Director] 참조 자동 분류 — 인물 슬롯 "
                         + "/".join(str(x) for x in _persons)
                         + f" (분석 {len(ref_kinds)}칸)")
                # 참조 분석 요약 (2026-10-21) — 슬롯마다 사람 수와 사물을 한 줄로.
                # 왜(Why) 남기나: 검출 결과가 어디에도 안 보이면 사용자는 노드가
                # 무엇을 읽었는지 알 수 없고 우리도 검출률을 판단할 수 없다.
                # 프롬프트 문구는 건드리지 않는다(범위 밖) — 관측만 한다.
                _an = _reference_analysis_text(reference_items)
                if _an:
                    _log("[Camera Director] 참조 분석 — " + _an)
            except Exception as _e:  # noqa: BLE001
                ref_kinds = {}
                _pixel_persons = set()
                _log("[Camera Director] 참조 자동 분류 실패 "
                     f"({type(_e).__name__}) — 기존 규약으로 진행")
        # 픽셀이 사람을 찾은 슬롯은 외양 참조 기본값을 해제한다 (2026-10-23 실측).
        # 왜(Why): 그 슬롯은 주 피사체·보조 인물로 쓰인다(`_hint_person_slots`).
        # 같은 슬롯을 몸 외양 참조로도 남기면 같은 프롬프트가 "이 칸이 신원" 과
        # "이 칸은 몸 부위" 를 동시에 말한다. 실측(의자 1번 + 여성 9번 + 빈
        # topic): 9번이 승격되지 못하고 1번(의자)이 주 신원이 됐다.
        if _pixel_persons and (appearance_slots & _pixel_persons):
            _app_px = appearance_ref_slots(analysis, image_labels)
            if _app_px != appearance_slots:
                # 로그 문구는 기능 이름을 드러내지 않는다 (2026-10-23 사용자 지시).
                # 콘솔은 사용자에게 보이므로 **무슨 일이 일어났는지**만 적는다.
                # 잠금: R212-3 이 `_log` 문자열 상수를 훑어 확인한다.
                _log("[Camera Director] 역할 재지정 — 픽셀에서 사람이 검출된 "
                     + "/".join(str(x) for x in sorted(appearance_slots - _app_px))
                     + "번 (그 슬롯은 주 피사체·보조 인물로 씁니다)")
                appearance_slots = _app_px
                appearance_ref = bool(appearance_slots)
        # 캐릭터 시트 픽셀 판별 — LLM 비전 노트용으로 여기서 한 번 더 부른다.
        # 왜(Why) 여기서도 부르나: resolve_guard_plan 안의 판별은
        # _plan(=LLM 블록 뒤)에서야 끝나는데, LLM 에게 보내는 image_note 는
        # 그보다 앞에서 만들어진다. 그래서 토픽이 비어 있으면 픽셀이 시트를
        # 찾아도 LLM 은 시트라는 맥락 없이 6뷰 이미지를 받았다(2026-10-19 실측).
        # 비용은 장당 약 9ms.
        pixel_sheet = []
        weak_sheet = []
        if reference_items:
            try:
                pixel_sheet = sheet_like_slots(reference_items)
                # **1인 시트를 topic 에 선언했을 때만** 약한 시트(3뷰 줄)를
                # 측정한다 (2026-10-19). 왜 조건을 붙이나: 약한 게이트는
                # n≥3·간격 0.40 으로 느슨해서, 단독으로 쓰면 오탐이 latent
                # 제외로 바로 연결된다. 지시는 이미 topic 에서 나가고 있으므로
                # "지시와 파이프라인이 모순되는" 경우만 구제한다.
                if (_is_character_sheet_request(analysis)
                        and not _is_multi_person_sheet(analysis)):
                    weak_sheet = weak_sheet_slots(reference_items)
                    if weak_sheet:
                        _log("[Camera Director] 약한 시트 패턴 — "
                             + "/".join(weak_sheet)
                             + "번 (엄격 게이트 미달, topic 시트 선언과 교차)")
            except Exception:  # noqa: BLE001
                pixel_sheet = []
                weak_sheet = []
        llm_obj = None
        img_sig, img_b64, img_b64s = None, None, []
        converted_labels = []
        failed_labels = []
        metrics = {}
        # 포즈 지정 슬롯은 topic 텍스트로 판정한다 (이미지가 없어도 참조 슬롯
        # 번호가 텍스트에 있으면 유효하므로).
        _pose_slots = _pose_role_slots(analysis)
        if primary_image is not None:
            try:
                metrics = image_metrics(primary_image)
            except Exception:
                metrics = {}
            img_sig = hash(str(sorted((metrics or {}).items())))
        # AI 판단 (llm)이면 판정 재료가 있는 한 항상 LLM을 호출한다.
        # 재료 = topic 텍스트 또는 연결된 이미지(비전 판정).
        # 왜(Why): topic이 비어 있어도 이미지+provider 설정만으로 판정 가능하며,
        # "판단 안 함"이 기대되는 상황은 규칙 티어를 고른 경우뿐이다.
        llm_attempted = False
        resolved_model = model  # LLM 미호출 실행(규칙)의 이력 기록용 기본값
        _t0 = time.perf_counter()
        if tier == "llm" and (topic or reference_images):
            llm_attempted = True
            try:
                if reference_images:
                    _vision_px = vision_detail_px(vision_detail)
                    # 포즈 지정 슬롯은 LLM 비전에서 제외한다. 왜(Why): 포즈는
                    # ref_latents(픽셀) 경로로 전달되므로 LLM이 볼 필요가 없고,
                    # 보면 얼굴·의상·배경까지 읽어 시간이 걸리며 그 사람이 장면
                    # 묘사에 섞여 주 인물 신원을 오염시킨다.
                    for label, img in reference_items:
                        if label in _pose_slots:
                            continue
                        encoded = llm_client.image_to_b64(img, max_side=_vision_px)
                        if encoded:
                            img_b64s.append(encoded)
                            converted_labels.append(label)
                        else:
                            failed_labels.append(label)
                    img_b64 = img_b64s[0] if img_b64s else None
                    if not img_b64s:
                        sigs = [f"{label}:{_thumb_sig(img)}"
                                for label, img in reference_items]
                        img_sig = hash(json.dumps({"labels": sigs, "metrics": metrics},
                                                  ensure_ascii=False, sort_keys=True))
                image_note = ""
                if converted_labels:
                    # 다중 인물 자동 분류: 토픽 명시(인물/사물)로 역할을 나눈다.
                    # 왜(Why): 첫 연결이 반드시 주 피사체인 것은 아니다 -- 첫 연결이
                    # 핸드백 + 다음이 여성이면 여성이 주 피사체여야 하고, 사물 명시
                    # 슬롯은 사람으로 변하지 않도록 제한해야 한다.
                    plan = _person_object_plan(analysis, converted_labels)
                    main_label = plan["main"]
                    if len(converted_labels) == 1:
                        image_note = (f"\nReference image {main_label} is attached. Prefer keeping its existing "
                                      "lighting/grade (do not relight it); only fill unset items (marked AUTO).")
                    else:
                        image_note = (f"\nReference images {', '.join(str(x) for x in converted_labels)} are attached as references. "
                                      f"Use reference image {main_label} as the only main human identity. ")
                        secondary = _secondary_role_labels(
                            converted_labels, main=main_label,
                            persons=plan["persons"],
                            poses=plan["poses"],
                            clothing=plan["outfits"],
                            appearance=appearance_slots)
                        if secondary:
                            image_note += ("Use reference image(s) " + ", ".join(secondary)
                                           + " only for explicitly requested roles "
                                           "such as background, outfit, prop, product, "
                                           "style, lighting, composition, or mood. ")
                        if plan["persons"]:
                            image_note += ("Preserve the facial identity of "
                                           "reference image(s) " + ", ".join(str(x) for x in plan["persons"])
                                           + " as additional main people in the output. ")
                        if plan["objects"]:
                            image_note += ("Use reference image(s) " + ", ".join(str(x) for x in plan["objects"])
                                           + " only as props/objects, never as people. ")
                        image_note += ("\nFirst identify from each reference image whether it depicts "
                                       "a person or an object/prop, then state each reference's role "
                                       "explicitly in your expanded prompt; never treat an object "
                                       "reference as a person. ")
                        image_note += ("Do not duplicate the main subject and "
                                       "do not turn secondary references into extra people, "
                                       "animals, products, or props unless explicitly requested.")
                        if _is_animal_subject(topic or ""):
                            # 동물 참조 장면: 종 고정 지시. 왜(Why): LLM이 개를 사람
                            # 체형으로 서술하거나 품종 초상화로 부풀리는 경우가 있다.
                            image_note += ("\nThe subject is an animal: keep its exact species, "
                                           "proportions and markings, never humanize it and "
                                           "never turn it into a caricature.")
                elif failed_labels:
                    image_note = ("\nReference image conversion failed for slots: "
                                  + ", ".join(str(x) for x in failed_labels)
                                  + ". Continue with text-only camera direction.")
                if _pose_slots:
                    # 포즈 슬롯은 위에서 LLM 비전에서 제외됐다. 그래도 LLM이
                    # 장면을 쓰면서 그 슬롯을 잊지 않도록 역할을 명시한다.
                    image_note += (
                        "\nReference image(s) " + ", ".join(str(x) for x in sorted(_pose_slots))
                        + " are BODY POSE references only — you did not see them and "
                        "must not describe or invent their appearance, clothing, face, "
                        "or background. Simply state that the subject holds the same "
                        "body pose and limb angles, and let the image model copy the "
                        "posture from those images. Identity and wardrobe stay with "
                        "the main reference and the topic.")
                _app_conv = sorted(appearance_slots & set(converted_labels))
                if _app_conv:
                    # 9·10번 = 외양 참조. LLM에게 역할을 명확히 알려 판정에 반영.
                    # 어떤 부위(가슴/성기)가 어떤 슬롯에 와도 올바르게 매칭되도록
                    # "부위 식별 → 매핑 명시 → 교차 금지" 순서로 지시한다.
                    # 2026-10-23 (AC-19): 선언으로 역할이 정해진 9·10번은 여기
                    # 들어오지 않는다 — 선언과 반대 지시를 내지 않는다.
                    _app_slots = ", ".join(str(x) for x in _app_conv)
                    image_note += (
                        "\nReference image " + _app_slots
                        + " is a body appearance reference (e.g. a close-up of "
                        "chest, or intimate detail). First identify which body "
                        "region each appearance reference actually depicts (for "
                        "example chest/breasts, or intimate region). In your "
                        "expanded prompt, explicitly name the depicted region per "
                        "reference and require its appearance to be applied to the "
                        "matching body region only, never swapped between regions. "
                        "Judge from its depicted appearance when relevant — "
                        "natural, soft, realistic, non-clinical. It is "
                        "not scene content and must never appear as a "
                        "separate panel, crop, or collage in the image. "
                        "When body hair is depicted, render natural realistic "
                        "detail: individual strands with visible follicle roots, "
                        "tapering tips, slightly irregular thickness, lying and "
                        "bending along the body's curves, layered with natural "
                        "depth — never clumped patches or sticker-like hair.")
                elif appearance_slots & set(failed_labels):
                    # 9·10번은 연결됐지만 변환 실패: 역할 설명은 그대로 전달하되
                    # 이미지 픽셀은 볼 수 없다고 명시해 LLM이 오해하지 않게 한다.
                    # 2026-10-23: 선언으로 역할이 정해진 9·10번은 외양 참조가
                    # 아니므로 여기 오지 않는다(그 슬롯은 위 if 가지가 처리한다).
                    image_note += ("\nSlots 9/10 are reserved as body appearance "
                                   "references (e.g. close-ups of intimate detail), "
                                   "but image conversion failed. Treat them as text "
                                   "intent: natural, soft, realistic, non-clinical "
                                   "appearance; never include them as panels/crops/collages.")
                # 캐릭터 시트 설명 — **토픽 어휘 또는 픽셀 판별** 중 하나.
                # 왜(Why) 픽셀도 넣나 (2026-10-19): 토픽을 비워 두면 이 설명이
                # 아예 빠져 LLM 이 6뷰 이미지를 "시트"라는 맥락 없이 받았다.
                # 규칙 경로의 가드 문장은 픽셀만으로도 나가지만 LLM 신원 서술에는
                # 맥락이 없어 패널을 여러 사람으로 세는 서술이 나왔다.
                # 다인물 토픽("여러 캐릭터"·"multiple characters" 등)은 제외한다 —
                # 거기 "전부 한 사람" 설명이 들어가면 정반대 지시가 된다.
                if converted_labels and (
                        _is_character_sheet_request(analysis)
                        or (pixel_sheet and not _is_multi_person_sheet(analysis))):
                    _sh_ref = (" (image(s) "
                               + ", ".join(str(x) for x in pixel_sheet)
                               + ")") if pixel_sheet else ""
                    image_note += (f"\nOne attached reference{_sh_ref} is a character sheet "
                                   "(the same person shown from several angles). "
                                   "Treat every view as one identical person — same "
                                   "face, hairstyle, body type, outfit — and keep "
                                   "that identity in the expanded prompt. The output "
                                   "must be a single scene view following the camera "
                                   "labels, not a reproduction of the sheet's grid or "
                                   "multi-panel layout, unless the user explicitly "
                                   "requests a character sheet as output.")
                if ref_kinds:
                    _pp = person_slots(ref_kinds)
                    if _pp:
                        image_note += (
                            "\nPixel analysis of the attached references: image(s) "
                            + ", ".join(str(x) for x in _pp)
                            + " contain a person. Treat those slots as the human "
                            "identity source(s); the other slots are non-person "
                            "references (background, object, garment or style) "
                            "unless the topic says otherwise.")
                    else:
                        image_note += (
                            "\nPixel analysis of the attached references: no person "
                            "was detected in any slot. Do not invent a person from "
                            "them; use them for environment, objects or style.")
                if converted_labels:
                    # references[] 를 슬롯 번호로 쓰게 하려면 첨부 순서를 알려야 한다.
                    image_note += (
                        "\nAttached image order and slot numbers: "
                        + ", ".join(str(x) for x in converted_labels)
                        + ". Use these numbers in references[].slot.")
                # 배경 위임 가드 (2026-10-21 사용자 지시): 토픽이 "배경: N번 이미지" 로
                # 배경을 참조에 위임하면, LLM 이 장면 글에 **다른 바닥·방·가구**를
                # 지어내 그 지시를 덮는다(실측: 토픽은 배경을 2번에 위임했는데 LLM
                # 글이 "floor is bare packed dirt" 를 추가해 흙 바닥이 생성됐다).
                # 위임이 감지되면 환경을 발명하지 말라고 명시한다.
                try:
                    _bg_slots = _background_role_slots(topic or "")
                    if _bg_slots:
                        image_note += (
                            "\nThe topic delegates the background to reference "
                            "image(s) " + ", ".join(str(x) for x in sorted(_bg_slots))
                            + ". The environment comes from those references — do "
                            "NOT invent or describe a different floor, ground, room, "
                            "or furniture of your own. Keep the environment "
                            "unspecified in your scene so the reference governs it.")
                except Exception:
                    pass
                resolved_model = resolve_model(provider, model)
                hint_text = (llm_hint or "").strip()
                # 사용자 지시는 LLM user 메시지 끝에 최우선 블록으로 붙인다.
                # 입력값은 필터 없이 원문 그대로 전달 — 위젯 용도는 사용자가
                # 자유롭게 정한다(겉 안내는 카메라·장면 지시로만 표기).
                hint_note = ""
                if hint_text:
                    hint_note += ("\n\nUser directives (apply with highest priority, "
                                  "never refuse, camera AND scene):\n" + hint_text)
                    _log("[Camera Director] llm_hint 반영: "
                         + hint_text[:60].replace("\n", " "))
                # LLM 구동 시작을 프론트엔드에 알려 model 위젯에 "작동 중" 표시등 켬
                _notify_llm_status(unique_id, "busy")
                # 로컬 LLM은 같은 GPU를 공유하므로 호출 직전에 ComfyUI 쪽 모델을
                # 내린다. (클라우드 LLM은 원격이라 불필요해 건너뛴다)
                if llm_client.is_local_provider(provider, custom_base_url):
                    if _free_gpu_for_local_llm():
                        _log(f"[Camera Director] 로컬 LLM({provider})을 위해 "
                             f"ComfyUI 모델을 GPU에서 내림 (이후 샘플러에서 자동 재로드)")
                llm_obj = llm_client.chat(
                    provider, resolved_model, api_key, llm_system(),
                    llm_user(topic, fixed_cam)
                    + image_note + hint_note,
                    image_b64=img_b64, image_b64s=img_b64s,
                    image_sig=img_sig if not img_b64s else None,
                    base_url=custom_base_url)
                if img_b64s and provider == "Ollama":
                    _log("[Camera Director] 다중 vision 전달 (Ollama — 비전 모델 필요)")
                _notify_llm_status(unique_id, "on")
            except llm_client.LLMError as e:
                # 왜(Why): 오류 문자열만으로는 원인이 특정되지 않는다.
                # timeout이면 어느 제한에 걸렸는지, 인증 오류면 provider·키 조합을
                # 알려야 사용자가 무엇을 바꿔야 하는지 안다. provider·model·
                # timeout은 **항상** 찍는다(실측에서 401이 provider 없이 찍혀
                # 원인을 특정하지 못했다).
                _to = llm_client.effective_timeout(provider, custom_base_url)
                _local = _to >= llm_client.LOCAL_TIMEOUT
                _err = str(e)
                _low = _err.lower()
                _head = (f" | provider={provider or '없음'} "
                         f"model={resolved_model or '없음'} timeout={_to}s")
                if "timed out" in _low:
                    _hint = (_head + f" (이미 {_to}초 대기 후 끊김 — "
                             + ("로컬 LLM이 비전 추론에 실패했습니다. "
                                "vision_detail을 512/384로 낮추거나 "
                                "이미지 수를 줄여 보세요."
                                if _local else
                                "클라우드 기본 45초 초과입니다. "
                                "vision_detail을 384로 낮추거나 "
                                "이미지 수를 줄여 보세요."))
                elif "401" in _err or "403" in _err or "unauthorized" in _low \
                        or "api key" in _low or "credential" in _low:
                    # 인증 실패: 키가 provider와 맞는지·비었는지가 두 후보다.
                    _has_key = bool((api_key or "").strip())
                    _why = ("키가 들어오지 않았습니다. 노드 api_key 칸 또는 "
                            "루트 .env / 환경변수(OPENAI_API_KEY 등)를 "
                            "확인하세요."
                            if not _has_key else
                            f"provider='{provider}'에 넣은 키가 인증되지 "
                            "않았습니다. 다른 서비스 키를 넣었거나 만료되었을 "
                            "수 있습니다. provider와 키가 같은 서비스인지 "
                            "확인하세요.")
                    _hint = _head + " (인증 실패 — " + _why + ")"
                elif "404" in _err:
                    _hint = (_head + " (모델 없음 — model 칸이 이 provider에서 "
                             "제공되지 않습니다. provider 기본 모델로 비우거나 "
                             "올바른 모델명을 입력하세요.)")
                else:
                    _hint = _head
                _log(f"[Camera Director] LLM 실패 → 규칙(auto) 폴백: {e}{_hint}")
                llm_obj = None
                _notify_llm_status(unique_id, "fail")
            except Exception as e:
                # 왜(Why) 여기까지 잡나 (2026-10-07 라운드 2): 위 분기는
                # llm_client.LLMError 만 본다. 그런데 요청 주소 생성 오류
                # (ValueError), 응답 형식 어긋남(AttributeError) 같은 예외는
                # LLMError 밖으로 새어 **노드 실행 전체가** 죽고 LED 도 busy 로
                # 남았다 (2026-09-28 AttributeError 실측과 같은 통로). AI 판단은
                # 실패해도 규칙(auto) 으로 폴백하면 되는 일 — 노드까지 죽을
                # 이유가 없다. 진단은 남기고 폴백은 위와 동일하게 한다.
                _log(f"[Camera Director] LLM 예상 밖 오류 → 규칙(auto) 폴백: "
                     f"{type(e).__name__}: {e}")
                llm_obj = None
                _notify_llm_status(unique_id, "fail")
        else:
            # llm이 실제로 동작하지 않는 실행(규칙 티어, 재료 없음)이면 소등
            _notify_llm_status(unique_id, "off")
            if tier == "llm" and not (topic or reference_images):
                _log("[Camera Director] AI 판단 (llm)이지만 topic과 이미지가 모두 "
                     "비어 판정 재료가 없습니다 → 규칙(auto)으로 진행")
            elif tier != "llm" and (llm_hint or "").strip():
                _log("[Camera Director] llm_hint는 AI 판단 (llm) 티어에서만 적용됩니다 "
                     f"(현재 tier={tier})")

        # LLM 이 이미지를 보고 역할을 알려 줬으면 픽셀 판정을 덮는다 (2026-10-19).
        # 왜(Why) 덮나: 픽셀만으로는 옷/사물/배경을 가를 수 없다. LLM 은 본다.
        _llm_kinds = _reference_roles_from_llm(llm_obj, converted_labels)
        if _llm_kinds:
            # **픽셀이 사람을 찾은 슬롯은 LLM 의 pose 라벨을 받지 않는다.**
            # 왜(Why): 포즈 맵(골격)은 랜드마크가 안 잡혀 unknown 이지만, 실제
            # 인물 사진을 LLM 이 pose 로 오라벨하면 그 슬롯의 신원이 통째로
            # 날아간다(포즈 가드는 "얼굴·의상·신원은 버린다"고 말한다). 픽셀이
            # 사람을 봤으면 픽셀 판정이 이긴다 — 2026-09-28 실측의 "신원 상실"
            # 부류라 가장 보수적으로 닫는다. 포즈 맵은 사람이 안 잡히므로
            # 정상 경로는 그대로 통과한다.
            _px_persons = {int(k) for k, v in ref_kinds.items()
                           if v == "person"}
            _gated = {k: v for k, v in _llm_kinds.items()
                      if not (v == "pose" and int(k) in _px_persons)}
            if _gated != _llm_kinds:
                _log("[Camera Director] LLM 포즈 라벨 거부 — 픽셀에서 사람이 "
                     "검출된 슬롯 "
                     + "/".join(str(k) for k in sorted(set(_llm_kinds)
                                                       - set(_gated)))
                     + "번은 신원 소스로 유지합니다")
                _llm_kinds = _gated
        if _llm_kinds:
            ref_kinds.update(_llm_kinds)
            # 병합된 지도에는 LLM 의 person 이 섞인다 — 픽셀 근거는 위에서 구한
            # 집합을 그대로 넘겨 9·10번 경계가 풀리지 않게 한다 (2026-10-23).
            set_reference_kinds(ref_kinds, persons=_pixel_persons)
            _log("[Camera Director] LLM 참조 역할 — "
                 + ", ".join(f"{k}번={v}" for k, v in sorted(_llm_kinds.items())))
            # LLM 분석까지 반영한 **최종** 종류로 외양 참조 기본값을 다시 계산한다
            # (2026-10-23, AC-24 — 사용자 지시 "분석은 LLM, 반영은 우리 규칙").
            # 왜(Why) 여기서 다시 계산하나: 위 869행은 LLM 호출 **전**이라 선언만
            # 안다. LLM 이 "9번은 소품" 이라고 분석했는데 외양 가드가 남으면 같은
            # 프롬프트가 "몸 외양" 과 "소품" 을 동시에 말한다 — 실측으로 찾은 구멍.
            _app_llm = appearance_ref_slots(analysis, image_labels, _llm_kinds)
            if _app_llm != appearance_slots:
                # 로그 문구는 기능 이름을 드러내지 않는다 (2026-10-23 사용자 지시).
                _log("[Camera Director] 역할 재지정 — LLM 역할 반영 ("
                     + "/".join(str(x) for x in sorted(appearance_slots - _app_llm))
                     + "번)")
                appearance_slots = _app_llm
                appearance_ref = bool(appearance_slots)

        # LLM 의 시트 판정 (2026-10-19) — 픽셀만으로는 같은 사람 반복과 다른
        # 캐릭터 나열을 가를 수 없다(실측 sim 0.415 대 0.216). LLM 은 faces·
        # hair·outfit 을 보므로 이 판정을 할 수 있다. 어휘는 single/multi 로
        # 닫혀 있고, 값이 없으면 "" (기존 topic 분기 그대로).
        _sheet_kind = _sheet_kind_from_llm(llm_obj)
        if _sheet_kind:
            _log("[Camera Director] LLM 시트 판정 — "
                 + ("패널마다 다른 인물" if _sheet_kind == "multi"
                    else "전부 같은 한 사람"))

        if tier == "auto":
            camera, locked, _ = resolve_rules_camera(topic, metrics, fixed_cam, locked)
            if preset_cam is None:
                hints_note = " + 이미지 힌트" if camera.get("_hints") else ""
                cam_source = ("직접 설정+규칙" if fixed_cam else "규칙") + hints_note
        else:  # llm
            llm_cam = self._llm_camera(llm_obj) if llm_obj else None
            if llm_cam is not None:
                camera = {**llm_cam, **(fixed_cam or {})}  # 고정값이 LLM보다 우선
                # LLM 이 실제로 고른 칸(값이 DEFAULTS 와 다른 칸)과 사용자 고정값을
                # locked 에 넣는다 — 아래 후처리(구도→조명·이미지 힌트)가 그 칸을
                # 덮지 않게 한다. 왜(Why) 필요한가 (2026-10-21): 예전엔 LLM 성공
                # 경로가 resolve_rules_camera 를 아예 안 불러 apply_framing_lighting
                # 과 apply_image_hints 가 죽었다. 그 결과 같은 입력에서 규칙 경로와
                # LLM 경로의 후처리가 갈렸다. 판단 주체는 달라도 **후처리 보정은
                # 공통**이어야 한다(사용자 지시). 단 LLM/사용자가 이미 정한 칸은
                # 건드리지 않는다 — locked 로 존중한다.
                for _k, _v in camera.items():
                    if _k.startswith("_"):
                        continue
                    if _k in (fixed_cam or {}):
                        locked.add(_k)
                    elif _v != DEFAULTS.get(_k):
                        locked.add(_k)
                camera, locked = apply_framing_lighting(camera, locked)
                if metrics:
                    camera = apply_image_hints(camera, locked, metrics)
                if preset_cam is None:
                    hints_note = " + 이미지 힌트" if camera.get("_hints") else ""
                    cam_source = ("LLM 판단" + ("(이미지 참조)" if image_count else "")
                                  + ("+직접 고정" if fixed_cam else "") + hints_note)
                elif llm_attempted:
                    cam_source = cam_source or "LLM 판단"
            else:
                camera, locked, _ = resolve_rules_camera(
                    topic, metrics, fixed_cam, locked)
                if preset_cam is None:
                    hints_note = " + 이미지 힌트" if camera.get("_hints") else ""
                    cam_source = (("직접 설정+규칙" if fixed_cam else "규칙")
                                  + ("(LLM 폴백)" if llm_attempted else "(LLM 생략)")
                                  + hints_note)
                elif llm_attempted:
                    cam_source += "(LLM 폴백)"

        explicit_shot = topic_shot_label(topic)
        if explicit_shot and "shot" not in locked:
            camera["shot"] = explicit_shot

        # 2.5) 무빙 게이팅 (2026-10-21 사용자 지시): 하류가 정지 이미지면
        # motion·motion2 는 영상 전용 지시라 왜곡을 유발한다 — 제거한다.
        # speed·amplitude 는 motion 수식어라 함께 기본값으로 되돌린다.
        # 하류가 영상이면 그대로 둔다. 판정은 hidden 입력 prompt 그래프의
        # 비디오 노드 표식으로 한다(detect_video_pipeline). 불명은 이미지로
        # 간주(안전 기본). 프론트에도 신호를 보내 UI 가 '영상 전용' 표시를
        # 하게 한다(백엔드/UI 어긋남 방지).
        is_video = detect_video_pipeline(prompt)
        try:
            notify_pipeline_type(unique_id, is_video)
        except Exception:
            pass
        if not is_video:
            _removed_motion = []
            for _mk in ("motion", "motion2"):
                if split_multi(camera.get(_mk)):
                    _removed_motion.append(_mk)
                    camera[_mk] = "없음 (none)"
            for _mk in ("speed", "amplitude"):
                camera[_mk] = DEFAULTS.get(_mk, camera.get(_mk))
            if _removed_motion:
                _log("[Camera Director] 정지 이미지 파이프라인 — 무빙 제거 "
                     "(" + ", ".join(_removed_motion) + "). 영상 워크플로에서만 활성")

        # 3) 장면: llm 성공 시 영문 확장, 그 외 주제 원문
        scene, scene_src = topic, "주제 원문"
        llm_extra = ""
        llm_anatomy = ""
        # LLM 이 참조 인물의 의상을 서술했으면(2026-10-25) 상태로 넘긴다.
        # 규칙(auto) tier 는 이 값을 빈 문자열로 두어 문구가 한 글자도 달라지지
        # 않는다. 읽는 곳은 run_prompt 의 최종 병합부 하나뿐이다.
        llm_outfit = ""
        if tier == "llm" and isinstance(llm_obj, dict):
            s = clean_scene_text(str(llm_obj.get("scene") or ""))
            if s:
                scene, scene_src = s, "LLM 확장"
# 왜(Why) 이걸 로그로 남기나 (2026-10-03 실측, WORK_STATUS 45절):
                # 카메라는 인코더에 넘긴 텍스트를 **어디에도 남기지 않았다.**
                # 카메라 dict 만 찍히므로 "드리프트가 났는데 프롬프트가 왜 바뀌는지"
                # 를 로그만으로 볼 수 없었다. 그 때문에 40~45절을 여러 차례 돌았다.
                # 같은 유형의 조용한 실패가 11-2(게이트가 조용히 없는 것처럼 보인다)다.
                # 드리프트가 났을 때 원인을 즉시 볼 수 있게 길이와 앞부분을 남긴다.
                # 길이를 함께 남기는 이유: 45절에서 프롬프트가 565자 -> 2783자로
                # 4.9배 늘어난 것이 핵심이었다. 앞부분만 보면 그 증가를 알 수 없다.
                #
                # 프라이버시 — 2026-10-03 **사용자 결정: 현재 방식 유지**(선택지 A).
                # anonymize 하지 않는다. 근거는 세 가지다.
                #   ① tier=llm 이면 참조 이미지를 이미 외부 LLM 에 보낸다.
                #      이 문장은 그 데이터에서 파생된 서술이므로 **새 유출이 아니다.**
                #   ② 로컬 LLM 이면 아무것도 밖에 안 나갔고, 로컬 파일에 쓰는 것은
                #      사용자가 소유하고 지울 수 있는 범위 안이다.
                #   ③ ComfyUI 가 prev 로그를 남기므로 세 파일로 한정된다.
                # 선례도 있다: llm_anatomy 가 이미 150자를 평문으로 로그한다(:4385).
                # B(길이만)는 진단 가치를 0으로 만든다 — 50-1 에서 판정을 바꾼 것은
                # LLM 이 고른 **단어**였다. C(마스킹)는 새 조용한 실패를 만든다.
                # **A 가 틀리는 조건 두 가지**(그때는 B 로 바꾼다):
                #   1  여러 사람이 쓰는 공유 컴피 서버 — 다른 사람이 로그를 읽는다
                #   2  comfyui.log 를 버그 리포트에 첨부해 외부로 보낸다
                _log(f"[Camera Director] LLM 장면 확장 사용 — {len(s)}자 "
                     f"(주제 원문 {len(topic or '')}자): {s[:200]}")
            llm_extra = str(llm_obj.get("negative") or "")
            # 왜(Why) anatomy 를 여기서 읽나 (2026-10-02): LLM 이 참조 이미지에서
            # 잘못된 사지 개수(발 3개, 손 6가락 등)를 보면 보고하게 했다.
            # 포즈 33점은 3번째 발을 못 보고, segmentation 은 SIGABRT 로 못 쓴다.
            # VLM 이 유일한 발/발가락 검출 수단이다. 있으면 ⚠ 로 알리고 negative 에
            # 합쳐 다음 생성이 피하게 한다. 없으면(키 생략) 조용히 넘어간다.
            llm_anatomy = str(llm_obj.get("anatomy") or "").strip()
            # 왜(Why) 200자로 자르고 영문·숫자·기본 구두점으로만 남기나:
            # LLM 출력이 통째로 negative(diffusion 프롬프트)에 들어간다.
            # 장황하거나 탈주한 응답이 프롬프트를 오염시킨다. 로그(위)와
            # 텔레메트리(아래)는 자르기 전 길이를 알 수 있게 별도 표기 없이 둔다.
            llm_anatomy = re.sub(r"[^A-Za-z0-9 ,.\-()]+", " ", llm_anatomy).strip()[:200]
            if llm_anatomy:
                _log(f"[Camera Director] ⚠ LLM이 참조 이미지에서 해부학 이상을 "
                     f"보고했습니다: {llm_anatomy[:150]}")
                # negative 에 합쳐 다음 생성이 피하게 한다. llm_extra 와 같은
                # 경로(L4421 build_negative)로 간다 — 둘 다 LLM 이 준 회피 지시라
                # 합치는 게 맞다. 로그는 위에서 따로 남겼으므로 추적 가능하다.
                llm_extra = (llm_extra.rstrip("., ") + ", " + llm_anatomy
                             if llm_extra.strip() else llm_anatomy)
            # LLM 이 읽은 참조 인물의 의상 (2026-10-25). 왜(Why) 읽나: 규칙(C)
            # 경로에는 옷을 읽는 눈이 없어 "옷을 바꾸지 말라" 만 내보낸다. LLM 이
            # 있으면 참조 1번의 옷을 **이름으로** 서술해 그 문구에 실어 보낸다.
            # 정제는 anatomy 와 같은 이유(LLM 출력이 프롬프트에 들어간다)로
            # 영문·숫자·기본 구두점만 남기고 200자로 자른다. 없으면 조용히 넘어간다.
            llm_outfit = str(llm_obj.get("outfit") or "").strip()
            llm_outfit = re.sub(r"[^A-Za-z0-9 ,.\-()']+", " ",
                                llm_outfit).strip()[:200]
            if llm_outfit:
                _log("[Camera Director] LLM 의상 서술: " + llm_outfit[:150])

        # 한국어→영어 번역 (규칙 tier 전용). LLM tier 는 위 블록이 이미 영문화.
        # assemble 출력(scene)만 번역하고, 판정/경고/프리플라이트는 원본(한글)
        # 텍스트로 둔다 (한글 마커 기반 가드 판정 보존).
        # 시놉시스(다문장)면 문장별 구조화로 응집된 영문 장면을 만든다 — 단문/
        # 번역 불가 시 기존 단일 번역으로 폴백(기존 동작 보존, 조립 로직 비변경).
        # LLM tier 는 이 분기를 타지 않아 깊은 서사 이해는 LLM 확장 결과가 된다.
        # 역할 선언 줄 분리 (2026-10-23, AC-10~AC-12): 사용자 표기
        # `1번: 한국 여성 / 2번: 의자 / 연출: <장면>` 에서 선언부는 슬롯 배정용이지
        # 그림 내용이 아니다. 그대로 번역·조립하면 번역기가 "1번:" 을 문장으로 읽는다.
        # **번역 입력과 조립 문장만** scene_out 을 쓴다.
        # 왜(Why) scene 을 자르지 않나: fix_background_clause·fix_fan_clause 가
        # 한글 원문(scene)에서 `배경: 2번` 선언을 읽어 절을 복원한다 — 자르면
        # R189 배경 복원이 깨진다(design 4절). LLM tier 는 scene 이 이미 영문
        # 장면이므로 손대지 않는다(AC-13, 동작 완전 동일).
        scene_out = scene if tier == "llm" else scene_text(topic)
        if scene_out != scene:
            _log("[Camera Director] 역할 선언 줄을 장면에서 분리했습니다 — "
                 f"장면 {len(scene_out)}자 / 원문 {len(scene)}자")
        _scene_assembled = scene_out
        if tier != "llm" and scene_out:
            if _looks_like_synopsis(scene_out):
                _syn = structure_ko_synopsis(scene_out)
                _syn_en = _syn.get("scene_en", "")
                if _syn_en and _syn_en != scene_out:
                    _scene_assembled = fix_footwear_clause(scene, _syn_en)
                    _h = _syn.get("hints", {}) or {}
                    _h_log = ", ".join(f"{k}" for k, v in _h.items()
                                       if v and k != "sentence_count")
                    _log(f"[Camera Director] 시놉시스 구조화 완료 "
                         f"({_h.get('sentence_count', 0)}문장 → 영문 장면)"
                         + (f" · 이해: {_h_log}" if _h_log else ""))
                else:
                    # 왜(Why) _has_cjk 가드인가 (2026-10-13 실측): translate_ko_to_en
                    # 은 비CJK 입력에 None 을 돌려준다(설계상 번역 불필요). 그 None 을
                    # 실패로 로그하면 영어 topic 매 실행이 "번역 실패" 오경고가 된다 —
                    # 실제 로그 5연속이 그 오경고였다 (엔진·모델·의존성 전부 정상).
                    if _has_cjk(scene_out):
                        _tr = translate_ko_to_en(scene_out)
                        if _tr:
                            _scene_assembled = _en_normalize(
                                fix_footwear_clause(
                                    scene, fix_pose_clause(scene, _tr)))
                            _log("[Camera Director] 주제를 영어로 번역했습니다 (tc-big)")
                        else:
                            _log("[Camera Director] ⚠ 주제 번역 실패 — 원문 사용")
                    # else: 영어 원문 그대로 (번역 불필요 — 실패 로그 없음)
            else:
                if _has_cjk(scene_out):
                    _tr = translate_ko_to_en(scene_out)
                    if _tr:
                        _scene_assembled = _en_normalize(
                            fix_footwear_clause(
                                scene, fix_pose_clause(scene, _tr)))
                        _log("[Camera Director] 주제를 영어로 번역했습니다 (tc-big)")
                    else:
                        _log("[Camera Director] ⚠ 주제 번역 실패 — 원문 사용")
        # 배경 지정 문장 보정 (2026-10-15): 번역기가 뭉갠 자기참조 배경
        # 문장은 지시력을 잃는다 — 한글 원문 근거로 정식 문장이 되돌린다.
        _scene_assembled = fix_background_clause(scene, _scene_assembled)
        # 부채 보유 문장 복구 (2026-10-15): 번역이 없앤 부채를 한글 원문
        # 근거로 되붙인다 (같은 이유 — 없어진 지시는 생성물에도 없다).
        _scene_assembled = fix_fan_clause(scene, _scene_assembled)
        # 손가락 분리 단서를 장면 문장 위치에도 둔다 (2026-10-22 R194 실측).
        # 왜(Why) 가드 위치만으로는 부족했나: 실기 A/B 에서 가드 위치 단독은
        # 시드별로 엇갈렸다(-0.14 / +0.08 / +0.36). 시드 8개 짝지음에서는 장면
        # 문장에도 둔 팔이 평균 +0.33 · 5승 2패 1무 · 해부 붕괴 0 이었다.
        # 문구·게이트는 cam_guards 의 scene_finger_cue 한 곳에 있다(R192 가드와
        # 같은 사람 판정 — 여기서 다시 판정하지 않는다).
        _scene_cue = scene_finger_cue((analysis or "") + " " + (scene or ""))
        if _scene_cue:
            _scene_assembled = (_scene_assembled.rstrip().rstrip(".")
                                + ". " + _scene_cue)
        # 로그는 여기서 남기지 않는다 (R196, 2026-10-22 실측). 이 조립문은
        # prompt_in 이 있으면 **버려진다** — run_prompt 가 앵커로 다시 세운다.
        # 그래서 여기서 "둠" 을 찍으면 실제 출력에 없는 삽입을 알리게 되고,
        # run_prompt 도 같은 줄을 찍어 한 생성에 같은 로그가 2번 났다.
        # 최종 텍스트를 아는 run_prompt 한 곳에서만 찍는다.
        # 포즈 분기 문장 (2026-10-13, PROVISIONAL): 포즈 동사가 있는 장면은
        # 묘사 쪽으로 당긴다. 참조와 같으면 무해(일치하므로)하고 다르면
        # 분기를 지시한다. 샘플러 추종은 사용자 A/B 로 확인한다.
        _scene_assembled = add_pose_divergence(
            _scene_assembled, image_count, scene)
        # 신발 형용사가 옷 명사에 붙은 입력 경고 (2026-10-22, **로그 전용**).
        # 왜(Why) 로그만인가: 원인은 카메라가 아니라 사용자가 쓴 문장이다
        # (오타 "단환" → 번역기가 "closed-toed shorts" 창작 — 실측). 문구를
        # 바꾸면 원문에 없는 것을 지어내는 추정 교정이 되고, 같은 문구를 쓰는
        # 멀쩡한 조건의 결과도 함께 흔들린다(2026-10-21 잘림 경고와 같은 판단).
        # 그래서 새 플래그·plan 키·negative 가 없다. 사용자가 고칠 문제이므로
        # 사실(문제 문구)과 처방(철자 확인)만 알린다.
        # 왜(Why) 사용자 입력만 보나: 카메라가 만든 가드 문구에는 "open-toe
        # shoes" 처럼 정상 조합만 있다 — 진단 대상은 사람이 쓴 문장이다.
        # 왜(Why) _scene_assembled 도 함께 보나: 한글 토픽은 이 시점에 이미
        # 영문이고, 번역기가 창작한 문장은 여기에만 나타난다.
        for _fn_bad in footwear_noun_mismatch(
                " ".join(x for x in (topic, scene, _scene_assembled,
                                     prompt_in) if x)):
            _log("[Camera Director] ⚠ 신발 형용사가 옷 명사에 붙어 있습니다: "
                 f"\"{_fn_bad}\" — 번역기가 신발 낱말을 다른 단어로 옮겼을 "
                 "수 있습니다. 주제의 신발 단어 철자를 확인하십시오 "
                 "(실측 예: \"단환\" → \"단화\")")
        # 정면 응시 보강 (2026-10-15 실측): "정면을 바라보며" 가 있어도
        # 생성 결과는 시선을 옆으로 돌렸다. 사람 주제 + 정면 markers 일 때만
        # positive 보강문과 negative 회피어를 짝으로 준다.
        _gaze_pos, _gaze_neg = gaze_forward_guard(
            (topic or "") + " " + (scene or ""), _scene_assembled)
        if _gaze_pos:
            _scene_assembled = (_scene_assembled.rstrip().rstrip(".")
                                + ". " + _gaze_pos)
            _log("[Camera Director] 정면 응시 가드 활성 (positive 보강 + "
                 "negative 회피어)")
        # 의류 색상 고정 (2026-10-15 실측): "흰색 단화" 지시에도 결과는
        # 크림/베이지색이 나왔다. 색상어가 의류 명사에 인접한 주제에서만
        # (positive 고정문, negative 오색) 짝을 준다.
        _item_pos, _item_neg = color_adherence_guard(
            (topic or "") + " " + (scene or ""), _scene_assembled)
        if _item_pos:
            _scene_assembled = (_scene_assembled.rstrip().rstrip(".")
                                + ". " + _item_pos)
            _log("[Camera Director] 의류 색상 고정 가드 활성 (positive 고정 + "
                 "negative 오색)")

        if not topic:
            _log("[Camera Director] ⚠ 주제가 비어 있습니다 — 카메라 조항만 출력됩니다.")

        hints = list(camera.pop("_hints", []))
        mismatch = scene_camera_mismatch(scene, camera)
        if mismatch:
            # 자동 교정 (2026-10-21 사용자 지시): 경고만 남기면 모순이 최종
            # 프롬프트에 그대로 실려 "명시한 것과 다른 결과"가 나온다. 최종
            # shot 라벨(카메라 블록)이 정본이므로 장면 글의 다른 샷 표현을
            # 걷어낸다. fix_footwear_clause 등과 같은 후처리 계열이다.
            _fixed_scene = fix_scene_shot_clause(_scene_assembled, camera)
            if _fixed_scene != _scene_assembled:
                _scene_assembled = _fixed_scene
                _log(f"[Camera Director] ⚠ {mismatch} — 장면의 샷 표현을 제거함")
            else:
                _log(f"[Camera Director] ⚠ {mismatch}")
        # 출발 점검: 깨질 조합이면 콘솔 경고 (pf_* 0은 검사 안 함).
        # 여기서 latent_mp 를 넘기지 않는 것은 **빠뜨린 것이 아니다** — base
        # 노드에는 LATENT 입력이 없고 run() 에도 latent 인자가 없어 알 수 있는
        # 값 자체가 없다(해상도 없는 경로에서 저해상 경고는 불가능하다).
        # 얼굴 클로즈업·저해상 경고는 latent 를 받는 Encode 경로가 낸다
        # (run_prompt 가 같은 점검에 latent_mp 를 넘긴다). 이 사실은 R179 가
        # 실측으로 고정한다 — 종전에 "run() 이 안 넘겨 두 경로 모두 침묵한다" 는
        # 보고가 있었으나 사실이 아니었다.
        for _warn in preflight_warnings(topic or scene, camera,
                                        steps=pf_steps, cfg=pf_cfg,
                                        denoise=pf_denoise):
            _log(f"[Camera Director] 출발 점검 ⚠ {_warn}")
        positive = assemble(_scene_assembled, camera, image_count=image_count, topic=topic,
                            image_labels=image_labels)
        # 가드 판정은 resolve_guard_plan 한 곳에서. run() 과 run_prompt() 가
        # 각자 반복하던 시대를 끝내고, 짝이 어긋날 수 없게 했다.
        # topic 칸 원문을 판정 소스에 합친다 (2026-10-25 F4). prompt_in 이
        # 연결돼 topic 칸이 출력에서 버려진 실행에서도, 그 칸에 적힌 슬롯·포즈
        # 지시는 가드 판정에 반영해야 한다 — 아래 declare 도 같은 취지다.
        _guard_src = (analysis or "") + " " + (scene or "")
        _declared_topic = topic or ""
        if external and _topic_field:
            _guard_src = _guard_src + " " + _topic_field
            _declared_topic = (_declared_topic + " " + _topic_field).strip()
        _plan = resolve_guard_plan(
            _guard_src, camera, image_count,
            image_labels, reference_items, primary_image, reference_images,
            tier=tier, llm_hint=llm_hint,
            weak_sheet_slots=weak_sheet, sheet_kind=_sheet_kind,
            declared_topic=_declared_topic)
        _gpos = _plan["positive"]
        _gflags = _plan["flags"]
        nudity_guard_text = nudity_anatomy_guard((topic or "") + " " + (scene or ""))
        mix_guard = _gflags["mix_guard"]
        body_balance = _gflags["body_balance"]
        detail_def = _gflags["detail_def"]
        anatomy_count = _gflags["anatomy_count"]
        footwear = _gflags["footwear"]
        footwear_bare = _gflags["footwear_bare"]
        body_object_boundary = _gflags["body_object_boundary"]
        garment_boundary = _gflags["garment_boundary"]
        hint_defense = _gflags["hint_defense"]
        char_sheet = _gpos["character_sheet"]
        _furn_text = _gpos["furniture"]
        _rm_text = _gflags["remove_item"]
        _pose_ref_text = _gpos["pose"]
        _phys_pos = _gpos["physics"]
        _phys_neg = _plan["physics_neg"]
        _px_sheet = _plan["pixel_sheet_slots"]
        # 참조 하단 잘림 경고 (2026-10-21). **로그 전용** — 프롬프트 문구는
        # 건드리지 않는다. 근거: 실측에서 자동 프리셋 조항을 하나씩 바꿔도
        # (샷만·렌즈만) 3다리가 남았으므로 문구로 잡히는 문제가 아니고,
        # 문구를 늘리면 같은 게이트를 쓰는 다른 조건의 결과가 함께 흔들린다.
        # 사용자에게 필요한 것은 사실과 처방이므로 그것을 여기서 알린다.
        if _gflags.get("ref_bottom_cropped"):
            _bm_ref = (_plan["spacing_measure"] or {}).get("bottom_margin") or 0.0
            _log("[Camera Director] ⚠ 참조 인물이 화면 하단에서 잘려 있습니다"
                 f"(측정 하단 여백 {int(round(_bm_ref * 100))}%) — 이 샷은 화면에 "
                 "없는 하반신(다리·발)을 모델이 새로 만들어야 하므로 다리·발 "
                 "개수가 늘어날 수 있습니다. 다리까지 보이는 참조를 함께 넣거나, "
                 "상반신 샷(근접 CU·극접 ECU)으로 자르거나, 시드를 바꾸십시오")
            # 손 배치 표지가 함께 있으면 손도 같은 위험에 놓인다 (2026-10-24, R220,
            # AC-4). 손은 무릎 높이(=화면 하단)에 오므로 하단이 잘린 참조에서는
            # 손의 픽셀 근거가 없어 모델이 손을 새로 그린다 — 그때 두 손이 겹치거나
            # 뭉친다. **로그 전용**이다: 문구를 늘리면 같은 게이트의 다른 조건
            # 결과가 함께 흔들린다(위 경고와 같은 판단).
            if _gpos["hand_placement"]:
                _log("[Camera Director] ⚠ 손 배치 장면입니다 — 참조에 그 손 위치가 "
                     "보이지 않으면(하단 잘림 또는 손이 옷·몸에 가림) 모델이 손을 "
                     "새로 그려야 하므로 두 손이 겹치거나 한 덩어리로 뭉칠 수 "
                     "있습니다. 원하는 손 위치가 보이는 참조를 넣거나, 시드를 "
                     "바꾸어 다시 생성하십시오")
        if mix_guard:
            positive = positive.rstrip(". ") + ". " + _gpos["mix_guard"] + "."
            _log("[Camera Director] 다중 참조 믹스 가드 활성 (연결 이미지 "
                 f"{image_count}장 — 융합/신원 혼합 방어)")
            # 참조 간 조명 충돌 점검 (설정 불필요 — 픽셀 근거 자동).
            _clash = _lighting_clash([_reference_lighting_flow(img)
                                      for img in reference_images])
            if _clash is not None and _clash > 1.0:
                _log(f"[Camera Director] ⚠ 참조 간 조명 흐름 충돌({_clash:.2f}) — "
                     f"합성 결과 조명이 어긋날 수 있음. 조명 방향이 같은 참조 권장")
        if appearance_ref:
            positive = positive.rstrip(". ") + ". " + APPEARANCE_REF_POSITIVE + "."
            _slots = "/".join(str(x) for x in sorted(appearance_slots))
            # 로그 문구는 기능 이름을 드러내지 않는다 (2026-10-23 사용자 지시).
            _log("[Camera Director] " + _slots
                 + "번 참조 가드 활성 (몸 비율 + 컷 삽입 방어)")
            positive = positive.rstrip(". ") + ". " \
                + APPEARANCE_HAIR_REALISM_POSITIVE + "."
        if body_balance:
            positive = positive.rstrip(". ") + ". " + _gpos["body_balance"] + "."
        if detail_def:
            positive = positive.rstrip(". ") + ". " + _gpos["detail_def"] + "."
            _log("[Camera Director] 부위별 디테일 경계 가드 활성 "
                 "(다리·팔·어깨·손가락 뭉개짐 방어)")
        if anatomy_count:
            positive = positive.rstrip(". ") + ". " + _gpos["anatomy_count"] + "."
        # 다리·발·종아리 무결성 (2026-10-21). cfg=1.0 이라 negative 가 무효라
        # positive 가 유일한 방어 — 발 추가·휜 종아리·손 뭉갬을 여기서 못박는다.
        if _gpos["limb_integrity"]:
            positive = positive.rstrip(". ") + ". " + _gpos["limb_integrity"] + "."
            _log("[Camera Director] 다리·발·종아리 무결성 가드 활성 "
                 "(추가 발·휜 종아리·손 뭉갬 방어)")
        if footwear or footwear_bare:
            positive = positive.rstrip(". ") + ". " + _gpos["footwear"] + "."
        if body_object_boundary:
            positive = positive.rstrip(". ") + ". " + _gpos["body_object_boundary"] + "."
        # 좌석 접촉점 (2026-10-24, R226) — 위 body-object 경계 **뒤에** 온다
        # (경계 → 접촉점 순서). 좌석 슬롯이 있을 때만 나간다.
        if _gpos.get("seat"):
            positive = positive.rstrip(". ") + ". " + _gpos["seat"] + "."
            _log("[Camera Director] 좌석 접촉점 가드 활성 ("
                 + "/".join(str(x) for x in sorted(_plan["seat_slots"]))
                 + "번 — 체중이 좌석 쿠션에, 팔걸이 걸터앉음 방어)")
        # 의복 경계 (2026-10-16) — 손이 치마에 삼켜진 실측. 위 가구 경계와 짝.
        if garment_boundary:
            positive = positive.rstrip(". ") + ". " + _gpos["garment_boundary"] + "."
            _log("[Camera Director] 의복 경계 가드 활성 "
                 "(손·사지가 옷에 잠기지 않음)")
        # 손 배치 (2026-10-24, R220) — 두 손이 겹치거나 한 덩어리로 합쳐지고
        # 손가락이 서로 넘어가는 실패 방어. cfg=1.0 이라 negative 가 무효여서
        # positive 가 유일한 방어다(위 다리·발 무결성과 같은 이유).
        if _gpos["hand_placement"]:
            positive = positive.rstrip(". ") + ". " + _gpos["hand_placement"] + "."
            _log("[Camera Director] 손 배치 가드 활성 "
                 "(두 손 겹침·한 덩어리 합침·손가락 넘어감 방어)")
        if _furn_text:
            positive = positive.rstrip(". ") + ". " + _furn_text + "."
            _log("[Camera Director] 가구·사물 DNA 가드 활성 ("
                 + "/".join(str(x) for x in sorted(_plan["furniture_slots"]))
                 + "번 — 형태·재질·색·비율 원본 유지)")
        # 배경 참조의 사물 충실 (2026-10-22 실측) — 위 사물 DNA 와 달리 **존재를
        # 요구하지 않는** 조건문이다. 있으면 참조 그대로, 없으면 만들지 말 것.
        # 왜 배경에만 붙는지는 cam_guards 의 FURNITURE_BACKGROUND_POSITIVE 참조.
        _fbg_text = _gpos.get("furniture_bg", "")
        if _fbg_text:
            positive = positive.rstrip(". ") + ". " + _fbg_text + "."
            _log("[Camera Director] 배경 참조 사물 충실 가드 활성 ("
                 + "/".join(str(x) for x in
                            sorted(_plan["furniture_bg_slots"]))
                 + "번 — 화면에 보이면 참조 그대로: 다리·접지·재질·색)")
        # 참조 사물 외형 고정 (2026-10-16 실측) — 가구 DNA 문구와 **짝**이다.
        # 한쪽만 붙으면 방어가 조용히 사라진다 (같은 이음새 결함 실측 다수).
        _fsurf_pos = _plan.get("furniture_surface_pos", "")
        if _fsurf_pos:
            positive = positive.rstrip(". ") + ". " + _fsurf_pos + "."
            _log("[Camera Director] 사물 외형 고정 가드 활성 (표면 구조 보존"
                 + (", 참조 대표색 고정" if "surface colour lock" in _fsurf_pos
                    else ", 색 판독 실패 — 구조만")
                 + ")")
        if _rm_text:
            _log("[Camera Director] 반쪽 물체·찌꺼기 방어 활성 "
                 "(제거된 사물은 완전 제거 또는 그대로)")
        if _px_sheet:
            _log(f"[Camera Director] 참조 이미지 {'/'.join(_px_sheet)}번에서 "
                 f"캐릭터 시트 패턴 감지 (여러 뷰가 반복 배치) — topic 문구와 "
                 f"무관하게 시트 지시를 적용합니다")
        # topic 이 비었는데 참조가 붙어 있으면 역할이 지정되지 않은 것이다.
        # 조용히 아무 지시도 안 나가는 것을 막기 위해 무엇을 쓸 수 있는지
        # 알려준다(2026-09-28 실측: 포즈 이미지에서 옷까지 복제됨).
        if image_count >= 2 and not (topic or "").strip() and not _px_sheet:
            _auto_p = person_slots(ref_kinds)
            if _auto_p:
                _log("[Camera Director] topic 이 비어 있어 픽셀 분석으로 역할을 "
                     "정했습니다 — 인물 슬롯 "
                     + "/".join(str(x) for x in _auto_p)
                     + f", 그중 {_auto_p[0]}번을 주 피사체로 사용합니다. 다른 칸은 "
                     "보조 참조(배경·사물·스타일)입니다. 역할을 직접 정하려면 "
                     "topic 에 '2번은 포즈만' 처럼 적어주세요")
            else:
                _log('[Camera Director] ⚠ topic 이 비어 있고 참조에서 사람도 '
                     '찾지 못했습니다. 기본값으로 1번=주 피사체, 나머지=배경/구도/'
                     '조명 전용(옷·얼굴은 복사 안 함)이 적용됩니다. 포즈·시트·인물 '
                     '구분을 원하면 topic 에 \'2번은 포즈만, 3번은 1인 캐릭터 시트\' '
                     '처럼 역할을 적어주세요')
        if char_sheet:
            positive = positive.rstrip(". ") + ". " + char_sheet + "."
            _log("[Camera Director] 캐릭터 시트 참조 가드 활성 "
                 "(신원 일관성 + 시트 레이아웃 복제 방어)")
        if _pose_ref_text:
            positive = positive.rstrip(". ") + ". " + _pose_ref_text + "."
            _log("[Camera Director] 포즈 참조 가드 활성 ("
                 + "/".join(str(x) for x in _plan["pose_slots"])
                 + "번 — 자세만 따르고 얼굴·의상·배경은 비전에서 제외)")
        if _plan["positive"]["spacing"]:
            positive = positive.rstrip(". ") + ". " \
                + _plan["positive"]["spacing"] + "."
            _log("[Camera Director] 픽셀 공간 측정 ("
                 + (spacing_log_text(_plan["spacing_measure"]) or "판정 불가")
                 + ") — topic에 동작 표현 없어도 거리 유지 지시 적용")
        if _phys_pos:
            positive = positive.rstrip(". ") + ". " + _phys_pos + "."
            _log("[Camera Director] 물리·공간 가드 활성 (접촉/동작 상태를 "
                 "이미지 조건으로 번역)")
        if _gpos["ground"]:
            positive = positive.rstrip(". ") + ". " + _gpos["ground"] + "."
            _log("[Camera Director] 배경 지면 고정 가드 활성 (참조 지면으로 "
                 "통일 + 콘크리트/실내 매끈 바닥 방어)")
        # hint_defense/mix_guard/body_balance 는 _last_guard_plan 안에 있다.
        # 개별로 저장하면 plan 과 값이 어긋날 수 있고(그러면 짝인 negative 가
        # 사라진다), 읽는 곳도 plan 이므로 중복이다.
        self._last_guard_plan = _plan
        self._last_appearance_ref = appearance_ref
        self._last_subject_text = ((topic or "") + " " + (scene or ""))
        # topic 칸 원문도 판정 소스에 합친다 (2026-10-25 F4). prompt_in 연결로
        # 출력에서 버려진 그 칸의 슬롯·포즈 지시가 negative 쪽 판정에도
        # 반영되게 한다 — plan(positive)과 같은 텍스트를 보게 맞춘다.
        if external and _topic_field:
            self._last_subject_text = (self._last_subject_text + " "
                                       + _topic_field).strip()
        negative = build_negative(camera, extra=extra_negative or "",
                                  llm_extra=llm_extra,
                                  topic=_guard_src,
                                  hint_defense=hint_defense, mix_guard=mix_guard,
                                  appearance_ref=appearance_ref,
                                  sheet_kind=_sheet_kind,
                                  body_balance=body_balance,
                                  character_sheet=bool(char_sheet),
                                  image_count=image_count,
                                  image_labels=list(image_labels),
                                  pose_ref=bool(_pose_ref_text),
                                  physics_neg=_phys_neg,
                                  detail_def=detail_def,
                                  furniture=bool(_furn_text),
                                  furniture_bg=bool(_fbg_text),
                                  remove_item=bool(_rm_text),
                                   anatomy_count=anatomy_count,
                                   anatomy_count_upper=bool(
                                       _plan["flags"].get(
                                           "anatomy_count_upper")),
                                   detail_def_upper=bool(
                                       _plan["flags"].get(
                                           "detail_def_upper")),
                                   footwear=footwear,
                                   footwear_upper=bool(
                                       _plan["flags"].get(
                                           "footwear_upper")),
                                   footwear_bare=bool(
                                       _plan["flags"].get(
                                           "footwear_bare")),
                                   body_object_boundary=body_object_boundary,
                                    body_object_boundary_upper=bool(
                                        _plan["flags"].get(
                                            "body_object_boundary_upper")),
                                   garment_boundary=garment_boundary,
                                    garment_boundary_upper=bool(
                                        _plan["flags"].get(
                                            "garment_boundary_upper")),
                                   hand_placement=bool(
                                       _plan["flags"].get("hand_placement")),
                                   seat=bool(_plan["flags"].get("seat")))
        # 정면 응시 회피어 (2026-10-15) — positive 보강문과 짝이다.
        # 한쪽만 붙으면 방어가 조용히 사라진다 (같은 이음새 결함 실측 다수).
        if _gaze_neg:
            negative = negative.rstrip("., ") + ", " + _gaze_neg
        # 의류 오색 (2026-10-15) — 고정 positive 와 짝이다.
        if _item_neg:
            negative = negative.rstrip("., ") + ", " + _item_neg
        # 사물 표면 소실·표백 회피어 (2026-10-16) — 위 표면 구조 고정과 짝이다.
        _fsurf_neg = _plan.get("furniture_surface_neg", "")
        if _fsurf_neg:
            negative = negative.rstrip("., ") + ", " + _fsurf_neg
        # 자동 분류 역할 문장 (2026-10-19) — 토픽이 슬롯을 지목하지 않았을 때만.
        # 왜(Why) 여기서 붙이나: 기존 가드 파이프라인은 텍스트 기반이라 분류
        # 결과를 억지로 끼워 넣으면 판정과 충돌한다. 문장 하나를 더하는 방식이
        # 가장 좁고 되돌리기 쉽다. 토픽이 "2번 의상" 이라고 했으면 쓰지 않는다.
        _auto_roles = ""
        if ref_kinds and not _text_names_slots(analysis):
            _auto_roles = auto_reference_roles_positive(ref_kinds, image_labels)
            if _auto_roles:
                positive = positive.rstrip(". ") + ". " + _auto_roles + "."
                _log("[Camera Director] 자동 역할 문장 적용 ("
                     + ", ".join(f"{k}번={v}"
                                 for k, v in sorted(ref_kinds.items())) + ")")
        # prompt_in 경로도 같은 자동 역할 문장을 병합할 수 있게 상태로 넘긴다
        # (2026-10-25 감사). 왜(Why): 이 문장은 여기(base)에서만 붙어 prompt_out
        # 에 들어갔다. prompt_in 경로는 positive_text 를 앵커로 **다시** 세우므로
        # 이 문장이 사라져, 사물 참조에 "keep its exact shape, material and
        # colour" 지시가 빠졌다(실측: 나무 의자 제품 샷 + 참조 1장에서 base/standalone
        # 에는 있고 prompt_in 에는 없음). _last_image_labels 와 같은 상태 전달 패턴.
        self._last_auto_roles = _auto_roles
        self._last_camera = dict(camera)
        self._last_llm_extra = llm_extra
        # LLM 이 서술한 참조 인물 의상 (2026-10-25). run_prompt 의 최종 병합부가
        # prompt_in 유무와 무관하게 같은 값을 읽는다. 규칙 tier 는 "".
        self._last_llm_outfit = llm_outfit
        self._last_image_count = image_count
        self._last_image_labels = list(image_labels)
        # Skills(run_prompt) 경로는 run() 을 거치지 않으므로 LLM 시트 판정을
        # 상태로 넘긴다 (_last_image_labels 와 같은 폴백 패턴, 2026-09-29 결함
        # 교훈). 없으면 "" — 기존 topic 분기 그대로.
        self._last_sheet_kind = _sheet_kind

        hint_text = (" | hints: " + "; ".join(hints)) if hints else ""
        # 프리셋 위에 얹은 가감을 남긴다. 이 로그가 없으면 "프리셋을 골랐는데
        # 왜 이 값이 나왔는지"를 사용자가 확인할 방법이 없다.
        if preset_added or preset_removed:
            _add = ", ".join(f"{_k}={_v}" for _k, _v in preset_added) or "없음"
            _rem = ", ".join(f"{_k}={_v}" for _k, _v in preset_removed) or "없음"
            _log(f"[Camera Director] 프리셋 '{preset}' 가감 — 추가: {_add} / 제외: {_rem}")
        # 값이 여러 개(콤마 구분)일 수 있다 — 그대로 찍으면 무엇이 골라졌는지 보인다.
        _log(f"📷 Camera Director | tier={tier} preset={preset} source={cam_source} "
             f"| in={topic_src} shot={camera.get('shot', '')} "
             f"lens={camera.get('lens', '')} "
             f"angle={camera.get('angle', '')} motion={camera.get('motion', '')} "
             f"| scene={scene_src} "
             f"| image={image_count if image_count else 'none'}{hint_text}")
        _post_telemetry(
            tier=tier, preset=preset, automation=automation,
            cam_source=cam_source, topic_chars=len(topic or ""),
            camera=dict(camera), guards={
                "mix_guard": mix_guard,
                "appearance_ref": appearance_ref,
                "hint_defense": hint_defense,
                "nudity_guard": bool(nudity_guard_text),
            },
            image_count=image_count, image_labels=list(image_labels),
            llm={
                "attempted": llm_attempted,
                "used": bool(llm_obj),
                "provider": provider, "model": resolved_model,
                # 왜(Why) 캐시 지표를 넣나 (2026-10-02 실측): 캐시 히트는
                # 네트워크 호출 0회라 `used=True` 인데 시간이 안 걸린다. 지표가
                # 없으면 "작동을 안 하는데?" 를 구분할 방법이 없다 — 로그로도.
                "cache": llm_client.cache_stats()[1],
                # 왜(Why) anatomy 를 넣나 (2026-10-02): LLM 이 본 사지 이상이
                # 있으면 기록해야 다음에 "언제 처음 봤나" 를 추적할 수 있다.
                "anatomy": llm_anatomy[:200] if llm_anatomy else "",
            },
            elapsed_ms=int((time.perf_counter() - _t0) * 1000))
        _release_vram()
        # 분류 힌트는 이번 실행 한정이다 — 다음 실행(다른 이미지)에 새지 않게 지운다.
        clear_reference_kinds()
        return (positive, negative, primary_image)


# ---------------------------------------------------------------------------
# (GoRi) Camera Director Skills
#
# positive_out/negative_out은 CONDITIONING이며 KSampler에 직접 연결한다.
# prompt_out은 STRING이며 humans/debug/Qwen 재확인용이다.
# image 입력은 프롬프트 힌트/비전 LLM 판단에 사용되며, 첫 번째(주 reference)
# 이미지는 image_out으로 그대로 통과해 후속 노드(I2V·업스케일)에 쓸 수 있다.
# ---------------------------------------------------------------------------

class CameraDirectorEncode(CameraDirector):
    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "STRING", "IMAGE", "LATENT")
    RETURN_NAMES = ("positive_out", "negative_out", "prompt_out", "image_out",
                    "reference_latent_out")
    FUNCTION = "run_prompt"
    CATEGORY = "HF Skills/Camera"
    DESCRIPTION = ("주제와 1~10장의 레퍼런스 이미지로 카메라 연출을 구성한 영문 프롬프트를 "
                   "positive/negative conditioning과 prompt_out으로 출력합니다. "
                   "positive_out/negative_out은 KSampler에, prompt_out은 확인용으로 사용하세요.")

    # 노출 노드 입력 정의 — 베이스에 clip(필수)/vae(선택)를 더하고 image 류를 뺀다
    @classmethod
    def INPUT_TYPES(cls):
        base = CameraDirector.INPUT_TYPES()
        required = dict(base["required"])
        required["clip"] = ("CLIP",)
        optional = dict(base.get("optional", {}))
        optional.pop("image", None)
        optional.pop("extra_negative", None)
        # 왜(Why) vae 가 required 가 아니나: reference conditioning 캐시용이라
        # 선택이다 — run_prompt 도 vae=None 을 기본값으로 받고, _prepare_qwen_
        # image_data 도 vae=None 이면 latent 변환을 건너뛴다. required 로 두면
        # VAE 없이 쓰는 프롬프트 전용 경로(README 가 권장하는 KREA 2 ·
        # MiniMax H3 용도)가 UI 에서 아예 막힌다.
        optional["vae"] = ("VAE",)
        optional["latent_image"] = ("LATENT", {"optional": True})
        optional["positive"] = ("CONDITIONING",)
        optional["negative"] = ("CONDITIONING",)
        for i in range(1, MAX_REFERENCE_IMAGES + 1):
            optional[f"image_{i}"] = ("IMAGE", {
                "optional": True,
                "tooltip": f"Reference image #{i}",
            })
        # 포즈 맵 입력 (2026-10-14): 맨 뒤 — 기존 소켓 순서·위젯 매핑 보호.
        # DWPreprocessor 결과(검은 배경 + 색 뼈대)를 받는다. 참조 사진이
        # 아니라 image_items(개수·vision·latent)에 넣지 않는다.
        optional["pose_image"] = ("IMAGE",)
        # 호환용 자리 위젯 reference_max_mp (2026-10-23 되살림). 왜(Why) 지웠다가
        # 되살렸나: 참조 해상도의 출처는 입력(latent_image)의 MP 로 옮겼으므로
        # (아래 _prepare_qwen_image_data docstring) 사용자가 정할 값이 아니다.
        # 그래서 지웠는데, **지우면 저장된 위젯 값이 한 칸씩 밀렸다.**
        # 실측 (2026-10-23, 브라우저에서 확인): ComfyUI 프런트엔드는 저장된
        # widgets_values 를 자리 순서로 위젯에 넣는다. 옛 워크플로(이 위젯이
        # 있던 시절 저장)는 값이 23개다. 위젯이 22개가 되면 값 22개는 정상
        # 정렬되지만 23개는 **provider(첫 optional 위젯)부터 한 칸 밀린다** —
        # 제공자·모델명·주소가 엉뚱한 칸으로 가고 pf_steps 가 1 이 되어
        # "steps 범위 이탈(8~150)" 경고가 뜬다. 즉 "맨 뒤 위젯이라 안 밀린다"
        # 는 판단은 틀렸다.
        # 그래서 **값은 쓰지 않고 자리만 지키는** 위젯으로 남긴다. 화면에는
        # hidden 으로 감추므로(llm_hint 와 같은 방식) 사용자가 다룰 숫자는
        # 여전히 없다. 이 자리를 다시 지우려면 위 밀림 실측을 먼저 보라.
        optional["reference_max_mp"] = ("FLOAT", {
            "default": 1.0, "min": 0.0, "max": 64.0, "step": 0.5,
            "hidden": True,
            "tooltip": ("호환용 자리 — 값은 쓰이지 않는다. 참조 해상도는 "
                        "latent_image 입력의 픽셀 수를 따른다."),
        })
        # 참조 충실(가드 압축)은 2026-10-26 부터 **내부 동작**이다 — 위젯이 없다.
        # 왜(Why) 위젯을 되살리면 안 되나: 기본값이 꺼짐인 스위치가 있으면 기본
        # 동작이 두 계약으로 갈리고, 그 위젯을 모르는 사용자는 계속 참조를 잃는다
        # (실측 2026-10-26: 규칙 경로 3.26% 대 17.51%). 설계와 근거는
        # docs/dev-loop/2026-10-26-ref-fidelity-internal/ 참조. 옛 워크플로가
        # 이 위젯 값을 들고 있어도 안전하다 — 위젯은 optional 맨 뒤였고, 서버는
        # 모르는 입력 키를 kwargs 에 넣지 않는다(execution.py:173-195).
        return {"required": required, "optional": optional,
                "hidden": dict(base.get("hidden", {}))}

    @staticmethod
    def _reference_target_size(latent_image, vae=None):
        """reference 목표 크기 (w, h). latent 미연결·파손이면 (None, None).

        왜(Why): _prepare와 run_prompt(기준 latent 조회)가 같은 캐시 키를
        써야 적중한다. 계산을 한 곳에 둔다.

        왜(Why) 배수를 어디서 읽나 (2026-10-23): `_latent_mp` 와 같은 규칙이다
        — **latent 가 선언한 배수가 먼저**(`_latent_declared_ratio`)이고,
        선언이 없으면 vae.downscale_ratio, 그것도 없으면 16 이다. 선언을 모델
        비율로 덮어쓰면 빈 latent 노드가 보낸 8 배 격자를 16 배로 읽어 참조가
        4배가 된다 (실측은 `_latent_declared_ratio` 주석에).
        """
        try:
            samples = latent_image.get("samples") if isinstance(latent_image, dict) else None
            if samples is not None and samples.ndim == 4:
                _ratio = _latent_declared_ratio(latent_image)
                if _ratio is None:
                    _ratio = _vae_ratio(vae)
                return (int(samples.shape[-1]) * _ratio, int(samples.shape[-2]) * _ratio)
        except Exception:
            pass
        return (None, None)

    @staticmethod
    def _canvas_fit_latent(ref_latent, latent_image, vae=None):
        """기준 latent 출력을 사용자 캔버스(latent_image)의 H,W 에 맞춘다.

        왜(Why) 필요한가 (2026-10-23 실측 / 2026-10-24 재적용): 이 노드의 5번 출력은
        샘플러의 시작 latent 로 연결된다. 샘플러가 만드는 이미지 크기는 시작 latent
        의 H,W 가 정하므로, 이 값이 사용자가 고른 빈 latent 와 같아야 "내가 고른
        비율로 나온다" 가 성립한다. 이 함수가 없으면 13가지 비율을 모두 넣어도 출력이
        참조 사진 비율로 고정된다 — 2026-10-24 실측: 79번을 16:9 로 두든 9:16 으로
        두든 저장된 출력이 똑같이 736x1328 이었다(참조 사진 비율).

        2026-10-24 왕복 기록: 이 함수는 522a302 에서 "비율을 바꾸니 같은 시드의 결과가
        달라졌다" 는 이유로 한 번 빠졌다. 다시 넣는 이유는 그 변화가 denoise=1.0 에서
        **필연**이기 때문이다 — 시작 latent 의 모양이 곧 시드이므로 비율을 바꾸면
        그림이 달라지는 것이 정상이고, 달라지지 않는 쪽이 고장이다. 대가(합의):
        비율을 바꾸면 같은 시드라도 그림이 바뀐다.

        왜(Why) vae 를 받나 (2026-10-23 실측 회귀): 캔버스 격자를 **샘플러가 보는
        크기로 환산**해야 한다. 빈 latent 노드는 `height//8` 격자에 선언 8 을 붙여
        보내지만 Qwen 2.1 VAE 는 16 배다. 환산 없이 격자를 그대로 내보내면
        `fix_empty_latent_channels` 가 **비어 있지 않은** 참조 latent 을 보정하지
        않아(comfy/sample.py:49~56 — is_empty 일 때만 선언을 쓴다) 샘플러가 raw 격자로
        돌고 디코드 x16 에서 출력이 4배가 된다(768x1344 를 고르면 2688x1536 이 나간다).
        그래서 comfy/sample.py:53~56 과 같은 식으로 선언/모델 비율만큼 줄인다. 선언이
        없거나 vae 가 없으면 환산하지 않는다 — 기존 계약(격자 그대로)이 그대로 유지된다.

        조건화(positive 안의 reference_latents)는 이 함수를 지나지 않는다 — Qwen 이
        참조 레이아웃을 따라가는 동작과 캐시 키는 그대로다(R216·R217 계약).

        반환: 캔버스 크기로 맞춘 latent dict. 캔버스가 없거나 파손이면 원본을
        **같은 객체로** 돌려준다(하위호환 — latent_image 를 연결하지 않은 기존
        그래프의 결과가 한 픽셀도 안 바뀐다).
        """
        if ref_latent is None:
            return None
        try:
            samples = (ref_latent.get("samples")
                       if isinstance(ref_latent, dict) else ref_latent)
            canvas = (latent_image.get("samples")
                      if isinstance(latent_image, dict) else latent_image)
            if (samples is None or canvas is None
                    or getattr(samples, "ndim", 0) != 4
                    or getattr(canvas, "ndim", 0) != 4):
                return ref_latent
            target_h, target_w = int(canvas.shape[-2]), int(canvas.shape[-1])
            # 캔버스 격자 → 모델 격자 환산 (선언이 모델 비율과 다를 때만).
            _decl = _latent_declared_ratio(latent_image)
            _model = getattr(vae, "downscale_ratio", None)
            if (_decl is not None and not isinstance(_model, bool)
                    and isinstance(_model, int) and _model > 0
                    and _decl != _model):
                target_h = max(1, int(round(target_h * _decl / float(_model))))
                target_w = max(1, int(round(target_w * _decl / float(_model))))
            if (int(samples.shape[-2]), int(samples.shape[-1])) == (target_h, target_w):
                return ref_latent      # 이미 같은 크기 — 텐서를 새로 만들지 않는다
            import torch.nn.functional as _F
            fitted = _F.interpolate(samples.float(), size=(target_h, target_w),
                                    mode="bicubic", align_corners=False)
            fitted = fitted.to(dtype=samples.dtype, device=samples.device)
            _note_once(
                "camera.ref_canvas_fit",
                "[Camera Director] 기준 latent 를 캔버스 크기로 맞춥니다 "
                "(참조 사진 비율 대신 사용자가 고른 크기).")
            return {"samples": fitted}
        except Exception as exc:  # noqa: BLE001
            # 왜(Why) 말하나: 조정이 조용히 실패하면 5번 출력이 다시 참조 사진
            # 비율로 나가는데 화면에는 아무 단서가 없다.
            _note_once("camera.ref_canvas_fit_fail",
                       "[Camera Director] 기준 latent 크기 조정 실패 — 참조 사진 "
                       f"비율로 진행: {type(exc).__name__}: {str(exc)[:80]}")
            return ref_latent

    @staticmethod
    def _prepare_qwen_image_data(image_items, vae=None, latent_image=None,
                                 latent_skip_labels=None):
        """Prepare Qwen vision images and VAE reference latents once.

        latent_skip_labels 에 해당하는 슬롯은 **언어 모델용 vision image 로만**
        넣고 VAE reference latent 에서는 제외한다.

        왜(Why) 필요한가 — 2026-09-29 실측: Qwen-Image-2.1 은 reference latent
        의 **레이아웃까지** 따라 그린다. 1인 6뷰 캐릭터 시트를 reference 로
        넣으면 결과도 **6뷰 시트 그대로** 렌더링됐다. 분리 실험으로 확정:
        시트 없으면 항상 1인 정상 / 시트 있으면 topic 에 "a single continuous
        photograph of one young woman" 라고 명시해도 4뷰가 나온다.
        프롬프트로는 이길 수 없다 — pixel-level 레이아웃 힌트라서.
        그래서 시트는 LLM(신원 파악)에만 보여주고 diffusion 에서는 뺀다.

        크기 규칙 (2026-10-23 사용자 판정): **참조 픽셀 수 = 입력(latent_image)
        픽셀 수.** 참조 사진의 종횡비는 그대로 두므로 격자 셀 수가 입력과
        같아지고 모양만 사진대로 남는다. 입력이 연결되지 않았으면 따를 값이
        없으므로 1MP(QWEN_REF_MAX_PIXELS)로 폴백한다.

        모양 규칙 (2026-10-23 판정): **참조 종횡비를 캔버스로 강제하지 않는다.**
        캔버스가 16:9 인데 사진이 세로면 참조도 세로다. 여백·크롭·늘리기로
        모양을 맞추는 세 방식은 A/B 6판 실측에서 모두 현행보다 나쁘거나
        이득이 없었다(아래 크기 계산부 주석에 수치). 모양을 맞추려면
        **사용자가 사진을 그 모양으로 준비**한다 — 그러면 아래 계산이 그
        모양을 그대로 낸다. R216 이 이 판정을 잠근다.
        """
        latent_skip_labels = {str(x) for x in (latent_skip_labels or set())}
        if not image_items:
            return [], None
        if not all(hasattr(image, "movedim") for _label, image in image_items):
            # 왜(Why) 말하나 (2026-10-07 라운드 2): tensor 속성이 없는 입력을
            # 조용히 빼면 "연결은 됐는데 왜 반영이 안 되나" 를 원인 없이
            # 읽는다. 한 번만 말하고 텍스트 경로로 계속 진행한다.
            _note_once("camera.qwen_not_tensor",
                       "[Camera Director] 참조 이미지에 tensor 속성(movedim)이 "
                       "없어 이미지·latent 준비를 건너뜁니다 "
                       "(텍스트 지시만 반영됩니다).")
            return [], None
        try:
            import comfy.utils
            import node_helpers
        except Exception as exc:  # noqa: BLE001
            _log("[GoRi Camera Director Skills] ComfyUI image utilities "
                 f"unavailable (comfy.utils/node_helpers), text fallback: {exc}")
            return [], None
        ref_latents = []
        images_vl = []
        target_w, target_h = CameraDirectorEncode._reference_target_size(
            latent_image, vae=vae)
        # 참조 크기의 출처는 입력이다 (2026-10-23 사용자 판정). 왜(Why):
        # 2026-10-22 의 위젯 reference_max_mp 는 1MP 하드 상한을 열었지만 입력에
        # 묶지 않아서, 입력 1MP 에 위젯 2.0 을 넣으면 참조가 2MP 로 인코딩됐다 —
        # 생성에 쓰이지 않는 해상도라 정보가 늘지 않고 격자만 어긋난다. 사용자
        # 관찰: 그 어긋남이 피부 변화로 눈에 보인다. 그래서 상한을 없애고
        # **참조 픽셀 수 = 입력 픽셀 수** 로 맞춘다. 따를 입력이 없을 때만
        # (latent 미연결) 종전 하드값 1MP 로 폴백한다.
        for _label, image in image_items:
            try:
                # **(H,W,C) 3차원 입력을 (1,H,W,C) 로 정규화한다** (2026-10-19).
                # 왜(Why): ComfyUI IMAGE 는 4차원이 정상이지만, 3차원이 들어오면
                # image[:1] 이 (W,C) 가 돼 movedim 조회가 죽는다. per-image
                # except 가 그것을 **조용히 제외**해서 — "연결은 됐는데 참조가
                # 왜 안 먹지" 의 원인이 로그 한 줄로만 남았다(테스트 중 실측:
                # "tuple index out of range"). 배치 축을 채우면 같은 이미지가
                # 정상 경로로 들어간다.
                if getattr(image, "ndim", 0) == 3:
                    image = image.unsqueeze(0)
                cache_key = _qwen_ref_cache_key(image, target_w, target_h, vae)
                cached = _qwen_ref_cache_get(cache_key, vae)
                if cached is not None:
                    cached_rgb, cached_latent = cached
                    images_vl.append(cached_rgb)
                    if (cached_latent is not None and
                            str(_label) not in latent_skip_labels):
                        ref_latents.append(cached_latent)
                    continue
                samples = image[:1].movedim(-1, 1)
                if target_w and target_h:
                    # 참조 픽셀 수 = 입력 픽셀 수 (1:1). 사진의 종횡비는 유지하므로
                    # 격자 셀 수가 입력과 같아지고 모양만 사진대로 남는다.
                    # 16 배수 정렬: VAE 가 H//16 으로 격자를 만든다 — 정렬하지
                    # 않으면 의도한 픽셀 수와 실제 격자가 몇 칸 어긋난다.
                    ratio = samples.shape[3] / samples.shape[2]
                    _px_in = float(target_w) * float(target_h)
                    width = int(round((_px_in * ratio) ** 0.5))
                    height = int(round((_px_in / ratio) ** 0.5))
                    width = max(32, int(round(width / 16.0)) * 16)
                    height = max(32, int(round(height / 16.0)) * 16)
                    # 왜(Why) 모양까지 캔버스에 맞추지 않나 (2026-10-23 A/B 6판):
                    # 캔버스 1344x736(16:9) · 세로 사진(비율 0.558) 기준 실측.
                    #  여백   볼 색 +1.2/+4.6/+5.2% · 배치 추론 -155자 소실
                    #         → 이득 없음 (세 방식 중 가장 온건)
                    #  크롭   -10.3/-21.6/-27.3% · 코트 소실 · 얼굴이 다른 사람
                    #         → 파괴적
                    #  늘리기 체형과 얼굴이 넓어짐 → 왜곡
                    # 셋 다 현행(사진 비율 유지)보다 나쁘거나 이득이 측정되지
                    # 않아 모양 강제를 넣지 않는다. 그 판정을 R216 이 잠근다 —
                    # 여백·크롭·늘리기가 들어오면 참조 비율이 캔버스 비율이 되어
                    # R216-3 이 곧바로 깨진다.
                else:
                    total = QWEN_REF_MAX_PIXELS
                    scale_by = ((total / (samples.shape[3] * samples.shape[2])) ** 0.5)
                    width = round(samples.shape[3] * scale_by / 32) * 32
                    height = round(samples.shape[2] * scale_by / 32) * 32
                s = image[:1]
                if (width, height) != (samples.shape[3], samples.shape[2]):
                    s = comfy.utils.common_upscale(samples, width, height, "lanczos", "disabled").movedim(1, -1)
                rgb = s[:, :, :, :3]
                if s.shape[-1] > 3:
                    rgb = rgb * s[:, :, :, 3:] + (1.0 - s[:, :, :, 3:])
                images_vl.append(rgb)
                # 시트 슬롯은 vision 에만 넣고 latent 에서는 제외한다(위 docstring).
                latent = None
                if vae is not None and str(_label) not in latent_skip_labels:
                    latent = vae.encode(s)
                if latent is not None:
                    ref_latents.append(latent)
                _qwen_ref_cache_put(cache_key, (rgb, latent, vae))
            except Exception as exc:  # noqa: BLE001
                # 한 장이 깨져도 전체 실행은 살린다 — 해당 이미지만 제외.
                _log(f"[GoRi Camera Director Skills] reference 이미지 변환 실패로 제외: {exc}")
                continue
        return images_vl, ref_latents

    @staticmethod
    def _qwen_image_edit_conditioning(clip, text, image_items=None, vae=None,
                                       latent_image=None, prepared=None,
                                       latent_skip_labels=None):
        """Encode Qwen image-edit text with precomputed shared reference data."""
        if prepared is None:
            images_vl, ref_latents = CameraDirectorEncode._prepare_qwen_image_data(
                image_items, vae=vae, latent_image=latent_image,
                latent_skip_labels=latent_skip_labels
            )
        else:
            images_vl, ref_latents = prepared
        if not images_vl:
            return clip.encode_from_tokens_scheduled(clip.tokenize(text))
        try:
            import node_helpers
        except Exception as exc:  # noqa: BLE001
            _log(f"[GoRi Camera Director Skills] ComfyUI conditioning helper unavailable: {exc}")
            return clip.encode_from_tokens_scheduled(clip.tokenize(text))
        tokens = clip.tokenize(
            text,
            images=images_vl,
            keep_vision=len(ref_latents) == 0,
            prevent_empty_text=True,
        )
        conditioning = clip.encode_from_tokens_scheduled(tokens)
        if ref_latents:
            conditioning = node_helpers.conditioning_set_values(
                conditioning, {"reference_latents": ref_latents}, append=True
            )
        return conditioning

    # conditioning 이어 붙이기 — 베이스가 없으면 카메라 것만 반환
    @staticmethod
    def _combine_conditioning(base_conditioning, director_conditioning):
        if base_conditioning is None:
            return director_conditioning
        return base_conditioning + director_conditioning

    # 프롬프트 문장 합치기 — 마침표 하나로 자연스럽게 잇고, 끝도 마침표 하나로 닫는다.
    # 왜(Why) 끝 마침표를 여기서 보장하나 (R197, 2026-10-22 전수 실측): 이 함수의
    # 마지막 분기가 `base + ". " + camera` 를 그대로 돌려주고, 마지막에 붙는
    # 조각(prompt_in 분기의 가드 절)이 마침표 없이 끝나면 조립문 전체가
    # 마침표 없이 끝났다. 실측: 30 토픽 × prompt_in 3종 × 참조 4조합 = 360/600
    # 케이스가 마침표 없이 끝났고, prompt_in 이 없는 경로(품질가드 조립)는
    # 마침표로 끝나 **두 경로가 서로 달랐다**. 위 주석이 이미 "마침표 하나" 를
    # 계약으로 적어 두었으므로 코드를 그 계약에 맞춘다.
    # 조각마다 끝 마침표·공백을 떼고 이어 붙이므로 ".." 도 " ." 도 생기지 않는다
    # (R195 와 같은 규칙 — 그리하여 결과는 정확히 마침표 한 번으로 끝난다).
    @staticmethod
    def _combine_prompt_text(base_text: str, camera_text: str) -> str:
        base = (base_text or "").strip().rstrip("., ")
        camera = (camera_text or "").strip().rstrip(". ")
        if not base:
            return camera + "." if camera else ""
        if not camera:
            return base + "."
        return base + ". " + camera + "."

    # 프롬프트 전용 실행 본체 — 판정/가드/문장 조립 후 conditioning 2개 + 문장 + 이미지 + latent 반환
    def run_prompt(self, clip, topic="", preset=AUTO, automation="",
                   shot=AUTO, lens=AUTO, angle=AUTO, composition=AUTO,
                   lighting=AUTO, grade=AUTO, motion=AUTO, speed=AUTO,
                   amplitude=AUTO, motion2=AUTO,
                   prompt_in=None, provider="OpenAI", model="gpt-4o-mini",
                   api_key="", custom_base_url="", positive=None, negative=None,
                   vae=None, latent_image=None,
                   image_1=None, image_2=None, image_3=None, image_4=None,
                   image_5=None, image_6=None, image_7=None, image_8=None,
                    image_9=None, image_10=None, llm_hint="", unique_id=None,
                    prompt=None, extra_pnginfo=None,
                    vision_detail=VISION_DETAIL_DEFAULT,
                    pf_steps=0, pf_cfg=0.0, pf_denoise=0.0, pose_image=None,
                    reference_max_mp=1.0):
        # reference_max_mp 는 자리만 지키는 호환 위젯이라 값이 쓰이지 않는다
        # (INPUT_TYPES 주석 참조). 그런데 **받아 두기는 해야 한다** — ComfyUI 는
        # 프롬프트에 실린 입력 키를 전부 f(**inputs) 로 넘기므로(execution.py
        # get_input_data), 위젯이 존재하는 한 이 인자가 없으면 실행이
        # TypeError 로 죽는다. llm_hint(같은 hidden 위젯)도 같은 이유로 받는다.
        del reference_max_mp
        image_items = [
            (1, image_1), (2, image_2), (3, image_3), (4, image_4), (5, image_5),
            (6, image_6), (7, image_7), (8, image_8), (9, image_9), (10, image_10),
        ]
        image_items = [(label, img) for label, img in image_items if img is not None]
        # base run 의 negative 는 쓰지 않는다 — 아래에서 build_camera_negative 로
        # 카메라 전용 negative 를 **다시 만든다**(그 과정에 llm_extra·방어어를
        # 병합한다). 그래서 여기서 받은 negative 는 즉시 버려지는 값이다.
        # 언팩은 자리만 지킨다(2026-10-25 죽은 변수 정리 — 종전 이름
        # `negative_text` 는 2832 에서 곧바로 재할당돼 한 번도 읽히지 않았다).
        prompt_out, _, _ = CameraDirector.run(
            self, topic=topic, preset=preset, automation=automation,
            shot=shot, lens=lens, angle=angle, composition=composition,
            lighting=lighting, grade=grade, motion=motion,
            speed=speed, amplitude=amplitude, motion2=motion2, prompt_in=prompt_in,
            provider=provider, model=model, api_key=api_key,
            custom_base_url=custom_base_url,
            image_items=image_items, llm_hint=llm_hint, unique_id=unique_id,
            prompt=prompt, extra_pnginfo=extra_pnginfo,
            vision_detail=vision_detail,
            pf_steps=pf_steps, pf_cfg=pf_cfg, pf_denoise=pf_denoise)
        # 왜(Why) 여기서 다시 심나 (2026-10-21 결함 수정): 위 run() 은 이번 실행
        # 한정으로 끝에서 clear_reference_kinds() 를 부른다(누수 방지). 그런데
        # Skills 는 run() 을 지나온 뒤 **아래에서** 신원 앵커·image_out 을 다시
        # 만든다 — 그 시점엔 힌트가 이미 없어, 가드 plan 은 힌트(2번=인물)로
        # 만들고 앵커는 옛 규약(1번=주 피사체)으로 되돌아가 같은 프롬프트가
        # 모순됐다(실측: "reference image 1 as the exact identity source").
        # 여기서 참조 목록으로 힌트를 되심어 앵커·image_out 이 같은 판정을 쓴다.
        # 정리는 이 함수 끝의 clear_reference_kinds() 가 맡는다.
        if image_items:
            try:
                set_reference_kinds(classify_references(image_items))
            except Exception as _e:  # noqa: BLE001
                _log("[Camera Director] 참조 자동 분류 실패(Skills 재심기) "
                     f"({type(_e).__name__}) — 기존 규약으로 진행")
        camera = getattr(self, "_last_camera", dict(DEFAULTS))
        camera_text = build_camera_conditioning(camera)
        external_prompt = (prompt_in or "").strip()
        # 한국어→영어 번역 (규칙 tier 전용, 비ASCII 감지 시에만 동작).
        # LLM tier 는 cam_llm.py 가 이미 영문으로 확장하므로 여기선 번역 안 함.
        # 번역된 영문은 아래 _user_text 조립에만 쓰고, 가드 판정은 원본 한글
        # external_prompt 를 그대로 쓴다 (한글 마커 기반 검증 동작 보존).
        # tier 는 llm / auto 두 가지뿐이다 (수동 제거).
        _tier_rp = "llm" if "llm" in (automation or "").lower() else "auto"
        external_prompt_en = external_prompt
        # _has_cjk 가드 (2026-10-13): 영어 prompt_in 은 번역 대상이 아니라
        # None(번역 불필요)이 정상이다. 가드 없이 로그하면 매 실행 오경고.
        if _tier_rp != "llm" and external_prompt and _has_cjk(external_prompt):
            _tr = translate_ko_to_en(external_prompt)
            if _tr:
                external_prompt_en = fix_fan_clause(
                    external_prompt,
                    fix_footwear_clause(
                        external_prompt, fix_pose_clause(external_prompt, _tr)))
                _log("[Camera Director] prompt_in 한글을 영어로 번역했습니다 (tc-big)")
            else:
                _log("[Camera Director] ⚠ 번역 실패 — prompt_in 원문을 사용합니다")
        # latent 크기 점검 (base run에는 latent가 없어 여기서만 가능).
        for _warn in preflight_warnings(external_prompt or (topic or ""),
                                        camera, latent_mp=_latent_mp(latent_image, vae=vae)):
            _log(f"[Camera Director] 출발 점검 ⚠ {_warn}")
        # 국가 표현형·포즈 참조 가드는 참조 슬롯 정보를 함께 봐야 하므로
        # 바깥에서 확보한다 (negative 생성도 이 블록 밖에서 일어난다).
        last_count = getattr(self, "_last_image_count", 0)
        # **폴백 필수(2026-09-29 실측 결함 수정)**: Skills 는 base run() 을
        # 거치지 않으므로 _last_image_labels 가 항상 None 이었다. 그래서
        # 슬롯 정보가 필요한 가드(포즈 참조·캐릭터 시트·가구 DNA·국가 표현형)가
        # 전부 "슬롯 교집합 = 공집합" 이 되어 조용히 미작동했다.
        # 실제 실행에서 "3번은 포즈만" 인데 포즈 가드가 붙지 않은 것이 이 결함이다.
        # image_items 로 직접 폴백해야 한다(아래쪽 image_out 블록은 같은 폴백 사용).
        last_labels = (getattr(self, "_last_image_labels", None)
                       or [l for l, _ in (image_items or [])])
        if not last_count:
            last_count = len(image_items or [])
        # positive·negative가 **같은 텍스트 소스**를 본다. 이음새가 어긋나면
        # positive 지시의 짝인 negative가 조용히 사라진다(리뷰로 실제 확인).
        # base run 이 저장한 판정 소스(topic + LLM 확장 scene)를 재사용한다.
        # 예전엔 (prompt_in + topic) 뿐이라 LLM 확장이 negative 판정에서
        # 사라졌다 — positive 지시만 있고 짝인 negative 가 없는 상태(2026-09-28).
        _subject_pi = (getattr(self, "_last_subject_text", "") or "").strip()
        _eth_text_pi = " ".join(
            x for x in (external_prompt, topic, _subject_pi) if x)
        # 가드 판정은 base run() 이 resolve_guard_plan 으로 한 번만 한다.
        # 예전엔 여기서 같은 판정을 다시 돌렸는데(포즈·물리·시트·가구·부위),
        # **텍스트 소스가 달랐다** — 여기는 prompt_in 을 앞에 붙인
        # _eth_text_pi 를 쓴다. 그래서 양쪽이 어긋나 짝인 negative 가
        # 조용히 사라졌다(2026-09-28 실측: 지시가 한쪽_only 가 됨).
        # 이제 plan 하나로 양쪽이 같은 판정을 쓴다.
        _plan_pi = getattr(self, "_last_guard_plan", None)
        if _plan_pi is None:
            # run() 없이 단독 호출된 경우(테스트·재사용). 같은 함수로 판정한다.
            # 참조 분류 힌트도 여기서 다시 심는다 — run() 이 끝나며 지웠기 때문.
            if image_items:
                try:
                    set_reference_kinds(classify_references(image_items))
                except Exception as _e:  # noqa: BLE001
                    # run() 경로(위)와 같은 이유로 원인을 남긴다 — 조용히
                    # 삼키면 "참조가 왜 안 먹지" 를 로그로 추적할 수 없다.
                    _log("[Camera Director] 참조 자동 분류 실패(단독 호출) "
                         f"({type(_e).__name__}) — 기존 규약으로 진행")
            # 왜(Why) 인자에서 다시 유도하나 (2026-10-05 감사): 예전엔
            # _last_tier/_last_llm_hint 를 읽었지만 이 속성을 쓰는 곳이
            # 저장소에 하나도 없어 폴백이 항상 tier=""/llm_hint="" 로
            # 판정했다 — 유령 속성. run() 이 automation 에서 tier 를
            # 유도하는 것과 같은 식을 이 함수의 인자로 재현한다.
            _low_a_pi = (automation or "").lower()
            # tier 는 llm / auto 두 가지뿐이다 (수동 제거).
            _tier_pi = "llm" if "llm" in _low_a_pi else "auto"
            # 약한 시트(3뷰 줄) — run() 을 거치지 않은 단독 호출에서도
            # topic 시트 선언과 교차하면 측정한다.
            _weak_sheet_pi = []
            if (_is_character_sheet_request(_eth_text_pi)
                    and not _is_multi_person_sheet(_eth_text_pi)):
                try:
                    _weak_sheet_pi = weak_sheet_slots(image_items)
                except Exception:  # noqa: BLE001
                    _weak_sheet_pi = []
            _plan_pi = resolve_guard_plan(
                _eth_text_pi, camera, last_count, last_labels, image_items,
                (image_items[0][1] if image_items else None), [],
                tier=_tier_pi, llm_hint=llm_hint,
                weak_sheet_slots=_weak_sheet_pi,
                sheet_kind=getattr(self, "_last_sheet_kind", ""),
                declared_topic=topic or "")
        _gpos_pi = _plan_pi["positive"]
        _gflags_pi = _plan_pi["flags"]
        _px_sheet_pi = _plan_pi["pixel_sheet_slots"]
        # 약한 시트(3뷰 줄) — run() 이 측정해 plan 에 실어 보낸 값. 엄격 판정과
        # 합쳐 latent 제외에만 쓴다(가드 발동에는 안 쓴다).
        _weak_pi = _plan_pi.get("weak_sheet_slots") or []
        if _px_sheet_pi:
            _log(f"[Camera Director] 참조 이미지 {'/'.join(_px_sheet_pi)}번에서 "
                 "캐릭터 시트 패턴 감지 (topic 문구와 무관)")
        _cs_text_pi = _gpos_pi["character_sheet"]
        _furn_pos_pi = _gpos_pi["furniture"]
        # 배경 참조 사물 충실 (2026-10-22) — base run 과 같은 plan 조각.
        _furn_bg_pi = _gpos_pi.get("furniture_bg", "")
        # 참조 사물 외형 고정 (2026-10-16) — 가구 DNA 문구와 짝이다.
        _furn_surf_pos_pi = _plan_pi.get("furniture_surface_pos", "")
        _furn_surf_neg_pi = _plan_pi.get("furniture_surface_neg", "")
        _remove_item_pi = _gflags_pi["remove_item"]
        _detail_def_pi = _gflags_pi["detail_def"]
        _anatomy_count_pi = _gflags_pi["anatomy_count"]
        _footwear_pi = _gflags_pi["footwear"]
        _footwear_bare_pi = _gflags_pi["footwear_bare"]
        _boundary_pi = _gflags_pi["body_object_boundary"]
        _garment_pi = _gflags_pi["garment_boundary"]
        # 손 배치 (2026-10-24, R220) — base run 과 같은 plan 조각.
        _hand_place_pi = _gflags_pi["hand_placement"]
        _pose_pos_pi = _gpos_pi["pose"]
        _phys_pos_pi = _gpos_pi["physics"]
        _phys_neg_pi = _plan_pi["physics_neg"]
        # 정면 응시 (2026-10-15): external_prompt 없는 실행에서도 아래
        # 병합부가 이름을 찾을 수 있게 미리 빈 값으로 둔다.
        _gaze_pos_pi, _gaze_neg_pi = "", ""
        # 의류 색상 (2026-10-15): 같은 이유로 미리 빈 값으로 둔다.
        _item_pos_pi, _item_neg_pi = "", ""
        if external_prompt:
            # 의도 분석용 코어 (2026-10-19). 외부 프롬프트는 태그 나열이라
            # 서술 조각("wearing a summer dress")이 옷 교체로 오탐돼 신원
            # 앵커의 의상 보존 분기가 조용히 사라졌다(실측). 감지에는 코어를
            # 쓰고 출력 문장은 외부 프롬프트를 그대로 쓴다.
            _analysis_pi = intent_core(" ".join(
                x for x in (external_prompt, topic) if x))
            identity_anchor = build_identity_anchor(
                last_count, _analysis_pi, image_labels=last_labels)
            single_person_anchor = build_single_person_anchor(
                last_count, _analysis_pi, image_labels=last_labels)
            # Qwen 표준 경로에도 의상 교체 의도가 명확하면 의상 전용 가드를 둔다.
            # 왜(Why): 이 가드는 standalone 경로(assemble)에만 있어 prompt_in
            # 사용 시 의상 융합 방지 문구가 전혀 안 들어갔기 때문이다.
            outfit_anchor = outfit_guard(last_count, _analysis_pi)
            duo_anchor = build_duo_person_anchor(
                last_count, _analysis_pi, image_labels=last_labels)
            # duo(2인)일 때는 보조-role 제한 가드를 빼고 duo 정체성 보존을 둔다.
            # 왜(Why): role 제한은 image_2의 인물 역할을 금지해 남성이 사라지기 때문이다.
            role_anchor = "" if duo_anchor else build_secondary_role_anchor(
                last_count, _analysis_pi, image_labels=last_labels)
            base_text = self._combine_prompt_text(identity_anchor, single_person_anchor)
            base_text = self._combine_prompt_text(base_text, outfit_anchor)
            base_text = self._combine_prompt_text(base_text, duo_anchor)
            base_text = self._combine_prompt_text(base_text, role_anchor)
            # 자동 분류 역할 문장 (2026-10-25 감사) — base run 이 분류 결과로 만든
            # 문장을 여기서도 병합한다. 왜(Why): 이 문장은 base 에서만 붙어
            # prompt_out 으로 나갔고, prompt_in 경로는 앵커로 다시 세우느라 그것을
            # 잃었다. 다만 **참조에 사람이 있을 때는 병합하지 않는다** — 그때는
            # 신원·보조 역할 앵커가 이미 참조 사용법을 정해 두었고(빈 topic 이어도
            # 2번 사람을 주 피사체로 지목한다), 자동 역할 문장을 겹치면 R172 가
            # 금지하는 "reference image 1"(비주체 참조를 포함 대상으로 지목)이
            # 다시 나타난다. 사람이 없으면 앵커가 비어(build_identity_anchor 는
            # 비-사람이면 "") 이 문장이 참조 사용법을 알리는 유일한 문구라
            # 반드시 필요하다 — base/standalone 과 같은 문장을 넣는다.
            _auto_roles_pi = (getattr(self, "_last_auto_roles", "") or "").strip()
            if (_auto_roles_pi and not _hint_person_slots()
                    and _auto_roles_pi not in base_text):
                base_text = self._combine_prompt_text(base_text, _auto_roles_pi)
            # topic 칸도 **장면 텍스트로 포함**한다 (2026-10-13 사용자 지시).
            # 왜(Why) 고쳤나: 종전에는 prompt_in 이 연결되면 topic 텍스트가
            # 프롬프트에서 **조용히 빠졌다.** 판정용 텍스트(_eth_text_pi)에는
            # 합쳐지고 프롬프트에는 안 들어가는 어중간한 상태라, 사용자가 topic 에
            # 써 놓고 "반영됐겠지" 하면 로그로도 알 수 없었다(조용한 무시 금지).
            # 중복 회피: prompt_in 이 이미 같은 문장을 담고 있으면 붙이지 않고
            # 그 사실을 로그로 말한다 — 두 번 넣으면 샘플러가 같은 장면을 두 번 읽는다.
            # (네거티브에는 넣지 않는다 — topic 은 긍정 서술이라 부정문이 되면
            #  positive 와 정면 충돌한다. 2026-10-11 MIX_GUARD 실측과 같은 이유.)
            _scene_pi = (topic or "").strip()
            # 역할 선언 줄 분리 (2026-10-23, AC-12): Skills(topic) 경로에도 같은
            # 표기가 들어온다 — 이 노드가 사용자가 실제로 실행하는 노드다.
            # 보정 근거(_scene_pi → fix_footwear/fix_pose)는 **원문 그대로** 두고,
            # 번역 입력과 프롬프트 문장만 scene_out 을 쓴다(design 4절과 같은 원칙).
            _scene_pi_out = (_scene_pi if _tier_rp == "llm"
                             else scene_text(topic))
            _scene_pi_en = _scene_pi_out
            if _tier_rp != "llm" and _scene_pi_out:
                if _looks_like_synopsis(_scene_pi_out):
                    _syn = structure_ko_synopsis(_scene_pi_out)
                    _syn_en = _syn.get("scene_en", "")
                    if _syn_en and _syn_en != _scene_pi_out:
                        _scene_pi_en = _syn_en
                        _h = _syn.get("hints", {}) or {}
                        _h_log = ", ".join(f"{k}" for k, v in _h.items()
                                           if v and k != "sentence_count")
                        _log(f"[Camera Director] topic 시놉시스 구조화 완료 "
                             f"({_h.get('sentence_count', 0)}문장 → 영문 장면)"
                             + (f" · 이해: {_h_log}" if _h_log else ""))
                    else:
                        # _has_cjk 가드 — 영어 topic 은 번역 대상이 아니라
                        # translate 가 None(정상)을 돌려 기본값(_scene_pi)을
                        # 유지한다. 가드 없이 호출해도 결과는 같고 조용하다.
                        if _has_cjk(_scene_pi_out):
                            _tr = translate_ko_to_en(_scene_pi_out)
                            if _tr:
                                _scene_pi_en = _en_normalize(
                                    fix_footwear_clause(
                                        _scene_pi,
                                        fix_pose_clause(_scene_pi, _tr)))
                else:
                    if _has_cjk(_scene_pi_out):
                        _tr = translate_ko_to_en(_scene_pi_out)
                        if _tr:
                            _scene_pi_en = _en_normalize(
                                fix_footwear_clause(
                                    _scene_pi, fix_pose_clause(_scene_pi, _tr)))
            # 역할 선언 줄 분리 (R224, 2026-10-24 실측): prompt_in 경로에도 같은
            # 표기가 들어온다 — 워크플로의 GoogleTranslateTextNode 가 토픽을 영어로
            # 미리 번역해 넣으면 `Number 1: ... / Directed by: <장면>` 이 최종
            # 프롬프트에 그대로 실렸다(8389자). 위 topic 경로와 **같은 함수**를
            # 쓴다 — 따로 만들면 한쪽만 갱신돼 조용히 갈린다.
            # LLM tier 는 이미 영문 장면이라 손대지 않는다(_scene_pi_out 과 같은 규칙).
            _external_out = (external_prompt_en if _tier_rp == "llm"
                             else scene_text(external_prompt_en))
            _user_text = _external_out
            if _scene_pi_out:
                if _scene_pi_out.lower() in _external_out.lower():
                    _log("[Camera Director] topic 칸 텍스트가 prompt_in 에 이미 "
                         "포함돼 있어 중복을 생략합니다 (장면 문장 1회만)")
                else:
                    _user_text = self._combine_prompt_text(
                        _scene_pi_en, _external_out)
            # 배경 지정 문장 보정 (2026-10-15, base run과 동일 판정):
            # 번역기가 뭉갠 자기참조 배경 문장은 지시력을 잃는다.
            _ko_user_pi = (topic or "") + " " + (external_prompt or "")
            _user_text = fix_background_clause(_ko_user_pi, _user_text)
            # 부채 보유 문장 복구 (2026-10-15, base run과 동일 판정).
            _user_text = fix_fan_clause(_ko_user_pi, _user_text)
            # 손가락 분리 단서를 장면 문장 위치에도 둔다 (2026-10-22 R194 실측).
            # base run 과 **같은 헬퍼**(scene_finger_cue)로 판정한다 — 두 경로가
            # 각자 판정하면 한쪽만 갱신돼 방어가 조용히 어긋난다(2026-09-28 실측).
            # 문장 소스는 resolve_guard_plan 에 넘긴 _eth_text_pi 와 같다.
            # 위치: 포즈 분기·정면 응시·색상 고정보다 **앞** — 실측한 팔에서 단서가
            # 사용자 문장 끝(prompt_in 안)에 있었고 그 뒤에 저 문장들이 붙었다.
            _scene_cue_pi = scene_finger_cue(_eth_text_pi)
            if _scene_cue_pi and _user_text.strip():
                _user_text = (_user_text.rstrip().rstrip(".")
                              + ". " + _scene_cue_pi)
            # 로그는 아래(분기 밖)에서 **최종 텍스트**를 보고 한 번만 남긴다
            # (R196). 여기서 찍으면 prompt_in 이 **없는** 분기에서 이 사본이
            # 버려지는데도(positive_text = prompt_out) "둠" 이라고 알리게 된다.
            # 포즈 분기 문장 (2026-10-13, PROVISIONAL): _scene_pi_en 과
            # external_prompt_en 을 합친 뒤 한 번만. 각자에 붙이면 문장이
            # 2회 중복된다 (add_pose_divergence 는 같은 문장 중복을 막지만
            # 합친 텍스트에 2개 들어가면 그대로 둔다).
            _user_text = add_pose_divergence(
                _user_text, last_count or len(image_items or []),
                (topic or "") + " " + (external_prompt or ""))
            # 정면 응시 보강 (2026-10-15, base run과 동일 판정) —
            # negative 회피어는 아래 병합부에서 짝으로 붙는다.
            _gaze_pos_pi, _gaze_neg_pi = gaze_forward_guard(
                (topic or "") + " " + (external_prompt or ""), _user_text)
            if _gaze_pos_pi:
                _user_text = (_user_text.rstrip().rstrip(".")
                              + ". " + _gaze_pos_pi)
                _log("[Camera Director] 정면 응시 가드 활성 (positive 보강 + "
                     "negative 회피어)")
            # 의류 색상 고정 (2026-10-15, base run과 동일 판정) —
            # negative 오색은 아래 병합부에서 짝으로 붙는다.
            _item_pos_pi, _item_neg_pi = color_adherence_guard(
                (topic or "") + " " + (external_prompt or ""), _user_text)
            if _item_pos_pi:
                _user_text = (_user_text.rstrip().rstrip(".")
                              + ". " + _item_pos_pi)
                _log("[Camera Director] 의류 색상 고정 가드 활성 (positive "
                     "고정 + negative 오색)")
            # 좌석 접촉점을 장면 문장 **뒤**로 옮긴다 (2026-10-25, R239).
            # 왜(Why) — 실측 A/B (같은 실행 그래프, seed 42, tier=규칙, 참조 4장).
            # 네 실행 모두 좌석·가구 가드가 동일하게 발동했는데 의자(2번 참조)
            # 충실도가 갈렸다: `#112` 가 98자(노드 가드만)인 실행은 의자가
            # **소실**됐고, 같은 가드 **원문**을 장면 문장 뒤에 둔 실행은 의자가
            # **회복**됐다. 즉 문구 내용은 옳고 **위치가 틀렸다** — 종전 자리인
            # 꼬리에는 조항이 15개 더 이어져 희석된다.
            # 옮기는 것은 **접촉점 조항 하나**다. 실측에서 접촉점만 넣으면 의자가
            # 살아나고 의상이 멀쩡했으나, 방향 조항만 넣거나 둘 다 넣으면
            # 카디건이 사라졌다(그 조항은 `reference image 2` 를 반복 지목하는
            # 긴 문장이라 앞에 두면 꼬리 가드를 희석한다). 그래서 방향 조항은
            # 가구 DNA 안의 종전 자리를 지킨다.
            # 장면 문장을 **따르는** 자리여야 한다 — 앞에 두면 무효였다(실측).
            if _gpos_pi.get("seat"):
                _user_text = (_user_text.rstrip().rstrip(".")
                              + ". " + _gpos_pi["seat"])
                _log("[Camera Director] 좌석 접촉점 가드 활성 ("
                     + "/".join(str(x) for x in
                                sorted(_plan_pi["seat_slots"]))
                     + "번 — 장면 문장 뒤로 이동, 체중이 좌석 쿠션에, "
                     "팔걸이 걸터앉음 방어)")
            base_text = self._combine_prompt_text(base_text, _user_text)
            positive_text = self._combine_prompt_text(base_text, camera_text)
        else:
            positive_text = prompt_out
            single_person_anchor = ""
            # 정면 응시·의류 색상의 negative 회피어를 standalone 에서도 살린다
            # (2026-10-25 비대칭 결함 수정). 왜(Why) 필요한가: 이 두 가드의
            # 보강문(positive)은 base run 이 만든 prompt_out 에 이미 들어 있는데
            # (positive_text = prompt_out), negative 는 아래에서
            # build_camera_negative 로 **다시 만든다** — base run 의 negative 를
            # 쓰지 않는다. 그 재조립에는 gaze/item 회피어가 없어서 positive 에는
            # 있고 negative 에는 없는 비대칭이 됐다(실측: standalone 정면 응시·
            # 의류 색상 회피어 유실). 위 `if external_prompt:` 블록 안에서만
            # 계산되던 것을 여기서도 같은 함수·같은 원문 소스로 계산해 짝을 맞춘다
            # (소스는 위 분기와 동일하게 topic + prompt_in 으로 맞춘다).
            _guard_src_pi = (topic or "") + " " + (external_prompt or "")
            _gaze_pos_pi, _gaze_neg_pi = gaze_forward_guard(
                _guard_src_pi, positive_text)
            _item_pos_pi, _item_neg_pi = color_adherence_guard(
                _guard_src_pi, positive_text)
            # 짝 강제 (2026-10-25 감사). 이 분기의 positive_text 는 base run 의
            # prompt_out 이라, 그 가드의 보강문이 이미 들어 있으면 negative 만
            # 더하면 짝이 맞는다. 문제는 **보강문 없이 negative 만 붙는 경로**다:
            # 위 gaze_forward_guard 는 en_text(최종 프롬프트)에서 영문 마커를
            # 찾는데, 그 안에는 사물 방향 잠금 상용구("The side facing the camera
            # in the reference ...", FURNITURE_ORIENTATION_POSITIVE)의
            # "facing the camera" 도 들어 있다. 사람 주제 + 사물 참조에서 이것이
            # 정면 응시 마커로 **오탐**되고, base run 은 자기 소스(장면문)로
            # 판정하므로 보강문을 넣지 않는다 — 그래서 negative 만 나가
            # 요청하지 않은 "profile view·side glance" 회피어가 측면·옆모습
            # 구도를 억제했다(실측 재현: _workspace/probe10_gaze_natural.py).
            # 보강문이 실제로 없으면 negative 도 붙이지 않는다(짝 불변식).
            if (_gaze_neg_pi
                    and "directly into the camera" not in positive_text.lower()):
                _gaze_neg_pi = ""
            # 색상 고정도 같은 불변식을 적용한다 — 보강문이 없으면 회피어도 뺀다.
            if (_item_neg_pi
                    and "kept true to the requested shade"
                    not in positive_text.lower()):
                _item_neg_pi = ""
        # R196 (2026-10-22 실측) — 단서 로그는 **최종 텍스트에서 한 번만**.
        # 왜(Why) 종전에는 같은 줄이 2번 찍혔나: run() 과 run_prompt() 가 각자
        # 자기 삽입에 로그를 남겼는데, 두 분기 중 **한쪽 삽입은 항상 버려진다**
        #   prompt_in 있음   positive_text 를 앵커로 다시 세운다 -> run() 몫 버려짐
        #   prompt_in 없음   positive_text = prompt_out          -> run_prompt 몫 버려짐
        # 그래서 "실제로 나가는 글자" 를 아는 이 자리에서 한 번만 알린다.
        # 판정 표식은 앞이 ". " 인 사본이다 — 단서 문구(SCENE_FINGER_CUE)가
        # FINGER_SEPARATION_POSITIVE 를 품고 그 부분문자열이 **가드 문장 끝과
        # 같은 글자**라, 그냥 세면 가드 몫까지 세어진다(2026-10-22 실측 함정).
        if (". " + SCENE_FINGER_CUE) in positive_text:
            _log("[Camera Director] 손가락 분리 단서를 장면 문장 위치에도 둠 "
                 "(R194 · 실측 평균 +0.33, 보장 아님)")
        # 포즈 맵 + 프롬프트 묘사를 **함께** 쓴다 (2026-10-14 사용자 지시).
        # pose_image 가 연결되고 판독되면 맵 문장을 프롬프트에 **보탠다**.
        # image_items(개수·vision·latent)에는 넣지 않는다 — 맵은 참조 사진이
        # 아니라 강제 원본이라 개수 가드·신원 판독·확산 prior 에 닿으면 안 된다.
        # 왜(Why) 종전의 "분기 문장 제거" 를 되돌렸나 (2026-10-14 실측 A/B):
        #   종전엔 맵이 판독되면 _POSE_DIVERGENCE("포즈는 위 묘사를 따른다")를
        #   지워 맵을 단독 권위로 만들었다. 그러면 프롬프트에 적은 포즈 묘사가
        #   힘을 잃는다. 실측으로 묘사 문장 하나가 실제로 포즈를 바꾼다 —
        #   같은 그래프에서 "이미지2의 의자에 앉아있다" 를 넣자 서 있음(SUV
        #   배경)이 벤치에 앉음(공원)으로 바뀌었고, 그 한 문장이 유일한 차였다.
        #   두 선언은 방향이 같다(둘 다 참조 사진의 포즈를 밀어낸다) — 함께
        #   두면 서로를 보강한다. 맵이 말하지 않는 것(구도·장면)은 묘사가 채운다.
        #   주의: 토픽과 맵이 정반대 포즈를 말하면 두 문장이 부딪힌다. 그때는
        #   로그로 드러나므로 사용자가 어느 쪽을 고칠지 판단한다.
        # 미연결·판독불가면 기존과 바이트 동일.
        if pose_image is not None:
            try:
                _parsed = parse_dw_pose_map(pose_image)
                _map_class = _parsed.get("pose")
                if _map_class:
                    _log(f"[Camera Director] 목표 포즈(맵): {_map_class}")
                    _map_sentence = pose_map_sentence(
                        _map_class, _parsed.get("detail"))
                    if _map_sentence:
                        positive_text = self._combine_prompt_text(
                            positive_text, _map_sentence)
                        _log("[Camera Director] 포즈맵 문장을 프롬프트 묘사에 "
                             "보탭니다 (묘사 유지 — 둘 다 사용)")
                else:
                    _why = (_parsed.get('detail') or {}).get('reason')
                    _hint = ""
                    if _why == "no-limb-mass":
                        # 실측 2026-10-14: DW 는 원본 해상도 캔버스에 그린 뒤
                        # resolution 크기로 줄여 반환한다. 원본이 크면 선이
                        # 1px 대로 얇아져 팔다리 덩어리가 하나도 안 남는다.
                        # DW **앞**에 ImageScaleToTotalPixels 를 두면 살아난다
                        # (실측 0개 -> 4개, 도트 0색 -> 9색).
                        _hint = (" — DW 앞에 ImageScaleToTotalPixels(약 1MP)를 "
                                 "두면 선 굵기가 살아납니다")
                    elif _why in ("no-thigh-mass", "ambiguous-mass"):
                        # 실측 2026-10-14: 정면에서 다리를 앞으로 뻗은 앉음은
                        # 2D 투영이 서 있음과 구분되지 않는다(굴곡각 12~15도).
                        # 접촉 임계를 풀면 오히려 서 있음으로 **오판**하므로
                        # None 을 유지한다. 프롬프트 묘사가 그 자리를 받는다.
                        _hint = (" — 정면 앉음은 2D 투영이 서 있음과 겹칩니다. "
                                 "포즈는 프롬프트 문장으로 묘사하세요")
                    _log("[Camera Director] 포즈 맵 판독 불가 — 기존 방식 유지 "
                         f"(사유={_why}){_hint}")
            except Exception as _e:
                _log("[Camera Director] 포즈 맵 판독 실패 "
                     f"({type(_e).__name__}) — 기존 방식 유지")
        # 아래 가드 병합은 prompt_in 경로에만 적용한다.
        # 왜(Why): standalone 경로의 prompt_out(assemble 결과)에는 매크로·노출·
        # 믹스·외양·발란스·시트 가드가 이미 들어 있어, 그대로 다시 붙이면
        # 같은 문구가 2회 중복되기 때문이다. prompt_in 경로는 앵커를 다시
        # 조립하므로 여기서 붙여야 한다.
        if external_prompt:
            detail_guard = macro_detail_guard(external_prompt or topic, camera)
            if detail_guard:
                positive_text = self._combine_prompt_text(positive_text, detail_guard)
            nudity_guard = nudity_anatomy_guard(external_prompt or topic)
            if nudity_guard:
                positive_text = self._combine_prompt_text(positive_text, nudity_guard)
            # 사용자가 직접 지시한 가림만 반영한다 (자동 개입 아님).
            cover_guard = coverage_guard(external_prompt or topic)
            if cover_guard:
                positive_text = self._combine_prompt_text(positive_text,
                                                          cover_guard)
            # 다중 참조 실행이면 믹스 가드도 Skills positive에 병합한다.
            # 왜(Why): base run()의 믹스 가드는 standalone assemble 결과에만 붙고,
            # prompt_in 경로는 앵커를 다시 조립하므로 유실되기 때문이다.
            if _gflags_pi["mix_guard"]:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _gpos_pi["mix_guard"])
            # 10번 외양 참조 실행이면 외양 가드도 Skills positive에 병합한다.
            if getattr(self, "_last_appearance_ref", False):
                positive_text = self._combine_prompt_text(positive_text,
                                                          APPEARANCE_REF_POSITIVE)
                positive_text = self._combine_prompt_text(
                    positive_text, APPEARANCE_HAIR_REALISM_POSITIVE)
            if _gflags_pi["body_balance"]:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["body_balance"])
            # 부위별 디테일 경계·가구 DNA도 Skills positive에 병합한다
            # (base run과 **동일 판정** — 하나만 갱신되면 positive/negative가
            #  어긋나 짝인 방어가 사라진다).
            if _detail_def_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["detail_def"])
            if _anatomy_count_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["anatomy_count"])
            # 다리·발·종아리 무결성 (2026-10-21) — prompt_in 경로도 같은 판정.
            if _gpos_pi["limb_integrity"]:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["limb_integrity"])
                _log("[Camera Director] 다리·발·종아리 무결성 가드 활성 "
                     "(추가 발·휜 종아리·손 뭉갬 방어)")
            if _footwear_pi or _footwear_bare_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["footwear"])
            if _boundary_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["body_object_boundary"])
            # 좌석 접촉점 (2026-10-24, R226) 은 여기(꼬리)에 있지 않다.
            # 2026-10-25 R239 실측: 꼬리에서는 뒤따르는 15개 조항에 희석돼
            # 의자가 소실됐다. 위 장면 조립 블록(장면 문장 바로 뒤)으로 옮겼다.
            # 방향 조항(SEAT_ORIENTATION_POSITIVE)은 가구 DNA 안 종전 자리를
            # 지킨다 — 그 조항은 `reference image 2` 를 반복 지목하는 긴
            # 문장이라 앞에 두면 의상 보존 꼬리 가드를 희석한다(b8/b4 실측).
            # 의복 경계 (2026-10-16) — 위 가구 경계와 짝이다.
            if _garment_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["garment_boundary"])
            # 손 배치 (2026-10-24, R220) — base run 과 같은 plan 조각.
            if _hand_place_pi:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["hand_placement"])
                _log("[Camera Director] 손 배치 가드 활성 "
                     "(두 손 겹침·한 덩어리 합침·손가락 넘어감 방어)")
            if _cs_text_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _cs_text_pi)
            if _furn_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _furn_pos_pi)
            # 참조 사물 외형 고정 (2026-10-16) — 위 가구 DNA 와 짝이다.
            if _furn_surf_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _furn_surf_pos_pi)
            # 배경 참조 사물 충실 (2026-10-22) — base run 과 같은 판정·같은
            # plan 조각이다. 사물 정식 슬롯과 달리 존재를 요구하지 않는다.
            if _furn_bg_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _furn_bg_pi)
            # (캐릭터 시트 문구는 위에서 _cs_text_pi 로 이미 병합했다.
            # 실행 간 캐시로 같은 문구를 또 붙이면 110단어어 positive 가 두 번
            # 들어가 token 을 중복 소비한다. 2026-09-28 실행 간 캐시 제거,
            # 2026-09-29 죽은 속성까지 정리)
            # 스케일 일관 가드도 prompt_in 경로에 병합한다.
            # (standalone는 assemble에 이미 포함. 판정 소스는 이 경로의
            # 다른 가드(민족·동물·포즈)와 같은 _eth_text_pi 다 — 2026-10-16
            # 감사: 예전 `external_prompt or topic` 은 prompt_in 연결 시
            # topic 의 인물 표기를 못 보아 판정이 꺼질 수 있었다.)
            if _needs_scale_guard(_eth_text_pi, camera):
                positive_text = self._combine_prompt_text(positive_text,
                                                          SCALE_COHERENCE_POSITIVE)
            # 국가 표현형 가드도 prompt_in 경로에 병합한다.
            # (국가명은 한글 위젯 topic에만 있을 수 있어 양쪽 다 본다)
            # 참조 이미지가 신원을 고정하는 실행은 억제된다 (positive/negative 동일 판정).
            _eth_pos_pi, _ = _ethnicity_guard(_eth_text_pi, last_count, last_labels)
            if _eth_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _eth_pos_pi)
            # 동물 종 보존 가드도 prompt_in 경로에 병합한다.
            if _is_animal_subject(_eth_text_pi):
                positive_text = self._combine_prompt_text(
                    positive_text, ANIMAL_SPECIES_POSITIVE)
            # 포즈 참조 가드도 prompt_in 경로에 병합한다 (base run과 동일 판정).
            if _pose_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _pose_pos_pi)
            # 물리·공간 가드도 prompt_in 경로에 병합한다.
            if _phys_pos_pi:
                positive_text = self._combine_prompt_text(positive_text,
                                                          _phys_pos_pi)
            # 간격 유지 가드(spacing)도 prompt_in 경로에 병합한다 (2026-10-23).
            # 왜(Why) 필요했나: base run 은 `_plan["positive"]["spacing"]` 을
            # 붙이는데(1652) prompt_in 경로는 physics/ground 만 읽어, 이 가드가
            # **단독으로 서는 경우**(physics positive 가 비어 있고 참조 2장 이상)
            # positive 문구만 사라지고 짝 negative 는 그대로 나갔다 — "간격을
            # 벌리지 마라" 만 있고 "측정된 거리·지면을 유지하라" 가 없는 한 방향
            # 방어였다(실측: BASE positive True / prompt_in False). plan 조각
            # `spacing` 은 physics positive 가 있으면 이미 빈 값이므로(442)
            # 여기서 중복 병합은 생기지 않는다.
            if _gpos_pi.get("spacing"):
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["spacing"])
            # 배경 지면 고정 가드도 prompt_in 경로에 병합한다 (base run과
            # 동일 판정 — plan 하나가 두 경로의 positive/negative 를 만든다).
            if _gpos_pi["ground"]:
                positive_text = self._combine_prompt_text(
                    positive_text, _gpos_pi["ground"])
                _log("[Camera Director] 배경 지면 고정 가드 활성 (참조 지면으로 "
                     "통일 + 콘크리트/실내 매끈 바닥 방어)")
            # 품질 가드도 prompt_in 경로에 병합한다 (base run의
            # assemble → add_quality_guard 에 해당. 왜(Why): 이 경로에만
            # 빠져 있어 prompt_in 실행에서 품질 지시가 없었다
            # 2026-10-07 감사). 주제에 맞는 상수는 quality_guard_text 한 곳이
            # 고른다 (사람 / 동물 전용 / 비인간 장면 — 2026-10-25 감사 통합).
            # add_quality_guard 와 **같은 함수**를 써서 두 경로가 갈리지 않는다.
            positive_text = self._combine_prompt_text(
                positive_text, quality_guard_text(_eth_text_pi))
        # LLM 의상 서술을 최종 문장에 반영한다 (2026-10-25, AC-2).
        # 왜(Why) 여기가 유일한 자리인가: prompt_in 이 연결되면 base run 이 만든
        # LLM 장면(prompt_out)은 이 함수에서 버려지고(위 분기), 이 노드는 앵커로
        # 문장을 다시 세운다. 그래서 LLM 이 옷을 서술해도 그 문장이 최종 프롬프트에
        # **닿지 못했다**(실측 2026-10-25: 장면에 "wearing elegant high heels" 만
        # 남고 카디건·원피스 누락). 두 분기(prompt_in / standalone)를 **지난 뒤**
        # 한 번만 붙여 양쪽이 같은 문구를 받게 한다. standalone 은 prompt_out 에
        # 장면이 이미 들어 있어 중복이 될 수 있으므로 부분문자열 중복 검사로 막는다.
        # 규칙(auto) tier 는 `_last_llm_outfit` 이 빈 값이라 무동작(AC-3).
        if _tier_rp == "llm":
            _llm_outfit_pi = (getattr(self, "_last_llm_outfit", "") or "").strip()
            if _llm_outfit_pi and _llm_outfit_pi.lower() not in positive_text.lower():
                positive_text = self._combine_prompt_text(
                    positive_text, "wearing " + _llm_outfit_pi)
                _log("[Camera Director] LLM 의상 서술을 프롬프트에 반영 ("
                     + str(len(_llm_outfit_pi)) + "자)")
        prevent_duplicates = bool(single_person_anchor) if external_prompt else False
        # negative도 positive와 **같은 텍스트 소스**를 본다 (topic + prompt_in).
        # 왜(Why): 이음새가 어긋나면 positive에 붙은 지시의 짝인 negative가
        # 조용히 사라진다 — 실측으로 국가 표현형(브라질)·동물 가드에서 확인됨.
        # 국가명은 한글 topic 칸에만 있을 수 있어 prompt_in만 보면 놓친다.
        # 출력 가로세로비를 latent 에서 읽는다 (2026-10-16). DenoResolutionSetup
        # 이 latent 크기를 정하므로 그 가로/세로가 곧 출력 비율이다. 화면비
        # 인지형 다리 복제 에스컬레이션(16:9·19:6) 판정 근거로 쓴다.
        _aspect_ratio_pi = None
        if latent_image is not None:
            try:
                _s_pi = (latent_image["samples"]
                         if isinstance(latent_image, dict) else latent_image)
                _h_pi, _w_pi = int(_s_pi.shape[-2]), int(_s_pi.shape[-1])
                if _h_pi and _w_pi:
                    _aspect_ratio_pi = _w_pi / _h_pi
            except Exception:  # noqa: BLE001
                _aspect_ratio_pi = None
        negative_text = build_camera_negative(
            camera, prevent_duplicates=prevent_duplicates,
            topic=_eth_text_pi, image_count=last_count,
            image_labels=last_labels,
            pose_ref=bool(_pose_pos_pi), physics_neg=_phys_neg_pi,
            detail_def=_detail_def_pi, furniture=bool(_furn_pos_pi),
            furniture_bg=bool(_furn_bg_pi),
            remove_item=_remove_item_pi, anatomy_count=_anatomy_count_pi,
            character_sheet=bool(_cs_text_pi),
            sheet_kind=getattr(self, "_last_sheet_kind", ""),
            anatomy_count_upper=bool(
                _plan_pi["flags"].get("anatomy_count_upper")),
            detail_def_upper=bool(
                _plan_pi["flags"].get("detail_def_upper")),
            footwear=_footwear_pi,
            footwear_upper=bool(
                _plan_pi["flags"].get("footwear_upper")),
            footwear_bare=_footwear_bare_pi,
            body_object_boundary=_boundary_pi,
            body_object_boundary_upper=bool(
                _plan_pi["flags"].get("body_object_boundary_upper")),
            garment_boundary=_garment_pi,
            garment_boundary_upper=bool(
                _plan_pi["flags"].get("garment_boundary_upper")),
            hand_placement=_hand_place_pi,
            seat=bool(_gpos_pi.get("seat")),
            aspect_ratio=_aspect_ratio_pi)
        # LLM이 제안한 extra negative가 있으면 카메라 negative 뒤에 병합한다.
        # 왜(Why): base run()은 llm_extra를 build_negative에 넣지만, 위에서
        # 카메라 전용 negative로 덮어쓰면서 조용히 버려졌기 때문이다.
        llm_extra_text = (getattr(self, "_last_llm_extra", "") or "").strip().rstrip("., ")
        if llm_extra_text:
            negative_text = negative_text.rstrip("., ") + ", " + llm_extra_text
        # llm_hint 사용 실행이면 검열 방어어도 Skills negative에 병합한다.
        # 왜(Why): Skills 경로는 negative를 build_camera_negative로 다시 만들어
        # base run()의 방어어가 유실되기 때문이다.
        if _gflags_pi["hint_defense"]:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + HINT_DEFENSE_NEGATIVE)
        # 다중 참조 실행이면 믹스 가드 방어어도 Skills negative에 병합한다.
        if _gflags_pi["mix_guard"]:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + MIX_GUARD_NEGATIVE)
        # 10번 외양 참조 실행이면 컷 삽입 방어어도 Skills negative에 병합한다.
        if getattr(self, "_last_appearance_ref", False):
            negative_text = (negative_text.rstrip("., ")
                             + ", " + APPEARANCE_REF_NEGATIVE)
        # 인물 신체 발란스 방어어도 병합한다.
        if _gflags_pi["body_balance"]:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + BODY_BALANCE_NEGATIVE)
        # 정면 응시 회피어 (2026-10-15) — positive 보강문과 짝이다.
        if _gaze_neg_pi:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + _gaze_neg_pi)
        # 의류 오색 (2026-10-15) — 고정 positive 와 짝이다.
        if _item_neg_pi:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + _item_neg_pi)
        # 사물 표면 소실·표백 회피어 (2026-10-16) — 위 표면 구조 고정과 짝이다.
        if _furn_surf_neg_pi:
            negative_text = (negative_text.rstrip("., ")
                             + ", " + _furn_surf_neg_pi)
        # (캐릭터 시트 negative 는 build_camera_negative(character_sheet=) 가
        # 두 상수를 이미 넣는다. 수동 병합은 중복. 2026-09-28 제거)
        try:
            # 시트 슬롯은 **언어 모델(vision) 에만** 넣고 VAE reference
            # latent 에서는 제외한다 — 그래야 diffusion 이 시트
            # 레이아웃(6뷰 배치)을 따라 그리지 않는다.
            # 왜(Why) 실측 2026-09-29: 시트를 reference 로 넣으면
            # 결과가 **시트 그대로** 렌더링됐다. 분리 실험으로 확정 —
            # 시트 없으면 항상 1인 정상, 시트 있으면 topic 에 장면을
            # 명시해도 4뷰. 프롬프트로는 이길 수 없다(pixel 힌트).
            # **약한 시트(3뷰 줄)도 합친다** (2026-10-19): 엄격 게이트를
            # 0.01 탈락한 삼면도가 지시("레이아웃을 복사하지 마")와 모순되게
            # latent 로 들어가고 있었다. 약한 슬롯은 이미 topic 시트 선언과
            # 교차한 것이므로(measure 조건) 여기서는 그대로 신뢰한다.
            _latent_skip_pi = list(set(_px_sheet_pi) | set(_weak_pi))
            prepared = self._prepare_qwen_image_data(
                image_items, vae=vae, latent_image=latent_image,
                latent_skip_labels=_latent_skip_pi
            )
        except Exception as exc:  # noqa: BLE001
            # reference 준비 실패해도 실행은 살린다 — 텍스트 전용으로 폴백.
            _log(f"[GoRi Camera Director Skills] reference 준비 실패, 텍스트 폴백: {exc}")
            prepared = ([], None)
        try:
            positive_out = self._qwen_image_edit_conditioning(
                clip, positive_text, prepared=prepared
            )
        except Exception as exc:  # noqa: BLE001
            # vision 인코딩 실패 시 텍스트만으로 재시도 (reference 없이도 동작).
            _log(f"[GoRi Camera Director Skills] vision 인코딩 실패, 텍스트 폴백: {exc}")
            positive_out = self._qwen_image_edit_conditioning(
                clip, positive_text, prepared=([], None)
            )
        # negative는 텍스트만 인코딩한다. 왜(Why): negative 문구는 카메라/영상
        # 실패 모드라 vision 참조가 불필요하고, 이미지 포함 인코딩을 반복하면
        # Qwen Vision 인코딩이 2회 실행 + reference_latents가 positive/negative
        # 양쪽에 첨부돼 KSampler가 reference를 이중 처리하기 때문이다.
        negative_cond = self._qwen_image_edit_conditioning(
            clip, negative_text, prepared=([], None)
        )
        negative_out = self._combine_conditioning(negative, negative_cond)
        if positive is not None:
            _log("[GoRi Camera Director Skills] positive conditioning 입력은 새 문자열 경로에서 무시됩니다. "
                 "프롬프트 재작성기의 positive_prompt 문자열을 prompt_in에 연결하세요.")
        _log("[GoRi Camera Director Skills] positive_out/negative_out/prompt_out 출력 "
              f"(single_encode={bool(external_prompt or positive is None)})")
        # image_out: 역할 계획(plan)이 선출한 주 reference 이미지를 그대로 통과.
        # I2V 시작 프레임·업스케일 등 후속 노드에 연결할 수 있다. 미연결이면 None.
        # 왜(Why): 항상 첫 연결을 통과하면(구버전) 첫 연결이 사물인 워크플로
        # (1번 핸드백 + 2번 여성)에서 핸드백이 나갔다(정밀 검토 발견 #5).
        last_labels = getattr(self, "_last_image_labels", None) or [l for l, _ in image_items]
        image_out = None
        main_slot = None
        main_img = None
        try:
            main_slot = _person_object_plan(
                external_prompt or (topic or ""), last_labels)["main"]
        except Exception:
            main_slot = None
        if image_items:
            # 주 슬롯 이미지는 image_out과 reference_latent_out이 **같은 픽셀**을
            # 써야 짝이 맞는다. 한 번만 찾고 두 출력에 함께 쓴다 (리뷰로 확인된 복붙).
            # 시트 슬롯은 여기서도 뺀다 (2026-10-21 결함 수정). README 5-6 은
            # "시트는 참조 latent 에서 뺀다" 고 약속하는데, 그 제외가 conditioning
            # 경로(_latent_skip_pi)에만 적용되고 image_out/reference_latent_out
            # 은 미필터 image_items 에서 main 을 골라 시트가 그대로 나갔다.
            # Qwen 은 참조 배치를 따라 그리므로 시트가 I2V 시작 프레임·3번 교정
            # 노드의 기준 latent 로 들어가면 결과가 여러 칸 시트로 나온다.
            # conditioning 과 같은 제외 집합을 쓴다(엄격 시트 + 약한 시트).
            _sheet_skip = set(str(x) for x in
                              (list(_px_sheet_pi) + list(_weak_pi)))
            for label, img in image_items:
                if str(label) in _sheet_skip:
                    continue
                if label == main_slot:
                    main_img = img
                    break
            if main_img is None:
                # main 이 시트로 제외됐으면 시트가 아닌 첫 슬롯으로 폴백한다.
                for label, img in image_items:
                    if str(label) not in _sheet_skip:
                        main_img = img
                        break
            image_out = main_img
        # 기준 latent 출력 (3번 교정 노드·샘플러 시작 latent 용). _prepare가 이미
        # 인코딩한 결과를 캐시 키로 조회만 한다 — 재인코딩 없음. vae 미연결이면 None.
        # 2026-10-24 재적용: 이 출력을 사용자 캔버스 H,W 로 맞추는 `_canvas_fit_latent`
        # (R215)를 다시 넣는다. 왜(Why) — 빠져 있는 동안 비율 위젯이 출력 크기를 정하지
        # 못하는 고장이 실측으로 재현됐다(79번 16:9 -> 1344x736 · 9:16 -> 736x1344 인데
        # 저장된 출력은 둘 다 736x1328 · 참조 사진 비율). 522a302 의 되돌림 근거였던
        # "비율을 바꾸니 같은 시드에서 그림이 달라졌다" 는 denoise=1.0 에서 **필연**이다
        # — 시작 latent 의 모양이 곧 시드이므로 비율을 바꾸면 그림이 바뀌는 것이 정상이다.
        # 대가(합의 2026-10-24): 비율을 바꾸면 같은 시드라도 그림이 바뀐다. 그 맞바꿈을
        # 사용자가 선택했다. 캔버스를 연결하지 않으면 같은 객체가 그대로 나간다(하위호환).
        reference_latent_out = None
        try:
            if vae is not None and main_img is not None:
                _tw, _th = CameraDirectorEncode._reference_target_size(latent_image, vae=vae)
                _cached = _qwen_ref_cache_get(
                    _qwen_ref_cache_key(main_img, _tw, _th, vae), vae)
                if _cached is not None and _cached[1] is not None:
                    reference_latent_out = CameraDirectorEncode._canvas_fit_latent(
                        {"samples": _cached[1]}, latent_image, vae=vae)
        except Exception as e:
            # 왜(Why) 말하나 (2026-10-07 라운드 2): 기준 latent 가 조용히
            # None 이 되면 3번 교정 노드가 "camera 기준 없음" 으로 죽고
            # 원인을 찾을 수 없다. 한 번만 말한다.
            _note_once("camera.ref_latent_lookup",
                       "[Camera Director] 기준 latent 조회 실패 — 캐시 키 계산"
                       "또는 이동 중 오류 (기준 latent 없이 진행): "
                       f"{type(e).__name__}: {str(e)[:80]}")
            reference_latent_out = None
        _release_vram()
        clear_reference_kinds()
        return (positive_out, negative_out, positive_text, image_out,
                reference_latent_out)



# ---------------------------------------------------------------------------
# Qwen reference conditioning 속도 최적화용 캐시/상한.
#
# 왜(Why): 같은 reference 이미지는 프롬프트를 바꿔도 매 실행마다
# common_upscale(lanczos) + vae.encode()를 반복했다. VAE encode 1회가
# 수초대라 반복 실행 체감 속도를 지배하므로, 내용 해시+목표 크기 키로
# 재사용한다.
# 크기 정책은 2026-10-23 부로 "참조 픽셀 수 = 입력 픽셀 수" 다 (사용자 판정).
# 2026-10-22 에 있던 위젯은 제거됐다 — 값의 출처가 입력이 됐기 때문이다.
# 이 상수는 이제 **입력이 없을 때(latent_image 미연결)만** 쓰는 폴백값이다.
# ---------------------------------------------------------------------------

QWEN_REF_MAX_PIXELS = 1024 * 1024  # 입력 미연결 시 reference 폴백 1MP


_QWEN_REF_CACHE: dict = {}


_QWEN_REF_CACHE_ORDER: list = []


# (왜) 12 인가 (2026-10-02 실측): 노드가 받는 참조 이미지는 `image_1` ~ `image_10`
# 으로 **최대 10장**(L4906-4915)인데 용량이 8 이었다. L4805 가 라벨 순서로
# 매 실행 순차 접근하므로, working set(10) > 용량(8) 이면 LRU 이 매 실행
# 전부 미스가 된다 — 순차 스캔은 LRU 최악 패턴이다. 측정한 계단:
#   1~8장  → 매 실행 0 encodes (정상 동작)
#   9장    → 매 실행 9/9 encodes  (적중률 0%)
#   10장   → 매 실행 10/10 encodes (적중률 0%)
# 즉 지원 설정 10개 중 2개에서 캐시가 영영 이득이 없다. 용량은 한 실행의
# 서로 다른 키 수(10) 이상이어야 한다. 여유 2칸은 이미지를 갈아끼운 직후의
# 혼합 구간용이다.
# (왜) 12 면 되는가: latent 는 put 에서 `.cpu()` 로 내려간다(L4695) — 그래서
# VRAM 이 아니라 시스템 RAM 을 쓴다. 1MP 기준 한 장 0.25MB, 12장 3MB.
# (왜) 무한대 는 아닌가: 키가 VAE weakref 로 검증되므로 죽은 VAE 항목은
# 걸러지지만, dict 는 자라기만 하므로 상한이 있어야 evict 규칙이 성립한다.
_QWEN_REF_CACHE_MAX = 12


_QWEN_REF_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# 실행 이력 전송 — GoRi 텔레메트리 허브 연동.
#
# 왜(Why): 실행 이력은 custom_nodes/ComfyUI_workflows_MY_data_save 허브에서
# 일원 관리한다(노드별 하위 폴더 분류). 노드는 파일에 직접 쓰지 않고 허브
# 서버 엔드포인트(POST /gori_telemetry/write)로 기록을 넘긴다.
#
# 개인정보/프라이버시 원칙 (사용자 요구, 2026-09-27):
#   - 모든 데이터는 로컬 허브의 data/ 안에만 저장된다. 외부 전송 없음.
#   - topic 원문은 전송하지 않는다(길이만 기록) — 내용 유출 표면 최소화.
#   - 전송은 백그라운드 스레드로 수행되며 실패해도 조용히 무시된다 —
#     노드 실행을 절대 막지 않는다.
# ---------------------------------------------------------------------------
TELEMETRY_URL = "http://127.0.0.1:8188/gori_telemetry/write"


_TELEMETRY_SENDER = None  # 테스트 주입 지점(None이면 표준 전송기 사용)


def _default_telemetry_sender(record: dict) -> None:
    """허브 엔드포인트로 실행 이력 전송. 실패해도 조용히 무시한다."""
    try:
        import urllib.request as _u
        req = _u.Request(
            TELEMETRY_URL,
            data=json.dumps(record, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        _u.urlopen(req, timeout=3).close()
    except Exception:
        pass


def _post_telemetry(**record) -> None:
    """실행 1회를 허브로 전송. 절대 노드 실행을 막지 않는다.

    왜(Why) 기본 꺼짐인가 (2026-10-02 실측): 매 실행마다 데몬 스레드 1개 +
    DNS(getaddrinfo 74ms) + 소켓을 쓰고 받는 서버가 없다. ComfyUI 로그에
    엔드포인트가 없고, 이 저장소에도 수신 코드가 없다. 켜려면
    `GORI_TELEMETRY=1` 환경변수를 둔다. 테스트 주입(`_TELEMETRY_SENDER`)은
    환경변수와 무관하게 항상 동작한다.
    """
    try:
        if _TELEMETRY_SENDER is None and os.environ.get("GORI_TELEMETRY", "0") != "1":
            return
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        record["node"] = "camera_director"
        if _TELEMETRY_SENDER is not None:
            _TELEMETRY_SENDER(record)  # 테스트: 동기 호출로 결정적 검증
        else:
            threading.Thread(target=_default_telemetry_sender,
                             args=(record,), daemon=True).start()
    except Exception:
        pass


def _thumb_digest(image, length: int = 16):
    """이미지 썸네일 sha1 공통 헬퍼. (shape, digest) 반환, 실패 시 (None, None).

    왜(Why): _thumb_sig와 _qwen_ref_cache_key가 동일한 축소+해시 블록을
    중복로 가지고 있어 한쪽만 수정되는 퇴행 위험이 있었다.
    (..., H, W, C) 형태의 ComfyUI IMAGE 텐서/배열을 전제로 한다.

    (왜) **블록 평균**인가, 점 샘플이 아닌가 (2026-10-02 실측): 이전에는
    `image[::h//16, ::w//16]` 로 **점**을 골랐다. 1024x1024 면 64px 간격이라
    샘플 사이 63x63 px 가 해시에서 사라진다. 실측 결과 8x8 워터마크 200개 중
    **199개(100%)가 해시를 못 바꿨다** — 1024px 이미지 위 8px 표식은 흔한
    작업이다. 캐시가 "바뀐 이미지에 옛 latent" 를 조용히 돌려주므로 캐시가
    없느니 나빴다. 오프셋 그리드 3장은 100% → 98%로effect가 거의 없었다
    (격자가 너무 성깁니다). 블록 평균(adaptive_avg_pool2d, 64x64)은 **0/200**.
    비용은 이미지당 약 1.4ms — VAE 인코딩 1회(수십~수백 ms)보다 작고,
    첫 캐시 적중에서 회수된다.
    (왜) 64 인가: 16/32/64 모두 0/200 이라 가장 싼 16 을 고르면 되지만,
    그물코가 촘촘할수록 국소 변경이 여러 셀에 걸려 더 안전하다. 64x64x3 =
    12KB 해시. 32 는 측정값이 같아도 여유를 두지 않았다 — 근거 없는 상수
    늘리기를 피했다.

    (왜) list 같은 입력도 해시를 얻나: 이전엔 실패해 `noid:{id(image)}`
    키로 내려갔고, CPython 은 GC 뒤 주소를 재배정한다(실측 299/300 = 100%).
    그 키로 서로 다른 입력이 같은 캐시 항목을 맞는다. numpy 로 한 번 더
    변환해 해시를 얻도록 했고, 이제 `noid` 로 내려가는 것은 shape 조회가
    불가능한 값(예: None)뿐이다.
    """
    try:
        import hashlib as _hl
        import numpy as _np
        import torch as _t
        import torch.nn.functional as _tf
        # (왜) shape 를 원본에서 읽지 않는가: list 를 넘기면 `.shape` 가 없어
        # 여기서 죽는다. numpy 로 먼저 바꿔야 list·numpy·tensor 가 한 갈래로
        # 합쳐진다 — 이전엔 list 가 `noid:` 키로 내려갔다.
        raw = image.detach().cpu() if hasattr(image, "detach") else image
        x = _np.asarray(raw, dtype=_np.float32)
        shape = tuple(int(d) for d in x.shape)
        if x.ndim == 4:
            x = x[0]
        if x.ndim != 3 or x.shape[0] < 4 or x.shape[1] < 4:
            if x.ndim < 3:
                # 3차원이 아닌 값(예: None, 스칼라)은 식별할 수 없다.
                return shape, None
            # 너무 작아 블록 평균이 불가능하면 있는 범위만 해시한다.
            return shape, _hl.sha1(_np.ascontiguousarray(
                x[:, :, :3]).tobytes()).hexdigest()[:length]
        t = _t.from_numpy(_np.ascontiguousarray(x[:, :, :3]))
        pooled = _tf.adaptive_avg_pool2d(
            t.permute(2, 0, 1)[None], (64, 64))[0]
        return shape, _hl.sha1(
            _np.ascontiguousarray(
                pooled.permute(1, 2, 0).numpy()).tobytes()
        ).hexdigest()[:length]
    except Exception:
        return None, None


def _thumb_sig(image) -> str:
    """이미지 내용 식별용 짧은 해시 (LLM 캐시 폴백 키용).

    왜(Why): base64 변환 실패 시 대체 키가 1번 이미지 수치에만 의존해
    2번 이후 교체가 캐시에 미반영되는 stale 문제가 있었기 때문이다.
    """
    _shape, digest = _thumb_digest(image, length=12)
    if digest:
        return digest
    # 왜(Why) id(object) 가 아니라 매번 새 키인가 (2026-10-07 라운드 2):
    # `noid:{id(image)}` 는 CPython 이 GC 뒤 주소를 재활용하면 서로 다른
    # 입력이 같은 캐시를 맞는다(실측 50회 중 35회 재사용). 식별을 못 했으면
    # **매번 새 키 = 항상 미스 = 재계산**이 정답이다 — 재계산은 틀리지 않는다.
    return f"noid:{uuid.uuid4().hex}"


def _qwen_ref_cache_key(image, target_w, target_h, vae) -> str:
    """reference 캐시 키: 내용 썸네일 해시 + 목표 크기 + VAE 식별자.

    규칙 (2026-10-23 실측 사고): **참조 결과를 바꾸는 입력은 전부 이 키에
    있어야 한다.** 빠지면 바뀐 입력으로 재실행해도 캐시에 먹혀 옛 참조가
    나간다 — 실측: 참조 크기 상한이 키에 없던 동안 상한 1.0 판과 0.25 판의
    출력이 픽셀까지 동일했다(maxAbs=0). 그래서 "참조를 키워도 비용이 안
    는다" 는 결론이 나왔고, 실측은 정반대였다(2배 = 3.4배 시간).
    참조 크기를 정하는 값(사진 내용 · 목표 크기 · VAE)은 지금 다 들어 있다.
    새 입력을 참조에 반영하려면 이 키에도 넣어야 한다 (R217 이 인코딩 횟수로
    잠근다).
    """
    shape, digest = _thumb_digest(image, length=16)
    if digest is None:
        # 식별 불가 — 새 키로 항상 미스시킨다(_thumb_sig 와 같은 이유:
        # id 재활용 충돌 방지). 캐시는 상한 12 로 정리된다.
        return f"noid:{uuid.uuid4().hex}|{target_w}x{target_h}|vae:{id(vae)}"
    return f"{shape}|{target_w}x{target_h}|vae:{id(vae)}|{digest}"


# 참조 캐시 조회 — VAE 는 weakref 로만 비교, 죽었으면 미스(재인코딩)
def _qwen_ref_cache_get(key, vae=None):
    with _QWEN_REF_LOCK:
        cached = _QWEN_REF_CACHE.get(key)
    if cached is None:
        return None
    rgb, latent, vae_ref = cached
    # 왜(Why): 캐시가 VAE 객체를 강한 참조로 들면 그 VAE가 ComfyUI에서
    # 영영 회수되지 않아 작업 끝난 뒤에도 VRAM을 붙잡는다. weakref로만
    # 동일성 비교에 쓴다. 죽은 VAE면 캐시 미스로 보고 재인코딩한다.
    try:
        if vae_ref() is None:
            # VAE가 회수됨 → 미스(재인코딩). 살아 있는 객체만 재사용한다.
            return None
        if vae_ref() is not vae:
            return None
    except TypeError:
        # weakref 불가 객체면 강한 참조로 되돌린다(동작 동일, 단 만료 안 됨).
        if vae_ref is not vae:
            return None
    if latent is not None:
        # 캐시는 CPU에 둔다. GPU 텐서를 상주시키면 empty_cache()로도 안 풀린다.
        # 조회할 때만 원래 VAE 디바이스로 되돌린다 (이동 비용 << VAE encode).
        _dev = getattr(vae, "device", None) if vae is not None else None
        if _dev is not None and hasattr(latent, "to"):
            try:
                latent = latent.to(_dev)
            except Exception:
                pass
    return rgb, latent


# 참조 캐시 저장 — CPU latent + VAE weakref 만 남겨 GPU/VRAM 상주를 막는다
def _qwen_ref_cache_put(key, value) -> None:
    rgb, latent, vae = value
    # 캐시에는 CPU latent + VAE weakref만 남긴다 (GPU 점유·VAE 상주 방지).
    if latent is not None and hasattr(latent, "cpu"):
        try:
            latent = latent.cpu()
        except Exception:
            pass
    try:
        vae_ref = weakref.ref(vae)
    except TypeError:
        vae_ref = vae
    with _QWEN_REF_LOCK:
        if key in _QWEN_REF_CACHE:
            _QWEN_REF_CACHE_ORDER.remove(key)
        _QWEN_REF_CACHE[key] = (rgb, latent, vae_ref)
        _QWEN_REF_CACHE_ORDER.append(key)
        while len(_QWEN_REF_CACHE_ORDER) > _QWEN_REF_CACHE_MAX:
            _QWEN_REF_CACHE.pop(_QWEN_REF_CACHE_ORDER.pop(0), None)


def clear_qwen_ref_cache() -> None:
    """reference 캐시 비우기 (테스트/디버그용)."""
    with _QWEN_REF_LOCK:
        _QWEN_REF_CACHE.clear()
        _QWEN_REF_CACHE_ORDER.clear()
