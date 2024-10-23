"""
TODO:
- add check box with height 56, that should be gap between fron_panel and ceil
- move front top cover 30 from edge of ceil, move front pannels
- add mill to pannels for movement

Dowel diameter should match plane
dowel_diam / thickness in interval (2/5, 3/5)
for thickness 18, we should use 8 mm dowels.
Connections overview: https://publi.cz/books/164/01.html

ChatGPT recommnet dowel distance 100 to 150 mm, for safety I will use 100mm distance
Bit problematic are two dowels of the strong_edge connection.


FreeCAD notes:
- boolean operations result into a shpae that is at its original place, but with zero Placement
- to transform it back one can use:
  result_shape.transformGeometry(base_box.Placement.toMatrix().inverse())
"""

import sys
from typing import *
from pathlib import Path

import freecad

# Get the directory of the current script
script_dir = Path(__file__).parent
model_dir = script_dir / "model"
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

def merge_shelves(list1: List['Shelf'], list2 : List['Shelf']) -> Tuple[float, List['Shelf'], List['Shelf']]:
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
        self.draft = True
        self.door_open = True

        self.dowel_diam = 8
        self.dowel_len = 35
        self.cross_dowel_extent = 12
        self.common_dowel_dist = 100
        self.rail_pannel_predrill = 3   # screw diam 3mm / 5mm
        self.rail_height = 44
        self.rail_thickness = 12.5


        # Load the ODS file
        # Replace 'your_file.ods' with the path to your ODS file
        df = pd.read_excel(workdir / 'Objednávka MAPH.ods', engine='odf', header=None)


        self.dowel = lambda *a, **b : ts.dowel(*a, **b, diam=self.dowel_diam, length=self.dowel_len)
        self.strong_edge = lambda *a, **b : ts.strong_edge(*a, **b,
                                                           dowel_extent=self.cross_dowel_extent, dowel_fn=self.dowel)
        self.dowel_row = lambda *a, **b : ts.dowel_row(*a, **b, dowel_fn=self.dowel)
        self.dowel_connect = lambda *a, **b: ts.dowel_connect(*a, **b,
                             dowel_row_fn=self.dowel_row, dowel_dist=self.common_dowel_dist)

        # Filter rows where the 'I' column is not empty
        valid = df.iloc[:, ord('I') - ord('A')].notna()
        df = df[valid]
        n_parts = df.iloc[:, 0]
        identifier = df.iloc[:, ord('I') - ord('A')]
        print(identifier)
        suffix = df.iloc[:, ord('J') - ord('A')]
        length = df.iloc[:, ord('B') - ord('A')]
        width = df.iloc[:, ord('C') - ord('A')]
        rot_ax = df.iloc[:, ord('D') - ord('A')]
        for i, s, l, w, r, n in zip(identifier, suffix, length, width, rot_ax, n_parts):
            part = ts.WPart.construct(i, s, l, w, r, n, thick=self.thickness)
            print("Creating part:", part)
            setattr(self, part.name, part)

        z_shift = -8
        rail = ts.Rail(self.rail_height, self.rail_thickness)
        drawer_fn = lambda dx, dz, n : ts.Drawer.make([dx, self.shelf_width, dz], n, z_shift, rail)

        # drawers
        self.drawer_40_24 = drawer_fn(390, 240, 2)
        self.drawer_40_30 =  drawer_fn(390, 300,  2)
        self.drawer_40_20 =  drawer_fn(390, 200,  6)
        self.drawer_30_24 =  drawer_fn(300, 240,  1)
        self.drawer_30_30 =  drawer_fn(300, 300,  2)

        # Create a new document

        self.parts = [] # List of parts
        self.placed_objects: List[ts.PlacedPart] = []
        self._pin_edge = ts.side_symmetric(ts.pin_edge(self.shelf_width))
        self._rastex =  self.strong_edge(self.thickness, self.shelf_width, ts.rastex, through=False)
        self._rastex_through =  self.strong_edge(self.thickness, self.shelf_width, ts.rastex, through=True)
        self._vb_strip =  self.strong_edge(self.thickness, self.shelf_width, ts.vb, through=False)
        self._vb_strip_through =  self.strong_edge(self.thickness, self.shelf_width, ts.vb, through=True)
        self._rail = self.drawer_40_30.rail_drill(self.rail_pannel_predrill)
        self.make_parts()




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
        tool_placement =  ts.translate([x_shift, common_width / 2, shelf.position[2]])
        pannel_tool, shelf_tool = tool_side
        pannel.apply_op(pannel_tool @ tool_placement)
        shelf.apply_op(shelf_tool @ tool_placement)
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
        self.drill_edge(pannel, shelf, self._rail)

    def add_object(self, part:ts.WPart, position) -> ts.PlacedPart:
        if isinstance(position, FreeCAD.Vector):
            position = vec_to_list(position)
        placed = ts.PlacedPart(part, position, name=f"{part.name}_{part.allocate()}")
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
        bot_y_shift = 0
        print("Create columns")

        # bottom front
        y_shift = (self.vertical_panel.dimensions.width - self.bottom.dimensions.length
                   - self.bottom_front_L.dimensions.width + bot_y_shift)
        print("bottom_front y shift ")
        bot_front_l = self.add_object(self.bottom_front_L, [0, y_shift, 0])
        bot_front_r = self.add_object(self.bottom_front_R, [bot_front_l.part.dimensions.length, y_shift, 0] )
        # in colision with perpendicular bottom part, well conected by that
        bot_front_l, bot_front_r =  self.dowel_connect(bot_front_l, bot_front_r, dowel_dir=0, edge_dir=1,
                                                    rel_range=[None, (0.3, 1.0), None])

        # bottom_front_width = 130, 60 under pannel, 70 outer
        ts.ramp_mill(bot_front_l, width=30)
        ts.ramp_mill(bot_front_r, width=30)

        # ceiling
        ceil_y_shift = -100
        ceil_z_shift = self.vertical_panel.dimensions.length + self.thickness
        ceil_a = self.add_object(self.ceil_A, [0, ceil_y_shift, ceil_z_shift])
        ceil_b = self.add_object(self.ceil_B, [ceil_a.part.dimensions.length, ceil_y_shift, ceil_z_shift])
        ceil_c = self.add_object(self.ceil_C, [ceil_a.part.dimensions.length, ceil_y_shift + 600, ceil_z_shift])
        ceil_a, ceil_b =  self.dowel_connect(ceil_a, ceil_b, dowel_dir=0, edge_dir=1)
        ceil_b, ceil_c =  self.dowel_connect(ceil_b, ceil_c, dowel_dir=1, edge_dir=0)
        #self.add_object(ts.WPart(tool, 1, 'ceil_dowel_cut'), [0, 0, 0])

        # front cover
        y_cover = ceil_y_shift + 20
        cover_z_shift = ceil_z_shift - self.middle_front_A.dimensions.width
        cover_a = self.add_object(self.middle_front_B, [0, y_cover, cover_z_shift])
        cover_b = self.add_object(self.middle_front_A, [cover_a.part.dimensions.length, y_cover, cover_z_shift])
        cover_a, cover_b =  self.dowel_connect(cover_a, cover_b, dowel_dir=0, edge_dir=2)
        for cov in [cover_a, cover_b]:
            for ceil in [ceil_a, ceil_b]:
                 self.dowel_connect(cov, ceil, dowel_dir=2, edge_dir=0,
                                    left_extent=-self.cross_dowel_extent)
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
            bottom: ts.PlacedPart = self.add_object(bot_part, [x_shift + align_shift, pannel_plank.width - bot_plank.length + bot_y_shift, 0])
            bot_front_l, bottom =  self.dowel_connect(bot_front_l, bottom, dowel_dir=1, edge_dir=0)
            bot_front_r, bottom =  self.dowel_connect(bot_front_r, bottom, dowel_dir=1, edge_dir=0)
            bottom, pannel_placed =  self.dowel_connect(bottom, pannel_placed, dowel_dir=2, edge_dir=1, left_extent=self.cross_dowel_extent)
            bot_front_l, pannel_placed =  self.dowel_connect(bot_front_l, pannel_placed, dowel_dir=2, edge_dir=1,
                                                          rel_range = [None, [0, 0.7], None], left_extent=self.cross_dowel_extent)
            bot_front_r, pannel_placed =  self.dowel_connect(bot_front_r, pannel_placed, dowel_dir=2, edge_dir=1,
                                                          rel_range = [None, [0, 0.7], None], left_extent=self.cross_dowel_extent)

            # shelf pairs
            x_shift+= self.thickness
            shelf_pairs = merge_shelves(last.shelves, col.shelves)

            # top dowels
            # search for shelf at the top of pannel or use all ceiling parts.
            z_max = pannel_placed.aabb[1, 2]
            top_shlef =[ (last, current)  for h, last, current in shelf_pairs if abs(h - z_max) <1e-6]
            if top_shlef:
                assert len(top_shlef) == 1
                last_shelf, shlef = top_shlef[0]
                assert last_shelf.part == shelf.part
                self.dowel_connect(pannel_placed, last_shelf.placed, dowel_dir=2, edge_dir=1, left_extent=-self.cross_dowel_extent)
            else:
                for c in [ceil_a, ceil_b, ceil_c]:
                     self.dowel_connect(pannel_placed, c, dowel_dir=2, edge_dir=1, left_extent=-self.cross_dowel_extent)

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
                    shelf.placed = last_shelf.placed
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

        total_x = x_shift
        print("Total X dim: ", total_x)

        # front pannels

        self.front_doors(y_cover, total_x, (bot_front_l, bot_front_r), cover_a)

        left_ceil_height = 2616
        right_ceil_height = 2695
        ceil_z_top = ceil_z_shift + self.thickness
        middle_shift = 1000
        dx_middle = self.ceil__front_middle.dimensions.length
        dx_side = self.ceil_front_side.dimensions.length

        # top parts 8 mm shorter in in total then total_x
        x_top = [1, 3 +  dx_side, 5 + dx_side + dx_middle, 7 + dx_side + 2 * dx_middle]
        top_middle = self.add_object(self.ceil__front_middle, position=[x_top[1], ceil_y_shift, ceil_z_top])
        top_side = self.add_object(self.ceil_front_side, position=[x_top[0], ceil_y_shift, ceil_z_top])

        A = left_ceil_height - ceil_z_top
        B = right_ceil_height - ceil_z_top
        print("top l,r:", A, B)

        ceil_y_pt = lambda x : A * (1 - x / total_x) + B * x / total_x

        # def cut_mill(a, b):
        #     r = 5
        #     start = [*a, self.thickness]
        #     start[1] += r
        #     end = [*b, self.thickness]
        #     end[1] += r
        #     return ts.MillOp(r, self.thickness, [0, 0, -1], start, end)

        def top_handle_mill(a, b):
            mill_diam = 4
            pt_a = [*a, 0]
            pt_a[1] += mill_diam / 2
            pt_b = [*b, 0]
            pt_b[1] += mill_diam / 2
            path  = ts.handle_path(pt_a, pt_b, 0.1, 15, 0)
            return ts.ShapeOp(ts.create_sweep_shape(path, W_rect = mill_diam, H_rect=self.thickness))

        # cut first
        def cut_part(part:ts.PlacedPart, a, b, c, d):
            eps = 10
            dx, dz, dy = part.dims
            assert b - a == d - c
            a_pt = [a + eps - a, ceil_y_pt(a + eps)]
            b_pt = [b - eps - a, ceil_y_pt(b - eps)]
            handle_op = top_handle_mill(a_pt, b_pt)
            inv_handle_op = handle_op @ ts.rotate([0, 0, 1], 180) @ ts.translate([b-a, ceil_y_pt(a) + (dy - ceil_y_pt(c)), 0])

            #ab_cut = cut_mill([eps, ceil_y_pt(a + eps)], [dx - eps, ceil_y_pt(b - eps)])
            #dc_cut = cut_mill([eps, dy - ceil_y_pt(d - eps)], [dx - eps, dy - ceil_y_pt(c + eps)])
            part.apply_op(handle_op @ part.placement)
            part.apply_op(inv_handle_op @ part.placement)

        cut_part(top_side, 0, dx_side, 2 * dx_middle + dx_side, 2 * dx_middle + 2 * dx_side)
        cut_part(top_middle, dx_side, dx_side + dx_middle, dx_side + dx_middle, dx_side + 2 * dx_middle)

        inv_rotate = ts.rotate([0, 0, 1], 180) @ ts.rotate([1, 0, 0], 90)
        self.placed_objects.append(top_middle.copy(inv_rotate,[x_top[2], ceil_y_shift, ceil_z_top]))
        self.placed_objects.append(top_side.copy(inv_rotate, [x_top[3], ceil_y_shift, ceil_z_top]))


    def front_doors(self, y_cover, total_x, bot_parts, cover_a):
        rail_y = 48
        y_shift = y_cover + rail_y

        # top rail with 10 dist from front reference plane of interrior
        # pannel placed at outer rail

        # pannel shift from front reference plane at y=0
        front_z_shift = self.thickness + 7 # slider part specification
        x_dim_pannel = self.front_panel.dimensions.width
        y_dim_pannel = self.front_panel.dimensions.length

        if self.door_open:
            # open position
            x_left = 0
            x_right = total_x - x_dim_pannel
        else:
            # closed position
            x_left = total_x / 2.0 - x_dim_pannel
            x_right = total_x / 2.0

        front_l = self.add_object(self.front_panel, [x_left, y_shift, front_z_shift])
        front_r = self.add_object(self.front_panel, [x_right, y_shift, front_z_shift])

        door_mirror = ts.mirror(plane_pt=[total_x / 2.0, 0, 0], plane_normal=[1, 0, 0])

        wheels_op = ts.drill_wheels(front_r.aabb)
        front_l.apply_op(wheels_op @ door_mirror)
        front_r.apply_op(wheels_op)
        for f in [front_l, front_r]:
            # Drill pannel holes for slider
            ts.drill_sliders(f)
            # top pannels wheels

        # mill handles
        depth = 12
        y_add = 10
        handle_op = ts.handle_mill_op(40, 150, depth + y_add)
        handle_height = 1000 # lowest OK for avarage adult
        def door_handles(pannel, x_pannel_pos):
            pannel.apply_op(handle_op @ ts.translate([x_pannel_pos + 50, y_shift - y_add, handle_height]))
            pannel.apply_op(handle_op @ ts.translate([x_pannel_pos + x_dim_pannel - 50, y_shift - y_add, handle_height]))
        door_handles(front_l, x_left)
        door_handles(front_r, x_right)


        from l_sys_dragon import get_dragon_vertical_segments
        if self.draft:
            depth = 7
            axiom='++FX'
        else:
            depth = 11
            axiom='+FX'

        segments, x_range, y_range  = get_dragon_vertical_segments(depth, axiom)
        # x_range = (-42, 10)
        # y_range = (-42, 21)
        #x_range = (-21, 5)
        #y_range = (-21, 10)

        x_margin = 50.0
        def scale_solve(range1, range2):
            r1a, r1b = range1
            r2a, r2b = range2
            b = (r2b - r2a) / (r1b - r1a)
            a = r2a - r1a * b
            return a, b
        x_range_out = (x_right + x_margin, x_right + x_dim_pannel - x_margin)
        x0, x1 = scale_solve(x_range, x_range_out)
        y1 = x1
        y_center = (y_dim_pannel + front_z_shift + handle_height) / 2.0
        y0 = y_center - y1 * (y_range[0] + y_range[1]) / 2.0
        sx = lambda x: x0 + x * x1
        sy = lambda y: y0 + y * y1
        scale_seg = lambda seg : ([sx(seg.x), y_shift, sy(seg.y1)], [sx(seg.x), y_shift, sy(seg.y2)])
        mill_dragon = ts.OperationList(*[
            ts.MillOp.ball(3.0, 3.0, [0, 1, 0], *scale_seg(seg))
            for seg in segments
            if seg.y1 != seg.y2
        ])
        front_r.apply_op(mill_dragon)
        front_l.apply_op(mill_dragon @ door_mirror)

        bot_front_l, bot_front_r = bot_parts
        bot_mill = ts.bottom_slider_profile(
            x_dim=total_x, y_shift=y_shift + self.thickness / 2.0, z_shift=self.thickness)
        bot_front_l.apply_op(bot_mill)
        bot_front_r.apply_op(bot_mill)

        # test rail box
        dims = (3000, rail_y, 56)
        top_rail_box = freecad.make_box(dims, origin=[total_x / 2.0 - dims[0] / 2.0, cover_a.aabb[1, 1], cover_a.aabb[1, 2] - dims[2]])
        self.add_object(ts.WPart(top_rail_box, 1, "top_rail"), [0, 0, 0])
        # top front pannels
        #self.add_object(self.ceil_front_side, [])
        #self.add_object(self.ceil__front_middle, [])


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
        drill_vb_strip = self.drill_vb_strip
        drill_rastex = self.drill_rastex
        drill_pins = self.drill_pins
        drill_rail = self.drill_rail
        if self.draft:
            drill_vb_strip = None
            drill_rastex = None
            drill_pins = None
            #drill_rail = None

        top_shelves = lambda fittings : (
            Shelf(1500, self.shelf_top_long, fittings),
            Shelf(1770, self.shelf_top_long, drill_pins),
            Shelf(2040, self.shelf_top_long, drill_pins)
        )

        col_0_shelves = [
            Shelf(1250, self.drawer_30_24.part, drill_rail),
            *top_shelves(fittings=(drill_vb_strip, drill_rastex))
            ]
        col_1_shelves = [
            Shelf(330, self.drawer_40_30.part, drill_rail),
            Shelf(650, self.drawer_40_30.part, drill_rail),
            Shelf(970, self.drawer_40_24.part, drill_rail),
            Shelf(1230, self.shelf_40, drill_pins),
            *top_shelves(fittings=(drill_rastex, drill_rastex))
            ]
        col_2_shelves = [
            Shelf(330, self.drawer_40_20.part, drill_rail),
            Shelf(540, self.drawer_40_20.part, drill_rail),
            Shelf(750, self.drawer_40_20.part, drill_rail),
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
            Shelf(330, self.drawer_30_30.part, drill_rail),
            Shelf(645, self.drawer_30_30.part, drill_rail),
            Shelf(960, self.shelf_30, drill_pins),
            Shelf(1230, self.shelf_30, drill_pins),
            *top_shelves(fittings=(drill_rastex, drill_rastex))
            ]
        col_6_shelves = [
            Shelf(330, self.shelf_40, drill_pins),
            Shelf(705, self.drawer_40_24.part, drill_rail),
            Shelf(960, self.shelf_40, drill_pins),
            Shelf(1230, self.shelf_40, drill_pins),
            *top_shelves(fittings=(drill_rastex, drill_rastex))
            ]

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

    def list_operations(self, fname):
        with open(fname, "w") as f:
            for obj in self.placed_objects:
                f.write(f"{obj.name}\n")
                for op in obj.machine_ops:
                    f.write(f"    {op}\n")


