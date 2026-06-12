# Wanzhi

Wanzhi is an offline Raspberry Pi elder-care assistant. It runs locally on the Pi and connects voice interaction, vision recognition, and a medication list UI through low-latency local IPC instead of a web backend.

- `wanzhi-voice`: wake word, speech recognition, local llama.cpp agent with tool calling, and Kokoro/Piper speech output.
- `wanzhi-vision`: camera capture, pose estimation, fall detection, shared-memory preview frames, and emergency events.
- `wanzhi-ui`: a Kivy fullscreen assistant face, camera screen, and medication screen for the connected display.

The project keeps large model files out of git. Put ASR, TTS, wake word, LLM GGUF, and optional vision assets under `models/`, and runtime state under `data/`.

## Overall Architecture

The application is organized as three long-running local services plus shared runtime files:

```text
Microphone
  -> wanzhi-voice
  -> ZeroMQ ipc:// event bus
  -> wanzhi-ui

Camera
  -> wanzhi-vision
  -> POSIX shared memory preview
  -> wanzhi-ui

Medication data
  -> data/wanzhi.db
  -> wanzhi-ui and wanzhi-voice
```

There is currently no HTTP or REST API layer. The services communicate through:

- `ipc:///tmp/wanzhi-events.sock`: ZeroMQ PUSH/PULL event bus for instant UI updates.
- `ipc:///tmp/wanzhi-vision-alerts.sock`: ZeroMQ PUB/SUB bus for vision fall alerts.
- `data/events.jsonl`: optional JSONL audit log when `events.audit_jsonl: true`.
- `wanzhi_camera_preview`: POSIX shared memory segment for zero-copy camera preview frames.
- `data/wanzhi.db`: SQLite database used for medication schedules and intake logs.

Important source directories:

- `src/wanzhi/core/`: configuration, event definitions, event bus, and shared memory frame transport.
- `src/wanzhi/voice/`: wake word, recording, ASR, llama.cpp agent, TTS, and speech playback.
- `src/wanzhi/vision/`: camera capture, pose estimation, fall detection, preview publishing, and fall alerts.
- `src/wanzhi/ui/`: Kivy app, assistant face screen, camera screen, and medication list screen.
- `src/wanzhi/actions/`: business actions exposed as native agent tools.
- `src/wanzhi/services/medication/`: SQLite schema, repository, and reminder scheduler.
- `src/wanzhi/services/emergency/`: emergency event notification.

## Runtime Flow

### Voice Interaction

The voice pipeline lives in `src/wanzhi/voice/pipeline.py`:

```text
WakeWordDetector
  -> SpeechRecorder
  -> VoskSTT or SherpaSTT
  -> VoiceAgent (llama.cpp + tool calling)
  -> ActionRegistry tools
  -> TTSManager + SpeechQueue
  -> ZeroMQ EventBus
```

Typical flow:

1. The service waits for the configured wake word, currently `你好，小丸子`.
2. After wake-up it records one user utterance and transcribes it locally.
3. `VoiceAgent` runs a local ReAct loop with `llama-cpp-python` and native tools such as medication list, emergency alert, UI switching, and voice changes.
4. When a tool call is detected, TTS output is muted until the final spoken confirmation is generated.
5. Final replies are split at Chinese sentence boundaries and streamed into Kokoro/Piper TTS.
6. The assistant emits UI state events such as `voice.awake`, `voice.listening`, and `voice.speaking`.

Set `llm.provider: ollama` in config to fall back to the legacy keyword router plus Ollama chat.

### Vision Recognition

The vision loop lives in `src/wanzhi/vision/daemon.py`:

```text
Camera
  -> YOLO pose ONNX (onnxruntime)
  -> PoseAnalyzer (3 geometric fall rules + 15-frame debounce)
  -> shared memory preview writer
  -> VisionAlertPublisher (ZeroMQ PUB ipc://)
  -> VisionAlerter / EmergencyNotifier
  -> ZeroMQ EventBus
```

The vision service continuously reads camera frames, estimates the user's pose with `yolov8n-pose.onnx`, and checks for fall-like posture using in-memory geometry only. Preview frames are written into POSIX shared memory for the UI camera screen. The daemon runs at `Nice=10` so it does not compete with voice and UI threads.

