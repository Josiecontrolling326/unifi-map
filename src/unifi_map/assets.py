"""Fetch real UniFi product artwork and cache it locally.

Where these come from
---------------------
**Not the controller.** Network application 10.5.67 serves no device imagery
locally: every path under ``/proxy/network/manage/angular/<hash>/`` that could
plausibly hold device PNGs returns the SPA's HTML 404 fallback. The web UI pulls
its artwork from Ubiquiti's public CDN, and so do we.

- Catalog: ``https://static.ui.com/fingerprint/ui/public.json`` (~700 KB, 680
  devices), the same hardware database the UI uses.
- Artwork: ``.../images/{id}/{variant}/{hash}.png``, where the ``topology``
  variant is the render UniFi itself uses in its topology view.

Devices are matched on **sysid**, not model name: the controller's ``model``
string does not reliably match the catalog's ``shortnames`` (a USW Pro HD 24 PoE
reports ``USWED72`` while the catalog calls it ``USPH24P``). Catalog sysids are
hex strings and the controller reports a decimal int; all 1178 catalog values
are unambiguously hex, so strict base-16 parsing is correct.

Everything degrades: no network, no Pillow, or an unknown device all fall back to
the plain shape renderer rather than failing the run.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

CATALOG_URL = "https://static.ui.com/fingerprint/ui/public.json"

# Filenames for the controller-sourced icon font, written by `fetch`.
FONT_FILE = "ubnt-icon.ttf"
FONT_MAP_FILE = "ubnt-icon.json"
IMAGE_URL = "https://static.ui.com/fingerprint/ui/images/{id}/{variant}/{hash}.png"

# Client artwork, keyed by the fingerprint dev_id that stat/sta already reports.
# This is `staticFingerprintOld` in the Network UI's config, and it is what the
# topology view actually renders for clients: real product artwork, not glyphs.
# Only these three sizes exist; anything else 302s to ui.com.
CLIENT_ICON_URL = "https://static.ui.com/fingerprint/0/{dev_id}_{size}.png"
CLIENT_ICON_SIZES = ("257x257", "129x129", "101x101")

# Preference order. `topology` is what the UniFi topology view uses; the others
# are fallbacks for hardware that lacks it.
VARIANTS = ("topology", "nopadding", "default")

# Product renders are 1-2 MB each. Downscaling keeps an embedded diagram in the
# low hundreds of KB instead of tens of MB.
ICON_PX = 256


class AssetError(RuntimeError):
    """Raised only for unrecoverable local problems, never for network failures."""


def _normalise(text: Any) -> str:
    """Lowercase alphanumerics only, so "g3-flex" and "UVC G3 Flex" compare."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _to_int(value: Any, base: int) -> int | None:
    try:
        return int(str(value).strip(), base)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class IconAsset:
    """A cached artwork file and its pixel dimensions.

    Dimensions travel with the path so renderers can size a cell to the real
    aspect ratio without depending on Pillow themselves. Rack switches are wide
    and short; forcing them into a square cell letterboxes them into a thin
    strip surrounded by dead space.
    """

    path: Path
    width: int
    height: int

    def display_size(self, box_w: float, box_h: float) -> tuple[int, int]:
        """Fit inside the box, preserving aspect ratio."""
        if self.width <= 0 or self.height <= 0:
            return int(box_w), int(box_h)
        scale = min(box_w / self.width, box_h / self.height)
        return max(1, round(self.width * scale)), max(1, round(self.height * scale))


