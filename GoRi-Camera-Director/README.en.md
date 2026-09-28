# 🎥 (GoRi) Camera Director Skills

> 🌐 [한국어 버전](README.md)

> **Full Qwen-Image 2.1 support** — works the same reference-latents way as the Text Encode Qwen Image 2.1 node. 10 reference image inputs, native RGBA (transparency) passthrough, use your 2K native workflow as-is.

> **Also usable with KREA 2 · MiniMax H3** — you can copy the camera-direction English prompt from `prompt_out` and paste it as-is.
> - **KREA 2** (image, Qwen3-VL encoder): paste the `prompt_out` text into the KREA 2 text encoder — shot·lens·lighting phrases carry over.
> - **MiniMax H3** (video, Hailuo): use the camera-move phrases built from the motion/speed fields as the H3 video prompt — handy for camera work in I2V.
> Direct conditioning connections (`positive_out`/`negative_out`) are based on the Qwen family.

> **Fully local operation** — the rule engine (KO/EN keyword dictionary) runs 100% offline with no API key or cloud. The LLM tier is optional; add a key or connect a local LLM (Ollama/LM Studio) for better AI judgment.

Type a one-line topic (Korean OK), attach optional images and optional positive/negative conditioning, and **camera framing·lens·angle·lighting·grade·(video) motion** are composed automatically. Outputs are `positive_out` / `negative_out` conditioning, verification `prompt_out`, and main-reference passthrough `image_out`.

- Package folder: `comfyui-GoRi-camera-director`
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
- With 2+ reference images, the role planner elects the main subject (first connected image unless specified otherwise), and extra images are guarded to only serve requested roles among `background / outfit / prop / product / style / lighting / composition / mood`.
- The outfit-only guard is added only when `Image 2` is explicitly used as an outfit reference (e.g. outfit swap jobs). Merely mentioning `dress` or clothes in a scene description never triggers the outfit guard on cat/background/product scenes.
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
     └── comfyui-GoRi-camera-director/   ← copy this whole folder
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
- `negative_out`: keeps your existing negative conditioning if connected, then only merges camera/video failure modes. On the single-reference path only `multiple people`, `duplicate person`, `cloned person`, `mirrored twin`, `background person` are added for duplicate suppression. `extra arms`, `face mismatch`, and skin-tone contamination guards are NOT added. Negative is encoded text-only without vision, so Qwen Vision encoding runs once for positive only, and `reference_latents` attach to positive only. LLM-suggested extra negatives (llm tier) are merged after the camera negatives.
- On the `prompt_in` standard path, the outfit-only guard is added when outfit-swap intent is explicit with 2+ images, and with multiple images one secondary-reference role-restriction sentence is added. Single images get no role guards.
- Naming two people across 2 images (e.g. `Image 1's woman and Image 2's man facing each other`) switches to the 2-person duo guard. Slots 3–8 are recognized the same way (`Image 3's man`, `Image 8's woman`, …). `Exactly one main person` suppression, duplicate-person negatives, and role restrictions are all dropped; identity-preservation phrases for those slots go in instead. A two-way body-separation phrase blocks the two bodies merging into one or limbs getting mixed. Outfit-swap phrases are never mistaken for duo.
- On the standalone path (`prompt_in` disconnected), positive gets face/body/outfit legacy guards, while negative carries only camera failure modes by current policy. For two-sided positive defense, connect `prompt_out` to a separate CLIPTextEncode and reinforce negative yourself.
- The `규칙 (auto)` tier reads shot/lens/angle/lighting/motion/speed keywords. Words like `네온 (neon)`, `노을/석양 (sunset)`, `스튜디오 (studio)`, `실루엣/역광 (silhouette)`, `어두운/심야/야간 (dark)`, `화사한 (bright)` decide lighting. A bare everyday `밤 (night)` alone never flips to low-key (false-positive guard; extendable via the `keywords_ko_en.json` dictionary).
- `latent_image` is optional. Even with 2MP/2.5MP/3MP real sampling latents connected, reference conditioning is capped at 1MP. Without it, the 1MP cap applies from input image size.
- At high resolution, vision tensors and VAE latents of identical reference images are cached by content-hash + target-size key, never recomputed on repeat runs. This speeds up reference conditioning.
- At 3MP+, KSampler steps, preview, and VAE decode dominate total time. When speed matters, generate at 2–3MP first, then upscale.
- Video (I2V): `motion` is selectable. `image_1`–`image_10` are prompt-judgment inputs only, so connect the original `LoadImage` output straight into the I2V node for the start frame.

