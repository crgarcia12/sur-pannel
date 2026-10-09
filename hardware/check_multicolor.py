"""Validate multipart 3MF geometry, material groups and preserved print placement."""

from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parent
NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


def check():
    reports = json.loads((ROOT / "multicolor" / "parts.json").read_text(encoding="utf-8"))
    if len(reports) != 4:
        raise ValueError("Expected four multicolor faceplates.")
    for report in reports:
        with zipfile.ZipFile(ROOT / "multicolor" / report["file"]) as archive:
            if archive.testzip() is not None:
                raise ValueError("Damaged 3MF archive.")
            model = ET.fromstring(archive.read("3D/3dmodel.model"))
            settings = ET.fromstring(archive.read("Metadata/model_settings.config"))
        if model.get("unit") != "millimeter":
            raise ValueError("3MF units are not millimeters.")
        materials = model.findall("m:resources/m:basematerials/m:base", NS)
        objects = model.findall("m:resources/m:object", NS)
        meshes = [obj for obj in objects if obj.find("m:mesh", NS) is not None]
        if [obj.get("name") for obj in meshes] != report["color_parts"]:
            raise ValueError("Named material parts differ from the export report.")
        volume = 0
        base_top = None
        detail_bottoms = []
        for obj in meshes:
            color = int(obj.get("pindex"))
            if obj.get("pid") != "1" or not materials[color].get("displaycolor").startswith("#"):
                raise ValueError("Missing material/color assignment.")
            vertices = [
                tuple(float(v.get(axis)) for axis in ("x", "y", "z"))
                for v in obj.findall("m:mesh/m:vertices/m:vertex", NS)
            ]
            faces = [
                tuple(int(t.get(axis)) for axis in ("v1", "v2", "v3"))
                for t in obj.findall("m:mesh/m:triangles/m:triangle", NS)
            ]
            edges = Counter()
            directed = Counter()
            for face in faces:
                if len(set(face)) != 3 or any(i < 0 or i >= len(vertices) for i in face):
                    raise ValueError("Invalid triangle indices.")
                for a, b in zip(face, face[1:] + face[:1]):
                    edges[tuple(sorted((a, b)))] += 1
                    directed[(a, b)] += 1
                a, b, c = [vertices[i] for i in face]
                volume += (
                    a[0] * (b[1] * c[2] - b[2] * c[1])
                    - a[1] * (b[0] * c[2] - b[2] * c[0])
                    + a[2] * (b[0] * c[1] - b[1] * c[0])
                ) / 6
            if any(n != 2 for n in edges.values()) or any(directed[(b, a)] != n for (a, b), n in directed.items()):
                raise ValueError(f"Non-manifold or inconsistent winding in {obj.get('name')}.")
            if color == 0:
                base_top = max(v[2] for v in vertices)
                if abs(min(v[2] for v in vertices)) > 1e-5:
                    raise ValueError("Panel is not placed on the bed.")
            else:
                detail_bottoms.append(min(v[2] for v in vertices))
        if abs(base_top - 3) > 1e-5 or any(abs(z - base_top) > 1e-5 for z in detail_bottoms):
            raise ValueError("Color details are misaligned or overlap the panel.")
        if abs(volume / 1000 - report["volume_cm3"]) > 0.05:
            raise ValueError("Mesh volume differs from original CAD.")
        assembly = next(obj for obj in objects if obj.find("m:components", NS) is not None)
        ids = {obj.get("id") for obj in meshes}
        if {c.get("objectid") for c in assembly.findall("m:components/m:component", NS)} != ids:
            raise ValueError("Assembly does not reference all color parts.")
        if model.find("m:build/m:item", NS).get("objectid") != assembly.get("id"):
            raise ValueError("Build must contain one aligned assembly.")
        if {p.get("id") for p in settings.findall("object/part")} != ids:
            raise ValueError("Bambu part metadata does not match geometry.")
        print(f"OK: {report['file']}: {len(meshes)} color parts, welded closed meshes, preserved placement and volume.")


if __name__ == "__main__":
    check()
