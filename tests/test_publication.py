import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from pysrc.analysis.publication import (
    AVERSE_STYLE, NEUTRAL_STYLE, PUBLICATION_DPI, TRANSFER_STYLES,
    BLUE, VERMILLION, LINE_WIDTH, save_publication_figure, shade_under_line,
)
from pysrc.replication.build_results_in_paper import _copy_results_in_paper_figures
from pysrc.replication.paper_assets import (
    PDF_UPLOAD_NAMES, generated_figure_name_candidates, paper_figure_format_name,
)


class PublicationTests(unittest.TestCase):
    def test_upload_names_preserve_original_png_counterparts(self):
        for old, new in PDF_UPLOAD_NAMES.items():
            with self.subTest(name=new):
                self.assertEqual(paper_figure_format_name(old, "pdf"), new)
                self.assertEqual(paper_figure_format_name(new, "pdf"), new)
                self.assertEqual(paper_figure_format_name(new, "png"), str(Path(old).with_suffix(".png")))
                self.assertEqual(paper_figure_format_name(str(Path(old).with_suffix(".png")), "pdf"), new)

    def test_collection_uses_all_four_pdf_upload_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "output").mkdir()
            records = []
            for old in PDF_UPLOAD_NAMES:
                prefix, source = old.split("_", 1)
                number = int(prefix.removeprefix("Figure"))
                (root / "output" / source).write_bytes(b"%PDF-upload-fixture")
                records.append({"figure_number": number, "exhibit": f"Figure {number}",
                                "source_basename": str(Path(source).with_suffix(".png")),
                                "paper_include_path": source})
            inputs = root / "inputs.csv"
            pd.DataFrame(records).to_csv(inputs, index=False)
            for _ in range(2):
                manifest = _copy_results_in_paper_figures(root, root / "results_in_paper", None, inputs, ("pdf",))
                self.assertTrue(manifest["copied"].all())
            self.assertEqual({p.name for p in (root / "results_in_paper").iterdir()}, set(PDF_UPLOAD_NAMES.values()))

    def test_figure1_highlights_are_black_bold_and_open(self):
        module = importlib.import_module("pysrc.scripts.figure1")
        data = pd.DataFrame({
            "Country Code": ["CHN", "IND", "EUU", "USA", "AMAZON"],
            "gdp_pc_ppp_2018_100k": [0.1, 0.03, 0.4, 0.6, 0.1],
            "emissions_pc_2018": [7, 2, 6, 15, 40.6],
        })
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, "save_publication_figure") as save:
            module.make_figure(data, Path(directory) / "figure.png", Path(directory) / "figure.pdf")
        ax = save.call_args.args[0].axes[0]
        highlights = [t for t in ax.texts if t.get_text() in module.HIGHLIGHTS.values()]
        self.assertEqual(len(highlights), 4)
        for label in highlights:
            self.assertEqual(label.get_color(), "black")
            self.assertEqual(label.get_fontsize(), 12)
            self.assertEqual(label.get_fontweight(), "bold")
        for marker in ax.collections[1:5]:
            self.assertEqual(tuple(marker.get_edgecolors()[0][:3]), (0, 0, 0))
            self.assertEqual(tuple(marker.get_facecolors()[0][:3]), (1, 1, 1))

    def test_original_model_color_mapping(self):
        self.assertEqual(NEUTRAL_STYLE["color"], VERMILLION)
        self.assertEqual(AVERSE_STYLE["color"], BLUE)
        self.assertEqual(LINE_WIDTH, 3.2)

    def test_density_shading_stays_below_opaque_lines(self):
        fig, ax = plt.subplots()
        dashed, = ax.plot([0, 1, 2], [0, 1, 0], color=VERMILLION,
                          linestyle="--", linewidth=LINE_WIDTH, zorder=2)
        solid, = ax.plot([0, 1, 2], [0, 0.8, 0], color=BLUE,
                         linewidth=LINE_WIDTH, zorder=3)
        shade = shade_under_line(ax, dashed, alpha=0.18)
        self.assertEqual(shade.get_alpha(), 0.18)
        self.assertEqual(tuple(shade.get_facecolor()[0][:3]), matplotlib.colors.to_rgb(VERMILLION))
        self.assertLess(shade.get_zorder(), dashed.get_zorder())
        self.assertLess(dashed.get_zorder(), solid.get_zorder())
        self.assertIsNone(dashed.get_alpha())
        plt.close(fig)

    def test_export_enforces_1200_dpi_for_both_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            fig, _ = plt.subplots()
            with patch.dict("os.environ", {"PAPER_FIGURE_FORMATS": "png,pdf"}), \
                 patch.object(fig, "savefig") as save:
                save_publication_figure(fig, Path(directory) / "figure.png", dpi=100)
            plt.close(fig)
            self.assertEqual(PUBLICATION_DPI, 1200)
            self.assertEqual(save.call_count, 2)
            for call in save.call_args_list:
                self.assertEqual(call.kwargs["dpi"], 1200)

    def test_color_styles_keep_noncolor_distinctions(self):
        for style in [NEUTRAL_STYLE, AVERSE_STYLE, *TRANSFER_STYLES.values()]:
            rgb = matplotlib.colors.to_rgb(style["color"])
            self.assertGreater(max(rgb) - min(rgb), 0.1)
        self.assertNotEqual(NEUTRAL_STYLE["linestyle"], AVERSE_STYLE["linestyle"])
        self.assertEqual(len({s["linestyle"] for s in TRANSFER_STYLES.values()}), 3)

    def test_pdf_only_keeps_png_and_exports_vector_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.png"
            path.write_bytes(b"original PNG sentinel")
            fig, ax = plt.subplots()
            ax.plot([0, 1], [0, 1], color="black")
            with patch.dict("os.environ", {"PAPER_FIGURE_FORMATS": "pdf"}):
                written = save_publication_figure(fig, path)
            plt.close(fig)
            self.assertEqual(path.read_bytes(), b"original PNG sentinel")
            self.assertEqual(written, [path.with_suffix(".pdf")])
            self.assertTrue(written[0].read_bytes().startswith(b"%PDF-"))
            self.assertNotIn(b"/Subtype /Image", written[0].read_bytes())

    def test_default_exports_both_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            fig, ax = plt.subplots(figsize=(1, 1))
            ax.plot([1, 2])
            with patch.dict("os.environ", {"PAPER_FIGURE_FORMATS": "png,pdf"}):
                paths = save_publication_figure(fig, Path(directory) / "figure.png")
            plt.close(fig)
            self.assertEqual({p.suffix for p in paths}, {".png", ".pdf"})
            self.assertTrue(all(p.exists() for p in paths))

    def test_aliases_preserve_requested_format(self):
        self.assertEqual(
            generated_figure_name_candidates("mpc_landallocation_b_0_baseline_same_ylim.pdf"),
            ["mpc_landallocation_b_0_baseline_same_ylim.pdf", "mpc_landallocation_b_0_adjust.pdf"],
        )
        self.assertEqual(
            generated_figure_name_candidates("aggregate_percentage_Z_example_same_ylim.pdf"),
            ["aggregate_percentage_Z_example_same_ylim.pdf", "aggregate_percentage_Z_example.pdf"],
        )

    def test_pdf_collection_preserves_original_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "output").mkdir()
            (root / "results_in_paper").mkdir()
            (root / "output" / "example.pdf").write_bytes(b"%PDF-example")
            png = root / "results_in_paper" / "Figure1_example.png"
            png.write_bytes(b"original")
            inputs = root / "inputs.csv"
            pd.DataFrame([{
                "figure_number": 1, "exhibit": "Figure 1",
                "source_basename": "example.png", "paper_include_path": "example.png",
            }]).to_csv(inputs, index=False)
            manifest = _copy_results_in_paper_figures(
                root, root / "results_in_paper", None, inputs, ("pdf",),
            )
            self.assertEqual(png.read_bytes(), b"original")
            self.assertEqual(manifest.iloc[0]["generated_file"], "results_in_paper/Figure1_example.pdf")
            self.assertTrue(manifest.iloc[0]["copied"])

    def test_hmm_import_does_not_estimate_and_redraw_uses_cache(self):
        module = importlib.import_module("pysrc.scripts.price_estimation")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "job-outs/stage_hmm/price_estimation/0001_run.out"
            log.parent.mkdir(parents=True)
            log.write_text("distinct variances (1, array([35.76, 44.32])\n"
                           "common variances (1, array([32.49, 42.85])\n")
            prices = pd.DataFrame({"price_real_mon_cattle": [40.0] * 276})
            probabilities = pd.DataFrame({"predict": [0.5] * 276})
            with patch.object(module, "get_path", side_effect=lambda *args: root.joinpath(*args)), \
                 patch.object(module.pd, "read_csv", side_effect=[prices, probabilities, probabilities]), \
                 patch.object(module, "est", side_effect=AssertionError("must not estimate")), \
                 patch.object(module, "plot_hmm_results") as plot:
                module.redraw_cached_figures()
        self.assertEqual(plot.call_count, 2)
        for call in plot.call_args_list:
            self.assertEqual(len(call.args[1]), 276)
            self.assertFalse(call.kwargs["save_inputs"])

    def test_delta_plot_only_does_not_solve_or_save_solutions(self):
        module = importlib.import_module("pysrc.scripts.deterministic_delta_sensitivity")
        with patch("sys.argv", ["delta", "--plot-only"]), \
             patch.object(module, "load_site_data", return_value=([1], None, None)), \
             patch.object(module, "carbon_price", return_value=6.8), \
             patch.object(module, "carbon_price_with_metric", return_value=(4.9, 0)), \
             patch.object(module, "load_solution", return_value=None) as load, \
             patch.object(module, "solve_deterministic_trajectory", side_effect=AssertionError("must not solve")), \
             patch.object(module, "save_solution", side_effect=AssertionError("must not save solutions")), \
             patch.object(module, "plot_zshare_delta_comparison_figure") as plot:
            self.assertEqual(module.main(), 0)
        self.assertEqual(load.call_count, 4)
        self.assertEqual(plot.call_count, 1)


if __name__ == "__main__":
    unittest.main()
