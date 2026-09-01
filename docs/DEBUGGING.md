# Debugging and compatibility reports

Three ways to get a report, all stripped of anything identifying. Start here
if setup fails, or if you are testing a brand that isn't confirmed yet.

## Authentication is always logged

Every setup writes its auth outcome, unconditionally — one line, once:

```
Smart Shade signed in -- brand=smartshade gateway=https://gxlvgoouw8…/
  style=GET + query parameter AppName=None devices=3 | probe: smartshade:MATCHED, 3 device(s)
```

A **failed** sign-in writes the full report at `WARNING` instead. That one
ignores every preference, because a failed setup creates no config entry — so
there are no diagnostics and no switch to flip, and the log is all you have.

## The Debug logging switch

Payload shapes are the other half, and they're an ongoing question rather than a
one-shot one, so they get a runtime toggle instead: **Debug logging**, on the
*Smart Shade account* device.

While it's on, **every poll** writes a full payload report at `WARNING` — what
devices came back, how each was classified (including the ones filtered out),
and the structure of the hub shadow. Flipping it on triggers an immediate
refresh so you get output straight away rather than waiting for the next poll.

It is noisy on purpose. Turn it on, capture a report, paste it into an issue,
turn it off. The state survives a restart, so leaving it on to catch something
intermittent works.

Setup also checks the shapes it gets against the ones it expects, and if
anything is off it says so at `WARNING` — naming the problem inline and pointing
at this switch — even with debug logging off. It flags:

- the hub shadow has no `data.state.desired.CMD_LST.CMD_steps` (the cover's
  state *and* its command format both come from there)
- the RF descriptor isn't `remoteType:action:remoteNumber:channel`
- a device entry is missing `GrillNumber` or `Model`
- a serial prefix isn't in the app's classification map
- devices came back but every one classified as a non-hub, so no entities

## ⚠️ Don't paste raw component debug logs

Setting `custom_components.smartshade: debug` in your `logger:` config dumps
**raw API responses** — nicknames, coordinates, full serial numbers, the email
on the account. That is what debug logging is for, and it stays that way, but it
is *not* scrubbed.

The compatibility report and the Debug logging switch are the scrubbed paths.
Use those when sharing. If you do paste a raw debug log, read it first.

## Setup failing? Run the report by hand

Settings → Devices & Services → **Add Integration** → *Smart Shade Awning*, then
choose **Compatibility report** instead of *Set up my awning*. It signs in,
prints exactly what the cloud returned, and **saves nothing** — no config entry
is created, so it works precisely when normal setup does not. That is the point:
Home Assistant's built-in diagnostics need a working config entry, and the
accounts we most need to hear about never get one.

The report is also written to the log at warning level, so you can copy it from
Settings → System → Logs if selecting from the dialog is awkward.

## Already set up? Use diagnostics

The integration page's **Download diagnostics** gives the same report as JSON.

## What's in it — and what isn't

It reports *shapes, not values*:

| Included | Redacted |
| --- | --- |
| Which pool authenticated, and which were rejected | Email, password, tokens |
| Gateway URL and request style | Device nicknames |
| `AppName` that worked | Latitude / longitude / state / country |
| Serial **prefixes** (`MNH-********`) and lengths | Full serial numbers |
| `Model` per device, and how each was classified | Wi-Fi SSID |
| The **key names** returned by the API | Every value not on a protocol safelist |
| Shadow structure, incl. the RF descriptor `"1:4:1:0"` | |

Values survive only when the key is on an explicit safelist of protocol
constants (`MODE`, `CID`, `C`, `D`, `Model`, `AppName`, firmware and wind
settings). Anything else — known or unknown — is replaced by its type, so a
field we haven't mapped yet can't leak by accident.
