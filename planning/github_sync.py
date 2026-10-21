"""Turns the plan into GitHub labels, milestones and issues.

    uv run python -m planning.github_sync                 # dry run: print what would change
    uv run python -m planning.github_sync --apply         # create what is missing
    uv run python -m planning.github_sync --project 1     # also fill Start/Target/Estimate

project.yaml stays the single source of truth. The sync creates what is missing,
matched by title, and never closes anything. It edits only two things: the body
of an issue that still shows a placeholder, once its task is detailed, and the
planned Start, Target and Estimate on the Project, which belong to the plan. To
change a planned date, change project.yaml, not the board. Running it again is
always safe.

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
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .calendar import finish_date, fmt, monday, start_date
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
class Command:
    """A gh invocation plus a one-line summary for the dry run."""

    argv: tuple[str, ...]
    summary: str


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
def plan_commands(desired: State, existing: Existing, repo: str) -> list[Command]:
    """gh commands that create what is missing, in an order that always works:
    labels and milestones first, because issues refer to them."""
    cmds: list[Command] = []
    for lb in desired.labels:
        if lb.name not in existing.labels:
            cmds.append(Command(("gh", "label", "create", lb.name, "--repo", repo,
                                 "--color", lb.colour, "--description", lb.description),
                                f"label      {lb.name}"))
    for ms in desired.milestones:
        if ms.title not in existing.milestones:
            cmds.append(Command(("gh", "api", f"repos/{repo}/milestones", "--method", "POST",
                                 "-f", f"title={ms.title}",
                                 "-f", f"due_on={ms.due.isoformat()}T23:59:59Z",
                                 "-f", f"description={ms.description}"),
                                f"milestone  {ms.title}"))
    for iss in desired.issues:
        stale = existing.placeholders.get(iss.title)
        if stale and stale[1].strip() != iss.body.strip():
            cmds.append(Command(("gh", "issue", "edit", str(stale[0]), "--repo", repo,
                                 "--body", iss.body), f"detail     {iss.title}"))
            continue
        if iss.title not in existing.issues:
            argv = ["gh", "issue", "create", "--repo", repo, "--title", iss.title, "--body", iss.body]
            for lb in iss.labels:
                argv += ["--label", lb]
            if iss.milestone:
                argv += ["--milestone", iss.milestone]
            cmds.append(Command(tuple(argv), f"issue      {iss.title}"))
    return cmds


# --------------------------------------------------------------------------- project fields
# The GitHub Project draws its Roadmap from these fields, not from the issue text,
# so the dates and estimates of the plan are copied into them.
FIELD_NAMES = {"start": "Start", "target": "Target", "estimate": "Estimate"}


@dataclass(frozen=True)
class Schedule:
    """Planned values of one issue, in the form the Project fields take."""

    start: date
    target: date
    estimate: float


@dataclass(frozen=True)
class ProjectBoard:
    """A GitHub Project: its id, the ids of the three fields, and its items by issue title."""

    project_id: str
    field_ids: dict[str, str]                    # "start" | "target" | "estimate" -> field id
    items: dict[str, tuple[str, dict]]           # issue title -> (item id, current values)


def schedules(project: Project) -> dict[str, Schedule]:
    """Issue title -> planned start, target and estimate. The project must be levelled."""
    c = project.config
    end = monday(c, c.weeks) - timedelta(days=1)
    out = {issue_title(t): Schedule(c.start, end, round(t.estimate.expected, 1))
           for t in project.ongoing}
    for t in project.tasks:
        if not t.is_milestone:
            out[issue_title(t)] = Schedule(start_date(c, t), finish_date(c, t),
                                           round(t.estimate.expected, 1))
    return out


def plan_field_commands(wanted: dict[str, Schedule], board: ProjectBoard) -> list[Command]:
    """gh commands that set the fields whose value differs from the plan.
    Issues that are not on the board yet are skipped: auto-add puts them there."""
    cmds: list[Command] = []
    for title, sched in wanted.items():
        if title not in board.items:
            continue
        item_id, current = board.items[title]
        for key, flag, value in (("start", "--date", sched.start.isoformat()),
                                 ("target", "--date", sched.target.isoformat()),
                                 ("estimate", "--number", f"{sched.estimate:g}")):
            if _same(current.get(key), value):
                continue
            cmds.append(Command(("gh", "project", "item-edit", "--id", item_id,
                                 "--project-id", board.project_id,
                                 "--field-id", board.field_ids[key], flag, value),
                                f"field      {title}: {FIELD_NAMES[key]} = {value}"))
    return cmds


def _same(current: object, wanted: str) -> bool:
    if current is None:
        return False
    try:
        return abs(float(current) - float(wanted)) < 1e-6
    except (TypeError, ValueError):
        return str(current)[:10] == wanted


# --------------------------------------------------------------------------- GitHub
class GhError(RuntimeError):
    """A gh command failed. Carries GitHub's own message, not just the exit code."""


