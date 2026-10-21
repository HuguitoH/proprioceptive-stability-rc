"""Turns the plan into GitHub labels, milestones and issues.

    uv run python -m planning.github_sync                 # dry run: print what would change
    uv run python -m planning.github_sync --apply         # create what is missing

project.yaml stays the single source of truth. The sync creates what is missing,
matched by title, and never closes anything. The only edit it makes is filling in
the body of an issue that still shows a placeholder, once its task is detailed in
the plan, so running it again is safe and nothing written on GitHub is lost.

The work is split in three steps so the logic can be tested without GitHub:
  desired_state()  plan    -> what GitHub should contain     (pure)
  plan_commands()  desired -> gh commands for what is missing (pure)
  GhClient         runs the commands with the GitHub CLI      (side effects)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .calendar import finish_date, fmt, start_date
from .loader import load
from .model import Project, Task
from .scheduler import level

# One colour per phase, the same as in the Gantt chart of Appendix D.
WP_COLOUR = {"1": "8A8F98", "2": "4E79A7", "3": "59A14F", "4": "59A14F", "5": "59A14F",
             "6": "E15759", "7": "E15759", "8": "8C6D9E", "9": "8C6D9E", "10": "B07AA1"}
SECONDARY_LABEL = "secondary"
ONGOING_LABEL = "ongoing"
# Text that marks a body nobody has edited by hand yet.
PLACEHOLDER_MARKERS = ("_Defined when this task is detailed._",
                       "_Define the outcome that closes this issue before starting it._")
ROLLING_WAVE_NOTE = ("_Not detailed yet. Following the rolling-wave approach of Appendix D, this task is "
                     "detailed when its phase is replanned after the poster presentation._")


@dataclass(frozen=True)
class Label:
    name: str
    colour: str
    description: str


@dataclass(frozen=True)
class Milestone:
    title: str
    due: date
    description: str


@dataclass(frozen=True)
class Issue:
    title: str
    body: str
    labels: tuple[str, ...]
    milestone: str | None


@dataclass
class State:
    labels: list[Label] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass(frozen=True)
class Existing:
    """What is already on GitHub, matched by title.

    `placeholders` maps the title of each issue whose body still has a
    placeholder (never detailed by hand) to its body and number. Only those
    bodies may be refreshed, so nothing written on GitHub is ever lost.
    """

    labels: frozenset[str] = frozenset()
    milestones: frozenset[str] = frozenset()
    issues: frozenset[str] = frozenset()
    placeholders: dict[str, tuple[int, str]] = field(default_factory=dict)


# --------------------------------------------------------------------------- desired state
def wp_label(project: Project, wp: str) -> str:
    return f"WP{wp} {project.work_packages[wp].replace('--', '-')}"


def milestone_title(task: Task) -> str:
    return f"{task.id} {task.name}"


def issue_title(task: Task) -> str:
    return f"{task.id} {task.name}"


def next_milestone(project: Project, task: Task) -> Task | None:
    """First milestone reached by following the dependency network forwards.

    An issue belongs to the milestone it helps to reach, so the milestone's
    progress bar on GitHub shows how close that milestone is.
    """
    successors: dict[str, list[Task]] = {t.id: [] for t in project.tasks}
    for t in project.tasks:
        for p in t.after:
            successors[p].append(t)
    reached: list[Task] = []
    queue, seen = deque(successors[task.id]), set()
    while queue:
        t = queue.popleft()
        if t.id in seen:
            continue
        seen.add(t.id)
        if t.is_milestone:
            reached.append(t)
        else:
            queue.extend(successors[t.id])
    return min(reached, key=lambda m: m.ef, default=None)


def _issue_body(project: Project, task: Task, milestone: Task | None, ongoing: bool) -> str:
    c, e = project.config, task.estimate
    lines = [f"**Work package:** {wp_label(project, task.work_package)}"]
    source = project.traceability.get(task.work_package)
    if source:
        lines.append(f"**Source:** {source}")
    if ongoing:
        lines.append("**Planned:** spread over the whole project")
    else:
        lines.append(f"**Planned:** {fmt(start_date(c, task))} to {fmt(finish_date(c, task))} "
                     f"(week {task.es + 1}, {task.weeks} week{'s' if task.weeks > 1 else ''})")
    lines.append(f"**Estimate (PERT, h):** O {e.optimistic:g} · M {e.likely:g} · P {e.pessimistic:g} "
                 f"→ E {e.expected:.1f}")
    if task.after:
        lines.append(f"**Depends on:** {', '.join(task.after)}")
    if milestone:
        lines.append(f"**Contributes to:** {milestone.id}, {milestone.evidence.rstrip('.')}.")
    if task.secondary:
        lines.append("**Secondary objective:** outside the baseline, started only if reserve hours remain.")
    if task.detail:
        lines += ["", "### What", task.detail.what, "", "### Done when"]
        lines += [f"- [ ] {item}" for item in task.detail.done_when]
    else:
        lines += ["", "### What", ROLLING_WAVE_NOTE, "", "### Done when",
                  "- [ ] _Defined when this task is detailed._"]
    lines += ["", "_Generated from `planning/project.yaml`. Log hours in `log/hours.csv` with task id "
              f"`{task.id}`._"]
    return "\n".join(lines)


def desired_state(project: Project) -> State:
    """What GitHub should contain for this plan. The project must already be levelled."""
    state = State()
    for wp in project.work_packages:
        state.labels.append(Label(wp_label(project, wp), WP_COLOUR.get(wp, "8A8F98"),
                                  project.traceability.get(wp, project.work_packages[wp])[:100]))
    state.labels.append(Label(SECONDARY_LABEL, "B07AA1", "Secondary objective, outside the baseline"))
    state.labels.append(Label(ONGOING_LABEL, "8A8F98", "Spread over the whole project"))

    for t in project.tasks:
        if t.is_milestone:
            state.milestones.append(Milestone(milestone_title(t), finish_date(project.config, t),
                                              t.evidence))
    for t in project.ongoing:
        state.issues.append(Issue(issue_title(t), _issue_body(project, t, None, ongoing=True),
                                  (wp_label(project, t.work_package), ONGOING_LABEL), None))
    for t in project.tasks:
        if t.is_milestone:
            continue
        ms = next_milestone(project, t)
        labels = [wp_label(project, t.work_package)]
        if t.secondary:
            labels.append(SECONDARY_LABEL)
        state.issues.append(Issue(issue_title(t), _issue_body(project, t, ms, ongoing=False),
                                  tuple(labels), milestone_title(ms) if ms else None))
    return state


# --------------------------------------------------------------------------- commands
def plan_commands(desired: State, existing: Existing, repo: str) -> list[list[str]]:
    """gh commands that create what is missing, in an order that always works:
    labels and milestones first, because issues refer to them."""
    cmds: list[list[str]] = []
    for lb in desired.labels:
        if lb.name not in existing.labels:
            cmds.append(["gh", "label", "create", lb.name, "--repo", repo,
                         "--color", lb.colour, "--description", lb.description])
    for ms in desired.milestones:
        if ms.title not in existing.milestones:
            cmds.append(["gh", "api", f"repos/{repo}/milestones", "--method", "POST",
                         "-f", f"title={ms.title}", "-f", f"due_on={ms.due.isoformat()}T23:59:59Z",
                         "-f", f"description={ms.description}"])
    for iss in desired.issues:
        stale = existing.placeholders.get(iss.title)
        if stale and stale[1].strip() != iss.body.strip():
            cmds.append(["gh", "issue", "edit", str(stale[0]), "--repo", repo, "--body", iss.body])
            continue
        if iss.title not in existing.issues:
            cmd = ["gh", "issue", "create", "--repo", repo, "--title", iss.title, "--body", iss.body]
            for lb in iss.labels:
                cmd += ["--label", lb]
            if iss.milestone:
                cmd += ["--milestone", iss.milestone]
            cmds.append(cmd)
    return cmds


# --------------------------------------------------------------------------- GitHub
class GhClient:
    """Thin wrapper over the GitHub CLI (`gh`), which handles authentication."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def _json(self, *args: str) -> list[dict]:
        out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
        return json.loads(out or "[]")

    def existing(self) -> Existing:
        labels = self._json("label", "list", "--repo", self.repo, "--limit", "200", "--json", "name")
        milestones = self._json("api", f"repos/{self.repo}/milestones?state=all&per_page=100")
        issues = self._json("issue", "list", "--repo", self.repo, "--state", "all",
                            "--limit", "500", "--json", "title,number,body")
        placeholders = {x["title"]: (x["number"], x["body"]) for x in issues
                        if any(m in x["body"] for m in PLACEHOLDER_MARKERS)}
        return Existing(frozenset(x["name"] for x in labels),
                        frozenset(x["title"] for x in milestones),
                        frozenset(x["title"] for x in issues),
                        placeholders)

    @staticmethod
    def run(cmd: list[str]) -> None:
        subprocess.run(cmd, check=True, capture_output=True, text=True)


