# Smart Van & Route Scheduling using CSP — Assignment 4

## Why this project (and not VeriRAG)

Your friend's VeriRAG idea (RAG + logic verification + CSP + adversarial critique +
a full RAGAS evaluation suite) is a genuinely good *portfolio* project, but it's a
poor fit for **this specific assignment**:

- The brief asks for a **small project** using *one* of Genetic/CSP/Adversarial
  Search, gradeable on **50 marks with a viva in the next few days**.
- You must be able to **explain the logic yourself** in the viva. A system that
  stitches together embeddings, satisfiability solving, minimax over claim-trees,
  *and* CSP retrieval is very hard to defend convincingly on short notice, even if
  an AI tool helped write the code.
- The assignment file itself already gives you an ideal, well-scoped topic:
  **"Smart Van and Route Scheduling using CSP"** — with a worked example
  (V1/V2/V3, R1/R2/R3) and an explicit list of algorithms to implement.

So this project builds exactly that, fully working, using every CSP technique
your brief names. If you still want to explore VeriRAG later as a summer/resume
project, the idea is solid — just not for a 1-week, 50-mark assignment.

## What's implemented

| Required technique          | Where |
|---|---|
| Backtracking Search          | `SchedulingCSP.backtracking_search` |
| Forward Checking             | `SchedulingCSP.forward_check` |
| Arc Consistency (AC-3)       | `SchedulingCSP.ac3` |
| Constraint Propagation       | AC-3 + forward checking together |
| MRV (Minimum Remaining Values) | `select_unassigned_variable` |
| Degree Heuristic (tie-break) | `select_unassigned_variable` |
| Least Constraining Value (LCV) | `order_domain_values` |
| Min-Conflicts (local search, for comparison) | `SchedulingCSP.min_conflicts` |

### CSP formulation

- **Variables**: one per route (`R1`, `R2`, ...)
- **Domain**: every legal `(van, driver, start_time)` triple for that route —
  legal meaning van capacity ≥ passengers, van fuel range ≥ route distance,
  and the driver is on shift for the whole route duration.
- **Binary constraints**: two routes assigned the same van, or the same driver,
  must not overlap in time.
- **Global constraint**: a driver's total assigned minutes in the day can't
  exceed their `max_hours_per_day`.

### Files

- `model.py` — `Van`, `Driver`, `Route` data classes + time-overlap helper
- `csp_solver.py` — the CSP engine (all algorithms above)
- `main.py` — sample dataset (extends the assignment's example scenario) and a
  demo that solves the same problem three ways and compares them

## Running it

```bash
python3 main.py            # 6-route sample scenario
python3 main.py --stress   # 12-route, more tightly-constrained scenario
```

This prints:
1. The final schedule (`Van -> Route -> Driver -> Time`), total distance,
   average vehicle utilization, and constraint violations — in the exact
   format the assignment's "Expected Output" section shows.
2. A comparison table: **nodes expanded** and **backtracks** for
   (a) full heuristics + AC-3 + forward checking vs. (b) plain backtracking
   with none of that — this is your "evaluation" evidence for the report/demo.
3. A Min-Conflicts run as a second, independent solving strategy, included
   because the assignment explicitly lists it as a technique to apply.

**On the 6-route sample**: heuristics cut node expansions from 44 down to 6
(both find a 0-violation solution instantly).

**On the 12-route `--stress` instance**: plain backtracking expands **7,095**
nodes with 89 backtracks; the AC-3 + MRV/Degree + LCV + forward-checking
version expands only **12** nodes with zero backtracks — a ~590x reduction
in search effort. Note that wall-clock time doesn't shrink by the same
factor, because each heuristic decision (LCV domain ordering, degree
tie-breaks) does more work per node — that's a legitimate, discussable
trade-off for your report: heuristics buy a *drastically* smaller search
tree at the cost of pricier per-node bookkeeping, and the net win grows with
problem size. Min-Conflicts, being incomplete local search, occasionally
fails to converge within its step budget on this harder instance — a good
talking point on complete vs. incomplete search.

## Viva prep — likely questions and how to answer them

**"Walk me through your CSP formulation."**
Variables = routes. Each variable's domain is every (van, driver, time) combo
that individually satisfies capacity, fuel range, and driver availability —
those are unary constraints, so I bake them into the domain instead of
checking them repeatedly. The real constraints I check during search are
binary: no van or driver double-booked on overlapping times.

**"What does AC-3 actually do here, concretely?"**
Before search starts, for every ordered pair of routes (Ri, Rj), I remove any
value from Ri's domain that has *no* compatible value left in Rj's domain
(no shared van/driver/time conflict). If a route's domain empties out, the
problem is unsolvable as posed — that's detected before wasting time on search.

**"Why MRV, then Degree heuristic, then LCV?"**
MRV picks the *most constrained* route to assign next (fewest legal options
left) — fail fast if we're heading for a dead end. Degree heuristic is only
a tie-breaker when two routes have equal domain size — pick whichever
shares vans/drivers with the most other still-unassigned routes, since
assigning it prunes the most. LCV is different: once we've picked *which*
route to assign, it orders *which value* to try first — the value that
eliminates the fewest options for everyone else, to keep future search open.

**"What does forward checking add on top of AC-3?"**
AC-3 runs once, before search. Forward checking re-prunes domains after
*every* assignment made during search, catching conflicts that only appear
once other variables are also fixed.

**"Why compare against Min-Conflicts?"**
Backtracking is complete (finds a solution if one exists, or proves none
does) and works well at this scale. Min-conflicts is an incomplete local
search — faster to get a decent assignment on much larger instances, but it
can get stuck and isn't guaranteed to find a solution. Showing both
demonstrates I understand the trade-off between systematic and local search.

**"What's the real-world constraint you found hardest to model?"**
The driver max-hours constraint, because it isn't binary — it depends on the
sum of durations across *however many* routes end up assigned to that driver,
so it can't be checked between just two variables. I check it globally, adding
up a candidate driver's total assigned minutes across the whole partial
assignment before accepting a value.

## Extending it (optional, if you want a stronger demo)

- Add a `--stress` mode in `main.py` with 15–20 routes to make the runtime gap
  between plain backtracking and the heuristic version dramatic (on 6 routes
  the instance is solved almost instantly either way).
- Swap `min_conflicts`'s random restarts for a greedy initial assignment to
  show it converging even faster.
