# Color scales with ordered lightness for grayscale printing; 1200 dpi export.
# Set PAPER_FIGURE_FORMATS=pdf to leave existing PNGs untouched.
# Layout calculations may open the default device before explicit export.
if (!interactive()) options(device = function(...) grDevices::pdf(file = NULL, ...))
paper_dpi <- 1200
paper_border_colour <- "grey50"
paper_border_linewidth <- 0.3
paper_grid_colour <- "grey80"
paper_grid_linewidth <- 0.07
paper_colors <- c("#FED976", "#FEB24C", "#FD8D3C", "#E31A1C", "#800026")
paper_share_colors <- c("white", paper_colors)
paper_rank_colors <- c("#FFF0A6", "#FED976", "#FDA45C", "#F46D43", "#C52B1A", "#800026")

embed_paper_fonts <- function(filename) {
  # PDF input needs the standard Helvetica/Symbol fonts explicitly included.
  grDevices::embedFonts(filename, options = c(
    "-dEmbedAllFonts=true", paste0("-r", paper_dpi), "-c",
    shQuote(paste("<</NeverEmbed [] /AlwaysEmbed",
                  "[/Helvetica /Helvetica-Bold /Helvetica-Oblique /Helvetica-BoldOblique /Symbol]>>",
                  "setdistillerparams")), "-f"
  ))
}

save_paper_plot <- function(filename, plot, width, height, ...) {
  formats <- trimws(strsplit(Sys.getenv("PAPER_FIGURE_FORMATS", "png,pdf"), ",")[[1]])
  stopifnot(all(formats %in% c("png", "pdf")))
  for (format in formats) {
    target <- sub("\\.[^.]+$", paste0(".", format), filename)
    if (format == "pdf") {
      ggplot2::ggsave(target, plot = plot, device = grDevices::pdf,
                      width = width, height = height, units = "in",
                      bg = "white", useDingbats = FALSE, dpi = paper_dpi, ...)
      embed_paper_fonts(target)
    } else {
      ggplot2::ggsave(target, plot = plot, device = "png", width = width,
                      height = height, units = "in", bg = "white", dpi = paper_dpi, ...)
    }
  }
}

# Legacy map exporters specify pixel dimensions. Keep their aspect ratios,
# but use physical page sizes for the vector version.
save_paper_map <- function(plot, filename, width, height) {
  save_paper_plot(filename, plot, width / 300, height / 300)
}

# Give comparison panels a shared legend, keeping the year/transfer in each title.
paper_share_panel <- function(plot, title_size = 12) {
  panel_title <- plot$scales$get_scales("fill")$name
  fill_scale <- plot$scales$get_scales("fill")$clone()
  fill_scale$name <- "Agricultural area (%)"
  plot <- suppressMessages(plot + fill_scale)
  plot + ggplot2::labs(title = panel_title) +
    ggplot2::theme(
      plot.title = ggplot2::element_text(size = title_size, hjust = 0.5),
      legend.title = ggplot2::element_text(size = 10),
      legend.text = ggplot2::element_text(size = 9),
      legend.key.width = grid::unit(0.8, "cm"),
      legend.key.height = grid::unit(0.3, "cm")
    )
}

paper_site_ring <- function(data) {
  # One point per selected site, rather than one overprint per model/year.
  points <- unique(sf::st_drop_geometry(data)[c("x", "y")])
  list(
    ggplot2::geom_point(data = points, ggplot2::aes(x = x, y = y),
                       inherit.aes = FALSE, shape = 21, fill = NA,
                       colour = "white", size = 8, stroke = 2.5),
    ggplot2::geom_point(data = points, ggplot2::aes(x = x, y = y),
                       inherit.aes = FALSE, shape = 21, fill = NA,
                       colour = "black", size = 8, stroke = 1)
  )
}
