from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

import sympy as sp


SLICAP_DIR = Path(__file__).resolve().parents[1]
if str(SLICAP_DIR) not in sys.path:
    sys.path.insert(0, str(SLICAP_DIR))

import sfg_bridge


def _error(
    relative: float,
    magnitude: float,
    phase: float,
    *,
    accepted: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        accepted=accepted,
        max_relative_error=relative,
        max_magnitude_error_db=magnitude,
        max_phase_error_deg=phase,
    )


class SfgBridgeTest(unittest.TestCase):
    def test_default_netlist_has_title_and_bode_uses_hz(self) -> None:
        packup_source = (SLICAP_DIR / "packup2.py").read_text(encoding="utf-8")
        bode_source = (SLICAP_DIR / "run_bode.py").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_NETLIST = """Common_source_test\nVdd ', packup_source)
        self.assertEqual(bode_source.count('sweepScale=""'), 2)
        self.assertNotIn('sweepScale="M"', bode_source)

    def test_frequency_uses_angular_frequency_units(self) -> None:
        self.assertEqual(
            sfg_bridge._format_frequency(31_830_988.618379068),
            "31.831 MHz (ω=200 Mrad/s)",
        )

    def test_report_uses_dominant_error_and_frequency_band_target_roots(self) -> None:
        captured: dict[str, object] = {}

        class FakeConfig:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        target_root = SimpleNamespace(
            kind="pole",
            root_index=1,
            expression=-1 / (sp.Symbol("Rd") * sp.Symbol("cdg1")),
            reference_value=complex(-2e8, 0),
            reference_frequency_hz=31_830_988.618379068,
            numeric_value=complex(-2e8, 0),
            frequency_hz=31_830_988.618379068,
            relative_root_error=0.0,
            status="resolved",
        )
        graph_error = _error(0.0, 0.0, 0.0)
        # Relative error and the object's legacy flag must not control the
        # desktop-aligned 2 dB / 5 degree acceptance policy.
        dominant_error = _error(99.0, 0.12484, 0.49831, accepted=False)
        dominant = SimpleNamespace(
            transfer=sp.Symbol("H_dominant"),
            nominal_error=dominant_error,
            parameter_influences=(),
        )
        transfer = SimpleNamespace(
            success=True,
            transfer=sp.Symbol("H_graph"),
            error=None,
        )
        subrange = SimpleNamespace(
            cluster_index=1,
            lower_frequency_hz=1e-3,
            upper_frequency_hz=1e8,
            transfer=transfer,
            dominant_term_transfer=dominant,
            target_root_approximations=(target_root,),
            error=graph_error,
        )
        result = SimpleNamespace(
            pipeline=SimpleNamespace(
                reference=SimpleNamespace(laplace=sp.Symbol("H_reference")),
                clusters=(),
                error_specs=(),
            ),
            subrange_results=(subrange,),
            final_error=graph_error,
        )

        pipeline_module = ModuleType("sfg_prototype.pipeline")
        pipeline_module.SimplificationConfig = FakeConfig
        pipeline_module.simplify_netlist = lambda *args, **kwargs: result
        pipeline_module.error_policy_report = lambda value: ""
        pipeline_module.error_trace_report = lambda value: ""
        pipeline_module.operation_ranking_report = lambda value: ""
        pipeline_module.subrange_simplification_report = lambda value: ""
        package_module = ModuleType("sfg_prototype")
        package_module.__path__ = []

        previous_package = sys.modules.get("sfg_prototype")
        previous_pipeline = sys.modules.get("sfg_prototype.pipeline")
        sys.modules["sfg_prototype"] = package_module
        sys.modules["sfg_prototype.pipeline"] = pipeline_module
        try:
            response = sfg_bridge.run_sfg_symbolic_simplification(
                "Test circuit\n.source Vin\n.detector V_out\n.end",
                magnitude_error_db=2.0,
                phase_error_deg=5.0,
            )
        finally:
            if previous_package is None:
                sys.modules.pop("sfg_prototype", None)
            else:
                sys.modules["sfg_prototype"] = previous_package
            if previous_pipeline is None:
                sys.modules.pop("sfg_prototype.pipeline", None)
            else:
                sys.modules["sfg_prototype.pipeline"] = previous_pipeline

        markdown = response["markdown"]
        self.assertTrue(response["ok"])
        self.assertEqual(captured["error_norm"], "bode_linf")
        self.assertIn("H_{dominant}", markdown)
        self.assertNotIn("H_{graph}", markdown)
        self.assertIn("最大幅值 0.125 dB", markdown)
        self.assertIn("最大相位 0.498°", markdown)
        self.assertIn("整体误差验收: <span", markdown)
        self.assertIn(">通过</span>", markdown)
        self.assertIn("精确数值频率", markdown)
        self.assertIn("31.831 MHz (ω=200 Mrad/s)", markdown)
        self.assertIn("根位置偏差（诊断）", markdown)
        self.assertNotIn("相对 0", markdown)

    def test_invalid_bode_limit_is_rejected(self) -> None:
        response = sfg_bridge.run_sfg_symbolic_simplification(
            "Test circuit\n.source Vin\n.detector V_out\n.end",
            magnitude_error_db=-1,
            phase_error_deg=5,
        )
        self.assertFalse(response["ok"])
        self.assertIn("幅值误差上限", response["error"])


if __name__ == "__main__":
    unittest.main()