### Two prompt input paths (usable together)

| Path | How | Trait |
|---|---|---|
| **topic field** | Type directly (Korean OK) | Widget **always stays** — keeps being used unless you wire a line |
| **prompt_in slot** | Wire from an external/AI text node | Overrides the topic field **only while connected**; auto-falls back when unplugged |

> **Important:** this conditioning director is a general-purpose node. `clip`, `positive`, and `negative` must all be same-family CLIP/conditioning matching your final model. Qwen models → Qwen-family CLIP; Flux/SDXL → their own CLIP. Mixing CLIPs across models can break faces/skin.
>
> 💡 For **finished prompts** from outside, `automation = 수동 (manual)` is recommended (original preserved + camera clauses only)
> - Console `in=topic 칸` / `in=외부(prompt_in)` tells you which side was used

## 2b. Output contract

| Output | Type | Goes to | Description |
|---|---|---|---|
| `positive_out` | `CONDITIONING` | `KSampler.positive` | Qwen prompt + people-reference identity anchor + camera phrases, encoded once. `positive` conditioning is ignored |
| `negative_out` | `CONDITIONING` | `KSampler.negative` | Keeps existing negative conditioning if any; only camera/video failure modes merged |
| `prompt_out` | `STRING` | `Show Text` / other prompt-rewrite nodes | Debug string identical to the real positive string |
| `image_out` | `IMAGE` | I2V start frame / upscale / Preview Image | The role planner's elected main reference (first connected if unelected), passed through. Empty when unconnected |

With `prompt_in` connected, the Qwen prompt and camera phrases merge into one string, encoded once with the final model CLIP. Without `prompt_in`, a topic-based standalone prompt is encoded once. `positive` conditioning is ignored on the new path. Connecting `negative` conditioning preserves your negative, then adds only camera/video failure modes.

### IMAGE inputs

- `image_1`–`image_10` are optional, same style as other multi-reference conditioning nodes.
- `규칙 (auto)` uses the first connected image for brightness/contrast/saturation camera hints.
- `AI 판단 (llm)` packs all connected images into a base64 list for multi-vision delivery to supporting providers.
- With multiple images, the role planner's elected main subject (defaults to `Image 1`) stays fixed, and extra images serve only requested roles among background/outfit/props/product/style/lighting/composition/mood. Main person, face, body, clothes, product, and background subjects are never duplicated.
- **Mix guard**: connecting 2+ images auto-adds fusion/identity-mixing defenses to positive·negative — outfit references are treated as a separate clothing layer over the body, with original body-ratio/skin/face/hair/pose preservation plus negative defenses like "clothing fusion with skin, mixed facial features, identity blending". (Console `믹스 가드 활성` log)
- While feeding prompt judgment, the elected main reference image also passes through as `image_out` — wire it straight into an I2V start frame or upscale node.

### LLM status light

Running `AI 판단 (llm)` makes the `model` field **blink green while the LLM works** — local LLMs (Ollama/LM Studio) can take tens of seconds, so you can tell "computing" from "stuck". After judgment the green holds briefly then fades (success); on failure with rule fallback it turns **red** (reason also in console). Rule/manual tiers never light it. Lights reset on each new run.

### llm_hint — short instructions to the LLM

The `llm_hint` field at the bottom takes short composition·lighting·mood·scene instructions, applied top-priority to LLM judgment (e.g. `어두운 무드, 클로즈업 위주, 비 오는 장면`). Applies only to the **AI 판단 (llm)** tier; ignored on rule/manual tiers (console note). Empty = same as before.

