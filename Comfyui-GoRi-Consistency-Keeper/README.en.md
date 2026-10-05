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
Same VAE ── vae ──→ ┘ (body mask, optional. Global pull without it)
```

`original_image` (IMAGE, optional) sets the original reference from an
image instead of a latent. Qwen Edit's latent output is an all-zero
empty canvas, so this is the accurate source there (takes priority).

## Widgets

| Widget | Default | Description |
|---|---|---|
| `strength_sampler` | 1.0 | Master gain on the whole correction. 1.0 = unchanged behaviour, 0.0 = pass-through (output = input), 0.5 = half applied. Negative inverts the correction |
| `strength_camera` | 0.2 | Direction pull (camera reference, -1.0–1.0) |
| `strength_original` | 0.2 | Original identity pull (-1.0–1.0) |
| `trust_gate` | False | Judgment gate. On: per-part detail restoration (the region boost) is applied only to body parts judged trustworthy in the original (pose + hand check) — damaged parts are blocked from the boost, impossible judgment keeps existing behaviour with a reason log. The base pull strength itself is unaffected by the gate. Off: existing behaviour |

Negatives are **anti-reference** (push resemblance away). Large drift
auto-damps the pull ("fuse without deforming" — console notice).
Diverging light flow (Retinex-style low-frequency check) damps further.

## Body-masked pull (optional)

Wiring `vae` pulls the human region selectively (MediaPipe pose segmentation
mask — without it a one-time notice is logged and the global pull runs, no
settings). Background stays put,
whole body covered. Finger counts themselves can't be fixed (detailer territory).

0 skips that reference. Missing reference latents or batch/channel mismatches
are skipped with a console note. Different spatial sizes are matched with
bicubic resize.

## Tuning guide

> ### ⭐ Recommended: `camera` 0.2 / `original` 0.2 (physical ceiling)
>
> The node caps each reference pull at a **measured physical ceiling of 0.20** —
> beyond it the result gets mushier than the original (correspondence-point
> measurement, 2026-09-28). When auto-damping is not active, any widget value
> above 0.20 **behaves identically to 0.20** and a "pull exceeded the physical
> ceiling" warning is logged on every run it is capped. Note: if the drift
> auto-damping (Widgets section) engages first and brings the effective pull to
> 0.20 or below, it passes without the ceiling warning.
> The formerly recommended 0.33 was effectively capped at 0.20 too. Start at
> 0.2 / 0.2 and only adjust downward from the table — raising is capped at 0.20.

| Value | When |
|---|---|
| **0.2 / 0.2** | **Starting point — the ceiling. Any value above 0.2 behaves the same.** |
| 0.15–0.2 | Pasted-on or flat look (over-pull) |
| 0 / unconnected | Only one reference is in use |

| Symptom | Adjust |
|---|---|
| Face differs from original | `original` up to the ceiling (0.2). If still not enough, the **automatic per-part restoration** (section below) handles it |
| Composition/lighting off | `camera` up to the ceiling (0.2) |
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
MediaPipe for landmarks; without it the node logs a one-time notice and falls
back to its existing behaviour.

## Character sheet reference detection (no setting needed)

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
  identities), so a sheet is only accepted with 4+ panels of even spacing.
  Irregular photos are not treated as sheets.
- When a sheet is detected, the best-matching panel replaces the original
  reference (stage A); if framing fails the gate, `strength_original` is
  halved (stage B).
- Without `mediapipe` the framing check counts as failed — the panel is not
  used as identity source and (B) `strength_original` is halved.

## Operating systems (Windows / macOS / Linux)

All three are supported and verified in CI (ubuntu/windows/macos × Python
3.10/3.12). `torch` and `numpy` are already in the ComfyUI environment.
`mediapipe` is an optional dependency — without it those features switch off
and the reason is logged to the console once.

This node only works on latent tensors and **reads** the bundled pose/hand
`.task` model files — it never writes files, so OS path differences do not
affect it.

- **macOS Apple Silicon (M1/M2/M3)**: there is no mediapipe wheel, so the
  person mask switches off automatically. Per-part edge comparison, lighting
  flow and character sheet panel detection use only torch/numpy and keep
  working.
- CUDA, MPS (Mac) and CPU all run without exceptions.

## Pose/hand detection models (mediapipe)

`mediapipe` is an optional dependency. The node uses the two `.task` model
files bundled in the node folder (`pose_landmarker_lite.task`,
`hand_landmarker.task`) by default; you can point to other model files with
the `GORI_POSE_MODEL` and `GORI_HAND_MODEL` environment variables.

One development-only diagnostic exists: setting `GORI_PROBE_PHYSICS=1`
enables extra logs that measure the physical direction of the pull — it
adds 3 extra VAE decodes per run (3x cost), so leave it off normally.

If the model files or mediapipe are missing, the person mask and the
pose/hand features stay off and only the global pull keeps working — the
reason is logged to the console **once** (not repeated on every run).

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

## Troubleshooting

**If every run logs `인체 마스크 없음 — 전역 당김으로 진행합니다` (person
mask missing — global pull):** the mask was not built. That line repeats on
every run, but the **root cause is logged once per process** on a separate
line (the repeating line does not point at it). Scroll up in the console and
look for one of these:

| Root-cause line (logged once) | Meaning |
|---|---|
| `인체 마스크·부위별 강도·프레이밍 판정이 꺼져 있다 ...` | mediapipe missing or the `.task` model files cannot be read — check the pose/hand model section above and the `GORI_POSE_MODEL` path |
| `⚠ person mask failed in _person_mask_from_rgb` | exception in the mask geometry — check the exception name/message that follows |
| `⚠ pose inference failed in ...` | exception while running pose inference — check the exception that follows |
| `pose input 변환 실패 ...` | exception converting the latent into a detector input — check the exception that follows |

If none of these lines appear, no person was detected (product shots,
distant figures) or the mask-side VAE decode failed. If it persists on
person images, check the `vae` connection. With batch input the mask
feature is off by design (see Batch input above).

## Limits

- Consistency pull only. Won't redraw broken fingers and the like
  (that's detailer territory).
- Verify: `python tests/test_node.py`

## License

MIT. Methodology refs: PuLID paper (Apache 2.0), built-in LatentBlend.
No copied code — original implementation.
