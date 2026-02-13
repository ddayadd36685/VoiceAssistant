# VoiceAssistant

一个本地运行的语音助手项目，包含后端服务（FastAPI + WebSocket）与桌面悬浮球 UI（PyQt6）。推荐使用统一入口启动：`run_app.py`。

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

### LLM（意图识别 + 闲聊）

当前 Parser 完全由大模型驱动：既能给系统返回可执行的指令（如打开文件/网页），也能返回对用户的自然回复（闲聊/问答）。

需要配置 DeepSeek API Key（二选一）：
- 系统环境变量：`DEEPSEEK_API_KEY`
- 或在项目根目录创建/编辑 `.env`，写入：`DEEPSEEK_API_KEY=你的key`

注意：不要把真实 Key 提交到仓库。

其中 VAD 支持以下可选项（用于控制“静音判停”与录音时长等行为）：
- `vad.silence_threshold`
- `vad.max_recording_sec`
- `vad.wakeup_silence_limit_sec`（默认 2.5）
- `vad.wakeup_silence_ramp_sec`（默认 1.0）

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

