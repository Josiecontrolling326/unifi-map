"""Asset fetching, caching and SVG inlining.

No test here touches the network: the catalog is written straight into the cache
so AssetStore reads it from disk.
"""

from __future__ import annotations

import json

import pytest

from unifi_map.assets import AssetStore, IconAsset
from unifi_map.svg_post import inline_svg_images

CATALOG = {
    "version": "test",
    "devices": [
        {
            "id": "aaaa-bbbb",
            # Catalog sysids are hex strings; the controller reports decimal.
            "sysids": ["a682"],
            "product": {"name": "Access Point U7 Pro"},
            "images": {"topology": "topohash", "default": "defhash"},
            "icon": {"id": "icon-uuid"},
        },
        {
            "id": "cccc-dddd",
            "sysid": "ed72",
            "product": {"name": "Switch Pro HD 24 PoE"},
            # No topology variant: must fall back down the preference list.
            "images": {"default": "onlydefault"},
        },
        {"id": "eeee", "sysids": ["ffff"], "product": {"name": "No Art"}, "images": {}},
    ],
}


@pytest.fixture
def store(tmp_path) -> AssetStore:
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "ui-device-catalog.json").write_text(json.dumps(CATALOG), encoding="utf-8")
    return AssetStore(cache_dir=cache, offline=True)


class TestCatalog:
    def test_hex_sysids_are_parsed_to_the_controllers_decimal_values(self, store: AssetStore):
        # 0xa682 == 42626, which is what stat/device reports for a U7 Pro.
        assert 42626 in store.catalog()
        assert 0xED72 in store.catalog()

    def test_product_name_lookup(self, store: AssetStore):
        assert store.product_name(42626) == "Access Point U7 Pro"
        assert store.product_name(0xFFFF) == "No Art"

    def test_unknown_sysid_resolves_to_nothing(self, store: AssetStore):
        assert store.product_name(0x1234) is None
        assert store.icon(0x1234) is None

    def test_none_sysid_is_tolerated(self, store: AssetStore):
        assert store.product_name(None) is None
        assert store.icon(None) is None

    def test_corrupt_cached_catalog_does_not_raise_when_offline(self, tmp_path):
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "ui-device-catalog.json").write_text("{not json", encoding="utf-8")
        store = AssetStore(cache_dir=cache, offline=True)
        # Degrades to an empty catalog rather than exploding.
        assert store.catalog() == {}


class TestIconCache:
    def test_offline_with_no_cached_file_yields_nothing(self, store: AssetStore):
        assert store.icon(42626) is None

    def test_a_cached_file_is_measured_and_reused(self, store: AssetStore, png_bytes):
        from unifi_map.assets import ICON_PX

        store.icon_dir.mkdir(parents=True, exist_ok=True)
        # Filename encodes sysid, variant and size; `topology` is preferred.
        target = store.icon_dir / f"{42626:04x}-topology-{ICON_PX}.png"
        target.write_bytes(png_bytes(40, 10))

        asset = store.icon(42626)
        assert asset is not None
        assert asset.path == target
        assert (asset.width, asset.height) == (40, 10)

    def test_variant_preference_falls_back_when_topology_is_absent(
        self, store: AssetStore, png_bytes
    ):
        from unifi_map.assets import ICON_PX

        store.icon_dir.mkdir(parents=True, exist_ok=True)
        target = store.icon_dir / f"{0xED72:04x}-default-{ICON_PX}.png"
        target.write_bytes(png_bytes(20, 20))
        assert store.icon(0xED72) is not None

    def test_device_with_no_images_yields_nothing(self, store: AssetStore):
        assert store.icon(0xFFFF) is None


class TestSvgInlining:
    def test_png_reference_becomes_a_data_uri(self, tmp_path, png_bytes):
        icon = tmp_path / "icon.png"
        icon.write_bytes(png_bytes(4, 4))
        svg = f'<svg><image xlink:href="{icon}" /></svg>'.encode()

        out = inline_svg_images(svg, allowed_root=tmp_path)
        assert b"data:image/png;base64," in out
        assert str(icon).encode() not in out

    def test_repeated_reference_is_encoded_once_and_reused(self, tmp_path, png_bytes):
        icon = tmp_path / "icon.png"
        icon.write_bytes(png_bytes(4, 4))
        svg = f'<svg><image href="{icon}"/><image href="{icon}"/></svg>'.encode()
        out = inline_svg_images(svg, allowed_root=tmp_path)
        assert out.count(b"data:image/png;base64,") == 2

    def test_files_outside_the_allowed_root_are_refused(self, tmp_path, png_bytes):
        outside = tmp_path / "secret.png"
        outside.write_bytes(png_bytes(4, 4))
        allowed = tmp_path / "icons"
        allowed.mkdir()
        svg = f'<svg><image href="{outside}"/></svg>'.encode()

        out = inline_svg_images(svg, allowed_root=allowed)
        # Left untouched rather than embedded.
        assert b"data:image/png" not in out
        assert str(outside).encode() in out

    def test_missing_file_is_left_alone(self, tmp_path):
        svg = f'<svg><image href="{tmp_path / "nope.png"}"/></svg>'.encode()
        assert inline_svg_images(svg, allowed_root=tmp_path).count(b"data:") == 0

    def test_existing_data_uri_is_not_double_encoded(self, tmp_path):
        svg = b'<svg><image href="data:image/png;base64,QQ==.png"/></svg>'
        assert inline_svg_images(svg, allowed_root=tmp_path) == svg

    def test_non_png_references_are_ignored(self, tmp_path):
        svg = b'<svg><image href="/etc/passwd"/></svg>'
        assert inline_svg_images(svg, allowed_root=tmp_path) == svg


