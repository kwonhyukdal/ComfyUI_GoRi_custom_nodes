# 작업 진행상황 (WORK STATUS)

> **이 문서는 이 저장소의 단일 진실 원천(single source of truth)입니다.**
> 어떤 AI가 이 폴더에서 작업을 시작하면 **반드시 이 파일을 먼저 읽고**, 작업을 진행하면서
> **갱신해야** 합니다. 컨텍스트가 길어지면 실제로 오판이 발생합니다. 이 파일이 그 방어선입니다.
>
> 마지막 갱신: 2026-10-01
> 현재 브랜치: `fix/audit-2026-09-30` (origin과 동기화됨, `origin/main`보다 9커밋 앞섬)

---

## 1. 이 저장소가 무엇인가

ComfyUI 커스텀 노드 3종이 **하나의 클론**에 들어 있다 (`custom_nodes` 아래, 개발은 여기서 진행).

| 폴더 | 역할 |
|---|---|
| `ComfyUI-GoRi-camera-director/` | 카메라 디렉터. 프롬프트/조명/구도 지시 + 기준 이미지의 VAE latent 제공 |
| `Comfyui-GoRi-Consistency-Keeper/` | 일관성 키퍼. 샘플러 결과를 기준 latent 쪽으로 당겨 신원·구도 틀어짐을 줄이는 2차 패스 |
| `tests/` | 공용 테스트 |
| `tools/` | (미추적) UI 워크플로→API 변환기 및 실행기. 아래 6절 참조 |
| `AGENTS.md` | 이 폴더에서 코딩하는 모든 AI 가 자동으로 읽는 작업 규칙 |
| `jev-pref.json` | 저장소별 Jev 의미 규칙. **있으면 게이트가 자동 동작** |
| `run_tests.bat` | 테스트 실행기. ComfyUI 내장 Python 3.12로 돌린다 |
| `install_hook.bat` | 커밋 게이트 설치 (clone 맨 처음 1회) |
| `Keeper_Logic.md` | **(개인, gitignore 됨)** 키퍼 로직 전체 해설. 위치를 아는 사람이 쓴다 |

카메라 디렉터와 키퍼는 **항상 세트로 함께** 쓰인다. 카메라만 있으면 키퍼가 기준을 못 받고,
키퍼만 있으면 카메라 연출이 없다.

---

## 2. 반드시 지켜야 할 설계 결정 (깨우면 되돌리기 어렵다)

### 2-1. 세 latent 의 역할 구분
```
original_latent  리사이즈·VAE 인코딩된 **고정된 DNA 정답지**
camera_latent    카메라가 sampler 에 전달한 **연출 의도**
sampled_latent   sampler 가 재해석한 **실제 발생 결과**
```
키퍼는演出은 유지하면서 **sampler 가 잃은 원본 DNA 만 복원**한다.
`detail_boost` 의 조건 대상은 변하는 `sampled` 다. 고정 `original` 이 "동적"인 게 아니다.

### 2-2. 시트 2단계 (사용자 승인 완료)
- 게이트 통과 시: 최상위 패널을 기준 원본으로 사용 + 강도 50% 감쇠
- 게이트 실패 시: 강도 0.50 → 0.25

### 2-3. 워크플로의 두 가지 규칙 (실측으로 확정)
- `ComfySwitchNode.switch = true` 가 **Qwen Edit 정석 경로**다. 기준 이미지는
  `latent_image` 가 아니라 `TextEncodeQwenImage21.images` **조건부**로 들어간다.
  `false` 로 바꾸면 기준 latent 를 시작점으로 써 버려 결과가 무너진다.
- `KSampler.denoise` 는 **1.0 이 맞다.** 8스텝 증류 LoRA 는 부분 denoise 를 못 견딘다.
  0.5 로 낮추면 **텍스처 노이즈만 가득한 이미지**가 나온다 (실측).
  카메라 노드가 "0.6~0.8 권장"이라고 경고하지만, 그건 `pf_*` 프리필터 쪽 이야기다.

---

## 3. 완료된 작업

