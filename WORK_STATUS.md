# 작업 진행상황 (WORK STATUS)

> **이 문서는 이 저장소의 단일 진실 원천(single source of truth)입니다.**
> 어떤 AI가 이 폴더에서 작업을 시작하면 **반드시 이 파일을 먼저 읽고**, 작업을 진행하면서
> **갱신해야** 합니다. 컨텍스트가 길어지면 실제로 오판이 발생합니다. 이 파일이 그 방어선입니다.
>
> 마지막 갱신: 2026-10-01 (판정층 설계 추가)
> 현재 브랜치: `fix/audit-2026-09-30` (origin과 동기화됨, `origin/main`보다 16커밋 앞섬)
>
> **현재 최우선 방향은 10절의 판정층이다.** 5절의 블로커 두 건은 판정층으로 풀린다.

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
| `Keeper_Logic.md` | **(개인, gitignore 됨)** 키퍼 로직 해설 |
| `camera_Logic.md` | **(개인, gitignore 됨)** 카메라 로직 해설 |

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
규칙 2      각 폴더의 .py 가 stage 면 그 폴더의 해설서가 코드보다 최신이어야 통과
무시        git commit --no-verify   ← 의도적으로 우회할 때
```
`.git/hooks` 는 git 이 추적하지 않아 fresh clone 에는 훅이 없다 → `install_hook.bat` 필요.

**개념 해설서 2종은 개인 문서라 gitignore 로 저장소에서 뺐다.**
stage 대상이 아니므로 규칙 2 는 **수정 시각**으로 신선도를 잰다.
문서가 없으면(fresh clone) 규칙 2 는 적용되지 않는다 — 아무도 안 가진 파일에
게이트를 걸면 결국 우회당하기 때문이다.

**테스트 하네스는 이 저장소에 없다.** 아래 별도 저장소에 있다 (2026-10-01):
```
C:\Users\khd19\Documents\개발\coding skills\My_Jev_Browser_harness_skills
    \examples\comfyui-gori\
        wf_to_api.py     UI→API 변환기 (노드 무관하게 재사용 가능)
        run_keeper.py    실행기 (값 대입 8곳만 노드별로 수정)
        Harness_Logic.md 해설서 + 문서 이름 규칙
```
> 워크플로에 하네스가 덧대는 배선(값 대입 8곳과 그 사유)은 그쪽 `Harness_Logic.md` 3절에 있다.

**문서 이름 규칙: 개발 대상 이름 + `_Logic.md`**
| 대상 | 폴더 | 문서 |
|---|---|---|
| 키퍼 | `Comfyui-GoRi-Consistency-Keeper/` | `Keeper_Logic.md` |
| 카메라 | `ComfyUI-GoRi-Camera-Director/` | `camera_Logic.md` |

**새 노드를 개발하면** ① `<노드이름>_Logic.md` 작성 ② `.gitignore` 추가
③ 훅에 폴더↔문서 짝 추가. 세 단계를 빠뜨리면 그 노드는 규칙 2 에 걸리지 않습니다.

> **대소문자 함정 (2026-10-01 실측)**: git 은 Windows 에서도 pathspec 을
> **대소문자를 구분**합니다. `git add "Comfyui-GoRi-Camera-Director/..."` 는
> exit=0 인데 **아무것도 stage 하지 않습니다**. 그래서 훅의 폴더명은
> `git ls-files` 출력에서 그대로 복사했습니다. 틀리면 규칙이 조용히 발동 안 합니다.

**검증 완료 (실측 7케이스)**
```
키퍼 .py + WORK_STATUS, 해설서 오래됨   → 차단 (exit 1)  ✅
카메라 .py + WORK_STATUS, 해설서 오래됨 → 차단 (exit 1)  ✅
두 해설서 모두 최신                     → 통과 (exit 0)  ✅
해설서 하나가 없음                      → 통과 (exit 0)  ✅ 규칙2 미적용
WORK_STATUS 없이 .py 만                → 차단 (exit 1)  ✅
카메라만 바꿔도 키퍼 해설서는 요구 안 함  → 통과 (exit 0)  ✅
git commit --no-verify                 → 통과 (exit 0)  ✅
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

