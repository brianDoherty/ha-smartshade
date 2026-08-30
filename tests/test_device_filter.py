"""Serial-prefix classification.

The filter decides which of an account's devices become entities. Getting it
wrong in one direction hides the user's awning; in the other it turns a light
strip into a cover with buttons that go nowhere.
"""

import pytest


def keep(const, serial: str) -> bool:
    """Mirror of is_controllable_hub, which lives behind a homeassistant import."""
    if serial.startswith(const.HUB_SERIAL_PREFIXES):
        return True
    if serial.startswith(const.NON_HUB_SERIAL_PREFIXES):
        return False
    return True


@pytest.mark.parametrize(
    "serial",
    ["RFH-9001", "MNH-A19F32B7", "RFT-0004", "TRH-22", "MNL-77"],
)
def test_every_hub_model_is_kept(const, serial):
    assert keep(const, serial)


@pytest.mark.parametrize(
    ("serial", "what"),
    [
        ("BND-R7", "Smart RF Remote"),
        ("USL-77", "universal remote"),
        ("SRF-12", "Somfy remote"),
        ("MUS-12", "ultrasonic sensor"),
        ("MSB-4", "WindGuard solar sensor"),
        ("RFS-3", "WindGuard sensor"),
        ("FRF-8", "IF10 receiver"),
    ],
)
def test_rf_only_accessories_are_dropped(const, serial, what):
    assert not keep(const, serial), what


@pytest.mark.parametrize(
    ("serial", "what"),
    [
        ("LBS-9931", "Light Bug"),
        ("MNR-8", "RGB IC"),
        ("MNA-3", "RGBIC & motion"),
        ("SOL-2", "SOLX"),
        ("RFF-1", "The One"),
        ("TFF-5", "Touchscreen The One"),
        ("WPH-6", "WPH"),
        ("MPS-3", "smart probe"),
    ],
)
def test_other_t2fi_products_with_shadows_are_dropped(const, serial, what):
    """These have real device shadows, so a fallthrough would expose them."""
    assert not keep(const, serial), what


def test_unknown_prefix_falls_through_rather_than_vanishing(const):
    """A hub model newer than the map must still work."""
    assert keep(const, "ZZZ-4411")


def test_hub_and_non_hub_sets_do_not_overlap(const):
    assert not set(const.HUB_SERIAL_PREFIXES) & set(const.NON_HUB_SERIAL_PREFIXES)


def test_no_non_hub_prefix_shadows_a_hub_prefix(const):
    """A non-hub entry must never swallow a hub serial."""
    for hub in const.HUB_SERIAL_PREFIXES:
        assert not hub.startswith(tuple(const.NON_HUB_SERIAL_PREFIXES))
