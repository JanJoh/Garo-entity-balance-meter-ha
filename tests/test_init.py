from datetime import timedelta

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.garo_entity_balance_meter.const import DOMAIN

HOST = "192.0.2.10"
BASE = f"https://{HOST}"
METER = [{"sampledValue": [
    {"measurand": "Current.Import", "phase": "L1", "value": "3.2"},
    {"measurand": "Power.Active.Import", "value": "1565"},
    {"measurand": "Energy.Active.Import.Register", "value": "100062083"},
]}]


def _log_line(ts, f, r=(13, 15, 13)):
    return (f"{ts} dlmcontrol:391 INFO GaroCS-1: DLM limits: raw=({r[0]:>4},{r[1]:>4},{r[2]:>4}), "
            f"filtered=({f[0]:>4},{f[1]:>4},{f[2]:>4})\n")


def _mock_device(aioclient_mock, log: bytes):
    aioclient_mock.get(f"{BASE}/status/energy-meter", json=METER)
    for p in ("/status/temperatures", "/config/firmware-version", "/config/device-id", "/config/unit-id",
              "/netconf/network-interface", "/netconf/connection-status", "/netconf/csms-connection-status"):
        aioclient_mock.get(f"{BASE}{p}", json={})
    aioclient_mock.get(f"{BASE}/log/garoevse.log", content=log, status=206,
                       headers={"Content-Range": f"bytes 0-{len(log) - 1}/{len(log)}"})


async def test_migration_moves_credentials_out_of_options(hass: HomeAssistant, aioclient_mock):
    now = dt_util.utcnow().isoformat()
    _mock_device(aioclient_mock, b"partial line from before\n" + _log_line(now, (11, 13, 9)).encode())
    entry = MockConfigEntry(
        domain=DOMAIN, version=1, minor_version=1, unique_id=HOST,
        data={"host": HOST, "username": "u", "password": "p"},
        # 1.1.x options flow copied credentials into options:
        options={"host": HOST, "username": "u", "password": "p", "scan_interval": 5, "slow_scan_interval": 120},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 3
    assert not {"host", "username", "password"} & set(entry.options)
    assert entry.data["password"] == "p"
    assert entry.options["scan_interval"] == 5

    assert hass.states.get("sensor.entity_balance_current_l1").state == "3.2"
    assert hass.states.get("sensor.entity_balance_dlm_limit_l1").state == "11"
    assert hass.states.get("sensor.entity_balance_dlm_limit_l3").state == "9"
    lowest = hass.states.get("sensor.entity_balance_dlm_limit_lowest")
    assert lowest.state == "9"
    assert lowest.attributes["limiting_phase"] == "L3"
    assert hass.states.get("sensor.entity_balance_dlm_limit_l2").attributes["raw"] == 15


async def test_dlm_goes_unavailable_when_stale(hass: HomeAssistant, aioclient_mock):
    old = (dt_util.utcnow() - timedelta(minutes=10)).isoformat()
    _mock_device(aioclient_mock, b"x\n" + _log_line(old, (11, 13, 9)).encode())
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.entity_balance_dlm_limit_l1").state == "unavailable"
    assert hass.states.get("sensor.entity_balance_current_l1").state == "3.2"


async def test_options_flow_never_stores_credentials(hass: HomeAssistant, aioclient_mock):
    _mock_device(aioclient_mock, b"")
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 10, "slow_scan_interval": 60, "enable_dlm": False})
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.options == {"scan_interval": 10, "slow_scan_interval": 60, "enable_dlm": False,
                             "ignore_tls_errors": True, "use_http": False}
    assert hass.states.get("sensor.entity_balance_dlm_limit_l1") is None


async def test_diagnostics_redacts(hass: HomeAssistant, aioclient_mock):
    from custom_components.garo_entity_balance_meter.diagnostics import async_get_config_entry_diagnostics
    _mock_device(aioclient_mock, b"")
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["password"] == "**REDACTED**"
    assert diag["entry"]["data"]["username"] == "**REDACTED**"