**배포 관련**: `origin/main` 은 `c74b28e`(1.9.6) 에 머물러 있다. 이 브랜치가 16커밋 앞선다.
버전 bump(1.9.7) 와 main 머지는 미결.

---

## 9. 다음 작업 순서 (2026-10-01 갱신)

**순서가 바뀌었다.** 5-1 과 5-2 를 개별 고치는 대신 **10절의 판정층**을 세운다.
strength 스윕이 무의미한 이유(5-1)가 판정층 도입의 직접 동기였기 때문이다.

1. **판정층 1층(포즈) 구현** — 좌표 정규화 + 손상 판정. 10절 명세대로
2. **판정층을 키퍼에 연결** — 영역별 strength. 5-1 이 이 단계에서 같이 풀린다
3. 1·2층 통과 후 2층(동작), 3층(물리)
4. 그때 5-2(의상 교체)와 strength 스윕을 함께 확인
5. `tools/` 커밋 여부, 1.9.7 bump, main 머지

- 게이트 검증 중 생긴 테스트 주석을 되돌렸다(커밋 87910c 에 들어갔음).

---

## 10. 판정층 (신규 방향, 2026-10-01)

원본 이미지가 **오염·가림·교차**되면 그 픽셀을 그대로 당겨도 오류가 강제된다.
그래서 생성이 아니라 **신뢰할 수 있는 원본 영역을 판정해 그 부분만 당긴다.**

### 10-1. 방향 정정 (이걸 먼저 읽을 것)

처음 설계는 **"이 자세가 가능한가?"** (절대 유효성) 였다. 이건 반대다.
원본이 캐릭터의 기준이므로, 정상이면서 극단적인 자세가 "위반"으로 걸리는 순간
기준이 뒤집힌다. NASA 가동범위를 통과 기준으로 세운 것은 이 목적을 반대로 써먹었다.

```
잘못됨   원본이 절대적으로 올바른가?   → 절대 평가   ✗
옳음     원본이 손상되지 않았는가?      → 손상 평가   ✓
```

따라서 **가동범위·체격 비례·좌우 대칭은 통과 기준이 아니다.** 정상이면서 극적인
자세는 원본 그대로 살아 있어야 한다. 이 값들은 **가려진 관절을 추정할 때 쓰는
보조 데이터**로 역할이 낮아진다.

### 10-2. 좌표 정규화 — 세 층의 공통 전제

원본 좌표는 이미지별로 정규화되어 있어 스케일이 전부 다르다. NASA 체격·CMU 동작과
비교하려면 **신체 기준 프레임**으로 바꿔야 한다.

```
origin = 중골반 (left_hip, right_hip 의 중점)
up     = mid_shoulder - mid_hip
scale  = |mid_shoulder - mid_hip|      ← 몸통 길이

정규화 좌표 = (p - origin) / scale
```

이렇게 하면 거리·프레이밍과 무관하게 같은 사람의 척추·어깨너비·다리길이가
항상 같은 숫자가 된다.

**함정**: MediaPipe 는 2D 에 z 가 더해진 값이다. **3/4 각도에서 비율이 짧아진다.**
정면·측면에서만 판정을 걸고 3/4 는 임계값을 넓혀야 한다.

### 10-3. 반환 형식

네 층이 **같은 형식**을 갖는다. 그래야 나중에 해부학 층을 규칙만 채워 끼울 수 있다.

```
verdict     : intact | damaged | undetermined
violations  : [{layer, check_id, landmark_ids, measured, allowed, severity}]
confidence  : 0.0 ~ 1.0
```

`undetermined` 는 **판단 보류**다. 위반도 정상도 아니다. 이 상태가 없으면
근거 없는 확신을 만들어내고 그 확신으로 원본을 끌어온다.

### 10-4. 층별 판정 — 네 층이 같은 질문을 한다

> "이 원본 영역을 끌어와도 되는가?"

