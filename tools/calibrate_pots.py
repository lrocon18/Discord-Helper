"""
calibrate_pots.py — Captura a posicao dos 3 slots de pot via cursor.

Uso:
    python calibrate_pots.py

Move o cursor pro CENTRO de cada slot e aperta a tecla correspondente:

    1 = slot HP pot
    2 = slot SP pot
    3 = slot MP pot
    Q = encerrar e imprimir ratios

Output vai pro console + arquivo calibrate_pots.log na mesma pasta.
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
from datetime import datetime

user32 = ctypes.WinDLL("user32")

user32.GetCursorPos.argtypes      = [ctypes.POINTER(wt.POINT)]
user32.GetAsyncKeyState.argtypes  = [ctypes.c_int]
user32.GetAsyncKeyState.restype   = ctypes.c_short
user32.GetClientRect.argtypes     = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.ClientToScreen.argtypes    = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.GetWindowTextW.argtypes    = [wt.HWND, wt.LPWSTR, ctypes.c_int]

TITLE_PFX = "PristonTale"
LOG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate_pots.log")


def find_window():
    found = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        if user32.GetWindowTextW(hwnd, buf, 256) > 0:
            if buf.value.startswith(TITLE_PFX) and user32.IsWindowVisible(hwnd):
                found.append((hwnd, buf.value))
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else (None, None)


def get_client(hwnd):
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return r.right - r.left, r.bottom - r.top, pt.x, pt.y


def key_down(vk):
    return user32.GetAsyncKeyState(vk) & 0x8000 != 0


class Tee:
    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
    def write(self, s):
        print(s)
        self.f.write(s + "\n")
        self.f.flush()
    def close(self):
        self.f.close()


def main():
    tee = Tee(LOG_FILE)
    tee.write(f"=== calibrate_pots.log @ {datetime.now().isoformat(timespec='seconds')} ===")

    hwnd, title = find_window()
    if not hwnd:
        tee.write(f"ERRO: janela '{TITLE_PFX}*' nao encontrada.")
        tee.close()
        sys.exit(1)
    w, h, ox, oy = get_client(hwnd)
    tee.write(f"Janela: {title}")
    tee.write(f"Client area: {w}x{h} @ origem ({ox}, {oy})")
    tee.write("")
    tee.write("Move o cursor pro centro de cada slot e aperta:")
    tee.write("  1 = slot HP pot")
    tee.write("  2 = slot SP pot")
    tee.write("  3 = slot MP pot")
    tee.write("  Q = encerrar e imprimir ratios")
    tee.write("")
    tee.write("Aguardando teclas...")
    tee.write("")

    slots = {}
    keys = {0x31: '1', 0x32: '2', 0x33: '3', 0x51: 'q'}
    last_press = {vk: 0.0 for vk in keys}
    debounce = 0.3

    while True:
        now = time.monotonic()
        for vk, label in keys.items():
            if key_down(vk) and now - last_press[vk] > debounce:
                last_press[vk] = now
                if label == 'q':
                    tee.write("\n[encerrando]")
                    break
                pt = wt.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                rx = pt.x - ox
                ry = pt.y - oy
                if 0 <= rx < w and 0 <= ry < h:
                    slots[label] = (rx, ry)
                    tee.write(f"  slot {label}: pixel ({rx}, {ry}) | ratio ({rx/w:.4f}, {ry/h:.4f})")
                else:
                    tee.write(f"  slot {label}: cursor FORA da janela ({pt.x}, {pt.y}) — ignorado")
        else:
            time.sleep(0.05)
            continue
        break

    tee.write("")
    tee.write("--- COLA NO discord.py ---")
    for k, const in [('1', '_PA_R'), ('2', '_PB_R'), ('3', '_PC_R')]:
        if k in slots:
            rx, ry = slots[k]
            tee.write(f"{const} = ({rx/w:.4f}, {ry/h:.4f})  # slot {k}")
        else:
            tee.write(f"{const} = (?, ?)  # slot {k} — nao capturado")

    tee.write("")
    tee.write(f"Log salvo em: {LOG_FILE}")
    tee.close()


if __name__ == "__main__":
    main()
