# Qwen 冷启动延迟分析

## 结论摘要

当前 Wanzhi 的 Qwen 本地模型确实是**懒加载**的：`wanzhi-voice` 服务启动后不会立即把 GGUF 模型加载进内存，而是在第一次真正进入 `llm.chat()` / `llm.generate()` 时才初始化 `llama_cpp.Llama`。

因此，用户指出的“第一次冷启动很慢，可能是把 Qwen 模型从 SD 卡搬到 RAM 的耗时”基本成立，但需要更精确地表述为：

> 首次有效对话时，程序才执行 `llama.cpp` 模型初始化。这个阶段会打开约 2GB GGUF 文件、建立 mmap/上下文、触发大量 page fault，并在 `use_mlock=True` 时尝试锁定部分或全部模型页。若 SD 卡页缓存是冷的，就会表现为从 SD 卡读取模型进入内存的长延迟。

日志中观察到一次首轮有效对话：

```text
11:51:59 识别文本：你 可以 换 一个 温柔 一点 声音 吗
11:53:14 回复文本：好的，已经切换成最接近的老年女声...
```

这次从 STT 完成到回复打印约 **75 秒**。该时间包含 Qwen 首次加载、首轮推理、工具调用处理和 TTS 合成，尚未拆分计时，但冷启动加载很可能是主要贡献之一。

## 当前代码路径

### 1. 服务启动阶段不会加载 GGUF

`VoicePipeline.__init__()` 会创建 LLM client：

```python
self.llm = self._build_llm()
```

但 `_build_llm()` 只是创建 `LlamaCppClient`：

```python
return LlamaCppClient(
    model_path=self.config.path("llm.model_path", "models/llm/qwen2.5-3b-instruct-q4_k_m.gguf"),
    n_ctx=int(self.config.get("llm.n_ctx", 4096)),
    n_threads=int(self.config.get("llm.n_threads", 4)),
    n_gpu_layers=int(self.config.get("llm.n_gpu_layers", 0)),
    use_mlock=bool(self.config.get("llm.use_mlock", True)),
    temperature=float(self.config.get("llm.temperature", 0.4)),
)
```

`LlamaCppClient.__init__()` 只保存参数：

```python
self.model_path = model_path
self.use_mlock = use_mlock
self._llm = None
```

所以此时没有读取 `models/llm/qwen2.5-3b-instruct-q4_k_m.gguf`。

### 2. 首次正文进入模型时才加载

`LlamaCppClient.chat()` 第一行会调用：

```python
llm = self._ensure_model()
```

`_ensure_model()` 中才真正执行：

```python
self._llm = Llama(
    model_path=str(self.model_path),
    n_ctx=self.n_ctx,
    n_threads=self.n_threads,
    n_gpu_layers=self.n_gpu_layers,
    use_mlock=self.use_mlock,
    verbose=False,
)
```

这意味着第一次用户唤醒并说完正文后，才开始付出模型初始化成本。

## 当前配置与运行状态

配置：

```yaml
llm:
  provider: llama-cpp
  model_path: models/llm/qwen2.5-3b-instruct-q4_k_m.gguf
  n_ctx: 4096
  n_threads: 4
  n_gpu_layers: 0
  use_mlock: true
```

systemd：

```ini
LimitMEMLOCK=infinity
```

模型文件：

```text
models/llm/qwen2.5-3b-instruct-q4_k_m.gguf  2.0G
```

首轮有效对话后进程内存：

```text
VmSize: 7516000 kB
VmRSS:  4298560 kB
VmHWM:  4298560 kB
VmLck:   170944 kB
Threads: 11
```

说明模型和上下文确实已经让 `wanzhi-voice` 常驻内存涨到约 **4.3GB RSS**。

不过有一个重要细节：`VmLck` 只有约 **167MB**，明显小于 2GB GGUF 文件。这说明虽然代码设置了 `use_mlock=True`，但当前系统观测到的“已锁定内存”并不是整个模型大小。可能原因包括：

- `llama.cpp`/`llama-cpp-python` 只锁定了部分区域。
- mlock 对 mmap 模型页的统计方式和预期不同。
- mlock 失败或部分失败，但由于 `verbose=False` 没有日志。
- KV cache、运行时 buffer 和模型 mmap 的锁定策略不同。

