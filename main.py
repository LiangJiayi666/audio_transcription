#!/usr/bin/env python3
"""录音批量转写工具 - 使用 Groq Whisper API 将音频转为带时间戳的中文 Markdown。"""

import os
import sys
from openai import OpenAI

GROQ_KEY_FILE = "groq_key.md"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "whisper-large-v3-turbo"

SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB


def load_api_key() -> str:
    """从 groq_key.md 文件第一行读取 API key，去除首尾空白。"""
    if not os.path.isfile(GROQ_KEY_FILE):
        print(f"错误: 找不到 {GROQ_KEY_FILE} 文件，请创建该文件并写入 API key。")
        sys.exit(1)

    with open(GROQ_KEY_FILE, "r") as f:
        key = f.readline().strip()

    if not key:
        print(f"错误: {GROQ_KEY_FILE} 文件第一行为空，请写入 API key。")
        sys.exit(1)

    return key


def seconds_to_mmss(seconds: float) -> str:
    """将秒数转换为 MM:SS 格式。"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def transcribe_file(client: OpenAI, audio_path: str) -> list | None:
    """转写单个音频文件，返回 segments 列表。失败或不支持时返回 None。"""
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        print(f"  跳过: 不支持的格式 {ext}")
        return None

    size = os.path.getsize(audio_path)
    if size > MAX_FILE_SIZE:
        size_mb = size / (1024 * 1024)
        print(f"  错误: 文件大小 {size_mb:.1f}MB 超过 25MB 限制，跳过")
        return None

    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model=GROQ_MODEL,
            file=f,
            response_format="verbose_json",
            language="zh",
        )

    return transcription.segments


def format_markdown(segments: list, filename: str) -> str:
    """将 segments 格式化为带时间戳的 Markdown。"""
    name = os.path.splitext(os.path.basename(filename))[0]
    lines = [f"# {name}", ""]
    for seg in segments:
        timestamp = seconds_to_mmss(seg.start)
        lines.append(f"**{timestamp}** {seg.text.strip()}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    key = load_api_key()
    print(f"✓ 成功读取 API key (长度: {len(key)})")
