#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wanzhi.core.config import load_config  # noqa: E402
from wanzhi.voice.tts_manager import TTSManager  # noqa: E402


DEFAULT_TEXT = "你好，我是丸智，今天我会陪着你。"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample wav files for Sherpa speaker audition.")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "voice-auditions"))
    parser.add_argument("--aishell3", default="0,10,21,33,41,45,66,99,103,120")
    parser.add_argument("--kokoro", default="1,18,23,24,45,46,47,48,49,50,51,52")
    args = parser.parse_args()

    config = load_config()
    manager = TTSManager(config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    catalog: list[dict] = []
    for model, speaker_ids in {
        "aishell3": _parse_ids(args.aishell3),
        "kokoro": _parse_ids(args.kokoro),
    }.items():
        for speaker in speaker_ids:
            voice_id = f"audition_{model}_{speaker}"
            manager.voices[voice_id] = {
                "label": f"{model} speaker {speaker}",
                "engine": "sherpa",
                "model": model,
                "speaker": speaker,
            }
            output_path = output_dir / f"{model}-sid-{speaker}.wav"
            started = time.perf_counter()
            generated = manager.synthesize(args.text, voice_id=voice_id, use_cache=False)
            generated.replace(output_path)
            elapsed = time.perf_counter() - started
            catalog.append(
                {
                    "voice_id": voice_id,
                    "model": model,
                    "speaker": speaker,
                    "file": str(output_path.relative_to(ROOT)),
                    "text": args.text,
                    "elapsed_seconds": round(elapsed, 3),
                    "notes": "",
                }
            )
            print(f"generated {output_path} in {elapsed:.2f}s")

    catalog_path = output_dir / "voice_catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {catalog_path}")


def _parse_ids(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


if __name__ == "__main__":
    main()