这部分需要单独验证，不能简单断言“整个 2GB 已被 mlock 锁住”。

## 是否就是“从 SD 卡搬到 RAM”的问题

判断：**大概率是主要原因之一，但不是唯一因素。**

首次慢的组成可能是：

1. GGUF 文件打开和 mmap。
2. 首次 page fault 触发 SD 卡读取。
3. `use_mlock=True` 尝试让页面常驻物理内存。
4. llama.cpp tokenizer / metadata / tensor mapping 初始化。
5. `n_ctx=4096` 对应的 KV cache 和运行时 buffer 分配。
6. 首轮 prompt eval 和 token generation。
7. 工具调用解析和第二轮最终回复生成。
8. 阿里云 TTS 合成和播放。

其中 1-5 是典型冷启动成本；6-8 是每次请求也会发生的运行成本。

## 当前设计的主要问题

### 问题 1：模型加载发生在用户等待路径上

现在流程是：

```text
服务启动
  -> 等待唤醒词
  -> 用户说正文
  -> STT 完成
  -> 第一次调用 llm.chat()
  -> 这时才加载 Qwen GGUF
  -> 用户等待 60s+
```

用户体验上，冷启动成本全部压在第一次对话上。

### 问题 2：没有明确的 warmup 状态

UI/语音层不知道模型是否已准备好。用户第一次问问题时，只看到“卡住”。

### 问题 3：没有加载阶段计时

目前日志只打印：

```text
识别文本：...
回复文本：...
```

没有拆分：

- `llama load start`
- `llama load done`
- `prompt eval start/done`
- `generation start/done`
- `tool call start/done`
- `tts start/done`

因此现在只能推断，不能精确归因。

## 可讨论的解决方向

### 方案 A：服务启动时预加载 Qwen

在 `VoicePipeline.__init__()` 完成后主动调用：

```python
self.llm.warmup()
```

`warmup()` 内部执行 `_ensure_model()`，也可以跑一个极短 prompt。

优点：

- 第一次用户对话不会付模型加载成本。
- 启动慢但体验更可控。
- 可以在 UI 显示“模型准备中”。

缺点：

- `wanzhi-voice` 启动会变慢。
- 服务重启时会立即占用 4GB 左右 RSS。
- 如果模型加载失败，voice 服务可能反复重启，需加降级策略。

### 方案 B：后台异步预热

服务启动后立即进入唤醒监听，同时后台线程加载模型：

```text
wanzhi-voice 启动
  -> wake word 立即可用
  -> 后台加载 Qwen
  -> UI 显示“本地模型准备中”
```

优点：

- 唤醒词可尽快可用。
- 如果用户稍后才问问题，Qwen 可能已经热好了。

缺点：

- 如果用户刚启动就问，仍可能遇到模型未就绪。
- 需要线程安全保护 `_llm` 初始化。
- 后台加载期间 CPU/IO 抢占可能影响唤醒识别。

### 方案 C：拆分 LLM 为常驻独立进程

把 Qwen 作为独立 daemon，例如：

```text
wanzhi-llm.service
  -> 启动时加载并持有 Qwen
wanzhi-voice.service
  -> 通过 ZeroMQ/UDS 请求 LLM
```

优点：

- voice 进程重启不必重新加载模型。
- LLM 生命周期独立，适合长期驻留。
- 后续可以做请求队列、健康检查、预热状态。

缺点：

- 架构复杂度增加。
- 需要定义本地 RPC 协议。
- 工具调用执行要么在 voice 侧，要么跨进程协调。

### 方案 D：使用 llama.cpp server

用 `llama-server` 或 `llama.cpp` server 常驻加载模型，voice 通过 HTTP 或 UDS 请求。

优点：

- 成熟的常驻模型服务。
- 支持预加载、并发、健康检查。
- 避免 Python 进程内模型生命周期问题。

缺点：

- 多一个二进制和服务管理。
- 工具调用格式与现有 `llama-cpp-python` wrapper 需要适配。
- 本地 HTTP 可能比进程内调用略多开销，但通常远小于冷启动成本。