Runs using `llm_hint` get a censorship-artifact defense auto-added to negative (`censored, mosaic, bar censor, pixelated, modest`) — suppresses the image model's tendency to sanitize or mosaic expressions on its own. No hint = no defense.

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

## 6. Verification checklist

- [ ] 1. Shows in the node list after install
- [ ] 2. `직접 설정 (custom)`+`85mm` etc. → English clauses in output
- [ ] 3. tier=llm + Korean topic → expanded into an English scene
- [ ] 4. llm run with no key → console fallback log + normal output
- [ ] **5. Same-seed A/B** (camera off/on) → visible framing/texture difference
- [ ] 6. Motion applied in video → camera move visible
- [ ] 7. Same-topic rerun → no LLM call (console cache)
- [ ] 8. Preset vs direct-setup behavior check
- Local logic pre-check: `python tests/test_node.py` (auto verification)

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Node missing | Check console errors → folder name/`__init__.py`, then restart |
| Can't drop a line onto `text` | Right-click widget → *Convert widget to input* (or drag auto-converts) |
| llm tier gives rule-level results | Check console `LLM 실패` message (key·model name·Ollama running?) |
| Topic (Korean) echoed in output | `auto/manual` tiers can't translate → switch tier to `llm` |
| Broken Korean glyphs in image text | Model lacks Korean (Flux/SDXL) → Qwen-Image family or separate overlay |
| 📷 shows as `?` in console | Windows console codepage issue — output text itself is fine (cosmetic) |
| Quality/person drift on regen | See storyboard guide §8 below (fixed original reference + `manual` lock) |
| Plastic-looking skin | Drop `flawless/smooth` from the front prompt; grainy grades like `시네마틱 필릭`·`35mm 필름`. The node auto-adds pore/texture/directional-light/grain phrases on people scenes. For pore/peach-fuzz detail use lens `100mm 매크로` + people topic (not applied to products) |
| Smeared anatomy on exposure scenes | Exposure intent (`nude/나체` etc.) auto-adds clinical-completion (positive) and smear-guard (standalone negative). Caveat: explicit detail is bounded by model safety tuning — closer framing, even lighting, lower denoise, and higher resolution help more |

## 8. Storyboard chains (quality·consistency)

Chaining (reusing each output as the next reference) is a **copy of a copy** — quality and identity drift a little every generation (VAE round-trip loss + resampling + Edit-model reinterpretation). For consistent storyboards:

**Rule: references always the first original, settings locked for all cuts**

1. **Lock the original** — from cut 2 on, keep connecting the **first original** (source photo / first PNG), never the previous cut. Chaining accumulates loss.
2. **Use saved PNGs** — preview drags and JPGs are lossy by themselves. Connect `SaveImage` PNG files via `LoadImage`.
3. **Lock `automation = manual` + preset** — `auto` shifts lighting/grade from input-image stats, `llm` rewrites the scene every time. Same preset (or `직접 설정 (custom)`) on every cut keeps the look.
4. **Lock slot numbers** — same person on the same `image_N` every cut (e.g. this series: 1=lead, 2=support, everywhere). Renumbering points identity/duo anchors at the wrong person. When the combo changes mid-series (1·2 women duo → 1 man + 2 woman etc.), apply the new numbering rule to all cuts from the changed cut on.
5. **Same resolution** — same latent size on all cuts. The node caps references at 1MP, so changing base resolution changes reference detail.
6. **Low denoise on regen** — higher Edit/second-pass denoise drifts further from the original (KSampler-side setting).
7. **Only prompts change per cut** — backgrounds·actions·lines via `prompt_in`/topic only; hands off camera·people·settings.

## 9. Credits·License

- Camera prompt composition rules: `higgsfield-ai/skills` (MIT) — prompt-engineering / thumbnail house-structure / video explainer blocks
- This node: MIT (same as the source)
