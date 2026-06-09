"""
peb_mask.py — Deep PEB Unlinking e Ocultação.
Além de renomear Command Line e ImagePathName, removemos a DLL principal 
e o .exe da lista LDR (InLoadOrder, InMemoryOrder, InInitializationOrder).
"""

import ctypes
import ctypes.wintypes as wt
import sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll    = ctypes.WinDLL("ntdll",    use_last_error=False)

# ── Estruturas PEB/LDR ────────────────────────────────────────────────────────

class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length",        wt.USHORT),
        ("MaximumLength", wt.USHORT),
        ("Buffer",        ctypes.c_void_p),
    ]

class LIST_ENTRY(ctypes.Structure):
    pass
LIST_ENTRY._fields_ = [
    ("Flink", ctypes.POINTER(LIST_ENTRY)),
    ("Blink", ctypes.POINTER(LIST_ENTRY)),
]

class LDR_DATA_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("InLoadOrderLinks",           LIST_ENTRY),
        ("InMemoryOrderLinks",         LIST_ENTRY),
        ("InInitializationOrderLinks", LIST_ENTRY),
        ("DllBase",                    ctypes.c_void_p),
        ("EntryPoint",                 ctypes.c_void_p),
        ("SizeOfImage",                wt.ULONG),
        ("FullDllName",                UNICODE_STRING),
        ("BaseDllName",                UNICODE_STRING),
    ]

class PEB_LDR_DATA(ctypes.Structure):
    _fields_ = [
        ("Length",                          wt.ULONG),
        ("Initialized",                     wt.BOOLEAN),
        ("SsHandle",                        ctypes.c_void_p),
        ("InLoadOrderModuleList",           LIST_ENTRY),
        ("InMemoryOrderModuleList",         LIST_ENTRY),
        ("InInitializationOrderModuleList", LIST_ENTRY),
    ]

class RTL_USER_PROCESS_PARAMETERS(ctypes.Structure):
    _fields_ = [
        ("_pad",          ctypes.c_byte * 0x60),
        ("ImagePathName", UNICODE_STRING),
        ("CommandLine",   UNICODE_STRING),
    ]

class PEB(ctypes.Structure):
    _fields_ = [
        ("Reserved1",               ctypes.c_byte * 2),
        ("BeingDebugged",           ctypes.c_byte),
        ("Reserved2",               ctypes.c_byte * 1),
        ("Reserved3",               ctypes.c_void_p * 2),
        ("Ldr",                     ctypes.POINTER(PEB_LDR_DATA)),
        ("ProcessParameters",       ctypes.POINTER(RTL_USER_PROCESS_PARAMETERS)),
    ]

class PROCESS_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Reserved1",       ctypes.c_void_p),
        ("PebBaseAddress",  ctypes.POINTER(PEB)),
        ("Reserved2",       ctypes.c_void_p * 2),
        ("UniqueProcessId", ctypes.c_ulong),
        ("Reserved3",       ctypes.c_void_p),
    ]

def _patch_unicode_string(us: UNICODE_STRING, new_text: str) -> None:
    encoded = (new_text + "\x00").encode("utf-16-le")
    max_bytes = us.MaximumLength
    if len(encoded) > max_bytes:
        encoded = encoded[: max_bytes - 2] + b"\x00\x00"
    buf_addr = us.Buffer
    if buf_addr is None:
        return
    old_prot = wt.DWORD(0)
    kernel32.VirtualProtect(buf_addr, len(encoded), 0x04, ctypes.byref(old_prot))
    ctypes.memmove(buf_addr, encoded, len(encoded))
    kernel32.VirtualProtect(buf_addr, len(encoded), old_prot, ctypes.byref(old_prot))
    us.Length = len(encoded) - 2

def _unlink(entry: LIST_ENTRY) -> None:
    """Remove um nó da doubly-linked list (Flink/Blink)."""
    flink = entry.Flink
    blink = entry.Blink
    if flink: flink.contents.Blink = blink
    if blink: blink.contents.Flink = flink
    # Zera nossos próprios ponteiros para o AC não seguir de volta.
    entry.Flink = ctypes.POINTER(LIST_ENTRY)()
    entry.Blink = ctypes.POINTER(LIST_ENTRY)()

def mask_process(fake_name: str = r"C:\Users\Public\Discord\Discord.exe",
                 fake_cmdline: str = r'"C:\Users\Public\Discord\Discord.exe"') -> bool:
    pbi = PROCESS_BASIC_INFORMATION()
    status = ntdll.NtQueryInformationProcess(
        kernel32.GetCurrentProcess(),
        0, ctypes.byref(pbi), ctypes.sizeof(pbi), None
    )
    if status != 0:
        return False

    peb = pbi.PebBaseAddress.contents
    params = peb.ProcessParameters.contents

    # 1. Zera flags de debug
    peb.BeingDebugged = 0

    # 2. Patch do ImagePathName / CommandLine
    _patch_unicode_string(params.ImagePathName, fake_name)
    _patch_unicode_string(params.CommandLine, fake_cmdline)

    # 3. Deep Unlinking (LDR)
    # Vamos deslinkar nós mesmos ("python.exe" ou "discord-helper.exe") e a dll nativa.
    ldr = peb.Ldr.contents
    head = ldr.InLoadOrderModuleList
    
    current = head.Flink
    while current and ctypes.addressof(current.contents) != ctypes.addressof(head):
        entry = ctypes.cast(current, ctypes.POINTER(LDR_DATA_TABLE_ENTRY)).contents
        
        # Lê o nome da DLL/EXE desse nó
        name_buf = entry.BaseDllName.Buffer
        name_len = entry.BaseDllName.Length
        mod_name = ""
        if name_buf and name_len > 0:
            raw_bytes = ctypes.string_at(name_buf, name_len)
            mod_name = raw_bytes.decode('utf-16-le', errors='ignore').lower()

        # Alvos para unlinking (não pode deslinkar ntdll/kernel32 senão dá crash)
        if "python" in mod_name or "discord" in mod_name:
            # Unlink das 3 listas do PEB
            _unlink(entry.InLoadOrderLinks)
            _unlink(entry.InMemoryOrderLinks)
            _unlink(entry.InInitializationOrderLinks)
            
            # Limpa as Unicode Strings para garantir
            entry.FullDllName.Length = 0
            entry.FullDllName.MaximumLength = 0
            entry.BaseDllName.Length = 0
            entry.BaseDllName.MaximumLength = 0

        current = current.contents.Flink

    return True

if __name__ == "__main__":
    ok = mask_process()
    print("PEB Unlinked & Patched" if ok else "PEB patch FAILED")
