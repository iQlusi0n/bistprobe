import itertools
import time
from pathlib import Path

import pytest

from bistprobe import cli
from bistprobe.protocol import build_frame


class FakePort:
    """Serves queued bytes on read and records writes with the read offset at write time."""

    def __init__(self, rx: bytes = b"", responses: list[bytes] | None = None) -> None:
        self.rx = rx
        self.pos = 0
        self.responses = responses or []
        self.writes: list[tuple[int, bytes]] = []

    def read(self, size: int = 1, /) -> bytes:
        if self.pos < len(self.rx):
            chunk = self.rx[self.pos : self.pos + size]
            self.pos += len(chunk)
            return chunk
        return self.responses.pop(0) if self.responses else b""

    def write(self, data: bytes, /) -> int:
        self.writes.append((self.pos, data))
        return len(data)

    def flush(self) -> None:
        pass

    def written(self) -> bytes:
        return b"".join(data for _, data in self.writes)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)


def test_authenticate_sends_sequence_only_after_prompt_line() -> None:
    prompt = b"boot \xff noise\r\nF0 not yet\nF0\r\n"
    port = FakePort(prompt + b"junk\nBIST Dataport Started\n")

    cli.authenticate(port)

    assert port.written() == cli.AUTH_SEQUENCE
    assert all(pos == len(prompt) for pos, _ in port.writes)
    assert port.pos == len(port.rx)


def test_probe_appends_every_frame_and_response_to_log(tmp_path: Path) -> None:
    log_file = tmp_path / "results.log"
    log_file.write_text("previous run\n", encoding="utf-8")
    combos = list(itertools.product(cli.CHANNELS, cli.CMD_IDS, cli.PAYLOADS, cli.SIZE_MARKERS))
    responses = [f"ACK{i}".encode() for i in range(len(combos))]
    port = FakePort(responses=list(responses))

    cli.probe(port, log_file)

    frames = [build_frame(*combo[:3], size_marker=combo[3]) for combo in combos]
    assert port.written() == b"".join(frames)
    log = log_file.read_text(encoding="utf-8")
    assert log.startswith("previous run\n")
    for frame, response in zip(frames, responses, strict=True):
        assert f"SENT: {frame!r}\n" in log
        assert f"RECV: {response!r}\n" in log


def test_wait_for_line_times_out_on_silence() -> None:
    port = FakePort()
    with pytest.raises(TimeoutError, match="F0"):
        cli.wait_for_line(port, "F0", timeout=0.1)


def test_main_reports_missing_port_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli.main(["--port", str(tmp_path / "no-such-tty")])

    assert exit_code == 1
    assert "serial error" in capsys.readouterr().err