class GhClient:
    """Thin wrapper over the GitHub CLI (`gh`), which handles authentication."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def _json(self, *args: str):
        result = subprocess.run(["gh", *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise GhError(f"gh {' '.join(args[:3])}\n{result.stderr.strip()}")
        return json.loads(result.stdout or "[]")

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

    # GitHub limits how fast content can be created and recommends at least one
    # second between such requests. Going faster triggers its secondary rate
    # limit and the request is rejected.
    PAUSE_S = 1.5
    RETRY_AFTER_S = 60

    def board(self, number: int) -> ProjectBoard:
        owner = self.repo.split("/")[0]
        projects = self._json("project", "list", "--owner", owner, "--format", "json")
        project = next((p for p in projects.get("projects", []) if p["number"] == number), None)
        if project is None:
            raise GhError(f"project {number} not found for {owner}. "
                          "If it exists, run: gh auth refresh -s project")
        fields = self._json("project", "field-list", str(number), "--owner", owner,
                            "--format", "json", "--limit", "100")
        by_name = {f["name"]: f["id"] for f in fields.get("fields", [])}
        missing = [n for n in FIELD_NAMES.values() if n not in by_name]
        if missing:
            raise GhError(f"the project has no field {', '.join(missing)}. "
                          "Create Start and Target (date) and Estimate (number) first.")
        listed = self._json("project", "item-list", str(number), "--owner", owner,
                            "--format", "json", "--limit", "500")
        items = {}
        for it in listed.get("items", []):
            content = it.get("content") or {}
            if content.get("type") == "Issue":
                items[content["title"]] = (it["id"], {k: it.get(k) for k in FIELD_NAMES})
        return ProjectBoard(project["id"], {k: by_name[v] for k, v in FIELD_NAMES.items()}, items)

    def run(self, cmd: Command) -> None:
        for attempt in (1, 2):
            result = subprocess.run(cmd.argv, capture_output=True, text=True)
            if result.returncode == 0:
                time.sleep(self.PAUSE_S)
                return
            if attempt == 1 and "rate limit" in result.stderr.lower():
                print(f"  rate limited by GitHub, waiting {self.RETRY_AFTER_S} s and retrying")
                time.sleep(self.RETRY_AFTER_S)
                continue
            raise GhError(f"{cmd.summary}\n{result.stderr.strip()}")


def repo_slug(url: str) -> str:
    """owner/name from https://github.com/owner/name."""
    return "/".join(url.rstrip("/").split("/")[-2:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m planning.github_sync", description=__doc__.split("\n")[0])
    parser.add_argument("--plan", type=Path, default=Path(__file__).with_name("project.yaml"))
    parser.add_argument("--project", type=int, metavar="NUMBER",
                        help="also set Start, Target and Estimate on this GitHub Project")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: dry run)")
    args = parser.parse_args(argv)

    project = load(args.plan)
    level(project)
    repo = repo_slug(project.config.repository)
    client = GhClient(repo)
    try:
        commands = plan_commands(desired_state(project), client.existing(), repo)
        if args.project is not None:
            commands += plan_field_commands(schedules(project), client.board(args.project))
    except GhError as err:
        print(f"Could not read GitHub: {err}", file=sys.stderr)
        return 1

    if not commands:
        print(f"{repo} is already in sync with the plan.")
        return 0
    for cmd in commands:
        print(("applying   " if args.apply else "would do   ") + cmd.summary)
        if args.apply:
            try:
                client.run(cmd)
            except GhError as err:
                print(f"\nGitHub refused: {err}\nNothing after this was changed. "
                      "Fix the cause and run again: only what is still missing is done.",
                      file=sys.stderr)
                return 1
    if not args.apply:
        print(f"\n{len(commands)} changes pending. Run again with --apply to make them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
