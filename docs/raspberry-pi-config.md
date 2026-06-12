# 树莓派硬件与系统配置

> 采集时间：2026-06-05
> 主机名：`raspberrypi`

## 概览

| 项目 | 配置 |
|------|------|
| 型号 | Raspberry Pi 5 Model B Rev 1.0 |
| 系统位数 | **64 位**（`aarch64`） |
| 内存 | **8 GB** |
| CPU | 4 核 ARM Cortex-A76，最高 2.4 GHz |
| 操作系统 | Debian GNU/Linux 12 (bookworm) |
| 内核 | `6.6.74+rpt-rpi-2712` |

---

## 处理器（CPU）

| 项目 | 值 |
|------|-----|
| 架构 | `aarch64`（64 位） |
| 运行模式 | 支持 32 位 / 64 位 |
| 核心数 | 4 |
| 型号 | ARM Cortex-A76（stepping r4p1） |
| 最高频率 | 2400 MHz |
| 最低频率 | 1500 MHz |
| 当前频率 | ~2400 MHz |
| L1 缓存 | 256 KiB（数据）+ 256 KiB（指令）× 4 核 |
| L2 缓存 | 2 MiB × 4 核 |
| L3 缓存 | 2 MiB |
| 字节序 | Little Endian |

固件配置（`/boot/firmware/config.txt` 生效项）：

- `arm_64bit=1` — 启用 64 位模式
- `arm_boost=1` — 启用性能加速
- `arm_freq=2400` — CPU 最高 2.4 GHz
- `arm_freq_min=1500` — CPU 最低 1.5 GHz
- `total_mem=8192` — 识别为 8 GB 内存型号

---

## 内存（RAM）

| 项目 | 值 |
|------|-----|
| 物理内存总量 | **7.9 GiB**（8,245,504 kB） |
| 当前已用 | ~2.7 GiB |
| 当前空闲 | ~3.9 GiB |
| 当前可用 | ~5.2 GiB |
| Swap 交换分区 | 512 MiB（当前未使用） |

---

## 图形与显存（GPU）

| 项目 | 值 |
|------|-----|
| GPU 驱动 | `vc4-drm`（VideoCore，Pi 5） |
| 3D 频率（v3d） | 960 MHz（最低 500 MHz） |
| 核心频率（core） | 910 MHz |
| GPU 固件版本 | `26826259`（2024-09-23） |
| H.264 硬解 | 未启用 |
| HEVC 硬解 | 未启用 |
| HDMI 4K@60 | 已启用（`hdmi_enable_4kp60=1`） |

### 显存分配说明

通过 `vcgencmd get_mem` 查询：

| 类型 | 分配 |
|------|------|
| GPU 专用 | 4 MiB |
| ARM 可用 | ~1020 MiB（启动时快照） |

> **注意**：树莓派 5 采用统一内存架构（UMA），GPU 与 CPU 共享 8 GB 物理内存，不再像旧款那样通过 `gpu_mem` 做大块静态切分。上述 `gpu=4M` 为兼容接口的统计值，实际图形/多媒体任务会按需从系统内存中动态分配。

---

## 启动与硬件接口配置

`/boot/firmware/config.txt` 当前关键配置：

| 配置 | 说明 |
|------|------|
| `dtparam=i2c_arm=on` | 启用 I2C |
| `dtparam=spi=on` | 启用 SPI |
| `dtparam=audio=on` | 启用板载音频驱动 |
| `camera_auto_detect=1` | 自动加载检测到的摄像头 overlay |
| `display_auto_detect=1` | 自动加载检测到的 DSI 显示屏 overlay |
| `auto_initramfs=1` | 自动加载 initramfs |
| `dtoverlay=vc4-kms-v3d` | 启用 DRM/KMS V3D 图形驱动 |
| `max_framebuffers=2` | 启用双 framebuffer |
| `disable_fw_kms_setup=1` | 不由固件写入初始 `video=` 参数 |
| `arm_64bit=1` | 64 位启动 |
| `disable_overscan=1` | 禁用 overscan 补偿 |
| `arm_boost=1` | 使用固件/主板允许的最高性能 |
| `dtoverlay=w1-gpio` | 启用 1-Wire GPIO |
| `dtparam=uart0=on` | 启用 UART0 |

