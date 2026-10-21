#include "Control.h"
#include <Arduino.h>

#include "config.h"

//  Private configuration and state (only this module)
namespace {
  // PID gains (to be tuned experimentally with the car running)
  const float KP = 2.0;    // proportional: reacts to current error
  const float KI = 0.0;    // integral: eliminates persistent error
  const float KD = 0.5;    // derivative: dampens, prevents overshoot

  // PID internal state (kept between calls)
  float integral = 0.0;      // accumulated error
  float previousError = 0.0; // error from the last call
  unsigned long lastTime = 0;
}

//  Public function implementations

void controlInit() {
  integral = 0.0;
  previousError = 0.0;
  lastTime = micros();
}

int computeSteering(const CarState& state, float targetYawRate) {
  // - The ERROR: difference between desired and actual
  float error = targetYawRate - state.orientation.yawRate;

  // - Time elapsed since last call
  unsigned long now = micros();
  float dt = (now - lastTime) / 1000000.0;
  lastTime = now;
  if (dt <= 0) dt = 0.001;   // safety against division issues

  // - P: proportional to the current error
  float proportional = KP * error;

  // - I: proportional to the accumulated error
  integral += error * dt;
  float integralTerm = KI * integral;

  // - D: proportional to the rate of change of the error
  float derivative = (error - previousError) / dt;
  float derivativeTerm = KD * derivative;
  previousError = error;

  // - Total correction (the PID formula)
  float correction = proportional + integralTerm + derivativeTerm;

  // - Apply correction to the steering center
  int steering = config::kSteerCentre + (int)correction;

  // - Clamp to safe range 
  steering = constrain(steering, config::kSteerRight, config::kSteerLeft);

  return steering;
}
