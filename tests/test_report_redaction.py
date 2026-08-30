"""Redaction.

The report is handed to users with "safe to paste into a GitHub issue" attached
to it. That claim is the thing under test.
"""

import json

import pytest

# Everything a real payload might carry that must never survive. All values
# here are invented -- this file must never contain anyone's actual data, which
# would be a particularly embarrassing way for a redaction test to fail.
SECRETS = [
    "owner@example.com",
    "Back Patio",
    "MNH-A19F32B7",
    "MUS-77C401",
    "12.345678",
    "-98.765432",
    "HomeNet-5G",
    "eyJmYWtldG9rZW5mb3J0ZXN0aW5nb25seQ",
]

DEVICES = [
    {
        "GrillNumber": "MNH-A19F32B7",
        "Model": "RF MINI HUB",
        "NickName": "Back Patio",
        "AppName": "smartshade_pro",
        "Latitude": 12.345678,
        "Longitude": -98.765432,
        "DeviceLocationState": "Someplace",
        "OwnerEmail": "owner@example.com",
    },
    {"GrillNumber": "MUS-77C401", "Model": "SMART SENSOR", "NickName": "Wind"},
]

SHADOW = {
    "data": {
        "state": {
            "desired": {
                "MODE": 1,
                "CID": "42",
                "CMD_LST": {"CMD_steps": [{"C": "1:4:1:0", "D": 0.2}]},
            },
            "reported": {
                "LastCID": 42,
                "linkedMUS": "MUS-77C401",
                "NickName": "Back Patio",
                "Latitude": 12.345678,
                "ssid": "HomeNet-5G",
                "token": "eyJmYWtldG9rZW5mb3J0ZXN0aW5nb25seQ",
            },
        }
    }
}


@pytest.fixture
def full(report):
    return report.build_report(
        brand_key="smartshade",
        brand_name="Smart Shade PRO",
        gateway="https://gxlvgoouw8.execute-api.us-east-1.amazonaws.com/",
        new_api=False,
        app_name=None,
        auth_attempts=[
            {"brand": "smartshade", "result": "MATCHED", "app_name": None, "detail": None}
        ],
        devices=DEVICES,
        shadow=SHADOW,
        brand_verified=True,
    )


@pytest.mark.parametrize("secret", SECRETS)
def test_no_secret_survives_the_rendered_report(report, full, secret):
    assert secret not in report.render(full)


@pytest.mark.parametrize("secret", SECRETS)
def test_no_secret_survives_the_structured_report(full, secret):
    assert secret not in json.dumps(full)


def test_serial_keeps_only_its_classifying_prefix(report):
    assert report.redact_serial("MNH-A19F32B7") == "MNH-********"
    assert report.redact_serial(None) == "<none>"


def test_rf_descriptor_survives(report, full):
    """The most useful debugging value must not be redacted or depth-capped."""
    assert "1:4:1:0" in report.render(full)


def test_key_names_are_kept_even_for_redacted_values(report, full):
    """The schema is the point; only the values are dropped."""
    rendered = report.render(full)
    assert "OwnerEmail" in rendered and "Latitude" in rendered


def test_unsafe_values_become_types(report):
    shaped = report.shape({"NickName": "Patio", "ssid": "x", "MODE": 1})
    assert shaped["NickName"] == "<str>"
    assert shaped["ssid"] == "<str>"
    assert shaped["MODE"] == 1  # safelisted protocol constant


def test_server_error_reduced_to_endpoint_and_status(report):
    body = (
        'get-grill-list HTTP 400: {"NickName":"Patio",'
        '"GrillNumber":"MNH-A19F32B7","u":"b@x.com"}'
    )
    assert report.summarize_error(f"SmartShadeApiError: {body}") == (
        "SmartShadeApiError: get-grill-list HTTP 400"
    )


def test_error_of_unknown_shape_is_scrubbed_and_truncated(report):
    out = report.summarize_error("Weird: contact owner@example.com " + "x" * 400)
    assert "owner@example.com" not in out
    assert len(out) <= 120


def test_scrub_leaves_ordinary_hyphenated_words_alone(report):
    """The serial pattern must not eat endpoint names."""
    assert report.scrub("get-grill-list failed") == "get-grill-list failed"


def test_selected_brand_is_not_reported_as_matched(report):
    """A failed sign-in must not read as a success.

    The report used to print the brand the user picked on the 'matched' line
    even when authentication was rejected, so it claimed a match directly under
    'auth rejected'.
    """
    rep = report.build_report(
        brand_key=None, brand_name=None, selected_brand="marygrove",
        gateway="https://example/", new_api=False, app_name=None,
        auth_attempts=[{"brand": "marygrove", "result": "auth rejected",
                        "app_name": None, "detail": "SmartShadeAuthError"}],
        devices=None, shadow=None,
        error="SmartShadeAuthError: [InitiateAuth] User does not exist.",
    )
    assert rep["login"]["matched_brand"] is None
    assert rep["login"]["selected_brand"] == "marygrove"
    out = report.render(rep)
    assert "brand tried  : marygrove" in out
    assert "sign-in did not succeed" in out
