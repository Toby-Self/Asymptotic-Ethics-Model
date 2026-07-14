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

import mesa
import numpy as np
from collections import deque
import hashlib
import secrets

# ============================================================
# Privacy primitives: real SHA-256 commitments + a real Merkle tree.
#
# HONEST SCOPE: this is NOT a zero-knowledge proof system. It does not
# cryptographically prove that an aggregate (e.g. a percentile) was
# computed correctly on hidden inputs -- that requires actual zk-SNARK/
# zk-STARK circuits, a genuinely hard cryptography problem out of scope
# here. What this DOES provide, for real:
#   1. Input hiding: a citizen's raw reputation is never exposed through
#      any external-facing interface -- only a commitment (a one-way hash)
#      is public. The value can't be recovered from the commitment.
#   2. Tamper-evidence: the Merkle root binds a community's PUBLISHED
#      aggregate to a specific, fixed set of committed inputs. If anyone
#      later claims a different set of citizens (or values) produced that
#      aggregate, the root won't match -- fabrication is detectable.
#   3. Voluntary selective disclosure: any citizen can choose to "open"
#      their own commitment (reveal value + nonce) to prove their specific
#      data was correctly included, without anyone being forced to reveal
#      anything. This is a real, meaningful privacy pattern on its own.
# What it does NOT provide: proof that the published percentile itself is
# the mathematically correct result of the hidden values, without someone
# trusted (here, the CommunityNode) actually computing on real data
# internally -- same as any real system, e.g. a company's payroll process
# has to know real salaries to run payroll; the point of this scheme is
# what gets revealed to OTHERS, not that the computing entity is blind.
# ============================================================

def make_commitment(value, nonce):
    """A real, one-way SHA-256 commitment. Given only this hash, the
    original value cannot be recovered -- that's what makes it a genuine
    commitment rather than just an encoding."""
    return hashlib.sha256(f"{value}:{nonce}".encode()).hexdigest()

def verify_commitment(value, nonce, commitment):
    return make_commitment(value, nonce) == commitment

def merkle_root(hashes):
    """Standard binary Merkle tree over a list of hex-digest hashes.
    Odd node at any level is paired with itself (common convention)."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha256((level[i] + level[i + 1]).encode()).hexdigest()
                 for i in range(0, len(level), 2)]
    return level[0]
import hashlib
import secrets

# ============================================================
# Citizen Agent
# ============================================================
class Citizen(mesa.Agent):
    def __init__(self, model, community, strategy="honest"):
        super().__init__(model)
        self.community = community
        self.strategy = strategy
        self.reputation = 0.5
        self.resources = 1.0
        self.contribution = 0.0
        # --- Rehabilitation Protocol state ---
        self.care_streak = 0
        self.rehabilitated = False
        self.recovery_tenure = 0
        # NOTE: 'experience' is tracked but not currently read by any active
        # code path. It exists to support an alternative peer-rehabilitation
        # mechanic (see Model.perform_rehabilitation) that is defined but
        # deliberately not wired into step() -- see conversation notes.
        self.experience = 0
        # --- Meaningful Care state (individual caregiver-target pairing) ---
        self.caregiver_of = None  # for a lazy/parasite citizen: the honest citizen caring for them
        self.caring_for = None    # for an honest citizen: the specific citizen they're caring for
        # --- Relational agency state (Ostrom principle 6: real voice, not
        # forced pairing) ---
        # Persistent, bilateral, builds through actual interaction history --
        # a real stand-in for "relationship," one of the genuinely scarce
        # things left once resources aren't. Never exported, never used by
        # any allocation formula -- purely relational.
        self.affinities = {}  # other citizen's unique_id -> float in [0, 1]
        self.relapse_count = 0  # this citizen's own track record of broken care relationships
        # --- Privacy state ---
        self._reputation_nonce = secrets.token_hex(16)

    def get_affinity(self, other):
        """other is a Citizen object, not just an id -- needed to read their
        relapse_count for a first-encounter default. NOT wired to
        reputation: a gamed reputation looks identical to an earned one by
        construction, so scaling trust off reputation would just reward
        successful gaming with a bigger head start. Relapse history is a
        real behavioral record instead -- can't be faked the same way."""
        if other.unique_id not in self.affinities:
            default = max(0.1, 0.5 - self.model.relapse_history_penalty * other.relapse_count)
            self.affinities[other.unique_id] = default
        return self.affinities[other.unique_id]

    def preferred_policy(self):
        """What policy this citizen would vote for, based on which policy's
        mechanics actually benefit their strategy -- self-interest, not
        civic virtue. honest benefits most from being genuinely rewarded
        for contribution (meritocratic). colluder has an explicit built-in
        bonus under clique. lazy/greedy/parasite all do best under lenient
        specifically: highest care-load tolerance, slowest reputation
        decay, and (per the memory-decay findings) the best protection for
        a gamed reputation. Nobody's self-interest points toward strict --
        it has no natural constituency in this preference scheme."""
        if self.strategy == "honest":
            return "meritocratic"
        elif self.strategy == "colluder":
            return "clique"
        else:  # lazy, greedy, parasite
            return "lenient"

    def reputation_commitment(self):
        """Public: a one-way hash. Cannot be used to recover self.reputation."""
        return make_commitment(self.reputation, self._reputation_nonce)

    def open_reputation_commitment(self):
        """Voluntary disclosure: THIS citizen chooses to reveal their own
        value + nonce, letting anyone verify it against a previously
        published commitment. Nobody else can be forced to do this."""
        return self.reputation, self._reputation_nonce

    def step(self):
        penalty = self.community.productivity_penalty

        if self.strategy == "honest":
            self.contribution = np.random.uniform(0.6, 1.0) * penalty
        elif self.strategy == "lazy":
            drain_intensity = np.random.uniform(0.2, 0.6)
            raw_drain = drain_intensity + self.model.stabilization_cost
            multiplier = self.model.care_load_multiplier.get(self.community.policy, 1.0)
            # Under post-scarcity, automation can absorb some or all of the
            # administrative/attentional burden ("Dopamine Drain") that lazy
            # agents generate for their community, rather than it landing on
            # community capacity (care_load) the way it does under scarcity.
            # This is a DIFFERENT lever from the material dividend above --
            # automation_care_absorption has to be explicitly nonzero to
            # matter. Gated on "some form of automation exists" (post_scarcity
            # OR production-side automation), not narrowly on the dividend --
            # this was previously gated on post_scarcity_enabled alone, which
            # meant automation_care_absorption silently did nothing at all
            # if only automation_level_enabled was on. Fixed.
            some_automation_present = self.model.post_scarcity_enabled or self.model.automation_level_enabled
            absorbed_fraction = self.model.automation_care_absorption if some_automation_present else 0.0
            unabsorbed_drain = raw_drain * (1.0 - absorbed_fraction)
            self.community.care_load += unabsorbed_drain * multiplier
            self.contribution = np.random.uniform(0.0, 0.1)
        elif self.strategy == "greedy":
            self.contribution = (0.8 if self.reputation < 0.4 else 0.15) * penalty
        elif self.strategy == "colluder":
            self.contribution = np.random.uniform(0.4, 0.8) * penalty
        elif self.strategy == "parasite":
            self.contribution = 0.0
            self.reputation = 0.9

        effort_cost = self.contribution ** 2
        if not self.model.post_labor_economy_enabled:
            self.resources -= effort_cost
        # else: contribution costs nothing materially -- labor is no longer
        # tied to survival at all. Citizens still contribute at their
        # strategy-driven level (honest still draws 0.6-1.0, etc.) but that
        # now represents voluntary dedication, not an economic necessity.
        # Reputation (via update_local_rep below, unchanged) remains the
        # only reward for contributing -- meaning/status, not resources.

        # --- Post-Scarcity: Automation Dividend ---
        # Unconditional, identical for every citizen regardless of strategy,
        # community, policy, or reputation. Deliberately bypasses the
        # Ledger's GOVERNANCE role entirely -- no legibility, no reputation
        # gating, no crisis-state dependency. That's still true here.
        # What's NOT still true, once ledger_ecological_cost_enabled: this
        # doesn't bypass PHYSICS. The dividend represents real automated
        # production, and real production has a real ecological cost --
        # treating it as infinitely free was inconsistent with every other
        # "post-scarcity, not post-physics" mechanism already built (see
        # contested_sites' ecological_impact). The same throttle that
        # constrains raw material shipment constrains this too.
        if self.model.post_scarcity_enabled:
            delivered = self.model.automation_dividend_per_capita * self.model.get_ledger_throttle_factor()
            self.resources += delivered
            self.model.ledger_delivery_this_step += delivered

        self.reputation = self.community.update_local_rep(self)
        if self.model.privacy_enabled:
            # A fresh nonce every update -- reusing a nonce across different
            # values would let an observer detect WHEN reputation changed
            # even without learning the value, a real privacy leak.
            self._reputation_nonce = secrets.token_hex(16)
        if self.resources < 0:
            self.resources = 0

        # --- Rehabilitation Protocol ---
        # Investment is only available when the community is on normal
        # governance -- crisis_management explicitly deprioritizes anything
        # discretionary in favor of raw throughput, so rehabilitation is the
        # first thing suspended when a community is overwhelmed.
        if self.model.rehabilitation_enabled and self.strategy in ("lazy", "parasite"):
            investing = self.community.policy != "crisis_management"
            if investing:
                # The "Social Work tax": running the program costs real
                # capacity, added on top of whatever passive drain the
                # agent's strategy already generates. This is what lets
                # over-investment trigger the very crisis that halts it.
                self.community.care_load += self.model.investment_cost_per_agent
                # --- Care Economy: care work counted as real output ---
                # Previously this was pure cost with zero offsetting credit
                # anywhere in the model -- a direct instance of the
                # "invisible labor" critique (care work isn't counted as
                # economic output even though it demonstrably takes real
                # capacity to perform). When enabled, the same effort that
                # generates the tax also generates measured productivity,
                # feeding into reserve growth AND the Ledger's allocation
                # competition exactly like labor or automated output does.
                if self.model.care_work_counts_as_productivity:
                    self.community.care_work_output += (
                        self.model.investment_cost_per_agent * self.model.care_work_productivity_multiplier
                    )

                # --- Meaningful Care: individual caregiver-target pairing ---
                # Distinct from the abstract productivity credit above: this
                # rewards a SPECIFIC honest citizen for caring for a SPECIFIC
                # target, representing intrinsic reward from meaningful work
                # rather than an accounting fix. Community capacity-limited:
                # if no honest citizen is currently free to pair, this target
                # goes without a caregiver that step (a community can only
                # meaningfully care for as many people as it has willing,
                # available carers).
                if self.model.meaningful_care_enabled:
                    if self.caregiver_of is None or self.caregiver_of not in self.community.citizens:
                        available = [
                            c for c in self.community.citizens
                            if c.strategy == "honest" and c.caring_for is None and c is not self
                        ]
                        if self.model.caregiver_choice_enabled:
                            # Real mutual agency: the target approaches
                            # candidates in order of ITS OWN preference
                            # (highest affinity first -- who they'd feel
                            # most comfortable being helped by), but each
                            # candidate can genuinely decline based on
                            # THEIR OWN affinity toward the target. This is
                            # the difference between assignment and choice:
                            # a match here required both people to actually
                            # be willing, not just be free.
                            ranked = sorted(available, key=lambda c: -self.get_affinity(c))
                            matched = False
                            for candidate in ranked:
                                self.model.pairing_attempts_this_step += 1
                                if candidate.get_affinity(self) >= self.model.caregiver_acceptance_threshold:
                                    self.caregiver_of = candidate
                                    candidate.caring_for = self
                                    matched = True
                                    break
                                else:
                                    self.model.pairing_declines_this_step += 1
                            if not matched and available:
                                # Genuine unmet need -- SOMEONE was free but
                                # nobody was willing. Distinct from simple
                                # capacity shortage (nobody free at all),
                                # which already existed before this feature
                                # and isn't a new relational-agency finding.
                                self.model.unmet_care_need_this_step += 1
                        elif available:
                            # Old behavior when caregiver_choice_enabled=False:
                            # random assignment, no voice for either party.
                            chosen = self.model.random.choice(available)
                            self.caregiver_of = chosen
                            chosen.caring_for = self
                    if self.caregiver_of is not None:
                        cg = self.caregiver_of
                        cg.reputation = min(1.0, cg.reputation + self.model.caregiver_reputation_bonus)
                        cg.resources += self.model.caregiver_resource_bonus
                        if self.model.caregiver_choice_enabled:
                            # The relationship deepens through actual
                            # continued interaction -- this is what makes
                            # affinity a genuine record of relational
                            # history rather than a static trait.
                            new_a = min(1.0, cg.get_affinity(self) + self.model.affinity_gain_per_interaction)
                            new_b = min(1.0, self.get_affinity(cg) + self.model.affinity_gain_per_interaction)
                            cg.affinities[self.unique_id] = new_a
                            self.affinities[cg.unique_id] = new_b

                self.care_streak += 1
                p_convert = self.model.conversion_base_rate * min(1.0, self.care_streak / self.model.conversion_streak_needed)
                if self.model.meaningful_care_enabled and self.caregiver_of is not None:
                    # The actual test of the hypothesis: does having a
                    # specific, engaged caregiver make conversion more
                    # likely than generic, impersonal community investment?
                    # Without this, rewarding caregivers has no causal path
                    # to affecting outcomes at all -- it's a side-payment
                    # disconnected from the mechanism it's meant to improve.
                    p_convert *= self.model.paired_care_conversion_multiplier
                if np.random.random() < p_convert:
                    self.strategy = "honest"
                    self.rehabilitated = True
                    self.care_streak = 0
                    self.model.conversions_this_step += 1
                    if self.model.meaningful_care_enabled and self.caregiver_of is not None:
                        # The payoff: a real, one-time reward for having
                        # actually helped someone specific succeed, distinct
                        # from the small ongoing maintenance reward above.
                        cg = self.caregiver_of
                        cg.reputation = min(1.0, cg.reputation + self.model.caregiver_conversion_bonus_reputation)
                        cg.resources += self.model.caregiver_conversion_bonus_resources
                        cg.caring_for = None
                    self.caregiver_of = None
            else:
                # Care was interrupted: progress erodes but doesn't vanish.
                self.care_streak = max(0, self.care_streak - self.model.relapse_decay)
                if self.model.meaningful_care_enabled and self.care_streak == 0 and self.caregiver_of is not None:
                    # Gave up without success -- pairing dissolves, caregiver freed.
                    self.caregiver_of.caring_for = None
                    self.caregiver_of = None

        elif self.model.peer_rehabilitation_enabled and self.strategy in ("lazy", "parasite"):
            # Alternative to the community-scale, impersonal investment
            # mechanic above: individual, relational, skill-building.
            # A specific honest citizen rehabilitates a specific target,
            # getting better at it with practice (Model.perform_rehabilitation's
            # experience-based success formula) rather than the community
            # paying a flat administrative cost regardless of who's involved.
            # Deliberately mutually exclusive with rehabilitation_enabled
            # (see the warning printed in __init__ if both are set) --
            # built to be directly compared against it, not combined with it.
            # Same crisis-gating as the investment mechanic, for a fair
            # comparison: crisis suspends this too, it isn't a free pass.
            investing = self.community.policy != "crisis_management"
            if investing:
                if self.caregiver_of is None or self.caregiver_of not in self.community.citizens:
                    available = [
                        c for c in self.community.citizens
                        if c.strategy == "honest" and c.caring_for is None and c is not self
                    ]
                    if available:
                        chosen = self.model.random.choice(available)
                        self.caregiver_of = chosen
                        chosen.caring_for = self
                if self.caregiver_of is not None:
                    success = self.model.perform_rehabilitation(self.caregiver_of, self)
                    if success:
                        self.rehabilitated = True
                        self.model.conversions_this_step += 1
                        self.caregiver_of.caring_for = None
                        self.caregiver_of = None
            else:
                # Crisis suspends peer rehabilitation too -- no unfair
                # advantage over the investment mechanic, which is
                # equally blocked during crisis_management.
                if self.caregiver_of is not None:
                    self.caregiver_of.caring_for = None
                    self.caregiver_of = None

        # Rehabilitated agents are fragile initially, but under the
        # Graduation Protocol, sustained time-since-conversion durably
        # reduces relapse risk rather than holding it constant forever.
        # Without graduation: effective_relapse == relapse_probability always.
        # With graduation: risk decays toward a small floor as tenure grows,
        # asymptotic, never exactly zero -- durable is not the same as immune.
        if self.rehabilitated:
            self.recovery_tenure += 1
            if self.model.graduation_enabled:
                effective_relapse = self.model.relapse_probability * (
                    0.5 ** (self.recovery_tenure / self.model.graduation_halflife)
                )
            else:
                effective_relapse = self.model.relapse_probability

            if self.community.policy == "crisis_management":
                if np.random.random() < effective_relapse:
                    self.strategy = "lazy"
                    self.rehabilitated = False
                    self.care_streak = 0
                    self.recovery_tenure = 0
                    self.model.relapses_this_step += 1
                    self.relapse_count += 1
                    if self.model.caregiver_choice_enabled and self.caregiver_of is not None:
                        # A relationship that ends in relapse is a real
                        # strain, not neutral -- affinity takes a hit on
                        # both sides, same as any real relational setback.
                        cg = self.caregiver_of
                        cg.affinities[self.unique_id] = max(0.0, cg.get_affinity(self) - self.model.affinity_loss_on_relapse)
                        self.affinities[cg.unique_id] = max(0.0, self.get_affinity(cg) - self.model.affinity_loss_on_relapse)
                        cg.caring_for = None
                        self.caregiver_of = None


