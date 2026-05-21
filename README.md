# Nimbus Relay

Nimbus Relay is the SDR ingestion and decoding service for the Nimbus Home Assistant integration.

It receives NOAA Weather Radio broadcasts using an RTL-SDR device, decodes SAME/EAS headers using `multimon-ng`, streams live MP3 audio over HTTP, and publishes normalized alert events to MQTT for Home Assistant.

---

# Features

- RTL-SDR NOAA Weather Radio receiver
- SAME/EAS decoding
- MQTT publishing
- Live MP3 audio streaming
- Automatic pipeline restart/recovery
- systemd support

---

# Architecture

```text
RTL-SDR
   ↓
rtl_fm
   ↓
Nimbus Relay
   ├── multimon-ng SAME decoding
   ├── MQTT publishing
   └── MP3 HTTP audio stream
           ↓
      Home Assistant Nimbus
```

---

# MQTT Topics

Default topic root:

```text
nimbus
```

Topics published:

| Topic | Description |
|---|---|
| `nimbus/alert/same` | SAME/EAS alert payload |
| `nimbus/alert/eom` | End-of-message event |
| `nimbus/audio/url` | Live MP3 stream URL |
| `nimbus/status` | Relay runtime status |
| `nimbus/relay/health` | Health/status telemetry |

---

# Example SAME Payload

```json
{
  "event_code": "TOR",
  "org": "WXR",
  "counties": ["048113"],
  "wfo": "KOUN/NWS",
  "valid_seconds": 3600,
  "issue_utc": "2026-05-21T02:00:00+00:00",
  "issue_expiry_utc": "2026-05-21T03:00:00+00:00",
  "true_remaining_secs": 3600,
  "received_utc": "2026-05-21T02:00:00+00:00",
  "raw": "ZCZC-WXR-TOR-048113+0100-1410200-KOUN/NWS-"
}
```

---

# Requirements

Hardware:

- RTL-SDR USB dongle
- NOAA Weather Radio reception

Software:

- Linux (Debian/Raspberry Pi OS recommended)
- Python 3.12+
- rtl-sdr
- ffmpeg
- multimon-ng

---

# Installation

Clone the repository:

```bash
git clone https://github.com/tannerprice/nimbus-relay.git
cd nimbus-relay
```

Install everything:

```bash
make install
```

This will:

- install system packages
- create the `nimbus` service user
- install Python dependencies
- create `/opt/nimbus-relay`
- install a systemd service
- create the default config

---

# Configuration

Edit:

```text
/opt/nimbus-relay/config.env
```

Example:

```env
MQTT_HOST=homeassistant.local
MQTT_PORT=1883
MQTT_USER=sdr_mqtt
MQTT_PASS=password

MQTT_TOPIC_ROOT=nimbus

SDR_DEVICE_INDEX=0
SDR_FREQUENCY=162.550M
SDR_SAMPLE_RATE=32000
SDR_GAIN=28.0

SAME_SAMPLE_RATE=22050

AUDIO_STREAM_HOST=0.0.0.0
AUDIO_STREAM_PORT=8765
AUDIO_PUBLIC_HOST=

LOG_LEVEL=INFO
```

---

# Start the Service

```bash
sudo make restart
```

Check status:

```bash
make status
```

View logs:

```bash
make logs
```

---

# SDR Testing

Verify the RTL-SDR is visible:

```bash
rtl_test
```

Example:

```text
Found 1 device(s):
  0: Nooelec, NESDR SMArt v5
```

Verify the service user can access the SDR:

```bash
sudo -u nimbus rtl_test
```

---

# Audio Stream

Nimbus Relay exposes a live MP3 stream:

```text
http://PI_IP:8765/nwr.mp3
```

Example:

```text
http://192.168.1.50:8765/nwr.mp3
```

This URL is also published to MQTT:

```text
nimbus/audio/url
```

---

# Testing MQTT

Install mosquitto clients:

```bash
# Debian
sudo apt install mosquitto-clients

#macOS
brew install mosquitto
```

Watch topics:

```bash
mosquitto_sub -h localhost -t 'nimbus/#' -v
```

---

# Running Manually

Create a virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -e .
```

Run:

```bash
NIMBUS_RELAY_CONFIG=./config.env python -m nimbus_relay.main
```

---

# Repository Layout

```text
nimbus-relay/
├── Makefile
├── README.md
├── pyproject.toml
├── config.env.example
├── nimbus_relay/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── mqtt_client.py
│   ├── pipeline.py
│   ├── audio_server.py
│   └── same.py
```

---

# Makefile Commands

| Command | Description |
|---|---|
| `make install` | Full installation |
| `make restart` | Restart service |
| `make stop` | Stop service |
| `make status` | Show service status |
| `make logs` | Follow logs |
| `make uninstall` | Remove everything |

---

# systemd Service

Nimbus Relay installs:

```text
/etc/systemd/system/nimbus-relay.service
```

Enable at boot:

```bash
sudo systemctl enable nimbus-relay
```

---

# Troubleshooting

## SDR Permission Errors

If you see:

```text
usb_claim_interface error -6
```

Add the service user to SDR-related groups:

```bash
sudo usermod -aG plugdev,audio,dialout nimbus
```

Then reboot.

---

## Device Busy

If another SDR app is running:

```bash
sudo systemctl stop dump1090-fa
sudo systemctl stop rtl_tcp
```

---

## No Audio

Test manually:

```bash
rtl_fm -f 162.550M -M fm -s 32000 -g 28 -
```

---

# Future Plans

- CAP/IPAWS support
- Warning polygon support
- Audio clipping/archive
- Native alert text generation
- Geo filtering

---

# License

MIT License

---

# Disclaimer

Nimbus Relay is not affiliated with NOAA, NWS, FEMA, or IPAWS.

Always rely on official emergency alerting systems for life safety information.
