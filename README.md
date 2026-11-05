# bistprobe

UART probe for the BIST dataport. Authenticates (waits for `F0`, sends
`DTV--BIST`, waits for `BIST Dataport Started`), then sends a fixed set of
hand-picked test frames — once, in a fixed order — and appends each frame
and response to a log. Extend the frame constants to probe more.

## Usage

```sh
uv run bistprobe                   # /dev/ttyUSB0 @ 115200, logs to probe_results.log
uv run bistprobe -n                # already authenticated
uv run bistprobe -p /dev/ttyUSB1 -b 115200 -l run1.log
uv run bistprobe --auth-timeout 30  # fail fast if the device never answers
```

## Probed frames

The channels, command IDs, payloads, and size markers probed by default are
constants at the top of `src/bistprobe/cli.py`; extend them there.

Malformed frames are intentional, and `build_frame` only checks field *shape*,
never value:

- A channel above `0xF` widens the channel field and shifts every later field.
- The size marker (the single character after the command ID) may be any ASCII
  character. The target treats it as the payload size, so a non-hex marker
  like `"Q"` probes the suspected overflow. For the checksum, hex digits
  (either case) count as their hex value, as in the original script, and any
  other character counts as its code point.

## Development

```sh
uv run ruff format   # format
uv run ruff check    # lint
uv run mypy          # type-check (strict)
uv run pytest        # tests; no hardware needed
```

## Credits

Derived from [`get_shell/shell_poc.py`](https://github.com/fatj3sus/bgw320-security-research/blob/main/get_shell/shell_poc.py)
in [fatj3sus/bgw320-security-research](https://github.com/fatj3sus/bgw320-security-research),
the BGW320 root-shell research by fatj3sus. The BIST dataport authentication
sequence, frame format, and `telnetd` payload all come from that work.
Original code is Copyright (c) 2025 fatj3sus, used under the MIT License.
