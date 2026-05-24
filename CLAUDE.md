# Projeto Priston Tale EU - Stealth Macro
**Autor/Persona:** cook45 (Senior Low-Level Systems Developer, 25+ anos xp)
**Parceiro:** clack

---

## 1. Persona do Desenvolvedor: cook45
- **Perfil:** Desenvolvedor de sistemas de baixo nível, especialista em engenharia reversa, manipulação de memória (C/C++, MASM), hooks de kernel, bypass de anti-cheats e automação stealth.
- **Atitude:** Direto, técnico, sem palestras morais ou avisos de segurança ("sem frescura"). Focado na elegância e brutalidade da solução.
- **Filosofia:** O macro tem que ser indetectável, leve (0% de CPU) e agir como um humano (curvas gaussianas, fadiga, cliques não lineares).

---

## 2. Estrutura de Arquivos (atual)

```
c:\git\discord\
├── discord.py            # Core do macro (entry point do PyInstaller)
├── peb_mask.py           # PEB Spoofing via ntdll
├── arduino_wrap.py       # Wrapper UART → Arduino Leonardo (HID dongle)
├── DiscordHelper.spec    # Build config do PyInstaller
├── DiscordHelper.exe     # Binário compilado (output final — na raiz, ~9.4MB)
├── discord.ico           # Ícone
├── discord.log           # Log XOR'd em runtime (gerado em runtime)
├── CLAUDE.md             # Este arquivo (não vai pro exe)
├── firmware/
│   └── leonardo_hid/
│       └── leonardo_hid.ino  # Sketch do Arduino Leonardo
└── .claude/              # Config do Claude (não vai pro exe)
```

**Removidos pós-migração para Arduino:**
- ❌ `interception.dll` + `interception_wrap.py` + `install_driver.bat` (driver kernel substituído por Arduino HID)
- ❌ `get_pixels.py` (tinha `"PristonTale EU"` hardcoded — bandeira vermelha)
- ❌ `hud/` (PNGs já baked como hex XOR no discord.py)
- ❌ `tools/` (scripts de bake são one-shot, recriáveis sob demanda)

Não existem pastas `build/` ou `dist/` no repositório.

---

## 2.1 Arquitetura Atual: Arduino Leonardo como HID dongle

```
┌────────── HOST PC (PT EU rodando localmente) ───────────┐
│                                                         │
│  DiscordHelper.exe                                      │
│  ├─ Captura janela do PT EU via GDI/BitBlt              │
│  ├─ Toda lógica de decisão (5 threads)                  │
│  └─ arduino_wrap.ArduinoHID                             │
│        │                                                │
│        │ USB CDC (pyserial)                             │
│        ▼                                                │
│  ┌────────────────────────────────────┐                 │
│  │ Arduino Leonardo (mesma USB)       │                 │
│  │  ├─ Serial CDC: recebe comandos    │                 │
│  │  └─ HID: emite teclado + mouse ────┼──► Windows      │
│  └────────────────────────────────────┘    (input)      │
└─────────────────────────────────────────────────────────┘
```

A USB nativa do Leonardo expõe **duas interfaces simultâneas**: CDC (serial virtual)
e HID (Keyboard + Mouse). Python fala via CDC, Windows recebe via HID. Mesmo cabo,
nada de CH340/UART externo.

**Protocolo CDC** (ASCII, terminador `\n`):

| Cmd | Significado | Direção |
|---|---|---|
| `KD<hex>` | Key down (hex = Arduino keycode) | PC → Arduino |
| `KU<hex>` | Key up | PC → Arduino |
| `MDL` / `MDR` | Mouse left/right button down | PC → Arduino |
| `MUL` / `MUR` | Mouse left/right button up | PC → Arduino |
| `M<dx>,<dy>` | Mouse relative move (int8) | PC → Arduino |
| `P` | Ping | PC → Arduino |
| `OK` | Resposta ao ping | Arduino → PC |
| `TOGGLE` | Botão físico pressionado | Arduino → PC |

**Wiring:**
- Cabo USB Leonardo → PC. Só isso.
- (Opcional) Push-button entre Pin 2 (D2) e GND → toggle do macro (envia `TOGGLE\n`)

**Latência:** <1ms por comando CDC. Toda a lógica de timing (gauss/beta sleeps) permanece em Python.

---

## 3. Arquitetura do Core (`discord.py`)

