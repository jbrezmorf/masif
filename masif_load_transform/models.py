from __future__ import annotations
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import re
import time
import zipfile
import adsk.core
import adsk.fusion
import adsk.cam
from tools import Logger
from tools import mat_translation, mat_rotation, compose, bbox_dims_xyz


def pt_diff(b, a):
    return adsk.core.Point3D.create(
        b.x-a.x,
        b.y-a.y,
        b.z-a.z)


def _fmt_mm(value: float) -> str:
    s = f"{value:.3f}".rstrip("0")  #.rstrip(".")
    return s if s else "0"

@dataclass(frozen=True)
class JobConfig:
    _workdir: Path
    step_path: Path
    shift_z_after_rot_y_cm: float = -1.8
    delete_base_import_occurrence: bool = False
    safe_z_mm: float = 45.0
    cycle_plane_z_mm: float = 25.0
    min_z_mm: float = -16.0
    remove_tool_length_compensation: bool = False

    @cached_property
    def workdir(self):
        self._workdir.mkdir(parents=True, exist_ok=True)
        return self._workdir
    
    @property
    def logfile(self):
        logf = self.workdir / f"{self.step_path.stem}.log"
        if logf.exists():
            logf.unlink()
        return logf

    @property
    def template_dir(self):
        return (self.workdir.parent / "tools").resolve()

    @property
    def tool_library_path(self):
        return self.template_dir / "TULab CNC_own.tools"

    @property
    def ncdir(self):
        return self.workdir / "g-code"

    @cached_property
    def slack_dir(self):
        return {
            "vertical_panel_1": 59.8,
            "vertical_panel_2": 59.6,
            "vertical_panel_3": 59.7,
            "vertical_panel_4": 59.9,
            "vertical_panel_5": 59.7,
            "vertical_panel_6": 59.9,
            "vertical_short_1": 59.6,
            "vertical_short_2": 59.6,
        }

    @property
    def slack_x_cm(self) -> float:
        real_width = self.slack_dir.get(self.step_path.stem, 60.0)
        return 60.0 - real_width

