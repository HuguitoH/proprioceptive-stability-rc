"""Critical path method with weekly resource levelling.

1. A backward pass gives every task its latest start (its priority).
2. Tasks are placed one by one, least flexible first, in the earliest week
   where their weekly hours fit the planning capacity. One person cannot run
   five tasks in parallel at full rate, so this step is what makes the dates real.
3. A second backward pass on the levelled dates gives the slack.
"""
from __future__ import annotations

from .model import Config, PlanError, Project, Task


def ongoing_rate(project: Project) -> float:
    """Hours per week taken by the ongoing (level-of-effort) tasks."""
    return sum(t.effort for t in project.ongoing) / project.config.weeks


def week_capacity(project: Project, week: int) -> float:
    """Hours available for network tasks in a 1-based week."""
    c = project.config
    factor = 0.5 if week in c.christmas_weeks else 1.0
    return factor * (c.hours_per_week * c.weekly_loading - ongoing_rate(project))


def total_capacity(config: Config) -> float:
    half = len(config.christmas_weeks)
    return (config.weeks - half) * config.hours_per_week + half * config.hours_per_week / 2


def topological_order(tasks: list[Task]) -> list[Task]:
    by_id = {t.id: t for t in tasks}
    seen: set[str] = set()
    order: list[Task] = []

    def visit(t: Task, path: tuple[str, ...]) -> None:
        if t.id in path:
            raise PlanError(f"dependency cycle through {t.id}")
        if t.id in seen:
            return
        for p in t.after:
            visit(by_id[p], path + (t.id,))
        seen.add(t.id)
        order.append(t)

    for t in tasks:
        visit(t, ())
    return order


def backward_pass(project: Project) -> None:
    tasks = project.tasks
    succs: dict[str, list[Task]] = {t.id: [] for t in tasks}
    for t in tasks:
        for p in t.after:
            succs[p].append(t)
    for t in reversed(topological_order(tasks)):
        limits = [s.ls for s in succs[t.id]]
        if t.fixed_week is not None:
            limits.append(t.fixed_week)
        if not limits:                                   # open end: bounded by the submission
            limits.append(project.config.submission_week)
        t.lf = min(limits)
        t.ls = t.lf - t.weeks


def _place(project: Project, priority: dict[str, int]) -> tuple[dict[int, float], int]:
    """One serial pass: place ready tasks in priority order at the earliest week
    where their weekly hours fit. Returns the load and how many weeks the fixed
    milestones are missed by (0 means feasible)."""
    by_id = {t.id: t for t in project.tasks}
    load: dict[int, float] = {}
    placed: set[str] = set()
    lateness = 0
    while len(placed) < len(project.tasks):
        ready = [t for t in project.tasks
                 if t.id not in placed and all(p in placed for p in t.after)]
        t = min(ready, key=lambda x: (priority[x.id], x.id))
        start = max([by_id[p].ef for p in t.after] + [t.not_before])
        if t.fixed_week is not None:
            lateness = max(lateness, start - t.fixed_week)
            start = max(start, t.fixed_week)
        elif not t.is_milestone and t.baseline:
            rate = t.effort / t.weeks
            while not all(load.get(w, 0.0) + rate <= week_capacity(project, w) + 1e-9
                          for w in range(start + 1, start + t.weeks + 1)):
                start += 1
            for w in range(start + 1, start + t.weeks + 1):
                load[w] = load.get(w, 0.0) + rate
        t.es, t.ef = start, start + t.weeks
        placed.add(t.id)
    overrun = max(t.ef for t in project.tasks) - project.config.weeks
    return load, max(lateness, overrun, 0)


def level(project: Project, strict: bool = True, iterations: int = 25) -> dict[int, float]:
    """Levelled schedule with iterative priority repair.

    The first pass uses the latest starts of the unlevelled network as priorities.
    If a fixed milestone is missed, the backward pass on the levelled dates gives
    negative slack to the tasks that caused it, and their new latest starts move
    them forward in the next pass. With strict=False the best attempt is kept even
    if it is infeasible, to see by how much it overruns."""
    c = project.config
    backward_pass(project)
    priority = {t.id: t.ls for t in project.tasks}
    best: tuple[int, dict[int, float], dict[str, tuple[int, int]]] | None = None
    for _ in range(iterations):
        load, late = _place(project, priority)
        if best is None or late < best[0]:
            best = (late, load, {t.id: (t.es, t.ef) for t in project.tasks})
        if late == 0:
            break
        backward_pass(project)
        priority = {t.id: min(priority[t.id], t.ls) for t in project.tasks}

    late, load, dates = best
    for t in project.tasks:
        t.es, t.ef = dates[t.id]
    if late and strict:
        raise PlanError(f"the plan misses its fixed dates by {late} week(s)")
    backward_pass(project)                               # slack on the levelled dates
    if strict:
        negative = [t.id for t in project.tasks if t.slack < 0]
        if negative:
            raise PlanError(f"negative slack in {negative}")
    return {w: load.get(w, 0.0) for w in range(1, c.weeks + 1)}


def critical_ids(project: Project) -> set[str]:
    """Two segments: zero slack into the fixed poster date, and the least-slack
    chain after it into the submission."""
    c = project.config
    base = [t for t in project.tasks if t.baseline]
    before = {t.id for t in base
              if t.ef <= c.poster_week and t.slack == 0
              and not (t.fixed_week is not None and not t.after)}  # a bare fixed date drives nothing
    after = [t for t in base if t.ef > c.poster_week and t.fixed_week is None]
    least = min(t.slack for t in after)
    return before | {t.id for t in after if t.slack == least} | {
        t.id for t in base if t.fixed_week == c.submission_week}
