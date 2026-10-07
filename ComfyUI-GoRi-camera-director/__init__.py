# -*- coding: utf-8 -*-
"""comfyui-GoRi-camera-director — ComfyUI 커스텀 노드 등록.

설치: 이 폴더(comfyui-GoRi-camera-director)를 ComfyUI/custom_nodes/에 복사 후 재시작.
의존성: 외부 pip 패키지 없이 실행되며, vision 입력 변환에는 ComfyUI 환경의 PIL/torch/numpy를 사용한다.
"""

from .camera_director import CameraDirectorEncode
from .camera_director import __version__

# 로드 시 버전을 남긴다. 여러 노드가 섞여 있을 때 어느 버전이 떴는지
# 로그로 알 수 있다. 로드 시점에는 로거가 아직 준비되지 않을 수 있어
# print 로 쓰고, 콘솔 인코딩 문제로 실패해도 노드 등록은 막지 않는다.
try:
    print("[GoRi] Camera Director v%s loaded" % (__version__,), flush=True)
except Exception:
    pass

# 사용자에게 노출되는 노드는 하나뿐이다.
# CameraDirector는 내부 계산/테스트 호환용 베이스 클래스로 남겨 둔다.
NODE_CLASS_MAPPINGS = {
    "GoRi_CameraDirectorEncodeSkills": CameraDirectorEncode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoRi_CameraDirectorEncodeSkills": "(GoRi) Camera Director Skills",
}

# 프론트엔드 확장: image_2~10 단자를 연결 개수에 맞춰 점진적으로 공개.
# 프론트엔드 1.52.x는 소켓 hidden 플래그를 무시하므로, 동적 소켓 API
# (removeInput/addInput)로 구현. 제거·재추가는 항상 맨 뒤(미연결) 소켓만
# 다루므로 기존 링크와 워크플로 호환성이 유지된다.
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY",
           "__version__"]
