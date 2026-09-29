# 🛡️ (GoRi) Consistency Keeper

> 🌐 [한국어 버전](README.md)
>
> ☕ If this helped, buy me a coffee: [Donate via PayPal](https://paypal.me/GoRi57788)

Pulls KSampler output latents toward original/camera reference latents to
reduce identity/composition drift. **Does not redraw**
(no re-encode, no resampling).

## Wiring

```text
LoadImage → VAE Encode ── original_latent ──→ ┐
(GoRi) Camera Director Skills ── reference_latent_out ── camera_latent ──→ (GoRi) Consistency Keeper ── latent_out ──→ VAE Decode → SaveImage
KSampler ── LATENT ── sampled_latent ──→ ┘
Same VAE ── vae ──→ ┘ (hand masks, optional. Global pull without it)
```

## Widgets

| Widget | Default | Description |
|---|---|---|
| `strength_camera` | 0.2 | Direction pull (camera reference, -1.0–1.0) |
| `strength_original` | 0.2 | Original identity pull (-1.0–1.0) |

Negatives are **anti-reference** (push resemblance away). Large drift
auto-damps the pull ("fuse without deforming" — console notice).
Diverging light flow (Retinex-style low-frequency check) damps further.

## Body-masked pull (optional)

Wiring `vae` pulls the human region selectively (MediaPipe pose segmentation
mask — silent global pull without it, no settings). Background stays put,
whole body covered. Finger counts themselves can't be fixed (detailer territory).

0 skips that reference. Missing reference latents or batch/channel mismatches
are skipped with a console note. Different spatial sizes are matched with
bicubic resize.

## Tuning guide

> ### ⭐ Recommended: `camera` 0.33 / `original` 0.33
>
> **Real-world testing shows the same value (0.33) on both strengths is the most
> stable setting.** It keeps camera direction and original identity pulling at the
> same weight. Use this first, then adjust only from the table below.
> (The widget default is 0.2, but 0.33 is the verified practical optimum.)

| Value | When |
|---|---|
| **0.33 / 0.33** | **Default — most stable. Start here.** |
| 0.15–0.2 | Pasted-on or flat look (over-pull) |
| 0.45–0.6 | Strengthen one side specifically (`original` = face lock, `camera` = composition lock) |
| 0 / unconnected | Only one reference is in use |

| Symptom | Adjust |
|---|---|
| Face differs from original | Raise `original` to 0.45–0.6 |
| Composition/lighting off | Raise `camera` to 0.45–0.6 |
| Pasted-on / flat look | Lower both to 0.15–0.2 (over-pull) |
| Two people merging into one | Lower both to 0.15–0.2 |
| Single reference only | Set the unused side to 0 or leave unconnected |

Adjust one at a time in 0.05–0.1 steps (raising both high overcooks). Negligible
compute — no VRAM/speed worry.

## Automatic per-part detail restoration (no setting needed)

If the sampler output is mushier than the reference in a given part (hands,
legs, face), the node finds it from pixels and raises `original` strength for
that part only. Console example:

```
[GoRi Consistency Keeper] per-part restore boost (hand_left(89%), leg_left(72%))
— pulling the parts where the reference is intact but the result degraded
```

The "exactly five fingers" wording Camera Director puts in the prompt is not a
constraint diffusion can enforce. This node is the pixel-level catch for when
that wording fails.

Limit: a region is left alone when the reference itself has no detail there
(if the source cannot be trusted, restoring from it is just as wrong). It needs
MediaPipe for landmarks; without it the node quietly falls back to its existing
behaviour.

## Character sheet reference detection (no setting needed, detection + log only)

The node checks from pixels whether the `original` reference is a **character
sheet** (several views laid out in a row: front, back, close-up head, ...) and
picks the **single view** that best matches the sampled result. Console:

```
[GoRi Consistency Keeper] 6 panels detected in the original reference — looks like a character sheet
[GoRi Consistency Keeper]   best matching view: panel 3 (similarity 0.81)
[GoRi Consistency Keeper]   framing similarity 0.72 — pixels correspond, this view can be the identity source
```

- Camera Director sees the sheet as one blob, so per-view identity differences
  cannot be controlled from the prompt. This handles only that part.
- A false positive is worse than a miss (views would be averaged into several
  identities), so a sheet is only accepted with 3+ panels of regular width and
  spacing. Irregular photos are not treated as sheets.
- **Strength is not changed yet.** The judgement is logged first; panel-based
  identity sourcing comes in the next step.
- Without `mediapipe` the framing check is skipped and only the log remains.

## Operating systems (Windows / macOS / Linux)

All three are supported and verified in CI (ubuntu/windows/macos × Python
3.10/3.12). `torch` and `numpy` are already in the ComfyUI environment.
`mediapipe` is an optional dependency — without it those features simply
switch off.

This node **never touches the filesystem** — it only works on latent tensors,
so there is no path handling to differ between operating systems.

- **macOS Apple Silicon (M1/M2/M3)**: there is no mediapipe wheel, so the
  person mask switches off automatically. Per-part edge comparison, lighting
  flow and character sheet panel detection use only torch/numpy and keep
  working.
- CUDA, MPS (Mac) and CPU all run without exceptions.

## Batch input

With a batch of two or more images in `sampled_latent`, **only the global
pull** is applied. The person mask, per-part restoration and character sheet
analysis are single-image features and switch off automatically; the console
says so. Strength values still apply as given.

To process a batch, split the images and run one at a time, or lower the
strengths and rely on the global pull alone.

## Ghosting (double exposure) fix

Overlapping faces/bodies mean the reference and output poses differ.
Latent blending only holds for matched poses:

1. Match the reference image pose to the output (most reliable)
2. Lower strengths to 0.1–0.15
3. A console "poses differ greatly" warning means do one of the above

## Limits

- Consistency pull only. Won't redraw broken fingers and the like
  (that's detailer territory).
- Verify: `python tests/test_node.py`

## License

MIT. Methodology refs: PuLID paper (Apache 2.0), built-in LatentBlend.
No copied code — original implementation.