### 3-1. 키퍼 (Consistency Keeper)
- 포즈 경로 전체가 실행된 적 없었음 → 3중 버그 수정 (`4ed3297`)
  - `BaseOptions` import 가 하드코딩 경로 하나였음
  - `output_segmentation_masks=True` 네이티브 `SIGABRT` → ComfyUI 서버가 죽던 버그, 제거
  - Qwen VAE 의 `(B,H,W,4)` 출력을 3채널 HWC 로 정규화하지 못해 포즈가 전부 실패
- 인체 마스크를 33점 landmark 기반(mediapipe segmentation 아님)으로 교체
- 마스크 튜닝: 커버 74.56% → 57.32% (실제 인물만 선택)
- 조용한 실패 4곳에 1회 로그, 진단 불가 구간 3곳에 로그 추가
- VRAM 해상도 상한 + 포즈 놓칠 때만 크게 재디코드 (`f32c398`, `f7e703c`)
- 0×0 / 1×1 이미지의 mediapipe 네이티브 진입 차단

### 3-2. 카메라 디렉터 (`ce2109b` — 최신)
한 장짜리 사진이 캐릭터 시트로 오판되어 **기준 latent 를 의도적으로 withheld** → 키퍼가
"camera 기준 없음" 으로 죽었다. 원인 2가지:

1. `_sheet_normalize` 가 **해상도 의존적**이었다. 주석은 "크기 무관하게 동작한다"고
   적혀 있었으나 정수 나눗셈(`max//512`) 양자화로 정규화 크기가 1.5배 흔들렸다.
   ```
   1019x1544 → 514x339  시트로 판정
    995x1508 → 754x497  정상 판정
   ```
   → 최대 변을 정확히 512 로 맞춤. 정규화 크기가 종횡비만의 함수가 됨.
2. **문틀 3개(문/사람/문)** 가 등간격 세로 3구조로 시트에 걸렸다.
   실측: 진짜 시트는 `n=4`, 오탐은 `n=3`. `sim` 은 0.243 vs 0.263 으로 겹쳐서
   손댈 수 없다(시트3 깨짐) → `_SHEET_MIN_PANELS` 3→4.

효과: `camera 기준 없음` → `camera 틀어짐 MSE=5.72 당김 0.33`

---

## 4. 지금 상태: 검증 결과

```
전체 스위트   카메라 1025 / 키퍼 262 / 팩 16  — FAIL 0, exit 0
Jev 게이트    approve (exit 0)
시트 판정     13장 × 8개 캔버스 크기 — 자세 10장 전부 정상, 시트 3장 전부 검출
```

**테스트 환경**
```
입력   ComfyUI/input/keeper test input          13장
출력   ComfyUI/output/keeper test output        생성물 저장 위치
컴피   0.37.0 / Python 3.12.10 / RTX 3080 10GB
속도   34~66초 / 장 (8스텝, 1024px 근처)
```

---

## 5. 미해결 (이것이 다음 일)

### 5-1. 프레이밍 감쇠가 강도를 0으로 누른다 — **블로커**
```
[GoRi Consistency Keeper] camera   틀어짐 MSE=5.72  → 감쇠 0.33→0.00
[GoRi Consistency Keeper] original 틀어짐 MSE=14.33 → 감쇠 0.33→0.00
```
결과물은 원본과 거의 같은데도 불일치가 크다. **MSE 기준선의 근거를 재검토해야 한다.**
이게 해결되기 전에는 strength 스윕이 무의미하다(몇 값을 넣든 결과물이 같다).

### 5-2. 의상 교체가 일어나지 않는다
프롬프트에 "다른 옷으로 교체"를 넣어도 같은 니트가 나온다. 이미지가 너무 강하게 반영된다.
교체가 일어나려면 어느 방향으로 손을 대야 할지 미결.

### 5-3. 카메라 노드가 외부 LLM 을 호출하려 한다
```
[Camera Director] LLM 호출 실패: HTTP 401 "No cookie auth credentials found"
   provider=Custom (OpenAI 호환) / model=space-bunny-alpha
   → https://openrouter.ai/api/v1 로 외부 요청 후 실패, 회당 45초 낭비
```
워크플로에 `automation="AI 판단 (llm)"` + 빈 api_key 로 남아 있으면 매 실행 실패한다.
사용자가 `automation` 을 **규칙 오토**로 변경함. LLM 을 쓰지 않는 쪽이 안전하다.

---

## 6. 테스트 하네스 (`tools/`, 미추적)

