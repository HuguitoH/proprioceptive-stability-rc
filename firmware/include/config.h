#pragma once

// Hardware wiring and calibration of this vehicle, in one place.
// Every module reads its constants from here, so a pin or a limit is never
// defined twice (it was duplicated in Control and Actuation before).

namespace config {

// - Pins
constexpr int kI2cSda   = 8;
constexpr int kI2cScl   = 9;
constexpr int kHallPin  = 6;
constexpr int kServoPin = 4;
constexpr int kEscPin   = 5;

// - Hall sensor on the driveshaft
constexpr int kMagnetsOnShaft = 2;
// Pulses closer than this are switch bounce, not a magnet.
constexpr unsigned long kHallDebounceUs = 2000;

// - Steering servo (degrees as written to the servo) 
constexpr int kSteerCentre = 90;
constexpr int kSteerLeft   = 145;   // mechanical limit
constexpr int kSteerRight  = 35;    // mechanical limit

// - ESC
constexpr int kMotorNeutral = 90;
constexpr unsigned long kEscArmingMs = 3000;

// - Telemetry
constexpr int kTelemetryPort = 8080;

}  // namespace config
