"""
peb_mask.py — Renomeia o processo no PEB (ProcessParameters->ImagePathName
e CommandLine) para enganar ferramentas que listam processos via NtQueryInformationProcess.
Não modifica disco, só memória do processo atual.
"""
import ctypes
import ctypes.wintypes as wt
import sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll    = ctypes.WinDLL("ntdll",    use_last_error=False)

# ── estruturas mínimas ────────────────────────────────────────────────────────

class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length",        wt.USHORT),
        ("MaximumLength", wt.USHORT),
        # FIX-1: c_void_p em vez de c_wchar_p.
        # c_wchar_p faz o ctypes achar que é dono desse ponteiro e pode tentar
        # gerenciar (ou liberar) a memória ao fazer cast — comportamento undefined.
        # c_void_p é um inteiro bruto de 8 bytes: lê o endereço, não mexe na memória.
        ("Buffer",        ctypes.c_void_p),
    ]

# FIX-2: offset explícito para x64.
# No Windows x64, RTL_USER_PROCESS_PARAMETERS tem:
#   0x00–0x5F  campos que não precisamos tocar (MaximumLength, Flags, handles, etc.)
#   0x60       ImagePathName  (UNICODE_STRING, 16 bytes)
#   0x70       CommandLine    (UNICODE_STRING, 16 bytes)
# O padding de 0x60 bytes garante que estamos no campo certo independente de
# como o ctypes decide alinhar os campos intermediários.
class RTL_USER_PROCESS_PARAMETERS(ctypes.Structure):
    _fields_ = [
        ("_pad",          ctypes.c_byte * 0x60),  # skip até ImagePathName
        ("ImagePathName", UNICODE_STRING),
        ("CommandLine",   UNICODE_STRING),
    ]

class PEB(ctypes.Structure):
    _fields_ = [
        ("Reserved1",               ctypes.c_byte * 2),
        ("BeingDebugged",           ctypes.c_byte),
        ("Reserved2",               ctypes.c_byte * 1),
        ("Reserved3",               ctypes.c_void_p * 2),
        ("Ldr",                     ctypes.c_void_p),
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

# ── helper: sobrescreve UNICODE_STRING in-place ───────────────────────────────

def _patch_unicode_string(us: UNICODE_STRING, new_text: str) -> None:
    """
    Escreve new_text direto no buffer existente da UNICODE_STRING.
    Se new_text for maior que MaximumLength, trunca (melhor que crash).
    """
    encoded = (new_text + "\x00").encode("utf-16-le")
    max_bytes = us.MaximumLength  # bytes disponíveis no buffer original

    if len(encoded) > max_bytes:
        # Trunca pra caber — sem alocação nova pra não deixar rastro no heap
        encoded = encoded[: max_bytes - 2] + b"\x00\x00"

    # Buffer agora é c_void_p: o valor JÁ é o endereço inteiro, sem cast extra.
    buf_addr = us.Buffer
    if buf_addr is None:
        return

    # VirtualProtect pra garantir write permission (raro, mas existe)
    old_prot = wt.DWORD(0)
    PAGE_READWRITE = 0x04
    kernel32.VirtualProtect(buf_addr, len(encoded), PAGE_READWRITE, ctypes.byref(old_prot))

    ctypes.memmove(buf_addr, encoded, len(encoded))

    # Restaura proteção original
    kernel32.VirtualProtect(buf_addr, len(encoded), old_prot, ctypes.byref(old_prot))

    # Atualiza Length (bytes, não chars)
    us.Length = len(encoded) - 2  # sem o null terminator


def mask_process(fake_name: str = r"C:\Users\Public\Discord\Discord.exe",
                 fake_cmdline: str = r'"C:\Users\Public\Discord\Discord.exe"') -> bool:
    """
    Altera ImagePathName e CommandLine no PEB do processo atual.
    Retorna True em sucesso.
    """
    pbi = PROCESS_BASIC_INFORMATION()
    status = ntdll.NtQueryInformationProcess(
        kernel32.GetCurrentProcess(),
        0,                          # ProcessBasicInformation
        ctypes.byref(pbi),
        ctypes.sizeof(pbi),
        None,
    )
    if status != 0:
        return False

    peb = pbi.PebBaseAddress.contents
    params = peb.ProcessParameters.contents

    # FIX-3: zera BeingDebugged.
    # Se o processo já foi attachado por um debugger em algum momento (mesmo que
    # já desconectado), esse byte fica 1. Qualquer anti-cheat que lê o PEB
    # diretamente via NtQueryInformationProcess (ou até ReadProcessMemory de
    # outro processo) detecta isso e pode banir ou encerrar a sessão.
    peb.BeingDebugged = 0

    _patch_unicode_string(params.ImagePathName, fake_name)
    _patch_unicode_string(params.CommandLine,   fake_cmdline)
    return True


if __name__ == "__main__":
    ok = mask_process()
    print("PEB patched" if ok else "PEB patch FAILED")
    input("enter...")
