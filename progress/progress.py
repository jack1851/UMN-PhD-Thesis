# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib>=3.8"]
# ///
"""Log thesis writing progress from git history and plot it.

For every commit that touched chapters/, plus the current working tree, count
words per chapter file with texcount and open items (\\todo, \\missingfigure,
and TODO/FIXME in comments). Results accumulate in progress/out/progress.csv
(commits already logged are not recounted) and are drawn as
progress/out/progress.png and .svg:

  1. total words as a burn-up chart: the actual count against bands set by
     a planned pace and the last-possible pace to the deadline
  2. one small panel per chapter with the same bands, as a share of its target

Open items are reported in the printed table only.

Chapter labels, targets and old file names live in progress/targets.toml.

Usage:  uv run progress/progress.py [--no-plot] [--out DIR]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHAPTER_DIRS = ["chapters"]
FIELDS = ["commit", "time", "file", "words", "todos"]
NO_FILES = "-"  # marker row for commits with no chapter files
WORKTREE = "worktree"

TODO_MACRO = re.compile(r"\\(?:todo|missingfigure)\b")
TODO_COMMENT = re.compile(r"%[^\n]*\b(?:TODO|FIXME)\b")
TEX_COMMENT = re.compile(r"(?<!\\)%[^\n]*")

SURFACE, INK, INK2, MUTED, GRID, AXIS = (
    "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7")


# --------------------------------------------------------------------------
# collecting
# --------------------------------------------------------------------------
def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout


def load_config() -> tuple[dict, dict[str, dict]]:
    cfg = tomllib.loads((HERE / "targets.toml").read_text())
    return cfg, cfg.get("chapters", {})


def chapter_commits() -> list[tuple[str, int]]:
    out = git("log", "--reverse", "--format=%H%x09%ct", "--", *CHAPTER_DIRS)
    return [(sha, int(ts)) for sha, ts in
            (line.split("\t") for line in out.splitlines())]


def extract(sha: str, dest: Path) -> list[str]:
    """Check out the chapter sources of one commit into dest."""
    proc = subprocess.run(["git", "archive", sha, "--", *CHAPTER_DIRS],
                          cwd=ROOT, capture_output=True)
    if proc.returncode != 0:  # the directory did not exist yet
        return []
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(dest, filter="data")
    return tex_files(dest)


def tex_files(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix()
                  for d in CHAPTER_DIRS if (base / d).is_dir()
                  for p in (base / d).rglob("*.tex"))


def word_counts(cwd: Path, files: list[str]) -> dict[str, int]:
    if not files:
        return {}
    proc = subprocess.run(["texcount", "-brief", "-sum", "-q", "-utf8", *files],
                          cwd=cwd, capture_output=True, text=True)
    counts = {m.group(2).strip(): int(m.group(1))
              for m in re.finditer(r"^(\d+): File: (.+)$", proc.stdout, re.M)}
    missing = [f for f in files if f not in counts]
    if missing:
        print(f"warning: texcount gave no count for {missing}", file=sys.stderr)
    return counts


def todo_count(text: str) -> int:
    n = len(TODO_COMMENT.findall(text))
    n += len(TODO_MACRO.findall(TEX_COMMENT.sub("", text)))
    return n


def count_tree(sha: str, when: int, cwd: Path, files: list[str]) -> list[dict]:
    if not files:
        return [dict(commit=sha, time=when, file=NO_FILES, words=0, todos=0)]
    words = word_counts(cwd, files)
    return [dict(commit=sha, time=when, file=f, words=words.get(f, 0),
                 todos=todo_count((cwd / f).read_text(errors="replace")))
            for f in files]


def read_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return [dict(r, time=int(r["time"]), words=int(r["words"]),
                     todos=int(r["todos"])) for r in csv.DictReader(fh)]


def write_log(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["time"], r["commit"], r["file"])))


def update_log(path: Path) -> list[dict]:
    commits = chapter_commits()
    known = {sha for sha, _ in commits}
    rows = [r for r in read_log(path)
            if r["commit"] in known]  # drop rewritten history and old worktree rows
    done = {r["commit"] for r in rows}
    todo = [(sha, ts) for sha, ts in commits if sha not in done]
    if todo:
        print(f"counting {len(todo)} new commit(s)")
    with tempfile.TemporaryDirectory() as tmp:
        for sha, ts in todo:
            dest = Path(tmp) / sha
            rows += count_tree(sha, ts, dest, extract(sha, dest))
    now = int(dt.datetime.now().timestamp())
    rows += count_tree(WORKTREE, now, ROOT, tex_files(ROOT))
    write_log(path, rows)
    return rows


# --------------------------------------------------------------------------
# shaping
# --------------------------------------------------------------------------
def canonical_map(chapters: dict[str, dict]) -> dict[str, str]:
    m = {}
    for key, c in chapters.items():
        m[key] = key
        for alias in c.get("aliases", []):
            m[alias] = key
    return m


def series(rows: list[dict], chapters: dict[str, dict]):
    """Per snapshot: time, total words, total todos, per-chapter words/todos."""
    canon = canonical_map(chapters)
    snaps: dict[str, dict] = {}
    for r in rows:
        s = snaps.setdefault(r["commit"], dict(
            time=r["time"], words=0, todos=0,
            by={k: dict(words=0, todos=0) for k in chapters}))
        if r["file"] == NO_FILES:
            continue
        s["words"] += r["words"]
        s["todos"] += r["todos"]
        key = canon.get(r["file"])
        if key:
            s["by"][key]["words"] += r["words"]
            s["by"][key]["todos"] += r["todos"]
    return sorted(snaps.values(), key=lambda s: s["time"])


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def print_summary(snaps: list[dict], chapters: dict[str, dict]) -> None:
    latest = snaps[-1]
    last_change = {}
    for key in chapters:
        prev = None
        for s in snaps:
            cur = s["by"][key]["words"]
            if prev is not None and cur != prev:
                last_change[key] = s["time"]
            prev = cur
    total_target = sum(c.get("target", 0) for c in chapters.values())
    width = max(len(c["label"]) for c in chapters.values())
    print(f"{'chapter':<{width}}  {'words':>6}  {'target':>6}  {'done':>5}  "
          f"{'open':>4}  last change")
    for key, c in chapters.items():
        b = latest["by"][key]
        tgt = c.get("target")
        pct = f"{100 * b['words'] / tgt:4.0f}%" if tgt else "    -"
        when = last_change.get(key)
        when = dt.date.fromtimestamp(when).isoformat() if when else "-"
        print(f"{c['label']:<{width}}  {b['words']:>6}  {tgt or '-':>6}  {pct:>5}  "
              f"{b['todos']:>4}  {when}")
    pct = f"{100 * latest['words'] / total_target:4.0f}%" if total_target else "    -"
    print(f"{'total':<{width}}  {latest['words']:>6}  {total_target:>6}  {pct:>5}  "
          f"{latest['todos']:>4}")


def plot(snaps: list[dict], chapters: dict[str, dict], cfg: dict, out: Path) -> None:
    """Burn-up chart of total words, then one small multiple per chapter.

    Every panel shows the actual word count against four bands set by two
    paces: a planned pace (baseline) and the last-possible pace that still
    reaches the target by the deadline. Config in targets.toml, top level
    (all optional; without a deadline the bands are skipped):

      deadline      date the thesis must be complete
      plan_start    date the planned pace starts (default: today)
      plan_end      date the planned pace reaches the target (default: deadline - 8 weeks)
      max_pace      sustainable words/week for a last-minute push (default 3000)
      danger_days   margin before the last-possible start (default 30)

    A chapter table may override plan_start, plan_end and deadline for its
    own panel; its last-possible pace is max_pace scaled by its share of the
    total target, so chapters pushed in parallel would all finish together.
    """
    import math
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif", "font.size": 9,
        "axes.facecolor": SURFACE, "figure.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8,
        "axes.labelcolor": INK2, "axes.titlecolor": INK, "axes.titleweight": "bold",
        "axes.titlesize": 10, "axes.titlelocation": "left",
        "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
        "axes.grid": True, "axes.grid.axis": "y",
        "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "axes.spines.top": False, "axes.spines.right": False,
    })
    BLUE, GREEN, YELLOW, RED = "#9db8f0", "#a9d3a0", "#f6efa2", "#f2a49c"
    BLUE_LINE, RED_LINE = "#2a78d6", "#e34948"
    day = dt.timedelta(days=1)
    times = [dt.datetime.fromtimestamp(s["time"]) for s in snaps]
    keys = list(chapters)
    ncol = 4
    nrow = math.ceil(len(keys) / ncol)
    target = sum(c.get("target", 0) for c in chapters.values())

    def as_dt(d, default):
        return dt.datetime.combine(d, dt.time()) if d else default

    deadline = as_dt(cfg.get("deadline"), None)
    plan_start = as_dt(cfg.get("plan_start"), times[-1])
    plan_end = as_dt(cfg.get("plan_end"), deadline - 56 * day if deadline else None)
    pace = cfg.get("max_pace", 3000) / 7          # words/day
    margin = cfg.get("danger_days", 30) * day
    if deadline:
        x_start = min(plan_start, times[-1]) - 14 * day
        x_end = deadline + 60 * day
    else:
        x_start, x_end = times[0], times[-1]
    grid = [x_start + i * day for i in range(int((x_end - x_start).days) + 1)]

    def ramp(t, t0, t1, top):
        if t1 <= t0 or t >= t1:
            return float(top)
        if t <= t0:
            return 0.0
        return top * (t - t0) / (t1 - t0)

    def bands(ax, top, t_start, t_end, dl, wpd, ymax, legend=False):
        """Fill the four bands on ax for a target `top` (in the axis units)."""
        jit_start = dl - (top / wpd) * day
        base = [ramp(t, t_start, t_end, top) for t in grid]
        jit = [ramp(t, jit_start, dl, top) for t in grid]
        danger = [ramp(t, jit_start - margin, dl - margin, top) for t in grid]
        lab = dict(ahead="Baseline", on="On track", dng="Danger", late="Late") \
            if legend else dict(ahead=None, on=None, dng=None, late=None)
        ax.fill_between(grid, base, ymax, color=BLUE, linewidth=0, label=lab["ahead"])
        ax.fill_between(grid, danger, base, color=GREEN, linewidth=0, label=lab["on"])
        ax.fill_between(grid, jit, danger, color=YELLOW, linewidth=0, label=lab["dng"])
        ax.fill_between(grid, 0, jit, color=RED, linewidth=0, label=lab["late"])
        ax.plot(grid, base, color=BLUE_LINE, linewidth=1.2)
        ax.plot(grid, jit, color=RED_LINE, linewidth=1.2)
        ax.axvline(dl, color=INK2, linewidth=0.7, linestyle="--")
        ax.grid(False)

    fig = plt.figure(figsize=(11, 4.6 + 1.5 * nrow))
    gs = fig.add_gridspec(1 + nrow, ncol,
                          height_ratios=[3] + [1.25] * nrow,
                          hspace=0.6, wspace=0.28)

    # 1. total words
    ax1 = fig.add_subplot(gs[0, :])
    total = [s["words"] for s in snaps]
    title = "Total word count"
    if target and deadline:
        top = target * 1.06
        bands(ax1, target, plan_start, plan_end, deadline, pace, top, legend=True)
        ax1.annotate(f"Deadline: {deadline:%b %-d, %Y}", (deadline, 0), xytext=(-4, 4),
                     textcoords="offset points", ha="right", va="bottom",
                     color=INK2, fontsize=8)
        if deadline > times[-1]:
            days = max((deadline - times[-1]).days, 1)
            title += (f"   ·   {(target - total[-1]) / days * 7:,.0f} words/week "
                      f"from today finishes on the deadline")
        ax1.set_ylim(0, top)
        ax1.legend(loc="upper left", ncol=4, fontsize=8, frameon=True,
                   facecolor=SURFACE, edgecolor=AXIS, framealpha=1.0,
                   bbox_to_anchor=(0.01, 0.97), handlelength=1.2, columnspacing=1.2,
                   borderpad=0.7)
    else:
        if target:
            ax1.axhline(target, color=MUTED, linewidth=0.8, linestyle="--")
        ax1.set_ylim(bottom=0)
    ax1.plot(times, total, color=INK, linewidth=1.8, marker="o", markersize=4,
             markeredgecolor=SURFACE, markeredgewidth=0.6, drawstyle="steps-post")
    ax1.annotate(f"{total[-1]:,} words", (times[-1], total[-1]),
                 xytext=(8, 2), textcoords="offset points", va="bottom",
                 color=INK, fontsize=8, fontweight="bold")
    ax1.set_title(title, pad=6)
    ax1.set_xlim(x_start, x_end)
    ax1.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    loc = mdates.AutoDateLocator()
    ax1.xaxis.set_major_locator(loc)
    ax1.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))

    # 2. one small multiple per chapter: share of its own target, same bands
    ymax = 110.0
    for key in keys:
        tgt = chapters[key].get("target")
        if tgt:
            ymax = max(ymax, 100 * max(s["by"][key]["words"] for s in snaps) / tgt + 8)
    for i, key in enumerate(keys):
        r, c = divmod(i, ncol)
        ax = fig.add_subplot(gs[1 + r, c], sharex=ax1)
        ch = chapters[key]
        tgt = ch.get("target")
        words = [s["by"][key]["words"] for s in snaps]
        pct = [100 * w / tgt for w in words] if tgt else [0] * len(words)
        if tgt and deadline:
            c_dl = as_dt(ch.get("deadline"), deadline)
            c_start = as_dt(ch.get("plan_start"), plan_start)
            c_end = as_dt(ch.get("plan_end"), plan_end if ch.get("deadline") is None
                          else c_dl - 56 * day)
            c_pace = pace * tgt / target * (100 / tgt)   # %/day, scaled by share of total
            bands(ax, 100, c_start, c_end, c_dl, c_pace, ymax)
        else:
            ax.axhline(100, color=MUTED, linewidth=0.7, linestyle="--")
        ax.plot(times, pct, color=INK, linewidth=1.2, marker="o", markersize=2.5,
                markeredgecolor=SURFACE, markeredgewidth=0.6, drawstyle="steps-post")
        ax.set_ylim(0, ymax)
        ax.set_yticks([0, 50, 100])
        ax.set_title(ch["label"], fontsize=8.5, pad=13)
        ax.annotate(f"{pct[-1]:.0f}%  ·  {words[-1]:,} / {tgt:,} words",
                    (0, 1), xycoords="axes fraction", xytext=(0, 2),
                    textcoords="offset points", va="bottom", ha="left",
                    color=INK2, fontsize=7)
        if c == 0:
            ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
        else:
            plt.setp(ax.get_yticklabels(), visible=False)
        if r == nrow - 1:
            sloc = mdates.AutoDateLocator(minticks=2, maxticks=4)
            ax.xaxis.set_major_locator(sloc)
            ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(sloc))
            ax.tick_params(axis="x", labelsize=7)
        else:
            plt.setp(ax.get_xticklabels(), visible=False)
    fig.canvas.draw()
    top_y = max(a.get_position().y1 for a in fig.axes[1:1 + ncol])
    fig.text(0.07, top_y + 0.045, "Per Chapter",
             fontsize=10, fontweight="bold", color=INK, ha="left")

    stamp = times[-1].strftime("%Y-%m-%d")
    fig.suptitle(f"Thesis progress as of {stamp}",
                 x=0.07, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.subplots_adjust(left=0.07, right=0.95, top=0.93, bottom=0.05)
    fig.savefig(out / "progress.png", dpi=200)
    fig.savefig(out / "progress.svg")
    print(f"wrote {out / 'progress.png'} and .svg")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-plot", action="store_true", help="only update the CSV")
    ap.add_argument("--out", type=Path, default=HERE / "out",
                    help="output directory (default progress/out)")
    args = ap.parse_args()
    cfg, chapters = load_config()
    rows = update_log(args.out / "progress.csv")
    snaps = series(rows, chapters)
    print_summary(snaps, chapters)
    if not args.no_plot:
        plot(snaps, chapters, cfg, args.out)


if __name__ == "__main__":
    main()