# ============================================================
# Community Node
# ============================================================
class CommunityNode(mesa.Agent):
    def __init__(self, model, policy="meritocratic"):
        super().__init__(model)
        self.policy = policy
        self.citizens = []
        self.global_budget = 0
        self.care_load = 0.0
        self.productivity_penalty = 1.0
        self.crisis_threshold = model.crisis_threshold
        # --- Contestable governance state ---
        self.recall_cooldown = 0
        self.recall_events = 0
        # --- Coupled governance / Resilience Protocol state ---
        self.in_crisis_management = False
        self.pre_crisis_policy = None
        self.crisis_transitions = 0
        # --- Gradual Crisis Response state (Ostrom-aligned rework) ---
        self.crisis_severity = 0.0     # smooth 0-1, the real/unavoidable strain
        self.emergency_declared = False  # citizen-VOTED status, not forced
        # --- Care Economy state ---
        self.care_work_output = 0.0  # reset each step in Model.step
        # --- Federated Network of Commons state ---
        # Only used when model.federated_mode=True. local_reserve replaces
        # any dependence on the global pool; trust is bilateral and persists
        # across the whole run, lazily initialized on first contact.
        self.local_reserve = model.local_reserve_initial
        self.trust = {}  # other_community.unique_id -> float in [0, 1]
        self.transfers_given_cumulative = 0.0
        self.transfers_received_cumulative = 0.0
        # --- Communication Latency state ---
        # distance = one-way ticks to/from a shared reference point ("hub"),
        # used two ways: centralized allocation's round-trip to that hub
        # (2x distance), and federated pairwise latency between two
        # communities (|distance_i - distance_j|, i.e. communities at
        # similar distances from the hub are also close to each other --
        # a simple linear layout, not literal orbital mechanics, but enough
        # to make distances genuinely asymmetric across community pairs).
        self.distance = model.random.randint(model.min_distance, model.max_distance) if model.communication_latency_enabled else 0
        self.history = {}  # tick -> snapshot dict, pruned each step

        # --- Raw Material Conversion economy state ---
        # Only used when model.raw_material_economy_enabled=True. Two
        # genuinely different goods, not one fungible number: raw_materials
        # (what the blind global Ledger sees and ships), and
        # local_particulars (what this community actually produces --
        # invisible to the Ledger by construction, not just by convention).
        self.raw_materials = model.raw_materials_initial
        self.local_particulars = {ptype: 0.0 for ptype in model.particular_types}
        # production_strategy: proportions summing to ~1.0 across particular
        # types. This is the evolvable trait -- randomized at spawn so
        # different communities start with genuinely different production
        # mixes, letting run_production_strategy_evolution() select among
        # them later.
        if model.raw_material_economy_enabled:
            raw_weights = [model.random.random() for _ in model.particular_types]
            total_w = sum(raw_weights) or 1.0
            self.production_strategy = {
                ptype: w / total_w for ptype, w in zip(model.particular_types, raw_weights)
            }
        else:
            self.production_strategy = {}
        self.trade_volume_since_tournament = 0.0

        # --- Community Assimilation state ---
        # Tracks sustained abandonment (not the momentary emptiness that
        # ordinary migration usually fills within one step). Once a
        # community has been genuinely empty long enough, its production
        # gets redirected to a neighbor rather than either freezing in
        # place or growing unbounded with nobody there to use it.
        self.consecutive_empty_steps = 0
        self.assimilated_by = None

    def get_trust(self, other_id):
        return self.trust.setdefault(other_id, self.model.trust_initial)

    def record_history_snapshot(self, tick):
        """Called every step when communication_latency_enabled, so any
        community can later look up what this community's state WAS at a
        given past tick -- modeling that distant observers only see old news."""
        self.history[tick] = {
            "local_reserve": self.local_reserve,
            "need_signal": self.local_need_signal(self.model),
            "productivity": self.productivity(),
            "proof": self.export_zk_proof(),
        }
        max_age = self.model.max_distance * 3 + 5
        for old_tick in [t for t in self.history if t < tick - max_age]:
            del self.history[old_tick]

    def get_delayed_snapshot(self, current_tick, delay):
        """Most recent snapshot at or before current_tick - delay. Falls
        back to the oldest available snapshot if the community didn't exist
        that far back (start of run), rather than crashing."""
        target = current_tick - delay
        available = [t for t in self.history if t <= target]
        if not available:
            available_any = sorted(self.history.keys())
            if not available_any:
                return {"local_reserve": self.local_reserve, "need_signal": 0.0,
                        "productivity": 0.0, "proof": 0.0}
            return self.history[available_any[0]]
        return self.history[max(available)]

    def step(self):
        if self.model.coupled_governance and self.model.gradual_crisis_response_enabled:
            # Real strain is always real, regardless of whether anyone has
            # formally acknowledged it -- severity and its productivity
            # cost apply smoothly and automatically, exactly like
            # ecological impact accruing while a site is used. What's
            # DIFFERENT from the original binary version: forced policy
            # suspension is no longer automatic. It only happens if
            # citizens have actually voted to declare an emergency (see
            # Model.run_crisis_vote) -- this is the direct Ostrom-principle-2/7
            # fix: strain has real, unavoidable consequences, but a
            # community's own elected governance is only overridden with
            # its own consent, not by threshold alone.
            self.crisis_severity = min(1.0, self.care_load / self.crisis_threshold)
            self.productivity_penalty = 1.0 - self.crisis_severity * 0.2

            if self.emergency_declared and not self.in_crisis_management:
                self.pre_crisis_policy = self.policy
                self.policy = "crisis_management"
                self.in_crisis_management = True
                self.crisis_transitions += 1
            elif not self.emergency_declared and self.in_crisis_management:
                self.policy = self.pre_crisis_policy
                self.in_crisis_management = False
                self.crisis_transitions += 1
        else:
            if self.care_load > self.crisis_threshold:
                self.productivity_penalty = 0.8
            else:
                self.productivity_penalty = 1.0

            # --- Governance Override (Resilience Protocol) ---
            # This runs BEFORE recall/tournament: survival state takes precedence
            # over elected/evolved policy. Hysteresis band (crisis_threshold vs
            # recovery_threshold) prevents single-step flicker on noise alone,
            # but does NOT prevent multi-step oscillation if the underlying
            # care_load genuinely swings across the band repeatedly.
            if self.model.coupled_governance:
                if self.care_load > self.crisis_threshold:
                    if not self.in_crisis_management:
                        self.pre_crisis_policy = self.policy
                        self.policy = "crisis_management"
                        self.in_crisis_management = True
                        self.crisis_transitions += 1
                else:
                    if self.in_crisis_management and self.care_load <= self.model.recovery_threshold:
                        self.policy = self.pre_crisis_policy
                        self.in_crisis_management = False
                        self.crisis_transitions += 1

        if self.recall_cooldown > 0:
            self.recall_cooldown -= 1

        if self.model.recall_enabled and self.recall_cooldown == 0 and not self.in_crisis_management:
            self.check_recall()

    def resource_gini(self):
        return gini([c.resources for c in self.citizens])

    def contribution_gini(self):
        return gini([c.contribution for c in self.citizens])

    def check_recall(self):
        """Agents 'exit/recall' when material inequality within the
        community crosses a threshold. This is meant to fire specifically
        on the lenient-policy failure mode: reputation capture that doesn't
        show up as resource inequality yet, but does show up once you look
        at contribution vs payout mismatch."""
        if len(self.citizens) < 3:
            return
        mismatch = self.contribution_gini() - self.resource_gini()
        # High mismatch = people are being paid roughly equally despite very
        # unequal contribution -> free-riding is being rewarded -> recall trigger.
        if mismatch > self.model.recall_mismatch_threshold:
            self.trigger_recall()

    def trigger_recall(self):
        self.recall_events += 1
        self.recall_cooldown = self.model.recall_duration
        # Materially costly to the Ledger: the recall process itself burns reserve.
        self.model.global_reserve = max(0, self.model.global_reserve - self.model.recall_cost)
        # Policy is forcibly replaced (agents "throw the bums out").
        other_policies = [p for p in ["meritocratic", "strict", "lenient", "clique"] if p != self.policy]
        self.policy = self.model.random.choice(other_policies)

    def update_local_rep(self, citizen):
        c, r = citizen.contribution, citizen.reputation
        if self.policy == "meritocratic":
            rep = 0.8 * c + 0.2 * r
        elif self.policy == "clique":
            rep = r + (0.20 if citizen.strategy == "colluder" else 0)
        elif self.policy == "strict":
            rep = r + (c - 0.5) * 0.6
        elif self.policy == "lenient":
            rep = 0.95 * r + 0.05 * c
        elif self.policy == "crisis_management":
            rep = c
        else:
            rep = r

        # --- Memory Decay (Ledger-wide forgetting layer) ---
        # Applied on TOP of whatever the local policy computed, uniformly,
        # regardless of which policy is active. This is what lets a single
        # dial address stickiness that otherwise lives unevenly inside each
        # policy's own formula (meritocratic already forgets fast; lenient
        # and clique barely forget at all). memory_decay_rate is the weight
        # retained on the policy's own computed rep; the remainder is pulled
        # toward the citizen's current, instantaneous contribution.
        if self.model.memory_decay_enabled:
            rep = self.model.memory_decay_rate * rep + (1 - self.model.memory_decay_rate) * c

        # --- Gradual Crisis Response: real strain erodes trust smoothly
        # even before anyone formally declares an emergency. This is the
        # "unavoidable cost, always real" half of the design -- separate
        # from emergency_declared, which only controls whether POLICY
        # itself gets forcibly suspended (handled above via self.policy
        # already being set to "crisis_management" when declared, which the
        # branch above already covers). No-op when severity is 0 or the
        # community is already in full emergency (blending c with c).
        if self.model.gradual_crisis_response_enabled and not self.emergency_declared:
            rep = (1 - self.crisis_severity) * rep + self.crisis_severity * c

        return np.clip(rep, 0, 1)

    def export_zk_proof(self):
        """Computes the 90th-percentile reputation score. When
        model.privacy_enabled=True, this ALSO records a commitment-based
        audit trail (self.last_proof_commitments, self.last_proof_root) so
        the published number can be externally verified without exposing
        any individual citizen's raw reputation. The percentile still has
        to be computed on real values internally -- that's unavoidable for
        any entity actually producing the number, same as any real system.
        The privacy property is about what's exposed to OTHERS afterward.
        """
        scores = [c.reputation for c in self.citizens]
        percentile = np.percentile(scores, 90) if scores else 0

        if self.model.privacy_enabled:
            commitments = [(c.unique_id, c.reputation_commitment()) for c in self.citizens]
            self.last_proof_commitments = commitments
            self.last_proof_root = merkle_root([h for _, h in commitments])
            self.last_proof_value = percentile

        return percentile

    def verify_proof(self, claimed_value, spot_check_openings=None):
        """External, honest verification -- callable by anyone, using only
        what's public plus whatever citizens have voluntarily opened.
        Returns (root_matches, spot_checks_passed, details) rather than a
        single boolean, so a caller can see exactly what was and wasn't
        actually verified -- this does NOT prove the percentile itself is
        mathematically correct (that needs real ZK circuits, out of scope);
        it proves the claimed inputs weren't fabricated or substituted, and
        that any voluntarily-opened citizen's data matches what was
        committed at proof time.
        """
        if not hasattr(self, "last_proof_root"):
            return False, [], {"error": "no proof has been published by this community yet"}

        recomputed_root = merkle_root([h for _, h in self.last_proof_commitments])
        root_matches = (recomputed_root == self.last_proof_root)

        spot_results = []
        if spot_check_openings:
            committed = dict(self.last_proof_commitments)
            for citizen_id, value, nonce in spot_check_openings:
                expected_commitment = committed.get(citizen_id)
                passed = expected_commitment is not None and verify_commitment(value, nonce, expected_commitment)
                spot_results.append((citizen_id, passed))

        details = {
            "published_value": self.last_proof_value,
            "claimed_value_matches_published": abs(claimed_value - self.last_proof_value) < 1e-9,
            "n_committed_citizens": len(self.last_proof_commitments),
        }
        return root_matches, spot_results, details

    def productivity(self):
        labor_output = sum(c.contribution for c in self.citizens)
        output = labor_output
        if self.model.automation_level_enabled:
            # Genuine production-side automation: this output is NOT
            # attributed to any citizen, doesn't depend on contribution or
            # population size, and flows through every downstream use of
            # productivity() exactly like labor output does -- the Ledger's
            # prod_per_capita weighting, reserve growth, migration deficit
            # signal, all of it. Contrast with the automation_dividend
            # (post_scarcity_enabled), which bypasses the Ledger entirely;
            # this instead changes what the Ledger is actually distributing.
            output += self.model.automated_output_per_community
        if self.model.care_work_counts_as_productivity:
            output += self.care_work_output
        return output

    def labor_productivity(self):
        """Labor-only output, excluding automation -- exposed for diagnosing
        what fraction of total output is still labor-sourced vs automated."""
        return sum(c.contribution for c in self.citizens)

    # ============================================================
    # Federated Network of Commons: local production, maintenance,
    # and distribution. Only called when model.federated_mode=True.
    # Deliberately mirrors the shape of the centralized reserve logic
    # (production, upkeep, growth, per-capita payout) so behavior is
    # comparable to the old system where it can be, and to reuse the
    # allocation_weighting_mode / automation / care-economy inputs that
    # already exist rather than reimplementing them.
    # ============================================================

    def local_production_and_maintenance(self, model):
        """No shared pool, no global growth formula. Each community's
        reserve grows or shrinks based entirely on ITS OWN production minus
        ITS OWN maintenance cost -- genuine local sustainability, not a
        slice of a global number. Reuses productivity() so automation and
        care-economy credits still apply exactly as they do centrally."""
        total_local_prod = self.productivity()  # labor + automation + care-work, per existing logic
        maintenance_cost = model.local_maintenance_per_capita * (len(self.citizens) + 1e-6)
        self.local_reserve += (total_local_prod - maintenance_cost) * model.local_growth_rate
        self.local_reserve = max(0.0, min(self.local_reserve, 5000.0))

    def distribute_locally(self, model):
        """Per-capita payout sourced entirely from this community's own
        local_reserve -- no cross-community competition, no global budget.
        Reuses distribution_fraction for consistency with the centralized
        system's semantics (fraction of reserve paid out per step)."""
        if not self.citizens:
            return
        total_payout = self.local_reserve * model.distribution_fraction
        per_capita = total_payout / len(self.citizens)
        for citizen in self.citizens:
            citizen.resources += per_capita
        self.local_reserve -= total_payout

    def local_need_signal(self, model):
        """Positive = in deficit (needs aid), negative = has surplus.
        Combines reserve shortfall against a per-capita target with
        care_load pressure, so a community can register need either from
        thin reserves or from acute administrative strain, matching the
        two distress channels that already exist elsewhere in the model."""
        reserve_gap = (model.local_reserve_target * len(self.citizens)) - self.local_reserve
        care_pressure = max(0.0, self.care_load - self.crisis_threshold) * model.local_care_weight
        return reserve_gap + care_pressure

    def update_abandonment_status(self, model):
        """Called every step. Tracks sustained (not momentary) emptiness
        and triggers/clears assimilation accordingly. Repopulation always
        clears assimilation immediately -- once someone actually lives
        here again, this stops being a ghost town, full stop."""
        if self.citizens:
            self.consecutive_empty_steps = 0
            self.assimilated_by = None
            return

        self.consecutive_empty_steps += 1
        if self.assimilated_by is None and self.consecutive_empty_steps >= model.abandonment_threshold:
            others = [c for c in model.communities if c is not self]
            if others:
                # Prefer whoever already trusts this community most -- a
                # real, if slightly grim, use of the trust relationships
                # this same community built while being drained as a
                # 'phantom donor'. Falls back to random if no trust
                # history exists yet.
                trusted = [(c, c.get_trust(self.unique_id)) for c in others]
                best = max(trusted, key=lambda x: x[1])
                self.assimilated_by = best[0]
                # One-time transfer of whatever's currently on hand;
                # ongoing production redirects from here on (see
                # convert_raw_materials) rather than accumulating locally.
                self.assimilated_by.raw_materials += self.raw_materials
                self.raw_materials = 0.0
                for ptype, amount in self.local_particulars.items():
                    self.assimilated_by.local_particulars[ptype] += amount
                    self.local_particulars[ptype] = 0.0

    def convert_raw_materials(self, model):
        """Sovereign local production: the community decides its OWN
        production mix (production_strategy), the Ledger has no say in and
        no visibility into this at all -- it only ever sees raw_materials
        before this call and after, never local_particulars or the
        strategy that produced them. This is what makes the Ledger's
        blindness architectural rather than a policy of not looking:
        nothing about this method's output is ever read by SystemLedger.

        Two distinct, deliberately different stages for an empty
        community, not one:
          1. Wind-down (immediate, cheaply reversible): nobody's running
             the equipment, so it just stops -- production freezes exactly
             where it was, nothing lost, nothing gained. If someone
             resettles even one step later, it resumes instantly from
             whatever was left, no cost either way.
          2. Assimilation (only after sustained abandonment -- see
             update_abandonment_status): if nobody comes back for a long
             time, the frozen stock actually gets transferred to a
             trusted neighbor rather than sitting idle forever. That's a
             real, harder-to-reverse event; wind-down is not."""
        if not self.citizens or self.assimilated_by is not None:
            return
        amount_to_convert = min(self.raw_materials, model.conversion_rate_per_step)
        if amount_to_convert <= 0:
            return
        for ptype, proportion in self.production_strategy.items():
            self.local_particulars[ptype] += amount_to_convert * proportion * model.conversion_efficiency
        self.raw_materials -= amount_to_convert

    def total_particulars(self):
        return sum(self.local_particulars.values())

    def distribute_particulars_to_citizens(self, model):
        """Closes a real gap: until now, a community's production and trade
        success never reached any individual citizen at all -- particulars
        just accumulated (or got assimilated away) at the community level,
        completely disconnected from personal welfare.

        CORRECTED after direct testing: the first version valued all
        particular types with a flat, equal, additive rate -- total value
        was just the sum of quantities regardless of type mix. That's a
        real design bug, not a neutral simplification: since barter trades
        only ever preserve or reduce total quantity (trust scales executed
        trades below the full mutually-beneficial amount, and it's a swap,
        not new production), a flat-value function makes NOT trading a
        strictly dominant strategy -- confirmed directly, an isolated
        community's citizens ended up ahead in 7 of 8 test seeds, not by
        luck but by construction. Diminishing returns per type (sqrt, the
        standard device for this) fixes it: a diverse basket is worth MORE
        than a large pile of one thing at equal raw quantity, which is what
        actually makes trading toward diversity valuable rather than
        value-neutral-at-best."""
        if not self.citizens or not model.particulars_consumption_enabled:
            return
        consumed_amounts = {}
        utility = 0.0
        for ptype, amount in self.local_particulars.items():
            consumed = amount * model.particulars_consumption_rate
            consumed_amounts[ptype] = consumed
            utility += consumed ** 0.5
        if utility <= 0:
            return
        for ptype, consumed in consumed_amounts.items():
            self.local_particulars[ptype] = max(0.0, self.local_particulars[ptype] - consumed)
        total_payout = utility * model.particular_value_rate
        per_capita = total_payout / len(self.citizens)
        for citizen in self.citizens:
            citizen.resources += per_capita

    def pct_below_security_threshold(self, target):
        """Fraction of citizens below a resources target. A pure aggregate
        -- reveals HOW MANY are struggling, never WHO. This is what lets a
        privacy-preserving AI detect internal inequality a mean can hide:
        a community can average comfortably above target while a real
        subgroup is still in crisis underneath a healthy-looking number."""
        if not self.citizens:
            return 0.0
        below = sum(1 for c in self.citizens if c.resources < target)
        return below / len(self.citizens)

    def internal_resource_gini(self):
        """This community's own Gini over its citizens' resources -- again
        a single aggregate number, not a list of who has what."""
        return gini([c.resources for c in self.citizens])


