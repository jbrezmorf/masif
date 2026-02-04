import adsk.core
import datetime
from pathlib import Path

# ----------------------------
# Logging
# ----------------------------
class Logger:
    def __init__(self, workdir: Path, logfile: Path):
        self.workdir = Path(workdir)
        self.logfile = Path(logfile)

    def filelog(self, msg: str):
        self.workdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.logfile.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")

    def textlog(self, ui: adsk.core.UserInterface, msg: str):
        try:
            pal = ui.palettes.itemById("TextCommands")
            if pal:
                pal.isVisible = True
                pal.writeText(str(msg) + "\n")
            adsk.doEvents()
        except:
            pass

    def log(self, ui: adsk.core.UserInterface, msg: str):
        # Always attempt file log; TextCommands best-effort.
        try:
            self.filelog(msg)
        except:
            pass
        # try:
        #     self.textlog(ui, msg)
        # except:
        #     pass


# ----------------------------
# Matrix helpers
# ----------------------------
def deg2rad(d: float) -> float:
    return d * 3.141592653589793 / 180.0


def mat_translation(x, y, z) -> adsk.core.Matrix3D:
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(x, y, z)
    return m


def mat_rotation(deg, axis: adsk.core.Vector3D) -> adsk.core.Matrix3D:
    m = adsk.core.Matrix3D.create()
    origin = adsk.core.Point3D.create(0, 0, 0)
    m.setToRotation(deg2rad(deg), axis, origin)
    return m


def compose(*mats: adsk.core.Matrix3D) -> adsk.core.Matrix3D:
    """
    Compose matrices left-to-right: r = I; r = r * mats[0] * mats[1] * ...
    """
    r = adsk.core.Matrix3D.create()
    for m in mats:
        r.transformBy(m)
    return r


# ----------------------------
# Bounding box helpers
# ----------------------------
def bbox_dims_xyz(bb: adsk.core.BoundingBox3D):
    minp = bb.minPoint
    maxp = bb.maxPoint
    dx = maxp.x - minp.x
    dy = maxp.y - minp.y
    dz = maxp.z - minp.z
    return dx, dy, dz, minp, maxp
