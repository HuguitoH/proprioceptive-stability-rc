#include "Actuation.h"
#include <Arduino.h>
#include <ESP32Servo.h>

#include "config.h"

//  Private configuration (only this module needs to know)
namespace {
  // Objects controlling the hardware
  Servo steeringServo;
  Servo esc;
}

//  Public function implementations
void actuationInit() {
  steeringServo.attach(config::kServoPin);
  esc.attach(config::kEscPin);
  setSteering(config::kSteerCentre);   // start centered
  setMotor(config::kMotorNeutral);     // start stopped
  delay(config::kEscArmingMs);  // give the ESC time to arm
}

void setSteering(int angle) {
  // Clamp to the safe range to protect the steering mechanics
  angle = constrain(angle, config::kSteerRight, config::kSteerLeft);
  steeringServo.write(angle);
}

void setMotor(int signal) {
  esc.write(signal);
}
