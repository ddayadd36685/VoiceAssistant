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

其中 VAD 支持以下可选项（用于控制“静音判停”与录音时长等行为）：
- `vad.silence_threshold`
- `vad.max_recording_sec`
- `vad.wakeup_silence_limit_sec`（默认 2.5）
- `vad.wakeup_silence_ramp_sec`（默认 1.0）

## 测试

```bash
python -m pytest -q
```

## 常见问题

### 模型太大怎么处理？

仓库默认忽略 `voice_assistant/models/`，避免把大体积模型提交到 Git。你可以通过 `tests/` 目录下的下载脚本按需获取模型。

