# MCP 媒体工具接入调研

## 结论摘要

当前 Wanzhi 的语音链路已经具备本地 function tool calling 能力。用户语音经过唤醒、录音、ASR 后，会进入 `VoiceAgent` 的 ReAct 循环，由 llama.cpp/Qwen 根据 `TOOL_SCHEMAS` 选择工具，再通过 `ActionRegistry.execute_tool()` 执行本地动作。

因此，接入 MCP 的最小路径不是重做语音交互，而是在现有工具执行层后面增加一个 MCP/media bridge：

```text
用户语音
  -> VoicePipeline
  -> VoiceAgent
  -> function tool call
  -> ActionRegistry.execute_tool()
  -> 本地 Action 或 MCP/media bridge
  -> ToolResult
  -> 最终口语确认
```

播放音乐、播放故事、停止播放这类能力可以先暴露为普通 function tools，例如 `play_music`、`play_story`、`stop_media`。对模型来说它们和药单、急救、切屏工具一样；对执行层来说，它们可以转发给本地 MCP server、媒体 daemon 或直接调用播放器。

喜马拉雅类内容建议先抽象成 `play_story` 的 provider，不要把抓取、账号、鉴权和播放逻辑塞进 `wanzhi-voice` 主流程。这样后续可以替换为本地音频库、合法 API、MCP server 或其他音频源。

## 当前语音工具链路

主链路集中在 `src/wanzhi/voice/pipeline.py`：

```text
WakeWordDetector
  -> SpeechRecorder
  -> VoskSTT / SherpaSTT
  -> VoiceAgent
  -> ActionRegistry tools
  -> TTSManager + SpeechQueue
  -> AudioPlayer
  -> EventBus
```

关键代码边界：

- `src/wanzhi/voice/daemon.py`：`wanzhi-voice` 进程入口，创建 `VoicePipeline`。
- `src/wanzhi/voice/pipeline.py`：语音主编排，负责唤醒、录音、ASR、agent 回复和 TTS 播放。
- `src/wanzhi/voice/agent.py`：ReAct 风格 agent，调用 LLM，并在检测到 tool call 后执行工具。
- `src/wanzhi/voice/tools.py`：静态定义当前 function tool schemas 和 system prompt。
- `src/wanzhi/actions/registry.py`：工具执行中枢，`execute_tool()` 是最重要的扩展点。
- `src/wanzhi/voice/llm_llamacpp.py`：封装 llama.cpp chat completion，并解析 Qwen 可能输出的 `<tool_call>` 文本。

`VoicePipeline` 当前会把 `ActionRegistry.execute_tool` 直接注入给 `VoiceAgent`：

```text
VoiceAgent(
  llm=self.llm,
  tool_executor=self.actions.execute_tool,
  max_steps=...
)
```

这说明工具执行层已经和 agent 解耦，适合在 `ActionRegistry` 后面挂 MCP。

## 现有工具能力

`src/wanzhi/voice/tools.py` 目前定义了 6 个工具：

| 工具 | 作用 | 执行位置 |
| --- | --- | --- |
| `switch_ui_screen` | 切换到药单或摄像头界面 | `ActionRegistry.execute_tool()` |
| `show_medication_list` | 展示今日药单并口头总结 | `MedicationActions.show_today()` |
| `open_medication_for_confirmation` | 打开药单供确认或添加 | `MedicationActions.schedule_from_text()` |
| `trigger_emergency` | 触发紧急求助 | `EmergencyActions.trigger()` |
| `change_voice` | 切换 TTS 音色 | `ActionRegistry._change_voice()` |
| `end_conversation` | 结束当前语音会话 | `ActionRegistry.execute_tool()` |

Legacy 路径也存在：当 `llm.provider` 是 `ollama` 时，系统会绕过 `VoiceAgent`，使用 `IntentRouter` 做关键词意图识别，再调用 `ActionRegistry.handle()`。这条路径目前没有 function tool calling。因此如果要兼容 Ollama fallback，需要在 `src/wanzhi/voice/router.py` 和 `ActionRegistry.handle()` 中补充“播放音乐/讲故事/停止播放”的关键词处理。

## 当前可复用点

### 事件总线

项目没有 HTTP/REST 后端，服务间通信主要使用本地 IPC：

- `ipc:///tmp/wanzhi-events.sock`：ZeroMQ PUSH/PULL 事件总线。
- `ipc:///tmp/wanzhi-vision-alerts.sock`：跌倒告警 PUB/SUB。
- `data/events.jsonl`：可选审计日志。

媒体状态可以沿用事件模式，例如：

```text
media.play_requested
media.playing
media.stopped
media.error
```

