"""Brand registry: the credential split that decides everything downstream."""

POOL_A = "us-east-1_xCzWPPECR"
POOL_B = "us-east-1_8oziOkCAf"


def test_every_brand_key_matches_its_dict_key(const):
    for key, brand in const.BRANDS.items():
        assert brand.key == key


def test_brands_split_across_exactly_two_pools(const):
    assert {b.pool_id for b in const.BRANDS.values()} == {POOL_A, POOL_B}


def test_pool_a_brands_share_one_credential_set(const):
    a = [b for b in const.BRANDS.values() if b.pool_id == POOL_A]
    assert len({(b.client_id, b.client_secret) for b in a}) == 1
    assert all(not b.new_api for b in a)
    # The legacy gateway takes no AppName at all.
    assert all(b.app_name is None for b in a)


def test_pool_b_brands_share_credentials_but_not_app_names(const):
    b = [x for x in const.BRANDS.values() if x.pool_id == POOL_B]
    assert len({(x.client_id, x.client_secret) for x in b}) == 1
    assert all(x.new_api for x in b)
    # AppName is per-app; four brands must not collide on it.
    names = [x.app_name for x in b]
    assert all(names) and len(set(names)) == len(names)


def test_only_marygrove_hardware_is_confirmed(const):
    """Marygrove is the one brand actually driven end to end.

    Smart Shade PRO shares its credentials, which is why the integration is
    named after it -- but no Smart Shade PRO hardware has ever been tested, and
    conflating the two is exactly the error this guards against.
    """
    assert {k for k, v in const.BRANDS.items() if v.hardware_confirmed} == {"marygrove"}


def test_credentials_confirmed_tracks_the_pool_not_the_brand(const):
    """Credential confidence is a property of the pool, so it must be uniform."""
    for pool in {b.pool_id for b in const.BRANDS.values()}:
        peers = [b for b in const.BRANDS.values() if b.pool_id == pool]
        assert len({b.credentials_confirmed for b in peers}) == 1, pool
    assert const.BRANDS["smartshade"].credentials_confirmed
    assert not const.BRANDS["liberty"].credentials_confirmed


def test_hardware_confirmed_implies_credentials_confirmed(const):
    for b in const.BRANDS.values():
        if b.hardware_confirmed:
            assert b.credentials_confirmed, b.key


def test_status_labels(const):
    assert const.BRANDS["marygrove"].status == "confirmed"
    assert "untested hardware" in const.BRANDS["smartshade"].status
    assert const.BRANDS["liberty"].status == "untested"


def test_default_brand_is_the_confirmed_one(const):
    assert const.DEFAULT_BRAND in const.BRANDS
    assert const.BRANDS[const.DEFAULT_BRAND].hardware_confirmed


def test_legacy_entries_without_a_brand_resolve_to_identical_credentials(const):
    """Entries predating the brand field fell back to the default.

    Those entries were created against Pool A, so the fallback must land on a
    brand with byte-identical credentials or existing installs would break.
    """
    d = const.BRANDS[const.DEFAULT_BRAND]
    legacy = const.BRANDS["smartshade"]
    assert (d.pool_id, d.client_id, d.client_secret) == (
        legacy.pool_id, legacy.client_id, legacy.client_secret)


def test_pool_name_strips_the_region(const):
    assert const.BRANDS["smartshade"].pool_name == "xCzWPPECR"


def test_gateways_differ_by_pool(const):
    a = const.BRANDS["smartshade"]
    b = const.BRANDS["liberty"]
    assert a.api_base != b.api_base
    assert all(x.api_base.startswith("https://") for x in (a, b))
    assert all(x.api_base.endswith("/") for x in (a, b))
