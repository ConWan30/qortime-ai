# `demo_pipeline/`: demo-video captions (Muse Voice Transcribe 1.0)

> **Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4 2026.** Everything in this folder is event work.
> Pre-existing vs built this week: [repo README](../README.md#built-this-week-vs-pre-existing) · [`PROVENANCE.md`](../PROVENANCE.md).

`captions/transcribe_stream.py` streams the narration through Muse Voice Transcribe 1.0; `captions/make_srt.py` uses
each partial's `audioProcessedMs` to time the burned-in captions. The text is the narration script, so ASR mishearings
never reach the screen. The committed data reproduces `captions/data/vo-v6-captions.srt` byte-for-byte. Video only;
never part of the referee.

```bash
pip install -e '.[captions]'
cd demo_pipeline/captions
META_API_KEY=... python transcribe_stream.py NARRATION_24k_mono.wav data/voice-transcribe-stream.json   # step 1, live ASR (paid)
python make_srt.py --stream data/vo-v6-voice-transcribe-stream.json --vo NARRATION.wav --out captions.srt   # step 2
```
The narration WAV is not committed (`*.wav` is git-ignored); step 2 uses it only to calibrate model latency against
the narration's acoustic onsets. Committed data: `captions/data/` (stream, response, build report, SRTs).
