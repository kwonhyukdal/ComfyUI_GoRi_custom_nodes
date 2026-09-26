# 🎥 (GoRi) Camera Director Skills

주제 한 줄(한글 OK), 선택 이미지, 선택적 positive/negative conditioning을 입력하면 **카메라 구도·렌즈·앵글·조명·그레이드·(영상)무빙**이 자동으로 조합됩니다. 최종적으로 `positive_out`, `negative_out` conditioning과 확인용 `prompt_out`을 출력합니다.

- 패키지 폴더: `comfyui-GoRi-camera-director`
- 노드 표시 이름: `(GoRi) Camera Director Skills`
- 출력: `positive_out` (`CONDITIONING`), `negative_out` (`CONDITIONING`), `prompt_out` (`STRING`)
- `clip`은 최종 Qwen Image 모델의 text encoder입니다.
- `vae`는 원본 reference conditioning을 위해 선택적으로 연결합니다. Qwen Image Edit/Image 2.1 identity 유지에는 `image_1`과 `vae`를 함께 연결하는 것이 권장됩니다.
- Qwen 프롬프트 재작성기의 `CLIP`을 `clip`에 연결하지 마십시오. Qwen `positive_prompt` **문자열**을 `prompt_in`에 연결하고, 최종 모델용 CLIP을 `clip`에 연결하십시오.
- `positive` conditioning 입력은 이전 배선과의 호환성을 위해 남겨 두지만 새 표준 경로에서는 사용하지 않습니다. 잘못된 CLIP conditioning이 얼굴을 바꾸는 것을 막기 위해 무시됩니다.
- `negative` conditioning은 선택 입력입니다. 기존 negative를 보존한 뒤 카메라/영상 실패 모드만 추가합니다.
- `image_1`~`image_10`은 카메라 힌트/비전 LLM 판단용 입력이며, 별도 출력하지 않습니다.
- 연결된 `image_N` 번호는 LLM note와 reference guard에 그대로 유지됩니다. `image_3`만 연결하면 `image_1`로 압축되지 않습니다.
- 레퍼런스 이미지가 2장 이상이면 첫 번째 연결 이미지가 주 인물 기준이 되고, 추가 이미지는 `background / outfit / prop / product / style / lighting / composition / mood` 중 요청된 역할로만 사용하도록 가드가 추가됩니다.
- 의상/옷 교체처럼 `Image 2`를 의상 참고로 명시적으로 쓰는 작업일 때만 의상 전용 가드가 추가됩니다. 단순히 장면 설명에 `dress`나 `옷`이라는 단어가 있어도 고양이/배경/제품 장면에는 의상 가드를 넣지 않습니다.
- 주제에 `full-body shot`, `close-up shot`, `wide shot` 등 카메라 샷을 이미 명시했다면, 기본 카메라 샷보다 사용자가 입력한 샷을 우선합니다.
- 사람/인물 reference가 있는 이미지 장면에서는 `face and body preservation guard`가 추가됩니다. 원본 얼굴 구조, 골반·힙·어깨·허리 비율, 피부색을 유지하고 배경색이 피부에 번지지 않게 합니다. 제품/고양이/배경 only 장면에는 적용되지 않습니다.
- `prompt_out`에는 범용 positive 품질 가드가 붙습니다: 자연스러운 피부, 정상적인 사람 비율, 손가락 5개, 자연스러운 얼굴, 정체성 일관성.
- 이미지 입력 시 `same facial structure / same hairstyle / same outfit / same body proportions` 같은 원본 유지 문구도 추가됩니다.
- 외부 pip 패키지는 필요하지 않으며, vision 입력 변환에는 ComfyUI 환경의 `PIL`/`torch`/`numpy`를 사용합니다.

---

## 1. 설치

```
ComfyUI/
└── custom_nodes/
    └── comfyui-GoRi-camera-director/   ← 이 폴더 전체를 복사
```

> 📍 **이 PC의 실제 설치 위치 (2026-09-25 확인):**
> `C:\ComfyUI\ComfyUI video\ComfyUI-Easy-Install\ComfyUI\custom_nodes\comfyui-GoRi-camera-director`
> 배포 Python: `python_embeded\python.exe` (3.12.10) — 자동 테스트 통과 확인

1. 이 폴더를 `ComfyUI/custom_nodes/` 에 복사
2. ComfyUI 재시작 (`Start ComfyUI.bat`)
3. 노드 추가 메뉴 → **HF Skills / Camera** → **`(GoRi) Camera Director Skills`**