class SystemLedger:
    """NOTE: When model.federated_mode=True, this class plays NO role in
    resource allocation -- that's the point of the federated refactor. It
    remains only because informed_migration (a separate, unrelated feature:
    citizens choosing where to migrate) reads get_system_status() for a
    deficit signal. Genuinely decommissioning it would require also
    removing informed_migration, which wasn't asked for. In federated mode,
    resource allocation is fully local + peer-negotiated; this class is
    inert unless informed_migration=True is separately enabled.

    Raw Material Conversion economy (model.raw_material_economy_enabled):
    ship_raw_materials() below is the ENTIRE interface this class has to
    that economy. Read it end to end -- every line references
    comm.raw_materials and nothing else on CommunityNode. It never reads
    local_particulars, production_strategy, or policy. This isn't a
    convention this class chooses to follow; it's a structural fact you can
    verify by inspection -- delete every other CommunityNode attribute and
    this method still runs unchanged, because it never touched them.
    """
    def __init__(self, model):
        self.model = model

    def get_system_status(self):
        status = []
        for comm in self.model.communities:
            deficit = 1.0 - (comm.productivity() / (len(comm.citizens) + 1e-6))
            status.append({"community": comm, "deficit": deficit})
        return status

    def ship_raw_materials(self):
        """The 'passive nervous system': reads ONLY comm.raw_materials
        (never particulars, never strategy, never policy) and ships more
        raw material to any community below SUSTAINABILITY_THRESHOLD.
        Need-capped, not proportionally force-fed -- shipping exactly the
        shortfall rather than an arbitrary share avoids the earlier
        over-delivery bug found in automated_provisioning's first version.
        Non-authoritarian by construction: it can only ADD raw material to
        a community that's short, never remove, redirect production, or
        touch anything else about how that community organizes itself.

        Reading comm.assimilated_by (and, here, whether a community is
        currently empty at all) is a deliberate, narrow exception to
        blindness, not an oversight: it's a logistics fact (is anyone
        physically present to receive a shipment), not a production or
        governance fact (what gets made, how it's decided). A postal
        service can know an address is vacant and hold delivery without
        knowing anything about what the resident used to do there.

        Shipment cap is scaled by get_ledger_throttle_factor() -- extracting
        and moving raw material at scale isn't ecologically free, and this
        is the mechanism that actually charges for it (see
        update_ledger_ecological_damage)."""
        m = self.model
        effective_cap = m.raw_material_shipment_cap * m.get_ledger_throttle_factor()
        for comm in m.communities:
            if comm.assimilated_by is not None:
                target = comm.assimilated_by
            elif not comm.citizens:
                continue  # wound down: nobody to receive it, don't ship
            else:
                target = comm
            shortfall = m.sustainability_threshold - target.raw_materials
            if shortfall > 0:
                delivered = min(shortfall, effective_cap)
                target.raw_materials += delivered
                m.ledger_delivery_this_step += delivered