async def test_reconfigure_updates_data_only(hass: HomeAssistant, aioclient_mock):
    _mock_device(aioclient_mock, b"")
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "old"},
                            options={"scan_interval": 5, "slow_scan_interval": 120})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": HOST, "username": "u", "password": "new"})
    await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "new"
    assert "password" not in entry.options


def _reauth_flows(hass):
    return [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == SOURCE_REAUTH]


async def test_unique_ids_migrated_to_entry_scope(hass: HomeAssistant, aioclient_mock):
    _mock_device(aioclient_mock, b"")
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create("sensor", DOMAIN, "garo_current_l1",
                                       config_entry=entry, suggested_object_id="current_l1")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 3
    migrated = registry.async_get(old.entity_id)
    assert migrated.unique_id == f"{entry.entry_id}_current_l1"
    assert old.entity_id == "sensor.current_l1"
    assert hass.states.get("sensor.current_l1").state == "3.2"
    assert not [e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
                if e.unique_id.startswith("garo_")]


async def test_two_balancers_both_get_entities(hass: HomeAssistant, aioclient_mock):
    other = "192.0.2.11"
    _mock_device(aioclient_mock, b"")
    aioclient_mock.get(f"https://{other}/status/energy-meter", json=METER)
    for p in ("/status/temperatures", "/config/firmware-version", "/config/device-id", "/config/unit-id",
              "/netconf/network-interface", "/netconf/connection-status", "/netconf/csms-connection-status"):
        aioclient_mock.get(f"https://{other}{p}", json={})
    aioclient_mock.get(f"https://{other}/log/garoevse.log", content=b"", status=206,
                       headers={"Content-Range": "bytes */0"})
    entries = []
    for host in (HOST, other):
        entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=3, unique_id=host,
                                data={"host": host, "username": "u", "password": "p"})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)

    registry = er.async_get(hass)
    counts = [len(er.async_entries_for_config_entry(registry, e.entry_id)) for e in entries]
    assert counts[0] > 0 and counts[0] == counts[1]

    # Turning DLM off on one balancer must not remove the other's DLM entities.
    result = await hass.config_entries.options.async_init(entries[1].entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 15, "slow_scan_interval": 300, "enable_dlm": False})
    await hass.async_block_till_done()
    first = {e.unique_id for e in er.async_entries_for_config_entry(registry, entries[0].entry_id)}
    assert f"{entries[0].entry_id}_dlm_limit_l1" in first
    assert f"{entries[0].entry_id}_firmware_update" in first


async def test_rejected_password_at_setup_starts_reauth(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{BASE}/status/energy-meter", status=401)
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=3, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "wrong"})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(_reauth_flows(hass)) == 1


async def test_rejected_password_while_running_starts_reauth(hass: HomeAssistant, aioclient_mock):
    _mock_device(aioclient_mock, b"")
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=3, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not _reauth_flows(hass)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/status/energy-meter", status=401)
    for p in ("/status/temperatures", "/config/firmware-version", "/config/device-id", "/config/unit-id",
              "/netconf/network-interface", "/netconf/connection-status", "/netconf/csms-connection-status"):
        aioclient_mock.get(f"{BASE}{p}", status=401)
    aioclient_mock.get(f"{BASE}/log/garoevse.log", status=401)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=20))
    await hass.async_block_till_done()
    assert len(_reauth_flows(hass)) == 1

    # Polling stops: no further requests to the device after the failure.
    calls = aioclient_mock.call_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == calls


async def test_reauth_flow_stores_new_password(hass: HomeAssistant, aioclient_mock):
    _mock_device(aioclient_mock, b"")
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=3, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "old"},
                            options={"scan_interval": 5, "slow_scan_interval": 120})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "u", "password": "new"})
    await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"
    assert entry.data["host"] == HOST
    assert "password" not in entry.options
