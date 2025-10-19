#!/usr/bin/env python3
import sys
import json
import math

def err(msg):
    out = {"status":"error","message":msg}
    print(json.dumps(out))
    sys.exit(0)

import numpy as np
from scipy.optimize import linprog


def read_input():
    data = json.load(sys.stdin)
    return data

def build_lp(data, target_rate):
    machines = data.get("machines", {})
    recipes = data.get("recipes", {})
    modules = data.get("modules", {})
    limits = data.get("limits", {})
    raw_caps = limits.get("raw_supply_per_min", {})
    max_machines = limits.get("max_machines", {})
    recipe_names = list(recipes.keys())
    raw_items = list(raw_caps.keys())

    items = set()
    for r, rd in recipes.items():
        for k in rd.get("in", {}):
            items.add(k)
        for k in rd.get("out", {}):
            items.add(k)
    target_item = data.get("target", {}).get("item", None)
    if target_item:
        items.add(target_item)
    items = sorted(items)

    eff_rate, prod_mult = {}, {}
    for r in recipe_names:
        rd = recipes[r]
        m = rd["machine"]
        mach = machines.get(m)
        if mach is None:
            err(f"Recipe {r} references unknown machine {m}")
        base_cpm = mach["crafts_per_min"]
        mod = modules.get(m, {})
        speed = mod.get("speed", 0.0)
        prod = mod.get("prod", 0.0)
        time_s = rd["time_s"]
        eff = base_cpm * (1.0 + speed) * 60.0 / float(time_s)
        eff_rate[r] = eff
        prod_mult[r] = prod

    n_rec = len(recipe_names)
    n_raw = len(raw_items)
    n_vars = n_rec + n_raw

    c = np.zeros(n_vars, dtype=float)
    for i, r in enumerate(recipe_names):
        c[i] = 1.0 / eff_rate[r] if eff_rate[r] > 0 else 1e9

    A_eq, b_eq = [], []
    for item in items:
        row = np.zeros(n_vars, dtype=float)
        for i, r in enumerate(recipe_names):
            out_map = recipes[r].get("out", {})
            out_amount = out_map.get(item, 0.0)
            if out_amount:
                row[i] += out_amount * (1.0 + prod_mult[r])
        for i, r in enumerate(recipe_names):
            in_map = recipes[r].get("in", {})
            in_amount = in_map.get(item, 0.0)
            if in_amount:
                row[i] -= in_amount
        if item in raw_items:
            rc_idx = n_rec + raw_items.index(item)
            row[rc_idx] = 1.0
            rhs = 0.0
        elif item == target_item:
            rhs = float(target_rate)
        else:
            rhs = 0.0
        A_eq.append(row)
        b_eq.append(rhs)
    A_eq, b_eq = np.array(A_eq), np.array(b_eq)

    A_ub, b_ub = [], []
    machine_recipe_map = {}
    for i, r in enumerate(recipe_names):
        m = recipes[r]["machine"]
        machine_recipe_map.setdefault(m, []).append(i)
    for m, rec_inds in machine_recipe_map.items():
        row = np.zeros(n_vars, dtype=float)
        for i in rec_inds:
            r = recipe_names[i]
            row[i] = 1.0 / eff_rate[r] if eff_rate[r] > 0 else 1e9
        cap = max_machines.get(m, float("inf"))
        A_ub.append(row)
        b_ub.append(float(cap))
    A_ub, b_ub = np.array(A_ub), np.array(b_ub)

    bounds = [(0.0, None)] * n_rec
    for item in raw_items:
        cap = raw_caps.get(item, None)
        bounds.append((0.0, float(cap) if cap is not None else None))

    return {
        "c": c,
        "A_eq": A_eq, "b_eq": b_eq,
        "A_ub": A_ub, "b_ub": b_ub,
        "bounds": bounds,
        "recipe_names": recipe_names,
        "raw_items": raw_items,
        "eff_rate": eff_rate,
        "items": items,
        "recipes": recipes,
        "raw_caps": raw_caps,
        "machines": machines,
    }

def solve_lp(lp):
    res = linprog(lp["c"], A_ub=lp["A_ub"], b_ub=lp["b_ub"],
                  A_eq=lp["A_eq"], b_eq=lp["b_eq"],
                  bounds=lp["bounds"], method="highs")
    return res

def extract_output(res, lp, target_rate):
    if not res.success:
        return None, res.message
    x = res.x
    n_rec = len(lp["recipe_names"])
    recipe_vals = {r: float(x[i]) for i, r in enumerate(lp["recipe_names"])}
    per_machine_counts = {}
    for m in lp["machines"].keys():
        total = sum(
            x[i] / lp["eff_rate"][r]
            for i, r in enumerate(lp["recipe_names"])
            if lp["recipes"][r]["machine"] == m
        )
        per_machine_counts[m] = float(total)
    raw_consumption = {
        item: float(x[n_rec + j]) for j, item in enumerate(lp["raw_items"])
    }
    return {
        "status": "ok",
        "per_recipe_crafts_per_min": recipe_vals,
        "per_machine_counts": per_machine_counts,
        "raw_consumption_per_min": raw_consumption,
    }, None

def find_max_feasible_target(data, low=0.0, high=None):
    if high is None:
        high = 1.0
    while True:
        lp = build_lp(data, high)
        res = solve_lp(lp)
        if not res.success:
            break
        high *= 2.0
        if high > 1e9:
            break
    for _ in range(50):
        mid = (low + high) / 2.0
        lp = build_lp(data, mid)
        res = solve_lp(lp)
        if res.success:
            low = mid
        else:
            high = mid
    return low

def compute_bottleneck_hints(data, res, lp):
    hints = []
    x = res.x
    n_rec = len(lp["recipe_names"])
    for m in lp["machines"].keys():
        total = sum(
            x[i] / lp["eff_rate"][r]
            for i, r in enumerate(lp["recipe_names"])
            if lp["recipes"][r]["machine"] == m
        )
        cap = data.get("limits", {}).get("max_machines", {}).get(m, None)
        if cap is not None and total > 0.999999999 * cap:
            hints.append(m + " cap")
    for j, item in enumerate(lp["raw_items"]):
        rc_val = float(x[n_rec + j])
        cap = lp["raw_caps"].get(item, None)
        if cap is not None and rc_val > 0.999999999 * cap:
            hints.append(item + " supply")
    return list(dict.fromkeys(hints)) or ["unknown"]

def main():
    data = read_input()
    target_rate = data.get("target", {}).get("rate_per_min")
    
    lp = build_lp(data, target_rate)
    res = solve_lp(lp)
    
    if res.success:
        out, _ = extract_output(res, lp, target_rate)
        print(json.dumps(out))
        return
    
    max_feasible = find_max_feasible_target(data)
    lp2 = build_lp(data, max_feasible * 0.999999 if max_feasible > 0 else 0.0)
    res2 = solve_lp(lp2)
    hints = compute_bottleneck_hints(data, res2, lp2) if res2.success else ["infeasible_problem"]
    
    out = {
        "status": "infeasible",
        "max_feasible_target_per_min": float(max_feasible),
        "bottleneck_hint": hints,
    }
    print(json.dumps(out))

if __name__ == "__main__":
    main()
