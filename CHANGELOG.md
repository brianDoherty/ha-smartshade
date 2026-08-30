# Changelog

All notable changes to this integration are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-28

First release. Control a retractable awning through a Spettmann Smart-Shade RF
hub, using the same cloud API as t2Fi's branded apps.

**Confirmed on exactly one setup:** a Marygrove awning on a Spettmann
Smart-Shade Mini Hub, via the Smart Shade PRO app. Seven other brands are wired
up and marked `(unconfirmed)` — see the README.

### Added

- **Cover entity** per hub — Open / Close / Stop, `assumed_state`, device class
  `awning`.
- **Light button** — sends the remote's LIGHT command (RF action 5).
- **Last cloud command sensor** (diagnostic) — `open` / `close` / `stop` /
  `light`, the raw signal the cover's state is inferred from.
- **Debug logging switch** (config, on a *Smart Shade account* service device) —
  while on, every poll writes a redacted payload report to the log. Survives
  restarts; flipping it on triggers an immediate refresh.
- **Brand selector** covering all eight t2Fi awning apps, confirmed ones listed
  first. Credentials are only ever sent to the pool for the app you choose.
- **Compatibility report** in the config flow — runs the sign-in, prints what
  the cloud returned, saves nothing. Works when normal setup fails, which is
  when HA's built-in diagnostics cannot help.
- **Diagnostics platform** for the already-working case.
- **Automatic shape checks** at setup: flags a missing
  `data.state.desired.CMD_LST.CMD_steps`, an RF descriptor that isn't
  `remoteType:action:remoteNumber:channel`, device entries missing
  `GrillNumber`/`Model`, unrecognised serial prefixes, and accounts where every
  device filtered out.
- **Re-authentication flow** for when a stored login stops working.
- **Options flow** to tune the paired-remote descriptor
  (`remoteType:action:remoteNumber:channel` + receiver suffix).

### Supported brands

Three separate claims, kept separate:

| Pool | Apps | Status |
| --- | --- | --- |
| A (`xCzWPPECR`, legacy gateway) | **Marygrove Pro** | ✅ **Confirmed** — driven end to end on a Marygrove awning + Spettmann `MNH-` Mini Hub |
| A | Smart Shade PRO, The Awning Company, SunPro | ➖ Share Marygrove's exact credentials, so sign-in should work; no hardware of these brands tested |
| B (`8oziOkCAf`, newer gateway) | Liberty Smart Shade, MacDonald Awning, Acacia, Exclusive Awnings | ⛔ Untested — credentials have never authenticated anything |

The integration was **built** from the Smart Shade PRO APK (hence the
`smartshade` domain) but **proven** against Marygrove hardware. Those are
different claims; do not read the domain name as a confirmation.

### Notes on the cloud's behaviour

- Cognito usernames are **case-sensitive**. `Bills@…` and `bills@…` are
  different users, and the failure ("User does not exist") gives no hint that
  case is the problem. Sign-in now retries once in lower case and stores
  whichever spelling worked.

### Known limitations

- **State can be stale.** The hub is a one-way RF transmitter with no position
  sensing. Open/closed is inferred from the last command recorded in the cloud
  shadow, so commands from Home Assistant or the official app are tracked, but a
  press of the physical remote or a wind-sensor auto-retract is invisible.
- **No wind telemetry.** The wind sensor's cloud shadow carries only its own
  configuration — sensitivity and firmware — with no live reading and no
  auto-retract event, so there is nothing to expose.
- **Pool B is unverified end to end.** Sign-in and the device list are checked
  at setup, but whether Open/Close physically reaches the awning cannot be
  tested without moving one.
- Paired accessories and other t2Fi products on the same account (remotes, wind
  sensors, Light Bug, RGB controllers, probes, fireplace and grill controllers)
  are filtered out by serial prefix and do not become entities.

### Safety and legal

- Added a **Safety notice** and expanded **Disclaimer** to the README: no
  affiliation with any manufacturer, no warranty, no liability, and explicit
  warnings that Home Assistant cannot see the awning's real position or detect
  wind, and must not be treated as a safety system.
- The setup screen now leads with a short version of the same warning.

### Notes

- Cloud polling at 60-second intervals; the integration is `cloud_polling`.
- Requires Home Assistant 2024.12.0 or newer.
- Unofficial. Not affiliated with t2Fi, Spettmann, Marygrove or Girard.

[0.1.0]: https://github.com/briandoherty/ha-smartshade/releases/tag/v0.1.0
