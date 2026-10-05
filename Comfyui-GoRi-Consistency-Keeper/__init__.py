# -*- coding: utf-8 -*-
"""ComfyUI_GoRi_custom_nodes 의 GoRi-Consistency-Keeper — ComfyUI 커스텀 노드 등록.

설치: 이 폴더(Comfyui-GoRi-Consistency-Keeper)를 ComfyUI/custom_nodes/에 복사 후 재시작.
의존성: torch·numpy (ComfyUI 환경에 이미 있음). mediapipe 는 선택 의존이라
       없으면 인체 마스크·부위별 복원·포즈 프레이밍이 꺼지며, 그 이유를
       콘솔에 한 번 알린다.
"""

try:
    from .consistency_keeper import GoRiConsistencyKeeper
    from .consistency_keeper import __version__
except ImportError:
    # 단독 실행(테스트)이면 상대 임포트가 안 되므로 절대 임포트로 폴백한다.
    # 단, 모듈 **내부**에서 난 ImportError 까지 삼키면 원인 없는
    # ImportError 로 보인다(그리고 클래스 객체가 두 개 생긴다).
    # 그래서 폴백이 실제로 성공했는지 확인한다.
    from consistency_keeper import GoRiConsistencyKeeper
    from consistency_keeper import __version__

# 로드 시 버전을 남긴다. 여러 노드가 섞여 있을 때 어느 버전이 떴는지
# 로그로 알 수 있다.
try:
    print("[GoRi] Consistency Keeper v%s loaded" % (__version__,), flush=True)
except Exception:
    pass

NODE_CLASS_MAPPINGS = {
    "GoRi_ConsistencyKeeper": GoRiConsistencyKeeper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoRi_ConsistencyKeeper": "(GoRi) Consistency Keeper",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "__version__"]
