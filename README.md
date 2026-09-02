# Smart Shade Awning

Home Assistant integration for retractable awnings on a **Spettmann Smart-Shade
RF hub** (Desktop Hub / Mini Hub), using the same cloud the t2Fi family of apps
uses — Marygrove Pro, Smart Shade PRO, Liberty, SunPro and others.

Unofficial. Not affiliated with any manufacturer. See [Disclaimer](#disclaimer).

<a href="https://www.buymeacoffee.com/BrianDoherty"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy me a coffee" height="50" width="178"></a>

---

## ⚠️ Read this before automating

**An awning is motorised outdoor equipment, and this lets software open it while
nobody is watching.**

- **Home Assistant does not know where your awning actually is.** The hub has no
  position sensing. Open/closed is inferred from the last command sent through
  the cloud, so a press of the handheld remote or a wind-sensor retract is
  invisible. HA can say "closed" while the awning is out.
- **This is not a safety system.** It cannot detect wind, rain, snow, ice,
  obstructions, people or pets. It will happily extend an awning into a storm.
- **Leave your wind sensor in place.** It protects the awning by talking
  straight to the receiver, with no dependency on Home Assistant. Nothing here
  replaces it.
- **Unattended *opening* is the risky part.** Closing on a schedule is low risk;
  opening on a schedule means extending in weather nobody has checked.
- **Cloud commands can fail silently.** A "close" you issued may never arrive.

Awnings can be destroyed by wind in seconds and can pull mounting hardware out
of a wall. Verify any automation with the awning in view before trusting it.

## Does it work with my awning?

Confirmed on a **Marygrove awning + Spettmann Smart-Shade `MNH-` Mini Hub**.

Eight t2Fi apps are wired up, and you pick yours at setup. Each is labelled with
how far it has actually been verified:

| Status | Apps |
| --- | --- |
| ✅ **Confirmed** — driven end to end | Marygrove Pro |
| ➖ Shares Marygrove's exact credentials; sign-in should work, hardware untested | Smart Shade PRO, The Awning Company, SunPro |
| ⛔ Untested — never run against anything | Liberty Smart Shade, MacDonald Awning, Acacia, Exclusive Awnings |

Your credentials are only ever sent to the login system for the app you choose.

**Not supported:** Marygrove's newer Bluetooth-only awnings (no cloud hub), and
Lippert Solera. Full detail in [docs/BRANDS.md](docs/BRANDS.md).

## Installation

Requires Home Assistant **2024.12** or newer.

### Via HACS (recommended)

This isn't in the HACS default store yet, so add it as a custom repository —
it's a one-time paste:

1. Open **HACS** → **Integrations**
2. Click the **⋮** menu (top right) → **Custom repositories**
3. Repository: `https://github.com/brianDoherty/ha-smartshade`
   Category: **Integration** → **Add**
4. Close the dialog, search HACS for **Smart Shade Awning**, and click
   **Download**
5. **Restart Home Assistant**

### Manually

Copy the `custom_components/smartshade/` folder from this repo into your Home
Assistant `config/custom_components/` directory, so you end up with
`config/custom_components/smartshade/`, then restart Home Assistant.

### Then set it up

**Settings → Devices & Services → Add Integration → Smart Shade Awning**

Choose **Set up my awning**, pick the app you sign into on your phone, and use
that account's email and password. If sign-in fails, choose **Compatibility
report** instead — see [Something not working?](#something-not-working).

## Entities

Each hub becomes one device:

| Entity | Type | Notes |
| --- | --- | --- |
| Awning | `cover` | Open / Close / Stop |
| Light | `button` | The remote's LIGHT command |
| Last cloud command | `sensor` | Diagnostic — `open` / `close` / `stop` / `light` |

Plus a **Debug logging** switch on a *Smart Shade account* device.

Only RF hubs become devices. Handheld remotes, wind sensors and other t2Fi
products on the same account are filtered out by serial prefix — they would
otherwise appear as awnings with buttons that do nothing.

## Known limitation: state can be stale

**This is the thing to understand before you rely on it.** The hub is a one-way
RF transmitter with no position feedback. Open/closed is inferred from the last
command recorded in the cloud, which means it is:

- **accurate** for commands sent from Home Assistant or the official app
- **blind** to the handheld remote, which talks straight to the receiver
- **blind** to wind-sensor auto-retract, which happens at the receiver too

After either of those, HA keeps showing the previous state until the next cloud
command. The cover is marked `assumed_state`, so the UI shows explicit
Open/Close/Stop buttons rather than a toggle that claims to know better.

There is no wind telemetry in the cloud API at all — the sensor only exposes its
own sensitivity setting — so this cannot be worked around in software. A wired
contact sensor on the awning would fix it.

## Something not working?

Setup writes a **compatibility report** containing no email, password, token,
nickname, location or full serial number — safe to paste into an issue. It works
even when sign-in fails, which is when HA's built-in diagnostics can't help.

**Add Integration → Smart Shade Awning → Compatibility report.**

See [docs/DEBUGGING.md](docs/DEBUGGING.md) for what's in it, the Debug logging
switch, and why you should not paste raw component debug logs.

## Help wanted

**Only Marygrove is confirmed.** If you own any other brand above, you can
change that without writing any code:

1. Install it and pick your brand — all eight are already wired up.
2. [Open an issue](https://github.com/brianDoherty/ha-smartshade/issues) with
   what happened, ideally with a compatibility report attached.
3. Whatever the log shows gets fixed — usually an `AppName` or a request shape.

**A report that it doesn't work is as useful as one that does.** Same goes for
unusual hubs: this was built against an `MNH-` Mini Hub, and `RFH-`, `RFT-`,
`TRH-` and `MNL-` are recognised in code but never exercised.

## Disclaimer

**Unofficial, unsupported, community software. Not a product.**

**No affiliation.** Not affiliated with, endorsed by or supported by t2Fi LLC,
Spettmann, Marygrove, Girard, Lippert, Liberty, Acacia, MacDonald Awning,
Exclusive Awnings, SunPro, The Awning Company, or any other manufacturer,
distributor or installer. All trademarks are the property of their respective
owners and are used only to identify compatibility.

**No warranty, no liability.** Provided "as is" — see [LICENSE](LICENSE). To the
fullest extent permitted by law, the authors accept no liability for any claim
or damages, including property damage, damage to your awning, hub or building,
personal injury, or economic loss, arising from this software or its use,
whether the awning was attended or unattended.

**You are responsible for how you use it** — the automations you write and their
physical consequences, whether this is compatible with your manufacturer's terms
of service, and any effect on your warranty or insurance.

**Undocumented API.** This talks to a private cloud API reverse-engineered from
a publicly distributed Android app for interoperability. Nothing about it is
documented, guaranteed or stable, and it may break at any time.

**Credentials.** The Cognito client identifiers in `const.py` come from publicly
distributed app packages and are shipped to every user of those apps. They are
not anyone's private secret. Your own credentials stay in your HA config and go
only to the app vendor's servers.

If you do not accept all of the above, do not install this.

*Not legal advice — a good-faith plain-language notice, not a lawyer-drafted
document.*

## License

MIT — see [LICENSE](LICENSE).
