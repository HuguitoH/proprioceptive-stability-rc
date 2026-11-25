"""Reads project.yaml into the domain model and checks that it is well formed."""
from __future__ import annotations

from pathlib import Path

import yaml

from .calendar import week_of
from .model import Config, Detail, Estimate, Feature, PlanError, Project, Risk, Status, Task


TASK_KEYS = {"id", "name", "short", "est", "weeks", "after", "secondary",
             "fixed_week", "weekday", "not_before", "evidence"}


def _task(raw: dict) -> Task:
    # An unquoted comma inside a YAML flow mapping silently splits a value into a
    # new key, so unknown keys are treated as an error rather than ignored.
    unknown = set(raw) - TASK_KEYS
    if unknown:
        raise PlanError(f"task {raw.get('id')}: unknown keys {sorted(map(str, unknown))} "
                        f"(quote values that contain commas)")
    est = raw.get("est")
    return Task(
        id=str(raw["id"]),
        name=raw["name"],
        short=raw.get("short", raw["name"]),
        estimate=Estimate(*est) if est else None,
        weeks=raw.get("weeks", 0),
        after=[str(a) for a in raw.get("after", [])],
        secondary=raw.get("secondary", False),
        fixed_week=raw.get("fixed_week"),
        weekday=raw.get("weekday", 4),
        not_before=raw.get("not_before", 0),
        evidence=raw.get("evidence", ""),
    )


def load(path: Path, status: Path | None = None) -> Project:
    """Read the plan. With a status file, finished work stays where it happened
    and the rest is scheduled from the status week (replanning). Without one,
    the plan is built from week 1 (the baseline)."""
    data = yaml.safe_load(path.read_text())
    c = data["config"]
    config = Config(
        module_start=c["module_start"],
        start=c["start"],
        weeks=c["weeks"],
        hours_per_week=c["hours_per_week"],
        christmas_weeks=tuple(c["christmas_weeks"]),
        contingency=c["contingency"],
        weekly_loading=c["weekly_loading"],
        poster_week=c["poster_week"],
        submission_week=c["submission_week"],
        repository=c["repository"],
        class_days=tuple(c["class_days"]),
        capacity={int(w): float(h) for w, h in c.get("capacity", {}).items()},
    )
    project = Project(
        config=config,
        work_packages={str(k): v for k, v in data["work_packages"].items()},
        ongoing=[_task(t) for t in data["ongoing"]],
        tasks=[_task(t) for t in data["tasks"]],
        risks=[Risk(**r) for r in data["risks"]],
        network=data["network"],
        scope=[Feature(**f) for f in data.get("scope", [])],
        traceability={str(k): v for k, v in data.get("traceability", {}).items()},
    )
    _attach_details(project, data.get("details", {}))
    if status is not None:
        apply_status(project, read_status(status))
    validate(project)
    return project


def read_status(path: Path) -> Status:
    data = yaml.safe_load(path.read_text())
    return Status(
        as_of=data["as_of"],
        done={str(k): int(v) for k, v in (data.get("done") or {}).items()},
        remaining={str(k): float(v) for k, v in (data.get("remaining") or {}).items()},
    )


def apply_status(project: Project, status: Status) -> None:
    tasks = {t.id: t for t in project.tasks}
    unknown = sorted((set(status.done) | set(status.remaining)) - set(tasks))
    if unknown:
        raise PlanError(f"status mentions unknown tasks {unknown}")
    project.status_week = week_of(project.config, status.as_of)
    for task_id, week in status.done.items():
        if week > project.status_week:
            raise PlanError(f"{task_id} finished in week {week}, after the status week {project.status_week}")
        tasks[task_id].done_week = week
    for task_id, hours in status.remaining.items():
        if task_id in status.done:
            raise PlanError(f"{task_id} is done, so it cannot have hours remaining")
        if hours <= 0:
            raise PlanError(f"{task_id}: remaining hours must be positive (close the issue instead)")
        if tasks[task_id].is_milestone:
            raise PlanError(f"{task_id} is a milestone and has no hours")
        tasks[task_id].remaining = hours


def _attach_details(project: Project, details: dict) -> None:
    tasks = {t.id: t for t in project.ongoing + project.tasks}
    for task_id, raw in details.items():
        task = tasks.get(str(task_id))
        if task is None:
            raise PlanError(f"details given for unknown task {task_id}")
        if set(raw) - {"what", "done_when"}:
            raise PlanError(f"details of {task_id}: only 'what' and 'done_when' are allowed")
        task.detail = Detail(raw["what"].strip(), tuple(raw.get("done_when", [])))


def validate(project: Project) -> None:
    ids = [t.id for t in project.tasks]
    if len(ids) != len(set(ids)):
        raise PlanError("duplicate task ids")
    known = set(ids)
    for t in project.tasks:
        missing = [a for a in t.after if a not in known]
        if missing:
            raise PlanError(f"{t.id} depends on unknown tasks {missing}")
        if t.is_milestone != (t.estimate is None):
            raise PlanError(f"{t.id}: milestones have no estimate and tasks need one")
