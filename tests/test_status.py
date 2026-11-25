"""Tests for the progress snapshot: each fact read from its one source."""
from datetime import date

import yaml

from planning.model import Config
from planning.status import last_worked, latest_remaining, render, snapshot, task_id

CONFIG = Config(module_start=date(2026, 9, 23), start=date(2026, 10, 19), weeks=31,
                hours_per_week=14, christmas_weeks=(), contingency=0.2, weekly_loading=0.9,
                poster_week=15, submission_week=31, repository="", class_days=())


def test_task_id_is_read_from_issue_and_milestone_titles():
    assert task_id("2.1 Buy remaining parts") == "2.1"
    assert task_id("10.2 S2 gain adaptation") == "10.2"
    assert task_id("M0 Ethics check confirmed") == "M0"
    assert task_id("Fix typo in README") is None


def test_last_worked_keeps_the_latest_day_per_task():
    rows = [{"date": "2026-11-15", "task_id": "2.1"}, {"date": "2026-11-17", "task_id": "2.1"},
            {"date": "2026-11-03", "task_id": "2.2"}]
    assert last_worked(rows) == {"2.1": date(2026, 11, 17), "2.2": date(2026, 11, 3)}


def test_latest_remaining_estimate_wins():
    rows = [{"date": "2026-11-25", "task_id": "2.3", "remaining_hours": "9"},
            {"date": "2026-11-29", "task_id": "2.3", "remaining_hours": "4"}]
    assert latest_remaining(rows) == {"2.3": 4.0}


def test_done_week_comes_from_hours_and_falls_back_to_the_closing_day():
    status = snapshot(CONFIG, date(2026, 11, 25),
                      closed={"2.1": date(2026, 11, 25), "M0": date(2026, 10, 21)},
                      worked={"2.1": date(2026, 11, 17)}, remaining={}, known={"2.1", "M0"})
    assert status["done"] == {"2.1": 5, "M0": 1}


def test_done_tasks_and_ongoing_tasks_are_left_out_of_remaining():
    status = snapshot(CONFIG, date(2026, 11, 25), closed={"2.1": date(2026, 11, 17)}, worked={},
                      remaining={"2.1": 1, "2.3": 9, "1.2": 3}, known={"2.1", "2.3"})
    assert status["remaining"] == {"2.3": 9}


def test_rendered_status_reads_back_as_yaml():
    status = {"as_of": date(2026, 11, 25), "done": {"2.1": 5}, "remaining": {"2.3": 9.5}}
    data = yaml.safe_load(render(status))
    assert data == {"as_of": date(2026, 11, 25), "done": {"2.1": 5}, "remaining": {"2.3": 9.5}}


def test_empty_status_still_reads_back():
    data = yaml.safe_load(render({"as_of": date(2026, 11, 25), "done": {}, "remaining": {}}))
    assert data["done"] == {} and data["remaining"] == {}
