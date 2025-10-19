Design Notes: Factory & Belts Assignment

This document details the design and modeling choices for the factory and belts command-line tools.

Part A: Factory Steady State (factory)

1. Factory Modeling Choices

The factory problem is modeled as a standard Linear Program (LP). The scipy.optimize.linprog function (with the high-performance highs method) is used to find the optimal solution.

Variables:
The LP model defines two sets of variables:

Recipe Crafts ($x_r$): One variable for each recipe, representing its crafts/min rate.

Raw Consumption ($c_i$): An explicit variable for each raw item, representing the total items/min drawn from the external supply. This directly models the problem's constraints and simplifies the conservation equations.

Conservation Equations:
We enforce strict conservation for all items (raw, intermediate, and target) using equality constraints:

For Intermediates: $\sum (\text{Production}) - \sum (\text{Consumption}) = 0$

For the Target Item: $\sum (\text{Production}) - \sum (\text{Consumption}) = \text{target\_rate}$

For Raw Items: $\sum (\text{Production}) - \sum (\text{Consumption}) + c_i = 0$. This links the factory's net balance to the explicit consumption variable $c_i$.

Constraints:

Raw Consumption: The raw consumption variables are bounded: $0 \le c_i \le \text{raw\_supply\_per\_min}[i]$.

Machine Capacity: For each machine type m, a single upper_bound constraint sums the machine usage: $\sum_{r \text{ uses } m} (x_r / \text{eff\_crafts\_per\_min}(r)) \le \text{max\_machines}[m]$.

Non-Negativity: All recipe craft rates $x_r$ are bounded to be $\ge 0$.

Module Application:
Modules are handled by pre-calculating values for each recipe before building the LP:

eff_rate(r): The effective crafts/min, base_speed * (1 + speed_mod) * 60 / time_s, is used as a coefficient in the machine capacity constraints.

prod_mult(r): The productivity bonus (e.g., 0.2) is used to scale the out items in the conservation equations: output_amount * (1.0 + prod_mult).

Tie-Breaking (Minimizing Machines):
The problem is formulated as a single LP. The objective function is set to directly minimize the total machine count, which is a linear combination of the recipe variables:
minimize: \sum_{r} (1 / \text{eff\_crafts\_per\_min}(r)) * x_r.
This single-pass approach finds a feasible solution that also has the minimum possible machine count.

Infeasibility Detection:
If the initial linprog solve fails, we find the maximum feasible rate using a hybrid search algorithm:

First, an exponential probe (high *= 2.0) is used to quickly find a loose upper bound on the target rate that is known to be infeasible.

Then, a binary search runs for 50 iterations between low=0 and this upper bound to precisely find the max_feasible_target_per_min.

To generate bottleneck hints, the LP is solved one final time at a rate just inside the feasible region (max_feasible * 0.999999). We then inspect the solution and report any machine or raw material constraints that are "tight" (i.e., usage is within 1e-9 of the cap).

Part B: Belts with Bounds (belts)

1. Belts Modeling Choices

The bounded belts problem is modeled as a classic max-flow with lower bounds. The solution is implemented using a hand-rolled Edmonds-Karp algorithm, which uses BFS to find augmenting paths in the graph.

Node Capacity Handling:
Node capacities are handled via node splitting.

Any node v with a cap c is split into two nodes: v_in and v_out.

All original incoming edges (u, v) are re-routed to (u, v_in).

All original outgoing edges (v, w) are re-routed from (v_out, w).

A new edge (v_in, v_out) is added with capacity c.

Lower Bounds Transformation:
The problem is transformed into a standard max-flow problem and solved in two phases:

Feasibility Check (Circulation): A circulation network is created to see if lower bounds can be satisfied.

A graph G is built where each edge (u, v) has capacity hi - lo.

An imbalance value is tracked for each node: imbalance[v] is credited with lo, and imbalance[u] is debited by lo.

A super-source s_star is connected to all nodes with positive imbalance (demand), and a super-sink t_star is connected to all nodes with negative imbalance (supply).

We run max-flow on G. The lower bounds are feasible if and only if the resulting flow equals the total demand.

Main Flow (Supplies to Sink):

If Phase 1 is feasible, a new graph H is built with the same hi - lo capacities.

A main super-source s_sup is connected to all original sources (s1, s2, etc.).

We run max-flow on H from s_sup to the final sink. The problem is feasible if this flow equals the total supply.

The final flow on an edge (u, v) is reconstructed as actual_flow = lo + flow_from_phase_2.

Infeasibility Certificates (Min-Cut):
If the first phase (lower bound feasibility) fails, a min-cut is computed to provide a detailed certificate.

A traversal (DFS/BFS) is run from the super-source s_star on the final residual graph G.

All nodes reachable from s_star are collected and reported as cut_reachable.

The deficit is the difference between the required demand and the flow achieved.

Common Numeric & Design Choices

Numeric Tolerances:

All floating-point comparisons for flow, capacity, and LP constraints use an absolute tolerance, typically 1e-9.

Tie-Breaking & Determinism:

Factory (LP): The scipy.optimize.linprog highs solver is deterministic by default.

Belts (Max-Flow): Determinism is explicitly guaranteed. During the BFS step of the Edmonds-Karp algorithm, the neighbors of a node are explored in sorted alphabetical order. This ensures that the same augmenting path is chosen every time for a given input.
