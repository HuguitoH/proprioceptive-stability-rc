// Bench probe: does the 5 V supply survive WiFi transmit peaks?
// Counters live in flash, so they survive the resets we are looking for.
// Procedure: flash over USB, unplug USB, power from the buck, let it run,
// then power off the buck, plug USB back in and read the counters.

#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiUdp.h>

#include "secrets.h"

namespace {

constexpr uint8_t  kBootButtonPin  = 0;      // BOOT button, LOW when pressed
constexpr uint32_t kResetWindowMs  = 3000;   // press BOOT within this window after power-up
constexpr uint16_t kUdpPort        = 12345;
constexpr uint32_t kTransmitGapMs  = 2;      // short gap: keeps the radio busy without flooding lwIP
constexpr uint32_t kPrintPeriodMs  = 1000;   // repeated, so a late serial monitor still sees it
constexpr uint32_t kUptimeSavePeriodMs = 10000;
constexpr size_t   kLogSize         = 10;
constexpr char     kNamespace[]    = "brownout";

struct BootCounters {
  uint32_t boots;
  uint32_t brownouts;
  uint32_t lastReason;   // raw esp_reset_reason_t, so other resets (watchdog...) are visible too
};

WiFiUDP udp;             // one socket for the whole run, not one per loop iteration

// Holding BOOT while the chip powers up enters the ROM downloader instead of
// running this sketch, so the request is a press shortly AFTER power-up.
bool resetRequested() {
  pinMode(kBootButtonPin, INPUT_PULLUP);
  Serial.printf("Press BOOT within %lu ms to reset the counters\n",
                static_cast<unsigned long>(kResetWindowMs));
  const uint32_t start = millis();
  while (millis() - start < kResetWindowMs) {
    if (digitalRead(kBootButtonPin) == LOW) {
      return true;
    }
    delay(10);
  }
  return false;
}

BootCounters loadCounters() {
  Preferences prefs;
  prefs.begin(kNamespace, /*readOnly=*/true);   // fails harmlessly on the very first run: defaults apply
  const BootCounters c{prefs.getUInt("boots", 0),
                       prefs.getUInt("brownouts", 0),
                       prefs.getUInt("lastReason", 0)};
  prefs.end();
  return c;
}

void saveCounters(const BootCounters& c) {
  Preferences prefs;
  prefs.begin(kNamespace, /*readOnly=*/false);
  prefs.putUInt("boots", c.boots);
  prefs.putUInt("brownouts", c.brownouts);
  prefs.putUInt("lastReason", c.lastReason);
  prefs.end();
}

// Pure: takes the stored counters and why this boot happened, returns the new counters.
BootCounters recordBoot(BootCounters c, esp_reset_reason_t reason) {
  c.boots++;
  if (reason == ESP_RST_BROWNOUT) {
    c.brownouts++;
  }
  c.lastReason = static_cast<uint32_t>(reason);
  return c;
}

void printCounters(const BootCounters& c) {
  // Reason codes: see esp_reset_reason_t (ESP_RST_POWERON, ESP_RST_BROWNOUT, ESP_RST_TASK_WDT...)
  Serial.printf("Boots: %lu, Brownouts: %lu, Last reason: %lu\n",
                static_cast<unsigned long>(c.boots),
                static_cast<unsigned long>(c.brownouts),
                static_cast<unsigned long>(c.lastReason));
}

struct BootLogEntry {
  uint32_t reason;
  uint32_t previousUptimeS;
};

struct BootLog {
  BootLogEntry entries[kLogSize]{};
  uint8_t nextIndex = 0;
  uint8_t count = 0;

