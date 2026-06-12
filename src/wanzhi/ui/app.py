from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from wanzhi.core.alert_listener import VisionAlertListener
from wanzhi.core.bus import create_event_bus_from_config
from wanzhi.core.events import Event, EventTypes
from wanzhi.services.medication.repository import MedicationRepository
from wanzhi.ui.fonts import DEFAULT_UI_FONT_SCALE, register_chinese_font, register_emoji_font

if TYPE_CHECKING:
    from wanzhi.core.config import AppConfig


def _config_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _config_float(value: object, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


EMERGENCY_REASON_LABELS = {
    "fall_detected": "检测到跌倒",
    "hand_raise_sos": "检测到举手呼救",
    "arm_wave_sos": "检测到挥手求救",
    "abnormal_struggle": "检测到异常挣扎",
    "distress_detected": "检测到紧急求救动作",
}


def emergency_display_message(payload: dict) -> str:
    reason = str(payload.get("reason") or "fall_detected")
    return EMERGENCY_REASON_LABELS.get(reason, reason or "检测到紧急情况")


def voice_speaking_should_take_focus(current_screen: str) -> bool:
    return current_screen not in {"medication", "camera"}


def run(config: AppConfig) -> None:
    fullscreen_enabled = _config_bool(config.get("ui.fullscreen", True), True)
    font_scale = _config_float(config.get("ui.font_scale", DEFAULT_UI_FONT_SCALE), DEFAULT_UI_FONT_SCALE)

    try:
        from kivy.config import Config  # type: ignore[reportMissingImports]

        Config.set("graphics", "fullscreen", "1" if fullscreen_enabled else "0")
        Config.set("graphics", "borderless", "1" if fullscreen_enabled else "0")

        from kivy.app import App  # type: ignore[reportMissingImports]
        from kivy.clock import Clock  # type: ignore[reportMissingImports]
        from kivy.core.window import Window  # type: ignore[reportMissingImports]
        from kivy.uix.screenmanager import ScreenManager  # type: ignore[reportMissingImports]
    except ImportError:
        print("Kivy is not installed; UI service cannot start.")
        return

    from wanzhi.ui.screens.face_screen import FaceScreen
    from wanzhi.ui.screens.camera_screen import CameraScreen
    from wanzhi.ui.screens.medication_screen import MedicationScreen

    class WanzhiApp(App):
        def build(self):  # type: ignore[no-untyped-def]
            Window.fullscreen = fullscreen_enabled
            Window.borderless = fullscreen_enabled
            self.font_name = register_chinese_font()
            self.emoji_font_name = register_emoji_font()
            self.bus = create_event_bus_from_config(config, role="pull")
            self._pending_alerts: list[Event] = []
            alert_endpoint = str(config.get("alerts.zmq_endpoint", "ipc:///tmp/wanzhi-vision-alerts.sock"))
            self.alert_listener = VisionAlertListener(
                alert_endpoint,
                lambda event: self._pending_alerts.append(event),
            )
            self.repo = MedicationRepository(config.path("database.path", "data/wanzhi.db"))
            self.manager = ScreenManager()
            self.face_screen = FaceScreen(
                name="face",
                font_name=self.font_name,
                emoji_font_name=self.emoji_font_name,
                font_scale=font_scale,
            )
            self.camera_screen = CameraScreen(
                name="camera",
                shm_name=str(config.get("ui.camera_shm_name", "wanzhi_camera_preview")),
                fps=float(config.get("ui.camera_fps", 24)),
                font_name=self.font_name,
                font_scale=font_scale,
            )
            self.medication_screen = MedicationScreen(
                name="medication",
                items_provider=lambda: self.repo.list_due_on(date.today()),
                mark_taken=self.repo.mark_taken,
                font_name=self.font_name,
                emoji_font_name=self.emoji_font_name,
                font_scale=font_scale,
            )
            self.manager.add_widget(self.face_screen)
            self.manager.add_widget(self.camera_screen)
            self.manager.add_widget(self.medication_screen)
            self.manager.current = str(config.get("ui.default_screen", "face"))
            poll_interval = float(config.get("ui.event_poll_interval", 0.05))
            Clock.schedule_interval(self._poll_events, poll_interval)
            return self.manager

        def on_stop(self) -> None:
            if hasattr(self, "alert_listener"):
                self.alert_listener.close()

        def _handle_emergency(self, event: Event) -> None:
            self.face_screen.set_state("alert", emergency_display_message(event.payload))
            self.manager.current = "face"

        def _poll_events(self, _dt: float) -> None:
            while self._pending_alerts:
                self._handle_emergency(self._pending_alerts.pop(0))

            for event in self.bus.poll_new():
                if event.type == EventTypes.UI_SHOW_MEDICATION:
                    self.medication_screen.refresh()
                    self.manager.current = "medication"
                elif event.type == EventTypes.UI_SHOW_CAMERA:
                    self.manager.current = "camera"
                elif event.type in {
                    EventTypes.EMERGENCY_FALL_DETECTED,
                    EventTypes.EMERGENCY_TRIGGERED,
                }:
                    self._handle_emergency(event)
                elif event.type == EventTypes.VOICE_AWAKE:
                    text = event.payload.get("text", "我在呢")
                    self.face_screen.set_state("speaking")
                    self.face_screen.set_reply_text(text)
                    self.manager.current = "face"
                elif event.type == EventTypes.VOICE_LISTENING:
                    self.face_screen.set_state("listening")
                    self.manager.current = "face"
                elif event.type == EventTypes.VOICE_TRANSCRIBED:
                    self.face_screen.set_user_text(event.payload.get("text", ""))
                    self.manager.current = "face"
                elif event.type == EventTypes.VOICE_SPEAKING:
                    text = event.payload.get("text", "")
                    emoji = event.payload.get("emoji", "")
                    self.face_screen.set_state("speaking")
                    self.face_screen.set_suggested_emoji(str(emoji))
                    self.face_screen.set_reply_text(text)
                    if voice_speaking_should_take_focus(str(self.manager.current)):
                        self.manager.current = "face"
                elif event.type == EventTypes.LLM_LOADING:
                    text = event.payload.get("text", "本地对话核心正在准备中，请稍后。")
                    self.face_screen.set_state("warming", str(text))
                    self.face_screen.set_reply_text("")
                    self.manager.current = "face"
                elif event.type == EventTypes.LLM_READY:
                    text = event.payload.get("text", "本地对话核心已准备好。")
                    self.face_screen.set_state("idle", str(text))
                    self.face_screen.set_reply_text("")
                    self.manager.current = "face"
                elif event.type == EventTypes.MEDICATION_REMINDER:
                    self.medication_screen.refresh()
                    self.manager.current = "medication"

    WanzhiApp().run()
