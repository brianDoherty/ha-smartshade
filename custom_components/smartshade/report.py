"""PII-free compatibility reporting.

Shared by the diagnostics platform and the config flow's compatibility-report
step so the two can never drift apart.

The guiding rule is **report shapes, not values**. What makes an unsupported
brand debuggable is which pool authenticated, which gateway answered, what keys
came back, and how each device was classified -- none of which requires a single
piece of anyone's data. Values are included only for keys on an explicit
safelist of technical fields; everything else is reduced to its type.
"""

from __future__ import annotations

import re
from typing import Any

from .const import HUB_SERIAL_PREFIXES, NON_HUB_SERIAL_PREFIXES

# Keys whose values are inherently technical -- protocol constants, model
# identifiers, RF descriptors. Anything not listed here is reported as a type
# only, which is the safe default for a payload we have not fully mapped.
SAFE_VALUE_KEYS = frozenset(
    {
        "AppName",
        "C",  # RF command descriptor, e.g. "1:4:1:0"
        "CID",
        "D",
        "FW",
        "LastCID",
        "MODE",
        "Model",
        "SchCommand",
        "cid",
        "fw",
        "modelType",
        "otaProgress",
        "vibEnable",
        "vibSense",
        "windLevel",
        "windSensitivity",
    }
)

# Keys that carry a device serial. Serials are not secret, but they identify
# specific hardware, and only the prefix matters for classification.
SERIAL_KEYS = frozenset({"GrillNumber", "linkedMUS", "sensorLinkedHub", "serial"})


# Server error bodies are echoed into the report, and we cannot assume they are
# free of user data -- an API is entitled to quote back whatever it was sent.
# Everything that reaches the report is scrubbed through here first, so the
# "safe to paste" promise holds for text we did not author.
_SCRUBBERS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    # Serials are an uppercase prefix plus a dash; requiring uppercase keeps
    # this off ordinary hyphenated words like "get-grill-list".
    (re.compile(r"\b[A-Z]{2,5}-[A-Za-z0-9]{4,}\b"), "<serial>"),
    (re.compile(r"\b[A-Za-z0-9_-]{24,}\b"), "<token>"),
    (re.compile(r"-?\d{1,3}\.\d{4,}"), "<coord>"),
)


def scrub(text: str | None, limit: int = 300) -> str | None:
    """Strip identifying patterns out of text we did not generate."""
    if not text:
        return text
    for pattern, replacement in _SCRUBBERS:
        text = pattern.sub(replacement, text)
    return text[:limit]


# An error body is written by the server, so no pattern can prove it holds no
# user data -- a free-text nickname matches nothing. Rather than weaken the
# promise the report makes, keep only the part we can vouch for: which endpoint
# failed and with what status. The full body still goes to the debug log for
# anyone who wants to dig, it just does not ride along in a report we tell
# people is safe to paste.
_ERROR_SHAPE = re.compile(r"([\w][\w-]*) HTTP (\d{3})")


def summarize_error(text: str | None) -> str | None:
    """Reduce a server error to its endpoint and status code."""
    if not text:
        return text
    prefix = ""
    if ": " in text:
        head = text.split(": ", 1)[0]
        if head.endswith("Error"):
            prefix = f"{head}: "
    match = _ERROR_SHAPE.search(text)
    if match:
        return f"{prefix}{match.group(1)} HTTP {match.group(2)}"
    # Unrecognised shape (a Cognito exception name, say). Scrub hard and keep
    # it short -- enough to identify, too little to carry a payload.
    return scrub(text, 120)


def redact_serial(serial: str | None) -> str:
    """Keep the classifying prefix, drop the identifying remainder."""
    if not serial:
        return "<none>"
    head, sep, tail = serial.partition("-")
    if not sep:
        return f"<no-dash:{len(serial)} chars>"
    return f"{head}-{'*' * len(tail)}"


def classify(serial: str) -> str:
    """How the coordinator's filter will treat this serial."""
    if serial.startswith(HUB_SERIAL_PREFIXES):
        return "hub -> exposed"
    if serial.startswith(NON_HUB_SERIAL_PREFIXES):
        return "known non-hub -> skipped"
    return "unrecognised -> shadow fetch decides"


