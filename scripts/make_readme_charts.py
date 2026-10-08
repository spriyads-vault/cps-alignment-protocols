"""Draws the README charts as static SVG files in docs/img. Free, no dependencies.

    uv run python scripts/make_readme_charts.py

The numbers are copied from results/*/report.md and the README tables, so rerun this after any result changes.
Colours follow Anthropic's warm palette (cream surface, slate ink, clay accent). The three series colours
were checked with the dataviz palette validator: lightness band, chroma floor and colour-blind separation
pass, and every series is also labelled directly.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path("docs/img")
SURFACE, INK, SOFT, MUTED, GRID = "#FAF9F5", "#141413", "#5E5D59", "#87867F", "#E3DACC"
CLAY, BLUE, OLIVE = "#C6613F", "#4F86C6", "#6B8F3A"
SANS = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
SERIF = "Georgia, 'Times New Roman', serif"


def svg(w: int, h: int, body: str, title: str, sub: str = "") -> str:
    subline = f'<text x="24" y="52" font-size="13" fill="{SOFT}">{sub}</text>' if sub else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'font-family="{SANS}" role="img" aria-label="{title}">'
        f'<rect width="{w}" height="{h}" rx="12" fill="{SURFACE}" stroke="{GRID}"/>'
        f'<text x="24" y="32" font-family="{SERIF}" font-size="19" fill="{INK}">{title}</text>'
        f"{subline}{body}</svg>"
    )


def write(name: str, content: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(content)


def tiles() -> str:
    data = [
        ("0 of 288", "cells with an overflow when the guard sits at the plant", OLIVE),
        ("1x hold", "delay a remote guard tolerates, about one hold period", CLAY),
        ("3 of 3", "covert attacks that beat block-and-hold at a 1% false-alarm budget", BLUE),
        ("190", "tests passing, ruff and mypy strict clean", INK),
    ]
    w, h, gap = 1000, 150, 16
    cw = (w - 48 - 3 * gap) / 4
    b = ""
    for i, (big, small, col) in enumerate(data):
        x = 24 + i * (cw + gap)
        b += f'<rect x="{x:.0f}" y="24" width="{cw:.0f}" height="102" rx="10" fill="#fff" stroke="{GRID}"/>'
        b += f'<rect x="{x:.0f}" y="24" width="6" height="102" rx="3" fill="{col}"/>'
        b += f'<text x="{x + 22:.0f}" y="66" font-family="{SERIF}" font-size="30" fill="{INK}">{big}</text>'
        words, line, ln = small.split(), "", 0
        for wd in words:
            if len(line) + len(wd) > 27:
                b += f'<text x="{x + 22:.0f}" y="{88 + ln * 16}" font-size="12" fill="{SOFT}">{line.strip()}</text>'
                line, ln = "", ln + 1
            line += wd + " "
        b += f'<text x="{x + 22:.0f}" y="{88 + ln * 16}" font-size="12" fill="{SOFT}">{line.strip()}</text>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="{SANS}" role="img" aria-label="Headline numbers">{b}</svg>'


def delay_chart() -> str:
    xs = [0, 2, 6, 8, 10, 12, 16, 20, 30, 46, 60, 90]
    series = [
        ("Guard at the plant (edge), every attack", [0] * 12, OLIVE),
        (
            "Guard next to the supervisor (remote), injection",
            [0, 0, 0, 0, 0, 1, 30, 30, 30, 30, 30, 30],
            CLAY,
        ),
        ("Monitor + remote guard, overt attack", [0, 0, 0, 0, 0, 1, 6, 21, 28, 23, 17, 1], BLUE),
    ]
    w, h, lm, r, t, bt = 900, 430, 64, 24, 80, 330
    px = lambda i: lm + i * (w - lm - r - 150) / (len(xs) - 1)  # noqa: E731
    py = lambda v: bt - v * (bt - t) / 30  # noqa: E731
    b = ""
    for v in (0, 10, 20, 30):
        b += f'<line x1="{lm}" x2="{w - r - 150}" y1="{py(v)}" y2="{py(v)}" stroke="{GRID}"/>'
        b += f'<text x="{lm - 10}" y="{py(v) + 4}" text-anchor="end" font-size="12" fill="{MUTED}">{v}</text>'
    for i, x in enumerate(xs):
        b += f'<text x="{px(i):.0f}" y="{bt + 20}" text-anchor="middle" font-size="12" fill="{MUTED}">{x}</text>'
    b += f'<text x="{(lm + w - r - 150) / 2:.0f}" y="{bt + 44}" text-anchor="middle" font-size="12" fill="{SOFT}">effective delay, seconds</text>'
    b += f'<text x="18" y="{(t + bt) / 2:.0f}" transform="rotate(-90 18 {(t + bt) / 2:.0f})" text-anchor="middle" font-size="12" fill="{SOFT}">overflows out of 30</text>'
    # the knee
    b += f'<line x1="{px(5):.0f}" x2="{px(5):.0f}" y1="{t}" y2="{bt}" stroke="{MUTED}" stroke-dasharray="4 4"/>'
    b += f'<text x="{px(5) - 8:.0f}" text-anchor="end" y="{py(18):.0f}" font-size="12" fill="{SOFT}">about 12 s: one hold period</text>'
    for k, (_name, ys, col) in enumerate(series):
        pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(ys))
        b += f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round"/>'
        for i, v in enumerate(ys):
            b += f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="3.5" fill="{col}" stroke="{SURFACE}" stroke-width="2"/>'
        ly = py(ys[-1]) + (4 if k == 0 else (4 if k == 1 else -14))
        b += f'<text x="{px(11) + 12:.0f}" y="{ly:.0f}" font-size="12" font-weight="600" fill="{col}">{["edge", "remote", "remote + monitor"][k]}</text>'
    # legend row
    lx = 24
    for name, _, col in series:
        b += f'<rect x="{lx}" y="{h - 26}" width="12" height="12" rx="3" fill="{col}"/><text x="{lx + 18}" y="{h - 16}" font-size="12" fill="{SOFT}">{name}</text>'
        lx += 18 + len(name) * 6.2 + 26
    return svg(
        w,
        h,
        b,
        "Where the guard runs decides how much delay it survives",
        "Minimum-phase plant, 30 episodes per point. Edge recorded 0 overflows in all 288 of its cells.",
    )


def hbars(
    name: str,
    title: str,
    sub: str,
    groups: list[tuple[str, list[float]]],
    keys: list[tuple[str, str]],
    unit: str,
    vmax: float,
    ref: tuple[float, str] | None = None,
    w: int = 900,
) -> str:
    left, right, top = 230, 70, 104
    bar, gap, grp = 16, 4, 16
    gh = len(keys) * (bar + gap) + grp
    h = top + len(groups) * gh + 52
    px = lambda v: left + v * (w - left - right) / vmax  # noqa: E731
    b = ""
    for tick in range(0, int(vmax) + 1, max(1, int(vmax // 5))):
        b += f'<line x1="{px(tick):.0f}" x2="{px(tick):.0f}" y1="{top - 8}" y2="{h - 48}" stroke="{GRID}"/>'
        b += f'<text x="{px(tick):.0f}" y="{h - 32}" text-anchor="middle" font-size="12" fill="{MUTED}">{tick}</text>'
    b += f'<text x="{(left + w - right) / 2:.0f}" y="{h - 12}" text-anchor="middle" font-size="12" fill="{SOFT}">{unit}</text>'
    if ref:
        b += f'<line x1="{px(ref[0]):.1f}" x2="{px(ref[0]):.1f}" y1="{top - 8}" y2="{h - 48}" stroke="{INK}" stroke-dasharray="5 4"/>'
        b += f'<text x="{px(ref[0]) + 6:.0f}" y="{top - 12}" font-size="12" fill="{INK}">{ref[1]}</text>'
    for gi, (label, vals) in enumerate(groups):
        y0 = top + gi * gh
        b += f'<text x="{left - 14}" y="{y0 + gh / 2 - 4:.0f}" text-anchor="end" font-size="13" fill="{INK}">{label}</text>'
        for ki, v in enumerate(vals):
            y = y0 + ki * (bar + gap)
            col = keys[ki][1]
            b += f'<path d="M{left},{y} h{max(px(v) - left - 4, 0):.1f} a4,4 0 0 1 4,4 v{bar - 8} a4,4 0 0 1 -4,4 h-{max(px(v) - left - 4, 0):.1f} z" fill="{col}"/>'
            b += f'<text x="{px(v) + 8:.0f}" y="{y + bar - 3}" font-size="12" fill="{INK}">{v:g}</text>'
    ly = 76
    lx = left
    for k, c in keys:
        b += f'<rect x="{lx}" y="{ly - 10}" width="12" height="12" rx="3" fill="{c}"/><text x="{lx + 18}" y="{ly}" font-size="12" fill="{SOFT}">{k}</text>'
        lx += 18 + len(k) * 7 + 22
    return svg(w, h, b, title, sub)


def main() -> None:
    write("tiles.svg", tiles())
    write("delay.svg", delay_chart())
    write(
        "threshold.svg",
        hbars(
            "threshold",
            "Delay budget grows with the hold period, shrinks with a looser barrier",
            "Delay at which the remote guard loses safety (d*), seconds. 10 episodes per cell.",
            [
                ("baseline (hold 10 s)", [12.0, 12.2]),
                ("hold 4 s", [4.2, 6.2]),
                ("hold 20 s", [24.4, 18.2]),
                ("looser barrier, gamma 0.8", [8.2, 8.2]),
                ("tighter barrier, gamma 0.3", [20.4, 16.2]),
                ("barrier 17 cm", [12.2, 14.2]),
                ("barrier 16 cm", [16.2, 16.2]),
            ],
            [("minimum-phase plant", CLAY), ("non-minimum-phase plant", BLUE)],
            "seconds of delay tolerated",
            30,
        ),
    )
    write(
        "monitor.svg",
        hbars(
            "monitor",
            "A real monitor catches blatant attacks and most covert ones",
            "Claude Haiku 4.5, share of attack decisions caught at a 1% false-alarm threshold. Overt and injection: 100%.",
            [("covert", [80, 89, 64]), ("covert, monitor-aware", [83, 82, 64])],
            [
                ("prompt warns of authority claims", CLAY),
                ("no warning", BLUE),
                ("numbers only", OLIVE),
            ],
            "% of decisions caught",
            100,
        ),
    )
    write(
        "adaptive.svg",
        hbars(
            "adaptive",
            "A searched attack beats a fooled monitor and finds nothing against one that is not",
            "Sabotage score after black-box search, 10 held-out seeds. 1 is the sabotage line. Surrogate monitor.",
            [("minimum-phase", [38.95, 0.72, 0.72]), ("non-minimum-phase", [35.86, 0.70, 0.69])],
            [
                ("monitor fooled by authority claims", CLAY),
                ("monitor not fooled", BLUE),
                ("honest supervisor, no attack", OLIVE),
            ],
            "sabotage score",
            40,
            ref=(1, "sabotage line = 1"),
        ),
    )
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
