"""
csp_solver.py
-------------
General-purpose CSP engine for the Van/Route scheduling problem.

Variables : route ids
Domain    : list of (van_id, driver_id, start_time) triples that individually
            satisfy capacity / fuel-range / time-window / driver-availability
Constraints:
  binary   -> two routes assigned the same van (or same driver) must not
              overlap in time
  global   -> a driver's total assigned duration in a day must not exceed
              their max_hours_per_day

Implements, exactly as required by the assignment brief:
  - Backtracking Search
  - Forward Checking
  - Arc Consistency (AC-3)
  - Constraint Propagation
  - MRV (Minimum Remaining Values)
  - Degree Heuristic
  - Least Constraining Value (LCV)
  - Min-Conflicts (local-search alternative, used for comparison)
"""

import random
import time
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

from model import Van, Driver, Route, Assignment, overlaps


class SchedulingCSP:
    def __init__(self, vans: List[Van], drivers: List[Driver], routes: List[Route]):
        self.vans = {v.id: v for v in vans}
        self.drivers = {d.id: d for d in drivers}
        self.routes = {r.id: r for r in routes}
        self.route_ids = list(self.routes.keys())

        # --- stats collected during the last search, useful for the report ---
        self.nodes_expanded = 0
        self.backtracks = 0

        self.domains: Dict[str, List[Assignment]] = self._build_initial_domains()

    # ------------------------------------------------------------------ #
    # Domain construction (unary constraints baked in directly)
    # ------------------------------------------------------------------ #
    def _build_initial_domains(self) -> Dict[str, List[Assignment]]:
        domains = {}
        for rid, route in self.routes.items():
            values = []
            for van in self.vans.values():
                if route.passengers > van.capacity:
                    continue                       # capacity constraint
                if route.distance_km > van.fuel_range_km:
                    continue                       # fuel/distance constraint
                for driver in self.drivers.values():
                    for t in route.candidate_start_times():
                        if t < driver.available_from or (t + route.duration_min) > driver.available_to:
                            continue               # driver availability
                        values.append((van.id, driver.id, t))
            domains[rid] = values
        return domains

    # ------------------------------------------------------------------ #
    # Constraint checking
    # ------------------------------------------------------------------ #
    def consistent_pair(self, r1: str, v1: Assignment, r2: str, v2: Assignment) -> bool:
        """Binary constraint between two DIFFERENT routes' proposed values."""
        van1, drv1, t1 = v1
        van2, drv2, t2 = v2
        dur1 = self.routes[r1].duration_min
        dur2 = self.routes[r2].duration_min

        if van1 == van2 and overlaps(t1, dur1, t2, dur2):
            return False                            # no route-overlap constraint (same van)
        if drv1 == drv2 and overlaps(t1, dur1, t2, dur2):
            return False                            # driver can't be in two places at once
        return True

    def driver_hours_ok(self, assignment: Dict[str, Assignment], route_id: str, value: Assignment) -> bool:
        """Global (n-ary) max-working-hours constraint for the driver in `value`."""
        _, driver_id, _ = value
        total_min = self.routes[route_id].duration_min
        for rid, val in assignment.items():
            if rid == route_id:
                continue
            if val[1] == driver_id:
                total_min += self.routes[rid].duration_min
        return total_min <= self.drivers[driver_id].max_hours_per_day * 60

    def is_consistent(self, assignment: Dict[str, Assignment], route_id: str, value: Assignment) -> bool:
        if not self.driver_hours_ok(assignment, route_id, value):
            return False
        for rid, val in assignment.items():
            if rid == route_id:
                continue
            if not self.consistent_pair(route_id, value, rid, val):
                return False
        return True

    def count_violations(self, assignment: Dict[str, Assignment]) -> int:
        """Used by min-conflicts and for the final report."""
        violations = 0
        rids = list(assignment.keys())
        for i in range(len(rids)):
            for j in range(i + 1, len(rids)):
                if not self.consistent_pair(rids[i], assignment[rids[i]], rids[j], assignment[rids[j]]):
                    violations += 1
        for rid, val in assignment.items():
            partial = {k: v for k, v in assignment.items() if k != rid}
            if not self.driver_hours_ok(partial, rid, val):
                violations += 1
        return violations

    # ------------------------------------------------------------------ #
    # AC-3 (arc consistency preprocessing / constraint propagation)
    # ------------------------------------------------------------------ #
    def ac3(self, domains: Optional[Dict[str, List[Assignment]]] = None) -> bool:
        domains = domains if domains is not None else self.domains
        queue = [(ri, rj) for ri in self.route_ids for rj in self.route_ids if ri != rj]

        def revise(ri, rj):
            revised = False
            to_remove = []
            for vi in domains[ri]:
                # keep vi only if SOME value vj in rj's domain is compatible
                if not any(self.consistent_pair(ri, vi, rj, vj) for vj in domains[rj]):
                    to_remove.append(vi)
            if to_remove:
                for vi in to_remove:
                    domains[ri].remove(vi)
                revised = True
            return revised

        while queue:
            ri, rj = queue.pop(0)
            if revise(ri, rj):
                if not domains[ri]:
                    return False                    # a domain wiped out -> no solution
                for rk in self.route_ids:
                    if rk != ri and rk != rj:
                        queue.append((rk, ri))
        return True

    # ------------------------------------------------------------------ #
    # Heuristics: MRV, Degree heuristic (tie-break), LCV
    # ------------------------------------------------------------------ #
    def select_unassigned_variable(self, assignment: Dict[str, Assignment],
                                    domains: Dict[str, List[Assignment]],
                                    use_heuristics: bool) -> str:
        unassigned = [r for r in self.route_ids if r not in assignment]
        if not use_heuristics:
            return unassigned[0]

        # MRV: fewest remaining legal values
        min_size = min(len(domains[r]) for r in unassigned)
        mrv_candidates = [r for r in unassigned if len(domains[r]) == min_size]
        if len(mrv_candidates) == 1:
            return mrv_candidates[0]

        # Degree heuristic tie-break: most constraints with other unassigned routes
        # (approximated as: shares a van OR driver option with the most other
        # unassigned routes' domains)
        def degree(rid):
            vans_drivers = {(v, d) for v, d, _ in domains[rid]}
            count = 0
            for other in unassigned:
                if other == rid:
                    continue
                other_vd = {(v, d) for v, d, _ in domains[other]}
                if vans_drivers & other_vd:
                    count += 1
            return count

        return max(mrv_candidates, key=degree)

    def order_domain_values(self, rid: str, domains: Dict[str, List[Assignment]],
                             assignment: Dict[str, Assignment], use_heuristics: bool) -> List[Assignment]:
        values = domains[rid]
        if not use_heuristics:
            return list(values)

        # LCV: prefer values that rule out the fewest options for OTHER unassigned routes
        unassigned = [r for r in self.route_ids if r not in assignment and r != rid]

        def conflicts_caused(value):
            total = 0
            for other in unassigned:
                for ov in domains[other]:
                    if not self.consistent_pair(rid, value, other, ov):
                        total += 1
            return total

        return sorted(values, key=conflicts_caused)

    # ------------------------------------------------------------------ #
    # Forward checking
    # ------------------------------------------------------------------ #
    def forward_check(self, rid: str, value: Assignment,
                       domains: Dict[str, List[Assignment]],
                       assignment: Dict[str, Assignment]) -> Optional[Dict[str, List[Assignment]]]:
        new_domains = {r: list(vals) for r, vals in domains.items()}
        for other in self.route_ids:
            if other == rid or other in assignment:
                continue
            pruned = [ov for ov in new_domains[other] if self.consistent_pair(rid, value, other, ov)]
            if not pruned:
                return None                          # wipeout -> dead end
            new_domains[other] = pruned
        return new_domains

    # ------------------------------------------------------------------ #
    # Backtracking search (toggle heuristics/FC/AC-3 to compare strategies)
    # ------------------------------------------------------------------ #
    def backtracking_search(self, use_ac3: bool = True, use_fc: bool = True,
                             use_heuristics: bool = True) -> Optional[Dict[str, Assignment]]:
        self.nodes_expanded = 0
        self.backtracks = 0

        domains = {r: list(v) for r, v in self.domains.items()}
        if use_ac3:
            if not self.ac3(domains):
                return None

        def backtrack(assignment, domains):
            if len(assignment) == len(self.route_ids):
                return assignment

            rid = self.select_unassigned_variable(assignment, domains, use_heuristics)
            for value in self.order_domain_values(rid, domains, assignment, use_heuristics):
                self.nodes_expanded += 1
                if self.is_consistent(assignment, rid, value):
                    assignment[rid] = value
                    pruned_domains = domains
                    if use_fc:
                        pruned_domains = self.forward_check(rid, value, domains, assignment)
                    if pruned_domains is not None:
                        result = backtrack(assignment, pruned_domains)
                        if result is not None:
                            return result
                    del assignment[rid]
            self.backtracks += 1
            return None

        return backtrack({}, domains)

    # ------------------------------------------------------------------ #
    # Min-Conflicts local search (alternative technique, for comparison)
    # ------------------------------------------------------------------ #
    def min_conflicts(self, max_steps: int = 2000) -> Tuple[Optional[Dict[str, Assignment]], int]:
        assignment = {}
        for rid in self.route_ids:
            if not self.domains[rid]:
                return None, 0
            assignment[rid] = random.choice(self.domains[rid])

        for step in range(max_steps):
            violations = self.count_violations(assignment)
            if violations == 0:
                return assignment, step

            conflicted = [rid for rid in self.route_ids
                          if self._route_has_conflict(assignment, rid)]
            rid = random.choice(conflicted)

            best_value, best_score = assignment[rid], float("inf")
            for value in self.domains[rid]:
                trial = dict(assignment)
                trial[rid] = value
                score = self.count_violations(trial)
                if score < best_score:
                    best_score, best_value = score, value
            assignment[rid] = best_value

        return (assignment if self.count_violations(assignment) == 0 else None), max_steps

    def _route_has_conflict(self, assignment, rid) -> bool:
        for other, val in assignment.items():
            if other == rid:
                continue
            if not self.consistent_pair(rid, assignment[rid], other, val):
                return True
        partial = {k: v for k, v in assignment.items() if k != rid}
        return not self.driver_hours_ok(partial, rid, assignment[rid])