def build_from_placed(doc, placed_parts: List[ts.PlacedPart]):
    print("Placing components")
    all_cuts = []
    all_objects = []
    for p in placed_parts:
        print(p.name)
        obj, cuts = p.make_obj(doc)
        # Export the selected objects to a STEP file
        Part.export([obj], str(model_dir / f"{p.name}.step"))
        all_objects.append(obj)
        all_cuts.extend(cuts)
    print("fuse cut objects")
    #cuts_shape = ts.fuse(all_cuts)
    cuts_shape = Part.makeCompound(all_cuts)
    cuts_obj = doc.addObject("Part::Feature", "cuts compound")
    cuts_obj.Shape = cuts_shape
    Part.export([cuts_obj], str(model_dir / "cuts.step"))

    Part.export(all_objects, str(model_dir / "waredrobe.step"))

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
def get_doc():
    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument()
    else:
        clear_document(FreeCAD.ActiveDocument)
    doc = FreeCAD.ActiveDocument  # Get the cleared (or new) document
    return doc

def waredrobe_model():
    w = Wardrobe(model_dir)
    w.list_operations("operations_list.txt")
    doc = get_doc()
    build_from_placed(doc, w.placed_objects)
    doc.recompute()
    # Ensure all objects in the document are visible
    for obj in doc.Objects:
        obj.Visibility = True  # Make the object visible

    path = str(model_dir / "Warderobe.FCStd")
    doc.saveAs(path)



