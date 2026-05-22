from __future__ import annotations

import argparse
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-type", choices=["vits", "kokoro"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokens", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--sid", type=int, default=0)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--num-threads", type=int, default=2)
    parser.add_argument("--lexicon", default="")
    parser.add_argument("--voices", default="")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--rule-fsts", default="")
    args = parser.parse_args()

    import numpy as np
    import sherpa_onnx

    config = sherpa_onnx.OfflineTtsConfig()
    config.model.num_threads = args.num_threads
    config.model.debug = False
    if args.model_type == "kokoro":
        config.model.kokoro.model = args.model
        config.model.kokoro.tokens = args.tokens
        config.model.kokoro.voices = args.voices
        config.model.kokoro.lexicon = args.lexicon
        config.model.kokoro.data_dir = args.data_dir
    else:
        config.model.vits.model = args.model
        config.model.vits.tokens = args.tokens
        config.model.vits.lexicon = args.lexicon
        config.model.vits.data_dir = args.data_dir
    config.rule_fsts = args.rule_fsts

    tts = sherpa_onnx.OfflineTts(config)
    audio = tts.generate(args.text, sid=args.sid, speed=args.speed)
    samples = np.asarray(audio.samples, dtype=np.float32)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(audio.sample_rate))
        wav.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
