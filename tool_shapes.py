from typing import *
import sys
import attrs
import numpy as np
from functools import cached_property

import freecad

import FreeCAD
import Part
from machine import (DrillOp, MillOp, NoneOp, OperationList,
                     rotate, translate, Transform,
                     make_cylinder, make_box, fuse, cut, fvec, vec_list)

#Vector = np.ndarray

def add_object(doc, name, shape, translate = None, rotate = None):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    if  translate is None:
        translate = [0, 0, 0]
    if rotate is None:
        rotate = FreeCAD.Rotation()
    assert len(translate) == 3
    pos_vec = FreeCAD.Vector(*translate)
    placement = FreeCAD.Placement(pos_vec, rotate)
    obj.Placement = placement
    return obj


def aabb(bb:FreeCAD.BoundBox):
    return np.array( [(bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)] )






# def drill(feature: Part.Feature, tool:'Shape', position:Union[FreeCAD.Placement, List[float]] = None, rotation=None):
#     # Create a copy of the tool and apply possition then cut it from part in actual placement.
#     #
#     # Set the position and rotation of the tool
#     print("    drill(...", end=None)
#     if position is None:
#         position = [0, 0, 0]
#     if isinstance(position, FreeCAD.Placement):
#         tool_placement = position
#     else:
#         if rotation is None:
#             rotation = FreeCAD.Rotation()  # No rotation by default
#         assert len(position) == 3
#         tool_placement = FreeCAD.Placement(FreeCAD.Vector(position), rotation)
#     tool_shape = tool.copy().transformGeometry(tool_placement.toMatrix())
#     f_placement = feature.Placement
#     part_shape = feature.Shape.copy().transformGeometry(f_placement.toMatrix())
#     part_shape.Placement = FreeCAD.Placement()
#     # Perform the cut operation
#     result_shape = part_shape.cut(tool_shape)
#     inverse_placement = f_placement.inverse()
#     inv_mat = inverse_placement.toMatrix()
#     res_shape_back = result_shape.transformGeometry(inv_mat)
#     feature.Shape = res_shape_back
#     feature.Placement = f_placement
#     print(")")
#     return feature


def pin():
    # pin real dimensions
    pin_in_diam = 5.0
    pin_in_l = 7.0
    pin_out_diam = 7 + 0.5
    pin_out_l = 10 + 0.5
    pin_z = pin_out_diam / 2
    # shelf drill extension
    box_dims = (pin_out_l, pin_out_diam, pin_out_diam/2)
    box = Part.makeBox(*box_dims, FreeCAD.Vector(0, -box_dims[1] / 2, ))
    shelf_op = MillOp(pin_out_diam/2.0, pin_out_l,
           direction=[1, 0, 0], start=[0, 0, -pin_z], end=[0, 0, +pin_z])

    # pannel drill
    pannel_op = DrillOp(pin_in_diam/2, pin_in_l,
            start=[0, 0, pin_z], direction=[-1, 0, 0])

    # # Create the left barrel (inner)
    # left_barrel = Part.makeCylinder(pin_in_diam / 2, pin_in_l)
    # # Move the left barrel to be centered around the origin
    # left_barrel.translate(FreeCAD.Vector(0, 0, -pin_in_l))
    #
    # # Create the right barrel (outer)
    # right_barrel = Part.makeCylinder(pin_out_diam / 2, pin_out_l)
    # # Move the right barrel to be centered around the origin
    # barrels = left_barrel.fuse(right_barrel)
    # barrels = barrels @ rotate([0, 1, 0], +90) @ translate([0, 0, pin_out_diam/2])
    #
    # # Fuse the box with the barrel part
    # final_part = barrels.fuse(box)
    return pannel_op, shelf_op



def pin_edge(shelf_width):
    """
    All pin drills associated with shelf edge.
    Assume shelf bottom edge passing through origin.
    Coordinate system:
    X - shelf length
    Y - shelf depth/width
    Z - shelf thickness
    :return:
    """
    pannel_pin, shelf_pin = pin()
    # Assume panel and shelf are objects with Placement
    z_step = 40
    dist_from_front = 40
    y_shift = shelf_width / 2 - dist_from_front
    pins = lambda x_pin: [
        (x_pin.copy()) @ (translate([0, y, z]))
        for z in [-z_step, 0, z_step]
        for y in [-y_shift, y_shift]
    ]
    return OperationList(
        OperationList(*pins(pannel_pin)),
              OperationList(*pins(shelf_pin))
    )

