// main.cpp -- unit utama purifier (ESP32-S3). Membaca sensor, menjalankan state machine, mengatur kipas.
//
// BELUM diuji di perangkat keras / Wokwi. Logika kontrolnya (controller.h) SUDAH diuji di komputer
// terhadap simulator Python (make test-firmware). Lapisan Arduino di file ini = tugas pengujianmu.
//
// Keluaran serial (115200 baud), satu baris CSV per langkah kontrol, cocok untuk logging data:
//   ms,pm_raw,rh,pm_corr,pm_f,level,profil,rpm,gangguan
#include <Arduino.h>
#include <Preferences.h>
#include <Wire.h>
#include <math.h>

#include "config.h"
#include "controller.h"
#include "pms5003.h"
#include "sht31.h"

using namespace purifier;

static Controller ctl;
static Preferences prefs;
static Pms5003Parser pms;
static volatile uint32_t tach_pulses = 0;
static double pm_sum = 0.0;
static uint32_t pm_count = 0;
static double rh_now = 70.0;  // dipakai bila SHT31 tidak ada/gagal (asumsi RH tropis)
static int pm_fault_ticks = 0;
static int fan_fault_ticks = 0;
static bool profile_vuln = false;

void IRAM_ATTR on_tach() { tach_pulses = tach_pulses + 1; }

// ---------- PWM (kompatibel Arduino-ESP32 2.x dan 3.x) ----------
static void pwm_init() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_FAN_PWM, PWM_FREQ, PWM_BITS);
#else
  ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_BITS);
  ledcAttachPin(PIN_FAN_PWM, PWM_CHANNEL);
#endif
}

static void pwm_write(uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(PIN_FAN_PWM, duty);
#else
  ledcWrite(PWM_CHANNEL, duty);
#endif
}

static void fan_apply(int level) {
  const uint32_t duty = (uint32_t)(SPEED[level] * ((1u << PWM_BITS) - 1) + 0.5);
  digitalWrite(PIN_FAN_EN, level == LVL_OFF ? LOW : HIGH);  // OFF = daya kipas diputus (modul saklar)
  pwm_write(duty);
}

static void leds_apply(int level, bool fault) {
  digitalWrite(PIN_LED_LOW, level >= LVL_LOW);
  digitalWrite(PIN_LED_MED, level >= LVL_MEDIUM);
  digitalWrite(PIN_LED_TURBO, level >= LVL_TURBO);
  digitalWrite(PIN_LED_FAULT, fault);
}

// ---------- Profil rentan (tombol) ----------
static void set_profile(bool vuln, bool save) {
  profile_vuln = vuln;
  ctl.cfg.f_profile = vuln ? VULN_FACTOR : 1.0;
  if (save) prefs.putBool("vuln", vuln);
}

static void handle_button(uint32_t now) {
  static bool last = HIGH;
  static uint32_t t_change = 0;
  const bool v = digitalRead(PIN_BTN_PROFILE);
  if (v != last && now - t_change > 50) {
    t_change = now;
    last = v;
    if (v == LOW) set_profile(!profile_vuln, true);
  }
}

// ---------- Sensor ----------
#if !SIM_ANALOG
static void pms_poll() {
  while (Serial2.available()) {
    Pms5003Frame fr;
    if (pms.feed((uint8_t)Serial2.read(), fr)) {
      pm_sum += fr.pm25_cf1;  // CF=1; dirata-ratakan selama satu periode kontrol
      ++pm_count;
    }
  }
}

static void sht31_read() {
  Wire.beginTransmission(SHT31_ADDR);
  Wire.write(0x24);
  Wire.write(0x00);
  if (Wire.endTransmission() != 0) return;
  delay(16);
  if (Wire.requestFrom((int)SHT31_ADDR, 6) != 6) return;
  uint8_t b[6];
  for (int i = 0; i < 6; ++i) b[i] = Wire.read();
  double t, rh;
  if (sht31_parse(b, t, rh)) rh_now = rh;
}
#endif

#if SIM_ANALOG
static double adc_to_pm(int v) {  // 0..600 ug/m3, skala kuadrat agar rentang rendah mudah diatur
  const double x = v / 4095.0;
  return 600.0 * x * x;
}
static double adc_to_rh(int v) { return 40.0 + 59.0 * v / 4095.0; }
#endif

// ---------- Satu langkah kontrol ----------
static void control_tick() {
  double raw = 0.0;
  bool ok = false;
#if SIM_ANALOG
  raw = adc_to_pm(analogRead(PIN_POT_PM));
  rh_now = adc_to_rh(analogRead(PIN_POT_RH));
  ok = true;
#else
  if (pm_count > 0) {
    raw = pm_sum / pm_count;
    ok = true;
  }
  pm_sum = 0.0;
  pm_count = 0;
  sht31_read();
#endif

  if (ok) {
    pm_fault_ticks = 0;
    ctl.step(raw, rh_now, DT_MIN);
  } else if (pm_fault_ticks < 1000) {
    ++pm_fault_ticks;
  }
  const bool pm_fault = pm_fault_ticks >= PM_FAULT_LIMIT;
  if (pm_fault) ctl.force_level(LVL_MEDIUM);  // fail-safe: sensor debu mati -> tetap menyaring (TIDAK ada di simulator)

  uint32_t pulses;
  noInterrupts();
  pulses = tach_pulses;
  tach_pulses = 0;
  interrupts();
  const double rpm = pulses / 2.0 * 60.0 / (TICK_MS / 1000.0);  // 2 pulsa per putaran
  if (TACH_ENABLED && ctl.level > LVL_OFF && rpm < MIN_RPM) {
    ++fan_fault_ticks;
  } else {
    fan_fault_ticks = 0;
  }
  const bool fan_fault = fan_fault_ticks >= FAN_FAULT_LIMIT;
  const bool fault = pm_fault || fan_fault;

  fan_apply(ctl.level);
  leds_apply(ctl.level, fault);

  const double corr = firmware_correct(raw, rh_now, ctl.cfg.kappa_est, ctl.cfg.smoke_est);
  Serial.printf("%lu,%.0f,%.1f,%.1f,%.1f,%d,%d,%.0f,%d\n", (unsigned long)millis(), raw, rh_now, corr,
                ctl.pm_f, ctl.level, profile_vuln ? 1 : 0, rpm, fault ? 1 : 0);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FAN_EN, OUTPUT);
  pinMode(PIN_LED_LOW, OUTPUT);
  pinMode(PIN_LED_MED, OUTPUT);
  pinMode(PIN_LED_TURBO, OUTPUT);
  pinMode(PIN_LED_FAULT, OUTPUT);
  pinMode(PIN_BTN_PROFILE, INPUT_PULLUP);
  pinMode(PIN_TACH, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_TACH), on_tach, FALLING);
  pwm_init();

  prefs.begin("purifier", false);
  set_profile(prefs.getBool("vuln", false), false);

#if SIM_ANALOG
  analogReadResolution(12);
#else
  Serial2.begin(9600, SERIAL_8N1, PIN_PMS_RX, PIN_PMS_TX);
  Wire.begin(PIN_SDA, PIN_SCL);
#endif

  fan_apply(LVL_OFF);
  leds_apply(LVL_OFF, false);
  Serial.println(F("ms,pm_raw,rh,pm_corr,pm_f,level,profil,rpm,gangguan"));
}

void loop() {
  static uint32_t t_tick = 0;
  const uint32_t now = millis();
  handle_button(now);
#if !SIM_ANALOG
  pms_poll();
#endif
  if (now - t_tick >= TICK_MS) {
    t_tick = now;
    control_tick();
  }
}