### 方案 E：降低模型/上下文成本

可调项：

- 换更小模型，例如 Qwen2.5-1.5B。
- 降低量化等级或使用更小 GGUF。
- 降低 `n_ctx`，例如 4096 -> 2048。
- `use_mlock=false`，减少启动时强制驻留成本，但可能带来运行时 page fault。

优点：

- 最直接降低内存和加载成本。

缺点：

- 能力下降。
- `use_mlock=false` 可能让 SD 卡抖动回到推理中途。

## 建议优先级

推荐与 Gemini 讨论时按以下顺序评估：

1. **先加计时日志**：确认 75 秒里到底加载、推理、TTS 各占多少。
2. **短期修复：后台异步预热**：启动后立刻加载模型，但不阻塞 UI/wake。
3. **中期方案：独立 `wanzhi-llm.service`**：让模型常驻，voice 重启不影响 Qwen 热状态。
4. **同时验证 `use_mlock` 是否真的锁住模型页**：当前 `VmLck` 只有约 167MB，需要打开 `verbose=True` 或检查 llama.cpp 日志。

## 建议添加的计时代码点

在 `LlamaCppClient._ensure_model()`：

```python
start = time.monotonic()
print("llama load start", flush=True)
self._llm = Llama(...)
print(f"llama load done seconds={time.monotonic() - start:.2f}", flush=True)
```

在 `VoiceAgent.run_turn_streaming()`：

```python
print("llm generation start", flush=True)
...
print("llm generation done", flush=True)
```

在 `TTSManager.synthesize()`：

```python
print(f"tts backend start {backend.__class__.__name__}", flush=True)
...
print(f"tts backend done seconds=...", flush=True)
```

## 一个可能的短期实现草案

```python
class LlamaCppClient:
    def warmup(self) -> None:
        self._ensure_model()

class VoicePipeline:
    def __init__(...):
        ...
        if isinstance(self.llm, LlamaCppClient) and config.get("llm.preload", True):
            threading.Thread(target=self._warmup_llm, daemon=True).start()

    def _warmup_llm(self) -> None:
        try:
            self.llm.warmup()
            self.bus.emit(Event("llm.ready", source="voice"))
        except Exception as exc:
            print(f"llm warmup failed: {exc}", flush=True)
```

对应配置：

```yaml
llm:
  preload: true
  preload_mode: background
```

这个方案不会让第一次唤醒必须等待模型加载，但如果用户启动后立刻说话，仍需在 UI 上提示“本地模型准备中，请稍等”。

## 当前判断

目前证据支持：

- Qwen 模型不是服务启动时加载，而是首次正文进入模型时加载。
- 首次有效对话出现了约 75 秒延迟。
- 模型加载后 voice 进程 RSS 到约 4.3GB。
- `use_mlock=True` 已配置，systemd 也允许 `LimitMEMLOCK=infinity`。

仍需进一步验证：

- 75 秒中模型加载具体占比。
- `use_mlock=True` 是否锁住了完整 GGUF。
- 是否 SD 卡冷页缓存导致主要耗时，还是 prompt eval / tool-call 二次生成 / TTS 占比也很高。

## 追加调查：当前运行进程是否真的使用 Qwen，以及 mlock 为什么不完整

调查时间：2026-06-06

### 1. 是否真的使用的是 Qwen GGUF

结论：**是。**

这次没有依赖模型自述或回复内容判断，而是直接检查运行中的 `wanzhi-voice` 进程 `/proc/<pid>/maps` 和 `/proc/<pid>/smaps`。

当前 `wanzhi-voice` PID：

```text
7045
```

进程映射中明确存在：

```text
/home/icenter/wanzhi/models/llm/qwen2.5-3b-instruct-q4_k_m.gguf
```

`maps` 中相关映射：

```text
7ffe4a1ac000-7ffe5489c000 r--s 0f918000 ... /home/icenter/wanzhi/models/llm/qwen2.5-3b-instruct-q4_k_m.gguf
7ffe5489c000-7ffeb8000000 r--s 1a008000 ... /home/icenter/wanzhi/models/llm/qwen2.5-3b-instruct-q4_k_m.gguf
```

