"""Follow the Entity Balance log and extract dynamic load management (DLM) limits.

The balancer computes, roughly every 10 s, how much current each connected
charger may use per phase, and logs it as:

    2026-10-22T06:57:26.027+00:00 dlmcontrol:391 INFO GaroCS-44111AAA46980: DLM limits: raw=(  13,  15,  13), filtered=(  11,  13,  11)

No REST endpoint exposes this, so DlmLogFollower tails /log/garoevse.log with
HTTP Range requests: the first read takes the last INITIAL_TAIL_BYTES, later
reads fetch only what was appended since. When the log is rotated the server
answers 416 (offset past the new, smaller file) and the follower starts over
from the tail.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp

_LOGGER = logging.getLogger(__name__)

LOG_PATH = "/log/garoevse.log"
INITIAL_TAIL_BYTES = 16 * 1024
MAX_READ_BYTES = 256 * 1024

_DLM_RE = re.compile(
    r"^(?P<ts>\S+)\s+dlmcontrol:\d+\s+\w+\s+(?P<charger>\S+?):\s+DLM limits:\s+"
    r"raw=\(\s*(?P<r1>-?\d+),\s*(?P<r2>-?\d+),\s*(?P<r3>-?\d+)\),\s+"
    r"filtered=\(\s*(?P<f1>-?\d+),\s*(?P<f2>-?\d+),\s*(?P<f3>-?\d+)\)"
)
_CONTENT_RANGE_RE = re.compile(r"bytes\s+(?:(\d+)-\d+|\*)/(\d+)")


@dataclass
class DlmReading:
    timestamp: datetime
    charger: str
    raw: tuple[int, int, int]
    filtered: tuple[int, int, int]


def parse_dlm_line(line: str) -> DlmReading | None:
    m = _DLM_RE.match(line)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(m["ts"])
    except ValueError:
        return None
    return DlmReading(
        timestamp=ts,
        charger=m["charger"],
        raw=(int(m["r1"]), int(m["r2"]), int(m["r3"])),
        filtered=(int(m["f1"]), int(m["f2"]), int(m["f3"])),
    )


def _parse_content_range(value: str | None) -> tuple[int | None, int | None]:
    """'bytes 100-199/1000' -> (100, 1000); 'bytes */1000' -> (None, 1000)."""
    m = _CONTENT_RANGE_RE.match(value or "")
    if not m:
        return None, None
    return (int(m[1]) if m[1] else None), int(m[2])


async def _read_up_to(resp: aiohttp.ClientResponse, limit: int) -> bytes:
    """Read the body until EOF or until more than `limit` bytes were received.

    resp.content.read(n) returns whatever is buffered (often 16 kB), not n bytes.
    """
    chunks, total = [], 0
    async for chunk in resp.content.iter_chunked(64 * 1024):
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            break
    return b"".join(chunks)


@dataclass
class DlmLogFollower:
    """Incremental reader of the balancer log. One instance per config entry."""

    base_url: str
    auth: aiohttp.BasicAuth
    offset: int | None = None  # byte offset of the next unread byte; None = tail on next poll
    latest: DlmReading | None = None
    changes: int = 0  # number of times the filtered limit changed since startup
    _partial: bytes = field(default=b"", repr=False)  # incomplete last line

    async def poll(self, session: aiohttp.ClientSession) -> DlmReading | None:
        """Read new log lines; return the newest DLM reading seen so far."""
        range_header = (
            f"bytes=-{INITIAL_TAIL_BYTES}" if self.offset is None else f"bytes={self.offset}-"
        )
        async with session.get(
            f"{self.base_url}{LOG_PATH}", auth=self.auth, headers={"Range": range_header}
        ) as resp:
            start, total = _parse_content_range(resp.headers.get("Content-Range"))
            if resp.status == 416:
                # Nothing new, or the file was rotated and is now shorter than our offset.
                if total is not None and self.offset is not None and total < self.offset:
                    _LOGGER.debug("DLM log rotated (size %s < offset %s)", total, self.offset)
                    self.offset, self._partial = None, b""
                return self.latest
            if resp.status == 206:
                body = await _read_up_to(resp, MAX_READ_BYTES)
                start = start or 0
            elif resp.status == 200:
                # Server ignored Range and sent the whole file.
                full = await resp.read()
                if self.offset is not None and self.offset <= len(full):
                    start = self.offset
                else:
                    self.offset, self._partial = None, b""
                    start = max(0, len(full) - INITIAL_TAIL_BYTES)
                body = full[start:]
            else:
                _LOGGER.debug("DLM log fetch HTTP %s", resp.status)
                return self.latest

        resync = self.offset is None
        if len(body) > MAX_READ_BYTES:
            # Far behind (e.g. HA was paused): skip to the newest MAX_READ_BYTES.
            start += len(body) - MAX_READ_BYTES
            body = body[-MAX_READ_BYTES:]
            resync = True
        self.offset = start + len(body)

        if resync:
            # We started mid-line; drop up to the first newline.
            nl = body.find(b"\n")
            body = body[nl + 1:] if nl >= 0 else b""
            self._partial = b""

        data = self._partial + body
        last_nl = data.rfind(b"\n")
        if last_nl < 0:
            self._partial = data
            return self.latest
        self._partial = data[last_nl + 1:]

        for raw_line in data[: last_nl + 1].splitlines():
            reading = parse_dlm_line(raw_line.decode("utf-8", errors="replace"))
            if reading is None:
                continue
            if self.latest is not None and reading.timestamp < self.latest.timestamp:
                continue
            if self.latest is not None and reading.filtered != self.latest.filtered:
                self.changes += 1
            self.latest = reading
        return self.latest
