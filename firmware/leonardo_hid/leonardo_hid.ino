/*
 * leonardo_hid.ino — Arduino Leonardo R3 (ATmega32u4) HID dongle.
 *
 * USB nativo do Leonardo expõe DUAS interfaces ao PC:
 *   1) CDC (Serial virtual) — recebe comandos do macro Python
 *   2) HID Keyboard + Mouse — re-emite como input físico no SO
 *
 * Mesma USB, mesmo cabo. NÃO precisa de CH340 nem fios extras.
 *
 * Protocolo ASCII, 115200 baud (CDC ignora baud rate na prática),
 * terminador '\n':
 *   KD<hex>     key down  (hex = Arduino keycode, ex: C2 = F1)
 *   KU<hex>     key up
 *   MDL / MDR   mouse left/right button down
 *   MUL / MUR   mouse left/right button up
 *   M<dx>,<dy>  mouse move relative (signed decimal, -127..127 por comando)
 *   P           ping  → responde "OK\n"
 *
 * Eventos enviados do Arduino para o PC:
 *   TOGGLE      botão físico no PIN_TOGGLE pressionado
 *
 * Wiring:
 *   USB Leonardo → PC. Só isso.
 *   (Opcional) Push button entre PIN_TOGGLE (D2) e GND
 */

#include <Keyboard.h>
#include <Mouse.h>

// ── Config ─────────────────────────────────────────────────────────────────
static const uint32_t UART_BAUD     = 115200;
static const uint8_t  PIN_TOGGLE    = 2;     // botão físico opcional → GND
static const uint16_t DEBOUNCE_MS   = 50;
static const uint16_t LONG_PRESS_MS = 1000;  // segurar ≥1s = KILL
static const uint8_t  PIN_LED       = LED_BUILTIN;
static const uint8_t  RX_BUF_SIZE   = 64;

// ── Estado do parser ───────────────────────────────────────────────────────
static char    rxBuf[RX_BUF_SIZE];
static uint8_t rxLen = 0;

// ── Estado do botão ────────────────────────────────────────────────────────
static uint8_t  lastBtnState  = HIGH;
static uint32_t lastBtnChange = 0;
static uint32_t pressStart    = 0;     // millis() quando o botão foi pressionado
static bool     killFired     = false; // evita duplo-fire enquanto segura

// ── Utils ──────────────────────────────────────────────────────────────────
static int hexNibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
  if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
  return -1;
}

// Parses 2-char hex byte starting at idx. Returns -1 on bad input.
static int parseHexByte(const char* s, uint8_t idx) {
  int hi = hexNibble(s[idx]);
  int lo = hexNibble(s[idx + 1]);
  if (hi < 0 || lo < 0) return -1;
  return (hi << 4) | lo;
}

// Parses "M<dx>,<dy>" — returns true and fills outputs on success.
static bool parseMove(const char* s, int8_t& dx, int8_t& dy) {
  // s points to char after 'M' (the start of dx digits)
  char* end1;
  long x = strtol(s, &end1, 10);
  if (end1 == s || *end1 != ',') return false;
  char* end2;
  long y = strtol(end1 + 1, &end2, 10);
  if (end2 == end1 + 1) return false;
  // clamp para int8_t (Mouse.move limit)
  if (x < -127) x = -127; if (x > 127) x = 127;
  if (y < -127) y = -127; if (y > 127) y = 127;
  dx = (int8_t)x;
  dy = (int8_t)y;
  return true;
}

