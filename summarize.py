#!/usr/bin/env python3
"""Post-process transcription output using DeepSeek LLM.
Reorganizes each raw .md transcript into structured meeting notes with
会议纪要, 经验, 待办, and cleaned transcript."""

import os
import re
import sys
from openai import OpenAI

DEEPSEEK_KEY_FILE = "deepseek_key.md"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
OUTPUT_DIR = "output"
SUMMARY_DIR = "summary"

SYSTEM_PROMPT = """你是一个专业的会议纪要整理助手。你的输入是一份带时间戳的会议录音转写（中文）。
请仔细阅读全部内容，生成一份结构化的 Markdown 文档，严格包含以下三个部分：

## 会议纪要
- 提炼会议的核心议题、讨论要点和达成的共识/结论
- 用 5-10 条精炼的要点概括，每条 1-2 句话

## 经验
- 从讨论中提取可复用的经验、方法论、最佳实践、踩坑教训
- 用 5-10 条要点列出，每条包含具体场景和结论

## 待办
- 提取所有待办事项、任务分配、后续安排
- 逐条列出，包含负责人（如有提及）和具体事项；未提及负责人则写"待定"

注意：只输出上述三个部分，不要输出原文转写，不要添加额外解释。"""


def load_api_key() -> str:
    if not os.path.isfile(DEEPSEEK_KEY_FILE):
        print(f"错误: 找不到 {DEEPSEEK_KEY_FILE} 文件。")
        print(f"请复制 {DEEPSEEK_KEY_FILE.replace('.md', '.example.md')} 为 {DEEPSEEK_KEY_FILE} 并写入您的 DeepSeek API Key。")
        sys.exit(1)
    with open(DEEPSEEK_KEY_FILE) as f:
        key = f.readline().strip()
    if not key:
        print(f"错误: {DEEPSEEK_KEY_FILE} 第一行为空。")
        sys.exit(1)
    return key


POLISH_PROMPT = """你是一个中文文本润色助手。请对以下语音转写文本进行整理：
1. 添加合适的标点符号（句号、逗号、问号、顿号、引号等）
2. 修正口语化的表达、重复、语序不通顺之处，使其成为通顺流畅的书面中文
3. 将文本合理分段，使结构清晰易读
4. 保留原文的全部信息，不增删实质性内容

只输出整理后的文本，不要添加任何解释。"""

POLISH_CHUNK_SIZE = 3000  # max chars per chunk before sending to DeepSeek


def _split_text(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks, trying to break at whitespace boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Try to break at a whitespace near the limit
            break_point = text.rfind('\n', start, end)
            if break_point == -1 or break_point < start + chunk_size // 2:
                break_point = text.rfind(' ', start, end)
            if break_point == -1 or break_point < start + chunk_size // 2:
                break_point = end
        else:
            break_point = end
        chunks.append(text[start:break_point].strip())
        start = break_point
    return chunks


def polish_transcript(client: OpenAI, text: str) -> str:
    """Use DeepSeek to add punctuation and smooth out spoken Chinese into readable prose.
    Splits into chunks if text exceeds POLISH_CHUNK_SIZE."""
    if not text.strip():
        return text

    if len(text) <= POLISH_CHUNK_SIZE:
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": POLISH_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            max_tokens=8192,
        )
        return resp.choices[0].message.content

    chunks = _split_text(text, POLISH_CHUNK_SIZE)
    print(f"  文本较长 ({len(text)} 字)，分 {len(chunks)} 段处理...")
    results = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  润色第 {i}/{len(chunks)} 段...", end=" ", flush=True)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": POLISH_PROMPT},
                {"role": "user", "content": chunk},
            ],
            temperature=0.1,
            max_tokens=8192,
        )
        results.append(resp.choices[0].message.content)
        print("✓")

    return '\n\n'.join(results)


def clean_transcript(text: str) -> str:
    """Remove timestamps and markdown headers, return raw text for LLM polishing."""
    text = re.sub(r'^#+\s+.*\n+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*\d{2}:\d{2}\*\*\s*', '', text)
    return text.strip()


def process_file(client: OpenAI, md_path: str):
    transcript = open(md_path, encoding="utf-8").read()

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是会议转写内容，请按要求整理：\n\n{transcript}"},
        ],
        temperature=0.3,
        max_tokens=8192,
    )
    llm_result = resp.choices[0].message.content
    clean_text = clean_transcript(transcript)
    polished = polish_transcript(client, clean_text)

    return f"{llm_result.strip()}\n\n## 原文会议转写\n\n{polished}"


def main():
    api_key = load_api_key()
    client = OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=api_key)

    md_files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".md"))
    if not md_files:
        print("output/ 中没有 .md 文件，请先运行 main.py 进行转写。")
        return

    os.makedirs(SUMMARY_DIR, exist_ok=True)

    for filename in md_files:
        path = os.path.join(OUTPUT_DIR, filename)
        print(f"正在整理 {filename}...")
        try:
            result = process_file(client, path)
            out_path = os.path.join(SUMMARY_DIR, filename)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"  ✓ {SUMMARY_DIR}/{filename} 整理完成")
        except Exception as e:
            print(f"  ✗ {filename} 处理失败: {e}")

    print("\n全部整理完成！")


if __name__ == "__main__":
    main()
