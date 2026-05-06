#!/usr/bin/env python3
"""录音批量转写工具 - 使用 Groq Whisper API 将音频转为带时间戳的中文 Markdown。"""

import os
import sys

GROQ_KEY_FILE = "groq_key.md"


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


if __name__ == "__main__":
    key = load_api_key()
    print(f"✓ 成功读取 API key (长度: {len(key)})")
