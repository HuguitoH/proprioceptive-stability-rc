"""Build the plan: python -m planning [planning/project.yaml] [output_dir]
Snapshot progress: python -m planning status [planning/project.yaml]
Draft of a plan that breaks its rules: add --draft to see by how much it overruns.

Loads the tasks, schedules them, checks the plan against its own rules and
writes the LaTeX fragments that main.tex includes. If planning/status.yaml sits
next to the plan, finished work is kept where it happened and the rest is
scheduled from the status date (the revised plan). A copy of the plan with no
status file beside it, such as the one at the baseline-plan tag, rebuilds the
baseline.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from . import render_latex as tex
from .loader import load
from .model import PlanError, Project
from .scheduler import critical_ids, level
from .status import fetch_closed, last_worked, latest_remaining, read_csv, render, snapshot

PROPOSAL_TARGETS = {"M0": "Oct 2026", "M2": "O1: Nov 2026", "M3": "O2: Dec 2026",
                    "M4": "Poster: Jan 2027", "M5": "O4: Feb 2027", "M6": "O3: Mar 2027",
                    "M8": "May 2027"}


def check(project: Project) -> None:
    s = tex.summary(project)
    if s["expected"] > s["plannable"]:
        raise PlanError(f"expected effort {s['expected']:.0f} h exceeds the plannable {s['plannable']:.0f} h")
    if s["largest"] > s["five_percent"]:
        raise PlanError(f"a task of {s['largest']:.1f} h exceeds 5 % of the effort ({s['five_percent']:.1f} h)")


def build(project_file: Path, out: Path, strict: bool = True) -> Project:
    status_file = project_file.with_name("status.yaml")
    project = load(project_file, status_file if status_file.exists() else None)
    if strict:
        check(project)
    load_by_week = level(project, strict=strict)
    crit = critical_ids(project)
    out.mkdir(parents=True, exist_ok=True)
    fragments = {
        "macros.tex": tex.macros(project, crit),
        "effort.tex": tex.effort_table(project),
        "schedule.tex": tex.schedule_table(project, crit),
        "milestones.tex": tex.milestone_table(project, PROPOSAL_TARGETS),
        "risks.tex": tex.risk_table(project),
        "gantt.tex": tex.gantt(project, crit),
        "wbs.tex": tex.wbs(project),
        "network.tex": tex.network(project, crit),
        "load.tex": tex.load_chart(project, load_by_week),
        "scope.tex": tex.scope_matrix(project),
    }
    for name, text in fragments.items():
        (out / name).write_text(text)

    s = tex.summary(project)
    if status_file.exists():
        print(f"revised plan from week {project.status_week} ({status_file})")
    print(f"capacity {s['capacity']:.0f} h | plannable {s['plannable']:.0f} h | "
          f"expected {s['expected']:.0f} h (sigma {s['sigma']:.1f}, P95 {s['p95']:.0f}) | "
          f"secondary {s['secondary']:.0f} h")
    print("weekly load:", " ".join(f"{load_by_week[w]:.1f}" for w in sorted(load_by_week)))
    print("critical:", " -> ".join(t.id for t in project.tasks if t.id in crit))
    return project


def write_status(project_file: Path) -> Path:
    """Snapshot GitHub and the logs into planning/status.yaml."""
    project = load(project_file)
    root = project_file.resolve().parents[1]
    status = snapshot(
        project.config, date.today(),
        closed=fetch_closed(project.config.repository),
        worked=last_worked(read_csv(root / "log" / "hours.csv")),
        remaining=latest_remaining(read_csv(root / "log" / "remaining.csv")),
        known={t.id for t in project.tasks},
    )
    path = project_file.with_name("status.yaml")
    path.write_text(render(status))
    print(f"status as of {status['as_of']}: done {list(status['done'])}, "
          f"remaining {status['remaining']}")
    return path


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        project_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).with_name("project.yaml")
        write_status(project_file)
        return 0
    draft = "--draft" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--draft"]
    project_file = Path(args[0]) if args else Path(__file__).with_name("project.yaml")
    out = Path(args[1]) if len(args) > 1 else Path("generated")
    try:
        build(project_file, out, strict=not draft)
    except PlanError as err:
        print(f"plan error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
