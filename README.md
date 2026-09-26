# ComfyUI_GoRi_custom_nodes

GoRi(권혁달) 제작 ComfyUI 커스텀 노드 통합 배포 저장소입니다.

## 포함된 노드

| 노드 | 설명 | 설치 폴더 |
|---|---|---|
| [GoRi Camera Director](./GoRi-Camera-Director) | 주제(한글 OK) + 레퍼런스 이미지 → 카메라 연출이 포함된 영문 프롬프트·conditioning 출력 (Qwen Image Edit 경로) | `GoRi-Camera-Director/` |

## 설치 방법

1. 원하는 노드 폴더 전체를 ComfyUI의 `custom_nodes/` 안으로 복사합니다.
   ```
   ComfyUI/custom_nodes/GoRi-Camera-Director/
   ```
2. ComfyUI를 재시작합니다.
3. 노드 검색에서 `(GoRi)` 접두어로 찾을 수 있습니다. 자세한 사용법은 각 노드 폴더의 README를 참고하세요.

> 통합 저장소 전체를 `custom_nodes/`에 통째로 복사하면 ComfyUI가 하위 노드를
> 인식하지 못합니다. 반드시 **노드 폴더 단위**로 복사하세요.

## 노드 추가 / 업로드 규칙 (기여자·AI 에이전트용)

1. 노드마다 최상위 폴더 하나를 만듭니다 (`GoRi-<노드이름>/`).
2. 폴더 안에 노드 코드와 README(설치·사용법·입출력 설명)를 포함합니다.
3. 테스트가 있으면 푸시 전에 로컬에서 먼저 통과시킵니다 (GitHub Actions CI도 각 push마다 실행).
4. API 키 등 시크릿은 절대 커밋하지 않습니다.

## CI

`.github/workflows/ci.yml` — 각 노드 폴더의 `tests/` 내 테스트를 Python 3.10/3.12에서 자동 실행합니다.

## 라이선스

MIT License — [LICENSE](./LICENSE)
