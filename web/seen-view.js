// "What the referee saw" — SAM 3.1 Evidence Lens panel (display layer). Built Oct 27 2026 during the Meta AI Developer
// Hackathon (Oct 26 - Nov 4 2026).
//
// seen.json (schema seen.v0) is written by qortime_ai/seen: SAM 3.1 tracks the scorebug from the referee's own OCR region
// (box prompt) and "football player" masks split the frame-difference energy into players / HUD / rest. It is
// VISUALIZATION ONLY: it never feeds the referee, carries no status, and this panel never changes what verify.js shows.
// The Evidence Lens appears only inside receipt event windows (score lock, challenge window, the lock's segment).
// Colours: aqua by default; gold ONLY for a score lock when the verifier's own status is VERIFIED.
import { canonicalize } from "../upstream/qortime/verify/verify.js";

export const SEEN_SCHEMA = "seen.v0";
export const CORNER_LABEL = "SAM 3.1 · visualization, not a referee input";
export const MATERIALIZE_S = 0.3, DISSOLVE_S = 0.4;
const FORBIDDEN_KEYS = new Set(["status", "verdict", "cap", "max_cap", "masks", "boxes", "per_frame", "frames_data"]);
const BANNED = /attest|hardware[\s_-]*(verified|backed|proof|proven|secured)|certif(ied|y)|guarantee|cheat[\s_-]*(free|proof)/i;

const hex = (b) => Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("");
async function sha256Hex(s) { return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s))); }

function findForbidden(o, path = "") {
  if (Array.isArray(o)) return o.flatMap((v, i) => findForbidden(v, `${path}[${i}]`));
  if (o && typeof o === "object") {
    return Object.entries(o).flatMap(([k, v]) => (FORBIDDEN_KEYS.has(k) ? [`${path}.${k}`] : []).concat(findForbidden(v, `${path}.${k}`)));
  }
  return [];
}

/** { ok, problems, clips }. Never throws. Binding: receipt_jcs_sha256 must match this receipt. */
export async function checkSeen(doc, receipt) {
  const p = [];
  if (!doc || typeof doc !== "object") return { ok: false, problems: ["not_an_object"] };
  if (doc.schema !== SEEN_SCHEMA) p.push("bad_schema");
  if (doc.affects_verdict !== false || doc.emits_status !== false) p.push("must_be_info_only");
  if (!String(doc.label || "").includes("not a referee input")) p.push("missing_label");
  const bad = findForbidden(doc);
  if (bad.length) p.push("forbidden_fields:" + bad.slice(0, 3).join(","));
  try {
    if (!receipt || doc.receipt_jcs_sha256 !== await sha256Hex(canonicalize(receipt))) p.push("receipt_mismatch");
  } catch { p.push("receipt_mismatch"); }
  const clips = Array.isArray(doc.clips) ? doc.clips : [];
  if (!clips.length) p.push("no_clips");
  for (const c of clips) for (const s of c.segments || []) if (BANNED.test(String(s.caption || "").replace(/\[[^\]]*\]/g, " "))) p.push(`banned_word:${s.seq}`);
  return { ok: p.length === 0, problems: p, clips };
}

/** Lens colour: gold only for a score lock on a VERIFIED receipt. */
export function lensColor(kind, verifierStatus) { return kind === "score_lock" && verifierStatus === "VERIFIED" ? "gold" : "aqua"; }

/** Mirrors qortime_ai/seen/lens.py. null outside [t0, t1). */
export function lensState(ev, t, verifierStatus) {
  const t0 = Number(ev.t0), t1 = Number(ev.t1);
  if (!(t0 <= t && t < t1) || t1 <= t0) return null;
  const dur = t1 - t0, m = Math.min(MATERIALIZE_S, dur / 2), d = Math.min(DISSOLVE_S, dur / 2);
  const color = lensColor(ev.kind, verifierStatus);
  if (t < t0 + m) { const p = (t - t0) / m; return { phase: "materialize", p, alpha: p, color }; }
  if (t >= t1 - d) { const p = (t - (t1 - d)) / d; return { phase: "dissolve", p, alpha: 1 - p, color }; }
  return { phase: "hold", p: (t - t0 - m) / Math.max(dur - m - d, 1e-9), alpha: 1, color };
}

export function lensTag(ev, clip) {
  if (ev.kind === "score_lock") return `SCORE READ AWAY ${ev.score?.away}–HOME ${ev.score?.home} · [${ev.cite}]`;
  if (ev.kind === "motion_segment") {
    const s = (clip?.segments || []).find((x) => x.seq === ev.seq);
    return `MOTION SEGMENT ${ev.seq}${s ? ` · players ${s.motion_pct.players}%` : ""} · [${ev.cite}]`;
  }
  return `CHALLENGE WINDOW · [${ev.cite}]`;
}

const COLORS = { aqua: "#2EE6D6", gold: "#E8B84A" };

