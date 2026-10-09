"""Check native archives and STL geometry with Python 3.14's standard library."""

from collections import Counter
import json
from pathlib import Path
import struct
import zipfile


ROOT = Path(__file__).resolve().parent


def vertices(path):
    data = path.read_bytes()
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * count:
            for index in range(count):
                coords = struct.unpack_from("<9f", data, 84 + 50 * index + 12)
                yield tuple(tuple(coords[i:i + 3]) for i in (0, 3, 6))
            return
    points = [
        tuple(map(float, line.split()[1:]))
        for line in data.decode("ascii").splitlines()
        if line.strip().startswith("vertex ")
    ]
    if not points or len(points) % 3:
        raise ValueError(f"Invalid STL: {path.name}")
    for index in range(0, len(points), 3):
        yield tuple(points[index:index + 3])


def check():
    archives = sorted(ROOT.glob("*.f3d"))
    if len(archives) != 6:
        raise ValueError(f"Expected assembly plus five component archives, found {len(archives)}")
    for path in archives:
        if not zipfile.is_zipfile(path):
            raise ValueError(f"Invalid Fusion archive: {path.name}")
        with zipfile.ZipFile(path) as archive:
            if any(item.compress_type == 93 for item in archive.infolist()) and not hasattr(zipfile, "ZIP_ZSTANDARD"):
                raise RuntimeError("Fusion uses Zstandard ZIP compression. Run this check with Python 3.14 or newer, or inside Fusion's Python environment.")
            damaged = archive.testzip()
            if damaged:
                raise ValueError(f"Damaged Fusion archive: {path.name}: {damaged}")
    parts = json.loads((ROOT / "parts.json").read_text(encoding="utf-8"))
    if len(parts) != 11:
        raise ValueError(f"Expected 11 unique printable parts, found {len(parts)}")
    for part in parts:
        if not part["solid"] or part["volume_cm3"] <= 0:
            raise ValueError(f"Non-solid or empty part: {part['part']}")
        triangles = list(vertices(ROOT / part["file"]))
        if not triangles:
            raise ValueError(f"Empty STL: {part['file']}")
        edges = Counter()
        points = []
        for triangle in triangles:
            rounded = [tuple(round(coord, 5) for coord in point) for point in triangle]
            points.extend(triangle)
            for a, b in zip(rounded, rounded[1:] + rounded[:1]):
                edges[tuple(sorted((a, b)))] += 1
        if any(count != 2 for count in edges.values()):
            raise ValueError(f"Non-watertight STL: {part['file']}")
        size = [
            max(point[axis] for point in points) - min(point[axis] for point in points)
            for axis in range(3)
        ]
        if max(size) > 200.1:
            raise ValueError(f"STL exceeds print envelope: {part['file']}: {size}")
        if any(abs(a - b) > 0.05 for a, b in zip(size, part["size_mm"])):
            raise ValueError(f"STL/CAD dimensions differ: {part['file']}: {size}")
        print(f"{part['part']}: {len(triangles)} triangles, {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm")
    print(f"OK: {len(archives)} native archives, {len(parts)} watertight printable parts.")


if __name__ == "__main__":
    check()