  void add(const BootLogEntry& entry) {
    entries[nextIndex] = entry;
    nextIndex = (nextIndex + 1) % kLogSize;
    if (count < kLogSize) {
      count++;
    }
  }
};

BootLog loadBootLog() {
  BootLog log;
  Preferences prefs;
  prefs.begin(kNamespace, /*readOnly=*/true);
  const bool valid =
      prefs.getBytes("bootLog", log.entries, sizeof(log.entries)) == sizeof(log.entries);
  if (valid) {
    log.nextIndex = prefs.getUChar("logIndex", 0);
    log.count = prefs.getUChar("logCount", 0);
  }
  prefs.end();

  // Missing or corrupt state starts an empty log rather than a half-valid one.
  if (!valid || log.nextIndex >= kLogSize || log.count > kLogSize) {
    return BootLog{};
  }
  return log;
}

void saveBootLog(const BootLog& log) {
  Preferences prefs;
  prefs.begin(kNamespace, /*readOnly=*/false);
  prefs.putBytes("bootLog", log.entries, sizeof(log.entries));
  prefs.putUChar("logIndex", log.nextIndex);
  prefs.putUChar("logCount", log.count);
  prefs.end();
}

uint32_t loadPreviousUptimeS() {
  Preferences prefs;
  prefs.begin(kNamespace, /*readOnly=*/true);
  const uint32_t uptimeS = prefs.getUInt("uptimeS", 0);
  prefs.end();
  return uptimeS;
}

void saveUptimeS(uint32_t uptimeS) {
  Preferences prefs;
  prefs.begin(kNamespace, /*readOnly=*/false);
  prefs.putUInt("uptimeS", uptimeS);
  prefs.end();
}

void printBootLog(const BootLog& log) {
  const uint8_t oldestIndex = log.count == kLogSize
                                  ? log.nextIndex
                                  : 0;
  for (uint8_t offset = 0; offset < log.count; ++offset) {
    const uint8_t entryIndex = (oldestIndex + offset) % kLogSize;
    const BootLogEntry& entry = log.entries[entryIndex];
    Serial.printf("Log %u: reason %lu, previous uptime %lu s\n",
                  static_cast<unsigned>(offset),
                  static_cast<unsigned long>(entry.reason),
                  static_cast<unsigned long>(entry.previousUptimeS));
  }
}

void startAccessPoint() {
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(secrets::kWifiSsid, secrets::kWifiPassword)) {
    Serial.println("ERROR: access point did not start");   // explicit: a silent radio would fake a pass
    return;
  }
  Serial.printf("Access point '%s' started\n", secrets::kWifiSsid);   // never log the password
}

// Broadcast, not our own IP: packets addressed to ourselves never reach the antenna.
void transmitBurst() {
  static uint32_t sequence = 0;
  udp.beginPacket(WiFi.softAPBroadcastIP(), kUdpPort);
  udp.printf("probe %lu", static_cast<unsigned long>(sequence++));
  udp.endPacket();
  delay(kTransmitGapMs);
}

}// namespace

void setup() {
  Serial.begin(115200);
  const uint32_t previousUptimeS = loadPreviousUptimeS();
  const esp_reset_reason_t reason = esp_reset_reason();

  // Check if the user wants to reset the counters.
    if (resetRequested()) {
    saveCounters({0, 0, 0});
    saveBootLog(BootLog{});      // old runs must not leak into this one
    saveUptimeS(0);
    Serial.println("Counters and boot log reset");
  }

  saveCounters(recordBoot(loadCounters(), reason));

  BootLog log = loadBootLog();
  log.add({static_cast<uint32_t>(reason), previousUptimeS});
  saveBootLog(log);
  saveUptimeS(0);
  printBootLog(log);
  startAccessPoint();
}

void loop() {
  transmitBurst();

  static uint32_t lastUptimeSave = 0;
  if (millis() - lastUptimeSave >= kUptimeSavePeriodMs) {
    saveUptimeS(millis() / 1000);
    lastUptimeSave = millis();
  }

  static uint32_t lastPrint = 0;
    if (millis() - lastPrint >= kPrintPeriodMs) {
    printCounters(loadCounters());
    printBootLog(loadBootLog());
    lastPrint = millis();
  }
}
