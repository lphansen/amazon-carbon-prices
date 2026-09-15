import argparse
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

cache_root = Path(tempfile.gettempdir()) / "amazon_carbon_prices_cache"
(cache_root / "matplotlib").mkdir(parents=True, exist_ok=True)
(cache_root / "xdg").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_root / "xdg"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pysrc.optimization import PlannerSolution, solve_planner_problem
from pysrc.replication.parameters import CarbonPriceKey, carbon_price, load_carbon_prices, normalize_xi
from pysrc.services.data_service import load_productivity_params, load_site_data
from pysrc.services.file_service import get_path
from pysrc.analysis.publication import LINE_WIDTH, save_publication_figure


@dataclass(frozen=True)
class TrajectoryMetrics:
    z_share_pct: np.ndarray
    capture_gt: np.ndarray
    net_transfer: np.ndarray


def delta_slug(delta: float) -> str:
    return f"delta_{delta:g}".replace("-", "m").replace(".", "p")


def format_number(value: float) -> str:
    return f"{value:g}"


def solution_dir(
    *,
    outputs_root: Path,
    delta: float,
    solver: str,
    sites: int,
    pa: float,
    pe: float,
) -> Path:
    return (
        outputs_root
        / delta_slug(delta)
        / "optimization"
        / "det"
        / solver
        / f"{sites}sites"
        / f"pa_{format_number(pa)}"
        / f"pe_{format_number(pe)}"
    )


def baseline_solution_dir(
    *,
    outputs_root: Path,
    solver: str,
    sites: int,
    pa: float,
    pe: float,
) -> Path:
    return (
        outputs_root
        / "optimization"
        / "det"
        / solver
        / f"{sites}sites"
        / f"pa_{format_number(pa)}"
        / f"pe_{format_number(pe)}"
    )


def figures_dir(*, outputs_root: Path, delta: float) -> Path:
    return outputs_root / delta_slug(delta) / "figures"


