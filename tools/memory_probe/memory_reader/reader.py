import ctypes
from ctypes import wintypes


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

MEM_COMMIT = 0x1000

PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

ReadProcessMemory = kernel32.ReadProcessMemory
ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
ReadProcessMemory.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

VirtualQueryEx = kernel32.VirtualQueryEx
VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
]
VirtualQueryEx.restype = ctypes.c_size_t


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def _open_process_for_read(pid):
    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    return handle


def read_region(proc, address, size):
    handle = _open_process_for_read(proc.pid)
    if not handle:
        return None

    try:
        buf = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)

        ok = ReadProcessMemory(
            handle,
            ctypes.c_void_p(address),
            buf,
            size,
            ctypes.byref(bytes_read),
        )

        if not ok or bytes_read.value == 0:
            return None

        return bytes(buf.raw[: bytes_read.value])

    finally:
        CloseHandle(handle)


def iter_readable_regions(proc, limit=256):
    handle = _open_process_for_read(proc.pid)
    if not handle:
        return []

    regions = []

    try:
        mbi = MEMORY_BASIC_INFORMATION()
        address = 0
        max_address = 0x00007FFFFFFF0000

        while address < max_address and len(regions) < limit:
            result = VirtualQueryEx(
                handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi),
            )

            if result == 0:
                break

            base = int(mbi.BaseAddress or 0)
            size = int(mbi.RegionSize or 0)
            protect = int(mbi.Protect)
            state = int(mbi.State)

            readable = (
                state == MEM_COMMIT
                and protect != PAGE_NOACCESS
                and (protect & PAGE_GUARD) == 0
            )

            if readable and size > 0:
                regions.append({
                    "base_address": base,
                    "region_size": size,
                    "protect": protect,
                    "type": int(mbi.Type),
                })

            next_address = base + size
            if next_address <= address:
                break

            address = next_address

        return regions

    finally:
        CloseHandle(handle)