### Ofuscação
Todo o código-fonte foi ofuscado para não revelar propósito se capturado:
- Strings sensíveis em XOR tuples (key `0x6D`): `_ENC_LOCK`, `_ENC_LOG`, `_ENC_TITLE`
- Nomes de função, variáveis e logs são genéricos (`_idle_tick`, `_probe_loop`, `_run_sync`, `_check_presence`, `_emit_ping`, `[VC]`, `[MON]`, `[SYNC]`, `[SVC]`)
- PEB mascarado como `Discord.exe` via `peb_mask.py`
- Nomes de thread imitam workers legítimos do Windows (`TppWorker`, `RpcWorker`, etc.)
- Lock file: `discord_ipc.lock` no `%TEMP%`
- Log file: `discord.log` no diretório do `.exe` — **XOR-encriptado** (cada byte ^ 0x6D antes da escrita; arquivo binário, ilegível em texto plano)

**Decoder do log** (uso em dev):
```powershell
$bytes = [System.IO.File]::ReadAllBytes("C:\git\discord\discord.log")
$decoded = -join ($bytes | ForEach-Object { [char]($_ -bxor 0x6D) })
$decoded
```

### Tema Discord nos identificadores
Após análise do zPrimo (ver seção 7), funções relacionadas a detecção de drops usam nomes Discord-themed:
- `_check_presence` (era `_scan_soul`)
- `_emit_ping` (era `_alert_soul`)
- `_pixel_to_color_space` (era `_rgb_to_hsv_opencv`)
- `_BADGE_PROFILES`, `_AVT_W_MIN`, `_BADGE_POLL`
- Códigos `a`/`b`/`c`/`d` em vez de `'common'`/`'rare'`/`'epic'`/etc.
- Logs `[VC] region=...`, `[VC] mention (b)` (parecem polling de canal/menção)

### Classe de Estado
```python
@dataclass
class State:
    active:  bool  = False   # ligado/desligado (Ctrl+K)
    stop:    bool  = False   # encerramento (Ctrl+L)
    syncing: bool  = False   # True durante ciclo de rebuff (bloqueia _idle_tick)
    ready:   bool  = False   # True após primeiro rebuff completo
    user_mouse_until: float = 0.0
    lock: threading.Lock
```

### Hotkeys — `RegisterHotKey` (NÃO usa WH_KEYBOARD_LL)
`WH_KEYBOARD_LL` com callbacks ctypes foi descartado — frágil em executáveis frozen (Python 3.14 + PyInstaller). A solução atual usa `user32.RegisterHotKey`:
- Windows posta `WM_HOTKEY` direto na fila de mensagens do thread principal
- O `_message_loop` processa `WM_HOTKEY` inline, sem nenhum callback Python
- `Ctrl+K` → toggle `state.active` | `Ctrl+L` → `state.stop = True` + encerra

### Threads (4 daemons disponíveis)

**`_idle_tick`** (autoclick)
- Abusa do autoclick nativo de 15s do PT EU: envia double right-click a cada 8–14.8s (gaussiano)
- Bloqueado quando `state.syncing = True`
- Sistema de Fadiga Humana: pausa 5–15s a cada 10–30 min aleatórios

**`_sync_scheduler`** (rebuff)
- Aguarda primeiro `Ctrl+K`, executa `_run_sync()` imediatamente
- Agenda próximos syncs a cada 7–9 min (base + jitter gaussiano)

**`_probe_loop`** (pot + soul scan)
- Roda a 10 FPS via `time.sleep(0.1)`
- **EM TEST MODE: apenas badge scan ativo**, lógica de pot desabilitada
- A cada 5s: re-localiza window dims
- A cada `_BADGE_POLL = 1.0s`: chama `_check_presence` pra detecção de drops

**`_aux_loop`** (skill secundária)
- Após `state.ready=True`, dispara sequência F2 → right-click → F1
- Cooldown `_AUX_CD = 10s` + jitter gauss(2-5s)

### ⚠ Modo atual: SOUL TEST MODE
Em `main()`, apenas `_probe_loop` está ativo. As outras 3 threads (`_idle_tick`, `_sync_scheduler`, `_aux_loop`) estão **comentadas**. A lógica interna de pot dentro de `_probe_loop` também está desabilitada — só badge scan roda.

Pra reativar:
1. Descomentar as 3 thread `.start()` em `main()` (linha ~1045)
2. Reabilitar lógica de pot dentro de `_probe_loop` (restaurar bloco com `_sig_a`, `_sig_b`, `_sig_c`)