def dowel(left_extent=0, dowel_vec=None, diam=8, length=35):
    """
    Dowel extends left to be drilled to the pannel.
    left_extent :
    0 : dowel centered
    >0 : abs(left_extent) is size of left drill
    <0 : abs(left_extent) is size of right drill
    :param thickness:
    :return:
    """
    if left_extent == 0:
        right_extent = left_extent = length / 2
    elif left_extent > 0:
        right_extent = length - left_extent
    elif left_extent < 0:
        right_extent = abs(left_extent)
        left_extent = length - right_extent
    else:
        raise ValueError("Non-real dowel extent.")
    if dowel_vec is None:
        dowel_vec = [1, 0, 0]
    drill_left = DrillOp(diam / 2, left_extent + 1, direction=-np.array(dowel_vec))
    drill_right = DrillOp(diam / 2, right_extent + 1, direction=dowel_vec)
    dowel_pair = OperationList(drill_left, drill_right)
    return dowel_pair

def dowel_row(y_pos_vec, dowel_vec, edge_vec, left_extent=0, dowel_fn=dowel):
    """
    Produce two drill operations one to the X<0 half space,
    one for the X>0 half space.
    :param edge_0: start position in edge_vec direction
    :param edge_dist: dowel distance in edge_vec direction
    :param n: number of dowels to place
    :param dowel_vec: direction of the dowel axis [0, 1, 2]
    :param edge_vec: direction of the connected edge axis [0, 1, 2] != dowel_vec
    :param left_extent: extension of the dowels to the left (>0) or to the right (<0), or centered dowels for (=0)
    :return: Dowel drilling operations OpList[ DrillPair, ..]
    """
    edge_vec = np.array(edge_vec)
    dowel_pair = dowel_fn(left_extent, dowel_vec=dowel_vec)
    row = OperationList(*[dowel_pair @ translate(yy * edge_vec) for yy in y_pos_vec])
    return row


def rastex(shelf_thickness, through:bool=False):
    """
    Drilling tool for rastex fitting for the whole shelf edga
    Composed of:
    - rastex fitting
    - wooden dowels every 150-200mm
    IKEA use fittings 50mm from edges, independent of the shelf depth.
    We use the same, that possibly makes the front edge more robust.
    50, rastex, 125, dowel, 125, dowel, 125, dowel, 170, rastex, 50


    :param self:
    :param shelf_thickness:
    :param through:
    :return:
    """
    hetix_diam = 15.5  # 15 exact
    hetix_l = 13.5     # 13 exact
    # hetix_x = 34
    if through:
        pin_in_diam = 8.5   # 8 exact
        pin_in_l = shelf_thickness
        hetix_x = 24.5  # assume shorter double ended dowel and 0.5 correction for 18mm pannel
        # asume usage without side spring
    else:
        # M6 fitting
        pin_in_diam = 8
        pin_in_l = 11.5
        hetix_x = 34
    # shlef connection
    pin_out_diam = 8.5
    pin_out_l = hetix_x

    # center of fitting should be at the center of the shelf
    z_shift = shelf_thickness / 2

    # Create the hetix cylinder (vertical along Z-axis)
    # Create the pin_in cylinder (to the left of hetix, along X-axis with Y shift)
    shelf_drill = OperationList(
   DrillOp(hetix_diam / 2, hetix_l, start=[hetix_x, 0, 0]),
        DrillOp(pin_out_diam / 2, pin_out_l, start = [0, 0, z_shift], direction=[1, 0, 0])
    )
    # Create the pin_out cylinder (to the right of hetix, along X-axis with Y shift)
    pannel_drill = DrillOp(pin_in_diam / 2, pin_in_l, start=[0, 0, z_shift], direction=[-1, 0, 0])
    return OperationList(pannel_drill, shelf_drill)



