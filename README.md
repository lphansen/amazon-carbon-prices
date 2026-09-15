# Data and Code for: Carbon Prices, Forest Conservation and Reforestation in the Brazilian Amazon

This repository contains the data-cleaning, estimation, optimization, and
post-processing code for the Amazon carbon-prices manuscript. The replication
workflow is organized around a single driver, `run.sh`, and the exhibit audit
files in `replication/`.

Manuscript authors and affiliations:

- Juliano Assunção (Climate Policy Initiative and PUC-Rio)
- Lars Peter Hansen (University of Chicago)
- Todd Munson (Argonne National Laboratories)
- José A. Scheinkman (Columbia and Princeton Universities)

## Acknowledgments

This Git repository was prepared by Jiaying Liao (Jessie), building on an
earlier repository that included work by Pengyu Chen, Leonardo Gomes, Patricio
Hernandez, Zhaoyang Xu, and Daniel Zhao.

The package is structured to be usable both on a local machine and on a server
or cluster. Local runs execute commands directly. On a server or cluster, the
same steps can be submitted through Slurm.

## Journal Reproducibility Check Status

This section documents the scope of the reproducibility check reported by the
JPE Data Editor on June 30, 2026. It records which components were run during
the journal reproducibility check and which components were not run because of
computational constraints.

| Component | Status in reproducibility check | Notes |
| --- | --- | --- |
| Environment setup | Completed after Linux dependency fixes | See the Linux setup notes below. |
| Full end-to-end pipeline | Not run | Computational constraints for the JPE Data Editor. |
| Data cleaning: `rsrc/cleaning/_masterfile.R` | Not run | Computational constraints for the JPE Data Editor. |
| Data processing: `rsrc/processing/_masterfile.R` | Not run | Computational constraints for the JPE Data Editor. |
| Calibration: `rsrc/calibration/_masterfile.R` | Not run | Computational constraints for the JPE Data Editor. |
| Post-processing-only run | Completed | `./run.sh --steps postprocess-only --backend local`. |
| Figures and tables | Reproduced | All feasible figures and tables were reproduced; Figure 11 had a minor y-axis scale difference, while the plot and numbers matched. |
| In-text numbers not tied to tables or figures | Documented below | The README lists each item from the report and the corresponding replication evidence. |

## Quick Start

Most users should use a local machine for R data and plotting steps and a
Slurm server for the computationally heavy Python/Gurobi/CmdStan steps. The
full workflow is controlled by one entry point, `run.sh`.

```bash
git clone <repo-url>
cd amazon-carbon-prices
source ./setup_env.sh local
./run.sh --steps stage-data --backend local
```

Then sync the repository, `data/`, and any generated inputs to the server and
run the heavy non-R stages:

```bash
source ./setup_env.sh server
./run.sh --steps stage-hmm stage-deterministic stage-time-consistency stage-hmc stage-mpc --backend slurm --slurm-account pi-<pi_account_name>
```

When those server jobs finish, sync `job-outs/`, `output/`, `plots/`, and
`replication/derived/` back to the local machine, then run the R maps and final
audit locally:

```bash
./run.sh --steps maps hmc-maps --backend local --jobs 1
./run.sh --steps postprocess-only --backend local
```

If the server has R and the R environment has been restored there, submit the
complete workflow, including R data and map steps, in one command:

```bash
./run.sh --steps all --backend slurm --slurm-account pi-<pi_account_name> --run-r-on-slurm
```

Before any long run, inspect the exact plan without executing commands:

```bash
./run.sh --steps all --backend slurm --slurm-account pi-<pi_account_name> --run-r-on-slurm --dry-run
```

## Choosing Local or Server Runs

| Use case | Recommended run location | Command pattern |
| --- | --- | --- |
| Build raw data products and R maps | Local machine, unless server R is configured | `./run.sh --steps stage-data --backend local`; after model outputs exist, `./run.sh --steps maps hmc-maps --backend local` |
| Run Python/Gurobi/CmdStan model jobs | Slurm server | `./run.sh --steps stage-hmm stage-deterministic stage-time-consistency stage-hmc stage-mpc --backend slurm --slurm-account <account>` |
| Server has no R | Run R stages locally, sync `data/`, then run non-R stages on Slurm | `./run.sh --steps stage-hmm stage-deterministic stage-time-consistency stage-hmc stage-mpc --backend slurm --slurm-account <account>` |
| Server has R and `renv` restored | Run everything on Slurm | `./run.sh --steps all --backend slurm --slurm-account <account> --run-r-on-slurm` |
| Heavy outputs already exist | Refresh tables, manifests, and `results_in_paper/` locally | `./run.sh --steps postprocess-only --backend local` |

## Workflow Overview and Runtime

The table below summarizes what each stage does, whether it needs R, and the
approximate runtime observed in the completed replication logs. Times are
hardware- and queue-dependent. The `observed wall time` column reflects the
logged wall-clock span when parallel jobs ran concurrently; the heavy MPC stage
would take much longer if run strictly serially.

| Stage | Main tools | Needs R? | Parallel? | Observed wall time | Notes |
| --- | --- | --- | --- | --- | --- |
| `stage-data` | R, Python | Yes for raw data processing; Python only for Figure 1 | Mostly serial | About 4 hours | Builds `data/processed/`, `data/clean/`, `data/calibration/`, and Figure 1. |
| `stage-hmm` | Python, CmdStan | No | Partly parallel | About 1.5 hours | Price estimation, baseline sampling summaries, Bayesian R2. |
| `stage-deterministic` | Python, Gurobi, R maps | R only for maps | Parallel shadow-price jobs | About 2-3 hours plus sensitivity jobs | Deterministic shadow prices, deterministic tables, `delta=0.03` sensitivity trajectories, and maps. |
| `stage-time-consistency` | Python, Gurobi | No | Two independent jobs | About 7.3 hours | Runs `bf=3.75` and `bf=5`. |
| `stage-hmc` | Python, CmdStan, Gurobi, R maps | R only for maps | Highly parallel | About 16 hours | Finite-`xi` shadow prices and HMC sampling are the bottlenecks. |
| `stage-mpc` | Python, Gurobi | No | Highly parallel | About 13-14 hours | MPC shadow-price grid and Figure 14 simulation jobs dominate. |
| `stage-postprocess` | Python | No | Mostly serial | Less than 1 minute | Builds audit CSVs, paper numbers, and `results_in_paper/`. |

With enough Slurm parallelism, the completed logs imply an end-to-end run of
roughly two days after environment setup and data placement are ready. The same
commands can run locally, but a single-worker local run is not practical for a
fresh full replication: the MPC Figure 14 simulation jobs alone accumulated more than
2,400 job-hours across parallel tasks. For local verification, prefer
`postprocess-only`, R map refreshes, or one stage at a time.

The most expensive steps are `stage_hmc/shadow_prices_hmc`,
`stage_hmc/hmc_sampling`, `stage_mpc/mpc_sp_grid`,
`stage_mpc/mpc_hmc_figure14_unconstrained`, and
`stage_time_consistency/time_consistency`. These are designed for parallel or
grouped Slurm execution. The required ordering is:

```text
data
  -> HMM and baseline sampling
  -> deterministic and HMC shadow-price searches
  -> derived carbon-price CSVs
  -> deterministic/HMC/MPC model outputs, maps, and tables
  -> postprocess-final and results_in_paper/
```

More specifically, HMC sampling must finish before `relative-entropy` and HMC
density/map figures; the MPC shadow-price grid must finish before `mpc-prices`;
and the MPC simulation jobs must finish before Table 18 and Figure 14 are
rebuilt. The only named steps that call `Rscript` are `data`, `maps`, and
`hmc-maps`; the other stages are Python, Gurobi, or CmdStan steps.

## Repository Layout

- `data/raw/`: raw input data. The final journal archive should include this folder; GitHub mirrors may omit large raw files.
- `data/processed/`, `data/clean/` and `data/calibration/`: processed, cleaned and calibrated data generated from the raw inputs.
- `data/codebook.csv`: source-level data inventory, access notes, generated-data descriptions, and open-format companion notes.
- `data/source_permissions.csv`: source-by-source audit record for access, license or terms, redistribution status, and final-review notes.
- `rsrc/`: R data-cleaning, calibration, and map/figure scripts.
- `pysrc/`: Python package code for sampling, optimization, MPC, and shared
  helpers.
- `pysrc/scripts/`: user-facing Python scripts that run analysis, estimation,
  figures, and workflow orchestration.
- `pysrc/replication/`: replication post-processing code that turns raw model
  outputs and logs into derived CSVs, manifests, paper numbers, and `results_in_paper`
  assets.
  The previous top-level `scripts` layout has been folded into `pysrc/` so
  Python code lives under one importable package tree.
- `replication/figure1/`: World Bank inputs included in the repository and
  `FIGURE1_DOCUMENTATION.md` notes for reproducing Figure 1 through
  `pysrc/scripts/figure1.py`.