def gini(values):
    values = np.array([v for v in values if v is not None], dtype=float)
    if len(values) == 0 or values.sum() == 0:
        return 0.0
    sorted_vals = np.sort(values)
    n = len(values)
    cumulative = np.cumsum(sorted_vals)
    return (n + 1 - 2 * (cumulative.sum() / cumulative[-1])) / n


# ============================================================
# Model
# ============================================================
class AsymptoticEthicsModel(mesa.Model):
    def __init__(
        self,
        N_citizens,
        N_communities,
        informed_migration=False,
        crisis_threshold=2.0,
        stabilization_cost=0.1,
        migration_reputation_decay=0.20,
        reserve_baseline=None,
        # --- Contestable governance ---
        recall_enabled=False,
        recall_mismatch_threshold=0.35,
        recall_duration=10,
        recall_cost=15.0,
        # --- Policy tournament ---
        tournament_enabled=False,
        tournament_period=10,
        tournament_metric="resource_gini",   # "resource_gini" or "contribution_gini"
        tournament_copy_prob=0.5,
        tournament_mutation_prob=0.1,
        # --- Coupled governance / Resilience Protocol ---
        coupled_governance=False,
        care_load_multiplier=None,
        recovery_threshold=None,
        # --- Rehabilitation Protocol ---
        rehabilitation_enabled=False,
        investment_cost_per_agent=0.15,
        conversion_base_rate=0.08,
        conversion_streak_needed=15,
        relapse_decay=2,
        relapse_probability=0.05,
        graduation_enabled=False,
        graduation_halflife=40,
        flat_allocation=False,
        memory_decay_enabled=False,
        memory_decay_rate=0.9,
        # --- Opt-in additions merged from uploaded draft (all default OFF
        # so existing experiment results are unaffected unless explicitly enabled) ---
        shock_enabled=False,
        shock_tick=150,
        shock_fraction=0.4,
        solidarity_fund_enabled=False,
        solidarity_fund_fraction=0.2,
        entropy_maintenance_enabled=False,
        entropy_maintenance_base=45.0,
        entropy_maintenance_rate=0.1,
        debug_assertions=False,
        log_allocation_details=False,
        adaptive_reserve_baseline=False,
        adaptive_baseline_window=50,
        adaptive_baseline_min_history=5,
        reserve_growth_rate=0.5,
        post_scarcity_enabled=False,
        automation_dividend_per_capita=1.5,
        automation_care_absorption=0.0,
        automation_care_absorption_auto=False,
        automation_level_enabled=False,
        automated_output_per_community=20.0,
        distribution_fraction=0.1,
        allocation_weighting_mode="full",
        population_weighted_allocation=False,
        care_work_counts_as_productivity=False,
        care_work_productivity_multiplier=1.0,
        meaningful_care_enabled=False,
        caregiver_reputation_bonus=0.02,
        caregiver_resource_bonus=0.05,
        caregiver_conversion_bonus_reputation=0.15,
        caregiver_conversion_bonus_resources=1.0,
        paired_care_conversion_multiplier=1.5,
        federated_mode=False,
        local_reserve_initial=50.0,
        local_maintenance_per_capita=0.3,
        local_growth_rate=0.5,
        local_reserve_target=0.5,
        local_care_weight=5.0,
        trust_initial=0.5,
        trust_gain_per_transfer=0.05,
        trust_decay_on_unmet_need=0.02,
        surplus_threshold=3.0,
        deficit_threshold=3.0,
        max_transfer_fraction=0.3,
        communication_latency_enabled=False,
        min_distance=1,
        max_distance=15,
        colluder_reputation_portable=False,
        privacy_enabled=False,
        automated_provisioning_enabled=False,
        ai_supply_per_step=50.0,
        resource_security_target=2.0,
        provisioning_detects_inequality=True,
        post_labor_economy_enabled=False,
        emergency_response_enabled=True,
        emergency_response_amount=50.0,
        individual_floor_enabled=False,
        individual_floor_threshold=1.0,
        caregiver_choice_enabled=False,
        caregiver_acceptance_threshold=0.3,
        affinity_gain_per_interaction=0.05,
        affinity_loss_on_relapse=0.15,
        policy_voting_enabled=False,
        policy_vote_period=20,
        relapse_history_penalty=0.15,
        catastrophe_cooldown_enabled=False,
        catastrophe_cooldown_period=100,
        contested_sites_enabled=False,
        build_window_length=20,
        ecological_impact_enabled=False,
        impact_growth_rate=0.05,
        impact_recovery_rate=0.02,
        eco_value_decay_rate=0.01,
        eco_vote_period=50,
        eco_concern_sensitivity=0.15,
        gradual_crisis_response_enabled=False,
        crisis_vote_period=50,
        emergency_declare_sensitivity=1.0,
        raw_material_economy_enabled=False,
        particular_types=None,
        raw_materials_initial=50.0,
        conversion_rate_per_step=5.0,
        conversion_efficiency=0.9,
        sustainability_threshold=20.0,
        raw_material_shipment_cap=1000.0,
        particulars_trade_min=1.0,
        particulars_consumption_enabled=False,
        particulars_consumption_rate=0.1,
        particular_value_rate=1.0,
        strategy_tournament_period=20,
        strategy_mutation_prob=0.1,
        strategy_copy_prob=0.5,
        strategy_fitness_metric="total_particulars",
        abandonment_threshold=30,
        ledger_ecological_cost_enabled=False,
        ecological_cost_per_unit=0.005,
        ledger_damage_recovery_rate=0.3,
        ledger_damage_throttle_sensitivity=0.02,
        citizen_philanthropy_enabled=False,
        philanthropy_surplus_threshold=5.0,
        philanthropy_donation_fraction=0.1,
        philanthropy_reputation_rate=0.05,
        philanthropy_min_contribution=0.3,
        peer_rehabilitation_enabled=False,
        seed=None,
    ):
        super().__init__(seed=seed)
        # Fix: previously only self.random (mesa's Random) was seeded: the
        # model's actual strategy/contribution rolls use np.random directly
        # throughout, which was an independent, unseeded stream. Seeding it
        # here makes seed= actually reproduce a full run end-to-end.
        if seed is not None:
            np.random.seed(seed)
        self.informed_migration = informed_migration
        self.crisis_threshold = crisis_threshold
        self.stabilization_cost = stabilization_cost
        self.migration_reputation_decay = migration_reputation_decay
        self.reserve_baseline = reserve_baseline or (N_citizens * 0.5)

        self.recall_enabled = recall_enabled
        self.recall_mismatch_threshold = recall_mismatch_threshold
        self.recall_duration = recall_duration
        self.recall_cost = recall_cost

        self.tournament_enabled = tournament_enabled
        self.tournament_period = tournament_period
        self.tournament_metric = tournament_metric
        self.tournament_copy_prob = tournament_copy_prob
        self.tournament_mutation_prob = tournament_mutation_prob

        self.coupled_governance = coupled_governance
        # Sanctuary effect: lenient nodes absorb more care burden (tolerate/
        # welcome dependents rather than deflecting them); strict nodes
        # offload it. crisis_management itself runs lean once triggered.
        self.care_load_multiplier = care_load_multiplier or {
            "meritocratic": 1.0,
            "strict": 0.6,
            "lenient": 1.5,
            "clique": 1.0,
            "crisis_management": 0.5,
        }
        self.recovery_threshold = recovery_threshold if recovery_threshold is not None else crisis_threshold * 0.5

        self.rehabilitation_enabled = rehabilitation_enabled
        self.investment_cost_per_agent = investment_cost_per_agent
        self.conversion_base_rate = conversion_base_rate
        self.conversion_streak_needed = conversion_streak_needed
        self.relapse_decay = relapse_decay
        self.relapse_probability = relapse_probability
        self.graduation_enabled = graduation_enabled
        self.graduation_halflife = graduation_halflife
        self.flat_allocation = flat_allocation
        self.memory_decay_enabled = memory_decay_enabled
        self.memory_decay_rate = memory_decay_rate
        self.shock_enabled = shock_enabled
        self.shock_tick = shock_tick
        self.shock_fraction = shock_fraction
        self.solidarity_fund_enabled = solidarity_fund_enabled
        self.solidarity_fund_fraction = solidarity_fund_fraction
        self.entropy_maintenance_enabled = entropy_maintenance_enabled
        self.entropy_maintenance_base = entropy_maintenance_base
        self.entropy_maintenance_rate = entropy_maintenance_rate
        self.debug_assertions = debug_assertions
        self.log_allocation_details = log_allocation_details
        self.allocation_log = []
        self.N_citizens_initial = N_citizens
        self.adaptive_reserve_baseline = adaptive_reserve_baseline
        self.adaptive_baseline_window = adaptive_baseline_window
        self.adaptive_baseline_min_history = adaptive_baseline_min_history
        self.reserve_growth_rate = reserve_growth_rate
        self.post_scarcity_enabled = post_scarcity_enabled
        self.automation_dividend_per_capita = automation_dividend_per_capita
        self.automation_level_enabled = automation_level_enabled
        # Auto-coupling: if a society is modeled as having pervasive
        # automation (production-side, and/or the material dividend), it's
        # a real inconsistency to leave care-work absorption at its old
        # default of 0% -- there's no principled reason automation would
        # cover material production and provisioning but somehow not
        # administrative/care burden. When enabled, this OVERRIDES whatever
        # automation_care_absorption was passed in with full absorption
        # (1.0) any time some form of automation is present, rather than
        # requiring it to be set by hand every time alongside the other
        # automation flags.
        if automation_care_absorption_auto and (post_scarcity_enabled or automation_level_enabled):
            self.automation_care_absorption = 1.0
        else:
            self.automation_care_absorption = automation_care_absorption
        self.automated_output_per_community = automated_output_per_community
        self.distribution_fraction = distribution_fraction
        self.allocation_weighting_mode = allocation_weighting_mode
        self.population_weighted_allocation = population_weighted_allocation
        self.care_work_counts_as_productivity = care_work_counts_as_productivity
        self.care_work_productivity_multiplier = care_work_productivity_multiplier
        self.meaningful_care_enabled = meaningful_care_enabled
        self.caregiver_reputation_bonus = caregiver_reputation_bonus
        self.caregiver_resource_bonus = caregiver_resource_bonus
        self.caregiver_conversion_bonus_reputation = caregiver_conversion_bonus_reputation
        self.caregiver_conversion_bonus_resources = caregiver_conversion_bonus_resources
        self.paired_care_conversion_multiplier = paired_care_conversion_multiplier
        self.federated_mode = federated_mode
        self.local_reserve_initial = local_reserve_initial
        self.local_maintenance_per_capita = local_maintenance_per_capita
        self.local_growth_rate = local_growth_rate
        self.local_reserve_target = local_reserve_target
        self.local_care_weight = local_care_weight
        self.trust_initial = trust_initial
        self.trust_gain_per_transfer = trust_gain_per_transfer
        self.trust_decay_on_unmet_need = trust_decay_on_unmet_need
        self.surplus_threshold = surplus_threshold
        self.deficit_threshold = deficit_threshold
        self.max_transfer_fraction = max_transfer_fraction
        self.communication_latency_enabled = communication_latency_enabled
        self.min_distance = min_distance
        self.max_distance = max_distance
        self.colluder_reputation_portable = colluder_reputation_portable
        self.privacy_enabled = privacy_enabled
        self.automated_provisioning_enabled = automated_provisioning_enabled
        self.ai_supply_per_step = ai_supply_per_step
        self.resource_security_target = resource_security_target
        self.provisioning_detects_inequality = provisioning_detects_inequality
        self.post_labor_economy_enabled = post_labor_economy_enabled
        self.emergency_response_enabled = emergency_response_enabled
        self.emergency_response_amount = emergency_response_amount
        self.individual_floor_enabled = individual_floor_enabled
        self.individual_floor_threshold = individual_floor_threshold
        self.caregiver_choice_enabled = caregiver_choice_enabled
        self.caregiver_acceptance_threshold = caregiver_acceptance_threshold
        self.affinity_gain_per_interaction = affinity_gain_per_interaction
        self.affinity_loss_on_relapse = affinity_loss_on_relapse
        self.policy_voting_enabled = policy_voting_enabled
        self.policy_vote_period = policy_vote_period
        self.relapse_history_penalty = relapse_history_penalty
        self.catastrophe_cooldown_enabled = catastrophe_cooldown_enabled
        self.catastrophe_cooldown_period = catastrophe_cooldown_period
        self.community_last_catastrophe_tick = {}
        self.contested_sites_enabled = contested_sites_enabled
        self.build_window_length = build_window_length
        self.ecological_impact_enabled = ecological_impact_enabled
        self.impact_growth_rate = impact_growth_rate
        self.impact_recovery_rate = impact_recovery_rate
        self.eco_value_decay_rate = eco_value_decay_rate
        self.eco_vote_period = eco_vote_period
        self.eco_concern_sensitivity = eco_concern_sensitivity
        self.gradual_crisis_response_enabled = gradual_crisis_response_enabled
        self.crisis_vote_period = crisis_vote_period
        self.emergency_declare_sensitivity = emergency_declare_sensitivity
        self.raw_material_economy_enabled = raw_material_economy_enabled
        self.particular_types = particular_types if particular_types is not None else ["care_tech", "artisanal", "research"]
        self.raw_materials_initial = raw_materials_initial
        self.conversion_rate_per_step = conversion_rate_per_step
        self.conversion_efficiency = conversion_efficiency
        self.sustainability_threshold = sustainability_threshold
        self.raw_material_shipment_cap = raw_material_shipment_cap
        self.particulars_trade_min = particulars_trade_min
        self.particulars_consumption_enabled = particulars_consumption_enabled
        self.particulars_consumption_rate = particulars_consumption_rate
        self.particular_value_rate = particular_value_rate
        self.strategy_tournament_period = strategy_tournament_period
        self.strategy_mutation_prob = strategy_mutation_prob
        self.strategy_copy_prob = strategy_copy_prob
        self.strategy_fitness_metric = strategy_fitness_metric
        self.abandonment_threshold = abandonment_threshold
        self.ledger_ecological_cost_enabled = ledger_ecological_cost_enabled
        self.ecological_cost_per_unit = ecological_cost_per_unit
        self.ledger_damage_recovery_rate = ledger_damage_recovery_rate
        self.ledger_damage_throttle_sensitivity = ledger_damage_throttle_sensitivity
        self.cumulative_ledger_damage = 0.0
        self.current_ledger_throttle = 1.0  # 1.0 = full capacity, shrinks as damage accrues
        self.ledger_delivery_this_step = 0.0  # accumulates across shipment + dividend, reset each step
        self.citizen_philanthropy_enabled = citizen_philanthropy_enabled
        self.philanthropy_surplus_threshold = philanthropy_surplus_threshold
        self.philanthropy_donation_fraction = philanthropy_donation_fraction
        self.philanthropy_reputation_rate = philanthropy_reputation_rate
        self.philanthropy_min_contribution = philanthropy_min_contribution
        self.peer_rehabilitation_enabled = peer_rehabilitation_enabled
        if rehabilitation_enabled and peer_rehabilitation_enabled:
            print("WARNING: rehabilitation_enabled=True and peer_rehabilitation_enabled=True "
                  "were both set -- these are mutually exclusive rehabilitation mechanics, "
                  "built to be directly compared, not combined. rehabilitation_enabled's "
                  "community-investment mechanic takes precedence (checked first in Citizen.step).")
        self.philanthropy_donated_this_step = 0.0
        self.contested_sites = []
        self.pairing_attempts_this_step = 0
        self.pairing_declines_this_step = 0
        self.unmet_care_need_this_step = 0
        self.floor_topups_this_step = 0
        self.last_catastrophe_community = None
        self.last_catastrophe_tick = None
        self.provisioning_delivered_this_step = 0.0
        self.pending_transfers = []   # list of (arrival_tick, donor, recipient, amount) -- federated
        self.pending_payouts = []     # list of (arrival_tick, community, payout_per_capita) -- centralized
        self.transfers_this_step = 0
        self.total_transfer_volume_this_step = 0.0
        self.productivity_history = deque(maxlen=adaptive_baseline_window)
        self.current_effective_baseline = reserve_baseline or (N_citizens * 0.5)
        if adaptive_reserve_baseline and entropy_maintenance_enabled:
            print("WARNING: adaptive_reserve_baseline=True and entropy_maintenance_enabled=True "
                  "were both set -- these are mutually exclusive reserve-growth modes; "
                  "entropy_maintenance takes precedence (checked first in allocate_resources).")
        if entropy_maintenance_enabled and reserve_baseline is not None:
            print(f"WARNING: reserve_baseline={reserve_baseline} was explicitly set but "
                  f"entropy_maintenance_enabled=True means it will be ignored -- these two "
                  f"reserve-growth modes are mutually exclusive, entropy_maintenance wins.")
        self.conversions_this_step = 0
        self.relapses_this_step = 0
        self.cumulative_conversions = 0
        self.cumulative_relapses = 0

        self.communities = [
            CommunityNode(self, np.random.choice(["meritocratic", "strict", "lenient", "clique"]))
            for _ in range(N_communities)
        ]
        self.ledger = SystemLedger(self)

        if self.contested_sites_enabled:
            # Space as a genuinely indivisible good: two communities pair
            # off around one shared site, each with a different large-scale
            # project they want built there. Only one project can occupy
            # the site at a time -- this can't be split like a divisible
            # resource, so the resolution has to be about WHEN, not
            # HOW MUCH. Reframing an intractable space conflict as a
            # tractable time-allocation one.
            for i in range(0, len(self.communities) - 1, 2):
                comm_a, comm_b = self.communities[i], self.communities[i + 1]
                self.contested_sites.append({
                    "community_a": comm_a,
                    "community_b": comm_b,
                    "current_builder": comm_a,  # arbitrary first pick -- both start at 0 built ticks
                    "window_remaining": self.build_window_length,
                    "build_ticks": {comm_a.unique_id: 0, comm_b.unique_id: 0},
                    "ecological_impact": 0.0,
                    "paused": False,
                })

        strategies = ["honest", "lazy", "greedy", "colluder", "parasite"]
        probabilities = [0.40, 0.25, 0.15, 0.10, 0.10]
        for _ in range(N_citizens):
            comm = self.random.choice(self.communities)
            citizen = Citizen(self, comm, strategy=np.random.choice(strategies, p=probabilities))
            comm.citizens.append(citizen)

        self.global_reserve = 1000
        self.tick = 0

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "total_productivity": lambda m: sum(c.productivity() for c in m.communities),
                "total_labor_productivity": lambda m: sum(c.labor_productivity() for c in m.communities),
                "automation_share_of_output": lambda m: (
                    (sum(c.productivity() for c in m.communities) - sum(c.labor_productivity() for c in m.communities))
                    / max(sum(c.productivity() for c in m.communities), 1e-9)
                ),
                "global_reserve": lambda m: m.global_reserve,
                "effective_reserve_baseline": lambda m: m.current_effective_baseline,
                "resource_gini": lambda m: gini([a.resources for a in m.agents if isinstance(a, Citizen)]),
                "communities_in_crisis": lambda m: sum(c.care_load > c.crisis_threshold for c in m.communities),
                "recall_events_cumulative": lambda m: sum(c.recall_events for c in m.communities),
                "pct_lenient": lambda m: np.mean([c.policy == "lenient" for c in m.communities]),
                "pct_meritocratic": lambda m: np.mean([c.policy == "meritocratic" for c in m.communities]),
                "pct_strict": lambda m: np.mean([c.policy == "strict" for c in m.communities]),
                "pct_clique": lambda m: np.mean([c.policy == "clique" for c in m.communities]),
                "pct_crisis_mgmt": lambda m: np.mean([c.policy == "crisis_management" for c in m.communities]),
                "pct_emergency_declared": lambda m: np.mean([c.emergency_declared for c in m.communities]),
                "mean_crisis_severity": lambda m: np.mean([c.crisis_severity for c in m.communities]),
                "total_crisis_transitions": lambda m: sum(c.crisis_transitions for c in m.communities),
                "pct_honest": lambda m: np.mean(
                    [a.strategy == "honest" for a in m.agents if isinstance(a, Citizen)]
                ),
                "pct_lazy_or_parasite": lambda m: np.mean(
                    [a.strategy in ("lazy", "parasite") for a in m.agents if isinstance(a, Citizen)]
                ),
                "cumulative_conversions": lambda m: m.cumulative_conversions,
                "pairing_attempts_this_step": lambda m: (m.pairing_attempts_this_step if m.caregiver_choice_enabled else np.nan),
                "pairing_declines_this_step": lambda m: (m.pairing_declines_this_step if m.caregiver_choice_enabled else np.nan),
                "unmet_care_need_this_step": lambda m: (m.unmet_care_need_this_step if m.caregiver_choice_enabled else np.nan),
                "mean_local_reserve": lambda m: (np.mean([c.local_reserve for c in m.communities]) if m.federated_mode else np.nan),
                "mean_trust": lambda m: (
                    np.mean([v for c in m.communities for v in c.trust.values()])
                    if m.federated_mode and any(c.trust for c in m.communities) else np.nan
                ),
                "transfers_this_step": lambda m: (m.transfers_this_step if m.federated_mode else np.nan),
                "transfer_volume_this_step": lambda m: (m.total_transfer_volume_this_step if m.federated_mode else np.nan),
                "provisioning_delivered_this_step": lambda m: (m.provisioning_delivered_this_step if m.automated_provisioning_enabled else np.nan),
                "mean_raw_materials": lambda m: (np.mean([c.raw_materials for c in m.communities]) if m.raw_material_economy_enabled else np.nan),
                "mean_total_particulars": lambda m: (np.mean([c.total_particulars() for c in m.communities]) if m.raw_material_economy_enabled else np.nan),
                "cumulative_ledger_damage": lambda m: (m.cumulative_ledger_damage if m.ledger_ecological_cost_enabled else np.nan),
                "current_ledger_throttle": lambda m: (m.current_ledger_throttle if m.ledger_ecological_cost_enabled else np.nan),
                "pct_honest_who_are_caregivers": lambda m: (
                    np.mean([a.caring_for is not None for a in m.agents if isinstance(a, Citizen) and a.strategy == "honest"])
                    if any(isinstance(a, Citizen) and a.strategy == "honest" for a in m.agents) else np.nan
                ),
                "caregiver_mean_reputation": lambda m: (
                    lambda caregivers: np.mean([c.reputation for c in caregivers]) if caregivers else np.nan
                )([a for a in m.agents if isinstance(a, Citizen) and a.caring_for is not None]),
                "non_caregiver_honest_mean_reputation": lambda m: (
                    lambda others: np.mean([c.reputation for c in others]) if others else np.nan
                )([a for a in m.agents if isinstance(a, Citizen) and a.strategy == "honest" and a.caring_for is None]),
                "cumulative_relapses": lambda m: m.cumulative_relapses,
                "parasite_mean_reputation": lambda m: np.mean(
                    [a.reputation for a in m.agents if isinstance(a, Citizen) and a.strategy == "parasite"]
                ) if any(isinstance(a, Citizen) and a.strategy == "parasite" for a in m.agents) else np.nan,
            },
        )

    def get_ledger_throttle_factor(self):
        """The 'coordinating raw materials isn't free' fix: as cumulative
        ecological damage from Ledger-delivered material (shipment AND
        the flat dividend -- both are automation-based delivery, treated
        consistently rather than one being free and one being costed)
        rises, the effective amount deliverable shrinks. Floored at 0.1,
        not 0 -- some baseline automated capacity always remains, this
        throttles abundance, it doesn't eliminate it. Same shape as the
        contested-sites ecological mechanism: real cost, recoverable with
        restraint, never a hard binary veto."""
        if not self.ledger_ecological_cost_enabled:
            return 1.0
        return max(0.1, 1.0 - self.cumulative_ledger_damage * self.ledger_damage_throttle_sensitivity)

    def update_ledger_ecological_damage(self):
        """Called once per step: bank this step's total delivery into
        cumulative damage, then let it recover somewhat if delivery has
        been restrained -- damage rises with throughput, heals with
        restraint, exactly like the contested-sites mechanism this is
        deliberately modeled on."""
        if not self.ledger_ecological_cost_enabled:
            return
        self.cumulative_ledger_damage += self.ecological_cost_per_unit * self.ledger_delivery_this_step
        self.cumulative_ledger_damage = max(0.0, self.cumulative_ledger_damage - self.ledger_damage_recovery_rate)
        self.current_ledger_throttle = self.get_ledger_throttle_factor()
        self.ledger_delivery_this_step = 0.0

    def introduce_catastrophe(self):
        if self.random.random() < 0.01:
            # Cooldown: without this, the same community can be struck
            # again before it's recovered from the last hit -- this is what
            # actually made the "worst-off citizen" worst off in testing:
            # not individual vulnerability, but one community getting hit
            # twice in quick succession (24 ticks apart in one traced case)
            # with no protection against exactly that.
            if self.catastrophe_cooldown_enabled:
                eligible = [
                    c for c in self.communities
                    if (self.tick - self.community_last_catastrophe_tick.get(c.unique_id, -10**9)) >= self.catastrophe_cooldown_period
                ]
                if not eligible:
                    return
            else:
                eligible = self.communities

            target_comm = self.random.choice(eligible)
            target_comm.global_budget = 0
            for citizen in target_comm.citizens:
                citizen.resources = 0
                citizen.reputation = 0.0
            self.last_catastrophe_community = target_comm.unique_id
            self.last_catastrophe_tick = self.tick
            self.community_last_catastrophe_tick[target_comm.unique_id] = self.tick

            if self.automated_provisioning_enabled and self.emergency_response_enabled:
                # The gap this closes: run_automated_provisioning() only
                # runs on its normal per-step schedule, reading mean/
                # inequality signals that reflect steady-state need. A
                # catastrophe is a step-change, not steady-state -- without
                # this, a community wiped late in a run may not have enough
                # remaining steps to recover before anyone measures outcomes,
                # even though every other safety net (dividend, provisioning)
                # is working correctly. This gives immediate relief to the
                # SPECIFIC community that was just hit, same tick, rather
                # than waiting for the next scheduled assessment.
                if target_comm.citizens:
                    per_capita = self.emergency_response_amount / len(target_comm.citizens)
                    for citizen in target_comm.citizens:
                        citizen.resources += per_capita

    def perform_rehabilitation(self, honest_agent, target_agent):
        """Alternative peer-to-peer rehabilitation mechanic from the
        uploaded draft: an honest agent's accumulated 'experience' raises
        conversion odds for a specific target, capped at 0.9.

        NOT CALLED from step() -- this would functionally compete with the
        validated care_streak/investment rehabilitation mechanic already in
        Citizen.step (the one behind the graduation/big-push/memory-decay
        results from this conversation). Wiring both in simultaneously would
        double-count conversion pressure. Left defined but inert until a
        decision is made to: (a) replace the existing mechanic with this one,
        (b) run it as a distinct additional pathway, or (c) discard it.
        """
        base_rate = 0.08
        success_chance = min(0.9, base_rate + (honest_agent.experience * 0.02))
        if self.random.random() < success_chance:
            target_agent.strategy = "honest"
            honest_agent.experience += 1
            return True
        return False

    def _run_sanity_checks(self):
        """Structural invariants that should never be violated regardless of
        which opt-in features are active. Cheap enough to run every step
        when debug_assertions=True; skipped entirely otherwise so sweeps
        aren't slowed down. Raises AssertionError with context on failure
        rather than letting a violation silently corrupt downstream metrics."""
        citizens = [a for a in self.agents if isinstance(a, Citizen)]

        n_total = sum(len(c.citizens) for c in self.communities)
        assert n_total == self.N_citizens_initial, (
            f"tick {self.tick}: population not conserved -- {n_total} citizens across "
            f"communities, expected {self.N_citizens_initial}. Likely a migration bug "
            f"(citizen removed from one list without being added to another, or duplicated)."
        )
        assert len(citizens) == self.N_citizens_initial, (
            f"tick {self.tick}: agent count ({len(citizens)}) doesn't match community "
            f"membership count ({n_total}) -- an agent exists that no community claims, "
            f"or vice versa."
        )

        for c in citizens:
            assert c.resources >= 0, f"tick {self.tick}: citizen {c.unique_id} has negative resources ({c.resources})"
            assert 0.0 <= c.reputation <= 1.0, f"tick {self.tick}: citizen {c.unique_id} reputation out of [0,1] ({c.reputation})"

        if self.federated_mode:
            # global_reserve is genuinely decommissioned in this mode --
            # checking its bounds would be checking an inert number.
            # Check the actual invariants of the federated system instead.
            for c in self.communities:
                assert c.local_reserve >= 0, (
                    f"tick {self.tick}: community {c.unique_id} local_reserve is negative "
                    f"({c.local_reserve}) -- a transfer or local distribution overdrew it."
                )
                for other_id, trust_val in c.trust.items():
                    assert 0.0 <= trust_val <= 1.0, (
                        f"tick {self.tick}: trust from community {c.unique_id} toward "
                        f"{other_id} is out of [0,1] ({trust_val})."
                    )
        else:
            assert 0 <= self.global_reserve <= 5000, f"tick {self.tick}: global_reserve out of bounds ({self.global_reserve})"

    def step(self):
        self.tick += 1
        for comm in self.communities:
            comm.care_load = 0.0
            comm.care_work_output = 0.0
        self.conversions_this_step = 0
        self.relapses_this_step = 0
        self.pairing_attempts_this_step = 0
        self.pairing_declines_this_step = 0
        self.unmet_care_need_this_step = 0

        # Opt-in shock (off by default): forces a fraction of currently-
        # honest agents (including rehabilitated ones) back to 'lazy'.
        # Uses self.random, not the stdlib random module, so it respects
        # seed= like everything else.
        if self.shock_enabled and self.tick == self.shock_tick:
            honest_agents = [a for a in self.agents if isinstance(a, Citizen) and a.strategy == "honest"]
            n_shock = int(len(honest_agents) * self.shock_fraction)
            for agent in self.random.sample(honest_agents, min(n_shock, len(honest_agents))):
                agent.strategy = "lazy"
                agent.rehabilitated = False
                agent.recovery_tenure = 0

        self.introduce_catastrophe()
        self.agents_by_type[Citizen].shuffle_do("step")
        self.agents_by_type[CommunityNode].do("step")

        self.cumulative_conversions += self.conversions_this_step
        self.cumulative_relapses += self.relapses_this_step

        if self.raw_material_economy_enabled:
            # Abandonment status must be current BEFORE shipment decides
            # where to redirect -- assimilation redirects logistics, so it
            # has to be known first.
            for comm in self.communities:
                comm.update_abandonment_status(self)
            # Global tier first (blind shipment based only on raw_materials),
            # then local tier (sovereign conversion), then P2P trade of
            # what was produced -- the Ledger never sees the output of the
            # steps that follow it.
            self.ledger.ship_raw_materials()
            for comm in self.communities:
                comm.convert_raw_materials(self)
            self.run_particulars_negotiation()
            for comm in self.communities:
                comm.distribute_particulars_to_citizens(self)
            if self.tick % self.strategy_tournament_period == 0:
                self.run_production_strategy_evolution()

        if self.citizen_philanthropy_enabled:
            self.run_citizen_philanthropy()

        if self.federated_mode:
            self.run_federated_step()
        else:
            self.allocate_resources()

        if self.automated_provisioning_enabled:
            self.run_automated_provisioning()

        if self.individual_floor_enabled:
            self.enforce_individual_floor()

        self.migration_phase()

        if self.tournament_enabled and self.tick % self.tournament_period == 0:
            self.run_policy_tournament()

        if self.policy_voting_enabled and self.tick % self.policy_vote_period == 0:
            self.run_policy_vote()

        if self.gradual_crisis_response_enabled and self.tick % self.crisis_vote_period == 0:
            self.run_crisis_vote()

        if self.contested_sites_enabled:
            self.run_contested_sites()

        self.update_ledger_ecological_damage()

        self.datacollector.collect(self)

        if self.debug_assertions:
            self._run_sanity_checks()

    def pairwise_latency(self, comm_a, comm_b):
        return max(1, abs(comm_a.distance - comm_b.distance))

    def run_particulars_negotiation(self):
        """P2P barter of local_particulars between communities -- no
        central coordinator, no common medium of exchange. This means it's
        genuinely subject to the classic 'double coincidence of wants'
        problem (Jevons): a trade only happens if A has a surplus of
        something B lacks, AND B simultaneously has a surplus of something
        A lacks. That's an honest limitation of real barter, not a bug in
        this implementation -- money exists historically to solve exactly
        this friction, and this protocol deliberately doesn't reintroduce
        it. Trust (reused from the federated commons trust dict) breaks
        ties among multiple valid trading partners.

        Surplus/deficit is measured against a simple 'even local basket'
        baseline per community -- production beyond an even split across
        types is what becomes tradeable specialization.
        """
        if len(self.particular_types) < 2:
            return
        baselines = {}
        for comm in self.communities:
            even_share = comm.total_particulars() / len(self.particular_types)
            baselines[comm.unique_id] = {
                ptype: comm.local_particulars[ptype] - even_share
                for ptype in self.particular_types
            }

        for comm_a in self.communities:
            surplus_a = baselines[comm_a.unique_id]
            types_a_has_surplus = [t for t, v in surplus_a.items() if v > self.particulars_trade_min]
            types_a_needs = [t for t, v in surplus_a.items() if v < -self.particulars_trade_min]
            if not types_a_has_surplus or not types_a_needs:
                continue

            best_partner, best_trust, best_trade = None, -1.0, None
            for comm_b in self.communities:
                if comm_b is comm_a:
                    continue
                surplus_b = baselines[comm_b.unique_id]
                # Genuine double coincidence: a type A can give that B
                # lacks, AND a type B can give that A lacks, at once.
                give_type = next((t for t in types_a_has_surplus if surplus_b.get(t, 0) < -self.particulars_trade_min), None)
                get_type = next((t for t in types_a_needs if surplus_b.get(t, 0) > self.particulars_trade_min), None)
                if give_type is None or get_type is None:
                    continue
                trust_level = comm_a.get_trust(comm_b.unique_id)
                if trust_level > best_trust:
                    best_trust, best_partner, best_trade = trust_level, comm_b, (give_type, get_type)

            if best_partner is None:
                continue  # no double coincidence this step -- genuinely no trade, not an error

            give_type, get_type = best_trade
            surplus_b = baselines[best_partner.unique_id]
            amount = min(surplus_a[give_type], -surplus_b[give_type],
                         surplus_b[get_type], -surplus_a[get_type]) * best_trust
            amount = max(0.0, amount)
            if amount <= 0:
                continue

            comm_a.local_particulars[give_type] -= amount
            comm_a.local_particulars[get_type] += amount
            best_partner.local_particulars[give_type] += amount
            best_partner.local_particulars[get_type] -= amount
            comm_a.trade_volume_since_tournament += amount
            best_partner.trade_volume_since_tournament += amount
            # Keep this step's remaining baselines honest for subsequent
            # pairs, same reasoning as the 'committed' fix in resource
            # negotiation -- don't let one community over-trade the same
            # surplus twice in a single pass.
            surplus_a[give_type] -= amount
            surplus_a[get_type] += amount
            surplus_b[give_type] += amount
            surplus_b[get_type] -= amount

            new_a = min(1.0, comm_a.get_trust(best_partner.unique_id) + self.trust_gain_per_transfer)
            new_b = min(1.0, best_partner.get_trust(comm_a.unique_id) + self.trust_gain_per_transfer)
            comm_a.trust[best_partner.unique_id] = new_a
            best_partner.trust[comm_a.unique_id] = new_b

    def run_production_strategy_evolution(self):
        """Evolvable production strategy: periodically, communities compare
        fitness and the worst-performing half copy the best performer's
        production_strategy, with mutation for exploration. Deliberately
        the same pattern as run_policy_tournament rather than a new
        mechanism.

        strategy_fitness_metric matters more than it looks: "total_particulars"
        (raw output) was found to collapse ALL communities to one identical
        strategy within ~400 steps, killing the specialization diversity
        that trade depends on -- a community identical to its neighbors has
        nothing left to trade. "trade_volume" instead rewards a community
        for having successfully traded, which structurally requires staying
        different enough from neighbors to have something they want --
        tested directly to see whether this sustains diversity instead of
        collapsing it (see FINDINGS.md)."""
        if self.strategy_fitness_metric == "trade_volume":
            ranked = sorted(self.communities, key=lambda c: -c.trade_volume_since_tournament)
        else:
            ranked = sorted(self.communities, key=lambda c: -c.total_particulars())
        best_strategy = dict(ranked[0].production_strategy)
        n = len(ranked)
        for comm in ranked[n // 2:]:
            if self.random.random() < self.strategy_mutation_prob:
                raw = [self.random.random() for _ in self.particular_types]
                total = sum(raw) or 1.0
                comm.production_strategy = {t: w / total for t, w in zip(self.particular_types, raw)}
            elif self.random.random() < self.strategy_copy_prob:
                comm.production_strategy = dict(best_strategy)

        for comm in self.communities:
            comm.trade_volume_since_tournament = 0.0

    def run_citizen_philanthropy(self):
        """Individual citizens, regardless of home community, can donate
        surplus resources to whichever community is currently neediest --
        paid back in reputation, not resources or any currency. This is
        the individual-level analog to the community-level trade
        mechanisms already built, operationalizing the finding from
        post_labor_economy_enabled directly: once material want is solved,
        reputation/status becomes the durable thing people actually
        compete for, so let people buy it with generosity instead of with
        money that no longer functions as a real constraint.

        KNOWN EXPLOITABILITY RISK, worth stating plainly rather than
        discovering it as a surprise later: this is structurally identical
        to real-world reputation-laundering through philanthropy -- wealth
        converted to social standing without any real behavioral change.
        Diminishing returns (sqrt, not linear) are a partial mitigation,
        not a fix. Test this directly (see FINDINGS.md) before trusting it
        the way any other reputation-reward mechanism in this model has
        needed testing.
        """
        self.philanthropy_donated_this_step = 0.0
        if not self.communities:
            return

        if self.raw_material_economy_enabled:
            neediest = min(self.communities, key=lambda c: c.raw_materials - self.sustainability_threshold)
        elif self.federated_mode:
            neediest = max(self.communities, key=lambda c: c.local_need_signal(self))
        else:
            neediest = min(self.communities, key=lambda c: (
                np.mean([ci.resources for ci in c.citizens]) if c.citizens else float("inf")
            ))

        for citizen in self.agents:
            if not isinstance(citizen, Citizen):
                continue
            surplus = citizen.resources - self.philanthropy_surplus_threshold
            if surplus <= 0:
                continue
            donation = surplus * self.philanthropy_donation_fraction
            citizen.resources -= donation
            self.philanthropy_donated_this_step += donation

            if self.raw_material_economy_enabled:
                neediest.raw_materials += donation
            elif self.federated_mode:
                neediest.local_reserve += donation
            else:
                if neediest.citizens:
                    per_capita = donation / len(neediest.citizens)
                    for ci in neediest.citizens:
                        ci.resources += per_capita

            # CLOSES A CONFIRMED EXPLOIT: an earlier version rewarded any
            # citizen with surplus, regardless of strategy -- tested
            # directly and found that lazy/parasite citizens, whose
            # resources come almost entirely from the unconditional
            # dividend rather than real contribution, gained MORE absolute
            # reputation from philanthropy than honest citizens did,
            # because the dividend gives everyone similar surplus
            # regardless of behavior. Gating the reputation reward on
            # current contribution means donating dividend money you never
            # worked for buys nothing -- philanthropy can only ADD to
            # reputation someone is already earning through real
            # contribution, not substitute for it.
            if citizen.contribution > self.philanthropy_min_contribution:
                citizen.reputation = min(1.0, citizen.reputation + self.philanthropy_reputation_rate * (donation ** 0.5))

    def run_peer_negotiation(self):
        """Trust-based peer-to-peer transfer protocol. Replaces the global
        allocation formula entirely when federated_mode=True: no algorithm
        decides who gets what across the whole society. Instead, each
        community privately assesses its own need, and surplus communities
        choose (via trust) whether to help specific deficit communities.

        With communication_latency_enabled: a community always knows its
        OWN current state, but evaluates every OTHER community using a
        snapshot delayed by their pairwise distance -- decisions get made
        on old news about anyone far away, exactly like real light-lag.
        Agreed transfers are queued and arrive `pairwise_latency` ticks
        later, not instantly -- resources take time to actually travel.

        Ordering matters for what this can represent: needy communities are
        processed most-deficient-first, so early transfers can exhaust a
        popular donor's surplus before less-needy communities get a turn --
        a real scarcity dynamic, not just bookkeeping.
        """
        self.transfers_this_step = 0
        self.total_transfer_volume_this_step = 0.0
        lat = self.communication_latency_enabled

        def need_of(observer, target):
            if not lat or target is observer:
                return target.local_need_signal(self)
            delay = self.pairwise_latency(observer, target)
            snap = target.get_delayed_snapshot(self.tick, delay)
            reserve_gap = (self.local_reserve_target * len(target.citizens)) - snap["local_reserve"]
            return reserve_gap  # care_pressure omitted from delayed view -- observers can't see live crisis state either

        # Deficit/surplus classification uses each community's OWN self-report
        # (always current -- you know your own state instantly), but donors
        # are only findable/evaluable through what others can currently see
        # of them, which is where staleness enters.
        needs = [(c, c.local_need_signal(self)) for c in self.communities]
        needy = sorted([(c, n) for c, n in needs if n > self.deficit_threshold],
                        key=lambda x: -x[1])
        all_comms = self.communities
        committed = {}  # donor.unique_id -> amount already pledged THIS negotiation pass

        for recipient, need in needy:
            best_donor, best_score = None, -1.0
            for donor in all_comms:
                if donor is recipient:
                    continue
                observed_need = need_of(recipient, donor)  # recipient's (possibly stale) view of donor
                surplus = -observed_need - committed.get(donor.unique_id, 0.0)
                if surplus <= self.surplus_threshold:
                    continue
                score = surplus * donor.get_trust(recipient.unique_id)
                if score > best_score:
                    best_donor, best_score = donor, score

            if best_donor is None:
                for other in all_comms:
                    if other is not recipient:
                        t = recipient.get_trust(other.unique_id)
                        recipient.trust[other.unique_id] = max(0.0, t - self.trust_decay_on_unmet_need)
                continue

            donor_surplus = -need_of(recipient, best_donor) - committed.get(best_donor.unique_id, 0.0)
            trust_level = best_donor.get_trust(recipient.unique_id)
            transfer_amount = min(need, donor_surplus * self.max_transfer_fraction) * trust_level
            transfer_amount = max(0.0, transfer_amount)
            if transfer_amount <= 0:
                continue

            delay = self.pairwise_latency(best_donor, recipient) if lat else 0
            # Donor's reserve is committed NOW (it can't spend it twice while
            # in transit) but the recipient doesn't receive it until arrival.
            best_donor.local_reserve = max(0.0, best_donor.local_reserve - transfer_amount)
            committed[best_donor.unique_id] = committed.get(best_donor.unique_id, 0.0) + transfer_amount
            if delay > 0:
                self.pending_transfers.append((self.tick + delay, best_donor, recipient, transfer_amount))
            else:
                recipient.local_reserve += transfer_amount
                recipient.transfers_received_cumulative += transfer_amount
            best_donor.transfers_given_cumulative += transfer_amount
            self.transfers_this_step += 1
            self.total_transfer_volume_this_step += transfer_amount

            # Trust updates happen at negotiation time (agreeing to help is
            # already meaningful), not at arrival -- modeling that intent
            # and reputation propagate differently from physical goods.
            new_trust_recipient_side = min(1.0, recipient.get_trust(best_donor.unique_id) + self.trust_gain_per_transfer)
            new_trust_donor_side = min(1.0, best_donor.get_trust(recipient.unique_id) + self.trust_gain_per_transfer)
            recipient.trust[best_donor.unique_id] = new_trust_recipient_side
            best_donor.trust[recipient.unique_id] = new_trust_donor_side

    def process_pending_transfers(self):
        """Deliver any federated transfers whose travel time has elapsed."""
        arrived = [p for p in self.pending_transfers if p[0] <= self.tick]
        self.pending_transfers = [p for p in self.pending_transfers if p[0] > self.tick]
        for arrival_tick, donor, recipient, amount in arrived:
            recipient.local_reserve += amount
            recipient.transfers_received_cumulative += amount

    def run_automated_provisioning(self):
        """The AI-as-infrastructure layer: reads ONLY aggregate signals per
        community -- never any individual citizen's data -- and pushes
        automated production directly toward whoever needs it most.

        Two DIFFERENT need signals, deliberately combined rather than just
        one:
          1. Mean shortfall: this community is poor on average.
          2. pct_below_security_threshold: even if the average looks fine,
             a real subgroup may be struggling underneath it -- a mean
             alone can't see this (see FINDINGS.md: at ai_supply_per_step=800,
             every community averaged well above target while EVERY
             community still had honest citizens at exactly zero resources).
        Delivery is still equal-per-capita within a community -- the AI can
        detect THAT inequality exists without ever learning WHO specifically
        is struggling, but it genuinely cannot target aid to just the
        struggling subset without that information. This is a real,
        unavoidable cost of the privacy design, not a limitation of this
        implementation specifically: fixing hidden inequality through a
        privacy-preserving channel costs MORE total resources than targeted
        aid would (the well-off receive some too), because equal
        distribution is the only mechanism available that doesn't require
        knowing who's who.

        Delivery is CAPPED at genuine need in resource units, not just
        distributed proportionally by relative deficit share -- this is
        what makes a real saturation point possible: once ai_supply_per_step
        exceeds total need across the whole society, the excess simply
        isn't delivered (nobody gets force-fed beyond security), rather
        than growing outcomes unboundedly as supply increases.
        """
        self.provisioning_delivered_this_step = 0.0
        needs = {}
        for comm in self.communities:
            if not comm.citizens:
                continue
            n = len(comm.citizens)
            mean_res = np.mean([c.resources for c in comm.citizens])
            mean_shortfall_need = max(0.0, self.resource_security_target - mean_res) * n

            # Generous, privacy-safe estimate: assume everyone below
            # threshold needs roughly a full target's worth of top-up.
            # Deliberately conservative/generous rather than trying to
            # infer exact individual shortfalls, which would require
            # information the AI doesn't have and shouldn't have.
            pct_below = comm.pct_below_security_threshold(self.resource_security_target)
            inequality_need = (pct_below * n * self.resource_security_target
                                if self.provisioning_detects_inequality else 0.0)

            needs[comm.unique_id] = mean_shortfall_need + inequality_need

        total_need = sum(needs.values())
        if total_need <= 0:
            return  # every community already at or above the security target

        available = self.ai_supply_per_step
        # Highest-need communities served first, so a limited supply doesn't
        # get thinly smeared across everyone when it can't cover total need.
        for comm in sorted(self.communities, key=lambda c: -needs.get(c.unique_id, 0.0)):
            need = needs.get(comm.unique_id, 0.0)
            if need <= 0 or available <= 0:
                continue
            delivered = min(need, available)
            per_capita = delivered / len(comm.citizens)
            for citizen in comm.citizens:
                citizen.resources += per_capita
            available -= delivered
            self.provisioning_delivered_this_step += delivered

    def run_federated_step(self):
        """Orchestrates the federated phases in place of allocate_resources():
        deliver anything in transit, local production/maintenance, record
        this tick's history snapshot (for future latency lookups), peer
        negotiation, then local distribution. Called from Model.step only
        when federated_mode=True; allocate_resources() is untouched and
        still runs exactly as before when federated_mode=False."""
        if self.communication_latency_enabled:
            self.process_pending_transfers()
        for comm in self.communities:
            comm.local_production_and_maintenance(self)
        if self.communication_latency_enabled:
            for comm in self.communities:
                comm.record_history_snapshot(self.tick)
        self.run_peer_negotiation()
        for comm in self.communities:
            comm.distribute_locally(self)

    def process_pending_payouts(self):
        """Deliver any centralized payouts whose round-trip travel time
        (decision -> community, 2x one-way distance to the hub) has elapsed.
        Divides the TOTAL committed amount by whoever is actually in the
        community NOW -- see the comment in allocate_resources for why this
        has to be total-then-redivide rather than a carried per-capita rate."""
        arrived = [p for p in self.pending_payouts if p[0] <= self.tick]
        self.pending_payouts = [p for p in self.pending_payouts if p[0] > self.tick]
        for arrival_tick, comm, total_amount in arrived:
            if not comm.citizens:
                continue  # nobody left to receive it -- amount is lost, not stockpiled
            per_capita_now = total_amount / len(comm.citizens)
            for citizen in comm.citizens:
                citizen.resources += per_capita_now

    def allocate_resources(self):
        if self.communication_latency_enabled:
            self.process_pending_payouts()
            for comm in self.communities:
                comm.record_history_snapshot(self.tick)

        if self.communication_latency_enabled:
            # The hub's view of total production is a patchwork of
            # different-aged reports -- nearby communities' output is
            # near-current, far ones are stale, but there's no way to wait
            # for "the truth" since more recent data just keeps arriving
            # from different communities at different times.
            delayed_prods = [c.get_delayed_snapshot(self.tick, c.distance)["productivity"] for c in self.communities]
            current_total_prod = sum(delayed_prods)
            # labor/automated split isn't separately recorded in snapshots;
            # approximate using each community's current automation share
            # applied to the delayed total (automation share changes slowly
            # relative to distance-scale lags, so this is a reasonable proxy).
            live_total = sum(c.productivity() for c in self.communities)
            live_labor = sum(c.labor_productivity() for c in self.communities)
            automated_frac = (live_total - live_labor) / live_total if live_total > 0 else 0.0
            labor_prod = current_total_prod * (1 - automated_frac)
            automated_total = current_total_prod * automated_frac
        else:
            current_total_prod = sum(c.productivity() for c in self.communities)
            labor_prod = sum(c.labor_productivity() for c in self.communities)
            automated_total = current_total_prod - labor_prod  # 0 unless automation_level_enabled

        if self.entropy_maintenance_enabled:
            # Alternative reserve-growth model: maintenance cost rises with
            # tick (system entropy), rather than the fixed reserve_baseline
            # comparison. These two are mutually exclusive -- do not enable
            # both, they would double-count reserve growth.
            maintenance_cost = self.entropy_maintenance_base + self.tick * self.entropy_maintenance_rate
            self.global_reserve += current_total_prod - maintenance_cost
        elif self.adaptive_reserve_baseline:
            # Baseline chases a rolling average of REALIZED productivity
            # (lagged -- computed from history BEFORE this step is added,
            # so the comparison isn't self-cancelling). This means the
            # reserve responds to trend rather than an arbitrary fixed
            # target the population may never be able to hit: if this
            # population's sustainable output is 90, the baseline settles
            # near 90, not a hardcoded 100 that permanently drains the
            # reserve to zero regardless of what's actually achievable.
            if len(self.productivity_history) >= self.adaptive_baseline_min_history:
                effective_baseline = np.mean(self.productivity_history)
            else:
                # Not enough history yet: fall back to the fixed formula
                # as a bootstrap so early steps aren't comparing against
                # an undefined or zero baseline.
                effective_baseline = self.reserve_baseline
            self.current_effective_baseline = effective_baseline  # exposed for diagnostics/logging
            self.global_reserve += (labor_prod - effective_baseline) * self.reserve_growth_rate + automated_total
            self.productivity_history.append(current_total_prod)
        else:
            # Labor's contribution to growth is still surplus-based and
            # dampened (only the excess above baseline counts, and only a
            # fraction of that) -- this was designed for a labor economy
            # where "growth" means the population produced more than it
            # needed to sustain itself. Automated output gets NO such
            # dampening: it's a direct capital input, not a strained
            # surplus, so it flows into the reserve at full value. This is
            # the calibration fix -- previously automated output was routed
            # through productivity() and inherited labor's *0.5 surplus
            # discount, which is why it never meaningfully outgrew the
            # reserve's steady state regardless of how large it was set.
            self.global_reserve += (labor_prod - self.reserve_baseline) * self.reserve_growth_rate + automated_total
        self.global_reserve = np.clip(self.global_reserve, 0, 5000)

        # Opt-in Solidarity Fund (off by default): skims a fraction of the
        # reserve BEFORE the normal weighted/flat allocation and routes it
        # directly to whichever community currently has the highest
        # care_load. Properly decremented from global_reserve, unlike the
        # uploaded draft's version which created resources from nothing.
        if self.solidarity_fund_enabled and self.communities:
            solidarity_fund = self.global_reserve * self.solidarity_fund_fraction
            self.global_reserve -= solidarity_fund
            neediest = max(self.communities, key=lambda c: c.care_load)
            if neediest.citizens:
                share = solidarity_fund / len(neediest.citizens)
                for citizen in neediest.citizens:
                    citizen.resources += share

        if self.communication_latency_enabled:
            proofs = np.array([c.get_delayed_snapshot(self.tick, c.distance)["proof"] for c in self.communities])
            prod_per_capita = np.array([
                c.get_delayed_snapshot(self.tick, c.distance)["productivity"] / (len(c.citizens) + 1e-6)
                for c in self.communities
            ])
        else:
            proofs = np.array([c.export_zk_proof() for c in self.communities])
            prod_per_capita = np.array([(c.productivity() / (len(c.citizens) + 1e-6)) for c in self.communities])
        n_citizens_arr = np.array([len(c.citizens) for c in self.communities], dtype=float)

        # Decomposition for isolating which term drives allocation inequality.
        # "full" is the original formula; "proof_only" and "prod_only" zero
        # out one factor by replacing it with a constant, so the OTHER
        # factor still varies but contributes no differentiation of its own.
        if self.allocation_weighting_mode == "proof_only":
            weighted_scores = proofs * np.ones_like(prod_per_capita)
        elif self.allocation_weighting_mode == "prod_only":
            weighted_scores = np.ones_like(proofs) * (prod_per_capita ** 0.5)
        else:  # "full" (default)
            weighted_scores = proofs * (prod_per_capita ** 0.5)

        budget_to_distribute = self.global_reserve * self.distribution_fraction

        if self.population_weighted_allocation:
            # Corrected mechanism: allocate based on PER-CAPITA claims
            # directly, normalized across the whole population, rather than
            # computing a community-level weight and then dividing by
            # population a second time. The old path effectively applied an
            # extra, unintended population penalty/bonus on top of whatever
            # prod_per_capita had already normalized -- smaller communities
            # were structurally over-rewarded independent of merit. This
            # path removes that artifact: payout_per_capita is proportional
            # to a community's per-capita claim score, full stop, with no
            # residual size dependency.
            claim_per_capita = np.ones(len(self.communities)) if self.flat_allocation else weighted_scores
            total_claim = (claim_per_capita * n_citizens_arr).sum()
            if total_claim > 0:
                payout_per_capita_arr = claim_per_capita * budget_to_distribute / total_claim
            else:
                payout_per_capita_arr = np.full(len(self.communities), budget_to_distribute / max(n_citizens_arr.sum(), 1e-6))
            weights = (claim_per_capita * n_citizens_arr) / max(total_claim, 1e-9)  # for logging/assertions only
        else:
            # ORIGINAL mechanism, preserved exactly for backward comparability
            # with every earlier experiment this conversation ran.
            total = weighted_scores.sum()
            if self.flat_allocation:
                weights = np.ones(len(self.communities)) / len(self.communities)
            elif total > 0:
                weights = weighted_scores / total
            else:
                weights = np.ones(len(self.communities)) / len(self.communities)
            payout_per_capita_arr = weights * budget_to_distribute / (n_citizens_arr + 1e-6)

        if self.debug_assertions:
            assert np.isclose(weights.sum(), 1.0, atol=1e-6), (
                f"tick {self.tick}: allocation weights sum to {weights.sum()}, not 1.0 -- "
                f"a community is being over- or under-allocated relative to the budget."
            )

        n_comms = len(self.communities)
        for i, comm in enumerate(self.communities):
            if comm.recall_cooldown > 0:
                # Under active recall: Ledger's discretionary (merit-weighted)
                # allocation is suspended. Community gets a flat equal share
                # instead -- the cost of losing legibility-based multiplier.
                payout = (budget_to_distribute / n_comms) / (len(comm.citizens) + 1e-6)
                comm.global_budget = budget_to_distribute / n_comms
            else:
                payout = payout_per_capita_arr[i]
                comm.global_budget = payout * len(comm.citizens)

            # Round-trip: decision needs the community's report (already
            # accounted for via the delayed snapshot above) and the payout
            # then needs to physically arrive -- another one-way trip.
            # CRITICAL: queue the TOTAL committed amount, not a per-capita
            # rate. Population can change substantially during transit
            # (migration is constant in this model); re-dividing a stale
            # per-capita rate across a LATER, possibly very different
            # population is what causes runaway blowup if a community
            # shrinks near zero between commitment and delivery. Queuing
            # the total and dividing by whoever is actually there on
            # arrival keeps the payout bounded by what was actually earned.
            total_committed = payout * len(comm.citizens)
            delay = 2 * comm.distance if self.communication_latency_enabled else 0
            if delay > 0:
                self.pending_payouts.append((self.tick + delay, comm, total_committed))
            else:
                for citizen in comm.citizens:
                    citizen.resources += payout
            self.global_reserve -= total_committed

            # Opt-in allocation instrumentation, built specifically to confirm
            # or refute Mechanism 1 (crisis-locked communities winning a
            # disproportionate share because rep=c is undiluted by decay)
            # rather than leaving it as an endpoint inference.
            if self.log_allocation_details:
                self.allocation_log.append({
                    "tick": self.tick,
                    "community_id": comm.unique_id,
                    "policy": comm.policy,
                    "in_crisis_management": comm.in_crisis_management,
                    "n_citizens": len(comm.citizens),
                    "proof": float(proofs[i]),
                    "prod_per_capita": float(prod_per_capita[i]),
                    "weighted_score": float(weighted_scores[i]),
                    "weight": float(weights[i]),
                    "payout_per_capita": float(payout),
                })

    def enforce_individual_floor(self):
        """A genuine, unconditional guarantee: no citizen ends a step below
        individual_floor_threshold, regardless of their community's
        aggregate state, regardless of whether a catastrophe just hit,
        regardless of what automated_provisioning's community-level need
        calculation decided. This is the difference between "on average,
        almost nobody suffers" and "nobody, ever, specifically" -- the two
        are NOT the same claim, and everything else in this model only
        guarantees the first one.

        Privacy note: this checks and corrects individual resource values
        directly, same as every other internal mechanic in this model
        already does -- the privacy commitment scheme concerns what gets
        PUBLISHED to other parties, not whether the AI's internal logic can
        act on individual data. Nothing about who was topped up, or by how
        much, is exposed anywhere -- only a step-level count is tracked,
        itself just an aggregate.
        """
        self.floor_topups_this_step = 0
        for citizen in self.agents:
            if not isinstance(citizen, Citizen):
                continue
            if citizen.resources < self.individual_floor_threshold:
                citizen.resources = self.individual_floor_threshold
                self.floor_topups_this_step += 1

    def migration_phase(self):
        migrants = [a for a in self.agents if isinstance(a, Citizen) and a.resources < 0.5]
        if self.informed_migration:
            status = self.ledger.get_system_status()
        for citizen in migrants:
            if self.informed_migration:
                candidates = self.random.sample(status, k=min(3, len(status)))
                dest = min(candidates, key=lambda x: x["deficit"])["community"]
            else:
                dest = self.random.choice(self.communities)
            if dest != citizen.community:
                if citizen in citizen.community.citizens:
                    citizen.community.citizens.remove(citizen)
                dest.citizens.append(citizen)
                citizen.community = dest
                # Colluder reputation represents an in-group network, not
                # locally-earned standing -- when portable, it travels with
                # the citizen rather than resetting like honest reputation
                # does. This is the actual test of whether colluder's clique
                # bonus can function as designed: previously it was being
                # wiped out by migration-driven resets far faster than it
                # could accumulate (colluder migrates ~6-8x more per capita
                # than greedy, since its contribution is reputation-blind
                # and never gets to "coast" the way greedy's does).
                if not (self.colluder_reputation_portable and citizen.strategy == "colluder"):
                    citizen.reputation *= self.migration_reputation_decay
                # A caregiver-target relationship can't span communities --
                # migration dissolves it, freeing both parties to re-pair.
                if self.meaningful_care_enabled:
                    if citizen.caregiver_of is not None:
                        citizen.caregiver_of.caring_for = None
                        citizen.caregiver_of = None
                    if citizen.caring_for is not None:
                        citizen.caring_for.caregiver_of = None
                        citizen.caring_for = None

    def run_policy_tournament(self):
        """Replicator dynamics over community policy, selecting on a
        configurable fitness metric. copy_prob controls how strongly the
        worst performer imitates the best; mutation_prob allows exploration
        away from the current leader so the system doesn't lock in early."""
        if self.tournament_metric == "resource_gini":
            fitness = {c: -c.resource_gini() for c in self.communities}   # lower gini = fitter
        elif self.tournament_metric == "contribution_gini":
            fitness = {c: -c.contribution_gini() for c in self.communities}
        else:
            raise ValueError("unknown tournament_metric")

        # Communities currently under Governance Override sit out the
        # tournament entirely: survival state isn't up for a vote.
        eligible = [c for c in self.communities if not c.in_crisis_management]
        if len(eligible) < 2:
            return
        ranked = sorted(eligible, key=lambda c: fitness[c], reverse=True)
        best_policy = ranked[0].policy
        n = len(ranked)
        worst_half = ranked[n // 2:]

        for comm in worst_half:
            if self.random.random() < self.tournament_mutation_prob:
                comm.policy = self.random.choice(["meritocratic", "strict", "lenient", "clique"])
            elif self.random.random() < self.tournament_copy_prob:
                comm.policy = best_policy

    def run_policy_vote(self):
        """Genuine collective choice (Ostrom principle 3): citizens vote on
        their OWN community's policy by simple majority of preferred_policy().
        Unlike the Tournament (communities copying whoever scores best on an
        external fitness metric) or crisis override (forced), this is the
        first mechanism where citizens actually determine their own
        governance -- for better or worse. Self-interest, not virtue, drives
        the vote; if free-riding strategies form a numerical majority in a
        community, they can vote in the policy that benefits them, same as
        any real democracy is vulnerable to a self-interested majority.

        Communities in crisis_management sit out -- survival state isn't
        up for a vote, consistent with how the Tournament already handles
        this.
        """
        for comm in self.communities:
            if comm.in_crisis_management or not comm.citizens:
                continue
            votes = {}
            for citizen in comm.citizens:
                pref = citizen.preferred_policy()
                votes[pref] = votes.get(pref, 0) + 1
            winner = max(votes, key=votes.get)
            comm.policy = winner

    def run_crisis_vote(self):
        """Citizens vote on whether to formally declare an emergency --
        i.e., whether to accept forced suspension of their own elected
        policy. Directly analogous to the ecological continue/pause vote:
        the AI surfaces real strain (crisis_severity, computed every step
        regardless of the vote) but does not unilaterally act on it. Vote
        probability scales with how severe the real strain actually is --
        citizens under real pressure are more likely to accept emergency
        measures, but it's their acceptance, not an automatic override."""
        for comm in self.communities:
            if not comm.citizens:
                continue
            p_declare = min(1.0, comm.crisis_severity * self.emergency_declare_sensitivity)
            declare_votes = sum(1 for _ in comm.citizens if self.random.random() < p_declare)
            comm.emergency_declared = declare_votes >= (len(comm.citizens) / 2)

    def run_contested_sites(self):
        """Sequential build windows on a shared, indivisible site. Space
        can't be split the way a divisible resource can -- so instead of
        arbitrating WHO gets the site permanently, this arbitrates WHEN
        each community gets it. Fairness comes from the handoff rule, not
        from the initial pick: whoever has built LESS so far always goes
        next, so no community can end up permanently behind regardless of
        how the very first turn was decided.

        With ecological_impact_enabled: the AI never unilaterally stops a
        project. It only does two things -- (1) lets impact accumulate
        while building and recover while paused, exactly like land needing
        time to rest, and (2) makes the DECLINING VALUE of continued
        building directly visible in what the builder actually receives,
        rather than hiding it in an internal number nobody responds to.
        Whether to keep going is decided by an actual citizen vote, not an
        override -- this is the gradual-cost-plus-real-choice combination,
        not the hard-veto version that crisis_management already showed
        tends to become permanent rather than exceptional.
        """
        for site in self.contested_sites:
            eco_on = self.ecological_impact_enabled

            if eco_on:
                if site["paused"]:
                    site["ecological_impact"] = max(0.0, site["ecological_impact"] - self.impact_recovery_rate)
                else:
                    site["ecological_impact"] += self.impact_growth_rate
                    value_multiplier = max(0.1, 1.0 - site["ecological_impact"] * self.eco_value_decay_rate)
                    # The declining value is visible and real, not just
                    # logged -- the builder's own citizens feel it directly.
                    for citizen in site["current_builder"].citizens:
                        citizen.reputation = min(1.0, citizen.reputation + 0.01 * value_multiplier)

                if self.tick % self.eco_vote_period == 0:
                    voters = site["community_a"].citizens + site["community_b"].citizens
                    p_continue = max(0.0, 1.0 - site["ecological_impact"] * self.eco_concern_sensitivity)
                    continue_votes = sum(1 for _ in voters if self.random.random() < p_continue)
                    site["paused"] = continue_votes < (len(voters) / 2)

            if site["paused"]:
                continue  # no build progress, no handoff, while paused

            site["window_remaining"] -= 1
            if site["window_remaining"] <= 0:
                current = site["current_builder"]
                site["build_ticks"][current.unique_id] += self.build_window_length
                comm_a, comm_b = site["community_a"], site["community_b"]
                other = comm_b if current is comm_a else comm_a
                # Handoff, not a fresh contest each time -- whoever's behind
                # on cumulative build time gets the next window, keeping
                # long-run access roughly equal without needing a new
                # negotiation every single cycle.
                if site["build_ticks"][other.unique_id] <= site["build_ticks"][current.unique_id]:
                    site["current_builder"] = other
                site["window_remaining"] = self.build_window_length
