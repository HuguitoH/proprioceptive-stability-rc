"""Build the plan: python -m planning [planning/project.yaml] [output_dir]

Loads the tasks, schedules them, checks the plan against its own rules and
writes the LaTeX fragments that main.tex includes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import render_latex as tex
from .loader import load
from .model import PlanError, Project
from .scheduler import critical_ids, level

PROPOSAL_TARGETS = {"M0": "Oct 2026", "M2": "O1: Nov 2026", "M3": "O2: Dec 2026",
                    "M4": "Poster: Jan 2027", "M5": "O4: Feb 2027", "M6": "O3: Mar 2027",
                    "M8": "May 2027"}


def check(project: Project) -> None:
    s = tex.summary(project)
    if s["expected"] > s["plannable"]:
        raise PlanError(f"expected effort {s['expected']:.0f} h exceeds the plannable {s['plannable']:.0f} h")
    if s["largest"] > s["five_percent"]:
        raise PlanError(f"a task of {s['largest']:.1f} h exceeds 5 % of the effort ({s['five_percent']:.1f} h)")


def build(project_file: Path, out: Path) -> Project:
    project = load(project_file)
    check(project)
    load_by_week = level(project)
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
    print(f"capacity {s['capacity']:.0f} h | plannable {s['plannable']:.0f} h | "
          f"expected {s['expected']:.0f} h (sigma {s['sigma']:.1f}, P95 {s['p95']:.0f}) | "
          f"secondary {s['secondary']:.0f} h")
    print("weekly load:", " ".join(f"{load_by_week[w]:.1f}" for w in sorted(load_by_week)))
    print("critical:", " -> ".join(t.id for t in project.tasks if t.id in crit))
    return project


def main() -> int:
    project_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("project.yaml")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("generated")
    try:
        build(project_file, out)
    except PlanError as err:
        print(f"plan error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
