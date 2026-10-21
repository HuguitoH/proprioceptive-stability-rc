"""Maps week indices to calendar dates. Week 1 starts on config.start (a Monday)."""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta

from .model import Config, Task


def monday(config: Config, week_index: int) -> date:
    """Monday of the week that starts at 0-based index `week_index`."""
    return config.start + timedelta(weeks=week_index)


def week_of(config: Config, day: date) -> int:
    """1-based planning week that contains `day`."""
    return (day - config.start).days // 7 + 1


def fmt(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def start_date(config: Config, task: Task) -> date:
    return monday(config, task.es)


def finish_date(config: Config, task: Task) -> date:
    if task.is_milestone:
        return monday(config, task.ef - 1) + timedelta(days=task.weekday)
    return monday(config, task.ef) - timedelta(days=1)          # Sunday of the last week


def month_spans(config: Config) -> list[tuple[str, int]]:
    """Number of planning weeks whose Monday falls in each month, in order."""
    spans: OrderedDict[str, int] = OrderedDict()
    for w in range(config.weeks):
        key = monday(config, w).strftime("%b %Y")
        spans[key] = spans.get(key, 0) + 1
    return [(k.split()[0], n) for k, n in spans.items()]


def year_spans(config: Config) -> list[tuple[str, int]]:
    spans: OrderedDict[str, int] = OrderedDict()
    for w in range(config.weeks):
        y = str(monday(config, w).year)
        spans[y] = spans.get(y, 0) + 1
    return list(spans.items())
