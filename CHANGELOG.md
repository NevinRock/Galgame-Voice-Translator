# Changelog

## 0.1.0 - 2026-10-17

- Added SiglusEngine KOE extraction-manifest import and Japanese/Chinese line alignment.
- Added optional Japanese-to-Chinese translation through an OpenAI-compatible API.
- Added Fish Speech Drama 3 cross-language character voice cloning.
- Switched the recommended synthesis mode from exact-line/dual references to a stable
  character reference, preventing short Mandarin lines from repeating Japanese audio.
- Added deterministic multi-candidate generation, duration gating and final rhythm
  alignment against the original Japanese line.
- Added resumable processing and A800 helpers using one GPU by default.
- Added safe OVK rebuilding that never writes into the original game directory.

Generated audio, game files and model weights are intentionally excluded from releases.
