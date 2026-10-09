"""Trace the website logo into simplified, printable colored outlines."""

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent


def area(points):
    return sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(points, points[1:] + points[:1])
    ) / 2


def simplify(points, tolerance):
    if len(points) < 3:
        return points
    first, last = points[0], points[-1]
    dx, dy = last[0] - first[0], last[1] - first[1]
    length = (dx * dx + dy * dy) ** 0.5
    distances = [
        abs(dy * (p[0] - first[0]) - dx * (p[1] - first[1])) / length
        if length else ((p[0] - first[0]) ** 2 + (p[1] - first[1]) ** 2) ** 0.5
        for p in points
    ]
    index = max(range(len(points)), key=distances.__getitem__)
    if distances[index] <= tolerance:
        return [first, last]
    return simplify(points[:index + 1], tolerance)[:-1] + simplify(
        points[index:], tolerance
    )


def contours(mask):
    edges = {}
    for x, y in mask:
        for neighbor, start, end in (
            ((x, y - 1), (x, y), (x + 1, y)),
            ((x + 1, y), (x + 1, y), (x + 1, y + 1)),
            ((x, y + 1), (x + 1, y + 1), (x, y + 1)),
            ((x - 1, y), (x, y + 1), (x, y)),
        ):
            if neighbor not in mask:
                edges.setdefault(start, []).append(end)
    loops = []
    while edges:
        start = min(edges)
        point = start
        loop = []
        while True:
            loop.append(point)
            next_point = edges[point].pop()
            if not edges[point]:
                del edges[point]
            point = next_point
            if point == start:
                break
        if abs(area(loop)) > 4:
            split = len(loop) // 2
            reduced = simplify(loop[:split + 1], 1.5)[:-1]
            reduced += simplify(loop[split:] + [loop[0]], 1.5)[:-1]
            loops.append(reduced)
    return loops


def contains(polygon, point):
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y):
            if x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                inside = not inside
    return inside


def main():
    image = Image.open(ROOT / "assets" / "sur-air-logo.png").convert("RGBA")
    image.thumbnail((700, 100))
    width, height = image.size
    groups = []
    for color in ("red", "white"):
        mask = set()
        for y in range(height):
            for x in range(width):
                r, g, b, alpha = image.getpixel((x, y))
                selected = r > 130 and g < 110 and b < 110 if color == "red" else min(r, g, b) > 180
                if alpha > 128 and selected:
                    mask.add((x, y))
        loops = contours(mask)
        outer = [loop for loop in loops if area(loop) > 0]
        holes = [loop for loop in loops if area(loop) < 0]
        for loop in outer:
            rings = [loop] + [hole for hole in holes if contains(loop, hole[0])]
            groups.append({
                "color": color,
                "rings": [
                    [[round(x / width, 6), round((height - y) / width, 6)] for x, y in ring]
                    for ring in rings
                ],
            })
    result = {"aspect": height / width, "groups": groups}
    (ROOT / "assets" / "logo-contours.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Traced {len(groups)} colored islands from {width} x {height} pixels.")


if __name__ == "__main__":
    main()
