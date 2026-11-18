#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera puzzles.js con crucigramas diarios (fácil/medio/difícil).

Uso: python3 generate.py [fecha-inicio YYYY-MM-DD] [días]
Por defecto: hoy, 30 días. Reproducible: la semilla es fecha+nivel y el
historial de los días anteriores que ya están en puzzles.js.

Variedad:
- ninguna palabra se repite en RECENT_DAYS días (en ningún nivel)
- cada nivel destaca 2 temáticas del día, que no se repiten en THEME_COOLDOWN días
"""
import datetime
import json
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from words import WORDS

LEVELS = [
    # (nombre, tamaño, palabras objetivo, nivel máximo de palabra)
    ("facil",   10, 14, 1),
    ("medio",   12, 18, 2),
    ("dificil", 14, 23, 3),
]

RECENT_DAYS = 7
THEME_COOLDOWN = 3
FEATURED_PER_LEVEL = 2
FILLER_THEMES = {"general", "cotidiano"}  # nunca se destacan

ACROSS, DOWN = 0, 1


def can_place(grid, size, word, r, c, d):
    """Devuelve nº de cruces si la palabra cabe en (r,c) dirección d, si no None."""
    if d == ACROSS:
        if r < 0 or r >= size or c < 0 or c + len(word) > size:
            return None
        if (r, c - 1) in grid or (r, c + len(word)) in grid:
            return None
    else:
        if c < 0 or c >= size or r < 0 or r + len(word) > size:
            return None
        if (r - 1, c) in grid or (r + len(word), c) in grid:
            return None
    crosses = 0
    prev_occupied = False
    for i, ch in enumerate(word):
        rr, cc = (r, c + i) if d == ACROSS else (r + i, c)
        if (rr, cc) in grid:
            if grid[(rr, cc)] != ch:
                return None
            if prev_occupied:  # solaparía una palabra paralela
                return None
            crosses += 1
            prev_occupied = True
        else:
            prev_occupied = False
            # sin letra: los vecinos perpendiculares deben estar vacíos
            if d == ACROSS:
                if (rr - 1, cc) in grid or (rr + 1, cc) in grid:
                    return None
            else:
                if (rr, cc - 1) in grid or (rr, cc + 1) in grid:
                    return None
    return crosses


def place(grid, word, r, c, d):
    for i, ch in enumerate(word):
        rr, cc = (r, c + i) if d == ACROSS else (r + i, c)
        grid[(rr, cc)] = ch


def try_build(pool, size, target, rng, score):
    """Un intento de armado. pool: lista de entradas (w, clue, lvl, tema).
    score(entry) -> número; menor = se intenta antes."""
    grid = {}
    placed = []
    used = set()

    # primera palabra: larga, horizontal, cerca del centro
    firsts = [e for e in pool if size - 3 <= len(e[0]) <= size]
    if not firsts:
        firsts = [e for e in pool if len(e[0]) <= size]
    first = min(firsts, key=lambda e: score(e) + rng.random())
    r0 = size // 2 + rng.randint(-1, 1)
    c0 = (size - len(first[0])) // 2
    by_letter = {}  # letra -> celdas ocupadas con esa letra

    def put(word, r, c, d):
        for i, ch in enumerate(word):
            cell = (r, c + i) if d == ACROSS else (r + i, c)
            if cell not in grid:
                by_letter.setdefault(ch, []).append(cell)
        place(grid, word, r, c, d)

    put(first[0], r0, c0, ACROSS)
    placed.append((first, r0, c0, ACROSS))
    used.add(first[0])

    stall = 0
    while len(placed) < target and stall < 3:
        candidates = [e for e in pool if e[0] not in used and len(e[0]) <= size]
        keys = {e[0]: score(e) + rng.random() for e in candidates}
        candidates.sort(key=lambda e: keys[e[0]])
        progress = False
        for entry in candidates:
            word = entry[0]
            options = []
            idx = list(range(len(word)))
            rng.shuffle(idx)
            for i in idx:
                for gr, gc in by_letter.get(word[i], ()):
                    for d, rr, cc in ((ACROSS, gr, gc - i), (DOWN, gr - i, gc)):
                        cr = can_place(grid, size, word, rr, cc, d)
                        if cr is not None and cr >= 1:
                            options.append((rr, cc, d))
                if len(options) >= 6:
                    break
            if options:
                rr, cc, d = rng.choice(options)
                put(word, rr, cc, d)
                placed.append((entry, rr, cc, d))
                used.add(word)
                progress = True
                if len(placed) >= target:
                    break
        stall = 0 if progress else stall + 1
    return grid, placed


def numbering(rows, size):
    nums = {}
    k = 0
    for r in range(size):
        for c in range(size):
            if rows[r][c] == "#":
                continue
            sa = (c == 0 or rows[r][c - 1] == "#") and c + 1 < size and rows[r][c + 1] != "#"
            sd = (r == 0 or rows[r - 1][c] == "#") and r + 1 < size and rows[r + 1][c] != "#"
            if sa or sd:
                k += 1
                nums[(r, c)] = k
    return nums


def verify(rows, size, placed):
    """Toda secuencia >=2 letras del grid debe ser una palabra colocada."""
    placed_at = {(r, c, d): e[0] for e, r, c, d in placed}
    for r in range(size):
        c = 0
        while c < size:
            if rows[r][c] != "#" and (c == 0 or rows[r][c - 1] == "#"):
                cc = c
                while cc < size and rows[r][cc] != "#":
                    cc += 1
                if cc - c >= 2:
                    assert placed_at.get((r, c, ACROSS)) == rows[r][c:cc], \
                        f"Secuencia horizontal espuria en ({r},{c}): {rows[r][c:cc]}"
                c = cc
            else:
                c += 1
    for c in range(size):
        r = 0
        while r < size:
            if rows[r][c] != "#" and (r == 0 or rows[r - 1][c] == "#"):
                rr = r
                while rr < size and rows[rr][c] != "#":
                    rr += 1
                if rr - r >= 2:
                    word = "".join(rows[i][c] for i in range(r, rr))
                    assert placed_at.get((r, c, DOWN)) == word, \
                        f"Secuencia vertical espuria en ({r},{c}): {word}"
                r = rr
            else:
                r += 1


def build_level(date_str, name, size, target, max_lvl, banned, featured):
    rng = random.Random(f"{date_str}:{name}")
    pool = [e for e in WORDS if e[2] <= max_lvl and e[0] not in banned]

    def score(e):
        # temáticas del día primero; en niveles altos, palabras más difíciles
        return (0 if e[3] in featured else 1.0) + 0.4 * (max_lvl - e[2])

    best = None
    for _ in range(200):
        grid, placed = try_build(pool, size, target, rng, score)
        if best is None or len(placed) > len(best[1]):
            best = (grid, placed)
        if len(placed) >= target:
            break
    grid, placed = best

    rows = ["".join(grid.get((r, c), "#") for c in range(size)) for r in range(size)]
    verify(rows, size, placed)
    nums = numbering(rows, size)

    across, down = [], []
    temas = set()
    for entry, r, c, d in placed:
        word, clue, lvl, tema = entry
        n = nums[(r, c)]
        (across if d == ACROSS else down).append([n, clue])
        temas.add(tema)
    across.sort()
    down.sort()
    return {
        "size": size,
        "grid": rows,
        "across": across,
        "down": down,
        "temas": sorted(temas),
        "destacados": sorted(featured),
    }, [e[0] for e, *_ in placed]


CLUE_TO_WORD = {c: w for w, c, *_ in WORDS}


def day_words(day):
    """Palabras de un día ya generado (se reconocen por su pista)."""
    out = set()
    for p in day.values():
        for _, clue in p["across"] + p["down"]:
            if clue in CLUE_TO_WORD:
                out.add(CLUE_TO_WORD[clue])
    return out


def pick_featured(date_str, recent_featured):
    themes = sorted({e[3] for e in WORDS} - FILLER_THEMES)
    fresh = [t for t in themes if t not in recent_featured]
    rng = random.Random(f"{date_str}:temas")
    rng.shuffle(fresh)
    n = FEATURED_PER_LEVEL
    return [set(fresh[i * n:(i + 1) * n]) for i in range(len(LEVELS))]


def main():
    start = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 \
        else datetime.date.today()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "puzzles.js")
    existing = {}
    if os.path.exists(out):
        src = open(out, encoding="utf-8").read()
        existing = json.loads(src[src.index("{"):src.rindex(";")])

    # historial: palabras y temáticas destacadas de los días previos al inicio
    words_by_day, featured_by_day = {}, {}
    for k, day in existing.items():
        if k < start.isoformat():
            words_by_day[k] = day_words(day)
            featured_by_day[k] = set().union(*(p.get("destacados", []) for p in day.values()))

    def recent(store, date, n):
        res = set()
        for back in range(1, n + 1):
            res |= store.get((date - datetime.timedelta(days=back)).isoformat(), set())
        return res

    puzzles = {}
    for i in range(days):
        date = start + datetime.timedelta(days=i)
        date_str = date.isoformat()
        featured = pick_featured(date_str, recent(featured_by_day, date, THEME_COOLDOWN))
        used_today = set()
        day = {}
        for (name, size, target, max_lvl), feat in zip(LEVELS, featured):
            # antes de repetir palabras se aceptan hasta dos menos; si ni así
            # alcanza, se acorta la ventana de no repetición
            for window in (RECENT_DAYS, 4, 2, 0):
                banned = recent(words_by_day, date, window) | used_today
                puzzle, words = build_level(date_str, name, size, target, max_lvl, banned, feat)
                if len(words) >= target - 2 * (window == RECENT_DAYS):
                    break
            used_today |= set(words)
            day[name] = puzzle
            note = "" if window == RECENT_DAYS else f" (ventana {window} días)"
            print(f"{date_str} {name}: {len(words)} palabras · {', '.join(sorted(feat))}{note}")
        puzzles[date_str] = day
        words_by_day[date_str] = used_today
        featured_by_day[date_str] = set().union(*featured)

    # fusiona con lo existente y poda fechas de más de 45 días atrás
    cutoff = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
    existing = {k: v for k, v in existing.items() if k >= cutoff}
    existing.update(puzzles)
    puzzles = dict(sorted(existing.items()))

    with open(out, "w", encoding="utf-8") as f:
        f.write("// Generado por tools/generate.py — no editar a mano.\n")
        f.write("const PUZZLES = ")
        f.write(json.dumps(puzzles, ensure_ascii=False, separators=(",", ":")))
        f.write(";\n")
    print(f"\nEscrito {out} ({days} días)")


if __name__ == "__main__":
    main()
