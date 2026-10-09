"""Run build() in Fusion 360's Python environment; dimensions are millimeters."""

import json
from pathlib import Path
import zipfile

import adsk.core
import adsk.fusion


ROOT = Path(__file__).resolve().parent
GRAY = (66, 79, 91)
WHITE = (235, 235, 224)
BLACK = (14, 20, 23)
AMBER = (255, 171, 54)
GREEN = (97, 216, 126)
RED = (226, 27, 35)


def build():
    app = adsk.core.Application.get()

    def stage(name):
        (ROOT / ".build-status.json").write_text(json.dumps({"stage": name}), encoding="utf-8")
        adsk.doEvents()

    stage("Creating new Fusion document")
    document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    document.name = "SUR Air - Modular Airbus Panel"
    design = adsk.fusion.Design.cast(app.activeProduct)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    root = design.rootComponent
    for name, value, description in (
        ("faceThickness", "3 mm", "Printable faceplate thickness"),
        ("caseDepth", "42 mm", "Rear enclosure depth"),
        ("wallThickness", "3 mm", "Rear enclosure wall"),
        ("switchBore", "6.5 mm", "Provisional toggle-switch mounting bore"),
        ("encoderBore", "7.2 mm", "Provisional encoder mounting bore"),
        ("buttonBore", "12.2 mm", "Provisional pushbutton mounting bore"),
        ("mountBore", "3.4 mm", "M3 through-bolt clearance"),
        ("shaftBore", "6.2 mm", "Provisional round encoder shaft socket"),
    ):
        design.userParameters.add(name, adsk.core.ValueInput.createByString(value), "mm", description)

    def pt(x, y, z=0):
        return adsk.core.Point3D.create(x / 10, y / 10, z / 10)

    def collection(items):
        result = adsk.core.ObjectCollection.create()
        for item in items:
            result.add(item)
        return result

    appearances = {}

    def appearance_for(rgb):
        if rgb not in appearances:
            library = app.materialLibraries.itemByName("Fusion Appearance Library")
            if library is None:
                raise RuntimeError("Fusion Appearance Library is unavailable.")
            base = library.appearances.itemByName("Plastic - Matte (Gray)")
            if base is None:
                raise RuntimeError("Fusion matte-plastic appearance is unavailable.")
            appearance = design.appearances.addByCopy(base, "SUR " + "-".join(map(str, rgb)))
            prop = adsk.core.ColorProperty.cast(appearance.appearanceProperties.itemByName("Color"))
            if prop is None:
                raise RuntimeError("Appearance has no editable Color property.")
            prop.value = adsk.core.Color.create(*rgb, 255)
            appearances[rgb] = appearance
        return appearances[rgb]

    def color(body, rgb):
        body.appearance = appearance_for(rgb)

    def feature_color(feature, rgb):
        appearance = appearance_for(rgb)
        for surface in list(feature.sideFaces) + list(feature.endFaces):
            surface.appearance = appearance

    def component(name, x=0, y=0, z=0):
        transform = adsk.core.Matrix3D.create()
        transform.translation = adsk.core.Vector3D.create(x / 10, y / 10, z / 10)
        comp = root.occurrences.addNewComponent(transform).component
        comp.name = name
        return comp

    def sketch(comp, name, z=0):
        if z:
            plane_input = comp.constructionPlanes.createInput()
            plane_input.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByString(f"{z} mm"))
            plane = comp.constructionPlanes.add(plane_input)
        else:
            plane = comp.xYConstructionPlane
        result = comp.sketches.add(plane)
        result.name = name
        return result

    def rectangle(sk, x, y, w, h):
        sk.sketchCurves.sketchLines.addTwoPointRectangle(pt(x, y), pt(x + w, y + h))

    def extrude(comp, profiles, distance, name, operation=None, targets=None):
        operation = operation if operation is not None else adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        inp = comp.features.extrudeFeatures.createInput(profiles, operation)
        value = adsk.core.ValueInput.createByString(distance if isinstance(distance, str) else f"{distance} mm")
        inp.setDistanceExtent(False, value)
        if targets:
            inp.participantBodies = targets
        feature = comp.features.extrudeFeatures.add(inp)
        feature.name = name
        return feature

    def box(comp, name, x, y, z, w, h, depth, rgb):
        sk = sketch(comp, name + " footprint", z)
        rectangle(sk, x, y, w, h)
        feature = extrude(comp, sk.profiles.item(0), depth, name)
        body = feature.bodies.item(0)
        body.name = name
        color(body, rgb)
        sk.isVisible = False
        return body

    def cylinder(comp, name, x, y, z, radius, depth, rgb):
        sk = sketch(comp, name + " footprint", z)
        sk.sketchCurves.sketchCircles.addByCenterRadius(pt(x, y), radius / 10)
        body = extrude(comp, sk.profiles.item(0), depth, name).bodies.item(0)
        body.name = name
        color(body, rgb)
        sk.isVisible = False
        return body

    def holes(comp, body, coords, diameter, name, z=3, depth=-3):
        sk = sketch(comp, name, z)
        sk.isComputeDeferred = True
        for x, y in coords:
            circle = sk.sketchCurves.sketchCircles.addByCenterRadius(pt(x, y), diameter / 20)
            parameter = {6.5: "switchBore", 7.2: "encoderBore", 12.2: "buttonBore",
                         3.4: "mountBore", 6.2: "shaftBore"}.get(diameter)
            if parameter:
                dimension = sk.sketchDimensions.addDiameterDimension(circle, pt(x + diameter, y + diameter))
                dimension.parameter.expression = parameter
        sk.isComputeDeferred = False
        extrude(comp, collection([sk.profiles.item(i) for i in range(sk.profiles.count)]), depth, name + " cut",
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])
        sk.isVisible = False

    def cut_rectangle(comp, body, x, y, w, h, name, z=3, depth=-3):
        sk = sketch(comp, name, z)
        rectangle(sk, x, y, w, h)
        extrude(comp, sk.profiles.item(0), depth, name + " cut",
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])
        sk.isVisible = False

    faceplates = {}

    def text(comp, label, x, y, size=3, rgb=WHITE, z=3):
        sk = sketch(comp, "Legend " + label, z)
        inp = sk.sketchTexts.createInput2(label, size / 10)
        inp.fontName = "Arial"
        inp.setAsMultiLine(pt(x, y), pt(x + max(20, len(label) * size), y + size * 1.8),
                           adsk.core.HorizontalAlignments.LeftHorizontalAlignment,
                           adsk.core.VerticalAlignments.BottomVerticalAlignment, 0)
        sk.sketchTexts.add(inp)
        target = faceplates.get(comp.name) if z >= 3 else None
        feature = extrude(comp, collection([sk.sketchTexts.item(0)]), 0.45, "Raised legend " + label,
                          adsk.fusion.FeatureOperations.JoinFeatureOperation if target else None,
                          [target] if target else None)
        if target:
            feature_color(feature, rgb)
        else:
            for body in feature.bodies:
                body.name = "Legend - " + label
                color(body, rgb)
        sk.isVisible = False

    def line(comp, name, x, y, w, h=0.7):
        return box(comp, name, x, y, 3, w, h, 0.45, WHITE)

    def rounded(body, comp, radius):
        vertical = []
        for edge in body.edges:
            bounds = edge.boundingBox
            if bounds.maxPoint.z - bounds.minPoint.z > 0.25 and abs(bounds.maxPoint.x - bounds.minPoint.x) < 0.001 and abs(bounds.maxPoint.y - bounds.minPoint.y) < 0.001:
                vertical.append(edge)
        if vertical:
            inp = comp.features.filletFeatures.createInput()
            inp.addConstantRadiusEdgeSet(collection(vertical), adsk.core.ValueInput.createByString(f"{radius} mm"), True)
            comp.features.filletFeatures.add(inp)

    modules = []
    for title, x, width in (("01 LIGHTS AND SIGNS", 0, 180), ("02 FCU SPEED HEADING", 180, 200), ("03 FCU ALTITUDE VERTICAL", 380, 200)):
        stage("Building " + title)
        comp = component(title, x)
        face = box(comp, title + " faceplate", 0, 0, 0, width, 150, "faceThickness", GRAY)
        rounded(face, comp, 4)
        mounts = [(7, 7), (width - 7, 7), (7, 143), (width - 7, 143)]
        holes(comp, face, mounts, 3.4, "Face M3 mounting holes")
        tray = box(comp, title + " rear tray", 0, 0, -42, width, 150, "caseDepth", GRAY)
        rounded(tray, comp, 4)
        cut_rectangle(comp, tray, 3, 3, width - 6, 144, "Tray cavity", 0, "-caseDepth + wallThickness")
        for i, (mx, my) in enumerate(mounts):
            boss = cylinder(comp, title + f" bolt column {i + 1}", mx, my, -39, 5, 39, GRAY)
            combine = comp.features.combineFeatures.createInput(tray, collection([boss]))
            combine.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
            comp.features.combineFeatures.add(combine)
        holes(comp, tray, mounts, 3.4, "Tray M3 through holes", 0, -42)
        cut_rectangle(comp, tray, width / 2 - 10, 5, 20, 10, "Rear cable exit", -39, -3)
        for label, y in (("Lower join", 28), ("Upper join", 112)):
            holes(comp, tray, [(11, y), (width - 11, y)], 3.4, label + " rear bridge bolts", -39, -3)
        modules.append((comp, face))
        faceplates[comp.name] = face

    light, light_face = modules[0]
    stage("Adding lights, signs and call controls")
    text(light, "LIGHTS", 14, 130, 4)
    line(light, "Lights rule", 14, 125, 152)
    switches = [(25, 101, "LAND"), (67, 101, "TAXI"), (109, 101, "STROBE"), (151, 101, "BEACON")]
    holes(light, light_face, [(x, y) for x, y, _ in switches], 6.5, "Light toggle bores")
    previews = component("VISUAL REFERENCES - switches and buttons - NOT PRINTABLE")

    def toggle(x, y):
        cylinder(previews, "Toggle retaining nut reference", x, y, 3, 5, 2, BLACK)
        cylinder(previews, "Toggle lever reference", x, y, 5, 1.4, 13, WHITE)
        cylinder(previews, "Airbus toggle cap reference", x, y, 14, 3, 7, WHITE)

    for x, y, label in switches:
        toggle(x, y)
        text(light, label, x - 13, 113, 2.6)
        text(light, "ON", x - 4, 84, 2.2)
    text(light, "SIGNS / CALLS", 14, 66, 4)
    line(light, "Signs rule", 14, 61, 152)
    holes(light, light_face, [(30, 37)], 6.5, "Seatbelt toggle bore")
    holes(light, light_face, [(87, 37), (145, 37)], 12.2, "Call pushbutton bores")
    toggle(30, 37)
    text(light, "SEATBELT", 16, 49, 2.5)
    text(light, "MECH", 76, 49, 2.5)
    text(light, "FWD", 136, 49, 2.5)

    def button(comp, face, offset, x, y, label, label_size=2.4):
        holes(comp, face, [(x, y)], 12.2, label + " button bore")
        box(previews, label + " square button reference", offset + x - 7, y - 7, 3, 14, 14, 5, BLACK)
        box(previews, label + " annunciator reference", offset + x - 4, y - 1, 8, 8, 1.4, 0.2, GREEN)
        text(comp, label, x - 8, y + 10, label_size)

    for x, label in ((87, "MECH"), (145, "FWD")):
        box(previews, label + " call button reference", x - 7, 30, 3, 14, 14, 5, BLACK)

    left, left_face = modules[1]
    right, right_face = modules[2]
    stage("Adding FCU controls and legends")
    for comp, face, offset, fields in (
        (left, left_face, 180, ((18, "SPD / MACH", "250", 49), (112, "HDG / TRK", "180", 143))),
        (right, right_face, 380, ((18, "ALT", "12000", 49), (112, "V/S / FPA", "+1500", 143))),
    ):
        for dx, label, digits, knob_x in fields:
            text(comp, label, dx, 131, 3.2)
            cut_rectangle(comp, face, dx, 104, 68, 20, label + " display aperture")
            box(previews, label + " display reference", offset + dx, 104, 1, 68, 20, 1, BLACK)
            text(comp, digits, dx + 7, 106, 8, AMBER, 2)
            holes(comp, face, [(knob_x, 71)], 7.2, label + " encoder bore")
            text(comp, "PUSH LEVEL OFF" if label == "V/S / FPA" else "PUSH MANAGED", knob_x - 26, 49, 2.3)
            text(comp, "PULL V/S-FPA" if label == "V/S / FPA" else "PULL SELECTED", knob_x - 26, 42, 2.3)
        line(comp, "FCU lower rule", 15, 35, 170)
    button(left, left_face, 180, 25, 18, "FD")
    button(left, left_face, 180, 67, 18, "LS")
    button(left, left_face, 180, 111, 18, "LOC")
    button(left, left_face, 180, 160, 18, "APPR")
    button(right, right_face, 380, 25, 18, "AP1")
    button(right, right_face, 380, 67, 18, "AP2")
    button(right, right_face, 380, 111, 18, "A/THR")
    button(right, right_face, 380, 160, 18, "EXPED")
    button(left, left_face, 180, 95, 89, "SPD/MACH", 1.9)
    button(right, right_face, 380, 95, 89, "HDG/TRK", 1.9)
    holes(right, right_face, [(92, 59)], 6.5, "Altitude increment selector bore")
    toggle(380 + 92, 59)
    text(right, "100 / 1000", 79, 47, 2)

    knobs = component("04 PRINTABLE FCU KNOBS")
    stage("Building printable FCU knobs")
    for name, x, radius, style in (
        ("SPEED", 229, 12, "round"),
        ("HEADING", 323, 12, "round"),
        ("ALTITUDE", 429, 14, "round"),
        ("VERTICAL SPEED", 523, 11, "square"),
    ):
        if style == "square":
            body = box(knobs, name + " knob", x - 11, 60, 5, 22, 22, 18, WHITE)
            rounded(body, knobs, 3)
        else:
            body = cylinder(knobs, name + " knob", x, 71, 5, radius, 18, WHITE)
        holes(knobs, body, [(x, 71)], 6.2, name + " shaft socket", 5, 14)
        if style == "round":
            import math
            scallops = []
            for n in range(12):
                angle = n * math.pi / 6
                scallops.append((x + (radius + 0.9) * math.cos(angle), 71 + (radius + 0.9) * math.sin(angle)))
            holes(knobs, body, scallops, 3.6, name + " grip scallops", 23, -18)

    logo = json.loads((ROOT / "assets" / "logo-contours.json").read_text(encoding="utf-8"))
    for i, group in enumerate(logo["groups"]):
        stage(f"Building logo island {i + 1} of {len(logo['groups'])}")
        sk = sketch(light, f"SUR Air logo outline {i + 1}", 3)
        sk.isComputeDeferred = True
        for ring in group["rings"]:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                sk.sketchCurves.sketchLines.addByTwoPoints(pt(51 + a[0] * 76, 17 + a[1] * 76),
                                                          pt(51 + b[0] * 76, 17 + b[1] * 76))
        sk.isComputeDeferred = False
        profile = max([sk.profiles.item(j) for j in range(sk.profiles.count)], key=lambda p: p.areaProperties().area)
        feature = extrude(light, profile, 0.6, f"SUR Air logo island {i + 1}",
                          adsk.fusion.FeatureOperations.JoinFeatureOperation, [light_face])
        feature_color(feature, RED if group["color"] == "red" else WHITE)
        sk.isVisible = False

    bridges = component("05 PRINTABLE REAR JOINING BRIDGES")
    stage("Building joining bridges")
    bridge = box(bridges, "Rear joining bridge - print four", 166, 20, -45, 28, 16, 3, GRAY)
    holes(bridges, bridge, [(169, 28), (191, 28)], 3.4, "Bridge M3 bolt holes", -42, -3)
    for x, y in ((180, 112), (380, 28), (380, 112)):
        body = box(bridges, f"Rear bridge at {x} {y}", x - 14, y - 8, -45, 28, 16, 3, GRAY)
        holes(bridges, body, [(x - 11, y), (x + 11, y)], 3.4, "Bridge M3 holes", -42, -3)

    for comp, face in modules:
        stage("Joining raised legends to " + comp.name)
        decorations = [
            body for body in comp.bRepBodies
            if body != face and body.name.startswith(("Lights rule", "Signs rule", "FCU lower rule"))
            and body.boundingBox.minPoint.z >= 0.299
        ]
        for body in decorations:
            for surface in body.faces:
                surface.appearance = body.appearance
        if decorations:
            inp = comp.features.combineFeatures.createInput(face, collection(decorations))
            inp.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
            comp.features.combineFeatures.add(inp)

    return export_design(design)


