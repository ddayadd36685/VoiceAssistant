# 实施计划（阶段一：离线唤醒词语音助手 + MCP 打开文件）

目标：实现一个可在 Windows 11 后台常驻运行的离线语音助手，流程为「唤醒词 → 录音（VAD）→ 本地 ASR → 规则解析 → 通过 MCP 工具执行 open_file」。使用rich包美化终端输出

## 0. 约束与原则

- 唤醒词检测、录音、ASR 均离线完成
- 本项目不直接执行 shell/PowerShell 命令
- 文件相关操作全部通过 MCP server 暴露的工具完成
- 模块解耦：唤醒 / 录音 / ASR / 解析 / MCP / 状态机互相独立
- 每个模块的功能清晰，职责分明。
- 每个文件夹下包含一个test文件，用于一次性测试该模块各个文件的功能。

## 1. 代码结构落地

预期结构（与需求说明书一致）：

```
voice_assistant/
├── main.py
├── voice_assistant/
│   ├── __init__.py
│   ├── audio_stream.py
│   ├── wakeword.py
│   ├── vad_recorder.py
│   ├── asr.py
│   ├── parser.py
│   ├── mcp_client.py
│   ├── test.py
│   └── state_machine.py
└── mcptool/
    ├── __init__.py
    ├── find_file.py
    ├── test.py
    └── open_file.py
```

交付物：
- `main.py`：唯一入口；读取配置、启动状态机、启动音频采集、注册回调
- `voice_assistant/*`：核心逻辑包
- `mcptool/*`：MCP server 工具实现（或其适配/封装），与核心逻辑解耦

## 2. 音频采集与 Ring Buffer（audio_stream）

要做的事：
- 以 16kHz/mono/16-bit PCM 采集麦克风音频
- 提供固定长度 ring buffer，用于 pre-roll（回溯 0.5–1.0 秒音频）
- 输出统一的帧格式（bytes 或 numpy array），供 wakeword/vad 使用

验收点：
- 连续采集稳定，无明显断裂
- 可获取「最近 N 秒」音频片段用于拼接

## 3. 唤醒词检测（wakeword）

要做的事：
- 在 `IDLE` 状态持续消费音频帧
- 触发条件：检测到固定中文唤醒词（离线）
- 触发后进入 cooldown，避免重复唤醒

验收点：
- 唤醒延迟可接受（主观体验）
- cooldown 生效

## 4. 录音 + VAD 结束检测（vad_recorder）

要做的事：
- 被唤醒后开始录音
- 拼接 pre-roll 音频，避免漏掉第一句话
- 运行 VAD 判断说话结束，生成一段完整音频（wav/pcm）

验收点：
- 能生成可播放的音频文件（或内存中的音频 buffer）
- 录音结束判断稳定：不会过早截断，也不会无限等待

## 5. 本地 ASR（asr）

要做的事：
- 输入：录音音频（路径或 buffer）
- 输出：完整中文文本（字符串）
- 延迟允许 1–3 秒级

验收点：
- 输出文本可用于规则解析
- 失败时给出可恢复的错误/空文本处理策略

## 6. 规则意图解析（parser）

要做的事：
- 解析“打开 XXX / 帮我打开 XXX / 开启 XXX / XXX 打开一下”等表达
- 输出统一结构：`intent` + `target`
- 解析失败输出 `unknown`

验收点：
- 覆盖需求中的典型表达
- 能从文本里稳定提取 target

## 7. MCP 调用封装（mcp_client）

要做的事：
- 对接既有 MCP server
- 暴露方法：
  - `find_file(query, base_dirs, limit)`
  - `open_file(target)`
- 处理网络/协议错误，输出结构化结果给状态机

验收点：
- 能调用 `find_file` 返回候选路径
- 能调用 `open_file` 打开目标文件并返回结果

## 8. 状态机与全链路串联（state_machine + main）

状态：
- `IDLE`：监听唤醒
- `LISTENING`：录音 + VAD
- `THINKING`：ASR + 解析
- `EXECUTING`：调用 MCP
- 返回 `IDLE`

要做的事：
- 将每个模块以事件/回调方式串起来
- 统一错误处理：任何阶段失败都可回到 `IDLE`
- 关键日志（不要泄露隐私/路径细节，必要时脱敏）

验收点：
- 说出唤醒词后进入录音
- 说出“打开 XXX”后能触发 MCP 打开文件
- 执行完成后回到待机

## 9. mcptool（独立目录）

要做的事（两种选择择一）：
- 如果 MCP server 由本项目提供：在 `mcptool/` 里实现 `find_file` 与 `open_file`
- 如果 MCP server 外部已存在：在 `mcptool/` 里放适配层/调用示例与约束（例如 base_dirs 白名单）

安全要求：
- 路径规范化
- 目录白名单
- 防止路径穿越

验收点：
- 仅能访问白名单目录
- 对非法路径请求能拒绝并返回明确错误

## 10. 测试与运行检查

要做的事：
- 冒烟测试：全链路跑通一次（含失败路径）
- 模块级测试（优先）：parser、路径规范化、find_file 的过滤规则
- 性能检查：CPU 占用与延迟（主观 + 粗略指标）

验收点：
- 满足需求说明书「验收标准（阶段一）」

