# Design Notes: Factory & Belts Assignment

## Part A: Factory Steady State (`factory`)

### 1. Factory Modeling Choices

The factory problem is modeled as a standard Linear Program (LP). [cite_start]The `scipy.optimize.linprog` function (with the default `highs` method) is used to find the optimal solution[cite: 268].

**Variables:**
The LP model defines two sets of variables:
1.  **Recipe Crafts ($x_r$):** One variable for each recipe, representing its `crafts/min` rate.
2.  **Raw Consumption ($c_i$):** One *explicit* variable for each raw item, representing the total `items/min` consumed from the external supply.

This choice simplifies the conservation equations, as raw material caps can be applied as a simple upper bound on these $c_i$ variables.

**Conservation Equations:**
[cite_start]We enforce strict conservation for all items (raw, intermediate, and target)[cite: 254]:
* **For Intermediates:** $\sum (\text{Production}) - \sum (\text{Consumption}) = 0$
* **For the Target Item:** $\sum (\text{Production}) - \sum (\text{Consumption}) = \text{target\_rate}$
* **For Raw Items:** $\sum (\text{Production}) - \sum (\text{Consumption}) + c_i = 0$. This equation links the net factory balance to the explicit consumption variable $c_i$.

**Constraints:**
1.  [cite_start]**Raw Consumption:** The explicit raw consumption variables are bounded: $0 \le c_i \le \text{raw\_supply\_per\_min}[i]$[cite: 255].
2.  [cite_start]**Machine Capacity:** For each machine type `m`, a single constraint sums the machine usage of all recipes running on it: $\sum_{r \text{ uses } m} (x_r / \text{eff\_crafts\_per\_min}(r)) \le \text{max\_machines}[m]$[cite: 255].
3.  **Non-Negativity:** All $x_r \ge 0$.

**Module Application:**
[cite_start]Modules are handled by pre-calculating two values for each recipe `r` *before* building the LP[cite: 256]:
1.  [cite_start]`eff_rate(r)`: The effective crafts/min, calculated as `base_speed * (1 + speed_mod) * 60 / time_s`[cite: 35]. This value is used in the machine capacity constraints.
2.  `prod_mult(r)`: The productivity bonus (e.g., `0.2`). This is used to multiply the `out` items in the conservation equations: `output_amount * (1.0 + prod_mult)`[cite: 39].

**Cycles and Byproducts:**
[cite_start]The LP steady-state model handles cycles and byproducts naturally[cite: 257]. By enforcing a balance of `0` for all intermediates, any cyclic processes are forced to be self-sustaining, and any byproducts must be consumed by other recipes.

**Tie-Breaking (Minimizing Machines):**
[cite_start]The problem is formulated as a single LP[cite: 66]. The objective function is set to *directly* minimize the total machine count, which is a linear combination of the recipe variables:
[cite_start]`minimize: \sum_{r} (x_r / \text{eff\_crafts\_per\_min}(r))`[cite: 61].
[cite_start]This single-pass approach finds the feasible solution that *also* has the minimum machine count, satisfying the tie-breaking requirement[cite: 258].

