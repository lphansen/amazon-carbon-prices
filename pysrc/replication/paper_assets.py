from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

from pysrc.services.file_service import get_path


DEFAULT_PAPER_TEX: Path | None = None
PAPER_FIGURE_INPUTS_FILE = get_path("replication", "paper_figure_inputs.csv")
INCLUDEGRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\{(?P<path>[^}]+)\}"
)
FIGURE_ENV_RE = re.compile(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", re.S)
FIGURE_INPUT_COLUMNS = [
    "figure_number",
    "exhibit",
    "paper_include_path",
    "source_basename",
]

# Final PDF names requested by the upload workflow; internal sources and PNGs keep their names.
PDF_UPLOAD_NAMES = {
    "Figure11_aggregate_percentage_Z_b0_pehmc_6.8_pedet_6.8_xi_1.0.pdf":
        "Figure11_agg_percentage_Z_b0_pehmc_6.8_pedet_6.8_xi_1.0.pdf",
    "Figure13_aggregate_percentage_Z_b0_pehmc_4.8_pedet_6.8_xi_1.0_same_ylim.pdf":
        "Figure13_aggpct_Z_b0_pehmc_4.8_pedet_6.8_xi_1.0_same_ylim.pdf",
    "Figure13_aggregate_percentage_Z_b15_pehmc_19.8_pedet_21.8_xi_1.0_same_ylim.pdf":
        "Figure13_aggpct_Z_b15_pehmc_19.8_pedet_21.8_xi_1.0_same_ylim.pdf",
    "Figure15_pred_zshare_delta_comparison_1043_sites_det_delta_0p03.pdf":
        "Figure15_pred_zshare_delta_comp_1043_sites_det_delta_0p03.pdf",
}


def paper_figure_format_name(filename: str, fmt: str) -> str:
    """Resolve a paper filename for a format, including the four PDF-only aliases."""
    original = next((old for old, new in PDF_UPLOAD_NAMES.items() if new == filename), filename)
    name = str(Path(original).with_suffix("." + fmt))
    return PDF_UPLOAD_NAMES.get(name, name)


def empty_figure_inputs() -> pd.DataFrame:
    return pd.DataFrame(columns=FIGURE_INPUT_COLUMNS)


def strip_latex_comments(text: str) -> str:
    text = re.sub(r"\\begin\{comment\}.*?\\end\{comment\}", "", text, flags=re.S)
    lines: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        out: list[str] = []
        escaped = False
        for char in line:
            if char == "%" and not escaped:
                break
            out.append(char)
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
        lines.append("".join(out))
    return "\n".join(lines)


def paper_figure_inputs(paper_tex: Path | None) -> pd.DataFrame:
    if paper_tex is None or not paper_tex.exists():
        return empty_figure_inputs()

    clean = strip_latex_comments(paper_tex.read_text(errors="ignore"))
    rows: list[dict[str, object]] = []
    figure_number = 0
    for match in FIGURE_ENV_RE.finditer(clean):
        body = match.group(2)
        includes = [item.group("path") for item in INCLUDEGRAPHICS_RE.finditer(body)]
        if not includes:
            continue
        figure_number += 1
        for include_path in includes:
            rows.append(
                {
                    "figure_number": figure_number,
                    "exhibit": f"Figure {figure_number}",
                    "paper_include_path": include_path,
                    "source_basename": Path(include_path).name,
                }
            )
    return pd.DataFrame(rows, columns=FIGURE_INPUT_COLUMNS)


def read_or_build_paper_figure_inputs(
    paper_tex: Path | None,
    cache_path: Path = PAPER_FIGURE_INPUTS_FILE,
) -> pd.DataFrame:
    if paper_tex is None or not paper_tex.exists():
        if not cache_path.exists():
            raise FileNotFoundError(
                f"Missing {cache_path}. The replication package expects this "
                "repo-internal figure list; pass --paper-tex only when intentionally "
                "refreshing it from a manuscript source."
            )
        return pd.read_csv(cache_path).fillna("")

    inputs = paper_figure_inputs(paper_tex)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    inputs.to_csv(cache_path, index=False, quoting=csv.QUOTE_MINIMAL)
    return inputs


def generated_figure_name_candidates(basename: str) -> list[str]:
    suffix = Path(basename).suffix
    png_basename = str(Path(basename).with_suffix(".png"))
    mpc_match = re.fullmatch(
        r"mpc_landallocation_b_(?P<b>\d+)_baseline_same_ylim\.png",
        png_basename,
    )
    if mpc_match:
        candidates = [basename]
        candidates.append(f"mpc_landallocation_b_{mpc_match.group('b')}_adjust{suffix}")
    elif basename.startswith("aggregate_percentage_Z_") and basename.endswith(
        "_same_ylim" + suffix
    ):
        candidates = [basename, basename.replace("_same_ylim" + suffix, suffix)]
    else:
        candidates = [basename]
        if basename.endswith("_same_ylim" + suffix):
            candidates.append(basename.replace("_same_ylim" + suffix, suffix))

    return list(dict.fromkeys(candidates))


def resolve_generated_figure(root: Path, basename: str) -> Path | None:
    matches: list[Path] = []
    for candidate in generated_figure_name_candidates(basename):
        for folder in [root / "output", root / "plots"]:
            if folder.exists():
                matches.extend(
                    path
                    for path in folder.rglob(candidate)
                    if path.is_file() and not path.name.startswith("._")
                )
        if matches:
            return sorted(matches, key=lambda path: str(path.relative_to(root)))[0]
    return None
