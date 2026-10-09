"""Run export() inside Fusion to create aligned, color-separated Bambu 3MFs."""

from collections import Counter
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

import adsk.core
import adsk.fusion


ROOT = Path(__file__).resolve().parent
NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
COLORS = [
    ("Panel - gray blue", "#424F5BFF"),
    ("Text and markings - white", "#EBEBE0FF"),
    ("SUR logo - red", "#E21B23FF"),
]


def write_3mf(path, groups):
    """Keep all material meshes in one assembly, at their original coordinates."""
    ET.register_namespace("", NS)

    def element(parent, tag, **attrs):
        return ET.SubElement(parent, f"{{{NS}}}{tag}", {k: str(v) for k, v in attrs.items()})

    model = ET.Element(f"{{{NS}}}model", {"unit": "millimeter", "{http://www.w3.org/XML/1998/namespace}lang": "en-US"})
    resources = element(model, "resources")
    materials = element(resources, "basematerials", id=1)
    for name, color in COLORS:
        element(materials, "base", name=name, displaycolor=color)
    config = ET.Element("config")
    assembly_id = 10
    settings = ET.SubElement(config, "object", {"id": str(assembly_id)})
    ET.SubElement(settings, "metadata", {"key": "name", "value": path.stem})
    ids = []
    for color_index, meshes in sorted(groups.items()):
        object_id = 2 + color_index
        ids.append(object_id)
        name = COLORS[color_index][0]
        obj = element(resources, "object", id=object_id, type="model", name=name, pid=1, pindex=color_index)
        mesh = element(obj, "mesh")
        vertices = element(mesh, "vertices")
        triangles = element(mesh, "triangles")
        offset = 0
        count = 0
        for coords, indices in meshes:
            for x, y, z in coords:
                element(vertices, "vertex", x=f"{x:.7f}", y=f"{y:.7f}", z=f"{z:.7f}")
            for a, b, c in indices:
                element(triangles, "triangle", v1=a + offset, v2=b + offset, v3=c + offset)
            offset += len(coords)
            count += len(indices)
        part = ET.SubElement(settings, "part", {"id": str(object_id), "subtype": "normal_part"})
        ET.SubElement(part, "metadata", {"key": "name", "value": name})
        ET.SubElement(part, "metadata", {"key": "extruder", "value": str(color_index + 1)})
        ET.SubElement(part, "mesh_stat", {"edges_fixed": "0", "degenerate_facets": "0", "facets_removed": "0",
                                        "facets_reversed": "0", "backwards_edges": "0", "number_of_facets": str(count)})
    assembly = element(resources, "object", id=assembly_id, type="model", name=path.stem)
    components = element(assembly, "components")
    for object_id in ids:
        element(components, "component", objectid=object_id)
    element(element(model, "build"), "item", objectid=assembly_id)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '<Default Extension="config" ContentType="application/xml"/>'
        '</Types>'
    )
    relations = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relations)
        archive.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))
        archive.writestr("Metadata/model_settings.config", ET.tostring(config, encoding="utf-8", xml_declaration=True))


def mesh_body(body):
    calc = body.meshManager.createMeshCalculator()
    calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.HighQualityTriangleMesh)
    mesh = calc.calculate()
    if mesh is None:
        raise RuntimeError(f"Cannot tessellate {body.name}")
    raw_coords = [(p.x * 10, p.y * 10, p.z * 10) for p in mesh.nodeCoordinates]
    coords = []
    lookup = {}
    remap = []
    for point in raw_coords:
        key = tuple(round(value, 6) for value in point)
        if key not in lookup:
            lookup[key] = len(coords)
            coords.append(point)
        remap.append(lookup[key])
    indices = mesh.nodeIndices
    faces = [tuple(remap[j] for j in indices[i:i + 3]) for i in range(0, len(indices), 3)]
    edges = Counter()
    for face in faces:
        if len(set(face)) != 3:
            raise RuntimeError(f"Color body has a degenerate triangle: {body.name}")
        for a, b in zip(face, face[1:] + face[:1]):
            edges[tuple(sorted((a, b)))] += 1
    if not faces or any(value != 2 for value in edges.values()):
        raise RuntimeError(f"Color body has a non-watertight mesh: {body.name}")
    return coords, faces


def export():
    app = adsk.core.Application.get()
    original = app.activeDocument
    imported = app.importManager.importToNewDocument(
        app.importManager.createFusionArchiveImportOptions(str(ROOT / "sur-air-panel-assembly.f3d"))
    )
    if imported is None:
        raise RuntimeError("Cannot reopen source assembly.")
    imported.name = "SUR Air - Multicolor print parts"
    design = adsk.fusion.Design.cast(imported.products.itemByProductType("DesignProductType"))
    output = ROOT / "multicolor"
    output.mkdir(exist_ok=True)
    report = []
    try:
        modules = sorted(
            [c for c in design.allComponents if c.name.startswith(("01 ", "02 ", "03 ", "06 "))],
            key=lambda c: c.name,
        )
        if len(modules) != 4:
            raise RuntimeError("Expected four faceplate modules.")
        for comp in modules:
            body = next(b for b in comp.bRepBodies if b.name.endswith(" faceplate"))
            volume = body.volume
            plane_input = comp.constructionPlanes.createInput()
            plane_input.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByString("3 mm"))
            plane = comp.constructionPlanes.add(plane_input)
            feature = comp.features.splitBodyFeatures.add(comp.features.splitBodyFeatures.createInput(body, plane, True))
            feature.name = "Separate panel, lettering and logo for multicolor printing"
            groups = {}
            actual_volume = 0
            counts = Counter()
            for split in feature.bodies:
                if not split.isSolid:
                    raise RuntimeError(f"Split produced a non-solid body in {comp.name}")
                actual_volume += split.volume
                bounds = split.boundingBox
                if bounds.maxPoint.z <= 0.30001:
                    color_index = 0
                else:
                    # The logo's top is at 3.6 mm; lettering and guides at 3.45 mm.
                    top = max(split.faces, key=lambda f: f.boundingBox.maxPoint.z)
                    color_index = 2 if top.appearance.name == "SUR 226-27-35" else 1
                    if bounds.minPoint.z < 0.29999:
                        raise RuntimeError(f"Detail overlaps the base in {comp.name}")
                counts[color_index] += 1
                split.name = COLORS[color_index][0] + f" - {counts[color_index]:03d}"
                groups.setdefault(color_index, []).append(mesh_body(split))
            if abs(actual_volume - volume) > 1e-6:
                raise RuntimeError(f"Color separation changed faceplate volume in {comp.name}")
            expected = {0, 1, 2} if comp.name.startswith("01 ") else {0, 1}
            if set(groups) != expected:
                raise RuntimeError(f"Missing expected colors in {comp.name}: {set(groups)}")
            path = output / (comp.name.lower().replace(" ", "-") + ".3mf")
            write_3mf(path, groups)
            report.append({"file": path.name, "color_parts": [COLORS[i][0] for i in sorted(groups)],
                           "solid_bodies": sum(counts.values()), "volume_cm3": round(volume, 6)})
            plane.isLightBulbOn = False
            adsk.doEvents()
        archive = output / "sur-air-color-separated.f3d"
        if not design.exportManager.execute(design.exportManager.createFusionArchiveExportOptions(str(archive))):
            raise RuntimeError("Could not export color-separated Fusion assembly.")
        (output / "parts.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        app.activeViewport.fit()
        return report
    except Exception:
        if original:
            original.activate()
        raise


if __name__ == "__main__":
    export()
