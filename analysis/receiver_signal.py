"""Receiver probe dumps: extract them from a monitor log into a CSV, and plot them.

        uv run receiver-signal extract <probe.log>
        uv run receiver-signal plot

The CSV keeps the values exactly as logged (time since boot, millivolts at the pin).
Everything derived from them (time origin, divider gain, steering position) is
computed here when plotting, so a wrong constant is fixed by editing code, not data.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

CSV_HEADER = "time_us,mV"           # header line the probe prints inside every dump
HIGH_THRESHOLD_MV = 1100            # between 0 V and the lowest high level at the pin (~2.2 V), same as the probe
DIVIDER_GAIN = 1.5                  # 1k over 2k: receiver voltage = pin voltage x (1k + 2k) / 2k
CENTRE_US = 1500                    # nominal pulse width with the steering wheel centred


DEFAULT_CSV = Path("data/bench/receiver_dumps.csv")         # raw dumps, versioned
DEFAULT_FIGURE = Path("docs/figures/receiver_signal.png")   # regenerated from the CSV


@dataclass(frozen=True)
class Sample:
    block: int    # which BEGIN/END dump the sample came from
    time_us: int  # microseconds since the ESP32 booted, as logged
    mv_pin: int   # millivolts at the ADC pin, before the divider gain (not the receiver signal)


# pure logic
def extract_dumps(log_text: str) -> tuple[list[Sample], list[str]]:
    """Extract samples from every BEGIN/END block.

    Values are returned unchanged. Every line that cannot be trusted produces a
    warning instead of being dropped silently: malformed samples, and blocks that
    were never closed. Samples of an unclosed block are kept, because each line
    that did arrive is a complete measurement. Only the end of the dump is missing.
    """
    samples: list[Sample] = []
    warnings: list[str] = []
    block: int | None = None
    next_block = 0

    for line_number, raw_line in enumerate(log_text.splitlines(), start=1):
        line = raw_line.strip()
        if line == "BEGIN":
            if block is not None:
                warnings.append(f"line {line_number}: block {block} has no END, kept as it is")
            block = next_block
            next_block += 1
            continue
        if line == "END":
            block = None
            continue
        if block is None or line == CSV_HEADER or not line:
            continue

        try:
            # A wrong number of fields also raises ValueError when unpacking.
            time_us, mv_pin = (int(field) for field in line.split(","))
        except ValueError:
            warnings.append(f"line {line_number}: skipped malformed sample: {line}")
            continue
        samples.append(Sample(block, time_us, mv_pin))

    if block is not None:
        warnings.append(f"end of log: block {block} has no END, kept as it is")
    return samples, warnings


def pulse_widths(samples: list[Sample]) -> list[int]:
    """Width in microseconds of every complete pulse in one block.

    A pulse counts only if both its rising and falling edge were seen. Edges fall
    between samples, so each width may read up to one sampling step (~89 us) long.
    """
    widths: list[int] = []
    rising_time_us: int | None = None   # None: no rising edge waiting for its falling edge
    for previous, current in zip(samples, samples[1:]):
        was_high = previous.mv_pin >= HIGH_THRESHOLD_MV
        is_high = current.mv_pin >= HIGH_THRESHOLD_MV
        if is_high and not was_high:
            rising_time_us = current.time_us
        elif was_high and not is_high and rising_time_us is not None:
            widths.append(current.time_us - rising_time_us)
            rising_time_us = None
    return widths


def split_blocks(samples: list[Sample]) -> dict[int, list[Sample]]:
    """Samples grouped by block. Samples of one block are consecutive, as extracted."""
    return {block: list(group) for block, group in groupby(samples, key=lambda s: s.block)}


def steering_positions(blocks: dict[int, list[Sample]]) -> dict[str, int]:
    """Pick one block per steering position from its mean pulse width:
    the shortest pulses are full left, the longest full right, and the
    closest to the nominal centre is centred."""
    means = {b: sum(w) / len(w) for b, s in blocks.items() if (w := pulse_widths(s))}
    if len(means) < 3:
        raise ValueError(f"need at least three blocks with pulses, found {len(means)}")
    return {
        "left": min(means, key=means.get),
        "centre": min(means, key=lambda b: abs(means[b] - CENTRE_US)),
        "right": max(means, key=means.get),
    }



# files
def write_csv(samples: list[Sample], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["block", "time_us", "mv_pin"])
        writer.writerows((s.block, s.time_us, s.mv_pin) for s in samples)


def read_csv(path: Path) -> list[Sample]:
    with path.open(newline="") as f:
        return [Sample(int(r["block"]), int(r["time_us"]), int(r["mv_pin"])) for r in csv.DictReader(f)]


def plot(blocks: dict[int, list[Sample]], path: Path) -> None:
    """Top: 50 ms of the centred signal. Bottom: one pulse per steering position,
    aligned on its rising edge, with the ADC samples shown as dots."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def volts(sample: Sample) -> float:
        return sample.mv_pin * DIVIDER_GAIN / 1000

    def first_rise_us(samples: list[Sample]) -> int:
        return next(c.time_us for p, c in zip(samples, samples[1:])
                    if c.mv_pin >= HIGH_THRESHOLD_MV > p.mv_pin)

    positions = steering_positions(blocks)
    colours = {"left": "#993C1D", "centre": "#185FA5", "right": "#0F6E56"}
    fig, (overview, pulses) = plt.subplots(2, 1, figsize=(8, 6.2))

    centre = blocks[positions["centre"]]
    origin = first_rise_us(centre) - 2_000
    window = [s for s in centre if 0 <= s.time_us - origin <= 52_000]
    overview.plot([(s.time_us - origin) / 1000 for s in window], [volts(s) for s in window],
                  color=colours["centre"], lw=1.2)
    overview.set(xlabel="time (ms)", ylabel="signal at receiver (V)", xlim=(0, 52), ylim=(-0.2, 4))
    overview.set_title("Receiver CH1, steering centred", loc="left", fontsize=10)

    for name, block in positions.items():
        samples = blocks[block]
        rise = first_rise_us(samples)
        near = [s for s in samples if -400 <= s.time_us - rise <= 2_700]
        x = [s.time_us - rise for s in near]
        y = [volts(s) for s in near]
        pulses.step(x, y, where="post", color=colours[name], lw=1.3, label=name)
        pulses.plot(x, y, "o", ms=2.2, color=colours[name])
    pulses.set(xlabel="time from rising edge (µs)", ylabel="signal at receiver (V)",
               xlim=(-400, 2_700), ylim=(-0.2, 4))
    pulses.set_title("One pulse per steering position (dots are ADC samples)", loc="left", fontsize=10)
    pulses.legend(frameon=False, loc="upper right")

    for axes in (overview, pulses):
        axes.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)



#  command line
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m analysis.receiver_signal", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="probe monitor log -> CSV of every dump")
    extract.add_argument("log", type=Path)
    extract.add_argument("csv", type=Path, nargs="?", default=DEFAULT_CSV)
    draw = commands.add_parser("plot", help="CSV of dumps -> figure")
    draw.add_argument("csv", type=Path, nargs="?", default=DEFAULT_CSV)
    draw.add_argument("figure", type=Path, nargs="?", default=DEFAULT_FIGURE)
    args = parser.parse_args(argv)

    if args.command == "extract":
        samples, warnings = extract_dumps(args.log.read_text(errors="replace"))
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        write_csv(samples, args.csv)
        print(f"{args.csv}: {len(samples)} samples in {len(split_blocks(samples))} blocks")
    else:
        plot(split_blocks(read_csv(args.csv)), args.figure)
        print(f"{args.figure} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
