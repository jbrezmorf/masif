import adsk.core
import traceback
from pathlib import Path
import sys
"""
CNC Stepcraft Q204
665 x 1265 x 145
"""


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

import importlib

def import_safe(module_name: str):
    module = importlib.import_module(module_name)
    importlib.reload(module)


import_safe("tools")
import_safe("feeds_speeds")
import_safe("models")
import_safe("holes_8mm")
import_safe("mill")
import_safe("holes_5mm")
from models import JobConfig, PartContext
from holes_8mm import holes_8mm
from mill import mill
from holes_5mm import holes_5mm

# ----------------------------
# USER CONFIG
# ----------------------------


SHIFT_Z_AFTER_ROT_Y_CM = -1.8  # -18mm

def run(context):
    ui = None
    ctx = None
    
    WORKDIR = THIS_DIR / "workspace"
    #single_part(WORKDIR / "vertical_panel_6.step")
    #single_part(WORKDIR / "bottom_1.step")
    for step_path in WORKDIR.glob("*.step"):
        single_part(step_path)


def single_part(part_path: Path):
    WORKDIR = part_path.parent
    config = JobConfig(
        WORKDIR,
        part_path,
        SHIFT_Z_AFTER_ROT_Y_CM,
        delete_base_import_occurrence=True
    )
    ctx = PartContext(config)
    try:
        ui = ctx.ui

        ctx.log("=== main.py run() VER 8mm ===")

        created = ctx.load_and_split()
        process_all(ctx, created)

        # Show result summary
        names = ", ".join(created.keys())
        # ui.messageBox(
        #     "Done.\n"
        #     f"Created {len(created)} transformed components:\n{names}\n\n"
        #     f"Log: {LOGFILE}"
        # )

    except:
        err = traceback.format_exc()
        # log to file even if TextCommands fails
        ctx.logger.filelog("ERROR:\n" + err)
        ui.messageBox("Failed:\n" + err)

def process_all(ctx: PartContext, created):
    for slot_name, occ in created.items():
        copy_process(ctx, occ, slot_name)


def copy_process(ctx: PartContext, occurrence, slot_name: str):
    ctx.log(f"Processing slot: {slot_name}")
    holes_8mm(ctx, occurrence, slot_name)
    mill(ctx, occurrence, slot_name)
    holes_5mm(ctx, occurrence, slot_name)


