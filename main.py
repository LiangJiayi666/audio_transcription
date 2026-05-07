#!/usr/bin/env python3
"""录音批量转写工具 - 使用 Groq Whisper API 将音频转为带时间戳的中文 Markdown。

特性：
- 自动解压 zip/tar 压缩包
- 递归查找所有音频文件
- 自动切割超大文件（>25MB）并合并转写结果
- 失败自动重试
"""

import os
import sys
import time
import json
import shutil
import zipfile
import tarfile
import tempfile
import subprocess
from openai import OpenAI

GROQ_KEY_FILE = "groq_key.md"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "whisper-large-v3-turbo"

SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".webm"}
ARCHIVE_FORMATS = {".zip", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz"}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
INPUT_DIR = "input"
OUTPUT_DIR = "output"
MAX_RETRY_ROUNDS = 2
RETRY_DELAY = 2
TEMP_DIR = None  # global temp dir for this run


# ─── helpers ────────────────────────────────────────────────────────────────

def load_api_key() -> str:
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
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def require_ffmpeg():
    """If ffmpeg/ffprobe not found, exit with install instructions."""
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            print(f"错误: 需要 {cmd}，请先安装 ffmpeg:  sudo apt install -y ffmpeg")
            sys.exit(1)


# ─── archive extraction ─────────────────────────────────────────────────────

def is_archive(filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in ARCHIVE_FORMATS)


def extract_archive(archive_path: str, dest_dir: str) -> list[str]:
    """Extract archive to dest_dir, return list of extracted file paths."""
    lower = archive_path.lower()
    extracted = []

    try:
        if lower.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dest_dir)
                extracted = [os.path.join(dest_dir, n) for n in zf.namelist()]

        elif any(lower.endswith(ext) for ext in (".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz")):
            mode_map = {".gz": "r:gz", ".bz2": "r:bz2", ".xz": "r:xz"}
            mode = "r"
            for ext, m in mode_map.items():
                if lower.endswith(ext):
                    mode = m
                    break
            with tarfile.open(archive_path, mode) as tf:
                tf.extractall(dest_dir)
                extracted = [os.path.join(dest_dir, n) for n in tf.getnames()]

        else:
            print(f"  跳过不支持的压缩格式: {os.path.basename(archive_path)}")
            return []

        # Only keep files (not directories), resolve to dest_dir
        extracted = [p for p in extracted if os.path.isfile(p)]
        print(f"  解压: {os.path.basename(archive_path)} → {len(extracted)} 个文件")
        return extracted

    except Exception as e:
        print(f"  解压失败 {os.path.basename(archive_path)}: {e}")
        return []


def process_archives(input_dir: str) -> list[str]:
    """Extract all archives found in input_dir, returns paths of extracted audio files.
    Archives themselves are skipped from direct transcription."""
    audio_files = []
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if not os.path.isfile(path):
            continue
        if is_archive(name):
            # extract to a subfolder named after the archive (without extension)
            base = os.path.splitext(name)[0]
            # handle double extensions like .tar.gz
            for ext in (".tar", ".tgz", ".tbz2", ".txz"):
                if base.lower().endswith(ext):
                    base = os.path.splitext(base)[0]
            extract_to = os.path.join(input_dir, f"_extracted_{base}")
            os.makedirs(extract_to, exist_ok=True)
            extracted = extract_archive(path, extract_to)
            audio_files.extend(extracted)
    return audio_files


# ─── file discovery ──────────────────────────────────────────────────────────

def find_audio_files(directory: str, paths_from_archive: list[str] = None) -> list[str]:
    """Recursively find all supported audio files. Deduplicate and sort."""
    found = set()
    if paths_from_archive:
        for p in paths_from_archive:
            ext = os.path.splitext(p)[1].lower()
            if ext in SUPPORTED_FORMATS:
                found.add(os.path.abspath(p))

    # Also walk the directory for any audio files (including in extracted folders)
    if os.path.isdir(directory):
        for root, dirs, files in os.walk(directory):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in SUPPORTED_FORMATS:
                    found.add(os.path.abspath(os.path.join(root, fname)))

    return sorted(found)


