# -*- coding: utf-8 -*-
"""comfyui-GoRi-camera-director — ComfyUI 커스텀 노드 등록.

설치: 이 폴더(comfyui-GoRi-camera-director)를 ComfyUI/custom_nodes/에 복사 후 재시작.
의존성: 외부 pip 패키지 없이 실행되며, vision 입력 변환에는 ComfyUI 환경의 PIL/torch/numpy를 사용한다.
"""

from .camera_director import CameraDirectorEncode

# 사용자에게 노출되는 노드는 하나뿐이다.
# CameraDirector는 내부 계산/테스트 호환용 베이스 클래스로 남겨 둔다.
NODE_CLASS_MAPPINGS = {
    "GoRi_CameraDirectorEncodeSkills": CameraDirectorEncode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GoRi_CameraDirectorEncodeSkills": "(GoRi) Camera Director Skills",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
