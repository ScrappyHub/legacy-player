from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from tools.memory_probe.memory_reader.reader import read_region


DEFAULT_PREVIEW_HEX_BYTES = 32
DEFAULT_MAX_WINDOW_COUNT = 1024
DEFAULT_ALIGNMENT = 64


def _align_down(value: int, alignment: int) -> int:
    if alignment <= 1:
        return value
    return value - (value % alignment)


def build_sample_offsets(
    region_size: int,
    window_size: int,
    max_scan_bytes: int,
    max_window_count: int = DEFAULT_MAX_WINDOW_COUNT,
    alignment: int = DEFAULT_ALIGNMENT,
) -> List[int]:
    """
    Build a deterministic sparse set of sample offsets across the full RAM region.

    Design:
    - spread offsets across the entire region
    - cap total windows with max_window_count
    - use max_scan_bytes as a scan budget
    - align offsets for stability across runs
    """
    if region_size <= 0:
        return []

    if window_size <= 0:
        raise ValueError("window_size must be > 0")

    if max_scan_bytes <= 0:
        raise ValueError("max_scan_bytes must be > 0")

    effective_window_size = min(window_size, region_size)
    max_start = max(0, region_size - effective_window_size)

    requested_window_count = max(1, max_scan_bytes // effective_window_size)
    window_count = max(1, min(requested_window_count, max_window_count))

    if window_count == 1 or max_start == 0:
        return [0]

    raw_offsets: List[int] = []
    for i in range(window_count):
        ratio = i / (window_count - 1)
        raw = int(round(max_start * ratio))
        aligned = _align_down(raw, alignment)
        if aligned > max_start:
            aligned = max_start
        raw_offsets.append(aligned)

    offsets = sorted(set(raw_offsets))

    if offsets and offsets[0] != 0:
        offsets.insert(0, 0)

    aligned_end = _align_down(max_start, alignment)
    if aligned_end > max_start:
        aligned_end = max_start

    if offsets and offsets[-1] != aligned_end:
        offsets.append(aligned_end)

    offsets = sorted(set(min(max_start, off) for off in offsets))

    if not offsets:
        return [0]

    return offsets


def _serialize_window(
    base_address: int,
    window_offset: int,
    window_size: int,
    data: Optional[bytes],
    preview_hex_bytes: int,
) -> Dict:
    absolute_address = base_address + window_offset

    if data is None:
        return {
            "window_offset": window_offset,
            "absolute_address": hex(absolute_address),
            "window_size": window_size,
            "data_sha256": None,
            "preview_hex": None,
            "data_hex": None,
        }

    return {
        "window_offset": window_offset,
        "absolute_address": hex(absolute_address),
        "window_size": len(data),
        "data_sha256": hashlib.sha256(data).hexdigest(),
        "preview_hex": data[:preview_hex_bytes].hex(),
        "data_hex": data.hex(),
    }


def read_sampled_snapshot(
    proc,
    ram_region: Dict,
    window_size: int,
    max_scan_bytes: int,
    preview_hex_bytes: int = DEFAULT_PREVIEW_HEX_BYTES,
    max_window_count: int = DEFAULT_MAX_WINDOW_COUNT,
    alignment: int = DEFAULT_ALIGNMENT,
) -> Dict:
    """
    Read a deterministic sparse sample across the selected Dolphin RAM region.
    """
    base_address = ram_region["base_address"]
    region_size = ram_region["region_size"]

    offsets = build_sample_offsets(
        region_size=region_size,
        window_size=window_size,
        max_scan_bytes=max_scan_bytes,
        max_window_count=max_window_count,
        alignment=alignment,
    )

    sampled_windows: List[Dict] = []

    for offset in offsets:
        remaining = max(0, region_size - offset)
        current_window_size = min(window_size, remaining)

        if current_window_size <= 0:
            continue

        data = read_region(proc, base_address + offset, current_window_size)

        sampled_windows.append(
            _serialize_window(
                base_address=base_address,
                window_offset=offset,
                window_size=current_window_size,
                data=data,
                preview_hex_bytes=preview_hex_bytes,
            )
        )

    return {
        "base_address": hex(base_address),
        "region_size": region_size,
        "protect": hex(ram_region["protect"]),
        "type": hex(ram_region["type"]),
        "sample_window_count": len(sampled_windows),
        "sample_window_size": window_size,
        "max_scan_bytes": max_scan_bytes,
        "alignment": alignment,
        "sample_offsets_preview": offsets[:32],
        "sampled_windows": sampled_windows,
    }