// Demo (Node, offline): check the public VERIFIED match 170123 the way the browser does.
// 1. The verdict comes ONLY from the pre-existing verifier (upstream verify.js, fetched by scripts/fetch_upstream.sh).
// 2. Event-built code then: auto-pins a trusted referee key, checks the three signed advisory files
//    (Muse Spark explanation, Muse Spark score cross-check, Show Your Hands) and applies the lower-only rule.
// No network, no API key. Built during the Meta AI Developer Hackathon (Oct 26 - Nov 4 2026).
import { readFileSync } from "node:fs";
import { verifyReceipt } from "../upstream/qortime/verify/verify.js";
import { autoPinFor } from "./auto-pin.js";
import { checkAiRuling } from "./ai-ruling-view.js";
import { checkCrosscheck, applyCrosscheck } from "./score-crosscheck-view.js";
import { checkHands, applyHands } from "./hands-view.js";
import { checkWitness, applyWitness, witnessLine } from "./commentary-witness-view.js";
import { acceptLowerOnly } from "./lower-only.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const receipt = read("../examples/170123/receipt.json");

const auto = await autoPinFor(receipt);
const v0 = await verifyReceipt(receipt, auto.pin);
console.log(`verdict (verify.js, deterministic): ${v0.status}   referee key auto-pinned: ${auto.pin ? "yes (" + auto.source + ")" : "no"}`);

const xc = await checkCrosscheck(read("../examples/170123/score_crosscheck.json"), receipt);
const hands = await checkHands(read("../examples/170123/hands.json"), receipt);
const cw = await checkWitness(read("../examples/170123/commentary_witness.json"), receipt);
const v = acceptLowerOnly(v0, applyWitness(applyHands(applyCrosscheck(v0, xc), hands), cw));
console.log(`after lower-only advisory signals:  ${v.status}${v.status === v0.status ? " (unchanged)" : " (lowered)"}`);
console.log(`Muse Spark score cross-check:       ${xc && xc.ok !== false ? JSON.stringify(xc.summary ?? xc) : "hidden (" + (xc?.problems || []).join(",") + ")"}`);
console.log(`Commentary witness (info only):    ${cw.ok ? witnessLine(cw) : "hidden (" + cw.problems.join(",") + ")"}`);
console.log(`Show Your Hands:                    ${hands && hands.ok !== false ? JSON.stringify(hands.summary ?? hands) : "hidden (" + (hands?.problems || []).join(",") + ")"}`);

const ai = await checkAiRuling(read("../examples/170123/ai_ruling.json"), receipt, v0.status);
console.log("\nMuse Spark explanation (advisory, signed by the AI advisory key, never a referee key):");
console.log(ai.ok ? ai.text : `hidden (${ai.problems.join(",")})`);