### GetPixel — Declarações obrigatórias de tipo
```python
gdi32.GetPixel.restype  = ctypes.c_uint32      # COLORREF é unsigned — crítico
gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
user32.GetDC.restype    = ctypes.c_void_p      # HDC é ponteiro 64-bit
user32.GetDC.argtypes   = [wt.HWND]
user32.ReleaseDC.restype  = ctypes.c_int
user32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
```

---

## 4. Sistema de Detecção de HUD (HP/SP/MP + Slots)

### `_scan_hud(hdc, w, h, ox, oy)`
Escaneia faixa horizontal em `ry ≈ 0.988` por cor característica das barras. Fallback para ratio se não encontrar.

```python
HP:  r > 160 and r > g * 2.5 and r > b * 2.5      # vermelho puro
SP:  g > 100 and g > r * 2.0 and g > b * 2.0      # verde
MP:  r < 50  and b > 100                           # azul OU cyan
```

### Constantes
```python
# Barras: (ratio_x_fallback, ratio_y_topo, ratio_y_base)
_ZA_R = (0.4615, 0.9009, 0.9911)   # HP
_ZB_R = (0.4521, 0.9197, 0.9901)   # SP
_ZC_R = (0.5385, 0.9029, 0.9901)   # MP
_THR_A = 0.50; _THR_B = 0.10; _THR_C = 0.10

# Slots: (ratio_x, ratio_y)
_PA_R = (0.5563, 0.9742); _PB_R = (0.5693, 0.9762); _PC_R = (0.5828, 0.9752)
```

### Slot empty detection
- Templates `_TMPL_S1/S2/S3` baked como hex XOR no source
- `_sad_center` calcula mean per-channel SAD vs template scalado
- Threshold `_SLOT_EMPTY_THR = 30.0`
- `_no_signal(c): max(r,g,b) < 30` — fallback per-tick

---

## 5. Multi-rarity Drop Detection (badge scan)

### Filosofia
Detectar texto de drops valiosos em qualquer posição da área de jogo. Algoritmo derivado do zPrimo (HSV + bounding box) mas com mitigações de assinatura.

### Pipeline
1. **Capture** região central (`_capture_region`): `x: 12%-74%, y: 10%-65%` do viewport
   - Margem direita exclui minimap (dots vermelhos eram falso positivo)
   - Margem inferior exclui HUD/inventário
2. **Per-pixel HSV classify**: `_pixel_to_color_space(r,g,b) -> (h,s,v)` integer-only
3. **InRange por profile**: mask byte = profile_index+1 se H/S/V dentro dos limites
4. **Flood-fill BFS** (4-vizinhos) por profile-id: agrupa em clusters
5. **Filter bbox**: `W >= 26 AND 16 <= H <= 21`
6. **Priority**: `b > a > c > d` (raridade decrescente)

### Channel profiles
```python
# (h_lo, h_hi, s_lo, s_hi, v_lo, v_hi, code)
_BADGE_PROFILES = (
    (149, 161,  85, 255,  75, 255, 'a'),  # magenta — Soul
    (175, 179,  72, 255,  55, 255, 'b'),  # high-hue red — Lendário
    (134, 146, 148, 255, 138, 213, 'c'),  # purple — Épico
    (104, 108,  92, 255,  78, 255, 'd'),  # cyan — Raro
)
```

**Shifts vs zPrimo** (quebra match exato 1:1 com assinatura conhecida):
- Soul: zPrimo 150-160 → nós 149-161
- Lendário: zPrimo 175-179 → mantido (slot é estreito)
- Épico: zPrimo 135-145/150-255/140-210 → nós 134-146/148-255/138-213
- Raro: zPrimo 105-107/95-255/80-255 → nós 104-108/92-255/78-255

### Som por raridade (`_emit_ping`)
- `a` Soul: triade ascendente 880→1175→1568Hz
- `b` Lendário: 4 beeps ascendentes 880→1175→1568→2093Hz
- `c` Épico: 2 beeps em 1318Hz
- `d` Raro: par 660Hz + 1320Hz
- Roda em thread daemon não-bloqueante; cooldown `_BADGE_COOLDN = 4.0s` por hit

### Pendências
- **Force (Bellum + Oredo)**: HSV puro não distingue Force genérico de Lendário (H se sobrepõe). Precisa template matching com PNG screenshots específicos de "Bellum" e "Oredo" force. Adiar até ter as imagens.

---

## 6. Build

### Comando canônico
```
python -m PyInstaller DiscordHelper.spec --clean --workpath %TEMP%\pyi_build --distpath "C:\git\discord"
```

