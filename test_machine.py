from machine import DrillOp, OperationList
from tool_shapes import rotate, translate

def test_drill_op():
    drill = DrillOp(2, 3)
    drill2 = DrillOp(2, 3, start=[1, 0, 0], direction= [0, 1, 0])
    drill1 = drill.apply(rotate([0, 0, 1], [0, 1, 0]) @ translate([1, 0, 0]))
    print("drill1:", drill1)
    print("drill2:", drill2)

    assert drill1 == drill2

def test_operation_list():
    a = OperationList(DrillOp(2, 3), DrillOp(3, 4))
    b = OperationList(DrillOp(5, 6), DrillOp(7, 8))
    c = OperationList(a, b)

    print()
    for ca, cb in c:
        print(ca, '&',  cb)

    cc =c.apply(translate([-1, 0, -1]))

    aa = a.apply(translate([-1, 0, -1]))
    for ia in aa:
        assert isinstance(ia, DrillOp)
    print()
    for cca, ccb in cc:
        print(cca, '&',  ccb)