| 층 | 판정 | 원본에서 무너지는 것 | 상태 |
|---|---|---|---|
| 1 포즈 | 관절이 연속으로 이어져 있는가 | 팔이 몸통을 관통, 팔다리가 서로 붙음, 관절이 다른 판다리로 점프 | 구현 가능 |
| 2 동작 | 프레임 간 연속성 유지 | 지터, 순간이동, 팼다가 갑자기 바뀜 | 구현 가능 |
| 3 물리 | 지지·접지 성립 | 발이 뜸, 손이 허공에 부딪힘, 무게중심이 발밖 | 지면 추정 필요 |
| 4 해부학 | 손가락 온전 | 손가락이 네 개로 붙음 | 후순위 |

**오염된 원본을 고치려고 생성하지 않는다. 버리기만 한다.** 그 영역은 원본을
따르지 않고, 최종적으로 생성이 알아서 채운다.

### 10-5. 커버리지 실측 (테스트 13장 전수)

포즈 33점 중 얼굴 11점을 제외하면 **신체 22점**이다.

| 부위 | 실측 가시성 | 판정 가능 |
|---|---|---|
| 어깨·팔꿈치·손목 | 0.44 ~ 1.00 | 완전 |
| 손 (손목 + 미지·약지·엄지 3점) | 0.69 ~ 1.00 | 완전 |
| 손가락 | 손 21점 모델 **실측 작동** | 끝점 5개 분리 확인 |
| 고관절·무릎·발목 | 정상 검출 | 완전 |
| **발 (발뒤꿈치·엄지)** | **0.03 ~ 0.47** | 미흡 |
| **발가락** | **모델에 없음** | 불가 |
| 얼굴 | 해당 없음 | 제외 (원본 일관성을 따름) |

**13장 전수 검출 결과 — 아래 점수는 전부 `min_pose_detection_confidence=0.3` 기준이다**
```
img#0   515x827       425,905 px   포즈  0점   1.57배 확대·0.3 에서도 0점
img#1   573x865       495,645 px   포즈  0점   1.45배 확대·0.3 에서도 0점
img#2   864x1184    1,022,976 px   25점
img#3   1904x1077                  21점        손 1개 검출
img#4   530x803                    27점        손 1개 검출
img#5   717x901        646,017 px   27점
img#6   1243x1815  2,256,045 px   27점
img#7   1536x2688                  27점        손 2개 검출
img#8   577x824        475,448 px   29점
img#9   546x662        361,452 px   25점
img#10  10896x6800 74,092,800 px   16점        캐릭터 시트 → 분절 검출
img#11  10896x6800 74,092,800 px   13점        캐릭터 시트 → 분절 검출
img#12  2752x1536  4,227,072 px   33점
```

> **정정 (2026-10-01 재측정)**: 위 표를 처음엔 임계값 0.5 와 0.3 이 구분된 것처럼
> 적었으나 **둘 다 0.3 으로 돌린 값**이었다. 스크립트의 confidence 인자가
> landmarker 생성에만 쓰이고 검출 루프에 전달되지 않았다.
>
> ```
> 임계값 0.5 → 9/13 검출   (img#2, img#10 이 빠진다)
> 임계값 0.3 → 11/13 검출  (img#0, img#1 만 실패)
> ```
>
> 키퍼는 **0.5 (기본값)** 를 쓴다. 즉 실제 노드 동작은 9/13 이고,
> `img#2` 와 `img#10` 은 키퍼에서 포즈를 못 잡는다.

**관절별 가시성 (2026-10-01 실측, conf 0.3, 검출 11장 × 22점 중앙값)**

이미지별로 "최솟값"을 모으면 발목 한 점이 전체를 끌어내린다. 관절별로 보면 다르다.
```
어깨  1.00        팔꿈치 0.87 ~ 0.97     손목  0.81 ~ 0.90
골반  1.00        무릎   0.81 ~ 0.85
발목  0.21        발뒤꿈치 0.19          발끝  0.08
```
→ **무릎까지는 쓸 만하고 발밑은 못 쓴다.** 판정 대상은 앞의 10개 관절로 잡았다.

**기하 판정은 쓸 수 없다 — 부정적 결과 (2026-10-01 실측)**
```
정상 사진의 투영 팔길이 좌우 차이(몸통길이 기준) 최대 0.745
정상 사진의 투영 다리길이 좌우 차이              최대 0.445
```
한쪽 팔이 앞으로 나온 사진에서는 그게 **정상**이다. 임계값을 추측으로 넣으면
정상 9장의 절반 이상이 "손상" 으로 분류된다 → **판정 근거로 못 쓴다.**
그래서 v1 은 기하 판정을 하지 않고 가시성만 본다 (10-11 참조).

