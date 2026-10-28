// Challenge Echo panel (display layer). Built Oct 27 2026 during the Meta AI Developer Hackathon (Oct 26 - Nov 4 2026).
//
// echo.sidecar.json (qortime.echo.v0) is written by qortime_ai/echo. In the browser it is INFO-ONLY: the panel never
// changes the status verify.js computed (the file is unsigned, so it is not allowed to lower anything here either).
// A malformed file, or one bound to a different receipt, shows no panel. verify.js is unchanged.
export const ECHO_SCHEMA = "qortime.echo.v0";
const STATES = ["consistent", "partial", "mismatch", "unscorable"];

async function sha256Hex(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(d), (x) => x.toString(16).padStart(2, "0")).join("");
}

/** { ok, problems, clips, summary, boundTo } . Never throws. `canonicalize` = verify.js JCS (for receipt binding). */
export async function checkEcho(doc, receipt, { canonicalize } = {}) {
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return { ok: false, problems: ["not_an_object"] };
  const p = [];
  if (doc.schema !== ECHO_SCHEMA) p.push("bad_schema");
  if (doc.affects_verdict !== "lower_only" || doc.max_cap !== "PARTIAL" || doc.emits_status !== false) p.push("not_lower_only");
  const clips = Array.isArray(doc.clips) ? doc.clips : [];
  if (!clips.length || clips.some((c) => !c || !STATES.includes(c.status))) p.push("bad_clips");
  let boundTo = "none";
  if (doc.receipt_jcs_sha256) {
    if (!receipt || !canonicalize) p.push("cannot_check_binding");
    else if ((await sha256Hex(canonicalize(receipt))) !== doc.receipt_jcs_sha256) p.push("other_receipt");
    else boundTo = "this_receipt";
  }
  if (p.length) return { ok: false, problems: p };
  return { ok: true, problems: [], clips, summary: String(doc.summary || ""), boundTo, pattern: doc.pattern || [] };
}

/** Status is returned untouched: Echo is info-only in the viewer. */
export const applyEcho = (v) => v;

const median = (xs) => { const s = xs.filter((x) => Number.isFinite(x)).sort((a, b) => a - b); return s.length ? s[(s.length - 1) >> 1] : null; };

export function echoRows(e) {
  return e.clips.map((c) => ({ id: String(c.id), status: c.status, dirs: `${c.directions_matched | 0}/${c.directions_total | 0}`,
    latency: Number.isFinite(c.latency_median_ms) ? c.latency_median_ms : null, jitter: Number.isFinite(c.jitter_ms) ? c.jitter_ms : null,
    menu: !!(c.menu && c.menu.appeared), tracker: String(c.tracker || "") }));
}

/** Panel DOM, or null when there is nothing valid to show. Never gold, never a verdict. */
export function echoPanel(e, { title = "Challenge Echo" } = {}) {
  if (!e || !e.ok) return null;
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const sec = el("section", "panel reveal s-unchecked xc-panel echo-panel");
  sec.id = "p-echo"; sec.setAttribute("aria-label", title);
  const head = el("header"); head.append(el("h3", null, title)); head.append(el("span", "chip s-unchecked", "Info only")); sec.append(head);
  const rows = echoRows(e);
  const med = median(rows.map((r) => r.latency));
  sec.append(el("p", "xc-line", `${e.summary} Median press-to-pixel ${med ?? "-"} ms.`));
  const tbl = el("table", "echo-table");
  const hr = el("tr"); for (const h of ["Window", "Directions", "Latency (median)", "Jitter", "Menu after OPTIONS", "Echo"]) hr.append(el("th", null, h));
  tbl.append(hr);
  for (const r of rows) {
    const tr = el("tr");
    for (const v of [r.id, r.dirs, r.latency == null ? "-" : `${r.latency} ms`, r.jitter == null ? "-" : `±${r.jitter} ms`, r.menu ? "yes" : "no", r.status]) tr.append(el("td", null, v));
    tbl.append(tr);
  }
  sec.append(tbl);
  sec.append(el("p", "pnote", "Challenge Echo checks that the pause-menu highlight in the video follows the logged D-pad presses (Meta SAM 3.1 tracks the highlight; the matching is deterministic code). It is shown for information only here and does not change the result above. LEFT/RIGHT do nothing on this menu, so for them it only checks that the highlight stayed still."));
  return sec;
}
