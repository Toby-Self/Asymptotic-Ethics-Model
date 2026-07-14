Federated AI-Commons Model — Full Experimental Record

Companion to README.md. Organized by subsystem, in the order each was
built and tested. Earlier sections (base economy, federated commons,
latency, privacy, automated provisioning, the Ostrom-agency arc) are
preserved from prior revisions; this update adds the Raw Material
Conversion economy, ecological cost feedback, the resolved dead-code
items, and the persisted test suite.


Raw Material Conversion Economy

Built in response to a specific request: move from a "finished goods"
model to a two-tier system where a blind global Ledger coordinates raw
materials, and sovereign local communities convert and trade the
particulars they produce.

Architecture


SystemLedger.ship_raw_materials() — reads only raw_materials
levels, ships to any community below sustainability_threshold,
need-capped rather than proportionally force-fed (avoiding the earlier
over-delivery bug found in automated_provisioning's first version).
Verified by direct source inspection (now part of the permanent
test suite) that the method never references local_particulars,
production_strategy, or .policy — blindness is structural, not a
matter of convention.
CommunityNode.convert_raw_materials() — sovereign local
production. Each community has its own production_strategy (a
proportion vector across particular types, randomized per community at
spawn), converting raw material into local_particulars.
run_particulars_negotiation() — genuine bilateral barter, no
central coordinator, no common medium of exchange. Subject to the real
"double coincidence of wants" problem (Jevons): a trade only happens if
A has a surplus of something B lacks AND B simultaneously has a surplus
of something A lacks. Trust (reused from the federated commons) breaks
ties among valid partners.
run_production_strategy_evolution() — periodic tournament-style
evolution of production strategies, reusing the existing policy
tournament pattern.


Finding — production strategy evolution collapses to monoculture, and that's a worse problem than currency emergence

The original worry when this was built was whether one particular type
would spontaneously become a de facto currency (Menger's theory of money
emerging from barter friction). Tested rigorously with rolling-window
turnover measurement across 8 seeds and 2000 steps — no robust,
seed-independent currency emergence found. What actually happened was
more fundamental: unique_strategies collapsed from 8/8 (full diversity)
to exactly 1/8 by step 400, precisely coinciding with trade volume
flatlining to zero across all three particular types. The evolutionary
pressure (strategy_fitness_metric="total_particulars", rewarding raw
output) mechanically destroyed the specialization diversity that barter
depends on — once every community converges on the same "winning" mix,
nobody has anything a neighbor lacks, and trade becomes structurally
impossible, not just unprofitable.

Fix: strategy_fitness_metric="trade_volume" rewards communities for
successfully trading, which structurally requires staying different
enough from neighbors to have something they want. Tested directly against
the same seeds: diversity stayed consistently higher at every checkpoint
across the full 2000-step run (never dropping below 3.0 unique strategies,
vs. repeatedly collapsing to 1.5–2.0 under the raw-output metric).

Finding — the isolationist community-level test

Forcing one community's trust to zero in both directions (genuine,
verified non-participation — confirmed zero transfers across 8 seeds after
fixing a real bug in the first attempt, where get_trust()'s
setdefault() handed fresh pairings a 0.5 default instead of the intended
0.0, letting real trades slip through before the fix): high-variance,
not simply worse. Isolationist lost in 6 of 8 seeds (sometimes badly —
87% shortfall) but won dramatically in the other 2 (2–3x ahead). The
mechanism: mutual aid smooths outcomes (help when short, give when
flush); isolation forgoes both sides of that exchange, producing the same
kind of variance reduction/upside cap tradeoff real insurance markets show.


Particulars Consumption — closing the community/individual gap

Until this was built, raw_material_economy's entire output never reached
any individual citizen — confirmed directly by inspecting
convert_raw_materials and run_particulars_negotiation for any
reference to citizen.resources (none existed).

Bug found and fixed: flat valuation made trading a dominated strategy

