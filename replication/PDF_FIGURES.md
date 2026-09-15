# 彩色、黑白打印可读的 PDF（1200 dpi）：生成与重跑清单

`results_in_paper/` 的 42 个原始 PNG 保留；PDF 除下述四个上传短文件名外，使用相同的文件名主干。
PDF 保留彩色，同时用线型、标记和明暗递进保证黑白打印可读；不是导出成黑白 PDF。
PDF 从绘图对象直接导出，不是把 PNG 装进 PDF。模型参数、数据、分箱和曲线数值不变。

## 上传用短文件名

以下仅修改 `results_in_paper/` 的最终 PDF 名称；内部绘图输出、原 PNG 和原论文引用路径不变。
对应规则位于 `pysrc/replication/paper_assets.py` 的 `PDF_UPLOAD_NAMES`，收集脚本和完整重跑均自动应用。

| 原 PDF 文件名 | 上传 PDF 文件名 |
| --- | --- |
| `Figure11_aggregate_percentage_Z_b0_pehmc_6.8_pedet_6.8_xi_1.0.pdf` | `Figure11_agg_percentage_Z_b0_pehmc_6.8_pedet_6.8_xi_1.0.pdf` |
| `Figure13_aggregate_percentage_Z_b0_pehmc_4.8_pedet_6.8_xi_1.0_same_ylim.pdf` | `Figure13_aggpct_Z_b0_pehmc_4.8_pedet_6.8_xi_1.0_same_ylim.pdf` |
| `Figure13_aggregate_percentage_Z_b15_pehmc_19.8_pedet_21.8_xi_1.0_same_ylim.pdf` | `Figure13_aggpct_Z_b15_pehmc_19.8_pedet_21.8_xi_1.0_same_ylim.pdf` |
| `Figure15_pred_zshare_delta_comparison_1043_sites_det_delta_0p03.pdf` | `Figure15_pred_zshare_delta_comp_1043_sites_det_delta_0p03.pdf` |

## 1200 dpi 的含义

Python 和 R 的公共导出函数统一设置为 1200 dpi，覆盖旧的 100/300 dpi 导出参数。
PNG 和任何需要栅格化的绘图元素使用该分辨率，Ghostscript 的处理分辨率也设为 1200 dpi。
本次 42 个 PDF 的图形、文字均保留矢量，没有嵌入位图，所以 PDF 本身没有固定的像素分辨率；
不能将其描述成一张具有固定 1200 dpi 的位图。矢量内容可直接按 1200 dpi 或更高分辨率印刷。
不把整页栅格化，也不通过插值放大旧 PNG。

## 一次重画全部图

在仓库根目录、已有 Python/R 环境中运行：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures --collect
```

默认只生成和收集 PDF，不覆盖 PNG，也不重写论文表格。
需要同步更新彩色 PNG 时，明确增加 `--formats png pdf`（PNG 也将以 1200 dpi 导出）。
只查看命令而不执行：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures --list --collect
```

本机已有的 R 库可直接使用，避开 renv 启动时的锁等待：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures \
  --r-library renv/library/macos/R-4.4/aarch64-apple-darwin20 \
  --collect
```

`--r-library` 使用已有库，不安装包；其他机器应指定自己的库路径或省略此选项。
R 图使用原生 `pdf()` 加 `embedFonts()`，需要 Ghostscript；不依赖 Cairo/XQuartz。
Python PDF 嵌入 TrueType 字体。运行器自动使用无窗口绘图和临时缓存目录。

## 分组重跑

下面的每个组均可通过 `--groups 组名` 单独运行，也可以列出多个组。

| 图号 | 组名 | 实际绘图代码 |
| --- | --- | --- |
| 1 | `figure1` | `pysrc/scripts/figure1.py --plot-only` |
| 2 | `capture` | `rsrc/analysis/carbon_capture_curves/02_analysis.R` |
| 3、4 | `calibration` | `rsrc/analysis/calibration_maps_1043_sites.R` |
| 5、6 | `deterministic` | `pysrc/scripts/conduction_det.py --figures-only` → `pysrc/analysis/figures.py` |
| 7、8 | `det-maps` | `rsrc/analysis/map_1043_det.R` |
| 9、18、19 | `densities` | `pysrc/scripts/conduction_hmc.py --skip-optimization --xi 1 2 0.5 --figures density --gamma-sites 938 929 --theta-sites 985 1028` |
| 10、11、12、13 | `hmc-comparisons` | `pysrc/scripts/conduction_hmc.py --skip-optimization --xi 1 --figures histograms trajectories` |
| 14 | `mpc` | `pysrc/scripts/mpc_trajectory.py` |
| 15 | `delta` | `pysrc/scripts/deterministic_delta_sensitivity.py --plot-only` |
| 16 | `hmm` | `pysrc/scripts/price_estimation.py --plot-only` |
| 17 | `entropy-map` | `rsrc/analysis/map_kl.R` |
| 20 | `hmc-map-1` | `rsrc/analysis/map_1043_hmc_xi1.R` |
| 21 | `hmc-map-05` | `rsrc/analysis/map_1043_hmc_xi05.R` |
| 22 | `r2` | `pysrc/scripts/bayesian_R2.py` |

例如，只重画 Figure 15、16：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures --groups delta hmm --collect
```

这些命令不运行 Gurobi 求解、Stan 抽样或 HMM 估计。
Figure 2 会从已有 `combined_df.Rdata` 重算年龄组统计，Figure 22 从已有参数样本重算 R²；
Figure 14 会读取已有模拟路径并求平均。地图脚本可能额外导出不在论文清单中的面板，汇总只选择论文图。