这样 UI 后续可以监听播放状态，语音侧也可以在紧急告警时打断媒体。

### 外部进程播放

`src/wanzhi/voice/audio_player.py` 已经有一个很小的 subprocess 播放封装：

- 用 `pw-play` 或 `aplay` 播放 TTS 生成的 WAV 文件。
- 支持 `stop()` 终止当前播放进程。
- `play()` 当前是同步阻塞等待播放结束。

这个实现可以作为长媒体播放器的参考，但不建议直接复用为音乐/故事播放器。原因是 TTS 播报和长媒体播放的生命周期不同：TTS 是短句队列，音乐/故事是长时播放，需要后台进程、停止、暂停、恢复、状态上报和与 TTS 的互斥策略。

### 工具执行返回

`ToolResult` 目前包含：

```text
observation: str
spoken_reply: str | None
end_session: bool
```

这足够表达媒体工具的结果。例如：

- `observation`: `已开始播放故事：西游记第一回。`
- `spoken_reply`: `好的，开始播放西游记。`
- `end_session`: 播放类工具应保持 `False`，不要结束会话。

## 推荐架构

推荐分两步做。

第一步先做同步最小闭环：

```text
VoiceAgent
  -> ActionRegistry.execute_tool("play_story")
  -> MediaToolBridge
  -> MCP client 或本地播放器
  -> ToolResult
```

这个方案改动最少，适合验证 Qwen 是否能稳定调用媒体工具，以及声卡播放是否正常。

第二步再把长媒体播放迁移成独立 sidecar：

```text
VoiceAgent
  -> ActionRegistry.execute_tool("play_story")
  -> bus.emit(media.play_requested)
  -> wanzhi-media daemon
  -> MCP server / provider / player
  -> bus.emit(media.playing / media.stopped)
```

这个方案更适合实际运行，因为音乐和故事播放可能持续很久，不应该阻塞 `wanzhi-voice` 的 agent 推理循环。

## MCP 适配方式

项目目前没有 MCP 依赖，也没有 MCP 客户端/服务端代码。若使用 Python MCP SDK，典型模式是：

```text
StdioServerParameters(command=..., args=...)
  -> stdio_client(...)
  -> ClientSession(...)
  -> session.initialize()
  -> session.list_tools()
  -> session.call_tool(name, arguments)
```

在 Wanzhi 中可以封装为 `McpToolClient`：

```text
McpToolClient
  - load servers from config
  - list_tools()
  - call_tool(server_name, tool_name, args)
  - convert result content to ToolResult observation
  - enforce timeout
```

如果目标只是播放本地文件或 URL，MCP 层可以先非常薄：

- MCP server 负责解析“播放什么”，返回 URL、本地文件路径或结构化播放指令。
- Wanzhi 的 media bridge 负责实际调用 `mpv`、`ffplay` 或系统播放器。

这样可以避免让外部 MCP server 直接控制本机声卡，也方便统一实现停止、打断和事件上报。

## 建议新增工具

### `play_music`

用于播放音乐。

参数建议：

```json
{
  "query": "用户想听的歌曲、歌手、风格或歌单",
  "source": "可选，local / url / provider",
  "mood": "可选，轻松、怀旧、安静等"
}
```

### `play_story`

用于播放故事、有声书、戏曲、评书或喜马拉雅类内容。

参数建议：

```json
{
  "query": "故事名、人物、类型或用户原话",
  "provider": "可选，例如 ximalaya / local",
  "episode": "可选，集数或章节"
}
```

### `stop_media`

用于停止当前音乐或故事播放。

参数建议：

```json
{
  "reason": "可选，用户原话或停止原因"
}
```

后续可以扩展：

- `pause_media`
- `resume_media`
- `next_media`
- `set_media_volume`

## 最小改动清单

P0：验证工具调用和播放闭环。

- 修改 `src/wanzhi/voice/tools.py`
  - 新增 `play_music`、`play_story`、`stop_media` schema。
  - 更新 `SYSTEM_PROMPT`，要求涉及音乐、故事、有声内容时优先调用工具。
- 修改 `src/wanzhi/actions/registry.py`
  - 在 `execute_tool()` 中分发媒体工具。
  - 返回清晰的 `ToolResult`。
- 新增 `src/wanzhi/actions/media.py` 或 `src/wanzhi/integrations/media.py`
  - 封装播放请求、停止请求和错误处理。
  - MVP 可先用假实现或本地文件播放。
- 修改 `config/default.yaml`
  - 增加 `media.*` 和可选 `mcp.*` 配置。
- 增加测试
  - 覆盖 `ActionRegistry.execute_tool("play_story", ...)`。
  - 覆盖未知媒体工具或播放失败时的返回。