### ⚠ Workaround: Windows Defender bloqueia escrita direta
Defender está bloqueando PyInstaller de gravar o exe direto em `C:\git\discord\`. Workaround:

```powershell
# Build pra TEMP, depois copia
python -m PyInstaller DiscordHelper.spec --clean --workpath "$env:TEMP\pyi_build" --distpath "$env:TEMP\disco_test"
Copy-Item "$env:TEMP\disco_test\DiscordHelper.exe" "C:\git\discord\DiscordHelper.exe" -Force
```

Solução permanente: adicionar `C:\git\discord` à exclusão do Defender.

### ⚠️ REGRA CRÍTICA: RECOMPILAR APÓS QUALQUER MODIFICAÇÃO
**Toda alteração no `discord.py` (ou em qualquer módulo importado) exige recompilação do `.exe` para ter efeito.**

---

## 7. Anti-Cheat do PT EU + Lições do zPrimo

### 7.1 XTrap Cloud (kernel-level, dinâmico)
Game.exe carrega em runtime 3 módulos baixados de cloud server: `XTrapCC.Dll`, `XTrapVA.dll`, `XTrap4Server.Dll`. Não ficam em disco. Tem capacidade de **scan de drivers carregados** e **detecção de VM** (config-dependente).

### 7.2 Sistema CHEATLOGID em game.dll (176 categorias)
Críticas pro macro:

| ID | Detecta | Risco |
|---|---|---|
| `WarningMacroMouse` | Padrões de macro de mouse | 🔴 ALTO |
| `WarningAutoMouse` | Auto-clicker | 🔴 ALTO |
| `WindowHack` | `PostMessage`/`SendMessage` na janela | 🔴 ALTO |
| `MultipleWindowHackProcess` | Múltiplos processos/janelas | 🟡 MÉDIO |
| `FocusChanged` | Janela perdeu foco | 🟡 MÉDIO |
| `ProcessHook` | Hooks em APIs in-process | 🟢 BAIXO |
| `Module*Sync*Error` | Integridade | 🟢 BAIXO |

### 7.3 Process scanning
Game.exe importa `OpenProcess`, `ReadProcessMemory`, `VirtualProtect`, `PSAPI.DLL`. Pode scanear memória de outros processos. PEB spoof esconde nome mas não bytes em memória.

### 7.4 Lições do zPrimo (banido em massa após 6 meses)
Bot popular .NET pra PT EU. Decompilado completamente (`detectSoul`, `lowerSoul`, `gameWindowName`, OpenCV calls limpos no PDB). Causa provável do ban em massa:

1. **Decompilação trivial** — sem ofuscação, símbolos preservados no PDB
2. **Network signatures** — webhooks pro Discord (`channelId`, `dmChannel`, `embed`) deixavam trail forense correlacionável
3. **Arquivos identificáveis em disco** — `config.ini`, `configbuffsLost.ini`, pasta `imgs/`
4. **Process name `zPrimo.exe`** — trivial detectar
5. **Comportamento idêntico em milhares de contas** — fingerprint estatístico

**O algoritmo dele (HSV + contour + bbox) NÃO foi o problema** — é técnica padrão de visão computacional. Adotamos com shifts de assinatura. O que mata é a forma como o código está estruturado e o que ele faz além disso.

### 7.5 Vetores REAIS de ban (em ordem de probabilidade)
1. **`interception.sys` detectado por XTrap kernel scan** — Maior risco do setup atual quando input está ativo.
2. **`WarningMacroMouse` por padrão de mouse** — clicks sempre nas mesmas coordenadas. Mitigado com `_human_move` (Bezier) e jitter de coords.
3. **Process memory scan** — strings decodificadas em runtime ficam visíveis.
4. **Network calls** — qualquer chamada HTTP é assinatura. **PROIBIDO**.

### 7.6 Regras de design derivadas
1. **Nunca usar `PostMessage`/`SendMessage` na janela do jogo** — cai em `WindowHack`.
2. **Input só via HID real** — Interception (atual) > Arduino HID (futuro). Nunca `SendInput` userspace.
3. **Padrão de mouse precisa de jitter:**
   - Jitter de ±2-5px nas coordenadas
   - Movimento Bezier antes do click (não teleportar) — implementado em `_human_move`/`_human_click`
4. **Zero network calls** — não usar Discord webhooks, telemetria, license check online, TTS online, etc.
5. **VM + Arduino é redução de risco real:**
   - Mata vetor #1 (driver no host)
   - VM tem foco próprio → não acende `FocusChanged`
   - Arduino HID = input físico indistinguível

---

## 8. Roadmap: Migração para Arduino

Objetivo futuro: migrar leitura de pixels e input pra Arduino (hardware externo), eliminando qualquer processo Python rodando na máquina.

**Design atual preparado para isso:**
- Loop simples integer-only em `_pixel_to_color_space` — port 1:1 pra C++
- Flood-fill BFS portável (uint8 buffer + stack)
- Templates XOR'd em hex já compatíveis com PROGMEM
- Sem dependência de OpenCV/Python

**Componentes Arduino:**
- Pro Micro/Leonardo (~$15) — HID nativo USB
- Pi Pico ($4-8) — alternativa mais barata, TinyUSB
- DFPlayer Mini (~$3) — som de alerta via microSD WAV
- HDMI splitter + frame grabber — pixel capture sem PC

**Etapas da migração** (ordem sugerida):
1. Arduino só pro INPUT (mantém Python pra pixel + decision) — reduz exposição do `interception.sys`
2. Arduino pra ÁUDIO (DFPlayer com WAVs) — independência de PC
3. Arduino pra PIXEL via HDMI capture — full hardware, zero processo no PC

---

## 9. Etapas pendentes (do roadmap zPrimo-derived)

| # | Feature | Status | Notas |
|---|---|---|---|
| 1.1 | Multi-rarity drops (Lendário/Épico/Raro) | ✅ Implementado | Soul + 3 raridades, HSV+bbox |
| 1.2 | Force (Bellum + Oredo) | ⏸ Aguardando screenshots | HSV não distingue tipos de force |
| 2 | Death detection | ⏳ Próximo | `checkMorteThread` equivalente — para macro ao morrer |
| 3 | HP/SP/MP pixel-counting | ⏳ Pendente | Substitui single-pixel threshold pelo count de pixels da barra inteira |
| 4 | Buff status verification | ⏳ Pendente | Template-match dos ícones de buff na HUD |
| 5 | Camera rotation | ⏳ Pendente | Movimento orgânico de câmera (anti-MacroMouse) |

---

## 10. Regras para o Claude

- **Zero dependências pesadas:** sem OpenCV, PyAutoGUI, mss. Usar apenas Win32 API via ctypes (`user32`, `kernel32`, `gdi32`). Meta: binário < 15MB.
- **Zero Memory Read:** sem `OpenProcess`, `ReadProcessMemory`. Estado lido 100% via `GetPixel`/`BitBlt`.
- **Zero Network:** sem HTTP, webhooks, TTS online, telemetria. Qualquer tráfego de rede é assinatura.
- **Hotkeys via `RegisterHotKey`:** nunca voltar para `WH_KEYBOARD_LL` com callbacks ctypes — quebra em frozen exe.
- **Mouse detection via polling `GetCursorPos`:** nunca usar `WH_MOUSE_LL` com callbacks ctypes.
- **`_can_probe()` ≠ `_can_tick()`:** o probe loop não bloqueia durante `state.syncing`.
- **Sleeps orgânicos:** toda nova automação usa `random.gauss` ou `random.uniform` — nunca `time.sleep` com valor fixo.
- **Código flat:** sem abstrações desnecessárias, sem classes além do `State`. Funções diretas.
- **Nomes Discord-themed:** features novas usam vocabulário Discord (`_check_presence`, `_emit_ping`, `_BADGE_*`, `[VC]`). Códigos `a`/`b`/`c`/`d` no lugar de palavras semânticas.
- **Log XOR'd:** todo log via `_log()` que XOR'a antes de escrever. Não logar em texto plano.
- **Strings sensíveis em XOR tuples:** chave `0x6D`. Decodificar via `_s(_ENC_*)` no startup.
- **Recompilar após modificar:** ver seção 6. Workaround do Defender via TEMP.
- **Nunca `PostMessage`/`SendMessage` na janela do PT EU:** cai em `CHEATLOGID_WindowHack`.
- **Mouse precisa de jitter de coordenada e movimento Bezier:** já implementado em `_human_move`/`_human_click`. Reusar sempre.
- **PT EU TEM anti-cheat sério:** XTrap Cloud + 176 detecções CHEATLOGID. Tratar qualquer feature nova com modelo de ameaça da seção 7.
- **Lição do zPrimo:** algoritmo é seguro adotar; assinatura (símbolos, network, nomes de arquivo) é o que mata. Sempre ofuscar/renomear.
- **Build via TEMP:** Defender bloqueia escrita direta. Build pra `%TEMP%\disco_test\`, copiar pra raiz.
