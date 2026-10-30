from homeassistant.core import HomeAssistant, State
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache_with_extra_data

from custom_components.garo_entity_balance_meter.const import DOMAIN
from custom_components.garo_entity_balance_meter.firmware import FirmwareState, version_from_location

from .test_init import BASE, HOST, _mock_device

ORDER = ('2026-10-29T20:00:16.121+00:00 ocpp:57 INFO GaroLI-X: < [2,"a","SignedUpdateFirmware",{"requestId":9,'
         '"firmware":{"location":"https://example.com/fw/garo-entity-3.0.12-4.10.3-imx-r5bf98996f.upd",'
         '"retrieveDateTime":"1970-01-01T00:00:01Z","signingCertificate":"c","signature":"s"}}]')


def status(t, s):
    return f'{t} ocpp:76 INFO GaroLI-X: > [2,"b","SignedFirmwareStatusNotification",{{"status":"{s}","requestId":9}}]'


def test_version_from_location():
    assert version_from_location("https://x/garo-entity-3.0.12-4.10.3-imx-r5bf98996f.upd")[:2] == ("4.10.3", "5bf98996f")


async def _setup(hass, aioclient_mock, log_lines, installed="4.2.7"):
    log = ("cut line\n" + "".join(f"{line}\n" for line in log_lines)).encode()
    aioclient_mock.get(f"{BASE}/config/firmware-version", json={"version": installed, "revision": "abc"})
    _mock_device(aioclient_mock, log)
    entry = MockConfigEntry(domain=DOMAIN, version=1, minor_version=2, unique_id=HOST,
                            data={"host": HOST, "username": "u", "password": "p"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    states = hass.states.async_all("update")
    assert len(states) == 1, states
    return states[0]


async def test_update_available(hass: HomeAssistant, aioclient_mock):
    st = await _setup(hass, aioclient_mock, [ORDER, status("2026-10-29T20:01:49+00:00", "SignatureVerified")])
    assert st.state == "on"
    assert (st.attributes["installed_version"], st.attributes["latest_version"]) == ("4.2.7", "4.10.3")
    assert st.attributes["release_summary"] == "Downloaded and verified, waiting to install"
    assert st.attributes["supported_features"] == 4  # PROGRESS only: reported, never installed from HA


async def test_installing_then_installed(hass: HomeAssistant, aioclient_mock):
    st = await _setup(hass, aioclient_mock, [ORDER, status("2026-10-30T08:34:34+00:00", "Installing")])
    assert st.attributes["in_progress"] is True


async def test_installed(hass: HomeAssistant, aioclient_mock):
    st = await _setup(hass, aioclient_mock, [ORDER, status("2026-10-30T08:41:59+00:00", "Installed")], installed="4.10.3")
    assert st.state == "off" and st.attributes["release_summary"] is None


async def test_order_restored_after_restart(hass: HomeAssistant, aioclient_mock):
    saved = FirmwareState()
    saved.feed_line(ORDER, None)
    mock_restore_cache_with_extra_data(hass, [(State("update.entity_balance_firmware", "on"), saved.as_dict())])
    st = await _setup(hass, aioclient_mock, [])
    assert st.entity_id == "update.entity_balance_firmware"
    assert st.state == "on" and st.attributes["release_summary"] == "Ordered"


async def test_removed_when_log_reading_off(hass: HomeAssistant, aioclient_mock):
    await _setup(hass, aioclient_mock, [])
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    hass.config_entries.async_update_entry(entry, options={"enable_dlm": False})
    await hass.async_block_till_done()
    assert not hass.states.async_all("update")
