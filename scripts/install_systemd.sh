#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"

mkdir -p "$USER_SYSTEMD_DIR"
cp "$ROOT_DIR/systemd/"wanzhi-*.service "$USER_SYSTEMD_DIR/"

loginctl enable-linger "${USER}"
systemctl --user daemon-reload
systemctl --user enable wanzhi-ui.service wanzhi-voice.service wanzhi-vision.service

cat <<'MSG'
Installed user services.
User lingering is enabled, so services can start after boot without an interactive login.

Start them now with:
  systemctl --user start wanzhi-ui.service wanzhi-voice.service wanzhi-vision.service

View logs with:
  journalctl --user -u wanzhi-voice.service -f
MSG
