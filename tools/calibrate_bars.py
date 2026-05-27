"""
calibrate_bars.py — Captura interativa do topo e base das barras HP/SP/MP.

Uso:
    python calibrate_bars.py

Move o cursor pra cada ponto e aperta a tecla:

    Q = topo HP        A = base HP
    W = topo SP        S = base SP
    E = topo MP        D = base MP
    X = encerrar e imprimir ratios

Output vai pro console + arquivo calibrate_bars.log na mesma pasta.
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
LOG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrate_bars.log")


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
    tee.write(f"=== calibrate_bars.log @ {datetime.now().isoformat(timespec='seconds')} ===")

    hwnd, title = find_window()
    if not hwnd:
        tee.write(f"ERRO: janela '{TITLE_PFX}*' nao encontrada. Abre o jogo primeiro.")
        tee.close()
        sys.exit(1)
    w, h, ox, oy = get_client(hwnd)
    tee.write(f"Janela: {title}")
    tee.write(f"Client area: {w}x{h} @ origem ({ox}, {oy})")
    tee.write("")
    tee.write("Move o cursor e aperte a tecla pra capturar:")
    tee.write("  Q = topo HP    A = base HP")
    tee.write("  W = topo SP    S = base SP")
    tee.write("  E = topo MP    D = base MP")
    tee.write("  X = encerrar e imprimir ratios")
    tee.write("")
    tee.write("Aguardando teclas...")
    tee.write("")

    # vk: (label, dict_key)
    keys = {
        0x51: ("topo HP", "hp_top"), 0x41: ("base HP", "hp_bot"),
        0x57: ("topo SP", "sp_top"), 0x53: ("base SP", "sp_bot"),
        0x45: ("topo MP", "mp_top"), 0x44: ("base MP", "mp_bot"),
        0x58: ("quit",    "quit"),
    }
    last_press = {vk: 0.0 for vk in keys}
    debounce = 0.3
    captured = {}

    while True:
        now = time.monotonic()
        for vk, (label, slot) in keys.items():
            if key_down(vk) and now - last_press[vk] > debounce:
                last_press[vk] = now
                if slot == "quit":
                    tee.write("\n[encerrando]")
                    break
                pt = wt.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                rx = pt.x - ox
                ry = pt.y - oy
                if 0 <= rx < w and 0 <= ry < h:
                    captured[slot] = (rx, ry)
                    tee.write(f"  {label:<10} -> pixel ({rx}, {ry}) | ratio ({rx/w:.4f}, {ry/h:.4f})")
                else:
                    tee.write(f"  {label:<10} -> cursor FORA da janela ({pt.x}, {pt.y}) — ignorado")
        else:
            time.sleep(0.05)
            continue
        break  # saiu do for via 'X'

    tee.write("")
    tee.write("--- COLA NO discord.py ---")
    tee.write("# (x_fallback_ratio, y_top_ratio, y_bot_ratio)")

    for prefix, label_top, label_bot, const_name in [
        ("hp", "hp_top", "hp_bot", "_ZA_R"),
        ("sp", "sp_top", "sp_bot", "_ZB_R"),
        ("mp", "mp_top", "mp_bot", "_ZC_R"),
    ]:
        t = captured.get(label_top)
        b = captured.get(label_bot)
        if t and b:
            x_avg = (t[0] + b[0]) / 2
            x_r = x_avg / w
            yt_r = t[1] / h
            yb_r = b[1] / h
            tee.write(f"{const_name} = ({x_r:.4f}, {yt_r:.4f}, {yb_r:.4f})  # {prefix.upper()}")
        else:
            tee.write(f"{const_name} = (?, ?, ?)  # {prefix.upper()} — faltou capturar topo ou base")

    tee.write("")
    tee.write(f"Log salvo em: {LOG_FILE}")
    tee.close()


if __name__ == "__main__":
    main()
