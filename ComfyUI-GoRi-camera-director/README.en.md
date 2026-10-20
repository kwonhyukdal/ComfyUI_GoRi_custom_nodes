# 🎥 (GoRi) Camera Director Skills

> 🌐 [한국어 버전](README.md)
>
> ☕ If this helped, buy me a coffee: [Support on PayPal](https://paypal.me/GoRi57788)

Give it one line of scene description (Korean is fine) plus optional reference
images, and it builds an English prompt with **shot, lens, angle, composition,
lighting, grade and camera motion** already attached. The result plugs straight
into Qwen-Image 2.1, and the text alone can be pasted into KREA 2 or MiniMax H3.

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

## 1. Install

1. Copy the `ComfyUI-GoRi-camera-director` folder into `ComfyUI/custom_nodes/`.
2. Restart ComfyUI.
3. In the node menu open **HF Skills / Camera** → **(GoRi) Camera Director Skills**.

No extra pip packages are needed. It uses only `torch`, `numpy` and `PIL`, which
ComfyUI already ships.

---

## 2. First wiring

```text
Final model CLIP ─────────────────────────→ clip
Qwen prompt rewriter ──── positive_prompt → prompt_in
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
  └─ reference_latent_out → Consistency Keeper.camera_latent (optional)
```

The shortest path is: **type the scene into `topic`, connect `clip`, done.**
You do not need `prompt_in`; the node builds the prompt from `topic` itself.

> **Connect the final model's CLIP to `clip`.** Qwen-Image 2.1 needs a Qwen
> CLIP; Flux or SDXL needs its own. Mixing CLIPs from different models can
> break faces and skin.

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
| `reference_latent_out` | LATENT | Consistency Keeper, VAE Decode | Latent of the main reference. Requires `vae` |

> **A sheet image is also dropped from `image_out` and `reference_latent_out`.**
> Even if a character sheet becomes the main reference, the outputs carry a
> non-sheet reference instead. Passing the sheet through would make downstream
> nodes (I2V, upscale, Keeper) draw a multi-panel sheet. If the sheet is the
> only connected reference, both outputs are empty.

Connecting `prompt_out` to the Consistency Keeper's `camera_prompt` tells the
keeper about intent such as "change the outfit" or "change the background".

> The `positive` socket is kept for compatibility with older workflows. The new
> path does not use it and ignores it even when connected — this node builds the
> prompt itself.

---

## 4. Using the widgets

Top to bottom: **topic → preset → automation → ten camera dropdowns → AI LLM settings**.

### 4-1. topic — one line of scene

Write the scene as you would describe it. **Korean works.**

```
A woman in a black coat turns around in a rainy alley
```

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

### 4-2. preset — set the mood in one click

Choosing a preset **fills all ten camera dropdowns with that preset's values**.
Choosing `자동 (auto)` clears them back to auto.

| Preset | Feel |
|---|---|
| `자동 (auto)` | Rules or AI decide (default) |
| `시네마틱 인물 (cinematic portrait)` | Standard portrait recipe — 85mm, medium close-up, Rembrandt light, cinematic grade |
| `제품 히어로 (product hero)` | Sharp product shot — 100mm macro, centered, three-point studio |
| `CF 버티컬 (vertical ad)` | Vertical ad — medium close-up, centered, vivid grade |
| `다큐 핸드헬드 (doc handheld)` | Documentary look — 35mm, soft overcast, premium grade |
| `드라마틱 롱샷 (dramatic long shot)` | Wide, low angle, low key, strong contrast |

> **All five presets are unique.** Choosing any of them visibly changes the output.
> To customize preset values, see section 10.
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
| `motion` | Camera movement (video only) | 21 (push-in, pan, orbit, handheld…) |
| `speed` | Movement speed | slow / normal / fast |
| `amplitude` | Movement strength | subtle / normal / dramatic |
| `motion2` | A second movement (video only) | Same 21 as `motion` |

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

### 4-5. AI LLM settings (collapsed)

A new node starts with a collapsed **`AI LLM 설정`** (AI LLM settings) row.
Click it to expand five fields. The folded state is saved in the workflow, so it
stays the way you left it.

| Field | Description |
|---|---|
| `provider` | [OI] · Anthropic · Gemini · OpenRouter · Groq · DeepSeek · Mistral · Ollama · LM Studio · Custom |
| `model` | Model name. Empty uses the provider default |
| `api_key` | Key. If empty, `.env` and environment variables are checked |
| `custom_base_url` | Only for `Custom ([OI] compatible)` |
| `vision_detail` | Image size sent to the LLM: `선명 (768)` / `균형 (512)` / `절약 (384)` |

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
- Connect the **same numbers** to the Consistency Keeper. Different numbers mean
  the keeper pulls toward a different person.

### 5-2. Pose

Write **slot number plus a pose** in the topic and that image becomes pose-only.
Any slot from 1 to 10 works, and you can name several at once.

```
follow the pose from image 2
poses from images 3 and 7
image 2 is pose only
image 2, sitting
```

Pose slots are removed from identity, outfit and object sources, and are **not
sent to the LLM** — they travel only through the image model's pixel path. That
is why the face or clothes in a pose reference do not leak into the main subject.

In `AI 판단 (llm)` mode you do not have to name a slot at all: the LLM looks at
each reference image's pose and **picks the pose reference itself**, attaching a
label. That choice is then verified against pixels, so it only applies to slots
where a person was actually detected (guards against false positives). If you
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
  so on). The keeper only restores small drift within the same composition; it
  cannot rebuild a face when the composition changes a lot.

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