**해상도는 포즈 검출의 결정 요인이 아니다.** 361K 픽셀짜리 img#9 도 25점이 나온다.
→ **기존 4MP 재디코드 로직은 img#0/#1 실패를 해결하지 못한다.** 원인은 미조사다
(추측으로 쓰지 않는다).

**캐릭터 시트 2장은 13~16점만 잡는다.** 패널이 여러 개라 인체가 분절된 상태로
잡힌다 — 시트 게이트가 먼저 걸러야 하는 이유가 이것이다.

### 10-6. MediaPipe 실측 함정 (2026-10-01)

```
mediapipe 0.10.33      solutions 모듈 없다. tasks.python.vision 만 있다
.task 파일             site-packages 안에 없다. 외부 경로에서 로드한다
create_from_options()  running_mode 인자를 받지 않는다. Options 객체에 넣어야 한다
Image 이름 충돌        PIL.Image 로 import 하면 `_image_ptr` AttributeError 로 죽는다
vision task 목록       face_detector, face_landmarker, hand_landmarker,
                       holistic_landmarker, pose_landmarker, gesture_recognizer,
                       object_detector, image_segmenter, image_classifier,
                       image_embedder, interactive_segmenter
                       → foot_landmarker 도 발가락 모델도 없다
로컬 모델              pose_landmarker_lite.task, hand_landmarker.task
                       얼굴 landmark 모델은 로컬에 없다
```

### 10-7. 데이터 라이선스 검증 (상업 요건)

**금지 — 연구 전용**
```
CrowdHuman   "non-commercial research and educational purposes only"
FreeMan      CC-BY-NC-4.0 · "No commercial usage is allowed"
SHHQ         "non-commercial research purposes only"
SynBody      CC BY-NC-SA 4.0
Motion-X     CC BY-NC-SA
BEDLAM       연구용. 상업 라이선스는 별도 문의
SMPL/SMPL-X  "any use for commercial purposes is prohibited"
             → 판정층에 필요 없다. MediaPipe 로 충분하니 회피한다
```

**허용 — 채택**
```
CMU Mocap     "free for all uses"
              "may include this data in commercially-sold products,
               but you may not resell this data directly"
              "may be copied, modified, or redistributed without permission"
              → 판정 기준으로 "사용"하는 쪽이므로 재판매가 아니라 조건 충족
NASA-STD-3001 Volume 2 Rev C   미국 정부 문서이므로 public domain
              체격 5/50/95 백분위, 관절 가동범위, 체절 질량·무게중심·관성모멘트,
              토크·가속도 하중, 체표면적. 근거는 ANSUR 1988 미국 육군 설문
```

**조건부**
```
COCO         어노테이션은 CC BY 4.0 → 상업 사용 가능 (출처표기만)
             이미지는 Flickr 이미지별 → 비상업·파생금지 혼재, 출처표기 누락 있음
             2017 unlabeled 123,403장 중 무조건 자유·USgov 는 5% 뿐
             → 좌표만 쓴다. 픽셀을 쓰지 않는다
Open Images  어노테이션 CC BY 4.0, 이미지 CC BY 2.0 이나
             "각 이미지 라이선스를 직접 확인하라" 고 명시
             → 단독 상업 안전 후보로 승인하지 않는다
```

**CMU 의 결함 (중요)**: 손가락·엄지 관절은 **캡처하지 않았다.** 편집 편의용으로
가상으로 붙인 관절이며 원자료는 무시하라고 명시되어 있다. → 2층으로 손가락
판정은 불가능하다. 4층이 그 몫이다.

### 10-8. 데이터 역할이 바뀌었다

| 데이터 | 처음 역할 | 지금 역할 |
|---|---|---|
| COCO 좌표 | 통과 기준 | 가림 위치의 통계 — 어디가 보통 가려지는지 |
| CMU 동작 | 통과 기준 | 지터·순간이동 임계값 산정 근거 |
| NASA | 통과 기준 | 가려진 관절 위치 추정 보조 |

