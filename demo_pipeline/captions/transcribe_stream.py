"""Demo-video captions, step 1: Meta Muse Voice Transcribe 1.0 on the narration stem (event-stream mode).

Every streamed partial transcript carries the model's audioProcessedMs, which step 2 (make_srt.py) uses as caption timing.
Built during the Meta AI Developer Hackathon (Oct 26 - Nov 4 2026). Key from env META_API_KEY (never hard-coded, never logged).

  python transcribe_stream.py NARRATION_24k_mono.wav data/voice-transcribe-stream.json
"""
import json, os, sys, time, wave

import requests

KW = ["QorTime", "QorCap", "Muse Spark", "SAM", "Muse Voice Transcribe", "Show Your Hands", "scorebug", "VERIFIED", "PARTIAL", "Madden", "Call of Duty", "Meta"]


def main(wav: str, out_path: str) -> int:
    key = os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not key:
        print("set META_API_KEY", file=sys.stderr); return 2
    w = wave.open(wav); sec = w.getnframes() / w.getframerate()
    req = {"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "mode": "ENDPOINTING", "languageBias": ["English"],
           "keywords": KW, "partialMode": "CUMULATIVE", "emitAudioProgress": True}
    events = []
    with open(wav, "rb") as a:
        r = requests.post("https://api.meta.ai/v1/asr/transcribe?sessionId=qortime-demo-captions-stream",
                          headers={"Authorization": f"Bearer {key}", "Accept": "text/event-stream"},
                          files={"request": (None, json.dumps(req), "application/json"), "audio": ("vo.wav", a, "audio/wav")},
                          timeout=600, stream=True)
        print("http", r.status_code)
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try: events.append(json.loads(line[5:].strip()))
                except Exception: events.append({"raw": line[:500]})
    out = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "audio_s": round(sec, 3), "request": req, "http": r.status_code,
           "accept": "text/event-stream", "events": events}
    json.dump(out, open(out_path, "w"), indent=1)
    print(f"{len(events)} events -> {out_path} (~${sec / 3600 * 0.18:.4f})")
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
