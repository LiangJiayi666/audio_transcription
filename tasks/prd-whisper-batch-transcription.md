# PRD: 录音批量转写工具

## 1. Introduction

一个命令行工具，将 `input/` 目录下的所有音频文件批量转写为中文文字，输出带时间戳的 Markdown 文件到 `output/` 目录。使用 **Groq API** 调用 **Whisper Large V3 Turbo** 模型，支持常见音频格式，失败文件自动重试。

## 2. Goals

- 一键批量转写 `input/` 下所有音频文件
- 输出带时间戳分段的 Markdown 文件（同名，`.md` 后缀）
- 转写语言为中文（`zh`）
- 单个文件失败不阻塞其他文件，全部成功文件处理完后重试失败文件（最多 2 次）
- 最终打印转写汇总报告（成功/失败列表）

## 3. User Stories

### US-001: 项目初始化与环境配置
**Description:** 作为使用者，我希望能一键安装依赖并配置 API key，之后即可使用。

**Acceptance Criteria:**
- [ ] `requirements.txt` 列出所有 Python 依赖（`openai`）
- [ ] 从 `groq_key.md` 文件读取 API key（仅第一行，去除首尾空白）
- [ ] `groq_key.md` 加入 `.gitignore`，避免泄露
- [ ] `README.md` 包含安装和使用说明

### US-002: 单文件转写核心逻辑
**Description:** 作为使用者，我希望能将单个音频文件转写为带时间戳的中文 Markdown。

**Acceptance Criteria:**
- [ ] 调用 Groq API (`https://api.groq.com/openai/v1`)，模型 `whisper-large-v3-turbo`
- [ ] 请求参数：`response_format="verbose_json"`，`language="zh"`
- [ ] 将返回的时间戳分段（segments）格式化为 Markdown
- [ ] 输出格式：`## 标题\n\n**00:00** 第一段文字\n\n**00:05** 第二段文字\n\n...`
- [ ] 支持 `.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.webm` 格式
- [ ] 文件大小超过 25MB 时报错提示（Groq 限制）

### US-003: 批量处理与重试机制
**Description:** 作为使用者，我想一次性处理 `input/` 下所有音频，失败的自动排到末尾重试。

**Acceptance Criteria:**
- [ ] 扫描 `input/` 下所有支持的音频文件
- [ ] 逐个转写，成功则输出到 `output/`（同名 `.md`）
- [ ] 失败文件收集到队列，全部首轮完成后统一重试（最多 2 轮）
- [ ] 每次重试间隔 2 秒
- [ ] 最终在终端打印汇总：成功 N 个 / 失败 M 个，列出文件名

### US-004: CLI 入口
**Description:** 作为使用者，我希望能用一条命令运行整个转写流程。

**Acceptance Criteria:**
- [ ] `python main.py` 即可启动批量转写
- [ ] 运行前检查 `groq_key.md` 是否存在且内容不为空，否则报错退出
- [ ] 运行前检查 `input/` 是否有文件，为空则提示并退出
- [ ] 自动创建 `output/` 目录（如不存在）

## 4. Functional Requirements

- FR-1: 项目使用 Python 编写，依赖仅 `openai` SDK
- FR-2: API key 从 `groq_key.md` 文件第一行读取，去除首尾空白，不硬编码在代码中
- FR-3: 支持音频格式：`.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.webm`
- FR-4: 调用 Groq API 的 `/openai/v1/audio/transcriptions` 端点
- FR-5: 请求参数：`model="whisper-large-v3-turbo"`, `response_format="verbose_json"`, `language="zh"`
- FR-6: 超过 25MB 的文件跳过并报告错误
- FR-7: 输出 Markdown 文件，文件名 = 音频文件名（后缀换 `.md`），含时间戳段落
- FR-8: 处理顺序：先处理全部文件，失败文件排在队列末尾，全部首轮完成后重试（最多 2 轮）
- FR-9: 每轮重试间隔 2 秒
- FR-10: 完成后打印汇总：各文件耗时、成功数、失败数、失败文件列表

## 5. Non-Goals（不在范围内）

- 不支持实时/流式转写
- 不支持非中文语言转写（固定 `language="zh"`）
- 不提供 Web UI 或 GUI
- 不支持音频预处理（降噪、切割等）
- 不监控文件夹变化自动触发转写
- 不输出 `.srt`、`.vtt` 字幕格式

## 6. Design Considerations

- **输出 Markdown 格式**：每个音频文件生成一个同名的 `.md` 文件，以音频文件名作为一级标题，按时间戳分段。段落间用空行分隔，便于阅读。
- **终端输出**：处理过程中实时反馈进度（`[1/3] 正在转写 audio1.mp3... ✓`），最终打印汇总表。

## 7. Technical Considerations

- **Groq API 端点**：`https://api.groq.com/openai/v1/audio/transcriptions`
- **兼容 OpenAI SDK**：直接使用 `openai.OpenAI` 客户端，修改 `base_url` 即可
- **文件大小限制**：Groq 单文件上限 25MB
- **速率限制**：注意 Groq 的 rate limit，串行处理避免触发限制
- **超时设置**：建议设置 120s 超时，大文件转写可能耗时较长

## 8. Success Metrics

- `python main.py` 一条命令完成全流程，无需手动干预
- 转写准确率满足阅读需求（Whisper Large V3 Turbo 中文 WER 约 8-10%）
- 失败重试机制确保偶发网络错误不会导致文件遗漏

## 9. Open Questions

- 是否需要支持自定义 prompt（如提供上下文词汇以提高专有名词准确率）？
- 是否需要支持输出纯文本（无时间戳）模式？
- Groq 并发限制是否支持并行处理多文件以加速？
