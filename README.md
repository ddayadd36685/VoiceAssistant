# VoiceAssistant

一个本地运行的语音助手项目，包含后端服务（FastAPI + WebSocket）与桌面悬浮球 UI（PyQt6）。推荐使用统一入口启动：`run_app.py`。

## 功能

- 悬浮球 UI：常驻桌面，展示“已唤醒/我听到/执行结果”等状态
- 唤醒词（KWS）：支持在设置里配置多个唤醒词（需重启生效）
- 录音与静音判停（VAD）：唤醒后自动录音，检测静音后结束并进入识别
- ASR 可切换：支持 Sherpa-ONNX 或 FunASR（SenseVoiceSmall）
- 意图解析与执行：支持将语音解析为“打开文件/打开网页”等动作并执行
- 本地优先：核心流程在本机运行；LLM 用于解析/闲聊（可通过环境变量禁用）

## 适用场景

- 桌面快捷启动：用语音打开常用软件、文件或网页
- 半自动工作流：通过“意图解析 → 动作执行”把口头指令变成可重复操作
- 本地语音交互试验：在 Windows 上快速搭一套“唤醒词 + 录音 + 识别 + 指令”闭环

## 架构与工作流

本项目由两部分组成：

- 后端服务（FastAPI）：负责语音链路、状态机、解析与执行，并通过 WebSocket 推送事件
- 桌面 UI（PyQt6 悬浮球）：负责展示状态、打开设置界面、接收后端事件并提示用户

一次完整交互通常是：

1. 监听唤醒词（KWS）
2. 唤醒后开始录音，并用静音检测决定何时停止（VAD）
3. 将录到的音频送入 ASR 得到文本
4. Parser 对文本进行意图解析：产出“要做什么 + 目标是什么”以及可选的自然回复
5. 执行动作（例如打开文件/网页），并把结果通过事件流回传 UI

## 目录结构（关键文件）

- `run_app.py`：推荐入口，一键启动 UI + 后端，并负责后端子进程的生命周期
- `run_server.py`：仅启动后端（调试用）
- `run_ui.py`：仅启动 UI（调试用）
- `voice_assistant/server.py`：FastAPI 服务与 WebSocket 事件流
- `voice_assistant/ui/app.py`：悬浮球 UI 与设置界面
- `voice_assistant/wakeword.py`：唤醒词检测（Sherpa-ONNX KWS）
- `voice_assistant/asr.py`：ASR 后端封装（Sherpa / FunASR）
- `voice_assistant/parser.py`：意图解析（LLM 驱动）
- `mcp_config/file_config.yaml`：允许“打开文件”的关键词与路径映射
- `mcp_config/web_config.yaml`：允许“打开网页”的关键词与 URL 映射

## 环境要求

- Windows
- Python 3.10+（建议使用虚拟环境）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动方式

### 推荐：一键启动（UI + 后端）

```bash
python run_app.py
```

启动流程：
- 自动拉起后端子进程（若检测到后端已在运行则不会重复启动）
- 轮询 `GET /v1/health` 做健康检查
- 启动悬浮球 UI
- 退出时自动清理后端子进程（仅清理由 `run_app.py` 拉起的后端）

### 分别启动（调试用）

后端：

```bash
python run_server.py
```

UI：

```bash
python run_ui.py
```

## 后端接口

- 健康检查：`GET http://127.0.0.1:8000/v1/health`
- 状态：`GET http://127.0.0.1:8000/v1/status`
- 事件流：`WS ws://127.0.0.1:8000/v1/events`

## 配置

主配置文件：`config.yaml`

### audio（录音前缓存）

用于控制“唤醒时带上前几秒音频”，减少刚开口时的截断：

- `audio.pre_roll_sec`：预录音时长（秒）

### ASR（语音识别引擎）

支持的引擎：
- `sherpa`（Sherpa-ONNX）
- `funasr`（FunASR / SenseVoiceSmall）

示例：

```yaml
asr:
  provider: funasr
  sherpa:
    model_path: voice_assistant/models/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23
  funasr:
    model_name: iic/SenseVoiceSmall
    device: cuda   # 可选：cuda/cpu
```

在 UI 的“设置”里切换 ASR 引擎后会触发重启。

### KWS（唤醒词）

唤醒词在 UI 的“设置”→“主配置”里配置（需重启生效），会写入 `config.yaml` 的 `kws.keywords`。

```yaml
kws:
  keywords: ["你好小梦", "小梦同学"]
```

当 `kws.keywords` 为空时，会使用模型自带的关键词文件（`voice_assistant/models/.../keywords.txt`）。当配置了自定义唤醒词时，会在本地生成 `mcp_config/custom_keywords.txt` 并在启动时优先加载它。

### VAD（静音判停）

用于控制录音何时结束与最长录音时间：

- `vad.silence_threshold`：静音阈值（RMS），越小越敏感
- `vad.max_recording_sec`：最大录音时长（秒）
- `vad.wakeup_silence_limit_sec`：刚唤醒后的“允许静音”秒数
- `vad.wakeup_silence_ramp_sec`：从初始静音限制逐步收紧到默认阈值的过渡时长

### LLM（意图识别 + 闲聊）

当前 Parser 完全由大模型驱动：既能给系统返回可执行的指令（如打开文件/网页），也能返回对用户的自然回复（闲聊/问答）。

需要配置 DeepSeek API Key（二选一）：
- 系统环境变量：`DEEPSEEK_API_KEY`
- 或在项目根目录创建/编辑 `.env`，写入：`DEEPSEEK_API_KEY=你的key`

注意：不要把真实 Key 提交到仓库。

可选：通过环境变量禁用大模型（便于离线调试或跑测试）：

```bash
set VOICE_ASSISTANT_DISABLE_LLM=1
```

## 指令与白名单（打开文件/网页）

为了安全起见，“打开文件/网页”采用白名单机制：只允许打开你在 `mcp_config` 里显式配置过的目标。

- 文件白名单：`mcp_config/file_config.yaml`（关键词 → 本机绝对路径）
- 网页白名单：`mcp_config/web_config.yaml`（关键词 → URL）

配置完成后，语音里出现对应关键词时，Parser 会解析出动作并交给执行器处理。

## 语音识别模式

当前是“录完一段再识别”的非流式模式：唤醒后录音直到检测到静音结束，然后把整段音频送去识别，再进入解析与执行。

## 测试

```bash
python -m pytest -q
```

## 常见问题

### Notice: ffmpeg is not installed

这是提示不是报错：未安装 ffmpeg 时，会使用 `torchaudio` 做音频解码。通常不影响录音识别流程。

### 模型太大怎么处理？

仓库默认忽略 `voice_assistant/models/`，避免把大体积模型提交到 Git。你可以通过 `tests/` 目录下的下载脚本按需获取模型。