/** Draw one lens frame on a 2D context sized w x h (box_ref is in 640x360 space). */
export function drawLens(ctx, ev, st, w, h, clip) {
  if (!st || !Array.isArray(ev.box_ref)) return;
  const sx = w / 640, sy = h / 360, pad = 5;
  const [x1, y1, x2, y2] = [ev.box_ref[0] * sx - pad, ev.box_ref[1] * sy - pad, ev.box_ref[2] * sx + pad, Math.min(ev.box_ref[3] * sy + pad, h - 2)];
  const col = COLORS[st.color], a = st.alpha, grow = st.phase === "materialize" ? Math.max(st.p, 0.05) : 1;
  const L = Math.max(4, Math.min(x2 - x1, y2 - y1, 40) * 0.45 * grow);
  ctx.save();
  ctx.globalAlpha = a; ctx.strokeStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 14; ctx.lineWidth = 2.5;
  for (const [cx, cy, dx, dy] of [[x1, y1, 1, 1], [x2, y1, -1, 1], [x1, y2, 1, -1], [x2, y2, -1, -1]]) {
    ctx.beginPath(); ctx.moveTo(cx + dx * L * 2, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + dy * L); ctx.stroke();
  }
  ctx.globalAlpha = a * 0.7; ctx.lineWidth = 1.2; ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
  ctx.globalAlpha = a * 0.08; ctx.fillStyle = col; ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
  if (st.phase === "materialize") {
    const y = y1 + (y2 - y1) * st.p; ctx.globalAlpha = 0.9; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x2, y); ctx.stroke();
  }
  if (st.phase !== "materialize" || st.p > 0.5) {
    const tag = lensTag(ev, clip); ctx.shadowBlur = 0; ctx.font = "12px ui-monospace, monospace";
    const tw = ctx.measureText(tag).width + 14, ty = y1 - 26 > 2 ? y1 - 26 : y2 + 6, tx = Math.min(Math.max(x1, 4), w - tw - 4);
    ctx.globalAlpha = a * 0.85; ctx.fillStyle = "#0B1020"; ctx.fillRect(tx, ty, tw, 20);
    ctx.globalAlpha = a; ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.strokeRect(tx, ty, tw, 20);
    ctx.fillStyle = col; ctx.fillText(tag, tx + 7, ty + 14);
  }
  ctx.restore();
}

/** Panel DOM. seen = checkSeen() result. opts: { verifierStatus, stillUrl, stillClip, stillT, reducedMotion }. */
export function seenPanel(seen, opts = {}) {
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const sec = el("section", "panel reveal seen-panel"); sec.id = "p-seen"; sec.setAttribute("aria-label", "What the referee saw (SAM 3.1)");
  const head = el("header"); head.append(el("h3", null, "What the referee saw")); head.append(el("span", "chip seen-chip", "visualization only"));
  sec.append(head);
  if (!seen || !seen.ok) { sec.append(el("p", "pnote", "No valid seen.json for this receipt.")); return sec; }
  const clip = seen.clips.find((c) => c.id === opts.stillClip) || seen.clips[0];
  if (opts.stillUrl && typeof HTMLCanvasElement !== "undefined") {
    const wrap = el("div", "seen-stage"), img = el("img"), cv = el("canvas");
    img.src = opts.stillUrl; img.alt = "Public 170123 highlight frame"; wrap.append(img, cv, el("span", "seen-corner", CORNER_LABEL));
    sec.append(wrap);
    const reduce = opts.reducedMotion ?? (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
    const t = Number(opts.stillT ?? clip.lock?.t_s ?? 0);
    const evs = (clip.lens_events || []).filter((e) => e.t0 <= t && t < e.t1);
    const paint = (sec2) => {
      const w = cv.width = img.clientWidth || 640, h = cv.height = img.clientHeight || 360, ctx = cv.getContext("2d");
      if (!ctx) return; ctx.clearRect(0, 0, w, h);
      for (const e of evs) {
        // Animated replay of the event window on the still; reduced motion = static hold frame.
        const tt = reduce ? (e.t0 + e.t1) / 2 : e.t0 + (sec2 % (e.t1 - e.t0 + 0.6));
        drawLens(ctx, e, lensState(e, tt, opts.verifierStatus), w, h, clip);
      }
    };
    if (reduce) img.addEventListener("load", () => paint(0));
    else { const t0 = performance.now(); const loop = (now) => { paint((now - t0) / 1000); if (sec.isConnected !== false) requestAnimationFrame(loop); }; img.addEventListener("load", () => requestAnimationFrame(loop)); }
  }
  const ul = el("ul", "seen-list");
  for (const c of seen.clips) {
    const sb = c.scorebug, m = c.motion_pct;
    ul.append(el("li", null, `${c.id}: scorebug in place ${sb.in_place}/${sb.frames} frames (max anchor move ${sb.max_anchor_jump_px} px)` +
      ` · motion energy players ${m.players}% · HUD ${m.hud}% · rest ${m.rest}%`));
  }
  sec.append(ul);
  sec.append(el("p", "pnote", "Meta SAM 3.1 tracks the scorebug from the referee's own OCR region and splits the referee's frame-difference energy into players / HUD / rest of screen. Visualization only: it is not a referee input, carries no status, and never changes the result above. Gold appears only on a score lock of a VERIFIED receipt."));
  return sec;
}
