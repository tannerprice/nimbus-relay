from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import dotenv_values


@dataclass(frozen=True)
class RelayConfig:
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str
    mqtt_pass: str
    topic_root: str

    sdr_device_index: str
    sdr_frequency: str
    sdr_sample_rate: str
    sdr_gain: str
    same_sample_rate: str

    audio_input_file: str | None
    audio_stream_host: str
    audio_stream_port: int
    audio_public_host: str | None

    log_level: str


def load_config() -> RelayConfig:
    path = os.environ.get("NIMBUS_RELAY_CONFIG", "/opt/nimbus-relay/config.env")
    cfg = dotenv_values(path)

    def _get(
        key: str,
        default: str,
    ) -> str:

        value = cfg.get(key)

        if value is None:
            return default

        return str(value)

    return RelayConfig(
        mqtt_host=_get("MQTT_HOST", "localhost"),
        mqtt_port=int(_get("MQTT_PORT", "1883")),
        mqtt_user=_get("MQTT_USER", ""),
        mqtt_pass=_get("MQTT_PASS", ""),
        topic_root=_get("MQTT_TOPIC_ROOT", "nimbus").strip("/"),
        sdr_device_index=_get("SDR_DEVICE_INDEX", "0"),
        sdr_frequency=_get("SDR_FREQUENCY", "162.550M"),
        sdr_sample_rate=_get("SDR_SAMPLE_RATE", "32000"),
        sdr_gain=_get("SDR_GAIN", "28.0"),
        same_sample_rate=_get("SAME_SAMPLE_RATE", "22050"),
        audio_input_file=_get("AUDIO_INPUT_FILE", "") or None,
        audio_stream_host=_get("AUDIO_STREAM_HOST", "0.0.0.0"),
        audio_stream_port=int(_get("AUDIO_STREAM_PORT", "8765")),
        audio_public_host=_get("AUDIO_PUBLIC_HOST", "") or None,
        log_level=_get("LOG_LEVEL", "INFO"),
    )