UI 워크플로(`Qwen Image 2.1.json`)를 API 형식으로 바꿔 컴피에 넣는 도구.
**ComfyUI 는 UI 형식을 받지 않는다** — 프런트엔드만 변환할 수 있어서 직접 변환해야 한다.

| 파일 | 역할 |
|---|---|
| `tools/wf_to_api.py` | UI(nodes+links) → API 형식. 우회 노드(mode=4) 해석, 위젯 배치 탐색 |
| `tools/run_keeper.py` | 지정 이미지 + strength 로 생성하고 결과 저장 |

**변환기에서 잡은 실제 버그 (모두 조용히 실패하던 것)**
```
링크 노드ID 가 정수      → KeyError, 그래프 전체 무실행
우회된 LoadImage 참조    → 끊어야 하는데 남아 KeyError
ResizeImageMaskNode 6개  → 검증 실패 → 하위 전부 "Output will be ignored"
위젯 순서 밀림           → KSampler steps='fixed', 카메라 api_key 에 base_url
```

**하네스가 워크플로에 덧대는 배선 (전부 주석에 사유 있음)**
```
node9.prompt          ← 의상 교체 프롬프트 직접 주입
node160.switch        = true   유지 (Qwen Edit 정석)
node283.original_latent ← node9 출력 2 (스위치는 빈 캔버스를 내므로)
node9.images.image_1  ← node143 (ImageScaleToTotalPixels)
node285.image_1       ← node143
node285.prompt_in     제거 (있으면 single_encode 모드가 되고 기준 latent 가 안 나온다)
node14.width/height   ← 기준 이미지의 종횡비로 계산 (1024x1024 정사각이면 인물이 통째로 바뀜)
node900 추가          ← SaveImage. 워크플로의 SaveImage(93)는 mode=4 로 우회돼 있음
```

**주의**: `tools/` 는 아직 커밋하지 않았다. 이 문서를 커밋할 때 포함할지 결정 필요.

**미추적 파일이 Jev 를 막는다 (실측).** `jev-pref` 의 요청 예산이 20,000자로,
`tools/` 같은 미추적 파일이 섞이면 `review-error: whole diff (N chars) exceeds...`
로 **exit=2** 가 난다. 이건 판정이 아니다. `--include` 로 좁히거나
미추적 파일을 stage 에서 내리면 통과한다.

**저장소 루트 문서 두 개 (2026-10-01 추가)**
```
AGENTS.md        모든 AI 가 자동으로 읽는 작업 규칙. "작업 전 WORK_STATUS.md 읽고,
                 작업 후 갱신하라" 를 강제한다. 없으면 AI 는 맥락을 새로 짠다.
WORK_STATUS.md   진행상황·설계 결정·미해결·실측 수치의 단일 진실 원천.
```

### 6-1. 커밋 게이트 (pre-commit 훅)

`AGENTS.md` 가 "갱신하라"고 말해도 규칙은 지키고 싶을 때만 지켜진다. 그래서 훅으로 강제한다.

```
설치        install_hook.bat 실행 (clone 마다 1회)
규칙 1      .py 가 stage 면 WORK_STATUS.md 도 stage 되어야 커밋 통과
규칙 2      키퍼 폴더의 .py 가 stage 면 Keeper_Logic.md 가 코드보다 최신이어야 통과
무시        git commit --no-verify   ← 의도적으로 우회할 때
```
`.git/hooks` 는 git 이 추적하지 않아 fresh clone 에는 훅이 없다 → `install_hook.bat` 필요.

**`Keeper_Logic.md` 는 개인 문서라 gitignore 로 저장소에서 뺐다.**
stage 대상이 아니므로 규칙 2 는 **수정 시각**으로 신선도를 잰다.
문서가 없으면(fresh clone) 규칙 2 는 적용되지 않는다 — 아무도 안 가진 파일에
게이트를 걸면 결국 우회당하기 때문이다.

**검증 완료 (실측 5케이스)**
```
.py 만 stage                          → 차단 (exit 1)  ✅
WORK_STATUS + 키퍼 .py (문서가 오래됨) → 차단 (exit 1)  ✅
WORK_STATUS + 키퍼 .py (문서가 최신)   → 통과 (exit 0)  ✅
WORK_STATUS + 문서 없음 + 키퍼 .py    → 통과 (exit 0)  ✅ 규칙2 미적용
git commit --no-verify                → 통과 (exit 0)  ✅
```