def test_icon_asset_display_size_never_returns_zero():
    tiny = IconAsset(path=None, width=1, height=1000)  # type: ignore[arg-type]
    w, h = tiny.display_size(168, 90)
    assert w >= 1 and h >= 1


class TestClientArtwork:
    def test_offline_yields_nothing_without_a_cached_file(self, store: AssetStore):
        assert store.client_icon(4425) is None

    def test_none_dev_id_is_tolerated(self, store: AssetStore):
        assert store.client_icon(None) is None

    def test_a_cached_client_icon_is_measured_and_reused(self, store: AssetStore, png_bytes):
        from unifi_map.assets import ICON_PX

        store.icon_dir.mkdir(parents=True, exist_ok=True)
        target = store.icon_dir / f"client-4425-{ICON_PX}.png"
        target.write_bytes(png_bytes(32, 24))

        asset = store.client_icon(4425)
        assert asset is not None
        assert asset.path == target
        assert (asset.width, asset.height) == (32, 24)


class TestClientGlyphs:
    def test_no_font_means_no_glyph(self, store: AssetStore):
        assert store.client_glyph("user-wired", "#888888") is None

    def test_codepoints_are_read_from_the_cached_map(self, store: AssetStore):
        store.cache_dir.mkdir(parents=True, exist_ok=True)
        store.font_map_path.write_text('{"user-wired": 59681}', encoding="utf-8")
        assert store.glyph_codepoints() == {"user-wired": 59681}

    def test_corrupt_codepoint_map_degrades_quietly(self, store: AssetStore):
        store.cache_dir.mkdir(parents=True, exist_ok=True)
        store.font_map_path.write_text("{nope", encoding="utf-8")
        assert store.glyph_codepoints() == {}

    def test_saving_the_font_writes_both_files(self, store: AssetStore):
        store.save_icon_font(b"not-a-real-font", {"user-wired": 1})
        assert store.font_path.read_bytes() == b"not-a-real-font"
        assert store.glyph_codepoints() == {"user-wired": 1}

    def test_unknown_glyph_name_yields_nothing(self, store: AssetStore):
        store.save_icon_font(b"x", {"user-wired": 1})
        assert store.client_glyph("no-such-glyph", "#888888") is None


class TestHardwareNameLookup:
    """UniFi hardware that appears as a client has no fingerprint, so its
    hostname is matched against the hardware catalog instead."""

    def test_unique_match_resolves(self, store: AssetStore):
        assert store.sysid_for_name("U7 Pro") == 42626
        assert store.sysid_for_name("u7-pro") == 42626

    def test_matching_is_punctuation_insensitive(self, store: AssetStore):
        assert store.sysid_for_name("Pro HD 24 PoE") == 0xED72
        assert store.sysid_for_name("pro-hd-24-poe") == 0xED72

    def test_ambiguous_name_refuses_to_guess(self, tmp_path):
        # "g3flex" really does match both a Protect camera and an Access reader
        # in the real catalog. Picking one would be inventing data.
        catalog = {
            "devices": [
                {
                    "id": "a",
                    "sysid": "a534",
                    "product": {"name": "Camera G3 Flex"},
                    "shortnames": ["UVC-G3-FLEX"],
                    "deviceType": "camera",
                    "images": {},
                },
                {
                    "id": "b",
                    "sysid": "b100",
                    "product": {"name": "G3 Reader Flex"},
                    "shortnames": ["UA-G3-Flex"],
                    "deviceType": "door-access",
                    "images": {},
                },
            ]
        }
        cache = tmp_path / "c"
        cache.mkdir()
        (cache / "ui-device-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        store = AssetStore(cache_dir=cache, offline=True)

        assert store.sysid_for_name("g3-flex") is None
        # A device type breaks the tie, which is what Protect provides.
        assert store.sysid_for_name("g3-flex", device_type="camera") == 0xA534
        assert store.sysid_for_name("g3-flex", device_type="door-access") == 0xB100

    def test_unknown_name_resolves_to_nothing(self, store: AssetStore):
        assert store.sysid_for_name("definitely-not-a-product") is None

    def test_short_or_empty_names_are_ignored(self, store: AssetStore):
        # Two characters would match half the catalog.
        assert store.sysid_for_name("u7") is None
        assert store.sysid_for_name("") is None
        assert store.sysid_for_name(None) is None
