"""Constants for the Smart Shade PRO / t2Fi awning integration.

The AWS identifiers below were extracted from the public Android apps
(com.smartshade_pro, com.marygrovepro, com.liberty_home). The Cognito app-client
ids/secrets are embedded in the distributed APKs and are therefore public
*client* identifiers, not user secrets.
"""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "smartshade"

AWS_REGION = "us-east-1"


@dataclass(frozen=True)
class Brand:
    """One t2Fi white-label app: its Cognito pool and its REST surface.

    t2Fi ships several branded apps over one shared backend (the `girardiot`
    Amplify project, one IoT endpoint, one S3 bucket), but they do NOT all share
    a Cognito user pool -- and the pool a brand sits in determines which API
    Gateway it talks to and what shape the requests take. In the app this is the
    `CloudRepositoryFunctions.newUserPool` flag: false selects the legacy
    gateway (GET reads, GrillNumber as a query parameter), true selects the
    newer one (POST everything, GrillNumber in the JSON body).
    """

    key: str
    name: str
    pool_id: str
    client_id: str
    client_secret: str
    api_base: str
    new_api: bool
    # The AppName this app sends on the newer gateway's get-grill-list, which
    # takes {"AppName": ...} rather than a GrillNumber. Taken from the app's
    # non-empty `app_name_upload` string, else its `app_name`. None on the
    # legacy gateway, which does not take an AppName at all.
    app_name: str | None = None
    # Two separate claims, which an earlier version wrongly collapsed into one:
    #
    #   credentials_confirmed -- this Cognito pool + client pair has been proven
    #       to authenticate a real account and return its devices. It is a
    #       property of the POOL, so it is true for every app sharing it.
    #   hardware_confirmed -- an awning of THIS brand has actually been driven
    #       end to end. Only ever true where someone owns the hardware.
    #
    # Shared credentials make the first a strong inference for sibling apps.
    # They say nothing about the second.
    credentials_confirmed: bool = False
    hardware_confirmed: bool = False

    @property
    def status(self) -> str:
        """Short, honest label for the config flow and reports."""
        if self.hardware_confirmed:
            return "confirmed"
        if self.credentials_confirmed:
            return "shares a confirmed login, untested hardware"
        return "untested"

    @property
    def pool_name(self) -> str:
        """The part of the pool id after the region, used in the SRP exchange."""
        return self.pool_id.split("_", 1)[1]

    @property
    def idp_url(self) -> str:
        return f"https://cognito-idp.{AWS_REGION}.amazonaws.com/"


# Legacy gateway: reads are GET with GrillNumber as a query parameter.
_HOST_LEGACY = "https://gxlvgoouw8.execute-api.us-east-1.amazonaws.com/"
# Newer gateway: everything is POST with GrillNumber in the JSON body.
_HOST_NEW = "https://327ayp4dud.execute-api.us-east-1.amazonaws.com/"

# The two credential sets, shared verbatim by the apps in each group. Every
# value here is read from the corresponding APK's amplifyconfiguration.json.
_POOL_A = {
    "pool_id": "us-east-1_xCzWPPECR",
    "client_id": "5i2jru21l4a85mcjecqeva95us",
    "client_secret": "112hrdv4ociam8vd71rk9dai5f2eedhdbnug932r8rr1g6mj3sm2",
    "api_base": _HOST_LEGACY,
    "new_api": False,
}
_POOL_B = {
    "pool_id": "us-east-1_8oziOkCAf",
    "client_id": "2dnljf87cm6sfsf3vbss2sjruo",
    "client_secret": "mk1iu21hr3n3qkr208v9mu6c0uuvlp9664u2h21r8je07g3i7lj",
    "api_base": _HOST_NEW,
    "new_api": True,
}

# Keyed by the app the user signs into, because that is the question they can
# actually answer -- it is the icon on their phone. The user picks; we never
# guess, and credentials are only ever sent to the one pool they chose.
BRANDS: dict[str, Brand] = {
    # Confirmed end to end: a Marygrove awning on a Spettmann Smart-Shade
    # MNH- Mini Hub. Note the *hub* is Spettmann and the *awning* is Marygrove,
    # and com.smartshade_pro / com.marygrovepro ship byte-identical Cognito
    # config -- so a successful login proves the pool, never which app.
    "marygrove": Brand(
        key="marygrove",
        name="Marygrove Pro",
        credentials_confirmed=True,
        hardware_confirmed=True,
        **_POOL_A,
    ),
    "smartshade": Brand(
        key="smartshade",
        name="Smart Shade PRO",
        credentials_confirmed=True,
        **_POOL_A,
    ),
    "awning_company": Brand(
        key="awning_company",
        name="The Awning Company",
        credentials_confirmed=True,
        **_POOL_A,
    ),
    "sunpro": Brand(
        key="sunpro", name="SunPro", credentials_confirmed=True, **_POOL_A
    ),
    "liberty": Brand(
        key="liberty", name="Liberty Smart Shade", app_name="liberty", **_POOL_B
    ),
    "macdonald": Brand(
        key="macdonald", name="MacDonald Awning", app_name="macdonald", **_POOL_B
    ),
    "acacia": Brand(key="acacia", name="Acacia", app_name="Acacia", **_POOL_B),
    "exclusive_awnings": Brand(
        key="exclusive_awnings",
        name="Exclusive Awnings",
        app_name="Exclusive Awnings",
        **_POOL_B,
    ),
}