## 2. 기본 배선 — conditioning 디렉터로 KSampler에 연결

```text
Qwen Prompt Rewrite.positive_prompt ── prompt_in ────────────────→ GoRi Camera Director Skills.prompt_in
최종 Qwen 모델 Text Encode의 CLIP ─────────────────────────→ GoRi Camera Director Skills.clip
원본 reference image ─────────────────────────────────────→ GoRi Camera Director Skills.image_1
최종 Qwen 모델 VAE ───────────────────────────────────────→ GoRi Camera Director Skills.vae
고해상도/MP latent 생성 노드 ──────────────────────────────→ GoRi Camera Director Skills.latent_image
최종 모델 Text Encode negative ── negative ───────────────────→ GoRi Camera Director Skills.negative

GoRi Camera Director Skills ── positive_out ──────────────────→ KSampler.positive
GoRi Camera Director Skills ── negative_out ──────────────────→ KSampler.negative
GoRi Camera Director Skills ── prompt_out ────────────────────→ Show Text / debugging
```

> **중요:** `positive_prompt`는 conditioning이 아니라 `STRING`입니다. Qwen 프롬프트와 카메라 문구를 이 노드에서 하나의 문자열로 합친 뒤, 최종 모델용 CLIP으로 한 번만 인코딩합니다. `positive` conditioning을 직접 `+`로 합치는 경로는 더 이상 사용하지 않습니다.

`positive_out`과 `negative_out`은 실제 KSampler에 연결하는 conditioning 출력입니다. `prompt_out`은 humans/debug/재확인용 문자열입니다.

- `text`가 위젯이면: 우클릭 → **Convert widget to input** 후 `prompt_out` 선을 연결합니다.
- 최신 ComfyUI에서는 `prompt_out`을 `text` 위로 드래그해도 입력 단자로 변환됩니다.
- `positive_out`은 `prompt_in`이 연결되면 Qwen `positive_prompt`, 짧은 reference identity anchor, 카메라 문구를 하나의 문자열로 합친 뒤 최종 CLIP으로 한 번 인코딩한 결과입니다. 사람 reference가 있을 때만 identity anchor가 추가되며, 원본 reference latent는 `image_1`과 `vae`로 전달됩니다. 단일 인물 anchor와 duplicate negative는 명시적인 여러 인물에는 적용되지 않으며, 유리창/거울/반사 장면에서는 중복 억제를 적용하지 않습니다. 골반/체형 측정 문구는 public Qwen 경로에 넣지 않습니다. `positive` conditioning은 새 경로에서 무시됩니다.
- `negative_out`은 기존 negative conditioning이 연결되어 있으면 이를 유지한 뒤, 카메라/영상 실패 모드만 합친 결과입니다. 단일 reference 경로에서는 `multiple people`, `duplicate person`, `cloned person`, `mirrored twin`만 중복 억제용으로 추가합니다. `extra arms`, `face mismatch`, 피부색 오염 방지 문구는 추가하지 않습니다. negative는 vision 없이 텍스트만 인코딩하므로 Qwen Vision 인코딩은 positive 1회만 실행되고, `reference_latents`도 positive에만 첨부됩니다. `llm` 티어에서 LLM이 제안한 extra negative가 있으면 카메라 negative 뒤에 병합됩니다.
- `prompt_in` 표준 경로에서도 의상 교체 의도가 명확하고 이미지가 2장 이상이면 의상 전용 가드가 추가되고, 다중 이미지일 때는 보조 reference 역할 제한 1문장이 추가됩니다. 단일 이미지에는 역할 가드를 넣지 않습니다.
- 이미지 2장에 두 인물을 지정하면(예: `Image 1의 여성과 Image 2의 남성이 서로 마주보기`) 2인 duo 가드로 전환됩니다. 3~10번 슬롯도 동일하게 인식합니다 (`Image 3의 남성`, `Image 10의 여성` 등). `Exactly one main person` 억제와 중복 인물 negative, 보조 역할 제한이 모두 빠지고 해당 슬롯의 정체성 보존 문구가 들어갑니다. 두 신체가 하나로 합쳐지거나 팔다리가 뒤섞이는 양방향 융합을 막는 신체 분리 문구도 함께 들어갑니다. 의상 교체 문구는 duo로 오인하지 않습니다.
- standalone 경로(`prompt_in` 미연결)의 positive에는 얼굴/신체/의상 legacy guard가 붙지만, negative는 카메라 실패 모드만 담는 것이 현행 정책입니다. positive 양면 방어가 필요하면 `prompt_out`을 별도 CLIPTextEncode에 연결해 negative를 직접 보완하십시오.
- `auto (규칙)` 티어는 shot/lens/angle/lighting/motion/speed 키워드를 봅니다. `네온`, `노을/석양`, `스튜디오`, `실루엣/역광`, `어두운/심야/야간`, `화사한` 같은 단어가 조명을 결정합니다. 일상적인 `밤` 한 글자로는 로우키로 바꾸지 않습니다 (오탐 방지, 키워드 사전 `keywords_ko_en.json`에서 확장 가능).
- `latent_image`는 선택 입력입니다. 2MP/2.5MP/3MP 등 실제 sampling latent를 연결해도 reference conditioning은 1MP 상한으로 묶입니다. 연결하지 않으면 1024 기준 reference conditioning을 사용합니다.
- 고해상도에서 동일한 reference 이미지의 vision tensor와 VAE latent는 내용 해시+목표 크기 키로 캐시되어 반복 실행 시 재계산하지 않습니다. 이를 통해 reference conditioning 속도를 개선했습니다.
- 3MP 이상에서는 KSampler 스텝, preview, VAE decode 비용이 전체 시간에서 더 큰 비중을 차지할 수 있습니다. 속도가 필요하면 2~3MP를 기준으로 생성한 뒤 upscale하는 편이 안전합니다.
- 영상(I2V): `motion`을 선택할 수 있습니다. `image_1`~`image_10` 입력은 프롬프트 판단용이므로, I2V 시작 프레임은 원래 `LoadImage` 출력을 I2V 노드에 직접 연결하십시오.

