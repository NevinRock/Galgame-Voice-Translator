# Galgame Voice Translator

[English](README.md) | [简体中文](README.zh-CN.md)

本项目将 SiglusEngine 视觉小说的日语语音和中文脚本按全局 KOE 编号对齐，
再使用 [Fish Speech](https://github.com/fishaudio/fish-speech) Drama 3 生成中文普通话配音。
流水线优先保留角色音色和说话语气，同时以原日语句子的时长为约束，
使中文配音的节奏尽量接近原作。

本仓库不包含任何游戏脚本、原声、生成音频或模型权重。请只处理你有权使用的资源。

## 处理流程

1. 用 SiglusSceneScriptUtility 提取原日语语音，并从原版和汉化版脚本导出 KOE 清单。
2. 根据全局 KOE 编号合并日文、中文、角色信息和音频路径。
3. 如果没有现成的中文脚本，可通过 OpenAI-compatible API 翻译台词。
4. 使用固定的角色参考音频生成多个普通话候选。
5. 只接受与日语原句时长偏差不超过 `max(0.25 秒, 15%)` 的候选，
   再用 FFmpeg `atempo` 对齐精确时长。
6. 将通过检查的 WAV 编码为 Ogg Vorbis，并重建 OVK 语音包。

自适应生成不会把当前日语原句直接作为 TTS 参考音频。在跨语言短句中，
这种参考容易压过中文目标，导致模型重复日语。原句只用来确定目标时长，
较长的固定角色样本则用来保留音色和说话风格。

## 硬件要求

Fish Speech 官方安装文档给出了以下推理要求：

- Drama 3：单张 NVIDIA GPU，FP8 模式至少需要 48 GB 显存。Drama 3 不支持
  CPU、Apple MPS 或 AMD ROCm 推理。
- S2-Pro：至少需要 24 GB 显存，也支持 CPU 推理。
- 系统：Linux 或 WSL。

最新兼容性请查看
[Fish Speech 官方安装文档](https://github.com/fishaudio/fish-speech/blob/main/docs/en/install.md)。

48 GB 是 FP8 路径的官方最低值。在下面记录的 A800 环境中，固定版本的
Drama 3 加载模型和 codec 后实测占用约 72–74 GiB，因此这套配置建议使用
单张 80 GB GPU。项目脚本只使用一张卡，默认选择 GPU 3。

## 已测试环境

- 操作系统：Ubuntu 22.04
- GPU：单张 NVIDIA A800-SXM4-80GB，总显存 81,920 MiB
- NVIDIA 驱动：590.48.01
- Python：3.10.12
- PyTorch：2.8.0+cu128
- PyTorch CUDA runtime：12.8
- FFmpeg：4.4.2
- Fish Speech 提交：`541566932abbaebcb0a40e562a1f846738383f38`
- SiglusSceneScriptUtility 提交：`85700715aed8695a95183bb973f981a61ae9d9c7`

## 本地安装

需要 Python 3.10 或更高版本、Git、FFmpeg 和 ffprobe。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# 在本地获取固定版本的第三方源码，不会下载模型。
bash scripts/bootstrap_sources.sh
```

第三方仓库、虚拟环境、模型权重、游戏资源和生成文件已被 `.gitignore` 排除，
不会提交到 Git。

## 提取与对齐 SiglusEngine 游戏

以《終のステラ》的目录结构为例：

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

`config/` 目录提供了通用的台词清单、角色参考和翻译术语表示例。

## A800 单卡部署

默认服务器路径是 `/ssd/BNW/Galgame_voice`。代码和已提取的语音任务分开上传，
游戏本体不会被上传。

```bash
# 本地执行，并确保先运行了 scripts/bootstrap_sources.sh。
bash scripts/upload_code_to_a800.sh
bash scripts/upload_voice_jobs_to_a800.sh work/tsui_no_stella

# 在 A800 服务器上执行。模型权重直接下载到服务器。
cd /ssd/BNW/Galgame_voice
bash scripts/a800_install.sh
bash scripts/a800_download_model.sh /ssd/BNW/Galgame_voice drama-3

# 在 GPU 3 上启动一个 API 进程和一个生成 worker。
bash scripts/a800_start_api.sh
bash scripts/a800_start_batch.sh /ssd/BNW/Galgame_voice \
  tsui_no_stella generated_voice
bash scripts/a800_batch_status.sh /ssd/BNW/Galgame_voice \
  tsui_no_stella generated_voice
```

如果要使用其他单张 GPU 或端口，请在两个启动命令中传入相同的环境变量：

```bash
FISH_GPU=0 FISH_PORT=18080 bash scripts/a800_start_api.sh
FISH_GPU=0 FISH_PORT=18080 bash scripts/a800_start_batch.sh
```

脚本只会启动一个 API 进程和一个生成 worker。已存在的输出会被跳过，
因此中断后可以直接使用同一命令恢复。每句的 seed、候选时长和选择结果会写入
`_results_worker_0.jsonl`。未通过时长检查的最优候选会保存到 `.rejected/`，不会当作成品发布。

模型下载脚本在中国大陆服务器上默认使用 ModelScope。也可以选择 Hugging Face，
此时 `HF_ENDPOINT` 默认设置为 `https://hf-mirror.com`。

## 重建 OVK 语音包

```bash
rsync -az -e "ssh -F $HOME/.ssh/config" \
  a800:/ssd/BNW/Galgame_voice/jobs/tsui_no_stella/generated_voice/ \
  work/tsui_no_stella/generated_voice/

bash scripts/repack_siglus_voice.sh \
  終のステラ/koe \
  work/tsui_no_stella/generated_voice \
  work/tsui_no_stella/repacked_koe
```

回包脚本只替换已生成的 KOE 条目，并且会拒绝将原游戏 `koe/` 目录作为输出位置。

## 验证

```bash
python -m unittest discover -v
bash -n scripts/*.sh
```

开发过程记录见 [CHANGELOG.md](CHANGELOG.md)。
