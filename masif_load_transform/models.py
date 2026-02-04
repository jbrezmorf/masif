from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import adsk.core
import adsk.fusion

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
