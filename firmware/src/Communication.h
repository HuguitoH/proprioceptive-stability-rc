#ifndef COMMUNICATION_H
#define COMMUNICATION_H

#include "CarState.h"

//  Communication module: sends the car's state as telemetry
//  over WiFi. This is the car's "voice" — it reports what it
//  senses so we can observe it remotely.
//  Known limitation: client.print() can block when the TCP
//  buffer is full, so telemetry can still delay control.
//  Moving it to its own task on the other core is part of
//  task 2.5.


// Creates the WiFi network (Access Point) and starts the
// telemetry server. Call once in setup().
void communicationInit();

// Sends the current car state as telemetry, if a client is
// connected. Reads the state without modifying it.
void sendTelemetry(const CarState& state);

#endif
