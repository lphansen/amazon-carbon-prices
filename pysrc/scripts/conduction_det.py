import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pysrc.analysis.figures import land_allocation, plot_transfers
from pysrc.analysis.tables import transfer_cost, value_decom
from pysrc.replication.parameters import CarbonPriceKey, carbon_price
from pysrc.services.get_opt import get_optimization

### Section 7.2 Results for case without stochasticity or ambiguity aversion


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic analysis outputs.")
    parser.add_argument("--solver", default="gurobi")
    parser.add_argument("--pa", type=float, default=41.11)
    parser.add_argument("--skip-optimization", action="store_true")
    parser.add_argument("--figures-only", action="store_true",
                        help="Only redraw Figures 5 and 6 from existing solutions.")
    args = parser.parse_args()

    pee_1043 = carbon_price(
        CarbonPriceKey(
            context="parameter_ambiguity", model="det", sites=1043, xi="inf"
        )
    )
    if args.figures_only:
        land_allocation(num_sites=1043, solver=args.solver, pee=pee_1043, pa=args.pa)
        plot_transfers(num_sites=1043, pee=pee_1043, solver=args.solver, pa=args.pa)
        return

    pee_78 = carbon_price(
        CarbonPriceKey(context="parameter_ambiguity", model="det", sites=78, xi="inf")
    )

    if not args.skip_optimization:
        get_optimization(
            num_sites=1043, pee=pee_1043, pa=args.pa, model="det", solver=args.solver
        )
    land_allocation(num_sites=1043, solver=args.solver, pee=pee_1043, pa=args.pa)
    value_decom(num_sites=1043, pee=pee_1043, solver=args.solver, pa=args.pa)
    transfer_cost(num_sites=1043, pee=pee_1043, y=30, solver=args.solver, pa=args.pa)
    transfer_cost(num_sites=1043, pee=pee_1043, y=15, solver=args.solver, pa=args.pa)
    plot_transfers(num_sites=1043, pee=pee_1043, solver=args.solver, pa=args.pa)

    if not args.skip_optimization:
        get_optimization(
            num_sites=78, pee=pee_78, pa=args.pa, model="det", solver=args.solver
        )
    value_decom(num_sites=78, pee=pee_78, solver=args.solver, pa=args.pa)

    print("det All done!")


if __name__ == "__main__":
    main()
