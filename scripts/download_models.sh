#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p \
  "$ROOT_DIR/models/sherpa-asr" \
  "$ROOT_DIR/models/sherpa-tts" \
  "$ROOT_DIR/models/piper-voices" \
  "$ROOT_DIR/models/wakeword" \
  "$ROOT_DIR/models/mediapipe"

HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
SHERPA_RELEASE_BASE="${SHERPA_RELEASE_BASE:-https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models}"
PIPER_REPO="${PIPER_REPO:-rhasspy/piper-voices}"
PIPER_VOICE="${PIPER_VOICE:-zh_CN-huayan-medium}"
PIPER_VOICE_DIR="${PIPER_VOICE_DIR:-zh/zh_CN/huayan/medium}"

download_if_missing() {
  local url="$1"
  local output="$2"
  if [[ -s "$output" ]]; then
    echo "Already exists: $output"
    return
  fi
  echo "Downloading: $url"
  curl -L --fail --connect-timeout 20 --max-time 300 -o "$output" "$url"
}

download_and_extract_tar_bz2() {
  local name="$1"
  local output_dir="$ROOT_DIR/models/sherpa-tts/$name"
  local archive="$ROOT_DIR/models/sherpa-tts/$name.tar.bz2"
  if [[ -d "$output_dir" && -s "$output_dir/model.onnx" ]]; then
    echo "Already exists: $output_dir"
    return
  fi
  download_if_missing "$SHERPA_RELEASE_BASE/$name.tar.bz2" "$archive"
  tar -xjf "$archive" -C "$ROOT_DIR/models/sherpa-tts"
}

download_if_missing \
  "$HF_ENDPOINT/$PIPER_REPO/resolve/main/$PIPER_VOICE_DIR/$PIPER_VOICE.onnx" \
  "$ROOT_DIR/models/piper-voices/$PIPER_VOICE.onnx"

download_if_missing \
  "$HF_ENDPOINT/$PIPER_REPO/resolve/main/$PIPER_VOICE_DIR/$PIPER_VOICE.onnx.json" \
  "$ROOT_DIR/models/piper-voices/$PIPER_VOICE.onnx.json"

download_and_extract_tar_bz2 "vits-icefall-zh-aishell3"

if [[ "${DOWNLOAD_KOKORO:-1}" == "1" ]]; then
  download_and_extract_tar_bz2 "kokoro-multi-lang-v1_0"
fi

cat <<MSG
Model download checklist:

1. Ollama
   ollama pull qwen2.5:1.5b-instruct

2. Sherpa-ONNX ASR
   Download a Chinese/English streaming Zipformer model into:
   models/sherpa-asr/streaming-zipformer-bilingual-zh-en/

2.5 Sherpa-ONNX TTS
   Downloaded or checked:
   models/sherpa-tts/vits-icefall-zh-aishell3/
   models/sherpa-tts/kokoro-multi-lang-v1_0/
   Override SHERPA_RELEASE_BASE or DOWNLOAD_KOKORO=0 if needed.

3. Piper TTS
   Downloaded default voice through:
   $HF_ENDPOINT/$PIPER_REPO
   Voice files:
   models/piper-voices/$PIPER_VOICE.onnx
   models/piper-voices/$PIPER_VOICE.onnx.json
   Override HF_ENDPOINT, PIPER_VOICE, or PIPER_VOICE_DIR to use another mirror or voice.

4. Wake word
   Put the trained openWakeWord model at:
   models/wakeword/wanzhi.onnx

Large model files are ignored by git.
MSG
