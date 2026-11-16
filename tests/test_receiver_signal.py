import pytest

from analysis.receiver_signal import (Sample, extract_dumps, pulse_widths, read_csv,
                                    split_blocks, steering_positions, write_csv)

FAKE_LOG = """\
--- Logging an output to logs/x.log
samples=10, step=89 us, max=2200 mV
BEGIN
time_us,mV
1000,0
1089,2200
11.89,oops
1178,2201
END
samples=10, step=89 us, max=2200 mV
BEGIN
time_us,mV
5000,0
END
"""


def pulse_train(block: int, width_us: int) -> list[Sample]:
    """Two complete pulses of the given width, 16 ms apart."""
    edges = [(0, 0), (100, 2200), (100 + width_us, 0), (16_100, 2200), (16_100 + width_us, 0)]
    return [Sample(block, t, mv) for t, mv in edges]


#  extract_dumps
def test_extracts_every_block_and_reports_broken_lines():
    samples, warnings = extract_dumps(FAKE_LOG)

    assert [sample.block for sample in samples] == [0, 0, 0, 1]
    assert [(sample.time_us, sample.mv_pin) for sample in samples] == [
        (1000, 0),
        (1089, 2200),
        (1178, 2201),
        (5000, 0),
    ]
    assert len(warnings) == 1
    assert "11.89,oops" in warnings[0]


def test_wrong_number_of_fields_is_reported():
    _, warnings = extract_dumps("BEGIN\n1000,0,7\n2000\nEND\n")
    assert len(warnings) == 2


def test_unclosed_block_at_the_end_is_kept_and_reported():
    samples, warnings = extract_dumps("BEGIN\ntime_us,mV\n1000,0\n1089,2200\n")
    assert [(s.time_us, s.mv_pin) for s in samples] == [(1000, 0), (1089, 2200)]
    assert len(warnings) == 1 and "no END" in warnings[0]


def test_begin_inside_a_block_closes_it_with_a_warning():
    samples, warnings = extract_dumps("BEGIN\n1000,0\nBEGIN\n2000,5\nEND\n")
    assert [s.block for s in samples] == [0, 1]
    assert len(warnings) == 1 and "block 0 has no END" in warnings[0]


def test_lines_outside_blocks_are_ignored():
    samples, warnings = extract_dumps("samples=10\n1000,0\nEND\n")
    assert samples == [] and warnings == []



#  pulse_widths
def test_pulse_widths_of_complete_pulses():
    samples = [Sample(0, t, mv) for t, mv in
            [(100, 0), (200, 2200), (300, 2200), (400, 0), (500, 0), (600, 2200), (750, 0)]]
    assert pulse_widths(samples) == [200, 150]


def test_pulse_already_high_at_the_start_is_ignored():
    samples = [Sample(0, t, mv) for t, mv in [(100, 2200), (200, 0), (300, 0), (400, 2200), (500, 0)]]
    assert pulse_widths(samples) == [100]


def test_pulse_still_high_at_the_end_is_ignored():
    samples = [Sample(0, t, mv) for t, mv in [(100, 0), (200, 2200), (300, 0), (400, 2200)]]
    assert pulse_widths(samples) == [100]



#  blocks and files
def test_blocks_are_labelled_by_their_pulse_width():
    blocks = split_blocks(pulse_train(0, 1500) + pulse_train(1, 1000) + pulse_train(2, 2000))
    assert steering_positions(blocks) == {"left": 1, "centre": 0, "right": 2}


def test_fewer_than_three_positions_is_an_error():
    with pytest.raises(ValueError):
        steering_positions(split_blocks(pulse_train(0, 1500)))


def test_csv_round_trip_keeps_the_values(tmp_path):
    samples = pulse_train(0, 1500) + pulse_train(1, 1000)
    path = tmp_path / "dumps.csv"
    write_csv(samples, path)
    assert read_csv(path) == samples
