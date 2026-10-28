# `web/`: browser panels for the signed advisory files

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026.** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../PROVENANCE.md).

Plain ES modules, no build step. The deterministic verdict always comes from the pre-existing `verify.js` (fetched
into `upstream/` by `scripts/fetch_upstream.sh`); these modules only show advisory panels and apply the lower-only guard.

| File | Role | Test |
|---|---|---|
| `ai-ruling-view.js` | "AI explanation · advisory" panel (signed Muse Spark text) | `ai-ruling.test.mjs` |
| `score-crosscheck-view.js`, `lower-only.js` | Muse Spark score cross-check; only "same status" or "VERIFIED → PARTIAL" accepted | `score-crosscheck.test.mjs` |
| `hands-view.js` | Show Your Hands panel | `hands.test.mjs` |
| `seen-view.js` | Evidence Lens canvas panel (reduced-motion = static frame) | `seen-view.test.mjs` |
| `echo-view.js` | Challenge Echo panel (info only) | `echo.test.mjs` |
| `advisory-fetch.js` | finds advisory files: a dropped file, the sibling of a same-origin `?receipt=` URL, or the referee's copy | `advisory-fetch.test.mjs` |
| `auto-pin.js` | verifier auto-pin of trusted referee keys ([`AUTO_PIN.md`](AUTO_PIN.md)) | `auto-pin.test.mjs` |
| `ai_advisory_keys.inc.js` | AI advisory key allowlist (mirror of `qortime_ai/ai_ruling/advisory_keys.json`) | — |
| `demo.html`, `demo-170123.mjs`, `advisory-panels.css` | local demo page and offline match-170123 demo | — |

```bash
npm test                     # 7 test files, 153 checks
node web/demo-170123.mjs     # offline demo on match 170123
python -m http.server 8000   # from the repo root, then open http://localhost:8000/web/demo.html
```
