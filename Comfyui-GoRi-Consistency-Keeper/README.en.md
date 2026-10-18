# 🛡️ (GoRi) Consistency Keeper

> 🌐 [한국어 버전](README.md)
>
> ☕ If this helped, buy me a coffee: [Support on PayPal](https://paypal.me/GoRi57788)

A second-pass node that **gently pulls the sampler's result toward the original
and camera references**, reducing identity and composition drift. **It does not
redraw** — no re-encoding and no resampling, only a latent pull.

```
Node name    (GoRi) Consistency Keeper
Menu         GoRi / Refine
Output       latent_out (LATENT)
```

---

## 1. Wiring

```text
KSampler ─────────────────── sampled_latent ─→ (GoRi) Consistency Keeper ─→ VAE Decode → SaveImage
Camera Director ── reference_latent_out ────→ camera_latent
Same original photo ────────────────────────→ image_1
Same VAE ───────────────────────────────────→ vae            (optional)
Camera Director ── prompt_out ──────────────→ camera_prompt  (optional)
```

- **`sampled_latent`** is the KSampler output. Place the keeper before Decode.
- **`camera_latent`** takes the camera node's `reference_latent_out` directly.
- **`image_1`** takes the **same original photo** you gave the camera node. The
  original reference is encoded from this image, which avoids using an empty
  latent as the reference.
- **`vae`** restricts the pull to the person area. Without it the whole frame is pulled.
- **`camera_prompt`** takes `prompt_out`. The keeper then reads instructions such
  as "change the outfit" or "change the background" and skips those areas.

---

## 2. Reference slots (`image_1` to `image_10`)

Connect the **same images under the same numbers** as on the camera node.
Different numbers mean the keeper pulls toward a different person. A new socket
appears each time you link one.

| Slot | Role |
|---|---|
| `image_1` | Main subject. Identity reference |
| `image_2` to `image_8` | Helper references. Pulled together from several originals |
| `image_9` to `image_10` | Appearance references. 9 pulls the upper body (shoulders), 10 pulls the lower body (hips) separately |

---

## 3. Widgets

| Widget | Default | Description |
|---|---|---|
| `strength_sampler` | 1.0 | Overall correction. 1.0 = as before, 0.0 = pass through (output = input), 0.5 = half |
| `strength_camera` | 0.2 | How hard to pull toward the camera reference |
| `strength_original` | 0.2 | How hard to pull toward the original |
| `trust_gate` | off | When on, the pose and hand verdict decides **which regions may be restored** |
| `repair_enable` | off | When on, regions judged damaged are pulled toward a corrected skeleton |

- Negative values pull **away** from a reference. Use them only deliberately.
- `trust_gate` and `repair_enable` are **opt-in**. Left off, only the basic pull runs.
- When `image_1` (the original) is connected, `strength_camera` is **not used for
  the pull** — the camera reference is for comparison only, because the original
  is the reference. Only without `image_1` does the camera reference take the
  original's place, and then this value applies.

---

## 4. Recommended settings

```
strength_sampler   1.0   (leave the default)
strength_camera    0.2
strength_original  0.2
```

**0.2 is effectively the ceiling for both strengths.** Values above 0.2 behave
the same as 0.2 and print a console note each run. Start at 0.2 and **lower it in
0.05-0.1 steps** while watching the result.

| Symptom | Adjustment |
|---|---|
| Face differs from the original | Check `strength_original`. If still short, the per-region restore handles it |
| Composition and lighting follow the sampler | Check `strength_camera` |
| Stiff, flat look | Lower both to about 0.15 |
| Two people merging into one | Lower both to about 0.15 |
| Using only one reference | Set the unused side to 0 |

Change one value at a time; raising both together overshoots. The operation is
cheap, so VRAM and speed are barely affected.

---

## 5. What it handles on its own

There is nothing to configure. It acts only where it is needed.

### Pulling only the person

With `vae` connected it selects the person and leaves the background alone. If
it cannot find a person it falls back to a global pull and says so once in the
console.

### Restoring smeared regions

It finds regions that came out softer than the original (hands, legs, face) and
pulls only those harder. If the original has no detail there, it leaves them alone.

### Tidying hands

Fused or overlapping fingers are pulled a few times **in the direction that
straightens them**. If nothing improves, the best state is kept. It cannot
create a missing finger — only relax what is bunched.

### Choosing a view from a character sheet

If the original reference is a character sheet (several angles in one image), it
picks the **single panel** that best matches the result as the identity source.
Averaging the whole sheet blends several faces. If no view matches well, the
pull strength is halved.

---

## 6. Batch input

When `sampled_latent` holds two or more images, **only the global pull** runs.
The body mask, per-region restore and character-sheet selection are single-image
features and turn off automatically, with a console note. Strength values still
apply.

To get per-region correction on a batch, run the images one at a time.

---

## 7. Ghosting (double image)

If faces or bodies appear doubled, the reference and the result have **different
compositions**. Blending latents only works when the composition matches.

1. Match the reference image to the result's composition and pose (most reliable).
2. Lower the strengths to 0.1-0.15.
3. If the console warns that the composition differs a lot, do one of the above.

The background is pulled along with the subject, so a mismatched background (for
example a chair in a different place) can leave a translucent double. The fix is
the same: match the composition. Telling the keeper about a scene change through
`camera_prompt` skips the background pull automatically.

---

## 8. Troubleshooting

**`인체 마스크 없음 — 전역 당김으로 진행합니다` (no body mask, using a global pull) keeps appearing**

The mask could not be built. This line repeats every run, but the **root cause is
printed only once**. Scroll up a little to find it.

| Console line | Meaning |
|---|---|
| `인체 마스크·부위별 강도·프레이밍 판정이 꺼져 있다` | `mediapipe` is missing or the model files cannot be read |
| `person mask failed` | Error while computing the mask. Check the message after it |
| `pose inference failed` | Error during pose inference. Check the message after it |
| `pose input 변환 실패` | Error converting the image. Check the message after it |

If no root-cause line appears, the image had no detectable person (product photo,
very distant figure) or `vae` is not connected. With a batch input, the mask
turning off is expected.

**The face drifts between runs**

Check that `image_1` holds the **original** photo. Feeding the previous output
back in makes a copy of a copy, and every generation drifts a little more.

---

## 9. Limits

- This node preserves consistency. Damage that has to be **redrawn**, such as six
  fingers, is out of scope (that is a detailer's job).
- Without `mediapipe`, the body mask, per-region restore and pose verdict turn
  off. Everything else (global pull, lighting-flow comparison, character-sheet
  panel detection) keeps working, and the reason is logged once.

---

## 10. License

MIT. Method references: the PuLID paper (Apache 2.0) and the built-in
LatentBlend. Implemented directly, with no copied code.
