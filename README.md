# Galgame Voice Translator

This project aligns Japanese voice clips and a translated script from a
SiglusEngine visual novel by global KOE number, then uses
[Fish Speech](https://github.com/fishaudio/fish-speech) Drama 3 to generate
Mandarin Chinese dialogue. The pipeline prioritizes character identity and
delivery while using the duration of each original Japanese line to preserve
the pacing of the game.

This repository does not contain game scripts, original voice assets,
generated audio, or model weights. Only process material that you are legally
allowed to use.

## Pipeline

1. Extract the original Japanese voice clips and export KOE manifests from the
   original and translated scripts with SiglusSceneScriptUtility.
2. Join Japanese text, Chinese text, speaker metadata, and audio paths by the
   global KOE number.
3. If no translated script is available, optionally translate the dialogue
   through an OpenAI-compatible API.
4. Generate several Mandarin candidates with one fixed character reference.
5. Accept only a candidate whose duration differs by no more than
   `max(0.25 seconds, 15%)` from the Japanese line, then align it exactly with
   FFmpeg `atempo`.
6. Encode accepted WAV files as Ogg Vorbis and rebuild the OVK archives.

Adaptive synthesis deliberately does not give the exact Japanese line to the
TTS model as an audio reference. On short cross-language lines, that reference
can overpower the Mandarin target and make the model repeat Japanese speech.
The original line is used only as a timing target. A longer, fixed character
sample provides the voice identity and speaking style.

## Hardware requirements

The official Fish Speech installation guide lists the following inference
requirements:

- Drama 3: one NVIDIA GPU with at least 48 GB of VRAM in FP8 mode. CPU, Apple
  MPS, and AMD ROCm inference are not supported for Drama 3.
- S2-Pro: at least 24 GB of VRAM; CPU inference is also supported.
- Linux or WSL.

See the
[official Fish Speech installation guide](https://github.com/fishaudio/fish-speech/blob/main/docs/en/install.md)
for the current compatibility matrix.

The 48 GB figure applies to the FP8 path. With the pinned Drama 3 build on the
A800 environment below, the API process used approximately 72-74 GiB after
loading the model and codec. An 80 GB GPU is therefore recommended for this
exact configuration. The provided scripts use one GPU only and default to
GPU 3.

## Tested environment

- Operating system: Ubuntu 22.04
- GPU: one NVIDIA A800-SXM4-80GB, 81,920 MiB total VRAM
- Selected device: GPU 3
- NVIDIA driver: 590.48.01
- Python: 3.10.12
- PyTorch: 2.8.0+cu128
- CUDA runtime used by PyTorch: 12.8
- FFmpeg: 4.4.2
- Fish Speech commit: `541566932abbaebcb0a40e562a1f846738383f38`
- SiglusSceneScriptUtility commit: `85700715aed8695a95183bb973f981a61ae9d9c7`

## Local installation

Python 3.10 or newer, Git, FFmpeg, and ffprobe are required.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# Fetch pinned third-party source code locally. This does not download models.
bash scripts/bootstrap_sources.sh
```

Third-party repositories, virtual environments, model weights, game data, and
generated files are excluded by `.gitignore` and are not committed.

## Extracting and aligning a SiglusEngine game

The following example uses the directory layout of *Tsui no Stella*:

```bash
PYTHONPATH=tools/SiglusSceneScriptUtility/src python3 -m siglus_ssu \
  --legacy-full -k 終のステラ/Scene.pck 終のステラ/koe \
  work/tsui_no_stella/japanese_voice --angou 終のステラ

cp 終のステラ/Scene.chs work/tsui_no_stella/Scene_chs.pck
PYTHONPATH=tools/SiglusSceneScriptUtility/src python3 -m siglus_ssu \
  --legacy-full -k --stats-only work/tsui_no_stella/Scene_chs.pck \
  終のステラ/koe work/tsui_no_stella/chinese_manifest \
  --angou 終のステラ

galgame-voice import-siglus \
  --koe-csv work/tsui_no_stella/japanese_voice/koe_master.csv \
  --zh-koe-csv work/tsui_no_stella/chinese_manifest/koe_master.csv \
  --voice-dir work/tsui_no_stella/japanese_voice \
  --output work/tsui_no_stella/job/lines.jsonl \
  --characters work/tsui_no_stella/job/characters.json
```

The `config/` directory contains generic examples for line manifests,
character references, and translation glossaries.

## Single-GPU A800 deployment

The default server path is `/ssd/BNW/Galgame_voice`. Source code and extracted
voice jobs are uploaded separately. The game installation is never uploaded.

```bash
# Run locally after scripts/bootstrap_sources.sh.
bash scripts/upload_code_to_a800.sh
bash scripts/upload_voice_jobs_to_a800.sh work/tsui_no_stella

# Run on the A800 server. Model weights are downloaded directly to the server.
cd /ssd/BNW/Galgame_voice
bash scripts/a800_install.sh
bash scripts/a800_download_model.sh /ssd/BNW/Galgame_voice drama-3

# Start one API process and one synthesis worker on GPU 3.
bash scripts/a800_start_api.sh
bash scripts/a800_start_batch.sh /ssd/BNW/Galgame_voice \
  tsui_no_stella generated_voice
bash scripts/a800_batch_status.sh /ssd/BNW/Galgame_voice \
  tsui_no_stella generated_voice
```

To use another single GPU or port, pass the same environment values to both
start commands:

```bash
FISH_GPU=0 FISH_PORT=18080 bash scripts/a800_start_api.sh
FISH_GPU=0 FISH_PORT=18080 bash scripts/a800_start_batch.sh
```

Only one API process and one synthesis worker are started. Existing output is
skipped, so an interrupted job can be resumed with the same command. Each
line's seeds, candidate durations, and selection result are recorded in
`_results_worker_0.jsonl`. The closest candidate is stored in `.rejected/`
instead of being published when it fails the duration gate.

The model download script uses ModelScope by default for servers in mainland
China. Hugging Face remains available through `HF_ENDPOINT`, which defaults to
`https://hf-mirror.com` when selected.

## Rebuilding OVK archives

```bash
rsync -az -e "ssh -F $HOME/.ssh/config" \
  a800:/ssd/BNW/Galgame_voice/jobs/tsui_no_stella/generated_voice/ \
  work/tsui_no_stella/generated_voice/

bash scripts/repack_siglus_voice.sh \
  終のステラ/koe \
  work/tsui_no_stella/generated_voice \
  work/tsui_no_stella/repacked_koe
```

The repacking script replaces only generated KOE entries and refuses to use
the original game `koe/` directory as its output destination.

## Validation

```bash
python -m unittest discover -v
bash -n scripts/*.sh
```

Development history is recorded in [CHANGELOG.md](CHANGELOG.md).
