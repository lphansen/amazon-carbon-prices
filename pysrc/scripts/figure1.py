from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import NullLocator

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pysrc.services.file_service import get_path
from pysrc.analysis.publication import save_publication_figure


YEAR = "2018"
AMAZON_GDP_PC_PPP_2018 = 9968.0
AMAZON_EMISSIONS_PC_2018 = 40.6
HIGHLIGHTS = {
    "CHN": "C",
    "IND": "I",
    "EUU": "E",
    "USA": "U",
}


def one_match(pattern: Path) -> Path:
    matches = sorted(glob.glob(str(pattern)))
    if not matches:
        raise FileNotFoundError(f"No file matched: {pattern}")
    return Path(matches[0])


def read_wdi_csv(path: Path, value_name: str) -> pd.DataFrame:
    raw = pd.read_csv(path, skiprows=4)
    out = raw[["Country Name", "Country Code", YEAR]].copy()
    out = out.rename(columns={YEAR: value_name})
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    return out


def build_plot_data(input_dir: Path, documentation_dir: Path) -> pd.DataFrame:
    gdp_file = one_match(input_dir / "API_NY.GDP.PCAP.PP.CD*.csv")
    co2_file = one_match(input_dir / "API_EN.ATM.CO2E.PC*.csv")
    metadata_file = one_match(
        documentation_dir / "Metadata_Country_API_NY.GDP.PCAP.PP.CD*.csv"
    )

    gdp = read_wdi_csv(gdp_file, "gdp_pc_ppp_2018")
    co2 = read_wdi_csv(co2_file, "emissions_pc_2018")
    meta = pd.read_csv(metadata_file)[["Country Code", "Region"]]

    df = gdp.merge(
        co2[["Country Code", "emissions_pc_2018"]],
        on="Country Code",
        how="inner",
    )
    df = df.merge(meta, on="Country Code", how="left")

    is_country_or_territory = (
        df["Region"].notna() & (df["Region"].astype(str).str.len() > 0)
    )
    is_eu = df["Country Code"].eq("EUU")
    df = df.loc[is_country_or_territory | is_eu].copy()

    df = df[(df["gdp_pc_ppp_2018"] > 0) & (df["emissions_pc_2018"] > 0)].copy()
    df["gdp_pc_ppp_2018_100k"] = df["gdp_pc_ppp_2018"] / 100000.0
    df["plot_group"] = "World Bank country/territory or EU"

    amazon = pd.DataFrame(
        [
            {
                "Country Name": "Brazilian Amazon",
                "Country Code": "AMAZON",
                "gdp_pc_ppp_2018": AMAZON_GDP_PC_PPP_2018,
                "emissions_pc_2018": AMAZON_EMISSIONS_PC_2018,
                "Region": "Brazilian Amazon",
                "gdp_pc_ppp_2018_100k": AMAZON_GDP_PC_PPP_2018 / 100000.0,
                "plot_group": "Brazilian Amazon",
            }
        ]
    )
    return pd.concat([df, amazon], ignore_index=True)


def make_figure(plot_data: pd.DataFrame, output_png: Path, output_pdf: Path) -> list[Path]:
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    df = plot_data[plot_data["Country Code"].ne("AMAZON")].copy()
    amazon = plot_data[plot_data["Country Code"].eq("AMAZON")].iloc[0]

    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.scatter(
        df["gdp_pc_ppp_2018_100k"],
        df["emissions_pc_2018"],
        s=13,
        c="0.4",
        edgecolors="none",
        zorder=1,
    )

    for code, label in HIGHLIGHTS.items():
        row = df[df["Country Code"].eq(code)].iloc[0]
        x = row["gdp_pc_ppp_2018_100k"]
        y = row["emissions_pc_2018"]
        ax.scatter([x], [y], s=40, facecolors="white", edgecolors="black", linewidths=1.4, zorder=3)
        ax.annotate(
            label,
            xy=(x, y),
            xytext=(6, 0),
            textcoords="offset points",
            color="black",
            fontsize=12,
            fontweight="bold",
            ha="left",
            va="center",
            zorder=4,
        )

    ax.scatter(
        [amazon["gdp_pc_ppp_2018_100k"]],
        [amazon["emissions_pc_2018"]],
        s=35,
        marker="^",
        c="#007A55",
        edgecolors="none",
        zorder=3,
    )
    ax.text(
        amazon["gdp_pc_ppp_2018_100k"] * 1.035,
        amazon["emissions_pc_2018"],
        "Amazon",
        color="#007A55",
        fontsize=10,
        fontweight="bold",
        ha="left",
        va="center",
        zorder=4,
    )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.006, 1.6)
    ax.set_ylim(0.02, 60)

    ax.set_xticks([0.01, 0.10, 1.00])
    ax.set_xticklabels(["0.01", "0.10", "1.00"])
    ax.set_yticks([0.1, 1.0, 10.0])
    ax.set_yticklabels(["0.1", "1.0", "10.0"])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())

    ax.set_xlabel(
        "GDP per capita PPP in 2018 (100,000 int. dollars, log scale)",
        fontsize=13,
    )
    ax.set_ylabel(
        "Emission per capita in 2018\n(metric tons CO2e, log scale)",
        fontsize=13,
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", which="major", labelsize=10, length=3, width=0.8)

    fig.subplots_adjust(left=0.14, bottom=0.14, right=0.98, top=0.96)
    written = save_publication_figure(fig, output_pdf, dpi=1200)
    plt.close(fig)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce Figure 1 from repo-internal World Bank inputs."
    )
    parser.add_argument("--input-dir", type=Path, default=get_path("replication", "figure1", "input"))
    parser.add_argument(
        "--documentation-dir",
        type=Path,
        default=get_path("replication", "figure1", "documentation"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=get_path("output", "figures"),
    )
    parser.add_argument(
        "--source-data-out",
        type=Path,
        default=get_path("replication", "derived", "figure1_source_data.csv"),
    )
    parser.add_argument("--plot-only", action="store_true",
                        help="Redraw from the saved Figure 1 source-data CSV.")
    args = parser.parse_args()

    if args.plot_only:
        plot_data = pd.read_csv(args.source_data_out)
    else:
        plot_data = build_plot_data(args.input_dir, args.documentation_dir)
        args.source_data_out.parent.mkdir(parents=True, exist_ok=True)
        plot_data.to_csv(args.source_data_out, index=False)

    output_png = args.output_dir / "scatter_emission_gdp_log.png"
    output_pdf = args.output_dir / "scatter_emission_gdp_log.pdf"
    written = make_figure(plot_data, output_png, output_pdf)

    for path in written:
        print(f"Wrote: {path}")
    if not args.plot_only:
        print(f"Wrote: {args.source_data_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
