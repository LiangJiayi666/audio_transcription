# 录音批量转写工具

使用 Groq API 调用 Whisper Large V3 Turbo 模型，将 `input/` 目录下所有音频文件批量转写为带时间戳的中文 Markdown，输出到 `output/` 目录。

## 安装

```bash
pip install -r requirements.txt
```

## 配置

1. 在项目根目录创建 `groq_key.md` 文件
2. 将你的 Groq API key 写入文件第一行

```
sk-your-groq-api-key
```

## 使用

将音频文件放入 `input/` 目录，然后运行：

```bash
python main.py
```

## 支持的格式

- `.mp3` `.wav` `.m4a` `.flac` `.ogg` `.webm`

## 注意事项

- Groq API 单文件上限 25MB
- 转写语言固定为中文（zh）
