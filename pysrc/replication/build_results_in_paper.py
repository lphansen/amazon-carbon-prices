from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pysrc.replication.paper_assets import (
    DEFAULT_PAPER_TEX,
    PAPER_FIGURE_INPUTS_FILE,
    paper_figure_format_name,
    read_or_build_paper_figure_inputs,
    resolve_generated_figure,
)
from pysrc.replication.parameters import CARBON_PRICE_FILE, normalize_xi
from pysrc.services.file_service import get_path


MPC_PROBABILITY_FILE = get_path(
    "replication", "derived", "mpc_transition_probabilities.csv"
)
RESULTS_IN_PAPER_TABLE_REFERENCE_DIR = get_path("replication", "results_in_paper_table_templates")
NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
VALUE_COLUMNS = [
    "agricultural output value",
    "net transfers",
    "forest services",
    "adjustment costs",
    "planner value",
]
XI_ORDER = ["inf", "1", "0.5"]
XI_LABELS = {
    "inf": r"$\infty$",
    "1": "1",
    "0.5": "0.5",
}
XI_MATH_LABELS = {
    "inf": r"\infty",
    "1": "1",
    "0.5": "0.5",
}
COEFFICIENT_LABELS = {
    "theta": [
        r"$\beta_0^{\theta}$",
        r"$\beta_1^{\theta}$",
        r"$\beta_2^{\theta}$",
        r"$\beta_3^{\theta}$",
        r"$\beta_4^{\theta}$",
        r"$\beta_5^{\theta}$",
        r"$\beta_6^{\theta}$",
        r"$\beta_7^{\theta}$",
    ],
    "gamma": [
        r"$\beta_0^{\gamma}$",
        r"$\beta_1^{\gamma}$",
        r"$\beta_2^{\gamma}$",
        r"$\beta_3^{\gamma}$",
        r"$\beta_4^{\gamma}$",
        r"$\beta_5^{\gamma}$",
    ],
}
SIGMA_LABELS = [
    r"$\sigma_{\eta}^{\gamma}$",
    r"$\sigma_{\zeta}^{\gamma}$",
    r"$\sigma_{\eta}^{\theta}$",
    r"$\sigma_{\zeta}^{\theta}$",
]
TABLE_NUMBERS = {
    "Shadowprice.tex": 1,
    "pvd_det_1043.tex": 2,
    "transfersCost_1043Sites_det.tex": 3,
    "valueObjectiveDecomposition_1043Sites_hmc.tex": 4,
    "Shadowprice_mpc.tex": 5,
    "present_value_mpc_b0_sites78.tex": 6,
    "transition_prob_b0_y5.tex": 7,
    "present_value_mpc_b15_sites78.tex": 8,
    "transition_prob_b15_y5.tex": 9,
    "hmm_results_table.tex": 10,
    "information_criterion.tex": 11,
    "present_value_mpc_constrained_sites78.tex": 12,
    "valueObjectiveDecomposition_78Sites_det.tex": 13,
    "transfersCost_1043Sites_hmc_y15.tex": 14,
    "transfersCost_1043Sites_hmc_y30.tex": 15,
    "valueObjectiveDecomposition_1043Sites_hmc_xi2.tex": 16,
    "valueObjectiveDecomposition_1043Sites_hmc_xi0_5.tex": 17,
    "value_decomp_comparison.tex": 18,
    "present_value_mpc_b10_sites78.tex": 19,
    "transition_prob_b10_y5.tex": 20,
    "present_value_mpc_b25_sites78.tex": 21,
    "transition_prob_b25_y5.tex": 22,
    "theta_coefficient.tex": 23,
    "gamma_coefficient.tex": 24,
    "sigma_quantiles.tex": 25,
}


def _data_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in path.read_text(errors="ignore").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("%") or "&" not in clean:
            continue
        if clean.startswith("\\"):
            continue
        clean = re.sub(r"\\\\.*$", "", clean).strip()
        rows.append([cell.strip().strip("{}") for cell in clean.split("&")])
    return rows


