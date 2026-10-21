"""Domain model of the plan: estimates, tasks, risks and configuration.

The model knows nothing about scheduling or LaTeX. Keeping it plain makes the
scheduler and the renderers easy to test on their own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class PlanError(ValueError):
    """Raised when the plan breaks one of its own rules (capacity, task size, dates)."""


@dataclass(frozen=True)
class Estimate:
    """Three-point (PERT) estimate in hours.

    The expected value weights the most likely case four times, which pulls the
    estimate towards the pessimistic side when the spread is skewed, as it
    usually is for tasks that can go wrong.
    """

    optimistic: float
    likely: float
    pessimistic: float

    def __post_init__(self) -> None:
        if not 0 < self.optimistic <= self.likely <= self.pessimistic:
            raise PlanError(f"estimate must satisfy 0 < O <= M <= P, got {self}")

    @property
    def expected(self) -> float:
        return (self.optimistic + 4 * self.likely + self.pessimistic) / 6

    @property
    def sigma(self) -> float:
        return (self.pessimistic - self.optimistic) / 6


@dataclass
class Task:
    id: str
    name: str
    short: str
    estimate: Estimate | None = None      # None for milestones
    weeks: int = 0                        # 0 means milestone
    after: list[str] = field(default_factory=list)
    secondary: bool = False               # outside the baseline budget
    fixed_week: int | None = None         # milestone tied to a calendar week
    weekday: int = 4                      # milestone date inside its week (0 = Monday)
    not_before: int = 0                   # earliest start week index, for levelling
    evidence: str = ""                    # what proves a milestone is reached
    # Filled in by the scheduler (week indices, 0-based, end-exclusive).
    es: int = 0
    ef: int = 0
    ls: int = 0
    lf: int = 0

    @property
    def is_milestone(self) -> bool:
        return self.weeks == 0

    @property
    def work_package(self) -> str:
        return self.id.split(".")[0]

    @property
    def effort(self) -> float:
        return self.estimate.expected if self.estimate else 0.0

    @property
    def slack(self) -> int:
        return self.ls - self.es

    @property
    def baseline(self) -> bool:
        return not self.secondary


@dataclass(frozen=True)
class Risk:
    risk: str
    type: str
    likelihood: int
    consequence: int
    strategy: str
    mitigation: str
    trigger: str

    @property
    def impact(self) -> int:
        return self.likelihood * self.consequence

    @property
    def rag(self) -> str:
        """Dawson (2015): above 10 is critical, 6 to 10 needs attention, below 6 is monitored."""
        if self.impact > 10:
            return "red"
        if self.impact >= 6:
            return "amber"
        return "green"


@dataclass(frozen=True)
class Config:
    module_start: date
    start: date
    weeks: int
    hours_per_week: float
    christmas_weeks: tuple[int, ...]
    contingency: float
    weekly_loading: float
    poster_week: int
    submission_week: int
    repository: str
    class_days: tuple[date, ...]


@dataclass(frozen=True)
class Feature:
    """A candidate feature placed on the value-effort matrix (scores from 1 to 5)."""

    name: str
    value: float
    effort: float
    decision: str                 # baseline | conditional | gaps | future

    DECISIONS = ("baseline", "conditional", "gaps", "future")

    def __post_init__(self) -> None:
        if self.decision not in self.DECISIONS:
            raise PlanError(f"{self.name}: decision must be one of {self.DECISIONS}")
        if not (0 <= self.value <= 5 and 0 <= self.effort <= 5):
            raise PlanError(f"{self.name}: scores must be between 0 and 5")


@dataclass
class Project:
    config: Config
    work_packages: dict[str, str]
    ongoing: list[Task]
    tasks: list[Task]
    risks: list[Risk]
    network: dict
    scope: list[Feature] = field(default_factory=list)

    def task(self, task_id: str) -> Task:
        return next(t for t in self.tasks if t.id == task_id)
