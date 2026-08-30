# Smart Shade Awning — Home Assistant integration

Control a retractable awning from Home Assistant through a **Spettmann
Smart-Shade RF hub** (Desktop Hub / Mini Hub), using the same cloud API as the
[Smart Shade PRO](https://play.google.com/store/apps/details?id=com.smartshade_pro)
and [Marygrove Pro](https://play.google.com/store/apps/details?id=com.marygrovepro)
apps by t2Fi.

> ### Confirmed on Marygrove. Eight brands will *try*.
>
> Eight t2Fi awning brands are wired up. Pick yours from the dropdown at setup
> and sign in with that app's account.
>
> But **only one is confirmed working**: a **Marygrove awning on a Spettmann
> Smart-Shade Mini Hub**, on a Marygrove Pro account. The other seven are
> built from their apps and have never been run against real hardware. If one
> of them is yours, the dropdown says exactly how far it has been verified —
> setup will either work or fail cleanly, and either way
> [I'd love to hear about it](#want-your-brand-supported-lets-collaborate).

> ⚠️ **Motorised outdoor equipment.** Home Assistant cannot see where your
> awning actually is, and cannot detect wind. Please read the
> [Safety notice](#safety-notice--read-this-before-automating) before writing
> any automation.

## Entities

Each hub becomes one device with:

| Entity | Type | Notes |
| --- | --- | --- |
| Awning | `cover` | Open / Close / Stop. `assumed_state` — see below. |
| Light | `button` | Sends the remote's LIGHT command (RF action 5). |
| Last cloud command | `sensor` (diagnostic) | `open` / `close` / `stop` / `light`. |

Plus one account-level entity on a *Smart Shade account* service device:
**Debug logging** (`switch`, config category) — see
[Debugging](#debugging-and-compatibility-reports).

Only RF hubs (`RFH-`, `MNH-`, `RFT-`, `TRH-`, `MNL-`) become devices. Everything
else in your account is filtered out by serial prefix, using the classification
map from the app itself — which is byte-for-byte identical across both brand
pools, so the filter behaves the same for every brand.

That covers two groups. Paired RF accessories — handheld remotes, WindGuard and
ultrasonic sensors, receiver registrations — accept no commands and report no
state, so entities for them would be permanently dead. And other t2Fi products
on the same login — Light Bug, RGB controllers, SOLX, The One, probes, fireplace
and grill controllers — *do* have cloud shadows, so without the filter they
would show up as "awnings" with buttons that go nowhere.

A serial prefix the map doesn't recognise is still tried, so a hub model newer
than this integration works rather than being silently dropped.

## Known limitation: state can be stale

**The hub cannot tell you where the awning actually is.** It is a one-way RF
transmitter with no position sensing. The open/closed state, and the
`Last cloud command` sensor, are both inferred from the last command recorded in
the hub's cloud shadow.

That means state is accurate for commands sent **from Home Assistant or from the
official app**, and blind to everything else:

- Pressing the **physical handheld remote** talks straight to the awning's
  receiver. The hub never hears it, so Home Assistant will not notice.
- A **wind sensor auto-retract** happens at the receiver too, and is likewise
  invisible.

After either of those, Home Assistant will keep showing the previous state until
the next command goes through the cloud. The cover is marked `assumed_state`, so
the UI shows explicit Open/Close/Stop buttons rather than a toggle that claims to
know better. There is no wind telemetry in the cloud API at all — the sensor
only exposes its own sensitivity setting — so this cannot be worked around.

If you need true position or local control, capture the remote's RF with a
Broadlink RM4 Pro instead; that is a different (local, also one-way) trade-off.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → **Custom repositories**
2. Add `https://github.com/briandoherty/ha-smartshade`, category **Integration**
3. Install **Smart Shade Awning**, then restart Home Assistant
4. Settings → Devices & Services → **Add Integration** → *Smart Shade Awning*

### Manual

Copy `custom_components/smartshade/` into your Home Assistant `config/custom_components/`
directory and restart.

## Configuration

Sign in with the email and password you use in your awning's app. There is no
app to pick from the dropdown, listing all eight supported brands. See
[Brands](#brands).

If Open/Close appear to do nothing, the paired-remote descriptor is probably
wrong for your hub. Configure → **Remote settings** lets you adjust it. The hub
expects a key shaped like:

```
<remoteType>:<action>:<remoteNumber>:<channel><receiverModel>
```

Defaults are `1:<action>:1:0` with an empty receiver suffix, which matches a
Mini Hub with a single paired remote on channel 0.

## Brands

t2Fi white-labels one codebase across eight awning brands, split across **two
Cognito user pools**. The pool decides which API gateway an account uses and
what shape its requests take.

**You pick your app at setup.** The dropdown lists all eight, each labelled with
how far it has actually been verified. Your credentials are only ever sent to
the pool for the app you chose — the integration never tries the other one.

### What "confirmed" means here

Three different claims get muddled in projects like this, so they're kept
separate:

| Label | Means |
| --- | --- |
| **confirmed** | An awning of this brand has been driven end to end — sign-in, device list, and Open/Close actually moving it. |
| **shares a confirmed login** | Byte-identical Cognito credentials to a confirmed brand, so signing in should work. Nobody has moved one of these awnings. |
| **untested** | Never run against anything. |

A successful login proves the **pool**, never the app: `com.smartshade_pro` and
`com.marygrovepro` ship identical credentials, so auth cannot tell them apart.

### Pool A — credentials confirmed

`us-east-1_xCzWPPECR`, legacy gateway. All four apps ship identical credentials.

| App | Package | Status |
| --- | --- | --- |
| **Marygrove Pro** | `com.marygrovepro` | ✅ **Confirmed** — a Marygrove awning on a Spettmann Smart-Shade `MNH-` Mini Hub, driven end to end. The cloud reports `AppName: 'Marygrove Pro'` for these devices |
| Smart Shade PRO | `com.smartshade_pro` | ➖ Shares a confirmed login. No Smart Shade PRO hardware has ever been tested |
| The Awning Company | `com.the_awning_company` | ➖ Shares a confirmed login |
| SunPro | `com.sunproapp` | ➖ Shares a confirmed login |

The integration was **built** by reverse-engineering the Smart Shade PRO APK,
which is why the domain is `smartshade` — but the hardware it was **proven**
against is Marygrove on a Spettmann hub. Those are different claims and the
earlier version of this README wrongly merged them.

### Pool B — untested

`us-east-1_8oziOkCAf`, newer gateway (`newUserPool = true`: POST everything,
`GrillNumber` in the JSON body). Shared credentials, but each app sends its own
`AppName` on the device-list call.

| App | Package | `AppName` sent | Status |
| --- | --- | --- | --- |
| Liberty Smart Shade | `com.liberty_home` | `liberty` | ⛔ Untested |
| MacDonald Awning | `com.macdonald_awning` | `macdonald` | ⛔ Untested |
| Acacia | `com.acacia_pro` | `Acacia` | ⛔ Untested |
| Exclusive Awnings | `com.exclusive_awnings` | `Exclusive Awnings` | ⛔ Untested |

⚠️ Nothing in pool B has run against real hardware, and its credentials have
never authenticated anything. Sign-in and the device list are verified at setup,
but whether Open/Close reaches your awning cannot be tested without moving one.

### Not on this platform

| App | Package | Why |
| --- | --- | --- |
| Lippert Solera | `com.lippert_solera` | No Cognito pool in the APK — different architecture |
| Marygrove installer | `com.mginstall` | Same |
| Girard Guard | *(iOS only)* | Predates this platform; no Android build |

t2Fi also ships non-awning apps on this codebase — iFlame and iFlame Pro
(fireplaces), Diamond Grills and Pro Smoker (grills, which is why the API calls
every device a `GrillNumber`), Eurofase, Prism Hardscapes, The Outdoor Plus,
Furrion. Out of scope.

### Do the entities work the same on both gateways?

Yes. The two gateways differ **only in how requests are addressed** — verb, and
whether `GrillNumber` rides in the query string or the JSON body. The responses
are identical: both `get-grill-list` variants deserialize to the same
`GrillListJSON` class in the app, and the shadow read and command endpoints
return raw bodies that the app parses through one code path with no branching.
So the cover, the light button, and the last-command sensor need no
gateway-specific handling at all.

## Debugging and compatibility reports

Three ways to get one, all stripped of anything identifying.

### Authentication is always logged

Every setup writes its auth outcome, unconditionally — one line, once:

```
Smart Shade signed in -- brand=smartshade gateway=https://gxlvgoouw8…/
  style=GET + query parameter AppName=None devices=3 | probe: smartshade:MATCHED, 3 device(s)
```

A **failed** sign-in writes the full report at `WARNING` instead. That one
ignores every preference, because a failed setup creates no config entry — so
there are no diagnostics and no switch to flip, and the log is all you have.

### The Debug logging switch

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

### ⚠️ Don't paste raw component debug logs

Setting `custom_components.smartshade: debug` in your `logger:` config dumps
**raw API responses** — nicknames, coordinates, full serial numbers, the email
on the account. That is what debug logging is for, and it stays that way, but it
is *not* scrubbed.

The compatibility report and the Debug logging switch are the scrubbed paths.
Use those when sharing. If you do paste a raw debug log, read it first.

### Setup failing? Run the report by hand

Settings → Devices & Services → **Add Integration** → *Smart Shade Awning*, then
choose **Compatibility report** instead of *Set up my awning*. It signs in,
prints exactly what the cloud returned, and **saves nothing** — no config entry
is created, so it works precisely when normal setup does not. That is the point:
Home Assistant's built-in diagnostics need a working config entry, and the
accounts we most need to hear about never get one.

The report is also written to the log at warning level, so you can copy it from
Settings → System → Logs if selecting from the dialog is awkward.

### Already set up? Use diagnostics

The integration page's **Download diagnostics** gives the same report as JSON.

### What's in it — and what isn't

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

## Want your brand supported? Let's collaborate

**Only Marygrove is confirmed. Everything above is an educated guess until
someone with the hardware tries it.** If you own any of these awnings, I'd
genuinely like to work with you on it —
[open an issue](https://github.com/briandoherty/ha-smartshade/issues) and say
what you have.

You don't need to write code or know Python. Here's the whole loop:

1. **You** install it and pick your brand from the dropdown — all eight are
   already wired up, so there's nothing to wait for.
2. **You** open an issue with what happened, ideally with a
   [compatibility report](#setup-failing-run-the-report-by-hand) attached.
3. **I** fix whatever the log shows — most likely an `AppName` value or a
   request shape, both of which the debug log spells out.
4. **Your brand moves from "untested" to confirmed.**

A report that something *doesn't* work is just as valuable as one that does. So
is a report about an unusual hub: this was built against an `MNH-` Mini Hub, and
`RFH-`, `RFT-`, `TRH-`, and `MNL-` hubs are all recognised in code but never
exercised.

## Credentials note

`const.py` contains both pools' Cognito client ids and secrets. These are extracted
from the public APKs — they are client identifiers shipped to every user of the
app, not anyone's secret. Your own username and password stay in your Home
Assistant config entry.

## Safety notice — read this before automating

**A retractable awning is motorised outdoor equipment. This integration lets
software open it while nobody is there to see what happens.**

- **Home Assistant does not know where your awning actually is.** The hub has no
  position sensing. Open/closed is inferred from the last command that went
  through the cloud, so a press of the physical remote or a wind-sensor
  auto-retract is invisible. HA can report "closed" while the awning is out.
  See [Known limitation: state can be stale](#known-limitation-state-can-be-stale).
- **Do not treat this as a safety system.** It cannot detect wind, rain, snow
  load, ice, obstructions, people, or pets. It will happily extend an awning
  into a storm.
- **Do not disable or bypass your wind sensor.** It protects the awning by
  talking directly to the receiver, independently of Home Assistant. Nothing
  here replaces it, and this integration cannot see it or read from it.
- **Think hard before automating unattended opening.** Scheduled or
  presence-based opening means the awning may extend with nobody watching, in
  weather nobody has checked. Closing unattended is far lower risk than opening.
- **Cloud commands can silently fail.** The service can be down, the hub can
  drop offline, or a command can be lost. A "close" you issued may never arrive.
- Verify behaviour with the awning in view before trusting any automation.

Awnings can be destroyed by wind in seconds, can injure someone standing under
them, and can pull mounting hardware out of a wall. Manufacturer warranties
commonly exclude damage from third-party or modified controls.

## Disclaimer

**This is an unofficial, unsupported, community project. It is not a product.**

**No affiliation.** Not affiliated with, endorsed by, sponsored by, or supported
by t2Fi LLC, Spettmann, Marygrove, Girard, Lippert, Liberty, Acacia, MacDonald
Awning, Exclusive Awnings, SunPro, The Awning Company, or any other
manufacturer, distributor or installer. All product names, trademarks and
registered trademarks are the property of their respective owners, and are used
here only to identify what this software is compatible with.

**No warranty.** This software is provided "as is", without warranty of any
kind, express or implied, including but not limited to the warranties of
merchantability, fitness for a particular purpose and non-infringement. See
[LICENSE](LICENSE) for the full terms.

**No liability.** To the fullest extent permitted by law, the authors and
contributors accept no liability for any claim, damages or other liability —
including property damage, damage to your awning, hub, or building, personal
injury, lost data, or economic loss — arising from or in connection with this
software or its use, whether the awning was attended or unattended at the time.

**You are responsible for how you use it.** That includes any automation you
write, any command you send, and the physical consequences. You are responsible
for reviewing your awning manufacturer's and app provider's terms of service and
for deciding whether using this software is compatible with them, and for any
effect on your warranty or insurance.

**Undocumented API.** This works by talking to a private cloud API that was
reverse-engineered from a publicly distributed Android app for interoperability.
Nothing about it is documented, guaranteed or stable. It may break, change, or
be withdrawn at any time, without notice and without recourse.

**Credentials.** The Cognito client identifiers in `const.py` are extracted from
publicly distributed app packages and are shipped to every user of those apps.
They are not anyone's private secret. Your own account credentials stay in your
Home Assistant configuration and are sent only to the app vendor's own servers.

If you do not accept all of the above, do not install or use this software.

*Not legal advice — this is a good-faith, plain-language notice, not a
lawyer-drafted document.*

## License

MIT — see [LICENSE](LICENSE).
