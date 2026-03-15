# Massif - a script for preparateion solid wood wardrobe components using CNC

Principles
- Currently use FreeCAD scripted from Python.
- We assume an input table with dimensions and count of the raw solid wood planks.
- The wardrobe is assembled in a 3D scene from the parts according to the Wardorbe.make_parts(..).
- During assembly the shelf attachment drills are performed.
- Other drills must be put explicitely to wardrobe.make_parts(..)

# Getting started
- development from PyCharm using FreeCAD as library adding freecad libs into PYTHONPATH:
    ```
    freecad_path = '/usr/lib/freecad-python3/lib'  # Set your FreeCAD installation path

    if freecad_path not in sys.path:
        sys.path.append(freecad_path)
    ```

- the Python script produced a FreeCAD file, but that fails to open in FreeCAD


TODO:
- add top and bottom dowels - panels
- 1mm cut for rails
- connection dowels
- front panels
- How display internal walls?
- save to STEP file

## `masif_load_transform`

Fusing 360 scripts for generating g-code.
- detect operations
- generate 1xmill, 2x drill, g-code for 4 part positions


## Front panels

CNC has active span 60cm, so we can not mill front panels almost 80cm
wide that barely fits there. That applies even more to the sliding pockets, that are mere 3cm from stock sides.

Conclusion: Try to find larger CNC possibly contact Kateřinky, and
try to figure out some cooperation in programmed/ML based  woodcrafting.

Backup option: scale dragon pattern smaller, do other ops manually.

## bottom
- Keep existing design, add minimalistic separators to the far side.
  need about 40mm x 18mm profile. There is a risk of deformation with time, but that should not matter as the containers will slide on the sides. Future designs: solid bottom or through going part, connecting the bottom slides.
- Adapt model of the front bottom to 130mm wide and elevated ramp.
- 