所以可以确认：当前进程实际 mmap 的就是配置里的 Qwen GGUF 文件，不只是配置写了 Qwen。

### 2. Qwen GGUF 映射的 RSS/Locked

对 `/proc/7045/smaps` 按该 GGUF 文件聚合后：

```text
model Size kB:   1800528
model Rss kB:    1800528
model Pss kB:    1800528
model Locked kB: 170944
```

含义：

- `Size/Rss/Pss ~= 1.8GB`：Qwen GGUF 的映射页基本已经驻留在 RSS 中。
- `Locked ~= 167MB`：只有约 167MB 被内核标记为 locked。

这说明模型确实在内存中，但并没有完整被 `mlock` 锁定。

### 3. 进程整体内存情况

`/proc/7045/status`：

```text
VmSize: 7541008 kB
VmLck:   170944 kB
VmHWM:  4324672 kB
VmRSS:  4324672 kB
RssAnon: 2475056 kB
RssFile: 1849616 kB
```

`/proc/7045/smaps_rollup`：

```text
Rss:           4327248 kB
Private_Clean: 1817776 kB
Private_Dirty: 2476928 kB
Anonymous:     2476928 kB
Locked:         170944 kB
```

解释：

- `RssFile/Private_Clean` 约 1.8GB，与 GGUF 文件映射大小一致。
- `RssAnon/Private_Dirty` 约 2.47GB，主要可能是 llama.cpp 运行时内存、KV cache、Python/依赖、ASR/TTS 相关内存等。
- `VmLck/Locked` 仍只有约 167MB。

### 4. `LimitMEMLOCK=infinity` 没有完全反映到进程 hard limit

`systemctl --user show wanzhi-voice.service` 显示：

```text
LimitMEMLOCK=infinity
LimitMEMLOCKSoft=infinity
```

但实际进程 `/proc/7045/limits` 显示：

```text
Max locked memory  1054900224  1054900224  bytes
```

也就是约 **1.05GB**，不是 infinity。

进一步检查用户级 systemd manager：

```text
PID 815 /lib/systemd/systemd --user
Max locked memory 1054900224 1054900224 bytes
```

当前 shell/Python 的 `RLIMIT_MEMLOCK` 也一样：

```text
(1054900224, 1054900224)
```

因此，这不是单个 `wanzhi-voice.service` 配置文件看起来的问题，而是用户会话 / `systemd --user` manager 的 hard limit 本身就是约 1GB。用户服务单元写 `LimitMEMLOCK=infinity` 后，表面上 unit 属性显示 infinity，但实际进程仍受 user manager 继承来的 hard limit 限制。

### 5. 这是否解释了只有 167MB 被 Locked

只能解释一部分。

因为即便 hard limit 是约 1.05GB，也理论上可以锁住高于 167MB 的内存；但实际只锁了约 167MB。

可能原因：

1. `llama.cpp` 只对部分 buffer 或部分 tensor 调用了 mlock。
2. `llama.cpp` 尝试锁更多内存，但达到某个内部阶段失败，失败日志因为 `verbose=False` 没有显示。
3. 文件映射页虽然已驻留 RSS，但没有全部被 `mlock()` 标记。
4. `llama-cpp-python` 传入的 `use_mlock=True` 不等价于“锁定整个 GGUF 文件映射”。

需要进一步验证：

- 临时打开 `verbose=True` 看 llama.cpp 是否打印 `mlock` 成功/失败日志。
- 在进程启动前把 `RLIMIT_MEMLOCK` 真正提升到足够大，再看 `Locked` 是否超过 167MB。
- 用 `llama.cpp` 官方 server/CLI 以相同 GGUF 和 `--mlock` 启动，对比 `/proc/<pid>/smaps`。

### 6. 关于“发一个问题看回复 jsonl 能否看出来”

从可靠性上看，回复内容或 `events.jsonl` 只能证明“有模型在生成文本”，不能可靠证明具体是哪一个模型。模型也可能自称错误。

这次更可靠的证据是进程内存映射：

