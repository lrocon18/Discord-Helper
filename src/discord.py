"""
discord.py — Discord Helper Service
Kernel input layer via ArduinoHID driver.
PEB masked as Discord.exe.

Ctrl+K — enable / pause
Ctrl+L — exit
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import random
import os
import sys
import winsound
import threading
import time
import json
from dataclasses import dataclass, field, asdict

_K = 0x6D

def _s(encoded: tuple) -> str:
    return ''.join(chr(b ^ _K) for b in encoded)

_ENC_LOCK  = (9,4,30,14,2,31,9,50,4,29,14,67,1,2,14,6)
_ENC_LOG   = (9,4,30,14,2,31,9,67,1,2,10)
_ENC_TITLE = (61, 31, 4, 30, 25, 2, 3, 57, 12, 1, 8, 77, 40, 56)  # "PristonTale EU"

if getattr(sys, 'frozen', False):
    _base_dir = os.path.dirname(sys.executable)
else:
    # dev mode: src/ -> repo root (..)
    _base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

_log_path  = os.path.join(_base_dir, _s(_ENC_LOG))

_CFG_DIR     = os.path.join(_base_dir, "customization")
_STATE_FILE  = os.path.join(_CFG_DIR, "state.json")
_RES_FILE    = os.path.join(_CFG_DIR, "resolutions.json")
_PROFILES    = ("profile1", "profile2", "profile3")


@dataclass
class Settings:
    # COMBATE — apenas enable + cooldown por F-key (sem nome/icone/classe)
    skill_f1:    bool  = True
    skill_f1_cd: float = 0.0     # F1 = main/spam, CD nao usado
    skill_f2:    bool  = False
    skill_f2_cd: float = 10.0
    skill_f3:    bool  = False
    skill_f3_cd: float = 15.0
    skill_f4:    bool  = False
    skill_f4_cd: float = 20.0
    rebuff_minutes:  int  = 7    # 5..10
    start_with_buff: bool = True
    # POT
    pot_hp_pct: int = 40
    pot_sp_pct: int = 5
    pot_mp_pct: int = 5
    # DROPS
    soul_beep: bool = True
    # RESOLUCAO ("auto" = detecta a mais proxima | "WxH" = forca essa)
    forced_resolution: str = "auto"


def _profile_path(name: str) -> str:
    return os.path.join(_CFG_DIR, f"{name}.json")


def _load_profile(name: str) -> Settings:
    s = Settings()
    try:
        with open(_profile_path(name), "r", encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
    except Exception:
        pass
    return s


def _save_profile(name: str, s: Settings) -> None:
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        with open(_profile_path(name), "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, indent=2)
    except Exception:
        pass


@dataclass
class HudState:
    """Estado da HUD (posicao + qual perfil esta ativo + nomes custom)."""
    active_profile: str = "profile1"
    hud_x: int = -1
    hud_y: int = -1
    profile_names: dict = field(default_factory=lambda: {
        "profile1": "Perfil 1",
        "profile2": "Perfil 2",
        "profile3": "Perfil 3",
    })


def _load_hud_state() -> HudState:
    s = HudState()
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if hasattr(s, k):
                setattr(s, k, v)
        if s.active_profile not in _PROFILES:
            s.active_profile = "profile1"
    except Exception:
        pass
    return s


def _save_hud_state(s: HudState) -> None:
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, indent=2)
    except Exception:
        pass


_hud_state: HudState = _load_hud_state()
_settings:  Settings = _load_profile(_hud_state.active_profile)


def _apply_settings(name: str, new_settings: Settings) -> None:
    """Chamado pela HUD ao clicar Save: troca perfil ativo + atualiza runtime."""
    global _settings, _hud_state, _CUR_PROFILE
    for f in new_settings.__dataclass_fields__:
        setattr(_settings, f, getattr(new_settings, f))
    _save_profile(name, _settings)
    _hud_state.active_profile = name
    _save_hud_state(_hud_state)
    _CUR_PROFILE = None   # forca probe_loop a reaplicar a resolucao
    _log(f"[CFG] saved profile={name} res={_settings.forced_resolution} "
         f"pot=({_settings.pot_hp_pct},{_settings.pot_sp_pct},{_settings.pot_mp_pct})%")


def _set_active_profile(name: str) -> None:
    """Chamado pela HUD ao clicar Utilizar: swap pra outro perfil sem alterar dados."""
    global _settings, _hud_state, _CUR_PROFILE
    loaded = _load_profile(name)
    for f in loaded.__dataclass_fields__:
        setattr(_settings, f, getattr(loaded, f))
    _hud_state.active_profile = name
    _save_hud_state(_hud_state)
    _CUR_PROFILE = None   # forca reaplicacao
    _log(f"[CFG] active profile -> {name}")


def _is_active() -> bool:
    """Callback pra HUD mostrar status do macro."""
    return state.active

def _log(msg: str) -> None:
    try:
        data = (msg + "\n").encode("utf-8")
        enc  = bytes(b ^ 0x6D for b in data)
        with open(_log_path, "ab") as f:
            f.write(enc)
    except Exception:
        pass

_THREAD_POOL = (
    "TppWorker", "RpcWorker", "LdrpWorker", "NtWaitThread",
    "WorkerFactory", "COMSurrogate", "TimerQueue", "WinEvtSvc",
    "MpsSvcHost", "CryptWorker",
)

def _tname() -> str:
    return random.choice(_THREAD_POOL) + f"_{random.randint(1, 99):02d}"

def _beep(freq: int, dur: int) -> None:
    winsound.Beep(max(37, freq + random.randint(-40, 40)), dur)

import peb_mask
peb_mask.mask_process(
    fake_name    = r"C:\Users\lucas\AppData\Local\Discord\app-1.0.9032\Discord.exe",
    fake_cmdline = r'"C:\Users\lucas\AppData\Local\Discord\app-1.0.9032\Discord.exe" --start-minimized',
)

from arduino_wrap import ArduinoHID
from hud import HUD

user32   = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")
gdi32    = ctypes.WinDLL("gdi32")

gdi32.GetPixel.restype  = ctypes.c_uint32
gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]

user32.GetDC.restype      = ctypes.c_void_p
user32.GetDC.argtypes     = [wt.HWND]
user32.ReleaseDC.restype  = ctypes.c_int
user32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]

gdi32.CreateCompatibleDC.restype      = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes     = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype  = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype            = ctypes.c_void_p
gdi32.SelectObject.argtypes           = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.BitBlt.restype                  = wt.BOOL
gdi32.BitBlt.argtypes                 = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                          ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetDIBits.restype               = ctypes.c_int
gdi32.GetDIBits.argtypes              = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT, wt.UINT,
                                          ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.restype            = wt.BOOL
gdi32.DeleteObject.argtypes           = [ctypes.c_void_p]
gdi32.DeleteDC.restype                = wt.BOOL
gdi32.DeleteDC.argtypes               = [ctypes.c_void_p]

class _BMIH(ctypes.Structure):
    _fields_ = [
        ('biSize',          wt.DWORD), ('biWidth',         wt.LONG),
        ('biHeight',        wt.LONG),  ('biPlanes',        wt.WORD),
        ('biBitCount',      wt.WORD),  ('biCompression',   wt.DWORD),
        ('biSizeImage',     wt.DWORD), ('biXPelsPerMeter', wt.LONG),
        ('biYPelsPerMeter', wt.LONG),  ('biClrUsed',       wt.DWORD),
        ('biClrImportant',  wt.DWORD),
    ]

kernel32.GetModuleHandleW.restype  = ctypes.c_void_p
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]

kernel32.GetLastError.restype  = wt.DWORD
kernel32.GetLastError.argtypes = []

kernel32.GetConsoleWindow.restype  = wt.HWND
kernel32.GetConsoleWindow.argtypes = []

user32.ShowWindow.restype  = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]

user32.FindWindowW.restype  = wt.HWND
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]

user32.GetClientRect.restype  = wt.BOOL
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

user32.ClientToScreen.restype  = wt.BOOL
user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]

user32.ClipCursor.restype  = wt.BOOL
user32.ClipCursor.argtypes = [ctypes.POINTER(wt.RECT)]

_INPUT_PAUSE   = 2.5
_SYNC_INTERVAL = 5 * 60
_JITTER_LO     = 1 * 60
_JITTER_HI     = 2 * 60
_SYNC_PAUSE    = 2.0

_REF_W = 1920   # reference resolution for template scaling
_REF_H = 1009
_SLOT_EMPTY_THR = 30.0  # mean per-channel SAD < threshold → slot matches empty template

# === Buff verification config ===
# Match threshold: lower = stricter pixel match required.
_BUFF_MATCH_THR     = 28.0
# How often the background monitor checks each buff.
_BUFF_VERIFY_PERIOD = 25.0
# Minimum seconds between recast attempts of the same buff.
_BUFF_RECAST_CD     = 5.0
# Buff profile entries — populated when user provides per-class buff icons.
# Format: (name, recast_key, tmpl_var_name, ratio_x, ratio_y)
#   name           — string label (used in logs only, e.g. "iron_skin")
#   recast_key     — Interception key to send when buff is missing (e.g. "f5")
#   tmpl_var_name  — name of the global containing the decoded template tuple
#                    (e.g. "_g_tmpl_buff1") — must exist before _verify_buffs runs.
#   ratio_x/y      — center of where this buff icon lands in the HUD,
#                    as ratios of game-window dimensions (0.0-1.0).
# Empty until templates are baked from class-specific screenshots.
_BUFF_PROFILES: tuple = ()

TOGGLE_VK = 0x4B   # K — toggle active
CLOSE_VK  = 0x4C   # L — close
HUD_VK    = 0x4A   # J — toggle HUD visibility

# Micro-reacao humana antes de cada pot (gaussiana). Quebra o fingerprint de
# reacao instantanea/identica do macro (WarningAutoMouse), mas rapida o bastante
# (media ~55ms) pra nao perder a barra. Tambem espaca disparos seguidos.
_POT_REACT_MEAN = 0.055
_POT_REACT_STD  = 0.022
_POT_REACT_LO   = 0.028
_POT_REACT_HI   = 0.120

_AUX_CD      = 10.0   # fixed game cooldown (seconds)
_AUX_JIT_LO  = 2.0    # human jitter range after cooldown
_AUX_JIT_HI  = 5.0

# Discord notification badge scanner tuning.
_BADGE_POLL    = 1.0    # seconds between presence polls
_BADGE_COOLDN  = 4.0    # min seconds between notification sounds per channel
# Strict avatar overlay bbox — text labels are consistently ~26x17-20.
# Tighter than initial test version to reject damage numbers / HP bars.
_AVT_W_MIN     = 26
_AVT_H_MIN     = 16
_AVT_H_MAX     = 21
_AVT_ASPECT_MN = 1.35   # bbox W/H ratio min — rejects squarish clusters (item borders)
_AVT_SAD_THR   = 60.0   # template match SAD — confirms cluster is actually 'Soul' text

# Channel color profiles. (h_lo, h_hi, s_lo, s_hi, v_lo, v_hi, code).
# Only magenta channel ('a') active — others removed.
_BADGE_PROFILES = (
    (149, 161,  85, 255,  75, 255, 'a'),  # magenta channel
)

# Profiles de calibracao por resolucao do client area.
# Chave = (width, height). Adicionar entradas conforme novas resolucoes calibradas.
_RES_PROFILES: dict = {
    (1918, 857): {
        'ZA': (0.4615, 0.9009, 0.9911),
        'ZB': (0.4521, 0.9197, 0.9901),
        'ZC': (0.5385, 0.9029, 0.9901),
        'PA': (0.5563, 0.9742),
        'PB': (0.5693, 0.9762),
        'PC': (0.5828, 0.9752),
    },
    (1366, 768): {
        'ZA': (0.4458, 0.8711, 0.9870),
        'ZB': (0.4319, 0.8945, 0.9883),
        'ZC': (0.5542, 0.8711, 0.9870),
        'PA': (0.5783, 0.9674),
        'PB': (0.5981, 0.9661),
        'PC': (0.6149, 0.9661),
    },
}

# Defaults — sobrescritos por _apply_resolution_profile assim que o probe_loop
# detecta as dimensoes da janela.
_ZA_R = (0.4458, 0.8711, 0.9870)
_ZB_R = (0.4319, 0.8945, 0.9883)
_ZC_R = (0.5542, 0.8711, 0.9870)
_PA_R = (0.5783, 0.9674)
_PB_R = (0.5981, 0.9661)
_PC_R = (0.6149, 0.9661)
_CUR_PROFILE: tuple | None = None


def _parse_resolution(s: str) -> tuple | None:
    """'1366x768' -> (1366, 768). Retorna None se nao parsear."""
    if not s or s == "auto":
        return None
    try:
        parts = s.lower().split("x")
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None


def resolution_keys() -> list[str]:
    """Lista das resolucoes mapeadas como strings 'WxH' (pra HUD popular dropdown)."""
    return [f"{w}x{h}" for (w, h) in _RES_PROFILES.keys()]


def _apply_resolution_profile(w: int, h: int) -> tuple | None:
    """Seleciona profile pelo settings (se forced != 'auto') ou pelo mais proximo
    de (w, h). Retorna a chave aplicada se mudou; None se nao mudou."""
    global _ZA_R, _ZB_R, _ZC_R, _PA_R, _PB_R, _PC_R, _CUR_PROFILE
    if not _RES_PROFILES:
        return None

    forced = _parse_resolution(getattr(_settings, "forced_resolution", "auto"))
    if forced and forced in _RES_PROFILES:
        target = forced
    else:
        target = min(_RES_PROFILES.keys(),
                     key=lambda k: (k[0] - w) ** 2 + (k[1] - h) ** 2)

    if target == _CUR_PROFILE:
        return None
    p = _RES_PROFILES[target]
    _ZA_R = p['ZA']; _ZB_R = p['ZB']; _ZC_R = p['ZC']
    _PA_R = p['PA']; _PB_R = p['PB']; _PC_R = p['PC']
    _CUR_PROFILE = target
    return target


def _load_resolutions() -> None:
    """Funde os profiles mapeados pelo usuario (resolutions.json) em _RES_PROFILES.
    Chamado no import — sobrescreve built-ins se o usuario remapeou a mesma WxH."""
    try:
        with open(_RES_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return
    for key, prof in d.items():
        wh = _parse_resolution(key)
        if not wh or not isinstance(prof, dict):
            continue
        try:
            _RES_PROFILES[wh] = {k: tuple(v) for k, v in prof.items()}
        except Exception:
            continue


def _save_resolution_mapping(w: int, h: int, prof: dict) -> None:
    """Persiste um profile recem-mapeado em resolutions.json e funde no runtime.
    Serializa TODO _RES_PROFILES (built-ins + custom) pra um unico arquivo."""
    global _CUR_PROFILE
    try:
        _RES_PROFILES[(int(w), int(h))] = {k: tuple(v) for k, v in prof.items()}
        _CUR_PROFILE = None   # forca probe_loop a reaplicar
        os.makedirs(_CFG_DIR, exist_ok=True)
        out = {f"{ww}x{hh}": {k: list(v) for k, v in p.items()}
               for (ww, hh), p in _RES_PROFILES.items()}
        with open(_RES_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        _log(f"[CFG] resolution mapped {w}x{h} -> {prof}")
    except Exception as e:
        _log(f"[ERR] save resolution {w}x{h}: {e}")


def _current_resolution() -> tuple | None:
    """(w, h) do viewport do jogo agora, ou None se a janela nao for encontrada.
    Usado pela HUD pra exibir 'Sua resolucao atual' (poll a cada ~1s)."""
    hwnd = _locate_window()
    if not hwnd:
        return None
    dims = _query_viewport(hwnd)
    if not dims:
        return None
    return (dims[0], dims[1])


def _resolution_is_mapped(w: int, h: int) -> bool:
    return (int(w), int(h)) in _RES_PROFILES


def _capture_ratio() -> tuple | None:
    """Posicao atual do cursor como ratio (rx, ry) relativo ao viewport do jogo.
    None se a janela nao existe ou o cursor esta fora dela. Usado pelo wizard de
    mapeamento — converte clique de tela em coordenada resolucao-independente."""
    hwnd = _locate_window()
    if not hwnd:
        return None
    dims = _query_viewport(hwnd)
    if not dims:
        return None
    w, h, ox, oy = dims
    pt = wt.POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return None
    rx = (pt.x - ox) / w
    ry = (pt.y - oy) / h
    if not (0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0):
        return None
    return (round(rx, 4), round(ry, 4))


_load_resolutions()   # funde profiles custom de resolutions.json sobre os built-ins

_THR_A = 0.50    # legacy ratio (used in _thresh_px for slot-empty calc)
_THR_B = 0.10
_THR_C = 0.10
# Integer-% thresholds used by _bar_pct pixel-counting detection.
_THR_A_PCT = 40  # HP
_THR_B_PCT = 5   # SP
_THR_C_PCT = 5   # MP

_LOCK_FILE = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), _s(_ENC_LOCK))

@dataclass
class State:
    active:  bool  = False
    stop:    bool  = False
    syncing: bool  = False
    ready:   bool  = False
    user_mouse_until: float = 0.0
    # Quando True: HP/SP/MP esta abaixo do threshold de pot. Threads de combate
    # (idle_tick, aux_loop) cedem espaco pra pot fire ter prioridade na serial.
    hp_critical: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def paused_by_user(self) -> bool:
        return time.monotonic() < self.user_mouse_until

    def bump_user_mouse(self) -> None:
        with self.lock:
            self.user_mouse_until = time.monotonic() + _INPUT_PAUSE


state = State()

PROCESS_TERMINATE                 = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_psapi = ctypes.WinDLL("psapi")
_psapi.EnumProcesses.restype  = wt.BOOL
_psapi.EnumProcesses.argtypes = [
    ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)
]

kernel32.QueryFullProcessImageNameW.restype  = wt.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)
]


def _kill_existing_instances() -> None:
    # PID-targeted kill via lock file only — never kill by image name,
    # senão mataríamos o cliente Discord legítimo quando o exe se chama Discord.exe.
    _kill_by_lock_file()

    try:
        os.remove(_LOCK_FILE)
    except Exception:
        pass


def _kill_by_lock_file() -> None:
    if not os.path.exists(_LOCK_FILE):
        return
    try:
        with open(_LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
        if pid == os.getpid():
            return
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            kernel32.TerminateProcess(h, 0)
            kernel32.CloseHandle(h)
    except Exception:
        pass
    try:
        os.remove(_LOCK_FILE)
    except Exception:
        pass
    time.sleep(0.4)


def _write_lock() -> None:
    try:
        with open(_LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def _remove_lock() -> None:
    try:
        if os.path.exists(_LOCK_FILE):
            pid_in_file = int(open(_LOCK_FILE).read().strip())
            if pid_in_file == os.getpid():
                os.remove(_LOCK_FILE)
    except Exception:
        pass


def _sleep_human(lo: float, hi: float) -> None:
    mid   = (lo + hi) / 2
    sigma = (hi - lo) / 4
    t = random.gauss(mid, sigma)
    t = max(lo * 0.88, min(hi * 1.12, t))
    time.sleep(t)


def _human_hold(lo: float = 0.07, hi: float = 0.13) -> float:
    """Tempo de hold humanlike pra send_key (curva gauss)."""
    mid   = (lo + hi) / 2
    sigma = (hi - lo) / 4
    t = random.gauss(mid, sigma)
    return max(lo * 0.85, min(hi * 1.15, t))


def _human_move(ic, dx: int, dy: int, steps: int = 0, total_ms: float = 0.0) -> None:
    # Quadratic Bezier from current pos to (dx, dy) with random perpendicular
    # control-point offset. Steps emitted as relative deltas via Interception
    # — kernel-level, indistinguishable from physical mouse.
    if ic is None:
        return
    if steps <= 0:
        steps = random.randint(8, 16)
    if total_ms <= 0.0:
        total_ms = random.uniform(80.0, 200.0)

    dist = (dx * dx + dy * dy) ** 0.5
    # perpendicular offset magnitude: scales with distance, clamped
    perp = random.gauss(0.0, max(1.5, dist * 0.18))
    perp = max(-dist * 0.45, min(dist * 0.45, perp))
    if dist > 0.5:
        nx = -dy / dist
        ny =  dx / dist
    else:
        nx = ny = 0.0
    cx = dx * 0.5 + nx * perp
    cy = dy * 0.5 + ny * perp

    prev_x = prev_y = 0.0
    step_sleep = (total_ms / 1000.0) / steps
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        px = 2 * u * t * cx + (t * t) * dx
        py = 2 * u * t * cy + (t * t) * dy
        ddx = int(round(px - prev_x))
        ddy = int(round(py - prev_y))
        if ddx or ddy:
            ic.move_relative(ddx, ddy)
        prev_x += ddx
        prev_y += ddy
        # jittered per-step sleep (5-15ms typical)
        jitter = random.gauss(step_sleep, step_sleep * 0.25)
        jitter = max(0.003, min(0.020, jitter))
        time.sleep(jitter)


def _human_click(ic, double: bool = False, right: bool = False) -> None:
    # Click in place — no pre-click drift. Pre-delay gaussiano.
    if ic is None:
        return
    _sleep_human(0.018, 0.060)
    ic.send_mouse_click(double=double, right=right)


def _target_window_focused() -> bool:
    # Apenas checa se a janela-alvo está em foreground (sem checar cursor).
    # Usado pra pot (defensivo) — vale disparar F1 mesmo com cursor fora do rect.
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    buf = ctypes.create_unicode_buffer(256)
    if user32.GetWindowTextW(hwnd, buf, 256) <= 0:
        return False
    return buf.value.startswith(_TITLE_PFX)


def _target_has_focus() -> bool:
    # Estrito: janela em foco + cursor dentro do rect.
    # Usado pra idle/aux (cliques agressivos) — cursor fora pausa naturalmente.
    if not _target_window_focused():
        return False
    hwnd = user32.GetForegroundWindow()
    dims = _query_viewport(hwnd)
    if not dims:
        return False
    w, h, ox, oy = dims
    pt = wt.POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return False
    return ox <= pt.x < ox + w and oy <= pt.y < oy + h


def _can_tick() -> bool:
    return (state.active and not state.stop and not state.paused_by_user()
            and not state.syncing and _target_has_focus())

def _can_probe() -> bool:
    return state.active and not state.stop


def _can_pot() -> bool:
    # Gate frouxo pra pot defensiva: não exige cursor-in-rect.
    return (state.active and not state.stop and not state.syncing
            and _target_window_focused())


user32.EnumWindows.restype  = wt.BOOL
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
user32.GetWindowTextW.restype  = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetForegroundWindow.restype  = wt.HWND
user32.GetForegroundWindow.argtypes = []
user32.IsWindowVisible.restype  = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]

_TITLE_PFX = _s(_ENC_TITLE)

def _locate_window() -> int | None:
    found = ctypes.c_void_p(0)
    buf   = ctypes.create_unicode_buffer(256)

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextW(hwnd, buf, 256) > 0:
            if buf.value.startswith(_TITLE_PFX):
                found.value = hwnd
                return False
        return True

    user32.EnumWindows(_cb, 0)
    return found.value or None

def _query_viewport(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    w = rect.right  - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return w, h, pt.x, pt.y



def _to_screen(rx: float, ry: float, w: int, h: int, ox: int, oy: int) -> tuple[int, int]:
    return (ox + int(rx * w), oy + int(ry * h))

def _scan_hud(hdc_src, w: int, h: int, ox: int, oy: int) -> tuple[int, int, int]:
    """
    Find bar x-positions by color dominance scan (resolution-independent).
    Scans three horizontal rows near bar bottoms (always filled when HP/SP/MP > ~3%).
    Falls back to ratio-based x if a bar is not detected.
    Returns (hp_x, sp_x, mp_x) as absolute screen x coords.
    """
    hp_x = sp_x = mp_x = None
    x_lo = int(w * 0.38)
    x_hi = int(w * 0.62)
    bw = x_hi - x_lo
    # 1 BitBlt da faixa inteira (3 linhas) + varredura na MEMORIA — substitui
    # ~1380 GetPixel por pixel (que em VM custam readback de GPU, ~segundos).
    rows = [oy + int(ry * h) for ry in (0.9875, 0.9885, 0.9895)]
    y0 = min(rows)
    band_h = max(rows) - y0 + 1
    cap = _capture_region(hdc_src, ox + x_lo, y0, bw, band_h) if bw > 0 else None
    if cap is not None:
        for ry_abs in rows:
            row_off = (ry_abs - y0) * bw * 4   # BGRX, 4 bytes/px, top-down
            for bx in range(bw):
                o = row_off + bx * 4
                b = cap[o]; g = cap[o+1]; r = cap[o+2]
                if hp_x is None and r > 160 and r > g * 2.5 and r > b * 2.5:
                    hp_x = ox + x_lo + bx
                if sp_x is None and g > 140 and g > r * 2.5 and g > b * 2.5:
                    sp_x = ox + x_lo + bx
                if mp_x is None and r < 50 and b > 100:
                    mp_x = ox + x_lo + bx
            if hp_x is not None and sp_x is not None and mp_x is not None:
                break
    fb_hp = hp_x is None
    fb_sp = sp_x is None
    fb_mp = mp_x is None
    if fb_hp: hp_x = ox + int(_ZA_R[0] * w)
    if fb_sp: sp_x = ox + int(_ZB_R[0] * w)
    if fb_mp: mp_x = ox + int(_ZC_R[0] * w)
    _log(f"[MON] scan x: hp={hp_x-ox}(fb={fb_hp}) sp={sp_x-ox}(fb={fb_sp}) mp={mp_x-ox}(fb={fb_mp})")
    return hp_x, sp_x, mp_x

def _thresh_px(screen_x: int, bar_r: tuple, thr: float, h: int, oy: int) -> tuple[int, int]:
    """Threshold pixel using scanned screen_x + ratio-based y."""
    _, ry_top, ry_bot = bar_r
    return screen_x, oy + int((ry_bot - thr * (ry_bot - ry_top)) * h)



def _nn_scale(src, sw: int, sh: int, sc: int, dw: int, dh: int) -> bytearray:
    """Nearest-neighbor scale src (sw×sh, sc channels) → dw×dh."""
    out = bytearray(dw * dh * sc)
    for dy in range(dh):
        sy_ = int(dy * sh / dh)
        for dx in range(dw):
            sx_ = int(dx * sw / dw)
            si = (sy_ * sw + sx_) * sc
            di = (dy * dw + dx) * sc
            out[di:di+sc] = src[si:si+sc]
    return out


def _capture_region(hdc_src, sx: int, sy: int, cw: int, ch: int):
    """BitBlt (sx,sy,cw,ch) into BGRX bytearray (4 bytes/px, top-down) or None."""
    hdc_m = gdi32.CreateCompatibleDC(hdc_src)
    if not hdc_m:
        return None
    bmp = gdi32.CreateCompatibleBitmap(hdc_src, cw, ch)
    if not bmp:
        gdi32.DeleteDC(hdc_m)
        return None
    old = gdi32.SelectObject(hdc_m, bmp)
    gdi32.BitBlt(hdc_m, 0, 0, cw, ch, hdc_src, sx, sy, 0xCC0020)
    bmi = _BMIH()
    bmi.biSize = ctypes.sizeof(_BMIH)
    bmi.biWidth = cw; bmi.biHeight = -ch   # negative → top-down row order
    bmi.biPlanes = 1; bmi.biBitCount = 32; bmi.biCompression = 0
    buf = (ctypes.c_uint8 * (cw * ch * 4))()
    gdi32.GetDIBits(hdc_m, bmp, 0, ch, buf, ctypes.byref(bmi), 0)
    gdi32.SelectObject(hdc_m, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc_m)
    return bytearray(buf)




def _sad_center(cap_bgrx, cw: int, ch: int,
                tmpl_rgb, tmpl_ch: int) -> float:
    """
    Mean per-channel SAD over the center 50% region of cap vs tmpl_rgb
    (tmpl_rgb must already be scaled to cw×ch).
    """
    x1, x2 = cw // 4, 3 * cw // 4
    y1, y2 = ch // 4, 3 * ch // 4
    n = (x2 - x1) * (y2 - y1)
    if n == 0:
        return 255.0
    total = 0
    for cy_ in range(y1, y2):
        for cx_ in range(x1, x2):
            ci = (cy_ * cw + cx_) * 4
            ti = (cy_ * cw + cx_) * tmpl_ch
            total += (abs(cap_bgrx[ci+2] - tmpl_rgb[ti])
                    + abs(cap_bgrx[ci+1] - tmpl_rgb[ti+1])
                    + abs(cap_bgrx[ci]   - tmpl_rgb[ti+2]))
    return total / (n * 3)


def _check_buff_present(hdc_src, ratio_x: float, ratio_y: float, tmpl,
                        w: int, h: int, ox: int, oy: int) -> tuple:
    # Single buff icon verification via SAD template match.
    # Returns (active: bool, avg_sad: float).
    # Same machinery as slot-empty detection — scales template to current
    # viewport, captures region around expected position, compares.
    if tmpl is None:
        return False, 999.0
    pix, tw, th, tc = tmpl
    sx_sc = w / _REF_W
    sy_sc = h / _REF_H
    cw = max(8, int(tw * sx_sc))
    ch = max(8, int(th * sy_sc))
    cx = ox + int(ratio_x * w)
    cy = oy + int(ratio_y * h)
    cap = _capture_region(hdc_src, cx - cw // 2, cy - ch // 2, cw, ch)
    if cap is None:
        return False, 999.0
    pix_s = _nn_scale(pix, tw, th, tc, cw, ch)
    avg   = _sad_center(cap, cw, ch, pix_s, tc)
    return avg < _BUFF_MATCH_THR, avg


def _verify_buffs(hdc_src, w: int, h: int, ox: int, oy: int) -> dict:
    # Iterates _BUFF_PROFILES, returns {name: (active, sad)}.
    # No-op if profiles list is empty (initial framework state).
    result = {}
    for entry in _BUFF_PROFILES:
        name, _key, tmpl_var, rx, ry = entry
        tmpl = globals().get(tmpl_var)
        active, sad = _check_buff_present(hdc_src, rx, ry, tmpl, w, h, ox, oy)
        result[name] = (active, sad)
    return result


def _bar_pct(hdc_src, bar_x: int, bar_r: tuple, h: int, oy: int,
             sig_fn, bar_w: int = 8) -> int:
    # Vertical-bar fill percentage via pixel counting.
    # _scan_hud returns the LEFT EDGE of the bar (first red pixel from left),
    # so capture starts AT bar_x and extends right INTO the bar interior.
    # Offset +1 skips anti-aliased left edge pixels.
    #
    # Arduino port: same loop, integer-only — read framebuffer rows in the
    # bar strip, count matches, divide.
    _, ry_top, ry_bot = bar_r
    y_top = oy + int(ry_top * h)
    y_bot = oy + int(ry_bot * h)
    bar_h = y_bot - y_top
    if bar_h <= 0:
        return 0
    cap = _capture_region(hdc_src, bar_x + 1, y_top, bar_w, bar_h)
    if cap is None:
        return 0
    matched = 0
    total   = bar_w * bar_h
    # BGRX: cap[i]=B, cap[i+1]=G, cap[i+2]=R
    for i in range(0, len(cap), 4):
        b = cap[i]; g = cap[i+1]; r = cap[i+2]
        if sig_fn((r, g, b)):
            matched += 1
    return (matched * 100) // total


def _pixel_to_color_space(r: int, g: int, b: int) -> tuple:
    # Convert RGB triple to a 0-179/0-255/0-255 color-space triple.
    # Integer-only — portable to MCU.
    v = r if r >= g and r >= b else (g if g >= b else b)
    mn = r if r <= g and r <= b else (g if g <= b else b)
    delta = v - mn
    if v == 0:
        return 0, 0, 0
    s = (delta * 255) // v
    if delta == 0:
        return 0, s, v
    if v == r:
        h = (30 * (g - b)) // delta
    elif v == g:
        h = (30 * (b - r)) // delta + 60
    else:
        h = (30 * (r - g)) // delta + 120
    if h < 0:
        h += 180
    return h, s, v


def _check_presence(hdc_src, ox: int, oy: int, w: int, h: int) -> str:
    # Notification-badge scan: HSV color-space filter + connected-component
    # bounding box. Two-pass pipeline portable to MCU framebuffer scans.
    # Scan center play area only. Right side (minimap, UI panels) excluded —
    # red dots on the minimap form clusters that match badge size.
    rx = ox + int(w * 0.12)
    ry = oy + int(h * 0.10)
    rw = int(w * 0.62)
    rh = int(h * 0.55)
    cap = _capture_region(hdc_src, rx, ry, rw, rh)
    if cap is None:
        return ''

    # Per-pixel HSV classification across all profiles in one pass.
    # mask byte value = profile index + 1 (0 = no match).
    mask = bytearray(rw * rh)
    counts = [0] * len(_BADGE_PROFILES)
    for y in range(rh):
        row_off = y * rw * 4
        mrow = y * rw
        for x in range(rw):
            o = row_off + x * 4
            b = cap[o]; g = cap[o+1]; r = cap[o+2]
            hh, ss, vv = _pixel_to_color_space(r, g, b)
            for pi in range(len(_BADGE_PROFILES)):
                p = _BADGE_PROFILES[pi]
                if (p[0] <= hh <= p[1] and
                    p[2] <= ss <= p[3] and
                    p[4] <= vv <= p[5]):
                    mask[mrow + x] = pi + 1
                    counts[pi] += 1
                    break

    if all(c == 0 for c in counts):
        _log(f"[VC] region=({rx},{ry},{rw}x{rh}) px=0 — quiet")
        return ''

    # Horizontal dilation — bridges 1-2px gaps between letters in text.
    # Without this, "Soul" gets split into S/o/u/l, each below bbox threshold.
    # Sheltom borders are continuous lines, so dilation doesn't merge unrelated
    # things; only helps connect adjacent letters of the same word.
    dilate_x = 2
    for y in range(rh):
        row_off = y * rw
        # Forward pass: extend rightward from each set pixel
        run = 0
        for x in range(rw):
            if mask[row_off + x]:
                run = dilate_x
            elif run > 0:
                mask[row_off + x] = 1   # mark as channel 'a' (only profile)
                run -= 1
        # Backward pass: extend leftward
        run = 0
        for x in range(rw - 1, -1, -1):
            v = mask[row_off + x]
            if v:
                run = dilate_x
            elif run > 0:
                mask[row_off + x] = 1
                run -= 1

    # Flood-fill within same profile-id; collect bbox per cluster.
    visited = bytearray(rw * rh)
    hits = {}   # profile_code -> (bbox, n_passed)
    n_clusters = 0
    for sy in range(rh):
        for sx in range(rw):
            idx = sy * rw + sx
            v = mask[idx]
            if v == 0 or visited[idx]:
                continue
            n_clusters += 1
            stack = [(sx, sy)]
            visited[idx] = 1
            xmin = xmax = sx
            ymin = ymax = sy
            while stack:
                x, y = stack.pop()
                if x < xmin: xmin = x
                if x > xmax: xmax = x
                if y < ymin: ymin = y
                if y > ymax: ymax = y
                if x > 0:
                    ni = y * rw + x - 1
                    if mask[ni] == v and not visited[ni]:
                        visited[ni] = 1; stack.append((x-1, y))
                if x < rw - 1:
                    ni = y * rw + x + 1
                    if mask[ni] == v and not visited[ni]:
                        visited[ni] = 1; stack.append((x+1, y))
                if y > 0:
                    ni = (y-1) * rw + x
                    if mask[ni] == v and not visited[ni]:
                        visited[ni] = 1; stack.append((x, y-1))
                if y < rh - 1:
                    ni = (y+1) * rw + x
                    if mask[ni] == v and not visited[ni]:
                        visited[ni] = 1; stack.append((x, y+1))
            bw = xmax - xmin + 1
            bh = ymax - ymin + 1
            # Stage 1: bbox size
            if not (bw >= _AVT_W_MIN and _AVT_H_MIN <= bh <= _AVT_H_MAX):
                continue
            # Stage 2: aspect ratio — text is wider than tall.
            # Sheltom/item borders are roughly square (W/H ~ 1.0-1.2).
            if bw < bh * _AVT_ASPECT_MN:
                continue
            # Stage 3: template SAD against magenta Soul template (channel 'a' only).
            # Extracts the bbox sub-region from the capture and compares to
            # the scaled template. Rejects color-only false positives.
            code = _BADGE_PROFILES[v - 1][6]
            if code == 'a' and _g_tmpl_sc is not None:
                sub = bytearray(bw * bh * 4)
                for j in range(bh):
                    src_off = ((ymin + j) * rw + xmin) * 4
                    dst_off = j * bw * 4
                    sub[dst_off:dst_off + bw * 4] = cap[src_off:src_off + bw * 4]
                pix, tw, th, tc = _g_tmpl_sc
                pix_s = _nn_scale(pix, tw, th, tc, bw, bh)
                sad = _sad_center(sub, bw, bh, pix_s, tc)
                if sad >= _AVT_SAD_THR:
                    continue
            if code not in hits:
                hits[code] = (xmin + rx, ymin + ry, bw, bh)

    _log(f"[VC] region=({rx},{ry},{rw}x{rh}) "
         f"px={counts} groups={n_clusters} hits={hits}")

    # Priority order: rarest first — b (high-hue red) > a (magenta) > c (green) > d (cyan)
    for code in ('b', 'a', 'c', 'd'):
        if code in hits:
            return code
    return ''


def _emit_ping(kind: str) -> None:
    # Non-blocking notification sound, distinct pattern per channel code.
    def _seq():
        try:
            if kind == 'a':
                # Magenta: triade ascendente (Soul alert)
                for f, d in [(880, 110), (1175, 110), (1568, 220)]:
                    _beep(f, d)
                    time.sleep(0.03)
            elif kind == 'p':
                # Empty pot warning: 3 descending low beeps — urgent, distinct from Soul
                for f, d in [(440, 180), (330, 180), (220, 350)]:
                    _beep(f, d)
                    time.sleep(0.05)
            else:
                _beep(880, 110)
        except Exception:
            pass
    threading.Thread(target=_seq, daemon=True, name=_tname()).start()




def _decode_tmpl(d_hex: str, w: int, h: int, ch: int):
    return bytes(b ^ _K for b in bytes.fromhex(d_hex)), w, h, ch

_TMPL_HP_W = 27; _TMPL_HP_H = 105; _TMPL_HP_C = 3
_TMPL_HP_D = '101f30101c361602351501390b3127010e23060f2008372a1a073e15003b1501391a073e1b043f1501391501380a30240309221c0a3c1f053c020822043227053325000f20060f20053227093625171d370d3b2b29505c4b4f76092d720f50483f5e4c5144722545712945735747712f4b765a4a7456497e5b49715c4977544f715b4f714c757b49777e5e737d5b427b5b5d7c5742795a4f7c74747e4c73752b2d5e3d245740444d36524fc0145ad9ed2badf11ca6c0fabad6c687bbab9d868f9c828787808485868f8e8a8cb7bbbbb5b9a7b9a7d5a6dd03aacb38a9f239ddf119c3f90fcae136e00656272f4b48497742474c29505c70777821544ff50256f2133dcae935dee10aa9c9e8aac7eab5daf98aabf486a7c59cb7d79cb7a9998eb1818ba4848aa895a61a98b9e89da1e180a3fb88a4efb8db1ad4f336150f575e414f72717a5c414e7a797c424b70212a44262b43063f2fe50e29f2082ccbed28dcfc2cc8112cc4115ff11c5ffe0b43e93244ec317315394efe0050e808511436573f557a2258412c5b48535c444449764d4d7a74787f454e717675775a40477d7863637f60607d634e487b1a345ac7e122c6e63cdff522c5fc39c8e726cc1326cceb3ccde923f3ec22f81523e80450063e565357444c774f627c7e757f7e747a7e7274744c4d714f73754a4e4de6ee05c1cae5d3d6ca09070b7e75747575797b73717474704e717376764f73724c4b4e70464845414b454443404945447672494e4f4c72704e497372aedcf9bcabcfe6f6155558445b555f494d77454c72f1f81ed9c0e7bfbcaea3b9a9454f45606466fc6769a06a6d963d4184a0a582b3b192736189696d8b686dca686de5686dca6a6daa414e63627d5355518db1bc8c8cb9adc2fe0b0627595f45464a73484b7a4f776152505cd5f2ec8484b1275b54677c7c126769a4656d9527458fd3d49fc3cc920d2d9660689c686dcb696df56a6da9646dac7378636064595e5eb6b4b8d7dbf50c3b2e515742424748555f4a777b7f7e7360484c76cff708b1bea32e555a7a7c7c006765af686d9b3f5989bba19ecbe392082e93525493505bb9626bd3676daa666dc9656e606066435c43bfa2a7ffe80376777b4c737a73777b285342484c77797d635c4576e2193eb6b4a22f5643787e7e076568a8686d9d3e5e8ebdbc9a123592235d974148905d44b46164a27c68be7566e0656f606564464044bcbca0e9150a7f7e63797f62444870242f595c414e7b7e6245707f190e2ab1b1be525e467d7b7d03666ba56a6d9d255e8da4af953a5992467b86646d86656dc26a6daf616db64675d8666961676745474bbcbdbdf8e518717e607a797d515b46222555555e45777b7f4f4c7802333cb7b8a02f5e41787b7d02666aa7646d832759b0acd49b3d5e927366b4656dba6b6d12686dfe6a6da07f6ba5594866676b4a4749a6a1a0ffec0275797f777a7e5254433f2757565b4677757e4c4d77110924b4baa32d57417f7d6201646ba7646d82245ab3d1d8981c2f927564b4686db4686def686dec6b6dc56a6da75e4b67686844444ea4a9aafcee1a787e637a787c555e453b235053554176757e4c717b150c21b5bba35655467c6267036469a4646d823855b1d1d59f1322927565b5656db4656de1696de66b6dd5656da84e7465686b444749aaa5a9f8ee1f616368797c63484c77222a5a555f45747b7f734e7c1f0c21b7b4bf525f456061641a6a6ea1656d81302fb2d4c698142a927565b6646db0646de3686d17696dc96b6dcf6a6c686869454448a7a5aee7ed076a646972777b7a797d242f5f59434975787c6a6065053b2ab7babc2c5f41606067196a6ea36b6d803225b2d6c199092d927b6ab7656db7656de4686d19696df6686dfe656c68696945444ea7a7aae411006e6e6e41477145497a5c414c7377797e7d606a6a6b093d2db2b7bb295441606767176b6ebc6b6d81362fb2d8c19a0956927a6bb4656db4656deb686d1f696df5686de26b6c6969684a4a49a7a7a5e2100269696f4e4c79575c4a7b7e627e7d61787c626b686e093c25b2b3bb295c4061646bec686ea26a6d87362eb0dec79a0e55927a6bb4656db4656de56b6d19696df36b6dca656c696969474548a6a0a2ec1b0c686e6e74786258404a4a70784e7662626263686b690f392e888bb328534167676513646ea0646d863f53b2dcca950e5a927b6ab6656db6646de56b6d1b696dce6b6dac727f69696943434ba1a1a0ee190c6b686c797e61585c410b2f4b56487b7e616b6e6f6e353f2d88888d25594766676517646fa26a6d872352b2d9cc9b1851927565b7646db7646de46b6d10696dc06a6da5434e6869695d4148a0a3a203093d6e6b6f737a7f5c404bc212582d4e797b7f646e6e6f3a3e2d898b8c26565e6066651a6a6fa1656d872157b2d8c89a1857927465b7646db6646de76b6d12696dc36a6da15a456868695d414aa6a6bd040f386e6869717a784549704a75734d747e767d696c6e6e22295a8b888d222f58676664026a6ea7686d872657b2dfca951857927261b6646db1646de0686de8686dd6676daf487a6b6969404748a1a6a6060a3f696e68777a7e717a786864677c7d647662686f696e535a5f8c8eba2d5f47666664186a6ea76b6d872751b2d9cb9b1a53927361b0646db2656de06b6de86b6db97a6ad67965696969414648a0a3a004083769686e7377747a7f7cee1a3b3035584a44767f7967554371bfb8a459434e676765e7676fa06a6d8723508cd9c59a10529373628d646d8c646dff6b6df8686db6477aab45776969695c404aa2a6a51c0a3c696e6f414b4f74797dc6f01d383e534e4477797c68464977a2bcad584373676665a4636c887f6d861f308dd7c39bee24934b7e8c616d8e616df86b6df66a6dbc7e6aae487568696e5f4345bda3a6083a3f696e6e2d575c777e7cddc81057504375487b7f7d6e4d4964a7bdd355434f666764ba4f609b736e87e3ec8eafd79de10891544f87616d87606df56a6df9686dd8646ddd666c696e6e404149a3a2a700372a6e6f6c2c59447b7e60d9f11e5e5c72784d627e7a6f767167a4a0d257404f666164ab7e6cb1616d861f0c8abda382c4e096235e997e6f9c7d6dc1646dce656dd9666df2646c696e6c43404ebfbfa3181d20696e6e5147404e7175d8f6ed5f58487a447f61636e79716ea5a5d2525f4b66646714656e8d636d81e91580b3b183a5d69008289977619e7a64d7676dcf656daf606df6656c696e6c44444ebab5b8100935686e6c7b7c6243474ddfcd1a575d4874497f677a6f667b6eaaa4ad565f49676665376a6e8f626d80f5fc86b9bf80cfe796235999626d99626dc8676dec686dc66a6df96a6c6969694a454eb5b6b910053a646565646464444870dcc9025b59497f7063697c6f657968a0bdab545d4e616767396a68b8606d86e41387bbb880dcf6962c479e636d9e636dcd6a6ded686dc8656de26a6f6e696e4a4548b5b4ba190a266164656a6768797e62c6c81b595f4e6174666e666c68606ea0bdac54434b666164396b69877c6d82c3c780b3b09da2a9962c4798626d9e626dcf6b6de36a6dd9646dfc656c696f6f454648b4b5b4ef190d6164696a65687c7e66cefa005b5d496a7f67696a6f656a6fa6a7ad545c4b63676580597096426582dedc80b0b19dbea4913c5a997c6e997d6ff06b6df8686dd9646dfa656f69696e45464ab8b9bf16033c63676b6b646e626260c9e21a5d5d78686a676f6b6f6b6f6ea3bea95859476166669926419e716d811b098ed7db86d6c3900d53987c6999626ef26b6de66b6dce6a6de3656c6b696844404ab8b9bfe41b0d60616967666966616adde21e4d47706e636b6c6e6e68696fbfa1ae555f45616064c8646fb8676d860b398ed7c283f3e6923a51957c6f9a626ccc686de46b6df76a6de86b6f696969464045bbbaa1e80204646569656a6e686a69c0f81a4a4370636b686f646f6e6f69a1bcd35a5d4d606667356569a46b6d862b548cd4c29cf3ef92082b957a669b7f6ac86b6de76b6dfe6a6dec656c696869404345bebea1ee18366b6b6966606e686a69d9c5104a417169676e6f6e6e69686fa3a7d755444e616666386a69ab686d8120548fd7c398e206933c5b9a7161957060df676de76b6dfe6a6ded6b6f696e6e44424abbbda5e51b336a6768487071434c76decce85848726e6f686e6e696b6c6ca2a7d1415d4d6061643d6a69aa686d803f578eadd99a1b2293514899796a9a7767de6b6de5686df9656d136b6c686e69455d4aa2a2aee1143766686e7d7a7f5d494dcee000474e746763696e6c6f686c6fa0a5d543474d6361653d6569ab6a6d810d2a8cadd59b02239056499f7d6f997e6eca656deb696df86a6ded6a6c696e6e415d4aa0a3ae1c1b3764656a6765657a7e7cf4e6054d44746962696b696965696bbea3ae41474e666665206a6ea3646d81053d8eafd89be43690574e82676d82616df3696de9696df96a6d10656f69696e465c48a6a1ac323b256a66696a6a69696b6af7ea054074766e6b6b6e6f6f6a6a6ea0a7d04e4770616466206a69aa646d8304238fafd79fe20a93574e87636d87636df36b6def696dfc6b6d116b6c6e6e69444049a4a3ad000e376a676a65676a696b6fe6e90d444e7063676f6f6f6f7c6569a5aad7494a7b6666653c6a6ea16a6d830c238cafd599e53392554d897d6d8b636df56a6d12686dfc686d176b6c696f6f4a404ea6a6ad0a033b67676a6a6665686b68e0160c4649736a6665696b6e606f69a6abd572497a60646a1f646eb07c6d81e6198cd6de9b173a925f70897c6d8b7c6dfa696d13686dfd6b6d176b6c69696e4a4149a5aad2040322656a6b65646b68656efdef327345706e64656c6e6c676b6aa1acdb71707864616a1d6a6eb1626d80e7028cd4df9b1a3d92417a8b606d85636dfa6e6ded686de2686d146a6c69696e48434eaaaed20202356665656a64656b606be3160f4b4a736967616d6e6e7e6b68a0aeda7571786664643a6a6eb4636d86e2118ed1d8951e2592457e8b616d84616dcd686de8686dfc6b6d12676e6e686945444ea8a9d0021c3867676a6a656a696569e8170c4a41786162656f6f6e636169bda9d474727f6161653d6b6ea3616d81e71388aed3951927924e7c8a636d8a626df66a6dee686df5696de3646e696e694e454eacafd8090c267f60612424566b6768ea1733484176676b646f6e6e7a7a68a3a7d57b797c606165396a6eaa6a6d8111078baaaf95eb3d924f628a606d8a636df0686de8686dcc656dfe666e68696972494fd4d7c708342b6164643821544c7374e5ed0d464b70636465696e6e7e776fa3a5d078797e666165356469aa676d81023689add795e73f92487d8b7d6d8b7d6df16a6de3696dc66a6df4676e686b69704972dfdcf60c212d6364644445715c5c49ed143b4740727d65656f696f61656ebdbda87f7879666067336469a8656d8337298cdac097eb2292477985636d8a636df46a6de0696dd5656dcb666f6a6b69724b72c2c1f5313c53666667717a7c797b7cfc17364041766665656d6f6c6a6969bca0af78787f60616a356569ab656d813b2b8cdec99bec26924b7d80666d83616dce6a6dc4646db04b7bd17a66656a6b724e72cacbe7303f2b60616473747e7f7f67ea010d414f766463686f6e686a6f6fb8a0ae7e7960646665326a6ea3606d830823b2c7f29ae824924b7e86666d80606dc0646ddb656d8c4375df626864666b724976c5f1e93a3f546060647b7f607d7f61ef1a32404777676b6b6f646f637969bcabd37a7b6366676ae76a6fb9616d811e308fc3cf9be73e92457f86606d807c6cc9656dcf656da7606de2646c64646b707176c8fa133334516362617a7a7f797862ef1909404a7163606a6c6c6e6b627fbca7d2787d6165676af4676eb87c6d80121c8dd8c39ce205925f7681606d80606df2656dff6b6dcd6a6de96b6f61616a707176cdf9110e312c7d7f6075747e4e7378e2110e5d4771677d6f696f6e46646abea6d77f6160666664f4616e8d7d6d86e31589d1db82cbe790514f81626d81626df2656de4686df76b6d1a656f60606473737af4fc1e0c3b2d7e7c7c545f45575a44e61731415f776366686f696f71726eb9a6d3627d66666665df616fbd636d8134288ed6db8ad3de932c48867c6d877d6df76b6dee686df86b6d1e646961636772777affeb062f2d59724d75353e2f5c4b4dfa17335972766667656e6c6e717a69a1acd77d636661666aba766fa7676d9e395cb2dcc080f3eb925a72877d6d847d6df96b6d17686dff6b6d0064696366644d7375eb180d5656430d395030382e444b71f4fb065d474861676b6f696e77786ea0a4d87e7d6664646aad666fae656d830426b2d9c684c8fc925b73867d6d867d6dfb6b6d1b696dfd686d0664696363644d4e730e37290f0929e51b305e5d4a434b72f813045d447e6e666a6c6e6e766565a8d1c5797c7c666167c1616fa9656d820224b2dcc088aed5935e7187606d87606df46a6d15696dfc6b6d016769627d674d4f4d23535efdec0b14063a4c4f74454d70fd17305d4573667d656f696f7f6267a8acc177777e606365e3666ea7646d9f0e588ddfc388aad390587085626d84606df76a6d166b6df96b6d066568626366734c7755414bf8e7191703375541485a5e49fc12095e5d4d60646a6e656e737b7dd0d5ce77707b606161f1606fbd7f6d99eb2b8cd7d88adbc190547085636d84626df66a6d16686dfc6b6d0166687d62664c4c73555f45202c55363c523d2b51202753fd110f5845497d7d6568696b717a7fd7dffc484974636367a47468886a6d83f614b2d5de8bc7f4935a7383666d83666df1686d14696dfe6b6d1a6a6e6662644f49703b3057494c4847494d4047704b4b73e0ee0c51434c6178616b616b49717cd5ddf947404c606366b74f79975868991125b2d5de89dccc932f499d606d9d606df06a6d15686df9686d1267697d64644e484df5e01d272e5971767677717e70717bfd1409585e487b796068606b4e4c71dcc1e441434d6360659c284e92397d9fe73bb3d6da8da0a49243779c7f6d9f7e6dcd656d11696df96b6de467696463674f4877c5fae811053871707b7073744f4b77161b31565c487a7a7d6a66674e7b79c1cd114742737d7f668b4373922b629b1253b0add68da2a6925d7a9d666d9d616dcc646deb6a6df4686dfb656f6360644d4872c2c9e7180b387a757a4f4c75454a4de41709535a44747879656067714f7ec0cfef42464e636061bd7b67942e61950a598dacd280feec925e72837d6d9c636dc36b6dfc6a6dc9656dfa616e6266654b4b72c2cce40a38247874797474794e4f71eb1b095658467b7a7f6665617b7063c6caeb43474d606161cf606f8e766d960e4cb1a8a99dfd1c9228479d7f6d9e7a6ec2646de3686ddd6a6dfe676f6465644b4672c7c8eb3922537b7b7f787a624c7275e817362f5d447e7b796462657f7560c8ff1a40464c606367006469ab676d963371b3a9d2981c25925f719c7c6f9b746adb646deb6a6dcb676df0676f67676a4f4a4ddec4e525575878757c7e797c70737511170a295c4178787c647d6762747dcdf4104a41767e62613b6a69ae656d953548b1aaad953a58924e7d9f7c6d94716aac656de76a6df66b6df3656f6467654f4b4cdfcde52f56437574797b7b7f3e716812060c2f5747787c7d646160734c7ff7e901474b73637e653a6b69ad6a6d953f458da8d39b3b55924e60987f64914c78aa656deb6b6dcd6b6dfd646f67676b494971c1fae82d544375757f79787ce6426b171b0d5355487b7a667c7c664a4472e1120543474d7c7f600f6568d66a6d9730488da8d298192892736194746a934c61ad646de96b6df76a6def646e67676a484a4cc4ff1051574374757c78787d15436f1b022155554878717f7d7967494677e7ef085c414f7d7f6303676ea4676d981b2e8dbca09fef3b924a7f9e7c6e997969d76a6de3696df36b6dee676f67676a4e4971c2c8e62e515975757e78797ccc5d6c15033154424978777d62797f444672ec1d31585d497c7e60366768a5616d971a2cb2b7b598eb359244798b7c6d857c6dde666df5686dca6a6dc8666c67676a4f4973c6fbee3f285775747e797b7cd23f6d1e073d5446487a757979767f5d5f4e190438425d45797e63216468d7646d931d5d8cbaba9b1f22924e628d7c6d8e7e6ddd676dfa656dc2656dd57e6a67656a48454ed9cafc32392a737374777778ed2c6fef060e5a554b757e797b78625c5c4a1b00305c40497b79622b6769d76b6d933e4bb3b7ba9a0129924c60b7606d8d606dc2676df4686dc26a6dd57e6a64666a454573f1fa1737222f4c4d714e7376e72669eb150f55564575797d7a757d575b41ec1d365f5d4b79787c2a6769d6686d93084eb3bbbb95002f924f60ba646db1676dc2616df0646dd6646dd6796b6466654a4873f7e6143f25574c4d774e4f71d73e65e8180f555a457b7a7c75787e53505f131e325d4349787d62296768d66a6d922967b2bbbd95022f924c63b6666d8d666dc06a6df2696dd9676dae756766616a4c4576cde11a3e2a57724d774a4e71e25166e51932575547747479797a7f29515def150d435c487f79793d6469d3656d92526fb2b4b99a102b924d60b76b6d896a6dc2656df1646dde676dd27b67666366494c70f2fb14292c5e707378454970287365ef17332c544b74747974767f265257e81b0c5d594a7b7b7f386468d1646d925069b2bebd9a1329924d60b46b6d8c656dc16a6df5686dd9656dd578666660664e4872f7e21b57564671737a4a487225535e1b1836575f4975777e787b78262c57e0eb065d5c457b7b7c356468d0656d9254658cbea594102e924963bc616db9616dce656dfc6b6ddd656da04c786667664a4e77f7e216595d4a7270784f4c702a505e020f3c5b404974717e7b7b782b5243e6e8055f5d4a787b793f6769d0656d925f6b8ebcd19b132b924862a6666da3606df0646de16b6dc1646dbc4a77666066444972f4ff165f43497677794b4f765355410233235842487a747e757a7c292c5aeb14085f5c457b787c376568d1656d92586e8abcc39aef2a924b7ebc616db8616df6646dfb6b6ddc616daa727c63606a474871f5fc1b5b5f457a7a7f4e4c7758434907323d5b5f4477737577767b212c56e4100a5c5c497b7a7e336769d0646d92596988d2c29be83c924078b1616d8d636dcd656df06b6dda676dca7d656063634a4573c8f8ed5755447b7b7c72717543434a020a395655414c4e764c7275242656ef100a5f424a797a7f366469d0646d925e6885a8f09fe10f925a738f666d84616dc5646dcf646da86a6dae4c7f676067454970cbf510555b417578627176754e4f73000f22505a414948714f4c743c272eec150b5d434e787962326569af616d92557e87c0e983f110905772b2796d8a7a6dc1666dcb656dd6606da347746762614b4b71cffe13595f4a787e7f757b784b494d0531215a5e4644474c4f4f7022242fed1d0e40464e7b7e7ff1676f89796d920b4787c8138ac2cc90447eb3666d85636dc7646dcd6a6dc1646dd07361617c614b4b70fbea195e5d4b78797c7b7a7f4c4f710d3a2559424a494a764c4c75272b5115033341464f7e797cb15b729d426192045f86cbe082150d90766a8e646d85646dc4656dfb6a6dc5646df2626e6263654c4c73e3ea025456417979627a7b7e74767b3339295c424a4f4c7072767a252d51141d0f44444f7e7963b75e7688786d92517c84f710810d3e9270658a7b6d8d7f6dca6b6dfb6b6dca646df0606f6262664c4d75e613002f565c787e6274757e45497037232c4046494d4d7776767b28505b121f0e44454d7c7d61ed676ebf636d922b708aff14843238924d658d626db4606df66a6df3676dc76a6dfe676e626060734e77e811062c5642787e63797863494d74353d2f47454c727674707478242c54121f084f4b737c626000666e8b7e6d91ff3a86dcfb831b06927469ba606dbb606dfd656dfa6a6dce666de6666e6260664e7276ed1306575d45757a7c7a7e7c7a7a793d262d4b4f7371757a747b7b2b505aec19094a49707d6360096769b57e6d94c11d81afdc9d053193756fbe676db9666dff646dfa686dc8656de2666e6262664e737410190959424a7a7b7f78796278787c2729544f4c7774747979757e232629131c0e497370627c62196769a7606d910f5484d7c4813f2b91796da3656dbd656de56a6dfc6b6dc96b6ded606e7d63604f7377171d0e42414c7f7f617f7c63797e6052565c4f4d777a757e7a7b7f3c25501c05344b70717f6066e3666eb9626d92587a86cf1284285695786fad656daf646dec6a6de3656df66b6d12606e7f7d634b4c7114000d4949706160657d7c61797962525b434c4d747e757f7a7a7e38222b08303d727777627c66fa606eb67e6d935d7f85f9059f48638b666dd0656dd0676d1e6b6dec686df76b6d106168787f7c474972020e3872717a66616a627d63787b7c5e404871767b7f797d767479343c250931214c767a636366f2676ebf7e6d93437c84ea339476678a646dd1656dd0656d03686d1e686de26b6d016365757a7f434b4d0836214973786666656666647b7b7f4b49717574797d7c634f4c700d38263b3e2f717678616164c27f6e8c756d94567a8b0327917e6b84656dd46a6dd46a6d33696d05696de96b6d0862677776795d4a4d323e29454c7a606367676064607d674e4e7679787c7f79635c5c45070c3d26525b777778666165ea616ea4636d944c6a8b0c58947e6d87606dd0656dd0656d09686d0b686def686d0d7d667677795d4772352656444f7b7e7f606360676767677376757e796274747828525b060a3e2857427477796060601e6569d7676d94756d84204287666db6656dc56a6dca6a6d30696d32686dec696d367c67707478424570262d4242457476757d7c7c61606066747678787e7f4b48723b3d2930392e2b5a424c72757c7d60136669d8676d997f6d875174b27c6db5646dc46b6dc46b6d08696d326e6ded686d0c63644972745d4a722f564643457649707e70747e7b787d747a7977747846454f313825343c2d29575f4948767e7f63e26368af666d98786d84407d89636da0656df5696df4696d37696d336e6d126b6d017d64497274404e70515f4b464e76454c7b484c754c737b71767b7273755b5c440f352523245628525f5f404b75757911606bf062689e706e8a55748c666dd36a6de0696de2696d35696d0f696d3d7c661e63654a4f77464970545c494a4e714e727a4b4c754d727a70767b474770272d583a212d2a5140262e5a5f5d4b4b4973717078fe7c6a98716d8526468e636dac696df8696df5696d1e696d0a686d3f7f6172767b4d707a5a5c49404570727779767a7c71767871767d47414f5b5c4b392051232b54525a43242f58515b40595f444b497177767874767977767b7072754d4d774d72777372757071757176787574794d727a5a5f485f414c72717b76757e7a7e637e7f61646465595c4a21295821285825505c2d55435055405658405842455658414246494e4f74734d7a73737871737b73737a73707a4c4c77484e765e434f5c464d45497173777b767a7e747f636263674b4f702a2d5428535c525a412c54432c5b42535b435a5f445c4649484c7149727742454f5e404b59424a585d4a5c404940474c454b72444a70464b73494d7770747b76747874757f76747c44444c303e2a131f0e010a3d555e47545f445e40485a5946575e465f424a5e434b4b4d7172767572767a4d71744c707448727644484d474a4d4972774c707a73777b70747b717778484c76313b2a1f05373139212d56595c414a5f454a'
_TMPL_SP_W = 21; _TMPL_SP_H = 86; _TMPL_SP_C = 3
_TMPL_SP_D = '2028575e414f4b4e764a4f744d717b71757f71757f76757f767a7f767a7c767a7c767a7c767a7c767a7c777a7c747b7c7b7e627e7d61787c626b686e093c2529535e4a4f777b7962215d743c42753c437929477851497b594c6345726473736452457e46497d4a4c62554b7b404d624a70784e7662626263686b690f392e545946777a7c5a4a783f5575f2307cd71746bfc21482b0db9c8aa69db3da89bdcea3d4efdacd04c4ec39f61624e404560b2f4b56487b7e616b6e6f6e353f2d5d46497e7d614d6066294463142662c50675ad1078b2124489104eb3e64eb7f45eb4f42cbbc821bdc726bdc43faff321c212582d4e797b7f646e6e6f3a3e2d4e4d777c636161646b4b717f797f65352c77362671093c4f130c48ef1c4804334e1e0f4d01394536224a235049554a4f4a75734d747e767d696c6e6e22295a72767a6766624e75636a646b696a6869656e6a6a69093c4f130c48ef1c4804334e1e0f4d01394536224a2350496968616864677c7d647662686f696e535a5f7775796363600f22533632200d2a55340f3764676464676965656266607d667e7f637f62616364676063686464686464ee1a3b3035584a44767f7967554371717478636065fcf802cbc8f3d9d9c1dbd5de717b7665646562ef66c297fe17982348a47044c57650d0726564667f7e7fc6f01d383e534e4477797c684649774e4d777c7c60676469232f5ff3f1e2d3d1d7574241646667631165bf96d61b99374ed1744ac47624a7486a6a6b4f4e7addc81057504375487b7f7d6e4d496442464e797d6064616a71737bfee837dfc0cb575f466167647d1764b897ab3f9f567acb7c73fa7b5fd1736764654c4e7ad9f11e5e5c72784d627e7a6f767167545e47747b7d7c63604a4d7b0d3e5ac4c1cc54594b636667621165be97ac2c9f457ccf617bee7c4cc37f646a6a4d4e7ad8f6ed5f58487a447f61636e79716e2c565c49727a7f62617249752b3c59cac6f248454c6666657d1365be97a9249e4463f56775e57d72c27c676a644f4c74dfcd1a575d4874497f677a6f667b6e2b5259454e77797c60754d7f2d5144c5c4cc4b444e6667647c1064bf97ad279f4460f76475ff7c73d97f66666a4c4d75dcc9025b59497f7063697c6f657968252c5b474971797f6375767c515345c5c5cd45484d6765647d1364a097d22c9f4561f3647bf77d76de7d6a6a6b724d7ac6c81b595f4e6174666e666c68606e252f5b464871787e637a707e57554bc8c6cd4f4970676465621364a197de219f4566f76a79fb6374dd636a676a4d4d74cefa005b5d496a7f67696a6f656a6f252f5b464871787e627b736254564adcc0cb4a4f7264646a631a65ac97c7289f4e67f76a7efb6074dc636b656a727375c9e21a5d5d78686a676f6b6f6b6f6e252f5b464871797f63797263505f4cdcc3ca44487665656a611865a994c62c9c4e67f66a7ff96074d963696a684e4c71dde21e4d47706e636b6c6e6e68696f252f5b464871797f637f7561514348dfdcc45c454d64676a601865d394cb509f7266cc6a7ffb6074de626868694e4f71c0f81a4a4370636b686f646f6e6f695459464648717e7c6079626752424fdcdcc75c4f72676765631f65d694cb5a9c7067cd6a7efe6377d27d686b68484b77d9c5104a417169676e6f6e6e69686f252f5b464871797f637c7c65565d4edfc2c45a474f656465601e65db94f95f9f7067f76a7eff6077ad7d686868484b76decce85848726e6f686e6e696b6c6c252f5b464871797f63626665535f49dbddc7574049656565601f6ac194ea469d7667f76a7efe6370ad7c696a694e4974cee000474e746763696e6c6f686c6f252f5b464871797f6060666a555845d9d8c051424c6a6b657fe867d897fb459d7467f16a78f6624dab7e686a6b4c4e74f4e6054d44746962696b696965696b252f5b464871787e626664685c4973dad6df2e58486567694edc7da194d94a9d7161cd6478fb7c4fab796a6b6b724977f7ea054074766e6b6b6e6f6f6a6a6e252f5b464871797f63606765434f4dd6d6df2b574167676a74f860b391bc2e995b78d46274e27f47a97a656a684d4d75e6e90d444e7063676f6f6f6f7c6569252f5b4648717e7c6060656b414975afd2da20545d66646871f263839084149a307bd27d72f17b43a8746a6b6a724d75e0160c4649736a6665696b6e606f69252f5b4648717e7c607d676b40747eaaa9d63f505c6665654fc27d8690892c9e5e62c6677ae57c4dd57f6a6b6b4c4c74fdef327345706e64656c6e6c676b6a252f5b464871797f637c6668464c79bda7d23a2a5866656749c07c9e9382439c4961cd657e116376dc626b656970717ae3160f4b4a736967616d6e6e7e6b68252f5b464871797f637a7b65424e79b8b9a9392f5b64646929b3769b939e2e9e5d63ce647d1f6074c3626b6a6973777ae8170c4a41786162656f6f6e636169252f5b464871797f637a786a44467eb0b5a122285e646a6a5aa07a8a91b000992762c0667e15637aca636a6a6973707bea1733484176676b646f6e6e7a7a68252f5b4648717e7c607579607175618cb1a3272e5c64646b74f960d594f43b9f527cc6617f1a637acb60656a6a4f7078e5ed0d464b70636465696e6e7e776f252f5b4648717e7c60767a604c497eb4b9ab255447676764631c65d995f83e9f597ad27c7be97c7bce606b696a4c7275ed143b4740727d65656f696f61656e252f5b464871797c63744d794d4f7eb7b9aa505a45676664601c65da95cf259c5e75d47d70f87874ca626a6a6872737afc17364041766665656d6f6c6a6969252f5b4648717e7d604a4d7577767eb4beab2b544361646a631c65ad94c458824b7dc76171f9787bce61656568737278ea010d414f766463686f6e686a6f6f252f5b4648717e7d604c4d7b7f7178b1bea9535f406665657fe866ab97df42834c63cf6479117d79cc616b646a73717bef1a32404777676b6b6f646f637969252f5b464871797c60797674787b7fbebfaf53594566666578eb61ab94dd43834f61f26463066679cc6665646b737079ef1909404a7163606a6c6c6e6b627f252f5b464871787f637b7062757e7dbbbdad53594e6666647fed66ab94c041834c60f265631c677ef76667676a737678e2110e5d4771677d6f696f6e46646a252f5b464871797c60777561787a7dbabead505d4b61606777f963aa94dc41834d61ce65631f677ecd66676468727079e61731415f776366686f696f71726e252f5b464871797c607179627b7761b5b9ae5f594866666a49ca7faf94c34a807167f36a63186779cd6665646b70707afa17335972766667656e6c6e717a69252f5b464871797c63757763727763b6beac555f4b6166654fca7ea396d04f817567f16a63186779cf6664676a72707bf4fb065d474861676b6f696e77786e252f5b464871797f6378797d4e4e78bba0d05f5d4e6467654dcd7fb796a04f817567f66b63156779ce6665656a71767af813045d447e6e666a6c6e6e766565252f5b464871787f63606064717760bca2d342437366676a74e260b691a24c817464f66b63156778c961656568727678fd17305d4573667d656f696f7f6267252f5b464871797c606a7d6a4f4c7dbfa0d044444d6766657ae160a396ad48807666cd6563186778ce6167646a72717afc12095e5d4d60646a6e656e737b7d252f5b464871797f60677f6a41467cbca2dd4b49766660657bee60d695c548827460cb647c17617ac56365676470777bfd110f5845497d7d6568696b717a7f252f5b464871797c6066626b5c4a62a2a1c449457667616a75e262db9af272807b60c5647ae17c49d778646a64737078e0ee0c51434c6178616b616b49717c252f5b4648717e7c607d626a58457aa0a8ca484f7167606676f57cdb98f04c837b61c96578e56248d778676664727075fd1409585e487b796068606b4e4c71252f5b4648717e7c607d7d6558464ca3aac7454e7461636a72cd7fd098c972837b60c9647ee86270de7f67676472727b161b31565c487a7a7d6a66674e7b79252f5b4648717e7c607578645a5848bcaadc4f49746366644fca7eaa9ade49827760cb647fec6376c37d666667707075e41709535a44747879656067714f7e252f5b4648717e7d616161645b5f4da3abc04c4d776066677be163d296ca4a9d7660ca647c146175ca636160644d727aeb1b095658467b7a7f6665617b7063252f5b4648717e7c60627d6556554ea6aeca4f4e746061657d1166d997f547827060ca677d17607bc963646064727175e817362f5d447e7b796462657f7560252f5b464871797c60627c6157544eaaaec74849756361677eec66da96f145837061cf677c13617ac96364676473727711170a295c4178787c647d6762747d252f5b4648717e7c60787a62525645a9adc54e4d767d626479eb61d096f24a837061ce647c03607afb606961654d4f7712060c2f5747787c7d646160734c7f252f5b4648717e7d617462622b5640acd3c8494f7763626174fd63ac94c645837061f3647d0f6178ee616a6161724c74171b0d5355487b7a667c7c664a4472252f5b4648717e7d61757b7829505facdaf34573776360674bc079a896c044827363f2677c30607918616767644d4d741b022155554878717f7d7967494677252f5b4648717e7d61757a7c24255aacdaf5454d7763636142d777db94cf4583737cc7607e3363790e66606065704d7415033154424978777d62797f444672252f5b464871797c6075757f392655d2d8fe4e727a637d672ca34ca597c04b80737dca67790d627e35666061644c727a1e073d5446487a757979767f5d5f4e252f5b464871797c6070737531342eadd8fa4a727162636158ac76ad97ca70867863f6667e3963750f636060614c4d7aef060e5a554b757e797b78625c5c4a252f5b4648717e7c607a70750e3953d3daf84a4877637d674fc979d396c85c864a62fb6678337c71067d607d604c7274eb150f55564575797d7a757d575b41252f5b464871797c60747775373b53d1d4ff414b4c627d6078ea61d494f35d844562fa61761f78740c636363614c727ae8180f555a457b7a7c75787e53505f252f5b4648717e7c6079747920255adac6e84341497c62617b1f62ce9ae8428a4463fd664de77471047d6362614d707ae51932575547747479797a7f29515d252f5b4648717e7d614c4c762a525fc2c9175c5f4e7f7f617b037dfe8610558b5c63e16148c870701c7f63626070727aef17332c544b74747974767f265257252f5b4648717e7c60487371505146cfcd115b5b477f7f63750f7fcd81e63587237bc27f44c27170007c6363637173781b1836575f4975777e787b78262c57252f5b464871797c604941495a5b45c0cfe85652427d6266771d78dc82cd03820d78c67c70127a4c1e7f7f7d60767079020f3c5b404974717e7b7b782b5243272e5a464870797c604b4b72565b73c0c914282c5d627c60710778d69cdd109c1d7cf96375087f4e1278627c617676790233235842487a747e757a7c292c5a272e5a4648707e7c614c4c7a5f4549c0c71226295d7d7f66753a79db83ca169d1c7cfe60740b7f4eee78787c6270767807323d5b5f4477737577767b212c56272e5a4648707e7c614f737a464a73c2c8eb28245d7e7e63743579d69dc01382197cfd6374057e4af87a79627d70777e020a395655414c4e764c7275242656272e5a4648707e7c604c4c744c4073c8c71324215f787863763a7eae9ed4ee82147ff56276027842db717c7d6074757c000f22505a414948714f4c743c272e272e55414b737e7c6173707a49584ccbc91b27235e79797d763778bd98abe883177ffb6273167b5dd6717c7f617a787f0531215a5e4644474c4f4f7022242f272e55414b73797c6070707a5c5b4ac1cee927235e7c7c61713778bd98aae980147ff96370147b41ca71637c61797e7c0d3a2559424a494a764c4c75272b51272e54414b737e7c614c4f7a5a564bcbf3ed2a53597e7c6373337bbc98abed801a7ef96274087e48e57a7c63677f7f633339295c424a4f4c7072767a252d51272e54414b73797c604c7574565242d9cbe929535e7a797d73337ba499d11f8a0a79f46275307f4d14797c7c607f7c6037232c4046494d4d7776767b28505b262e54404b72797c604f4c71575347c7f3ef272e587174784d0c7aa89fd432b33e7bcd7d740c7e4c12797d7c637f7d63353d2f47454c727674707478242c54262e54404b72797c61734c7a585742fae0002f2e437b7b7c70087bd09ddd3db42f74c77c711f794bfd7b6262667c7d603d262d4b4f7371757a747b7b2b505a262954434a727e7d614c4f7a572d5ff1fd105655447e7f61710179df85cb24bc5177de7e4de97a44f074617d666262612729544f4c7774747979757e232629202957434a727f62664d4f76532d5bc9f512505443787e7d76ed62cc8ae254a04177c37c4de87a4af775637d6662636652565c4f4d777a757e7a7b7f3c2550212e54404a727e7d614d4c76502f5ec7f1ec555446787f7d4cf47de5b21c5ea44b77dd7c70127b4ee57b616361626366525b434c4d747e757f7a7a7e38222b202956404a727e7d614c4976252a54c7c8e85b5a4b7e796377ef6018b40c59a74976d578761578701b7e6161656260665e404871767b7f797d767479343c25202956404a727e7d614d4d723d2457cac5e95e584f797f6277ef601eb43159a64e76d87974027976067c6762676060674b49717574797d7c634f4c700d3826202b564345727e7c6072727209332bc6cbe5405f4c7f7f634ecc7cf9b21b5ca84d75ca6274017f77077d6661666061674e4e7679787c7f79635c5c45070c3d202b564345727e7c60727376080823f3fa1143424f7f7c634df17cc48bff4ad77578f962740b7f76037c6361676161647376757e796274747828525b060a3e212b5643454d797c607348761b023df6f81a5c414c7c7c62741362eca2024cc5797be162740c7f71167c606366666664747678787e7f4b48723b3d2930392e262e57414b737e7d614b4b701f0238e9ef065b5d4f787e7c77106230d52a70f17e79eb6374067c76ed7c616666666664747a7977747846454f313825343c2d295059484d777c6366434248000b391219315b584b79797f77146253ec4070f37f78e560741f7d71ee7d7f7d637e7f6371767b7273755b5c440f35252324565b5c4775787c6260665858441f0a3e09332059404a7b787c77777843014d70ca7f79e663741c627e7c6376747976777870767b474770272d583a212d2a51404d70747c636143464b2c575e1c093e382352545a414a49765d4248444a4d444b72484f7072737570767b71777b7a787c47414f5b5c4b392051232b54525a437c62614243492c545e3d2a5605362a252c5b262856545e4740474c444b4d494f714f727772737472707a70767b494870595c4a21295821285825505c2d55435a5946522d58202b54303825262c585e424b2729552b535e535b41515947545e4458404b464a4c444a4c5357432b2c5e28535c525a412c54432c5b42535b43'
_TMPL_MP_W = 28; _TMPL_MP_H = 101; _TMPL_MP_C = 3
_TMPL_MP_D = '71747921544ff50256f2133dcae935dee10aa9c9e8aac7eab5daf98aabf486a7c59cb7d79cb7a9998eb1818ba4858ba99b82ae9d8dc099b4f380a3fb88a4efb8db1ad4f336150f575e414f4b4f762e5042363f2c7a797d424b70212a44262b43063f2fe50e29f2082ccbed28dcfc2cc8112cc4115ff11c5ffe0b43e93244ec317315394e1d224c0f21723456733f557a2258412c5b48535c444449764d4d7a777a7e585d48392151744c772c544578737761637c6b65636b6860f80f50f71d2cdde320d7e02cdefe57dafd24dcea24c6164bc90a54e608401c34473250702e5b70487a7860607f7f66607d787c717b7c4e4f73737375474b7326295847434fe1e203dcc4f9c0c2f50d003368637c68657d6965636865656f65616b68626968796469606a69666968666a784c696178697d7c6a7c637e797758594babdee1d6c0e9c6c9eec8cf125b434b454870202a5a4a4771eaec0bd9c6fd8b8eb6898d8a4973726e686e6c72e46d4b8d61049211b49224bb926adf926de6916d118e6d53d26d5cac6f288d641fa56767664973728688bc818eb2c3f2e8333b2e565e4743474c3d255449474d707b7859575ec2c8ed949b9a5355516b696a6e74ed6d4e8c621e92efb6922ca49264de926dd1906de78b6d2cad6d53aa6f358e6406a77c63645355519e8284b7a8c02125585858454d737a595d483f26567074794d737b737a73e51434979495595e5e7d6667687f1a6d7b8c7e1192c78d922ea49264c8926dab936dcf8a6d30a06d3da36f36886537ae7d6060595e5e989c84ceff142f5a4142414f494c772f5142373e2d4a4971787f6250575f110027959594435c437f7f7d6b7c196d788c7e1d92d58e9258ac9265cf926dd8936df08b6d32a66d39a36f0a8b653fac7c7d60435c43868b8fe7140954584a7a787c5d464f22245508312b515b47777a7e5358420b3b249a9e9f4640447b797c647b176d758e7e1392c2b39249d5926ae4926dff906d1cb36d2fd36d23a76f1c85650ca97e7d7c464044b7bbb9eb140f5459454d707a525440363e2c060c212f514373777857424f092054989d8345474b7e797d6a7b1b6d768b7eeb92c18d924bd3926b18926d17936d3bb76d47c26d55ad6f0c886500a67f626145474bbfbca6eb110d545948454970252f5e0d3529000e232b525d72717b55424c303f2d8285854a47497c7d63687f1e6d70857eeb92c18d9240d3926803926d03936d3ab56d46c26d42d16f298d6503a76260664a4749a0a6a4e9ed0f54584e4448702128580f3428000e202a525c4d717b555c49353d5180818a44444e7f7c666b791a6d71857be492c6b2925cd092681f926d0a936d39ba6d41dd6d59d06f228c650aa47d606144444ea6a7ab17153c5c434c454870212b5a0f3728010f2628525c4d717a5f404e3321509d8187444749627c66697b116d728574e992f4b5924ad492681e926d04926d3cba6d46dd6d40d66c2e8d6a3dad7c6664444749a6a6ac1d05224b4b744e4d742f56433a20500b312a2a525c4d717b40434d3139529c82814544487d7d60687b116d728a76ff92f9b4924fd4926b15926d0a926d22b56d44c36d47d56c51b36b27d2666664454448a4a7d3000821494f784e4d752e5143363f530533242b525d72767b41464f30355381868f45444e7d7c606974ef6d488577fc92fcb5924dd9926802926d0f936d20b56d4ac06d44d56c57b36b2ad367676745444ea8a5d2060c2770707e4f72752f5640343c500a302a285043727678484f743920578cb0b84a4a49797c636877ef6d4d8578e492e7be9272de926802926d0f936d2eba6d4ac36d44da6c56b36b22d264676a4a4a49aea8ad07332774777e4e4d75295043303952070d252e51437376784c7675232b5f8db6bb4745487c7f606877ed6d728579e792e8bf9273c3926b1e926d0e936d27ba6d4bc06d46da6c2cb26b0cab676664474548a8a9ad0d392876767f494c74252f5f0d3b2f070d252c574673767873737c3b2a578d8db943434b7d7c606874126d72857efb92e5bf9273c0926b1e926d0a926d2ebb6d4bc06d41d56f288c6a07a46b676543434baba8d2363d2d767a7f484c77272e590f35280209262d5446707779737378333a2db38cb45d4148797c616878176d74857efe92ebbd9272c3926b17926d0b926d2ebb6d4bc06d43d46f288c6b03a164656b5d4148aaa9d3383e567b7c63494c772729580830251f053c5254467077787371753e2656b1b6be5d414a7d7c636879186d798579f992e5bf9273c1926b1a926d09926d2ebb6d48c06d43d46f3d8c6b09a56467655d414aabd2d2372254787f6645497021285a08362a1d0823525441717478714c7b393854b5b6be4047487e7d6368791a6d7e8478fa92e4bf9272c0926a13926d0d936d2cb86d48c06d40d46f0b8b6b36a8676b68404748afacd626285779797c4549712628580831251e043f2f515d73767b77717b0f3756b7babf4146487c7d61694cea6d778779fa92e4bf9272c092681b926d36936d2eb86d4bc06d58d06f1f856b0ea5656b6b414648afadd1585d447f62614a4e762a2d5d33382d0209202f514373767b4f7379010b2bb2b1ba5c404a7d7d606e54cc6d289d41c792fbbb924dc392681b926d32936d20ba6d45c06d55ad6f0888680ea56568685c404ad2d2d04757497f616a4a4e76252d5d33395006322a545e44777a7e7570790c37278db6b95f43457c7f606e27c36d0e9f25d392c4b39245d6926aee926d0a936d24ba6d44c26d59d06c258c683dac6b65685f4345d3add14d5d4b7f64674a4e772853433039530209204748707b7f62454d741d322ab1b6be4041497d7e616e50cf6d568355df92ac88922eab9267f8926deb936d3bb46d5cdb6d56ac6c268c6825d368686b404149d1d1d17a464d6165654a49762629590e34281f0a3c717479595940464c74033b2fb0b4a243404e7e7f636876ed6d2f822ad092bd879206be9263c2926dea936d0db76d55d46d56ac6c398e6928d3686e6b43404ed3d0d045417261646b45487126295809362b1e053c787e62717674494f763e2651b5b7bc44444e7f7f63687f1e6d2e9d35ab92aa8a9254a99264fd926d06906d22b56d40d96d44db6c53b2682dd668696844444ed2d7d6455f7066656b44487020285b0e37280309202a2d2c2d5b5e4944753c2955bbbbb84a454e7e7f636b7c1f6d588325d292a4849224a4926a13926d33906d29ba6d49dd6d48d86c57b36959d669686b4a454ed0d1d5404171646765474870272e5e0c3b29030e2039202538262c4a7076262354bbb4bd4a45487f7e63687f1e6d3b9f08a092be849214b8926a13926d0c906d29bb6d4ec26d41d46c29b2695fd7686a6a4a4548d7d4db584676606765474870272f5e0c3a2e030e213d24293f265143404c222c58b9b7bc4546487e7f606e3ad86d1b9804bc92bc849213b59267fa926d07906d25bb6d4ec76d40d46c29b2695ad7686868454648d4ddc2575f4d7f676a4549712629590937280208212a53582f5b43464c722a5058b8b6bf45464a7c7e626e0cd66d0e9c55db92c1b49235a39261c5926d1d936d24bb6d4fc36d4bd86c5cb7695dd869686b45464adadfc353594f63666a454976242f5f0e352e1c0b202f5242434a4c7276762c4243babba744404a7c7f62695ff46d5f8340c092ceb59254af9267f6926d1f936d24bb6d4ec36d4edd6c45b46944df686b6844404ad9d9c72f565c636767454e76252d5c33392d063224555e454a4a73777a7e575c42bbb7bc4640457e7e6368791e6d778770f292cfb59253d39266f5926dfe936d38b46d49dd6d4cc26c4fba6945df686568464045dddfc726564779607f606164464b703d2a5b010d244544714a4b76787a66555845b5bea1404345627963687f026d758773cd92c8b0923ca49264f8926dec906d0db76d47d86d72c36c4dba6e45dc686b68404345dfc6c82c564c78787d67646a4e727a252c5c08362871707a4b4b7078777c2c5e46bcbdae44424a7f78616b7c016d7a874dcc92c7b39225a8926aef926d02906d31b76d44d86d72c36c72bb694bdc656b6844424ad9c0ce505e477a7e7f737679747a7c57594a3a2251787a7e4f4c757c7860282f5caca8d8455d4a7e7e636b7c016d738645c492c4b49254d0926b12926d0b906d26ba6d4edd6d76c66c72bb6948df6b6a6e455d4adcc0cb5b444963787f484c777c7d614045723f275479757e70727574757f323352d6d1c0415d4a7c7f626b7c036d498046c792c3b0922dd2926bef926d09906d52b86d72cb6d77c16c72bb694edf6a6a68415d4ad8c2cc5643417d637d5c484d5751497271782d57467a767e74707b774e7a0b0527dbdbc7465c487f7f616b7c006d4f8044c492ddb2922cac926b11926d05906d53b86d72c16d77c16c76b8694fdc6b6e69465c48d9c6cc5f43477063604640702f53437a787d40447272727570707d714d790e3024dadbcb4440497f7c60687c006d4f8045c692c6b39255d1926ae9926d32936d50be6d73c86d77c76c77b86e4fdc686568444049d5c1c95d59497d63634641722e524140414e7174794a4f7674757e7f7b6031232ed4dbc74a404e7d7c606971136d569d2dd192c5b09251d29265e1926d0d926d56b86d73c86d77c76c71bb6e4fdf696a6a4a404ed9c2cc5a54486260644b5d480f365252504454594741444c7e7b7c7e63670e222ed3d4dd4a4149627c66697a1b6d579d2dd692c4b29256d0926ae8926d37936d57b86d73c86d77c76c71bb694edf6a65684a4149d9dfc75d414560676a72714f131f0d3d215b5d5c4c595d4572727860626a0a3a52a9d3db48434e7e6267697f026d5a8229ac92c38c9254d1926b14926d3a936d57b86d70c66d77c76c73bb6948df6b6a6848434ed5dcc94242477d626b747a743b3d5a1114382c5240575540474b72656162323e29b9bda845444e637d61697c006d468327ad92d68e9254d5926810926d39936d54be6d71c86d77c76c4cba6b4ade6b656845444ed4dcf05b5847617d69786379495d731d1d391a1c3b4243497a74796a606a090e22b7b8bc4e454e627c61687c006d728653d692ad88922fac926b14926d38936d55be6d71c86d73c16c44b46b44d8656b6e4e454ed1dfcc2c544665666b62636a724e7642414f101a0a71707a627e606564690e0f20b0b7b972494f7d7d61697e1f6d4e8358db92d08b9224ab926bec926d3f906d54be6d73c86d4cc36c5cb66a46db6b6a6b72494fd5dff524505f6a676b626767797c6177707f0b093c79787c627d67656767330d238cb2b8704972627f666979196d4e804bc492c1b2922daf9265e6926d0d936d54be6d76ce6d4cc26c50b36b5fd1686469704972dfddff3324506e6468676b687879674f7278464a707e7862616164646b6a1d302f8889b4724b727c7f67687f1c6d498049c792f2b6925cd69268e8926d31936d28bb6d4ec76d59d06f15856b27d26b6868724b72d8c0fc0d205965606e6b6268797761313c5251554f777678627c646a65690a3551808abe724e727c7c67697b186d5f8344c192f5ba9240d5926b1a926d35936d2eb86d47dd6d50af6f1785692dd36b6a6a724e72d3dbf40f352d697d69677c6a2f554a35392722212f74767a75767f686a69043f528489b6724976627d67684eea6d5a8242d592f0b6925cd0926810926d3d906d52bb6d4ac06d5ed16c398c6944d76b6a6a724976abacf5190f2c69626e7e70620b3d2d223c275843467e7a7d7a71636b686900332c8688ba7071766660666947fd6d569d57da92c7b29229ac926516926d3e926d51be6d4fc46d45c26c44b46e4fd96f646b707176aba9f505002d6963684a4577083a2837363c747778617c607c7863656b6e0734538489bb7071766060676847e06d239d53ad92d98d9236a49267ff926d36926d55be6d4fc46d4ec76c4eba6f4edc6e6b69707176a3aef70e385a6567614349721b09210c0d3778757d607f617d7862676a6a0e3850858fad73737a66636b6958f46d559d77cf92de8d921cbd9262f2926d30926d59bf6d70c96d70c86c4cba6e73d9666e6973737aa2bdfc213b536b63674e4c4f1a042236303a7f78607e7b7f7c78626162663a265b8a8fd572777a6663656e2bcb6d47837ef492ceb79208a4927cc8926d34926d5ebf6d77cc6d77cf6c72ba6e4cdf6b696972777aa0aace3a38516675604f7a7b0c3e53213d2e252752724e7778787d667b6237255b88b0df4d73756661646e5bf66d728376f092f7bb9231aa927ccc926d37926d59bc6d77ce6d7bcd6c73bb6e4ddc696e6c4d7375aba5c82927597d7d6775797b2b5042425f4f515a5d44467378777f677b7c2129598fb1dc4d4e736461686f42f96d4a8073f292f2ba920da49262ce926d34926d59bc6d74ce6d7af26c70bb6e4ddc6c6b694d4e73afd6f82c29467f62637e667d3c205a454c747a7862484a70714f757b79622e51408dacf64d4f4d6466686f4ae66d5f837bf792ccb59205a79260f6926d36926d5fbc6d77ce6d7acc6c73bb6972dc686e684d4f4ddff013545a457d7e67627c7f24505f5d41496379667576794f4e77747b7c2c544aa0dbe3734c776464696f47e36d2e9d77fe92c7b69200a79263f0926d30926d5ebf6d74cc6d7acf6c73bb6e4ddc69696a734c77cdfc1f5b4776677f64607e634747727270757c7c6677757c4547734f4972534344afcaef4c4c736a6e686f2dcc6d0d9f45c992c5b49204a69260f7926d05926d55b86d77ce6d7acc6c4cba6945de6e69684c4c73f4e2145c40706a636b7c78634e73757d7f607d7a784d707a484772454e7144414da8cbee4f49706a6a696c20c76d11984df492c9bb9208aa9261fb926d06926d2bb46d70c96d77ce6c48b56e5dd76c6e6e4f4970eee305454771696468617b7d75787c7e6260777a7b76727542464d4c4d715c4548d0c0ee4e484d6968696c36d96de69849cd92c8b4920caa9261f8926d1f926d23b76d4ec66d72c46c44b4695ed06c6e6b4e484dfce8045541766467697e7678797d627c7f62797f637670755c44724f727b49464dd5c7ee4f48776968696c39dc6de19873e092f0b8920cab9261fd926d00926d3cb06d4ac06d44da6c5cb7692ed36b696b4f4877f51102445e486465687e4d747f62627f797e7b747e7a7478464b73767779454b72c3f01a4d48726868696c29c96d119f74e592cdba920daa9261fe926d1f926d3eb06d43df6d5bd06c2eb26853d36b6b694d4872e7ea0c4a4577607e657d617c7d7d667a71777672787a7a79494f7672777446474dd9f1e84b4b726b656b6f42f96d389d79e992c9b49236ac9261fc926d02926d0a8f6d5dd96d59d06c228d6857d768676c4b4b72e5ee377749716b79616578796061665e5e44744d767e7a7f4c4974494f785d404af3fb154b46726564696974136d40877eee92cdba923aa89266e3926d1f926d108a6d5fdb6d44db6c2ab2682dd667686b4b4672ebef0b4471747e667e657c677d65615b43484c4c753e71684f4d76484b745f5b46c9e0064f4a4d676b696e791e6d45877be592f5b59224ad9267ff926d1e926de9856d55d16d46d56c50b6692fd66b69674f4a4debe930444b747f7f7c63797a7d61684a4a734e4d7be6426b4f72714b4d77515a5ffee3004f4b4c67676969781d6d48867beb92febb922aaf9266fd926d14926dfc8a6d56d66d44db6f53b66854d56767654f4b4ceae90a4072717475635042406663654f4c78707b7b15436f4a4c744b4c77282c59f3e4024949716664656e75146d72857be692febe9224a89261ff926df5936dfd8a6d55d66d4ac26c55b4695ed96b6168494971ec13064b454f7b7f770028507e656a4d46496b667dcc5d6c42474e4e4c762d2f59f5e800484a4c6a676a6e70ed6d438472fd92f0b69220a99262c4926de1926d1d8d6d5ad46d41da6c2db4695ad9646661484a4ce0e4044a5d4e797274f8e31c7d6b64726360637e7dd23f6d5a5d454b4873292d55fe11074e497167646a6e74146d428472f992cdb49222ab927dc7926d15906d0db06d55d66d5fd46f23b66823d762646a4e4971e7170b5f4670737672ea0200646b7b787d7f636163ed2c6f595d4a484a73505843e7110b4f497365646b6e791f6d728a75e492fcb49229d29260cf926d19906d3ab76d50d66d5fd46f3bb36b32ac6a61674f4973ebef08465d4874497d04385062786a7d6879505a44e726694148724d4e71515942e61f3448454e66666a6e7e1d6d728a7be590e7be935ada9066fe936d1d916d3ab56d50d16d59d66f3bb36b31af66666548454ee80038465d4e737a793c3f5c617b66787d762b525fd73e6547484f4d4d765a5a4210063445457366636a6f791d6d728a7b1290ebbc9041c19161fa906d1d956d3ab56d2ed36d50d26f078c6b34d2607d6445457310193d5a42487f4d7935235b6a6b6958547619320de2516646484c484c762b585e1e17344a487366606b6e7f026d738a7e069114aa9147c69466f8916d0b9c6d33b46d2bd26d53ad6f088d6833d2627d634a4873021d255d424b627e7d0f38216e6b6e7040701e093e28736543444f4e4d772e545f010e3d4c45766361646f7e1d6d738a7e1c901eaf9444c49464e1906d3b8a6d0ab46d25ac6d56d26f0cb26b30d2657f614c45761c0023425b4f724c7d4f4a777a7c644c4e75552f4144454d4148704f4d7625525c03083f494c70616266697f006d73887e199003ad9447c69465e4916d3e886d31bb6d2ed36d55d16f0cb36b30d267606b494c70060e2e4643707a75747a7b7a666864764f7843454d5a594747454d4c72712b57591d073e4e4872636165697f0a6d70887f15900ad1944ac9946aeb916d3a8b6d26bc6d50d66d5cdb6f31b36a09af66616b4e48720d322e4e4e4d627e7e6464676a647d464770724f765f5d4e49727576717a2c55410a32244a4e776360616979016d768e7c1e903ada944ac9946be0916d3f8f6d28a36d5bda6d42db6f3ab06a05ae6461674a4e770a09254d4b73657f676460657178655c47727370785f46704c747671707a505842063127444972677c66687e066d768c6230903bda944bce946b13976d388e6d21bd6d5ada6d58d66f30b06a0ead6868664449720e053b4d4b7b6a64666e60647a66794946735f54475b43457172787670795355460c3425474871606363687e046d778d603a9126c2944bc5946be8976d0c8f6d33bb6d50d66d5ad16f32b36a38d16a60654748710004224c46757875757c626949717662626b7e707d555c4b757e7c7675795f5e4b353e214a4573607f61687e056d718c61389127c1944ef2946beb956d0b8f6d04b56d2cd36d55d66f05b26a08d264606b4a45731105397046734f707a555d44757f746a6a6b64676a4e72777d636376727a5d59473426244549707c7d67687e0a6d4f8c600f9153c6944ff69a6819956d0b8e6d00ba6d28ad6d54d16f0fb36a08ae61606645497015073b435d4979637f3d5352717a7567667d786166777578627e617077785f59473a252c4b4b717e7e676e4be96d3d857911912fc6944dfe9a69059a6d368f6d07ba6d29ac6d58d46f23b56a0ead6360664b4b71070931575e4a7f617f0d363b42724d7d6766606565797878757b794d72775742473423534b4b707e7e636e22c66d06807b119138d59445f69b6815956d078e6d0eb86d52d06d46df6c2ebe6b24d56767644b4b70110634512d44797e62010e352b2854637d63666065797c6379796273737b5055433e21524c4c737c7f626f26c56d268860309124dd9447f09b6bf6946dec886d35bc6d58d86d44c36c2dbf6b27d966656a4c4c73ee02332853427f747a383d2e343e2b7b78756161616360617c7c60747479575b430f3f214c4d75607c666974026d558f620f9150c89548f9996ac5946d158e6d24a36d40c36d44c36c50bc6851c36964644c4d75e1191d2a515c4c7a7b5b5842262c5426255148724d797e637c7e6374757f5754450e3e52734e776261676979096d3c8a76fe9100ac9453c19a68fe956d388f6d2fa66d44c56d4bc76c55a26855c0676a66724e77c5e016372052737b77414f4c5b5f4652575f2629557e787f7d7e66797b785e5c4b353d2a4e7276606362697d366d518f73f490e9a59547f99f68ef9b6d288c6d57a46d49ce6d49cb6c55a26859c66b6a644c7277c6e1ee093b20727c7d78767570767a45487240444d7070797c7c637e787f5f5c483a26284c7175606260697b0e6d40b378ef9103d09a7213836802996d2c8f6d58af6d4ccd6d4fc96c5ea66942ca696a6a4c7274c5e1ed08312e70737a7b7a627f787d707a7b4e49714f717a757f7e7c78635b424e3d242c7177787f7c616970026d5eb0620e9428cd9f771c806b069f6d54886d5caf6d70f76d4fcf6c42a76942c5676a6a4f4d74c9ea150e3452484972734f74777678707679777a7b4a4e73787d607b7a7f435d443a3f297270747f7c61684d1c6d53b360309b5ce6837b0784680f9c6d5a8f6d42d36d76f96d73f56c41a76a5cc5616665444971f0ed0030205340464f4a474c4c72717076787471795c5a4460636377767850515d0f3f2b497674787c636b4f1a6d42b4603b9b411184780884683a876d5a8c6d40d26d77ff6d77fe6c45aa6447c974787d404973fa1108302656464a4c4e4f704e7273494d754e48775d474c7f60664a73762627563a3e29727277797f636846e86d2eb362369f481f887e0d856839856d548c6d43ad6d77fd6d77fe6c4ea86747c4454e7159464fea1c340a3d5342414b4b48707176754b4e705e54444772757d7e60595744302052392950484d70757e626573026d41b86028804e0eb47e358e6b218b6d558d6d42d06d74fd6d77fc6c4eaf6744c1474b7056424b180e20092029474b4c4e4f704e72734b4c764b484b7a747c79797c392a2d3139283c2a53444b737b7f7f60710f6d77a06155857138a27f2bb26b2e8e6d5ab26d43d06d75fd6d74ff6c4ca96747df434a4d555d4a07312b0d235046444f4e4f704f7370414b7246424e6363684d73770b3725262f5a3c2a5440444f7a7b7f634d016d7aa061548b7720a07c2cb46a288d6d58b36d43ad6d7ae16d74f96c72aa6743d8474b7343444d333c2c333c2f4b454d4f727677747844454f46404e6464642b28583a3951505840262f5a41474d78787d6349186d4fa066548c7421a66350b56b2cb26d578d6d42d26d7ae66d75fa6c4dab6742da72707b5c404f373d523d285b4e4f704e7273454c744c7271494e73647d6625295b50515e4a454c252d58515b41777679667005644af7645abe7f53d36158a66e54ba6d5bba6d5faf6d77e66d76f4644ff16a46da707178202f583b26545759464e4c717271764448704f72714e7277494a795f554848497b707679535b402f575d4c727474747f6870cb6a42aa6354da6541d66e42d66c5cab6d5bad6d49fa6d4ccd694df17a7a7c474a7026295e2b525d54594744464c4d7376494f764c72714f72764a41736a646563636a7d63664b4977565947555f4448497176717874777f7776797373784b4e764f727474777e7e7862787b7d737378474473505544585f49575945585d44494e704e72734a4c774e7273494d77fefef81f0a346c6d6a6261607c7c7c4e4d764246495f40495e4348454b7373737a75747e7a757f74747e77767973737a4e4f744745705d404c5d414c4044734a4e70464a4d444a4d4e4f7146444f4d7277474773190a32e5eaeae5eaeb131716030b0f4c71714e7276454873454b70454870464a72474b72484e764448714047704a4a71484f764b49714b48714c4d75787a7f7a767e764f77724e704f484d4f4f7340464e212e5a'
_TMPL_S1_W = 34; _TMPL_S1_H = 31; _TMPL_S1_C = 3
_TMPL_S1_D = '61637d4f7377232853ddf2e8f9e10031382a764c7c7a78637d6064607c61636363617c61627d607d7d626162617d7c616362617d797e7c7e6171707871717a7e756267617a6761612b3e3dc5c6f6c2ddc8c7c2f2ccc9faf9fee802020f2d2f5444464848464e4f7077434a4c5c4548171f3bc9f5e7dbc2f3d8cbfdfae503151c33181b351c3234382a242d585c525259232c5e565a58565c425a55405d4247494e74767a7475787f797b7e70767e41424b27202d3e382b3a3b2a223b282d295b444a4e4c72774f704d704f4f4c4c7541444f5d414931232ee1ed00a8d0c0a6a8d9b4a2acb7bca9b5bea8babeaeb8bcd0a2a8d4a0a5d7aeaddedec7f3cff6fcfffce8fbe013ec16031c060b1d0f3b373239505d425d4344575c5c5a5b435959475f5847545f4642414e46444a4a464e39392272717b484a724548723b2e2c131a09d5dcc7d4c2c8c2c5f1dfcaf7c4cde3cfcdfbcffbfccecefac8cef4c3dccfdac2c8d9dfddc4ccf6cbcff1f5cdf6c9f6f6f3f1f1f5f6cee2fdcd352239295a55575e43414445494b495a475d5f4540444a4a46464b26285270707870747b73777a272e56111f06e1e4ec0d353f53545d53555c53515e53565f2d575f2d555c2c565e52565952565e565742565b5d54554355595d5f42474247454147485d4149464a4f484c7375797b6060617f7c7c2e57562a53512121276767677b797e4a49776263637f7c6252535de911031518063f3d2b6b656b62676062606060636362636360626362626066636363636262627f7c7c7f7c7c7c7c7c7f7e7f7e7e627e7f797e7b7e7e79757a7b7b75757b7562627f757a791b0206ea151901330560646763606041424c60636670707f25515affe611191c042a2b2c6160607f7d627e7c7c7f7d7d4047447372737c7f7f7b797b7e7b797a7e797a7b7b7a7b747a7a7a7a75747b75757575757a757b7e79787d627f626760666061737774040c33e112171e05057c627c7c627f6b646b636064766360282c59fbe212141b0620262562627d7a78787978785a585b2626254141467474797474747475747574747474747777767477777474747878787f797f626262636363636363626263676461737074333438e6efed0005087e7d7dd5dada6b6a69494e7a75627d2a535bf6f8e81e1c0425242f7f7c7f7b79782b282e2829292a2a2a4147417777747777747477767476767476767774747878787d7d7d60636063636162636062626260606061616067676073717509333afee1ee15070b7f7d7f363737646a697875634d76752a525bcdf5e4090d37525455797f7f757a757475747475742828284343437777777777777676767676767b7b7b7f7f7f63636363636363636062626262626262626263626260626367646770717433343cf6fbfd0004097f7d7d0c0c0c64606a7a76795d454c285254cecde20c303b56575b797e797a7b7a74757477777728282843434377777776767674747479797962626363636363636362626262626262626262636263626363626261606166666770707a373823c9ccf5180005787e7f4a4b4b7d7d6441454d5b4772252d5acff3fd363b3c4a48497879787475747474747777772b28285d5d437676767474747d7d7d63636363636362626262626262626262626262626263626262626260626260606064676670747a0f3639dec2c80102017e7f7f7878755d5d452a2b552c5542272d51c5cffa383c26757478797b7b747474777777777777282a2a4242427878786262626363636363636262626262626262626262626262626262626362626262626060626060636666674c7074093339d1dbc61c1c01787e7d78787449447651575f515541262c5bcacefb3c202b787d7e7a7a747474747777777477772b2a2b474747636363636363626262626262626262626262626262626262626262626262626262626062636362636063676b65737075090f3ed2d7c01a1a03787e7e7b7a7a774c77425d485c434b252d58c7cbf13c232a77767e7677747474747777777676764040407474746363636262626262626262626262626262626262626262626262626262626262626262626263606363606b6b6770717a08303bd2d7c1121a1f797e7d7a757a4d73765f5c4a425f4b252d55c0c4f03d202b7a757b7174717474747777777a7b7a636362626362626262626262626262626262626262626262626262626262626262626262626262626260636363636061656b6470777a090d3bd3dac610151e7f7c7f7a7b7a7b747f444a4d424648282956c8cdf93d202b74777e7376767474747575756262626263626262626262626262626262626262626262626262626262626262626262626262626262626263626262636366606a656b707175040830dac2c912101e797f7e1919197f747f484a7245464f282b55cef3f93d232a76767a7077777474757c7c7c6263636263626262626262626262626262626262626262626262626262626262626262626262626262626263636163606060636a656b7071751d0f33d8c0cce817197d7f7f7b757a797b784e4e73465c4f2e5359cecdf82023297675747b7a757f7f796362636262636262626262626263626262626262626262626262626262626262626262626262626261626362626260636262626063606b65657370751f040ddec7f0e810147d7f7d7b7a747649754c44725c5a4f295258f0f1fd23272b7674747c7e7d636660626363626262626262626262636262626262626262626262626262626262626262626262626262626262626262636366636261606760686a6a70717a1f0609dcc7cd1a18067d627d7f797872747b48444f555e40262e51f5fce12025297b7b7b626360616060636363626262626262626262626263626262626262626262636262636262626262626362626262626263626262606260626262616666646a6470777a00000cc3c5f1060b327d7d7d6262635542467348715b594a3e2153f2e3e63921217e797967606661606063616362626262626262636262636263626262626262626262626262636362626262626262626262626262626363636263616260666068686a71777a1f0105c6cbf61e05327f7e7d6664672a594276767b5e4b4e3e3f2bf3e2e43d272460616364616460636060626162636262626263636062626262626262626262636360626262626362636262626262626262626262626262626261636360616664646b71777a171b04c6caf10609317f627d646467787878777779435b5e323f24c6f8e13e21276764646166606061636262626262627c606367626062636267636060626062626262606262666362626062626361636362626262626262626260636666636665656471777a181806c5cff81c1e0863666061646a757b7874757838242f070c3bc4f1ff353d3d6a686b626461606363676763616664656b6664606667646067606561666767656b6b666b646665616761616b6462636167636360646660606160666564686a656b68494f73ebec10c7caf202040967676768686a76747976767533363f030936dac9cf30393c72737a6f6c6c64676868686868686868686868686868686468686868686868686868686868686868686868686868686868686861686861606662626564676a696969686b6beeec19cacef607083672737a6c6c6c74777c5f43470a3639101d0cc7f2ff060a0f79797d656465686b686b6b6b6b6b6b6b656b6564656564656564656564656564656564656564656564656564656564656564656564656b64656b64656b656b6b656b68656b03050ecbccf736353b79797d6564657a757e252a5a063221171b33ebec00101033eeea171bec0315070507e90817020fe4100d031a0b031a0b140a3205000a041b050a010d1b080e330e3a373c360e0a0c0e3434373a223d20272724292d2d5555515821252d00060ce9101c0b0a333009220b0f3a4f4d7b3a3a501f0438e3e413013322232b5f3d3a29000808ebe506e9e715e5e712e3e2eafffae5e0f9ece71215e4ec07eaebebe3eb10ed010603080e04313c0831250d3e22373e23373f2b35372a382325392025363a24060f35180a3611180e161e361800315c5c4a30232ce4ed01e4100b25565b2b2e5a2452465a424456575c51554052434a2b2c57532f51562d5c252c5d262d5e35352f39232c252c5a212b2d24295750515e52575f56555c51515e57555856515e515a5c5a5e4057555c50505840434a4a454c4b49735c5c4532382e1216090d35243639292b2c5b554045575a454d4e7b75717a5e5b4459454f474749464749594241575e4329515e2e52572e2d542d5b5c5859435c594042464b474a4e4b49724f4f7048484d49494c494972494e734f4f70707074717174737376'
_TMPL_S2_W = 28; _TMPL_S2_H = 28; _TMPL_S2_C = 3
_TMPL_S2_D = '444a4e4c72774f704d704f4f4a444f4e4e7378747c767a7c76777e49717a444f71575f46e9190ac8f1e2e8131d2828575a545d5c5e4447477271737577777875787e4f777b5d484814143a0f083977777f7b7a7942414e46444a4a464e393922f0cfe1e3e6171014051d063a131d09eb1101fbe71bcbcffedad8caf0fae32551284b49730d3323ccf1e5f0f9e833392f37373033003a2a2d2d2231364f5b407a764d7f636149445d5f4540444a4a46464b262852e7e817ebea13e3fdecf5f5e0c2dcc7c3c3cbcfccf9ee111a383539435854525a20e2e7c01818ef0908030938073a011e2a3e354c4c417971734b484077487362707f12090ffdfde22a53512121276767677b797e4c727047404b5e5840532d5751535f4042454f497377717b7a7a7e6762646a6a6b6e6a6a68696a64696868696969686e6a656768676564656b68696868686bf8faf9f5fee21f1e05ea1519013305606467636060646162666667676b676a6a6a6a6a6a6b6b656b6b6b616563627c7d7c7e637e7f7f797e7b797f7f7f7e7c7b7b7e7979787e6279787a7c7e627f616362797e7febe611f4fce0eeed17e112171e05057c627c7c627f6263627f7e78505550292f292e28285c5c5c7f7c7f7e797e74787974747b7b75747579757574777774757477757b7b797c7e7e627f626161676b6065454b72150301ebec17111a00e6efed0005087e7d7d7f7e7f7b78785a565a2725275b54542d2c2f21252746474474747476747a7677777077777676767077767878787e7c7f62626265606361606164666767676740444e050830e6ec16161c06fee1ee15070b7f7d7f7e7f7d787e752627255d42427474747171712120215d4240747474747477767176747476747b787f62626663626060636063616263626361626163666564665c414b191c0af1f5fc161e07f6fbfd0004097f7d7d7f79797b7a78595959724d4d7777774949492121214a4a4a767676767676787878627d7f6363636363636363626260626162626263626262616160606b64675e5d45161f04cecdf5141e06c9ccf5180005787e7f79797975747b7474747774775c5c5f2121215f5f5f7676767474747c7e7c62626363636362626362626260626262626262626263636363636161606067646b555e41121806cef2fa151c07dec2c80102017e7f7f7878757774744c4c4c2f2f2f282828434343767676757474627d7d636063626263626262626262626262626262626262626262626062626262606163656b6b50575c121503dcc7cd171c0ad1dbc61c1c01787e7d78787474747a2a2a2a5252527171717171767878786262626363636363626262606262626262626262626262626262626262626262626662626063636b6a6551545decec1edcc0cd141c0ad2d7c01a1a03787e7e7b7a7a4e4e4e2121212323232322232525252e2e2e4e4e4e6362626262626262626262626262626262626262626262626262626262626062626161606a656b50575ce9121cdec2cf1a1e0bd2d7c1121a1f797e7d7a757a4d4d4d5557575457575e59594343404343437777776262626262626262626262626262626262626262626362626362626362626362616061636b6b6b52575fe5ef1bd8ddce15020bd3dac610151e7f7c7f7a7b7a7474747171717a7a786363666363636262626262626262626262626262626262626262626262626262626362626362626262636763636160606b6a6550575ce4e91ec3c4f5141f05dac2c912101e797f7e757a7a7676777575756262626363636262626262626262626262626262626262626262626262626262626262626262626262626363626362626767606a6a6752575ce4ec1cdcc5f7101a06d8c0cce817197d7f7f7b757a7774777c7c7c6363636262626162626262626262626262626262626262626262626262626262626262626262626262626362626360626167636a646a50545de7ee1edcc7fa151e05dec7f0e810147d7f7d7b7a7479797e6362606363636262626262626262626262626262626262626262626262626262626262626262626262626362626262626360626060636b656450575ce4ec1cc2c6fb161e07dcc7cd1a18067d627d7f79786060636063636260626262626262636262626262626262626262626262626262626262626262626262626262626262626262626262636166666a6a6a565b43e6ec19c1c8f91a1d0ec3c5f1060b327d7d7d6262636661676361626262636262626262626262616262636262626262626261626262626262626262626262626262626262626260626360606060676a6568575b43e5ec1ec0c5f9111907c6cbf61e05327f7e7d6664676066636062606262636362626262626262626362636262626262626262636262626262626262626262636261606262626262626363626466666a6a6a545840ee1319cbccfe17000bc6caf10609317f627d6464676060616362616363626263636263606262626262606263626262666362626262626362626262606262636262626263606262636060636666676b686b585c44ef1319f4f8ee1e0008c5cff81c1e0863666061646a6664667d6260606062636060606362626260666262626262626060616062626360627d6262626263666062637d6263606060636263636666676b68654041491d040c111503040b33c7caf202040967676768686a6564676365676662656b66666a60646b6a61646b6b666760656765676664606566676b60676b6060676b65676a66666b66636561646768686768686a4b49730a09361e1c0a0d0e34cacef607083672737a6c6c6c686868686868686b68686868686868686868686868686868686868686868686868686868686868686868686868686868686468686868686868696969686b6b0d0d3b07040d30313dcbccf736353b79797d656465686b686b6b6b6b6b6b6b656b6564656564656564656564656564656564656564656564656564656564656564656564656b64656b64656b656b6b656b68656b350d34050b08323639e9101c0b0a333009220b0f3a300d330b0404ece9eee1e4e0f4e0ffe7f9fefbf0ccc9cac4cecac5c6f2c4ffc8e2e7f5ebf4fffefde0e7fcfefde0e0e1f6fee3e6e6f8e8e6eb16161b070004320e3b23232a223c25180a3611180e161e3618003118073210040ee50a04e40707e01b19faef14f7e6e5f4fee6fafee7f6f4f8fde1eefeea111b15090a3622222b2e20252a39212525222b2628552b28552f2a57575840585846515a5d'
_TMPL_S3_W = 29; _TMPL_S3_H = 32; _TMPL_S3_C = 3
_TMPL_S3_D = '88b5afdac6f9030f3f595c444145484d7177747a7c4d7078494d7a484c7a4b4c754a4f774a4e744a4e77444871474871484c75787e6076747b2b2c5a494d7a797f61444872767a7c70777e484d75414a715f414d073328b7beacc7c5feee140a343d2c50545d75717b7f7e7f5b585d5b585d5f5e404740484848704f4c714f4e7046454f43434f40434f4147704244734044702556452a574658417256584a255141584672454970777b7c04322a17160e1e1b330b3022292f5451545d2a575b242b2c38252538212d2e28555a555d5d434b5d5c4b565b442e525f3e23530e302319053e171c32e0e214c6cef1d3d5c0d8caf1f1fe17e8130c140f203e2e5e4e4d7759434f77777f7b7a797a75797b707e4e49715f5c46223e2f0e373d050835010530efec1efde1efffe2eee3e1ede0e1edfbf8e7f7f5fdf3f1fecdf3fbcff3f5f4fae0ffe1ebfefde7fde0e8f5e3ece0160ce41e3a34255a4b4e717f636149445d7d797c7b7a7d75707440464455575d5f5c415d5d4457555f2c2c57202751393f2e3b3e2b383e2b212451272b57212b512628512c545f5156422b2d573d212e36392202060be1eb16e2ea1dec013927504212090ffdfde225252b2c202b3b353b0c33360934332e50265d5f414e734c7574787171754e4f70444b4d474972444972464b4c4241485c404445484e7076744f737141454e585d442c5558010533ef161fe112003c2e5ef5fee21f1e056767677b797e4c727047404b5e5840532d5751535f4042454f497377717b7a7a7e6762646a6a6b6e6a6a68696a64696868696969686e6a656768676564656b68696868686b1d0b37121a07150637382b59f4fce0eeed17606467696969627c607d7c627c7c607e7c7e7f7c7e7c7e7e797e7e7c7f7c7e7f7f7e7f7f7d7e78627c78627f797d627c676760626262626060606260666161696969797e7fea120313150a36392b312056ebec17111a004a4972696b687f7f797575785051512525252727254040407b757b7b74757575747a7574797575787975787b757b7b757b7978757b7a787c786361636a67676b686825505ee0ef1a11190b2f535f13073ce6ec16161c064a4b4f6a68687e79795e5c5b2725255b585b2c2d2c262120717176777474777477747477757776747477747477787a757f7f7c7c7c7c676162666162646564686868535841ebed18161b0545454fe71533f1f5fc161e074b4b4f6b6a6a7e7c7f292f2e42415d7575745d5d5d2121214c4c4c747777777777767676767677747a747e7e786262626263636060616161626063636567606b686b5e404beeec1c1b020c44454fffee05cecdf5141e064a4e4f6a686a7a797875757b4b4b4b2121212121212828287677777777777676767477747878787d62626363636361626062606262626263626362636167606565654a4c7710101d1f030840414902063bcef2fa151c074b4f726b686b7b797b7a757a4d4c4c5555552f2f2f2424244c4c4c7676767575747c7c7c63626363626362626362626262626262626363626263636266676665676471757e1b15021e073344464e5e5c46dcc7cd171c0a4b72706b6b6a4849492121214c4c4c777777707070212121424242787878626262636363636363626262626262626262626262626262626263606262616165646665787f621f03041b1c044a454c76757adcc0cd141c0a4f70776a6a6a7677712121215555557777775d5d5d202020484848626262636363626362626262626262626263626262626262626262626262636262606666656464626067060b091e0630454b724b484cdec2cf1a1e0b497371656565747a755859582121212120202020202d2d2d7f7f7f63636362626262626262626262626262626262626262626262626262626262616260666064666463666432313b08303e4b4a73734d76d8ddce15020b4e4f706565657a7a757777775c5c5c5454545f5f5f7f7f7f63636362626262626262626262626262626262626262626262626262626262626362626266666665646466676535343d0c323d4b4a72494c71c3c4f5141f054f4f73656a6575747577777776767679797963636363636362626262626262626262626262626262626262626262626262626262636362626262626261666364646b6465653c3a200d323e4b4a73747b78dcc5f7101a06494c706765657b7a75777477787878626262636363626262626262626262626262626262626262626262626262626262626262626262626262626362676661656465656b6b3b333b080822494a72717675dcc7fa151e054e4970656565747474757a757d627d6363626262626262626262626262626262626262626262626262626262626262626262626262626362636262636366666564656b68683132390a053a49497070777bc2c6fb161e074b4b4c6465647474747c7c7c60636362636362626262626262626262626262626262626262626262626162626262626262626262626262626262616066616664666a6b6b680d3a391c06344e4b704d7376c1c8f91a1d0e494f736a6b6a7c7c79626263636363616262626262636362626262626262626162626262626262626262626261626262626262626262626262616260666066646465686b68300d341a180d494b73737374c0c5f91119074e49706b6b6a7c636363636062606262626260636263636262626262636262626262626262626262636262626362626262626262626262626362626261606667646468696930340cee12194b4a72727375cbccfe17000b4f727068686b61606160636363636363606060636263636062636362606360626062626362636262636262626262636263626363636262626262636066606765646a696969363332fbfd124e4973727376f4f8ee1e00084f72736e6e6867666463616360626360636262636061636061626063626360616366606362626262626262636262627d6262636262626063636062626766666564646969690b0a0affe3124c4f724c4c76111503040b334e4f4c6e6e69676b67676063666a606461616166606162636065656061616060627d646363676662636362636260626263636360606360636060636063616767676a6969690e0709e5ef06724c7372737a1e1c0a0d0e34494f746c6c6c6b68686b6a6b6465616464676b6465676b646065646a64676764606766636766666663666766676167616766666166616161636166666167646b68656969692222220408367470754f4d7707040d30313d72737a6c6c6c6868686868686868686868686868686868686a6868686868686a68686a686868656a6b6a686868686868686b6465646868656a686b686a64656b696b686b6b51515a323a3c7471754d7277050b0832363979797d656465686b686b6b6b6b6b6b6b656b6564656564656564656564656564656564656564656564656564656564656564656564656b64656b64656b656b6b656b68656b5f58582020297a747872737623232a223c25232b2934353805090e040c0e340d0b303b343c0e393e0d3636323e3b0c34310c310905090b050b32010809083a0b09360832351b0306ef1319eaec1aec101813151c1c00052323205f5d407475794f4c70585846515a5d265057232b532b292e23282c282c5a4358405351582e505a252b513e252f3c2a2b3f252e2a2c5a292e5552575d2c545e44444b4643455a555c572d585b5b40435c4e4c4e71717174727377787a797072764e4f714b4972494e734c4f777272707070737273737374777771757574787a757975777a74747575747875747a75757875747875777875777874747a73747472737072707577707471717a777175757578757578737076'

# === baked Soul drop templates ===
_TMPL_SC_W = 30; _TMPL_SC_H = 19; _TMPL_SC_C = 3
_TMPL_SC_D = 'a37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acc73747b707a7f777e607a7d6479606b7f61687f61697f60697e636979636879636b79636b796265787d647b7d677b7d677a7c61757f61757f61757f61747e61747e61747e61777e60777963767862707b7c73757e7274784d777b7a7d677b636a78636b7e61697f616e7f666f7c666e7f616e7e61697e606879636b7863657b62647a7c66757f61777963747e63747e60747e61777960777963767963767863717862717b7d707b7c737a7f7275794d777b4c76757f666e7c676f7c676f7f666f7c666f7c676f7f666e7e616878636a7b7d657a7d647a7c67747f61777e60777e60777e60747e60777e60777960767863717b7d707a7d737a7c73757f73757f72757e7275797274794d777b4c777b7f666f7e616e7e616e7f616e7f666e7f616979606b7b6265757c64757f67747f66757f66757f66757f66747f66747e61777e60777963717862707a7d73757f72747e7274794d77794d77784d77784d77784d77784d74784d777b7b7d697b62697963697f666e7f61682f545ccef2f7c9cdf6c9cdf6c9cdf65e414e7a7c677a7f66757f66757f61747e60777963717862707b7c73757f4d74794d77784d77784d777b4c767bc7cbce4c767b4c777b4c777b4c777b7b62697b7d697b62697863685c4472cef2f759404e757c647b7d657b6265786265787d657b7d647a7c67757f66747f61777963717b7d737a7f72747e4d74794d74794d74794d77784c777bc7cbce4c777b4c777b4c777b4c777b7863697b62697b63697863695c4473e9131a757c647a7c647b7d6578626a78626a78626a7b7d657b7c64757f67747e61767863707b7c72757f4d747e4d74794d77784c77784c777b4c777bc7cbce4c777b4c777b4c777b4d747805323b78636e78636e796369796369cff3f4060e377a7d657b626a79636b79636b2f575dcff3f4cef2f6c9cdf62a525a717863515941c4c8cc4c77784c767b4c717bc7cace2d555e4f717ac7cbce4f767b4c777b4c777b4c777b7863697a62697b626978626e7862697b7d6b060937c9cdf7cef2f778636b796068cff0f55d45727b62655e464fc8cdf1545d45515e41c7c8cc4c76784f717b4f717ac6cac92d545e4f717ac6cac94f717a4f717a4f717a4c767a7963697a7d69757c697a7d697b7d697b7d68757d6a757d6528515fcef3f4232857ec161979606b79606b7b626a010931272d55515f46c7c9cc4f77794f767b4f717bc6cace2d545f4f717bc7cace4f767b4f717b4c717a4c767b7b626b7b63697b7d697b7c69787d697963697863687a7d6a7a7d65070e37373c2bec16187e616879606879606b060e3627525a565c44c4c9cd4c747e4f77784f767bc6cace2d545f4f717bc6cace4f717b4f717b4f717b4f717b7963687862697a7c68787d697e63697f60697f61697e606878636acef2f75c474ccff3f44245737e61685d4a73cef3f45b404e717960c5cef25058404c77793c272ec6cace2d545f4f717bc7cace4f717b4f717b4f707a4f717aec111f79636e78626e79636e2d5441f2f1fbf2f6fbf2f6facdf1fa424a727b62655f474ccef2f4cff3f5ccf0f52e575c757c64767961303820c5cef2c4c9cc190005e0eaef2d545f4f717bc7cace4f717b4f717b4f717a4f717a79636d79636c7b7d6f78626f78636f7e606f7c666f7d676f7d646f7c676979636b7a7d657b7d6a7b7d6b78636b79636b7a7d65747f67777961717863707b7d73757c72747e4d77794c717b4f717b4f717b4f717b4f717a4c717b62646d7d676d7e616c78626f7b626f7a7d6978626e7f616f7d666f7c666e7e61697863687b626b7b62687b7d6b7b7d6b7b7d6b7b7d657a7c64757f67777961717b63707a7d72747f4d777e4c76794c76784c717b4d767b4d777967696d606b6d7f666d7e616c79636f78626e7862697e606e7f616e7e606979636978626978626978626978636979636979606879606b78626b7b7d6a757f65747e67767861707a6373757d73747c4d777e4d777972747e73757f606a6d616b6d7d676d7c676c7f666f7f61697c66697d67697c61697962697b7f68787d6e7f636f7f616f7c616e7c616e7d666e7d61697e60697963697862687b7d6b757f65777964767866777861767863767862767863717b60a37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acca37acc'
_TMPL_SR_W = 29; _TMPL_SR_H = 18; _TMPL_SR_C = 3
_TMPL_SR_D = 'd95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c59d95c5978626a74714e74714f75764f75764c75764c74714c77704e77734976724b71724b7a77727e78747f797b7c79787c79787d7e787d7e787c79787f787b7f787b7f79787d7e797d7f7e627f79627f79637f78637c7b637f7ad95c5975764f75764c75764c7a764d7a764d75714c74714f7770497673487a74737f79757d7e78637c7e627f7e627f7e627f7e7d7e797d7e797d7f797d7f797d7f797d7e7e7c797e7f787e607e7e617c7e617c79667c78d95c5974764f75764c7a774d7a774d7a774d7a764d7a764d75764d787a767c7e7b7d7f78627f797d79797f78787c79797c7e7e7d7e7e7d7e79627f79637c7e627c7e7d7f7e7d7e7e7d7e7e627e7e607f7e607c7e627e78d95c5974714e74764f75764c7a774d7b77727874707975767f787a627f7e637c7e637d79637f787d79787e7b787e7b797f7879797b797f78797d7979637e7e627f7e7d7c7e7f7f7e7f7f7e7c7e7e7c797962797960787ed95c5977704974714f75764c2c261a12f89712f89712f89712f8974a432566637f61627e61627e627f7e797b787a757b7b7a78787b7b79787a7e7e787e7f797c7c7e7f7f7e79797e12f897637d7e637c7e607d7e627e7ed95c5977704974714f425a3f12f897475f267d797b627f79637c7e617d7f617d7f617d7e607c7e627f797d7e7b7f7e757e7977797877797877787975787e7b797e7b7e7f787e7f7812f8977f7f797c7f797f79797e7878d95c5977704e75714d40592302eeb7627e78637c7e637f7f637f7f607c7f607d7e617d7e607c79637f7b7d79757f7877787a707875707b75707b7a70787a71787b76787b76787b7612f89778787779787479787a7f797bd95c5975714d7874707e7b7412f8973302d5607c7f637f7f627f7f627f7e562b0212f89712f89712f897532519797573435b3f12f8977b74727b74727b757212f89743583c7a774d12f8977a774d7a774c7a774d787572d95c597b74717e7a757d7978637f7e3302da12f89712f8977d7e7f7d797e12f897445c247d797a475f2112f89741592241592212f8977b74727a77727a774d12f897425a3e74714f12f8977770497770497471497a764fd95c597874777f787b627f7e607c7f617d7f607d7f562b0212f8972137fd02eeb77c787a7c78747f7b770d1cd7532519465e2012f8977b74727a774d75764c12f897425a3e74714e12f89777704974704974714e7a764fd95c59797a7a7d797e637f7e607c7f607d7f607c7f627f79321dd5350ac51deeb77f7b777f7b777f7b77321dd450251e465e2012f8977874727a714c75714f12f897425a3974714e12f89777704977704874704975714ed95c59797a787c787e637f7f607c7f617d7f637f797c787a12f89741592312f8974159237e7a76465e2012f897465e217f7b7712f897405b3d7a764d2c211512f897425a3e75714e12f897777049777048777048777049d95c597e7a787c787e562b0212f89712f89712f89712f89741592379757041592212f89712f89712f8975324197f7a777e7a713c32f712f89712f8970c1fd11de9b6425a3e74714e12f89777704876734b76734b76734bd95c597e7a797d797e607c7f607c79627e7a7c78747e7a76797570797570797570797571797a71797a76797a767875717874707a764d75714f74704e74704e74704e77734977734876734876734b76734b71734a76734bd95c59627f7e627e7e627e787d79757c78777e7a767975717875707874707874707874707874707874707874707b77737a714d74704e77734977724977734977734977734876724b71724a71724b71724b71724a71724ad95c5961627e627f787f78747e7a76797a717975717975717875717874707877707877737b77737b77707b77717a767274704c77734e77734977724877724877724876724b76724b76724b76734b71724a71724a767348d95c59607f7b7c78777e7a76797571797570797a71797a717975717875717875717875707874717b74777a767074714d77704f77734977734877734977734876734876734876734876734871724b71724a71724a76724bd95c59'


def _decode_tmpl(d_hex: str, w: int, h: int, ch: int):
    return bytes(b ^ _K for b in bytes.fromhex(d_hex)), w, h, ch

_g_tmpl_hp = _g_tmpl_sp = _g_tmpl_mp = None
_g_tmpl_s1 = _g_tmpl_s2 = _g_tmpl_s3 = None
_g_tmpl_sc = _g_tmpl_sr = None


def _init_templates() -> None:
    global _g_tmpl_hp, _g_tmpl_sp, _g_tmpl_mp
    global _g_tmpl_s1, _g_tmpl_s2, _g_tmpl_s3
    _g_tmpl_hp = _decode_tmpl(_TMPL_HP_D, _TMPL_HP_W, _TMPL_HP_H, _TMPL_HP_C)
    _g_tmpl_sp = _decode_tmpl(_TMPL_SP_D, _TMPL_SP_W, _TMPL_SP_H, _TMPL_SP_C)
    _g_tmpl_mp = _decode_tmpl(_TMPL_MP_D, _TMPL_MP_W, _TMPL_MP_H, _TMPL_MP_C)
    _g_tmpl_s1 = _decode_tmpl(_TMPL_S1_D, _TMPL_S1_W, _TMPL_S1_H, _TMPL_S1_C)
    _g_tmpl_s2 = _decode_tmpl(_TMPL_S2_D, _TMPL_S2_W, _TMPL_S2_H, _TMPL_S2_C)
    _g_tmpl_s3 = _decode_tmpl(_TMPL_S3_D, _TMPL_S3_W, _TMPL_S3_H, _TMPL_S3_C)
    global _g_tmpl_sc, _g_tmpl_sr
    _g_tmpl_sc = _decode_tmpl(_TMPL_SC_D, _TMPL_SC_W, _TMPL_SC_H, _TMPL_SC_C)
    _g_tmpl_sr = _decode_tmpl(_TMPL_SR_D, _TMPL_SR_W, _TMPL_SR_H, _TMPL_SR_C)
    _log('[SVC] templates ok')



_ic: ArduinoHID | None = None
_hud: HUD | None = None


def _idle_tick() -> None:
    RECLICK_LO = 8.0
    RECLICK_HI = 14.8

    last_fatigue_time = time.time()
    fatigue_interval  = random.uniform(600, 1800)

    while not state.stop:
        if not _can_tick():
            time.sleep(0.1)
            continue

        if not state.ready:
            time.sleep(0.1)
            continue

        # Cede pra pot enquanto HP critico
        if state.hp_critical:
            time.sleep(0.05)
            continue

        mid   = (RECLICK_LO + RECLICK_HI) / 2
        sigma = (RECLICK_HI - RECLICK_LO) / 4
        wait  = random.gauss(mid, sigma)
        wait  = max(RECLICK_LO, min(RECLICK_HI, wait))

        deadline = time.monotonic() + wait
        interrupted = False
        while time.monotonic() < deadline and not state.stop:
            if not state.active or state.syncing or state.hp_critical:
                interrupted = True
                break
            time.sleep(0.1)

        if state.stop:
            break

        if interrupted:
            continue

        now = time.time()
        if now - last_fatigue_time > fatigue_interval:
            fatigue_pause = random.uniform(5.0, 15.0)
            deadline_f = time.monotonic() + fatigue_pause
            while time.monotonic() < deadline_f and not state.stop:
                time.sleep(0.1)
            last_fatigue_time = time.time()
            fatigue_interval  = random.uniform(600, 1800)
            continue

        if _ic and _can_tick():
            _human_click(_ic, double=True, right=True)


def _run_sync() -> None:
    _log("[SYNC] called")
    if not _ic:
        _log("[SYNC] driver unavailable")
        return

    state.syncing = True
    _log("[SYNC] start")
    try:
        _ic.send_key('f5', hold_sec=random.uniform(0.08, 0.15))
        time.sleep(random.uniform(0.08, 0.15))
        _human_click(_ic, double=True, right=True)

        time.sleep(random.gauss(_SYNC_PAUSE, 0.15))

        for key in ('f6', 'f7', 'f8'):
            if state.stop:
                break
            _ic.send_key(key, hold_sec=random.uniform(0.08, 0.15))
            time.sleep(random.uniform(0.08, 0.15))
            _human_click(_ic, double=True, right=True)
            time.sleep(random.uniform(0.3, 0.6))

        if not state.stop:
            time.sleep(random.uniform(0.2, 0.4))
            _ic.send_key('f1', hold_sec=random.uniform(0.08, 0.12))
            time.sleep(random.uniform(0.15, 0.3))
            _human_click(_ic, double=True, right=True)

        # Post-sync verification: confirm buffs landed. Logs status only;
        # no auto-recast here (the dedicated monitor handles drift).
        if not state.stop and _BUFF_PROFILES:
            time.sleep(random.uniform(0.4, 0.8))
            _post_sync_verify()

    finally:
        state.syncing = False
        _log("[SYNC] done")


def _post_sync_verify() -> None:
    # Snapshot of buff status right after _run_sync.
    try:
        hwnd = _locate_window()
        dims = _query_viewport(hwnd) if hwnd else None
        if dims is None:
            return
        w, h, ox, oy = dims
        hdc = user32.GetDC(None)
        try:
            res = _verify_buffs(hdc, w, h, ox, oy)
        finally:
            user32.ReleaseDC(None, hdc)
        if res:
            parts = [f"{n}={'Y' if a else 'N'}({s:.0f})" for n, (a, s) in res.items()]
            _log(f"[SYNC] verify: {' '.join(parts)}")
    except Exception:
        pass


def _buff_monitor() -> None:
    # Periodic background check. If any configured buff is missing AND the
    # macro is in active/ready state, send the recast key for that single
    # buff (vs full sync). Skips during state.syncing to avoid stomping.
    if not _BUFF_PROFILES:
        # Framework only — exit if no profiles configured.
        _log("[BUF] monitor idle (no profiles)")
        return
    last_recast = {entry[0]: 0.0 for entry in _BUFF_PROFILES}
    while not state.stop:
        if state.syncing or not state.ready or not state.active:
            time.sleep(1.0)
            continue
        # Cycle through verify period
        deadline = time.monotonic() + _BUFF_VERIFY_PERIOD
        while time.monotonic() < deadline and not state.stop:
            time.sleep(0.5)
        if state.stop:
            break
        if state.syncing or not state.ready or not state.active:
            continue
        try:
            hwnd = _locate_window()
            dims = _query_viewport(hwnd) if hwnd else None
            if dims is None:
                continue
            w, h, ox, oy = dims
            hdc = user32.GetDC(None)
            try:
                res = _verify_buffs(hdc, w, h, ox, oy)
            finally:
                user32.ReleaseDC(None, hdc)
            now = time.monotonic()
            for entry in _BUFF_PROFILES:
                name, key, _tmpl_var, _rx, _ry = entry
                active, sad = res.get(name, (False, 999.0))
                if not active and (now - last_recast.get(name, 0.0)) > _BUFF_RECAST_CD:
                    if _ic and _can_tick():
                        _log(f"[BUF] {name} missing (sad={sad:.0f}) — recast {key}")
                        _ic.send_key(key, hold_sec=random.uniform(0.08, 0.15))
                        time.sleep(random.uniform(0.12, 0.22))
                        _human_click(_ic, double=False, right=True)
                        last_recast[name] = time.monotonic()
                        time.sleep(random.uniform(0.4, 0.8))
        except Exception:
            pass


def _read_px(hdc, x, y) -> tuple[int, int, int]:
    color = gdi32.GetPixel(hdc, x, y)
    if color == 0xFFFFFFFF:
        return -1, -1, -1
    return color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF

def _sig_a(c) -> bool:
    r, g, b = c
    # PT EU bar tem gradient + glow nas bordas. Pixels de transicao/sheen tem
    # r/g/b mais proximos, e o teste antigo (r > g*2.5) cortava ate ~10% da
    # barra. Versao relaxada: r dominante por >=30 ja conta como "fill".
    return r > 70 and r >= g + 30 and r >= b + 30

def _sig_b(c) -> bool:
    r, g, b = c
    # bright green; multiplier 2.0 to handle near-white bar glow
    return g > 100 and g > r * 2.0 and g > b * 2.0

def _sig_c(c) -> bool:
    r, g, b = c
    # catches pure blue (0,85,226) and cyan (0,252,252) — mana bar varies
    # b >= 90 to handle edge reads where b lands exactly at 100
    return r < 50 and b >= 90

def _no_signal(c) -> bool:
    r, g, b = c
    # empty slot center = pure black per image analysis
    return max(r, g, b) < 30

user32.GetCursorPos.restype  = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]


def _probe_loop() -> None:
    try:
        _hwnd             = None
        _dims             = None
        _bar_xs           = None
        _slot_positions   = None
        _slot_empty_tmpl  = [None, None, None]
        _next_refresh     = 0.0
        _dbg_tick         = 0

        while not state.stop:
            if not _can_probe():
                time.sleep(0.1)
                continue

            now_m = time.monotonic()
            if now_m >= _next_refresh or _dims is None:
                _hwnd         = _locate_window()
                _dims         = _query_viewport(_hwnd) if _hwnd else None
                _next_refresh = now_m + 5.0
                if _dims is None:
                    _log("[MON] window not found — waiting")
                    time.sleep(0.5)
                    continue
                w, h, ox, oy = _dims
                applied = _apply_resolution_profile(w, h)
                if applied is not None:
                    _log(f"[CFG] resolution {w}x{h} -> profile {applied[0]}x{applied[1]}")
                hdc_s = user32.GetDC(None)
                try:
                    hp_x, sp_x, mp_x = _scan_hud(hdc_s, w, h, ox, oy)
                    _bar_xs = (hp_x, sp_x, mp_x)
                    s1_pos = _to_screen(*_PA_R, w, h, ox, oy)
                    s2_pos = _to_screen(*_PB_R, w, h, ox, oy)
                    s3_pos = _to_screen(*_PC_R, w, h, ox, oy)
                    _slot_positions = (s1_pos, s2_pos, s3_pos)
                    # Slot empty via template match (5s cache)
                    sx_sc = w / _REF_W; sy_sc = h / _REF_H
                    for idx, (spos, tmpl) in enumerate([
                        (s1_pos, _g_tmpl_s1), (s2_pos, _g_tmpl_s2), (s3_pos, _g_tmpl_s3)
                    ]):
                        if tmpl is None:
                            _slot_empty_tmpl[idx] = None
                            continue
                        pix, tw, th, tc = tmpl
                        cw_ = max(4, int(tw * sx_sc))
                        ch_ = max(4, int(th * sy_sc))
                        slot_cap = _capture_region(
                            hdc_s, spos[0] - cw_//2, spos[1] - ch_//2, cw_, ch_
                        )
                        if slot_cap is not None:
                            pix_s = _nn_scale(pix, tw, th, tc, cw_, ch_)
                            avg   = _sad_center(slot_cap, cw_, ch_, pix_s, tc)
                            _slot_empty_tmpl[idx] = avg < _SLOT_EMPTY_THR
                        else:
                            _slot_empty_tmpl[idx] = None
                finally:
                    user32.ReleaseDC(None, hdc_s)
                _log(f"[MON] dims=({w}x{h}) origin=({ox},{oy}) bars: hp={hp_x} sp={sp_x} mp={mp_x}")
                _log(f"[MON] slots: s1={_slot_empty_tmpl[0]} s2={_slot_empty_tmpl[1]} s3={_slot_empty_tmpl[2]}")

            if _bar_xs is None or _dims is None or _slot_positions is None:
                time.sleep(0.1)
                continue

            w, h, ox, oy = _dims
            hp_x, sp_x, mp_x = _bar_xs
            s1_pos, s2_pos, s3_pos = _slot_positions

            # Per-tick: pixel-counting bar percentages + slot pixel reads
            hdc = user32.GetDC(None)
            try:
                hp_pct = _bar_pct(hdc, hp_x, _ZA_R, h, oy, _sig_a)
                sp_pct = _bar_pct(hdc, sp_x, _ZB_R, h, oy, _sig_b)
                mp_pct = _bar_pct(hdc, mp_x, _ZC_R, h, oy, _sig_c)
                s1_c = _read_px(hdc, *s1_pos)
                s2_c = _read_px(hdc, *s2_pos)
                s3_c = _read_px(hdc, *s3_pos)
            finally:
                user32.ReleaseDC(None, hdc)

            _dbg_tick += 1

            def _empty(tmpl_r, px_c) -> bool:
                if tmpl_r is not None:
                    return tmpl_r or _no_signal(px_c)
                return _no_signal(px_c)

            if _dbg_tick % 10 == 0:
                _log(
                    f"[BAR] t={_dbg_tick} hp={hp_pct}% sp={sp_pct}% mp={mp_pct}% "
                    f"hpx={hp_x} spx={sp_x} mpx={mp_x} "
                    f"s1e={_empty(_slot_empty_tmpl[0], s1_c)} "
                    f"s2e={_empty(_slot_empty_tmpl[1], s2_c)} "
                    f"s3e={_empty(_slot_empty_tmpl[2], s3_c)}"
                )

            def _try_pot(key: str, pct: int, thr: int, label: str):
                if not (_ic and _can_probe()):
                    return
                try:
                    # micro-reacao humana gaussiana antes de apertar — quebra o
                    # padrao de reacao instantanea/identica; tambem espaca disparos.
                    react = max(_POT_REACT_LO,
                                min(_POT_REACT_HI,
                                    random.gauss(_POT_REACT_MEAN, _POT_REACT_STD)))
                    time.sleep(react)
                    _ic.send_key(key, hold_sec=random.uniform(0.02, 0.04))
                    critical = pct <= max(1, thr // 2)
                    tag = "CRIT" if critical else "FIRED"
                    _log(f"[POT] {label} {tag} pct={pct}% thr={thr}% react={react*1000:.0f}ms")
                except Exception as e:
                    _log(f"[ERR] {label} send_key EXC: {type(e).__name__}: {e}")

            # Cada barra que cruza o threshold dispara, todas no mesmo tick. HP
            # vai primeiro (prioridade); SP/MP nao esperam — se varias precisam,
            # todas sao usadas. Cada uma tem sua micro-reacao gaussiana.
            hp_low = hp_pct < _settings.pot_hp_pct
            state.hp_critical = hp_low and hp_pct <= max(1, _settings.pot_hp_pct // 2)

            if hp_low:
                _try_pot('1', hp_pct, _settings.pot_hp_pct, 'hp')
            if sp_pct < _settings.pot_sp_pct:
                _try_pot('2', sp_pct, _settings.pot_sp_pct, 'sp')
            if mp_pct < _settings.pot_mp_pct:
                _try_pot('3', mp_pct, _settings.pot_mp_pct, 'mp')

            # (scan de Soul movido pra _soul_loop, thread separada — antes ele
            #  bloqueava o pot por segundos a cada poll de 1s)

            # Tick rate adaptativo: quase 0 (5ms) enquanto algum pct esta baixo —
            # mata o delay entre uma pot e a proxima; 50ms ocioso (detecta queda
            # rapido) quando tudo OK, ainda economico de CPU.
            any_low = (hp_pct < _settings.pot_hp_pct or
                       sp_pct < _settings.pot_sp_pct or
                       mp_pct < _settings.pot_mp_pct)
            time.sleep(0.005 if any_low else 0.05)

    except Exception:
        import traceback
        _log(f"[ERR] probe_loop: {traceback.format_exc()}")


def _soul_loop() -> None:
    """Scan de Soul/badge em thread SEPARADA. O scan e pesado (HSV + flood-fill
    em Python sobre a regiao central da tela), entao roda isolado pra NAO
    bloquear o loop de pot — antes travava o pot por segundos a cada poll."""
    last_ping = 0.0
    try:
        while not state.stop:
            if not _can_probe():
                time.sleep(0.2)
                continue
            hwnd = _locate_window()
            dims = _query_viewport(hwnd) if hwnd else None
            if dims is None:
                time.sleep(0.5)
                continue
            w, h, ox, oy = dims
            hdc_q = user32.GetDC(None)
            try:
                kind = _check_presence(hdc_q, ox, oy, w, h)
            finally:
                user32.ReleaseDC(None, hdc_q)
            now = time.monotonic()
            if kind and (now - last_ping) > _BADGE_COOLDN:
                last_ping = now
                _log(f"[VC] mention ({kind}) beep={_settings.soul_beep}")
                if _settings.soul_beep:
                    _emit_ping(kind)
            time.sleep(_BADGE_POLL)
    except Exception:
        import traceback
        _log(f"[ERR] soul_loop: {traceback.format_exc()}")


def _aux_loop() -> None:
    """Skills com cooldown configuravel via HUD.

    Logica:
      - F1 e a skill principal/spam. _idle_tick ja faz o right-click de combate.
      - F2/F3/F4: cada uma com CD proprio (settings). Quando o CD expira,
        dispara em ordem de prioridade (F2 > F3 > F4) — apenas UMA por ciclo.
      - Apos disparar F2/F3/F4, pressiona F1 pra retornar ao stance principal.
    """
    next_ready = {'f2': 0.0, 'f3': 0.0, 'f4': 0.0}

    while not state.stop:
        if not _can_tick() or not state.ready:
            time.sleep(0.1)
            continue
        # Cede serial pro pot quando HP critico
        if state.hp_critical:
            time.sleep(0.05)
            continue

        now = time.monotonic()
        fired = None
        for key in ('f2', 'f3', 'f4'):
            if not getattr(_settings, f"skill_{key}"):
                continue
            if now < next_ready[key]:
                continue
            if not (_ic and _can_tick()):
                continue
            # Re-checa critical antes de cada press — pode ter mudado
            if state.hp_critical:
                break

            _ic.send_key(key, hold_sec=_human_hold())
            # Delay minimo 1.0s + variancia gauss (~1.0-1.6s tipicamente)
            time.sleep(max(1.0, random.gauss(1.2, 0.2)))
            if _settings.skill_f1:
                _ic.send_key('f1', hold_sec=_human_hold())

            cd = float(getattr(_settings, f"skill_{key}_cd"))
            # Jitter gaussiano proporcional ao CD: ~10% do CD (piso 100ms, teto 2s)
            jit_base = max(0.10, min(2.0, cd * 0.10))
            jit = max(0.05, random.gauss(jit_base, jit_base * 0.4))
            next_ready[key] = now + cd + jit
            _log(f"[AUX] fired {key.upper()} -> F1 | cd={cd:.1f}s next +{cd + jit:.2f}s")
            fired = key
            break

        time.sleep(0.15 if fired else 0.08)


def _sync_scheduler() -> None:
    _log("[SYNC] waiting for activation")
    while not state.active and not state.stop:
        time.sleep(0.1)

    if state.stop:
        return

    _log(f"[SYNC] activated (start_buff={_settings.start_with_buff} "
         f"rebuff_min={_settings.rebuff_minutes})")
    time.sleep(1.0)
    if _settings.start_with_buff:
        _run_sync()
    state.ready = True
    _log("[SYNC] ready")

    while not state.stop:
        # Base do settings (5-10 min) + jitter humano.
        base = _settings.rebuff_minutes * 60.0
        wait = base + random.uniform(_JITTER_LO, _JITTER_HI)
        deadline = time.monotonic() + wait

        while time.monotonic() < deadline and not state.stop:
            time.sleep(0.5)

        if state.stop:
            break

        while not state.active and not state.stop:
            time.sleep(0.5)

        if state.stop:
            break

        _run_sync()


WM_HOTKEY    = 0x0312
MOD_CONTROL  = 0x0002
HOTKEY_TOGGLE = 1
HOTKEY_CLOSE  = 2
HOTKEY_HUD    = 3

user32.RegisterHotKey.restype  = wt.BOOL
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]

user32.UnregisterHotKey.restype  = wt.BOOL
user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]

user32.GetMessageW.restype  = wt.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes  = [ctypes.POINTER(wt.MSG)]


def _force_exit() -> None:
    time.sleep(0.35)
    if _ic:
        try:
            _ic.close()
        except Exception:
            pass
    os._exit(0)


def _register_hotkeys() -> bool:
    ok_toggle = user32.RegisterHotKey(None, HOTKEY_TOGGLE, MOD_CONTROL, TOGGLE_VK)
    ok_close  = user32.RegisterHotKey(None, HOTKEY_CLOSE,  MOD_CONTROL, CLOSE_VK)
    ok_hud    = user32.RegisterHotKey(None, HOTKEY_HUD,    MOD_CONTROL, HUD_VK)
    if not ok_toggle:
        _log(f"[ERR] RegisterHotKey toggle FAILED — err={kernel32.GetLastError()}")
    if not ok_close:
        _log(f"[ERR] RegisterHotKey close FAILED — err={kernel32.GetLastError()}")
    if not ok_hud:
        _log(f"[ERR] RegisterHotKey HUD FAILED — err={kernel32.GetLastError()}")
    return bool(ok_toggle and ok_close)


def _message_loop() -> None:
    msg = wt.MSG()

    while True:
        ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
        if ret == 0 or state.stop:
            break
        elif ret == -1:
            time.sleep(0.05)
            continue

        if msg.message == WM_HOTKEY:
            if msg.wParam == HOTKEY_TOGGLE:
                with state.lock:
                    state.active = not state.active
                _log(f"[EVT] toggle → active={state.active}")
                freq = 1500 if state.active else 600
                threading.Thread(target=_beep, args=(freq, 150), daemon=True, name=_tname()).start()
            elif msg.wParam == HOTKEY_HUD:
                if _hud:
                    _hud.toggle()
                    _log("[EVT] HUD toggle")
            elif msg.wParam == HOTKEY_CLOSE:
                _log("[EVT] close requested")
                state.stop = True
                _remove_lock()
                _beep(400, 300)  # synchronous — blocks until beep finishes
                user32.PostQuitMessage(0)
                threading.Thread(target=_force_exit, daemon=True).start()
                break

        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


_ctrl_handler_ref = None

def main() -> None:
    global _ic, _hud, _ctrl_handler_ref

    _log("[SVC] init")
    _init_templates()
    _kill_existing_instances()
    _write_lock()

    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        # user32.ShowWindow(hwnd, 0) # Comentado para Debug
        pass

    _log("[SVC] hardware hid init")
    def _toggle_from_arduino():
        with state.lock:
            state.active = not state.active
        _log(f"[EVT] HW toggle -> active={state.active}")
        freq = 1500 if state.active else 600
        threading.Thread(target=_beep, args=(freq, 150), daemon=True, name=_tname()).start()

    def _kill_from_arduino():
        _log("[EVT] HW kill (long press)")
        state.stop = True
        _remove_lock()
        _beep(400, 300)  # synchronous final beep
        user32.PostQuitMessage(0)
        threading.Thread(target=_force_exit, daemon=True).start()

    try:
        _ic = ArduinoHID(toggle_callback=_toggle_from_arduino,
                         kill_callback=_kill_from_arduino)
    except Exception as e:
        _ic = None
        _log(f"[SVC] Arduino nao encontrado: {e} — rodando em modo HUD-only")

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.DWORD)
    def _console_ctrl_handler(ctrl_type):
        if ctrl_type in (0, 2, 5, 6):
            _remove_lock()
            if _ic:
                try:
                    _ic.close()
                except Exception:
                    pass
            os._exit(0)
        return False
    _ctrl_handler_ref = _console_ctrl_handler
    kernel32.SetConsoleCtrlHandler(_ctrl_handler_ref, True)

    _log("[SVC] HUD start")
    _hud = HUD(
        settings=_settings,
        hud_state=_hud_state,
        profiles=_PROFILES,
        load_profile=_load_profile,
        on_save=_apply_settings,
        on_use=_set_active_profile,
        on_state_change=_save_hud_state,
        get_active=_is_active,
        resolutions=resolution_keys(),
        get_resolution=_current_resolution,
        capture_ratio=_capture_ratio,
        save_mapping=_save_resolution_mapping,
    )
    threading.Thread(target=_hud.run, daemon=True, name=_tname()).start()
    _hud.wait_ready(timeout=3.0)

    _log("[SVC] threads start")
    threading.Thread(target=_idle_tick,       daemon=True, name=_tname()).start()
    threading.Thread(target=_sync_scheduler,  daemon=True, name=_tname()).start()
    threading.Thread(target=_probe_loop,      daemon=True, name=_tname()).start()
    # DESABILITADO p/ analise — scan de Soul off pra medir o pot isolado.
    # Reabilitar: descomentar a linha abaixo.
    # threading.Thread(target=_soul_loop,       daemon=True, name=_tname()).start()
    threading.Thread(target=_aux_loop,        daemon=True, name=_tname()).start()
    threading.Thread(target=_buff_monitor,    daemon=True, name=_tname()).start()

    _log("[SVC] hotkeys register (RegisterHotKey)")
    if not _register_hotkeys():
        _log("[ERR] RegisterHotKey falhou — hotkeys nao funcionarao")

    _log("[SVC] message loop running")
    try:
        _message_loop()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop = True
        _remove_lock()
        if _ic:
            try:
                _ic.close()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
        _log("exit")
    except Exception:
        import traceback
        _log(f"[ERR] {traceback.format_exc()}")
