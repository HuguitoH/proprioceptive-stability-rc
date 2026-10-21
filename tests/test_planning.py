"""Tests for the planner: the estimate maths, the scheduler's guarantees and the
rules the plan promises to keep."""
from pathlib import Path

import pytest

from planning.loader import load
from planning.model import Config, Estimate, PlanError, Project, Task
from planning.render_latex import summary
from planning.scheduler import critical_ids, level, topological_order, week_capacity

PROJECT_FILE = Path(__file__).resolve().parents[1] / "planning" / "project.yaml"


@pytest.fixture
def project() -> Project:
    p = load(PROJECT_FILE)
    level(p)
    return p


# --------------------------------------------------------------------------- PERT
def test_pert_expected_weights_most_likely_four_times():
    assert Estimate(2, 5, 14).expected == pytest.approx((2 + 4 * 5 + 14) / 6)


def test_pert_sigma_is_a_sixth_of_the_range():
    assert Estimate(2, 5, 14).sigma == pytest.approx(2.0)


def test_estimate_rejects_unordered_values():
    with pytest.raises(PlanError):
        Estimate(5, 3, 8)


# --------------------------------------------------------------------------- scheduler
def _tiny(weeks: int = 6) -> Project:
    from datetime import date
    config = Config(module_start=date(2026, 9, 23), start=date(2026, 10, 19), weeks=weeks,
                    hours_per_week=10, christmas_weeks=(), contingency=0.2, weekly_loading=1.0,
                    poster_week=weeks, submission_week=weeks, repository="", class_days=())
    tasks = [Task("1.1", "a", "a", Estimate(8, 8, 8), 1),
             Task("1.2", "b", "b", Estimate(8, 8, 8), 1),
             Task("M8", "end", "end", None, 0, ["1.1", "1.2"], fixed_week=weeks)]
    return Project(config, {"1": "x"}, [], tasks, [], {})


def test_tasks_that_do_not_fit_together_are_spread_over_weeks():
    p = _tiny()
    load_by_week = level(p)
    assert {p.task("1.1").es, p.task("1.2").es} == {0, 1}      # 8 h + 8 h > 10 h a week
    assert max(load_by_week.values()) <= 10


def test_missed_fixed_date_is_reported():
    p = _tiny(weeks=1)
    with pytest.raises(PlanError):
        level(p)


def test_cycle_is_detected():
    a = Task("1.1", "a", "a", Estimate(1, 1, 1), 1, ["1.2"])
    b = Task("1.2", "b", "b", Estimate(1, 1, 1), 1, ["1.1"])
    with pytest.raises(PlanError):
        topological_order([a, b])


# --------------------------------------------------------------------------- the real plan
def test_dependencies_are_respected(project):
    by_id = {t.id: t for t in project.tasks}
    for t in project.tasks:
        for p in t.after:
            assert by_id[p].ef <= t.es, f"{t.id} starts before {p} finishes"


def test_no_week_exceeds_its_capacity(project):
    load_by_week = level(project)
    for week, hours in load_by_week.items():
        assert hours <= week_capacity(project, week) + 1e-6


def test_fixed_milestones_hold(project):
    for t in project.tasks:
        if t.fixed_week is not None:
            assert t.ef == t.fixed_week


def test_expected_effort_keeps_the_contingency(project):
    s = summary(project)
    assert s["expected"] <= s["plannable"]


def test_no_task_exceeds_five_percent_of_the_effort(project):
    s = summary(project)
    assert s["largest"] <= s["five_percent"]


def test_secondary_objectives_are_not_critical(project):
    crit = critical_ids(project)
    assert not any(t.secondary for t in project.tasks if t.id in crit)
