"""Audio source CLI: captures audio at a stage and streams it to a Vox Libera room.

Examples:
    voxlibera-source --room main-stage --file samples/talk-en.opus
    voxlibera-source --room main-stage --url rtmp://obs.local/live/stage1
    voxlibera-source --room main-stage --youtube https://www.youtube.com/watch?v=...
    voxlibera-source --room main-stage --mic "Microphone (USB Audio)"
    voxlibera-source --list-devices
"""

import argparse
import asyncio
import shutil
import subprocess
import sys
import threading

import websockets

from voxlibera import audio_input


def build_capture(arguments: argparse.Namespace) -> list[subprocess.Popen]:
    """Start the capture pipeline; the last process outputs PCM on stdout."""
    if arguments.file:
        return [audio_input.start_process(audio_input.file_command(arguments.file, loop=arguments.loop))]
    if arguments.url:
        return [audio_input.start_process(audio_input.stream_command(arguments.url))]
    if arguments.mic is not None:
        return [audio_input.start_process(audio_input.microphone_command(arguments.mic or None))]
    if arguments.youtube:
        downloader = shutil.which("yt-dlp")
        if downloader is None:
            sys.exit("yt-dlp not found in PATH (pip install yt-dlp)")
        download = subprocess.Popen(
            [downloader, "--quiet", "-f", "bestaudio/best", "-o", "-", arguments.youtube],
            stdout=subprocess.PIPE,
        )
        # A recorded video is paced to real time with -re; a live stream already is.
        decode_command = [audio_input.ffmpeg_executable(), "-hide_banner", "-loglevel", "error"]
        if not arguments.live:
            decode_command.append("-re")
        decode_command += ["-i", "pipe:0", "-vn", "-ac", "1", "-ar", str(audio_input.SAMPLE_RATE), "-f", "s16le", "-"]
        decode = audio_input.start_process(decode_command, stdin=download.stdout)
        return [download, decode]
    sys.exit("Choose an input: --file, --url, --youtube or --mic")


async def stream(arguments: argparse.Namespace) -> None:
    processes = build_capture(arguments)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    def pump() -> None:
        audio_input.pump_chunks(processes[-1], lambda chunk: loop.call_soon_threadsafe(queue.put_nowait, chunk))
        loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=pump, daemon=True).start()
    url = f"{arguments.server.rstrip('/')}/ws/ingest/{arguments.room}"
    if arguments.token:
        url += f"?token={arguments.token}"

    sent_bytes = 0
    last_report = -1
    try:
        async with websockets.connect(url, max_size=None) as connection:
            print(f"Streaming to {url} (Ctrl+C to stop)")
            while (chunk := await queue.get()) is not None:
                await connection.send(chunk)
                sent_bytes += len(chunk)
                seconds = int(sent_bytes / audio_input.BYTES_PER_SECOND)
                if seconds // 10 != last_report:
                    last_report = seconds // 10
                    print(f"  {seconds // 60:02}:{seconds % 60:02} sent", flush=True)
            print("Input finished, waiting for the last captions...")
            await asyncio.sleep(6)
    except websockets.ConnectionClosed as closed:
        print(f"Server closed the connection: {closed.rcvd.reason if closed.rcvd else closed}")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream stage audio to a Vox Libera room")
    parser.add_argument("--server", default="ws://localhost:8000", help="Vox Libera server (ws:// or wss://)")
    parser.add_argument("--room", help="Room id from rooms.yaml")
    parser.add_argument("--token", help="Admin key, if the server sets VOXLIBERA_ADMIN_KEY")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--file", help="Audio/video file, streamed at real-time speed")
    inputs.add_argument("--url", help="Live stream URL readable by ffmpeg (RTMP, SRT, HLS...)")
    inputs.add_argument("--youtube", help="YouTube URL (requires yt-dlp)")
    inputs.add_argument("--mic", nargs="?", const="", help="Microphone device name (see --list-devices)")
    parser.add_argument("--loop", action="store_true", help="Loop --file forever")
    parser.add_argument("--live", action="store_true", help="--youtube URL is a live stream (no pacing)")
    parser.add_argument("--list-devices", action="store_true", help="List capture devices and exit")
    arguments = parser.parse_args()

    if arguments.list_devices:
        subprocess.run(audio_input.list_devices_command())
        return
    if not arguments.room:
        parser.error("--room is required")
    try:
        asyncio.run(stream(arguments))
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
