from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MaterialFeedSpec:
    name: str
    surface_speed_m_min: float
    drill_feed_per_rev_mm_base: float
    mill_chip_load_mm_base: float
    base_diameter_mm: float = 8.0
    default_flutes: int = 2
    plunge_ratio: float = 0.5
    ramp_ratio: float = 0.7
    finish_ratio: float = 0.7

    def rpm_for_diameter(self, tool_diameter_mm: float) -> float:
        if tool_diameter_mm <= 0:
            raise ValueError("tool_diameter_mm must be > 0")
        return (self.surface_speed_m_min * 1000.0) / (math.pi * tool_diameter_mm)

    def scale_by_diameter(self, base_value: float, tool_diameter_mm: float) -> float:
        if tool_diameter_mm <= 0:
            raise ValueError("tool_diameter_mm must be > 0")
        return base_value * (tool_diameter_mm / self.base_diameter_mm)


SOFTWOOD_DRILL = MaterialFeedSpec(
    name="softwood_drill",
    surface_speed_m_min=75.0,
    drill_feed_per_rev_mm_base=0.08,
    mill_chip_load_mm_base=0.04,
)

SOFTWOOD_MILL = MaterialFeedSpec(
    name="softwood_mill",
    surface_speed_m_min=200.0,
    drill_feed_per_rev_mm_base=0.08,
    mill_chip_load_mm_base=0.08,
    plunge_ratio=0.25,
    ramp_ratio=0.5,
    finish_ratio=0.8,
)

def drill_feed_speed_params(
    tool_diameter_mm: float,
    spec: MaterialFeedSpec = SOFTWOOD_DRILL,
) -> dict:
    rpm = spec.rpm_for_diameter(tool_diameter_mm)
    feed_per_rev = spec.scale_by_diameter(spec.drill_feed_per_rev_mm_base, tool_diameter_mm)
    feed_plunge = rpm * feed_per_rev
    return dict(
        tool_spindleSpeed=f"{rpm:.0f}rpm",
        tool_useFeedPerRevolution=True,
        tool_feedPerRevolution=f"{feed_per_rev:.6f} mm",
        tool_feedPlunge=f"{feed_plunge:.3f} mm/min",
        tool_feedCutting=f"{feed_plunge:.3f} mm/min",
    )


def mill_feed_speed_params(
    tool_diameter_mm: float,
    flutes: int | None = None,
    spec: MaterialFeedSpec = SOFTWOOD_MILL,
) -> dict:
    rpm = spec.rpm_for_diameter(tool_diameter_mm)
    flute_count = flutes or spec.default_flutes
    if flute_count <= 0:
        raise ValueError("flutes must be > 0")
    chip_load = spec.scale_by_diameter(spec.mill_chip_load_mm_base, tool_diameter_mm)
    feed_cutting = rpm * flute_count * chip_load
    feed_plunge = feed_cutting * spec.plunge_ratio
    feed_ramp = feed_cutting * spec.ramp_ratio
    finish_feed = feed_cutting * spec.finish_ratio
    return dict(
        tool_spindleSpeed=f"{rpm:.0f}rpm",
        tool_feedPerTooth=f"{chip_load:.6f} mm",
        tool_feedCutting=f"{feed_cutting:.3f} mm/min",
        tool_feedPlunge=f"{feed_plunge:.3f} mm/min",
        tool_feedRamp=f"{feed_ramp:.3f} mm/min",
        finishFeedrate=f"{finish_feed:.3f} mm/min",
    )