@dataclass
class AssetStore:
    """Local cache of the device catalog and downscaled artwork.

    Deliberately separate from the controller-snapshot cache: a snapshot can be
    read from anywhere (a demo dataset shipped in the repo, say) without
    downloaded artwork landing next to it.
    """

    cache_dir: Path
    offline: bool = False
    timeout: float = 30.0
    _catalog: dict[int, dict[str, Any]] | None = None

    @property
    def catalog_path(self) -> Path:
        return self.cache_dir / "ui-device-catalog.json"

    @property
    def icon_dir(self) -> Path:
        return self.cache_dir / "icons"

    @property
    def font_path(self) -> Path:
        return self.cache_dir / FONT_FILE

    @property
    def font_map_path(self) -> Path:
        return self.cache_dir / FONT_MAP_FILE

    def save_icon_font(self, font: bytes, codepoints: dict[str, int]) -> None:
        """Cache the controller's icon font. Never vendored into the repo."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.font_path.write_bytes(font)
        self.font_map_path.write_text(json.dumps(codepoints, indent=2), encoding="utf-8")

    def glyph_codepoints(self) -> dict[str, int]:
        if not self.font_map_path.is_file():
            return {}
        try:
            raw = json.loads(self.font_map_path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
        return {str(k): int(v) for k, v in raw.items() if isinstance(v, int | str)}

    def client_icon(self, dev_id: int | None) -> IconAsset | None:
        """Real product artwork for a fingerprinted client.

        The fingerprint is Ubiquiti's and is sometimes plain wrong (a phone
        identified as an appliance). That is a data problem to fix with
        overrides, not a reason to draw something generic instead.
        """
        if dev_id is None:
            return None

        cached = self.icon_dir / f"client-{dev_id}-{ICON_PX}.png"
        if cached.is_file():
            return _measure(cached)
        if self.offline:
            return None

        for size in CLIENT_ICON_SIZES:
            url = CLIENT_ICON_URL.format(dev_id=dev_id, size=size)
            try:
                response = requests.get(url, timeout=self.timeout, allow_redirects=False)
            except requests.RequestException as exc:
                log.debug("Client artwork %s failed (%s).", url, exc)
                continue
            # A missing size 302s to ui.com rather than 404ing, so a redirect
            # means "not available", not "follow me".
            if response.status_code != 200 or not response.content:
                continue
            self.icon_dir.mkdir(parents=True, exist_ok=True)
            try:
                return _downscale(response.content, cached, ICON_PX)
            except AssetError as exc:
                log.warning("%s", exc)
                return None

        log.debug("No artwork for client dev_id %s.", dev_id)
        return None

    def client_glyph(self, name: str, color: str) -> IconAsset | None:
        """Rasterize one of UniFi's client glyphs from its own icon font.

        UniFi picks a client icon by CSS class, not by device type: its
        `getIconClassName` resolves every client to one of user/guest x
        wired/wireless. Rendering that same font glyph is therefore the actual
        artwork the UI shows, not an approximation of it.

        The font comes from the controller and is cached; it is deliberately not
        shipped in this repository.
        """
        codepoints = self.glyph_codepoints()
        codepoint = codepoints.get(name)
        if codepoint is None or not self.font_path.is_file():
            return None

        safe = color.lstrip("#").lower()
        cached = self.icon_dir / f"glyph-{name}-{safe}-{ICON_PX}.png"
        if cached.is_file():
            return _measure(cached)

        self.icon_dir.mkdir(parents=True, exist_ok=True)
        try:
            return _render_glyph(self.font_path, codepoint, color, cached, ICON_PX)
        except AssetError as exc:
            log.warning("%s", exc)
            return None

    def _load_catalog_json(self) -> Any | None:
        if self.catalog_path.is_file():
            try:
                return json.loads(self.catalog_path.read_text(encoding="utf-8"))
            except ValueError:
                log.warning("Cached device catalog is corrupt; refetching.")

        if self.offline:
            log.warning("Offline and no cached device catalog; icons disabled.")
            return None

        try:
            response = requests.get(CATALOG_URL, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("Could not fetch the UniFi device catalog (%s); icons disabled.", exc)
            return None

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def catalog(self) -> dict[int, dict[str, Any]]:
        """Map sysid (as int) to catalog entry."""
        if self._catalog is not None:
            return self._catalog

        payload = self._load_catalog_json()
        index: dict[int, dict[str, Any]] = {}
        for entry in (payload or {}).get("devices", []):
            if not isinstance(entry, dict):
                continue
            raw = list(entry.get("sysids") or [])
            if entry.get("sysid") is not None:
                raw.append(entry["sysid"])
            for value in raw:
                # Catalog sysids are hex strings; verified unambiguous.
                sysid = _to_int(value, 16)
                if sysid is not None:
                    index.setdefault(sysid, entry)

        self._catalog = index
        log.debug("Device catalog indexed: %d sysids", len(index))
        return index

    def product_name(self, sysid: int | None) -> str | None:
        if sysid is None:
            return None
        entry = self.catalog().get(sysid)
        if not entry:
            return None
        name = (entry.get("product") or {}).get("name")
        return str(name) if name else None

    def sysid_for_name(self, text: str | None, device_type: str | None = None) -> int | None:
        """Find UniFi hardware by name, for clients with no fingerprint.

        A UniFi device that appears as a *client* (a Protect camera on a switch
        port, say) has no fingerprint dev_id, so the only handle is its hostname.
        Matching is deliberately strict: a unique hit or nothing. "g3-flex"
        matches both UVC-G3-FLEX (a Protect camera) and UA-G3-Flex (an Access
        reader), and picking one at random would be inventing data.

        *device_type* filters the catalog first, which is how that particular
        ambiguity gets resolved when Protect confirms the MAC is a camera.
        """
        needle = _normalise(text)
        if not needle or len(needle) < 4:
            return None

        matches: set[int] = set()
        for sysid, entry in self.catalog().items():
            if device_type:
                types = [str(t).lower() for t in (entry.get("deviceTypes") or [])]
                types.append(str(entry.get("deviceType") or "").lower())
                if not any(device_type.lower() in t for t in types):
                    continue
            names = [(entry.get("product") or {}).get("name"), entry.get("sku")]
            names.extend(entry.get("shortnames") or [])
            if any(needle in _normalise(n) for n in names if n):
                matches.add(sysid)

        if len(matches) == 1:
            return matches.pop()
        if matches:
            log.debug("Name %r matched %d catalog entries; refusing to guess.", text, len(matches))
        return None

    def icon(self, sysid: int | None) -> IconAsset | None:
        """Cached, downscaled artwork for *sysid*, or None."""
        if sysid is None:
            return None
        entry = self.catalog().get(sysid)
        if not entry:
            return None

        images = entry.get("images") or {}
        variant = next((v for v in VARIANTS if images.get(v)), None)
        if variant is None:
            return None

        cached = self.icon_dir / f"{sysid:04x}-{variant}-{ICON_PX}.png"
        if cached.is_file():
            return _measure(cached)
        if self.offline:
            return None

        url = IMAGE_URL.format(id=entry.get("id"), variant=variant, hash=images[variant])
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            raw = response.content
        except requests.RequestException as exc:
            log.warning("Could not fetch artwork for sysid %04x (%s).", sysid, exc)
            return None

        self.icon_dir.mkdir(parents=True, exist_ok=True)
        try:
            return _downscale(raw, cached, ICON_PX)
        except AssetError as exc:
            log.warning("%s", exc)
            return None


def _pillow_image():
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise AssetError("Pillow is not installed; cannot process artwork.") from exc
    return Image


def _measure(path: Path) -> IconAsset | None:
    try:
        Image = _pillow_image()
        with Image.open(path) as image:
            return IconAsset(path=path, width=image.width, height=image.height)
    except (AssetError, OSError, ValueError):
        log.debug("Could not measure %s", path, exc_info=True)
        return None


def _render_glyph(font_path: Path, codepoint: int, color: str, dest: Path, box: int) -> IconAsset:
    """Draw a single font glyph, tightly cropped, into a transparent PNG."""
    Image = _pillow_image()
    try:
        from PIL import ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise AssetError("Pillow is not installed; cannot render glyphs.") from exc

    char = chr(codepoint)
    try:
        # Render oversized, then crop and downscale, so edges stay smooth.
        font = ImageFont.truetype(str(font_path), box * 2)
        canvas = Image.new("RGBA", (box * 4, box * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), char, font=font)
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            raise AssetError(f"Glyph U+{codepoint:04X} is empty in {font_path.name}.")
        draw.text((-bbox[0] + 4, -bbox[1] + 4), char, font=font, fill=color)
        cropped = canvas.crop(canvas.getbbox() or (0, 0, box, box))
        cropped.thumbnail((box, box), Image.LANCZOS)
        cropped.save(dest, format="PNG", optimize=True)
        return IconAsset(path=dest, width=cropped.width, height=cropped.height)
    except (OSError, ValueError) as exc:
        raise AssetError(f"Could not render glyph U+{codepoint:04X}: {exc}") from exc


def _downscale(raw: bytes, dest: Path, box: int) -> IconAsset:
    """Shrink *raw* PNG to fit *box*, preserving alpha and aspect ratio.

    Product renders arrive 1-2 MB each; trimming transparent margins first means
    the visible artwork actually fills the box rather than floating in padding.
    """
    from io import BytesIO

    Image = _pillow_image()
    try:
        with Image.open(BytesIO(raw)) as image:
            image = image.convert("RGBA")
            bbox = image.getbbox()
            if bbox:
                image = image.crop(bbox)
            image.thumbnail((box, box), Image.LANCZOS)
            image.save(dest, format="PNG", optimize=True)
            return IconAsset(path=dest, width=image.width, height=image.height)
    except (OSError, ValueError) as exc:
        raise AssetError(f"Could not process artwork: {exc}") from exc


def data_uri(path: Path) -> str:
    """base64 data URI for embedding in SVG or a draw.io style."""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
