# Proprioceptive stability control for a 1:10-scale vehicle

Can a car keep its balance using only what it feels, before it learns to see?

This repository holds the code, data and plan of my final-year Individual Study (BSc Computer Science, Canterbury Christ Church University, 2026–27):
*Low-Cost Proprioceptive Stability Control for a 1:10-Scale Vehicle without LiDAR: Towards Shared Autonomy*.

> **Research question.** To what extent can a reactive stability controller based solely on low-cost proprioception (IMU and encoder) reduce yaw-rate deviation in a 1:10-scale vehicle, and how can it be integrated into a shared-autonomy scheme?

The vehicle is a Jamara 1:10 buggy with an ESP32-S3, an MPU6050 IMU and a Hall-effect sensor on the driveshaft. The controller compares the measured yaw rate with the one expected from a kinematic bicycle model, and a Simplex-style safety layer decides when it may override the driver.

## Repository layout

| Folder | Contents |
|---|---|
| `firmware/` | PlatformIO project for the car. `lib/core` is hardware-free and unit-tested on the laptop |
| `analysis/` | Metrics and statistical tests computed from the logged runs |
| `data/` | Description of the dataset and where the raw logs are published |
| `planning/` | Project plan as data (`project.yaml`) and the planner that schedules it |
| `tests/` | Tests of the Python code |
| `docs/` | Build log of the vehicle, wiring and bill of materials |
| `log/` | Hours worked per task, for planned-versus-actual tracking |

## Getting started

**Firmware** ([PlatformIO](https://platformio.org/)):

```bash
cd firmware
cp include/secrets.example.h include/secrets.h   # then set your own WiFi password
pio test -e native            # unit tests on the laptop
pio run -e esp32s3 -t upload  # build and flash the car
```

**Python** ([uv](https://docs.astral.sh/uv/)):

```bash
uv sync                       # create the environment from uv.lock
uv run pytest                 # run the tests
uv run python -m planning     # regenerate the plan tables and diagrams
```

## Working conventions

- One branch per issue, merged through a pull request that closes it (`Closes #12`).
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
- Every push runs the firmware unit tests, the firmware build and the Python tests.

## Licence

Code is released under the [MIT licence](LICENSE). Data in `data/` is released under [CC BY 4.0](data/LICENSE).
