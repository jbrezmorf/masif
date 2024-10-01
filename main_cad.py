"""
TODO:
1. Form actual model after creating placed parts with drills, show all drils as single object
2. List drill operations.
3. Verify dowels
4. Add restex (implemented)
5: modify other drill parts
6. add mill operation
7. add mills for rails and for main rail


 figure out where to place part signature, make common function to add the signature
2. common mechanism to add parts and shift them automatically, add only parts we are working on
3.

FreeCAD notes:
- boolean operations result into a shpae that is at its original place, but with zero Placement
- to transform it back one can use:
  result_shape.transformGeometry(base_box.Placement.toMatrix().inverse())
"""

import sys
from typing import *
from pathlib import Path
# Get the directory of the current script
script_dir = Path(__file__).parent
import os

# Adjust the path according to where FreeCAD is installed
freecad_path = '/usr/lib/freecad-python3/lib'  # Set your FreeCAD installation path

if freecad_path not in sys.path:
    sys.path.append(freecad_path)
    sys.path.append(script_dir)

print(sys.path)
# Import FreeCAD modules
import tool_shapes as ts
import FreeCAD
import Part
#import FreeCADGui


import numpy as np
import pandas as pd
import attrs




def vec_to_list(vec:FreeCAD.Vector):
    return (vec.x, vec.y, vec.z)

def merge_shelves(list1, list2):
    # Create dictionaries mapping height to objects
    dict1 = {obj.height: obj for obj in list1}
    dict2 = {obj.height: obj for obj in list2}

    # Get all unique heights from both lists
    all_heights = sorted(set(dict1.keys()).union(dict2.keys()))

    # Create tuples by pairing objects from dict1 and dict2 based on height
    result = [(h, dict1.get(h), dict2.get(h)) for h in all_heights]
    return result







@attrs.define
class VPannel:
    bot_part: ts.WPart     # Floor plank
    bot_align: int      # allignment of pannel to floor part: left(-1), 0, right(1)
    part: ts.WPart

DrillFn = "Callable"
@attrs.define
class Shelf:
    height = attrs.field(type=int)
    part = attrs.field(type=ts.WPart)
    drills = attrs.field(type=Tuple[DrillFn, DrillFn],
                         converter=lambda x: x if isinstance(x, tuple) else (x, x))
    placed = attrs.field(type=ts.PlacedPart, default = None)

@attrs.define
class Col:
    pannel: VPannel
    width: int
    shelves: List[Shelf]

    @classmethod
    def empty(cls):
        return cls(VPannel(None, 0, None), 0, [])