**Infeasibility Detection:**
[cite_start]If the initial `linprog` call fails, we assume the `target_rate` is too high[cite: 259].
1.  We then find the maximum feasible rate by performing a binary search on `target_rate`.
2.  The search first finds a loose upper bound by exponential probing (`high *= 2.0`) until a solve fails.
3.  It then performs 50 iterations of a standard binary search between `low=0` and the found `high` to find the `max_feasible_target_per_min`.
4.  To generate bottleneck hints, the LP is solved *one more time* at `max_feasible * 0.999999` (to ensure it's in the feasible region).
5.  We then inspect the solution and report any machine or raw material constraints that are "tight" (i.e., usage is within `1e-9` of the cap).

---

## Part B: Belts with Bounds (`belts`)

### 1. Belts Modeling Choices

[cite_start]The bounded belts problem is modeled as a classic **max-flow with lower bounds**[cite: 262]. The solution is implemented using a **hand-rolled Edmonds-Karp algorithm** (which uses BFS to find augmenting paths).

**Node Capacity Handling:**
[cite_start]Node capacities are handled using **node splitting**[cite: 263].
* Any node `v` with a cap `c` is split into two nodes: `v_in` and `v_out`.
* All original edges `(u, v)` are re-routed to `(u, v_in)`.
* All original edges `(v, w)` are re-routed to `(v_out, w)`.
* A new edge `(v_in, v_out)` is added with capacity `c`.

**Lower Bounds Transformation:**
The problem is transformed into a standard max-flow problem in two phases:

1.  **Feasibility Check (Circulation):**
    * A graph `G` is built where each edge `(u, v)` has capacity `hi - lo`.
    * An `imbalance` value is tracked for each node. [cite_start]`imbalance[v]` is credited with `lo` and `imbalance[u]` is debited by `lo` for each edge[cite: 188].
    * [cite_start]A super-source `s_star` is connected to all nodes with positive imbalance (demand), and all nodes with negative imbalance (supply) are connected to a super-sink `t_star` [cite: 191-193].
    * We run max-flow on `G` from `s_star` to `t_star`.

2.  **Main Flow (Supplies to Sink):**
    * If the first phase is feasible (max-flow = total demand), a *new* graph `H` is built.
    * This graph `H` also has edge capacities `hi - lo`.
    * A main super-source `s_sup` is connected to all *original* sources (e.g., `s1`, `s2`) with their respective supply values.
    * [cite_start]We run max-flow on `H` from `s_sup` to the *mapped* sink node (e.g., `sink_in` if capped)[cite: 199].

**Feasibility Check Strategy:**
[cite_start]A solution is feasible **if and only if** both max-flow phases succeed[cite: 264]:
1.  The flow in Phase 1 must equal the total demand (sum of all lower bounds).
2.  The flow in Phase 2 must equal the total supply from all sources.

[cite_start]The final flow on an original edge `(u, v)` is reconstructed by `actual_flow = lo + flow_from_phase_2`, where `flow_from_phase_2` is found by inspecting the residual capacity of the *reverse* edge in graph `H`[cite: 201].

**Infeasibility Certificates (Min-Cut):**
[cite_start]If the *first* (lower bound) phase fails, we compute the min-cut[cite: 265].
* A DFS (or BFS) is run from `s_star` on the final residual graph `G`.
* [cite_start]All nodes reachable from `s_star` are collected and reported as `cut_reachable`[cite: 234].
* The `deficit` is reported as `total_demand - flow1`.
* If the second (main flow) phase fails, a simpler infeasibility message is generated, as the lower bounds were already proven feasible.

---

## Common Numeric & Design Choices

**Numeric Tolerances:**
* [cite_start]All floating-point comparisons for flow, capacity, and LP constraints use an absolute tolerance of `1e-9` (or `1e-12` in some flow checks)[cite: 267].

**Tie-Breaking & Determinism:**
* [cite_start]**Factory (LP):** The `scipy.optimize.linprog` `highs` solver is deterministic and handles internal tie-breaking[cite: 269].
* **Belts (Max-Flow):** Determinism is explicitly guaranteed. During the BFS step of the Edmonds-Karp algorithm, neighbors of a node are explored in `sorted()` alphabetical order. [cite_start]This ensures that the same augmenting path is chosen every time for a given input[cite: 241].

**Failure Modes & Edge Cases:**
* [cite_start]**Cycles (Factory):** Handled natively by the LP solver's steady-state constraints[cite: 271].
* [cite_start]**Infeasible Supplies (Factory):** Caught by the LP solver returning `success=False`, which triggers the binary search for `max_feasible_target_per_min`[cite: 272].
* **Degenerate Recipes (Factory):** Recipes with 0 time or 0 I/O are handled by the LP. A 0-time recipe (if it produces something) will have an infinite `eff_rate`, and the solver will use it as much as possible, bounded only by other constraints.
* [cite_start]**Disconnected Graph (Belts):** If a source is disconnected from the sink, the max-flow in Phase 2 will be less than the `total_supply`, and the problem will be correctly reported as infeasible[cite: 274].
