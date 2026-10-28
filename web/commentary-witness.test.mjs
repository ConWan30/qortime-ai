// node web/commentary-witness.test.mjs : commentary witness, lower-only (built Oct 28 2026, in-window; see PROVENANCE.md).
import { readFileSync } from "node:fs";
import * as ed from "../upstream/qortime/verify/vendor/noble-ed25519.js";
import { canonicalize, verifyReceipt } from "../upstream/qortime/verify/verify.js";
import { checkWitness, applyWitness, witnessLine, CW_CODE } from "./commentary-witness-view.js";
import { acceptLowerOnly } from "./lower-only.js";

let fails = 0;
const ok = (c, m) => { console.log((c ? "ok   " : "FAIL ") + m); if (!c) fails++; };
const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const hex = (b) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
const unhex = (s) => Uint8Array.from(s.match(/../g).map((x) => parseInt(x, 16)));
const kidOf = async (pub) => hex(new Uint8Array(await crypto.subtle.digest("SHA-256", unhex(pub)))).slice(0, 16);
const without = (o, k) => Object.fromEntries(Object.entries(o).filter(([x]) => x !== k));
const priv = ed.utils.randomPrivateKey(), pub = hex(await ed.getPublicKeyAsync(priv));
const keys = { keys: [{ id: "t", pubkey: pub, key_kind: "qortime-ai-advisory", status: "active" }] };
async function resign(doc) {
  const d = { ...without(doc, "advisory_signature"), advisory_key: { ...doc.advisory_key, pubkey: pub, key_id: await kidOf(pub) } };
  d.advisory_signature = { alg: "Ed25519", key_id: await kidOf(pub), sig: hex(await ed.signAsync(new TextEncoder().encode(canonicalize(d)), priv)) };
  return d;
}

const receipt = read("../examples/170123/receipt.json");
const cwDoc = read("../examples/170123/commentary_witness.json");
const v = await verifyReceipt(receipt, receipt.referee.pubkey);
const vJson = JSON.stringify(v);

// 1. Published 170123 witness: valid (Python-signed, checked in JS), broadcast agrees, status stays VERIFIED.
const cw = await checkWitness(cwDoc, receipt);
ok(cw.ok && cw.cap === null && cw.agree === 3 && cw.disagree === 0, "published 170123 witness is valid and agrees 3/3");
ok(cw.models.asr === "muse-voice-transcribe-1.0" && cw.models.extractor === "muse-spark-1.3", "models recorded");
const a = applyWitness(v, cw);
ok(a.status === "VERIFIED" && a.commentary_witness === "agrees" && JSON.stringify(v) === vJson, "agreement keeps VERIFIED; verifier output not mutated");
ok(witnessLine(cw).startsWith("Broadcast agrees: 3 of 3"), "match-page line: broadcast agrees");

// 2. A signed disagreement lowers VERIFIED to PARTIAL, and only that.
const dis = structuredClone(cwDoc); dis.locks[0].result = "disagree"; dis.cap = "PARTIAL";
const cwd = await checkWitness(await resign(dis), receipt, { keys });
ok(cwd.ok && cwd.cap === "PARTIAL", "signed disagreement is accepted (test key)");
const ad = applyWitness(v, cwd);
ok(ad.status === "PARTIAL" && ad.partial.includes(CW_CODE) && ad.commentary_witness === "disagrees", "disagreement lowers VERIFIED to PARTIAL");
ok(acceptLowerOnly(v, ad).status === "PARTIAL", "page guard accepts VERIFIED -> PARTIAL");
for (const st of ["PARTIAL", "SELF_ATTESTED", "FAIL"]) ok(applyWitness({ ...v, status: st }, cwd).status === st, `disagreement leaves ${st} unchanged`);
ok(witnessLine(cwd).startsWith("Broadcast disagrees: 1 of 3"), "match-page line: broadcast disagrees");

// 3. Invalid or missing sidecars: broadcast unchecked, status exactly as verify.js computed it.
ok((await checkWitness(dis, receipt)).problems.includes("bad_advisory_signature"), "edited sidecar => bad signature => ignored");
ok(applyWitness(v, await checkWitness(dis, receipt)).status === "VERIFIED", "ignored sidecar => VERIFIED unchanged");
ok(applyWitness(v, null).commentary_witness === "unchecked" && witnessLine(null).startsWith("Broadcast unchecked"), "no sidecar => broadcast unchecked, no penalty");
const muted = structuredClone(cwDoc); muted.locks.forEach((l) => { l.result = "unchecked"; l.reason = "no_commentary_in_window"; });
const cwm = await checkWitness(await resign(muted), receipt, { keys });
ok(cwm.ok && applyWitness(v, cwm).status === "VERIFIED" && applyWitness(v, cwm).commentary_witness === "unchecked", "muted commentary => unchecked, never disagrees");
const other = structuredClone(receipt); other.result.home_score = 3;
ok((await checkWitness(cwDoc, other)).problems.includes("receipt_mismatch"), "witness for another receipt => ignored");
const failCap = structuredClone(dis); failCap.cap = "FAIL";
ok((await checkWitness(await resign(failCap), receipt, { keys })).problems.includes("bad_cap"), "a FAIL cap is never accepted");
const incons = structuredClone(cwDoc); incons.cap = "PARTIAL";
ok((await checkWitness(await resign(incons), receipt, { keys })).problems.includes("cap_inconsistent"), "cap without a disagreeing lock is rejected");
const notLower = structuredClone(cwDoc); notLower.affects_verdict = true;
ok((await checkWitness(await resign(notLower), receipt, { keys })).problems.includes("not_lower_only"), "must declare lower_only");
const wordy = structuredClone(cwDoc); wordy.summary = "Broadcast agrees; safe to bet on it";
ok((await checkWitness(await resign(wordy), receipt, { keys })).problems.includes("wording"), "gambling wording rejected");
ok(!(await checkWitness(await resign(dis), receipt)).ok, "validly signed by an unlisted key => ignored");
const asRef = structuredClone(receipt); asRef.referee.pubkey = pub;
ok((await checkWitness(await resign(dis), asRef, { keys })).problems.includes("advisory_key_is_a_referee_key"), "referee key can't sign a witness");
for (const bad of [null, 3, "x", [], {}]) ok(!(await checkWitness(bad, receipt)).ok, `malformed ${JSON.stringify(bad)} => ignored`);
const src = readFileSync(new URL("./commentary-witness-view.js", import.meta.url), "utf8");
ok(!/innerHTML|gold/i.test(src), "panel: no innerHTML, no gold");
const lines = [witnessLine(cw), witnessLine(cwd), witnessLine(null), src.match(/"Meta Muse Voice Transcribe[^"]*"/)[0]].join(" ");
ok(!/proof of human play|settle|attest|certif|\b(bet|odds|wager)\b/i.test(lines), "panel text: no banned claims, no gambling words");
process.exit(fails ? 1 : 0);