CONF_APP_NAME = "app_name"

# Pre-selected in the config flow: the only brand confirmed on real hardware.
# Also the fallback for entries created before the brand field existed -- those
# used these same Pool A credentials, so the mapping is exact.
DEFAULT_BRAND = "marygrove"

# --- REST endpoints (same paths on both gateways, different verbs/param style) ---
EP_LIST = "get-grill-list"
EP_STATE = "get-state-w-auth"
EP_COMMAND = "send-command-w-auth"

# --- RF action codes (from RFHRemoteControlViewModel) ---
ACTION_OPEN = 4
ACTION_CLOSE = 2
ACTION_STOP = 3
ACTION_LIGHT = 5

# Human-readable names for the action codes, used by the "last cloud command"
# sensor and the cover's state attribute.
ACTION_NAMES = {
    ACTION_CLOSE: "close",
    ACTION_STOP: "stop",
    ACTION_OPEN: "open",
    ACTION_LIGHT: "light",
}

# Command key format:  "<remoteType>:<action>:<remoteNumber>:<channel><receiverModel>"
CMD_VALUE = 0.2

# Defaults for the paired-remote descriptor. Refined per-hub from the get-state
# reported shadow once we see a live response; overridable via options.
DEFAULT_REMOTE_TYPE = 1
DEFAULT_REMOTE_NUMBER = 1
DEFAULT_CHANNEL = 0  # observed in live shadow: C = "1:4:1:0"
DEFAULT_RECEIVER_MODEL = ""  # live shadow shows no suffix

CONF_REMOTE_TYPE = "remote_type"
CONF_REMOTE_NUMBER = "remote_number"
CONF_CHANNEL = "channel"
CONF_RECEIVER_MODEL = "receiver_model"
CONF_REFRESH_TOKEN = "refresh_token"
# The pool's real username (the cognito:username claim), which differs from the
# email alias used to sign in. REFRESH_TOKEN_AUTH validates SECRET_HASH against
# it, so it must survive a restart or the stored refresh token is unusable.
CONF_POOL_USERNAME = "pool_username"
CONF_BRAND = "brand"

DEFAULT_SCAN_INTERVAL = 60  # seconds


# --- Device classification by serial prefix ---
# The app types every device in get-grill-list by a regex on its serial
# (com.iflame_pro.Device.Device, the `attributes` map). That map is byte-for-
# byte identical in the pool A and pool B apps -- 77 entries, verified by diff --
# so one classification serves every brand.
#
# Only the RF hubs below can be sent awning commands.
HUB_SERIAL_PREFIXES = (
    "RFH-",  # RF SMART HUB
    "MNH-",  # RF MINI HUB
    "RFT-",  # Smart RF Hub
    "TRH-",  # Touchscreen HUB
    "MNL-",  # Mini Hub Pro
)

# Every other prefix the app recognises, derived mechanically from that same map
# rather than picked by hand. Two kinds of device live here and both must be
# skipped:
#
#   - RF-only accessories (handheld remotes, wind/ultrasonic sensors, receiver
#     registrations). These have no device shadow and answer 400.
#   - Other t2Fi products that DO have a shadow -- Light Bug (LBS-), RGB IC
#     (MNR-/MNA-), SOLX (SOL-), The One (RFF-/TFF-), WPH, probes, fireplace and
#     grill controllers. These are the dangerous ones: on an account that also
#     owns them, a shadow-fetch fallback would happily turn a light strip into
#     an "awning" with Open/Close buttons that do nothing.
NON_HUB_SERIAL_PREFIXES = (
    "B44-", "BBQ ProbeE ", "BEC-", "BND-", "BRF-", "CSP-", "Demo", "ECF-",
    "EFB-", "EFW-", "FBM-", "FRF-", "GIG-", "GRF-", "HAG-", "HUB-", "HZN-",
    "IGTST", "IRF-", "KRF-", "LBS-", "LRF-", "MKR-", "MKT-", "MNA-", "MNR-",
    "MOD-", "MPS-", "MRF", "MRN-", "MRT-", "MSB-", "MUS-", "NRF-", "PBA-",
    "PFA-", "PFB-", "PFR-", "RFB-", "RFF-", "RFP-", "RFS-", "S23-", "S42-",
    "S44-", "SH253", "SKB-", "SOL-", "SRF-", "SSN-", "SSR-", "SSV-", "STR-",
    "STS-", "TFF-", "TRF-", "TST-", "UML-", "UNM", "UNS-", "USL-", "WB2-",
    "WPH-", "WRH-", "WST-", "iGloo SMT-",
)
