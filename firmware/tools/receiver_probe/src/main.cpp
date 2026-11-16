#include <Arduino.h>

namespace {

// ADC1 pins are suitable for this probe because they also work while WiFi is enabled.
constexpr uint8_t kReceiverPin = 7;
// Midpoint between zero and the lowest expected high level after the divider (~2.2 V).
constexpr uint16_t kHighThresholdMv = 1100;
// Full-scale voltage of the ESP32-S3 ADC with 11 dB attenuation.
constexpr uint16_t kSaturationMv = 3100;
constexpr uint32_t kCaptureWindowUs = 900000;
// 12,000 samples occupy about 96 KiB because each Sample is 8-byte aligned.
constexpr size_t kMaxSamples = 12000;
constexpr uint32_t kReportPeriodUs = 1000000;

struct Sample {
  uint32_t timeUs;
  uint16_t millivolts;
};

struct Capture {
  Sample samples[kMaxSamples];
  size_t count = 0;
  uint32_t samplingStepUs = 0;
};

struct PulseStats {
  uint64_t sumUs = 0;
  uint32_t minimumUs = UINT32_MAX;
  uint32_t maximumUs = 0;
  size_t count = 0;

  void add(uint32_t valueUs) {
    sumUs += valueUs;
    count++;
    minimumUs = min(minimumUs, valueUs);
    maximumUs = max(maximumUs, valueUs);
  }

  uint32_t mean() const {
    return count == 0 ? 0 : static_cast<uint32_t>(sumUs / count);
  }
};

struct Analysis {
  uint16_t maximumMv = 0;
  bool saturated = false;
  uint32_t samplingStepUs = 0;
  PulseStats period;
  PulseStats width;
};

void captureSamples(Capture& capture) {
  capture.count = 0;
  capture.samplingStepUs = 0;
  const uint32_t startUs = micros();
  uint32_t previousTimeUs = startUs;

  while (capture.count < kMaxSamples &&
         micros() - startUs < kCaptureWindowUs) {
    const uint32_t timeUs = micros();
    const uint16_t millivolts =
        static_cast<uint16_t>(analogReadMilliVolts(kReceiverPin));
    capture.samples[capture.count++] = {timeUs, millivolts};

    if (capture.count > 1) {
      capture.samplingStepUs += timeUs - previousTimeUs;
    }
    previousTimeUs = timeUs;
  }

  if (capture.count > 1) {
    capture.samplingStepUs /= capture.count - 1;
  }
}

Analysis analyseSamples(const Sample* samples, size_t count,
                        uint32_t samplingStepUs) {
  Analysis result{};
  result.samplingStepUs = samplingStepUs;

  if (count == 0) {
    return result;
  }

  bool high = samples[0].millivolts >= kHighThresholdMv;
  bool haveRising = false;
  uint32_t risingUs = 0;
  result.maximumMv = samples[0].millivolts;
  result.saturated = samples[0].millivolts >= kSaturationMv;

  for (size_t i = 1; i < count; ++i) {
    result.maximumMv = max(result.maximumMv, samples[i].millivolts);
    result.saturated =
        result.saturated || samples[i].millivolts >= kSaturationMv;

    const bool currentHigh = samples[i].millivolts >= kHighThresholdMv;
    if (!high && currentHigh) {
      if (haveRising) {
        const uint32_t periodUs = samples[i].timeUs - risingUs;
        result.period.add(periodUs);
      }
      risingUs = samples[i].timeUs;
      haveRising = true;
    } else if (high && !currentHigh && haveRising) {
      const uint32_t widthUs = samples[i].timeUs - risingUs;
      result.width.add(widthUs);
    }
    high = currentHigh;
  }

  return result;
}

void printStats(const char* label, const PulseStats& stats) {
  Serial.printf(", %s=", label);
  if (stats.count > 0) {
    Serial.printf("mean=%lu us, min=%lu us, max=%lu us, n=%u",
                  static_cast<unsigned long>(stats.mean()),
                  static_cast<unsigned long>(stats.minimumUs),
                  static_cast<unsigned long>(stats.maximumUs),
                  static_cast<unsigned>(stats.count));
  } else {
    Serial.print("no data");
  }
}

void printAnalysis(const Analysis& result, size_t sampleCount) {
  Serial.printf(
      "samples=%u, step=%lu us (width error +/- %lu us), max=%u mV, "
      "saturation=%s",
      static_cast<unsigned>(sampleCount),
      static_cast<unsigned long>(result.samplingStepUs),
      static_cast<unsigned long>(result.samplingStepUs),
      static_cast<unsigned>(result.maximumMv),
      result.saturated ? "YES" : "NO");
  printStats("period", result.period);
  printStats("width", result.width);
  Serial.println();
}

void dumpSamples(const Capture& capture) {
  Serial.println("BEGIN");
  Serial.println("time_us,mV");
  for (size_t i = 0; i < capture.count; ++i) {
    Serial.printf("%lu,%u\n",
                  static_cast<unsigned long>(capture.samples[i].timeUs),
                  static_cast<unsigned>(capture.samples[i].millivolts));
  }
  Serial.println("END");
}

bool dumpRequested() {
  bool requested = false;
  while (Serial.available() > 0) {
    const char command = static_cast<char>(Serial.read());
    if (command == 'd' || command == 'D') {
      requested = true;
    }
  }
  return requested;
}

}  // namespace

void setup() {
  Serial.begin(921600);
  analogSetPinAttenuation(kReceiverPin, ADC_11db);
  Serial.printf("Receiver probe: GPIO%u, threshold=%u mV\n",
                static_cast<unsigned>(kReceiverPin),
                static_cast<unsigned>(kHighThresholdMv));
  Serial.println("Send DUMP or d to dump the next capture as CSV");
}

void loop() {
  static Capture capture;
  static uint32_t nextReportUs = 0;
  static bool pendingDump = false;
  const uint32_t captureStartUs = micros();

  pendingDump = pendingDump || dumpRequested();
  captureSamples(capture);
  const Analysis result =
      analyseSamples(capture.samples, capture.count, capture.samplingStepUs);
  printAnalysis(result, capture.count);

  pendingDump = pendingDump || dumpRequested();
  if (pendingDump) {
    dumpSamples(capture);
    pendingDump = false;
  }

  nextReportUs = captureStartUs + kReportPeriodUs;
  while (static_cast<int32_t>(micros() - nextReportUs) < 0) {
    delay(1);
  }
}
