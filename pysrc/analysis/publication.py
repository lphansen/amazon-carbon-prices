"""Color figures with grayscale-readable styles and 1200 dpi raster export."""

import os
from pathlib import Path

import matplotlib as mpl


PUBLICATION_DPI = 1200
LINE_WIDTH = 3.2
BLUE = "#0072B2"
VERMILLION = "#D55E00"
GREEN = "#009E73"

TRANSFER_STYLES = {
    0: {"color": VERMILLION, "linestyle": "-"},
    15: {"color": GREEN, "linestyle": (0, (6, 3))},
    25: {"color": BLUE, "linestyle": "-."},
}
NEUTRAL_STYLE = {"color": VERMILLION, "linestyle": "-"}
AVERSE_STYLE = {"color": BLUE, "linestyle": (0, (6, 3))}


def shade_under_line(ax, line, *, alpha):
    """Fill below a density curve without fading or obscuring its outline."""
    x, y = line.get_data()
    return ax.fill_between(x, y, color=line.get_color(), alpha=alpha,
                           linewidth=0, zorder=1)


def save_publication_figure(fig, filename, **kwargs):
    """Save PNG previews and vector PDFs; set PAPER_FIGURE_FORMATS=pdf for PDF only."""
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    formats = os.environ.get("PAPER_FIGURE_FORMATS", "png,pdf").split(",")
    options = {"bbox_inches": "tight", "facecolor": "white"}
    options.update(kwargs)
    # Keep vectors resolution-independent; rasterized artists/PNGs use 1200 dpi.
    options["dpi"] = PUBLICATION_DPI
    options.pop("format", None)
    written = []
    for fmt in formats:
        fmt = fmt.strip()
        if fmt not in {"png", "pdf"}:
            raise ValueError("PAPER_FIGURE_FORMATS must contain png and/or pdf")
        with mpl.rc_context({"pdf.fonttype": 42}):
            target = path.with_suffix("." + fmt)
            fig.savefig(target, format=fmt, **options)
            written.append(target)
    return written