First version: total_particulars() (a flat sum across types) determined
citizen payout. Tested directly: an isolated community's citizens
outperformed a trading community's citizens in 7 of 8 seeds — not luck,
but structural. Since barter trades only ever preserve or reduce total
quantity (trust scales executed trades below the full mutually-beneficial
amount; it's a swap, not new production), and citizen payout only cared
about total quantity, never diversity of holdings, trading could only
break even or lose value. Not trading was a strictly dominant strategy.

Fix: diminishing returns per type (amount ** 0.5, summed across
types), the standard economic device for making diversity actually
valuable. Retested on identical seeds: average flipped to favor trading
communities (19.44 vs. 16.64), with the isolationist's worst cases
becoming genuinely severe (portfolio concentration risk) — the correct
economic signature, not a rigged guarantee in either direction.


Ledger Ecological Cost

An already-complete implementation (ledger_ecological_cost_enabled,
cumulative_ledger_damage, current_ledger_throttle) was discovered
mid-session — a near-duplication incident: a parallel, differently-named
system (extraction_damage_enabled etc.) was partially built from scratch
before the existing one was found. The duplicate was removed; the existing
implementation was verified complete (constructor params, storage, call
sites, data collector entries all present) rather than rebuilt.

What it does: a single shared damage signal, accumulating from total
delivery (dividend payouts + raw material shipments combined, since both
count as "automation-based delivery"), throttles both systems
consistently via get_ledger_throttle_factor().

Finding — default parameters are too aggressive at this population scale

Tested directly via the isolationist experiment: with
ledger_ecological_cost_enabled=True at default settings, the throttle
collapsed to 0.200 (near its floor) and both isolationist and trading
communities' citizens crashed to ~0.02 resources — indistinguishable from
each other and from the pre-fix base labor economy. The dividend didn't
get moderately constrained; it collapsed almost entirely. Root cause:
defaults were calibrated without accounting for how much continuous
delivery this specific economy generates (200 citizens × 1.5/step
dividend = 300 units of damage-generating delivery per tick). Open
question, not yet resolved: what damage-rate calibration constrains
abundance meaningfully without collapsing it to zero — flagged for a
future sweep, not answered yet.


Community Assimilation — the "ghost town" problem, solved in two stages

Finding — migration doesn't recognize abandonment at all

A fully evacuated community gets repopulated by ordinary migration within
a single step (10–15 citizens landing there by pure chance) — migration
treats every community as an equally valid destination regardless of
current population. To study genuine sustained abandonment, migration had
to be artificially blocked for testing purposes.

Finding — sustained abandonment created two real problems, not one

In federated mode: an empty community's local_need_signal reads as
enormous surplus (target scales with population; zero population means
zero target), making it a "phantom donor" — real neighbors drained
15.95 total resources from it over 300 steps, and (since every successful
transfer builds bilateral trust) the ghost town ended up with genuine,
substantial trust relationships (0.5–0.95) with five living communities —
built entirely by having no agency to ever refuse.

In the raw material economy: local_particulars grew linearly,
forever, with zero citizens — 94.5 → 1174.5 over 300 steps, no cap
anywhere in the code (unlike local_reserve/global_reserve, both
explicitly capped at 5000). An abandoned automated factory running
indefinitely with nobody home.

Fix: two deliberately distinct stages, not one


Wind-down (immediate, free, fully reversible) — the moment a
community empties, convert_raw_materials and ship_raw_materials
both freeze completely. Confirmed directly: raw materials and
particulars held exactly flat for 15+ steps, and resumed production
in a single step upon repopulation with zero cost either way.
Assimilation (only after abandonment_threshold sustained empty
steps, default 30) — production and shipment redirect permanently to
whichever neighbor already trusts the community most (a fitting reuse
of the phantom-donor trust relationships). Confirmed: the ghost stayed
at exactly 0.00 for both raw materials and particulars across 120+
steps post-assimilation, with the neighbor absorbing the full output.


Deliberate scope decision: SystemLedger.ship_raw_materials() reads
comm.assimilated_by — a narrow, explicit exception to blindness,
justified as a logistics fact (where to physically deliver) rather than a
production or governance fact (what gets made, how it's decided).
Documented directly in the method's own docstring.


Citizen Philanthropy

Individual resources for reputation, explicitly not a currency — a direct
operationalization of the post-labor-economy finding that reputation
becomes the durable axis of stratification once material want is solved.

Bug found and fixed: reputation-laundering via the unconditional dividend

First version rewarded any citizen with surplus, regardless of strategy.
Tested directly: lazy citizens' reputation jumped nearly 15x (0.058
→ 0.839), and in absolute terms gained more reputation than honest
citizens did — because the universal dividend gives every strategy similar
surplus regardless of real contribution, and the reward wasn't gated on
anything behavioral. A citizen who contributed nothing could launder
unearned dividend money into reputation.

Fix: philanthropy_min_contribution gates the reputation reward (not
the donation itself, which still moves resources to the needy community
either way) on the citizen's current contribution level. Retested: lazy
and parasite reputation fell exactly back to their pre-philanthropy
baselines — completely excluded — while honest/colluder kept the
benefit.


Rehabilitation Mechanics — the dead-code items, resolved

perform_rehabilitation → peer_rehabilitation_enabled

Previously dormant for many revisions (flagged as a design decision never
made). Resolved by wiring it in as a genuine, mutually-exclusive
alternative to the community-investment mechanic, built to be directly
compared rather than combined (a warning fires if both are enabled
simultaneously).

Mechanism: individual, relational, skill-building — a specific honest
citizen rehabilitates a specific target, with success probability
min(0.9, 0.08 + experience * 0.02). Every success increments the
rehabilitator's own experience, making them measurably better at the
next attempt — a compounding dynamic the original mechanic structurally
lacks (its progression is per-target streak, not per-helper skill).

Finding: both mechanics converge to the same long-run flourishing
ceiling (0.764 vs. 0.764 pct_honest, 72.9 vs. 72.6 cumulative
conversions) — but peer rehabilitation gets there measurably faster,
consistently ahead at every early checkpoint (10-point lead at step 10:
0.599 vs. 0.491), converging as both approach the shared ceiling. Same
"speed, not destination" pattern found earlier with caregiver choice, now
confirmed to apply to the underlying mechanism choice too, not just to
whether pairing is random or chosen.

socialize_new_agent → deleted

Confirmed via direct search (grep for every Citizen( construction and
.citizens.append() that no birth/spawn mechanism exists anywhere in the
model — citizens are only ever created once, at __init__. The method was
permanently unreachable, not merely unused. Removed outright rather than
left as inert reference code (14 lines).


Persisted Test Suite

Built after two concrete incidents demonstrated that one-off regression
scripts had stopped being safe at this codebase's size: the
ledger_ecological_cost near-duplication, and an earlier false-regression
alarm caused by comparing a single-seed run against a value actually
derived from an 8-seed average.

13 tests, pytest test_federated_ai_commons_model.py, covering: base
economy invariants (2), the crisis-governance thread (4 — the project's
single most load-bearing finding), real-bug regression guards (3:
population-weighted allocation, colluder portability, the federated+latency
payout blowup), the founding philosophical thesis (1), anti-legibility/
privacy structural checks (2), and the rehabilitation-mechanics comparison
(1).

Dogfooding caught three real problems before the suite was ever
trusted, worth recording as a finding in its own right:


The population-weighted-allocation test reversed direction at
reduced population/seed scale (100/6, 3 seeds) — verified the real
finding only reproduces reliably at full scale (200/8, 8 seeds), where
it matches historical values exactly (49.31 vs. 43.54).
The post-labor-economy Gini comparison was too noisy at reduced scale
to reliably preserve direction — same fix, same exact-match result at
full scale (reputation Gini 0.501 vs. resource Gini 0.385).
A genuine bug in the test code itself: assert x is True fails even
when x is correctly True, because NumPy booleans aren't the same
object as Python's built-in True — is checks identity, not
equality. Fixed to a plain truthy check.


Explicit scope, stated in the suite's own docstring: this confirms
roughly a dozen load-bearing findings continue to hold; it is not a
substitute for the wide-seed adversarial sweeps that originally found the
bugs it now guards against, and covers a small fraction of the
~28-subsystem combinatorial space.


The "Big Push" — reconsidered, not removed (there was nothing to remove)

Clarified that the 90% forced-conversion event referenced throughout
FINDINGS.md's earlier sections was never implemented in the model
file itself — every test of it was done in throwaway experiment scripts,
manually flipping citizen.strategy from outside the running model.
Confirmed by direct search: zero functional references in
federated_ai_commons_model.py, only two comments mentioning it as
historical context.

Reconsidered finding, given a direct challenge to its necessity: once
the environment is properly fixed from the start (full care absorption


dividend + meaningful care all active at tick zero), organic
rehabilitation reaches the same flourishing outcome in ~21–26 steps with
no push at all — but purely organic conversion only succeeded in 6 of
8 seeds within a 100-step window; 2 seeds never got there. A modest
20–30% push (not the dramatic 90%) restored reliability to 7–8/8 seeds
without the implausible "overnight mass transformation" feel — the honest
middle ground between "we need it" and "we don't."



Known issues / open items (cumulative, updated)


Default labor economy still has the ~150x cost/payout mismatch, with
no runtime warning. Long-standing, still open.
Federated + automation threshold interaction still unfixed — mean_trust
silently stays NaN rather than erroring when both are combined.
Ledger ecological cost default calibration collapses abundance rather
than moderating it — a real, tested finding, not yet resolved with a
better calibration.
"Time" as a scarcity dimension remains unbuilt. Relationships
(affinity) and locality (contested sites, migration) both got real
mechanisms during the Ostrom-agency arc; citizens choosing how to
allocate their own time never did.
No exhaustive combinatorial coverage — 132 parameters, 28
independent subsystems, the persisted suite covers ~13 load-bearing
findings, nowhere near the full interaction space. A second
near-duplicate feature, undiscovered, remains a live possibility.
Reproducibility improved, not exact — mesa AgentSet shuffle
ordering can still cause fractional drift between identically-seeded
runs.
Both previously-flagged dead-code items are now resolved
(perform_rehabilitation → peer_rehabilitation_enabled;