- It **finds the slots that contain a person** and uses the first one as the main
  subject (face, body and outfit source). Other people stay as additional persons.
- Slots with no person become secondary references (background, object, style).
  Their faces and outfits are not copied.
- So **you can put an outfit or an object in slot 1.** If the person is in slot 2,
  slot 2 becomes the main subject.
- The result is logged: `참조 자동 분류 — 인물 슬롯 2`.
- If the topic names a slot (`image 2 is pose only`), **that always wins**.

**An object on a plain background is read as an `item`** (outfit photo, product
photo, studio furniture). Pixels cannot tell a garment from an object (measured:
the two signals overlap), so it only decides "item" and leaves wear-or-place to a
**conditional** sentence:

```
reference image 1 is an isolated item: if it is a garment, put it on the person
from reference image 2 with its exact colour, cut and material; if it is an
object or product, keep its exact shape, material and colour and place it in the
scene.
```

**AI 판단 (llm) classifies the roles more precisely.** The LLM looks at the
attached images and returns each slot's role in its JSON, which overrides the
pixel verdict (logged as `LLM 참조 역할 — 1번=outfit`). The role vocabulary is
closed to six words — `person`·`outfit`·`object`·`background`·`style`·`pose` — and
a slot number that is not actually connected is dropped. With an explicit
`outfit`, the sentence states the transfer outright:

```
dress the person from reference image 2 in the garment shown in reference image 1,
keeping its exact colour, cut, material and pattern; the garment must be worn on
the body, not held or placed beside it.
```

A room photo holding many objects is not an item (unknown). Only a single object
on a plain background counts.

Person detection uses a pose model. It borrows the model bundled with the keeper
folder; if that is missing (camera installed alone), the analysis turns off and
slot 1 becomes the main subject as before.

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

> The sheet is sent **only to the LLM** (to read identity) and is dropped from
> every path to the image model — not just the reference latents but also
> `image_out` and `reference_latent_out` (the outputs feeding Keeper, I2V and
> upscaling). Qwen-Image follows the layout of a reference image, so passing
> the sheet through would produce a multi-panel output. This handling prevents
> that.

### 5-7. Guards that attach automatically

There is nothing to switch on. The node adds only what the situation needs.

- **People**: finger and toe counts, limb separation, skin texture, face structure.
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

- **Model location**: `ComfyUI/models/translation/tc-big-ko-en`
  (or `models/translation/tc-big-ko-en` inside the node folder, or the folder
  named by the `GORI_TRANSLATE_MODEL` environment variable)
- **Not bundled with the repo.** Download it once, about 420 MB.
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
| Korean text inside the image is broken | The model cannot render Korean (Flux/SDXL). Use a Qwen-Image model or composite the text separately |
| Two people appear | A single-character sheet was treated as a cast sheet. Write `character sheet` in the topic |
| The output looks like a multi-panel sheet | A normal photo was detected as a sheet. Remove `character sheet` from the topic and describe the scene |
| `image_out` / `reference_latent_out` is empty | Only a sheet image is connected. Sheets are dropped from all outputs, so connect one more reference besides the sheet |
| The outfit from a reference is copied | Give that slot a role in the topic (`image 2 is background only`) |
| People look smeared | Lower denoise (0.6-0.8) and raise resolution. Enter the value in `pf_denoise` to get a warning |
| The face differs from the reference | Check whether the topic asks for a pose. Remove the pose sentence and use `중경 (MS)` or closer. If that is not enough, add a face-specific tool |
| Shoe colour or style changes | A guard keeps the reference shoes. If it still changes, name the colour and style you want in the topic |
| `pose_image` is connected but the pose does not change | A map that also draws hands and face can be misread. Connect a body-only map |
| Changing the reference image does not change the result | A stale cache. Restart ComfyUI |
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

## 10. Editing presets and keywords

| File | Purpose |
|---|---|
| `presets.json` | Change or add presets. Values must match the dropdown labels exactly |
| `keywords_ko_en.json` | The Korean/English keyword list used by `규칙 (auto)`. Add your own words |

Presets live in **two places**. The values used at run time are in `presets.json`;
the values that fill the widgets when you pick a preset on screen are in the
`CAMERA_PRESETS` block inside `web/progressive_image_inputs.js`. **Editing only
one of them makes the filled widgets and the actual result disagree.** Keep both
in sync when you change a preset.

---

## 11. Credits and license

- Camera prompt structure inspired by `higgsfield-ai/skills` (MIT)
- Five camera angles (POV, reflection, panoramic, three-quarter rear, wide hero)
  adapted from `xoxxel/camera-prompts` (MIT)
- Korean to English translation model: `Helsinki-NLP/opus-mt-tc-big-ko-en` (CC-BY-4.0)
- This node: MIT