### 프롬프트 입력 2경로 (동시 겸용 가능)

| 경로 | 방법 | 특징 |
|---|---|---|
| **topic 칸** | 직접 타이핑 (한글 OK) | 위젯이 **항상 유지** — 선을 안 끼우는 한 계속 씀 |
| **prompt_in 단자** | 외부/AI 텍스트 노드에서 선 연결 | **연결됐을 때만** topic 칸을 대체, 끊으면 topic 칸으로 자동 복귀 |

> **중요:** 이 conditioning 디렉터는 범용 노드입니다. `clip`, `positive`, `negative`는 모두 최종 모델에 맞는 같은 계열의 CLIP/conditioning이어야 합니다. Qwen 모델이면 Qwen 계열 CLIP을, Flux/SDXL이면 해당 모델의 CLIP을 연결하십시오. 서로 다른 모델의 CLIP conditioning을 섞으면 얼굴/피부가 깨질 수 있습니다.
>
> 💡 외부에서 **완성된 프롬프트**를 넣을 때는 `automation = manual (수동)` 권장 (원문 보존 + 카메라 조항만 추가)
> - 콘솔 로그의 `in=topic 칸` / `in=외부(prompt_in)` 으로 어느 쪽이 쓰였는지 확인 가능

## 2b. 출력 계약

| 출력 | 타입 | 연결처 | 설명 |
|---|---|---|---|
| `positive_out` | `CONDITIONING` | `KSampler.positive` | Qwen 프롬프트 + 사람 reference identity anchor + 카메라 문구를 한 번 인코딩한 결과. `positive` conditioning은 무시 |
| `negative_out` | `CONDITIONING` | `KSampler.negative` | 기존 negative conditioning이 있으면 유지하고, 카메라/영상 실패 모드만 합친 결과 |
| `prompt_out` | `STRING` | `Show Text` / 다른 프롬프트 재작성 노드 | 실제 positive 문자열과 동일한 디버그용 문자열 |

`prompt_in`을 연결하면 Qwen 프롬프트와 카메라 문구를 하나의 문자열로 합친 뒤 최종 모델용 CLIP으로 한 번 인코딩합니다. `prompt_in`을 연결하지 않으면 topic 기반 standalone 프롬프트를 한 번 인코딩합니다. `positive` conditioning은 새 경로에서 무시됩니다. `negative` conditioning을 연결하면 기존 negative를 유지한 뒤 카메라/영상 실패 모드만 추가합니다.

### IMAGE 입력

- `image_1`~`image_10`은 선택적 입력이며, 다른 다중 reference conditioning 노드와 같은 방식입니다.
- `auto (규칙)`에서는 첫 번째 연결 이미지 기준으로 밝기·대비·채도 등을 카메라 구성 힌트에 사용합니다.
- `llm (AI 판단)`에서는 연결된 모든 이미지를 base64 목록으로 만들어 지원 provider에 다중 비전으로 전달합니다.
- 다중 이미지일 때 `Image 1`은 주 인물 기준으로 고정되고, 추가 이미지는 배경/옷/소품/제품/스타일/조명/구도/분위기 중 요청된 역할로만 사용됩니다. 주 인물, 얼굴, 신체, 옷, 제품, 배경 주체가 복제되지 않게 방지합니다.
- 이 입력은 프롬프트 판단에만 사용되며, `image_out` 등 별도 출력은 없습니다.

