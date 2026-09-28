# -*- coding: utf-8 -*-
"""Comfyui-Consistency-Keeper — ComfyUI 커스텀 노드 등록.

설치: 이 폴더(Comfyui-Consistency-Keeper)를 ComfyUI/custom_nodes/에 복사 후 재시작.
의존성: 외부 pip 패키지 없음 (ComfyUI 환경의 torch만 사용).
"""

try:
    from .consistency_keeper import GoRiConsistencyKeeper
except ImportError:  # 단독 실행(테스트) 시 상대 임포트 폴백
    from consistency_keeper import GoRiConsistencyKeeper

NODE_CLASS_MAPPINGS = {
    "GoRi_ConsistencyKeeper": GoRiConsistencyKeeper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoRi_ConsistencyKeeper": "(GoRi) Consistency Keeper",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
