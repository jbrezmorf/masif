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
- add top and bottom dowels - pannels
- 1mm cut for rails
- connection dowels
- front pannels
- How display internall walls? 
- save to STEP file