- `job-outs/`: generated local or Slurm logs. The audit logs used to derive
  paper numbers are version controlled; routine run logs remain ignored.
- `output/` and `plots/`: generated tables, figures, and model outputs, not
  version controlled.
- `replication/`: static replication inputs, package manifests, generated
  manifests, and output-derived manuscript numbers.

## Requirements

### Software Requirements

- Python >= 3.9 and < 3.12. The author-tested local `.venv` has Python
  3.9.25 (`.venv/pyvenv.cfg`). The project dependencies are pinned in
  `pyproject.toml`.
- Core Python packages pinned by the project: `numpy==1.25.2`,
  `pandas==2.1.0`, `geopandas==0.14.4`, `pyomo==6.6.2`,
  `cmdstanpy==1.2.0`, `scipy==1.11.1`, `matplotlib==3.7.3`,
  `seaborn==0.13.2`, `jinja2==3.1.6`, and `hmmlearn==0.3.3`.
- Additional installed Python packages used in the author-tested local and
  server snapshots include `gurobipy==11.0.3`, `fiona==1.10.1`,
  `pyproj==3.6.1`, `shapely==2.0.7`, and `scikit-learn==1.6.1`.
- R 4.4.1 with packages restored from `renv.lock`. Key R packages pinned in
  the lockfile include `sf==1.0-16`, `terra==1.7-78`, `magick==2.8.3`,
  `units==0.8-5`, `nloptr==2.0.3`, `systemfonts==1.0.6`,
  `ragg==1.3.0`, `tidyverse==2.0.0`, and `renv==1.0.7`.
- GDAL, GEOS, PROJ, UDUNITS2, ImageMagick/Magick++, NLopt, CMake,
  `pkg-config`, and a working C/C++ toolchain are required to restore the R
  spatial and graphics stack on Linux.
- Gurobi is required for optimization. The author-tested local Python
  environment uses `gurobipy==11.0.3`; `gurobi_cl --version` on the local machine reports
  Gurobi Optimizer 12.0.2. The setup script installs `gurobipy==11.0.*`, so
  keep the command-line Gurobi installation and the Python package compatible
  with the available license.
- CmdStan is required through `cmdstanpy`. The author-tested local environment
  uses `cmdstanpy==1.2.0` and CmdStan 2.38.0 at
  `/Users/jessieliao/.cmdstan/cmdstan-2.38.0`. The Linux replicator report
  used a rebuilt CmdStan 2.39.0.
- Slurm is optional and only needed for `--backend slurm`.

### Author-Tested Local Environment

The local environment inspected for this README was:

| Item | Value |
| --- | --- |
| Machine | MacBook Pro |
| Model identifier | Mac16,6 |
| Model number | MX2K3LL/A |
| Chip | Apple M4 Max |
| CPU cores | 14 total: 10 performance and 4 efficiency |
| Memory | 36 GB |
| Architecture | arm64 |
| Operating system | macOS 26.5.2, build 25F84 |
| Kernel | Darwin 25.5.0 |
| Repository disk state at inspection | 91 GB total working tree; `data/` 28 GB, `output/` 52 GB, `job-outs/` 703 MB, `.venv` 606 MB, `.venv_server` 736 MB |
| Free disk space on repository volume | About 315 GiB free |
| Python | 3.9.25 in `.venv` |
| R | 4.4.1, with packages pinned by `renv.lock` |
| Gurobi | `gurobipy==11.0.3`; local `gurobi_cl` reports 12.0.2 |
| CmdStan | CmdStan 2.38.0 through `cmdstanpy==1.2.0` |

The local `.venv` is a complete virtual environment. The `.venv_server`
directory in this working copy contains a `lib/python3.9/site-packages`
snapshot with the core packages above, including `gurobipy==11.0.3`, but it
does not contain a `bin/python` executable or `pyvenv.cfg`. Treat
`.venv_server` as a package snapshot, not as a portable environment. Server
users should recreate `.venv` with `source ./setup_env.sh server`.

### Author Slurm Configuration

The completed heavy-stage outputs were produced with the Slurm backend driven
by `pysrc/scripts/run_replication.py`. Slurm batch scripts are submitted
inline by `sbatch` rather than written as separate `.sh` files. The exact
requested resources are visible in `slurm_batch_command()` and are equivalent
to:

```bash
#SBATCH --time=1-11:00:00
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
```

The account and partition are intentionally supplied by the user or environment:

```bash
REPLICATION_SLURM_ACCOUNT="pi-<pi_account_name>"
REPLICATION_SLURM_PARTITION="<partition-name>"
```

On the Midway server, the module setup used by `setup_env.sh server` is:

```bash
module load python/anaconda-2022.05 gurobi/11.0 gcc/12.2.0
```

The default Slurm grouping settings are:

| Setting | Default |
| --- | --- |
| Nodes per job | 1 |
| CPUs per task | 8 |
| Memory per job | 32G |
| Wall time per job | 1 day and 11 hours |
| Commands per grouped Slurm job | 10 |
| Minimum commands before grouping | 100 |
| MPC special-case grouping | One replication command per Slurm job for the large MPC steps |

Use `--dry-run` before submission to print the planned local or Slurm commands.
Use `--slurm-time`, `--slurm-cpus`, `--slurm-mem`, `--slurm-account`, and
`--slurm-partition` to override the defaults without editing source files.

### Runtime, Memory, and Storage

With enough Slurm parallelism, the observed end-to-end runtime is roughly two
days after data and environments are ready. A single-worker local run is not
recommended for the heavy HMC/MPC stages. The completed logs imply more than
2,400 accumulated job-hours for the MPC Figure 14 simulation jobs alone.

Plan for at least 100 GB of working storage if the full `data/`, `output/`,
`plots/`, `job-outs/`, local virtual environments, and generated results are
kept together. The final JPE archive should exclude `.venv/`, `.venv_server/`,
`renv/library/`, and CmdStan build caches because they are platform-specific
and regenerated by the setup scripts.

## Notes for Linux Users

The JPE replicator used a Nuvolos Ubuntu 24.04.1 LTS server with AMD EPYC
9354P, 32 cores, and 64 GB RAM, using Python 3.11 and R 4.5.3 during the
environment-rebuild attempts. The package ultimately ran after installing a
consistent Linux geospatial and compiler stack. These notes are not required
on macOS, but they are useful when `renv::restore()` fails on Linux.

Set the Gurobi license before setup:

