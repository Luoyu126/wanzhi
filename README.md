# Wanzhi

Wanzhi is an offline Raspberry Pi elder-care assistant. It is organized around three long-running processes:

- `wanzhi-voice`: wake word, speech recognition, intent routing, Ollama replies, and Piper speech output.
- `wanzhi-vision`: camera capture, pose estimation, fall detection, and emergency events.
- `wanzhi-ui`: a Kivy fullscreen assistant face and medication screen for the connected display.

The project keeps large model files out of git. Put ASR, TTS, wake word, and optional vision assets under `models/`, and runtime state under `data/`.

## Development

```bash
.venv/bin/wanzhi
```

Run individual services with:

```bash
.venv/bin/wanzhi-voice
.venv/bin/wanzhi-vision
.venv/bin/wanzhi-ui
```

The first implementation prefers local components: Sherpa-ONNX for Chinese/English ASR, Ollama for the LLM, Piper for TTS, OpenCV + MediaPipe for CPU pose estimation, Kivy for the display, and SQLite for medication data.

## Autostart Voice Service

Install the voice daemon as a user systemd service:

```bash
scripts/install_systemd.sh
systemctl --user start wanzhi-voice.service
```

The install script enables user lingering with `loginctl enable-linger`, so `wanzhi-voice.service` starts after boot without an interactive login. When the Pi has power, the voice daemon should stay running and listen for:

```text
你好，小丸子
```

Useful commands:

```bash
systemctl --user status wanzhi-voice.service
journalctl --user -u wanzhi-voice.service -f
systemctl --user restart wanzhi-voice.service
```
