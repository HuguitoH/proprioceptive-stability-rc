# Brownout probe

Does the 5 V supply keep the ESP32 alive while WiFi is transmitting?

The probe runs a WiFi access point and broadcasts UDP packets without pause, so the radio draws its current peaks.
It counts boots and keeps a log of the last ten reset reasons in flash, so resets that happen with no USB connected
can be read afterwards.

## Wiring

```
NiMH 4.2 Ah ──Tamiya──► buck IN+ / IN−
                         buck OUT+ ─────────► ESP32 5V
                         buck OUT− ─────────► ESP32 GND
```

| From | To |
|---|---|
| Electronics battery (Tamiya) | Buck IN+ and IN− |
| Buck OUT+ (red jumper) | ESP32 pin 5V |
| Buck OUT− (black jumper) | ESP32 pin G |

Never connect OUT+ to the 3V3 pin. Never power the board from the buck and USB at the same time.

## Procedure

1. Set the buck to 5.0 V with nothing on its output, and check it with the multimeter.
2. Flash the probe over USB and open the monitor:
   ```bash
   pio run -d firmware/tools/brownout_probe -t upload
   pio device monitor -d firmware/tools/brownout_probe -f log2file
   ```
3. Press BOOT within 3 s of the start message to reset the counters and the log.
4. Unplug USB. Connect the jumpers with the battery unplugged.
5. Plug the battery in one go. Pushing jumpers onto live pins causes contact bounce and extra boots.
6. Connect a phone to the probe's access point and keep it connected.
7. Leave it running for at least 10 minutes. Measure the 5 V at the buck terminals and at the ESP32 pin,
   and read the buck input on its display at the start, middle and end.
8. Unplug the battery, plug USB in, open the monitor and read the counters. Do not press BOOT.

## Reading the output

```
Boots: 3, Brownouts: 0, Last reason: 1
Log 0: reason 1, previous uptime 0 s
Log 1: reason 1, previous uptime 0 s
Log 2: reason 1, previous uptime 790 s
```

| Field | Meaning |
|---|---|
| Boots | Every start since the reset, the reset run and the final USB readout included |
| Brownouts | Starts caused by the supply dropping too low |
| reason | `esp_reset_reason_t`: 1 power on, 3 software, 4 panic, 6 task watchdog, 9 brownout |
| previous uptime | How long the previous boot ran, saved every 10 s |

A clean run gives 3 boots (reset, buck, readout), 0 brownouts, and the readout entry showing a previous uptime
equal to the test length. Extra entries with reason 1 and uptime 0 are contact bounce at power-up.

## Results

LM2596S buck, 14 Nov 2026: [issue #7](https://github.com/HuguitoH/proprioceptive-stability-rc/issues/7).
