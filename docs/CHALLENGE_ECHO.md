[← README](../README.md) · [Docs index](README.md)

# Challenge Echo — SAM 3.1, info only, lower-only

> Built Oct 27 2026, during the hackathon week. A mismatch can at most lower VERIFIED → PARTIAL; nothing else. The live referee and its challenge check are not changed.

**Built Oct 27 2026, during the hackathon week.** During a pause challenge the player presses OPTIONS, enters the
D-pad pattern on the pause menu, then selects Resume. `qortime_ai/echo/` checks that the **video follows the input
log**: every logged D-pad press must be followed by the matching move of the pause-menu highlight.
- **What SAM 3.1 does:** tracks the pause-menu highlight box. Only the menu window is sent, only the menu-list column
  (left 30 % × top 47 % of the frame, nothing player-identifying), at 30 fps; a **box prompt** on the first menu frame
  seeds one object and SAM propagates it forward. The track is the box's centre row.
- **What is deterministic code (not SAM):** press edges from `inputs.jsonl`; finding the highlight box that seeds the
  prompt; "menu appeared" (whole-frame luma goes dark after OPTIONS); the matching. A deterministic tracker (bright
  rows of the highlight box) is the fallback when SAM is off or fails, and a cross-check: on the practice set SAM and
  the fallback agree on 98–100 % of frames in 9 of 10 windows (72 % in the sloppy one, where a sub-menu opens).
- **Wrap test:** a jump counts as a wrap (DOWN on the last row → first row, UP on the first → last) when it is larger
  than one row step could produce: above 1.6 row pitches. The pitch is measured, deterministically, from the spacing of
  the menu's text rows outside the highlight box (median over frames across the menu window). One row step moves the
  box centre by about one pitch (up to ~1.3 when the highlighted row is taller), and the shortest wrap, in a 3-row
  list, is 2 pitches, so the test holds for any list length (the 7-row in-play menu and the 5-row menu alike). With no
  measurable pitch it falls back to the original fixed rule (1/6 of the frame height). Each clip reports
  `menu_geometry` (pitch, threshold, basis).
- **Matching:** DOWN/UP must move the highlight one row (wrap included) within ±100 ms of the window's common lag;
  LEFT/RIGHT do nothing on this vertical menu, so Echo only checks the highlight held still (counted, marked
  `visible: false`). Per press: press-to-pixel latency in ms. Per window: directions matched N of M, jitter, and
  whether the menu appeared after the OPTIONS press. Latencies are reported against the known 0.5–2.4 s capture/relay gap.
- **Effect:** `echo.sidecar.json` (schema `qortime.echo.v0`, integers only, next to the receipt; `receipt.v0.json` is
  untouched). `consistent` / `partial` / `unscorable` add a note only; `mismatch` can suggest VERIFIED → PARTIAL and
  nothing else (`qortime_ai/echo/sidecar.py`, tests). The browser panel (`web/echo-view.js`) is info-only and never
  changes the status. The live referee and its challenge check are not changed.

Practice run (10 pause challenges from one practice game, video and inputs kept private; aggregates in
`examples/practice-echo/echo.sidecar.json`): **8 consistent, 2 partial, 0 mismatch.** Median press-to-pixel per window
0.94–1.70 s, jitter inside a window ≤ 44 ms. The sloppy window (D-pad DOWN pressed six times, no LEFT/RIGHT/UP) comes out
`partial`, 1/4 directions; its six DOWN presses all line up with six highlight moves. One other window is `partial`
because the private extract has no release reports, so two quick DOWN presses read as one. The offset between the
video and input clocks was calibrated from the OPTIONS → pause-menu latency (see the sidecar's `clock`); absolute
latencies move with that offset, the jitter inside a window does not. The video also showed that the logged bit
8192 is DOWN (not LEFT), as in `hands/track.py`. Cost: SAM 3.1, 1,571 frames ≈ $0.31 including one probe.
```bash
META_API_KEY=... python -m qortime_ai.echo VIDEO inputs.jsonl --video-start-us T0 --pattern LEFT,DOWN,RIGHT,UP \
  --receipt receipt.v0.json --cache /private/cache --ledger spend.jsonl      # --no-sam = deterministic tracker only
```
Tests: `tests/test_echo.py` (synthetic presses, tracks and a drawn synthetic video), `web/echo.test.mjs`.
