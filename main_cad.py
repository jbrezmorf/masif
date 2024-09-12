"""
TODO:
1. figure out where to place part signature, make common function to add the signature
2. common mechanism to add parts and shift them automatically, add only parts we are working on
3.

FreeCAD notes:
- boolean operations result into a shpae that is at its original place, but with zero Placement
- to transform it back one can use:
  result_shape.transformGeometry(base_box.Placement.toMatrix().inverse())
"""

import sys
import os

# Adjust the path according to where FreeCAD is installed
freecad_path = '/usr/lib/freecad-python3/lib'  # Set your FreeCAD installation path

if freecad_path not in sys.path:
    sys.path.append(freecad_path)

# Import FreeCAD modules
import FreeCAD
import Part
#import FreeCADGui

from typing import *
from pathlib import Path

import numpy as np
import pandas as pd
import attrs


# Get the directory of the current script
script_dir = Path(__file__).parent


@attrs.define
class WPart:
    length : float
    width : float
    rot : FreeCAD.Rotation   # rotation object
    n_parts: int
    thick : float
    name: str
    _i_part: int = 0

    @classmethod
    def construct(cls,
            identifier, suffix,
            length, width,
            rot_ax, n_parts, thick):
        if isinstance(suffix, str) :
            name = (f"{identifier}_{suffix}")
        else:
            name = identifier

        rot_total = FreeCAD.Rotation()
        axes = dict(X=FreeCAD.Vector(1, 0, 0),
                    Y=FreeCAD.Vector(0, 1, 0),
                    Z=FreeCAD.Vector(0, 0, 1))
        #print(rot_ax, type(rot_ax))
        if isinstance(rot_ax, (str, )):
            for r_ax in rot_ax:
                rot = FreeCAD.Rotation(axes[r_ax], 90)
                rot_total = rot.multiply(rot_total)
               # print(rot_ax, rot, rot_total)
        return cls(length, width, rot_total, n_parts, thick, name)

    @property
    def shape(self):
        shape = Part.makeBox(self.length, self.width, self.thick)
        pos = FreeCAD.Vector(0,0,0)
        #print("1",pos, self.rot)
        shape.Placement = FreeCAD.Placement(pos, self.rot)
        bb = shape.BoundBox
        pos = FreeCAD.Vector(-bb.XMin, -bb.YMin, -bb.ZMin)
        #print("2",pos, self.rot)
        shape.Placement = FreeCAD.Placement(pos, self.rot)
        return shape

    def allocate(self):
        """
        Allocate new part instance, numbered from 1 in order
        :return:
        """
        self._i_part += 1
        assert self._i_part <= self.n_parts, f"Out of part: {self.name}, #{self._i_part} > {self.n_parts}"
        return self._i_part

@attrs.define
class PlacedPart:
    part : WPart
    position: FreeCAD.Vector       # Full placement object
    obj: 'Part.Feature' = None     # set after init
    name : str = ""

    @property
    def placement(self):
        new_placement = FreeCAD.Placement(self.position, FreeCAD.Rotation())
        return new_placement.multiply(self.part.shape.Placement)

    def max(self, ax):
        bb = self.obj.Shape.BoundBox
        return [bb.XMax, bb.YMax, bb.ZMax][ax]

@attrs.define
class VPannel:
    bot_part: WPart     # Floor plank
    bot_align: int      # allignment of pannel to floor part: left(-1), 0, right(1)
    part: WPart

DrillFn = "Callable"
@attrs.define
class Shelf:
    height = attrs.field(type=int)
    part = attrs.field(type=WPart)
    drills = attrs.field(type=Tuple[DrillFn, DrillFn],
                         converter=lambda x: x if isinstance(x, tuple) else (x, x))

@attrs.define
class Col:
    pannel: VPannel
    width: int
    shelves: List[Shelf]

