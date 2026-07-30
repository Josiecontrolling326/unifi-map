"""Visual themes.

Colour still never carries meaning alone (device role is in the artwork and
shape, link type in the line style), so both themes stay readable under
deuteranopia and in greyscale. The accents remain Okabe-Ito.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Kind

# Okabe-Ito. https://jfly.uni-koeln.de/color/
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
PURPLE = "#CC79A7"
SKY = "#56B4E9"
VERMILLION = "#D55E00"
YELLOW = "#F0E442"

CATEGORICAL = [BLUE, ORANGE, GREEN, PURPLE, SKY, VERMILLION, YELLOW]


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    card: str
    card_muted: str
    border: str
    text: str
    text_muted: str
    text_faint: str
    edge: str
    edge_label: str
    title: str
    accents: dict[Kind, str]

    def accent(self, kind: Kind) -> str:
        return self.accents.get(kind, self.border)


_ACCENTS: dict[Kind, str] = {
    Kind.INTERNET: "#8A8A8A",
    Kind.GATEWAY: BLUE,
    Kind.SWITCH: ORANGE,
    Kind.AP: SKY,
    Kind.BRIDGE: PURPLE,
    Kind.WIRED_CLIENT: GREEN,
    Kind.WIRELESS_CLIENT: PURPLE,
    Kind.UNKNOWN: "#8A8A8A",
}

LIGHT = Theme(
    name="light",
    background="#F7F8FA",
    card="#FFFFFF",
    card_muted="#EEF0F4",
    border="#C9CED6",
    text="#14171C",
    text_muted="#5A626E",
    text_faint="#8B93A0",
    edge="#9AA2AF",
    edge_label="#6B7280",
    title="#14171C",
    accents=_ACCENTS,
)

DARK = Theme(
    name="dark",
    background="#12151B",
    card="#1D222B",
    card_muted="#171B22",
    border="#333B47",
    text="#F2F4F7",
    text_muted="#A8B0BD",
    text_faint="#78808D",
    edge="#4C5563",
    edge_label="#98A1AE",
    title="#F2F4F7",
    accents=_ACCENTS,
)

THEMES: dict[str, Theme] = {"light": LIGHT, "dark": DARK}


def get_theme(name: str) -> Theme:
    try:
        return THEMES[name]
    except KeyError:
        raise ValueError(
            f"Unknown theme {name!r}. Choose from: {', '.join(sorted(THEMES))}"
        ) from None


# Fallback shapes for nodes with no artwork. Role stays encoded in shape so the
# diagram is still readable when the CDN is unreachable or in greyscale.
KIND_SHAPE: dict[Kind, str] = {
    Kind.INTERNET: "septagon",
    Kind.GATEWAY: "doubleoctagon",
    Kind.SWITCH: "box3d",
    Kind.AP: "trapezium",
    Kind.BRIDGE: "hexagon",
    Kind.WIRED_CLIENT: "box",
    Kind.WIRELESS_CLIENT: "ellipse",
    Kind.UNKNOWN: "diamond",
}

KIND_LABEL: dict[Kind, str] = {
    Kind.INTERNET: "Internet / WAN",
    Kind.GATEWAY: "Gateway",
    Kind.SWITCH: "Switch",
    Kind.AP: "Access point",
    Kind.BRIDGE: "Wireless bridge",
    Kind.WIRED_CLIENT: "Wired client",
    Kind.WIRELESS_CLIENT: "Wireless client",
    Kind.UNKNOWN: "Unclassified",
}


def network_colors(names: list[str]) -> dict[str, str]:
    """Stable colour per network name, so exports stay comparable over time."""
    return {name: CATEGORICAL[i % len(CATEGORICAL)] for i, name in enumerate(sorted(names))}
