#!/usr/bin/env python3
"""A FLORA demo galeriajanak illusztracioi.

Vektor, nem raszter: a csempek statikusak, a vilagitodobozban viszont nagyban is
megjelennek — egy SVG ott is eles marad, es par kilobajt.
A paletta a demos.css-bol jon (rozsa #B76E79, zsalya #2C4A3B, puder #F4E4E4).
"""
import math, pathlib

W, H = 900, 760
BLUSH, CREAM, ROSE, ROSE_D, SAGE, SAGE_L = "#F4E4E4", "#FFF8F5", "#B76E79", "#9C5A64", "#2C4A3B", "#6E8577"


def qbez(p0, p1, p2, t):
    """Pont es erinto-szog egy masodfoku Bezier-gorben."""
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
    dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
    dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
    return x, y, math.atan2(dy, dx)


def head(bg):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}" role="img">'
            f'<rect width="{W}" height="{H}" fill="{bg}"/>')


# ------------------------------------------------------------------ 1. agak
def branch():
    s = [head(BLUSH), f'<circle cx="622" cy="238" r="238" fill="{CREAM}" opacity=".9"/>']
    for p0, p1, p2, n, col, scale, op in (
            ((70, 730), (300, 470), (700, 250), 11, SAGE, 1.0, .85),
            ((210, 780), (500, 600), (860, 470), 8, SAGE_L, .78, .7)):
        s.append(f'<path d="M{p0[0]} {p0[1]} Q{p1[0]} {p1[1]} {p2[0]} {p2[1]}" fill="none" '
                 f'stroke="{col}" stroke-width="4" stroke-linecap="round" opacity=".8"/>')
        for i in range(n):
            t = 0.06 + 0.92 * i / (n - 1)
            x, y, ang = qbez(p0, p1, p2, t)
            side = 1 if i % 2 else -1
            taper = 1 - 0.45 * t                      # a hajtas vege felé kisebb level
            rx, ry = 62 * scale * taper, 30 * scale * taper
            # a level a szarra merolegesen ul ki, nem rajta
            off = (rx * 0.72) * side
            lx = x + off * math.cos(ang + math.pi / 2)
            ly = y + off * math.sin(ang + math.pi / 2)
            deg = math.degrees(ang) + side * 22
            s.append(f'<ellipse cx="{lx:.0f}" cy="{ly:.0f}" rx="{rx:.0f}" ry="{ry:.0f}" fill="{col}" '
                     f'opacity="{op if i % 2 else op - .2:.2f}" transform="rotate({deg:.0f} {lx:.0f} {ly:.0f})"/>')
    s.append(f'<circle cx="742" cy="150" r="26" fill="{ROSE}" opacity=".85"/>')
    s.append(f'<circle cx="800" cy="206" r="12" fill="{ROSE}" opacity=".5"/>')
    return "".join(s) + "</svg>"


# ----------------------------------------------------------------- 2. virag
def bloom():
    cx, cy = 450, 360
    s = [head(CREAM)]
    s.append(f'<circle cx="{cx}" cy="{cy}" r="268" fill="{BLUSH}"/>')
    for n, rx, ry, col, op, skew in ((9, 216, 76, ROSE, .30, 0), (6, 138, 52, ROSE_D, .42, 15)):
        for i in range(n):
            a = 180 * i / n + skew
            s.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{col}" opacity="{op}" '
                     f'transform="rotate({a:.1f} {cx} {cy})"/>')
    s.append(f'<circle cx="{cx}" cy="{cy}" r="30" fill="{SAGE}" opacity=".9"/>')
    s.append(f'<path d="M{cx} {cy+250} L{cx} {H}" stroke="{SAGE}" stroke-width="7" stroke-linecap="round" opacity=".75"/>')
    for side in (-1, 1):
        yy = cy + 330
        s.append(f'<ellipse cx="{cx + side*54}" cy="{yy}" rx="56" ry="24" fill="{SAGE}" opacity=".55" '
                 f'transform="rotate({side*-24} {cx + side*54} {yy})"/>')
    return "".join(s) + "</svg>"


# --------------------------------------------------------------- 3. hullamok
def strands():
    """Egymast nem fedo szalagok: egy tincs ivet idezi, nem abrazol semmit.

    A savok szandekosan nem egymasra vannak retegezve: atlatszo retegekbol
    egymasra csusztatva a rozsa es a zsalya szurkes-barna masszava keveredik.
    """
    s = [head(CREAM)]

    def ribbon(y0, thick, fill, stroke=None):
        amp = 62
        top = (f"M-60 {y0} C{W*0.24:.0f} {y0-amp:.0f} {W*0.44:.0f} {y0+amp:.0f} {W*0.66:.0f} {y0:.0f} "
               f"S{W*0.9:.0f} {y0-amp*0.95:.0f} {W+60} {y0-amp*0.5:.0f}")
        bot = (f"L{W+60} {y0+thick-amp*0.5:.0f} "
               f"C{W*0.9:.0f} {y0+thick-amp*0.95:.0f} {W*0.78:.0f} {y0+thick:.0f} {W*0.66:.0f} {y0+thick:.0f} "
               f"C{W*0.44:.0f} {y0+thick+amp:.0f} {W*0.24:.0f} {y0+thick-amp:.0f} -60 {y0+thick} Z")
        s.append(f'<path d="{top} {bot}" fill="{fill}"/>')
        if stroke:
            s.append(f'<path d="{top}" fill="none" stroke="{stroke}" stroke-width="3" opacity=".6"/>')

    s.append(f'<circle cx="726" cy="150" r="88" fill="{ROSE}" opacity=".35"/>')
    ribbon(150, 118, BLUSH)
    ribbon(300, 96, "#E8CDD1", SAGE_L)
    ribbon(424, 26, ROSE)
    ribbon(478, 132, "#DCE4DE")
    ribbon(636, 200, BLUSH, ROSE_D)
    return "".join(s) + "</svg>"


for name, fn in (("flora-1.svg", branch), ("flora-2.svg", bloom), ("flora-3.svg", strands)):
    pathlib.Path(name).write_text(fn(), encoding="utf-8")
    print(name, pathlib.Path(name).stat().st_size, "bytes")