def repo_slug(url: str) -> str:
    """owner/name from https://github.com/owner/name."""
    return "/".join(url.rstrip("/").split("/")[-2:])


def _describe(cmd: list[str]) -> str:
    kind = " ".join(cmd[1:3])
    if cmd[1] == "api":
        return f"milestone  {next(a[6:] for a in cmd if a.startswith('title='))}"
    if kind == "label create":
        return f"label      {cmd[3]}"
    if kind == "issue edit":
        return f"detail     issue #{cmd[3]}"
    return f"issue      {cmd[cmd.index('--title') + 1]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m planning.github_sync", description=__doc__.split("\n")[0])
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("project.yaml"))
    parser.add_argument("--apply", action="store_true", help="create the missing items (default: dry run)")
    args = parser.parse_args(argv)

    project = load(args.plan)
    level(project)
    repo = repo_slug(project.config.repository)
    client = GhClient(repo)
    commands = plan_commands(desired_state(project), client.existing(), repo)

    if not commands:
        print(f"{repo} is already in sync with the plan.")
        return 0
    for cmd in commands:
        print(("creating   " if args.apply else "would add  ") + _describe(cmd))
        if args.apply:
            client.run(cmd)
    if not args.apply:
        print(f"\n{len(commands)} items missing. Run again with --apply to create them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