라이선스 조사 결론 자체는 유효하다. 쓰임만 달라졌다.

### 10-9. 미결 — 구현 전에 정해야 하는 것

```
1. 3층(물리)의 지면 평면을 어떻게 잡나
   카메라 기준 프레임으로 근사 / 실측 디프스로 검출 / 3층을 보류하고 1·2층부터
   → 근거가 약한 판정이 들어가면 그게 더 해롭다. 3층 보류를 권한다

2. 판정층을 키퍼에 실제로 물리는가
   물리면 키퍼 동작이 바뀐다 (영역별 strength). 설계만 하고 코드는 건드리지 않는다

3. 4층(손가락) 인터페이스만 지금 만드는가
   21점 모델이 실측으로 작동함을 확인했으니 규격만 잡아두면 나중에 규칙만 채운다

4. img#0 / img#1 의 포즈 0건 원인 — 미조사
   해상도도 임계값도 아니다. 그림 자체를 눈으로 확인해야 한다
```

### 10-10. 키퍼에 연결하면 얻게 되는 것

지금은 카메라 기준 MSE 가 5.72 면 **전체 영역을 0으로 죽인다** → strength 0.00.
그래서 strength 스윕이 무의미하다 (5-1).

판정층이 주면 그 답이 나온다.
```
damaged      →  원본 픽셀을 버린다 (오류를 재주입하지 않는다)
undetermined →  그 픽셀은 건드리지 않는다
intact       →  그 픽셀만 끌어온다
```

strength 가 0 이 아니라 **영역별 다른 강도**가 된다. 이것이 판정층의 실제 목적이다.

---

### 10-11. 구현 상태 — 1층은 키퍼 안에서 (2026-10-01, R74)

**새 폴더를 만들지 않았다.** 처음에는 별도 폴더를 계획했으나 실측 결과 그것이
`parallel_abstraction`(게이트)을 걸었을 가능성이 높다:
```
키퍼가 이미 가진 것   _pose_landmarker / _pose_landmarks_from_tasks
                     _person_mask_from_rgb (landmarks -> 공간 가중치)
                     subject_bbox (landmarks -> bbox)
판정층이 필요한 것    landmarks -> **신뢰 판정**(intact/damaged/undetermined)
```
판정층의 입력은 키퍼가 이미 만드는 디코드된 RGB 다. 분리하면 **프레임마다
VAE 디코드를 두 번** 하게 되어 `new_vae_decode_in_per_frame_path` 게이트와
같은 낭비가 된다. 그래서 키퍼 모듈 안에 넣고 기존 검출 결과를 재사용한다.

**추가한 것**
```
_pose_landmarks_from_tasks(u8, with_visibility=False)
    기본값 False → 기존 호출자는 **똑같이 2-튜플**. 3-튜플은 옵션으로만.
_judge_triples()        landmark 형태(속성 객체/튜플) → (x, y, vis) 통일
_judge_body_frame()     몸통 기준 프레임 (ox, oy, scale)
judge_points()          순수 판정 함수 (검출 없음, 테스트 가능)
judge_reference_trust() u8 → 판정 dict (얇은 래퍼)

_JUDGE_CORE_LANDMARKS   어깨·팔꿈치·손목·골반·무릎 10점 (발 제외)
_JUDGE_VIS_MIN = 0.30   실측: 팔다리 관절 132점 중 77% 가 이 값 이상, 중앙값 0.93
_JUDGE_TORSO_MIN = 0.02 실측 정상 구간 0.156~0.511 보다 7.8배 낮음
```

**13장 실측 결과**
```
intact 7장 / undetermined 6장 / damaged 0장
img#0,1,2,10  포즈 미검출 → confidence 1.0, frame 없음
img#3         무릎 가시성 0.08 → 미판정
img#11(시트)  6개 관절 미확인 → 정확히 예측한 분절 검출
```

**v1 은 damaged 를 절대 반환하지 않는다.** 위 부정적 결과(10-5) 때문에
기하 판정을 하지 않는다. 가시성 외에 신뢰 신호가 없다는 뜻이며,
기준 데이터를 실측해 넣을 때 연다.

