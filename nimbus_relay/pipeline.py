from __future__ import annotations

import logging
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass

from .config import RelayConfig
from .same import normalize_multimon_line

_LOGGER = logging.getLogger(__name__)

AUDIO_CHUNK = 4096


@dataclass
class PipelineProcesses:
    rtl_fm: subprocess.Popen
    same_ffmpeg: subprocess.Popen
    multimon: subprocess.Popen
    audio_ffmpeg: subprocess.Popen


class NimbusPipeline:
    def __init__(
        self,
        config: RelayConfig,
    ) -> None:
        self.audio_clients: set[queue.Queue[bytes]] = set()
        self.audio_clients_lock = threading.Lock()
        self.audio_preroll: deque[bytes] = deque(maxlen=32)

        self.config = config
        self.line_queue: queue.Queue[str] = queue.Queue(maxsize=256)
        self.processes: PipelineProcesses | None = None
        self.running = False

    def register_audio_client(self) -> queue.Queue[bytes]:
        q: queue.Queue[bytes] = queue.Queue(maxsize=128)

        with self.audio_clients_lock:
            for chunk in self.audio_preroll:
                q.put_nowait(chunk)

            self.audio_clients.add(q)

        return q

    def unregister_audio_client(self, q: queue.Queue[bytes]) -> None:
        with self.audio_clients_lock:
            self.audio_clients.discard(q)

    def _broadcast_audio_chunk(self, chunk: bytes) -> None:
        with self.audio_clients_lock:
            self.audio_preroll.append(chunk)
            dead: set[queue.Queue[bytes]] = set()

            for q in self.audio_clients:
                try:
                    q.put_nowait(chunk)
                except queue.Full:
                    dead.add(q)

            self.audio_clients.difference_update(dead)

    def start(self) -> None:
        if self.running:
            return

        _LOGGER.info(
            "Starting SDR pipeline freq=%s device=%s gain=%s",
            self.config.sdr_frequency,
            self.config.sdr_device_index,
            self.config.sdr_gain,
        )

        rtl_cmd = [
            "rtl_fm",
            "-d",
            self.config.sdr_device_index,
            "-f",
            self.config.sdr_frequency,
            "-M",
            "fm",
            "-s",
            self.config.sdr_sample_rate,
            "-g",
            self.config.sdr_gain,
            "-F",
            "9",
            "-E",
            "deemp",
            "-E",
            "dc",
            "-",
        ]

        same_ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel",
            "quiet",
            "-f",
            "s16le",
            "-ar",
            self.config.sdr_sample_rate,
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-af",
            "highpass=f=300,lowpass=f=2800,volume=6dB",
            "-f",
            "s16le",
            "-ar",
            self.config.same_sample_rate,
            "-ac",
            "1",
            "pipe:1",
        ]

        multimon_cmd = [
            "multimon-ng",
            "-a",
            "EAS",
            "-t",
            "raw",
            "/dev/stdin",
        ]

        audio_ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner-loglevel",
            "warning",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-f",
            "s16le",
            "-ar",
            self.config.sdr_sample_rate,
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-af",
            "highpass=f=350,lowpass=f=3000,volume=6dB,alimiter=limit=0.92",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "64k",
            "-ar",
            "22050",
            "-ac",
            "1",
            "-f",
            "mp3",
            "-write_xing",
            "0",
            "-flush_packets",
            "1",
            "pipe:1",
        ]

        rtl_proc = subprocess.Popen(
            rtl_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        same_ffmpeg_proc = subprocess.Popen(
            same_ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        multimon_proc = subprocess.Popen(
            multimon_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        audio_ffmpeg_proc = subprocess.Popen(
            audio_ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.processes = PipelineProcesses(
            rtl_fm=rtl_proc,
            same_ffmpeg=same_ffmpeg_proc,
            multimon=multimon_proc,
            audio_ffmpeg=audio_ffmpeg_proc,
        )

        self.running = True

        threading.Thread(
            target=self._tee_rtl_audio,
            daemon=True,
            name="rtl-tee",
        ).start()

        threading.Thread(
            target=self._pipe_same_audio,
            daemon=True,
            name="same-pipe",
        ).start()

        threading.Thread(
            target=self._read_multimon_stdout,
            daemon=True,
            name="multimon-reader",
        ).start()

        threading.Thread(
            target=self._log_process_stderr,
            args=("rtl_fm", rtl_proc),
            daemon=True,
        ).start()

        threading.Thread(
            target=self._log_process_stderr,
            args=("multimon", multimon_proc),
            daemon=True,
        ).start()

        threading.Thread(
            target=self._log_process_stderr,
            args=("same-ffmpeg", same_ffmpeg_proc),
            daemon=True,
        ).start()

        threading.Thread(
            target=self._log_process_stderr,
            args=("audio-ffmpeg", audio_ffmpeg_proc),
            daemon=True,
        ).start()

        threading.Thread(
            target=self._read_audio_ffmpeg_stdout, daemon=True, name="audio-broadcast"
        ).start()

    def _read_audio_ffmpeg_stdout(self) -> None:
        assert self.processes is not None

        stdout = self.processes.audio_ffmpeg.stdout

        if stdout is None:
            return

        try:
            while self.running:
                chunk = stdout.read(AUDIO_CHUNK)

                if not chunk:
                    _LOGGER.error("audio ffmpeg stdout ended")
                    self.restart()

                    return

                self._broadcast_audio_chunk(chunk)

        except Exception:
            _LOGGER.exception("audio broadcaster crashed")

            self.restart()

    def stop(self) -> None:
        self.running = False

        if not self.processes:
            return

        for proc in (
            self.processes.audio_ffmpeg,
            self.processes.multimon,
            self.processes.same_ffmpeg,
            self.processes.rtl_fm,
        ):
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

        self.processes = None

    def restart(self) -> None:
        _LOGGER.warning("Restarting SDR pipeline")

        self.stop()

        time.sleep(2)

        self.start()

    def read_line(
        self,
        timeout: float = 1.0,
    ) -> str | None:
        try:
            return self.line_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_healthy(self) -> bool:
        if not self.processes:
            return False

        return (
            self.processes.rtl_fm.poll() is None
            and self.processes.same_ffmpeg.poll() is None
            and self.processes.multimon.poll() is None
            and self.processes.audio_ffmpeg.poll() is None
        )

    def _tee_rtl_audio(self) -> None:
        assert self.processes is not None

        rtl_stdout = self.processes.rtl_fm.stdout
        same_stdin = self.processes.same_ffmpeg.stdin
        audio_stdin = self.processes.audio_ffmpeg.stdin

        if rtl_stdout is None or same_stdin is None or audio_stdin is None:
            return

        try:
            while self.running:
                chunk = rtl_stdout.read(AUDIO_CHUNK)

                if not chunk:
                    _LOGGER.error("rtl_fm stdout ended")
                    self.restart()
                    return

                try:
                    same_stdin.write(chunk)
                    same_stdin.flush()
                except BrokenPipeError:
                    _LOGGER.error("same ffmpeg pipe broken")

                try:
                    audio_stdin.write(chunk)
                    audio_stdin.flush()
                except BrokenPipeError:
                    _LOGGER.error("audio ffmpeg pipe broken")

        except Exception:
            _LOGGER.exception("RTL tee thread crashed")
            self.restart()

    def _pipe_same_audio(self) -> None:
        assert self.processes is not None

        same_stdout = self.processes.same_ffmpeg.stdout
        multimon_stdin = self.processes.multimon.stdin

        if same_stdout is None or multimon_stdin is None:
            return

        try:
            while self.running:
                chunk = same_stdout.read(AUDIO_CHUNK)

                if not chunk:
                    _LOGGER.error("same ffmpeg stdout ended")
                    self.restart()
                    return

                multimon_stdin.write(chunk)
                multimon_stdin.flush()

        except Exception:
            _LOGGER.exception("same audio pipe crashed")
            self.restart()

    def _read_multimon_stdout(self) -> None:
        assert self.processes is not None

        stdout = self.processes.multimon.stdout

        if stdout is None:
            return

        try:
            for raw_bytes in stdout:
                line = raw_bytes.decode(
                    "utf-8",
                    errors="ignore",
                ).strip()

                if not line:
                    continue

                normalized = normalize_multimon_line(line)

                _LOGGER.info("multimon: %s", normalized)

                self.line_queue.put(normalized)

        except Exception:
            _LOGGER.exception("multimon reader crashed")
            self.restart()

    def _log_process_stderr(
        self,
        name: str,
        process: subprocess.Popen,
    ) -> None:
        if process.stderr is None:
            return

        try:
            for raw_bytes in process.stderr:
                line = raw_bytes.decode(
                    "utf-8",
                    errors="ignore",
                ).strip()

                if not line:
                    continue

                _LOGGER.warning("%s stderr: %s", name, line)

        except Exception:
            _LOGGER.exception("stderr logger crashed for %s", name)
