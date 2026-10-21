"""Reads project.yaml into the domain model and checks that it is well formed."""
from __future__ import annotations

from pathlib import Path

import yaml

from .model import Config, Estimate, Feature, PlanError, Project, Risk, Task


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


def load(path: Path) -> Project:
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
    )
    project = Project(
        config=config,
        work_packages={str(k): v for k, v in data["work_packages"].items()},
        ongoing=[_task(t) for t in data["ongoing"]],
        tasks=[_task(t) for t in data["tasks"]],
        risks=[Risk(**r) for r in data["risks"]],
        network=data["network"],
        scope=[Feature(**f) for f in data.get("scope", [])],
    )
    validate(project)
    return project


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