**Jev 게이트 결과 (2026-10-01)**
```
parallel_abstraction      걸리지 않음 (키퍼 안에 넣은 덕)
nonascii_stdout           P=0.90 으로 걸림 → **거짓 양성으로 확인**
                          cp1252 / ascii / cp949 3종 실측 exit 0 · PASS 297 · FAIL 0
                          원인: hunk 밖에 있는 `print = _say` 재바인딩을 못 봄
                          조치: 섹션 제목을 print 대신 _say 로 직접 호출
                          → 재검토 결과 approve (exit 0)
public_api_impact         judgment 블록 additive P=0.84 / landmarker 변경
                          behavioral P=0.44 (confidence 0.25, 자문)
                          → 판독: 기존 호출자는 2-튜플 그대로라 **additive**
```

**테스트**: 키퍼 262 → **297** (R74 35개 추가), FAIL 0. 카메라 1025 / 팩 16 유지.

**규칙 관련**: 새 폴더를 만들지 않았으므로 ①~③ (로직 문서·gitignore·훅 짝)을
이번엔 걸지 않는다. 규칙 1 때문에 `.py` 와 이 문서를 함께 stage 해야 한다.

**기존 인코딩 손상 (미해결, 이번 커밋 범위 밖)**
`consistency_keeper.py` 주석에 깨진 글자가 4곳 있다 (2026-10-01 확인).
```
332행    "정답은 <깨진 한자>이 아니라"   ← 한자가 들어갔다. "깊이" 의 뜻이어야 한다
1483행   "원본 해<깨진 2바이트>도로"     ← "해상도" 의 뜻이어야 한다
1486행   "패널 검<깨진 2바이트>·유사도"  ← "패널 검출·유사도" 의 뜻이어야 한다
```
모두 HEAD 에 있던 손상이고 주석만이라 기능 영향은 없다. 이번 diff 에는 없다.
깨진 바이트를 옮겨 적지 않고 **뜻으로만** 적었다 — 옮겨 적으면 문서도 깨진다.
`camera_Logic.md` 에도 한자 2곳, `test_node.py` 에도 3곳이 같은 방식으로 남아 있다.

### 10-12. 강도 연결 — `trust_gate` (2026-10-01, R75)

판정이 실제 결과물에 닿았다. **기본은 꺼짐**이고, 켠 경우에만 영역별로
다르게 당긴다.

```
기본 OFF  detail_boost(allow=None) → 기존과 바이트 단위로 동일
켜면 ON    원본 landmark → judge_points → judge_region_allowance
          → detail_boost(allow=...) 가 막힌 부위를 건너뛴다
```

**추가 디코드·추가 추론이 없다.** 이미 하던 검출을 버리지 않고 visibility만
함께 받아온다. `_part_detail_map` 이 각 latent 를 디코드하고 포즈를 검출하므로
거기서 3-튜플(`pts`)을 함께 보관하면 끝이다.

```
_part_detail_map 반환에 "pts" 추가 (x, y, visibility 3-튜플 × 33)
"xy" 는 2-튜플 그대로 — _apply_region_strength 가 `for (px, py) in xy` 로
        엄격 언팩하므로 3-튜플을 넣으면 죽는다. 두 계약을 함께 지킨다.
```

**부위 정의를 두 개 만들지 않았다.** `judge_region_allowance` 는 기존
`PART_REGIONS` 에 판정 대상 관절 인덱스를 **교집합**해서 쓴다. 부위 표가 두 개
생기면 나중에 한쪽만 고치는 사고가 난다.

```
PART_REGIONS        손목 15 → hand_left(15,17,19,21) 와 arm_left(11,13,15) 둘 다
왼쪽 무릎 25 → leg_left(23,25,...) 만 막힘. leg_right 는 26 이 멀쩡해서 통과
얼굴(0~10)   → 판정 대상이 아니라 항상 허용. 사용자가 "원본 일관성을 따른다" 고
                정한 결정이라, 코드가 뒤집으면 안 된다
```

