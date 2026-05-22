from __future__ import annotations

from datetime import date

from wanzhi.core.bus import JsonlEventBus
from wanzhi.core.config import AppConfig
from wanzhi.core.events import EventTypes
from wanzhi.services.medication.repository import MedicationRepository
from wanzhi.ui.fonts import register_chinese_font, register_emoji_font


def run(config: AppConfig) -> None:
    try:
        from kivy.app import App
        from kivy.clock import Clock
        from kivy.uix.screenmanager import ScreenManager
    except ImportError:
        print("Kivy is not installed; UI service cannot start.")
        return

    from wanzhi.ui.screens.face_screen import FaceScreen
    from wanzhi.ui.screens.camera_screen import CameraScreen
    from wanzhi.ui.screens.medication_screen import MedicationScreen

    class WanzhiApp(App):
        def build(self):  # type: ignore[no-untyped-def]
            self.font_name = register_chinese_font()
            self.emoji_font_name = register_emoji_font()
            self.bus = JsonlEventBus(config.path("events.log_path", "data/events.jsonl"))
            self.repo = MedicationRepository(config.path("database.path", "data/wanzhi.db"))
            self.manager = ScreenManager()
            self.face_screen = FaceScreen(name="face", font_name=self.font_name)
            self.camera_screen = CameraScreen(
                name="camera",
                frame_path=config.path("ui.camera_frame_path", "data/camera-preview/latest.jpg"),
                fps=float(config.get("ui.camera_fps", 24)),
            )
            self.medication_screen = MedicationScreen(
                name="medication",
                items_provider=lambda: self.repo.list_due_on(date.today()),
                mark_taken=self.repo.mark_taken,
                font_name=self.font_name,
                emoji_font_name=self.emoji_font_name,
            )
            self.manager.add_widget(self.face_screen)
            self.manager.add_widget(self.camera_screen)
            self.manager.add_widget(self.medication_screen)
            self.manager.current = str(config.get("ui.default_screen", "face"))
            Clock.schedule_interval(self._poll_events, 0.5)
            return self.manager

        def _poll_events(self, _dt: float) -> None:
            for event in self.bus.poll_new():
                if event.type == EventTypes.UI_SHOW_MEDICATION:
                    self.medication_screen.refresh()
                    self.manager.current = "medication"
                elif event.type in {
                    EventTypes.EMERGENCY_FALL_DETECTED,
                    EventTypes.EMERGENCY_TRIGGERED,
                }:
                    self.face_screen.set_state("alert", event.payload.get("reason", "紧急情况"))
                    self.manager.current = "face"
                elif event.type == EventTypes.VOICE_AWAKE:
                    self.face_screen.set_state("speaking", event.payload.get("text", "我在呢"))
                    self.manager.current = "face"
                elif event.type == EventTypes.VOICE_LISTENING:
                    self.face_screen.set_state("listening")
                    self.manager.current = "face"
                elif event.type == EventTypes.VOICE_SPEAKING:
                    self.face_screen.set_state("speaking", event.payload.get("text", ""))
                    self.manager.current = "face"
                elif event.type == EventTypes.MEDICATION_REMINDER:
                    self.medication_screen.refresh()
                    self.manager.current = "medication"
    WanzhiApp().run()
