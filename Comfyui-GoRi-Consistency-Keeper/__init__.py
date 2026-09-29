# -*- coding: utf-8 -*-
"""ComfyUI_GoRi_custom_nodes 의 GoRi-Consistency-Keeper — ComfyUI 커스텀 노드 등록.

설치: 이 폴더(GoRi-Consistency-Keeper)를 ComfyUI/custom_nodes/에 복사 후 재시작.
의존성: torch·numpy (ComfyUI 환경에 이미 있음). mediapipe 는 선택 의존이라
       없으면 인체 마스크·부위별 복원만 조용히 꺼진다.
"""

try:
    from .consistency_keeper import GoRiConsistencyKeeper
except ImportError:
    # 단독 실행(테스트)이면 상대 임포트가 안 되므로 절대 임포트로 폴백한다.
    # 단, 모듈 **내부**에서 난 ImportError 까지 삼키면 원인 없는
    # ImportError 로 보인다(그리고 클래스 객체가 두 개 생긴다).
    # 그래서 폴백이 실제로 성공했는지 확인한다.
    from consistency_keeper import GoRiConsistencyKeeper

NODE_CLASS_MAPPINGS = {
    "GoRi_ConsistencyKeeper": GoRiConsistencyKeeper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoRi_ConsistencyKeeper": "(GoRi) Consistency Keeper",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
