#pragma once

// Copy this file to secrets.h (ignored by git) and set your own values.
// The car creates its own WiFi access point for telemetry.

namespace secrets {
constexpr const char* kWifiSsid     = "rc-telemetry";
constexpr const char* kWifiPassword = "change-me-please";   // at least 8 characters
}  // namespace secrets
