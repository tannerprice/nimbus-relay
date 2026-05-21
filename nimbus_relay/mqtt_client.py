from __future__ import annotations

import json
import logging

import paho.mqtt.client as mqtt

from .config import RelayConfig

_LOGGER = logging.getLogger(__name__)


class NimbusMqttClient:
    def __init__(self, config: RelayConfig) -> None:
        self._config = config

        self.client = mqtt.Client(
            client_id="nimbus-relay",
            clean_session=True,
        )

        if config.mqtt_user:
            self.client.username_pw_set(
                config.mqtt_user,
                config.mqtt_pass,
            )

        self.client.will_set(
            self.topic("status"),
            payload="offline",
            retain=True,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def connect(self) -> None:
        _LOGGER.info(
            "Connecting MQTT to %s:%s",
            self._config.mqtt_host,
            self._config.mqtt_port,
        )

        self.client.connect(
            self._config.mqtt_host,
            self._config.mqtt_port,
            keepalive=60,
        )

        self.client.loop_start()

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def topic(self, suffix: str) -> str:
        return f"{self._config.topic_root}/{suffix}"

    def publish(
        self,
        topic: str,
        payload,
        retain: bool = False,
    ) -> None:
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)

        full_topic = self.topic(topic)

        self.client.publish(
            full_topic,
            payload=str(payload),
            qos=0,
            retain=retain,
        )

        _LOGGER.debug(
            "MQTT -> %s : %s",
            full_topic,
            str(payload)[:250],
        )

    def publish_status(self, status: str) -> None:
        self.publish(
            "status",
            status,
            retain=True,
        )

    def publish_same(self, payload: dict) -> None:
        self.publish(
            "alert/same",
            payload,
            retain=True,
        )

    def publish_eom(self, payload: dict) -> None:
        self.publish(
            "alert/eom",
            payload,
            retain=True,
        )

    def publish_audio_url(self, url: str) -> None:
        self.publish(
            "audio/url",
            url,
            retain=True,
        )

    def publish_health(self, payload: dict) -> None:
        self.publish(
            "relay/health",
            payload,
            retain=False,
        )

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        rc,
    ) -> None:
        code = rc if isinstance(rc, int) else rc.value

        if code == 0:
            _LOGGER.info("MQTT connected")
            self.publish_status("running")
        else:
            _LOGGER.error("MQTT connect failed rc=%s", rc)

    def _on_disconnect(
        self,
        client,
        userdata,
        rc,
    ) -> None:
        _LOGGER.warning("MQTT disconnected rc=%s", rc)
