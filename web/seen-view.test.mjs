// node web/seen-view.test.mjs : "What the referee saw" (SAM 3.1 Evidence Lens) panel checks. Built Oct 27 2026.
import { readFileSync } from "node:fs";
import { verifyReceipt } from "../upstream/qortime/verify/verify.js";
import { checkSeen, lensState, lensColor, lensTag } from "./seen-view.js";

let fails = 0;
const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) fails++; };
const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const receipt = read("../examples/170123/receipt.json");
const seenDoc = read("../examples/170123/seen.json");
const v = await verifyReceipt(receipt, receipt.referee.pubkey);
const vJson = JSON.stringify(v);

// 1. Published seen.json is valid, bound to this receipt, and info-only.
const s = await checkSeen(seenDoc, receipt);
ok(s.ok, "published 170123 seen.json is valid and bound to the receipt " + JSON.stringify(s.problems));
ok(seenDoc.affects_verdict === false && seenDoc.emits_status === false, "seen.json carries no status and affects nothing");
ok(JSON.stringify(v) === vJson && v.status === "VERIFIED", "verifier output untouched (VERIFIED from verify.js only)");

// 2. Tampering / mis-binding is rejected.
const other = structuredClone(receipt); other.result.home_score = 31;
ok(!(await checkSeen(seenDoc, other)).ok, "seen.json bound to a different receipt is rejected");
const withStatus = structuredClone(seenDoc); withStatus.clips[0].status = "VERIFIED";
ok((await checkSeen(withStatus, receipt)).problems.some((p) => p.startsWith("forbidden_fields")), "a status field anywhere is rejected");
const withMasks = structuredClone(seenDoc); withMasks.clips[0].masks = [[1, 2]];
ok(!(await checkSeen(withMasks, receipt)).ok, "per-frame mask data is rejected");
const banned = structuredClone(seenDoc); banned.clips[0].segments[0].caption = "This clip is certified clean [seen.seq].";
ok(!(await checkSeen(banned, receipt)).ok, "banned wording in a caption is rejected");

// 3. Evidence Lens appears ONLY inside receipt event windows.
let outside = 0, inside = 0;
for (const c of seenDoc.clips) {
  for (let f = 0; f < c.frames; f++) {
    const t = f / c.fps;
    for (const e of c.lens_events) {
      const st = lensState(e, t, "VERIFIED");
      if (t < e.t0 || t >= e.t1) outside += st === null ? 0 : 1; else inside += st ? 1 : 0;
    }
  }
}
ok(outside === 0 && inside > 0, `lens only inside event windows (inside frames ${inside}, leaks ${outside})`);
const ev = seenDoc.clips[1].lens_events.find((e) => e.kind === "score_lock");
ok(lensState(ev, ev.t0 + 0.1).phase === "materialize" && lensState(ev, ev.t0 + 1).phase === "hold" && lensState(ev, ev.t1 - 0.1).phase === "dissolve", "materialize -> hold -> dissolve");

// 4. Gold only for a score lock on a VERIFIED receipt.
ok(lensColor("score_lock", "VERIFIED") === "gold", "score lock + VERIFIED = gold");
for (const st of ["PARTIAL", "FAIL", "SELF_ATTESTED", undefined]) ok(lensColor("score_lock", st) === "aqua", `score lock + ${st} = aqua`);
for (const k of ["motion_segment", "challenge"]) ok(lensColor(k, "VERIFIED") === "aqua", `${k} is never gold`);
ok(lensTag(ev, seenDoc.clips[1]).includes("[checkpoints.away[459]]"), "score-lock tag cites the receipt checkpoint");

process.exit(fails ? 1 : 0);
