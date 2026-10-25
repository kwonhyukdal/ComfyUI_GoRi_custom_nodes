# 🎥 (GoRi) Camera Director Skills

> 🌐 [한국어 버전](README.md)
>
> ☕ If this helped, buy me a coffee: [Support on PayPal](https://paypal.me/GoRi57788)

Give it one line of scene description (Korean is fine) plus optional reference
images, and it builds an English prompt with **shot, lens, angle, composition,
lighting, grade and camera motion** already attached. The prompt works with **any
image model** — connect that model's CLIP to `clip` and the result plugs straight
in, or copy the text alone into KREA 2 or MiniMax H3.

- **Works with no API key.** The default mode (rules) picks the camera from a
  Korean/English keyword list, so it runs fully offline.
- **AI judgment is optional.** Add a key or a local LLM and it also interprets
  the scene.
- **Up to 10 reference images**, and any slot can hold any role. Slots that
  contain a person are found from pixels and used as the main subject.

```
Node name    (GoRi) Camera Director Skills
Menu         HF Skills / Camera
```

---

## Quick start (3 steps)

1. Type the scene into `topic`. **Korean is fine.** Or connect another node's
   **text box (STRING) to `topic`** — the camera node auto-classifies and applies
   the pose, motion and other data that arrives in `topic`.
2. Connect the final model's CLIP to `clip`.
3. Connect `positive_out` to the KSampler's `positive` and `negative_out` to
   `negative`, then run.

Picking a preset fills all ten camera fields for you. If you have reference
photos, connect them from `image_1` upward. The sections below explain each step.

---

## 1. Install

1. Copy the `ComfyUI-GoRi-camera-director` folder into `ComfyUI/custom_nodes/`.
2. Restart ComfyUI.
3. In the node menu open **HF Skills / Camera** → **(GoRi) Camera Director Skills**.

Prompt building needs no extra pip packages. It uses only `torch`, `numpy` and
`PIL`, which ComfyUI already ships.

> **Reference auto-analysis is optional (section 5-5).** Only this feature, which
> decides the role of each `image_1`~`image_10` from pixels, uses `mediapipe`.
> Without `mediapipe` the analysis is silently skipped and prompt building keeps
> working. If you want it, run `python -m pip install mediapipe` once with the
> ComfyUI Python.
>
> Pose detection also needs a pose model (`pose_landmarker_lite.task`). It ships
> inside this folder, so nothing else is downloaded. To use a different model,
> point `GORI_POSE_MODEL` at the full path of the `.task` file. The object model
> (`efficientdet_lite0.tflite`) ships inside this folder too.

---

## 2. First wiring

```text
Text box (STRING) ────────────────────────→ topic        (optional)
Final model CLIP ─────────────────────────→ clip
Prompt rewriter ───────── positive_prompt → prompt_in
Reference photo ──────────────────────────→ image_1
Pose map (DWPreprocessor, body only) ─────→ pose_image   (optional)
Final model VAE ──────────────────────────→ vae          (optional)
High-resolution latent node ──────────────→ latent_image (optional)
Existing negative conditioning ───────────→ negative     (optional)

(GoRi) Camera Director Skills
  ├─ positive_out ────────→ KSampler.positive
  ├─ negative_out ────────→ KSampler.negative
  ├─ prompt_out ──────────→ Show Text (for checking)
  ├─ image_out ───────────→ I2V start frame / upscale (optional)
  └─ reference_latent_out → KSampler.latent_image / VAE Decode (optional)
```

The shortest path is: **type the scene into `topic`, connect `clip`, done.**
You do not need `prompt_in`; the node builds the prompt from `topic` itself.

> **You can fill `topic` from a text box instead of typing.** Convert the `topic`
> field to an input (right-click the field) and connect another node's **text box
> (STRING)** output. The node auto-classifies and applies the pose, motion and
> other data that arrives in `topic`, exactly as if you had typed it.

> **Connect the final model's CLIP to `clip`.** Whatever model you render with,
> use **its own** CLIP. Mixing CLIPs from different models can break faces and
> skin.

> **Do not connect the prompt rewriter's CLIP here.** Take the rewriter's
> **string** output (`positive_prompt`) into `prompt_in`, and give `clip` the
> image model's CLIP.

---

## 3. The five outputs

| Output | Type | Connect to | What it is |
|---|---|---|---|
| `positive_out` | CONDITIONING | `KSampler.positive` | The final prompt, encoded once |
| `negative_out` | CONDITIONING | `KSampler.negative` | Keeps your existing negative and adds failure guards |
| `prompt_out` | STRING | Show Text, another prompt node | The exact English string used. Copy it into KREA 2 or similar |
| `image_out` | IMAGE | I2V start frame, upscale | Passes the main reference image through. Empty when no image is connected |
| `reference_latent_out` | LATENT | KSampler, VAE Decode | Latent of the main reference. Connect `latent_image` and it leaves at **exactly the width and height that node decided**; without `latent_image` it follows the reference image's aspect. Requires `vae` |

> **A sheet image is also dropped from `image_out` and `reference_latent_out`.**
> Even if a character sheet becomes the main reference, the outputs carry a
> non-sheet reference instead. Passing the sheet through would make downstream
> nodes (I2V, upscale) draw a multi-panel sheet. If the sheet is the
> only connected reference, both outputs are empty.

> **`reference_latent_out` can be used directly as the sampler's start latent.**
> Connect an empty latent (Empty Latent Image, Deno Resolution, ...) to
> `latent_image` and the output leaves at **exactly that node's width and height**.
> Every ratio works the same — 1:1, 4:5, 3:4, 2:3, 16:9, 9:16, 16:10, 21:9 — because
> the image size the sampler produces is decided by the start latent's size. Without
> `latent_image` it follows the reference image's aspect as before. With
> `denoise=1.0`, though, the start latent's **shape is the seed**, so changing the
> ratio changes the result even at the same seed (see 4-8).

> The `positive` socket is kept for compatibility with older workflows. The new
> path does not use it and ignores it even when connected — this node builds the
> prompt itself.

---

## 4. Using the widgets

Top to bottom: **topic → preset → automation → ten camera dropdowns → AI LLM
settings**. The preset row and each feature popup also carry a **↻ refresh
button** that restores the preset defaults (4-9).

### 4-1. topic — one line of scene

Write the scene as you would describe it. **Korean works.**

```
A woman in a black coat turns around in a rainy alley
```

- **You can feed `topic` from a text box instead of typing.** Convert the `topic`
  field to an input (right-click the field) and connect another node's **text box
  (STRING)** output. The node auto-classifies and applies the pose, motion and
  other data that arrives in `topic`.
- Connecting a wire to `prompt_in` makes it replace the `topic` field. Unplug it
  and the field takes over again.
- If you name a shot in the topic (`full body`, `close-up shot`), that wins over
  the dropdown defaults.
- Lighting and motion keywords are read too: `neon`, `sunset`, `studio`,
  `silhouette`, `night`, `bright` decide the lighting, and phrases like
  "slowly walks toward" decide the motion.
- **Both sentences and tag lists are understood.** A tag-style prompt such as
  `1girl, red dress, neon, night street` and a sentence like "a woman standing in
  a rainy alley" are read the same way. When deciding what each reference image is
  for (pose, outfit, ...), decorative tags are filtered out to avoid misreading.
- Dialogue or extra description is fine. The camera clauses are appended after it.
- **For how to write a prompt that actually holds, see 4-7.** Naming the person, the
  arm position and the garment matters most.

### 4-2. preset — set the mood in one click

Choosing a preset **fills all ten camera dropdowns with that preset's values**.
Switching presets does not erase what you set under another preset — each
preset remembers its own last state (see the note at the end of 4-4). To put a
field back to the preset default, press the **↻ button** on the preset row (4-9).

| Preset | Feel |
|---|---|
| `자동 (auto)` | Rules or AI decide (default) |
| `시네마틱 인물 (cinematic portrait)` | Standard portrait recipe — 85mm, medium close-up, Rembrandt light, cinematic grade |
| `제품 히어로 (product hero)` | Sharp product shot — 100mm macro, centered, three-point studio |
| `CF 버티컬 (vertical ad)` | Vertical ad — medium close-up, centered, vivid grade |
| `다큐 핸드헬드 (doc handheld)` | Documentary look — 35mm, soft overcast, premium grade |
| `드라마틱 롱샷 (dramatic long shot)` | Wide, low angle, low key, strong contrast |

> **All five presets are unique.** Choosing any of them visibly changes the output.
> To adjust a preset, pick different values in the ten camera fields below.
>
> **Presets carry no camera movement (`motion`).** Movement only applies to video
> pipelines, so selecting a preset leaves `motion` and `motion2` at `none`. To
> direct movement, pick it in the `motion` field yourself.

### 4-3. automation — who picks the camera

| Mode | Behavior | When |
|---|---|---|
| `규칙 (auto)` **(default)** | Picks from the Korean/English keyword list. Offline and free | When you have no key |
| `AI 판단 (llm)` | The LLM expands the scene into English and picks the camera | When you have a key and want the smartest result |

If `AI 판단 (llm)` has no key or the network is down, it **falls back to rules
automatically**. A run never fails because of this.

### 4-4. The ten camera dropdowns

| Widget | What it sets | Choices |
|---|---|---|
| `shot` | How large the subject appears | 7 (extreme close-up to extreme wide) |
| `lens` | Field of view and background compression | 8 (14mm to 200mm, plus macro) |
| `angle` | Camera height and direction | 13 (eye-level, low angle, POV, top-down…) |
| `composition` | Placement in frame | 8 (rule of thirds, centered, leading lines…) |
| `lighting` | Quality of light | 10 (window light, golden hour, Rembrandt, low key…) |
| `grade` | Color treatment | 8 (cinematic film, vivid, noir…) |
| `motion` | Camera movement (video only) | 22 (push-in, pan, orbit, handheld…) |
| `speed` | Movement speed | slow / normal / fast |
| `amplitude` | Movement strength | subtle / normal / dramatic |
| `motion2` | A second movement (video only) | Same 22 as `motion` |

> On screen, `motion` and `motion2` show as **`motion (only video)`** — the name
> carries an `(only video)` suffix. Movement only applies to video pipelines and
> is ignored for still images.

**Multiple selection** — click a dropdown and a list opens with a toggle on each
row. Turn on several and **all** of those clauses go into the prompt. The widget
shows `수동 (2개)` (manual, 2 selected), and clicking empty canvas closes the
list. `자동 (auto)` is not in the list; the header takes its place.

- `speed` and `amplitude` modify the movement, so only the **first** value is used.
- If any value in the field is unknown, the whole field is treated as auto.
- `motion` plus `motion2` combines two movements (e.g. push-in + pan).
  `none` means "add no movement clause"; `static` means "lock the camera off".

**Adding to and removing from a preset**

Choosing a preset fills all ten fields. The preset is the **per-field baseline**,
and the dropdowns add to or subtract from it.

| What you want | What to do | Result |
|---|---|---|
| Keep the preset | Touch nothing | All ten fields use the preset |
| Add an option | Turn one more option on in that field | Preset value **plus** the addition |
| Replace an option | Turn the old one off and the new one on | Only the new value in that field |
| Remove an option | Set that field back to `자동 (auto)` | That field only drops out of the preset and rules/AI fill it |

For example, with `dramatic long shot` (low key), adding `neon` to lighting puts
**both low key and neon** into the prompt. If you do not want low key, turn it off
and leave neon on.

> To drop the preset entirely, set the `preset` field to `자동 (auto)`. Clearing all
> ten fields is not the way — that state cannot be distinguished from the normal
> API path where widgets are left empty and the whole preset applies.

**Your toggles survive — each preset remembers its own state**

Switching presets never erases what you turned on under another preset. Add a
lighting option under `자동 (auto)`, switch to `시네마틱 인물`, and come back — your
earlier toggles return. Each preset keeps its own last state. After a page
refresh or ComfyUI restart the workflow restores its saved state, and
remembering starts from there.

The buttons that restore the preset defaults — the **↻ refresh buttons** on the
preset row and in each feature popup — are described in **4-9**.

### 4-5. AI LLM settings (collapsed)

A new node starts with a collapsed **`AI LLM 설정`** (AI LLM settings) row.
Click it to expand five fields. The folded state is saved in the workflow, so it
stays the way you left it.

| Field | Description |
|---|---|
| `provider` | OpenAI · Anthropic · Gemini · OpenRouter · Groq · DeepSeek · Mistral · Ollama · LM Studio · Custom |
| `model` | Model name. Empty uses the provider default |
| `api_key` | Key. If empty, `.env` and environment variables are checked |
| `custom_base_url` | Only for `Custom (OpenAI compatible)` |
| `vision_detail` | Image size sent to the LLM: `선명 (768)` / `균형 (512)` / `절약 (384)` |

One field is not in the table: `llm_hint`. It carries a short instruction for the
LLM and **never appears in the UI** (API and script use only). It applies only when
you run with `AI 판단 (llm)`, and is ignored under `규칙 (auto)`.

Running with `AI 판단 (llm)` makes the `model` field **blink green**. Local LLMs
can take tens of seconds, so this tells you it is working. When judgment
finishes the green light lingers briefly; if it failed and fell back to rules,
the light turns **red**.

### 4-6. Pre-flight check (optional)

Type the values from your KSampler into `pf_steps`, `pf_cfg` and `pf_denoise`
below the node, and it warns about risky combinations before running. Zero
disables the check.

| Field | Value to enter |
|---|---|
| `pf_steps` | The KSampler `steps` |
| `pf_cfg` | The KSampler `cfg` |
| `pf_denoise` | The KSampler `denoise` |

- A close-up with a very small latent gets a "faces may smear" warning.
- Steps or CFG far outside the usual range are flagged.
- Denoise above 0.9 is flagged as drifting away from the original.

> These fields **only warn**. They never block or change your values.

### 4-7. Writing a prompt that holds — five rules

**The node only keeps what you name.** Everything you leave out is filled
differently on every run.

**1. Name the person**

```
The woman is wearing jeans and sits on a chair indoors      (yes)
Wearing jeans and sitting on a chair indoors                (no — nobody named)
```

The node looks for a person in the text and attaches the face, finger and limb
guards. With nobody named, **none of them attach.**

Korean nouns (`여성`, `여자`, `사람`, `모델`) survive translation, so they are safe.
Watch this when you use a translator — the same meaning can come out as `He`, and
the guards drop silently.

**2. Say where the arms and hands are**

```
The woman sits on a chair with both hands on her knees, looking ahead    (yes)
The woman sits on a chair, looking ahead                                (no — the arms are nowhere)
```

When the arms from the reference photo do not carry over to the new pose (arms
raised to hold something, now sitting), an unnamed arm **disappears.**

**3. Name the garment**

If you do not name the garment, **the reference image is the only anchor**, and a
pose change redraws that area, so it differs from run to run. Naming it (`long
jeans`) keeps it stable.

**4. Write footwear as adjective + noun**

`closed-toed shoes` (good). A footwear adjective attached to another garment
(`closed-toed shorts`) prints one warning line in the console. It warns; it never
blocks.

**5. Fix the seed and change one thing at a time**

With many constraints the model satisfies **only some** of them, and which one it
drops changes from run to run. So **fix the seed** and edit the sentence. Picking
a lucky image by changing seeds is not reproducible.

> Guards **raise the odds; they do not guarantee.** If what you named does not come
> out, add one more of the five items above. Console logs and `prompt_out` show
> what was attached.

### 4-8. Reference image resolution — follows the input resolution

The reference image is conditioned at **the same pixel count as the resolution
node connected to `latent_image`**. The number field at the bottom of the node
(after the pose socket, `reference_max_mp`) is **hidden and its value is unused**
— the value comes from the input now. (It is kept as a **hidden slot-keeping
field** so that saved widget values are not shifted by one slot.)

| Input (resolution node) | Reference conditioning |
|---|---|
| 1.0MP (e.g. 1344x768) | also ~1.0MP — a portrait photo becomes 752x1360 (same pixel count) |
| 2.0MP | also ~2.0MP |
| 0.5MP | also ~0.5MP (smaller input, smaller reference) |
| not connected | nothing to follow, so the reference is set to 1MP |

- **Why it was removed:** the field let the reference be encoded larger than the
  input (input 1MP, reference 2MP). That resolution is never used for generation,
  so it adds no information and only misaligns the pixel grid between the
  reference and the result.
- The reference **photo keeps its own aspect ratio** — it is never cropped or
  letterboxed. Only the pixel count (grid cells) matches the input.
- **To make the photo match the canvas shape, prepare the photo in that shape
  yourself.** The node never crops, letterboxes or stretches it. Cropping
  changed the outfit and the face, padding (letterboxing) added nothing for the
  better, and stretching distorted the body and the face. A photo you prepared
  yourself is passed through as is.
- **The resolution node decides the output aspect and size.** Every ratio — 1:1,
  16:9, 9:16, 21:9 — comes out as is (output 5 leaves at exactly that size).
- **Trade-off:** with `reference_latent_out` as the sampler's
  start latent, the start latent's **shape is the seed** (`denoise=1.0`). Changing
  the ratio widget therefore changes the picture even at the same seed. This is not
  a defect but a necessary consequence of changing the ratio — a different ratio
  means a different canvas, and a different canvas means a different noise tensor.
  To get the same picture at the same seed, **do not change the ratio.**
- A larger output means a larger reference, and **step time follows the
  reference size** — a 2x reference takes about 3.4x the time, and half takes
  about 0.7x. On an 8GB card keep the resolution node near 1MP.

### 4-9. ↻ Refresh — back to the preset defaults

These put the fields back to the preset values after you changed some by hand.
Both look like a **browser refresh arrow (↻)**; normally only the arrow shows,
and hovering reveals the background.

| Button | Where | What it does |
|---|---|---|
| ↻ on the preset row | On the preset row, **one slot in from the right end** | Restores all ten camera fields to the current preset's defaults |
| ↻ in a popup | A feature popup (the window that opens when you click shot, lens, …), **top-right corner** | Restores **only that popup's field** to the preset default |

- The baseline is the **currently selected preset's defaults**. Values the preset
  provides stay and only your manual changes revert. A field the preset does not
  cover goes back to `auto`.
- The popup ↻ touches **only that popup** — other popups and the preset settings
  are left alone.
- The result is written into that preset's memory, so coming back to the preset
  shows the restored state (see "Your toggles survive" in 4-4).

---

## 5. Reference images (`image_1` to `image_10`)

### 5-1. Sockets and roles

Only `image_1` is visible at first. Each time you connect one, the **next socket
appears**. The hidden sockets are a display convenience; saved links are unaffected.

| Slot | Role |
|---|---|
| `image_1` to `image_10` | Any slot can be the **main subject** (face, body and outfit source). The role comes from the content, not the number |

- Slots with a person are found from pixels and used as main-subject candidates (5-5).
- Any slot that is not the main subject needs a role in the topic. Without one it
  will **not** copy face, hair, skin, outfit or identity (duplication guard).

#### Naming a role by slot number — the colon (`:`) is the rule

This is how you assign roles by number in the topic. **Write `N번:` and that slot is
fixed to that role.** The colon is the **declaration mark** — "this number is this
role".

**Four rules** — number + `번` + colon + role word.

```
1번: 한국 여성
2번: 의자
3번: 하이 힐
4번: 배경
연출: <scene sentence>
```

1. After the number write `번` (or `번째`) and then the **colon (`:`)**. The `번` is
   mandatory — it is the condition that keeps a **ratio** such as `16:9` from
   reading as a colon declaration.
2. Write the role word **after** the colon. **Spaces are free**
   (`3번: 하이힐` = `3번: 하이 힐`).
3. A particle may follow the word (`2번: 의자를` — slot 2 = object).
4. One per line, or separated with `/`.

| You write | The node reads |
|---|---|
| `2번: 의자` | slot 2 = object |
| `3번: 하이 힐` · `3번: 하이힐` | slot 3 = outfit (spaces are free) |
| `4번: 배경` | slot 4 = background |
| `1번: 한국 여성` | slot 1 = person |
| `둘째: 의자` · `두 번째: 의자` | slot 2 = object (Korean ordinals count as numbers) |
| `피사체: 1번 이미지` | slot 1 = main subject |
| `이미지 2의 핸드백` · `2번 이미지 의자` | the older forms still work (object) |
| `2번 앉은 자세` | slot 2 = pose |
| `연출: <sentence>` | only the sentence after this line becomes the scene |

**Read even without a colon** — outfit, background and pose notes, and the older
image notation, work as they always did: `3번 하이힐` · `4번 배경` ·
`2번 앉은 자세` · `2번 이미지 의자` · `이미지 2의 핸드백`.

**Deliberately not supported** — these are not read.

| You write | Why not |
|---|---|
| `2번 의자` (no colon) | there is **no way to tell a declaration from a sentence**. A wear sentence like `2번 옷을 입혀` (a person) leaks in as an outfit note. Put the colon in |
| `1번: 앉아` · `2번: 신겨` | a **verb** in the declaration slot is an action, not a thing. For a pose write a pose word, like `2번 앉은 자세` |

**Why the colon is required**: without it there is no way to tell a **declaration**
from a **sentence**. `2번 의자` (a declaration) and `2번 의자를 밀어` (a sentence),
`2번: 하이힐` (a declaration) and `2번 하이힐을 신겨` (a sentence) look the same in
plain text. Reading a sentence as a declaration can make a person disappear from the
result, so without a colon the node does not bind a slot to a role.

**It is still not silent** — when your topic looks like a colon-less declaration the
node prints one line in the console. **The note does not change any verdict** (the
prompt is unchanged).

```
[Camera Director] 콜론 없는 역할 표기 "2번 의자" — 역할로 읽지 않습니다.
그 칸을 역할로 쓰려면 2번: 의자 처럼 콜론을 붙여 주세요 (문장의 일부였다면 그대로 두세요)
```

The note covers **object and person** notes only — outfit, background and pose notes
that already work without a colon, and forms like `2번 이미지 의자`, are never
nagged about. Since the word may be the subject of a sentence, the line is worded
conditionally ("if you meant it as a role"). One line per run at most.

**Word class is sorted out automatically.** Nouns and numerals go through the
object, outfit, background and person lexicons; verbs go to the state or change
decision (`신발을 신고` is a state, `신겨` is a change); adjectives, adverbs and
determiners go to the modifier decision (`같은` keeps, `다른` swaps). **Unknown
words follow the old path** — the automatic classification never flips an
existing verdict.

If one slot is given several roles, **pose > object > person** wins.

### 5-2. Pose

Write **slot number plus a pose** in the topic and that image becomes pose-only.
Any slot from 1 to 10 works, and you can name several at once.

```
follow the pose from image 2
poses from images 3 and 7
image 2 is pose only
image 2, sitting
```

A pose slot is used only for the pose and is dropped as a source of face, outfit
or objects. That is why the face or clothes in a pose reference do not leak into
the main subject.

In `AI 판단 (llm)` mode you do not have to name a slot at all: the LLM looks at
each reference image's pose and **picks the pose reference itself**, attaching a
label. That choice is then verified against pixels, so it only applies to slots
where a person was actually detected (so it does not land on the wrong slot). If you
write `image 2 is pose only` yourself, **your instruction always wins**.

#### Pointing at a pose with a map image (`pose_image`)

Connect a stick-figure map to the `pose_image` socket and the node reads that
pose and adds it to the prompt. It reads three states: **sitting, standing and
lying**.

1. Add a pose extraction node such as `DWPreprocessor`.
2. Turn **hand and face drawing off** so only the body is drawn.
3. Connect the result (coloured skeleton on black) to `pose_image`.

- A pose map is **not** a reference photo. It does not affect the reference
  count, face or outfit judgment.
- A map that also draws hands and face has overlapping dots and can be misread.
  A body-only map is the most accurate. If the map cannot be read, nothing
  happens and the topic description alone drives the pose.
- You can still describe the pose in the topic. Both are used; neither erases
  the other.
- With nothing connected, the node behaves exactly as before.

#### Changing the pose redraws the face

When you ask for a pose (a topic word such as "sitting" or "walking", or a pose
map), the model rebuilds the body and **redraws the face too**. The node then
adds a face-lock phrase to the negative to steer it back to the reference
person. It still will not be a perfect match.

For shots where the face matters:

- **Do not put pose wording in the topic.** If you only want to change the
  background or props, leaving the topic empty is the safest choice.
- **Use `중경 (MS)` or a closer shot** so the face gets enough pixels. `auto`
  tends to frame the whole body and makes the face small.
- If the face must be preserved, add a face-specific tool (a face detailer and
  so on). This node only shapes the prompt; it cannot rebuild a face when the
  composition changes a lot.

### 5-3. Outfit replacement

**The first number is the outfit source, the second is the person wearing it.**

```
2 outfit, 1 replace
put the outfit from image 2 on the person in image 1
apply image 2's outfit to image 1
```

It understands outfit words such as outfit, clothes, dress, attire and uniform.
A phrase like "the woman wearing the dress in image 2" is read as **a person**,
not as an outfit source.

**Describing a state is not the same as asking for a change.**

| What you write | Interpretation |
|---|---|
| `the person in image 1 is wearing shoes` | State description → keep the reference shoes |
| `wear black shoes` | Change request → switch to those shoes |
| `change into white sneakers` | Change request (a colour or item means change) |
| `put the outfit from image 2 on them` | Change request (a slot number means change) |

In short, describing **what is happening** keeps the reference, while naming a
**specific item, colour or material** — or telling it to `wear` / `put on` —
switches to that outfit.

### 5-4. Two people

```
image 1 woman, image 2 man, image 3 her pose, image 4 his pose
```

With two people named, the "exactly one person" suppression is dropped and each
identity is preserved separately. It also guards against two bodies merging or
limbs swapping.

### 5-5. When the topic is empty — references are analysed

If you connect images but leave the topic blank, the node **analyses each image's
pixels and assigns the roles itself.**

> **`topic` counts the same whether you type it or wire a text box into it.** The
> pixel analysis always runs, but when the topic names a slot that verdict wins
> (see the last bullet below).

- It **finds the slots that contain a person** and uses the first one as the main
  subject (face, body and outfit source). Other people stay as additional persons.
- Slots with no person become secondary references (background, object, style).
  Their faces and outfits are not copied.
- So **you can put an outfit or an object in slot 1.** If the person is in slot 2,
  slot 2 becomes the main subject.
- The result is logged: `참조 자동 분류 — 인물 슬롯 2`.
- If the topic names a slot (`image 2 is pose only`), **that always wins**.

**An object on a plain background is read as an "item"** (outfit photo, product
photo, studio furniture). Pixels alone cannot tell a garment from an object, so
the node decides only "item" and lets the model work out whether to wear it or
place it.

- A garment photo is put on the person from another reference; an object or
  product keeps its shape, material and colour and is placed in the scene.
- A room photo holding many objects is not an item. Only a single object on a
  plain background counts.
- Where person detection is not available, slot 1 is treated as the main subject.

**AI 판단 (llm) classifies the roles more precisely.** The LLM looks at the
attached images and assigns each slot's role, which overrides the pixel verdict.
The roles are person, outfit, object, background, style and pose, and a slot that
is not actually connected is ignored.

> Auto-analysis needs `mediapipe` and a pose model (`.task`). If either is missing
> only the analysis is skipped and everything else keeps working (see section 1).

Character sheets are still detected from pixels even with an empty topic.

### 5-6. Character sheets (turnarounds)

A character sheet is **one image holding the same person from several angles**
(front, back, side, head views). Connect one and the node recognises it, adds
"every view is the same person", and prevents the sheet layout from being drawn
into the result.

**How to use**

1. Connect the sheet to any of `image_1` to `image_10`. The slot number does not matter.
2. **Leaving the topic empty is safest.** A scene description may be read as
   "show several angles at once".
3. Other references (pose, background, prop) can be connected alongside it.

**Two kinds, and they differ**

| Kind | Topic wording | Interpretation |
|---|---|---|
| Single-character sheet (default) | `character sheet`, `turnaround`, `model sheet` | Every repeated view is the same person |
| Cast sheet | `multiple characters`, `several characters`, `different characters`, `lineup`, `cast sheet`, `ensemble sheet` | Each panel is a different character |

If several different people are in one image but it is treated as a
single-character sheet, the "all the same person" instruction makes the result
strange. In that case write `multiple characters` in the topic.

**If automatic detection misses it**, the panel layout is probably irregular.
Write `character sheet` in the topic directly. Three-view sheets (front/side/back)
are also handled when the topic says "sheet".

**With AI 판단 (llm)** the node also tells a single-character sheet from a cast
sheet: the same person from several angles gets "every view is the same person",
a row of different characters gets "each panel is a different character". A topic
word like `multiple characters` always wins over that judgment.

> The sheet is used **only to read identity** and is never passed to the drawing
> side. So connecting a sheet does not produce a multi-panel image, and the sheet
> is dropped from `image_out` and `reference_latent_out` as well.

### 5-7. Guards that attach automatically

There is nothing to switch on. The node adds only what the situation needs.

- **People**: finger and toe counts, limb separation, skin texture, face structure.
- **Scenes without people**: for a landscape or an object (or an animal-only
  scene), people-only phrases such as finger and skin wording are left out.
- **Pose requests**: asking for a new pose makes the model redraw the face. A
  face-lock phrase goes into the negative so it does not become someone else.
- **Facing the camera**: wording such as `facing forward` or `looking at the
  camera` keeps the head from turning away.
- **With references**: part boundaries (legs, arms, shoulders do not smear),
  clothing that does not fuse into skin, faces that do not blend between references.
- **Outfit colour**: a colour named in the topic is locked, and a different
  colour is pushed back through the negative.
- **Footwear**: the shoes from the reference person are preserved — colour,
  silhouette, straps, heel height and material — and swapping to another style is
  blocked. If you explicitly ask to change the shoes, that request wins.
- **Object and furniture references**: shape, material, color and proportions kept
  from the original, including "similar but different furniture" swaps.
- **Contact and action wording**: `pushed against`, `holding`, `throwing`,
  `running` are translated into contact, weight and mid-action instructions.
- **Removal scenes**: no half-removed pieces or floating fragments left behind.
- **Two or more references**: distance between subjects and bottom margin are
  measured from pixels and preserved. Opposite lighting directions between
  references raise a console warning.

---

## 6. Korean to English translation (optional)

In `규칙 (auto)` mode, a Korean topic or `prompt_in` is translated to English when
the translation model is present. `AI 판단 (llm)` does not use it — the LLM writes
the English scene itself.

- **Model location**: drop it into `ComfyUI/models/translation/tc-big-ko-en`.
- **Not bundled with the node.** Download it once, about 420 MB.
- **Without it, Korean passes through unchanged.** Translation quietly turns off
  and the node keeps working.
- If you only use English, the model is never loaded.
- Repeated sentences reuse the previous translation, so the second run is fast.

---

## 7. LLM setup (only for `AI 판단 (llm)`)

| Provider | Default model | Key |
|---|---|---|
| OpenAI | `gpt-4o-mini` | `api_key` or `OPENAI_API_KEY` |
| Anthropic | `claude-3-5-haiku-latest` | `api_key` or `ANTHROPIC_API_KEY` |
| Gemini (free tier) | `gemini-1.5-flash` | `api_key` or `GEMINI_API_KEY` |
| OpenRouter (free models) | `google/gemini-flash-1.5` | `api_key` or `OPENROUTER_API_KEY` |
| Groq (free tier) | `llama-3.2-90b-vision-preview` | `api_key` or `GROQ_API_KEY` |
| DeepSeek (low cost) | `deepseek-chat` | `api_key` or `DEEPSEEK_API_KEY` |
| Mistral (free tier) | `pixtral-12b-2409` | `api_key` or `MISTRAL_API_KEY` |
| Ollama (local) | Name of an installed model | No key. Just run `ollama serve` |
| LM Studio (local) | Name of the loaded model | No key. Start the Local Server |
| Custom (OpenAI compatible) | Enter manually | Optional; keyless gateways work |

- **Image judgment needs a vision-capable model.** With a text-only model the
  judgment fails and it may fall back to rules.
- Gemini keys are free at [Google AI Studio](https://aistudio.google.com/).
- On OpenRouter, a model name ending in `:free` costs nothing.
- For `Custom`, put the base URL (e.g. `https://api.example.com/v1`) in
  `custom_base_url` and the server's model name in `model`.
- Local LLMs get a long timeout because inference can take a while.

### Keeping keys safe (recommended)

Create a `.env` file in the top-level ComfyUI folder and the `api_key` field can
stay empty.

```
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```

- Priority: **field entry > `.env` file > OS environment variable**
- Entering a key in the field and confirming saves it to `.env` and clears the field.
- Saved or shared workflow files and generated PNG metadata do not contain the key.
- **One exception**: `Export (API)`, and the `Custom`, `Ollama` and `LM Studio`
  providers, have no `.env` slot to save into, so the value stays in the field.
  Only in that case, clear the field before exporting. Right-click the node for
  **`api_key 지우기 (공유용)`** (clear API key for sharing).

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Node does not appear | Check the folder location and `__init__.py`, then restart ComfyUI |
| A wire will not attach to `prompt_in` | Right-click the widget → *Convert widget to input*, or drag the wire onto it |
| `AI 판단 (llm)` gives ordinary results | Check the console for the LLM failure (key, model name, server running). It falls back to rules |
| Korean text comes out unchanged | Switch to `AI 판단 (llm)` or install the translation model |
| Korean text inside the image is broken | Most image models cannot draw Korean. Pick a model that renders text well, or composite the text in an image editor |
| Two people appear | A single-character sheet was treated as a cast sheet. Write `character sheet` in the topic |
| The output looks like a multi-panel sheet | A normal photo was detected as a sheet. Remove `character sheet` from the topic and describe the scene |
| `image_out` / `reference_latent_out` is empty | Only a sheet image is connected. Sheets are dropped from all outputs, so connect one more reference besides the sheet |
| The outfit from a reference is copied | Give that slot a role in the topic (`image 2 is background only`) |
| People look smeared | Lower denoise (0.6-0.8) and raise resolution. Enter the value in `pf_denoise` to get a warning |
| One arm is missing | The reference arms did not carry over to the new pose. Name the arm position in the topic (`both hands on her knees`). See 4-7 |
| A garment changes (long jeans become shorts) | Name the garment in the topic. Without it the reference image is the only anchor. See 4-7 |
| The face differs from the reference | Check whether the topic asks for a pose. Remove the pose sentence and use `중경 (MS)` or closer. If that is not enough, add a face-specific tool |
| Shoe colour or style changes | A guard keeps the reference shoes. If it still changes, name the colour and style you want in the topic |
| `pose_image` is connected but the pose does not change | A map that also draws hands and face can be misread. Connect a body-only map |
| Changing the reference image does not change the result | A stale cache. Restart ComfyUI |
| Output ratio differs from the one you picked | Check that `latent_image` (Empty Latent etc.) is connected. With it, output 5 leaves at exactly that size. Without it, it follows the reference image's aspect (4-8) |
| The output stays at 1MP (e.g. 752x1360) and does not grow | `latent_image` (the resolution node) is not connected. Connect it and output 5 leaves at exactly that size, and the reference follows that pixel count too (4-8) |
| The same seed gives a different result | The start latent's size changed, which is equivalent to a different seed (`denoise=1.0`). Do not change the resolution node's ratio or megapixels between runs |
| The photo shape and the output composition drift apart | Keeping the reference photo's aspect ratio is the intended behaviour — the node never pads, crops or stretches it. To match shapes, prepare the photo in the canvas shape yourself (4-8) |
| Skin looks like plastic | Remove `flawless`/`smooth` from the upstream prompt and use a grainy grade such as `cinematic film` or `35mm film` |
| Emoji in the console show as `?` | A Windows console display issue. It does not affect the node |
| A shared file contained an API key | Check whether it was an `Export (API)` file. See the exception in section 7 |

---

## 9. Building a storyboard sequence

Generating one image and feeding the result back as a reference makes a **copy of
a copy**, so quality and identity drift. For a continuous sequence:

1. **Always reference the original**, not the previous output.
2. **Use the saved PNG.** Dragging a preview or using JPG loses quality by itself.
3. **Fix the preset and camera values for every shot.** `auto` changes lighting
   and grade with the input image, so the look shifts between shots.
4. **Keep the same person on the same slot number.** If slot 1 is the lead and
   slot 2 the co-star, do not swap them mid-sequence.
5. **Keep the resolution the same.** Changing the base size changes reference detail.
6. **Keep the second-pass denoise low.**
7. **Change only the scene description between shots.**

---

## 10. Credits and license

- Camera prompt structure inspired by `higgsfield-ai/skills` (MIT)
- Five camera angles (POV, reflection, panoramic, three-quarter rear, wide hero)
  adapted from `xoxxel/camera-prompts` (MIT)
- Korean to English translation model: `Helsinki-NLP/opus-mt-tc-big-ko-en` (CC-BY-4.0)
- Bundled pose model `pose_landmarker_lite.task`: MediaPipe Pose Landmarker (Apache-2.0) — see `POSE_MODEL_LICENSE.txt`
- Bundled object detector `efficientdet_lite0.tflite`: MediaPipe EfficientDet-Lite0 (Apache-2.0) — see `OBJECT_MODEL_LICENSE.txt`
- This node: MIT
