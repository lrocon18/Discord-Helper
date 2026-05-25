"""
arduino_wrap.py — Link USB CDC para Arduino Leonardo agindo como HID dongle.
Substitui o driver Interception. Toda a lógica de timing fica no Python;
Arduino só executa primitivas atômicas (key down/up, mouse down/up, move).

Mesma porta USB do Leonardo expõe DUAS interfaces:
    - CDC virtual serial: Python escreve comandos aqui (pyserial)
    - HID Keyboard + Mouse: Arduino re-emite como input físico no SO

Protocolo ASCII, terminador '\\n':
    KD<hex>     key down  — hex = Arduino keycode (não VK do Windows)
    KU<hex>     key up
    MDL / MDR   mouse left/right button down
    MUL / MUR   mouse left/right button up
    M<dx>,<dy>  mouse move relative (signed decimal)
    P           ping → Arduino responde "OK\\n"

Conexão:
    Host PC ── USB ── Arduino Leonardo
                       ├─ CDC (Python escreve)
                       └─ HID (PC recebe como teclado/mouse)
"""
from __future__ import annotations

import random
import time
import threading


# ── Mapa VK do Windows → keycode da Arduino Keyboard library ──────────────────
# Arduino Keyboard.h usa ASCII pra letras/dígitos (lowercase) e constantes
# especiais (KEY_*) pra funcionais/setas/modificadores. Tabela abaixo cobre
# todas as teclas que o discord.py manda.

_VK_TO_ARDUINO: dict[int, int] = {
    # Function keys (KEY_F1 = 0xC2 ... KEY_F12 = 0xCD)
    0x70: 0xC2, 0x71: 0xC3, 0x72: 0xC4, 0x73: 0xC5,
    0x74: 0xC6, 0x75: 0xC7, 0x76: 0xC8, 0x77: 0xC9,
    0x78: 0xCA, 0x79: 0xCB, 0x7A: 0xCC, 0x7B: 0xCD,
    # Modifiers
    0x10: 0x81,  # SHIFT  → KEY_LEFT_SHIFT
    0x11: 0x80,  # CTRL   → KEY_LEFT_CTRL
    0x12: 0x82,  # ALT    → KEY_LEFT_ALT
    # Control keys
    0x0D: 0xB0,  # ENTER  → KEY_RETURN
    0x1B: 0xB1,  # ESC    → KEY_ESC
    0x20: 0x20,  # SPACE  → ASCII space
    0x08: 0xB2,  # BACKSP → KEY_BACKSPACE
    0x09: 0xB3,  # TAB    → KEY_TAB
    # Arrows
    0x25: 0xD8,  # LEFT
    0x26: 0xDA,  # UP
    0x27: 0xD7,  # RIGHT
    0x28: 0xD9,  # DOWN
    # Digits 0-9: VK 0x30-0x39 → ASCII '0'-'9' (0x30-0x39, mesma coisa)
    **{0x30 + i: 0x30 + i for i in range(10)},
    # Letters A-Z: VK 0x41-0x5A → ASCII lowercase 'a'-'z' (0x61-0x7A)
    # Keyboard.press handles modifier state separately; lowercase is fine.
    **{0x41 + i: 0x61 + i for i in range(26)},
}


def _vk_to_ardkey(vk: int) -> int:
    if vk in _VK_TO_ARDUINO:
        return _VK_TO_ARDUINO[vk]
    raise ValueError(f"VK {vk:#x} sem mapeamento Arduino")


# Nomes amigáveis → VK (mesma tabela que estava no interception_wrap)
_NAMED_VK: dict[str, int] = {
    **{str(i): ord(str(i)) for i in range(10)},
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"},
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "enter": 0x0D, "space": 0x20, "esc": 0x1B,
    "tab": 0x09, "backspace": 0x08,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}


def resolve_vk(key) -> int:
    if isinstance(key, int):
        return key
    s = str(key).lower().replace("key.", "")
    if s in _NAMED_VK:
        return _NAMED_VK[s]
    raise ValueError(f"Tecla desconhecida: {key!r}")


# ── Leonardo detection ───────────────────────────────────────────────────────
# VID/PID conhecidos do Leonardo (oficial + clones comuns).

_LEONARDO_IDS: set[tuple[int, int]] = {
    (0x046D, 0xC077),  # Spoofed — Logitech M105 (running)
    (0x2341, 0x8036),  # Arduino LLC — Leonardo (running)
    (0x2341, 0x0036),  # Arduino LLC — Leonardo (bootloader)
    (0x2341, 0x8037),  # Arduino LLC — Micro
    (0x2341, 0x0037),  # Arduino LLC — Micro bootloader
    (0x2A03, 0x8036),  # Arduino SA — Leonardo
    (0x2A03, 0x0036),
    (0x2A03, 0x8037),  # Arduino SA — Micro
    (0x2A03, 0x0037),
    (0x1B4F, 0x9206),  # SparkFun Pro Micro (3.3V)
    (0x1B4F, 0x9205),  # SparkFun Pro Micro bootloader
    (0x1B4F, 0x9204),  # SparkFun Pro Micro (5V)
    (0x1B4F, 0x9203),
}