# ─── audio splitting ────────────────────────────────────────────────────────

def get_audio_duration(filepath: str) -> float:
    """Return duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", filepath],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def split_audio(filepath: str, max_bytes: int, temp_dir: str) -> list[tuple[str, float]]:
    """Split audio into chunks each under max_bytes. Returns list of (path, offset_seconds)."""
    duration = get_audio_duration(filepath)
    size = os.path.getsize(filepath)

    # Estimate bytes-per-second, then chunk duration to stay under max_bytes
    bps = size / duration
    chunk_duration = (max_bytes * 0.9) / bps  # 10% safety margin

    if chunk_duration >= duration:
        return [(filepath, 0.0)]

    num_chunks = max(2, int(duration / chunk_duration) + 1)
    chunk_len = duration / num_chunks

    basename = os.path.splitext(os.path.basename(filepath))[0]
    ext = os.path.splitext(filepath)[1]

    base_sanitized = basename.replace(" ", "_")
    out_pattern = os.path.join(temp_dir, f"{base_sanitized}_chunk_%03d{ext}")

    print(f"  文件 {os.path.basename(filepath)} 过大 ({size // 1024 // 1024}MB)，切割为 {num_chunks} 段...")

    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "quiet",
            "-i", filepath,
            "-f", "segment",
            "-segment_time", str(chunk_len),
            "-c", "copy",
            out_pattern,
        ],
        check=True,
    )

    chunk_files = sorted(
        os.path.join(temp_dir, f)
        for f in os.listdir(temp_dir)
        if f.endswith(ext) and f.startswith(f"{base_sanitized}_chunk_")
    )

    # Compute offset for each chunk
    result = []
    for idx, cf in enumerate(chunk_files):
        offset = idx * chunk_len
        result.append((cf, offset))
    return result


# ─── transcription ──────────────────────────────────────────────────────────

def transcribe_file(client: OpenAI, audio_path: str) -> list | None:
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in SUPPORTED_FORMATS:
        return None

    size = os.path.getsize(audio_path)
    if size > MAX_FILE_SIZE:
        # Should have been split already; if we reach here, something's wrong
        size_mb = size / (1024 * 1024)
        print(f"  错误: 文件 {size_mb:.1f}MB 超过 25MB 限制，且未能切割。")
        return None

    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model=GROQ_MODEL,
            file=f,
            response_format="verbose_json",
            language="zh",
        )
    return transcription.segments


def format_markdown(segments: list, title: str) -> str:
    lines = [f"# {title}", ""]
    for seg in segments:
        timestamp = seconds_to_mmss(seg.start)
        lines.append(f"**{timestamp}** {seg.text.strip()}")
        lines.append("")
    return "\n".join(lines)


# ─── main pipeline ──────────────────────────────────────────────────────────

def process_single_file(client: OpenAI, audio_path: str) -> list | None:
    """Transcribe one file, splitting it first if too large. Returns all segments with
    corrected timestamps (chunk offsets applied)."""
    size = os.path.getsize(audio_path)
    if size <= MAX_FILE_SIZE:
        return transcribe_file(client, audio_path)

    # File too large — split, transcribe chunks, merge with offset correction
    require_ffmpeg()
    global TEMP_DIR
    if TEMP_DIR is None:
        TEMP_DIR = tempfile.mkdtemp(prefix="audio_trans_")

    try:
        chunks = split_audio(audio_path, MAX_FILE_SIZE, TEMP_DIR)
    except subprocess.CalledProcessError as e:
        print(f"  切割失败: {e}")
        return None
    except json.JSONDecodeError:
        print("  无法读取音频时长，格式可能不支持")
        return None

    if len(chunks) == 1:
        # No split was actually needed (edge case where estimate said split but
        # ffmpeg produced only one chunk)
        return transcribe_file(client, chunks[0][0])

    all_segments = []
    for i, (chunk_path, offset) in enumerate(chunks):
        chunk_name = os.path.basename(chunk_path)
        print(f"  转写片段 {i + 1}/{len(chunks)}: {chunk_name}...", end=" ", flush=True)
        segments = transcribe_file(client, chunk_path)
        if segments is not None:
            # Apply time offset so timestamps are relative to original file start
            for seg in segments:
                seg.start += offset
                seg.end += offset
            all_segments.extend(segments)
            print("✓")
        else:
            print("✗")
            return None

    return all_segments


def run_pipeline():
    global TEMP_DIR

    api_key = load_api_key()
    print(f"✓ 成功读取 API key (长度: {len(api_key)})")

    os.makedirs(INPUT_DIR, exist_ok=True)

    # Step 1: Extract archives, if any
    print("\n--- 扫描压缩包 ---")
    extracted_paths = process_archives(INPUT_DIR)

    # Step 2: Find all audio files (incl. extracted ones, recursive)
    print("\n--- 扫描音频文件 ---")
    audio_files = find_audio_files(INPUT_DIR, extracted_paths)

    if not audio_files:
        print("未发现支持的音频文件，请将文件放入 input/ 目录后重试。")
        print(f"支持格式: {', '.join(SUPPORTED_FORMATS)}")
        return

    total = len(audio_files)
    print(f"发现 {total} 个音频文件\n")

    # Step 3: Transcribe
    client = OpenAI(base_url=GROQ_BASE_URL, api_key=api_key)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    success = 0
    failed_files = []
    # Track group info: original basename -> output path (for merged results)
    # Files from splitting share the same original base name

    for i, audio_path in enumerate(audio_files):
        filename = os.path.basename(audio_path)
        display_name = os.path.relpath(audio_path, INPUT_DIR)
        print(f"[{i + 1}/{total}] 正在转写 {display_name}...", end=" ", flush=True)

        segments = process_single_file(client, audio_path)
        if segments is not None:
            out_name = os.path.splitext(filename)[0] + ".md"
            out_path = os.path.join(OUTPUT_DIR, out_name)
            md_content = format_markdown(segments, os.path.splitext(filename)[0])
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            print("✓")
            success += 1
        else:
            print("✗")
            failed_files.append(audio_path)

    # Step 4: Retry failures
    for round_num in range(1, MAX_RETRY_ROUNDS + 1):
        if not failed_files:
            break
        print(f"\n--- 第 {round_num} 轮重试 ({len(failed_files)} 个文件) ---")
        time.sleep(RETRY_DELAY)

        still_failed = []
        for audio_path in failed_files:
            filename = os.path.basename(audio_path)
            print(f"  正在重试 {filename}...", end=" ", flush=True)
            segments = process_single_file(client, audio_path)
            if segments is not None:
                out_name = os.path.splitext(filename)[0] + ".md"
                out_path = os.path.join(OUTPUT_DIR, out_name)
                md_content = format_markdown(segments, os.path.splitext(filename)[0])
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print("✓")
                success += 1
            else:
                print("✗")
                still_failed.append(audio_path)
        failed_files = still_failed

    # Step 5: Cleanup temp files
    cleanup_temp()

    # Report
    print(f"\n{'=' * 40}")
    print(f"转写完成！成功: {success}, 失败: {len(failed_files)}")
    if failed_files:
        print("失败文件:")
        for f in failed_files:
            print(f"  - {os.path.basename(f)}")
    print(f"Markdown 输出保存在 {OUTPUT_DIR}/")


def cleanup_temp():
    global TEMP_DIR
    if TEMP_DIR and os.path.isdir(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        TEMP_DIR = None


if __name__ == "__main__":
    try:
        run_pipeline()
    finally:
        cleanup_temp()
