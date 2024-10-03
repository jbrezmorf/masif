from freecad import *

from machine import DrillOp, MillOp,  OperationList
#from tool_shapes import rotate, translate

def test_drill_op():
    drill = DrillOp(2, 3)
    drill2 = DrillOp(2, 3, start=[1, 0, 0], direction= [0, 1, 0])
    drill1 = drill @ rotate([0, 0, 1], [0, 1, 0]) @ translate([1, 0, 0])
    print("drill1:", drill1)
    print("drill2:", drill2)

    assert drill1 == drill2


def shape_doc(op):
    doc = FreeCAD.newDocument()
    shapes = [o.tool_shape for o in op.expand()]
    cut_shapes = fuse(shapes)
    part_obj = doc.addObject("Part::Feature", str(op.__class__.__name__))
    part_obj.Shape = cut_shapes
    doc.recompute()
    doc.saveAs(str(op.__class__.__name__))

def test_op_shapes():
    shape_doc(DrillOp(5/2.0, 5, start=[1, 0, 0]))
    shape_doc(MillOp(5 / 2.0, 5, direction=[1, 0, 0], start=[0, 0, -3], end=[0, 0, 3]))
    shape_doc(
        OperationList(
       DrillOp(5 / 2.0, 5, direction=[0, 0, -1]),
            OperationList(
            DrillOp(3 / 2.0, 5, direction=[1, 0, 0]),
                 DrillOp(3 / 2.0, 5, direction=[0, 1, 0]),
            ) @ translate([0, 1, 1])
        ))



def test_operation_list():
    a = OperationList(DrillOp(2, 3), DrillOp(3, 4))
    b = OperationList(DrillOp(5, 6), DrillOp(7, 8))
    c = OperationList(a, b)

    print()
    for ca, cb in c:
        print(ca, '&',  cb)

    cc =c @ (translate([-1, 0, -1]))

    aa = a @ (translate([-1, 0, -1]))
    for ia in aa:
        assert isinstance(ia, DrillOp)
    print()
    for cca, ccb in cc:
        print(cca, '&',  ccb)