## 缓存与原图对应关系

- Figure 1 的仅绘图入口读取 `replication/derived/figure1_source_data.csv`。
- Figure 15 的仅绘图入口读取 baseline 与 `output/delta_sensitivity/delta_0p03/optimization/` 中已有的解，只画比较图，不更新数值 CSV 或表格。
- Figure 16 读取 `smooth_prob_uncon.csv`、`smooth_prob_con.csv` 和原始价格序列。
  新估计会保存全精度的 `output/tables/hmm_plot_means_*.json`；旧结果没有该缓存时，读取
  `job-outs/stage_hmm/price_estimation/0001_run.out` 的最终均值（八位小数），不会使用论文表中两位小数的均值。
  因此旧结果的两条水平参考线精度受日志打印精度限制，概率曲线与价格序列仍使用已有完整 CSV。
- 密度图明确锁定论文使用的 gamma 站点 938/929 和 theta 站点 985/1028。
  当前相对熵站点 CSV 与旧日志不同，不能用新的自动选择替换论文图。
- Figure 17 继续沿用原绘图代码读取旧日志的圈选站点，不重新排名或更换圈选位置。
- Figure 14 的 `source_basename` 固定为 `_adjust.png`，对应 PDF 为 `_adjust.pdf`；原论文引用路径保留在清单中。

## 导出与收集

共享样式和导出函数位于：

- `pysrc/analysis/publication.py`
- `rsrc/analysis/publication.R`

直接运行原脚本时默认同时输出彩色 PNG 与 PDF；设置 `PAPER_FIGURE_FORMATS=pdf` 可仅导出 PDF。
地图保留原长宽比例、数值分箱和年份，采用亮度逐级递减的黄—橙—红色阶，并调整图例字号。
地图外轮廓统一为 `grey50`、0.3 mm，内部网格边线为 `grey80`、0.07 mm；
参数集中在 `rsrc/analysis/publication.R`，替代原来的黑色 0.45 mm 外框和较深的网格线。
Figure 17 的黑白圈选标记保持原样，不随地图边框变浅。
Figure 7、8、20、21 使用共享图例，原图例中的年份和补贴额移入各面板标题，避免图例被挤压。
Figure 7（四面板）和 Figure 8（六面板）的面板标题从 12 pt 放大至 16 pt；
从当前 9 英寸图宽缩到 6 英寸宽时，标题约为 10.7 pt。Figure 20、21 暂维持原字号。
Figure 2 删除图内的 “Carbon capture curve” 标题；Figure 9、18、19 删除所有
“Probability density … and site …” 标题，保留轴标签和图例，站点信息仍可由文件名和图注对应。
Figure 1 的 C、I、E、U 使用 12 pt 黑色粗体字、加大的黑色空心圆，字母相对标记中心向右偏移 6 pt。
密度图、模型比较和直方图同时用颜色与不同线型区分；接近重合的曲线增加稀疏空心标记。

当前线图主线宽为 3.2 pt；Figure 2 的 R 曲线线宽为 1.3 mm，Figure 16 的水平参考线为 2.4 pt。
Figure 9 恢复虚线曲线下的同色填充（alpha=0.30）。Figure 10、12、18、19 使用虚线同色的
浅色填充（alpha=0.18，即 82% 透明），填充在最底层、虚线居中、实线在最上层；线条本身不透明。
Figure 11、13、14 恢复原始模型颜色对应：neutral／确定性为红色系，averse 为蓝色系；线型和标记不取消。

只重跑这次线宽、阴影及模型颜色调整涉及的图：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures \
  --groups capture deterministic densities hmc-comparisons mpc delta hmm \
  --r-library renv/library/macos/R-4.4/aarch64-apple-darwin20 --collect
```

仅重画地图边框调整涉及的 Figure 3、4、7、8、17、20、21（12 个 PDF）：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures \
  --groups calibration det-maps entropy-map hmc-map-1 hmc-map-05 \
  --r-library renv/library/macos/R-4.4/aarch64-apple-darwin20 --collect
```

仅重画重复标题、Figure 1 高亮和 Figure 7、8 标题字号调整涉及的图：

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures \
  --groups figure1 capture densities det-maps \
  --r-library renv/library/macos/R-4.4/aarch64-apple-darwin20 --collect
```

仅收集已生成的 PDF：

```bash
.venv/bin/python -m pysrc.replication.build_results_in_paper \
  --figures-only --figure-formats pdf
```

图片 manifest 同时保留 PNG/PDF 的路径和格式记录。
完整后处理也会把已登记的 PDF 加入保留名单，不再把它们当作旧文件删除。
本次的原始 PNG 保持原样；未来需要匹配新 PDF 的彩色预览时，再显式重画 PNG。

## 检查

```bash
MPLCONFIGDIR=/private/tmp/amazon-paper-mpl \
XDG_CACHE_HOME=/private/tmp/amazon-paper-xdg \
.venv/bin/python -B -m unittest discover -s tests -v
```

交付检查包括：42 个 PNG 各有一个对应 PDF（四个短文件名按映射对应）、PDF 单页且可解析、没有嵌入整页位图、字体已嵌入；
并检查彩色内容、1200 dpi 导出设置、多面板地图图例、Figure 14 重合曲线和 Figure 17 圈选标记。
黑白预览只用于检查可读性，不替换交付的彩色 PDF。
