#!/usr/bin/env bash
# One-time setup: enable Wanzhi to start automatically when the Pi powers on.
# Boot orchestration is handled by systemd (not rc.local / cron).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
USER_AUTOSTART_DIR="${HOME}/.config/autostart"
WANZHI_USER="${WANZHI_USER:-${USER}}"

mkdir -p "$USER_SYSTEMD_DIR" "$USER_AUTOSTART_DIR"
cp "$ROOT_DIR/systemd/wanzhi.target" "$USER_SYSTEMD_DIR/"
cp "$ROOT_DIR/systemd/"wanzhi-*.service "$USER_SYSTEMD_DIR/"
rm -f "$USER_SYSTEMD_DIR/wanzhi-llm.service"
chmod +x "$ROOT_DIR/scripts/start_graphical_session.sh"
chmod +x "$ROOT_DIR/scripts/configure_labwc_fullscreen.py"
cp "$ROOT_DIR/systemd/wanzhi-session.desktop" "$USER_AUTOSTART_DIR/wanzhi-session.desktop"
"$ROOT_DIR/scripts/configure_labwc_fullscreen.py"

sudo cp "$ROOT_DIR/systemd/wanzhi-llm.service" /etc/systemd/system/wanzhi-llm.service
sudo systemctl daemon-reload
sudo systemctl enable wanzhi-llm.service

loginctl enable-linger "${WANZHI_USER}"

if [[ -d /etc/lightdm/lightdm.conf.d ]]; then
  sudo cp "$ROOT_DIR/systemd/lightdm-wanzhi-autologin.conf" \
    "/etc/lightdm/lightdm.conf.d/wanzhi-autologin.conf"
  echo "Configured LightDM autologin for ${WANZHI_USER} (wanzhi-ui needs graphical session)."
fi

systemctl --user daemon-reload
systemctl --user disable \
  wanzhi.target \
  wanzhi-ui.service \
  wanzhi-vision.service \
  wanzhi-voice.service >/dev/null 2>&1 || true

cat <<MSG
Wanzhi 开机自启已配置完成。

机制说明：
- 插电 / 重启后由 systemd 自动拉起，无需手动执行启动脚本
- 系统级：wanzhi-llm.service（Qwen 常驻 + mlock）
- 用户级：wanzhi.target → ui / vision / voice
- 图形会话：~/.config/autostart/wanzhi-session.desktop 会等待显示环境、导入 DISPLAY/WAYLAND_DISPLAY，并确保全屏 UI 启动
- labwc：~/.config/labwc/rc.xml 会按窗口标题 Wanzhi 强制全屏
- 一次性安装脚本：scripts/install_systemd.sh（就是本脚本）

开机顺序（systemd After/Wants 自动保证）：
  1. multi-user.target → wanzhi-llm.service（加载 Qwen 到 RAM）
  2. LightDM 自动登录 → graphical-session.target
  3. 桌面 autostart 导入 DISPLAY/WAYLAND_DISPLAY
  4. wanzhi.target → wanzhi-ui → wanzhi-vision → wanzhi-voice

立即启动（可选）：
  sudo systemctl start wanzhi-llm.service
  scripts/start_graphical_session.sh

查看状态：
  systemctl is-enabled wanzhi-llm.service
  test -f ~/.config/autostart/wanzhi-session.desktop && echo autostart installed
  systemctl --user status wanzhi-ui.service wanzhi-vision.service wanzhi-voice.service

查看日志：
  journalctl -u wanzhi-llm.service -f
  journalctl --user -u wanzhi-voice.service -f

验证 LLM 已锁定内存：
  ${ROOT_DIR}/.venv/bin/python ${ROOT_DIR}/scripts/verify_llm_mlock.py
MSG
