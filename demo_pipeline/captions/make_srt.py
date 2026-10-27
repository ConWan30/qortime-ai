"""Demo-video captions, step 2 (Meta AI Developer Hackathon, Oct 26 - Nov 4 2026).
TIMING: Meta Muse Voice Transcribe only. TIMING: Muse Voice Transcribe only (event-stream pass, vo-v6-voice-transcribe-stream.json).
TEXT: the narration script as already shown on screen in v5 (same 46 cue splits), so ASR mis-hears ("Core time", "CoreCap") never reach the screen.
Method:
 1. Each streamed `transcript` partial carries the model's audioProcessedMs. A word's time = the audioProcessedMs of the first partial that contains it
    (prefix-aligned to the final speechComplete transcript).
 2. Script words are aligned to the transcript words (difflib); unmatched script words (e.g. "one seven zero one two three" vs "170123") are interpolated
    between their matched neighbours.
 3. Partials arrive after the word is spoken. One constant model latency L is removed. L is calibrated against the narration's own acoustic onsets
    (ffmpeg silencedetect on the VO stem, first word of each sentence), not against the TTS timestamps.
 4. +20.015 s: the VO starts at 20 s in the cut, plus the 15 ms the v4/v5 master sits behind the raw mix (measured by cross-correlation)."""
import argparse, json, re, difflib, subprocess, numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("--stream", default="data/vo-v6-voice-transcribe-stream.json")
ap.add_argument("--script", default="data/narration-script-cues.srt", help="cue text/splits (the narration script); its timings are only used for the comparison report")
ap.add_argument("--vo", required=True, help="narration stem WAV, for latency calibration by acoustic onsets")
ap.add_argument("--out", default="data/vo-v6-captions.srt")
ap.add_argument("--offset", type=float, default=20.015, help="where the narration starts in the cut, seconds")
A = ap.parse_args()
OFF = A.offset
ev = json.load(open(A.stream))["events"]
parts = [(e["audioProcessedMs"], e["transcript"]) for e in ev if e.get("type") == "transcript"]
final = [e for e in ev if e.get("type") == "speechComplete"][0]["transcript"]
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
F = [norm(w) for w in final.split()]; F = [w for w in F if w]
first = [None] * len(F)
for t, txt in parts:
    P = [w for w in (norm(x) for x in txt.split()) if w]
    sm = difflib.SequenceMatcher(None, P, F[:len(P) + 6], autojunk=False)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            if first[b + k] is None: first[b + k] = t
# monotone fill
last = 0
for i in range(len(F)):
    if first[i] is None or first[i] < last: first[i] = last if first[i] is None else max(first[i], last)
    last = first[i]
# script cues from v5
srt = open(A.script).read().strip().split("\n\n")
cues = [b.split("\n", 2)[2].replace("\n", " ") for b in srt]
words = []; owner = []
for ci, c in enumerate(cues):
    for w in c.split():
        words.append(w); owner.append(ci)
S = [norm(w) for w in words]
sm = difflib.SequenceMatcher(None, S, F, autojunk=False)
amap = {}
for a, b, n in sm.get_matching_blocks():
    for k in range(n): amap[a + k] = b + k
E_ = np.full(len(S), np.nan)
for i, j in amap.items():
    if S[i]: E_[i] = first[j] / 1000.0
idx = np.where(~np.isnan(E_))[0]
E_ = np.interp(np.arange(len(S)), idx, E_[idx])
# latency calibration vs acoustic onsets of the VO stem
out = subprocess.run(["ffmpeg", "-nostats", "-i", A.vo, "-af", "silencedetect=n=-40dB:d=0.18", "-f", "null", "-"], capture_output=True, text=True).stderr
onsets = np.array([0.16] + [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", out)])
sent_first = [i for i in range(len(words)) if i == 0 or re.search(r"[.:—?!]$", words[i - 1]) or words[i - 1] == "—"]
best = None
for L in np.arange(0.0, 2.5, 0.01):
    err = np.median([np.min(np.abs(onsets - (E_[i] - L))) for i in sent_first])
    if best is None or err < best[1]: best = (round(float(L), 2), float(err))
L = best[0]
T = E_ - L
starts = []; ends = []
for ci in range(len(cues)):
    ws = [i for i in range(len(words)) if owner[i] == ci]
    starts.append(max(0.0, T[ws[0]]))
for ci in range(len(cues)):
    ws = [i for i in range(len(words)) if owner[i] == ci]
    e = T[ws[-1]] + 0.45
    if ci + 1 < len(cues): e = min(e, starts[ci + 1]) if starts[ci + 1] - e < 0.25 else e
    ends.append(max(e, starts[ci] + 0.3))
for ci in range(len(cues) - 1):  # no overlaps
    if ends[ci] > starts[ci + 1]: ends[ci] = starts[ci + 1]
fmt = lambda s: "%02d:%02d:%02d,%03d" % (int(s // 3600), int(s // 60 % 60), int(s % 60), int(round((s % 1) * 1000)) % 1000)
with open(A.out, "w") as f:
    for i, (s, e, c) in enumerate(zip(starts, ends, cues), 1):
        f.write(f"{i}\n{fmt(s + OFF)} --> {fmt(e + OFF)}\n{c}\n\n")
# compare with v5 (TTS-timed) cues for the report only
v5s = []
for b in srt:
    tline = b.split("\n")[1]; h, m, s = tline.split(" --> ")[0].replace(",", ".").split(":"); v5s.append(int(h) * 3600 + int(m) * 60 + float(s))
d = np.array(starts) + OFF - np.array(v5s)
meta = {"latency_s": L, "latency_fit_median_err_s": round(best[1], 3), "partials": len(parts), "asr_words": len(F), "script_words": len(S), "script_words_matched": len(amap),
        "cues": len(cues), "start_shift_vs_v5_s": {"median": round(float(np.median(d)), 3), "mean_abs": round(float(np.abs(d).mean()), 3), "max_abs": round(float(np.abs(d).max()), 3)}}
json.dump(meta, open(A.out.replace(".srt", "-build.json"), "w"), indent=1); print(json.dumps(meta))
