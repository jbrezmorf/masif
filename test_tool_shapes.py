"""
Each test creates a separate STEP file drilling
part into test vertical plane and test horizontal shelf.
"""
import pytest

import tool_shapes as ts

import FreeCAD
import Part
from pathlib import Path

# Get the directory of the current script
script_dir = Path(__file__).parent

def make_scene(tool_shape, name):
    doc = FreeCAD.newDocument()
    # vertical face, right face at origin
    z_pannel = 200
    shelf_width = 600
    shelf_l = 100
    thickness = 18
    pannel = Part.makeBox(thickness, shelf_width, z_pannel)
    pannel_f = ts.add_object(doc, 'pannel', pannel, [-thickness, 0, 0])
    # horizontal shelf, bottom edge at 50

    z_shelf_pos = z_pannel / 2
    shelf = Part.makeBox(shelf_l, shelf_width, thickness)
    shelf_r_f = ts.add_object(doc, 'shelf', shelf, [0, 0, z_shelf_pos])
    shelf_l_f = ts.add_object(doc, 'shelf', shelf, [-thickness-shelf_l, 0, z_shelf_pos])

    if isinstance(tool_shape, tuple):
        tool_l, tool_r = tool_shape
    else:
        tool_l = tool_shape.copy() @ ts.rotate([0, 0, 1], 180)
        tool_r = tool_shape
    # right side cut
    cut_pos = [0, shelf_width/2, z_shelf_pos]
    pannel_f = ts.drill(pannel_f, tool_r, cut_pos)
    shelf_r_f = ts.drill(shelf_r_f, tool_r, cut_pos)
    cut_r_feature = doc.addObject('Part::Feature', 'cut_tool_r')
    cut_r_feature.Shape = tool_r
    cut_r_feature.Placement = FreeCAD.Placement(FreeCAD.Vector(cut_pos), FreeCAD.Rotation())

    # left side cut
    cut_pos = [-thickness, shelf_width/2, z_shelf_pos]
    pannel_f = ts.drill(pannel_f, tool_l, cut_pos)
    shelf_l_f = ts.drill(shelf_l_f, tool_l, cut_pos)
    cut_l_feature = doc.addObject('Part::Feature', 'cut_tool_l')
    cut_l_feature.Shape = tool_l


    cut_l_feature.Placement = FreeCAD.Placement(FreeCAD.Vector(cut_pos), FreeCAD.Rotation())

    doc.recompute()
    path = script_dir / f"{name}.step"

    #all_objects = doc.Objects  # This returns all objects in the document
    Part.export([shelf_l_f, shelf_r_f, pannel_f, cut_l_feature, cut_r_feature], str(path))


thickness = 18

@pytest.mark.skip
def test_shelf_pin():
    make_scene(ts.pin_edge(600), 'pin_drill')

@pytest.mark.skip
def test_shelf_rastex():
    make_scene(ts.strong_edge(thickness, 600, ts.rastex), 'rastex_drill')

@pytest.mark.skip
def test_shelf_vb():
    make_scene(ts.strong_edge(thickness, 600, ts.vb), 'vb_drill')

def test_shelf_rail():
    make_scene(ts.rail(), 'rail_drill')

i_part = 0
def add_shape(doc, shape):
    global i_part
    feature = doc.addObject("Part::Feature", f"Part_{i_part:04}")
    feature.Shape = shape
    i_part += 1
    return feature

