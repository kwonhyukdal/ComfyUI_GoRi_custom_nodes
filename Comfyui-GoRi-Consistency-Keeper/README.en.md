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

Start with defaults (`strength_camera` 0.2 / `strength_original` 0.2).

| Symptom | Adjust |
|---|---|
| Face differs from original | Raise `original` to 0.5–0.6 |
| Composition/lighting off | Raise `camera` to 0.5–0.6 |
| Pasted-on / flat look | Lower both to 0.15–0.2 (over-pull) |
| Single reference only | Set the unused side to 0 or leave unconnected |

Adjust one at a time in 0.1 steps (raising both overcooks). Negligible
compute — no VRAM/speed worry.

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