```text
/home/icenter/wanzhi/models/llm/qwen2.5-3b-instruct-q4_k_m.gguf
```

所以不需要依赖模型自述来判断当前是不是 Qwen。

### 7. 对解决方案的影响

原先的冷启动结论需要补充两点：

1. **Qwen 已经确认在运行进程中被 mmap 并驻留 RSS。**
2. **`use_mlock=True` 当前并没有把完整 Qwen GGUF 锁住。**

如果要真正做到“模型权重完全锁进物理 RAM”，需要先解决用户级 memlock hard limit 和 llama.cpp 实际锁定范围两个问题。

建议下一步验证顺序：

1. 把 `llama-cpp-python` 的 `verbose` 临时打开，观察 mlock 日志。
2. 创建 `/etc/systemd/user.conf.d/` 或系统级配置，提高 user manager 的 `DefaultLimitMEMLOCK`，然后重启 user manager / 重新登录。
3. 重新启动 `wanzhi-voice`，检查：

```text
/proc/<pid>/limits
/proc/<pid>/status VmLck
/proc/<pid>/smaps 中 Qwen GGUF 的 Locked
```

4. 如果 user manager limit 已足够但 Locked 仍只有 167MB，再重点调查 llama.cpp / llama-cpp-python 的 mlock 实现行为。

## 追加调查 2：明确结论

调查时间：2026-06-06

这次继续做了两个对照实验，结论已经明确：

> `use_mlock=True` 本身是生效的；当前锁不住完整 Qwen GGUF 的根因是运行 `wanzhi-voice` 的用户会话 / user systemd manager 的 `RLIMIT_MEMLOCK` 太低。`LimitMEMLOCK=infinity` 写在 `wanzhi-voice.service` 中，但无法突破 user manager 进程本身继承到的 hard limit。

### 1. 普通用户进程的 llama.cpp verbose 结果

在普通用户环境中，`RLIMIT_MEMLOCK` 为：

```text
rlimit_memlock (1054900224, 1054900224)
```

约等于 **1006 MiB**。

同一 GGUF、同一 `use_mlock=True`、`verbose=True` 加载时，llama.cpp 明确打印：

```text
warning: failed to mlock 1668694016-byte buffer (after previously locking 436240384 bytes): Cannot allocate memory
```

换算：

```text
previously locking 436240384 bytes  ≈ 416 MiB
failed buffer      1668694016 bytes ≈ 1591 MiB
```

加载后进程统计：

```text
VmLck:                 170944 kB
model_smaps_size_kb:  1800528
model_smaps_rss_kb:   1800528
model_smaps_locked_kb: 170944
```

说明：

- Qwen GGUF 已完整 RSS 驻留。
- 但只有约 167MB 显示为 Locked。
- llama.cpp 的确尝试 mlock，并且因为内存锁上限不足而失败。

### 2. root + unlimited memlock 对照实验

为了确认不是 llama.cpp 只锁部分模型，做了 root 对照实验：

```python
resource.setrlimit(resource.RLIMIT_MEMLOCK, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
Llama(..., use_mlock=True, verbose=True)
```

对照实验中：

```text
uid 0
rlimit_before (1054900224, 1054900224)
rlimit_after (-1, -1)
```

同一模型加载后：

```text
VmLck:                1800528 kB
model_smaps_size_kb: 1800528
model_smaps_rss_kb:  1800528
model_smaps_locked_kb: 1800528
```

也就是说，当 memlock limit 足够时，llama.cpp 可以把完整 Qwen GGUF 映射锁住。

这直接排除了“llama.cpp / llama-cpp-python 天生只锁 167MB”的猜测。

### 3. 为什么 `LimitMEMLOCK=infinity` 没解决

`wanzhi-voice.service` 中确实有：

```ini
LimitMEMLOCK=infinity
```

`systemctl --user show wanzhi-voice.service` 也显示：

```text
LimitMEMLOCK=infinity
LimitMEMLOCKSoft=infinity
```

但实际进程 `/proc/<pid>/limits` 是：

```text
Max locked memory 1054900224 1054900224 bytes
```

用户级 systemd manager 本身：

