from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import RelayConfig
from .pipeline import NimbusPipeline

_LOGGER = logging.getLogger(__name__)


class AudioStreamServer:
    def __init__(
        self,
        config: RelayConfig,
        pipeline: NimbusPipeline,
    ) -> None:
        self.config = config
        self.pipeline = pipeline
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        handler = self._make_handler()

        self.server = ThreadingHTTPServer(
            (self.config.audio_stream_host, self.config.audio_stream_port),
            handler,
        )
        self.server.daemon_threads = True

        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
            name="audio-http",
        )
        self.thread.start()

        _LOGGER.info(
            "Audio stream server listening on http://%s:%s/nwr.mp3",
            self.config.audio_stream_host,
            self.config.audio_stream_port,
        )

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()

        self.server = None
        self.thread = None

    def _make_handler(self):
        pipeline = self.pipeline

        class AudioHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                if self.path not in ("/", "/nwr.mp3"):
                    self.send_response(404)
                    self.end_headers()
                    return

                _LOGGER.info("Audio client connected from %s", self.client_address[0])

                client_queue = pipeline.register_audio_client()

                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("icy-name", "Nimbus NOAA Weather Radio")
                    self.send_header("icy-description", "NOAA Weather Radio via Nimbus")
                    self.send_header("icy-genre", "Weather")
                    self.send_header("icy-br", "64")
                    self.send_header("Accept-Ranges", "none")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()

                    while True:
                        chunk = client_queue.get(timeout=10)

                        self.wfile.write(chunk)
                        self.wfile.flush()

                finally:
                    pipeline.unregister_audio_client(client_queue)

            def log_message(self, format: str, *args) -> None:
                _LOGGER.debug("HTTP " + format, *args)

        return AudioHandler
