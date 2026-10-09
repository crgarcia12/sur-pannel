# Hardware - Airbus-inspired SUR Air panel

The first revision is a **mechanical concept**, with real printable geometry
and provisional electronics interfaces. It is not a finished electronics
assembly or an exact Airbus replica.

![Assembly](assembly-preview.png)

[Isometric assembly view](assembly-isometric.png)

## Layout

Three independently printable modules join into a **580 x 150 mm** desktop
panel. The faceplates are 3 mm thick; rear trays are 42 mm deep with 3 mm
walls. No individual exported part exceeds a conservative 200 x 200 mm
footprint, leaving ample room on the H2C for a brim.

| Module | Faceplate | Controls |
|---|---|---|
| Lights and signs | 180 x 150 mm | LAND, TAXI, STROBE, BEACON; SEATBELT; MECH and FWD call buttons |
| FCU speed and heading | 200 x 150 mm | SPD/MACH and HDG/TRK displays and knobs; SPD/MACH mode; FD, LS, LOC, APPR |
| FCU altitude and vertical speed | 200 x 150 mm | ALT and V/S/FPA displays and knobs; HDG/TRK mode; 100/1000 selector; AP1, AP2, A/THR, EXPED |

The gray-blue faceplates, white legends, amber display references, scalloped
rotary knobs, square vertical-speed knob, and square annunciator buttons
follow Airbus visual cues. The actual red/white SUR Air website logo is
traced and raised on the lights/signs faceplate.

MECH and FWD are treated as momentary calls, not maintained cabin signs.
The initial switches are simple ON/OFF references; Airbus three-position
switch behavior can be added once switch models and simulator mappings
are selected.

## Files

- `sur-air-panel-assembly.f3d`: native editable assembly, including all modules.
- `01-*.f3d`, `02-*.f3d`, `03-*.f3d`: individual module archives.
- `04-*.f3d`: four printable knob designs.
- `05-*.f3d`: rear joining bridges.
- `stl/`: faceplates, trays, knobs, and one bridge design; print four bridges.
- `parts.json`: measured dimensions and solid-body information for exported parts.
- `check_exports.py`: verify native archive integrity, STL dimensions and watertightness.
- `build_panel.py`: reproducible Fusion 360 Python source with an editable timeline.
- `assets/sur-air-logo.png`: original logo downloaded from
  <https://www.sur-air.com/img/logo_sur_air_dark.png?v=2>.
- `assets/logo-contours.json`: simplified red/white print geometry.
- `trace_logo.py`: regenerate logo outlines with Python and Pillow.

The logo belongs to SUR Air; no ownership or license is asserted for that asset.

## Provisional parts and interfaces

| Interface | Initial geometry | Selection needed |
|---|---|---|
| Light/seatbelt switches and altitude selector | 6.5 mm bore | Threaded miniature toggle switches and retaining nuts |
| Four FCU encoders | 7.2 mm mounting bore | Encoders with actual push/pull mechanism or a separately designed mechanism |
| Twelve pushbuttons | 12.2 mm bore | Two call buttons, eight lower FCU buttons, two mode buttons; square external caps |
| Display apertures | Four 68 x 20 mm windows | Actual displays, carrier boards and fasteners |
| Knob sockets | 6.2 mm round bore, 14 mm deep | Verify shaft diameter, retention and fit with a small test print |
| Face/tray mounting | Four 3.4 mm through-holes per module | M3 bolts, nuts and washers |
| Rear bridge mounting | Two 3.4 mm holes per bridge | Four bridges and eight short M3 bolts with nuts |
| Cable routing | One 20 x 10 mm rear exit per module | Cable, strain relief and connectors |

The displayed digits, switch levers, button references and annunciators
are **visual references**, not purchased hardware or printable functioning
mechanisms. In Fusion, hide the component named
`VISUAL REFERENCES - switches and buttons - NOT PRINTABLE` to inspect the
mounting holes. Display digits remain separate reference bodies in the
FCU components and are excluded from faceplate STL exports.

Push/pull legends describe the intended FCU interaction. The printable
knobs alone do not implement that motion. Electronics, display mounts,
encoder retention, switch anti-rotation features and strain relief must
be designed after the actual components are chosen.

## Printing and assembly

Use gray-blue PETG or PLA for the plates and trays, white for the knobs,
and white/red for the raised legends/logo. Faceplate STLs contain the
raised geometry but STL does not retain colors: paint the raised surfaces
in the slicer for a multi-color print, or finish them after printing.

Start with 0.2 mm layers and a 0.4 mm nozzle. Print faceplates with their
flat rear side on the bed, trays with their rear side on the bed, knobs
with their socket openings facing upward, and bridges flat. Inspect thin
legends and the logo in the slicer; use finer layers where needed.

Print one faceplate and tray for each module, one of each knob, and four
bridges. The bridges bolt through adjacent tray backs; faceplates bolt
through the corner columns. Choose bolt lengths from the measured stack:
corner holes run through the full tray and faceplate, not just the plate.
Mount electronics before closing the trays.

Run a fit coupon before buying/printing the entire set. Bores are starting
dimensions, not verified fits for a particular switch or encoder.

## Regeneration

Run the logo conversion from the repository:

```powershell
python hardware\trace_logo.py
```

In Fusion 360's Python environment, load `build_panel.py` using
`importlib.util.spec_from_file_location`, then call the loaded module's
`build()`. The script creates a **new document**, leaves existing designs
untouched, and exports next to itself. It needs Fusion's appearance library
and the local logo-contour asset; no network access is used during modeling.

Change layout and component dimensions in the source and regenerate when
parts are selected. The timeline is editable, but changes to plate thickness
or layout require checking all dependent offsets, mounting columns and cuts.
This revision does not claim unrestricted parameter-driven resizing.

Check the generated files with **Python 3.14 or newer** (needed for
Fusion's Zstandard-compressed ZIP archives), or load `check_exports.py`
inside Fusion's Python environment and call `check()`:

```powershell
python hardware\check_exports.py
```
