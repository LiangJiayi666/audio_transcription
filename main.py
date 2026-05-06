#!/usr/bin/env python3
"""录音批量转写工具 - 使用 Groq Whisper API 将音频转为带时间戳的中文 Markdown。"""

import os
import sys
import time
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


INPUT_DIR = "input"
OUTPUT_DIR = "output"
MAX_RETRY_ROUNDS = 2
RETRY_DELAY = 2  # seconds


def scan_audio_files(directory: str) -> list[str]:
    """Scan directory for supported audio files, return sorted absolute paths."""
    if not os.path.isdir(directory):
        print(f"错误: {directory}/ 目录不存在，请创建并放入音频文件。")
        sys.exit(1)

    files = sorted(
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.splitext(f)[1].lower() in SUPPORTED_FORMATS
    )
    return files


def batch_transcribe(client: OpenAI) -> tuple[int, int, list[str]]:
    """批量转写，失败文件自动重试。返回 (成功数, 失败数, 失败文件名列表)。"""
    audio_files = scan_audio_files(INPUT_DIR)
    if not audio_files:
        print("input/ 目录中没有支持的音频文件，请放入文件后重试。")
        sys.exit(0)

    total = len(audio_files)
    print(f"发现 {total} 个音频文件\n")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    success = 0
    failed_files = []

    for i, audio_path in enumerate(audio_files):
        filename = os.path.basename(audio_path)
        print(f"[{i + 1}/{total}] 正在转写 {filename}...", end=" ", flush=True)

        segments = transcribe_file(client, audio_path)
        if segments is not None:
            md_content = format_markdown(segments, filename)
            out_path = os.path.join(OUTPUT_DIR, os.path.splitext(filename)[0] + ".md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            print("✓")
            success += 1
        else:
            print("✗")
            failed_files.append(audio_path)

    # 重试失败文件（最多 MAX_RETRY_ROUNDS 轮）
    for round_num in range(1, MAX_RETRY_ROUNDS + 1):
        if not failed_files:
            break

        print(f"\n--- 第 {round_num} 轮重试 ({len(failed_files)} 个文件) ---")
        time.sleep(RETRY_DELAY)

        still_failed = []
        for audio_path in failed_files:
            filename = os.path.basename(audio_path)
            print(f"  正在重试 {filename}...", end=" ", flush=True)

            segments = transcribe_file(client, audio_path)
            if segments is not None:
                md_content = format_markdown(segments, filename)
                out_path = os.path.join(OUTPUT_DIR, os.path.splitext(filename)[0] + ".md")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print("✓")
                success += 1
            else:
                print("✗")
                still_failed.append(audio_path)

        failed_files = still_failed

    return success, len(failed_files), [os.path.basename(f) for f in failed_files]


if __name__ == "__main__":
    api_key = load_api_key()
    print(f"✓ 成功读取 API key (长度: {len(api_key)})")

    client = OpenAI(base_url=GROQ_BASE_URL, api_key=api_key)
    ok, fail, fail_names = batch_transcribe(client)

    print(f"\n{'=' * 40}")
    print(f"转写完成！成功: {ok}, 失败: {fail}")
    if fail_names:
        print(f"失败文件:")
        for name in fail_names:
            print(f"  - {name}")
