from __future__ import annotations

import json
import os
import time
from pathlib import Path

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from wanzhi.core.config import AppConfig
from wanzhi.core.timing import log_timing, now_seconds
from wanzhi.voice.tts_base import TTSBackend, VoiceProfile


class AliyunTokenProvider:
    def __init__(self, region: str = "cn-shanghai") -> None:
        self.region = region
        self._token: str | None = None
        self._expires_at = 0

    def token(self) -> str:
        configured_token = os.getenv("ALIYUN_NLS_TOKEN")
        if configured_token:
            started = now_seconds()
            log_timing("tts.aliyun.token", started, source="env", cache_hit=True)
            return configured_token

        now = int(time.time())
        if self._token and now < self._expires_at - 300:
            started = now_seconds()
            log_timing("tts.aliyun.token", started, source="memory", cache_hit=True)
            return self._token

        started = now_seconds()
        access_key_id = os.getenv("ALIYUN_AK_ID") or os.getenv("ALIYUN_ACCESS_KEY_ID")
        access_key_secret = os.getenv("ALIYUN_AK_SECRET") or os.getenv("ALIYUN_ACCESS_KEY_SECRET")
        if not access_key_id or not access_key_secret:
            raise RuntimeError("Aliyun NLS credentials are not configured")

        client = AcsClient(access_key_id, access_key_secret, self.region)
        request = CommonRequest()
        request.set_method("POST")
        request.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")
        response = client.do_action_with_exception(request)
        payload = json.loads(response)
        token = payload.get("Token", {}).get("Id")
        expires_at = int(payload.get("Token", {}).get("ExpireTime") or 0)
        if not token:
            raise RuntimeError("Aliyun NLS token response did not include Token.Id")
        self._token = str(token)
        self._expires_at = expires_at
        log_timing("tts.aliyun.token", started, source="api", cache_hit=False)
        return self._token


class AliyunTTSBackend(TTSBackend):
    """Alibaba Cloud NLS speech synthesis backend."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.enabled = str(config.get("tts.provider", "")).lower() == "aliyun"
        self.appkey = str(config.get("tts.aliyun.appkey", "") or os.getenv("ALIYUN_NLS_APPKEY", ""))
        self.url = str(config.get("tts.aliyun.url", "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"))
        self.voice = str(config.get("tts.aliyun.voice", "ailun"))
        self.aformat = str(config.get("tts.aliyun.format", "wav"))
        self.sample_rate = int(config.get("tts.aliyun.sample_rate", 16000))
        self.volume = int(config.get("tts.aliyun.volume", 50))
        self.speech_rate = int(config.get("tts.aliyun.speech_rate", 0))
        self.pitch_rate = int(config.get("tts.aliyun.pitch_rate", 0))
        self.token_provider = AliyunTokenProvider(str(config.get("tts.aliyun.region", "cn-shanghai")))

    def can_synthesize(self, voice: VoiceProfile) -> bool:
        return self.enabled or str(voice.get("engine", "")).lower() == "aliyun"

    def prewarm(self) -> None:
        if self.enabled or self.appkey:
            self.token_provider.token()

    def synthesize(self, text: str, voice: VoiceProfile, output_path: Path) -> Path:
        if not self.appkey:
            raise RuntimeError("ALIYUN_NLS_APPKEY is not configured")

        import nls

        started = now_seconds()
        errors: list[str] = []
        voice_name = str(voice.get("aliyun_voice") or voice.get("voice") or self.voice)

        with output_path.open("wb") as output:
            def on_data(data, *args):  # type: ignore[no-untyped-def]
                output.write(data)

            def on_error(message, *args):  # type: ignore[no-untyped-def]
                errors.append(str(message))

            synthesizer = nls.NlsSpeechSynthesizer(
                url=self.url,
                token=self.token_provider.token(),
                appkey=self.appkey,
                on_data=on_data,
                on_error=on_error,
            )
            result = synthesizer.start(
                text,
                voice=voice_name,
                aformat=self.aformat,
                sample_rate=self.sample_rate,
                volume=self.volume,
                speech_rate=self.speech_rate,
                pitch_rate=self.pitch_rate,
                wait_complete=True,
            )

        if errors:
            raise RuntimeError("; ".join(errors))
        if result is False or not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("Aliyun NLS synthesis returned no audio")
        log_timing("tts.aliyun.synthesize", started, voice=voice_name, chars=len(text))
        return output_path
