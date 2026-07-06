from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict


class ImageProbeError(ValueError):
    pass


def _probe_png(data: bytes) -> Dict[str, object]:
    if len(data) < 29:
        raise ImageProbeError("truncated PNG header")
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ImageProbeError("not a PNG image")
    if data[12:16] != b"IHDR":
        raise ImageProbeError("PNG IHDR chunk not found")

    width, height = struct.unpack(">II", data[16:24])
    bit_depth = data[24]
    color_type = data[25]
    channels = {
        0: 1,  # grayscale
        2: 3,  # RGB
        3: 1,  # indexed color
        4: 2,  # grayscale + alpha
        6: 4,  # RGBA
    }.get(color_type)

    if channels is None:
        raise ImageProbeError(f"unsupported PNG color_type={color_type}")

    return {
        "format": "png",
        "width": int(width),
        "height": int(height),
        "channels": int(channels),
        "bit_depth": int(bit_depth),
        "color_type": int(color_type),
    }


def _probe_bmp(data: bytes) -> Dict[str, object]:
    if len(data) < 30:
        raise ImageProbeError("truncated BMP header")
    if data[:2] != b"BM":
        raise ImageProbeError("not a BMP image")

    width = struct.unpack("<i", data[18:22])[0]
    height = struct.unpack("<i", data[22:26])[0]
    bpp = struct.unpack("<H", data[28:30])[0]
    channels = max(1, int(bpp) // 8)

    return {
        "format": "bmp",
        "width": abs(int(width)),
        "height": abs(int(height)),
        "channels": channels,
        "bits_per_pixel": int(bpp),
    }


def _probe_jpeg(data: bytes) -> Dict[str, object]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ImageProbeError("not a JPEG image")

    pos = 2
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3,
        0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB,
        0xCD, 0xCE, 0xCF,
    }

    while pos < len(data):
        # Find marker prefix.
        while pos < len(data) and data[pos] != 0xFF:
            pos += 1
        if pos >= len(data):
            break

        # Skip fill bytes.
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            break

        marker = data[pos]
        pos += 1

        # Markers without payload length.
        if marker in {0x01} or 0xD0 <= marker <= 0xD9:
            continue

        # SOS or EOI before SOF means dimensions were not found.
        if marker in {0xDA, 0xD9}:
            break

        if pos + 2 > len(data):
            break
        segment_length = struct.unpack(">H", data[pos:pos + 2])[0]
        if segment_length < 2:
            raise ImageProbeError(f"invalid JPEG segment length={segment_length}")

        segment_start = pos + 2
        segment_end = pos + segment_length
        if segment_end > len(data):
            break

        if marker in sof_markers:
            if segment_start + 6 > len(data):
                raise ImageProbeError("truncated JPEG SOF segment")
            precision = data[segment_start]
            height = struct.unpack(">H", data[segment_start + 1:segment_start + 3])[0]
            width = struct.unpack(">H", data[segment_start + 3:segment_start + 5])[0]
            components = data[segment_start + 5]
            return {
                "format": "jpeg",
                "width": int(width),
                "height": int(height),
                "channels": int(components),
                "precision": int(precision),
                "sof_marker": f"0x{marker:02x}",
            }

        pos = segment_end

    raise ImageProbeError("JPEG SOF marker not found in header scan")


def probe_image(path: str, max_read_bytes: int = 1024 * 1024) -> Dict[str, object]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"image not found: {path}")
    if not p.is_file():
        raise ImageProbeError(f"image path is not a file: {path}")

    data = p.read_bytes()[:max_read_bytes]
    if len(data) < 8:
        raise ImageProbeError(f"image file is too small: {path}")

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        meta = _probe_png(data)
    elif data.startswith(b"\xff\xd8"):
        meta = _probe_jpeg(data)
    elif data.startswith(b"BM"):
        meta = _probe_bmp(data)
    else:
        raise ImageProbeError("unsupported image format; supported: JPEG, PNG, BMP")

    meta["path"] = str(p)
    meta["size_bytes"] = int(p.stat().st_size)
    return meta
