from __future__ import annotations

import audioop
import tempfile
import wave
from pathlib import Path


class SpeechRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        silence_rms: int = 500,
        silence_chunks: int = 16,
        max_seconds: int = 10,
        device_index: int | None = None,
        device_name: str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.silence_rms = silence_rms
        self.silence_chunks = silence_chunks
        self.max_seconds = max_seconds
        self.device_index = device_index
        self.device_name = device_name

    def record_once(self) -> Path:
        import pyaudio

        audio = pyaudio.PyAudio()
        device_index = self._resolve_input_device(audio)
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.chunk_size,
        )
        frames: list[bytes] = []
        silent_count = 0
        max_chunks = int(self.sample_rate / self.chunk_size * self.max_seconds)

        try:
            for _ in range(max_chunks):
                chunk = stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(chunk)
                if audioop.rms(chunk, 2) < self.silence_rms and frames:
                    silent_count += 1
                else:
                    silent_count = 0
                if len(frames) > self.silence_chunks and silent_count >= self.silence_chunks:
                    break
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()

        wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav_path = Path(wav.name)
        wav.close()
        with wave.open(str(wav_path), "wb") as wave_file:
            wave_file.setnchannels(1)
            wave_file.setsampwidth(2)
            wave_file.setframerate(self.sample_rate)
            wave_file.writeframes(b"".join(frames))
        return wav_path

    def _resolve_input_device(self, audio) -> int | None:
        if self.device_index is not None:
            return int(self.device_index)
        if not self.device_name:
            return None
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if self.device_name in str(info.get("name", "")) and int(info.get("maxInputChannels", 0)) > 0:
                return index
        return None
