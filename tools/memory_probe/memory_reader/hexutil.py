def bytes_to_hex(data):
    if data is None:
        return None
    return data.hex()


def short_hex(data, max_len=64):
    if data is None:
        return None

    hex_data = data.hex()
    if len(hex_data) <= max_len:
        return hex_data

    return hex_data[:max_len]