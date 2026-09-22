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

  1. total words against the total target (and a deadline, if configured)
  2. each chapter as a percentage of its own target
  3. open items per chapter

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

# Categorical palette, fixed order (see the dataviz reference palette).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
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
        "legend.frameon": False, "legend.fontsize": 8,
    })
    times = [dt.datetime.fromtimestamp(s["time"]) for s in snaps]
    marker = dict(marker="o", markersize=3.5, markeredgecolor=SURFACE,
                  markeredgewidth=0.8, drawstyle="steps-post")
    keys = list(chapters)
    if len(keys) > len(SERIES):
        sys.exit(f"at most {len(SERIES)} chapters can be plotted; fold some together")

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(11, 9.5), sharex=True,
        gridspec_kw=dict(height_ratios=[3, 3, 2], hspace=0.32))

    # 1. total words vs target
    total = [s["words"] for s in snaps]
    target = sum(c.get("target", 0) for c in chapters.values())
    ax1.plot(times, total, color=SERIES[0], linewidth=2, **marker)
    ax1.annotate(f"{total[-1]:,} words", (times[-1], total[-1]),
                 xytext=(6, 0), textcoords="offset points", va="center",
                 color=INK2, fontsize=8)
    if target:
        ax1.axhline(target, color=MUTED, linewidth=0.8, linestyle="--")
        ax1.annotate(f"target {target:,}", (times[0], target), xytext=(0, 4),
                     textcoords="offset points", color=INK2, fontsize=8)
    deadline = cfg.get("deadline")
    if deadline:
        dl = dt.datetime.combine(deadline, dt.time())
        for ax in (ax1, ax2, ax3):
            ax.axvline(dl, color=MUTED, linewidth=0.8, linestyle="--")
        ax1.annotate(f"deadline {deadline:%b %-d, %Y}", (dl, 0), xytext=(-4, 4),
                     textcoords="offset points", ha="right", va="bottom",
                     color=INK2, fontsize=8)
        if target and dl > times[-1]:
            ax1.plot([times[-1], dl], [total[-1], target], color=MUTED,
                     linewidth=0.8, linestyle=":")
            days = max((dl - times[-1]).days, 1)
            ax1.annotate(f"{(target - total[-1]) / days * 7:,.0f} words/week needed",
                         (dl, target), xytext=(-4, -12), textcoords="offset points",
                         ha="right", color=INK2, fontsize=8)
    ax1.set_title("Total words in chapters/")
    ax1.set_ylim(bottom=0)
    ax1.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")

    # 2. each chapter as a share of its target
    for i, key in enumerate(keys):
        tgt = chapters[key].get("target")
        if not tgt:
            continue
        pct = [100 * s["by"][key]["words"] / tgt for s in snaps]
        ax2.plot(times, pct, color=SERIES[i], linewidth=1.6,
                 label=chapters[key]["label"], **marker)
    ax2.axhline(100, color=MUTED, linewidth=0.8, linestyle="--")
    ax2.set_title("Each chapter as a share of its target")
    ax2.set_ylim(0, max(105, ax2.get_ylim()[1]))
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")

    # 3. open items per chapter
    for i, key in enumerate(keys):
        ax3.plot(times, [s["by"][key]["todos"] for s in snaps],
                 color=SERIES[i], linewidth=1.6, **marker)
    ax3.set_title(r"Open items (\todo, \missingfigure, TODO/FIXME comments)")
    from matplotlib.ticker import MaxNLocator
    ax3.set_ylim(0, max(2, ax3.get_ylim()[1]))
    ax3.yaxis.set_major_locator(MaxNLocator(integer=True))

    loc = mdates.AutoDateLocator()
    ax3.xaxis.set_major_locator(loc)
    ax3.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    handles, labels = ax2.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4,
               bbox_to_anchor=(0.5, 0.005), handlelength=1.6, columnspacing=1.6)
    stamp = times[-1].strftime("%Y-%m-%d %H:%M")
    fig.suptitle(f"Thesis progress  ·  as of {stamp} (working tree)",
                 x=0.06, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.subplots_adjust(left=0.07, right=0.93, top=0.93, bottom=0.11)
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
