[← README](../README.md) · [Docs index](README.md)

# What the referee saw — SAM 3.1 Evidence Lens

> **Visualization only, not a referee input.** Built Oct 27 2026, during the hackathon week. The referee and receipt it visualizes are pre-existing (QorTime @ `0e87ec3`).

Built Oct 27 2026, in the event window. `qortime_ai/seen/` chains the deterministic referee into Meta SAM 3.1 video
tracking on QorCap's three **public** match-170123 highlight clips (12 s each):
1. **Box prompt = the referee's own scorebug OCR region** (`madden27_standard`, 640×360: 8,340–485,359), forward
   propagation, one object id. Reports, per chain segment, how many frames the scorebug stayed *in place* (≥ 50 % of the
   OCR region inside SAM's mask), how far its anchor edges moved, and any dropouts / swaps. hl00 and hl01: 359/359 and
   360/360 frames in place, anchor moves ≤ 2 px. hl02: in place on 249/360 frames, until 8.3 s (the lock is at 8.0 s); the game then swaps
   in a "scoring drive" graphic and SAM's object leaves the OCR region — shown, not judged.
2. **Concept prompt "football player"** used ONLY to split the referee's own frame-difference energy (as in
   `motion_series`) into players / HUD / rest of screen. Aggregate percentages only — never per-player data, routes,
   speeds or play quality. On these clips most motion energy is camera and field movement (players 0–21 % per segment).
3. **`examples/170123/seen.json` (schema `seen.v0`)**: receipt JCS sha256, segment seqs + segment sha256s from the
   highlight manifest, SAM model and prompt types, summary numbers, Muse Spark captions, and the sha256 of each rendered
   overlay. No per-frame masks or boxes, no status field; receipt.v0 is unchanged. The receipt does not publish which
   segments the motion rule's random draw sampled, so seen.json says these are the chain segments the clips cover.
4. **Muse Spark 1.3** writes one caption per segment citing seen.json / receipt fields in `[brackets]`; the red-team
   citation checker + banned-word filter + a "not a coach" lint run after the model, with a template fallback.
5. **Evidence Lens render** (`python -m qortime_ai.seen … --render DIR`): a holographic box that materializes
   (corner brackets, glow, one scanline sweep, ~300 ms), follows SAM's track, and dissolves (~400 ms) **only inside
   receipt event windows** — the score-lock checkpoint (tag `SCORE READ AWAY 9–HOME 0 · [checkpoints.away[459]]`), the
   lock's segment (`MOTION SEGMENT 448 · players 9% · [signals.motion_permille.away]`) and any challenge window. Aqua by
   default; **gold only for a score lock when the pre-existing verifier returns VERIFIED**. Corner label:
   "SAM 3.1 · visualization, not a referee input". Web: `web/seen-view.js` (canvas lens, reduced-motion = static frame),
   shown at the bottom of `web/demo.html`; tests in `web/seen-view.test.mjs` and `tests/test_seen.py`.
Sample: `examples/170123/seen/` (stills + the 3.2 MB hl01 overlay). Cost: SAM 3.1 6 × 360 frames ≈ $0.43; Spark captions
≈ $0.05. Paid steps: `python -m qortime_ai.seen.fetch` (SAM, outputs cached outside the repo) and `--spark`.
