import hashlib
from typing import Dict, List


PREVIEW_HEX_BYTES = 32


def build_changed_pages(snapshot_a: Dict, snapshot_b: Dict) -> List[Dict]:
    changed_pages: List[Dict] = []

    windows_a = {
        int(w["page_offset"]): w
        for w in snapshot_a.get("sampled_pages", [])
    }
    windows_b = {
        int(w["page_offset"]): w
        for w in snapshot_b.get("sampled_pages", [])
    }

    all_offsets = sorted(set(windows_a.keys()) | set(windows_b.keys()))

    for offset in all_offsets:
        a = windows_a.get(offset)
        b = windows_b.get(offset)

        if a is None or b is None:
            changed_pages.append({
                "page_offset": offset,
                "reason": "missing_in_one_snapshot",
            })
            continue

        a_hex = a.get("data_hex")
        b_hex = b.get("data_hex")

        if a_hex == b_hex:
            continue

        changed_byte_offsets: List[int] = []
        changed_byte_count = 0

        if a_hex is not None and b_hex is not None:
            a_bytes = bytes.fromhex(a_hex)
            b_bytes = bytes.fromhex(b_hex)
            compare_len = min(len(a_bytes), len(b_bytes))

            for i in range(compare_len):
                if a_bytes[i] != b_bytes[i]:
                    changed_byte_offsets.append(i)

            changed_byte_count = len(changed_byte_offsets)

        changed_pages.append({
            "page_offset": offset,
            "absolute_address": a.get("absolute_address"),
            "page_size": a.get("page_size"),
            "changed_byte_count": changed_byte_count,
            "changed_byte_offsets_preview": changed_byte_offsets[:128],
            "before_sha256": a.get("data_sha256"),
            "after_sha256": b.get("data_sha256"),
            "before_preview_hex": (a_hex[: PREVIEW_HEX_BYTES * 2] if a_hex else None),
            "after_preview_hex": (b_hex[: PREVIEW_HEX_BYTES * 2] if b_hex else None),
        })

    return changed_pages


def summarize_compare_results(compare_results: List[Dict]) -> List[Dict]:
    out: List[Dict] = []

    for item in compare_results:
        out.append({
            "snapshot_name": item["snapshot_name"],
            "changed_page_count": item["changed_page_count"],
            "changed_byte_count": item["changed_byte_count"],
        })

    return out