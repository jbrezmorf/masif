from typing import *
import sys

# Adjust the path according to where FreeCAD is installed
freecad_path = '/usr/lib/freecad-python3/lib'  # Set your FreeCAD installation path

if freecad_path not in sys.path:
    sys.path.append(freecad_path)

import FreeCAD
import Part

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


def fuse(shapes):
    assert len(shapes) > 0
    result = shapes[0]
    for s in shapes[1:]:
        result = result.fuse(s)
    return result

def rotate(axis, angle):
    return Transform(rotation=FreeCAD.Rotation(FreeCAD.Vector(*axis), angle))

def translate(pos):
    return Transform(position=FreeCAD.Vector(*pos))


class Transform:
    def __init__(self, position=None, rotation=None):
        if position is None:
            position = FreeCAD.Vector(0, 0, 0)
        if rotation is None:
            rotation=FreeCAD.Rotation()
        # Store the placement (translation + rotation)
        self.placement = FreeCAD.Placement(position, rotation)

    def __rmatmul__(self, shape):
        """Apply the stored transform to the right-hand operand (shape)."""
        if not isinstance(shape, Part.Shape):
            raise TypeError(f"The right operand must be of type `Part.Shape` not {type(shape)}.")

        # Apply the placement transform to the shape
        mat = self.placement.toMatrix()
        transformed_shape = shape.transformGeometry(mat)
        return transformed_shape

def drill(feature: Part.Feature, tool:'Shape', position:Union[FreeCAD.Placement, List[float]], rotation=None):
    # Create a copy of the tool and apply possition then cut it from part in actual placement.
    #
    # Set the position and rotation of the tool
    print("    drill(...", end=None)
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
    pin_in_diam = 5
    pin_in_l = 7
    pin_out_diam = 7 + 0.5
    pin_out_l = 10 + 0.5

    # shelf drill extension
    box_dims = (pin_out_l, pin_out_diam, pin_out_diam/2)
    box = Part.makeBox(*box_dims, FreeCAD.Vector(0, -box_dims[1] / 2, ))

    # Create the left barrel (inner)
    left_barrel = Part.makeCylinder(pin_in_diam / 2, pin_in_l)
    # Move the left barrel to be centered around the origin
    left_barrel.translate(FreeCAD.Vector(0, 0, -pin_in_l))

    # Create the right barrel (outer)
    right_barrel = Part.makeCylinder(pin_out_diam / 2, pin_out_l)
    # Move the right barrel to be centered around the origin
    barrels = left_barrel.fuse(right_barrel)
    barrels = barrels @ rotate([0, 1, 0], +90) @ translate([0, 0, pin_out_diam/2])

    # Fuse the box with the barrel part
    final_part = barrels.fuse(box)

    return final_part



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
    single_pin = pin()
    # Assume panel and shelf are objects with Placement
    z_step = 40
    dist_from_front = 40
    y_shift = shelf_width / 2 - dist_from_front
    pins = [
        single_pin.copy().translate(FreeCAD.Vector(0, y, z))
        for z in [-z_step, 0, z_step]
        for y in [-y_shift, y_shift]
    ]
    return fuse(pins)

def dowel(thickness):
    """
    Dowel extends left to be drilled to the pannel.
    :param thickness:
    :return:
    """
    diam = 6
    l = 35.5
    return Part.makeCylinder(diam / 2, l) @ rotate([0, 1, 0], 90) @ translate([-14.25, 0, thickness/2])


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
    rastex_part = Part.makeCylinder(hetix_diam / 2, hetix_l) @ translate([hetix_x, 0, 0])
    # Create the pin_in cylinder (to the left of hetix, along X-axis with Y shift)
    pin_in = Part.makeCylinder(pin_in_diam / 2, pin_in_l) @ rotate([0, 1, 0], -90) @ translate([0, 0, z_shift])
    # Create the pin_out cylinder (to the right of hetix, along X-axis with Y shift)
    pin_out = Part.makeCylinder(pin_out_diam / 2, pin_out_l) @ rotate([0, 1, 0], 90) @ translate([0, 0, z_shift])

    # Combine all parts into a single shape
    combined = fuse([pin_in, pin_out, rastex_part])
    return combined



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
    large = Part.makeCylinder(vb_diam_large / 2, vb_l_large) @ translate([vb_large_x, 0, 0])
    small = Part.makeCylinder(vb_diam_small / 2, vb_l_small) @ translate([vb_small_x, 0, 0])
    pin_out = Part.makeCylinder(pin_in_diam / 2, pin_in_l) @ rotate([0, 1, 0], -90) @ translate([0, 0, pin_z_shift])

    # Combine all parts into a single shape
    combined = fuse([large, small, pin_out])
    return combined


def strong_edge(thickness, shelf_width, tool, through:bool=False):
    thickness = 18
    _rastex = tool(thickness, through)
    _dowel = dowel(thickness)
    dist_from_front = 40
    y_shift = shelf_width / 2 - dist_from_front  # 260
    parts = [_rastex, _dowel, _dowel, _dowel, _rastex]
    yy = [-y_shift, -120, 20, 160, y_shift]
    parts = [
        p.copy() @ translate([0, y, 0])
        for p, y in zip(parts, yy)]
    # - 260, -160, -120, -20, 20, 120, 160, 260
    return side_symmetric(fuse(parts))

def side_symmetric(shape):
    r_side = shape
    l_side = shape.copy() @ rotate([0, 0, 1], 180)
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

    def side_fn(angle, holes):
        drilled = [Part.makeCylinder((d - 2.5) / 2, x_depth)
                   @ rotate([0, 1, 0], angle)
                   @ translate([0, y - shelf_width/2 + y_shift, z + z_shift])
                    for d, y, z in holes]
        return fuse(drilled)

    sides = [side_fn(angle, holes)
             for angle, holes in zip((90, -90), (holes_l, holes_r))
            ]
    return tuple(sides)


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