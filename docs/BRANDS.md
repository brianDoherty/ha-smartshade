# Brands, pools and the protocol

How the t2Fi platform is put together, which apps share which credentials,
and why the two API gateways behave the way they do. You do not need any of
this to use the integration — see the [README](../README.md) for that.

t2Fi white-labels one codebase across eight awning brands, split across **two
Cognito user pools**. The pool decides which API gateway an account uses and
what shape its requests take.

**You pick your app at setup.** The dropdown lists all eight, each labelled with
how far it has actually been verified. Your credentials are only ever sent to
the pool for the app you chose — the integration never tries the other one.

## What "confirmed" means here

Three different claims get muddled in projects like this, so they're kept
separate:

| Label | Means |
| --- | --- |
| **confirmed** | An awning of this brand has been driven end to end — sign-in, device list, and Open/Close actually moving it. |
| **shares a confirmed login** | Byte-identical Cognito credentials to a confirmed brand, so signing in should work. Nobody has moved one of these awnings. |
| **untested** | Never run against anything. |

A successful login proves the **pool**, never the app: `com.smartshade_pro` and
`com.marygrovepro` ship identical credentials, so auth cannot tell them apart.

## Pool A — credentials confirmed

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

## Pool B — untested

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

## Not on this platform

| App | Package | Why |
| --- | --- | --- |
| Lippert Solera | `com.lippert_solera` | No Cognito pool in the APK — different architecture |
| Marygrove installer | `com.mginstall` | Same |
| Girard Guard | *(iOS only)* | Predates this platform; no Android build |

t2Fi also ships non-awning apps on this codebase — iFlame and iFlame Pro
(fireplaces), Diamond Grills and Pro Smoker (grills, which is why the API calls
every device a `GrillNumber`), Eurofase, Prism Hardscapes, The Outdoor Plus,
Furrion. Out of scope.

## Do the entities work the same on both gateways?

Yes. The two gateways differ **only in how requests are addressed** — verb, and
whether `GrillNumber` rides in the query string or the JSON body. The responses
are identical: both `get-grill-list` variants deserialize to the same
`GrillListJSON` class in the app, and the shadow read and command endpoints
return raw bodies that the app parses through one code path with no branching.
So the cover, the light button, and the last-command sensor need no
gateway-specific handling at all.
