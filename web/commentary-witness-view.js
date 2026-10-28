// Commentary witness (display layer). Built Oct 28 2026 during the Meta AI Developer Hackathon (Oct 26 - Nov 4 2026).
//
// commentary_witness.json (qortime.commentary_witness.v0) is written offline by qortime_ai/commentary/witness.py:
// Meta Muse Voice Transcribe turns the broadcast commentary into text, Meta Muse Spark lists the scoring plays the
// commentators call, and code compares them with the referee's locked scores. INFO ONLY, LOWER-ONLY:
//   * applied only when its AI advisory signature, advisory key, and receipt binding all check out;
//   * "broadcast agrees" keeps the status; "broadcast disagrees" turns VERIFIED into PARTIAL. Never raises, never FAIL;
//   * no valid sidecar, muted or absent commentary => "broadcast unchecked": status exactly as verify.js computed it.
// verify.js is unchanged; this adjusts only what the page displays. The referee decides; AI only explains.
import { advisorySignatureProblems } from "./ai-ruling-view.js";

export const CW_SCHEMA = "qortime.commentary_witness.v0";
export const CW_CODE = "commentary_witness_disagrees";
const BANNED = /attest|certif|guarantee|proo?f\s+of\s+(a\s+)?human\s+play|\bsettl(e|es|ed|ing|ement)\b|\b(bet|bets|betting|wager\w*|odds|parlay\w*|sportsbook\w*|gambl\w*)\b/i;

/** { ok, problems, cap, agree, disagree, checked, summary, models }. Never throws. */
export async function checkWitness(doc, receipt, opts = {}) {
  const p = await advisorySignatureProblems(doc, receipt, CW_SCHEMA, opts);
  if (p.length === 1 && p[0] === "not_an_object") return { ok: false, problems: p };
  if (doc.affects_verdict !== "lower_only" || doc.max_cap !== "PARTIAL") p.push("not_lower_only");
  if (doc.cap !== null && doc.cap !== "PARTIAL") p.push("bad_cap");
  const locks = Array.isArray(doc.locks) ? doc.locks : [];
  if ((doc.cap === "PARTIAL") !== locks.some((l) => l && l.result === "disagree")) p.push("cap_inconsistent");
  if (BANNED.test(`${doc.label || ""} ${doc.summary || ""}`)) p.push("wording");
  if (p.length) return { ok: false, problems: p };
  const n = (r) => locks.filter((l) => l && l.result === r).length;
  return { ok: true, problems: [], cap: doc.cap, agree: n("agree"), disagree: n("disagree"), checked: n("agree") + n("disagree"),
           summary: String(doc.summary || ""), models: { asr: String(doc.models?.asr || ""), extractor: String(doc.models?.extractor || "") } };
}

/** Copy of the verifier output with the witness applied (lower-only). Input is never mutated. */
export function applyWitness(v, cw) {
  if (!v || typeof v !== "object") return v;
  const out = { ...v, partial: [...(v.partial || [])] };
  if (!cw || !cw.ok) { out.commentary_witness = "unchecked"; return out; }
  if (cw.cap === "PARTIAL" && out.status === "VERIFIED") { out.status = "PARTIAL"; out.partial.push(CW_CODE); }
  out.commentary_witness = cw.cap === "PARTIAL" ? "disagrees" : cw.checked ? "agrees" : "unchecked";
  return out;
}

/** One line for the match page. cw may be null. */
export function witnessLine(cw) {
  if (!cw || !cw.ok || !cw.checked) return "Broadcast unchecked: no usable commentary for this match. No penalty.";
  return cw.cap
    ? `Broadcast disagrees: ${cw.disagree} of ${cw.checked} checked locked scores. Shown as PARTIAL, not VERIFIED. Info only.`
    : `Broadcast agrees: ${cw.agree} of ${cw.checked} checked locked scores. Info only; the referee decides.`;
}

/** Panel DOM (same chip states as the other advisory panels). */
export function witnessPanel(cw) {
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const state = !cw || !cw.ok || !cw.checked ? "unchecked" : cw.cap ? "partial" : "pass";
  const sec = el("section", `panel reveal s-${state} xc-panel cw-panel`);
  sec.id = "p-commentary-witness"; sec.dataset.state = state; sec.setAttribute("aria-label", "Commentary witness");
  const head = el("header"); head.append(el("h3", null, "Commentary witness"));
  const chip = el("span", `chip s-${state}`); const dot = el("i"); dot.setAttribute("aria-hidden", "true");
  chip.append(dot, state === "pass" ? "Broadcast agrees" : state === "partial" ? "Broadcast disagrees" : "Broadcast unchecked");
  head.append(chip); sec.append(head);
  sec.append(el("p", "xc-line", witnessLine(cw)));
  sec.append(el("p", "pnote", "Meta Muse Voice Transcribe transcribes the game's broadcast commentary; Meta Muse Spark lists the scoring plays the commentators call; code compares them with the referee's locked scores. A disagreement can only lower VERIFIED to PARTIAL. It never raises a status or fails a match. Signed by QorTime's AI advisory key, not a referee key."));
  return sec;
}
