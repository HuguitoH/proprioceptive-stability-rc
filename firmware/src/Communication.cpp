#include "Communication.h"
#include <WiFi.h>

#include "config.h"

// The real credentials live in secrets.h, which git ignores. A fresh clone
// (or the CI) falls back to the example values so the build still works.
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

//  Private configuration and state (only this module)
namespace {
  WiFiServer server(config::kTelemetryPort);
  WiFiClient client;
}

//  Public function implementations

void communicationInit() {
  WiFi.softAP(secrets::kWifiSsid, secrets::kWifiPassword);
  server.begin();
}

void sendTelemetry(const CarState& state) {
  // Connect a client if there isn't one (non-blocking)
  if (!client || !client.connected()) {
    client = server.available();
  }

  // Send only if a client is connected
  if (client && client.connected()) {
    client.print(state.orientation.pitch, 2);
    client.print(",");
    client.print(state.orientation.roll, 2);
    client.print(",");
    client.print(state.orientation.yaw, 2);
    client.print(",");
    client.println(state.speed.driveshaftRpm, 0);
  }
}