def _number(value: object) -> float:
    text = str(value).replace(",", "")
    if text.lower() == "nan":
        return math.nan
    match = re.search(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", text)
    if match is None:
        raise ValueError(f"Could not parse a numeric value from `{value}`")
    return float(match.group(0))


def _single_row_values(path: Path) -> dict[str, float]:
    rows = _data_rows(path)
    if not rows:
        raise ValueError(f"No data rows found in {path}")
    cells = rows[-1]
    values = [_number(cell) for cell in cells[1 : 1 + len(VALUE_COLUMNS)]]
    return dict(zip(VALUE_COLUMNS, values))


def _table_rows(path: Path) -> list[list[float]]:
    rows = []
    for cells in _data_rows(path):
        try:
            rows.append([_number(cell) for cell in cells])
        except ValueError:
            continue
    return rows


def _fmt0(value: float, scale: float = 1.0, absolute: bool = False) -> str:
    if absolute:
        value = abs(value)
    rounded = Decimal(str(value * scale)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return str(rounded)


def _fmt1(value: float, scale: float = 1.0) -> str:
    if math.isnan(value):
        return "-"
    return f"{value * scale:.1f}"


def _fmt_price(value: float) -> str:
    return f"{value:.1f}"


def _fmt_prob(value: float) -> str:
    return f"{value:.2f}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def _generated_table_name(name: str) -> str:
    table_number = TABLE_NUMBERS.get(name)
    if table_number is None:
        raise KeyError(f"No manuscript table number is registered for {name}")
    return f"Table{table_number}_{name}"


def _generated_figure_name(figure: str, source: Path) -> str:
    figure_number = int(figure.removeprefix("Figure ").strip())
    return paper_figure_format_name(f"Figure{figure_number}_{source.name}", source.suffix[1:])


def _active_numeric_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    if not path.exists():
        return rows
    for line in path.read_text(errors="ignore").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("%") or clean.startswith("\\") or "&" not in clean:
            continue
        if clean.endswith(r"\\"):
            clean = clean[:-2].strip()
        rows.append([match.group(0) for match in NUMBER_RE.finditer(clean)])
    return rows


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _numeric_diff_note(reference: Path, generated: Path) -> str:
    original_rows = _active_numeric_rows(reference)
    generated_rows = _active_numeric_rows(generated)
    if original_rows == generated_rows:
        return ""
    return f"old={original_rows}; new={generated_rows}"


def _ensure_table_reference(
    root: Path,
    results_dir: Path,
    reference_dir: Path,
    name: str,
    generated: Path,
    *,
    update_reference: bool = False,
) -> tuple[Path, bool, str]:
    reference = reference_dir / name
    unprefixed_result = results_dir / name

    if reference.exists():
        return reference, True, "cached_reference"

    if update_reference:
        if unprefixed_result.exists():
            reference.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(unprefixed_result, reference)
            return reference, True, "unprefixed_results_in_paper"

        if generated.exists():
            reference.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated, reference)
            return reference, True, "bootstrapped_from_generated"

    return reference, False, "missing_reference"


def _copy_results_in_paper_figures(
    root: Path,
    results_dir: Path,
    paper_tex: Path,
    figure_inputs_out: Path,
    formats: tuple[str, ...] = ("png", "pdf"),
) -> pd.DataFrame:
    figure_inputs = read_or_build_paper_figure_inputs(paper_tex, figure_inputs_out)

    rows: list[dict[str, object]] = []
    for record in figure_inputs.to_dict("records"):
        basename = str(record["source_basename"])
        for fmt in formats:
            source = resolve_generated_figure(root, str(Path(basename).with_suffix("." + fmt)))
            exhibit = str(record["exhibit"])
            target = results_dir / _generated_figure_name(
                exhibit, Path(basename).with_suffix("." + fmt),
            )
            copied = source is not None
            if copied:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            rows.append({
                "figure_number": record["figure_number"],
                "exhibit": exhibit,
                "paper_include_path": record["paper_include_path"],
                "source_file": str(source.relative_to(root)) if copied else "",
                "generated_file": str(target.relative_to(root)),
                "copied": copied,
                "format": fmt,
            })
    return pd.DataFrame(rows)


def _clean_results_dir(results_dir: Path, keep: set[Path]) -> list[Path]:
    removed: list[Path] = []
    if not results_dir.exists():
        return removed
    resolved_keep = {path.resolve() for path in keep}
    for path in sorted(results_dir.iterdir()):
        if path.resolve() in resolved_keep:
            continue
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed.append(path)
    return removed


def _carbon_price(
    prices: pd.DataFrame,
    *,
    context: str,
    model: str,
    sites: int,
    xi: str,
    price_model: str | None = None,
) -> float:
    xi = normalize_xi(xi)
    mask = (
        (prices["context"] == context)
        & (prices["model"] == model)
        & (prices["sites"] == sites)
        & (prices["xi"].map(normalize_xi) == xi)
    )
    if price_model is not None and "price_model" in prices:
        mask &= prices["price_model"].fillna("") == price_model
    matches = prices[mask]
    if matches.empty:
        raise ValueError(
            "Missing carbon price for "
            f"context={context}, model={model}, sites={sites}, xi={xi}"
        )
    return float(matches.iloc[0]["pee"])


def _mpc_output_path(
    root: Path,
    *,
    b: int,
    xi: str,
    model: str,
    day0: bool,
) -> Path:
    xi_label = "10000.0" if normalize_xi(xi) == "inf" else f"{float(xi):.1f}"
    prefix = "day0_present_value" if day0 else "present_value"
    pattern = f"{prefix}_mpc_b{b}_sites78_xi_{xi_label}_pee_*_{model}.tex"
    matches = sorted((root / "output" / "mpc").glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No MPC table found for pattern {pattern}")
    return matches[-1]


def _present_value_row(
    root: Path,
    *,
    b: int,
    xi: str,
    model: str,
    day0: bool,
) -> tuple[dict[str, float], Path]:
    path = _mpc_output_path(root, b=b, xi=xi, model=model, day0=day0)
    return _single_row_values(path), path


def render_shadow_price(prices: pd.DataFrame) -> str:
    rows = [
        (r"$\infty$", _carbon_price(prices, context="parameter_ambiguity", model="det", sites=1043, xi="inf")),
        ("2", _carbon_price(prices, context="parameter_ambiguity", model="hmc", sites=1043, xi="2")),
        ("1", _carbon_price(prices, context="parameter_ambiguity", model="hmc", sites=1043, xi="1")),
        ("0.5", _carbon_price(prices, context="parameter_ambiguity", model="hmc", sites=1043, xi="0.5")),
    ]
    lines = [
        r"\begin{tabular}{cccc}",
        r"\hline",
        r" ambiguity aversion ($\xi$) &  carbon price ($P^{ee}$)\\",
        r"\hline",
    ]
    lines.extend(f" {label} & {_fmt_price(price)} \\\\" for label, price in rows)
    lines.extend([r"\hline", r"\end{tabular}"])
    return "\n".join(lines)


def render_shadow_price_mpc(prices: pd.DataFrame) -> str:
    rows = [
        (r"$\infty$", "inf"),
        ("1", "1"),
        ("0.5", "0.5"),
    ]
    lines = [
        r"\begin{tabular}{ccc}",
        r"\hline",
        r"\rule{0pt}{1.2em}",
        r" $\widehat \xi$ &  carbon price ($P^{ee}$)\\",
        r"\hline",
        "",
    ]
    for label, xi in rows:
        price = _carbon_price(
            prices,
            context="price_stochasticity",
            model="unconstrained",
            sites=78,
            xi=xi,
            price_model="distinct_variance",
        )
        lines.append(f"  {label} & {_fmt_price(price)} \\\\")
    lines.extend(["", r"\hline", r"\end{tabular}"])
    return "\n".join(lines)


def render_det_value(rows: list[list[float]], *, include_sites_78_header_case: bool = False) -> str:
    ag = "Agricultural" if include_sites_78_header_case else "agricultural"
    net = "Net" if include_sites_78_header_case else "net"
    forest = "Forest" if include_sites_78_header_case else "forest"
    adjustment = "Adjustment" if include_sites_78_header_case else "adjustment"
    planner = "Planner" if include_sites_78_header_case else "planner"
    lines = [
        r"\begin{tabular}{ccccccc}",
        r"\toprule",
        rf"\makecell[c]{{$P^e$ \\ $(\$)$}} & \makecell[c]{{$b$ \\ $(\$)$}} & \makecell[c]{{{ag} \\ output value \\ ($\$$ billion)}} & \makecell[c]{{{net} \\ transfers \\ ($\$$ billion)}} & \makecell[c]{{{forest} \\ services \\ ($\$$ billion)}} & \makecell[c]{{{adjustment} \\ costs \\ ($\$$ billion)}} & \makecell[c]{{{planner} \\ value \\ ($\$$ billion)}} \\",
        r"\midrule",
    ]
    for row in rows:
        _, pe, b, ao, nt, fs, ac, pv = row
        lines.append(
            f" {_fmt_price(pe)} & {_fmt0(b)} & {_fmt0(ao, 100)} & "
            f"{_fmt0(nt, 100)} & {_fmt0(fs, 100)} & {_fmt0(ac, 100)} & "
            f"{_fmt0(pv, 100)} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines)


def render_transfer_det(rows15: list[list[float]], rows30: list[list[float]]) -> str:
    lines = [
        r"\begin{tabular}{cccccccc}",
        r"\toprule",
        r"&& \multicolumn{3}{c}{15 years} & \multicolumn{3}{c}{30 years} \\",
        r"\cmidrule[1pt](r){3-5} \cmidrule[1pt](r){6-8}",
        r"\makecell[c]{$P^e$ \\ (\$)} & \makecell[c]{$b$ \\ (\$)} & \makecell[c]{net captured \\ emissions \\ (CO$_2$e Gt)} & \makecell[c]{discounted \\ net transfers \\  (\$ billion)} & \makecell[c]{  effective cost \\ (\$ per ton \\ of CO$_2$e)} & \makecell[c]{net captured \\ emissions \\ (CO$_2$e Gt)} & \makecell[c]{discounted \\ net transfers \\ (\$ billion)} & \makecell[c]{  effective cost \\ (\$ per ton \\ of CO$_2$e)} \\",
        r"\midrule",
        "",
    ]
    for row15, row30 in zip(rows15, rows30):
        pe, b, nce15, nt15, ec15 = row15
        _, _, nce30, nt30, ec30 = row30
        lines.append(
            f"{_fmt_price(pe)} & {_fmt0(b)} & {_fmt1(nce15)} & "
            f"{_fmt0(nt15, 100)} & {_fmt1(ec15)} & {_fmt1(nce30)} & "
            f"{_fmt0(nt30, 100)} & {_fmt1(ec30)} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines)


def render_transfer_hmc(rows_det: list[list[float]], rows_hmc: list[list[float]]) -> str:
    lines = [
        "",
        r"\begin{tabular}[t]{ccccccc}",
        r"\toprule",
        "",
        r"& \multicolumn{3}{c}{ambiguity neutral} & \multicolumn{3}{c}{ambiguity aversion} \\",
        r"\cmidrule[1pt](r){2-4} \cmidrule[1pt](r){5-7} ",
        r"\makecell[c]{$b$ \\ (\$)} & \makecell[c]{net captured \\ emissions \\ (CO$_2$e Gt)} & \makecell[c]{discounted \\ net transfers \\  (\$ billion)} & \makecell[c]{  effective cost \\ (\$ per ton \\ of CO$_2$e)} & \makecell[c]{net captured \\ emissions \\ (CO$_2$e Gt)} & \makecell[c]{discounted \\ net transfers \\ (\$ billion)} & \makecell[c]{  effective cost \\ (\$ per ton \\ of CO$_2$e)} \\",
        r"\midrule",
        "",
        "",
    ]
    for det, hmc in zip(rows_det, rows_hmc):
        _, b, nce_det, nt_det, ec_det = det
        _, _, nce_hmc, nt_hmc, ec_hmc = hmc
        lines.append(
            f"{_fmt0(b)} & {_fmt1(nce_det)} & {_fmt0(nt_det, 100)} & "
            f"{_fmt1(ec_det)} & {_fmt1(nce_hmc)} & {_fmt0(nt_hmc, 100)} & "
            f"{_fmt1(ec_hmc)} \\\\"
        )
    lines.extend(["", r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines)


def render_ambiguity_decomp(rows: list[list[float]]) -> str:
    lines = [
        r"\begin{tabular}[t]{ccccccc}",
        r"\toprule",
        r"& \multicolumn{3}{c}{ \makecell[c]{agricultural output value  ($\$$ billion) }} & \multicolumn{3}{c}{\makecell[c]{planner value ($\$$ billion) }} \\",
        r"\cmidrule[1pt](r){2-4} \cmidrule[1pt](r){5-7} ",
        "",
        r"\makecell[c]{$b$ \\ $(\$)$} &\makecell[c]{ambiguity \\ neutral } & \makecell[c]{ambiguity \\ aversion } &  \makecell[c]{percent \\ change} &\makecell[c]{ambiguity \\ neutral }&\makecell[c]{ambiguity \\ aversion }  & \makecell[c]{percent \\ change}\\",
        r"\midrule",
    ]
    for row in rows:
        b, ao_det, ao_hmc, change_ao, pv_det, pv_hmc, change_pv = row
        lines.append(
            f"{_fmt0(b)} & {_fmt0(ao_det, 100)} & {_fmt0(ao_hmc, 100)} & "
            f"{_fmt0(change_ao)} & {_fmt0(pv_det, 100)} & {_fmt0(pv_hmc, 100)} & "
            f"{_fmt0(change_pv)} \\\\"
        )
    lines.extend(["", r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines)


def render_mpc_value(root: Path, b: int) -> tuple[str, list[Path]]:
    cols = "lcccc" if b == 0 else "lccccc"
    has_net = b != 0
    source_paths: list[Path] = []
    lines = [
        "",
        rf"\begin{{tabular}}{{{cols}}}",
        r"\toprule",
    ]
    if has_net:
        lines.append(
            r" &\makecell[c]{agricultural \\ output value \\ ($\$$ billion)} & \makecell[c]{net \\ transfers \\ (\$ billion)} & \makecell[c]{forest \\ services \\ (\$ billion)} & \makecell[c]{adjustment \\ costs \\ (\$ billion)} & \makecell[c]{planner \\ value \\ (\$ billion)} \\"
        )
    else:
        lines.append(
            r" &\makecell[c]{agricultural \\ output value \\ ($\$$ billion)} & \makecell[c]{forest \\ services \\ (\$ billion)} & \makecell[c]{adjustment \\ costs \\ (\$ billion)} & \makecell[c]{planner \\ value \\ (\$ billion)} \\"
        )
    lines.append(r"\midrule")
    for xi in XI_ORDER:
        values, path = _present_value_row(
            root, b=b, xi=xi, model="unconstrained", day0=True
        )
        source_paths.append(path)
        label = (
            rf"$\hspace{{.5cm}} \widehat \xi = {XI_MATH_LABELS[xi]}$"
            if b in {0, 15}
            else rf"$\widehat \xi = {XI_MATH_LABELS[xi]}$"
        )
        if has_net:
            line = (
                f"{label} & {_fmt0(values['agricultural output value'])} & "
                f"{_fmt0(values['net transfers'])} & {_fmt0(values['forest services'])} & "
                f"{_fmt0(values['adjustment costs'], absolute=True)} & "
                f"{_fmt0(values['planner value'])} \\\\"
            )
        else:
            line = (
                f"{label} & {_fmt0(values['agricultural output value'])} & "
                f"{_fmt0(values['forest services'])} & "
                f"{_fmt0(values['adjustment costs'], absolute=True)} & "
                f"{_fmt0(values['planner value'])} \\\\"
            )
        lines.append(line)
    lines.extend(["", r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines), source_paths


def render_mpc_constrained(root: Path) -> tuple[str, list[Path]]:
    source_paths: list[Path] = []
    lines = [
        "",
        "",
        r"\begin{tabular}{lccccc}",
        "",
        r"\toprule",
        "",
        r" &\makecell[c]{agricultural \\ output value \\ ($\$$ billion)} & \makecell[c]{net \\ transfers \\ (\$ billion)} & \makecell[c]{forest \\ services \\ (\$ billion)} & \makecell[c]{adjustment \\ costs \\ (\$ billion)} & \makecell[c]{planner \\ value \\ (\$ billion)} \\",
        r"\midrule",
        "",
    ]
    for b in [0, 10, 15, 20, 25]:
        lines.append(rf"\multicolumn{{6}}{{l}}{{ \hspace{{3.8 mm}} b = {b}}}  \\  ")
        lines.append(" ")
        for xi in XI_ORDER:
            values, path = _present_value_row(
                root, b=b, xi=xi, model="constrained", day0=True
            )
            source_paths.append(path)
            lines.append(
                rf"$\hspace{{.5cm}} \widehat \xi = {XI_MATH_LABELS[xi]}$ & "
                f"{_fmt0(values['agricultural output value'])} & "
                f"{_fmt0(values['net transfers'])} & "
                f"{_fmt0(values['forest services'])} & "
                f"{_fmt0(values['adjustment costs'], absolute=True)} & "
                f"{_fmt0(values['planner value'])} \\\\"
            )
        lines.append("")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines), source_paths


def render_transition_probabilities(
    probabilities: pd.DataFrame,
    *,
    b: int,
) -> str:
    lines = [
        r"\begin{tabular}{ccc}",
        r"\hline",
        r"\rule{0pt}{1.2em}",
        r"$\widehat \xi$  &Prob from low to low& Prob from high to high \\",
        r"\hline",
    ]
    for xi in XI_ORDER:
        row = probabilities[
            (probabilities["model"] == "unconstrained")
            & (probabilities["xi"].map(normalize_xi) == xi)
            & (probabilities["b"].round().astype(int) == b)
        ]
        if row.empty:
            raise ValueError(f"Missing transition probability for b={b}, xi={xi}")
        record = row.iloc[0]
        lines.append(
            f"{XI_LABELS[xi]} &  {_fmt_prob(record['prob_from_low_to_low'])} "
            f"& {_fmt_prob(record['prob_from_high_to_high'])} \\\\"
        )
    lines.extend(["", "", r"\hline", r"\end{tabular}"])
    return "\n".join(lines)


def render_value_decomp_comparison(root: Path) -> tuple[str, list[Path]]:
    source_paths: list[Path] = []
    lines = [
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"$\hspace{.5cm} \widehat \xi = \infty$ &\makecell[c]{agricultural \\ output value \\ ($\$$ billion)} & \makecell[c]{net \\ transfers \\ (\$ billion)} & \makecell[c]{forest \\ services \\ (\$ billion)} & \makecell[c]{adjustment \\ costs \\ (\$ billion)} & \makecell[c]{planner \\ value \\ (\$ billion)} \\",
        r"\midrule",
        "",
    ]
    for b in [0, 10, 15, 25]:
        initial, initial_path = _present_value_row(
            root, b=b, xi="inf", model="unconstrained", day0=True
        )
        simulation, simulation_path = _present_value_row(
            root, b=b, xi="inf", model="unconstrained", day0=False
        )
        source_paths.extend([initial_path, simulation_path])
        lines.extend(
            [
                rf"$b={b}$ & & & & & \\",
                (
                    r"\quad initial period solution & "
                    f"{_fmt0(initial['agricultural output value'])} & "
                    f"{_fmt0(initial['net transfers'])} & "
                    f"{_fmt0(initial['forest services'])} & "
                    f"{_fmt0(initial['adjustment costs'], absolute=True)} & "
                    f"{_fmt0(initial['planner value'])} \\\\"
                ),
                (
                    r"\quad simulation      & "
                    f"{_fmt0(simulation['agricultural output value'], 100)} & "
                    f"{_fmt0(simulation['net transfers'], 100)} & "
                    f"{_fmt0(simulation['forest services'], 100)} & "
                    f"{_fmt0(simulation['adjustment costs'], 100, absolute=True)} & "
                    f"{_fmt0(simulation['planner value'], 100)} \\\\"
                ),
                "",
                r"\addlinespace[1.2em]" if b != 25 else "",
            ]
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(line for line in lines if line != "\n"), source_paths


def render_coefficient_table(path: Path, kind: str) -> str:
    data = pd.read_csv(path)
    labels = COEFFICIENT_LABELS[kind]
    lines = [
        rf"\begin{{tabular}}{{{'c' * (len(labels) + 1)}}}",
        r"\hline",
        " & " + " & ".join(labels) + r" \\",
        r"\hline",
    ]
    for label, column in [
        ("10\\%", "10th_percentile"),
        ("50\\%", "50th_percentile"),
        ("90\\%", "90th_percentile"),
    ]:
        values = [f"{value:.3f}" for value in data[column].tolist()]
        lines.append(f"{label} & " + " & ".join(values) + r" \\")
    lines.extend([r"\hline", r"\end{tabular}"])
    return "\n".join(lines)


def render_sigma_table(path: Path) -> str:
    data = pd.read_csv(path).iloc[0]
    columns = [
        ["gamma_sigma_u_10th", "gamma_sigma_v_10th", "theta_sigma_u_10th", "theta_sigma_v_10th"],
        ["gamma_sigma_u_50th", "gamma_sigma_v_50th", "theta_sigma_u_50th", "theta_sigma_v_50th"],
        ["gamma_sigma_u_90th", "gamma_sigma_v_90th", "theta_sigma_u_90th", "theta_sigma_v_90th"],
    ]
    lines = [
        r"\begin{tabular}{ccccc}",
        r"\hline",
        " & " + " & ".join(SIGMA_LABELS) + r" \\",
        r"\hline",
    ]
    for label, cols in zip(["10\\%", "50\\%", "90\\%"], columns):
        values = [f"{float(data[col]):.3f}" for col in cols]
        lines.append(f"{label} & " + " & ".join(values) + r" \\")
    lines.extend([r"\hline", r"\end{tabular}"])
    return "\n".join(lines)


def build_tables(
    root: Path,
    results_dir: Path,
    reference_dir: Path,
    *,
    update_table_references: bool = False,
) -> pd.DataFrame:
    prices = pd.read_csv(CARBON_PRICE_FILE)
    prices["xi"] = prices["xi"].map(normalize_xi)
    probabilities = pd.read_csv(MPC_PROBABILITY_FILE)
    probabilities["xi"] = probabilities["xi"].map(normalize_xi)

    outputs: list[dict[str, str]] = []

    def write(name: str, text: str, sources: list[Path] | None = None) -> None:
        table_number = TABLE_NUMBERS[name]
        out = results_dir / _generated_table_name(name)
        _write(out, text)
        reference, reference_exists, reference_source = _ensure_table_reference(
            root,
            results_dir,
            reference_dir,
            name,
            out,
            update_reference=update_table_references,
        )
        numeric_note = (
            _numeric_diff_note(reference, out)
            if reference_exists
            else "no results_in_paper table reference available"
        )
        used_reference_format = reference_exists and numeric_note == ""
        if used_reference_format:
            out.write_text(reference.read_text(errors="ignore"))
        exact_match = (
            reference_exists
            and reference.read_text(errors="ignore") == out.read_text(errors="ignore")
        )
        outputs.append(
            {
                "table_number": table_number,
                "reference_file": _rel(reference, root),
                "generated_file": _rel(out, root),
                "reference_exists": reference_exists,
                "exact_file_match": exact_match,
                "active_numeric_match": reference_exists and numeric_note == "",
                "format_source": reference_source if used_reference_format else "rendered_from_outputs",
                "numeric_diff_note": numeric_note,
                "source_files": "|".join(
                    _rel(path, root) for path in (sources or [])
                ),
            }
        )

    write("Shadowprice.tex", render_shadow_price(prices), [CARBON_PRICE_FILE])
    write("Shadowprice_mpc.tex", render_shadow_price_mpc(prices), [CARBON_PRICE_FILE])

    pvd_1043 = root / "output" / "tables" / "present_value_site1043_pa41.11_det.tex"
    write("pvd_det_1043.tex", render_det_value(_table_rows(pvd_1043)), [pvd_1043])
    pvd_78 = root / "output" / "tables" / "present_value_site78_pa41.11_det.tex"
    write(
        "valueObjectiveDecomposition_78Sites_det.tex",
        render_det_value(_table_rows(pvd_78), include_sites_78_header_case=True),
        [pvd_78],
    )

    transfer15_det = root / "output" / "tables" / "transfer_cost_1043site_41.11pa_15year_det.tex"
    transfer30_det = root / "output" / "tables" / "transfer_cost_1043site_41.11pa_30year_det.tex"
    write(
        "transfersCost_1043Sites_det.tex",
        render_transfer_det(_table_rows(transfer15_det), _table_rows(transfer30_det)),
        [transfer15_det, transfer30_det],
    )

    for year in [15, 30]:
        det = root / "output" / "tables" / f"transfer_cost_1043site_41.11pa_{year}year_det.tex"
        hmc = root / "output" / "tables" / f"transfer_cost_1043site_41.11pa_{year}year_hmc_xi_1.0.tex"
        write(
            f"transfersCost_1043Sites_hmc_y{year}.tex",
            render_transfer_hmc(_table_rows(det), _table_rows(hmc)),
            [det, hmc],
        )

    ambiguity_specs = [
        ("1.0", "valueObjectiveDecomposition_1043Sites_hmc.tex"),
        ("2.0", "valueObjectiveDecomposition_1043Sites_hmc_xi2.tex"),
        ("0.5", "valueObjectiveDecomposition_1043Sites_hmc_xi0_5.tex"),
    ]
    for xi, name in ambiguity_specs:
        source = root / "output" / "tables" / f"present_value_site_ambiguity_comparison_xi_{xi}.tex"
        write(name, render_ambiguity_decomp(_table_rows(source)), [source])

    for b in [0, 10, 15, 25]:
        text, sources = render_mpc_value(root, b)
        write(f"present_value_mpc_b{b}_sites78.tex", text, sources)
        write(
            f"transition_prob_b{b}_y5.tex",
            render_transition_probabilities(
                probabilities, b=b
            ),
            [MPC_PROBABILITY_FILE],
        )

    comparison_text, comparison_sources = render_value_decomp_comparison(root)
    write("value_decomp_comparison.tex", comparison_text, comparison_sources)

    constrained_text, constrained_sources = render_mpc_constrained(root)
    write(
        "present_value_mpc_constrained_sites78.tex",
        constrained_text,
        constrained_sources,
    )

    for source, target in [
        (root / "output" / "tables" / "hmm_results_table.tex", "hmm_results_table.tex"),
        (
            root / "output" / "tables" / "hmm_information_criteria.tex",
            "information_criterion.tex",
        ),
    ]:
        write(target, source.read_text(errors="ignore"), [source])

    theta = root / "output" / "tables" / "theta_percentiles_1043.csv"
    gamma = root / "output" / "tables" / "gamma_percentiles_1043.csv"
    sigma = root / "output" / "tables" / "sigma_percentiles_1043.csv"
    write("theta_coefficient.tex", render_coefficient_table(theta, "theta"), [theta])
    write("gamma_coefficient.tex", render_coefficient_table(gamma, "gamma"), [gamma])
    write("sigma_quantiles.tex", render_sigma_table(sigma), [sigma])

    return pd.DataFrame(outputs).sort_values("table_number").reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build paper-formatted results_in_paper Table[number]_*.tex files and "
            "Figure[number]_* files from generated code outputs. "
            "This script never reads numeric values from the manuscript PDF."
        )
    )
    parser.add_argument("--root", type=Path, default=get_path())
    parser.add_argument("--results-dir", type=Path, default=get_path("results_in_paper"))
    parser.add_argument(
        "--table-reference-dir",
        type=Path,
        default=RESULTS_IN_PAPER_TABLE_REFERENCE_DIR,
        help=(
            "Stable paper-format table templates used read-only by default. "
            "This prevents the manifest from depending on unprefixed files "
            "that are cleaned from results_in_paper."
        ),
    )
    parser.add_argument(
        "--update-table-references",
        action="store_true",
        help=(
            "Maintenance mode: create missing files in --table-reference-dir "
            "from existing results_in_paper tables or newly generated tables. Normal "
            "replication runs leave the reference directory untouched."
        ),
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=get_path("replication", "results_in_paper_table_manifest.csv"),
    )
    parser.add_argument(
        "--paper-tex",
        type=Path,
        default=DEFAULT_PAPER_TEX,
        help=(
            "Optional manuscript TeX file for refreshing replication/paper_figure_inputs.csv. "
            "Normal replication uses the repo-internal cached CSV."
        ),
    )
    parser.add_argument(
        "--figure-inputs-out",
        type=Path,
        default=PAPER_FIGURE_INPUTS_FILE,
    )
    parser.add_argument(
        "--figure-manifest-out",
        type=Path,
        default=get_path("replication", "results_in_paper_figure_manifest.csv"),
    )
    parser.add_argument(
        "--keep-stale",
        action="store_true",
        help="Do not remove old files from results_in_paper after generating assets.",
    )
    parser.add_argument(
        "--figures-only",
        action="store_true",
        help=(
            "Only copy paper figures into results_in_paper/Figure[number]_* and write "
            "the figure manifest. Existing results_in_paper tables are left untouched."
        ),
    )
    parser.add_argument("--figure-formats", nargs="+", choices=["png", "pdf"],
                        default=["png", "pdf"],
                        help="Figure formats to collect. Use pdf to preserve existing PNGs.")
    args = parser.parse_args()

    if args.figures_only:
        figure_manifest = _copy_results_in_paper_figures(
            args.root,
            args.results_dir,
            args.paper_tex,
            args.figure_inputs_out,
            tuple(args.figure_formats),
        )
        copied_count = int(figure_manifest["copied"].sum()) if not figure_manifest.empty else 0
        if args.figure_manifest_out.exists():
            previous = pd.read_csv(args.figure_manifest_out).fillna("")
            previous["format"] = previous["generated_file"].map(lambda name: Path(name).suffix[1:])
            previous = previous[~previous["format"].isin(args.figure_formats)]
            figure_manifest = pd.concat([previous, figure_manifest], ignore_index=True)
        args.figure_manifest_out.parent.mkdir(parents=True, exist_ok=True)
        figure_manifest.to_csv(
            args.figure_manifest_out,
            index=False,
            quoting=csv.QUOTE_MINIMAL,
        )
        print(f"Copied {copied_count} results_in_paper figure files")
        print(f"Wrote results-in-paper figure manifest: {args.figure_manifest_out}")
        return 0

    manifest = build_tables(
        args.root,
        args.results_dir,
        args.table_reference_dir,
        update_table_references=args.update_table_references,
    )
    figure_manifest = _copy_results_in_paper_figures(
        args.root,
        args.results_dir,
        args.paper_tex,
        args.figure_inputs_out,
        tuple(args.figure_formats),
    )

    if not args.keep_stale:
        keep_paths = {
            args.root / path
            for path in manifest["generated_file"].tolist()
            + figure_manifest["generated_file"].tolist()
        }
        figure_paths = [args.root / path for path in figure_manifest["generated_file"]]
        for path in figure_paths:
            for fmt in {"png", "pdf"} - set(args.figure_formats):
                keep_paths.add(path.with_name(paper_figure_format_name(path.name, fmt)))
        removed = _clean_results_dir(args.results_dir, keep_paths)
    else:
        removed = []

    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.manifest_out, index=False, quoting=csv.QUOTE_MINIMAL)
    args.figure_manifest_out.parent.mkdir(parents=True, exist_ok=True)
    figure_manifest.to_csv(args.figure_manifest_out, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Wrote {len(manifest)} results_in_paper table-numbered tables")
    print(f"Copied {int(figure_manifest['copied'].sum()) if not figure_manifest.empty else 0} results_in_paper figure files")
    print(f"Removed {len(removed)} stale results_in_paper files")
    print(f"Wrote results-in-paper table manifest: {args.manifest_out}")
    print(f"Wrote results-in-paper figure manifest: {args.figure_manifest_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
