"""Redraw paper figures from existing results, without model estimation/optimization."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
STEPS = {
    "figure1": ("1", ["python", "-m", "pysrc.scripts.figure1", "--plot-only"]),
    "capture": ("2", ["Rscript", "rsrc/analysis/carbon_capture_curves/02_analysis.R"]),
    "calibration": ("3,4", ["Rscript", "rsrc/analysis/calibration_maps_1043_sites.R"]),
    "deterministic": ("5,6", ["python", "-m", "pysrc.scripts.conduction_det", "--figures-only"]),
    "det-maps": ("7,8", ["Rscript", "rsrc/analysis/map_1043_det.R"]),
    "densities": ("9,18,19", [
        "python", "-m", "pysrc.scripts.conduction_hmc", "--skip-optimization",
        "--xi", "1", "2", "0.5", "--figures", "density",
        "--gamma-sites", "938", "929", "--theta-sites", "985", "1028",
    ]),
    "hmc-comparisons": ("10,11,12,13", [
        "python", "-m", "pysrc.scripts.conduction_hmc", "--skip-optimization",
        "--xi", "1", "--figures", "histograms", "trajectories",
    ]),
    "mpc": ("14", ["python", "-m", "pysrc.scripts.mpc_trajectory"]),
    "delta": ("15", ["python", "-m", "pysrc.scripts.deterministic_delta_sensitivity", "--plot-only"]),
    "hmm": ("16", ["python", "-m", "pysrc.scripts.price_estimation", "--plot-only"]),
    "entropy-map": ("17", ["Rscript", "rsrc/analysis/map_kl.R"]),
    "hmc-map-1": ("20", ["Rscript", "rsrc/analysis/map_1043_hmc_xi1.R"]),
    "hmc-map-05": ("21", ["Rscript", "rsrc/analysis/map_1043_hmc_xi05.R"]),
    "r2": ("22", ["python", "-m", "pysrc.scripts.bayesian_R2"]),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", nargs="+", choices=list(STEPS), default=list(STEPS))
    parser.add_argument("--formats", nargs="+", choices=["png", "pdf"], default=["pdf"],
                        help="Default pdf preserves all original PNGs.")
    parser.add_argument("--r-library", type=Path,
                        help="Use an existing R package library with Rscript --vanilla, bypassing renv startup.")
    parser.add_argument("--list", action="store_true", help="Print commands without running them.")
    parser.add_argument("--collect", action="store_true", help="Collect paper files after redrawing.")
    args = parser.parse_args()
    env = os.environ.copy()
    env["PAPER_FIGURE_FORMATS"] = ",".join(args.formats)
    env["MPLBACKEND"] = "Agg"
    env.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "amazon-paper-mpl"))
    env.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "amazon-paper-xdg"))
    env["PYTHONUNBUFFERED"] = "1"
    if args.r_library:
        env["R_LIBS_USER"] = str(args.r_library.resolve())

    for group in args.groups:
        figures, template = STEPS[group]
        command = list(template)
        if command[0] == "python":
            command[0] = sys.executable
        elif args.r_library:
            command.insert(1, "--vanilla")
        print(f"Figures {figures}: {shlex.join(command)}", flush=True)
        if not args.list:
            subprocess.run(command, cwd=ROOT, env=env, check=True)

    if args.collect:
        command = [sys.executable, "-m", "pysrc.replication.build_results_in_paper",
                   "--figures-only", "--figure-formats", *args.formats]
        print(shlex.join(command), flush=True)
        if not args.list:
            subprocess.run(command, cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