class Wardrobe:
    def __init__(self, workdir, doc):
        self.thickness = 18

        # Load the ODS file
        # Replace 'your_file.ods' with the path to your ODS file
        df = pd.read_excel(workdir / 'Objednávka MAPH.ods', engine='odf', header=None)

        # Filter rows where the 'I' column is not empty
        valid = df.iloc[:, ord('I') - ord('A')].notna()
        df = df[valid]
        n_parts = df.iloc[:, 0]
        identifier = df.iloc[:, ord('I') - ord('A')]
        suffix = df.iloc[:, ord('J') - ord('A')]
        length = df.iloc[:, ord('B') - ord('A')]
        width = df.iloc[:, ord('C') - ord('A')]
        rot_ax = df.iloc[:, ord('D') - ord('A')]
        for i, s, l, w, r, n in zip(identifier, suffix, length, width, rot_ax, n_parts):
            #print(i)
            part = WPart.construct(i, s, l, w, r, n, thick=self.thickness)
            setattr(self, part.name, part)

        # Create a new document

        self.doc = doc
        self.parts = [] # List of parts
        self.make_parts()
        #dirll()
        #separate()


    def drill(self, part, tool, position, rotation=None):
        # Create a copy of the tool for operation
        tool_copy = tool.copy()

        # Set the position and rotation of the tool
        if rotation is None:
            rotation = FreeCAD.Rotation()  # No rotation by default

        tool_copy.Placement = FreeCAD.Placement(position, rotation)

        # Perform the cut operation
        result = part.cut(tool_copy)
        return result

    def drill_pins(self, panel, shelf):
        # Assume panel and shelf are objects with Placement
        pos = FreeCAD.Vector(*vec)
        z_move = FreeCAD.Vector(0, 0, 30)
        tool = Part.makeCylinder(5, 10)
        for p in [pos - z_move, pos, pos + z_move]:
            part = self.drill(part, tool, p)
        return part

    def drill_hetix(self, panel, shelf):
        pos = FreeCAD.Vector(*vec)
        z_move = FreeCAD.Vector(0, 0, 30)
        tool = Part.makeCylinder(5, 10)
        for p in [pos - z_move, pos, pos + z_move]:
            part = self.drill(part, tool, p)
        return part


    def add_object(self, part:WPart, placement):
        if not isinstance(placement, FreeCAD.Vector):
            placement = FreeCAD.Vector(*placement)
        placed = PlacedPart(part, placement, name=f"{part.name}_{part.allocate()}")
        obj = self.doc.addObject("Part::Feature", placed.name)
        obj.Shape = part.shape
        obj.Placement = placed.placement
        placed.obj = obj
        return placed

    # def part(self, name, form, x, y, z):
    #     position = FreeCAD.Vector(x, y, z)
    #     part = PlacedPart(form, position, name=name)
    #     obj = self.add_object(part)
    #     part.obj = obj
    #     setattr(self, name, part)
    #     return part

    def construct_columns(self, cols: List[Col]):
        """
        - construct FreeCAD objects of Waredrobe and place them
        - evary part is added to the list of parts
        - proper drilling is applied

        :return: composed wardrobe body object of the parst
        """
        # construct cols
        x_shift = 0
        for last, col in zip([None, *cols], cols):
            print(col)
            # left vertical pannel
            pannel: PlacedPart = self.add_object(col.pannel.part, [x_shift, 0, self.thickness])
            # bottom
            bot_part = col.pannel.bot_part
            if col.pannel.bot_align == -1:
                align_shift = 0
            elif col.pannel.bot_align == 0:
                align_shift = (-bot_part.width + self.thickness) / 2
            else:
                align_shift = -bot_part.width + self.thickness
            bottom: PlacedPart =  self.add_object(bot_part, [x_shift + align_shift, pannel.part.width - bot_part.length, 0])


            # shelfs
            x_shift+= self.thickness
            if last is not None:
                last_dict = {s.height: s for s in last.shelves}
            else:
                last_dict = {}

            for shelf in col.shelves:
                if col.pannel.part.length < shelf.height:
                    print(f"    ...{shelf}")
                    # continuing shelf
                    #assert , f"Pannel (l={col.pannel.part.length}) block continuing shelf (h={shelf.height})"
                    # check matching shelf in last
                    try:
                        continuing = last_dict[shelf.height]
                    except KeyError as e:
                        print(last_dict)
                        raise e
                else:
                    print(f"    {shelf}")
                    # new shelf
                    shlef_placed = self.add_object(shelf.part, [x_shift, 0, shelf.height])

            x_shift+= col.width

    def make_parts(self):
        """
        DEscription of the main warderobe body.
        Consists of columns that are separated by vertical panels.
        Column contains:
        - left pannel configuration:
          list of vertical pannels: component + vertical shift
        - horizontal shelfs:
          column width
          component -> column width
          ... tracking used width of every shelf
          ... allows shelfs over multiple columns
          list of shelfs from bottom to top
          Single shelf:
          -
          - indication of type of connection to pannels
            - free pin (two more hles drilled to the pannel)
            - hetix
            - two hole connection
            structural shells
        :return:
        """
        drill_strip = None
        drill_hetix = None
        drill_pins = self.drill_pins

        col_0_shelves = [
            Shelf(1500, self.shelf_top_long, (drill_strip, drill_hetix)),
            Shelf(1770, self.shelf_top_long, drill_pins),
            Shelf(2040, self.shelf_top_long, drill_pins)]
        col_1_shelves = [
            Shelf(1230, self.shelf_40, drill_pins),
            *col_0_shelves]
        col_2_shelves = [
            Shelf(982, self.shelf_40, drill_hetix),
            Shelf(1230, self.shelf_40, drill_pins),
            Shelf(1500, self.shelf_40, drill_hetix),
            Shelf(1770, self.shelf_40, drill_pins),
            Shelf(2040, self.shelf_40, drill_pins)]
        col_3_shelves = [
            Shelf(1500, self.shelf_middle, drill_hetix),
            Shelf(1770, self.shelf_middle, drill_pins),
            Shelf(2040, self.shelf_middle, drill_pins)]
        col_5_shelves = [
            Shelf(950, self.shelf_30, drill_pins),
            Shelf(1230, self.shelf_30, drill_pins),
            *col_0_shelves]
        col_6_shelves = [
            Shelf(350, self.shelf_40, drill_pins),
            Shelf(950, self.shelf_40, drill_pins),
            Shelf(1230, self.shelf_40, drill_pins),
            *col_0_shelves]

        left_pannel = VPannel(self.bottom_side, -1, self.vertical_panel)
        mid_long = VPannel(self.bottom, 0, self.vertical_panel)
        mid_short = VPannel(self.bottom, 0, self.vertical_short)
        right_pannel = VPannel(self.bottom_side, 1, self.vertical_panel)
        columns = [
            Col(left_pannel, 325, col_0_shelves),
            Col(mid_short, 415, col_1_shelves),
            Col(mid_long, 415, col_2_shelves),
            Col(mid_long, 710, col_3_shelves),
            Col(mid_long, 415, col_2_shelves),
            Col(mid_long, 325, col_5_shelves),
            Col(mid_short, 415, col_6_shelves),
            Col(right_pannel, 0, []),
        ]

        body = self.construct_columns(columns)

        # bottom front
        y_shift = self.vertical_panel.width - self.bottom.length - self.bottom_front_L.width
        bot_front_l = self.add_object(self.bottom_front_L, [0, y_shift, 0])
        self.add_object(self.bottom_front_R, [bot_front_l.part.length, y_shift, 0] )

        # ceiling
        y_shift = -100
        z_shift = self.vertical_panel.length + self.thickness
        ceil_a = self.add_object(self.ceil_A, [0, y_shift, z_shift])
        ceil_b = self.add_object(self.ceil_B, [ceil_a.part.length, y_shift, z_shift])
        ceil_c = self.add_object(self.ceil_C, [ceil_a.part.length, y_shift + 600, z_shift])

        # front cover
        z_shift = z_shift - self.middle_front_A.width
        cover_a = self.add_object(self.middle_front_A, [0, y_shift, z_shift])
        cover_b = self.add_object(self.middle_front_B, [cover_a.part.length, y_shift, z_shift])




