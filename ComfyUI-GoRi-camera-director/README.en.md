# 🎥 (GoRi) Camera Director Skills

> 🌐 [한국어 버전](README.md)
>
> ☕ If this helped, buy me a coffee: [Donate via PayPal](https://paypal.me/GoRi57788)

> **Full Qwen-Image 2.1 support** — works the same reference-latents way as the Text Encode Qwen Image 2.1 node. 10 reference image inputs, native RGBA (transparency) passthrough, use your 2K native workflow as-is.

> **Also usable with KREA 2 · MiniMax H3** — you can copy the camera-direction English prompt from `prompt_out` and paste it as-is.
> - **KREA 2** (image, Qwen3-VL encoder): paste the `prompt_out` text into the KREA 2 text encoder — shot·lens·lighting phrases carry over.
> - **MiniMax H3** (video, Hailuo): use the camera-move phrases built from the motion/speed fields as the H3 video prompt — handy for camera work in I2V.
> Direct conditioning connections (`positive_out`/`negative_out`) are based on the Qwen family.

> **Fully local operation** — the rule engine (KO/EN keyword dictionary) runs 100% offline with no API key or cloud. The LLM tier is optional; add a key or connect a local LLM (Ollama/LM Studio) for better AI judgment.

Type a one-line topic (Korean OK), attach optional images and optional positive/negative conditioning, and **camera framing·lens·angle·lighting·grade·(video) motion** are composed automatically. Outputs are `positive_out` / `negative_out` conditioning, verification `prompt_out`, and main-reference passthrough `image_out`.

- Package folder: `ComfyUI-GoRi-camera-director`
- Node display name: `(GoRi) Camera Director Skills`
- Outputs: `positive_out` (`CONDITIONING`), `negative_out` (`CONDITIONING`), `prompt_out` (`STRING`), `image_out` (`IMAGE`)
- `clip` is the text encoder of your final Qwen Image model.
- `vae` is optionally connected for original reference conditioning. For Qwen-Image 2.1 / Qwen Image Edit identity preservation, connecting reference images together with `vae` is recommended. 2.1 RGBA (4-channel) input passes alpha straight through to the VAE.
- Do NOT connect the Qwen prompt rewriter's `CLIP` to `clip`. Connect the Qwen `positive_prompt` **string** to `prompt_in`, and the final model CLIP to `clip`.
- The `positive` conditioning input is kept for backward compatibility but ignored on the new standard path. It is ignored to stop a wrong-CLIP conditioning from changing faces.
- `negative` conditioning is optional. Your existing negative is preserved, then only camera/video failure modes are added.
- `image_1`–`image_10` are camera-hint / vision-LLM inputs, and the elected main reference is passed through as `image_out`.
- **Progressive input slots**: only the `image_1` slot shows by default; each connection reveals the next one (e.g. connect `image_7` → `image_8` appears). Slot hiding is display-only and never affects saved-workflow link compatibility.
- Connected `image_N` numbers are preserved as-is in LLM notes and reference guards. Connecting only `image_3` never compresses it into `image_1`.
- With 2+ reference images, the role planner elects the main subject (first connected image unless specified otherwise), and extra images are guarded to serve **only explicitly requested** roles among `background / prop / product / style / lighting / composition / mood`.
  - `outfit` was removed from that default list. With an empty topic there is no "requested role" to pick, so the model was free to choose — and real testing showed it copying the **clothing off a pose reference**. Clothing is only transferred when the topic assigns an outfit role, and that path has its own dedicated guard. Unassigned secondary images never contribute face, hair, skin, identity, or clothing.
- **Character sheet pixel detection (no topic needed)**: the node reads **repeatedly arranged views directly from the pixels** of a reference and treats it as a single-person character sheet (both horizontal and vertical layouts). It fires even when the topic never says "character sheet" — real testing with an empty topic duplicated a one-person 6-view sheet into **two people**, and that information was already in the pixels with nobody reading it. On a positive match it attaches the sheet instruction (every view is the same person) plus `second person / duplicated characters / contact sheet` negatives, and logs `참조 이미지 3번에서 캐릭터 시트 패턴 감지`.
  - Thresholds are deliberately tight because a false positive is worse than a miss — misreading a photo as a sheet averages several views into several identities and fails quietly. Panels ≥3, spacing regularity ≥0.45 (panels are laid out as a grid), and **inter-panel content similarity ≥0.20** (the same subject repeated). The real reference sheet (10896×6800, 2 full-body + 4 head views) scores 0.95 / 0.414 and is detected; all 15 real photos are rejected (highest similarity 0.109). Single-person and two-person photos are never read as sheets.
  - The first criterion was "panels are evenly wide" and it was **wrong**: the real sheet's width ratio is 2.50, so it missed it. A full-body view and a head close-up are structurally different widths, so even widths are a coincidence rather than a property of a sheet. The detector now measures the actual definition — the same person repeated.
  - Detection is **independent of the image path**: the same file gives the same verdict whether it arrives as a ComfyUI tensor (BHWC) or a PIL image. Analysis downscaling targets 512, preserves aspect ratio, and matches the PIL path **pixel for pixel** — a single pixel of drift was enough to flip the verdict.
  - **Character sheets are excluded from the diffusion model and shown to the language model only.** Qwen-Image follows the *layout* of a reference image. Feeding a one-person 6-view sheet produced a **4-view sheet rendered verbatim**. The topic cannot fix this: writing "a single continuous photograph of one young woman" still produced 4 views, because the layout hint is pixel-level. So the sheet is shown to the LLM (for identity) and removed from the VAE reference. Re-verified with the same seed: **4 views → 1 person**.
  - How to use a sheet and the problems people hit are covered in **[2c. Character sheet rules](#2c-character-sheet-rules)**.
- The outfit-only guard is added only when `Image 2` is explicitly used as an outfit reference (e.g. outfit swap jobs). Merely mentioning `dress` or clothes in a scene description never triggers the outfit guard on cat/background/product scenes.
- **Pose reference**: a slot named as a pose source in the topic (`2번 이미지의 포즈를 따라`, `이미지 3의 자세`, `use pose from image 4`) is used for posture only. **Any slot 1~10**, and several at once (`3번과 7번 이미지의 포즈`). That slot is excluded from identity/outfit/object roles and is **dropped from the LLM vision input** — it reaches the image model through the pixel path only. Pose is a pixel signal, so the LLM does not need to see it, and seeing it costs time and leaks that person's face and clothing into the subject. Positive says "take only the posture, never their face/clothing/background"; negative names exactly those leaks.
  - Two-person poses work: `1번 이미지 여성 신원, 2번 이미지 남성 신원, 3번 여성 포즈, 4번 남성 포즈` gives each person their own pose. The remaining 1·2 are held by the duo anchor as two identities, and the LLM sees only those two.
  - **Just write the number plus what they are doing.** `2번은 포즈만`, `2번 앉은 자세`, `2번 손에 든 상태`, `3번 서 있는 모습`, `2번 leaning` are all recognised as pose slots — no role noun required. The noun form (`이미지 2의 포즈`) keeps working too.
  - Connecting images alone does nothing for pose — the pose role must be stated in the topic. (Character sheets are the exception: they are detected from pixels.) No new widget.
- **Outfit swap**: just write the numbers — `2 의상, 1 교체` (same style as pose). The `이미지` label is optional. Accepted: `2 의상, 1 교체` · `2번 의상, 1번 교체` · `2 의장, 1 적용` · `2번 옷, 1번 변경` · `2번 의장을 1번에 입혀` · `1번에 2번 의장을 입혀` · `2번 의장을 1번 인물에게 입히고` · `이미지 2 의상을 이미지 1에 적용`. Outfit words include `의상`·`옷`·`옷차림`·`의장`·`생활복`·`드레스`·`원피스` and similar.
  - **The first number is the outfit source, the last number is the swap target.** `2 의상, 1 교체` means "put the outfit from slot 2 on the person in slot 1". The order does not matter (`1번에 2번 의장을 입혀` is the same thing).
  - **The target is never treated as an outfit source.** If the target number were counted as an outfit source, that person would be excluded from the identity source and the **subject would disappear from the output** — so source and target are judged separately.
  - When an outfit word is followed by a **wearing verb** (`2번 드레스를 입은 여성`), that slot is the **person wearing it**, not an outfit source (excluding them from the identity source would delete them).
  - Connecting images alone does nothing for outfit — the role must be stated in the topic. No new widget.
- **Physics & space guard**: contact/action wording in the topic (`벽에 밀어붙였다`, `던진다`, `안고 있다`, `붙잡고 끌어당긴다`, `부딪친다`, `달리고 있다`, `공격한다`) is translated into an image-side physical state on both sides. "Pressed against the wall" becomes "bodies touching with no gap, weight visibly transferred" on positive and "standing apart, no contact" on negative. Throw / run / fall / impact also get mid-action framing (airborne posture, contact shadow, center of gravity), while still scenes get `no motion blur` instead so the subject does not smear. Ordinary people scenes with no contact wording still get the minimum physics (contact shadow, center of gravity). Not applied to animal, product, or landscape scenes.
  - This guard does **not** produce exact joint angles — that is ControlNet OpenPose territory. Its job is to move the model's convergence point away from "two figures standing side by side" toward actual contact, flight, or impact. No new widget.
- **Three common failures with reference images, defended against**:
  - **Part-level detail boundaries** — auto-attached when the topic is a person and 1+ reference is connected. Real testing showed legs, arms and shoulders turning mushy in reference runs, which is *not* blur (focus) but **eroded part boundaries**, so it gets its own wording (legs separate from each other and from the background, arms from the torso, finger joints, knee/elbow lines, fabric weave and seams). Not applied to text-only generation.
  - **Furniture / prop DNA** — auto-attached to **every secondary slot** except the main subject, additional people, and pose references. You do not need to write "use the bed from image 2". Like people, furniture and props have a DNA: unless the user says otherwise, silhouette, material, colour, proportions, part count and in-frame position must match. Negative says "do not substitute a different object" plus **"near-miss furniture"** — because the more common failure is a *slightly* different colour, pattern or proportion. Slots explicitly marked mood/lighting-only (`분위기만`, `조명만`) are exempt.
  - **Removed-item remnants (the debris problem)** — always attached on people topics, no topic wording needed. Whether to remove something is the model's call; what must be blocked is **leaving a fragment**. Negative states a removed item is either fully gone or fully kept — half an object, a scrap, debris, or a floating accessory is always wrong. Clothing and accessory fragments are covered too, not just shoes.
- **Limb and digit counts** — always attached on people topics. Positive states `exactly five fingers on each hand (one thumb plus four) · five toes on each foot · two arms ending in two hands · two legs ending in two feet · both sides symmetrical · every limb separated from its neighbour`. Negative blocks the *actual* failure shapes rather than just "too many": fused fingers, fingers split down the middle, mitten hands, fingers merging into the palm, fused toes, feet merged into one blob, three arms, three legs — because a sixth finger is usually two fingers fused or one split, not an extra one.
  - **Limit (honest)**: text cannot *enforce* counts. A diffusion prior is a soft probability, so compliance is never guaranteed. The reliable paths are ① **KSampler denoise 0.4–0.6** (preserves the source hand pixels) ② **ControlNet OpenPose** ③ a detailer pass, in that order. This guard helps by not fighting ① — it asks the model to keep what the reference already got right.
- **denoise 1.0 caveat**: the preflight check warns. `denoise` is "how much to redraw", so 1.0 barely uses the source pixels and effectively regenerates from scratch. **0.6~0.8** is recommended to preserve reference shape, colour and detail. At 1.0 fine detail (legs, arms, shoulders, hands) degrades first and furniture drifts far from the reference.
- **Pixel spacing measurement (no topic needed)**: with 2+ reference images and no action wording in the topic, the node measures the **distance between subjects and the bottom margin** straight from the reference pixels (numpy only, no new dependency). Close → "stay in contact", measurably apart → "keep that separation", bottom margin → "keep the same amount of floor visible". So the reference's spatial relationship survives even if you never type "pressed against the wall". The console prints the measurement, e.g. `픽셀 공간 측정 (간격 0% · 영역 1개 · 근접 · 하단 여백 8%)`.
  - The gap is graded in three steps: touching / apart / **far apart at opposite frame edges** (two people at the left and right edges get a "wide empty space" instruction, not a "moderately separated" one). Vertically stacked arrangements (lying, stairs, top-down) are detected separately and get a "do not align them on the same level" instruction. Two touching people are detected by counting two heads; silhouette width is deliberately not used because a close-up single person measured wider (0.50) than a touching pair (0.44) in testing.
  - Limit: without segmentation it only reads **how far apart** things are. How many people, and whether it is a fight or an embrace, is left to the topic text. External segmentation models (YOLO-World, SAM, GrabCut) are deliberately not used — install friction and GPL-3.0 licensing; this node stays dependency-free.
- If the topic already names a camera shot (`full-body shot`, `close-up shot`, `wide shot`, …), your shot wins over the default camera shot.
- On people-reference image scenes, a `face and body preservation guard` is added. It keeps the original face structure, pelvis/hip/shoulder/waist ratios, and skin tone, and stops background color from spilling onto skin. Not applied to product/cat/background-only scenes.
- `prompt_out` carries a generic positive quality guard: natural skin, normal human proportions, five fingers, natural face, identity consistency.
- With image input, original-preservation phrases are added too (`same facial structure / same hairstyle / same outfit / same body proportions`).
- No external pip packages required; vision input conversion uses ComfyUI's own `PIL`/`torch`/`numpy`.

---

## 1. Install

```
ComfyUI/
└── custom_nodes/
    └── ComfyUI-GoRi-camera-director/   ← copy this whole folder
```

1. Copy this folder into `ComfyUI/custom_nodes/`
2. Restart ComfyUI (`Start ComfyUI.bat`)
3. Add-node menu → **HF Skills / Camera** → **`(GoRi) Camera Director Skills`**

## 2. Basic wiring — KSampler via the conditioning director

```text
Qwen Prompt Rewrite.positive_prompt ── prompt_in ────────────────→ GoRi Camera Director Skills.prompt_in
Final Qwen model Text Encode CLIP ─────────────────────────→ GoRi Camera Director Skills.clip
Original reference image ─────────────────────────────────→ GoRi Camera Director Skills.image_1
Final Qwen model VAE ───────────────────────────────────→ GoRi Camera Director Skills.vae
Hi-res/MP latent generator ──────────────────────────────→ GoRi Camera Director Skills.latent_image
Final model Text Encode negative ── negative ───────────────────→ GoRi Camera Director Skills.negative

GoRi Camera Director Skills ── positive_out ──────────────────→ KSampler.positive
GoRi Camera Director Skills ── negative_out ──────────────────→ KSampler.negative
GoRi Camera Director Skills ── prompt_out ────────────────────→ Show Text / debugging
```

> **Important:** `positive_prompt` is a `STRING`, not conditioning. This node merges the Qwen prompt and camera phrases into one string, then encodes once with the final model CLIP. The old path of joining `positive` conditionings with `+` is no longer used.

`positive_out` and `negative_out` are the real conditioning outputs for KSampler. `prompt_out` is a human/debug/verification string.

- If `text` is a widget: right-click → **Convert widget to input**, then connect the `prompt_out` line.
- On recent ComfyUI, dragging `prompt_out` over `text` converts it into an input slot.
- `positive_out`: with `prompt_in` connected, merges Qwen `positive_prompt`, a short reference identity anchor, and camera phrases into one string, encoded once with the final CLIP. The identity anchor is added only with people references; original reference latents travel via connected reference images + `vae`. Single-person anchors and duplicate negatives don't apply to explicit multi-person scenes, and duplicate suppression is skipped on window/mirror/reflection scenes. Pelvis/body measurement phrases never go into the public Qwen path. `positive` conditioning is ignored on the new path.
- `negative_out`: keeps your existing negative conditioning if connected, then only merges camera/video failure modes. On the single-reference path only `multiple people`, `duplicate person`, `cloned person`, `mirrored twin`, `background person` are added for duplicate suppression. However, on a human topic (or when the topic is empty and there is no basis to judge) the shared base block is always added: anatomy, identity and skin-tone contamination guards (`extra arms`, `face mismatch`, `plastic waxy skin`, `background color spill on skin`, ...). Both paths (base/Skills) use the same shared block. Negative is encoded text-only without vision, so Qwen Vision encoding runs once for positive only, and `reference_latents` attach to positive only. LLM-suggested extra negatives (llm tier) are merged after the camera negatives.
- On the `prompt_in` standard path, the outfit-only guard is added when outfit-swap intent is explicit with 2+ images, and with multiple images one secondary-reference role-restriction sentence is added. Single images get no role guards.
- Naming two people across 2 images (e.g. `Image 1's woman and Image 2's man facing each other`) switches to the 2-person duo guard. Slots 3–8 are recognized the same way (`Image 3's man`, `Image 8's woman`, …). `Exactly one main person` suppression, duplicate-person negatives, and role restrictions are all dropped; identity-preservation phrases for those slots go in instead. A two-way body-separation phrase blocks the two bodies merging into one or limbs getting mixed. Outfit-swap phrases are never mistaken for duo.
- On the standalone path (`prompt_in` disconnected), positive gets face/body/outfit legacy guards, while negative carries only camera failure modes by current policy. For two-sided positive defense, connect `prompt_out` to a separate CLIPTextEncode and reinforce negative yourself.
- The `규칙 (auto)` tier reads shot/lens/angle/lighting/motion/speed keywords. Words like `네온 (neon)`, `노을/석양 (sunset)`, `스튜디오 (studio)`, `실루엣/역광 (silhouette)`, `어두운/심야/야간 (dark)`, `화사한 (bright)` decide lighting. A bare everyday `밤 (night)` alone never flips to low-key (false-positive guard; extendable via the `keywords_ko_en.json` dictionary).
- `latent_image` is optional. Even with 2MP/2.5MP/3MP real sampling latents connected, reference conditioning is capped at 1MP. Without it, the 1MP cap applies from input image size.
- At high resolution, vision tensors and VAE latents of identical reference images are cached by content-hash + target-size key, never recomputed on repeat runs. This speeds up reference conditioning.
- At 3MP+, KSampler steps, preview, and VAE decode dominate total time. When speed matters, generate at 2–3MP first, then upscale.
- Video (I2V): `motion` is selectable. `image_1`–`image_10` are prompt-judgment inputs only, so connect the original `LoadImage` output straight into the I2V node for the start frame.
- Compound motion: pick a second move in `motion2` to combine two camera moves (e.g. push-in + pan). Empty = single motion. Carries into video-model conditioning and H3 prompts as-is.

### Two prompt input paths (usable together)

| Path | How | Trait |
|---|---|---|
| **topic field** | Type directly (Korean OK) | Widget **always stays** — keeps being used unless you wire a line |
| **prompt_in slot** | Wire from an external/AI text node | Overrides the topic field **only while connected**; auto-falls back when unplugged |

> **Important:** this conditioning director is a general-purpose node. `clip`, `positive`, and `negative` must all be same-family CLIP/conditioning matching your final model. Qwen models → Qwen-family CLIP; Flux/SDXL → their own CLIP. Mixing CLIPs across models can break faces/skin.
>
> 💡 For **finished prompts** from outside, `automation = 수동 (manual)` is recommended (original preserved + camera clauses only)
> - Console `in=topic 칸` / `in=외부(prompt_in)` tells you which side was used

> ⚠ **Images connected with an empty topic**: there is nothing telling the node what each reference is *for* (character sheets are detected from pixels; pose and person roles are not). It then falls back to `image_1` = main subject, the rest = background/composition/lighting only, and copies no face or clothing. The console logs `⚠ topic 이 비어 있어 참조 이미지의 역할을 구분하지 못했습니다`. Name the roles to get them followed, e.g. `2번은 포즈만, 3번은 1인 캐릭터 시트`.

## 2b. Output contract

| Output | Type | Goes to | Description |
|---|---|---|---|
| `positive_out` | `CONDITIONING` | `KSampler.positive` | Qwen prompt + people-reference identity anchor + camera phrases, encoded once. `positive` conditioning is ignored |
| `negative_out` | `CONDITIONING` | `KSampler.negative` | Keeps existing negative conditioning if any; only camera/video failure modes merged |
| `prompt_out` | `STRING` | `Show Text` / other prompt-rewrite nodes | Debug string identical to the real positive string |
| `image_out` | `IMAGE` | I2V start frame / upscale / Preview Image | The role planner's elected main reference (first connected if unelected), passed through. Empty when unconnected |
| `reference_latent_out` | `LATENT` | pass-2 correction node / straight into VAE Decode | VAE latent of the same slot as the main reference (cache lookup, no re-encode). Empty without `vae` |

With `prompt_in` connected, the Qwen prompt and camera phrases merge into one string, encoded once with the final model CLIP. Without `prompt_in`, a topic-based standalone prompt is encoded once. `positive` conditioning is ignored on the new path. Connecting `negative` conditioning preserves your negative, then adds only camera/video failure modes.

### IMAGE inputs

- `image_1`–`image_10` are optional, same style as other multi-reference conditioning nodes.
- `규칙 (auto)` uses the first connected image for brightness/contrast/saturation camera hints.
- `AI 판단 (llm)` packs all connected images into a base64 list for multi-vision delivery to supporting providers.
- With multiple images, the role planner's elected main subject (defaults to `Image 1`) stays fixed, and extra images serve only requested roles among background/outfit/props/product/style/lighting/composition/mood. Main person, face, body, clothes, product, and background subjects are never duplicated.
- **Mix guard**: connecting 2+ images auto-adds fusion/identity-mixing defenses to positive·negative — outfit references are treated as a separate clothing layer over the body, with original body-ratio/skin/face/hair/pose preservation plus negative defenses like "clothing fusion with skin, mixed facial features, identity blending". (Console `믹스 가드 활성` log.) Clashing light flow between references (one left-lit, one right-lit) raises a console warning — automatic, pixel-grounded, no settings.
- While feeding prompt judgment, the elected main reference image also passes through as `image_out` — wire it straight into an I2V start frame or upscale node.

### Pre-flight (doomed-combo warnings)

Copy your KSampler values into `pf_steps`·`pf_cfg`·`pf_denoise` as-is
(0 skips the check) for console warnings before the run:

| Field | Copy from | e.g. |
|---|---|---|
| `pf_steps` | KSampler `steps` | 20 |
| `pf_cfg` | KSampler `cfg` | 3.5 |
| `pf_denoise` | KSampler `denoise` | 1.0 |

- Face close-up (ECU/CU) on a sub-1MP latent → face-melt warning
- steps/cfg outside 8–150 / 1.0–12.0 → instability warning
- denoise above 0.9 → drift-from-source warning
- Numbers only (clearing + OK shows NaN — retype 0)

Model ceilings and seed luck are out of scope. People topics also get
eye·teeth·ear·feet·joint anatomy defenses auto-added to both negatives.
Full-body people shots also get person-object scale coherence
(furniture/background ratio, perspective) on positive·negative.
Country names (Korea·Japan·USA…) add an origin-of-person phrase plus
varied individual features; without traditional intent, modern everyday wear
and anti-westernization / anti-costume / anti-homogenization defenses join
negative. No race-essential wording ("East Asian facial features") and no
gender words are used. It is skipped when a reference already fixes identity
or the topic already describes appearance. Region grouping only references the
FairFace 7-group taxonomy (CC BY 4.0, bias-measurement use); no dataset
labels or images are shipped.

The node does **not** infer nationality or ethnicity from the reference image —
a person's group is not guessed from their face. With a reference connected,
region wording is skipped and the identity-from-reference guard applies instead;
a region is only applied when the topic text names it.

Animal subjects (dog·cat·bird…) are detected separately: species/body
proportions (leg count, muzzle, ears, tail) and coat texture join positive,
while humanization (human hands, human face), mutated anatomy, breed caricature
and mascot costumes join negative. When people and animals share a scene, the
people guards take priority.

### LLM status light

Running `AI 판단 (llm)` makes the `model` field **blink green while the LLM works** — local LLMs (Ollama/LM Studio) can take tens of seconds, so you can tell "computing" from "stuck". After judgment the green holds briefly then fades (success); on failure with rule fallback it turns **red** (reason also in console). Rule/manual tiers never light it. Lights reset on each new run.

### llm_hint — short instructions to the LLM

The `llm_hint` field near the bottom takes short composition·lighting·mood·scene instructions, applied top-priority to LLM judgment (e.g. `어두운 무드, 클로즈업 위주, 비 오는 장면`). Applies only to the **AI 판단 (llm)** tier; ignored on rule/manual tiers (console note). Empty = same as before.

Runs using `llm_hint` get a censorship-artifact defense auto-added to negative (`censored, mosaic, bar censor, pixelated, modest`) — suppresses the image model's tendency to sanitize or mosaic expressions on its own. No hint = no defense.

## 2c. Character sheet rules (character sheet / turnaround)

A **character sheet** is one image that shows the *same* person from several angles — typically front and back full body, close-up head front and back, left and right profiles. This node detects sheets automatically and attaches an identity-consistency guard — **you do not need to write anything in the topic.**

### Why it needs dedicated handling

| Observed problem | What the node does |
|---|---|
| A 1-person sheet came back as **two people** | States that the repeated views are the *same* person + negative blocking "views counted as separate people" |
| The sheet itself (grid, labels, panels) got rendered | Positive says "the output is ONE photograph" + negative names the *result form* (several angles side by side) |
| Four views were drawn even with a scene in the topic | The sheet goes to the **language model only** and is excluded from the VAE reference path (see below) |

> You cannot win this with prompt wording. Qwen-Image style models copy the **layout** of the reference latent, so the sheet slot is removed from the VAE path and passed only to vision (the language model). Without this, four views come out.

### How to use it

1. **Connect the sheet to any of `image_1`~`image_10`.** The slot number does not matter — it is found from pixels and named correctly.
2. **The topic may stay empty.** Empty is the safest option (writing a scene description leaves room to misread it as "show me several angles"). Detection still works.
3. You can connect other references (pose, background, props) alongside it. Sheet slots are separated out as the identity source, and pose/object slots keep their own roles.
4. With several images connected, **all of them** may be detected as sheets. If you mix a plain identity photo with a sheet, putting the identity photo in slot 1 is the most predictable arrangement.

Recognised topic phrases:
`캐릭터 시트` · `캐릭터시트` · `턴어라운드` · `삼면도` · `다면도` · `다각도` · `정면후면` · `전신 다각도` · `시트 참고` · `character sheet` · `turnaround` · `multiple angles of the same` · `model sheet` · `reference sheet`

### Two different things

| Kind | Topic phrases | Meaning |
|---|---|---|
| **1-person sheet** (default) | `캐릭터 시트`, `턴어라운드`, `삼면도` … | Repeated views are **all the same one person** → identity lock |
| **Multi-person sheet** | `여러 캐릭터`, `라인업`, `다캐릭터`, `인물 시트`, `cast sheet`, `ensemble sheet`, `오디션 시트` … | Each panel is a **different character** → handled separately |

A multi-person sheet misread as 1-person gets an "all views are the same person" instruction, which makes the output wrong. If your image holds several *different* characters, write one of the multi-person phrases.

### Pixel detection criteria (reference)

Images are analysed even with an empty topic. All three must hold:
- **3 or more** panel divisions
- division spacing uniformity **≥ 0.45**
- average cross-panel similarity **≥ 0.20** (real sheet ≈ 0.41, real photos ≤ 0.11)

A sheet with **uneven** cut spacing may not be detected. Write `캐릭터 시트` in the topic in that case.

### Common problems

| Symptom | Cause | Fix |
|---|---|---|
| More than one person in the result | Misread as a multi-person sheet | State `여러 캐릭터` or `캐릭터 시트` explicitly |
| Output looks like a sheet (grid, several angles) | Qwen reference latent path | Handled automatically. If a photo was caught instead, state `캐릭터 시트` |
| Sheet not detected automatically | Criteria not met (uneven spacing) | Write `캐릭터 시트` in the topic |
| Wrong sheet slot named | — | Pixel detection names the slot; without detection the first slot is used |

> **tip.** The sheet slot is passed to the language model (vision) but **excluded from the VAE reference**, so the image model never sees the sheet as pixels — identity arrives through the text path, and the sheet layout is not reproduced.

## 3. Usage (3 automation tiers)

| tier | Behavior | When |
|---|---|---|
| **규칙 (auto)** default | KO/EN keyword dictionary camera pick (offline·free·no API key) | Default — works with no key |
| **AI 판단 (llm)** | LLM expands the topic into an English scene + auto camera (optional advanced feature) | When you have a key and want the smartest result |
| **수동 (manual)** | Dropdown values used as-is | Full manual control |

> Default automation is `규칙 (auto)`. 100% local/offline with no API key. To expand Korean topics into English scenes, switch to `AI 판단 (llm)` and set provider·model·api_key. Failed llm calls auto-fall-back to rules.

**Preset priority:** `specific preset` > `직접 설정 (custom)` (dropdowns) > `자동 (auto)` (tier judgment)
- e.g. preset=`시네마틱 인물` + tier=`llm` → **camera=preset-locked, LLM expands only the scene**

**Console log (Korean):**
```
📷 Camera Director | tier=llm preset=자동 (auto) source=LLM 판단 | shot=근접 (CU) lens=85mm f/1.4 ... | scene=LLM 확장
```

## 4. LLM setup (pick one for tier=llm)

| provider | default model | key |
|---|---|---|
| OpenAI | `gpt-4o-mini` | node `api_key` field or `OPENAI_API_KEY` env |
| Anthropic | `claude-3-5-haiku-latest` | `api_key` or `ANTHROPIC_API_KEY` |
| Gemini (free tier) | `gemini-1.5-flash` | `api_key` or `GEMINI_API_KEY` — free at [Google AI Studio](https://aistudio.google.com/) |
| OpenRouter (many free models) | `google/gemini-flash-1.5` | `api_key` or `OPENROUTER_API_KEY` — `:free` model names (e.g. `meta-llama/llama-3.2-90b-vision-instruct:free`) allowed |
| Groq (free tier) | `llama-3.2-90b-vision-preview` | `api_key` or `GROQ_API_KEY` |
| DeepSeek (cheap) | `deepseek-chat` | `api_key` or `DEEPSEEK_API_KEY` |
| Mistral (free tier) | `pixtral-12b-2409` | `api_key` or `MISTRAL_API_KEY` |
| Ollama (local·free) | `llama3.2` (your installed model) | no key — just `ollama serve` running |
| LM Studio (local·free) | model loaded in LM Studio | no key — start **Local Server** in LM Studio (port 1234) |
| Custom (OpenAI-compatible) | none — type the endpoint's model name in `model` | key optional — keyless gateways allowed |

- **Gemini:** free keys at [Google AI Studio](https://aistudio.google.com/). `gemini-1.5-flash` free tier handles image judgment.
- **OpenRouter:** one key for many providers. `:free`-suffixed models (e.g. `meta-llama/llama-3.2-90b-vision-instruct:free`) are **fully free**. OpenAI/Anthropic names pass through uncorrected.
- **Groq:** free tier, very fast. Use a vision model (`llama-3.2-90b-vision-preview`) for image judgment.
- **DeepSeek/Mistral:** cheap/free tiers. For image judgment use a vision model like Mistral's `pixtral-12b-2409`.
- **LM Studio:** search·download·load a model in the GUI app, turn on its Local Server. Type the loaded name (e.g. `qwen2.5-vl`) in `model` to call it; empty routes to the currently loaded model. For image judgment (llm tier + images) use a vision model like `qwen2.5-vl`.
- **Custom (OpenAI-compatible):** any API aggregator/local gateway works with just a Base URL. ① provider = `Custom (OpenAI 호환)` ② `custom_base_url` = Base URL (e.g. `https://api.example.com/v1` — `/chat/completions` auto-appended, trailing slash/full URL OK) ③ `model` = that endpoint's model name (required) ④ `api_key` optional (keyless local gateways allowed). Plain OpenAI chat-completions spec, so vision (image judgment) works; `localhost`/`127.0.0.1` Base URLs get the local timeout (300s).

> ⚠️ Keys typed into the node's `api_key` field are **always recorded blank** in saved workflow JSON
> (the run payload reads live values directly; files use serialize output).
> Still double-check before sharing/backing up; the root **`.env` file** is recommended.
> The screen shows `●●●●●●●●` (also masked while typing); typed values still run as-is.
> Saved workflow files always record the `api_key` slot blank.
> Reopening a save shows an empty key field — retype the key or use the root `.env` file / env vars.
> Generated images (PNG metadata) also carry no key — the node wipes only its own `api_key` from the server record at runtime. Sharing images alone is safe.
> Stray nodes with no outputs connected export no key into run records, and
> muted/bypassed nodes are excluded from the run list, keeping live values so unmuting restores them.
> (Unexecuted nodes — bypassed/disconnected — are not server-scrubbed, so check before sharing.)
> Before sharing a workflow: right-click the node → **api_key 지우기 (공유용)** to clear the key (disabled when already empty).

### Root .env key file (recommended)
Write per-provider keys in a `.env` memo at the very top ComfyUI folder and runs work with an empty `api_key` field:
```
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
```
- Typing a key and pressing OK in the dialog auto-saves it into that provider's slot; clearing + OK deletes it (closing with Esc applies nothing)
- Priority: field input > `.env` file > OS environment variables
- `.env` lives outside the node folder, so folder-zip sharing never carries keys along
> No key or dead network → **auto rule(auto) fallback** (runs always succeed)

### No API key travels with a shared workflow — with one exception

**Moving the key to `.env` is enough.** Type it into the `api_key` field and press
**OK** in the dialog: it is written to the root `.env` and **the field empties
itself.** Saved from there, no file carries the key.

```
type key + OK      →  stored in .env  →  field empties  →  saving and sharing are both clean
type key + Esc     →  nothing applied at all (cancel)
```

`Save` / `Save As` / `Export` blank `api_key` during serialization, so they are
**safe even with the field still filled in.**

> ⚠️ **Exception: `Export (API)`**
> An API-format file is not a display workflow, it is the execution request itself
> (`{"nodeId": {"class_type": "...", "inputs": {...}}}`). That format puts values
> straight into `inputs`, so the save-time blanking does not reach it.
>
> - The eight common providers (OpenAI·Anthropic·Gemini·OpenRouter·Groq·DeepSeek·Mistral)
>   empty the field automatically, so **you have to do nothing.**
> - `Custom` · `Ollama` · `LM Studio` have no `.env` slot, so the value stays put.
>   Only for these, clear the field before `Export (API)`.
> - In a hurry: right-click the node → **`api_key 지우기 (공유용)`**.

> 💡 **Model-name auto-fix:** switching providers with a stale name
> (`gpt-4o-mini` etc.) still in `model` auto-corrects to that provider's
> default with a console warning. Empty `model` always uses the provider default.
> Ollama·Groq·DeepSeek·Mistral correct only `gpt-`/`claude-`-prefixed names;
> other local names (`qwen2.5-vl` etc.) pass through.
> LM Studio·OpenRouter·Custom skip correction (too many name shapes) and use input as-is.

> 💡 **Local LLM timeouts:** Ollama/LM Studio can respond slowly
> (local vision inference takes tens of seconds to minutes), so call timeout is **300s**.
> Cloud providers (OpenAI/Anthropic/Gemini/OpenRouter/Groq/DeepSeek/Mistral) and
> remote Custom endpoints default to 45s; `localhost`/`127.0.0.1`
> Custom Base URLs get the local timeout (300s).

> 💡 **Direct setup + 자동 (auto):** with `preset=직접 설정`, dropdowns left at
> `자동 (auto)` follow tier (llm/auto/manual) judgment.
> Only explicitly picked items lock; a specific preset locks everything.

> 💡 **Composition → suggested lighting (rule engine):** angles/shots auto-suggest
> lighting without LLM — low angle/worm's-eye → rim light, Dutch tilt → low key,
> extreme/close-up → Rembrandt, medium close-up → window light, long/extreme-long → golden hour.
> Topic-keyword lighting, user-locked values, and manual tier win; suggestions apply only when undecided.

## 5. Customizing

| File | Purpose |
|---|---|
| `presets.json` | Edit/add preset combos (labels must match camera item labels) |
| `keywords_ko_en.json` | auto-tier KO/EN keyword dictionary — add entries freely |
| `SHOT/LENS/ANGLE/...` in `camera_director.py` | Change camera items and English clauses themselves |

## 6. Operating systems (Windows / macOS / Linux)

All three are supported and **verified in CI** (Windows, macOS and Linux x
Python 3.10/3.12).

- No external pip packages — only \	orch\, umpy\ and \PIL\, which ComfyUI
  already ships.
- All paths are built with \os.path\, so Windows backslashes and macOS/Linux
  slashes behave identically, including when the node folder is installed as a
  **symlink**.
- API keys written to \.env\ get permission 600 (owner-only) on Linux/macOS,
  and the file is replaced atomically, so a failure never destroys an existing
  key.
- On Apple Silicon (M1/M2/M3) there is no \mediapipe\ wheel, so the person
  mask and pose-based pixel checks switch off automatically. Everything else
  (lighting flow, spacing, reference lighting conflicts, edge analysis) uses
  only \	orch\/umpy\ and keeps working.
- CUDA (NVIDIA), MPS (Apple Silicon) and CPU all run without exceptions.

## 7. Verification checklist

- [ ] 1. Shows in the node list after install
- [ ] 2. `직접 설정 (custom)`+`85mm` etc. → English clauses in output
- [ ] 3. tier=llm + Korean topic → expanded into an English scene
- [ ] 4. llm run with no key → console fallback log + normal output
- [ ] **5. Same-seed A/B** (camera off/on) → visible framing/texture difference
- [ ] 6. Motion applied in video → camera move visible
- [ ] 7. Same-topic rerun → no LLM call (console cache)
- [ ] 8. Preset vs direct-setup behavior check
- Local logic pre-check: `python tests/test_node.py` (auto verification)

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Node missing | Check console errors → folder name/`__init__.py`, then restart |
| Can't drop a line onto `text` | Right-click widget → *Convert widget to input* (or drag auto-converts) |
| llm tier gives rule-level results | Check console `LLM 실패` message (key·model name·Ollama running?) |
| Topic (Korean) echoed in output | `auto/manual` tiers can't translate → switch tier to `llm` |
| Broken Korean glyphs in image text | Model lacks Korean (Flux/SDXL) → Qwen-Image family or separate overlay |
| `⚠ could not remove the API key from photo metadata` | ComfyUI did not inject `unique_id` as a hidden input, so the scrub was skipped. The node runs fine but **the key may remain in the saved PNG.** Use the node right-click → *Clear api_key (for sharing)*, or check your ComfyUI version |
| 📷 shows as `?` in console | Windows console codepage issue — output text itself is fine (cosmetic) |
| Quality/person drift on regen | See storyboard guide §8 below (fixed original reference + `manual` lock) |
| Plastic-looking skin | Drop `flawless/smooth` from the front prompt; grainy grades like `시네마틱 필릭`·`35mm 필름`. The node auto-adds pore/texture/directional-light/grain phrases on people scenes. For pore/peach-fuzz detail use lens `100mm 매크로` + people topic (not applied to products) |
| Smeared anatomy on exposure scenes | Exposure intent (`nude/나체` etc.) auto-adds clinical-completion (positive) and smear-guard (standalone negative). Caveat: explicit detail is bounded by model safety tuning — closer framing, even lighting, lower denoise, and higher resolution help more |

## 9. Storyboard chains (quality·consistency)

Chaining (reusing each output as the next reference) is a **copy of a copy** — quality and identity drift a little every generation (VAE round-trip loss + resampling + Edit-model reinterpretation). For consistent storyboards:

**Rule: references always the first original, settings locked for all cuts**

1. **Lock the original** — from cut 2 on, keep connecting the **first original** (source photo / first PNG), never the previous cut. Chaining accumulates loss.
2. **Use saved PNGs** — preview drags and JPGs are lossy by themselves. Connect `SaveImage` PNG files via `LoadImage`.
3. **Lock `automation = manual` + preset** — `auto` shifts lighting/grade from input-image stats, `llm` rewrites the scene every time. Same preset (or `직접 설정 (custom)`) on every cut keeps the look.
4. **Lock slot numbers** — same person on the same `image_N` every cut (e.g. this series: 1=lead, 2=support, everywhere). Renumbering points identity/duo anchors at the wrong person. When the combo changes mid-series (1·2 women duo → 1 man + 2 woman etc.), apply the new numbering rule to all cuts from the changed cut on.
5. **Same resolution** — same latent size on all cuts. The node caps references at 1MP, so changing base resolution changes reference detail.
6. **Low denoise on regen** — higher Edit/second-pass denoise drifts further from the original (KSampler-side setting).
7. **Only prompts change per cut** — backgrounds·actions·lines via `prompt_in`/topic only; hands off camera·people·settings.

## 10. Credits·License

- Camera prompt composition rules: `higgsfield-ai/skills` (MIT) — prompt-engineering / thumbnail house-structure / video explainer blocks
- 5 camera angles (POV·reflection·panoramic·three-quarter rear·wide hero): `xoxxel/camera-prompts` (MIT) — English keywords and effect descriptions adapted to this node's format (Korean label + English clause)
- This node: MIT (same as the source)
