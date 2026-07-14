# Copyright 2026 Tobias Self
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
test_asymptotic_ethics_model.py

Persisted regression suite for the load-bearing findings from the full
development history of this project. Run with:

    pytest test_asymptotic_ethics_model.py -v

WHY THIS EXISTS: every regression check in this project, until now, was a
one-off script written, run, read, and discarded. That stopped being safe
once the codebase got large enough to outgrow memory and grep. Two concrete
incidents motivated building this rather than continuing that way:
  1. A whole parallel ecological-cost subsystem started getting built from
     scratch before discovering a complete, working one already existed a
     few hundred lines away.
  2. A false "regression" alarm was raised by comparing a single-seed run
     against a number actually derived from an 8-seed average -- a
     needless re-investigation that a persisted, seed-count-explicit test
     would have prevented outright.

SCOPE, STATED HONESTLY: this checks that the dozen or so things everything
else in this project is built on top of remain true. It is NOT a substitute
for the wide-seed adversarial sweeps that actually FOUND those bugs in the
first place (those are exploratory; this is confirmatory), and it does not
cover more than a sliver of the ~27-subsystem combinatorial space. Seed
counts and population sizes below are deliberately smaller than the full
research runs documented in FINDINGS.md -- trading statistical confidence
for the speed a suite needs to actually get run often. Treat a failure here
as "something changed, go investigate with the full methodology," not as
a final verdict on its own.
"""
import numpy as np
import pytest
from asymptotic_ethics_model import AsymptoticEthicsModel, Citizen, gini


# ============================================================
# Base economy
# ============================================================

def test_baseline_labor_economy_collapses_to_zero():
    """The original, foundational bug: a ~150x mismatch between effort_cost
    and payout crushes honest citizens to exactly zero resources. This is
    KNOWN, EXPECTED behavior under default settings, not something being
    fixed here -- this test exists so it stays exactly this broken until
    someone deliberately changes the base economy, not by accident."""
    mins = []
    for seed in range(1, 4):
        m = AsymptoticEthicsModel(100, 6, seed=seed, debug_assertions=True)
        for _ in range(200):
            m.step()
        citizens = [a for a in m.agents if isinstance(a, Citizen)]
        honest = [c.resources for c in citizens if c.strategy == "honest"]
        mins.append(min(honest))
    assert np.mean(mins) < 0.5, "baseline economy should still crush honest citizens toward zero"


def test_population_conservation_under_full_stack():
    """Structural invariant: no citizen should ever be created, duplicated,
    or lost regardless of how many features are stacked together."""
    m = AsymptoticEthicsModel(
        100, 6, seed=1, coupled_governance=True, rehabilitation_enabled=True,
        graduation_enabled=True, meaningful_care_enabled=True,
        caregiver_choice_enabled=True, policy_voting_enabled=True,
        post_scarcity_enabled=True, automation_care_absorption=1.0,
        debug_assertions=True,
    )
    for _ in range(150):
        m.step()
    total = sum(len(c.citizens) for c in m.communities)
    assert total == 100


# ============================================================
# Crisis governance -- the single most load-bearing thread
# ============================================================

def test_coupled_governance_produces_permanent_not_occasional_crisis():
    """Under default settings, crisis_management should consume the large
    majority of governance time -- confirming this is the DEFAULT state,
    not an edge case (see FINDINGS.md for the full ~70-90% characterization)."""
    crises = []
    for seed in range(1, 4):
        m = AsymptoticEthicsModel(100, 6, seed=seed, coupled_governance=True, debug_assertions=True)
        for _ in range(300):
            m.step()
        df = m.datacollector.get_model_vars_dataframe()
        crises.append(df["pct_crisis_mgmt"].tail(50).mean())
    assert np.mean(crises) > 0.4, "crisis time should still dominate under default settings"


def test_material_abundance_alone_does_not_fix_crisis():
    """Crisis governance and material scarcity are separable axes: the
    dividend alone (no care absorption) should NOT meaningfully reduce
    crisis time. If this ever starts passing at a low crisis value, the
    separability finding itself needs re-examining, not just this test."""
    crises = []
    for seed in range(1, 4):
        m = AsymptoticEthicsModel(100, 6, seed=seed, coupled_governance=True,
                                    post_scarcity_enabled=True, debug_assertions=True)
        for _ in range(300):
            m.step()
        df = m.datacollector.get_model_vars_dataframe()
        crises.append(df["pct_crisis_mgmt"].tail(50).mean())
    assert np.mean(crises) > 0.4, "material abundance alone should not fix crisis governance"


def test_full_care_absorption_reaches_near_zero_crisis():
    """The single most robust, most-repeated finding in this project:
    automation_care_absorption=1.0 combined with material sufficiency
    drives crisis time to ~0, confirmed 8/8 seeds historically at full scale."""
    crises = []
    for seed in range(1, 4):
        m = AsymptoticEthicsModel(100, 6, seed=seed, coupled_governance=True,
                                    post_scarcity_enabled=True, automation_care_absorption=1.0,
                                    debug_assertions=True)
        for _ in range(300):
            m.step()
        df = m.datacollector.get_model_vars_dataframe()
        crises.append(df["pct_crisis_mgmt"].tail(50).mean())
    assert np.mean(crises) < 0.05, "full care absorption should drive crisis time close to 0"


def test_gradual_crisis_response_matches_hard_threshold_at_full_absorption():
    """The redesigned, consent-based emergency governance should reach the
    same near-zero-crisis outcome as the original forced version once
    combined with the same severity fix -- confirming legitimacy was added
    without losing the material result."""
    declared = []
    for seed in range(1, 4):
        m = AsymptoticEthicsModel(100, 6, seed=seed, coupled_governance=True,
                                    gradual_crisis_response_enabled=True,
                                    post_scarcity_enabled=True, automation_care_absorption=1.0,
                                    debug_assertions=True)
        for _ in range(300):
            m.step()
        df = m.datacollector.get_model_vars_dataframe()
        declared.append(df["pct_emergency_declared"].tail(50).mean())
    assert np.mean(declared) < 0.05


# ============================================================
# Real bugs found and fixed -- regression guards
# ============================================================

def test_population_weighted_allocation_reduces_size_bias():
    """Regression guard for a real bug: the original allocation formula
    divided community budget by population a second time after
    prod_per_capita had already normalized once, structurally
    over-rewarding small communities independent of merit.

    NOTE: uses full scale (200/8, 8 seeds) rather than this suite's usual
    reduced scale -- verified directly that the effect reverses under
    smaller population/fewer seeds. Slower, but a fast-and-wrong test is
    worse than a slow-and-correct one."""
    def run(pop_weighted):
        mins = []
        for seed in range(1, 9):
            m = AsymptoticEthicsModel(200, 8, seed=seed, automation_level_enabled=True,
                                        automated_output_per_community=40, flat_allocation=True,
                                        population_weighted_allocation=pop_weighted, debug_assertions=True)
            for _ in range(300):
                m.step()
            citizens = [a for a in m.agents if isinstance(a, Citizen)]
            honest = [c.resources for c in citizens if c.strategy == "honest"]
            mins.append(min(honest) if honest else 0)
        return np.mean(mins)
    assert run(True) >= run(False), "population-weighted allocation should not underperform the old formula"


def test_colluder_reputation_portability_fixes_clique_bonus():
    """Regression guard for a real bug: colluder's clique reputation bonus
    was being wiped out by migration-driven reputation decay faster than
    it could ever accumulate, making the intended bonus backfire."""
    def run(portable):
        m = AsymptoticEthicsModel(100, 6, seed=1, coupled_governance=False,
                                    colluder_reputation_portable=portable, debug_assertions=True)
        for c in m.communities:
            c.policy = "clique"
        for _ in range(150):
            m.step()
        citizens = [a for a in m.agents if isinstance(a, Citizen)]
        colluders = [c.reputation for c in citizens if c.strategy == "colluder"]
        return np.mean(colluders) if colluders else 0
    assert run(True) > run(False), "portable colluder reputation should score higher than the broken version"


def test_federated_latency_does_not_blow_up():
    """Regression guard for the worst bug found in this project: a payout
    formula storing a per-capita rate at commitment time and reapplying it
    to a DIFFERENT population size at delivery time produced values in the
    billions for 3 of 10 seeds. Confirms the total-then-redivide fix holds
    under combination with newer subsystems, not just in isolation."""
    for seed in range(1, 4):
        m = AsymptoticEthicsModel(100, 6, seed=seed, federated_mode=True,
                                    communication_latency_enabled=True, min_distance=1, max_distance=15,
                                    automation_level_enabled=True, automated_output_per_community=40,
                                    debug_assertions=True)
        for _ in range(200):
            m.step()
        citizens = [a for a in m.agents if isinstance(a, Citizen)]
        max_res = max(c.resources for c in citizens)
        assert max_res < 100000, f"seed {seed}: resource blowup detected ({max_res})"


# ============================================================
# The founding philosophical thesis
# ============================================================

def test_post_labor_economy_shows_reputation_outlasting_resource_inequality():
    """The core demonstration this whole project was built to test: once
    labor decouples from survival, resource inequality collapses toward
    equality while reputation inequality persists as the more durable axis
    of stratification. If this test starts failing, the project's central
    philosophical claim needs re-examining, not just the code.

    NOTE: uses full scale (200/8, 8 seeds) -- verified directly that this
    Gini comparison is too noisy to trust at this suite's usual reduced
    scale (3 seeds produced results that didn't reliably preserve direction)."""
    resource_ginis, reputation_ginis = [], []
    for seed in range(1, 9):
        m = AsymptoticEthicsModel(200, 8, seed=seed, post_labor_economy_enabled=True, debug_assertions=True)
        for _ in range(300):
            m.step()
        citizens = [a for a in m.agents if isinstance(a, Citizen)]
        df = m.datacollector.get_model_vars_dataframe()
        resource_ginis.append(df["resource_gini"].iloc[-1])
        reputation_ginis.append(gini([c.reputation for c in citizens]))
    assert np.mean(reputation_ginis) > np.mean(resource_ginis), \
        "reputation inequality should outlast resource inequality once labor decouples from survival"


# ============================================================
# Anti-legibility / privacy
# ============================================================

def test_ledger_shipment_never_references_particulars_or_strategy():
    """Structural check, not behavioral: the Ledger's raw-material shipment
    method should not even reference local_particulars, production_strategy,
    or policy anywhere in its source -- confirmed by direct inspection, not
    by trusting the docstring's claim about its own blindness."""
    import inspect
    from asymptotic_ethics_model import SystemLedger
    src = inspect.getsource(SystemLedger.ship_raw_materials)
    assert "local_particulars" not in src
    assert "production_strategy" not in src
    assert ".policy" not in src


def test_privacy_commitments_detect_tampering():
    """Confirms the commitment/Merkle scheme actually catches a fabricated
    claim, not just that it runs without raising an error."""
    m = AsymptoticEthicsModel(100, 6, seed=1, privacy_enabled=True, debug_assertions=True)
    for _ in range(50):
        m.step()
    comm = m.communities[0]
    real_value = comm.export_zk_proof()
    _, _, details = comm.verify_proof(real_value)
    assert details["claimed_value_matches_published"], "genuine claim should verify as matching"
    _, _, fake_details = comm.verify_proof(real_value + 0.5)
    assert not fake_details["claimed_value_matches_published"], "fabricated claim should be caught, not verified"


# ============================================================
# Rehabilitation mechanics
# ============================================================

def test_peer_rehabilitation_is_at_least_as_fast_as_investment():
    """Confirms the two rehabilitation mechanics (community investment vs
    individual peer skill-building) both make real early progress, with
    peer rehabilitation's compounding-skill dynamic making it at least as
    fast as the flat community-investment mechanic."""
    def early_progress(kwargs):
        vals = []
        for seed in range(1, 4):
            m = AsymptoticEthicsModel(100, 6, seed=seed, coupled_governance=True,
                                        post_scarcity_enabled=True, automation_care_absorption=1.0,
                                        debug_assertions=True, **kwargs)
            for _ in range(11):
                m.step()
            df = m.datacollector.get_model_vars_dataframe()
            vals.append(df["pct_honest"].iloc[10])
        return np.mean(vals)
    early_investment = early_progress(dict(rehabilitation_enabled=True, graduation_enabled=True))
    early_peer = early_progress(dict(peer_rehabilitation_enabled=True))
    assert early_peer >= early_investment - 0.05, "peer rehabilitation should be at least roughly as fast early on"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