def vb(shelf_thickness, through=False):
    """
    Drilling tool for rastex fitting for the whole shelf edga
    Composed of:
    - rastex fitting
    - wooden dowels every 150-200mm
    IKEA use fittings 50mm from edges, independent of the shelf depth.
    We use the same, that possibly makes the front edge more robust.
    50, rastex, 125, dowel, 125, dowel, 125, dowel, 170, rastex, 50


    :param self:
    :param shelf_thickness:
    :param through:
    :return:
    """
    vb_diam_large = 20
    vb_l_large = 12.5
    vb_large_x = 10
    vb_diam_small = 10
    vb_l_small = 10.5
    vb_small_x = 32 + vb_large_x

    # M6 fitting
    pin_in_diam = 8
    pin_in_l = 11.5
    # center of fitting should be at the center of the shelf
    pin_z_shift = 8

    # Create the hetix cylinder (vertical along Z-axis)
    # large = Part.makeCylinder(vb_diam_large / 2, vb_l_large) @ translate([vb_large_x, 0, 0])
    # small = Part.makeCylinder(vb_diam_small / 2, vb_l_small) @ translate([vb_small_x, 0, 0])
    # pin_out = Part.makeCylinder(pin_in_diam / 2, pin_in_l) @ rotate([0, 1, 0], -90) @ translate([0, 0, pin_z_shift])

    # Combine all parts into a single shape
    # combined = fuse([large, small, pin_out])

    shelf_drill = OperationList(
        DrillOp(vb_diam_large / 2.0, vb_l_large, start=[vb_large_x, 0, 0]),
        DrillOp(vb_diam_small / 2.0, vb_l_small, start=[vb_small_x, 0])
    )
    # Create the pin_out cylinder (to the right of hetix, along X-axis with Y shift)
    pannel_drill = DrillOp(pin_in_diam / 2.0, pin_in_l, start=[0, 0, pin_z_shift], direction=[-1, 0, 0])
    return OperationList(pannel_drill, shelf_drill)



def strong_edge(thickness, shelf_width, tool, through:bool=False, dowel_fn=dowel):
    thickness = 18
    dowel_to_pannel = 14
    rastex_pair = tool(thickness, through)
    dowel_pair = dowel_fn(left_extent=dowel_to_pannel) @ translate([0, 0, thickness/2.0])
    dist_from_front = 40
    y_shift = shelf_width / 2 - dist_from_front  # 260
    parts = [rastex_pair, dowel_pair, dowel_pair, dowel_pair, rastex_pair]
    pannel_parts, shelf_parts = zip(*parts)
    yy = [-y_shift, -120, 20, 160, y_shift]
    place = lambda parts : OperationList(*[
        p @ translate([0, y, 0])
        for p, y in zip(parts, yy)])
    # - 260, -160, -120, -20, 20, 120, 160, 260
    placed = map(place, [pannel_parts, shelf_parts])
    sides = side_symmetric(OperationList(*placed))
    return sides

def side_symmetric(shape: DrillOp):
    r_side = shape
    l_side = shape @ (rotate([0, 0, 1], 180))
    return (l_side, r_side)


@attrs.define
class Rail:
    height: float
    thickness: float

    def predrill(self, screw_diam, shelf_width):
            """
            In order to support rails at both sides of the pannel
            at same height we have distinct drill patterns for the left and the right
            side of the pannel. The two side drilling function has to support
            tools as pairs and decide for the left or right according to the side.
            :return:

            Pojez 1-2mm dovnitř, dopředu více, celkem cca 4
            """
            # holes relative to rail front and axis
            drill_depth = 12
            y_shift = 2  # rails 2mm from the front
            # total mill height = 44mm
            mill_depth = 1.0  # reserve horizontal space on a single side of rail, recommended 1mm
            rail_height = self.height
            screw_diam = 3

            # left face of pannel
            # hole tuple: (drill depth, Y pos (from front), vertical pos from rail axis, rail_diam)
            holes_l = [
                (drill_depth, 35, 0, 6),  #
                (drill_depth, 114.5, 0, 7),
                (0.5, 259, 0, 4),  # ??
                (0.5, 538, -9, 4.5)  # +/-9 hole
            ]

            # right place of pannel
            holes_r = [
                (drill_depth, 50, 0, 7),
                (drill_depth, 99.5, 0, 6),
                (0.5, 323, 0, 4),   # ??
                (0.5, 538, 9, 4.5)  # +/-9 hole
            ]

            def side_fn(x_dir, holes):
                ops = [DrillOp(screw_diam / 2.0, depth, direction=[x_dir, 0, 0])
                       @ translate([0, y, z])
                       for depth, y, z, _ in holes]
                ops.append(MillOp(rail_height / 2.0, mill_depth, direction=[x_dir, 0, 0],
                                  start=[0, 0, 0], end=[0, shelf_width, 0]))
                pannel_ops = OperationList(*ops)
                shelf_op = NoneOp()

                # drill composed operations are relative to shlef_width center
                return OperationList(pannel_ops, shelf_op) @ translate([0, - shelf_width / 2 + y_shift, 0])

            side_ops = OperationList(
                side_fn(x_dir=+1.0, holes=holes_l),
                side_fn(x_dir=-1.0, holes=holes_r)
            )
            return side_ops