def pin_drill_jig():
    thickness=18
    wall=3
    clamps_len=30
    lead_len = 20

    dist_8 = 80
    holes_x_8 = [20 + dist_8 * i for i in range(4)]
    length = 40 + holes_x_8[-1]
    dist_10 = 120
    holes_x_10 = [length -20 - dist_10 * i for i in range(3)]
    all_holes = np.array(holes_x_8 + holes_x_10)
    all_holes.sort()
    diffs = all_holes[2:] - all_holes[1:-1]
    print("Holes 8: ", holes_x_8)
    print("Holes 10: ", holes_x_10)
    print("Hole diffs: ", diffs)
    diffs = diffs[diffs != 0.0]
    assert diffs.min() >= (10 + 8)/2 + wall
    length=max(holes_x_8 + holes_x_10) + holes_x_8[0]

    def apply_holes(part, holes, diam):
        cyl_out = ts.make_cylinder(diam / 2 + wall, wall +  lead_len)
        cyl_in = ts.make_cylinder(diam / 2, wall +  lead_len)
        for x in holes:
            shift = ts.translate([x, 0, clamps_len])
            part = ts.fuse([part, cyl_out @ shift])
            part = ts.cut(part, cyl_in @ shift)
        return part

    y_dim = thickness+2*wall
    outer_box = ts.make_box([length, y_dim, clamps_len+wall]) @ ts.translate([0, -y_dim/2, 0])
    cut_box = ts.make_box([length, thickness, clamps_len]) @ ts.translate([0, -thickness/2, 0])
    part = ts.cut(outer_box, cut_box)
    part = apply_holes(part, holes_x_8, 8)
    part = apply_holes(part, holes_x_10, 10)

    mark_box = ts.make_box([10, wall, clamps_len / 2])
    part = ts.cut(part, mark_box @ ts.translate([0, thickness / 2, 0]))
    part = ts.cut(part, mark_box @ ts.translate([length - 10, -thickness / 2 - wall, 0]))


    doc = get_doc()
    ts.add_object(doc, "pin_drill_jig", part)
    doc.recompute()
    path = script_dir / "model" / "pin_drill_jig.FCStd"
    doc.saveAs(str(path))

def main():
    waredrobe_model()
    # pin_drill_jig()


main()