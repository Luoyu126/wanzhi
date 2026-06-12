#!/usr/bin/env bash
# Run from the desktop autostart entry after LightDM has created a graphical session.
set -euo pipefail

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
DISPLAY_READY=0

for _attempt in {1..30}; do
  if [[ -n "${WAYLAND_DISPLAY:-}" && -S "${RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]]; then
    export SDL_VIDEODRIVER=wayland
    DISPLAY_READY=1
    break
  fi

  if [[ -z "${WAYLAND_DISPLAY:-}" ]]; then
    for socket in "${RUNTIME_DIR}"/wayland-*; do
      if [[ -S "${socket}" ]]; then
        export WAYLAND_DISPLAY="$(basename "${socket}")"
        export SDL_VIDEODRIVER=wayland
        DISPLAY_READY=1
        break 2
      fi
    done
  fi

  if [[ -n "${DISPLAY:-}" ]]; then
    display_number="${DISPLAY#*:}"
    display_number="${display_number%%.*}"
    if [[ -S "/tmp/.X11-unix/X${display_number}" ]]; then
      export SDL_VIDEODRIVER=x11
      DISPLAY_READY=1
      break
    fi
  elif [[ -S /tmp/.X11-unix/X0 ]]; then
    export DISPLAY=:0
    export SDL_VIDEODRIVER=x11
    DISPLAY_READY=1
    break
  fi

  sleep 1
done

if [[ "${DISPLAY_READY}" != "1" ]]; then
  echo "Wanzhi UI not started: no Wayland or X11 display socket found." >&2
  exit 1
fi

systemctl --user import-environment \
  DISPLAY \
  WAYLAND_DISPLAY \
  XAUTHORITY \
  XDG_CURRENT_DESKTOP \
  XDG_SESSION_TYPE \
  XDG_RUNTIME_DIR \
  SDL_VIDEODRIVER \
  DBUS_SESSION_BUS_ADDRESS || true

if command -v dbus-update-activation-environment >/dev/null 2>&1; then
  dbus-update-activation-environment --systemd \
    DISPLAY \
    WAYLAND_DISPLAY \
    XAUTHORITY \
    XDG_CURRENT_DESKTOP \
    XDG_SESSION_TYPE \
    XDG_RUNTIME_DIR \
    SDL_VIDEODRIVER \
    DBUS_SESSION_BUS_ADDRESS || true
fi

systemctl --user start wanzhi.target
systemctl --user restart wanzhi-ui.service
systemctl --user start wanzhi-vision.service wanzhi-voice.service
