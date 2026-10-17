# Galgame Voice Translator

将 SiglusEngine 视觉小说的日语语音和中文脚本按 KOE 编号对齐，再用
[Fish Speech](https://github.com/fishaudio/fish-speech) Drama 3 生成中文普通话配音。
流水线优先保留角色音色和情绪，并以原日语句子的时长为约束恢复接近原作的节奏。

> 仓库不包含任何游戏脚本、原声、生成音频或模型权重。请只处理你有权使用的资源。

## 工作流程

1. 用 SiglusSceneScriptUtility 在本地解包原日语语音，导出原版与汉化版的 KOE 清单。
2. 按全局 KOE 编号合并日文、中文、角色和音频路径。
3. 如果没有成品中文脚本，可通过 OpenAI-compatible API 翻译。
4. 在 GPU 服务器上用角色参考音频生成多个候选，择取时长最接近原句的一个。
5. 只接受偏差不超过 `max(0.25 秒, 15%)` 的候选，最后用 `atempo` 对齐精确时长。
6. 将已通过检查的 WAV 编码回 Ogg Vorbis，重建 OVK 包。

自适应模式不把当前日语原句直接作为 TTS 参考。这是有意的：在跨语言的短句上，
精确原句容易压过中文目标，导致模型反复说日语。原句仅用来确定节奏长度，
固定的较长角色样本负责音色和说话风格。

## 本地安装

需要 Python 3.10+、Git、FFmpeg/​ffprobe。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

# 在本地获取固定版本的第三方源码，不会下载模型。
bash scripts/bootstrap_sources.sh
```

Fish Speech 固定在 `541566932abbaebcb0a40e562a1f846738383f38`，
SiglusSceneScriptUtility 固定在 `85700715aed8695a95183bb973f981a61ae9d9c7`。

## 提取与对齐

以《終のステラ》的目录布局为例：

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

`config/` 中有通用的清单、角色参考和术语表格式。

## A800 部署与三卡生成

默认服务器路径是 `/ssd/BNW/Galgame_voice`。代码和已提取语音分开上传，
游戏本体永远不会被同步。

```bash
# 本地
bash scripts/upload_code_to_a800.sh
bash scripts/upload_voice_jobs_to_a800.sh work/tsui_no_stella

# a800：安装依赖，权重直接从中国大陆可用源下载到服务器
cd /ssd/BNW/Galgame_voice
bash scripts/a800_install.sh
bash scripts/a800_download_model.sh /ssd/BNW/Galgame_voice drama-3

# 默认启动 GPU 0/3/7，端口 19081/8080/19082
bash scripts/a800_start_apis.sh
bash scripts/a800_start_batch.sh /ssd/BNW/Galgame_voice \
  tsui_no_stella generated_voice
bash scripts/a800_batch_status.sh /ssd/BNW/Galgame_voice \
  tsui_no_stella generated_voice
```

其他 GPU 可通过环境变量配置，两个列表必须等长：

```bash
FISH_GPUS="1 2" FISH_PORTS="18081 18082" bash scripts/a800_start_apis.sh
FISH_GPUS="1 2" FISH_PORTS="18081 18082" bash scripts/a800_start_batch.sh
```

任务会按 worker 数量稳定分片，已生成文件会被跳过，因此中断后可直接重跑。
每句的 seed、候选时长和选择结果记录在 `_results_worker_*.jsonl`；
超过时长阈值的最优候选会进入 `.rejected/`，不会冒充成品。

## 回包

```bash
rsync -az -e "ssh -F $HOME/.ssh/config" \
  a800:/ssd/BNW/Galgame_voice/jobs/tsui_no_stella/generated_voice/ \
  work/tsui_no_stella/generated_voice/

bash scripts/repack_siglus_voice.sh \
  終のステラ/koe \
  work/tsui_no_stella/generated_voice \
  work/tsui_no_stella/repacked_koe
```

回包脚本只替换已生成的 KOE 条目，并拒绝把输出指向原游戏 `koe/` 目录。

## 验证

```bash
python -m unittest discover -v
bash -n scripts/*.sh
```

完整的实验演进记录见 [CHANGELOG.md](CHANGELOG.md)。
