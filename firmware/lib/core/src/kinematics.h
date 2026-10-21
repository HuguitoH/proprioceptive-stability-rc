#pragma once

// Pure vehicle kinematics: no Arduino, no hardware.
// Everything in lib/core can be unit-tested on the laptop (pio test -e native),
// which is what lets the software progress while the car is still being built.

namespace core {

// Driveshaft speed from the Hall pulses counted over an interval.
// Returns 0 for a non-positive interval instead of dividing by zero.
inline float driveshaftRpm(unsigned long pulses, float intervalS, int magnetsOnShaft) {
  if (intervalS <= 0.0f || magnetsOnShaft <= 0) {
    return 0.0f;
  }
  const float revolutionsPerSecond = (static_cast<float>(pulses) / intervalS) / magnetsOnShaft;
  return revolutionsPerSecond * 60.0f;
}

}  // namespace core