P1：接入真正 MCP。

- 修改 `pyproject.toml`
  - 增加 MCP client 依赖。
- 新增 `src/wanzhi/integrations/mcp_client.py`
  - 连接 stdio MCP server。
  - 发现工具并调用工具。
  - 统一超时和异常转换。
- 让 media action 调 MCP 获取播放目标。

P2：做成长媒体服务。

- 新增 `src/wanzhi/media/daemon.py`
  - 订阅媒体请求或由 registry 直接调用。
  - 管理 `mpv`/`ffplay` 后台进程。
  - 上报 `media.playing`、`media.stopped`、`media.error`。
- 修改 `src/wanzhi/core/events.py`
  - 增加 `media.*` 事件类型。
- 可选修改 `src/wanzhi/ui/app.py`
  - 展示当前播放状态。

## 配置草案

可以在 `config/default.yaml` 中增加：

```yaml
media:
  enabled: true
  player: mpv
  default_provider: local
  stop_tts_before_play: true
  library_dir: data/media

mcp:
  enabled: false
  timeout_seconds: 8
  servers:
    media:
      transport: stdio
      command: .venv/bin/python
      args:
        - scripts/mcp_media_server.py
```

如果后续要接喜马拉雅，建议不要把账号或 cookie 写进默认配置。可用环境变量或本地未入库配置文件承载敏感信息。

QQ 音乐的网页 Cookie 通过环境变量提供：

```bash
QQ_MUSIC_COOKIE="uin=...; qqmusic_key=...; qm_keyst=..."
```

安装 systemd 服务后，`wanzhi-voice.service` 会可选读取 `data/secrets/media.env`。该目录已被 `.gitignore` 忽略，适合放本机 Cookie：

```bash
mkdir -p data/secrets
cat > data/secrets/media.env <<'EOF'
QQ_MUSIC_COOKIE='uin=...; qqmusic_key=...; qm_keyst=...'
EOF
systemctl --user daemon-reload
systemctl --user restart wanzhi-voice.service
```

## 主要风险

### 音频互斥

TTS 和音乐/故事都会占用声卡。当前 `SpeechQueue` 只管理 TTS 队列，不知道是否有长媒体在播放。需要定义策略：

- 播放媒体前是否停止当前 TTS。
- 媒体播放中是否允许丸智继续说话。
- 紧急告警是否必须打断媒体。
- 用户唤醒时是否降低媒体音量或暂停媒体。

### 同步阻塞

`ActionRegistry.execute_tool()` 在 agent 推理流程内同步执行。如果 MCP 调用、网络搜索或喜马拉雅解析很慢，会卡住整个语音回复。MVP 可以接受短超时；正式方案应把播放请求交给 media daemon。

### Provider 不确定性

喜马拉雅可能涉及账号、授权、内容版权、反爬策略和接口稳定性。工程上应把它放在 provider/MCP server 后面，Wanzhi 主程序只依赖“给定 query 后返回可播放项目或播放失败原因”的稳定接口。

### Ollama fallback 不支持 tools

当前只有 `llm.provider: llama-cpp` 时启用 `VoiceAgent` 和 function tool calling。若切到 Ollama，播放类能力需要通过 `IntentRouter` 补关键词 fallback，否则用户说“放首歌”会走普通聊天。

### 树莓派资源

本地 Qwen、ASR、TTS、UI 和流媒体解码同时运行时，CPU、内存和 I/O 压力会上升。媒体播放建议用轻量外部播放器，并避免在 voice 主线程中做重网络或重解析。

## 建议实施顺序

1. 先加 `play_music`、`play_story`、`stop_media` 三个 schema 和 `ActionRegistry` 分发。
2. 先用本地假 media action 验证 Qwen 能稳定调工具，回复不泄漏 `<tool_call>`。
3. 加一个最小播放器，支持本地文件或 URL，优先用 `mpv`。
4. 再接 MCP client，让 MCP server 返回候选音频或播放指令。
5. 最后把长媒体播放拆成 `wanzhi-media` daemon，并补 `media.*` 事件和 UI 状态。

## 推荐 MVP

最小可运行版本可以只做这些：

```text
tools.py:
  + play_music
  + play_story
  + stop_media

registry.py:
  + MediaActions

actions/media.py:
  + play_music(query)
  + play_story(query, provider)
  + stop()

config/default.yaml:
  + media.player
  + media.library_dir
```

MVP 的 `play_story` 可以先从 `data/media/stories/` 中按文件名模糊匹配并播放，确认语音工具闭环稳定后，再把故事来源替换成 MCP/喜马拉雅 provider。