def match_png_canvas_to_reference(output_path: Path, reference_path: Path) -> None:
    if not reference_path.exists():
        print(
            "Reference figure is missing; leaving sensitivity figure at matplotlib size: "
            f"{reference_path}"
        )
        return

    image = mpimg.imread(output_path)
    reference = mpimg.imread(reference_path)
    source_h, source_w = image.shape[:2]
    target_h, target_w = reference.shape[:2]
    if (source_w, source_h) == (target_w, target_h):
        return

    if image.ndim == 2:
        canvas = np.ones((target_h, target_w), dtype=image.dtype)
    else:
        canvas = np.ones((target_h, target_w, image.shape[2]), dtype=image.dtype)

    copy_w = min(source_w, target_w)
    copy_h = min(source_h, target_h)
    source_x0 = max((source_w - target_w) // 2, 0)
    source_y0 = max((source_h - target_h) // 2, 0)
    target_x0 = max((target_w - source_w) // 2, 0)
    target_y0 = max((target_h - source_h) // 2, 0)

    canvas[
        target_y0 : target_y0 + copy_h,
        target_x0 : target_x0 + copy_w,
        ...,
    ] = image[
        source_y0 : source_y0 + copy_h,
        source_x0 : source_x0 + copy_w,
        ...,
    ]
    mpimg.imsave(output_path, canvas, format="png", dpi=100)


def save_figure_like_reference(output_path: Path, reference_path: Path, **savefig_kwargs) -> None:
    savefig_options = {"format": "png", "dpi": 100}
    savefig_options.update(savefig_kwargs)
    plt.savefig(output_path, **savefig_options)
    match_png_canvas_to_reference(output_path, reference_path)


def save_solution(solution: PlannerSolution, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(output_dir / "Z.txt", solution.Z, delimiter=",")
    np.savetxt(output_dir / "X.txt", solution.X, delimiter=",")
    np.savetxt(output_dir / "U.txt", solution.U, delimiter=",")
    np.savetxt(output_dir / "V.txt", solution.V, delimiter=",")


def load_solution(output_dir: Path) -> PlannerSolution:
    missing = [
        name
        for name in ["Z.txt", "X.txt", "U.txt", "V.txt"]
        if not (output_dir / name).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Missing baseline deterministic solution files {missing} in {output_dir}. "
            "Run the baseline deterministic optimization jobs before the delta sensitivity step."
        )
    return PlannerSolution(
        Z=np.loadtxt(output_dir / "Z.txt", delimiter=","),
        X=np.loadtxt(output_dir / "X.txt", delimiter=","),
        U=np.loadtxt(output_dir / "U.txt", delimiter=","),
        V=np.loadtxt(output_dir / "V.txt", delimiter=","),
    )


def carbon_price_with_metric(key: CarbonPriceKey, path: Path) -> tuple[float, float]:
    df = load_carbon_prices(path)
    mask = (df["context"] == key.context) & (df["model"] == key.model)
    if key.sites is not None and "sites" in df.columns:
        mask &= df["sites"].fillna(-1).astype(int) == int(key.sites)
    if "xi" in df.columns:
        mask &= df["xi"] == normalize_xi(key.xi)
    if key.price_model is not None and "price_model" in df.columns:
        mask &= df["price_model"].fillna("") == key.price_model

    matches = df.loc[mask]
    if matches.empty:
        available = df[
            [c for c in ["context", "model", "sites", "xi", "price_model", "pee"] if c in df]
        ].to_dict("records")
        raise KeyError(f"No sensitivity carbon price for {key}. Available keys: {available}")
    if len(matches) > 1:
        matches = matches.sort_values(["abs_metric", "pee"], na_position="last")
    row = matches.iloc[0]
    metric = np.nan
    if "metric" in row and pd.notna(row["metric"]):
        metric = float(row["metric"])
    return float(row["pee"]), metric


def solve_deterministic_trajectory(
    *,
    sites: int,
    pe: float,
    pa: float,
    delta: float,
    solver: str,
    time_horizon: int,
) -> PlannerSolution:
    zbar, z0, forest_area = load_site_data(sites)
    theta, gamma = load_productivity_params(sites)
    x0 = gamma * forest_area
    return solve_planner_problem(
        time_horizon=time_horizon,
        theta=theta,
        gamma=gamma,
        x0=x0,
        zbar=zbar,
        z0=z0,
        price_emissions=pe,
        price_cattle=pa,
        delta=delta,
        solver=solver,
    )


def trajectory_metrics(
    solution: PlannerSolution,
    zbar: np.ndarray,
    years: int,
    transfer: float = 0.0,
    kappa: float = 2.094215255,
) -> TrajectoryMetrics:
    last_index = min(years, len(solution.Z) - 1)
    z = solution.Z[: last_index + 1]
    x = solution.X[: last_index + 1]
    z_share_pct = np.sum(z, axis=1) / np.sum(zbar) * 100
    capture_gt = np.sum(x, axis=1) - np.sum(x[0])
    if last_index > 0:
        x_dot = np.diff(solution.X[: last_index + 1], axis=0)
        net_transfer = -transfer * (kappa * solution.Z[1 : last_index + 1] - x_dot).sum(axis=1)
        net_transfer = np.concatenate([net_transfer, [np.nan]])
    else:
        net_transfer = np.array([np.nan])
    return TrajectoryMetrics(
        z_share_pct=z_share_pct,
        capture_gt=capture_gt,
        net_transfer=net_transfer,
    )


def plot_land_allocation_figures(
    *,
    sites: int,
    pee: float,
    delta: float,
    outputs_root: Path,
    zbar: np.ndarray,
    years: int,
    sensitivity_solutions: dict[float, PlannerSolution],
) -> None:
    output_dir = figures_dir(outputs_root=outputs_root, delta=delta)
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_transfers = [transfer for transfer in [0.0, 15.0, 25.0] if transfer in sensitivity_solutions]
    if not plot_transfers:
        print(f"No transfer levels available for land-allocation figures at delta={delta:g}.")
        return

    colors = {0.0: "red", 15.0: "green", 25.0: "blue"}
    labels = {transfer: format_number(transfer) for transfer in plot_transfers}
    metrics = {
        transfer: trajectory_metrics(solution, zbar, years, transfer)
        for transfer, solution in sensitivity_solutions.items()
    }

    plt.figure(figsize=(10, 6))
    plt.plot([], [], " ", label=f"$p^{{ee}}$={format_number(pee)}       $b$")
    for transfer in plot_transfers:
        time = list(range(len(metrics[transfer].z_share_pct)))
        plt.plot(
            time,
            metrics[transfer].z_share_pct,
            label=labels[transfer],
            linewidth=4,
            color=colors.get(transfer),
        )
    plt.xlabel("years", fontsize=16)
    plt.ylabel("Z(%)", fontsize=16)
    plt.xlim(0, max(time) + 2)
    plt.yticks([0, 5, 10, 15, 20], ["0", "5", "10", "15", "20"])
    plt.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=5,
        frameon=False,
        fontsize=16,
    )
    save_figure_like_reference(
        output_dir / f"pred_zshare_{sites}_sites_det_{delta_slug(delta)}.png",
        get_path("output", "figures", f"pred_zshare_{sites}_sites_det.png"),
        bbox_inches="tight",
    )
    plt.close()

    plt.figure(figsize=(10, 6))
    ax = plt.gca()
    plt.plot([], [], " ", label=f"$p^{{ee}}$={format_number(pee)}       $b$")
    for transfer in plot_transfers:
        time = list(range(len(metrics[transfer].capture_gt)))
        plt.plot(
            time,
            metrics[transfer].capture_gt,
            label=labels[transfer],
            linewidth=4,
            color=colors.get(transfer),
        )
    ax.spines["bottom"].set_position(("data", 0))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_ticks_position("bottom")
    ax.yaxis.set_ticks_position("left")
    plt.xlabel("years", fontsize=18)
    plt.ylabel("Capture (billions CO2e)", fontsize=18)
    plt.xlim(0, max(time) + 2)
    ax.set_xticks([10, 20, 30, 40, 50])
    plt.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=5,
        frameon=False,
        fontsize=18,
    )
    save_figure_like_reference(
        output_dir / f"plot_pred_x_{sites}_sites_det_{delta_slug(delta)}.png",
        get_path("output", "figures", f"plot_pred_x_{sites}_sites_det.png"),
        bbox_inches="tight",
    )
    plt.close()


def plot_zshare_delta_comparison_figure(
    *,
    sites: int,
    base_delta: float,
    sensitivity_delta: float,
    outputs_root: Path,
    zbar: np.ndarray,
    years: int,
    base_solutions: dict[float, PlannerSolution],
    sensitivity_solutions: dict[float, PlannerSolution],
) -> None:
    output_dir = figures_dir(outputs_root=outputs_root, delta=sensitivity_delta)
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_transfers = [
        transfer
        for transfer in [0.0, 25.0]
        if transfer in base_solutions and transfer in sensitivity_solutions
    ]
    if not plot_transfers:
        print(
            "No matching transfer levels available for Z-share delta comparison "
            f"at delta={sensitivity_delta:g}."
        )
        return

    markers = {0.0: "o", 25.0: "s"}
    delta_specs = [
        (base_delta, "-", base_solutions),
        (sensitivity_delta, "--", sensitivity_solutions),
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    for transfer in plot_transfers:
        for delta, linestyle, solutions in delta_specs:
            metrics = trajectory_metrics(solutions[transfer], zbar, years, transfer)
            time = list(range(len(metrics.z_share_pct)))
            ax.plot(
                time,
                metrics.z_share_pct,
                label=rf"$b={format_number(transfer)}, \delta={delta:.2f}$",
                linewidth=LINE_WIDTH,
                linestyle=linestyle,
                color="#D55E00" if transfer == 0 else "#0072B2",
                marker=markers[transfer], markerfacecolor="white", markersize=5.5, markeredgewidth=1.1,
                markevery=(0 if delta == base_delta else 3, 8),
            )

    ax.set_xlabel("years", fontsize=16)
    ax.set_ylabel("Z(%)", fontsize=16)
    ax.set_xlim(0, max(time) + 2)
    ax.set_yticks([0, 5, 10, 15, 20])
    ax.set_yticklabels(["0", "5", "10", "15", "20"])

    # Explicitly keep the full box.
    for side in ["top", "right", "bottom", "left"]:
        ax.spines[side].set_visible(True)
        ax.spines[side].set_linewidth(1.0)

    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=2,
        frameon=False,
        fontsize=16,
    )

    save_publication_figure(fig,
        output_dir
        / f"pred_zshare_delta_comparison_{sites}_sites_det_{delta_slug(sensitivity_delta)}.png",
        format="png",
        dpi=1200,
        bbox_inches="tight",
        pad_inches=0.08,
    )
    plt.close(fig)


def plot_net_transfers_figure(
    *,
    sites: int,
    delta: float,
    outputs_root: Path,
    sensitivity_solutions: dict[float, PlannerSolution],
    kappa: float = 2.094215255,
) -> None:
    output_dir = figures_dir(outputs_root=outputs_root, delta=delta)
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_transfers = [transfer for transfer in [15.0, 25.0] if transfer in sensitivity_solutions]
    if not plot_transfers:
        print(f"No transfer levels available for net-transfer figure at delta={delta:g}.")
        return

    colors = {15.0: "blue", 25.0: "red"}
    plt.figure(figsize=(6.4, 4.8))
    for transfer in plot_transfers:
        solution = sensitivity_solutions[transfer]
        x_dot = np.diff(solution.X, axis=0)
        transfers = -transfer * (kappa * solution.Z[1:] - x_dot).sum(axis=1)
        plt.plot(
            transfers[:50],
            label=f"b=${format_number(transfer)}",
            linewidth=4,
            color=colors.get(transfer),
        )
    plt.legend()
    plt.xlabel("years")
    plt.ylabel("Net Transfers ($ billion)")
    save_figure_like_reference(
        output_dir / f"net_transfers_{sites}_sites_det_{delta_slug(delta)}.png",
        get_path("output", "figures", "net_transfers.png"),
    )
    plt.close()


def summarize_difference(
    *,
    sites: int,
    base_pee: float,
    sensitivity_pee: float,
    sensitivity_price_metric: float,
    transfer: float,
    base_delta: float,
    sensitivity_delta: float,
    years: int,
    base: TrajectoryMetrics,
    sensitivity: TrajectoryMetrics,
) -> dict[str, float]:
    z_diff = sensitivity.z_share_pct - base.z_share_pct
    capture_diff = sensitivity.capture_gt - base.capture_gt
    net_transfer_diff = sensitivity.net_transfer - base.net_transfer
    final_capture_base = base.capture_gt[-1]
    relative_capture_diff_pct = np.nan
    if final_capture_base != 0:
        relative_capture_diff_pct = capture_diff[-1] / final_capture_base * 100
    valid_net_transfer_diff = net_transfer_diff[np.isfinite(net_transfer_diff)]
    max_abs_net_transfer_diff = np.nan
    if valid_net_transfer_diff.size:
        max_abs_net_transfer_diff = float(np.max(np.abs(valid_net_transfer_diff)))
    return {
        "sites": sites,
        "transfer": transfer,
        "base_delta": base_delta,
        "sensitivity_delta": sensitivity_delta,
        "base_pee": base_pee,
        "sensitivity_pee": sensitivity_pee,
        "sensitivity_price_metric": sensitivity_price_metric,
        "base_price_emissions": base_pee + transfer,
        "sensitivity_price_emissions": sensitivity_pee + transfer,
        "years_compared": years,
        "final_z_share_base_pct": base.z_share_pct[-1],
        "final_z_share_sensitivity_pct": sensitivity.z_share_pct[-1],
        "final_z_share_diff_pp": z_diff[-1],
        "max_abs_z_share_diff_pp": float(np.max(np.abs(z_diff))),
        "final_capture_base_gt": final_capture_base,
        "final_capture_sensitivity_gt": sensitivity.capture_gt[-1],
        "final_capture_diff_gt": capture_diff[-1],
        "max_abs_capture_diff_gt": float(np.max(np.abs(capture_diff))),
        "relative_final_capture_diff_pct": relative_capture_diff_pct,
        "max_abs_net_transfer_diff": max_abs_net_transfer_diff,
    }


def trajectory_rows(
    *,
    sites: int,
    base_pee: float,
    sensitivity_pee: float,
    transfer: float,
    base_delta: float,
    sensitivity_delta: float,
    base: TrajectoryMetrics,
    sensitivity: TrajectoryMetrics,
) -> list[dict[str, float]]:
    z_diff = sensitivity.z_share_pct - base.z_share_pct
    capture_diff = sensitivity.capture_gt - base.capture_gt
    net_transfer_diff = sensitivity.net_transfer - base.net_transfer
    return [
        {
            "sites": sites,
            "transfer": transfer,
            "base_delta": base_delta,
            "sensitivity_delta": sensitivity_delta,
            "base_pee": base_pee,
            "sensitivity_pee": sensitivity_pee,
            "base_price_emissions": base_pee + transfer,
            "sensitivity_price_emissions": sensitivity_pee + transfer,
            "year": year,
            "base_z_share_pct": base.z_share_pct[year],
            "sensitivity_z_share_pct": sensitivity.z_share_pct[year],
            "diff_z_share_pp": z_diff[year],
            "base_capture_gt": base.capture_gt[year],
            "sensitivity_capture_gt": sensitivity.capture_gt[year],
            "diff_capture_gt": capture_diff[year],
            "base_net_transfer": base.net_transfer[year],
            "sensitivity_net_transfer": sensitivity.net_transfer[year],
            "diff_net_transfer": net_transfer_diff[year],
        }
        for year in range(len(base.z_share_pct))
    ]


def average_abs_percent_change(group: pd.DataFrame, base_col: str, sensitivity_col: str) -> float:
    base = pd.to_numeric(group[base_col], errors="coerce")
    sensitivity = pd.to_numeric(group[sensitivity_col], errors="coerce")
    valid = base.notna() & sensitivity.notna() & (base.abs() > 1e-12)
    if not valid.any():
        return np.nan
    percent_change = (sensitivity[valid] - base[valid]) / base[valid] * 100
    return float(percent_change.abs().mean())


def latex_percent(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"{value:.2f}\\%"


def latex_number(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return ""
    return f"{value:.{digits}f}"


def write_latex_comparison_table(
    *,
    summary_path: Path,
    trajectories_path: Path,
    table_path: Path,
) -> None:
    summary = pd.read_csv(summary_path)
    trajectories = pd.read_csv(trajectories_path)
    rows = []

    group_cols = [
        "sites",
        "transfer",
        "base_delta",
        "sensitivity_delta",
        "base_pee",
        "sensitivity_pee",
    ]
    trajectory_groups = {
        key: group
        for key, group in trajectories.groupby(group_cols, dropna=False)
    }

    for _, row in summary.sort_values(["sites", "transfer"]).iterrows():
        key = tuple(row[col] for col in group_cols)
        group = trajectory_groups.get(key)
        if group is None:
            continue
        rows.append(
            {
                r"$\delta$": (
                    f"${latex_number(row['base_delta'], 2)}"
                    rf"\to {latex_number(row['sensitivity_delta'], 2)}$"
                ),
                r"$b$": latex_number(row["transfer"], 0),
                r"$P^{ee}$": (
                    f"${latex_number(row['base_pee'], 1)}"
                    rf"\to {latex_number(row['sensitivity_pee'], 1)}$"
                ),
                r"average \% change in $Z_t$": latex_percent(
                    average_abs_percent_change(
                        group,
                        "base_z_share_pct",
                        "sensitivity_z_share_pct",
                    )
                ),
                r"average \% change in capture $X_t$": latex_percent(
                    average_abs_percent_change(
                        group,
                        "base_capture_gt",
                        "sensitivity_capture_gt",
                    )
                ),
                r"average \% change in net transfers": latex_percent(
                    average_abs_percent_change(
                        group,
                        "base_net_transfer",
                        "sensitivity_net_transfer",
                    )
                ),
            }
        )

    table_path.parent.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(rows)
    latex = table.to_latex(index=False, escape=False)
    table_path.write_text(latex)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare deterministic future trajectories under the baseline 2 percent "
            "discount rate and a 3 percent discount-rate sensitivity."
        )
    )
    parser.add_argument("--sites", type=int, nargs="+", default=[1043])
    parser.add_argument("--transfers", type=float, nargs="+", default=[0, 10, 15, 20, 25])
    parser.add_argument("--base-delta", type=float, default=0.02)
    parser.add_argument("--sensitivity-delta", type=float, default=0.03)
    parser.add_argument("--pa", type=float, default=41.11)
    parser.add_argument("--solver", default="gurobi")
    parser.add_argument("--time-horizon", type=int, default=200)
    parser.add_argument("--years", type=int, default=50)
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=get_path("output", "delta_sensitivity"),
        help="Root directory for delta-specific optimization outputs and figures.",
    )
    parser.add_argument(
        "--baseline-outputs-root",
        type=Path,
        default=get_path("output"),
        help=(
            "Root directory containing existing baseline deterministic solutions "
            "under optimization/det/..."
        ),
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Only write the CSV sensitivity summaries.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=get_path("replication", "derived", "deterministic_delta_sensitivity.csv"),
    )
    parser.add_argument(
        "--trajectories-out",
        type=Path,
        default=get_path(
            "replication",
            "derived",
            "deterministic_delta_sensitivity_trajectories.csv",
        ),
    )
    parser.add_argument(
        "--table-out",
        type=Path,
        default=get_path("replication", "derived", "deterministic_delta_sensitivity_table.tex"),
    )
    parser.add_argument(
        "--sensitivity-prices",
        type=Path,
        default=get_path("replication", "derived", "deterministic_delta_sensitivity_prices.csv"),
        help=(
            "Selected delta-sensitivity carbon prices produced by "
            "`derive-prices-det-delta-sensitivity`."
        ),
    )
    parser.add_argument("--plot-only", action="store_true",
                        help="Redraw Figure 15 from saved solutions without solving or updating tables.")
    args = parser.parse_args()

    if args.plot_only:
        for sites in args.sites:
            zbar, _, _ = load_site_data(sites)
            key = CarbonPriceKey(context="parameter_ambiguity", model="det", sites=sites, xi="inf")
            base_pee = carbon_price(key)
            sensitivity_pee, _ = carbon_price_with_metric(key, args.sensitivity_prices)
            base_solutions = {
                b: load_solution(baseline_solution_dir(
                    outputs_root=args.baseline_outputs_root, solver=args.solver,
                    sites=sites, pa=args.pa, pe=base_pee + b,
                )) for b in (0.0, 25.0)
            }
            sensitivity_solutions = {
                b: load_solution(solution_dir(
                    outputs_root=args.outputs_root, delta=args.sensitivity_delta,
                    solver=args.solver, sites=sites, pa=args.pa, pe=sensitivity_pee + b,
                )) for b in (0.0, 25.0)
            }
            plot_zshare_delta_comparison_figure(
                sites=sites, base_delta=args.base_delta,
                sensitivity_delta=args.sensitivity_delta, outputs_root=args.outputs_root,
                zbar=zbar, years=args.years, base_solutions=base_solutions,
                sensitivity_solutions=sensitivity_solutions,
            )
        return 0

    if args.years > args.time_horizon:
        raise ValueError("--years cannot exceed --time-horizon.")

    summary_rows: list[dict[str, float]] = []
    all_trajectory_rows: list[dict[str, float]] = []
    base_solutions_for_figures: dict[int, tuple[float, np.ndarray, dict[float, PlannerSolution]]] = {}
    solutions_for_figures: dict[int, tuple[float, np.ndarray, dict[float, PlannerSolution]]] = {}

    for sites in args.sites:
        zbar, _, _ = load_site_data(sites)
        price_key = CarbonPriceKey(
            context="parameter_ambiguity",
            model="det",
            sites=sites,
            xi="inf",
        )
        base_pee = carbon_price(price_key)
        sensitivity_pee, sensitivity_price_metric = carbon_price_with_metric(
            price_key,
            args.sensitivity_prices,
        )
        print(
            "Loaded deterministic sensitivity carbon price: "
            f"sites={sites}, base_pee={base_pee:g}, "
            f"sensitivity_pee={sensitivity_pee:g}, "
            f"sensitivity_metric={sensitivity_price_metric:g}"
        )
        for transfer in args.transfers:
            base_pe = base_pee + transfer
            sensitivity_pe = sensitivity_pee + transfer
            print(
                "Loading baseline and solving deterministic delta sensitivity: "
                f"sites={sites}, transfer={transfer:g}, "
                f"base_pe={base_pe:g}, sensitivity_pe={sensitivity_pe:g}, "
                f"delta={args.base_delta:g} vs {args.sensitivity_delta:g}"
            )
            base_solution = load_solution(
                baseline_solution_dir(
                    outputs_root=args.baseline_outputs_root,
                    solver=args.solver,
                    sites=sites,
                    pa=args.pa,
                    pe=base_pe,
                )
            )
            sensitivity_solution = solve_deterministic_trajectory(
                sites=sites,
                pe=sensitivity_pe,
                pa=args.pa,
                delta=args.sensitivity_delta,
                solver=args.solver,
                time_horizon=args.time_horizon,
            )
            save_solution(
                sensitivity_solution,
                solution_dir(
                    outputs_root=args.outputs_root,
                    delta=args.sensitivity_delta,
                    solver=args.solver,
                    sites=sites,
                    pa=args.pa,
                    pe=sensitivity_pe,
                ),
            )
            base_solutions_for_figures.setdefault(sites, (base_pee, zbar, {}))[2][float(transfer)] = (
                base_solution
            )
            solutions_for_figures.setdefault(sites, (sensitivity_pee, zbar, {}))[2][float(transfer)] = (
                sensitivity_solution
            )
            sensitivity = trajectory_metrics(sensitivity_solution, zbar, args.years, transfer)
            base = trajectory_metrics(base_solution, zbar, args.years, transfer)
            summary_rows.append(
                summarize_difference(
                    sites=sites,
                    base_pee=base_pee,
                    sensitivity_pee=sensitivity_pee,
                    sensitivity_price_metric=sensitivity_price_metric,
                    transfer=transfer,
                    base_delta=args.base_delta,
                    sensitivity_delta=args.sensitivity_delta,
                    years=args.years,
                    base=base,
                    sensitivity=sensitivity,
                )
            )
            all_trajectory_rows.extend(
                trajectory_rows(
                    sites=sites,
                    base_pee=base_pee,
                    sensitivity_pee=sensitivity_pee,
                    transfer=transfer,
                    base_delta=args.base_delta,
                    sensitivity_delta=args.sensitivity_delta,
                    base=base,
                    sensitivity=sensitivity,
                )
            )

    if not args.skip_figures:
        for sites, (pee, zbar, sensitivity_solutions) in solutions_for_figures.items():
            plot_land_allocation_figures(
                sites=sites,
                pee=pee,
                delta=args.sensitivity_delta,
                outputs_root=args.outputs_root,
                zbar=zbar,
                years=args.years,
                sensitivity_solutions=sensitivity_solutions,
            )
            plot_net_transfers_figure(
                sites=sites,
                delta=args.sensitivity_delta,
                outputs_root=args.outputs_root,
                sensitivity_solutions=sensitivity_solutions,
            )
            base_solutions = base_solutions_for_figures[sites][2]
            plot_zshare_delta_comparison_figure(
                sites=sites,
                base_delta=args.base_delta,
                sensitivity_delta=args.sensitivity_delta,
                outputs_root=args.outputs_root,
                zbar=zbar,
                years=args.years,
                base_solutions=base_solutions,
                sensitivity_solutions=sensitivity_solutions,
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.trajectories_out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(args.out, index=False)
    pd.DataFrame(all_trajectory_rows).to_csv(args.trajectories_out, index=False)
    write_latex_comparison_table(
        summary_path=args.out,
        trajectories_path=args.trajectories_out,
        table_path=args.table_out,
    )

    print(f"Wrote {len(summary_rows)} summary rows to {args.out}")
    print(f"Wrote {len(all_trajectory_rows)} trajectory rows to {args.trajectories_out}")
    print(f"Wrote sensitivity comparison table to {args.table_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