```text
PID 815 /lib/systemd/systemd --user
Max locked memory 1054900224 1054900224 bytes
```

当前 shell/Python 也是：

```text
RLIMIT_MEMLOCK = (1054900224, 1054900224)
```

因此问题在更上层：

- `wanzhi-voice.service` 是 user service。
- user service 由 `/lib/systemd/systemd --user` 启动。
- user manager 本身的 hard limit 只有约 1GB。
- 子服务不能把 hard limit 提到超过父进程允许的范围。

所以 unit 里写 `LimitMEMLOCK=infinity` 不足以生效。

### 4. 关于配置来源

当前用户不在 `pipewire` 组：

```text
uid=1000(icenter) gid=1000(icenter) groups=... audio, video, ...
```

而 `/etc/security/limits.d/25-pw-rlimits.conf` 有：

```text
@pipewire - memlock 4194304
```

该规则对当前用户不会命中。

`/etc/systemd/user.conf` 没有设置：

```text
#DefaultLimitMEMLOCK=
```

`/etc/systemd/system.conf` 中默认值只是注释示例：

```text
#DefaultLimitMEMLOCK=8M
```

`user@1000.service` 的 systemd unit 属性显示默认 `LimitMEMLOCK=8M`，但实际 user manager 进程是约 1GB，说明启动链路中还有 PAM / logind / 桌面会话层面的限制参与。无论来源具体是哪一层，实测结果已经足够确定：**当前 user manager hard limit 不足以完整 mlock Qwen。**

### 5. 明确修复方向

要让 `use_mlock=True` 真正锁住完整 Qwen，需要让启动 `wanzhi-voice` 的 user manager 自身拥有足够高的 memlock hard limit。

可选修复方式：

#### 方式 A：给 `user@.service` 加 system-level drop-in

建议创建：

```ini
# /etc/systemd/system/user@.service.d/override.conf
[Service]
LimitMEMLOCK=infinity
```

然后：

```bash
sudo systemctl daemon-reload
loginctl terminate-user icenter
# 或重启系统
```

重新登录 / 重启后检查：

```bash
cat /proc/$(pgrep -u icenter -x systemd)/limits | grep "Max locked memory"
```

期望 user manager 的 hard limit 变成 unlimited 或至少大于 2GB。

#### 方式 B：通过 PAM limits 给当前用户足够 memlock

例如：

```text
icenter soft memlock unlimited
icenter hard memlock unlimited
```

或加入匹配的组规则。但这种方式是否影响 `systemd --user` 取决于具体 PAM 链路，需要重登后验证。

#### 方式 C：把 LLM 做成 system service

如果以后采用独立 `wanzhi-llm.service`，可以把它做成 system service 而不是 user service。system service 的 `LimitMEMLOCK=infinity` 更直接，不受 user manager hard limit 影响。

### 6. 最终判断

最终结论：

1. 当前运行的确实是 `Qwen2.5-3B-Instruct-GGUF Q4_K_M`。
2. llama.cpp 的 `use_mlock=True` 不是无效参数；它确实调用了 mlock。
3. 失败原因是 memlock limit 不足，日志明确为 `Cannot allocate memory`。
4. 当 root 进程把 `RLIMIT_MEMLOCK` 提到 infinity 后，完整 1.8GB Qwen GGUF 映射都被 `Locked`。
5. 当前 `wanzhi-voice.service` 的 `LimitMEMLOCK=infinity` 被 user manager 的 hard limit 截住，不能真正让子进程锁完整模型。

因此，如果目标是“Qwen 权重完全锁进物理 RAM”，下一步应先修 user manager / service 启动层的 memlock hard limit，而不是继续改 `llama-cpp-python` 参数。

## 追加调查 3：YOLO 模型大小与是否能和 Qwen 同时驻留/锁内存

调查时间：2026-06-06

### 1. 当前实际 YOLO 模型文件

当前视觉配置：

```yaml
vision:
  pose_backend: yolo
  pose_model_path: models/yolov8n-pose.onnx
```

项目里实际存在的 YOLO pose 模型文件：