## 3. 사용법 (자동화 3가지)

| tier | 동작 | 언제 |
|---|---|---|
| **llm (AI 판단)** 기본 | LLM이 주제를 영문 장면으로 확장 + 카메라 자동 선택 | 가장 똑똑한 결과 |
| **auto (규칙)** | 한/영 키워드 사전으로 카메라 선택 (오프라인·무료) | 네트워크/키 없을 때 |
| **manual (수동)** | 드롭다운 값 그대로 사용 | 완전 직접 제어 |

**프리셋 우선순위:** `특정 프리셋` > `직접 설정`(드롭다운) > `자동(auto)`(tier 판정)
- 예) 프리셋=`시네마틱 인물` + tier=`llm` → **카메라=프리셋 고정, 장면만 LLM이 확장**

**콘솔 로그 (한글):**
```
📷 Camera Director | tier=llm preset=자동 (auto) source=LLM 판단 | shot=근접 (CU) lens=85mm f/1.4 ... | scene=LLM 확장
```

## 4. LLM 설정 (tier=llm 을 쓰려면 하나만)

| provider | model 기본값 | 키 |
|---|---|---|
| OpenAI | `gpt-4o-mini` | 노드 `api_key` 칸 또는 환경변수 `OPENAI_API_KEY` |
| Anthropic | `claude-3-5-haiku-latest` | `api_key` 또는 `ANTHROPIC_API_KEY` |
| Ollama (로컬·무료) | `llama3.2` (설치한 모델명) | 키 불필요 — `ollama serve` 상태만 |

> ⚠️ 노드의 `api_key` 칸에 키를 넣으면 **워크플로 JSON에 저장**될 수 있습니다.
> 공유·백업 시 주의하고, 가능하면 **환경변수** 사용을 권장합니다.
> 키가 없거나 네트워크가 죽으면 → **자동으로 규칙(auto) 폴백** (실행은 항상 성공)

> 💡 **모델명 자동 교정:** provider를 Anthropic/Ollama로 바꿔도 `model` 칸에
> 이전 모델명(`gpt-4o-mini` 등)이 남아 있으면, 콘솔 경고와 함께 해당 provider의
> 기본 모델로 자동 교정합니다. `model` 칸을 비우면 항상 provider 기본값을
> 사용합니다. Ollama 로컬 모델명(`qwen2.5-vl` 등)은 그대로 유지됩니다.

> 💡 **직접 설정 + 자동 (auto):** `preset=직접 설정`에서 드롭다운을
> `자동 (auto)`으로 둔 항목은 tier(llm/auto/manual) 판정을 따릅니다.
> 명시적으로 고른 항목만 고정되며, 특정 프리셋을 고르면 전체가 고정됩니다.

## 5. 커스터마이징

| 파일 | 용도 |
|---|---|
| `presets.json` | 프리셋 조합 편집/추가 (라벨은 목록 A와 일치해야 함) |
| `keywords_ko_en.json` | auto 티어 한/영 키워드 사전 — 자유롭게 항목 추가 |
| `camera_director.py`의 `SHOT/LENS/ANGLE/...` | 카메라 항목과 영문 조항 자체를 바꿈 |

## 6. 검증 체크리스트

- [ ] 1. 설치 후 노드 목록에 표시
- [ ] 2. `직접 설정`+`85mm` 등 → 출력에 영문 조항 포함
- [ ] 3. tier=llm + 한글 주제 → 영문 장면으로 확장
- [ ] 4. 키 없이 llm 실행 → 콘솔 폴백 로그 + 정상 출력
- [ ] **5. 동일 시드 A/B** (카메라 off/on) → 구도·질감 육안 차이
- [ ] 6. 영상에서 무빙 적용 → 카메라 이동 확인
- [ ] 7. 동일 주제 재실행 → 콘솔 캐시로 LLM 호출 없음
- [ ] 8. 프리셋 vs 직접 설정 동작 확인
- 로컬 로직 사전 점검: `python tests/test_node.py` (자동 검증)

## 7. 트러블슈팅