def export_design(design):
    """Export an already-built design without repeating expensive modeling."""
    app = adsk.core.Application.get()
    root = design.rootComponent

    def stage(name):
        (ROOT / ".build-status.json").write_text(json.dumps({"stage": name}), encoding="utf-8")
        adsk.doEvents()

    components = list(design.allComponents)
    modules = sorted(
        [comp for comp in components if comp.name.startswith(("01 ", "02 ", "03 "))],
        key=lambda comp: comp.name,
    )
    knobs = next(comp for comp in components if comp.name.startswith("04 "))
    bridges = next(comp for comp in components if comp.name.startswith("05 "))
    previews = next(comp for comp in components if comp.name.startswith("VISUAL REFERENCES"))
    printable = [
        (comp, body) for comp in modules for body in comp.bRepBodies
        if body.name.endswith((" faceplate", " rear tray"))
    ]
    printable += [(knobs, body) for body in knobs.bRepBodies if body.name.endswith(" knob")]
    printable += [(bridges, bridges.bRepBodies.itemByName("Rear joining bridge - print four"))]
    if len(modules) != 3 or len(printable) != 11 or any(body is None for _, body in printable):
        raise RuntimeError("The active design does not contain the complete expected SUR Air part set.")

    white = design.appearances.itemByName("SUR 235-235-224")
    if white is None:
        raise RuntimeError("White legend appearance is missing from the design.")
    for comp in modules:
        faceplate = next(body for body in comp.bRepBodies if body.name.endswith(" faceplate"))
        for surface in faceplate.faces:
            bounds = surface.boundingBox
            if (bounds.minPoint.z >= 0.2999 and 0.3449 <= bounds.maxPoint.z < 0.3501
                    and surface.appearance.id != white.id):
                surface.appearance = white

    for comp in components:
        for sk in comp.sketches:
            sk.isVisible = False
        for plane in comp.constructionPlanes:
            plane.isLightBulbOn = False
    previews.isBodiesFolderLightBulbOn = True
    root.isConstructionFolderLightBulbOn = False
    camera = app.activeViewport.camera
    camera.cameraType = adsk.core.CameraTypes.OrthographicCameraType
    camera.eye = adsk.core.Point3D.create(29, 7.5, 90)
    camera.target = adsk.core.Point3D.create(29, 7.5, 0)
    camera.upVector = adsk.core.Vector3D.create(0, 1, 0)
    camera.isFitView = True
    app.activeViewport.camera = camera
    app.activeViewport.visualStyle = adsk.core.VisualStyles.ShadedVisualStyle
    app.activeViewport.fit()

    output = ROOT / "stl"
    stage("Exporting printable STL parts")
    output.mkdir(exist_ok=True)
    manager = design.exportManager
    report = []
    for comp, body in printable:
        name = body.name.lower().replace(" ", "-")
        path = output / f"{name}.stl"
        opts = manager.createSTLExportOptions(body, str(path))
        opts.isBinaryFormat = True
        opts.meshRefinement = adsk.fusion.MeshRefinementSettings.MeshRefinementHigh
        if not manager.execute(opts):
            raise RuntimeError(f"STL export failed: {path}")
        bounds = body.boundingBox
        size = [round((getattr(bounds.maxPoint, axis) - getattr(bounds.minPoint, axis)) * 10, 3) for axis in ("x", "y", "z")]
        if max(size) > 200.1:
            raise RuntimeError(f"Part exceeds the conservative 200 mm print envelope: {body.name}: {size}")
        report.append({"part": body.name, "file": str(path.relative_to(ROOT)), "size_mm": size,
                       "solid": body.isSolid, "volume_cm3": round(body.volume, 3)})

    archive = ROOT / "sur-air-panel-assembly.f3d"
    stage("Exporting native Fusion archives")

    def export_archive(path, comp=None):
        if path.exists():
            path.unlink()
        success = manager.execute(manager.createFusionArchiveExportOptions(str(path), comp))
        if not path.exists() or not zipfile.is_zipfile(path):
            raise RuntimeError(f"Fusion archive export failed: {path}")
        with zipfile.ZipFile(path) as contents:
            if contents.testzip() is not None:
                raise RuntimeError(f"Fusion archive is damaged: {path}")
        if not success:
            original = app.activeDocument
            imported = app.importManager.importToNewDocument(
                app.importManager.createFusionArchiveImportOptions(str(path))
            )
            if imported is None:
                raise RuntimeError(f"Fusion reported failure and the archive cannot be reopened: {path}")
            try:
                reopened = adsk.fusion.Design.cast(imported.products.itemByProductType("DesignProductType"))
                actual = sorted((body.name, round(body.volume, 4)) for c in reopened.allComponents for body in c.bRepBodies)
                source = [comp] if comp else components
                expected = sorted((body.name, round(body.volume, 4)) for c in source for body in c.bRepBodies)
                if actual != expected:
                    raise RuntimeError(f"Reopened Fusion archive differs from its source geometry: {path}")
            finally:
                original.activate()
                imported.close(False)
            print(f"WARNING: Fusion reported export failure for {path.name}; native reimport verified all body names and volumes.")

    export_archive(archive)
    for comp in modules:
        path = ROOT / (comp.name.lower().replace(" ", "-") + ".f3d")
        export_archive(path, comp)
    for comp in (knobs, bridges):
        path = ROOT / (comp.name.lower().replace(" ", "-") + ".f3d")
        export_archive(path, comp)
    (ROOT / "parts.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not app.activeViewport.saveAsImageFile(str(ROOT / "assembly-preview.png"), 1800, 900):
        raise RuntimeError("Front preview could not be saved.")
    camera = app.activeViewport.camera
    camera.eye = adsk.core.Point3D.create(80, -65, 80)
    camera.target = adsk.core.Point3D.create(29, 7.5, -1.1)
    camera.upVector = adsk.core.Vector3D.create(0, 0, 1)
    camera.isFitView = True
    app.activeViewport.camera = camera
    app.activeViewport.fit()
    if not app.activeViewport.saveAsImageFile(str(ROOT / "assembly-isometric.png"), 1800, 1000):
        raise RuntimeError("Isometric preview could not be saved.")
    stage("Complete")
    return {"archive": str(archive), "parts": report, "bodies": sum(comp.bRepBodies.count for comp in components),
            "components": design.allComponents.count, "timeline": design.timeline.count}


if __name__ == "__main__":
    build()
