"""The overrides schema and loader.

Applying overrides is not implemented; these cover the parts that are, so the
stub is not untested dead code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from unifi_map.overrides import Hosted, Link, OverrideError, Overrides, apply, load, parse

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "overrides.toml"


class TestParse:
    def test_links_and_hosted_are_read(self):
        result = parse(
            {
                "link": [{"from": "nas", "to": "Rack Switch", "port": 10, "speed": "10G"}],
                "hosted": [{"guest": "runner", "host": "hypervisor", "note": "VM"}],
            }
        )
        assert result.links == [Link(source="nas", target="Rack Switch", port="10", speed="10G")]
        assert result.hosted == [Hosted(guest="runner", host="hypervisor", note="VM")]

    def test_unquoted_integer_port_is_normalised_to_a_string(self):
        # Ports are naturally written unquoted in TOML.
        link = parse({"link": [{"from": "a", "to": "b", "port": 24}]}).links[0]
        assert link.port == "24"

    def test_empty_payload_is_falsy(self):
        assert not parse({})
        assert not Overrides()

    def test_wireless_flag_defaults_false(self):
        assert parse({"link": [{"from": "a", "to": "b"}]}).links[0].wireless is False
        assert parse({"link": [{"from": "a", "to": "b", "wireless": True}]}).links[0].wireless

    @pytest.mark.parametrize(
        "payload,message",
        [
            ({"link": [{"to": "b"}]}, "'from' is required"),
            ({"link": [{"from": "a"}]}, "'to' is required"),
            ({"link": [{"from": "", "to": "b"}]}, "'from' is required"),
            ({"link": ["nope"]}, "must be a table"),
            ({"hosted": [{"host": "h"}]}, "'guest' is required"),
            ({"hosted": [{"guest": "g"}]}, "'host' is required"),
            ({"hosted": ["nope"]}, "must be a table"),
        ],
    )
    def test_malformed_entries_are_rejected_loudly(self, payload, message):
        # A typo must fail the run, not silently do nothing.
        with pytest.raises(OverrideError, match=message):
            parse(payload)

    def test_error_message_identifies_the_offending_entry(self):
        with pytest.raises(OverrideError, match=r"\[\[link\]\] #2"):
            parse({"link": [{"from": "a", "to": "b"}, {"from": "c"}]})

    def test_non_string_optional_value_is_rejected(self):
        with pytest.raises(OverrideError, match="must be a string or number"):
            parse({"link": [{"from": "a", "to": "b", "note": ["x"]}]})


class TestLabels:
    def test_port_and_speed_are_combined(self):
        assert Link("a", "b", port="10", speed="10G").label == "port 10 · 10G"

    def test_partial_information_still_labels(self):
        assert Link("a", "b", port="3").label == "port 3"
        assert Link("a", "b", speed="1G").label == "1G"

    def test_no_detail_means_no_label(self):
        assert Link("a", "b").label is None


class TestLoad:
    def test_the_shipped_example_parses(self):
        result = load(EXAMPLE)
        # It documents both override kinds, so it must contain both.
        assert result.links
        assert result.hosted
        assert any(link.speed == "10G" for link in result.links)

    def test_missing_file_raises_override_error(self, tmp_path):
        with pytest.raises(OverrideError, match="No overrides file"):
            load(tmp_path / "absent.toml")

    def test_invalid_toml_raises_override_error(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text("[[link]\nfrom =", encoding="utf-8")
        with pytest.raises(OverrideError, match="not valid TOML"):
            load(path)


def test_apply_is_still_a_documented_stub():
    # Guards against the stub being quietly forgotten: when apply() is built,
    # this test should be replaced with real behaviour coverage.
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        apply(object(), Overrides())


class TestNodeOverrides:
    def test_name_and_icon_are_read(self):
        result = parse(
            {
                "node": [
                    {
                        "match": "10.0.30.22",
                        "name": "Network Bidet",
                        "icon": "assets/bidet.png",
                        "note": "UniFi says smart toothbrush",
                    }
                ]
            },
            base_dir=Path("/cfg"),
        )
        node = result.nodes[0]
        assert node.match == "10.0.30.22"
        assert node.name == "Network Bidet"
        assert node.note == "UniFi says smart toothbrush"
        # Relative to the overrides file, not the working directory.
        assert node.icon == Path("/cfg/assets/bidet.png")

    def test_absolute_icon_path_is_left_alone(self):
        node = parse(
            {"node": [{"match": "x", "icon": "/srv/art/bidet.png"}]}, base_dir=Path("/cfg")
        ).nodes[0]
        assert node.icon == Path("/srv/art/bidet.png")

    def test_relative_icon_without_base_dir_stays_relative(self):
        node = parse({"node": [{"match": "x", "icon": "a/b.png"}]}).nodes[0]
        assert node.icon == Path("a/b.png")

    def test_name_only_and_icon_only_are_both_valid(self):
        assert parse({"node": [{"match": "x", "name": "Renamed"}]}).nodes[0].icon is None
        assert parse({"node": [{"match": "x", "icon": "i.png"}]}).nodes[0].name is None

    def test_an_entry_that_changes_nothing_is_rejected(self):
        # Silently ignoring it would hide a typo'd key.
        with pytest.raises(OverrideError, match="at least one of 'name', 'icon' or 'hide'"):
            parse({"node": [{"match": "x", "note": "just a comment"}]})

    def test_match_is_required(self):
        with pytest.raises(OverrideError, match="'match' is required"):
            parse({"node": [{"name": "Renamed"}]})

    def test_non_table_entry_is_rejected(self):
        with pytest.raises(OverrideError, match=r"\[\[node\]\] #1 must be a table"):
            parse({"node": ["nope"]})

    def test_node_overrides_count_towards_truthiness(self):
        assert parse({"node": [{"match": "x", "name": "y"}]})


def test_the_shipped_example_documents_node_overrides():
    result = load(EXAMPLE)
    assert result.nodes
    # The bidet is the documented example of a wrong fingerprint.
    bidet = next(n for n in result.nodes if n.name == "Network Bidet")
    assert bidet.icon is not None
    # Resolved against the examples/ directory.
    assert bidet.icon.parent == EXAMPLE.parent / "assets"


class TestHideOverride:
    def test_hide_alone_is_a_valid_entry(self):
        node = parse({"node": [{"match": "Garage", "hide": True}]}).nodes[0]
        assert node.hide is True
        assert node.name is None and node.icon is None

    def test_hide_defaults_false(self):
        assert parse({"node": [{"match": "x", "name": "y"}]}).nodes[0].hide is False

    def test_hide_combines_with_a_rename(self):
        node = parse({"node": [{"match": "x", "name": "y", "hide": True}]}).nodes[0]
        assert (node.name, node.hide) == ("y", True)

    def test_an_entry_with_only_a_note_is_still_rejected(self):
        with pytest.raises(OverrideError, match="'name', 'icon' or 'hide'"):
            parse({"node": [{"match": "x", "note": "just a comment"}]})

    def test_hide_false_does_not_count_as_a_change(self):
        # hide = false is the default, so it changes nothing and must not sneak
        # past the "entry does nothing" check.
        with pytest.raises(OverrideError, match="'name', 'icon' or 'hide'"):
            parse({"node": [{"match": "x", "hide": False}]})

    def test_the_shipped_example_documents_hiding(self):
        hidden = [n for n in load(EXAMPLE).nodes if n.hide]
        # Both reasons to hide are worth showing: discretion and noise.
        assert len(hidden) >= 2, "examples/overrides.toml should show hide entries"
        assert any("naughty" in (n.note or "") for n in hidden)
        assert any(n.match == "Garage" for n in hidden)
