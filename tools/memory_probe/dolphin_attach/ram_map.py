from tools.memory_probe.memory_reader.reader import iter_readable_regions, read_region


DOLPHIN_EMULATED_RAM_MIN = 0x01800000   # 24 MiB
DOLPHIN_EMULATED_RAM_MAX = 0x04000000   # 64 MiB
ZERO_CHECK_BYTES = 0x1000


def ram_region_score(region):
    protect = region["protect"]
    region_type = region["type"]
    region_size = region["region_size"]
    base = region["base_address"]

    score = 0

    if protect in (0x04, 0x40, 0x80):
        score += 50

    if region_type == 0x40000:
        score += 25
    elif region_type != 0x1000000:
        score += 15

    if DOLPHIN_EMULATED_RAM_MIN <= region_size <= DOLPHIN_EMULATED_RAM_MAX:
        score += 35
    elif region_size >= 0x01000000:
        score += 20
    elif region_size >= 0x00100000:
        score += 10

    if base >= 0x100000000:
        score += 5

    return score


def is_plausible_dolphin_ram_region(region):
    region_size = region["region_size"]
    protect = region["protect"]

    if protect not in (0x04, 0x40, 0x80):
        return False

    if region_size < DOLPHIN_EMULATED_RAM_MIN:
        return False

    if region_size > DOLPHIN_EMULATED_RAM_MAX:
        return False

    return True


def is_zero_filled_region(proc, region, sample_size=ZERO_CHECK_BYTES):
    base = region["base_address"]
    region_size = region["region_size"]
    read_size = min(region_size, sample_size)

    if read_size <= 0:
        return True

    data = read_region(proc, base, read_size)
    if not data:
        return True

    return all(b == 0 for b in data)


def enrich_region(proc, region):
    enriched = dict(region)
    enriched["score"] = ram_region_score(region)
    enriched["zero_filled_head"] = is_zero_filled_region(proc, region)
    return enriched


def find_dolphin_ram_region(proc, limit=512):
    regions = iter_readable_regions(proc, limit=limit)
    candidates = []

    for region in regions:
        if not is_plausible_dolphin_ram_region(region):
            continue

        enriched = enrich_region(proc, region)

        # Prefer non-zero regions only.
        if enriched["zero_filled_head"]:
            continue

        candidates.append(enriched)

    if not candidates:
        # Fallback: return the best plausible region even if zero-filled,
        # so callers still get something inspectable.
        fallback = []
        for region in regions:
            if not is_plausible_dolphin_ram_region(region):
                continue
            fallback.append(enrich_region(proc, region))

        if not fallback:
            return None

        fallback.sort(
            key=lambda r: (
                r["score"],
                r["region_size"],
                r["base_address"],
            ),
            reverse=True,
        )
        return fallback[0]

    candidates.sort(
        key=lambda r: (
            r["score"],
            r["region_size"],
            r["base_address"],
        ),
        reverse=True,
    )

    return candidates[0]


def list_dolphin_ram_candidates(proc, limit=512):
    regions = iter_readable_regions(proc, limit=limit)
    candidates = []

    for region in regions:
        if not is_plausible_dolphin_ram_region(region):
            continue

        candidates.append(enrich_region(proc, region))

    candidates.sort(
        key=lambda r: (
            r["score"],
            r["region_size"],
            r["base_address"],
        ),
        reverse=True,
    )

    return candidates