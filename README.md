# Audio Batch Transcription Tool / 录音批量转写工具

使用 Groq Whisper API 将音频批量转写为带时间戳的中文 Markdown，支持 LLM 整理生成会议纪要。

Batch transcribe audio files to timestamped Chinese Markdown via Groq Whisper API, with optional LLM-powered meeting notes generation.

## Features / 特性

- 批量音频转写，输出带时间戳的 Markdown（`**MM:SS** text`）
- 自动解压 zip/tar/tar.gz/tar.bz2/tar.xz 压缩包
- 超大文件（>25MB）自动切割为片段分别转写后合并
- 失败自动重试，含速率限制检测
- 可选：DeepSeek LLM 整理转写结果，生成会议纪要、经验、待办 + 润色原文

## Prerequisites / 前置依赖

- Python 3.8+
- ffmpeg
- Groq API Key（转写必需）
- DeepSeek API Key（整理可选）

Install ffmpeg:

```bash
# Ubuntu/Debian
sudo apt install -y ffmpeg

# macOS
brew install ffmpeg
```

## Installation / 安装

```bash
git clone git@github.com:LiangJiayi666/audio_transcription.git
cd audio_transcription
pip install -r requirements.txt
```

## Configuration / 配置

```bash
# 复制模板文件，填入你的 API Key
cp groq_key.example.md groq_key.md
cp deepseek_key.example.md deepseek_key.md
```

然后编辑 `groq_key.md`，将第一行替换为你的 Groq API Key（从 https://console.groq.com/keys 获取）。

如需使用整理功能，同样编辑 `deepseek_key.md`（从 https://platform.deepseek.com/api_keys 获取）。

## Usage / 使用

### Step 1: Transcription / 转写

将音频文件（或压缩包）放入 `input/` 目录，然后运行：

```bash
python main.py
```

转写结果输出到 `output/`，处理完成的源文件自动移入 `done/`。

### Step 2: Summarization (optional) / 整理（可选）

```bash
python summarize.py
```

整理结果输出到 `summary/`，每份包含会议纪要、经验、待办和润色后的原文。

## Supported Formats / 支持的格式

| 类型 | 格式 |
|------|------|
| 音频 Audio | .mp3 .wav .m4a .flac .ogg .webm |
| 压缩包 Archives | .zip .tar .tar.gz .tar.bz2 .tar.xz |

## Project Structure / 项目结构

```
audio_transcription/
├── input/                   ← 音频放这里 / put audio files here
│   └── .gitkeep
├── output/                  ← 转写输出 / transcription .md
├── done/                    ← 已处理的源文件 / processed sources
├── summary/                 ← LLM 整理输出 / meeting notes
├── main.py                  ← 转写脚本 / transcription
├── summarize.py             ← 整理脚本 / summarization
├── groq_key.example.md      ← Groq Key 模板 / template
├── deepseek_key.example.md  ← DeepSeek Key 模板 / template
├── .gitignore
├── requirements.txt
└── README.md
```
