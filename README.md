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

## CNC notes
Autodesk Fusion
1. Deign, card: rotate manufacturing side up, corner (0, y_max) will be CNC zero
2. Manufacture, card:
    a) add CNC operation type (e.g. parallel 3D)
    b) set tool, select "tvrdé dřeviny" pro pomalejší pohyb
    c) path - selection -> select manufactured faces
    d) set retraction height
    OK -> add the operation
3. right click to setup -> edit -> check slack and zero corner at (top left of the model plane)
4. 01 on top -> save program

CNC program
1. double speed head (on strat)
2. calibrate TLS (Z coord)
3. go to zero
4. verify a selected part go to it manualy, measure it is well placed

==============