# panel1_group = doc.addObject("App::DocumentObjectGroup", "Panel1")
# panel2_group = doc.addObject("App::DocumentObjectGroup", "Panel2")
#
#
#
# thickness = 18  # mm
# width_panel1 = 600  # mm
# length_panel1 = 800  # mm
#
# # Define common hole positions, sizes, etc.
# hole_diameter = 5  # mm
#
# # Panel 1 creation
# panel1 = Part.makeBox(width_panel1, length_panel1, thickness)
# panel1_obj = doc.addObject("Part::Feature", "Panel1_Shape")
# panel1_obj.Shape = panel1
# panel1_group.addObject(panel1_obj)
#
# # Drilling holes on Panel 1
# hole1 = Part.makeCylinder(hole_diameter/2, thickness)
# hole1.translate(Base.Vector(100, 100, 0))  # Position hole on the panel
# panel1 = panel1.cut(hole1)
#
# panel1_obj.Shape = panel1  # Update the shape with the hole
#
# # Panel 2 creation (similar to Panel 1)
# width_panel2 = 500  # mm
# length_panel2 = 700  # mm
#
# panel2 = Part.makeBox(width_panel2, length_panel2, thickness)
# panel2_obj = doc.addObject("Part::Feature", "Panel2_Shape")
# panel2_obj.Shape = panel2
# panel2_group.addObject(panel2_obj)
#
# # Drilling holes on Panel 2
# hole2 = Part.makeCylinder(hole_diameter/2, thickness)
# hole2.translate(Base.Vector(150, 150, 0))  # Position hole on the panel
# panel2 = panel2.cut(hole2)
#
# panel2_obj.Shape = panel2  # Update the shape with the hole
#
#
# import FreeCAD as App
# import Draft
#
# doc = App.activeDocument()
#
# # Function to add a label to a part
# def add_label_to_part(part, label_text, offset=(10, 10, 10)):
#     # Get the center of the part's bounding box for label positioning
#     center = part.Shape.BoundBox.Center
#     label_position = center.add(App.Vector(*offset))
#
#     # Create the label
#     label = Draft.makeLabel([label_position], label_text)
#     label.ViewObject.FontSize = 20  # Adjust the font size as needed
#     label.ViewObject.TextColor = (1.0, 0.0, 0.0)  # Set color to red (RGB)
#
#     return label
#
#
#
#
#
# def add_drilling_pattern(panel, positions, hole_diameter, thickness):
#     for pos in positions:
#         hole = Part.makeCylinder(hole_diameter/2, thickness)
#         hole.translate(Base.Vector(pos[0], pos[1], 0))
#         panel = panel.cut(hole)
#     return panel
#
# # Apply a shared drilling pattern to both panels
# shared_positions = [(200, 200), (300, 300)]
# panel1 = add_drilling_pattern(panel1, shared_positions, hole_diameter, thickness)
# panel2 = add_drilling_pattern(panel2, shared_positions, hole_diameter, thickness)
#
# # Update the shapes in the document
# panel1_obj.Shape = panel1
# panel2_obj.Shape = panel2
#
#
# # Example: Add labels to parts in your document
# for obj in doc.Objects:
#     if obj.TypeId == "Part::Feature":  # Check if the object is a Part
#         add_label_to_part(obj, obj.Label)
#


def clear_document(doc):
    for obj in doc.Objects:
        doc.removeObject(obj.Name)

# Ensure that FreeCAD is running with a document
if FreeCAD.ActiveDocument is None:
    FreeCAD.newDocument()
else:
    clear_document(FreeCAD.ActiveDocument)
doc = FreeCAD.ActiveDocument  # Get the cleared (or new) document

w = Wardrobe(script_dir, doc)
w.doc.recompute()
path = script_dir / "Warderobe.FCStd"
w.doc.saveAs(str(path))