```bash
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

If the virtual environment has stale symlinks or permission problems:

```bash
rm -rf .venv
chmod +x ./setup_env.sh
./setup_env.sh local
```

A conda-forge environment that provides the support libraries can be created
with:

```bash
conda create -n amazon-carbon -c conda-forge python=3.11 "r-base=4.4.*" r-essentials imagemagick pkg-config
conda activate amazon-carbon
conda install -c conda-forge nlopt cmake pkg-config -y
conda install -c conda-forge udunits2 expat -y
conda install -c conda-forge "gdal=3.8.5" "libgdal=3.8.5" geos proj proj-data sqlite libspatialite -y
conda install -c conda-forge compilers libstdcxx-ng libgcc-ng sysroot_linux-64 make -y
```

Export GDAL and PROJ data paths if `sf` cannot find coordinate-transform data:

```bash
export PROJ_LIB=$CONDA_PREFIX/share/proj
export PROJ_DATA=$CONDA_PREFIX/share/proj
export GDAL_DATA=$CONDA_PREFIX/share/gdal
```

If `systemfonts` or `ragg` fail to compile because of missing `uint32_t` or
strict C++ conversions, create `~/.R/Makevars` with:

```bash
mkdir -p ~/.R
cat > ~/.R/Makevars <<'EOF'
CXXFLAGS += -include cstdint -fpermissive
CXX11FLAGS += -include cstdint -fpermissive
CXX14FLAGS += -include cstdint -fpermissive
CXX17FLAGS += -include cstdint -fpermissive
CXX20FLAGS += -include cstdint -fpermissive
EOF
```

If cached `stringi` packages point to missing ICU libraries, remove the stale
renv cache entry and rerun `renv::restore()`:

```bash
rm -rf /tmp/R/renv/cache/v5/linux-ubuntu-noble/R-4.4/x86_64-conda-linux-gnu/stringi
```

If `terra` or `sf` links against an inconsistent GDAL stack, remove
conda-installed `r-terra`, reinstall a single conda-forge GDAL stack, and then
rerun the R restore:

```bash
conda remove r-terra -y
conda install -c conda-forge "gdal=3.8.5" "libgdal=3.8.5" geos proj proj-data sqlite libspatialite -y
```

If CmdStan fails to build under conda because TBB cannot identify the compiler,
build it with explicit conda paths:

```bash
cd /path/to/.cmdstan/cmdstan-2.39.0
export CONDA_PREFIX=/path/to/conda/env
export PATH=$CONDA_PREFIX/bin:$PATH
export MAKE=$CONDA_PREFIX/bin/make
export TBB_CXX_TYPE=gcc
make build -j1
```

## Replication Workflow

Follow these steps in order. The commands work locally with `--backend local`
and on a Slurm server with `--backend slurm`.

### Step 1. Prepare the Environment

The setup can be run as one command from the repository root. Use `source` if
you want the environment to remain active in the current shell after setup
finishes.

```bash
git clone <repo-url>
cd amazon-carbon-prices
```

#### 1.1 Local Setup

Install Gurobi 11.0.x with a valid license, R, and a C/C++ compiler first.

Academic users can request a free academic license from the Gurobi Academic
License Program or Gurobi User Portal; after installing Gurobi, copy the
portal-provided `grbgetkey ...` command and run it on the local machine to
create `gurobi.lic`. Put `gurobi.lic` in a default Gurobi license directory, or
export `GRB_LICENSE_FILE=/full/path/to/gurobi.lic` before running this repo so
Gurobi and Pyomo can find the license.

On macOS, the compiler setup is usually:

```bash
xcode-select --install
brew install gcc@12
```

Then run:

```bash
source ./setup_env.sh local
```

The script creates `.venv`, installs the pinned Python dependencies from
`pyproject.toml`, installs `gurobipy==11.0.*`, installs CmdStan through
`cmdstanpy`, restores the R packages from `renv.lock`, and checks that Gurobi is
visible. If you do not want the script to activate `.venv` in the current
shell, run `./setup_env.sh local` instead. If you need to force a fresh CmdStan
install, add `--overwrite-cmdstan`.

If Gurobi on macOS is not found automatically, set these variables before
running the setup command. Adjust the folder name to your installed version:

```bash
export GUROBI_HOME="/Library/gurobi1103/macos_universal2"
export PATH="$GUROBI_HOME/bin:$PATH"
export DYLD_LIBRARY_PATH="$GUROBI_HOME/lib:${DYLD_LIBRARY_PATH:-}"
export GRB_LICENSE_FILE="$HOME/gurobi.lic"
```

#### 1.2 Server Setup

On the server, the same setup is also one command:

```bash
source ./setup_env.sh server
```

This loads the server modules, creates `.venv`, installs the Python package and
Gurobi Python package, installs CmdStan, and leaves the environment active in
the current shell. Server setup skips `renv::restore()` by default because the
server workflow is designed to skip `Rscript` steps unless R is explicitly
available. If the server has a working R installation and you want to run R
steps there, use:

```bash
source ./setup_env.sh server --with-renv
```

Internally the default server setup uses the same module setup as:

```bash
module avail python gurobi gcc
module load python/anaconda-2022.05 gurobi/11.0 gcc/12.2.0
/software/python-anaconda-2022.05-el8-x86_64/bin/python3 -m venv .venv
source .venv/bin/activate
```
For later server sessions:

```bash
cd amazon-carbon-prices
module load python/anaconda-2022.05 gurobi/11.0 gcc/12.2.0
source .venv/bin/activate
```

Keep environment setup separate from the replication run. Slurm jobs source the
existing `.venv`; they should not reinstall Python packages, CmdStan, or R
packages inside every submitted job.

### Step 2. Prepare the Data Inputs

The final journal replication archive should include the complete `data/`
directory: `data/raw/`, `data/processed/`, `data/clean/`, and
`data/calibration/`. A GitHub mirror may omit large raw and intermediate files;
if so, use the archived replication package as the authoritative data source.
Same raw-data bundle can be downloaded
[here](https://www.dropbox.com/scl/fo/n6gsyl7w2mki77eqew8ts/AMUKehiyaTFH2fjO5VotYwE?rlkey=iuk47v413domc1utvoa8x3yfp&st=ie2dyrzx&dl=0). The GitHub replication branch also provides
`data/calibration/` calibrated inputs as a reference and as a starting point for
users who want to skip raw-data calibration and reproduce the model, table, and
figure outputs directly.

#### Data Availability Statement

The package is designed to be reproducible from public administrative, market,
climate, remote-sensing, and carbon-price data.
The final JPE archive should contain the exact raw extracts used by the authors
plus the generated processed, cleaned, and calibrated data. No confidential
human subjects data are used. The data-source inventory, access notes,
provider names, generated-file descriptions, and `.Rdata` open-format
equivalents are documented below. `data/codebook.csv` mirrors the same
inventory in machine-readable form, but this README is the authoritative
documentation entry point.
After journal archiving, cite the permanent archive DOI assigned by the journal
repository as the authoritative source for the complete replication package.
Because the full `data/`, `output/`, and `plots/` directories can exceed 10GB,
authors should coordinate with the JPE Data Editor before final upload if the
accepted archive must be split across multiple files.

#### Raw Excel Files

Several third-party source files are archived in their original `.xls` or
`.xlsx` formats under `data/raw/` to preserve the exact raw
extracts used by the authors. These Excel files are raw archived sources, not
the final analysis data used in the paper tables and figures. The
data-processing scripts read the archived raw files and write generated CSV,
`.Rdata`, GeoJSON, and raster products under `data/processed/`, `data/clean/`,
`data/calibration/`, and `replication/derived/`; those generated files are the
analysis inputs used by the model, table, figure, and post-processing scripts.

#### Data Sources and Citations

The manuscript's Appendix A describes the data construction in detail. The
table below maps the data sources mentioned in the manuscript and used by the
code to the package folders. All source-specific licenses and citation
requirements remain with the original providers.

| Source | Package location | Use in paper/code | Citation or access note |
| --- | --- | --- | --- |
| World Bank / World Development Indicators and Climate Watch | `data/raw/worldbank/emission_kuznets/`, `replication/figure1/input/` | GDP per capita and CO2 emissions for Figure 1. | Manuscript Figure 1 states World Bank data were downloaded in March 2021. Metadata files are stored under `replication/figure1/documentation/`. |
| Fatos da Amazonia 2021 / Amazonia 2030 | `replication/figure1/reference/` and generated `replication/derived/figure1_source_data.csv` | Brazilian Amazon point in Figure 1. | Manuscript Figure 1 cites Fatos da Amazonia 2021, www.amazonia2030.org. |
| MapBiomas Collection 5 and related MapBiomas products | `data/raw/mapbiomas/` | Land-use/cover, total available area, agricultural area, deforestation, secondary vegetation age, pasture quality, and basin inputs. | Manuscript Appendix A and Section 5 cite MapBiomas and Souza et al. (2020); the text identifies Collection 5. |
| ANA/PNRH water-basin layers distributed through MapBiomas | `data/raw/mapbiomas/basin/` | Basin groups for agricultural-productivity random effects in Appendix C.1. | Manuscript Appendix C.1 notes sub-basins of the National Water Resources Plan, level 2, ANA 2006, available through MapBiomas. |
| ESA Biomass Climate Change Initiative | `data/raw/esa/above_ground_biomass/` | Above-ground biomass density for carbon absorption/productivity. | Manuscript cites Santoro and Cartus (2021), ESA Biomass CCI global above-ground biomass, v3; Appendix A.2 uses 2017 data. |
| SEEG | `data/raw/seeg/emission/` | Agricultural net emissions used to calibrate emissions contributed by agriculture. | Manuscript Appendix A.4 cites Sistema de Estimativas de Emissoes e Remocoes de Gases de Efeito Estufa and http://seeg.eco.br/. |
| IBGE | `data/raw/ibge/` | Municipal boundaries, Amazon biome, agricultural census land-use and cattle outputs. | Manuscript cites IBGE (2017), Censo Agropecuario Tables 6882 and 6911. |
| SEAB-PR / DERAL via IPEA | `data/raw/seabpr/commodity_prices/`, `data/raw/ipea/farm_gate_price/` | Monthly deflated cattle-price series and farm-gate prices. | Manuscript Appendix A.8 cites SEAB-PR (2021), IPEA distributor, accessed February 22, 2021. |
| IPEA | `data/raw/ipea/distance_to_capital/` | Distance-to-state-capital regressor in agricultural productivity. | Public IPEA geographic/economic input; retain source table and access date when known. |
| WorldClim | `data/raw/worldclim/` | Historical precipitation and temperature regressors. | Manuscript Appendix C.1 cites Fick and Hijmans (2017); raw files are WorldClim 2.1, 2.5-minute rasters. |
| FGV IBRE | `data/raw/fgv/deflator_ipa/` | Deflator used in price preparation. | Public/third-party economic series; retain provider citation and terms. |
| World Bank Carbon Pricing Dashboard / carbon-price files | `data/raw/worldbank/carbon_price/` | Carbon-pricing source inputs used by data-cleaning scripts and contextual outputs. | Include source files in the final archive; retain provider terms and access date when known. |

#### Data Documentation and Codebook

This section reproduces the contents of `data/codebook.csv` so that the README
contains the full source and generated-data inventory.

| Section | Path | Provider or script | Description | Format | Notes |
| --- | --- | --- | --- | --- | --- |
| raw | `data/raw/esa/above_ground_biomass` | European Space Agency | Above-ground biomass raster inputs | raster | ESA Biomass CCI v3; manuscript Appendix A.2 uses 2017 data; retain access date when known |
| raw | `data/raw/fgv/deflator_ipa` | FGV IBRE | Deflator series for real price preparation | tabular | Provider terms remain with original source |
| raw | `data/raw/ibge` | IBGE | Municipal boundaries, Amazon biome, agricultural census, and cattle inputs | shapefile/csv/other | Cite IBGE datasets and years |
| raw | `data/raw/ipea` | IPEA | Farm-gate price and distance-to-capital inputs | tabular | Cite IPEA source tables |
| raw | `data/raw/mapbiomas` | MapBiomas | Land-use/cover, pasture quality, basins, and secondary vegetation age | raster/vector | MapBiomas Collection 5 in manuscript; retain access date when known |
| raw | `data/raw/seabpr/commodity_prices` | SEAB PR DERAL | Commodity price inputs | tabular | SEAB-PR 2021 via IPEA; manuscript reports access date February 22, 2021 |
| raw | `data/raw/seeg/emission` | SEEG | Emissions inputs | tabular | SEEG emissions; raw filename includes 2020.11.05 extract; retain access date when known |
| raw | `data/raw/worldbank` | World Bank | Carbon-price, emissions, and GDP inputs | tabular | Metadata for Figure 1 is in `replication/figure1/documentation` |
| raw | `data/raw/worldclim` | WorldClim | Temperature and precipitation rasters | raster | WorldClim 2.1, 2.5-minute rasters; cite Fick and Hijmans 2017 |
| processed | `data/processed` | `rsrc/processing/_masterfile.R` | Intermediate municipal, pixel, biomass, land-use, emissions, and raster summaries | mixed | Generated from raw inputs |
| clean | `data/clean` | `rsrc/cleaning/_masterfile.R` | Cleaned source-specific R and raster objects | mixed | Generated from raw inputs |
| calibration | `data/calibration/calibration_1043_sites.csv` | `rsrc/calibration/_masterfile.R` | Main 1043-site calibration panel | csv | Open-format companion to `calibration_1043_sites.Rdata` |
| calibration | `data/calibration/calibration_78_sites.csv` | `rsrc/calibration/_masterfile.R` | Main 78-site calibration panel | csv | Open-format companion to `calibration_78_sites.Rdata` |
| calibration | `data/calibration/grid_1043_sites.geojson` | `rsrc/calibration/_masterfile.R` | 1043-site spatial grid | geojson | Open spatial companion |
| calibration | `data/calibration/grid_78_sites.geojson` | `rsrc/calibration/_masterfile.R` | 78-site spatial grid | geojson | Open spatial companion |
| calibration | `data/calibration/productivity_params_1043.csv` | `rsrc/calibration/_masterfile.R` | Fitted `gamma_fit` and `theta_fit` values for 1043 sites | csv | Model input |
| calibration | `data/calibration/productivity_params_78.csv` | `rsrc/calibration/_masterfile.R` | Fitted `gamma_fit` and `theta_fit` values for 78 sites | csv | Model input |
| calibration | `data/calibration/distribution_parameters_all_1043.csv` | `rsrc/calibration/_masterfile.R` | Distribution parameter summaries for 1043 sites | csv | Model input |
| calibration | `data/calibration/distribution_parameters_all_78.csv` | `rsrc/calibration/_masterfile.R` | Distribution parameter summaries for 78 sites | csv | Model input |
| derived | `replication/derived` | `pysrc/replication` | Output-derived paper-number and price CSVs | csv | Generated during post-processing |
| raw | `replication/figure1/reference` | Fatos da Amazonia 2021 / Amazonia 2030 | Brazilian Amazon point used in Figure 1 | script constants/source note | Manuscript Figure 1 cites Fatos da Amazonia 2021 and www.amazonia2030.org |
| raw | `data/raw/mapbiomas/basin` | ANA / PNRH via MapBiomas | National Water Resources Plan basin layers used for basin random effects | shapefile | Manuscript Appendix C.1 cites level-2 ANA 2006 sub-basins available through MapBiomas |

#### Source Access Conditions

This table reproduces the source-level access and redistribution notes tracked
in `data/source_permissions.csv`.

| Source | Package locations | Access date or version | Redistribution status and notes |
| --- | --- | --- | --- |
| World Bank World Development Indicators and Carbon Pricing Dashboard | `data/raw/worldbank/`; `replication/figure1/input/` | Figure 1 World Bank data downloaded March 2021; retain exact raw-file metadata for other extracts | Public source; include exact archived extract in JPE package subject to World Bank terms. Used for GDP, emissions, and carbon-price contextual inputs. |
| Climate Watch / World Resources Institute | `replication/figure1/input/`; `data/raw/worldbank/emission_kuznets/` | Retain exact downloaded extract and metadata in final archive | Public source; final deposit should confirm current provider terms before publication. Used with World Bank inputs for Figure 1 emissions context. |
| Amazonia 2030 / Fatos da Amazonia 2021 | `replication/figure1/reference/` | 2021 report cited in manuscript | Public source; final deposit should confirm redistribution permission or cite source files as archived reference material. |
| MapBiomas Collection 5 and related products | `data/raw/mapbiomas/` | Collection 5 identified in manuscript; retain raw-file metadata in final archive | Public source; final deposit should verify MapBiomas terms and cite Collection 5. |
| ANA PNRH basin layers distributed through MapBiomas | `data/raw/mapbiomas/basin/` | ANA 2006 level-2 sub-basins noted in manuscript Appendix C.1 | Public administrative/geographic source. |
| ESA Biomass Climate Change Initiative | `data/raw/esa/above_ground_biomass/` | Biomass_cci v3; 2017 data used in manuscript Appendix A.2 | Public scientific data; include exact archived extract subject to ESA CCI data policy. Cite DOI 10.5285/5f331c418e9f4935b8eb1b836f8a91b8. |
| SEEG emissions and removals data | `data/raw/seeg/emission/` | Raw filename records 2020.11.05 extract | Public source; final deposit should verify SEEG terms and citation requirements. |
| IBGE 2017 Agricultural Census and geographies | `data/raw/ibge/` | 2017 Agricultural Census; Tables 6882 and 6911 cited in manuscript | Public Brazilian statistical/geographic data. |
| SEAB-PR / DERAL commodity prices via IPEA | `data/raw/seabpr/commodity_prices/`; `data/raw/ipea/farm_gate_price/` | Manuscript reports IPEA access date February 22, 2021 | Public source; final deposit should verify IPEA and SEAB-PR terms. |
| IPEA distance-to-capital table | `data/raw/ipea/distance_to_capital/` | Raw filename records 2023-08-21 extract | Public source; final deposit should verify IPEA terms. |
| WorldClim 2.1 | `data/raw/worldclim/` | WorldClim 2.1; 2.5-minute historical rasters | Public climate data; final deposit should verify WorldClim terms. Cite Fick and Hijmans 2017. |
| FGV IBRE deflator series | `data/raw/fgv/deflator_ipa/` | Retain exact raw-file metadata in final archive | Public/third-party economic series. |

#### Data References

The following data references are included here to make the replication package
self-contained. Provider-specific license and terms information should be
reviewed before the final JPE Dataverse deposit; the audit trail is maintained
in `data/source_permissions.csv`.

- Amazonia 2030. 2021. *Fatos da Amazonia 2021*. Amazonia 2030. URL:
  https://amazonia2030.org.br/. Used for the Brazilian Amazon point in Figure
  1. Access note: cited in the manuscript Figure 1 source note; retain the
  downloaded reference files under `replication/figure1/reference/`.
- Agencia Nacional de Aguas e Saneamento Basico (ANA). 2006. *National Water
  Resources Plan basin layers, level 2*. Distributed through MapBiomas basin
  inputs. URL: https://www.gov.br/ana/. Used for basin groups in Appendix C.1.
- European Space Agency Climate Change Initiative Biomass Project. 2021. *ESA
  Biomass Climate Change Initiative (Biomass_cci): Global Datasets of Forest
  Above-Ground Biomass for the Years 2010, 2017 and 2018, v3*. NERC EDS
  Centre for Environmental Data Analysis. DOI: 10.5285/5f331c418e9f4935b8eb1b836f8a91b8.
  URL: https://climate.esa.int/en/projects/biomass/. Used for 2017
  above-ground biomass inputs.
- Fick, Stephen E., and Robert J. Hijmans. 2017. "WorldClim 2: New 1-km
  Spatial Resolution Climate Surfaces for Global Land Areas." *International
  Journal of Climatology* 37 (12): 4302-4315. DOI: 10.1002/joc.5086.
  Project URL: https://www.worldclim.org/. The package uses WorldClim 2.1,
  2.5-minute historical temperature and precipitation rasters.
- Fundacao Getulio Vargas, Instituto Brasileiro de Economia (FGV IBRE).
  Deflator series used for price preparation. URL: https://portalibre.fgv.br/.
  Access note: retain exact raw files and access metadata in the final archive.
- Instituto Brasileiro de Geografia e Estatistica (IBGE). 2017. *Censo
  Agropecuario 2017*, including Tables 6882 and 6911, and associated municipal
  and biome geographies. URL: https://www.ibge.gov.br/. Used for agricultural
  census, cattle, municipal boundary, and Amazon biome inputs.
- Instituto de Pesquisa Economica Aplicada (IPEA). Ipeadata tables for
  distance-to-capital and farm-gate or commodity-price inputs. URL:
  https://www.ipeadata.gov.br/. Access notes: the manuscript reports SEAB-PR
  price data distributed through IPEA were accessed on February 22, 2021; the
  distance raw filename records an August 21, 2023 extract.
- MapBiomas Project. *Collection 5 Annual Land Cover and Land Use Maps of
  Brazil* and related MapBiomas products. URL: https://mapbiomas.org/. Used for
  land-use/cover, total available area, agricultural area, deforestation,
  secondary vegetation age, pasture quality, and basin inputs. See also Souza
  Jr. et al. (2020), cited in the manuscript.
- Secretaria da Agricultura e do Abastecimento do Parana, Departamento de
  Economia Rural (SEAB-PR/DERAL). 2021. Commodity price series distributed
  through IPEA. URL: https://www.agricultura.pr.gov.br/. Used for monthly
  cattle-price inputs; manuscript Appendix A.8 reports access through IPEA on
  February 22, 2021.
- Sistema de Estimativas de Emissoes e Remocoes de Gases de Efeito Estufa
  (SEEG). Greenhouse-gas emissions and removals data. URL: https://seeg.eco.br/.
  Used for agricultural net emissions and emissions calibration; raw filenames
  record a 2020.11.05 extract.
- Souza Jr., Carlos M., Julia Z. Shimbo, Marcos R. Rosa, Leandro L. Parente,
  Ane A. Alencar, Bernardo F. T. Rudorff, Heinrich Hasenack, et al. 2020.
  "Reconstructing Three Decades of Land Use and Land Cover Changes in Brazilian
  Biomes with Landsat Archive and Earth Engine." *Remote Sensing* 12 (17):
  2735. DOI: 10.3390/rs12172735. Cited by the manuscript for MapBiomas.
- World Bank. World Development Indicators and World Bank source files used for
  Figure 1, GDP per capita, emissions, and carbon-pricing inputs. URLs:
  https://data.worldbank.org/, https://databank.worldbank.org/source/world-development-indicators,
  and https://carbonpricingdashboard.worldbank.org/. Access note: manuscript
  Figure 1 reports World Bank data were downloaded in March 2021.
- World Resources Institute. Climate Watch data used with World Bank inputs for
  Figure 1 emissions context. URL: https://www.climatewatchdata.org/. Access
  note: retain exact downloaded extracts and metadata under `replication/figure1/`
  and `data/raw/worldbank/`.

Generated data and metadata. The archive includes `data/processed/`, `data/clean/`, and `data/calibration/` as generated analysis inputs. Some R scripts read `.Rdata` files directly. Where practical, the package includes open-format companions: for example, `calibration_1043_sites.Rdata` has `calibration_1043_sites.csv` and `grid_1043_sites.geojson`; `calibration_78_sites.Rdata` has `calibration_78_sites.csv` and `grid_78_sites.geojson`; carbon and productivity calibration objects have `gamma_fit_*.geojson`, `theta_fit_*.geojson`, and related CSV files. Machine-readable mirrors are in `data/codebook.csv` and `data/source_permissions.csv`; final archive inclusion/exclusion decisions are summarized in `replication/package_manifest.csv`.

Main calibration variables. `data/calibration/calibration_1043_sites.csv` and
`data/calibration/calibration_78_sites.csv` contain the site-level analysis
variables used by the model and post-processing scripts.

| Variable or pattern | Meaning |
| --- | --- |
| `id` | Site identifier. |
| `share_agricultural_use_*`, `share_forest_*`, `share_other_*` | Land-cover shares by year. |
| `site_area_ha` | Site area in hectares. |
| `share_amazon_biome`, `area_amazon_biome` | Amazon biome share and area. |
| `z_1995`, `z_2008`, `z_2017` | Calibrated state variables derived from agricultural-use area. |
| `zbar_1995`, `zbar_2008`, `zbar_2017` | Site-level benchmark land/carbon-stock quantities. |
| `gamma`, `gamma_fit` | Carbon recovery or sequestration response parameters and fitted values. |
| `theta`, `theta_fit` | Agricultural productivity parameters and fitted values. |
| `x_1995`, `x_2008`, `x_2017` | Forest carbon-stock allocation variables. |
| `alpha` | Carbon accumulation speed parameter. |
| `delta` | Discount rate used in the calibration and value calculations; default is 0.02. |
| `kappa` | Net emissions conversion factor. |
| `zeta`, `zeta_alt` | Adjustment-cost calibration values. |
| `mean_pa_2017` | Agricultural price input used in calibration. |
| `pasture_area_2017` | Pasture area input. |

The analysis scripts are the authoritative source for transformations from raw
variables to model variables. Run `./run.sh --steps stage-data --backend local`
to rebuild generated data products from raw inputs.

1. Create the data folder:

   ```bash
   mkdir -p data
   ```

2. Download the `raw` data folder from the link above.

3. Move `raw` into `data/`, so the final structure is:

   ```text
   data/raw/
     esa/
     fgv/
     ibge/
     ipea/
     mapbiomas/
     seabpr/
     seeg/
     worldbank/
     worldclim/
   ```

   If the download also includes prepared `processed`, `clean`, or `calibration`
   folders, place them under `data/` with the same folder names.

4. Generate processed, cleaned, and calibration data when starting from raw
   inputs. This stage also builds the Python-only Figure 1 output from the
   World Bank inputs included in the repository under `replication/figure1/`:

   ```bash
   ./run.sh --steps stage-data --backend local
   ```
   In the completed local replication logs, the full R data-processing stage took about 4 hours. The Python-only Figure 1 step took only a few seconds.

   If the server has R available, the same data step can be submitted to Slurm
   with:

   ```bash
   ./run.sh --steps stage-data --backend slurm --slurm-account pi-<pi_account_name> --run-r-on-slurm
   ```

   If the server does not have R, run the R data-processing part locally and sync
   the generated `data/processed/`, `data/clean/`, and `data/calibration/` folders
   to the server before starting non-R Slurm stages. The `figure1` step itself can
   run locally or on Slurm because it uses Python only.

   The full workflow assumes these data outputs exist before estimation,
   optimization, and post-processing steps are run.

### Step 3. Run the Whole Project

The single driver is `run.sh`. It runs commands locally by default and saves
local command logs under `job-outs/`.

#### 3.1 Local Machine

1. Run the full workflow in one command when you are comfortable letting the
   machine run for a long time:

```bash
./run.sh --steps all --backend local --jobs 1
```

A full local run is useful for transparency but is not recommended for the heavy
HMC and MPC stages unless the machine can run for many days. The server workflow
is the intended route for `stage-hmc`, `stage-mpc`, and `stage-time-consistency`.

2. Or run the workflow in shorter local stages, which is easier to monitor:

```bash
./run.sh --steps stage-data --backend local
./run.sh --steps stage-hmm --backend local --jobs 2
./run.sh --steps stage-deterministic --backend local --jobs 2
./run.sh --steps stage-time-consistency --backend local --jobs 2
./run.sh --steps stage-hmc --backend local --jobs 2
./run.sh --steps stage-mpc --backend local --jobs 2
./run.sh --steps stage-postprocess --backend local
```

3. If you ran the heavy computations elsewhere and only need to refresh the final replication outputs locally, run:

   ```bash
   ./run.sh --steps maps hmc-maps --backend local --jobs 1
   ./run.sh --steps postprocess-only --backend local
   ```

4. For long local stages, run inside `tmux` and use macOS `caffeinate` so the
   job continues if the terminal window is closed and the machine does not
   sleep:

   ```bash
   brew install tmux
   tmux new -s amazon
   caffeinate -dimsu ./run.sh --steps stage-deterministic --backend local --jobs 4
   ```

   Detach from the tmux session with `Ctrl-b` then `d`, and return later with:

   ```bash
   tmux attach -t amazon
   ```

#### 3.2 Slurm Server

1. Use the same driver on Slurm. The server backend uses the same stage aliases
   and command lists as the local backend. The only intentional difference is
   that `Rscript` commands are skipped on Slurm unless `--run-r-on-slurm` is
   supplied.

2. On Midway, Slurm may require an account on every `sbatch` submission. Check
   the account available to your user, then either export it once or pass it to
   `run.sh`:

   ```bash
   sacctmgr show assoc user=$USER format=Account,Partition,QOS%30
   export REPLICATION_SLURM_ACCOUNT="pi-<pi_account_name>"
   ```

   The same setting can be supplied inline:

   ```bash
   ./run.sh --steps stage-hmm --backend slurm --slurm-account pi-<pi_account_name>
   ```

   If your allocation uses a specific partition, also set
   `REPLICATION_SLURM_PARTITION` or pass `--slurm-partition`.

3. Large non-MPC parallel steps can be grouped on Slurm when a step has at
   least `--slurm-group-min-commands` runnable commands. Each grouped Slurm job
   runs `--slurm-commands-per-job` replication commands sequentially, while each
   command still gets its own numbered `*_run.out` and `*_run.err`. The command
   line is written at the top of each `*_run.out` for auditing.

   The completed MPC outputs in this package were generated with one replication
   command per Slurm job for the large MPC steps, including `mpc-sp-grid`,
   `mpc-hmc-pre-unconstrained`, `mpc-hmc-figure14-unconstrained`, and `mpc-day0-*`. This
   keeps each MPC output and log isolated, but it submits many jobs. If a cluster
   has strict job-submission limits, one feasible adjustment is to group the five
   transfer commands `b=0,10,15,20,25` for each `(model, xi, id, trig)` case by
   increasing `MPC_COMMANDS_PER_GROUP` in `pysrc/scripts/run_replication.py`,
   then inspecting the plan with `--dry-run` before submission.

   To group non-MPC large steps, use for example:

   ```bash
   ./run.sh --steps stage-hmc --backend slurm --slurm-account pi-<pi_account_name> --slurm-commands-per-job 25
   ```

   Use a smaller value if grouped jobs are close to the Slurm time limit, or
   `--slurm-commands-per-job 1` to submit one Slurm job per command. To change
   the threshold for what counts as a large step, use `--slurm-group-min-commands`.

4. If the server does not have R, run the R data step locally first, then sync
   `data/processed/`, `data/clean/`, and `data/calibration/` to the server.
   Submit the non-R computation stages on the server with:

   ```bash
   ./run.sh --steps stage-hmm stage-deterministic stage-time-consistency stage-hmc stage-mpc --backend slurm --slurm-account pi-<pi_account_name>
   ```

   This submits the non-R computation jobs at once, but step order is preserved
   through Slurm dependencies. Commands inside parallel-safe steps are submitted
   together; later steps wait for upstream jobs to finish successfully. After
   these jobs finish, sync the outputs back to the local machine, run
   `maps hmc-maps`, and then run `postprocess-only` so the final audit includes
   the R figures.

5. If prepared data already exist on the server but R is not available, this is
   also valid. It skips `Rscript` steps and runs the Python/Gurobi/CmdStan
   parts:

   ```bash
   ./run.sh --steps all --backend slurm --slurm-account pi-<pi_account_name>
   ```

6. If the server has R and the R environment has been restored there, submit the
   complete workflow including R data and plot steps with:

   ```bash
   ./run.sh --steps all --backend slurm --slurm-account pi-<pi_account_name> --run-r-on-slurm
   ```

7. Before submitting a long server run, inspect the exact Slurm plan:

   ```bash
   ./run.sh --steps stage-hmm stage-deterministic stage-time-consistency stage-hmc stage-mpc --backend slurm --slurm-account pi-<pi_account_name> --dry-run
   ./run.sh --steps all --backend slurm --slurm-account pi-<pi_account_name> --run-r-on-slurm --dry-run
   ```

8. Monitor submitted jobs with:

   ```bash
   squeue -u $USER
   sacct -u $USER --format=JobID,JobName,State,ExitCode
   ```

9. After Slurm jobs finish, sync `job-outs/`, `output/`, `plots/`, and
   `replication/derived/` back to the local machine. If R was skipped on the
   server, run the R plot steps and final audit locally:

   ```bash
   ./run.sh --steps maps hmc-maps --backend local --jobs 1
   ./run.sh --steps postprocess-only --backend local
   ```

10. Slurm writes driver logs to the same stage folders as local runs, for
   example `job-outs/stage_deterministic/shadow_prices_det/0001_run.out`.
   When submitting stages separately on Slurm, wait for one stage to finish
   before starting the next, because dependencies are tracked only within one
   `run.sh` invocation.

#### 3.3 Stage Notes

1. `stage-data` runs the R data-processing driver and the Python-only Figure 1
   reproduction. On Slurm without R, the R command is skipped unless
   `--run-r-on-slurm` is supplied, but `figure1` can still run.

2. `stage-deterministic` runs only the deterministic parameter-ambiguity shadow
   prices (`xi=\infty`, represented in code as `xi=10000`) before refreshing
   `replication/derived/carbon_prices.csv`.

3. `stage-hmc` runs the finite-`xi` shadow prices (`xi=0.5,1,2`), refreshes
   the same carbon-price file, generates the HMC sampling outputs for the
   selected `P^{ee}` plus transfer levels, and then constructs HMC tables and
   figures. After HMC sampling, it also runs `relative-entropy` to create
   `output/figures/entropy/site_1043/xi1.0/kl_divergences_theta_gamma.csv`
   and `density_sites_from_relative_entropy.csv`; the latter selects the
   density-plot sites from the top KL-divergence sites before HMC density
   figures are regenerated, and Figure 17 reads the former. For `xi=1`, the
   sampling step also generates the deterministic `P^{ee}` case used by the
   common-price HMC figures; both prices are read from
   `replication/derived/carbon_prices.csv`. Each HMC sampling command is one
   `(xi, price source, transfer)` job, so
   `b=0,10,15,20,25` can run in parallel instead of being bundled into one long
   job.

4. The Slurm backend skips `Rscript` commands by default because the server may
   not have R installed. Add `--run-r-on-slurm` only when R is available and the
   R environment has been restored on the server.

5. `stage-time-consistency` runs the carrot-policy time-consistency evidence
   jobs for `bf=3.75` and `bf=5` at 1043 sites. These jobs are independent and
   can run in parallel. They write cached optimization objects and auditable
   summaries under `output/time_consistency/bf_*/`.

6. `stage-mpc` first creates MPC simulation paths, then runs the MPC
   shadow-price optimization grid (`xi=0.5,1,10000`, `P^{ee}=5.0,...,7.0`,
   constrained and unconstrained) before `mpc-prices` parses those grid outputs.
   The grid jobs are parallel-safe and are required before
   `pysrc/mpc/mpc_compute_sp.py` can read `output/optimization/mpc_shadow_price/`.
   By default, each grid job recomputes and overwrites its output folder, matching
   the original scripts and avoiding mixed old/new shadow-price outputs.
   After the MPC carbon prices are derived, the driver runs the unconstrained
   MPC-HMC pre/day-0/table/figure block first, then runs the constrained
   day-0/table block. The constrained MPC-HMC pre and constrained probability
   steps are not part of the current replication workflow. The driver uses the
   explicit unconstrained step names for MPC-HMC pre, MPC probabilities, Figure
   14 simulations, and MPC figures. Tables 6, 8, 12, 19,
   and 21 are reconstructed from day-0 outputs; Table 18 additionally uses
   simulation rows from `mpc_compute.py`, so those rows run only after the
   unconstrained Figure 14 MPC-HMC simulation jobs. Figure 14 is generated only
   from the unconstrained MPC-HMC jobs.
   The completed MPC Slurm outputs were generated with one replication command
   per Slurm job, so each MPC output and numbered log is isolated. To reduce job
   count on a constrained cluster, consider grouping the five transfer commands
   for each `(model, xi, id, trig)` case by increasing `MPC_COMMANDS_PER_GROUP`
   in `pysrc/scripts/run_replication.py` and checking the result with
   `--dry-run`.

7. `stage-postprocess` runs after `stage-mpc` and is intentionally separate
   from the heavy MPC jobs. Carbon prices are derived earlier, immediately
   after the shadow-price and MPC price-search outputs that downstream steps
   need. The final stage refreshes MPC transition probabilities, paper-number
   audit manifests, results-in-paper tables, and results-in-paper figures.

   The computational dependencies are intentionally one-way: downstream scripts
   read `replication/derived/carbon_prices.csv`,
   `replication/derived/mpc_transition_probabilities.csv`, `output/`, and
   `plots/`; they do not require manual edits to paper tables. Within a single
   Slurm invocation, the driver submits later stages with dependencies so they
   wait for earlier stages to finish successfully.

8. The first HMC/shadow-price job on a machine may compile
   `stan_model/adjusted` from `stan_model/adjusted.stan`. Parallel server jobs
   use a compile lock so only one job compiles at a time; other jobs wait and
   then reuse the executable. If a previous failed run left partial compilation
   files, remove them before resubmitting:

   ```bash
   rm -f stan_model/adjusted stan_model/adjusted.o stan_model/adjusted.hpp stan_model/adjusted.compile.lock
   ```

### Step 4. Process Generated Raw Results and Check Paper Outputs

After model jobs have produced raw outputs in `job-outs/`, `output/`, and
`plots/`, run the post-processing chain and lightweight replication audit:

```bash
./run.sh --steps postprocess-only --backend local
```

This expands to:

```text
mpc-probabilities-unconstrained
postprocess-final
results-in-paper-figures
```

Those steps do the following:

- `pysrc/replication/derive_mpc_transition_probabilities.py` parses
  stage-specific numbered MPC-HMC logs such as
  `job-outs/stage_mpc/mpc_hmc_*/*_run.out`
  and writes
  `replication/derived/mpc_transition_probabilities.csv`.
- `pysrc/replication/build_paper_numbers.py` writes
  `replication/exhibit_manifest.csv`, `replication/paper_numbers.csv`, and
  `replication/paper_numbers_missing_summary.csv`.
- `pysrc/replication/build_results_in_paper.py` refreshes
  `results_in_paper/Table<number>_*.tex`, `results_in_paper/Figure<number>_*`,
  `replication/results_in_paper_table_manifest.csv`, and
  `replication/results_in_paper_figure_manifest.csv`.

The post-processing scripts do not read values from the manuscript PDF. Reported
numbers are extracted from generated outputs and logs.
If you need to regenerate the MPC day-0 table files first, run
`mpc-tables-unconstrained` and/or `mpc-tables-constrained` before
`postprocess-final`.

After the command finishes, check these generated files:

```text
replication/exhibit_manifest.csv
replication/paper_numbers.csv
replication/paper_numbers_missing_summary.csv
replication/results_in_paper_table_manifest.csv
replication/results_in_paper_figure_manifest.csv
results_in_paper/
```

If `paper_numbers_missing_summary.csv` reports missing outputs, generate the
upstream outputs listed in `replication/exhibit_manifest.csv`, then rerun:

```bash
./run.sh --steps postprocess-only --backend local
```

The workflow is self-contained and does not require a manuscript TeX or PDF
outside the repository. The optional `--paper-tex` argument in the build scripts
is only for maintainers who intentionally want to refresh
`replication/paper_figure_inputs.csv`.

#### Output Manifest: Tables and Figures

The JPE report noted that the README should identify which programs generate
the paper tables and figures. The generated audit CSVs
`replication/results_in_paper_figure_manifest.csv`,
`replication/results_in_paper_table_manifest.csv`, and
`replication/paper_numbers_missing_summary.csv` contain file-level manifests;
the table below records the program and line-number mapping checked by JPE.

| Exhibit | Program | Line number(s) | JPE check |
| --- | --- | --- | --- |
| Figure 1 | `pysrc/scripts/figure1.py` | 166 | Reproduced |
| Figure 2 | `rsrc/analysis/carbon_capture_curves/02_analysis.R` | 68 | Reproduced |
| Figure 3a | `rsrc/analysis/calibration_maps_1043_sites.R` | 104 | Reproduced |
| Figure 3b | `rsrc/analysis/calibration_maps_1043_sites.R` | 195 | Reproduced |
| Figure 4a | `rsrc/analysis/calibration_maps_1043_sites.R` | 225 | Reproduced |
| Figure 4b | `rsrc/analysis/calibration_maps_1043_sites.R` | 246 | Reproduced |
| Figure 5a | `pysrc/analysis/figures.py` | 116 | Reproduced |
| Figure 5b | `pysrc/analysis/figures.py` | 161 | Reproduced |
| Figure 6 | `pysrc/analysis/figures.py` | 557 | Reproduced |
| Figure 7 | `rsrc/analysis/map_1043_det.R` | 305 | Reproduced |
| Figure 8 | `rsrc/analysis/map_1043_det.R` | 353 | Reproduced |
| Figure 9a | `pysrc/analysis/figures.py` | 374 | Reproduced |
| Figure 9b | `pysrc/analysis/figures.py` | 313 | Reproduced |
| Figure 9c | `pysrc/analysis/figures.py` | 404 | Reproduced |
| Figure 9d | `pysrc/analysis/figures.py` | 344 | Reproduced |
| Figure 10 | `pysrc/analysis/map.py` | 114 | Reproduced |
| Figure 11 | `pysrc/analysis/figures.py` | 482 | Reproduced |
| Figure 12a | `pysrc/analysis/map.py` | 114 | Reproduced |
| Figure 12b | `pysrc/analysis/map.py` | 114 | Reproduced |
| Figure 13a | `pysrc/analysis/figures.py` | 483 | Reproduced |
| Figure 13b | `pysrc/analysis/figures.py` | 483 | Reproduced |
| Figure 14a | `pysrc/scripts/mpc_trajectory.py` | 117 | Reproduced |
| Figure 14b | `pysrc/scripts/mpc_trajectory.py` | 117 | Reproduced |
| Figure 15 | `pysrc/scripts/deterministic_delta_sensitivity.py` | 396 | Reproduced |
| Figure 16a | `pysrc/scripts/price_estimation.py` | 130 | Reproduced |
| Figure 16b | `pysrc/scripts/price_estimation.py` | 130 | Reproduced |
| Figure 17a | `rsrc/analysis/map_kl.R` | 352 | Reproduced |
| Figure 17b | `rsrc/analysis/map_kl.R` | 366 | Reproduced |
| Figure 17c | `rsrc/analysis/map_kl.R` | 359 | Reproduced |
| Figure 17d | `rsrc/analysis/map_kl.R` | 373 | Reproduced |
| Figure 18a | `pysrc/analysis/figures.py` | 374 | Reproduced |
| Figure 18b | `pysrc/analysis/figures.py` | 313 | Reproduced |
| Figure 18c | `pysrc/analysis/figures.py` | 404 | Reproduced |
| Figure 18d | `pysrc/analysis/figures.py` | 344 | Reproduced |
| Figure 19a | `pysrc/analysis/figures.py` | 374 | Reproduced |
| Figure 19b | `pysrc/analysis/figures.py` | 313 | Reproduced |
| Figure 19c | `pysrc/analysis/figures.py` | 404 | Reproduced |
| Figure 19d | `pysrc/analysis/figures.py` | 344 | Reproduced |
| Figure 20 | `rsrc/analysis/map_1043_hmc_xi1.R` | 317 | Reproduced |
| Figure 21 | `rsrc/analysis/map_1043_hmc_xi05.R` | 298 | Reproduced |
| Figure 22a | `pysrc/scripts/bayesian_R2.py` | 70 | Reproduced |
| Figure 22b | `pysrc/scripts/bayesian_R2.py` | 108 | Reproduced |
| Table 1 | `pysrc/replication/derive_carbon_prices.py` | 275 | Reproduced |
| Table 2 | `pysrc/analysis/tables.py` | 136 | Reproduced |
| Table 3 | `pysrc/analysis/tables.py` | 253 | Reproduced |
| Table 4 | `pysrc/analysis/tables.py` | 454 | Reproduced |
| Table 5 | `pysrc/replication/derive_carbon_prices.py` | 275 | Reproduced |
| Table 6 | `pysrc/mpc/mpc_compute_day0.py` | 462 | Reproduced |
| Table 7 | `pysrc/replication/derive_mpc_transition_probabilities.py` | 305 | Reproduced |
| Table 8 | `pysrc/mpc/mpc_compute_day0.py` | 462 | Reproduced |
| Table 9 | `pysrc/replication/derive_mpc_transition_probabilities.py` | 305 | Reproduced |
| Table 10 | `pysrc/scripts/price_estimation.py` | 263 | Reproduced |
| Table 11 | `pysrc/scripts/price_estimation.py` | 267 | Reproduced |
| Table 12 | `pysrc/mpc/mpc_compute_day0.py` | 462 | Reproduced |
| Table 13 | `pysrc/analysis/tables.py` | 136 | Reproduced |
| Table 14 | `pysrc/analysis/tables.py` | 258 | Reproduced |
| Table 15 | `pysrc/analysis/tables.py` | 258 | Reproduced |
| Table 16 | `pysrc/analysis/tables.py` | 454 | Reproduced |
| Table 17 | `pysrc/analysis/tables.py` | 454 | Reproduced |
| Table 18 | `pysrc/mpc/mpc_compute_day0.py`; `pysrc/mpc/mpc_compute.py` | 462; 178 | Reproduced |
| Table 19 | `pysrc/mpc/mpc_compute_day0.py` | 462 | Reproduced |
| Table 20 | `pysrc/replication/derive_mpc_transition_probabilities.py` | 305 | Reproduced |
| Table 21 | `pysrc/mpc/mpc_compute_day0.py` | 462 | Reproduced |
| Table 22 | `pysrc/replication/derive_mpc_transition_probabilities.py` | 305 | Reproduced |
| Table 23 | `pysrc/sampling/baseline.py` | 127 | Reproduced |
| Table 24 | `pysrc/sampling/baseline.py` | 116 | Reproduced |
| Table 25 | `pysrc/sampling/baseline.py` | 149 | Reproduced |

#### In-Text Numbers Not Tied to Tables or Figures

The JPE report identified five in-text items that were not tied to a table or
figure in the earlier code description. The current replication evidence is:

| Manuscript location | Number or claim | Replication evidence |
| --- | --- | --- |
| Page 17, Footnote 28 | `R-squared = 0.66` | The deterministic maps step prints this diagnostic in `job-outs/stage_deterministic/maps/0001_run.out`: `R2 = 0.6601009`, which rounds to 0.66. The value is produced by `rsrc/analysis/carbon_capture_curves/_masterfile.R` during `stage-deterministic` `maps`. |
| Page 18 | `correlation = -0.27` | Verified by `pysrc/scripts/productivity_correlation.py`, which reads `data/calibration/productivity_params_1043.csv` and prints `Pearson correlation between gamma_fit and theta_fit = -0.2721352239863349`, which rounds to -0.27 in the `job-outs/stage_hmm/baseline/0003_run.out`. |
| Page 24, Footnote 35 | Future trajectories do not change much when moving from 2 percent to 3 percent | `stage-deterministic` re-solves deterministic `P^ee` under `delta=0.03` with one parallel job per candidate price before the `maps` step, derives the selected price, and compares baseline trajectories using `P^ee_{0.02}+b` with sensitivity trajectories using `P^ee_{0.03}+b`: `output/delta_sensitivity/delta_0p03/figures/pred_zshare_delta_comparison_1043_sites_det_delta_0p03.png`  |
| Page 38 | `b = 25`, `b_f = .15b`, `tau_f = 15`, no defection in 100 years | Verified by the time-consistency output. The implementation uses `total_transfer=25.0`, `bf=3.75`, and `b=21.25` in `pysrc/scripts/time_consistency.py`. Run `python pysrc/scripts/time_consistency.py --bf 3.75 --sites 1043`; the row with `tau_f=15` in `output/time_consistency/bf_3p75/time_consistency_summary.csv` has `never_defects=True` and blank first-defection-year columns. |
| Page 39, Footnote 43 | Case labeled "same" in the report | The deterministic stage log records the limiting case used for this statement. In `job-outs/stage_deterministic/deterministic/0001_run.out`, the `b=25`, `pe=31.8` run prints `Max z_i at t=100 (b=25, pe=31.8) = 2.11862458142161e-11 billion ha (0.0211862458142161 ha), site=1028`, indicating an effectively zero terminal value at the site level. |

### Step 5. Logs, Parallelism, and Dry Runs

Local and Slurm driver logs are saved under `job-outs/`, grouped first by
replication stage and then by step. Step folders use only the step name; the
per-command files keep their numeric prefixes:

```text
job-outs/
  stage_deterministic/
    shadow_prices_det/
      0001_run.out
      0001_run.err
      0002_run.out
      0002_run.err
  stage_hmc/
    shadow_prices_hmc/
      0001_run.out
      0001_run.err
  stage_mpc/
    mpc_prepare/
      0001_run.out
      0001_run.err
```

When `run.sh` starts, it safely renames older two-digit step folders such as
`16_postprocess_final` to `postprocess_final`. If the unprefixed folder already
exists, the old folder is skipped instead of being moved inside it.

MPC-HMC child output is written directly into the same stage-specific numbered
logs shown above; the driver does not create nested `job-outs/mpc/.../run.out`
files. The driver generates and submits Slurm batch scripts through `sbatch` at run time. The generated batch script is defined in `slurm_batch_command()`. Slurm driver-level `out`/`err` files use the same stage folders shown above.
Slurm creates and writes those files only after the scheduled job actually
starts, so a pending job may have no `Program starts` line yet. New Slurm
submissions set `PYTHONUNBUFFERED=1`, so Python progress is written to logs
while the command is running instead of waiting for process exit.
For grouped Slurm submissions, the group-level files are named like
`group_0001_0001_0010.out` and print the group start/end; each command inside
the group still writes the numbered files shown above with its own command
start/end. The group log also prints which numbered command is currently
running.
Running an individual named step also uses its canonical stage folder; for
example, `./run.sh --steps maps --backend local` writes to
`job-outs/stage_deterministic/maps/`.

To inspect commands without running them:

```bash
./run.sh --steps all --dry-run
```

To choose a subfolder under `job-outs/` for local logs:

```bash
./run.sh --steps stage-mpc --backend local --local-log-dir stage_mpc_logs
```

That command writes logs under `job-outs/stage_mpc_logs/stage_mpc/...`.

To stream output directly to the terminal:

```bash
./run.sh --steps postprocess-only --backend local --no-local-logs
```

To choose local `--jobs`, first check your machine:

```bash
python -c "import os; print(os.cpu_count())"
python -c "import os; print(round(os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / 1024**3, 1), 'GB')"
```

Start with `--jobs 1` or `--jobs 2` for memory-heavy HMC/MPC stages. Increase
only if CPU and memory pressure stay comfortable.

Available step names:

```text
data
figure1
price-estimation
baseline
shadow-prices
shadow-prices-det
shadow-prices-det-delta-sensitivity
shadow-prices-hmc
derive-prices
derive-prices-det
derive-prices-det-delta-sensitivity
derive-prices-hmc
derive-prices-mpc
deterministic
deterministic-delta-sensitivity
time-consistency
hmc-sampling
hmc-neutral-sampling
hmc
relative-entropy
hmc-maps
mpc-prepare
mpc-sp-grid
mpc-prices
mpc-hmc-pre-unconstrained
mpc-probabilities-unconstrained
mpc-day0
mpc-day0-unconstrained
mpc-day0-constrained
mpc-tables
mpc-tables-unconstrained
mpc-tables-constrained
mpc-simulation-tables-unconstrained
mpc-hmc-figure14-unconstrained
mpc-figures-unconstrained
results-in-paper-figures
bayesian-r2
maps
postprocess-final
postprocess-only
stage-data
stage-hmm
stage-deterministic
stage-time-consistency
stage-hmc
stage-mpc
stage-postprocess
all
```

Server module defaults can be tuned without editing code:

```bash
REPLICATION_SLURM_ACCOUNT="pi-<pi_account_name>"
REPLICATION_MODULES="python/anaconda-2022.05 gurobi/11.0 gcc/12.2.0"
REPLICATION_SLURM_TIME="1-11:00:00"
REPLICATION_SLURM_CPUS="8"
REPLICATION_SLURM_MEM="32G"
REPLICATION_SLURM_PARTITION="<partition-name>"
REPLICATION_SLURM_COMMANDS_PER_JOB="10"
REPLICATION_SLURM_GROUP_MIN_COMMANDS="1"
```

The clean replication branch uses `run.sh` as the single entry point for both
local and Slurm runs.

### Step 6. Reproducibility Notes

- Downstream scripts read `P^{ee}` from
  `replication/derived/carbon_prices.csv`; do not manually edit `pee` values.
- `pysrc/replication/derive_mpc_transition_probabilities.py` finds
  `year done: 1` in each MPC log, reads the immediately preceding
  `Parameters from current iteration` vector, uses the second-to-last entry as
  `low -> low`, and uses one minus the last entry as `high -> high`.

### Color vector PDFs readable in grayscale (1200 dpi export)

The paper plotting code exports color PDFs with line styles, markers, and
ordered-lightness map palettes that remain readable in grayscale. Export
resolution is 1200 dpi for PNGs and rasterized elements; PDF vectors remain
resolution-independent.
To redraw from existing results without rerunning optimization, HMC, or HMM estimation:

```bash
.venv/bin/python -m pysrc.scripts.redraw_paper_figures --collect
```

This command defaults to PDF only and preserves the original PNGs in
`results_in_paper/`. Use `--list` to inspect commands, or `--groups` to redraw
selected figure groups. See [PDF figure rerun list](replication/PDF_FIGURES.md)
for the figure-to-code mapping, R environment options, and cached-input details.

### Rights and License

The code written for this replication package is released under the MIT License;
see `LICENSE.txt`. Author-created derived data, tables, figures, manifests, and
documentation are released for academic replication under the terms stated in
`LICENSE.txt`. Third-party raw data in `data/raw/` remain subject to the terms of
the original providers listed above and in `data/codebook.csv`; they are included
in the journal archive only to allow exact replication of the reported results.
Users who reuse the raw sources outside replication should consult and follow the
original providers' licenses and citation requirements.

The authors certify that they have legitimate access to the data analyzed in
this manuscript. The authors also certify that they have documented permission
to redistribute or publish the data contained within this replication package
to the extent stated in `LICENSE.txt`; third-party raw data remain subject to
their original provider terms.
