"""Shape checks.

These fire when a brand signs in successfully but hands back payloads the
entities cannot read -- the failure mode setup would otherwise call a success.
"""

GOOD_SHADOW = {
    "data": {
        "state": {
            "desired": {"CMD_LST": {"CMD_steps": [{"C": "1:4:1:0", "D": 0.2}]}}
        }
    }
}
GOOD_DEVICE = [{"GrillNumber": "MNH-A1", "Model": "RF MINI HUB"}]


def test_confirmed_brand_with_normal_payload_is_silent(report):
    assert report.findings(
        brand_verified=True, devices=GOOD_DEVICE, shadow=GOOD_SHADOW
    ) == []


def test_unconfirmed_hardware_always_speaks_up(report):
    """Even a clean payload must say the awning itself was never driven."""
    out = report.findings(
        brand_verified=False, devices=GOOD_DEVICE, shadow=GOOD_SHADOW
    )
    assert len(out) == 1
    assert "driven end to end" in out[0]
    assert "Open/Close" in out[0]


def test_missing_command_path_is_flagged(report):
    out = report.findings(
        brand_verified=True,
        devices=GOOD_DEVICE,
        shadow={"data": {"state": {"desired": {"MODE": 1}}}},
    )
    assert any("CMD_steps" in f for f in out)


def test_wrong_rf_descriptor_shape_is_flagged(report):
    out = report.findings(
        brand_verified=True,
        devices=GOOD_DEVICE,
        shadow={"data": {"state": {"desired": {"CMD_LST": {"CMD_steps": [{"C": "OPEN"}]}}}}},
    )
    assert any("descriptor" in f for f in out)


def test_device_missing_expected_keys_is_flagged(report):
    out = report.findings(
        brand_verified=True, devices=[{"GrillNumber": "MNH-A1"}], shadow=GOOD_SHADOW
    )
    assert any("missing expected" in f for f in out)


def test_unrecognised_prefix_is_flagged_but_not_called_a_dead_install(report):
    """An unknown prefix is kept by the filter, so it must not claim no entities."""
    out = report.findings(
        brand_verified=True,
        devices=[{"GrillNumber": "XYZ-4411", "Model": "?"}],
        shadow=GOOD_SHADOW,
    )
    assert any("not in the app's classification map" in f for f in out)
    assert not any("no entities will be created" in f for f in out)


def test_all_devices_filtered_out_is_flagged(report):
    out = report.findings(
        brand_verified=True,
        devices=[{"GrillNumber": "MUS-77C401", "Model": "SMART SENSOR"}],
        shadow=None,
    )
    assert any("no entities will be created" in f for f in out)


def test_findings_never_leak_a_full_serial(report):
    out = report.findings(
        brand_verified=True,
        devices=[{"GrillNumber": "XYZ-4411SECRET"}],
        shadow=GOOD_SHADOW,
    )
    assert not any("4411SECRET" in f for f in out)
