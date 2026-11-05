"""Frame encoding for the BIST dataport UART protocol.

A frame is ASCII hex text, multi-byte fields big-endian::

    "EA" | channel (1 nibble) | cmd_id (2 bytes) | has_payload (1 nibble)
         | [length (1 byte) | PAYLOAD_PREFIX | payload]
         | checksum (1 byte)
"""

START_MARKER = b"EA"
HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
# 192.168.1.10 followed by 0x01, sent ahead of every payload.
PAYLOAD_PREFIX = bytes([192, 168, 1, 10, 1])


def _hex(data: bytes) -> bytes:
    return data.hex().upper().encode("ascii")


def checksum(frame: bytes | bytearray) -> int:
    """Sum of the value of every character in ``frame``, modulo 256.

    Hex digits count as their hex value, which matches the original script and
    the frames it was verified against. Any other ASCII character counts as
    its code point, matching the target's behavior of adding characters as
    ints.
    """
    total = 0
    for char in frame.decode("ascii"):
        total += int(char, 16) if char in HEX_DIGITS else ord(char)
    return total & 0xFF


def build_frame(
    channel: int, cmd_id: int, payload: bytes = b"", *, size_marker: str = "1"
) -> bytes:
    """Build a complete, checksummed frame.

    Field ranges are deliberately not checked so malformed frames can be sent:
    a channel above 0xF widens the channel field and shifts every later field,
    and ``size_marker`` may be any single ASCII character. Only the marker's
    shape (one character) is checked, never its value.
    """
    if len(size_marker) != 1 or not size_marker.isascii():
        msg = f"size_marker must be exactly one ASCII character, got {size_marker!r}"
        raise ValueError(msg)

    frame = bytearray(START_MARKER)
    frame += f"{channel:X}".encode("ascii")
    frame += _hex(cmd_id.to_bytes(2, "big"))

    if payload:
        # Suspected overflow point: the target treats this nibble as a size
        # field, so non-hex ASCII here should decode to 0xFF.
        frame += size_marker.encode("ascii")
        body = PAYLOAD_PREFIX + payload
        frame += _hex(len(body).to_bytes(1, "big"))
        frame += _hex(body)
    else:
        frame += b"0"

    frame += f"{checksum(frame):02X}".encode("ascii")
    return bytes(frame)