// ── Command dispatch ───────────────────────────────────────────────────────
static void handleCommand(const char* cmd, uint8_t len) {
  if (len == 0) return;

  // P — ping
  if (len == 1 && cmd[0] == 'P') {
    Serial.print("OK\n");
    return;
  }

  // K<D|U><hex>
  if (len >= 4 && cmd[0] == 'K' && (cmd[1] == 'D' || cmd[1] == 'U')) {
    int kc = parseHexByte(cmd, 2);
    if (kc < 0) return;
    
    Serial.print("LOG: Teclado ");
    Serial.print(cmd[1] == 'D' ? "DOWN " : "UP ");
    Serial.println(kc, HEX);

    if (cmd[1] == 'D') Keyboard.press((uint8_t)kc);
    else               Keyboard.release((uint8_t)kc);
    return;
  }

  // M<D|U><L|R>
  if (len == 3 && cmd[0] == 'M' && (cmd[1] == 'D' || cmd[1] == 'U')) {
    uint8_t btn;
    if      (cmd[2] == 'L') btn = MOUSE_LEFT;
    else if (cmd[2] == 'R') btn = MOUSE_RIGHT;
    else if (cmd[2] == 'M') btn = MOUSE_MIDDLE;
    else return;
    
    Serial.print("LOG: Mouse ");
    Serial.print(cmd[1] == 'D' ? "DOWN " : "UP ");
    Serial.println(cmd[2]);

    if (cmd[1] == 'D') Mouse.press(btn);
    else               Mouse.release(btn);
    return;
  }

  // M<dx>,<dy>
  if (len >= 4 && cmd[0] == 'M' && (cmd[1] == '-' || (cmd[1] >= '0' && cmd[1] <= '9'))) {
    int8_t dx, dy;
    if (parseMove(cmd + 1, dx, dy)) {
      Serial.print("LOG: Mover X=");
      Serial.print(dx);
      Serial.print(" Y=");
      Serial.println(dy);
      
      Mouse.move(dx, dy, 0);
    }
    return;
  }
}

// ── UART line reader ───────────────────────────────────────────────────────
static void pollUart() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLen > 0) {
        rxBuf[rxLen] = '\0';
        handleCommand(rxBuf, rxLen);
        rxLen = 0;
      }
    } else if (rxLen < RX_BUF_SIZE - 1) {
      rxBuf[rxLen++] = c;
    } else {
      // overflow — drop linha
      rxLen = 0;
    }
  }
}

// ── Botão físico ──────────────────────────────────────────────────────────
// Short press (<1s): envia TOGGLE
// Long press  (≥1s): envia KILL (LED aceso enquanto segura, dispara ao atingir)
static void pollButton() {
  uint8_t s = digitalRead(PIN_TOGGLE);
  uint32_t now = millis();

  // Transição (com debounce)
  if (s != lastBtnState && (now - lastBtnChange) > DEBOUNCE_MS) {
    lastBtnChange = now;
    lastBtnState = s;
    if (s == LOW) {                  // pressionou
      pressStart = now;
      killFired  = false;
    } else {                         // soltou
      if (!killFired) {
        Serial.print("TOGGLE\n");
        digitalWrite(PIN_LED, HIGH);
        delay(40);
        digitalWrite(PIN_LED, LOW);
      }
      // se killFired, já enviou KILL durante o hold — não manda TOGGLE
    }
  }

  // Enquanto segura, ao atingir LONG_PRESS_MS dispara KILL e acende LED
  if (s == LOW && !killFired && (now - pressStart) >= LONG_PRESS_MS) {
    killFired = true;
    Serial.print("KILL\n");
    digitalWrite(PIN_LED, HIGH);  // LED aceso até soltar (feedback visual)
  }
}

// ── Arduino lifecycle ──────────────────────────────────────────────────────
void setup() {
  pinMode(PIN_TOGGLE, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  Serial.begin(UART_BAUD);
  Keyboard.begin();
  Mouse.begin();

  // Heartbeat de boot — 3 piscadas curtas pra confirmar firmware vivo.
  for (uint8_t i = 0; i < 3; i++) {
    digitalWrite(PIN_LED, HIGH); delay(80);
    digitalWrite(PIN_LED, LOW);  delay(80);
  }
}

void loop() {
  pollUart();
  pollButton();
}