# Deep enough to reach the RF descriptor, which nests seven levels down:
# data > state > desired > CMD_LST > CMD_steps > [0] > C. That value ("1:4:1:0")
# is the single most useful field in a compatibility report, so the cap must
# clear it rather than truncate it to "<deeper>".
_MAX_DEPTH = 9


def shape(value: Any, depth: int = 0, key: str = "") -> Any:
    """Recursively reduce a payload to its structure.

    Dict keys are preserved (they are the schema, and the schema is the whole
    point). Values survive only if the key is safelisted; otherwise the type
    name stands in.
    """
    if depth > _MAX_DEPTH:
        return "<deeper>"
    if isinstance(value, dict):
        return {k: shape(v, depth + 1, k) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        # One representative element is enough to show the schema.
        return [shape(value[0], depth + 1, key), f"<+{len(value) - 1} more>"][
            : 1 if len(value) == 1 else 2
        ]
    if key in SERIAL_KEYS and isinstance(value, str):
        return redact_serial(value)
    if key in SAFE_VALUE_KEYS:
        return value
    if value is None:
        return None
    return f"<{type(value).__name__}>"


def describe_device(device: dict) -> dict[str, Any]:
    """One entry from get-grill-list, stripped to what aids compatibility work."""
    serial = str(device.get("GrillNumber") or "")
    return {
        "serial_prefix": redact_serial(serial),
        "serial_length": len(serial),
        "model": device.get("Model"),
        "app_name": device.get("AppName"),
        "classification": classify(serial),
        "keys_present": sorted(device),
    }


# What a working hub looks like. Divergence here is exactly the "shapes are off"
# case: the account signed in, devices came back, and something is still not
# what the integration is built to read.
EXPECTED_DEVICE_KEYS = frozenset({"GrillNumber", "Model"})
EXPECTED_SHADOW_PATH = ("data", "state", "desired", "CMD_LST", "CMD_steps")


def _dig(obj: Any, path: tuple[str, ...]) -> Any:
    for step in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(step)
    return obj


def findings(
    *, brand_verified: bool, devices: list[dict] | None, shadow: dict | None
) -> list[str]:
    """Things worth a human look even though setup succeeded."""
    out: list[str] = []
    if not brand_verified:
        out.append(
            "No awning of this brand has been driven end to end. Sign-in and "
            "the device list may well work -- what is unverified is whether "
            "Open/Close physically moves the awning. Please report either way."
        )
    if devices is None:
        return out

    for device in devices:
        serial = str(device.get("GrillNumber") or "")
        missing = EXPECTED_DEVICE_KEYS - set(device)
        if missing:
            out.append(
                f"{redact_serial(serial)}: device entry missing expected "
                f"key(s) {sorted(missing)}"
            )
        if classify(serial).startswith("unrecognised"):
            out.append(
                f"{redact_serial(serial)}: serial prefix is not in the app's "
                "classification map -- it was kept, but may not be a hub"
            )

    # Mirror the coordinator's filter: recognised hubs are kept, and so are
    # unrecognised prefixes (they fall through to the shadow fetch). Only
    # devices the map knows to be something else are dropped outright.
    kept = [
        d
        for d in devices
        if not classify(str(d.get("GrillNumber") or "")).startswith("known non-hub")
    ]
    if devices and not kept:
        out.append(
            f"All {len(devices)} device(s) classified as non-hub, so no "
            "entities will be created. If you do own an awning hub on this "
            "account, its serial prefix is being misread."
        )

    if shadow is not None:
        steps = _dig(shadow, EXPECTED_SHADOW_PATH)
        if steps is None:
            out.append(
                "Hub shadow has no "
                + ".".join(EXPECTED_SHADOW_PATH)
                + " -- the cover's state and its command format are both "
                "derived from there, so this brand likely needs different "
                "handling."
            )
        elif isinstance(steps, list) and steps:
            descriptor = steps[0].get("C") if isinstance(steps[0], dict) else None
            if not isinstance(descriptor, str) or descriptor.count(":") != 3:
                out.append(
                    f"RF command descriptor is {descriptor!r}, not the expected "
                    '"remoteType:action:remoteNumber:channel" shape.'
                )
    return out


def build_report(
    *,
    brand_key: str | None,
    brand_name: str | None,
    selected_brand: str | None = None,
    gateway: str | None,
    new_api: bool | None,
    app_name: str | None,
    auth_attempts: list[dict],
    devices: list[dict] | None,
    shadow: dict | None,
    error: str | None = None,
    brand_verified: bool = False,
) -> dict[str, Any]:
    """Assemble the structured report both surfaces render.

    Free text from the server -- error bodies, probe details -- is scrubbed
    here rather than at each call site, so a new caller cannot forget.
    """
    return {
        "findings": findings(
            brand_verified=brand_verified, devices=devices, shadow=shadow
        ),
        "redaction_note": (
            "Contains no email, password, token, nickname, location or full "
            "serial number. Serials are reduced to their classifying prefix; "
            "payload values are replaced by their types unless the key is a "
            "known protocol constant; server error text is reduced to its "
            "endpoint and status code."
        ),
        "login": {
            # What the user picked, versus what actually worked. Reporting the
            # selection as "matched" made a failed sign-in read as a success.
            "selected_brand": selected_brand or brand_key,
            "attempts": [
                {**a, "detail": summarize_error(a.get("detail"))}
                for a in auth_attempts
            ],
            "matched_brand": brand_key,
            "matched_brand_name": brand_name,
            "gateway": gateway,
            "request_style": (
                None
                if new_api is None
                else ("POST + JSON body" if new_api else "GET + query parameter")
            ),
            "app_name_used": app_name,
        },
        "error": summarize_error(error),
        "devices": {
            "count": None if devices is None else len(devices),
            "entries": [describe_device(d) for d in (devices or [])],
        },
        "first_hub_shadow_shape": shape(shadow) if shadow else None,
    }


def render_login(report: dict[str, Any]) -> str:
    """Just the authentication outcome.

    Logged unconditionally on every setup: which pool answered, over which
    gateway, in which request style. It is small, it never repeats, and it is
    the first thing anyone needs when a brand misbehaves. The payload shapes
    are a separate, opt-in concern -- see the debug-logging switch.
    """
    login = report["login"]
    parts = [
        f"brand={login['matched_brand']}",
        f"gateway={login['gateway']}",
        f"style={login['request_style']}",
        f"AppName={login['app_name_used']!r}",
        f"devices={report['devices']['count']}",
    ]
    tried = ", ".join(
        f"{a['brand']}:{a['result']}" for a in login["attempts"]
    )
    return " ".join(parts) + (f" | probe: {tried}" if tried else "")


def render(report: dict[str, Any]) -> str:
    """Flatten the report to text a user can paste into a GitHub issue."""
    lines: list[str] = []
    login = report["login"]
    lines.append("LOGIN")
    lines.append(f"  brand tried  : {login.get('selected_brand') or '<none>'}")
    for attempt in login["attempts"]:
        extra = [
            part
            for part in (
                f"AppName={attempt['app_name']!r}" if attempt.get("app_name") else None,
                attempt.get("detail"),
            )
            if part
        ]
        lines.append(
            f"  {attempt['brand']:12} {attempt['result']}"
            + (f"  ({'; '.join(extra)})" if extra else "")
        )
    lines.append(
        f"  matched      : {login['matched_brand'] or '<none>  (sign-in did not succeed)'}"
    )
    lines.append(f"  gateway      : {login['gateway'] or '<none>'}")
    lines.append(f"  request style: {login['request_style'] or '<none>'}")
    lines.append(f"  AppName sent : {login['app_name_used'] or '<none>'}")

    if report.get("error"):
        lines += ["", f"ERROR: {report['error']}"]

    if report.get("findings"):
        lines += ["", "WORTH A LOOK"]
        lines += [f"  - {f}" for f in report["findings"]]

    devices = report["devices"]
    if devices["count"] is None:
        lines += ["", "DEVICES: not reached (sign-in did not succeed)"]
    else:
        lines += ["", f"DEVICES ({devices['count']})"]
    for i, d in enumerate(devices["entries"], 1):
        lines.append(
            f"  [{i}] {d['serial_prefix']:14} len={d['serial_length']:<3}"
            f" model={d['model']!r}"
        )
        lines.append(f"      {d['classification']}")
        lines.append(f"      keys: {', '.join(d['keys_present'])}")

    if report.get("first_hub_shadow_shape"):
        import json

        lines += ["", "FIRST HUB SHADOW (structure only)"]
        lines += [
            "  " + line
            for line in json.dumps(report["first_hub_shadow_shape"], indent=2).splitlines()
        ]

    lines += ["", report["redaction_note"]]
    return "\n".join(lines)