@attrs.define
class Drawer:
    part: 'WPart'
    dims: List[float]
    rail_z: float
    rail: Rail

    @classmethod
    def make(cls, dimensions, n_parts, rail_z, rail):
        dx, dy, dz = dimensions
        components = [
            Part.makeBox(rail.thickness, dy, rail.height) @ translate([0, 0, rail_z]),
            Part.makeBox(dx, dy, dz) @ translate([rail.thickness, 0, 0]),
            Part.makeBox(rail.thickness, dy, rail.height) @ translate([rail.thickness + dx, 0, rail_z])
            ]
        shape = fuse(components)
        name = f"drawer_{dx}_{dy}"
        part = WPart(shape, n_parts, name)
        return cls(part, dimensions, rail_z, rail)

    def rail_drill(self, screw_diam):
        width = self.dims[1]
        return self.rail.predrill(screw_diam, width) @ translate([0, 0, self.rail_z + self.rail.height / 2.0])

@attrs.define
class PlankPart:
    length : float
    width : float
    rot : FreeCAD.Rotation   # rotation object
    thick : float

    def shape(self):
        shape = Part.makeBox(self.length, self.width, self.thick)
        rot_mat = FreeCAD.Placement(FreeCAD.Vector(0,0,0), self.rot).toMatrix()
        shape = shape.transformGeometry(rot_mat)
        bb = shape.BoundBox
        return shape @ translate([-bb.XMin, -bb.YMin, -bb.ZMin])




@attrs.define
class WPart:
    shape: Part.Shape
    n_parts: int
    name: str
    dimensions: PlankPart = None
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
        plank = PlankPart(length, width, rot_total, thick)
        part_shape = plank.shape()
        return cls(part_shape, n_parts, name, dimensions=plank)


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
    """
    TODO:
    - part as a shape in a reference position
    - store complete placement
    - store list of cuts
    """
    part : WPart
    #position: FreeCAD.Vector       # Full placement object
    position: List[float]
    obj: 'Part.Feature' = None     # set after init
    name : str = ""
    machine_ops: List[Any] = attrs.Factory(list)

    @cached_property
    def placement(self) -> Transform:
        pos = fvec(self.position)
        new_placement = FreeCAD.Placement(pos, FreeCAD.Rotation())
        return Transform(new_placement * self.part.shape.Placement)

    @cached_property
    def aabb(self):
        final_shape = self.part.shape @ self.placement
        return aabb(final_shape.BoundBox)

    def max(self, ax):
        return self.aabb[1][ax]

    def apply_op(self, drill_op):
        """
        Add machine operation to the list of operations
        :param drill_op:
        :return:
        """
        inv_placement = self.placement.inverse()
        drill_ops = (drill_op @ inv_placement).expand()
        self.machine_ops.extend(drill_ops)

    def apply_machine_ops(self):
        shape = self.part.shape
        cuts = []
        for op in self.machine_ops:
            # # Create a cylinder for the hole (drill) with the given radius and length
            # cylinder = Part.makeCylinder(op.radius, op.length)
            #
            # # Create a placement for the cylinder based on the DrillOp start and direction
            # direction_normalized = op.direction.normalize()
            #
            # # Define the rotation to align the cylinder along the direction vector
            # rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), direction_normalized)
            #
            # # Apply the placement (translation + rotation) to the cylinder
            # cylinder.Placement = FreeCAD.Placement(op.start, rotation)
            #
            print("   apply ", repr(op))
            tool = op.tool_shape
            placed_cut = tool.copy() @ self.placement
            cuts.append(placed_cut)
            # Subtract the cylinder from the original shape to simulate drilling
            shape = shape.cut(tool)

        return shape, cuts


    def make_obj(self, doc):
        obj = doc.addObject("Part::Feature", self.name)
        shape, cuts = self.apply_machine_ops()
        obj.Shape = shape
        obj.Placement = self.placement.placement
        return obj, cuts

