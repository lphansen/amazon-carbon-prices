import argparse
import json
import re
import numpy as np
import pandas as pd
import os
from hmmlearn import hmm
from scipy.linalg import logm, expm
import warnings
import contextlib
import sys
import os
import time
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pysrc.analysis.publication import LINE_WIDTH, save_publication_figure
from pysrc.services.file_service import get_path

Path("output/tables").mkdir(parents=True, exist_ok=True)
Path("output/figures").mkdir(parents=True, exist_ok=True)

@contextlib.contextmanager
def suppress_output():
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


def log(message):
    print(f"[price-estimation] {message}", flush=True)


def format_latex_table(result_uncon, result_con):
    _, _, _, mus_uncon, sigmas_uncon, _, _, _, P_uncon = result_uncon
    _, _, _, mus_con, sigmas_con, _, _, _, P_con = result_con

    table = r"""\begin{tabular}{cccccc}
\toprule
&\multicolumn{2}{c}{distinct variances} & &\multicolumn{2}{c}{a common variance} \\
\midrule
& low price & high price & & low price & high price \\
"""
    table += f" & {mus_uncon[0]:.2f} & {mus_uncon[1]:.2f} & & {mus_con[0]:.2f} & {mus_con[1]:.2f} \\\\\n"
    table += f"s.d. & {sigmas_uncon[0]:.3f} & {sigmas_uncon[1]:.3f} & & {sigmas_con[0]:.3f} & {sigmas_con[1]:.3f} \\\\\n"
    table += r"""\midrule
& & & transition probabilities & & \\
& low & high & & low & high \\
"""
    table += f"low  & {P_uncon[0,0]:.3f} & {P_uncon[0,1]:.3f} & & {P_con[0,0]:.3f} & {P_con[0,1]:.3f} \\\\\n"
    table += f"high & {P_uncon[1,0]:.3f} & {P_uncon[1,1]:.3f} & & {P_con[1,0]:.3f} & {P_con[1,1]:.3f} \\\\\n"
    table += r"\bottomrule" + "\n\\end{tabular}"

    return table

def information_criteria(result_uncon, result_con):
    aic_u, ll_u, bic_u = result_uncon[:3]
    aic_c, ll_c, bic_c = result_con[:3]

    table = r"""\begin{tabular}{ccc}
\hline
 & distinct variances & common variance \\
\hline
"""
    table += f"log likelihood & {ll_u:.2f} & {ll_c:.2f} \\\\\n"
    table += f"aic & {aic_u:.2f} & {aic_c:.2f} \\\\\n"
    table += f"bic & {bic_u:.2f} & {bic_c:.2f} \\\\\n"
    table += r"\hline" + "\n\\end{tabular}"

    return table


