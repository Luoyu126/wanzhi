from __future__ import annotations

from pathlib import Path

from wanzhi.core.timing import log_timing, now_seconds


class SherpaSTT:
    """Thin wrapper for Sherpa-ONNX ASR.

    The concrete model files vary by Sherpa release, so this class keeps model loading
    isolated and offers a deterministic fallback for development without downloaded
    models.
    """

    def __init__(self, model_dir: Path, fallback_text: str = "") -> None:
        self.model_dir = model_dir
        self.fallback_text = fallback_text
        self._recognizer = None

    def preload(self) -> bool:
        try:
            import sherpa_onnx  # type: ignore
        except ImportError:
            return False

        if not self.model_dir.exists():
            return False

        if self._recognizer is None:
            started = now_seconds()
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(self.model_dir / "encoder.onnx"),
                decoder=str(self.model_dir / "decoder.onnx"),
                joiner=str(self.model_dir / "joiner.onnx"),
                tokens=str(self.model_dir / "tokens.txt"),
                num_threads=2,
                sample_rate=16000,
                feature_dim=80,
            )
            log_timing("stt.sherpa.preload", started, model_dir=self.model_dir)
        return True

    def transcribe_file(self, wav_path: Path) -> str:
        if not self.model_dir.exists():
            return self.fallback_text

        # Sherpa has several model families. The project scripts download a matching
        # streaming model; until then, fail softly so the rest of the assistant works.
        try:
            if not self.preload() or self._recognizer is None:
                return self.fallback_text
            import wave

            started = now_seconds()
            with wave.open(str(wav_path), "rb") as wave_file:
                samples = wave_file.readframes(wave_file.getnframes())
            stream = self._recognizer.create_stream()
            stream.accept_wave_file(str(wav_path))
            self._recognizer.decode_stream(stream)
            text = str(stream.result.text).strip()
            log_timing("stt.sherpa.transcribe", started, bytes=len(samples), chars=len(text))
            return text
        except Exception:
            return self.fallback_text