class Wardrobe:
    def __init__(self, workdir):
        self.thickness = 18
        self.shelf_width = 600

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
            print("Creating part:", i)
            part = ts.WPart.construct(i, s, l, w, r, n, thick=self.thickness)
            setattr(self, part.name, part)

        # drawers
        self.drawer_40_24 = ts.WPart(ts.drawer(390, 240, self.shelf_width), 2, 'drawer_40_24')
        self.drawer_40_30 = ts.WPart(ts.drawer(390, 300, self.shelf_width), 2, 'drawer_40_30')
        self.drawer_40_20 = ts.WPart(ts.drawer(390, 200, self.shelf_width), 6, 'drawer_40_20')
        self.drawer_30_24 = ts.WPart(ts.drawer(300, 240, self.shelf_width), 1, 'drawer_30_24')
        self.drawer_30_30 = ts.WPart(ts.drawer(300, 300, self.shelf_width), 2, 'drawer_30_30')

        # Create a new document

        self.parts = [] # List of parts
        self.placed_objects: List[ts.PlacedPart] = []
        # self._pin_edge = ts.side_symmetric(ts.pin_edge(self.shelf_width))
        # self._rastex = ts.strong_edge(self.thickness, self.shelf_width, ts.rastex, through=False)
        # self._rastex_through = ts.strong_edge(self.thickness, self.shelf_width, ts.rastex, through=True)
        # self._vb_strip = ts.strong_edge(self.thickness, self.shelf_width, ts.vb, through=False)
        # self._vb_strip_through = ts.strong_edge(self.thickness, self.shelf_width, ts.vb, through=True)
        # self._rail = ts.rail()
        self.make_parts()
        #dirll()
        #separate()




    def drill_edge(self, pannel:ts.PlacedPart, shelf:ts.PlacedPart, tool):
        # Assume panel and shelf are objects with Placement
        tool_l, tool_r = tool

        if pannel.position[0] < shelf.position[0]:
            #drill_rot = FreeCAD.Rotation()
            x_shift = shelf.position[0]
            tool_side = tool_r
        else:
            #drill_rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 180)
            x_shift = pannel.position[0]
            tool_side = tool_l
        common_width = pannel.part.dimensions.width
        tool_placement =  FreeCAD.Placement(FreeCAD.Vector(x_shift, common_width / 2, shelf.position[2]), FreeCAD.Rotation())
        pannel.obj = ts.drill(pannel.obj, tool_side, tool_placement)
        shelf.obj = ts.drill(shelf.obj, tool_side, tool_placement)
        #
        # for z_add in [-z_dist, 0, z_dist]:
        #     for y_shift in [shelf.part.width * 0.1, shelf.part.width * 0.9]:
        #         position = FreeCAD.Vector(x_shift, y_shift, shelf.position[2] + z_add)
        #         pannel = self.drill(pannel, tool, position, rotation=drill_rot)
        #         shelf = self.drill(shelf, tool, position, rotation=drill_rot)
        # return pannel, shelf

    def drill_pins(self, pannel:ts.PlacedPart, shelf:ts.PlacedPart, through:bool = False):
        self.drill_edge(pannel, shelf, self._pin_edge)

    def drill_rastex(self, pannel:ts.PlacedPart, shelf:ts.PlacedPart, through:bool = False):
        if through:
            self.drill_edge(pannel, shelf, self._rastex_through)
        else:
            self.drill_edge(pannel, shelf, self._rastex)


    def drill_vb_strip(self, pannel:ts.PlacedPart, shelf:ts.PlacedPart, through:bool = False):
        if through:
            self.drill_edge(pannel, shelf, self._vb_strip_through)
        else:
            self.drill_edge(pannel, shelf, self._vb_strip)

    def drill_rail(self, pannel:ts.PlacedPart, shelf:ts.PlacedPart, through:bool = False):
        self. drill_edge(pannel, shelf, self._rail)

    def add_object(self, part:ts.WPart, placement) -> ts.PlacedPart:
        if not isinstance(placement, FreeCAD.Vector):
            placement = FreeCAD.Vector(*placement)
        placement = ts.translate(placement)
        placed = ts.PlacedPart(part, placement, name=f"{part.name}_{part.allocate()}")
        self.placed_objects.append(placed)
        return placed

    # def part(self, name, form, x, y, z):
    #     position = FreeCAD.Vector(x, y, z)
    #     part = ts.PlacedPart(form, position, name=name)
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
        print("Create columns")

        # bottom front
        y_shift = self.vertical_panel.dimensions.width - self.bottom.dimensions.length - self.bottom_front_L.dimensions.width
        bot_front_l = self.add_object(self.bottom_front_L, [0, y_shift, 0])
        bot_front_r = self.add_object(self.bottom_front_R, [bot_front_l.part.dimensions.length, y_shift, 0] )
        bot_front_l, bot_front_r = ts.dowel_connect(bot_front_l, bot_front_r, dowel_dir=0, edge_dir=1)

        # ceiling
        y_shift = -100
        z_shift = self.vertical_panel.dimensions.length + self.thickness
        ceil_a = self.add_object(self.ceil_A, [0, y_shift, z_shift])
        ceil_b = self.add_object(self.ceil_B, [ceil_a.part.dimensions.length, y_shift, z_shift])
        ceil_c = self.add_object(self.ceil_C, [ceil_a.part.dimensions.length, y_shift + 600, z_shift])
        ceil_a, ceil_b = ts.dowel_connect(ceil_a, ceil_b, dowel_dir=0, edge_dir=1)
        ceil_b, ceil_c = ts.dowel_connect(ceil_b, ceil_c, dowel_dir=1, edge_dir=0)
        #self.add_object(ts.WPart(tool, 1, 'ceil_dowel_cut'), [0, 0, 0])

        # front cover
        z_shift = z_shift - self.middle_front_A.dimensions.width
        cover_a = self.add_object(self.middle_front_A, [0, y_shift, z_shift])
        cover_b = self.add_object(self.middle_front_B, [cover_a.part.dimensions.length, y_shift, z_shift])
        cover_a, cover_b = ts.dowel_connect(cover_a, cover_b, dowel_dir=0, edge_dir=2)
        #self.add_object(ts.WPart(tool, 1, 'front_dowel_cut'), [0, 0, 0])


        # construct cols
        x_shift = 0
        for last, col in zip([Col.empty(), *cols], cols):
            print(col)
            # left vertical pannel
            pannel_plank = col.pannel.part.dimensions
            pannel_placed: ts.PlacedPart = self.add_object(col.pannel.part, [x_shift, 0, self.thickness])
            # bottom
            bot_plank = col.pannel.bot_part.dimensions
            bot_part = col.pannel.bot_part
            if col.pannel.bot_align == -1:
                align_shift = 0
            elif col.pannel.bot_align == 0:
                align_shift = (-bot_plank.width + self.thickness) / 2
            else:
                align_shift = -bot_plank.width + self.thickness
            bottom: ts.PlacedPart =  self.add_object(bot_part, [x_shift + align_shift, pannel_plank.width - bot_plank.length, 0])
            bot_front_l, bottom = ts.dowel_connect(bot_front_l, bottom, dowel_dir=1, edge_dir=0)
            #bot_front_r, bottom, tool_r = dowel_connect(bot_front_r, bottom, dowel_dir=1, edge_dir=0)
            #if tool_l is None:
            #    pass
                #assert tool_r is not None
                #self.add_object(ts.WPart(tool_r, 1, f'{bottom.name}_dowel_cut_r'), [0, 0, 0])
            #else:
                #if tool_r is not None:
                #    self.add_object(ts.WPart(tool_r, 1, f'{bottom.name}_dowel_cut_r'), [0, 0, 0])
            #    self.add_object(ts.WPart(tool_l, 1, f'{bottom.name}_dowel_cut_l'), [0, 0, 0])

            # shelf pairs
            x_shift+= self.thickness
            shelf_pairs = merge_shelves(last.shelves, col.shelves)
            for height, last_shelf, shelf in shelf_pairs:
                print(f"    shelf_h: {height}")
                shelf_flag = (last_shelf is not None, shelf is not None)
                shelf_fn = lambda s, i : None if s is None else s.drills[i]
                if pannel_plank.length < height:
                    # continuing shelf
                    #print(f"    ...{shelf}")
                    # check matching shelf in last
                    if not shelf_flag[0] or not shelf_flag[1]:
                        raise Exception(f"Missing continuing shelf, flag: {shelf_flag}.")
                else:
                    # new shelf
                    if shelf_flag[1] and shelf.part is not None:
                        shelf_placed = self.add_object(shelf.part, [x_shift, 0, shelf.height])
                        shelf.placed = shelf_placed

                    # drilling
                    last_drill = shelf_fn(last_shelf, 1)
                    act_drill = shelf_fn(shelf, 0)
                    drill_through = last_drill is act_drill
                    if last_drill is not None:
                        shelf_fn(last_shelf, 1)(pannel_placed, last_shelf.placed, through=drill_through)
                    if act_drill is not None:
                        shelf_fn(shelf, 0)(pannel_placed, shelf.placed, through=drill_through)

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
        drill_vb_strip = None #self.drill_vb_strip
        drill_rastex = None #self.drill_rastex
        drill_pins = None #self.drill_pins
        drill_rail = None # self.drill_rail

        col_0_shelves = [
            Shelf(1250, self.drawer_30_24, drill_rail),
            Shelf(1500, self.shelf_top_long, (drill_vb_strip, drill_rastex)),
            Shelf(1770, self.shelf_top_long, drill_pins),
            Shelf(2040, self.shelf_top_long, drill_pins)]
        col_1_shelves = [
            Shelf(330, self.drawer_40_30, drill_rail),
            Shelf(650, self.drawer_40_30, drill_rail),
            Shelf(970, self.drawer_40_24, drill_rail),
            Shelf(1230, self.shelf_40, drill_pins),
            *col_0_shelves[1:]]
        col_2_shelves = [
            Shelf(330, self.drawer_40_20, drill_rail),
            Shelf(540, self.drawer_40_20, drill_rail),
            Shelf(750, self.drawer_40_20, drill_rail),
            Shelf(960, self.shelf_40, drill_rastex),
            Shelf(1230, self.shelf_40, drill_pins),
            Shelf(1500, self.shelf_40, drill_rastex),
            Shelf(1770, self.shelf_40, drill_pins),
            Shelf(2040, self.shelf_40, drill_pins)]
        col_3_shelves = [
            Shelf(1500, self.shelf_middle, drill_rastex),
            Shelf(1770, self.shelf_middle, drill_pins),
            Shelf(2040, self.shelf_middle, drill_pins)]
        col_5_shelves = [
            Shelf(330, self.drawer_30_30, drill_rail),
            Shelf(645, self.drawer_30_30, drill_rail),
            Shelf(960, self.shelf_30, drill_pins),
            Shelf(1230, self.shelf_30, drill_pins),
            *col_0_shelves[1:]]
        col_6_shelves = [
            Shelf(330, self.shelf_40, drill_pins),
            Shelf(705, self.drawer_40_24, drill_rail),
            Shelf(960, self.shelf_40, drill_pins),
            Shelf(1230, self.shelf_40, drill_pins),
            *col_0_shelves[1:]]

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

    def list_operations(self):
        print("\n\nOpeartions:\n")
        for obj in self.placed_objects:
            print(obj.name)
            for op in obj.machine_ops:
                print("    ", op)


def build_from_placed(doc, placed_parts: List[ts.PlacedPart]):
    for p in placed_parts:
        p.make_obj(doc)
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

w = Wardrobe(script_dir)
w.list_operations()
build_from_placed(doc, w.placed_objects)

doc.recompute()
# Ensure all objects in the document are visible
for obj in doc.Objects:
    obj.Visibility = True  # Make the object visible

path = script_dir / "Warderobe.FCStd"
doc.saveAs(str(path))