def interval_intersect(bb_a, bb_b, rel_range = None):
    i_min, i_max = 0, 1
    if rel_range is None:
        rel_range = (0.0, 1.0)
    rel_a, rel_b = rel_range
    a, b = max(bb_a[i_min], bb_b[i_min]), min(bb_a[i_max], bb_b[i_max])
    return (1 - rel_a) * a + rel_a * b, (1 - rel_b) * a + rel_b * b


from functools import cached_property
from itertools import product, accumulate
from bisect import bisect_right


@attrs.define
class CombinationFinder:
    spacing: List[float]
    max_len: float

    @cached_property
    def sum_combos(self) -> List[Tuple[float, List[int]]]:
        """
        Lazily computes all unique sums of combinations from V with repetitions,
        up to the maximum length L_max. The combinations are represented by counts
        of each index in V. For the same 'total_length', stores the combination
        with the minimal number of items.
        """
        # Generate all possible counts within the max repetitions
        space_vec = np.array(self.spacing)
        ranges = [range(int(self.max_len // dist) + 1) for dist in self.spacing]
        sum_to_combo = {}
        max_num_items = float('inf')
        for counts in product(*ranges):
            total_length = np.dot(space_vec, counts)
            num_items = sum(counts)
            update = num_items, counts
            actual = sum_to_combo.setdefault(total_length, (max_num_items, []))
            sum_to_combo[total_length] = min(actual, update)
        sums_list = sorted([(tlen, counts) for tlen, (count, counts) in sum_to_combo.items()])
        return sums_list

    def get(self, L: float) -> Tuple[float, List[int]]:
        """
        Finds the combination with the largest sum less than or equal to L.

        :param L: The target length.
        :return: A tuple containing the sum and the counts of indices in V, or None if no such sum exists.
        """
        sums = self.sum_combos
        idx = bisect_right(sums, L, key = lambda item: item[0])
        # idx is first sum > L
        if idx < 2:
            # idx == 0 => not found
            # idx == 1 => found only item 0 with % total_length
            return 0, []  # No sum less than or equal to L
        else:
            closest_sum, counts = sums[idx - 1]
            return closest_sum, counts


dowel_plan = CombinationFinder([40, 80,  120], 2000)


def dowel_connect(part_a:PlacedPart, part_b:PlacedPart, dowel_dir, edge_dir,
                  other_pos=None, rel_range=(None, None, None), left_extent = 0,
                  dowel_row_fn=dowel_row, dowel_dist=100):
    """
    Place row of connecting dowels for two rectangular, axes aligned parts.
    The connecting surface is automatically detected from 'dowel_dir',
    'edge_dir' lays in this surface; remaining axis is named 'other'
    Dowel row extends over the connecting surface in the 'edge_dir' axis.
    Position along 'other' axis is given as center of the connecting surface by default
    or its absolute position could be given by 'other_pos'.
    Relative edge edtend or other dir position could be limited by rel_range.
    Rel range is tuple of three items one for each axis, each could be None (full extend)
    or pair of numbers in interval (0, 1.0) denoting sub range of connecting surface.
    :param dowel_dir: 0| 1 | 2; axis of dowels
    :param edge_dir: 0| 1 | 2; axis of the dowel row
    :param other_pos:
    :return:
    """
    # return part_a, part_b   # Temporarly disable all dowels
    i_min, i_max = 0, 1
    bb_a = part_a.aabb
    bb_b = part_b.aabb
    connect_plane_a = bb_a[i_max, dowel_dir]
    connect_plane_b = bb_b[i_min, dowel_dir]
    assert connect_plane_a == connect_plane_b, f"{connect_plane_a} != {connect_plane_b}"
    edge_min, edge_max = interval_intersect(bb_a[:, edge_dir], bb_b[:, edge_dir], rel_range[edge_dir])
    edge_min, edge_max = edge_min + 15, edge_max - 15

    dowel_positions = []
    row_len = edge_max - edge_min
    total_len, spacing_counts = dowel_plan.get(row_len)
    if total_len == 0:
        # less then min spacing
        # 2 dowels case
        # compute remaining dist
        if row_len > 20:
            # total edge len > 50
            dowel_positions = [0, row_len]
        elif row_len > 0:
            dowel_positions = [0]
    else:
        dowel_positions = [0]
        for count, space in zip(spacing_counts, dowel_plan.spacing):
            dowel_positions.extend( count * [space])
        dowel_positions = list(accumulate(dowel_positions))
    if len(dowel_positions) == 0:
        return part_a, part_b
    # center n dowels between edge_min edge_max
    assert dowel_positions[-1] <= row_len
    reminder = row_len - dowel_positions[-1]
    dowel_row_pos = [edge_min + reminder / 2.0 + pos for pos in dowel_positions]
    dowel_vec = [0, 0, 0]
    dowel_vec[dowel_dir] = 1.0
    edge_vec = [0, 0, 0]
    edge_vec[edge_dir] = 1.0
    dowel_ops = dowel_row_fn(dowel_row_pos, dowel_vec, edge_vec, left_extent=left_extent)
    for d in dowel_ops:
        dowel_left, dowel_right = d
        position = [0, 0, 0]
        position[dowel_dir] = connect_plane_a
        position[dowel_dir] = connect_plane_a
        remain_dir = 3 - dowel_dir - edge_dir
        if other_pos is None:
            other_min, other_max = interval_intersect(bb_a[:, remain_dir], bb_b[:, remain_dir], rel_range[remain_dir])
            #assert bb_a[i_min][remain_dir] == bb_b[i_min][remain_dir]
            #assert bb_a[i_max][remain_dir] == bb_b[i_max][remain_dir]
            if (other_max - other_min) < 16:
                # zero connecting surface
                return part_a, part_b
            remain_pos = (other_min + other_max) / 2.0
        else:
            remain_pos = other_pos
        position[remain_dir] = remain_pos
        shift = translate(position)
        part_a.apply_op(dowel_left @ (shift))
        part_b.apply_op(dowel_right @ (shift))
    return part_a, part_b

def bottom_slider():
    """
    Origin at slider center in X and Y, at slider/pannel connectin in Z
    axis.
    :return:
    """
    return OperationList(
        DrillOp(8.0 / 2, 10, start=[-16, 0, 0]),
        DrillOp(8.0 / 2, 10, start=[+16, 0, 0])
        )

def drill_sliders(front_pannel:PlacedPart):
    x_edge_dist = 32 / 2 + 30
    min_aabb, max_aabb = front_pannel.aabb
    thickness = max_aabb[1] - min_aabb[1]
    z_pos = min_aabb[2]
    y_pos = (min_aabb[1] + max_aabb[1]) / 2.0
    front_pannel.apply_op(OperationList(
        bottom_slider() @ translate([min_aabb[0] + x_edge_dist, y_pos, z_pos]),
        bottom_slider() @ translate([max_aabb[0] - x_edge_dist, y_pos, z_pos]),
    ))

def bottom_slider_profile(x_dim, y_shift, z_shift):
    # bottom slider profile
    return MillOp(7.5 / 2.0, 8, direction=[0, 0, -1], start=[0, y_shift, z_shift], end=[x_dim, y_shift, z_shift])


def top_wheel(thickness: float) -> OperationList:
    """
    Connection of single top wheel, origin at wheel center in X,
    pannel center in Y,
    pannel top in Z
    :return:
    """
    single_bolt = lambda x : [
            DrillOp(5.5 / 2, 40, direction=[0, 0, -1], start=[x, 0, 0]),
            DrillOp(12 / 2.0, 14, direction=[0, -1, 0], start=[x, thickness/2.0 , -40])
            ]
    bolt_dist = 64
    ops = single_bolt(x=-bolt_dist / 2.0) + single_bolt(x=bolt_dist / 2.0)
    return OperationList(*ops)


def drill_wheels(front_pannel:PlacedPart):
    bolt_dist = 64
    x_edge_dist = bolt_dist / 2.0 + 50
    min_aabb, max_aabb = front_pannel.aabb
    thickness = max_aabb[1] - min_aabb[1]
    z_pos = max_aabb[2]
    y_pos = (min_aabb[1] + max_aabb[1]) / 2.0
    wheel = top_wheel(thickness)
    front_pannel.apply_op(OperationList(
        wheel @ translate([min_aabb[0] + x_edge_dist, y_pos, z_pos]),
        wheel @ translate([max_aabb[0] - x_edge_dist, y_pos, z_pos]),
    ))
