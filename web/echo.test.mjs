// node web/echo.test.mjs : Challenge Echo panel (built Oct 27 2026, Meta AI Developer Hackathon). SYNTHETIC docs.
import { readFileSync, existsSync } from "node:fs";
import { checkEcho, applyEcho, echoRows } from "./echo-view.js";

let fails = 0;
const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) fails++; };
const doc = { schema: "qortime.echo.v0", affects_verdict: "lower_only", max_cap: "PARTIAL", emits_status: false,
  receipt_jcs_sha256: null, pattern: ["LEFT", "DOWN", "RIGHT", "UP"], summary: "1 consistent, 1 partial, 0 mismatch, 0 unscorable of 2 challenge window(s).",
  clips: [{ id: "s1", status: "consistent", directions_matched: 4, directions_total: 4, latency_median_ms: 1210, jitter_ms: 20, menu: { appeared: true }, tracker: "sam-3.1" },
          { id: "s2", status: "partial", directions_matched: 1, directions_total: 4, latency_median_ms: null, jitter_ms: null, menu: { appeared: true }, tracker: "sam-3.1" }] };

const e = await checkEcho(doc, null);
ok(e.ok && e.boundTo === "none", "synthetic echo sidecar is valid, unbound");
ok(echoRows(e)[0].dirs === "4/4" && echoRows(e)[1].latency === null, "rows: directions and latency");
for (const s of ["VERIFIED", "PARTIAL", "FAIL"]) ok(applyEcho({ status: s }, e).status === s, `info-only: ${s} unchanged`);
ok(!(await checkEcho({ ...doc, affects_verdict: "raise" })).ok, "rejects a non-lower-only file");
ok(!(await checkEcho({ ...doc, clips: [{ id: "x", status: "VERIFIED" }] })).ok, "rejects a clip claiming a verdict");
ok(!(await checkEcho({ ...doc, receipt_jcs_sha256: "00" }, { a: 1 }, { canonicalize: JSON.stringify })).ok, "rejects a file bound to another receipt");
ok(!(await checkEcho(null)).ok && !(await checkEcho([])).ok, "rejects non-objects");
const pub = new URL("../examples/practice-echo/echo.sidecar.json", import.meta.url);
if (existsSync(pub)) {
  const p = JSON.parse(readFileSync(pub));
  ok((await checkEcho(p, null)).ok, "published practice echo sidecar is valid");
  ok(!/attested|hardware.verified|t_us/i.test(JSON.stringify(p)), "practice sidecar: no banned words, no raw timeline");
}
if (fails) { console.log(`${fails} failure(s)`); process.exit(1); }
console.log("echo panel: all ok");