@pytest.mark.skip
def test_cut():
    doc = FreeCAD.newDocument("CutExample")
    features = []

    # Create a box shape
    shape = Part.makeBox(10, 10, 10)

    # Create tool shapes
    tool_1 = Part.makeCylinder(2, 10, FreeCAD.Vector(5, 5, 0))
    tool_2 = Part.makeCylinder(2, 10, FreeCAD.Vector(7, 7, 0))


    # Perform the first cut
    f_0 = add_shape(doc, shape)
    features.append(f_0)
    cut_feature_0 = add_shape(doc, shape)
    cut_feature_0.Placement = FreeCAD.Placement(FreeCAD.Vector([0, 0, 2]), FreeCAD.Rotation())


    cut_feature_1 = doc.addObject("Part::Feature", "Cut1")
    cut_feature_1.Shape = cut_feature_0.Shape
    cut_feature_1.Placement = cut_feature_0.Placement

    f_2 = add_shape(doc, tool_1)
    features.append(f_2)

    ts.drill(cut_feature_1, tool_1, [0, 0, 0])
    features.append(cut_feature_1)

    # drill proc 2.
    shp = cut_feature_1.Shape.copy()
    feature = add_shape(doc, shp)
    feature.Placement = cut_feature_1.Placement
    tool = tool_2
    position = [0,0,0]
    rotation = None
    # tool_placement = FreeCAD.Placement(FreeCAD.Vector(position), FreeCAD.Rotation())
    # tool_shape = tool_1.copy().transformGeometry(tool_placement.toMatrix())
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

    features.append(add_shape(doc, part_shape))
    features.append(add_shape(doc, tool_shape))

    result_shape = part_shape.cut(tool_shape)
    inverse_placement = f_placement.inverse()
    inv_mat = inverse_placement.toMatrix()
    res_shape_back = result_shape.transformGeometry(inv_mat)
    feature.Shape = res_shape_back
    feature.Placement = f_placement
    features.append(feature)

    # Perform the second cut
    #ts.drill(cut_feature_2, tool_2, [0,0,0])

    doc.recompute()
    path = script_dir / "test_cut.step"
    #all_objects = doc.Objects  # This returns all objects in the document
    Part.export(features, str(path))

@pytest.mark.skip
def test_cut2():
    doc = FreeCAD.newDocument("CutExample")
    features = []

    # Create a box shape
    shape = Part.makeBox(10, 10, 10)

    # Create tool shapes
    tool_1 = Part.makeCylinder(2, 10, FreeCAD.Vector(5, 5, 0))
    tool_2 = Part.makeCylinder(2, 10, FreeCAD.Vector(7, 7, 0))


    # Perform the first cut
    f_0 = add_shape(doc, shape)
    #features.append(f_0)
    # cut_feature_0 = add_shape(doc, shape)
    # cut_feature_0.Placement = FreeCAD.Placement(FreeCAD.Vector([0, 0, 2]), FreeCAD.Rotation())
    #
    #
    # cut_feature_1 = doc.addObject("Part::Feature", "Cut1")
    # cut_feature_1.Shape = cut_feature_0.Shape
    # cut_feature_1.Placement = cut_feature_0.Placement
    #
    # f_2 = add_shape(doc, tool_1)
    # features.append(f_2)

    ts.drill(f_0, tool_1, [0, 0, 0])
    features.append(f_0)

    f_1 = add_shape(doc, f_0.Shape)
    f_1.Placement = f_0.Placement
    ts.drill(f_1, tool_2, [0, 0, 0])
    features.append(f_1)

    # drill proc 2.
    # shp = cut_feature_1.Shape.copy()
    # feature = add_shape(doc, shp)
    # feature.Placement = cut_feature_1.Placement
    # tool = tool_2
    # position = [0,0,0]
    # rotation = None
    # # tool_placement = FreeCAD.Placement(FreeCAD.Vector(position), FreeCAD.Rotation())
    # # tool_shape = tool_1.copy().transformGeometry(tool_placement.toMatrix())
    # if isinstance(position, FreeCAD.Placement):
    #     tool_placement = position
    # else:
    #     if rotation is None:
    #         rotation = FreeCAD.Rotation()  # No rotation by default
    #     assert len(position) == 3
    #     tool_placement = FreeCAD.Placement(FreeCAD.Vector(position), rotation)
    # tool_shape = tool.copy().transformGeometry(tool_placement.toMatrix())
    # f_placement = feature.Placement
    # part_shape = feature.Shape.copy().transformGeometry(f_placement.toMatrix())
    # part_shape.Placement = FreeCAD.Placement()
    # # Perform the cut operation
    #
    # features.append(add_shape(doc, part_shape))
    # features.append(add_shape(doc, tool_shape))
    #
    # result_shape = part_shape.cut(tool_shape)
    # inverse_placement = f_placement.inverse()
    # inv_mat = inverse_placement.toMatrix()
    # res_shape_back = result_shape.transformGeometry(inv_mat)
    # feature.Shape = res_shape_back
    # feature.Placement = f_placement
    # features.append(feature)

    # Perform the second cut
    #ts.drill(cut_feature_2, tool_2, [0,0,0])

    doc.recompute()
    path = script_dir / "test_cut.step"
    #all_objects = doc.Objects  # This returns all objects in the document
    Part.export(features, str(path))
