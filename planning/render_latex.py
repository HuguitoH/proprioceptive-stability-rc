"""Writes the LaTeX fragments that main.tex includes. Presentation only: no
scheduling decisions are taken here."""
from __future__ import annotations

import math
from datetime import timedelta

from . import calendar as cal
from .model import Feature, Project, Task
from .scheduler import ongoing_rate, total_capacity, week_capacity

PHASE_COLOUR = {"1": "phpm", "2": "phbuild", "3": "phvalid", "4": "phvalid", "5": "phvalid",
                "6": "phexp", "7": "phexp", "8": "phwrite", "9": "phwrite", "10": "phsec"}
RAG_COLOUR = {"red": "ragred", "amber": "ragamber", "green": "raggreen"}
HATCH = ("bar/.append style={fill=none, draw=black!40, pattern=north east lines, "
         "pattern color=black!35}")


def _h(x: float) -> str:
    """Hours with one decimal, dropping a trailing .0."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- numbers
def summary(project: Project) -> dict[str, float]:
    c = project.config
    base = [t for t in project.ongoing + project.tasks if t.baseline and t.estimate]
    sec = [t for t in project.tasks if t.secondary and t.estimate]
    e_total = sum(t.effort for t in base)
    m_total = sum(t.estimate.likely for t in base)
    sigma = math.sqrt(sum(t.estimate.sigma ** 2 for t in base))
    cap = total_capacity(c)
    return dict(
        capacity=cap, contingency=cap * c.contingency, plannable=cap * (1 - c.contingency),
        expected=e_total, likely=m_total, sigma=sigma, p95=e_total + 1.645 * sigma,
        secondary=sum(t.effort for t in sec), reserve=cap - e_total,
        largest=max(t.effort for t in base), five_percent=0.05 * e_total,
    )


def macros(project: Project, crit: set[str]) -> str:
    c = project.config
    s = summary(project)
    order = [t for t in project.tasks if t.id in crit]
    m8 = project.task("M8")
    last = max(t.ef for t in project.tasks if t.baseline and not t.is_milestone)
    values = {
        "capTotal": f"{s['capacity']:.0f}", "capContingency": f"{s['contingency']:.0f}",
        "capPlannable": f"{s['plannable']:.0f}", "effortExpected": f"{s['expected']:.0f}",
        "effortLikely": f"{s['likely']:.0f}", "effortSigma": f"{s['sigma']:.0f}",
        "effortPninetyfive": f"{s['p95']:.0f}", "effortSecondary": f"{s['secondary']:.0f}",
        "reserveHours": f"{s['reserve']:.0f}", "reservePct": f"{100 * s['reserve'] / s['capacity']:.0f}",
        "largestTask": _h(s["largest"]), "fivePercent": _h(s["five_percent"]),
        "hoursPerWeek": f"{c.hours_per_week:g}", "loadingPct": f"{100 * c.weekly_loading:.0f}",
        "weekCap": _h(week_capacity(project, 1)), "ongoingPerWeek": _h(ongoing_rate(project)),
        "planWeeks": str(c.weeks), "posterWeek": str(c.poster_week),
        "submissionWeek": str(c.submission_week),
        "submissionDate": cal.finish_date(c, m8).strftime("%A %-d %B %Y"),
        "planStart": c.start.strftime("%A %-d %B %Y"),
        "planEnd": (cal.monday(c, c.weeks) - timedelta(days=1)).strftime("%A %-d %B %Y"),
        "moduleStart": c.module_start.strftime("%A %-d %B %Y"),
        "lastTaskWeek": str(last), "bufferWeeks": str(c.submission_week - last),
        "repoUrl": c.repository,
        "criticalA": r" $\rightarrow$ ".join(t.id for t in order if t.ef <= c.poster_week),
        "criticalB": r" $\rightarrow$ ".join(t.id for t in order if t.ef > c.poster_week),
        "classDays": ", ".join(cal.fmt(d) for d in c.class_days),
    }
    return "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in values.items()) + "\n"


# --------------------------------------------------------------------------- tables
def effort_table(project: Project) -> str:
    rows = []
    every = project.ongoing + project.tasks
    for wp, wp_name in project.work_packages.items():
        members = [t for t in every if t.estimate and t.work_package == wp]
        if not members:
            continue
        sub = sum(t.effort for t in members)
        rows.append(f"\\rowcolor{{black!6}}\\textbf{{{wp}}} & \\textbf{{{wp_name}}} & & & & "
                    f"\\textbf{{{_h(sub)}}} & \\\\")
        for t in members:
            e = t.estimate
            weeks = "ongoing" if t in project.ongoing else str(t.weeks)
            rows.append(f"{t.id} & {t.name} & {_h(e.optimistic)} & {_h(e.likely)} & "
                        f"{_h(e.pessimistic)} & {_h(e.expected)} & {weeks} \\\\")
    return "\n".join(rows) + "\n"


def schedule_table(project: Project, crit: set[str]) -> str:
    c = project.config
    submission = cal.finish_date(c, project.task("M8"))
    rows = []
    for t in project.tasks:
        if t.is_milestone:
            continue
        ident = f"\\textbf{{{t.id}}}" if t.id in crit else t.id
        ident += "$^{\\dagger}$" if t.secondary else ""
        after = ", ".join(t.after) or "--"
        rows.append(f"{ident} & {t.short} & {t.weeks} & {after} & "
                    f"W{t.es + 1} ({cal.fmt(cal.start_date(c, t))}) & "
                    f"W{t.ef} ({cal.fmt(min(cal.finish_date(c, t), submission - timedelta(days=1)))}) "
                    f"& {t.slack} \\\\")
    return "\n".join(rows) + "\n"


def milestone_table(project: Project, targets: dict[str, str]) -> str:
    c = project.config
    rows = []
    for t in project.tasks:
        if t.is_milestone:
            rows.append(f"{t.id} & {t.name} & {t.evidence} & W{t.ef} ({cal.fmt(cal.finish_date(c, t))}) "
                        f"& {t.slack} & {targets.get(t.id, '--')} \\\\")
    return "\n".join(rows) + "\n"


def risk_table(project: Project) -> str:
    rows = []
    ranked = sorted(project.risks, key=lambda r: -r.impact)
    for i, r in enumerate(ranked, 1):
        rows.append(f"R{i} & {r.risk} & {r.type} & {r.likelihood} & {r.consequence} & "
                    f"\\cellcolor{{{RAG_COLOUR[r.rag]}}}{r.impact} & "
                    f"\\textit{{{r.strategy}.}} {r.mitigation} & {r.trigger} \\\\")
    return "\n".join(rows) + "\n"


# --------------------------------------------------------------------------- figures
def gantt(project: Project, crit: set[str]) -> str:
    c = project.config
    lines = [" ".join(f"\\gantttitle{{{y}}}{{{n}}}" for y, n in cal.year_spans(c)) + " \\\\",
             " ".join(f"\\gantttitle{{{m}}}{{{n}}}" for m, n in cal.month_spans(c)) + " \\\\",
             f"\\gantttitlelist{{1,...,{c.weeks}}}{{1}} \\\\"]
    first, *rest = sorted({cal.week_of(c, d) for d in c.class_days if 1 <= cal.week_of(c, d) <= c.weeks})
    line = (f"\\ganttmilestone[milestone/.append style={{fill=headingblue, scale=0.8}}]"
            f"{{Class days (tasks and feedback)}}{{{first}}}")
    for w in rest:
        line += (f" \\ganttmilestone[inline, milestone/.append style={{fill=headingblue, scale=0.8}}]"
                 f"{{}}{{{w}}}")
    lines.append(line + " \\\\")
    lo, hi = min(c.christmas_weeks), max(c.christmas_weeks)
    lines.append(f"\\ganttbar[bar/.append style={{fill=black!12}}, bar label font=\\sffamily\\scriptsize\\itshape]"
                 f"{{Christmas break (half capacity)}}{{{lo}}}{{{hi}}} \\\\[grid]")

    current = None
    for t in project.tasks:
        wp = None if t.is_milestone else t.work_package
        if wp and wp != current:
            current = wp
            members = [x for x in project.tasks if not x.is_milestone and x.work_package == wp]
            lines.append(f"\\ganttgroup{{{wp} {project.work_packages[wp]}}}"
                         f"{{{min(x.es for x in members) + 1}}}{{{max(x.ef for x in members)}}} \\\\")
        if t.is_milestone:
            style = "milestone/.append style={fill=critred}" if t.id in crit else ""
            lines.append(f"\\ganttmilestone[{style}]{{{t.short}}}{{{t.ef}}} \\\\")
            continue
        colour = PHASE_COLOUR[t.work_package]
        if t.secondary:
            style = f"bar/.append style={{fill=white, draw={colour}, dashed, line width=0.8pt}}"
        elif t.id in crit:
            style = f"bar/.append style={{fill={colour}, draw=critred, line width=1.2pt}}"
        else:
            style = f"bar/.append style={{fill={colour}}}"
        line = f"\\ganttbar[{style}]{{{t.id} {t.short}}}{{{t.es + 1}}}{{{t.ef}}}"
        if t.slack > 0:
            line += f" \\ganttbar[inline=false, {HATCH}]{{}}{{{t.ef + 1}}}{{{t.lf}}}"
        lines.append(line + " \\\\")
    return "\n".join(lines) + "\n"


def wbs(project: Project) -> str:
    """Portrait layout: two rows of five work packages under the project root."""
    col_w, leaf_h = 3.25, 0.58
    every = project.ongoing + project.tasks
    packages = list(project.work_packages.items())
    rows = [packages[:5], packages[5:]]
    lines = [f"\\node[wbsroot] (root) at ({2 * col_w:.2f},0) "
             f"{{IS40: low-cost proprioceptive stability control}};"]
    y_wp = -1.3
    for r, row in enumerate(rows):
        bus_y = y_wp + 0.75
        if r == 0:
            lines.append(f"\\draw[wbsline] (root.south) -- ({2 * col_w:.2f},{bus_y:.2f});")
        else:
            lines.append(f"\\draw[wbsline] (root.west) -| (-1.75,{bus_y:.2f}) -- ({4 * col_w:.2f},{bus_y:.2f});")
        lines.append(f"\\draw[wbsline] (0,{bus_y:.2f}) -- ({4 * col_w:.2f},{bus_y:.2f});")
        deepest = 0
        for i, (wp, name) in enumerate(row):
            x = i * col_w
            dashed = ",secondary" if wp == "10" else ""
            lines.append(f"\\node[wbswp{dashed}] (wp{wp}) at ({x:.2f},{y_wp:.2f}) {{{wp} {name}}};")
            lines.append(f"\\draw[wbsline] ({x:.2f},{bus_y:.2f}) -- (wp{wp}.north);")
            members = [t for t in every if t.estimate and t.work_package == wp]   # ongoing tasks have no duration
            for j, t in enumerate(members):
                node = "t" + t.id.replace(".", "_")
                y = y_wp - 0.85 - j * leaf_h
                lines.append(f"\\node[wbsleaf{dashed}] ({node}) at ({x - 1.15:.2f},{y:.2f}) {{{t.id} {t.short}}};")
                lines.append(f"\\draw[wbsline] ({x - 1.3:.2f},{y_wp - 0.45:.2f}) |- ({node}.west);")
            deepest = max(deepest, len(members))
        y_wp = y_wp - 0.85 - deepest * leaf_h - 1.3
    return "\n".join(lines) + "\n"


def network(project: Project, crit: set[str]) -> str:
    """Summary activity-on-the-node network, laid out by hand in project.yaml."""
    by_id = {t.id: t for t in project.tasks}
    spec = project.network
    node_of: dict[str, str] = {}
    nodes: dict[str, dict] = {}
    for i, g in enumerate(spec["groups"], 1):
        key = f"g{i}"
        members = [by_id[m] for m in g["tasks"]]
        nodes[key] = dict(num=i, name=g["name"], at=g["at"], ms=False,
                          es=min(t.es for t in members), ef=max(t.ef for t in members),
                          crit=any(t.id in crit for t in members), secondary=members[0].secondary)
        for m in g["tasks"]:
            node_of[m] = key
    for mid, at in spec["milestones"].items():
        nodes[mid] = dict(name=by_id[mid].short, at=at, ms=True, crit=mid in crit)
        node_of[mid] = mid

    def resolve(tid: str) -> set[str]:
        if tid in node_of:
            return {node_of[tid]}
        return set().union(*(resolve(p) for p in by_id[tid].after)) if by_id[tid].after else set()

    edges = {(src, node_of[t.id]) for t in project.tasks if t.id in node_of
             for p in t.after for src in resolve(p) if src != node_of[t.id]}

    def reachable(a: str, b: str, skip: tuple[str, str]) -> bool:
        stack, seen = [a], {a}
        while stack:
            u = stack.pop()
            for x, y in edges:
                if x == u and (x, y) != skip and y not in seen:
                    if y == b:
                        return True
                    seen.add(y)
                    stack.append(y)
        return False

    edges = {e for e in edges if not reachable(e[0], e[1], e)}     # transitive reduction

    # Horizontal layout sized for a portrait page: time runs left to right, and
    # columns that hold only a milestone are narrower than activity columns.
    node_col, ms_col, row_h = 2.75, 1.5, 1.95
    ms_only = {c for c in range(20)
               if any(n["at"][0] == c for n in nodes.values())
               and all(n["ms"] for n in nodes.values() if n["at"][0] == c)}
    col_x, x_acc = {}, 0.0
    for c in range(max(n["at"][0] for n in nodes.values()) + 1):
        col_x[c] = x_acc
        x_acc += ms_col if c in ms_only else node_col

    lines = []
    for key, n in nodes.items():
        x, y = col_x[n["at"][0]], -n["at"][1] * row_h
        crit_style = ",crit" if n["crit"] else ""
        if n["ms"]:
            x += 0.6
            lines.append(f"\\node[ms{crit_style}] ({key}) at ({x:.2f},{y:.2f}) {{}};")
            lines.append(f"\\node[mslabel, anchor=north, align=center, text width=1.4cm] at ({x:.2f},{y - 0.26:.2f}) "
                         f"{{{n['name'].replace(' ', ' \\\\ ', 1)}}};")
        else:
            sec = ",secondary" if n["secondary"] else ""
            lines.append(f"\\node[aon{crit_style}{sec}] ({key}) at ({x:.2f},{y:.2f}) {{{n['name']}}};")
            lines.append(f"\\node[aontop] at ({key}.north west) {{W{n['es'] + 1} \\quad {n['ef'] - n['es']} wks}};")
            lines.append(f"\\node[aonnum] at ({key}.south west) {{{n['num']}}};")
    for a, b in sorted(edges):
        style = "critedge" if nodes[a]["crit"] and nodes[b]["crit"] else "edge"
        same_column = nodes[a]["at"][0] == nodes[b]["at"][0]
        if same_column:                                  # stacked nodes: vertical arrow
            down = nodes[a]["at"][1] < nodes[b]["at"][1]
            src, dst = ("south", "north") if down else ("north", "south")
            lines.append(f"\\draw[{style}] ([xshift=0.5cm]{a}.{src}) -- ([xshift=0.5cm]{b}.{dst});")
        else:
            lines.append(f"\\draw[{style}] ({a}.east) -- ({b}.west);")
    return "\n".join(lines) + "\n"


def load_chart(project: Project, load: dict[int, float]) -> str:
    c = project.config
    bar_w, y_scale = 0.42, 0.16
    loe = ongoing_rate(project)
    lines = []
    for w in range(1, c.weeks + 1):
        x = (w - 1) * bar_w
        half = 0.5 if w in c.christmas_weeks else 1.0
        net, mgmt, avail = load[w], loe * half, c.hours_per_week * half
        lines += [
            f"\\fill[loadnet] ({x + 0.04:.2f},0) rectangle ({x + bar_w - 0.04:.2f},{net * y_scale:.3f});",
            f"\\fill[loadloe] ({x + 0.04:.2f},{net * y_scale:.3f}) rectangle "
            f"({x + bar_w - 0.04:.2f},{(net + mgmt) * y_scale:.3f});",
            f"\\draw[availline] ({x:.2f},{avail * y_scale:.3f}) -- ({x + bar_w:.2f},{avail * y_scale:.3f});",
            f"\\draw[contline] ({x:.2f},{avail * c.weekly_loading * y_scale:.3f}) -- "
            f"({x + bar_w:.2f},{avail * c.weekly_loading * y_scale:.3f});",
        ]
        if w % 2 == 1:
            lines.append(f"\\node[axislabel, below] at ({x + bar_w / 2:.2f},0) {{{w}}};")
    for h in (0, 4, 8, 12, 14):
        lines.append(f"\\node[axislabel, left] at (0,{h * y_scale:.3f}) {{{h}}};")
    lines += [f"\\draw[black!50] (0,0) -- ({c.weeks * bar_w:.2f},0);",
              f"\\node[axislabel, rotate=90] at (-0.75,{7 * y_scale:.3f}) {{hours per week}};",
              f"\\node[axislabel] at ({c.weeks * bar_w / 2:.2f},-0.6) {{week}};"]
    return "\n".join(lines) + "\n"


SCOPE_LEGEND = {"baseline": "In the baseline", "conditional": "Only if reserve hours remain",
                "gaps": "Only to fill gaps", "future": "Future work"}


def scope_matrix(project: Project) -> str:
    """Value-effort matrix: each feature is a numbered point, coloured by decision,
    with the legend beside the plot so labels never overlap."""
    xs, ys = 1.8, 1.4                                    # cm per score point
    def c(v: float) -> str:
        return f"{v:.2f}"
    order = sorted(project.scope, key=lambda f: Feature.DECISIONS.index(f.decision))
    lines = [
        # quadrants split at 3 on both scales, as in the module's prioritisation chart
        f"\\fill[raggreen!45] (0,{c(3 * ys)}) rectangle ({c(3 * xs)},{c(5 * ys)});",
        f"\\fill[ragamber!45] ({c(3 * xs)},{c(3 * ys)}) rectangle ({c(5 * xs)},{c(5 * ys)});",
        f"\\fill[black!5] (0,0) rectangle ({c(3 * xs)},{c(3 * ys)});",
        f"\\fill[ragred!30] ({c(3 * xs)},0) rectangle ({c(5 * xs)},{c(3 * ys)});",
        f"\\draw[black!25] ({c(3 * xs)},0) -- ({c(3 * xs)},{c(5 * ys)}) (0,{c(3 * ys)}) -- ({c(5 * xs)},{c(3 * ys)});",
        f"\\draw[black!45, dashed] ({c(3 * xs)},{c(3 * ys)}) circle (0.9);",
        f"\\node[quadlabel, anchor=south west] at (0.05,{c(3 * ys + 0.05)}) {{Top priority}};",
        f"\\node[quadlabel, anchor=south east] at ({c(5 * xs - 0.05)},{c(3 * ys + 0.05)}) {{Re-evaluate}};",
        f"\\node[quadlabel, anchor=south west] at (0.05,0.05) {{Wish list}};",
        f"\\node[quadlabel, anchor=south east] at ({c(5 * xs - 0.05)},0.05) {{Parking lot}};",
        f"\\node[quadlabel, font=\\sffamily\\tiny\\itshape] at ({c(3 * xs)},{c(3 * ys - 1.12)}) {{medium}};",
        f"\\draw[-{{Stealth[length=2mm]}}, black!60] (0,0) -- ({c(5 * xs + 0.3)},0) node[right, axislabel] {{effort}};",
        f"\\draw[-{{Stealth[length=2mm]}}, black!60] (0,0) -- (0,{c(5 * ys + 0.3)}) node[above, axislabel] {{value for the research question}};",
        f"\\node[axislabel, below] at ({c(1.5 * xs)},0) {{low}};",
        f"\\node[axislabel, below] at ({c(4 * xs)},0) {{high}};",
        f"\\node[axislabel, left] at (0,{c(1.5 * ys)}) {{low}};",
        f"\\node[axislabel, left] at (0,{c(4 * ys)}) {{high}};",
    ]
    for i, f in enumerate(order, 1):
        lines.append(f"\\node[pt{f.decision}] at ({f.effort * xs:.2f},{f.value * ys:.2f}) {{{i}}};")

    x_leg, y = 5 * xs + 1.2, 5 * ys
    for decision in Feature.DECISIONS:
        members = [(i, f) for i, f in enumerate(order, 1) if f.decision == decision]
        if not members:
            continue
        lines.append(f"\\node[pt{decision}] at ({x_leg + 0.2:.2f},{y:.2f}) {{}};")
        lines.append(f"\\node[legendhead] at ({x_leg + 0.5:.2f},{y:.2f}) {{{SCOPE_LEGEND[decision]}}};")
        y -= 0.42
        for i, f in members:
            lines.append(f"\\node[legenditem] at ({x_leg + 0.5:.2f},{y:.2f}) {{{i}\\enspace {f.name}}};")
            y -= 0.36
        y -= 0.2
    return "\n".join(lines) + "\n"
