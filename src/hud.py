"""
hud.py — Overlay tkinter com secoes COMBATE/POT/DROPS, 3 perfis, save explicito.

Layout:
  ┌─ header (drag) ──────────────────┐
  │ status: Executando / Desativado  │
  │ [COMBATE] [POT] [DROPS]          │  ← tabs
  │  ... conteudo da secao ...       │
  ├──────────────────────────────────┤
  │ Editando: X  |  Em uso: Y        │
  │ Renomear: [_______________]      │
  │ [Perfil 1] [Perfil 2] [Perfil 3] │
  │ [ SALVAR ] [ UTILIZAR ]          │
  └──────────────────────────────────┘

SALVAR    = persiste edits + ativa perfil pro runtime
UTILIZAR  = ativa perfil pro runtime SEM persistir edits (so se editing != ativo)
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

try:
    import keyboard          # captura SPACE global (independe de foco da janela)
except Exception:            # pragma: no cover
    keyboard = None


_BG       = "#1a1a1a"
_PANEL    = "#222"
_FG       = "#e0e0e0"
_MUTED    = "#888"
_ACCENT   = "#5865f2"
_ACTIVE   = "#3b3f7a"
_SUCCESS  = "#3ba55c"
_DANGER   = "#ed4245"
_DISABLED = "#3a3a3a"
_ALPHA    = 0.92
_W        = 340
_H        = 620

_TABS = ("COMBATE", "POT", "DROPS", "RES")


class HUD:
    def __init__(
        self,
        settings,
        hud_state,
        profiles: tuple,
        load_profile: Callable[[str], object],
        on_save: Callable[[str, object], None],
        on_use: Callable[[str], None],
        on_state_change: Callable[[object], None],
        get_active: Callable[[], bool],
        resolutions: list = None,
        get_resolution: Callable[[], tuple] = None,
        capture_ratio: Callable[[], tuple] = None,
        save_mapping: Callable[[int, int, dict], None] = None,
    ):
        self._runtime    = settings
        self._hud_state  = hud_state
        self._profiles   = profiles
        self._load_prof  = load_profile
        self._on_save    = on_save
        self._on_use     = on_use
        self._on_state   = on_state_change
        self._get_active = get_active
        self._resolutions = resolutions or []
        self._get_res     = get_resolution
        self._capture     = capture_ratio
        self._save_map    = save_mapping

        # working copy
        self._working = self._load_prof(self._hud_state.active_profile)
        self._active  = self._hud_state.active_profile

        # tk state
        self.root        = None   # driver invisivel (event loop)
        self.win         = None   # janela de config (Toplevel destruivel)
        self.visible     = True
        self._drag_x     = 0
        self._drag_y     = 0
        self._toggle_pending = False
        self._ready_evt  = threading.Event()
        self._tk_vars    = {}
        self._tab_btns   = {}
        self._tab_frames = {}
        self._prof_btns  = {}
        self._cur_tab    = "COMBATE"
        self._dirty      = False
        self._status_lbl = None
        self._editing_lbl = None
        self._dirty_lbl  = None
        self._save_btn   = None
        self._use_btn    = None
        self._rename_var = None
        # combate widgets
        self._cd_vars    = {}     # 'f1' -> StringVar
        self._last_active_state = None
        self._shutdown_pending = False
        self._destroyed = False
        # resolucao (RES tab + wizard)
        self._res_cur_lbl  = None   # "Sua resolucao atual: WxH"
        self._res_stat_lbl = None   # mapeada / nao-mapeada
        self._res_list_lbl = None   # lista de mapeadas
        self._res_combo    = None
        self._last_res     = None   # ultima (w,h) detectada (evita refresh redundante)
        self._res_poll_ctr = 0
        self._wizard       = None
        # mini-badge permanente (Executando/Parado) — assume apos a 1a ativacao
        self._mini        = None
        self._mini_lbl    = None
        self._badge_state = None

    # ── thread entrypoint ─────────────────────────────────────────────────
    def run(self):
        try:
            self._build()
            self._ready_evt.set()
            self._tick()
            self.root.mainloop()
        except Exception:
            self._ready_evt.set()

    def wait_ready(self, timeout: float = 5.0) -> bool:
        return self._ready_evt.wait(timeout)

    def toggle(self):
        self._toggle_pending = True

    def shutdown(self):
        """Destroi a janela Tk. Chamado quando o macro ativa, pra remover a HUD
        do process inteiramente — anti-cheat enumerando child windows do
        Discord.exe nao acha mais window class Tk."""
        self._shutdown_pending = True

    # ── build ─────────────────────────────────────────────────────────────
    def _build(self):
        # Root = driver invisivel. Nunca aparece — so mantem o event loop vivo.
        # A janela de config (self.win) e um Toplevel destruivel: quando o macro
        # liga, self.win e DESTRUIDO (HUD some de verdade) e so o badge sobra;
        # o root segue rodando o loop e o badge.
        self.root = tk.Tk()
        self.root.title("d")
        self.root.withdraw()

        # ttk theme tweaks (combobox dark) — global ao interpretador
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "TCombobox",
            fieldbackground=_PANEL, background=_PANEL,
            foreground=_FG, selectforeground=_FG, selectbackground=_PANEL,
            arrowcolor=_FG, borderwidth=0,
        )
        # Map override pra todos os estados (readonly, focus, active, etc.)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", _PANEL), ("disabled", _PANEL), ("!disabled", _PANEL)],
            foreground     =[("readonly", _FG),    ("disabled", _MUTED),  ("!disabled", _FG)],
            selectforeground=[("readonly", _FG), ("!disabled", _FG)],
            selectbackground=[("readonly", _PANEL), ("!disabled", _PANEL)],
        )
        self.root.option_add("*TCombobox*Listbox.background", _PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", _FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", _ACTIVE)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")

        # Se o macro ja estiver ativo na subida, nem cria a config — so o badge.
        if self._safe_get_active():
            self._show_mini()
            self._update_badge(True)
        else:
            self._build_config()

    def _build_config(self):
        """(Re)constroi a janela de config (self.win) do zero. Chamado no startup
        e ao desligar o macro (pra HUD voltar). Reseta todos os widget-dicts."""
        self._tk_vars   = {}
        self._tab_btns  = {}
        self._tab_frames = {}
        self._prof_btns = {}
        self._cd_vars   = {}
        self.visible    = True

        self.win = tk.Toplevel(self.root)
        self.win.title("d")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", _ALPHA)
        self.win.configure(bg=_BG)

        sw = self.win.winfo_screenwidth()
        x = self._hud_state.hud_x if self._hud_state.hud_x >= 0 else (sw - _W - 20)
        y = self._hud_state.hud_y if self._hud_state.hud_y >= 0 else 40
        self.win.geometry(f"{_W}x{_H}+{x}+{y}")

        # ── header (drag) ──
        hdr = tk.Frame(self.win, bg=_ACCENT, height=28)
        hdr.pack(fill="x")
        tk.Label(hdr, text="settings", bg=_ACCENT, fg="white",
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=10, pady=5)
        tk.Label(hdr, text="ctrl+j", bg=_ACCENT, fg="#dcdef0",
                 font=("Segoe UI", 8)).pack(side="right", padx=10)
        for w in (hdr,) + tuple(hdr.winfo_children()):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        # ── status ──
        st_frame = tk.Frame(self.win, bg=_BG)
        st_frame.pack(fill="x", pady=(4, 4))
        self._status_lbl = tk.Label(
            st_frame, text="—", bg=_BG, fg=_MUTED,
            font=("Segoe UI", 10, "bold"))
        self._status_lbl.pack()

        # ── tabs ──
        tabs_bar = tk.Frame(self.win, bg=_PANEL)
        tabs_bar.pack(fill="x")
        for tab in _TABS:
            b = tk.Button(
                tabs_bar, text=tab, bg=_PANEL, fg=_FG, bd=0, relief="flat",
                font=("Segoe UI", 9, "bold"),
                activebackground=_ACTIVE, activeforeground="white",
                command=lambda t=tab: self._switch_tab(t),
            )
            b.pack(side="left", expand=True, fill="x", padx=1, pady=2)
            self._tab_btns[tab] = b

        # ── content ──
        content = tk.Frame(self.win, bg=_BG)
        content.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        self._build_combate(self._make_tab(content, "COMBATE"))
        self._build_pot(self._make_tab(content, "POT"))
        self._build_drops(self._make_tab(content, "DROPS"))
        self._build_res(self._make_tab(content, "RES"))

        # ── footer ──
        tk.Frame(self.win, bg="#2a2a2a", height=1).pack(fill="x", pady=(8, 0))
        footer = tk.Frame(self.win, bg=_BG)
        footer.pack(fill="x", padx=10, pady=(6, 10))

        self._editing_lbl = tk.Label(footer, text="", bg=_BG, fg=_MUTED,
                                     font=("Segoe UI", 8))
        self._editing_lbl.pack(anchor="w")

        # Rename entry
        rn_row = tk.Frame(footer, bg=_BG)
        rn_row.pack(fill="x", pady=(4, 2))
        tk.Label(rn_row, text="Renomear:", bg=_BG, fg=_FG,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
        self._rename_var = tk.StringVar(value=self._display_name(self._active))
        ent = tk.Entry(rn_row, textvariable=self._rename_var, bg=_PANEL, fg=_FG,
                       insertbackground=_FG, relief="flat", font=("Segoe UI", 9))
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<Return>",  lambda e: self._do_rename())
        ent.bind("<FocusOut>", lambda e: self._do_rename())

        # Profile buttons
        prof_row = tk.Frame(footer, bg=_BG)
        prof_row.pack(fill="x", pady=(6, 6))
        for name in self._profiles:
            b = tk.Button(
                prof_row, text=self._display_name(name), bd=0, relief="flat",
                font=("Segoe UI", 9), bg=_PANEL, fg=_FG,
                activebackground=_ACTIVE, activeforeground="white",
                command=lambda n=name: self._switch_profile(n),
            )
            b.pack(side="left", expand=True, fill="x", padx=2)
            self._prof_btns[name] = b

        self._dirty_lbl = tk.Label(footer, text="", bg=_BG, fg="#f0b132",
                                   font=("Segoe UI", 8))
        self._dirty_lbl.pack(anchor="w")

        # Save + Utilizar row
        btn_row = tk.Frame(footer, bg=_BG)
        btn_row.pack(fill="x", pady=(4, 0))
        self._save_btn = tk.Button(
            btn_row, text="SALVAR", bg=_SUCCESS, fg="white", bd=0, relief="flat",
            font=("Segoe UI", 10, "bold"), activebackground="#2d8049",
            activeforeground="white", command=self._save,
        )
        self._save_btn.pack(side="left", expand=True, fill="x", ipady=6, padx=(0, 3))
        self._use_btn = tk.Button(
            btn_row, text="UTILIZAR", bg=_DISABLED, fg=_MUTED, bd=0, relief="flat",
            font=("Segoe UI", 10, "bold"),
            activebackground=_ACCENT, activeforeground="white",
            state="disabled", command=self._use,
        )
        self._use_btn.pack(side="left", expand=True, fill="x", ipady=6, padx=(3, 0))

        # init
        self._switch_tab("COMBATE")
        self._highlight_active_profile()
        self._update_editing_label()
        self._update_use_button()
        self._update_status(self._safe_get_active())

    def _make_tab(self, parent, name):
        f = tk.Frame(parent, bg=_BG)
        self._tab_frames[name] = f
        return f

    # ── COMBATE ───────────────────────────────────────────────────────────
    def _build_combate(self, frame):
        self._section_title(frame, "Combate")
        tk.Label(
            frame,
            text="F1 = main/spam. F2-F4 disparam quando CD expira, depois retornam a F1.",
            bg=_BG, fg=_MUTED, font=("Segoe UI", 8),
            wraplength=290, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        for fk in ("f1", "f2", "f3", "f4"):
            self._build_skill_row(frame, fk)

        # Rebuff + start with buff
        tk.Frame(frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(8, 6))
        tk.Label(frame, text="Rebuff (minutos):", bg=_BG, fg=_FG,
                 font=("Segoe UI", 9)).pack(anchor="w")
        v_rb = tk.IntVar(value=int(self._working.rebuff_minutes))
        tk.Scale(frame, from_=5, to=10, orient="horizontal",
                 variable=v_rb, bg=_BG, fg=_FG, highlightthickness=0,
                 troughcolor=_PANEL, activebackground=_ACCENT,
                 command=lambda v: self._mark_dirty()).pack(fill="x")
        self._tk_vars["rebuff_minutes"] = v_rb

        v_sb = tk.BooleanVar(value=self._working.start_with_buff)
        tk.Checkbutton(frame, text="iniciar com buff", variable=v_sb,
                       bg=_BG, fg=_FG, selectcolor=_PANEL,
                       activebackground=_BG, activeforeground=_FG,
                       font=("Segoe UI", 9), command=self._mark_dirty).pack(anchor="w", pady=(2, 0))
        self._tk_vars["start_with_buff"] = v_sb

    def _build_skill_row(self, parent, fk):
        row = tk.Frame(parent, bg=_BG)
        row.pack(fill="x", pady=2)

        v_en = tk.BooleanVar(value=getattr(self._working, f"skill_{fk}"))
        cb = tk.Checkbutton(row, text=fk.upper(), variable=v_en,
                            bg=_BG, fg=_FG, selectcolor=_PANEL,
                            activebackground=_BG, activeforeground=_FG,
                            font=("Segoe UI", 9, "bold"), width=6, anchor="w",
                            command=self._mark_dirty)
        cb.pack(side="left")
        self._tk_vars[f"skill_{fk}"] = v_en

        tk.Label(row, text="CD:", bg=_BG, fg=_FG,
                 font=("Segoe UI", 9)).pack(side="left", padx=(10, 4))

        v_cd = tk.StringVar(value=f"{getattr(self._working, f'skill_{fk}_cd'):.1f}")
        is_f1 = (fk == "f1")
        ent = tk.Entry(
            row, textvariable=v_cd, width=8, bg=_PANEL,
            fg=(_MUTED if is_f1 else _FG),
            insertbackground=_FG, relief="flat", font=("Segoe UI", 9),
            readonlybackground=_PANEL,
            state=("readonly" if is_f1 else "normal"),
        )
        ent.pack(side="left")
        tk.Label(row, text="s", bg=_BG, fg=_MUTED, font=("Segoe UI", 8)).pack(side="left", padx=2)
        if not is_f1:
            ent.bind("<KeyRelease>", lambda e: self._mark_dirty())
        self._cd_vars[fk] = v_cd
        self._tk_vars[f"skill_{fk}_cd"] = v_cd

    # ── POT ───────────────────────────────────────────────────────────────
    def _build_pot(self, frame):
        self._section_title(frame, "Pot thresholds")
        tk.Label(frame, text="Dispara quando a barra cai abaixo do %:",
                 bg=_BG, fg=_MUTED, font=("Segoe UI", 8),
                 wraplength=290, justify="left").pack(anchor="w", pady=(0, 6))
        for label, field, color in [
            ("HP", "pot_hp_pct", "#e94f4f"),
            ("SP", "pot_sp_pct", "#67d061"),
            ("MP", "pot_mp_pct", "#5a9cff"),
        ]:
            row = tk.Frame(frame, bg=_BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=_BG, fg=color,
                     font=("Segoe UI", 10, "bold"), width=4).pack(side="left")
            v = tk.IntVar(value=int(getattr(self._working, field)))
            tk.Scale(row, from_=1, to=99, orient="horizontal",
                     variable=v, bg=_BG, fg=_FG, highlightthickness=0,
                     troughcolor=_PANEL, activebackground=_ACCENT,
                     command=lambda x: self._mark_dirty()).pack(side="left", fill="x", expand=True)
            self._tk_vars[field] = v

    # ── DROPS ─────────────────────────────────────────────────────────────
    def _build_drops(self, frame):
        self._section_title(frame, "Drops")
        v = tk.BooleanVar(value=self._working.soul_beep)
        tk.Checkbutton(frame, text="beep ao detectar Soul", variable=v,
                       bg=_BG, fg=_FG, selectcolor=_PANEL,
                       activebackground=_BG, activeforeground=_FG,
                       font=("Segoe UI", 9), command=self._mark_dirty).pack(anchor="w", pady=(4, 0))
        self._tk_vars["soul_beep"] = v

    # ── RES ───────────────────────────────────────────────────────────────
    def _build_res(self, frame):
        self._section_title(frame, "Resolucao")

        # Resolucao atual do jogo (live, atualizada no _tick)
        cur_box = tk.Frame(frame, bg=_PANEL)
        cur_box.pack(fill="x", pady=(0, 6))
        tk.Label(cur_box, text="Sua resolucao atual:", bg=_PANEL, fg=_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(6, 0))
        self._res_cur_lbl = tk.Label(cur_box, text="detectando...", bg=_PANEL,
                                     fg="white", font=("Segoe UI", 13, "bold"))
        self._res_cur_lbl.pack(anchor="w", padx=8, pady=(0, 6))

        # Status: mapeada / nao mapeada
        self._res_stat_lbl = tk.Label(frame, text="", bg=_BG, fg=_MUTED,
                                      font=("Segoe UI", 9, "bold"),
                                      wraplength=290, justify="left")
        self._res_stat_lbl.pack(anchor="w", pady=(0, 6))

        # Botao Mapear
        map_btn = tk.Button(
            frame, text="Mapear resolucao", bg=_ACCENT, fg="white", bd=0,
            relief="flat", font=("Segoe UI", 10, "bold"),
            activebackground=_ACTIVE, activeforeground="white",
            takefocus=0, command=self._open_map_wizard,
        )
        map_btn.pack(fill="x", ipady=5, pady=(0, 10))

        tk.Frame(frame, bg="#2a2a2a", height=1).pack(fill="x", pady=(0, 8))

        tk.Label(
            frame, text="Profile usado pelo macro:\n"
                        "Auto = segue a resolucao atual do jogo.",
            bg=_BG, fg=_MUTED, font=("Segoe UI", 8),
            wraplength=290, justify="left",
        ).pack(anchor="w", pady=(0, 4))

        cur = getattr(self._working, "forced_resolution", "auto")
        v = tk.StringVar(value=cur if cur else "auto")
        options = ["auto"] + list(self._resolutions)
        cmb = ttk.Combobox(frame, textvariable=v, values=options,
                           state="readonly", width=18)
        cmb.pack(anchor="w", pady=4)
        cmb.bind("<<ComboboxSelected>>", lambda e: self._mark_dirty())
        self._tk_vars["forced_resolution"] = v
        self._res_combo = cmb

        self._res_list_lbl = tk.Label(
            frame,
            text="Mapeadas: " + (", ".join(self._resolutions) if self._resolutions
                                 else "(nenhuma)"),
            bg=_BG, fg=_MUTED, font=("Segoe UI", 8),
            wraplength=290, justify="left",
        )
        self._res_list_lbl.pack(anchor="w", pady=(8, 0))

    # ── resolucao: poll + status ──────────────────────────────────────────
    def _refresh_res_status(self):
        """Atualiza o label 'sua resolucao atual' + status mapeada/nao-mapeada.
        Chamado no _tick (~1s). Detecta troca de resolucao do jogo em tempo real."""
        if self._get_res is None or self._res_cur_lbl is None:
            return
        try:
            res = self._get_res()
        except Exception:
            res = None
        if res == self._last_res:
            return
        self._last_res = res
        if not res:
            self._res_cur_lbl.config(text="jogo nao encontrado", fg=_MUTED)
            self._res_stat_lbl.config(text="", fg=_MUTED)
            return
        w, h = res
        key = f"{w}x{h}"
        self._res_cur_lbl.config(text=key, fg="white")
        if key in self._resolutions:
            self._res_stat_lbl.config(
                text="✓ Resolucao mapeada", fg=_SUCCESS)
        else:
            self._res_stat_lbl.config(
                text="⚠ Resolucao NAO mapeada\nClique em 'Mapear resolucao'.",
                fg="#f0b132")

    def _refresh_res_widgets(self):
        """Repopula dropdown + lista de mapeadas apos um novo mapeamento."""
        opts = ["auto"] + list(self._resolutions)
        if self._res_combo is not None:
            self._res_combo.config(values=opts)
        if self._res_list_lbl is not None:
            self._res_list_lbl.config(
                text="Mapeadas: " + (", ".join(self._resolutions)
                                     if self._resolutions else "(nenhuma)"))
        self._last_res = None       # forca _refresh_res_status a reavaliar
        self._refresh_res_status()

    def _open_map_wizard(self):
        if self._wizard is not None:
            return
        if self._get_res is None or self._capture is None or self._save_map is None:
            return
        try:
            res = self._get_res()
        except Exception:
            res = None
        if not res:
            self._res_stat_lbl.config(
                text="⚠ Jogo nao encontrado. Abra o PT EU antes de mapear.",
                fg=_DANGER)
            return
        self._wizard = _MapWizard(self, res)

    def _on_mapping_done(self, w, h, prof):
        """Callback do wizard ao concluir — persiste e atualiza a UI."""
        self._wizard = None
        if prof is None:
            return
        try:
            self._save_map(w, h, prof)
        except Exception:
            pass
        key = f"{w}x{h}"
        if key not in self._resolutions:
            self._resolutions.append(key)
        self._refresh_res_widgets()

    def _section_title(self, parent, text):
        tk.Label(parent, text=text, bg=_BG, fg=_FG,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 6))

    # ── tab / profile switching ───────────────────────────────────────────
    def _switch_tab(self, tab):
        self._cur_tab = tab
        for name, frame in self._tab_frames.items():
            frame.pack_forget()
        self._tab_frames[tab].pack(fill="both", expand=True)
        for name, btn in self._tab_btns.items():
            if name == tab:
                btn.config(bg=_ACTIVE, fg="white")
            else:
                btn.config(bg=_PANEL, fg=_FG)

    def _switch_profile(self, name):
        # carrega o perfil clicado pro working-copy (descarta edicoes nao-salvas)
        self._working = self._load_prof(name)
        self._active = name
        self._reload_vars_from_working()
        self._dirty = False
        self._rename_var.set(self._display_name(self._active))
        self._highlight_active_profile()
        self._update_editing_label()
        self._update_use_button()
        self._update_dirty_label()

    def _highlight_active_profile(self):
        runtime = self._hud_state.active_profile
        for name, btn in self._prof_btns.items():
            label = self._display_name(name)
            if name == self._active:
                btn.config(text=label, bg=_ACTIVE, fg="white",
                           font=("Segoe UI", 9, "bold"))
            elif name == runtime:
                # em uso pelo runtime mas nao sendo editado
                btn.config(text=f"● {label}", bg=_PANEL, fg=_SUCCESS,
                           font=("Segoe UI", 9))
            else:
                btn.config(text=label, bg=_PANEL, fg=_FG,
                           font=("Segoe UI", 9))

    def _display_name(self, profile_key: str) -> str:
        return self._hud_state.profile_names.get(profile_key, profile_key)

    def _update_editing_label(self):
        runtime = self._display_name(self._hud_state.active_profile)
        editing = self._display_name(self._active)
        self._editing_lbl.config(text=f"Editando: {editing}  |  Em uso: {runtime}")

    def _update_dirty_label(self):
        self._dirty_lbl.config(text="* alteracoes nao salvas" if self._dirty else "")

    def _update_use_button(self):
        if self._active != self._hud_state.active_profile:
            self._use_btn.config(state="normal", bg=_ACCENT, fg="white")
        else:
            self._use_btn.config(state="disabled", bg=_DISABLED, fg=_MUTED)

    def _update_status(self, active: bool):
        if self._last_active_state == active:
            return
        self._last_active_state = active
        if active:
            self._status_lbl.config(text="● Executando", fg=_SUCCESS)
        else:
            self._status_lbl.config(text="○ Desativado", fg=_DANGER)

    def _reload_vars_from_working(self):
        for field, var in self._tk_vars.items():
            val = getattr(self._working, field, None)
            if val is None:
                continue
            if isinstance(var, tk.StringVar):
                if isinstance(val, float):
                    var.set(f"{val:.1f}")
                else:
                    var.set(str(val))
            else:
                var.set(val)

    # ── rename ────────────────────────────────────────────────────────────
    def _do_rename(self):
        new = self._rename_var.get().strip()
        if not new:
            self._rename_var.set(self._display_name(self._active))
            return
        if new == self._display_name(self._active):
            return
        self._hud_state.profile_names[self._active] = new
        try:
            self._on_state(self._hud_state)
        except Exception:
            pass
        self._highlight_active_profile()
        self._update_editing_label()

    # ── save / use ────────────────────────────────────────────────────────
    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self._update_dirty_label()

    def _save(self):
        # garante que rename pendente foi commitado antes do save
        self._do_rename()
        # tk vars -> _working
        for field, var in self._tk_vars.items():
            try:
                raw = var.get()
            except Exception:
                continue
            cur = getattr(self._working, field)
            if isinstance(cur, bool):
                setattr(self._working, field, bool(raw))
            elif isinstance(cur, int):
                try:
                    setattr(self._working, field, int(raw))
                except (ValueError, TypeError):
                    pass
            elif isinstance(cur, float):
                try:
                    setattr(self._working, field, float(raw))
                except (ValueError, TypeError):
                    pass
            else:
                setattr(self._working, field, str(raw) if raw is not None else "")

        self._on_save(self._active, self._working)
        self._dirty = False
        self._update_editing_label()
        self._update_dirty_label()
        self._highlight_active_profile()
        self._update_use_button()

    def _use(self):
        if self._active == self._hud_state.active_profile:
            return
        self._on_use(self._active)
        self._update_editing_label()
        self._highlight_active_profile()
        self._update_use_button()

    # ── drag ──────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_x = e.x_root - self.win.winfo_x()
        self._drag_y = e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self.win.geometry(f"+{x}+{y}")

    def _drag_end(self, e):
        self._hud_state.hud_x = self.win.winfo_x()
        self._hud_state.hud_y = self.win.winfo_y()
        try:
            self._on_state(self._hud_state)
        except Exception:
            pass

    def _safe_get_active(self) -> bool:
        try:
            return bool(self._get_active())
        except Exception:
            return False

    # ── mini-badge (Executando / Parado) ──────────────────────────────────
    def _kill_config(self):
        """Mata a janela de config DE VEZ. Apos isso a config nunca mais volta —
        so o badge permanece, alternando Executando/Parado."""
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None

    def _show_mini(self):
        """Cria o badge permanente (uma unica vez)."""
        if self._mini is not None:
            return
        try:
            m = tk.Toplevel(self.root)
            m.overrideredirect(True)
            m.attributes("-topmost", True)
            m.attributes("-alpha", 0.92)
            m.configure(bg=_SUCCESS)
            lbl = tk.Label(m, text="●", bg=_SUCCESS, fg="white",
                           font=("Segoe UI", 9, "bold"), padx=12, pady=5)
            lbl.pack()
            self._mini = m
            self._mini_lbl = lbl
        except Exception:
            self._mini = None
            self._mini_lbl = None

    def _update_badge(self, active: bool):
        """Atualiza texto/cor do badge conforme o estado. So reescreve na mudanca."""
        if self._mini is None or self._mini_lbl is None:
            return
        state = bool(active)
        if self._badge_state == state:
            return
        self._badge_state = state
        bg = _SUCCESS if state else _DANGER
        txt = "● Executando" if state else "● Parado"
        try:
            self._mini.configure(bg=bg)
            self._mini_lbl.configure(text=txt, bg=bg)
            self._mini.update_idletasks()
            sw = self._mini.winfo_screenwidth()
            bw = self._mini.winfo_reqwidth()
            self._mini.geometry(f"+{sw - bw - 12}+12")   # canto superior direito
        except Exception:
            pass

    # ── tick ──────────────────────────────────────────────────────────────
    def _tick(self):
        if self._destroyed:
            return
        if self._shutdown_pending:
            self._shutdown_pending = False
            self._destroyed = True
            try:
                self.root.destroy()
            except Exception:
                pass
            return
        active = self._safe_get_active()
        # Ctrl+J so alterna a janela de config ENQUANTO ela existe (antes do macro
        # ligar pela 1a vez). Depois que o badge assume, Ctrl+J nao faz nada.
        if self._toggle_pending:
            self._toggle_pending = False
            if self.win is not None:
                self.visible = not self.visible
                try:
                    if self.visible:
                        self.win.attributes("-alpha", _ALPHA)
                        self.win.attributes("-disabled", False)
                    else:
                        self.win.attributes("-alpha", 0.0)
                        self.win.attributes("-disabled", True)
                except Exception:
                    pass
        # 1a ativacao: mata a config DE VEZ e cria o badge permanente.
        if active and self.win is not None:
            self._kill_config()
            self._show_mini()
        # Badge permanente: a partir daqui so alterna Executando/Parado.
        if self._mini is not None:
            self._update_badge(active)
        # Status + poll de resolucao so enquanto a config existe (antes de ligar).
        if self.win is not None:
            self._update_status(active)
            self._res_poll_ctr += 1
            if self._res_poll_ctr >= 5:
                self._res_poll_ctr = 0
                self._refresh_res_status()
        if self._wizard is not None:
            self._wizard.poll()
        self.root.after(200, self._tick)


# ── Wizard de mapeamento de resolucao ─────────────────────────────────────
class _MapWizard:
    """Modal pra mapear barras (HP/SP/MP) e slots de pote de uma resolucao.

    Captura SPACE GLOBALMENTE via keyboard lib — funciona mesmo com o PT EU em
    foco (o usuario mira no jogo, o HUD nem precisa ter foco). O botao Cancelar
    tem takefocus=0 pra nunca roubar o SPACE.
    """

    _STEPS = (
        ("Barra de VIDA — mire no TOPO da barra",     'top'),
        ("Barra de VIDA — mire na BASE da barra",     'bot'),
        ("Barra de STAMINA — mire no TOPO da barra",  'top'),
        ("Barra de STAMINA — mire na BASE da barra",  'bot'),
        ("Barra de MANA — mire no TOPO da barra",     'top'),
        ("Barra de MANA — mire na BASE da barra",     'bot'),
        ("Pote de VIDA — mire no CENTRO do slot",     'pt'),
        ("Pote de STAMINA — mire no CENTRO do slot",  'pt'),
        ("Pote de MANA — mire no CENTRO do slot",     'pt'),
    )

    def __init__(self, hud: "HUD", res: tuple):
        self._hud   = hud
        self._w, self._h = int(res[0]), int(res[1])
        self._step  = 0
        self._pts   = []          # lista de (rx, ry) na ordem dos steps
        self._pending = False     # setado pela thread do keyboard, lido no poll()
        self._hk    = None
        self._done  = False

        self.win = tk.Toplevel(hud.root)
        self.win.title("map")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)
        self.win.configure(bg=_BG)
        # canto superior-esquerdo — longe das barras (base) e potes (centro-baixo)
        self.win.geometry("330x210+30+30")

        tk.Label(self.win, bg=_ACCENT, fg="white", height=1,
                 text=f"Mapeando  {self._w}x{self._h}",
                 font=("Segoe UI", 10, "bold")).pack(fill="x")

        self._instr = tk.Label(self.win, bg=_BG, fg="white", wraplength=300,
                                justify="center", font=("Segoe UI", 11, "bold"))
        self._instr.pack(pady=(14, 4), padx=10)

        tk.Label(self.win, bg=_BG, fg=_MUTED, wraplength=300, justify="center",
                 text="Posicione o mouse SOBRE o jogo e tecle ESPACO.",
                 font=("Segoe UI", 8)).pack(padx=10)

        self._prog = tk.Label(self.win, bg=_BG, fg=_ACCENT,
                              font=("Segoe UI", 9, "bold"))
        self._prog.pack(pady=(8, 0))

        self._last = tk.Label(self.win, bg=_BG, fg=_MUTED, font=("Segoe UI", 8))
        self._last.pack()

        btns = tk.Frame(self.win, bg=_BG)
        btns.pack(side="bottom", fill="x", padx=10, pady=10)
        tk.Button(btns, text="Voltar", bg=_PANEL, fg=_FG, bd=0, relief="flat",
                  font=("Segoe UI", 9), activebackground=_ACTIVE,
                  activeforeground="white", takefocus=0,
                  command=self._back).pack(side="left", expand=True, fill="x", padx=(0, 3))
        tk.Button(btns, text="Cancelar", bg=_DANGER, fg="white", bd=0, relief="flat",
                  font=("Segoe UI", 9), activebackground="#a33",
                  activeforeground="white", takefocus=0,
                  command=self._cancel).pack(side="left", expand=True, fill="x", padx=(3, 0))

        # hook global de SPACE (suppress evita que o jogo receba o espaco)
        if keyboard is not None:
            try:
                self._hk = keyboard.add_hotkey("space", self._on_space,
                                               suppress=True, trigger_on_release=False)
            except Exception:
                self._hk = None
        # fallback local (so funciona com o wizard em foco)
        self.win.bind("<space>", lambda e: self._on_space())
        self.win.bind("<Escape>", lambda e: self._cancel())

        self._render()

    # keyboard thread → so seta flag (tk nao e thread-safe)
    def _on_space(self):
        self._pending = True

    # chamado no _tick do HUD (thread tk) — processa captura pendente
    def poll(self):
        if self._done or not self._pending:
            return
        self._pending = False
        self._capture_current()

    def _capture_current(self):
        if self._hud._capture is None:
            return
        try:
            pt = self._hud._capture()
        except Exception:
            pt = None
        if pt is None:
            self._last.config(text="cursor fora da janela do jogo — tente de novo",
                              fg=_DANGER)
            return
        self._pts.append(pt)
        self._last.config(text=f"capturado: ({pt[0]:.3f}, {pt[1]:.3f})", fg=_SUCCESS)
        self._step += 1
        if self._step >= len(self._STEPS):
            self._finish()
        else:
            self._render()

    def _back(self):
        if self._step == 0:
            return
        self._step -= 1
        if self._pts:
            self._pts.pop()
        self._last.config(text="", fg=_MUTED)
        self._render()

    def _render(self):
        if self._step >= len(self._STEPS):
            return
        txt, _ = self._STEPS[self._step]
        self._instr.config(text=txt)
        self._prog.config(text=f"Passo {self._step + 1} de {len(self._STEPS)}")

    def _finish(self):
        p = self._pts
        prof = {
            'ZA': (p[0][0], p[0][1], p[1][1]),
            'ZB': (p[2][0], p[2][1], p[3][1]),
            'ZC': (p[4][0], p[4][1], p[5][1]),
            'PA': (p[6][0], p[6][1]),
            'PB': (p[7][0], p[7][1]),
            'PC': (p[8][0], p[8][1]),
        }
        self._teardown()
        self._hud._on_mapping_done(self._w, self._h, prof)

    def _cancel(self):
        self._teardown()
        self._hud._on_mapping_done(self._w, self._h, None)

    def _teardown(self):
        if self._done:
            return
        self._done = True
        if self._hk is not None and keyboard is not None:
            try:
                keyboard.remove_hotkey(self._hk)
            except Exception:
                pass
            self._hk = None
        try:
            self.win.destroy()
        except Exception:
            pass