| 증상 | 해결 |
|---|---|
| 노드가 안 뜸 | 콘솔 에러 확인 → 폴더명/`__init__.py` 존재 확인 후 재시작 |
| `text`에 선이 안 닿음 | 위젯 우클릭 → *Convert widget to input* (또는 드래그 자동 변환) |
| llm인데 결과가 규칙 수준 | 콘솔의 `LLM 실패` 메시지 확인 (키·모델명·Ollama 실행 여부) |
| 출력에 주제(한글)가 그대로 | `auto/manual` tier는 번역을 못 함 → tier를 `llm`으로 |
| 이미지 안 한글 글씨가 깨짐 | 모델이 한글 미지원 (Flux/SDXL) → Qwen-Image 계열 사용 또는 별도 오버레이 |
| 콘솔에 📷가 `?`로 나옴 | Windows 콘솔 코드페이지 문제 — 출력 텍스트 자체는 정상(기능 무관) |
| 재생성할수록 화질·인물이 변함 | 아래 8번 스토리보드 가이드 참고 (원본 reference 고정 + `manual` 고정) |
| 피부가 플라스틱처럼 밋밋함 | 앞단 프롬프트의 `flawless/smooth`를 빼고, 그레이드는 그레인 있는 `시네마틱 필릭`·`35mm 필름`으로. 노드는 인물 장면에 모공·결·지향성광·그레인 문구를 자동 추가함. 모공·솜털까지 살리려면 렌즈 `100mm 매크로` + 인물 주제 (제품에는 붙지 않음) |
| 노출 장면의 해부학이 뭉개짐 | 노출 의도(`nude/나체` 등)가 있으면 임상적 완성 문구(positive)와 뭉개짐 방지(standalone negative)가 자동 추가됨. 단, 노골적 디테일은 모델 안전 튜닝 한계가 있어 프롬프트로 완전 극복 불가 — 근접 프레이밍·균일 조명·낮은 denoise·고해상도가 더 효과적 |

## 8. 스토리보드 연속 생성 (화질·일관성 유지)

한 장을 뽑고 그걸 다시 reference로 쓰는 체이닝은 **사본의 사본**이라 매 세대 화질·인물이 조금씩 변합니다 (VAE 압축 왕복 손실 + 리샘플링 + Edit 모델의 재해석). 스토리보드처럼 일관되게 이어가려면 아래 규칙을 지키세요.

**원칙: reference는 항상 최초 원본, 설정은 전 컷 고정**

1. **원본 고정** — 2컷째부터 reference는 전 컷 생성물이 아니라 **최초 원본**(원 사진/첫 생성 PNG)을 계속 연결합니다. 체이닝은 손실이 누적됩니다.
2. **PNG 저장본 사용** — 미리보기 드래그나 JPG은 그 자체로 손실입니다. `SaveImage` PNG 파일을 `LoadImage`로 연결하세요.
3. **`automation = manual` + 프리셋 고정** — `auto`는 입력 이미지 통계에 따라 조명/그레이드를 바꾸고, `llm`은 매번 장면을 다시 씁니다. 시리즈 전 컷에 같은 프리셋(또는 `직접 설정`)을 고정해야 룩이 안 바뀝니다.
4. **슬롯 번호 고정** — 같은 인물은 매 컷 같은 `image_N` 번호에 연결합니다 (예: 이번 시리즈에서 1번=주인공, 2번=조연으로 정했으면 전 컷 동일). 번호가 바뀌면 identity/duo 앵커가 다른 인물을 가리킵니다. 조합이 바뀌는 시리즈(1·2번 여성 듀오였다가 1번 남성·2번 여성으로 변경 등)에서는 바뀐 컷부터 새 번호 규칙을 전 컷에 동일하게 적용하세요.
5. **해상도 통일** — 전 컷 같은 latent 크기 사용. 노드는 reference를 1MP 상한으로 맞추므로, 기준 해상도를 바꾸면 reference 디테일이 달라집니다.
6. **재생성 denoise는 낮게** — Edit/2차 패스의 denoise가 높을수록 원본에서 멀어집니다 (워크플로 측 KSampler 설정).
7. **컷마다 바뀌는 건 프롬프트뿐** — 배경·행동·대사만 `prompt_in`/topic에서 바꾸고, 카메라·인물·설정은 손대지 마세요.

## 9. 출처·라이선스

- 카메라 프롬프트 구성 규칙 출처: `higgsfield-ai/skills` (MIT) — prompt-engineering / thumbnail house-structure / video explainer blocks
- 본 노드: MIT (근거 자료와 동일)
