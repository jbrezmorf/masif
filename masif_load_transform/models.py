from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import adsk.core
import adsk.fusion
import adsk.cam

from tools import Logger

def pt_diff(b, a):
    return adsk.core.Point3D.create(
        b.x-a.x,
        b.y-a.y,
        b.z-a.z)

@dataclass(frozen=True)
class JobConfig:
    workdir: Path
    logfile: Path
    step_path: Path
    template_dir: Path
    shift_z_after_rot_y_cm: float = -1.8
    delete_base_import_occurrence: bool = True


class PartContext:
    def __init__(self, config: JobConfig):
        self.config = config
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface
        self.logger = Logger(config.workdir, config.logfile)
        self.original_occurrence = None
        self.load()

    def log(self, msg: str):
        self.logger.log(self.ui, msg)

    def load(self):
        if self.original_occurrence is not None:
            return self.original_occurrence
        step_path = Path(self.config.step_path)
        if not step_path.exists():
            raise FileNotFoundError(str(step_path))
        doc = self.app.activeDocument
        design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
        if not design:
            raise RuntimeError("No active Design document.")
        root = design.rootComponent
        occs = root.occurrences
        before_tokens = set(occs.item(i).entityToken for i in range(occs.count))
        imp = self.app.importManager
        opts = imp.createSTEPImportOptions(str(step_path))
        imp.importToTarget(opts, root)
        imported = []
        for i in range(occs.count):
            o = occs.item(i)
            if o.entityToken not in before_tokens:
                imported.append(o)
        if not imported:
            raise RuntimeError("Import finished but no new occurrence detected.")
        self.original_occurrence = imported[0]

    @cached_property
    def dimensions(self) -> PartDimensions:
        bb = self.original_occurrence.boundingBox
        dd = pt_diff(bb.maxPoint, bb.minPoint)
        return dd


    def is_in_top(self, bb: adsk.core.BoundingBox3D, slot_name: str) -> bool:
        name = slot_name.strip().lower()
        assert name != ""
        height = self.dimensions.z
        self.log(f"{name}: h={height}, bbx=({bb.minPoint.x}, {bb.maxPoint.x})")
        if "top" in name:
            return bb.minPoint.x < (height / 2.0)
        if "bottom" in name:
            return bb.maxPoint.x < (height / 2.0)
        raise RuntimeError("slot_name must include 'top' or 'bottom'")

    def _get_cam_product(self):
        doc = self.app.activeDocument
        cam, prod = self._find_cam_in_products(doc)
        if cam:
            self._log_cam_info(cam, prod, "CAM product found")
            return cam

        self.log("CAM product not found; attempting to activate Manufacture workspace")
        ws = self.ui.workspaces.itemById("CAMEnvironment")
        if ws is None:
            ws = self.ui.workspaces.itemById("FusionCAMEnvironment")
        if ws:
            ws.activate()
        else:
            self.log("Manufacture workspace id not found")

        cam, prod = self._find_cam_in_products(doc)
        assert cam, "Failed to get CAM product"
        self._log_cam_info(cam, prod, "CAM product found after activation")
        return cam

    def _find_cam_in_products(self, doc):
        for i in range(doc.products.count):
            prod = doc.products.item(i)
            if prod.productType == "CAMProductType":
                return adsk.cam.CAM.cast(prod), prod
        return None, None

    def _log_cam_info(self, cam, prod, prefix: str):
        prod_name = getattr(prod, "name", "")
        prod_type = getattr(prod, "productType", "")
        cam_type = getattr(cam, "objectType", "")
        self.log(f"{prefix}: productType={prod_type} name={prod_name} objectType={cam_type}")

    def _create_drill_op(self, setup, holes, slot_name: str):
        op = self._apply_template_to_setup(setup, "masif_drill_8mm")
        op_name = f"{slot_name}_holes_8mm"
        op.displayName = op_name

        _set_drill_hole_faces(self, op, holes)

        self.log(f"Created drilling op from template: {op_name}")

        holeSelection: adsk.cam.CadObjectParameterValue = op.parameters.itemByName('holeFaces').value
        holeSelection.value = holes

        # Read back to confirm it stuck
        readback = holeSelection.value
        self.log(f"Drill op holeFaces set: count={len(readback)}")
        # op: adsk.cam.Operation = setup.operations.add(op)
        # Operation should already be within setup.
        return op

    def _apply_template_to_setup(self, setup, template_name: str):
        template_path = Path(self.config.template_dir) / f"{template_name}.f3dhsm-template"
        self.log(f"Template file: {template_path}")
        if not template_path.exists():
            raise RuntimeError(f"Template file not found: {template_path}")

        cam_template = adsk.cam.CAMTemplate.createFromFile(str(template_path))
        template_input = adsk.cam.CreateFromCAMTemplateInput.create()
        template_input.camTemplate = cam_template
        created_items = setup.createFromCAMTemplate2(template_input)
        assert len(created_items) == 1, f"Expected single operation from template: {created_items}"
        self.log(f"Template applied: created_items count={len(created_items)}")
        op = created_items[0]
        self.log(f"Operation: item: name={op.name} objectType={op.objectType}")
        return op
