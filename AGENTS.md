# AGENTS.md — 이 저장소에서 작업하는 모든 AI 를 위한 규칙

이 파일은 저장소 루트의 `AGENTS.md` 이며, 이 폴더에서 코딩하는 모든 AI 가 자동으로 읽습니다.

## 0. 가장 중요한 규칙 하나

**작업을 시작하기 전에 `WORK_STATUS.md` 를 읽고, 작업이 바뀌면 그 파일을 갱신하십시오.**

`WORK_STATUS.md` 는 이 저장소의 단일 진실 원천입니다. 그 안에 이미 기록된 것들:

- 카메라 디렉터와 키퍼는 **항상 세트로** 동작한다
- 이 워크플로에서 `switch=true` 와 `denoise=1.0` 이 **옳은 값**이며, 바꾸면 결과물이 무너진다
- 미해결 문제 3건과 각각의 실측 수치
- 이 폴더에서 이미 밸아본 함정 7가지 (한글 경로, LoadImage 하위 폴더, 시트 오탐 임계값 등)
- 테스트 하네스가 워크플로에 덧대는 배선과 그 사유

컨텍스트가 길어지면 이 문서가 없으면 같은 실수를 반복합니다. 한 페이지에서 오래 작업하지
마시고, 상태를 여기에 적어두면 새 세션에서 바로 이어갈 수 있습니다.

갱신을 **강제**한다. 커밋 게이트(pre-commit 훅)가 두 문서를 검사합니다:

```bash
install_hook.bat          # clone 맨 처음 1회 실행
git commit --no-verify    # 진짜 문서 갱신이 불필요하다고 판단될 때만
```

| 규칙 | 조건 | 필요한 것 |
|---|---|---|
| 1 | `.py` 를 stage 함 | `WORK_STATUS.md` 를 함께 stage |
| 2 | **키퍼 폴더**의 `.py` 를 stage 함 | `Keeper_Logic.md` 가 코드보다 최신이어야 함 |
| 2 | **카메라 폴더**의 `.py` 를 stage 함 | `camera_Logic.md` 가 코드보다 최신이어야 함 |

테스트 하네스는 이 저장소가 아니라 별도 저장소에 있습니다:
`Documents\개발\coding skills\My_Jev_Browser_harness_skills\examples\comfyui-gori\`

**새 노드를 만들면 세 단계를 따라야 규칙 2 에 걸립니다:**
① `<노드이름>_Logic.md` 작성 ② `.gitignore` 에 추가 ③ 훅에 폴더↔문서 짝 추가.

`Keeper_Logic.md` / `camera_Logic.md` / `Harness_Logic.md` 는 각 코드의
함수·상수·판정 근거를 한국어로 풀어쓴 **개인 해설서**입니다. 함수를 추가·고치면
그 함수의 설명과 상수표도 같이 고쳐야 합니다. 문서가 코드를 안 따라가면
누군가 그 문서를 믿고 시간만 날립니다.

**주의**: 이 문서들은 `.gitignore` 된 개인 파일이라 커밋에 실리지 않습니다.
그래서 게이트는 stage 여부가 아니라 **수정 시각**으로 신선도를 봅니다.
없으면(새 clone) 해당 규칙은 아예 적용되지 않습니다.

## 1. 작업 규칙

1. **실측 전에 추측으로 원인을 쓰지 않는다.** 이 저장소의 "미해결" 항목 대부분은
   추측이 틀렸던 결과입니다(denoise, switch, 시트 판정 모두). 로그·픽셀·숫자로 먼저
   확인하고 그 사실을 문서에 적으십시오.
2. **테스트는 `run_tests.bat` 으로만 돌린다.** 다른 인터프리터는 mediapipe 가 없고
   torch 도 CPU 전용이라 GPU 경로를 검증하지 못합니다.
3. **Jev 게이트를 통과해야 푸시한다.** `jev-pref.json` 이 있으므로 자동으로 걸립니다.
   `exit=2` 는 판정이 아니라 요청 예산 초과입니다 — 미추적 파일이 포함되면 난으니
   `--include` 로 좁히십시오.
4. **푸시는 사용자의 명시적 승인이 있을 때만.** commit 은 해도 되지만, 모호한 답변("응",
   "ㅇㅋ")으로는 push 하지 않습니다.
5. **커밋은 `run_tests.bat` 통과 후에만.** 메시지는 무엇을 고쳤는지 사실로 씁니다
   (BOM 없는 UTF-8, 첫 줄이 요약).

## 2. 이 저장소에서 반드시 조심할 것

```
한글이 든 경로              cmd.exe 가 읽지 못해 스크립트가 조용히 실패한다.
                            파이썬이 직접 os.listdir 로 열거하십시오.
PowerShell 콘솔이 cp949     Get-ChildItem 출력의 한글이 깨진다.
                            열거는 파이썬으로, 출력은 UTF-8 로.
LoadImage 하위 폴더 미지원   nodes.py:1750 이 input/ 최상위만 훑는다.
                            하위 폴더는 하드링크(input/kt_*)로 노출했다.
                            사용자가 정리하면 다시 만들어야 한다.
시트 감지 임계값             캐릭터 시트만 T, 일반 사진은 절대 T 가 되면 안 된다.
                            수정 후 반드시 8개 크기 × 13장으로 검증한다.
비ASCII 를 print()          Windows 콘솔에서 프로세스가 죽는다.
                            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BOM 저장                    .bat / .py 첫 줄이 깨진다. BOM 없이 저장.
외부 API 호출               지침상 금지. 카메라 노드의 LLM 경로는 api_key 가 비면
                            openrouter 로 요청해서 401 을 받고 45초를 날린다.
                            automation 을 로컬(규칙) 판단으로 유지하십시오.
```

## 3. 구조

```
ComfyUI-GoRi-camera-director/       카메라 디렉터 (프롬프트·구도 지시 + 기준 latent)
Comfyui-GoRi-Consistency-Keeper/   일관성 키퍼 (2차 패스로 신원·구도 복원)
tests/                             공용 테스트
tools/                             워크플로→API 변환기 (미추적)
jev-pref.json                      저장소별 Jev 의미 규칙
run_tests.bat                      테스트 실행기 (ComfyUI 내장 Python 3.12)
WORK_STATUS.md                     진행상황 문서 ← 반드시 읽고 갱신
```

자세한 진행상황과 미해결 문제, 실측 수치는 `WORK_STATUS.md` 를 보십시오.
