"""ffmpeg-based audio capture: any file, stream URL or microphone -> 16 kHz mono PCM."""

import platform
import shutil
import subprocess
from collections.abc import Callable

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # 16-bit mono
CHUNK_BYTES = BYTES_PER_SECOND // 10  # 100 ms, as recommended by the Live API

_PCM_OUTPUT = ["-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]


def ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("ffmpeg not found in PATH. Install it: https://ffmpeg.org/download.html")
    return executable


def file_command(path: str, realtime: bool = True, loop: bool = False) -> list[str]:
    """Read a local file. realtime=True paces it like a live stage (ffmpeg -re)."""
    command = [ffmpeg_executable(), "-hide_banner", "-loglevel", "error"]
    if loop:
        command += ["-stream_loop", "-1"]
    if realtime:
        command.append("-re")
    return command + ["-i", path, *_PCM_OUTPUT]


def stream_command(url: str) -> list[str]:
    """Read a live stream (RTMP, SRT, HLS, Icecast...). Already real-time, no pacing."""
    return [ffmpeg_executable(), "-hide_banner", "-loglevel", "error",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-i", url, *_PCM_OUTPUT]


def microphone_command(device: str | None) -> list[str]:
    system = platform.system()
    if system == "Windows":
        source = ["-f", "dshow", "-i", f"audio={device}"]
    elif system == "Darwin":
        source = ["-f", "avfoundation", "-i", f":{device or '0'}"]
    else:
        source = ["-f", "pulse", "-i", device or "default"]
    return [ffmpeg_executable(), "-hide_banner", "-loglevel", "error", *source, *_PCM_OUTPUT]


def list_devices_command() -> list[str]:
    system = platform.system()
    if system == "Windows":
        return [ffmpeg_executable(), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
    if system == "Darwin":
        return [ffmpeg_executable(), "-hide_banner", "-list_devices", "true", "-f", "avfoundation", "-i", ""]
    return ["pactl", "list", "short", "sources"]


def start_process(command: list[str], stdin=None) -> subprocess.Popen:
    return subprocess.Popen(command, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def pump_chunks(process: subprocess.Popen, on_chunk: Callable[[bytes], None]) -> None:
    """Blocking: read PCM from the process in 100 ms chunks until EOF. Run it in a thread."""
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(CHUNK_BYTES)
        if not chunk:
            return
        on_chunk(chunk)