---

## 7. AI 가 이 저장소에서 작업할 때의 규칙

1. **작업을 시작하기 전에 이 파일을 먼저 읽는다.** 아래 8절의 경고 사항이 전부 여기 있다.
2. **작업이 바뀌면 이 파일을 갱신한다** (3·5절 특히). 커밋과 함께.
3. **테스트는 `run_tests.bat`** 로 돌린다. 다른 인터프리터로 돌리지 않는다
   (3.14 에는 mediapipe 가 없고 torch 도 CPU 전용이라 GPU 경로를 못 검증한다).
4. **실측 전에 추측으로 원인을 쓰지 않는다.** 이 문서의 "미해결" 항목 대부분은
   추측이 틀렸던 결과다. 로그·픽셀·숫자로 먼저 확인한다.
5. **Jev 게이트를 통과해야 푸시한다.** `jev-pref.json` 이 있으니 자동으로 걸린다.
   `exit=2` 는 판정이 아니라 예산 초과다 — `tools/` 등 미추적 파일이 포함되면 난다.
6. **푸시는 사용자의 명시적 승인이 있을 때만.** commit 은 해도 되지만 push 는 금지.
7. **한 페이지에서 오래 작업하지 않는다.** 컨텍스트가 길어지면 실제로 오판이 발생한다.
   이 문서가 그 방어선이므로, 상태를 여기에 적어두면 새 세션에서 바로 이어갈 수 있다.

### 이 폴더에서 반드시 조심할 것

```
경로에 한글이 있다          cmd.exe 가 경로를 못 읽어 스크립트가 조용히 실패한다.
                            파이썬이 직접 os.listdir 로 열거할 것.
PowerShell 콘솔이 cp949     Get-ChildItem 출력의 한글이 깨진다.
                            열거는 파이썬으로, 출력은 UTF-8 로.
LoadImage 가 하위 폴더를 못 읽음  nodes.py:1750 — input/ 최상위만 훑는다.
                            하위 폴더 이미지는 하드링크(input/kt_*)로 노출했다.
                            사용자가 정리하면 다시 만들어야 한다.
시트 감지阈值               캐릭터 시트만 T, 일반 사진은 절대 T 가 되면 안 된다.
                            수정 후 반드시 8개 크기 × 13장으로 검증한다.
비ASCII 를 print()          Windows 콘솔에서 프로세스가 죽는다.
                            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BOM 저장                    .bat / .py 첫 줄이 깨진다. BOM 없이 저장.
외부 API                    지침상 금지. 카메라 노드의 LLM 경로는 api_key 비면
                            401 로 45초를 날린다. automation 을 로컬로 유지.
```

---

## 8. 커밋 이력 (최근)

```
ce2109b  Stop mistaking a doorway for a character sheet   ← 카메라 시트 오탐
f7e703c  Retry the decode bigger when the pose is missed  ← VRAM 상한 단조성 없음
f32c398  Cap the keeper decode size and stop two silent deaths
a4e5faf  Reflect the sheet verdict in the pull strength
4ed3297  Fix the keeper pose path that never ran
623f5e9  Put the camera category back
c74b28e  Bump to 1.9.6          ← main 이 여기까지
```

**배포 관련**: `origin/main` 은 `c74b28e`(1.9.6) 에 머물러 있다. 이 브랜치가 9커밋 앞선다.
버전 bump(1.9.7) 와 main 머지는 미결.

---

## 9. 다음 작업 순서 (2026-10-01 시점)

1. **5-1 프레이밍 감쇠 기준선** — 이게 안 풀리면 strength 스윕 자체가 무의미
2. **5-2 의상 교체가 실제로 일어나게** — 화면으로 바로 판단 가능
3. 위 둘이 정리되면 **strength 스윕** (사용자 요청: 가능한 값 전부 테스트해 최적값 찾기)
   - 대상: 서있는 자세 1~4, 앉은 자세 1~2, 누운 자세 1, 케릭터 시트 1~3
   - 그 다음 각 자세를 살짝 바꾼 구도 변형 테스트
4. `tools/` 커밋 여부, 1.9.7 bump, main 머지