When a fall is suspected or confirmed:

- `vision.fall_suspected` is emitted for suspicious states.
- `emergency.fall_detected` is broadcast on `ipc:///tmp/wanzhi-vision-alerts.sock` for voice/UI subscribers.
- The same event is also emitted on the main ZeroMQ event bus for audit/UI compatibility.

### Medication List UI

The medication screen lives in `src/wanzhi/ui/screens/medication_screen.py` and reads data through `MedicationRepository`:

```text
data/wanzhi.db
  -> MedicationRepository.list_due_on(date.today())
  -> MedicationScreen
  -> MedicationCard
  -> MedicationRepository.mark_taken()
```

When the user asks for medication information, the voice agent calls `show_medication_list` or `switch_ui_screen`, emits `ui.show_medication`, and speaks a summary. The Kivy UI polls the ZeroMQ bus every 50 ms and switches screens immediately.

Pressing "已服用" on a medication card writes an intake log through `MedicationRepository.mark_taken()`.

## Event Types

Events are defined in `src/wanzhi/core/events.py`. Main event groups:

- `voice.awake`, `voice.listening`, `voice.speaking`: update the assistant face screen.
- `ui.show_medication`, `ui.show_camera`: switch the UI to medication or camera screens.
- `medication.reminder`, `medication.taken`: medication workflow events.
- `vision.health`, `vision.fall_suspected`: vision service status and warnings.
- `emergency.fall_detected`, `emergency.triggered`: emergency UI state.

The Kivy app handles these events in `src/wanzhi/ui/app.py`.

## Current Implementation Notes

- `MedicationScheduler` exists in `src/wanzhi/services/medication/scheduler.py`, but it is not currently wired into a daemon or systemd service.
- Voice-based medication creation is not fully implemented yet; `schedule_from_text()` opens the medication list but does not parse and write a new medication.
- `MedicationRepository.list_due_on()` currently returns active schedules for the day and does not filter out already-taken items.
- Vision and voice do not call each other directly. They meet in the UI through the event bus and shared runtime files.

## Development

```bash
uv sync
scripts/download_models.sh
.venv/bin/wanzhi
```

Run individual services with:

```bash
.venv/bin/wanzhi-voice
.venv/bin/wanzhi-vision
.venv/bin/wanzhi-ui
```

The stack prefers local components: Sherpa-ONNX for Chinese/English ASR, llama.cpp with Qwen2.5-3B-Instruct GGUF for the agent, Kokoro/Piper for TTS, OpenCV + YOLO pose ONNX for CPU pose estimation, Kivy for the display, and SQLite for medication data.

Useful commands:

```bash
pytest
scripts/watch_events.py --type '*'
```

## Autostart Services

Install all daemons as user systemd services:

```bash
scripts/install_systemd.sh
scripts/start_graphical_session.sh
```

The install script enables LightDM autologin and installs `~/.config/autostart/wanzhi-session.desktop`. After the desktop session starts, that autostart entry waits for a Wayland/X11 display socket, imports `DISPLAY`/`WAYLAND_DISPLAY` into the user systemd manager, and starts `wanzhi.target`, so the Kivy UI opens fullscreen on the voice interaction screen instead of leaving the Pi on the desktop.

On labwc desktops, the installer also adds a `title="Wanzhi"` window rule to `~/.config/labwc/rc.xml` so the assistant is forced fullscreen even if Kivy opens through Xwayland.

Do not enable `wanzhi.target` or `wanzhi-ui.service` directly under the user `default.target`: starting Kivy before the graphical session has a display socket can make SDL fall back to direct DRM/KMS rendering and leave the attached screen black.

The voice service uses `LimitMEMLOCK=infinity` so the GGUF model can be locked into RAM with `use_mlock: true`.

When the Pi has power, the voice daemon should stay running and listen for:

```text
你好，小丸子
```

Useful commands:

```bash
systemctl --user status wanzhi-voice.service wanzhi-vision.service wanzhi-ui.service
journalctl --user -u wanzhi-voice.service -f
systemctl --user restart wanzhi-voice.service
```
