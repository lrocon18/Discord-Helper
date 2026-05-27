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

        # working copy
        self._working = self._load_prof(self._hud_state.active_profile)
        self._active  = self._hud_state.active_profile

        # tk state
        self.root        = None
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
        self.root = tk.Tk()
        self.root.title("d")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", _ALPHA)
        self.root.configure(bg=_BG)

        # ttk theme tweaks (combobox dark)
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

        sw = self.root.winfo_screenwidth()
        x = self._hud_state.hud_x if self._hud_state.hud_x >= 0 else (sw - _W - 20)
        y = self._hud_state.hud_y if self._hud_state.hud_y >= 0 else 40
        self.root.geometry(f"{_W}x{_H}+{x}+{y}")

        # ── header (drag) ──
        hdr = tk.Frame(self.root, bg=_ACCENT, height=28)
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
        st_frame = tk.Frame(self.root, bg=_BG)
        st_frame.pack(fill="x", pady=(4, 4))
        self._status_lbl = tk.Label(
            st_frame, text="—", bg=_BG, fg=_MUTED,
            font=("Segoe UI", 10, "bold"))
        self._status_lbl.pack()

        # ── tabs ──
        tabs_bar = tk.Frame(self.root, bg=_PANEL)
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
        content = tk.Frame(self.root, bg=_BG)
        content.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        self._build_combate(self._make_tab(content, "COMBATE"))
        self._build_pot(self._make_tab(content, "POT"))
        self._build_drops(self._make_tab(content, "DROPS"))
        self._build_res(self._make_tab(content, "RES"))

        # ── footer ──
        tk.Frame(self.root, bg="#2a2a2a", height=1).pack(fill="x", pady=(8, 0))
        footer = tk.Frame(self.root, bg=_BG)
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
        tk.Label(
            frame, text="Forca o profile de calibracao usado pelo macro.\n"
                        "Auto = detecta a resolucao mais proxima.",
            bg=_BG, fg=_MUTED, font=("Segoe UI", 8),
            wraplength=290, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        cur = getattr(self._working, "forced_resolution", "auto")
        v = tk.StringVar(value=cur if cur else "auto")
        options = ["auto"] + list(self._resolutions)
        cmb = ttk.Combobox(frame, textvariable=v, values=options,
                           state="readonly", width=18)
        cmb.pack(anchor="w", pady=4)
        cmb.bind("<<ComboboxSelected>>", lambda e: self._mark_dirty())
        self._tk_vars["forced_resolution"] = v

        tk.Label(
            frame,
            text="Mapeadas: " + (", ".join(self._resolutions) if self._resolutions
                                  else "(nenhuma)"),
            bg=_BG, fg=_MUTED, font=("Segoe UI", 8),
            wraplength=290, justify="left",
        ).pack(anchor="w", pady=(8, 0))

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
        # refresh comboboxes + icones
        for fk in ("f1", "f2", "f3", "f4"):
            self._refresh_skill_options(fk)
            self._refresh_skill_icon(fk)
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
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def _drag_end(self, e):
        self._hud_state.hud_x = self.root.winfo_x()
        self._hud_state.hud_y = self.root.winfo_y()
        try:
            self._on_state(self._hud_state)
        except Exception:
            pass

    def _safe_get_active(self) -> bool:
        try:
            return bool(self._get_active())
        except Exception:
            return False

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
        if self._toggle_pending:
            self._toggle_pending = False
            self.visible = not self.visible
            try:
                if self.visible:
                    self.root.attributes("-alpha", _ALPHA)
                    self.root.attributes("-disabled", False)
                else:
                    self.root.attributes("-alpha", 0.0)
                    self.root.attributes("-disabled", True)
            except Exception:
                pass
        # Auto-shutdown: assim que o macro vira active, destroi HUD
        active = self._safe_get_active()
        if active and not self._last_active_state:
            self._shutdown_pending = True
        self._update_status(active)
        self.root.after(200, self._tick)
