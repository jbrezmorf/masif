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
                     make_cylinder, make_box, fuse, fvec, vec_list)

#Vector = np.ndarray

def add_object(doc, name, shape, translate, rotate = None):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    if rotate is None:
        rotate = FreeCAD.Rotation()
    assert len(translate) == 3
    pos_vec = FreeCAD.Vector(*translate)
    placement = FreeCAD.Placement(pos_vec, rotate)
    obj.Placement = placement
    return obj


def aabb(bb:FreeCAD.BoundBox):
    return np.array( [(bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)] )






def drill(feature: Part.Feature, tool:'Shape', position:Union[FreeCAD.Placement, List[float]] = None, rotation=None):
    # Create a copy of the tool and apply possition then cut it from part in actual placement.
    #
    # Set the position and rotation of the tool
    print("    drill(...", end=None)
    if position is None:
        position = [0, 0, 0]
    if isinstance(position, FreeCAD.Placement):
        tool_placement = position
    else:
        if rotation is None:
            rotation = FreeCAD.Rotation()  # No rotation by default
        assert len(position) == 3
        tool_placement = FreeCAD.Placement(FreeCAD.Vector(position), rotation)
    tool_shape = tool.copy().transformGeometry(tool_placement.toMatrix())
    f_placement = feature.Placement
    part_shape = feature.Shape.copy().transformGeometry(f_placement.toMatrix())
    part_shape.Placement = FreeCAD.Placement()
    # Perform the cut operation
    result_shape = part_shape.cut(tool_shape)
    inverse_placement = f_placement.inverse()
    inv_mat = inverse_placement.toMatrix()
    res_shape_back = result_shape.transformGeometry(inv_mat)
    feature.Shape = res_shape_back
    feature.Placement = f_placement
    print(")")
    return feature


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

def dowel(left_extent=0, dowel_vec=None):
    """
    Dowel extends left to be drilled to the pannel.
    left_extent :
    0 : dowel centered
    >0 : abs(left_extent) is size of left drill
    <0 : abs(left_extent) is size of right drill
    :param thickness:
    :return:
    """
    diam = 6
    l = 35
    if left_extent == 0:
        right_extent = left_extent = l / 2
    elif left_extent > 0:
        right_extent = l - left_extent
    elif left_extent < 0:
        right_extent = abs(left_extent)
        left_extent = l - right_extent
    else:
        raise ValueError("Non-real dowel extent.")
    if dowel_vec is None:
        dowel_vec = [1, 0, 0]
    drill_left = DrillOp(diam / 2, left_extent + 0.5, direction=-np.array(dowel_vec))
    drill_right = DrillOp(diam / 2, right_extent + 0.5, direction=dowel_vec)
    dowel_pair = OperationList(drill_left, drill_right)
    return dowel_pair

def dowel_row(a, b, n, dowel_vec, edge_vec, left_extent=0):
    """
    Produce two drill operations one to the X<0 half space,
    one for the X>0 half space.
    :param a:
    :param b:
    :param n:
    :param dowel_vec:
    :param edge_vec:
    :param left_extent:
    :return:
    """
    dowel_pair = dowel(left_extent, dowel_vec=dowel_vec)
    y_pos_vec = [y * np.array(edge_vec) for y in np.linspace(a, b, n)]
    row = OperationList(*[dowel_pair @ translate(yy) for yy in y_pos_vec])
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
    hetix_diam = 15.5
    hetix_l = 13.5
    # hetix_x = 34
    if through:
        pin_in_diam = 8.5
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



def strong_edge(thickness, shelf_width, tool, through:bool=False):
    thickness = 18
    dowel_to_pannel = 14
    rastex_pair = tool(thickness, through)
    dowel_pair = dowel(left_extent=dowel_to_pannel) @ translate([0, 0, thickness/2.0])
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

def rail():
    """
    In order to support rails at both sides of the pannel
    at same height we have distinct drill patterns for the left and the right
    side of the pannel. The two side drilling function has to support
    tools as pairs and decide for the left or right according to the side.
    :return:

    Pojez 1-2mm dovnitř, dopředu více, celkem cca 4
    """
    # holes relative to rail front and axis
    z_shift = 47    # axis of rail from bottom face of the box
    x_depth = 12
    shelf_width = 600
    y_shift = 2     # rails 2mm from the front

    holes_l = [
        (6, 35, 0),
        (7, 114.5, 0),
        (4, 259, 0),
        (4, 538, -9)    # +/-9 hole
    ]

    holes_r = [
        (7, 50, 0),
        (6, 99.5, 0),
        (4, 323, 0),
        (4, 538, 9)  # +/-9 hole
    ]

    def side_fn(x_dir, holes):
        ops = [DrillOp((d - 2.5) / 2.0, x_depth, direction=[x_dir, 0, 0])
                   @ translate([0, y, z + z_shift])
                    for d, y, z in holes]
        # total mill height = 44mm
        rail_height = 44
        ops.append(MillOp(rail_height / 2.0, 1.0, direction=[x_dir, 0, 0],
                          start=[0, 0, z_shift], end=[0, shelf_width, z_shift]))
        pannel_ops = OperationList(*ops)
        shelf_op = NoneOp()

        # drill composed operations are relative to shlef_width center
        return OperationList(pannel_ops, shelf_op) @ translate([0,  - shelf_width/2 + y_shift, 0])

    side_ops = OperationList(
        side_fn(x_dir=+1.0, holes=holes_l),
        side_fn(x_dir=-1.0, holes=holes_r)
    )
    return side_ops


def drawer(width, height, depth):
    rail_thickness = 25 / 2
    rail_height = 45
    z_shift = 47 - rail_height / 2
    components = [
        Part.makeBox(rail_thickness, depth, rail_height) @ translate([0, 0, z_shift]),
        Part.makeBox(width, depth, height) @ translate([rail_thickness, 0, 0]),
        Part.makeBox(rail_thickness, depth, rail_height) @ translate([rail_thickness + width, 0, z_shift])
        ]
    return fuse(components)


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


def dowel_connect(part_a:PlacedPart, part_b:PlacedPart, dowel_dir, edge_dir,
                  other_pos=None, rel_range=(None, None, None), left_extent = 0):
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
    i_min, i_max = 0, 1
    bb_a = part_a.aabb
    bb_b = part_b.aabb
    connect_plane_a = bb_a[i_max, dowel_dir]
    connect_plane_b = bb_b[i_min, dowel_dir]
    assert connect_plane_a == connect_plane_b, f"{connect_plane_a} != {connect_plane_b}"
    edge_min, edge_max = interval_intersect(bb_a[:, edge_dir], bb_b[:, edge_dir], rel_range[edge_dir])
    edge_min, edge_max = edge_min + 20, edge_max -20
    if edge_max < edge_min:
        return part_a, part_b
    dowel_dist = 80
    n_dowels = int((edge_max - edge_min) / dowel_dist)
    if n_dowels < 3:
        # 2 dowels case
        edge_min -= 10
        edge_max += 10
        # compute remaining dist
        dowel_dist = edge_max - edge_min
        if edge_max - edge_min < 1.0:
            return part_a, part_b
        if dowel_dist > 20:
            n_dowels = 2
        elif dowel_dist > 0:
            n_dowels = 1
        else:
            # n_dowels == 0
            return part_a, part_b

    dowel_vec = [0, 0, 0]
    dowel_vec[dowel_dir] = 1.0
    edge_vec = [0, 0, 0]
    edge_vec[edge_dir] = 1.0
    dowel_ops = dowel_row(edge_min, edge_max, n_dowels, dowel_vec, edge_vec, left_extent=left_extent)
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