class PartContext:
    def __init__(self, config: JobConfig):
        self.config = config
        self.app = adsk.core.Application.get()
        self.ui = self.app.userInterface
        self.logger = Logger(config.workdir, config.logfile)
        self.original_occurrence = None
        self.dimensions = None
       

    def log(self, msg: str):
        self.logger.log(self.ui, msg)

    @cached_property
    def design(self) -> adsk.fusion.Design:
        doc = self.app.activeDocument
        design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
        if not design:
            raise RuntimeError("No active Design document.")
        return design

    @cached_property
    def root(self) -> adsk.fusion.Component:
        return self.design.rootComponent

    @cached_property
    def part_name(self) -> str:
        return Path(self.config.step_path).stem
    
    def _ensure_canonical_orientation(self, occ: adsk.fusion.Occurrence):
        """
        Rotate the occurrence so the longest dimension is Z and smallest is X.
        Assumes the model is axis-aligned (only axis permutation needed).
        """
        bb = occ.boundingBox
        dx, dy, dz, minp, maxp = bbox_dims_xyz(bb)
        dims = [dx, dy, dz]
        order = sorted(range(3), key=lambda i: dims[i])

        AX_X = adsk.core.Vector3D.create(1, 0, 0)
        AX_Y = adsk.core.Vector3D.create(0, 1, 0)
        AX_Z = adsk.core.Vector3D.create(0, 0, 1)
        AX_D = adsk.core.Vector3D.create(1, 1, 1)

        rot_map = {
            (0, 1, 2): (AX_Z, 0),
            (0, 2, 1): (AX_X, 90),
            (1, 0, 2): (AX_Z, 90),
            (2, 1, 0): (AX_Y, 90),
            (1, 2, 0): (AX_D, 240),
            (2, 0, 1): (AX_D, 120),
        }
        axis, angle = rot_map[tuple(order)]

        t0 = mat_translation(-minp.x, -minp.y, -minp.z)
        rot = mat_rotation(angle, axis)

        xs = (minp.x, maxp.x)
        ys = (minp.y, maxp.y)
        zs = (minp.z, maxp.z)
        corners = [adsk.core.Point3D.create(x, y, z) for x in xs for y in ys for z in zs]

        def apply(p, mats):
            q = adsk.core.Point3D.create(p.x, p.y, p.z)
            for m in mats:
                q.transformBy(m)
            return q

        rotated = [apply(p, (t0, rot)) for p in corners]
        minr = adsk.core.Point3D.create(
            min(p.x for p in rotated),
            min(p.y for p in rotated),
            min(p.z for p in rotated),
        )
        t1 = mat_translation(-minr.x, -minr.y, -minr.z)
        occ.transform = compose(occ.transform, t0, rot, t1)

        new_dims = (dims[order[0]], dims[order[1]], dims[order[2]])
        self.log(
            "Orientation xform: "
            f"dims=({dx:.6f},{dy:.6f},{dz:.6f}) "
            f"new_dims=({new_dims[0]:.6f},{new_dims[1]:.6f},{new_dims[2]:.6f}) "
            f"order={order} axis=({axis.x:.1f},{axis.y:.1f},{axis.z:.1f}) angle={angle}"
        )

        self.__dict__.pop("dimensions", None)
        return new_dims
       

    def load_and_split(self):
        """
        Uses the preloaded original occurrence and creates 4 transformed
        "Paste New" component copies with names:
        top_right, bottom_right, top_left, bottom_left

        Returns:
            dict[str, adsk.fusion.Occurrence]  # slot_name -> created occurrence
        """
        self.load()
        app = self.app
        shift_z_after_rot_y_cm = self.config.shift_z_after_rot_y_cm
        occs = self.root.occurrences

        self.log("=== load_and_split START ===")

        base_occ = self.original_occurrence
        if base_occ is None:
            raise RuntimeError("original_occurrence is not loaded")
        self.log(f"Imported component name (raw): {base_occ.component.name}")

        dims = self._ensure_canonical_orientation(base_occ)
        self.dimensions = adsk.core.Point3D.create(dims[0], dims[1], dims[2])
        thick, width, height = dims
        bb = base_occ.boundingBox
        _, _, _, minp, maxp = bbox_dims_xyz(bb)

        self.log(f"BoundingBox min = ({minp.x:.6f}, {minp.y:.6f}, {minp.z:.6f})")
        self.log(f"BoundingBox max = ({maxp.x:.6f}, {maxp.y:.6f}, {maxp.z:.6f})")
        self.log(f"Dimensions (X,Y,Z) = thick={thick:.6f}  width={width:.6f}  height={height:.6f}")

        # Shift so minZ -> 0 (world Z)
        # Shift so minX -> 0 (world X)
        #shift_to_zero_z = -minp.z
        #shift_to_zero_x = -minp.x
        #base_shift = mat_translation(shift_to_zero_x, 0, shift_to_zero_z)
        #self.log(f"Shift-to-zero: dz = {shift_to_zero_z:.6f} (so minZ -> 0)")
    
        # Apply shift to base occurrence for confirmation
        #base_occ.transform = compose(base_occ.transform, base_shift)
        base_tr = base_occ.transform

        # Verify
        bb2 = base_occ.boundingBox
        _, _, _, minp2, _ = bbox_dims_xyz(bb2)
        self.log(f"After applying base shift to base_occ, minZ = {minp2.z:.9f}")

        # Axes
        AX_Y = adsk.core.Vector3D.create(0, 1, 0)
        AX_Z = adsk.core.Vector3D.create(0, 0, 1)

        # Raw slot transforms (without base shift)
        tr_top_right_raw = compose(
            mat_rotation(270, AX_Y),
            mat_translation(0, 0, shift_z_after_rot_y_cm),
            mat_translation(height, 0, 0),
        )

        tr_bottom_right_raw = compose(
            mat_rotation(270, AX_Y),
            mat_translation(0, 0, shift_z_after_rot_y_cm),
            mat_rotation(180, AX_Z),
            mat_translation(0, width, 0),
        )

        tr_top_left_raw = compose(
            mat_rotation(90, AX_Y),
            mat_rotation(180, AX_Z),
            mat_translation(height, 0, 0),
            mat_translation(0, width, 0),
        )

        tr_bottom_left_raw = compose(
            mat_rotation(90, AX_Y),
        )

        xy_swap_longest_to_y = compose(
            mat_rotation(270, AX_Z),
        )
        slack_x_cm = self.config.slack_x_cm
        slack_tr = mat_translation(-slack_x_cm, 0, 0)

        # Apply base occurrence transform (canonical rotation + shift)
        tr_top_right = compose(base_tr, tr_top_right_raw, xy_swap_longest_to_y)
        tr_bottom_right = compose(base_tr, tr_bottom_right_raw, xy_swap_longest_to_y, slack_tr)
        tr_top_left = compose(base_tr, tr_top_left_raw, xy_swap_longest_to_y, slack_tr)
        tr_bottom_left = compose(base_tr, tr_bottom_left_raw, xy_swap_longest_to_y)

        self.log(
            "Machining frame remap: "
            f"X<=width={width:.6f} Y<=-height={height:.6f} Z<=-thick={thick:.6f}"
        )
        self.log(f"Part slack: {self.part_name} -> shift_x={slack_x_cm:.6f} cm")

        def add_named_copy(slot_name: str, tr: adsk.core.Matrix3D):
            new_occ = occs.addNewComponentCopy(base_occ.component, tr)
            if not new_occ:
                raise RuntimeError(f"addNewComponentCopy failed for slot {slot_name}")
            try:
                new_occ.component.name = slot_name
            except:
                pass
            self.log(f"Created slot: {slot_name}")
            return new_occ

        part = self.part_name
        created = {
            f"{part}_0_top_right": add_named_copy(f"{part}_0_top_right", tr_top_right),
            f"{part}_1_bottom_right": add_named_copy(f"{part}_1_bottom_right", tr_bottom_right),
            f"{part}_2_top_left": add_named_copy(f"{part}_2_top_left", tr_top_left),
            f"{part}_3_bottom_left": add_named_copy(f"{part}_3_bottom_left", tr_bottom_left),
        }

        self.delete_origin_occurance()
        self.log("=== load_and_split END ===")
        return created

    def delete_origin_occurance(self):
        try:
            self.original_occurrence.deleteMe()
            self.original_occurrence = None
            self.log("Deleted original imported occurrence (kept only 4 slots).")
        except:
            self.log("WARNING: Could not delete original imported occurrence.")


    def load(self):
        if self.original_occurrence is not None:
            return self.original_occurrence
        step_path = Path(self.config.step_path)
        if not step_path.exists():
            raise FileNotFoundError(str(step_path))
        occs = self.root.occurrences
        before_tokens = set(occs.item(i).entityToken for i in range(occs.count))
        imp = self.app.importManager
        opts = imp.createSTEPImportOptions(str(step_path))
        imp.importToTarget(opts, self.root)
        imported = []
        for i in range(occs.count):
            o = occs.item(i)
            if o.entityToken not in before_tokens:
                imported.append(o)
        if not imported:
            raise RuntimeError("Import finished but no new occurrence detected.")
        self.original_occurrence = imported[0]


    def is_in_top(self, bb: adsk.core.BoundingBox3D, slot_name: str) -> bool:
        """
        Return true if the BB is in active half.
        For top position, it is true if any BB part is in the active half.
        For the bottom  position, whole BB must be in active half. 
        """
        name = slot_name.strip().lower()
        assert name != ""
        height = self.dimensions.z
        cnc_limit = 125 # absolute limit is 1265 mm
        self.log(f"{name}: h={height}, bby=({bb.minPoint.y}, {bb.maxPoint.y})")
        # assuming X+, Y- quadrant
        if "top" in name:
            return bb.minPoint.y > -cnc_limit - 0.01
        if "bottom" in name:
            return (bb.maxPoint.y > -(height - cnc_limit) + 0.01) and (height > cnc_limit)
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

    def create_setup(self, occurrence, slot_name: str):
        cam = self._get_cam_product()

        setup_input: adsk.cam.SetupInput = cam.setups.createInput(adsk.cam.OperationTypes.MillingOperation)
        bodies = occurrence.bRepBodies
        body_count = bodies.count
        assert body_count > 0, "No bodies available for setup models"
        self.log(f"Setup models: occurrence.bRepBodies.count={body_count}")

        body_list = [b for b in bodies]
        setup_input.models = body_list
        setup_input.name = slot_name

        setup = cam.setups.add(setup_input)
        self.set_expr(setup, "job_stockOffsetSides", "0 mm")
        self.set_expr(setup, "job_stockOffsetTop", "0 mm")
        self.set_expr(setup, "job_stockOffsetBottom", "0 mm")
        self.set_expr(setup, "wcs_origin_mode", "modelOrigin")  # alternative param: "view_origin_mode"

        
        self.log(f"Created setup: {setup.name}")
        return setup

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

    def _find_tool_by_full_name(self, tool_full_name: str) -> adsk.cam.Tool:
        """
        Looks up a tool in an exported tool library file located at
        self.config.tool_library_path by tool name/description.
        Supports:
          - .json tool library
          - .tools (zipped tool library JSON)
        Does NOT use ToolLibraries/toolLibraryAtURL (asset locator URLs only).
        """
        needle = (tool_full_name or "").strip().lower()
        tool_library = self.external_tool_library

        return self._find_tool_in_library_by_needle(
            tool_library,
            needle=needle,
            context=f"external tool library '{Path(self.config.tool_library_path)}'",
            tool_full_name=tool_full_name,
        )

    @cached_property
    def external_tool_library(self) -> adsk.cam.ToolLibrary:
        """
        Loads and caches the external tool library from self.config.tool_library_path.
        """
        lib_path = Path(self.config.tool_library_path)
        if not lib_path.is_file():
            raise RuntimeError(f"Tool library path is not a file: '{lib_path}'")

        # .tools is typically a ZIP containing the tool library JSON
        try:
            with zipfile.ZipFile(str(lib_path), "r") as zf:
                names = zf.namelist()
                json_names = [n for n in names if n.lower().endswith(".json")]
                if not json_names:
                    raise RuntimeError(f"No .json found inside .tools archive: '{lib_path}'")
                if len(json_names) > 1:
                    raise RuntimeError(f"More then single JSON within tooll library: {json_names}.")# take the first json (usually only one)
                with zf.open(json_names[0], "r") as f:
                    raw_json = f.read().decode("utf-8", errors="replace")
            self.log(f"Loaded external tool library (.tools zip): '{lib_path}' -> '{json_names[0]}'")
        except zipfile.BadZipFile as e:
            # fallback to plain JSON
            raw_json = lib_path.read_text(encoding="utf-8", errors="replace")
            self.log(f"Loaded external tool library (json): '{lib_path}'")

        tool_library = adsk.cam.ToolLibrary.createFromJson(raw_json)
        if not tool_library or not tool_library.isValid:
            raise RuntimeError(f"Failed to parse tool library JSON from: '{lib_path}'")

        return tool_library
    
    def _find_tool_in_document_by_full_name(self, tool_full_name: str) -> adsk.cam.Tool:
        """
        Looks up a tool in the CAM document tool library by name/description.
        Assumes you've imported tools into the document tool library.
        (Kept for future usage.)
        """
        needle = (tool_full_name or "").strip().lower()
        if not needle:
            raise RuntimeError("tool_full_name must not be empty")

        cam = self._get_cam_product()
        lib = cam.documentToolLibrary  # document-scoped tools

        return self._find_tool_in_library_by_needle(
            lib,
            needle=needle,
            context="document tool library",
            tool_full_name=tool_full_name,
        )

    def _find_tool_in_library_by_needle(self, lib, needle: str, context: str, tool_full_name: str) -> adsk.cam.Tool:
        """
        Shared matcher for tools in any library-like object that supports:
          - .count
          - .item(i)
        Matches by tool.name or tool.description.
        """
        best = None
        for i in range(lib.count):
            t = lib.item(i)
            name = (getattr(t, "name", "") or "").strip()
            desc = (getattr(t, "description", "") or "").strip()

            key_name = name.lower()
            key_desc = desc.lower()

            # Exact match preferred
            if needle == key_name or needle == key_desc:
                self.log(f"Tool match exact ({context}): name='{name}' desc='{desc}'")
                return t

            # Substring match fallback
            if needle in key_name or needle in key_desc:
                best = best or t

        if best:
            self.log(f"Tool match substring ({context}): name='{getattr(best, 'name', '')}'")
            return best

        raise RuntimeError(f"Tool not found in {context}: '{tool_full_name}'")

    LOWER_FIRST = re.compile(r"^[a-z]")
    def set_expr(self, op_in, param_name: str, s: str):
        prm = op_in.parameters.itemByName(param_name)
        
        if not prm:
            params = op_in.parameters
            self.log(f"Invalid Param: {param_name} = {s}.")
            self.log("  Avaliable: " +
                ", ".join(
                    [f"{params.item(i).name}" for i in range(params.count)
                     ]))

            raise KeyError()
        if isinstance(s, str):
            expr = f"'{s}'" if self.LOWER_FIRST.match(s) else s
        else:
            expr = f"{str(s).lower()}"
        try:
            prm.expression = expr
        except Exception as e:
            self.log(f"Invalid value: {param_name} = {s}.")
            ch = adsk.cam.ChoiceParameterValue.cast(prm.value)
            if ch:
                ok, names, values = ch.getChoices()   # values are the internal enum tokens
                self.log(f"  OK: {ok}")
                self.log(f"  Choices: {names}")
                self.log(f"  Values: {values}")
            raise e

    def _create_drill_op(self, setup, holes, slot_name: str, 
                         tool_name: str, **kw_args):
        """
        Create a Drill operation without templates.
        """
        tool = self._find_tool_by_full_name(tool_name)

        # Create Drill operation input.
        # Fusion typically uses string ids like "drill".
        op_in: adsk.core.OperationInput = setup.operations.createInput("drill")
        op_in.displayName = f"{slot_name}_holes_8mm"

        # Assign tool explicitly (this avoids the “select tool” failure).
        op_in.tool = tool

        # ---- Required geometry: holeFaces ----
        p = op_in.parameters.itemByName("holeFaces")
        if not p:
            raise RuntimeError("Drill op input has no 'holeFaces' parameter (unexpected).")
        # For CadObject parameters, the value is a CadObjectParameterValue whose .value accepts a list/collection.
        p.value.value = holes

        # ---- Minimal sensible defaults (only if present) ----
        # Make it tolerant across post/operation variants by checking presence.


        for k, v in kw_args.items():
            self.set_expr(op_in, k, v)
        self.log(f"Created drill op input: {op_in.displayName}")
        return op_in

    def add_op_drill(self, setup, holes, slot_name: str, tool_name: str, **kw_args):
        op_in = self._create_drill_op(setup, holes, slot_name, tool_name, **kw_args)
        op = setup.operations.add(op_in)
        self.log(f"Created drill op: {op_in.displayName}")

        try:
            rb = op.parameters.itemByName("holeFaces").value.value
            self.log(f"Drill op holeFaces readback: count={len(rb)}")
        except Exception:
            pass
        return op


    # def _apply_template_to_setup(self, setup, template_name: str):
    #     template_path = Path(self.config.template_dir) / f"{template_name}.f3dhsm-template"
    #     self.log(f"Template file: {template_path}")
    #     if not template_path.exists():
    #         raise RuntimeError(f"Template file not found: {template_path}")

    #     cam_template = adsk.cam.CAMTemplate.createFromFile(str(template_path))
    #     template_input = adsk.cam.CreateFromCAMTemplateInput.create()
    #     template_input.camTemplate = cam_template
    #     created_items = setup.createFromCAMTemplate2(template_input)
    #     assert len(created_items) == 1, f"Expected single operation from template: {created_items}"
    #     self.log(f"Template applied: created_items count={len(created_items)}")
    #     op = created_items[0]
    #     self.log(f"Operation: item: name={op.name} objectType={op.objectType}")
    #     return op

    def _create_pocket2d_op(self, setup, pocket_chains, slot_name: str, tool_name: str, **kw_args):
        """
        Create a 2D Pocket operation input using CLOSED CHAIN geometry (outer boundary edges).
        Mirrors the drill automation style.
        """
        tool = self._find_tool_by_full_name(tool_name)

        op_in = setup.operations.createInput("pocket2d")
        op_in.displayName = f"{slot_name}_pocket2d"
        op_in.tool = tool

        # ---- Geometry: closed chains (best match to your GUI workflow) ----
        if not pocket_chains:
            raise RuntimeError("No pocket chains provided")

        prm = op_in.parameters.itemByName("pockets")
        if not prm:
            raise RuntimeError("Operation has no 'pockets' parameter.")

        # IMPORTANT: this is a CadContours2dParameterValue, not a CadObjectParameterValue
        pocket_sel = adsk.cam.CadContours2dParameterValue.cast(prm.value)
        if not pocket_sel:
            raise RuntimeError(f"'pockets' is not CadContours2dParameterValue (got {getattr(prm.value,'objectType','?')})")

        chains = pocket_sel.getCurveSelections()
        chains.clear()

        # Closed Chain == ChainSelection
        for boundary_edges in pocket_chains:
            ch = chains.createNewChainSelection()
            ch.inputGeometry = boundary_edges   # <-- SAME TYPE as case A boundary_edges

            # Optional: some builds expose isReverted (same meaning as GUI “Reverted”)
            # Guard it because properties can differ by build.
            try:
                ch.isReverted = True
            except:
                pass

        pocket_sel.applyCurveSelections(chains)       
    
        for k, v in kw_args.items():
            self.set_expr(op_in, k, v)
        
        self.log(f"Created pocket2d op input: {op_in.displayName}")
        return op_in


    def add_op_pocket2d(self, setup, pocket_chains, slot_name: str, tool_name: str, **kw_args):
        op_in = self._create_pocket2d_op(setup, pocket_chains, slot_name, tool_name, **kw_args)
        op = setup.operations.add(op_in)
        self.log(f"Created pocket2d op: {op_in.displayName}")
        return op

    def _create_manual_nc(self, setup: adsk.cam.Setup, name: str, gcode: str) -> adsk.cam.OperationInput:
        """
        Minimal Manual NC OperationInput creator.
        
        To get a list of the available strategies, you use the Operations.compatibleStrategies property,
         which returns a list of strategies supported for your configuration.
        https://help.autodesk.com/view/fusion360/CHS/?guid=GUID-7F3F9D48-ED88-451A-907C-82EAE67DEA93
        """
        op_in = setup.operations.createInput("manual")
        op_in.displayName = name

        # Store the code in the Manual NC 'code' parameter as a quoted string expression.
        # Use \n for multiple lines.
        #esc = "'" + gcode.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"    
        esc = gcode.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") 
        # params = op_in.parameters
        # self.log(f"Param count = {params.count}")
        # for pn in ["action", "manualType"]:
        #     p = op_in.parameters.itemByName(pn)
        #     v = p.value
        #     ch = adsk.cam.ChoiceParameterValue.cast(v)
        #     if not ch:
        #         self.log(f"{pn} is not a ChoiceParameterValue {getattr(v, "objectType", None)}")
        #         continue
        #     ok, names, values = ch.getChoices()
        #     for n, val in zip(names, values):
        #         self.log(f"  {n} => {val}")

        
        op_in.parameters.itemByName("message").expression = f"'{esc}'"
        op_in.parameters.itemByName("manualType").expression = "'pass-through'"
        return op_in

    def add_op_transverse(self, setup: adsk.cam.Setup, x_mm: float, y_mm: float, name: str | None = None):
        op_name = name or f"transverse_{_fmt_mm(x_mm)}_{_fmt_mm(y_mm)}"
        code = "\n".join([
            "M5",   # spin off
            "G90",  
            "G21",  # retract
            f"G0 Z{_fmt_mm(self.config.safe_z_mm)}",
            f"G0 X{_fmt_mm(x_mm)} Y{_fmt_mm(y_mm)}",
        ])
        op_in = self._create_manual_nc(setup, op_name, code)
        op = setup.operations.add(op_in)
        self.log(f"Created manual NC op: {op_in.displayName}")
        return op

    def generate_gcode(self, setup, slot_name: str, op_name: str | None = None):
        log_name = op_name or "g-code"
        self.log(f"{log_name} G-code START for {slot_name} setup={getattr(setup, 'name', '?')}")

        output_dir = self.config.ncdir
        output_dir.mkdir(parents=True, exist_ok=True)
        file_stem = self._build_gcode_stem(slot_name, op_name)

        post_config = Path(self.config.template_dir) / "uccnc.cps"
        if not post_config.exists():
            raise RuntimeError(f"Post config not found: {post_config}")
        self.log(f"{log_name} G-code: using post config: {post_config}")

        units = adsk.cam.PostOutputUnitOptions.MillimetersOutput
        output_file = str(output_dir / file_stem)
        self.log(
            f"Post settings: output_dir={output_dir} file_stem={file_stem} "
            f"post_config={post_config} units={units}"
        )

        post_input = self._create_post_input(output_file, post_config, output_dir, units)
        post_input.programName = file_stem
        post_input.isOpenInEditor = False
        output_path = output_dir / f"{file_stem}.nc"

        self._generate_toolpaths(setup, log_name)

        targets = adsk.core.ObjectCollection.create()
        targets.add(setup)
        cam = self._get_cam_product()

        try:
            ok = cam.postProcess(targets, post_input)
            self.log(f"{log_name} G-code: postProcess ok={ok}")
        except Exception as ex:
            self.log(f"{log_name} G-code: postProcess failed: {ex}")
            return

        self.postprocess_nc(output_path, log_name)
        self.check_nc(output_path, log_name)

        self.log(f"{log_name} G-code END for {slot_name}")

    def _build_gcode_stem(self, slot_name: str, op_name: str | None) -> str:
        stem = slot_name
        return f"{stem}_{op_name}" if op_name else stem

    def _generate_toolpaths(self, setup, log_name: str):
        cam = self._get_cam_product()

        ops = getattr(setup, "operations", None)
        targets = adsk.core.ObjectCollection.create()
        if ops and getattr(ops, "count", 0) > 0:
            for i in range(ops.count):
                targets.add(ops.item(i))
            self.log(f"{log_name} G-code: generating toolpaths for {ops.count} operations")
            future = cam.generateToolpath(targets)
        else:
            self.log(f"{log_name} G-code: generating toolpaths for setup")
            future = cam.generateToolpath(setup)

        # Don't use hasattr on properties like isGenerationCompleted (getter may throw)
        if not future or getattr(future, "objectType", "") != "adsk::cam::GenerateToolpathFuture":
            # Some older calls can return bool; treat False as failure.
            if isinstance(future, bool) and not future:
                raise RuntimeError("Toolpath generation failed (bool False)")
            return

        start = time.time()

        # Give Fusion a chance to actually start the generation
        adsk.doEvents()
        time.sleep(0.05)

        while True:
            adsk.doEvents()

            # Tolerate the transient "Generation not started" state
            try:
                done = future.isGenerationCompleted
            except RuntimeError as ex:
                if "Generation not started" in str(ex):
                    done = False
                else:
                    raise

            if done:
                # These can also throw in some builds; guard them too
                try:
                    if getattr(future, "hasError", False):
                        raise RuntimeError(getattr(future, "errorMessage", "Toolpath generation failed"))
                except RuntimeError:
                    # If even hasError/errorMessage are flaky, just break and let post reveal issues
                    pass
                break

            if time.time() - start > 300:
                raise RuntimeError("Toolpath generation timeout (300s)")

            time.sleep(0.05)

    def _create_post_input(self, output_file: str, post_config: str, output_dir: Path, units):
        assert units is not None, "PostProcessInput units must be set"
        post_input = adsk.cam.PostProcessInput.create(
            output_file,
            str(post_config),
            str(output_dir),
            units,
        )
        post_props = adsk.core.NamedValues.create()
        post_props.add("useToolCall", adsk.core.ValueInput.createByBoolean(False))
        post_input.postProperties = post_props
        self.log("Post property: useToolCall=False")
        return post_input

    def postprocess_nc(self, nc_path: Path, log_name: str):
        if not nc_path.exists():
            self.log(f"{log_name} G-code: posted file not found for postprocess: {nc_path}")
            return

        self._backup_original_nc(nc_path, log_name)
        self._post_remove_tool_change_lines(nc_path, log_name)
        if self.config.remove_tool_length_compensation:
            self._post_remove_length_compensation(nc_path, log_name)
        self._post_clamp_min_z(nc_path, log_name)

    def _post_remove_tool_change_lines(self, nc_path: Path, log_name: str):
        lines = self._read_nc_lines(nc_path)
        kept = []
        removed = []
        skip_tool_change_move = False

        for line in lines:
            stripped = line.strip()

            if "Move to tool change position" in stripped:
                removed.append(line)
                skip_tool_change_move = True
                continue

            if skip_tool_change_move and "G53" in stripped and "X" in stripped and "Y" in stripped:
                removed.append(line)
                skip_tool_change_move = False
                continue

            skip_tool_change_move = False

            if "Pause program for tool change" in stripped:
                removed.append(line)
                continue

            if re.search(r"\bMANUAL TOOL CHANGE TO T\d+\b", stripped, re.IGNORECASE):
                removed.append(line)
                continue

            if re.match(r"^T\d+\s*M0?6\b", stripped, re.IGNORECASE):
                removed.append(line)
                continue

            kept.append(line)

        if not removed:
            self.log(f"{log_name} G-code post: no tool-change lines removed from {nc_path.name}")
            return
        self._write_nc_lines(nc_path, kept)
        self.log(f"{log_name} G-code post: removed {len(removed)} tool-change lines from {nc_path.name}")

    def _post_remove_length_compensation(self, nc_path: Path, log_name: str):
        lines = self._read_nc_lines(nc_path)
        has_g49 = any(re.match(r"^G49\b", line.strip(), re.IGNORECASE) for line in lines)
        kept = []
        removed = []
        inserted_g49 = has_g49
        for line in lines:
            if re.match(r"^G43\b", line.strip(), re.IGNORECASE):
                removed.append(line)
                continue
            kept.append(line)
            if not inserted_g49 and re.match(r"^G90\b", line.strip(), re.IGNORECASE):
                kept.append("G49")
                inserted_g49 = True
        if not inserted_g49:
            kept.insert(0, "G49")
            inserted_g49 = True
        if not removed:
            self.log(f"{log_name} G-code post: no G43 lines removed from {nc_path.name}")
        else:
            self.log(f"{log_name} G-code post: removed {len(removed)} G43 lines from {nc_path.name}")
        if has_g49:
            self.log(f"{log_name} G-code post: G49 already present in {nc_path.name}")
            self._write_nc_lines(nc_path, kept)
            return
        self._write_nc_lines(nc_path, kept)
        position = "after G90" if any(re.match(r"^G90\b", line.strip(), re.IGNORECASE) for line in lines) else "at file start"
        self.log(f"{log_name} G-code post: inserted G49 {position} in {nc_path.name}")

    def _post_clamp_min_z(self, nc_path: Path, log_name: str):
        lines = self._read_nc_lines(nc_path)
        clamped, changed = self._clamp_min_z_lines(lines, self.config.min_z_mm)
        if not changed:
            self.log(f"{log_name} G-code post: no Z clamp needed for {nc_path.name}")
            return
        self._write_nc_lines(nc_path, clamped)
        self.log(
            f"{log_name} G-code post: clamped {changed} Z values to {self.config.min_z_mm:.3f} mm "
            f"in {nc_path.name}"
        )

    def _backup_original_nc(self, nc_path: Path, log_name: str):
        backup_path = nc_path.with_name(f"{nc_path.name}_orig")
        backup_path.write_text(nc_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        self.log(f"{log_name} G-code post: backed up original NC to {backup_path.name}")

    def _clamp_min_z_lines(self, lines: list[str], min_z_mm: float) -> tuple[list[str], int]:
        clamped = []
        changed = 0
        for line in lines:
            match = self.Z_WORD_RE.search(line)
            if not match:
                clamped.append(line)
                continue
            value = float(match.group("value"))
            if value >= min_z_mm:
                clamped.append(line)
                continue
            new_value = _fmt_mm(min_z_mm)
            clamped.append(
                f"{line[:match.start('value')]}{new_value}{line[match.end('value'):]}"
            )
            changed += 1
        return clamped, changed

    def check_nc(self, nc_path: Path, log_name: str):
        self._check_nc_min_z(nc_path, log_name)
        self._check_nc_length_comp(nc_path, log_name)

    def _check_nc_min_z(self, nc_path: Path, log_name: str):
        min_seen = None
        for line in self._read_nc_lines(nc_path):
            match = self.Z_WORD_RE.search(line)
            if not match:
                continue
            value = float(match.group("value"))
            min_seen = value if min_seen is None else min(min_seen, value)
        if min_seen is None:
            self.log(f"{log_name} G-code check: no Z words found in {nc_path.name}")
            return
        self.log(f"{log_name} G-code check: min Z={min_seen:.3f} mm in {nc_path.name}")
        if min_seen < self.config.min_z_mm:
            raise RuntimeError(f"{nc_path.name}: min Z {min_seen:.3f} below limit {self.config.min_z_mm:.3f}")

    def _check_nc_length_comp(self, nc_path: Path, log_name: str):
        lines = self._read_nc_lines(nc_path)
        g43_count = sum(1 for line in lines if re.match(r"^G43\b", line.strip(), re.IGNORECASE))
        g49_count = sum(1 for line in lines if re.match(r"^G49\b", line.strip(), re.IGNORECASE))
        self.log(
            f"{log_name} G-code check: G43={g43_count} G49={g49_count} "
            f"remove_length_comp={self.config.remove_tool_length_compensation}"
        )
        if self.config.remove_tool_length_compensation:
            if g43_count:
                raise RuntimeError(f"{nc_path.name}: G43 remains after compensation removal")
            if g49_count == 0:
                raise RuntimeError(f"{nc_path.name}: G49 missing after compensation removal")

    Z_WORD_RE = re.compile(r"(?P<prefix>\bZ)(?P<value>-?\d+(?:\.\d+)?)", re.IGNORECASE)



    def _read_nc_lines(self, nc_path: Path) -> list[str]:
        return nc_path.read_text(encoding="utf-8", errors="replace").splitlines()

    def _write_nc_lines(self, nc_path: Path, lines: list[str]):
        nc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