`/boot/firmware/cmdline.txt` 当前根分区参数：

- `root=PARTUUID=33246837-02`
- `rootfstype=ext4`
- `fsck.repair=yes`
- `rootwait`
- `cfg80211.ieee80211_regdom=CN`

---

## 存储

| 设备 | 容量 | 类型 | 挂载点 | 已用 |
|------|------|------|--------|------|
| `mmcblk0` | 59.4 GB | SD 卡 | — | — |
| `mmcblk0p1` | 512 MB | 启动分区（vfat） | `/boot/firmware` | 14% |
| `mmcblk0p2` | 58.9 GB | 根分区（ext4） | `/` | **42%** |
| `sda` | 0 B | USB 磁盘（未识别容量） | — | — |

当前 SD 卡已识别为约 **64 GB**（`59.4 GB`），根分区已扩展到 `58.9 GB`。当前 `/` 可用空间约 **33 GB**，足够继续安装本地 YOLO 视觉识别模型及其依赖。

---

## 网络

| 接口 | 状态 | 地址 |
|------|------|------|
| `wlan0` | UP | `192.168.3.41/24` |
| `eth0` | DOWN | — |
| `lo` | UP | `127.0.0.1` |

无线网卡固件：BCM4345/6

---

## 操作系统与运行时

| 项目 | 值 |
|------|-----|
| 发行版 | Debian GNU/Linux 12 (bookworm) |
| 内核 | `6.6.74+rpt-rpi-2712` |
| Python | 3.11.2 |
| 设备树兼容 | `raspberrypi,5-model-b` / `brcm,bcm2712` |
| 修订版（Revision） | `d04170` |

---

## 运行状态（采集时）

| 项目 | 值 |
|------|-----|
| 运行时间 | ~7 分钟（采集时刚重启不久） |
| CPU 温度 | 49.9 °C |
| 供电电压 | 0.852 V |
| 降频/欠压 | 无（`throttled=0x0`） |
| 负载（1/5/15 min） | 1.05 / 0.82 / 0.42 |

---

## 已连接 USB 外设

| 设备 | 说明 |
|------|------|
| SN0002 1080P USB Camera | 1080P 摄像头（含内置麦克风） |
| Yundea M1066 | USB 音箱（含麦克风） |
| Maxxter USB Gaming Mouse | 鼠标 |

---

## 与本项目（Wanzhi）的关系

本机配置满足 Wanzhi 离线语音助手 + 视觉跌倒检测的运行需求：

- **64 位系统**：可运行现代 Python 包与 ONNX/MediaPipe 等依赖
- **8 GB 内存**：足够同时运行 llama.cpp（约 2.2 GB GGUF + mlock）、Sherpa/Kokoro、OpenCV 视觉与 Kivy UI
- **USB 摄像头 + 音箱**：已接入，此前测试均可用
- **WiFi 局域网**：可通过 SSH（`192.168.3.41`）进行远程开发

### 推荐内存预算（8 GB）

| 组件 | 预算 |
|------|------|
| 系统 + Kivy UI | ~800 MB |
| Qwen2.5-3B GGUF (`Q4_K_M`, mlock) | ~2.2 GB |
| Sherpa ASR | ~200 MB |
| Kokoro TTS | ~150 MB |
| 视觉守护进程 | ~300 MB |
| 页缓存 / IPC 缓冲 | 剩余 |

### IPC 与服务优先级

- 事件总线：`ipc:///tmp/wanzhi-events.sock`（ZeroMQ PUSH/PULL）
- 摄像头预览：POSIX shared memory `wanzhi_camera_preview`
- 视觉服务：`Nice=10`，跌倒确认需连续 15 帧
- 语音服务：`LimitMEMLOCK=infinity`，配合 `llm.use_mlock: true`

---

## 常用查询命令

```bash
# 系统位数与架构
uname -m && getconf LONG_BIT

# 型号与内存
cat /proc/device-tree/model
free -h

# 存储与分区
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,TYPE,MODEL
df -h / /boot/firmware

# GPU / 温度 / 显存
vcgencmd get_mem gpu
vcgencmd get_mem arm
vcgencmd measure_temp
vcgencmd get_throttled

# 完整固件配置
vcgencmd get_config int

# 启动配置
cat /boot/firmware/config.txt
cat /boot/firmware/cmdline.txt
```
