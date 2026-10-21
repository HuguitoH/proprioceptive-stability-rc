#include <Arduino.h>

#include "Actuation.h"
#include "CarState.h"
#include "Communication.h"
#include "Perception.h"

// Starting point carried over from the summer prototype: the car senses
// itself and streams its state, with the actuators held at neutral.
// The closed-loop controller is NOT applied yet. It comes back through
// tasks 2.5 (100 Hz loop and logger), 2.6 (safety basics) and 4.1 (PI).

namespace {
  CarState state{};
}

void setup() {
  Serial.begin(115200);

  if (!perceptionInit()) {
    Serial.println("IMU not found: check the I2C wiring. Halting.");
    while (true) {
      delay(1000);
    }
  }
  actuationInit();       // steering centred, motor at neutral
  communicationInit();
}

void loop() {
  updatePerception(state);
  sendTelemetry(state);
}
