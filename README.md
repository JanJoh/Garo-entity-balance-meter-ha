# GARO Entity Balance Meter

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![GitHub release](https://img.shields.io/github/v/release/JanJoh/Garo-entity-balance-meter-ha)](https://github.com/JanJoh/Garo-entity-balance-meter-ha/releases)

Home Assistant integration for the GARO Entity Balance dynamic load balancer. Polls the device's local REST API — no cloud, no GARO account required.

> Mostly LLM-generated code. It works, but don't expect miracles.

---

## What it does

Reads grid consumption data from the GARO Entity Balance unit connected to your utility meter's P1 port. Exposes power, energy, and per-phase current and voltage as Home Assistant sensors.

Primary use case: use the **Grid Energy** sensor as a grid consumption source in the HA Energy dashboard — no separate P1 reader hardware needed if you already have the Entity Balance installed.

---

## What it is NOT

This integration talks to the **load balancer**, not to the EV charger. It measures whole-house grid consumption, not charger-specific data. For charger sensors (charging state, CP signal, etc.) see [GARO Entity Charger Meter](https://github.com/JanJoh/Garo-entity-charger-meter-ha).

---

## Requirements

- GARO Entity Balance unit connected to your utility meter's P1 port
- BasicAuth credentials (printed on a sticker on the physical device)
  - Username: `GaroLI-xxxxxxxxx`
  - Password: `xxxx-xxxx-xxxx` — **enter in lowercase**, regardless of what the sticker says

---

## Installation

### HACS (recommended)

1. HACS → **Custom repositories** → add `https://github.com/JanJoh/Garo-entity-balance-meter-ha` as type **Integration**
2. Install **GARO Entity Balance Meter**
3. Restart Home Assistant
4. Settings → Devices & Services → **Add integration** → search for *GARO Balance*

### Manual

Copy `custom_components/garo_entity_balance_meter/` into your HA `config/custom_components/` directory and restart.

---

## Configuration

| Field | Default | Description |
|---|---|---|
| Host | — | IP address of the Entity Balance unit (not the EV charger) |
| Username / Password | — | BasicAuth credentials from the device sticker |
| Fast poll interval | 15 s | How often to read live meter values (power, current, voltage, energy) |
| Slow poll interval | 300 s | How often to fetch diagnostic data (temperatures, firmware, network) |
| Ignore TLS errors | on | Skip certificate validation (recommended for local devices) |
| Use HTTP | off | Use plain HTTP instead of HTTPS |

Intervals and TLS settings can be changed after setup via **Settings → Devices & Services → GARO Entity Balance Meter → Configure**.

---

## Sensors

### Grid metering (fast poll)

| Sensor | Unit | Notes |
|---|---|---|
| Power Consumption | W | Instantaneous grid power |
| Energy Total | Wh | Total imported energy — use this in the HA Energy dashboard |
| Current L1 / L2 / L3 | A | Per-phase current |
| Voltage L1 / L2 / L3 | V | Per-phase voltage |

### Diagnostics (slow poll, disabled by default)

| Sensor | Notes |
|---|---|
| CPU / Board Temperature | °C |
| Firmware Version | |
| Device ID | Serial number |
| Unit ID | Hardware unit ID containing MAC address |
| Network Interface | Active interface (`Ethernet`, `wlan0`, etc.) |
| IP Address | |
| Wi-Fi SSID / Signal | Only populated when connected via Wi-Fi |
| CSMS Connection | Cloud/OCPP backend connection status |

Enable diagnostic sensors individually under Settings → Devices → GARO Entity Balance → the sensor → Enable.
