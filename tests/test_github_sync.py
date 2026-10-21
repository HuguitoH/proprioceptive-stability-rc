"""Tests for the GitHub sync: what it wants on GitHub and which commands it runs.
No test touches the network: the GitHub client is the only part with side effects."""
from pathlib import Path

import pytest

from datetime import date

from planning.github_sync import (Existing, ProjectBoard, Schedule, desired_state, issue_title,
                                  milestone_title, next_milestone, plan_commands,
                                  plan_field_commands, repo_slug, schedules)
from planning.loader import load
from planning.model import PlanError
from planning.scheduler import level

PROJECT_FILE = Path(__file__).resolve().parents[1] / "planning" / "project.yaml"
REPO = "owner/repo"


@pytest.fixture(scope="module")
def project():
    p = load(PROJECT_FILE)
    level(p)
    return p


@pytest.fixture(scope="module")
def state(project):
    return desired_state(project)


def test_one_issue_per_task_and_ongoing_task(project, state):
    expected = len(project.ongoing) + sum(not t.is_milestone for t in project.tasks)
    assert len(state.issues) == expected


def test_one_milestone_per_plan_milestone(project, state):
    assert [m.title for m in state.milestones] == \
        [milestone_title(t) for t in project.tasks if t.is_milestone]


def test_issue_titles_are_unique(state):
    titles = [i.title for i in state.issues]
    assert len(titles) == len(set(titles))


def test_every_issue_label_and_milestone_exists(state):
    labels = {lb.name for lb in state.labels}
    milestones = {m.title for m in state.milestones}
    for issue in state.issues:
        assert set(issue.labels) <= labels
        assert issue.milestone is None or issue.milestone in milestones


def test_issue_belongs_to_the_milestone_it_leads_to(project):
    assert next_milestone(project, project.task("2.5")).id == "M1"
    assert next_milestone(project, project.task("4.1")).id == "M3"


def test_issue_body_traces_back_to_the_proposal(project, state):
    body = next(i.body for i in state.issues if i.title == issue_title(project.task("3.2")))
    assert "O1" in body and "Sensor validation" in body
    assert "Done when" in body


def test_secondary_tasks_are_labelled(project, state):
    issue = next(i for i in state.issues if i.title == issue_title(project.task("10.1")))
    assert "secondary" in issue.labels


def test_nothing_is_created_twice(state):
    everything = Existing(frozenset(lb.name for lb in state.labels),
                          frozenset(m.title for m in state.milestones),
                          frozenset(i.title for i in state.issues))
    assert plan_commands(state, everything, REPO) == []


def test_labels_and_milestones_are_created_before_issues(state):
    kinds = [cmd.argv[1] for cmd in plan_commands(state, Existing(), REPO)]
    first_issue = kinds.index("issue")
    assert "label" not in kinds[first_issue:] and "api" not in kinds[first_issue:]


def test_repo_slug_from_url():
    assert repo_slug("https://github.com/HuguitoH/proprioceptive-stability-rc/") == \
        "HuguitoH/proprioceptive-stability-rc"


def test_detailed_task_has_what_and_done_when(project, state):
    body = next(i.body for i in state.issues if i.title == issue_title(project.task("2.5")))
    assert "### What" in body and "100 Hz" in body
    assert "- [ ] One run logged to microSD" in body


def test_undetailed_task_says_it_is_detailed_later(project, state):
    body = next(i.body for i in state.issues if i.title == issue_title(project.task("7.4")))
    assert "rolling-wave" in body


def test_only_placeholder_bodies_are_refreshed(project, state):
    issue = next(i for i in state.issues if i.title == issue_title(project.task("2.5")))
    titles = frozenset(i.title for i in state.issues)
    names = frozenset(lb.name for lb in state.labels)
    milestones = frozenset(m.title for m in state.milestones)
    untouched = Existing(names, milestones, titles,
                         {issue.title: (7, "old body\n- [ ] _Defined when this task is detailed._")})
    edited_by_hand = Existing(names, milestones, titles)
    assert [c.argv for c in plan_commands(state, untouched, REPO)] == \
        [("gh", "issue", "edit", "7", "--repo", REPO, "--body", issue.body)]
    assert plan_commands(state, edited_by_hand, REPO) == []


def test_details_for_an_unknown_task_are_rejected(tmp_path):
    text = PROJECT_FILE.read_text().replace('details:\n  "1.1":', 'details:\n  "99.9":', 1)
    bad = tmp_path / "project.yaml"
    bad.write_text(text)
    with pytest.raises(PlanError):
        load(bad)


# --------------------------------------------------------------------------- project fields
FIELD_IDS = {"start": "F_start", "target": "F_target", "estimate": "F_est"}


def test_schedule_matches_the_plan(project):
    sched = schedules(project)[issue_title(project.task("2.5"))]
    assert sched == Schedule(date(2026, 10, 19), date(2026, 11, 15), 14.3)


def test_every_issue_has_a_schedule(project, state):
    assert set(schedules(project)) == {i.title for i in state.issues}


def test_fields_are_set_when_empty():
    wanted = {"2.5 X": Schedule(date(2026, 10, 19), date(2026, 11, 15), 14.3)}
    board = ProjectBoard("P1", FIELD_IDS, {"2.5 X": ("I9", {})})
    argvs = [c.argv for c in plan_field_commands(wanted, board)]
    assert [a[-2:] for a in argvs] == [("--date", "2026-10-19"), ("--date", "2026-11-15"),
                                       ("--number", "14.3")]
    assert all(a[a.index("--id") + 1] == "I9" and a[a.index("--project-id") + 1] == "P1" for a in argvs)


def test_fields_already_matching_are_left_alone():
    wanted = {"2.5 X": Schedule(date(2026, 10, 19), date(2026, 11, 15), 14.3)}
    current = {"start": "2026-10-19", "target": "2026-11-15T00:00:00Z", "estimate": 14.3}
    board = ProjectBoard("P1", FIELD_IDS, {"2.5 X": ("I9", current)})
    assert plan_field_commands(wanted, board) == []


def test_issues_not_on_the_board_are_skipped():
    wanted = {"2.5 X": Schedule(date(2026, 10, 19), date(2026, 11, 15), 14.3)}
    assert plan_field_commands(wanted, ProjectBoard("P1", FIELD_IDS, {})) == []
