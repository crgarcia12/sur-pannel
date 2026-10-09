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
    if len(archives) != 9:
        raise ValueError(f"Expected assembly plus eight component archives, found {len(archives)}")
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
    if len(parts) != 23:
        raise ValueError(f"Expected 23 unique printable parts, found {len(parts)}")
    expected = {
        "01 LIGHTS AND SIGNS faceplate": (180, 150, 3.6),
        "02 FCU SPEED HEADING faceplate": (190, 150, 3.45),
        "03 FCU ALTITUDE VERTICAL faceplate": (210, 150, 3.45),
        "06 APU faceplate": (180, 100, 3.45),
        "ALTITUDE increment selector collar": (36, 36, 5),
    }
    for part in parts:
        if part["part"] in expected and any(
            abs(a - b) > 0.05 for a, b in zip(part["size_mm"], expected[part["part"]])
        ):
            raise ValueError(f"Required module dimensions changed: {part['part']}")
    if not set(expected).issubset({part["part"] for part in parts}):
        raise ValueError("Required FCU, APU or altitude-collar parts are missing.")
    if len(list((ROOT / "stl").glob("*.stl"))) != len(parts):
        raise ValueError("STL directory contains stale or missing exports.")
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
        if max(size) > 220.1:
            raise ValueError(f"STL exceeds print envelope: {part['file']}: {size}")
        if any(abs(a - b) > 0.05 for a, b in zip(size, part["size_mm"])):
            raise ValueError(f"STL/CAD dimensions differ: {part['file']}: {size}")
        print(f"{part['part']}: {len(triangles)} triangles, {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm")
    print(f"OK: {len(archives)} native archives, {len(parts)} watertight printable parts.")


def check_fusion_design(design):
    """Check actual bores and separated optical paths inside Fusion."""
    import adsk.core
    import adsk.fusion

    components = {comp.name: comp for comp in design.allComponents}

    def expect(body, x, y, z, inside):
        point = adsk.core.Point3D.create(x / 10, y / 10, z / 10)
        expected = (
            adsk.fusion.PointContainment.PointInsidePointContainment if inside
            else adsk.fusion.PointContainment.PointOutsidePointContainment
        )
        if body.pointContainment(point) != expected:
            raise ValueError(f"Unexpected material at {body.name}: {(x, y, z)}")

    for name, points in (
        ("02 FCU SPEED HEADING", [(56, 66), (120, 66), (15, 86), (130, 18), (177, 62)]),
        ("03 FCU ALTITUDE VERTICAL", [(88, 66), (170, 66), (10, 86), (122, 86),
                                    (29, 62), (10, 27), (91, 18), (173, 18)]),
    ):
        body = components[name].bRepBodies.itemByName(name + " faceplate")
        for x, y in points:
            expect(body, x, y, 1.5, False)

    caps = components["07 APU ILLUMINATED CAPS"]
    apu_face = components["06 APU"].bRepBodies.itemByName("06 APU faceplate")
    for x, label in ((37, "MASTER SW"), (90, "START"), (143, "APU BLEED")):
        body = caps.bRepBodies.itemByName(label + " illuminated cap")
        expect(apu_face, x, 45, 1.5, False)
        expect(body, x, 45, 1, False)
        expect(body, x, 45, 4, True)
        expect(body, x - 11, 45, 4, True)
        for y in (39, 51):
            expect(body, x, y, 1, False)
            expect(body, x, y, 4, False)
            expect(body, x, y, 8.5, False)
            expect(body, x + 9.5, y, 8.5, True)
    issues = [
        (comp.name, feature.name, feature.errorOrWarningMessage)
        for comp in design.allComponents for feature in comp.features
        if feature.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState
    ]
    if issues:
        raise ValueError(f"Unhealthy Fusion features: {issues}")
    print("OK: authentic FCU bore positions, APU cap clearance, LED bores, open light windows and opaque optical partitions.")


if __name__ == "__main__":
    check()
