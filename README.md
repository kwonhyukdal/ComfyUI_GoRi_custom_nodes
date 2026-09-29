# ComfyUI_GoRi_custom_nodes

> ☕ 도움이 됐다면 커피 한 잔: [PayPal로 후원하기](https://paypal.me/GoRi57788)

GoRi 제작 ComfyUI 커스텀 노드 통합 배포 저장소입니다.

## 포함된 노드

| 노드 | 설명 | 설치 폴더 |
|---|---|---|
| [GoRi Camera Director](./GoRi-Camera-Director) | 주제(한글 OK) + 레퍼런스 이미지 → 카메라 연출이 포함된 영문 프롬프트·conditioning 출력 — **Qwen-Image 2.1 완전 지원**, KREA 2·MiniMax H3 프롬프트로도 활용 가능 | `GoRi-Camera-Director/` |
| [GoRi Consistency Keeper](./GoRi-Consistency-Keeper) | 샘플러가 뽑은 latent를 원본·카메라 기준 latent 쪽으로 당겨 신원·구도 틀어짐을 줄이는 2차 패스 — 재인코딩·재샘플링 없음 | `GoRi-Consistency-Keeper/` |

## 설치 방법

**방법 A — ComfyUI Manager / 통째로 설치 (권장)**

ComfyUI Manager에서 `GoRi Custom Nodes`를 검색해 설치하거나, 저장소 전체를 `custom_nodes/`에 복사합니다. 루트 로더가 하위 노드를 모두 자동 등록합니다.
```
ComfyUI/custom_nodes/ComfyUI_GoRi_custom_nodes/
```

**방법 B — 개별 노드 폴더 복사**

원하는 노드 폴더만 골라 복사해도 각 폴더의 `__init__.py`가 직접 로드됩니다.
```
ComfyUI/custom_nodes/GoRi-Consistency-Keeper/
```

설치 후 ComfyUI를 재시작합니다. 노드 검색에서 `(GoRi)` 접두어로 찾을 수 있습니다. 자세한 사용법은 각 노드 폴더의 README를 참고하세요.

> 방법 B로 단독 복사 시 통합 루트 로더는 사용되지 않습니다. 전체 복사(방법 A)와
> 단독 복사(방법 B) 어느 쪽이든 두 방식은 서로 충돌하지 않습니다.

## 운영체제 지원

**Windows 11 / macOS (Intel·Apple Silicon) / Linux — 세 OS 모두 CI로 검증됩니다.**

| | Windows | macOS | Linux |
|---|---|---|---|
| ComfyUI 실행 | ✅ | ✅ | ✅ |
| Camera Director | ✅ | ✅ | ✅ |
| Consistency Keeper | ✅ | ✅ | ✅ |
| API 키 `.env` 저장 | ✅ | ✅ (권한 600) | ✅ (권한 600) |

- 외부 pip 패키지 없이 실행됩니다. `torch`·`numpy`·`PIL`은 ComfyUI가 이미
  가지고 있는 것만 사용합니다.
- macOS Apple Silicon(M1/M2/M3)은 `mediapipe` 휠이 없어 **인체 마스크와
  포즈 기반 기능이 자동으로 꺼집니다.** 나머지 기능(참조 이미지 픽셀 분석,
  조명·공간 흐름, 부위별 에지 대조, 캐릭터 시트 패널 검출)은 전부
  `torch`/`numpy`만 써서 **그대로 동작**합니다. 조용히 꺼질 뿐 실패하지
  않습니다.
- 경로 처리는 전부 `os.path` 기반이라 Windows 백슬래시와 macOS/Linux 슬래시
  모두에서 동일하게 동작합니다. 심볼릭 링크로 설치한 경우도 지원합니다.
- GPU는 CUDA(NVIDIA)·MPS(Apple Silicon)·CPU 모두에서 실행됩니다.

> GPU가 없는 환경에서도 예외 없이 **느리게** 동작합니다. 다만 실제 이미지
> 생성 모델(Qwen 등) 자체가 GPU를 요구하므로, 생성 단계에는 GPU 환경이
> 필요합니다.

## CI

`.github/workflows/ci.yml` — 각 노드 폴더의 `tests/` 내 테스트를
**Windows·macOS·Linux × Python 3.10/3.12** 조합(총 6)에서 자동 실행합니다.
세 OS 매트릭스는 2026-09-28에 추가됐고, 그 자리에서 심볼릭 링크 경로 버그가
발견·수정됐습니다.

## 라이선스

MIT License — [LICENSE](./LICENSE)
