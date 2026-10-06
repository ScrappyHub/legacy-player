from tools.memory_probe.memory_reader.reader import iter_readable_regions, read_region


DOLPHIN_EMULATED_RAM_MIN = 0x01800000
DOLPHIN_EMULATED_RAM_MAX = 0x04000000
GAMECUBE_MAIN_RAM_SIZE = 0x02000000
ZERO_CHECK_BYTES = 0x1000


def is_read_write_protection(protect: int) -> bool:
    return protect in (0x04, 0x40, 0x80)


def is_zero_filled_region(proc, region, sample_size=ZERO_CHECK_BYTES):
    read_size = min(region["region_size"], sample_size)
    if read_size <= 0:
        return True
    data = read_region(proc, region["base_address"], read_size)
    return not data or all(byte == 0 for byte in data)


def is_plausible_dolphin_ram_region(region):
    return (
        is_read_write_protection(region["protect"])
        and DOLPHIN_EMULATED_RAM_MIN
        <= region["region_size"]
        <= DOLPHIN_EMULATED_RAM_MAX
    )


def ram_region_score(region):
    score = 50 if is_read_write_protection(region["protect"]) else 0
    if region["type"] == 0x40000:
        score += 40
    elif region["type"] == 0x20000:
        score += 20
    elif region["type"] != 0x1000000:
        score += 10
    if region["region_size"] == GAMECUBE_MAIN_RAM_SIZE:
        score += 60
    elif abs(region["region_size"] - GAMECUBE_MAIN_RAM_SIZE) <= 0x00100000:
        score += 35
    else:
        score += 20
    if region["base_address"] >= 0x100000000:
        score += 5
    return score


def enrich_region(proc, region):
    enriched = dict(region)
    enriched.update(
        score=ram_region_score(region),
        zero_filled_head=is_zero_filled_region(proc, region),
        is_exact_gamecube_ram_size=region["region_size"] == GAMECUBE_MAIN_RAM_SIZE,
        is_mapped=region["type"] == 0x40000,
        is_private=region["type"] == 0x20000,
    )
    return enriched


def list_dolphin_ram_candidates(proc, limit=2048):
    candidates = [
        enrich_region(proc, region)
        for region in iter_readable_regions(proc, limit=limit)
        if is_plausible_dolphin_ram_region(region)
    ]
    return sorted(
        candidates,
        key=lambda region: (
            not region["zero_filled_head"],
            region["is_exact_gamecube_ram_size"],
            region["is_mapped"],
            region["score"],
            region["region_size"],
            region["base_address"],
        ),
        reverse=True,
    )


def find_dolphin_ram_region(proc, limit=2048):
    candidates = list_dolphin_ram_candidates(proc, limit=limit)
    for region in candidates:
        if (
            region["is_exact_gamecube_ram_size"]
            and region["is_mapped"]
            and not region["zero_filled_head"]
        ):
            return region
    for region in candidates:
        if region["is_exact_gamecube_ram_size"] and not region["zero_filled_head"]:
            return region
    return None