def plot_hmm_results(mu, predict, price, var, *, save_inputs=True):

    if predict.ndim == 2:
        predict = predict[:, np.argmax(mu)]
    predict = predict
    price = price

    start_date = '1995-01'
    dates = pd.date_range(start=start_date, periods=276, freq='M')

    df = pd.DataFrame({
    'date': dates,
    'predict': predict
    })

    # Save to CSV
    if save_inputs:
        df.to_csv(f'output/tables/smooth_prob_{var}.csv', index=False)
        Path(f"output/tables/hmm_plot_means_{var}.json").write_text(
            json.dumps({"mu": [float(value) for value in mu]}, indent=2) + "\n"
        )

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Plot the first dataset with the left y-axis (ax1)
    ax1.plot(dates, predict, linewidth=LINE_WIDTH, label='high state probability (left axis)', color='#0072B2')
    ax1.set_xlabel('time')
    ax1.set_ylabel('smoothed probability', color='black',fontsize=16)
    ax1.tick_params(axis='y', labelcolor='black')

    ax1.xaxis.set_major_locator(mdates.YearLocator(base=5))  # Major ticks every 5 years
    ax1.xaxis.set_minor_locator(mdates.YearLocator(base=1))  # Minor ticks every year
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    # Create a second y-axis on the right
    ax2 = ax1.twinx()

    # Plot the second dataset with the right y-axis (ax2)
    ax2.plot(dates, price, linewidth=LINE_WIDTH, linestyle='--', label='actual price (right axis)', color='#D55E00')
    ax2.set_ylabel('actual Price', color='black',fontsize=16)
    ax2.tick_params(axis='y', labelcolor='black')

    if mu[0]>mu[1]:
        ax2.axhline(y=mu[0], color='#009E73', linestyle='-.', linewidth=2.4, label='high price (right axis)')
        ax2.axhline(y=mu[1], color='#8E44AD', linestyle=':', linewidth=2.4, label='low price (right axis)')
    else:
        ax2.axhline(y=mu[0], color='#8E44AD', linestyle=':', linewidth=2.4, label='low price (right axis)')
        ax2.axhline(y=mu[1], color='#009E73', linestyle='-.', linewidth=2.4, label='high price (right axis)')

    # Add legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    lines = lines1 + lines2
    labels = labels1 + labels2
    ax1.legend(lines, labels, loc='lower left',fontsize=10, framealpha=1)

    plt.xticks(rotation=45)
    save_publication_figure(fig, f'output/figures/smooth_prob_{var}.png', format='png', bbox_inches='tight')
    plt.close()

def est(s_low=0.5,s_high=0.5,var='uncon'):
    step_start = time.time()
    log(f"start HMM fit block var={var}, startprob=({s_low:.6f}, {s_high:.6f})")

    warnings.filterwarnings("ignore", message="KMeans is known to have a memory leak on Windows with MKL, when there are less chunks than available threads. You can avoid it by setting the environment variable OMP_NUM_THREADS=2.")


    # need to input initial state prob s_low and s_high
    data_folder = os.getcwd()+"/data/calibration/"

    # read data
    df = pd.read_csv(data_folder+"seriesPriceCattle_prepared.csv")
    price = df['price_real_mon_cattle'].values.astype(float)
    logprice=np.log(price)
    log(f"loaded {len(logprice)} monthly prices for var={var}")


    # estimating the model

    Q=logprice.reshape(logprice.shape[0],1)

    np.random.seed(12345)

    best_score = best_model = None
    n_fits = 500

    for idx in range(n_fits):

        if var=='uncon':
            model = hmm.GaussianHMM(n_components=2,random_state=idx,init_params='tmc',params='stmc')
        else:
            model = hmm.GaussianHMM(n_components=2,random_state=idx,init_params='tmc',params='stmc',covariance_type='tied')

        model.startprob_= np.array([s_low, s_high])
        with suppress_output():
            model.fit(Q)

        score = model.score(Q)

        if best_score is None or score > best_score:
            best_model = model
            best_score = score
        if (idx + 1) % 50 == 0 or idx + 1 == n_fits:
            elapsed = time.time() - step_start
            log(
                f"var={var} completed {idx + 1}/{n_fits} fits; "
                f"best_score={best_score:.6f}; elapsed={elapsed:.1f}s"
            )

    aic = best_model.aic(Q)
    bic = best_model.bic(Q)
    mus = np.exp(np.ravel(best_model.means_))
    sigmas = np.ravel(np.sqrt([np.diag(c) for c in best_model.covars_]))
    P = np.round(best_model.transmat_,3)

    sorted_indices = np.argsort(mus)
    mus_sorted = mus[sorted_indices]
    sigmas_sorted = sigmas[sorted_indices]
    P_sorted = P[sorted_indices][:, sorted_indices]
    predict=best_model.predict_proba(Q)
    if var=='uncon':
        ll = (best_model.aic(Q)-12)/(-2)
    else:
        ll = (best_model.aic(Q)-10)/(-2)


    plot_hmm_results(mus,predict, price, var)
    log(f"finished HMM fit block var={var}; elapsed={time.time() - step_start:.1f}s")


    return(aic,ll,bic,mus_sorted,sigmas_sorted,P_sorted)




