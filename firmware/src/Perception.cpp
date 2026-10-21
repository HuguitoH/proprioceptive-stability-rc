#include "Perception.h"
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <math.h>

#include "config.h"
#include "kinematics.h"


//  Private configuration and state (only this module)

namespace {
  // Speed is recomputed over this window. 500 ms is far too slow for a
  // 100 Hz control loop: replacing it is part of task 2.5.
  const unsigned long SPEED_INTERVAL_MS = 500;

  // Complementary filter coefficient
  const float ALPHA = 0.98;

  // IMU object
  Adafruit_MPU6050 mpu;

  // Orientation state (kept between calls to integrate over time)
  unsigned long lastImuTime = 0;

  // Hall sensor state (shared with the interrupt)
  volatile unsigned long pulseCount = 0;
  volatile unsigned long lastPulseTime = 0;
  unsigned long previousPulseCount = 0;
  unsigned long lastSpeedTime = 0;

  // Interrupt: counts a pulse each time the magnet passes
  void IRAM_ATTR onHallPulse() {
    unsigned long now = micros();
    if (now - lastPulseTime > config::kHallDebounceUs) {
      pulseCount++;
      lastPulseTime = now;
    }
  }
}

//  Public function implementations

bool perceptionInit() {
  Wire.begin(config::kI2cSda, config::kI2cScl);

  if (!mpu.begin()) {
    return false;   // IMU not found
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  pinMode(config::kHallPin, INPUT);
  attachInterrupt(digitalPinToInterrupt(config::kHallPin), onHallPulse, FALLING);

  lastImuTime = micros();
  lastSpeedTime = millis();
  return true;
}

void updatePerception(CarState& state) {
  // --- Orientation (IMU + complementary filter) ---
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  unsigned long now = micros();
  float dt = (now - lastImuTime) / 1000000.0;
  lastImuTime = now;

  float pitchAcc = atan2(a.acceleration.x,
                    sqrt(a.acceleration.y * a.acceleration.y +
                         a.acceleration.z * a.acceleration.z)) * 180.0 / PI;
  float rollAcc = atan2(a.acceleration.y,
                   sqrt(a.acceleration.x * a.acceleration.x +
                        a.acceleration.z * a.acceleration.z)) * 180.0 / PI;

  float gx = g.gyro.x * 180.0 / PI;
  float gy = g.gyro.y * 180.0 / PI;
  float gz = g.gyro.z * 180.0 / PI;

  state.orientation.pitch = ALPHA * (state.orientation.pitch + gy * dt) + (1 - ALPHA) * pitchAcc;
  state.orientation.roll  = ALPHA * (state.orientation.roll  + gx * dt) + (1 - ALPHA) * rollAcc;
  state.orientation.yaw   = state.orientation.yaw + gz * dt;
  state.orientation.yawRate = gz;   // direct rotation speed, no drift

  // --- Speed (Hall sensor), computed every interval ---
  unsigned long nowMs = millis();
  if (nowMs - lastSpeedTime >= SPEED_INTERVAL_MS) {
    unsigned long pulses = pulseCount - previousPulseCount;
    previousPulseCount = pulseCount;

    float dtSpeed = (nowMs - lastSpeedTime) / 1000.0;
    lastSpeedTime = nowMs;

    state.speed.driveshaftRpm = core::driveshaftRpm(pulses, dtSpeed, config::kMagnetsOnShaft);
  }
}
