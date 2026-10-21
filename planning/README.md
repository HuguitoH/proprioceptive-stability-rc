# Planning

`project.yaml` is the project plan as data: tasks, PERT estimates, dependencies,
milestones and risks. Everything else is generated from it, so a change of plan
is made here and nowhere else.

| Command | What it does |
|---|---|
| `uv run python -m planning` | Schedules the plan and writes the Appendix D tables and diagrams to `generated/` |
| `uv run python -m planning.github_sync` | Dry run: lists the labels, milestones and issues missing on GitHub |
| `uv run python -m planning.github_sync --apply` | Creates them. Never edits or closes anything, so it is safe to run again |

The sync needs the [GitHub CLI](https://cli.github.com/) logged in (`gh auth login`).

## GitHub Project (set up once, by hand)

1. *Projects → New project → Board*, linked to this repository.
2. Add the fields **Iteration** (2 weeks, starting Monday 19 Oct 2026),
   **Estimate** (number, the PERT expected hours) and **Start** / **Target** (dates).
3. Views: **Board** by Status, **Roadmap** by Start/Target (the live Gantt), and a
   **Table** grouped by label (one group per work package).
4. *Workflows → Auto-add to project*: every new issue in this repository.