def stationary(transition_matrix,mus):

    eigenvals, eigenvects = np.linalg.eig(transition_matrix.T)
    close_to_1_idx = np.isclose(eigenvals,1)
    target_eigenvect = eigenvects[:,close_to_1_idx]
    target_eigenvect = target_eigenvect[:,0]
    stationary_distrib = target_eigenvect / sum(target_eigenvect)
    stationary_price=mus[0]*stationary_distrib[0]+mus[1]*stationary_distrib[1]
    return(stationary_distrib,stationary_price)


def annual_transition(transition_matrix):
    dτ = 1/12  # time step
    P = transition_matrix  #probability transition matrix
    M = logm(P)/dτ  # instantenous generator
    P = expm(M)  # Updated Probability transition matrix
    return P


def iteration_est(initial_prob, num_iterations=5,var='uncon'):


    for i in range(num_iterations):
        log(f"start stationary iteration {i + 1}/{num_iterations} for var={var}")
        if i == 0:
            s_low, s_high = initial_prob[0], initial_prob[1]
        else:
            s_low, s_high = sta_dist[0], sta_dist[1]

        aic, ll, bic, mus, sigmas, P = est(s_low, s_high, var)
        sta_dist, sta_price = stationary(P, mus)
        annual_P=annual_transition(P)
        log(
            f"finished stationary iteration {i + 1}/{num_iterations} for var={var}; "
            f"stationary_price={sta_price:.6f}"
        )

    return aic,ll,bic,mus,sigmas,P,sta_dist,sta_price,annual_P





def redraw_cached_figures():
    price = pd.read_csv(get_path("data", "calibration", "seriesPriceCattle_prepared.csv"))[
        "price_real_mon_cattle"
    ].to_numpy()
    log_path = get_path("job-outs", "stage_hmm", "price_estimation", "0001_run.out")
    for var, label in [("uncon", "distinct variances"), ("con", "common variances")]:
        predict = pd.read_csv(get_path("output", "tables", f"smooth_prob_{var}.csv"))[
            "predict"
        ].to_numpy()
        means_path = get_path("output", "tables", f"hmm_plot_means_{var}.json")
        if means_path.exists():
            mu = np.asarray(json.loads(means_path.read_text())["mu"])
        else:
            # Archived runs predate the full-precision plot cache.
            # The first printed array in each final result contains the two means.
            match = re.search(
                re.escape(label) + r"[^\n]*?array\(\[([^\]]+)\]",
                log_path.read_text(),
            )
            if match is None:
                raise ValueError(f"Missing final {label} means in {log_path}")
            mu = np.fromstring(match.group(1), sep=",")
            log(f"Using archived printed means for {var}: {mu}; precision is limited to the log.")
        plot_hmm_results(mu, predict, price, var, save_inputs=False)


def main():
    parser = argparse.ArgumentParser(description="Estimate the cattle-price HMM or redraw cached figures.")
    parser.add_argument("--plot-only", action="store_true",
                        help="Redraw Figure 16 from cached probabilities, prices and means.")
    args = parser.parse_args()
    if args.plot_only:
        redraw_cached_figures()
        return

    log("starting HMM price estimation")
    result_uncon = iteration_est([0.5, 0.5], num_iterations=5, var='uncon')
    result_con = iteration_est([0.5, 0.5], num_iterations=5, var='con')

    print("distinct variances",   result_uncon)
    print("common variances",   result_con)

    latex_table = format_latex_table(result_uncon, result_con)
    information_table = information_criteria(result_uncon, result_con)


    # Save to file
    with open("output/tables/hmm_results_table.tex", "w") as f:
        f.write(latex_table)


    with open("output/tables/hmm_information_criteria.tex", "w") as f:
        f.write(information_table)

    log("finished HMM price estimation")


if __name__ == "__main__":
    main()