```text
models/yolov8n-pose.onnx  13,484,153 bytes  ≈ 12.86 MiB
models/yolov8n-pose.pt     6,832,633 bytes  ≈  6.52 MiB
```

这确实很小，因为当前使用的是 **YOLOv8n-pose**，其中 `n` 是 nano 版。

### 2. vision 进程整体内存占用

当前 `wanzhi-vision` 进程状态：

```text
PID=917
RSS:     170352 kB
VmSize: 1369616 kB
VmLck:        0 kB
Threads:     19
```

`smaps_rollup`：

```text
Rss:             172432 kB
Pss:             157465 kB
Private_Dirty:   117392 kB
Anonymous:       116480 kB
Locked:               0 kB
```

所以虽然 YOLO ONNX 文件只有约 13MB，视觉进程整体 RSS 约 170MB。差额主要来自：

- ONNX Runtime
- OpenCV
- Python 运行时
- 输入/输出 tensor buffer
- 中间推理 buffer / allocator arena
- 摄像头与共享内存相关数据结构

### 3. ONNX Runtime 不像 Qwen GGUF 一样直接 mmap 文件

检查 `/proc/<vision_pid>/maps` 和 `/proc/<vision_pid>/smaps` 时，没有看到 `yolov8n-pose.onnx` 作为文件映射出现。

这和 Qwen GGUF 不同：

- Qwen GGUF 会以文件映射形式出现在 `/proc/<pid>/maps`。
- YOLO ONNX 当前没有以 `.onnx` 文件映射形式暴露。

推断：ONNX Runtime 大概率把模型读入自己的 heap / arena，而不是长期保留一个可见的 `.onnx` 文件 mmap。

因此不能像 Qwen 那样简单通过“模型文件映射的 Locked”判断 YOLO 权重是否被锁住。

### 4. 能否和 Qwen 同时锁进内存

从容量上看：**完全可行。**

主要量级：

```text
Qwen GGUF 文件映射：约 1.8 GiB RSS / Locked 目标
YOLO ONNX 文件：约 12.86 MiB
wanzhi-vision 整体 RSS：约 170 MiB
```

在 8GB RAM 设备上，Qwen + YOLO 同时常驻内存不是瓶颈。

真正的瓶颈仍然是前面确认的 memlock hard limit：

```text
当前 user manager / user service RLIMIT_MEMLOCK ≈ 1GB
Qwen 完整 mlock 需要约 1.8GB+
YOLO 本身只需要十几 MB，几乎可以忽略
```

如果把 user manager / service 的 memlock limit 提到足够大，Qwen 可以完整 `mlock`。YOLO 由于模型太小，即便不显式 `mlock`，实际冷启动和 SD 卡抖动风险也远小于 Qwen。

### 5. 是否需要对 YOLO 显式 mlock

优先级很低。

原因：

1. YOLO ONNX 文件只有约 13MB。
2. vision 进程整体 RSS 约 170MB，远小于 Qwen。
3. ONNX Runtime 没有暴露出简单的文件 mmap，因此要“严格锁 YOLO 权重”需要额外工程：
   - 手动读取 ONNX 文件到内存并 `mlock` 这块 buffer，但 ORT 未必复用该 buffer。
   - 或对 vision 进程所有关键匿名内存做 `mlockall()`，风险较高。
   - 或使用 system service + 足够 memlock 后验证 ORT allocator 行为。

更现实的做法：

- vision 服务启动时创建 `InferenceSession` 后执行一次 dummy inference 预热。
- 保持 vision daemon 常驻。
- 把精力优先放在 Qwen 的 memlock limit 和预加载/常驻服务上。

### 6. 关于“同时锁模型”的最终判断

最终判断：

1. 当前 YOLO 模型只有约 **13MB**，这是正常的 YOLOv8 nano pose 量级。
2. 当前 vision 进程整体内存约 **170MB RSS**。
3. 从 8GB RAM 容量角度，Qwen + YOLO 同时常驻完全没问题。
4. 从 `mlock` 角度，Qwen 是主要压力；YOLO 的大小可以忽略。
5. 当前不能完整锁 Qwen 的原因仍是 memlock hard limit，不是总内存不足，也不是 YOLO 竞争内存。