**내가 만들어서 고친 버그**: 처음에 `allow` 항목이 형식 오류면 그 부위를
건너뛰게 짰다. 그러면 **오타 하나가 region 보강 전체를 조용히 꺼버린다**
(silent degradation). 판정값은 항상 0.0/1.0 이므로 이 경로는 외부 호출자에만
닿지만, 방어를 못 해두는 건 게이트 규칙을 어기는 셈이다. → 게이트를 루프 전에
한 번에 청소하고, 해석 불가 항목은 **제한 없음**으로 두고 1회 로그한다.
fail-open 인 이유: 오타로 부위를 막는 것이 기능을 잃는 것보다 나쁘다.

**테스트**: 키퍼 297 → **320** (R75 23개 추가), FAIL 0.
카메라 1025 / 팩 16 유지.

**Jev 게이트 결과 (2026-10-01, R75)**
```
전체            advisory, exit 0  (게이트 실패 0건)
prompt_or_output_assembly_change  안 걸림 — 기본 경로를 그대로 둔 opt-in 이라
                                  pref 지침이 그대로 적용됨
public_api_impact  behavioral P=0.78 / 0.65 / 0.53 / 0.51 / 0.49 → 전부 advisory
                   (allow=True 일 때 결과가 실제로 달라진다. 의도한 변화다)
max-hunks      11 hunks > 기본 10 → exit 2. 판정이 아니라 인프라 한도라
                --max-hunks 20 으로 올려 다시 돌렸다
```

**아직 하지 않은 것**: `trust_gate` 를 켠 상태의 실측. 이 노드는 아직
ComfyUI 를 실제로 돌려 본 적이 없으므로 **결과물의 차이가 있는지는 아직 모른다.**
→ 아래 10-13 에서 실제로 돌려 봤다.

### 10-13. 첫 실제 구동 — 기존 버그가 여기서 죽었다 (2026-10-01)

판정층을 실으려고 하네스로 ComfyUI 를 돌렸는데 **키퍼가 죽었다.**

```
line 1884, in run
  out = out + eff * _mask * (matched - sampled)
RuntimeError: 텐서 장치가 둘로 섞여 있다 (GPU 와 CPU)
```

**원인은 판정층이 아니라 `_match_spatial` 이었다.** 크기가 같으면
`return ref` 로 즉시 돌려주는데, 그 `ref` 는 워크플로에서 넘어온 latent 라
target 과 다른 장치에 있을 수 있다. 크기가 같다는 이유로 device 정규화를
건너뛰고 있었다.

```
이 버그의 저자:  b176f0a (v1.7.0)  — 판정층 작업과 무관한 기존 코드
지금까지 안 드러난 이유: 이 노드가 끝까지 한 번도 실행된 적이 없다.
   이전 하네스 실행들은 더 앞단(배선·입력)에서 실패했다.
```

**기존 버그였습니다.** 제 변경으로 생긴 게 아니며, 판정층 작업이 처음으로
키퍼를 끝까지 돌리면서 드러났습니다. 조용히 못 도는 것과 죽는 것은 둘 다
실패이고, **죽는 쪽이 찾기 쉬웠습니다.**

**수정**: 조기 반환 경로에서도 device/dtype 을 맞춘다. 단 **이미 같으면
옮기지 않는다** — 무조건 `.to()` 를 걸면 매 호출마다 복사가 생긴다.

**우연히 걸린 저장소 규칙**: 에러 메시지를 주석에 그대로 인용했다가
`하드코딩 디바이스 문자열 없음` 테스트에 걸렸다. 이 저장소는 소스에
`cuda:0` 같은 문자열을 **금지한다** — 이 노드가 어떤 장치에서도 돌아야
하기 때문. 에러 문구를 **뜻으로만** 적는 것으로 고쳤다.
> **원칙**: 문제의 증거를 남길 때 원문을 인용하지 말고 뜻으로 적는다.
> 원문을 인용하면 규칙을 깨게 되고, 규칙을 깨려고 하면 증거가 약해진다.
> 이 둘을 동시에 지키는 방법은 "뜻으로만 적기" 뿐이었다.

**하네스 쪽에서 발견한 함정**: `run_keeper.py` 의 시드 인자가 PowerShell 에
빈 문자열 인자를 넘길 때 **조용히 사라져**(seed=None) 결과가 재현 불가였다.
A/B 비교를 계획했다면 이걸 먼저 고쳐야 한다.
