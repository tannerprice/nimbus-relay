from __future__ import annotations

import logging
import signal
import socket
import time
from datetime import datetime, timezone

from .config import RelayConfig, load_config
from .mqtt_client import NimbusMqttClient
from .pipeline import NimbusPipeline
from .same import parse_same

_LOGGER = logging.getLogger(__name__)


def configure_logging(config: RelayConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        sock.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


def get_audio_url(config: RelayConfig) -> str:
    host = config.audio_public_host or get_local_ip()

    return f"http://{host}:8000/nwr.mp3"


class NimbusRelayApp:
    def __init__(self, config: RelayConfig) -> None:
        self.config = config
        self.mqtt = NimbusMqttClient(config)
        self.pipeline = NimbusPipeline(config)

        self.running = False
        self._last_health_publish = 0.0
        self._last_eom_seen = 0.0
        self._same_seen: dict[str, float] = {}

    def start(self) -> None:
        self.running = True

        self.mqtt.connect()
        self.mqtt.publish_status("starting")

        self.pipeline.start()

        audio_url = get_audio_url(self.config)
        self.mqtt.publish_audio_url(audio_url)

        self.mqtt.publish_status("running")

        _LOGGER.info("Nimbus Relay started")
        _LOGGER.info("Audio URL: %s", audio_url)

    def stop(self) -> None:
        self.running = False

        _LOGGER.info("Stopping Nimbus Relay")

        try:
            self.mqtt.publish_status("stopping")
        except Exception:
            pass

        self.pipeline.stop()

        try:
            self.mqtt.publish_status("offline")
            self.mqtt.disconnect()
        except Exception:
            pass

    def run(self) -> None:
        self.start()

        try:
            while self.running:
                self._supervise_pipeline()
                self._publish_health_if_needed()

                line = self.pipeline.read_line(timeout=1.0)
                if not line:
                    continue

                self._handle_decoder_line(line)

        finally:
            self.stop()

    def _handle_decoder_line(self, line: str) -> None:
        if "ZCZC" in line:
            self._handle_same(line)
            return

        if "NNNN" in line:
            self._handle_eom()
            return

    def _handle_same(self, raw: str) -> None:
        if self._is_recent_same(raw):
            _LOGGER.info("Duplicate SAME header suppressed")
            return

        payload = parse_same(raw)

        if payload is None:
            _LOGGER.warning("Could not parse SAME header: %s", raw)
            return

        _LOGGER.info(
            "SAME alert decoded: %s counties=%s expires=%s",
            payload.get("event_code"),
            payload.get("counties"),
            payload.get("issue_expiry_utc"),
        )

        self.mqtt.publish_same(payload)

    def _handle_eom(self) -> None:
        now = time.monotonic()

        if now - self._last_eom_seen < 2:
            _LOGGER.info("Duplicate EOM suppressed")
            return

        self._last_eom_seen = now

        payload = {
            "eom_utc": datetime.now(timezone.utc).isoformat(),
        }

        _LOGGER.info("EOM decoded")
        self.mqtt.publish_eom(payload)

    def _is_recent_same(self, raw: str) -> bool:
        now = time.monotonic()
        cutoff = now - 15

        for seen_raw, seen_at in list(self._same_seen.items()):
            if seen_at < cutoff:
                del self._same_seen[seen_raw]

        if raw in self._same_seen:
            self._same_seen[raw] = now
            return True

        self._same_seen[raw] = now
        return False

    def _supervise_pipeline(self) -> None:
        if self.pipeline.is_healthy():
            return

        _LOGGER.error("SDR pipeline unhealthy; restarting")
        self.mqtt.publish_status("pipeline_restarting")
        self.pipeline.restart()
        self.mqtt.publish_status("running")

    def _publish_health_if_needed(self) -> None:
        now = time.monotonic()

        if now - self._last_health_publish < 30:
            return

        self._last_health_publish = now

        self.mqtt.publish_health(
            {
                "status": "running" if self.pipeline.is_healthy() else "unhealthy",
                "pipeline_healthy": self.pipeline.is_healthy(),
                "frequency": self.config.sdr_frequency,
                "device_index": self.config.sdr_device_index,
                "published_utc": datetime.now(timezone.utc).isoformat(),
            }
        )


def main() -> None:
    config = load_config()
    configure_logging(config)

    app = NimbusRelayApp(config)

    def shutdown_handler(signum, frame) -> None:
        _LOGGER.info("Received signal %s", signum)
        app.running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    app.run()


if __name__ == "__main__":
    main()
