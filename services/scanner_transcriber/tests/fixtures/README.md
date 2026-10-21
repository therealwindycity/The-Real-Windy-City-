# Redistributable Speech Fixtures

These small 16 kHz mono 16-bit PCM WAV fixtures verify end-to-end `faster-whisper` ASR,
silence gating, and HTTP stream chunking without requiring external network downloads:

- `jfk_16k.wav` (10.9 s, 341 KiB): Public-domain U.S. presidential inaugural address excerpt
  redistributed in `SYSTRAN/faster-whisper` (`tests/data/jfk.flac`, MIT License).
  Expected substring phrases: `"fellow americans"`, `"ask not what your country can do for you"`, `"ask what you can do for your country"`.
- `ever_tried_16k.wav` (5.5 s, 172 KiB): Clean English speech sample redistributed in
  `moonshine-ai/useful-transformers` (`examples/whisper/assets/ever_tried.wav`, MIT/Apache-2.0).
  Expected substring phrases: `"ever tried"`, `"no matter"`.
