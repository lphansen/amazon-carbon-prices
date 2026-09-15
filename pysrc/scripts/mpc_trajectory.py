import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pysrc.services.file_service import get_path
from pysrc.analysis.publication import LINE_WIDTH, AVERSE_STYLE, NEUTRAL_STYLE, save_publication_figure
import os
from pysrc.services.data_service import load_site_data
import matplotlib.pyplot as plt
from pysrc.replication.parameters import CarbonPriceKey, carbon_price


solver="gurobi"
num_sites=78
xi1=10000.0
xi2=1.0
xi3=0.5
pe1=carbon_price(CarbonPriceKey(context="price_stochasticity", model="unconstrained", sites=78, xi="inf", price_model="distinct_variance"))
pe2=carbon_price(CarbonPriceKey(context="price_stochasticity", model="unconstrained", sites=78, xi=1.0, price_model="distinct_variance"))
pe3=carbon_price(CarbonPriceKey(context="price_stochasticity", model="unconstrained", sites=78, xi=0.5, price_model="distinct_variance"))
# b=15
for b in [0,15]:
    (zbar, _, _) = load_site_data(num_sites)

    def read_file(result_directory):

        Z = np.loadtxt(os.path.join(result_directory, "Z.txt"), delimiter=",")
        X = np.sum(np.loadtxt(os.path.join(result_directory, "X.txt"), delimiter=","),axis=1)
        Xdot = np.diff(X, axis=0)
        U = np.loadtxt(os.path.join(result_directory, "U.txt"), delimiter=",")
        V = np.loadtxt(os.path.join(result_directory, "V.txt"), delimiter=",")

        return (Z / 1e2, Xdot / 1e2, U / 1e2, V / 1e2)

    result_zper1=[]
    result_zper2=[]
    result_zper3=[]

    for i in range(50):


        result_directory1 = (
            str(get_path("output"))
            + f"/optimization/mpc/{solver}/{num_sites}sites/xi_{xi1}/pa_41.1/"
            + f"pe_{pe1+b}/mc_{i+1}/unconstrained"
        )
        result_directory2 = (
            str(get_path("output"))
            + f"/optimization/mpc/{solver}/{num_sites}sites/xi_{xi2}/pa_41.1/"
            + f"pe_{pe2+b}/mc_{i+1}/unconstrained"
        )

        result_directory3 = (
            str(get_path("output"))
            + f"/optimization/mpc/{solver}/{num_sites}sites/xi_{xi3}/pa_41.1/"
            + f"pe_{pe3+b}/mc_{i+1}/unconstrained"
        )
        # result_directory2 = (
        #     str(get_path("output"))
        #     + f"/optimization/mpc_worstcase/{solver}/{num_sites}sites/xi_{xi2}/pa_41.1/"
        #     + f"pe_{pe2}/mc_{i+1}/unconstrained"
        # )

        # result_directory3 = (
        #     str(get_path("output"))
        #     + f"/optimization/mpc_worstcase/{solver}/{num_sites}sites/xi_{xi3}/pa_41.1/"
        #     + f"pe_{pe3}/mc_{i+1}/unconstrained"
        # )

        (dfz_np1,_,_,_) = read_file(
            result_directory1
        )
        (dfz_np2,_,_,_) = read_file(
            result_directory2
        )

        (dfz_np3,_,_,_) = read_file(
            result_directory3
        )


        dfz_np1=np.sum(dfz_np1,axis=1)[:50]
        dfz_np2=np.sum(dfz_np2,axis=1)[:50]
        dfz_np3=np.sum(dfz_np3,axis=1)[:50]

        result_zper1.append((dfz_np1/ np.sum(zbar)) * 100)
        result_zper2.append((dfz_np2/ np.sum(zbar)) * 100)
        result_zper3.append((dfz_np3/ np.sum(zbar)) * 100)



    result_zper1=np.mean(np.array(result_zper1),axis=0)
    result_zper2=np.mean(np.array(result_zper2),axis=0)
    result_zper3=np.mean(np.array(result_zper3),axis=0)


    time = list(range(len(dfz_np1)))
    output_folder = str(get_path("output"))
    plt.figure()

    plt.plot(time, result_zper1*100,linewidth=LINE_WIDTH, **NEUTRAL_STYLE, label=r"$\widehat{\xi}=\infty$")
    plt.plot(time, result_zper2*100,linewidth=LINE_WIDTH, **AVERSE_STYLE, marker='o', markevery=7, markersize=5.5, markeredgewidth=1.1, markerfacecolor='white', label=r"$\widehat{\xi}=1$")
    # plt.plot(time, result_zper3*100,linewidth=4,color = 'green', label=r"$\widehat{\xi}=0.5$")

    # plt.title("Land allocation, transfer b=0")
    plt.ylabel("Z(%)")
    plt.xlabel("years")
    plt.ylim(0,20)
    plt.xlim(0,50)
    plt.legend()
    save_publication_figure(plt.gcf(), os.path.join(output_folder, f"figures/mpc_landallocation_b_{b}_adjust.png"))
    save_publication_figure(plt.gcf(),
        os.path.join(
            output_folder,
            f"figures/mpc_landallocation_b_{b}_baseline_same_ylim.png",
        )
    )
    plt.close()
