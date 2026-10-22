from custom_components.garo_entity_balance_meter.dlm import parse_dlm_line, _parse_content_range


def test_parse_dlm_line():
    r = parse_dlm_line("2026-10-22T06:57:26.027+00:00 dlmcontrol:391 INFO GaroCS-44111AAA46980: "
                       "DLM limits: raw=(  13,  15,  13), filtered=(  11,  13,  11)")
    assert r.charger == "GaroCS-44111AAA46980"
    assert r.raw == (13, 15, 13) and r.filtered == (11, 13, 11)
    assert r.timestamp.tzinfo is not None


def test_parse_ignores_other_lines():
    assert parse_dlm_line("2026-10-22T06:57:28.996+00:00 http_server:78 INFO HTTP: GET /status") is None
    assert parse_dlm_line("garbage") is None
    assert parse_dlm_line("") is None


def test_negative_limits():
    r = parse_dlm_line("2026-10-22T06:57:26+00:00 dlmcontrol:391 INFO X: DLM limits: raw=( -2, 1, 13), filtered=( 0, 4, 13)")
    assert r.raw == (-2, 1, 13)


def test_content_range():
    assert _parse_content_range("bytes 100-199/1000") == (100, 1000)
    assert _parse_content_range("bytes */1000") == (None, 1000)
    assert _parse_content_range(None) == (None, None)


async def test_follower_incremental_and_rotation(hass, aioclient_mock):
    import aiohttp
    from custom_components.garo_entity_balance_meter.dlm import DlmLogFollower

    line = lambda ts, f: (f"{ts} dlmcontrol:1 INFO CS: DLM limits: raw=(1,1,1), filtered=({f},{f},{f})\n").encode()
    first = b"half a line\n" + line("2026-10-22T10:00:00+00:00", 10)
    url = "https://h/log/garoevse.log"

    session = aioclient_mock.create_session(hass.loop)
    try:
        f = DlmLogFollower("https://h", aiohttp.BasicAuth("u", "p"))

        aioclient_mock.get(url, content=first, status=206,
                           headers={"Content-Range": f"bytes 0-{len(first) - 1}/{len(first)}"})
        assert (await f.poll(session)).filtered == (10, 10, 10)
        assert f.offset == len(first)

        # Appended data, the last line still being written (no newline yet).
        more = line("2026-10-22T10:00:10+00:00", 8) + b"2026-10-22T10:00:20+00:00 dlmcontrol:1 INFO CS: DLM li"
        aioclient_mock.clear_requests(); aioclient_mock._mocks.clear()
        aioclient_mock.get(url, content=more, status=206,
                           headers={"Content-Range": f"bytes {len(first)}-{len(first) + len(more) - 1}/{len(first) + len(more)}"})
        assert (await f.poll(session)).filtered == (8, 8, 8)
        assert f.changes == 1

        # Rotation: new file is shorter than our offset -> 416, then re-tail.
        aioclient_mock.clear_requests(); aioclient_mock._mocks.clear()
        aioclient_mock.get(url, status=416, headers={"Content-Range": "bytes */20"})
        await f.poll(session)
        assert f.offset is None
        fresh = line("2026-10-22T10:01:00+00:00", 6)
        aioclient_mock.clear_requests(); aioclient_mock._mocks.clear()
        aioclient_mock.get(url, content=b"x\n" + fresh, status=206,
                           headers={"Content-Range": f"bytes 0-{len(fresh) + 1}/{len(fresh) + 2}"})
        assert (await f.poll(session)).filtered == (6, 6, 6)
    finally:
        await session.close()