def _auto_detect_port() -> str | None:
    """Procura o Leonardo (ou clone) conectado. Retorna device path (ex:
    'COM5') ou None se nenhum match."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    for p in list_ports.comports():
        vid, pid = p.vid, p.pid
        if vid is None:
            continue
        if (vid, pid) in _LEONARDO_IDS:
            return p.device
    return None


# ── Wrapper principal ────────────────────────────────────────────────────────

class ArduinoHID:
    """
    Substituto drop-in da classe Interception.

    Uso:
        with ArduinoHID() as ic:
            ic.send_key('f1')
            ic.send_mouse_click(right=True)
    """

    def __init__(self, port: str | None = None, baud: int = 115200,
                 write_timeout: float = 0.5,
                 toggle_callback=None, kill_callback=None) -> None:
        """
        toggle_callback: chamada sem args quando o Arduino envia "TOGGLE\\n"
        (botão físico, short press).
        kill_callback:   chamada sem args quando o Arduino envia "KILL\\n"
        (botão físico, long press ≥1s).
        """
        import serial
        if port is None:
            port = _auto_detect_port()
        if port is None:
            raise RuntimeError(
                "Arduino Leonardo não encontrado. "
                "Confira se o cabo USB está plugado e o firmware foi gravado."
            )
        self._port_name = port
        self._ser = serial.Serial(
            port=port, baudrate=baud, bytesize=8, parity='N', stopbits=1,
            timeout=0.1, write_timeout=write_timeout,
        )
        self._lock = threading.Lock()
        self._toggle_cb = toggle_callback
        self._kill_cb = kill_callback
        self._stop_reader = False
        # Pequena pausa pro Arduino terminar reset após open do CDC/UART
        time.sleep(0.4)
        try:
            self._ser.reset_input_buffer()
            self._ser.reset_output_buffer()
        except Exception:
            pass
        # Reader thread — escuta eventos do Arduino (botão físico, status)
        self._reader = threading.Thread(target=self._read_loop,
                                        daemon=True, name="ArdReader")
        self._reader.start()

    def _read_loop(self) -> None:
        buf = bytearray()
        while not self._stop_reader and self._ser is not None:
            try:
                chunk = self._ser.read(64)
            except Exception:
                break
            if not chunk:
                continue
            buf.extend(chunk)
            while b"\n" in buf:
                line, _, rest = buf.partition(b"\n")
                buf = bytearray(rest)
                msg = line.decode("ascii", errors="replace").strip()
                if msg == "TOGGLE" and self._toggle_cb is not None:
                    try:
                        self._toggle_cb()
                    except Exception:
                        pass
                elif msg == "KILL" and self._kill_cb is not None:
                    try:
                        self._kill_cb()
                    except Exception:
                        pass

    @property
    def port(self) -> str:
        return self._port_name

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self._stop_reader = True
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    # ── Transport primitivo ──────────────────────────────────────────────────

    def _write_line(self, line: str) -> None:
        if self._ser is None:
            return
        data = (line + "\n").encode("ascii")
        with self._lock:
            try:
                self._ser.write(data)
            except Exception:
                pass

    # ── Keyboard ─────────────────────────────────────────────────────────────

    def send_key(self, key, hold_sec: float = 0.0) -> None:
        """Pressiona e solta uma tecla. hold_sec entre press e release."""
        vk = resolve_vk(key)
        ak = _vk_to_ardkey(vk)
        self._write_line(f"KD{ak:02X}")
        if hold_sec > 0:
            time.sleep(hold_sec)
        self._write_line(f"KU{ak:02X}")

    # ── Mouse ────────────────────────────────────────────────────────────────

    def move_relative(self, dx: int, dy: int) -> None:
        # Arduino Mouse.move() aceita int8 (-127..127). Para deltas maiores,
        # quebra em vários comandos.
        STEP = 100
        while dx or dy:
            sx = max(-STEP, min(STEP, dx))
            sy = max(-STEP, min(STEP, dy))
            self._write_line(f"M{sx},{sy}")
            dx -= sx
            dy -= sy

    def _human_delay(self, base_min: float, base_max: float) -> None:
        """Beta dist (alpha=2, beta=5): cliques tendem ao rápido mas com cauda."""
        val = random.betavariate(2, 5)
        delay = base_min + (base_max - base_min) * val
        time.sleep(delay)

    def send_mouse_click(self, double: bool = False, right: bool = False) -> None:
        """Click com jitter de hand-tremor + delay beta-distribuído entre down/up."""
        btn = 'R' if right else 'L'

        # Tremor primário ±2px antes do click — dirty trail anti-heatmap
        self.move_relative(random.randint(-2, 2), random.randint(-2, 2))
        self._write_line(f"MD{btn}")
        self._human_delay(0.015, 0.080)
        self._write_line(f"MU{btn}")

        if double:
            self._human_delay(0.040, 0.120)
            self.move_relative(random.randint(-1, 1), random.randint(-1, 1))
            self._write_line(f"MD{btn}")
            self._human_delay(0.010, 0.065)
            self._write_line(f"MU{btn}")

