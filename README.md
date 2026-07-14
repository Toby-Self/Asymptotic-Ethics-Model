<!-- mcp-name: io.github.Toby-Self/asymptotic-ethics -->
# Asymptotic Ethics Model

An agent-based simulation testing whether a post-scarcity governance
framework — built on Elinor Ostrom's commons-governance principles —
actually holds up when implemented and adversarially stress-tested,
rather than just argued for in theory. Includes a working MCP server that
exposes the simulation as callable tools for AI agents, and a stateless
"governance primitive" that lets an agent check whether a proposed action
complies with the framework's rules, verified against the simulation's
own logic rather than reimplemented from a description of it.

**License:** Apache 2.0. **Core dependency:** [Mesa](https://mesa.readthedocs.io/) (agent-based modeling in Python).

---

## What makes this worth a look

Most of what's genuinely worth reading here isn't the simulation's
existence — it's the discipline behind it. Every mechanism was built
expecting to find its own failure mode, and several real bugs, exploits,
and false conclusions were caught and fixed as a direct result, not
hidden after the fact:

- A hard-threshold emergency-governance mechanic was found to produce
  *permanent* crisis rule under default conditions (~70–90% of the time),
  not occasional intervention — a concrete demonstration of a real AI
  governance risk. It was redesigned around consent (a citizen vote)
  rather than force, and the same pattern was later reused for
  ecological limits and shared-resource conflicts.
- Democratic policy voting was tested directly and found genuinely
  vulnerable to capture: free-riding strategies, forming a numerical
  majority, voted themselves into the most exploitable governance policy
  — a real result, not a hypothetical concern about democracy.
- A reputation-reward mechanism was found to let free-riders launder
  unearned resources into status before being fixed; a barter-economy
  value function was found to make trading a *strictly worse* strategy
  than isolation before being fixed; an evolutionary fitness metric was
  found to collapse an entire economy into monoculture before being fixed.
- The "governance primitive" compliance rules are extracted verbatim from
  the simulation's real decision logic and verified by capturing actual
  votes and transfers from a live run — not just checked against
  themselves, which would prove nothing.

The full record of every finding, bug, and fix — in the order it
happened — is in [`FINDINGS.md`](FINDINGS.md).

---

## Quick start

```bash
pip install mesa pytest mcp networkx numpy
```

```python
from asymptotic_ethics_model import AsymptoticEthicsModel

m = AsymptoticEthicsModel(200, 8, seed=1, coupled_governance=True,
                             rehabilitation_enabled=True, graduation_enabled=True)
for _ in range(300):
    m.step()

df = m.datacollector.get_model_vars_dataframe()
df.tail(10)
```

Run the regression suite before trusting any change:

```bash
pytest test_asymptotic_ethics_model.py -v
```

To run the MCP server (exposes the simulation as tools for an MCP client
like Claude Desktop — see the header comment in
`asymptotic_ethics_mcp_server.py` for exact client configuration):

```bash
python3 asymptotic_ethics_mcp_server.py
```

---

## What's in this repo

| file | what it is |
|---|---|
| `asymptotic_ethics_model.py` | The simulation itself — ~2,300 lines, ~132 opt-in parameters across 28 independent subsystems, all defaulted off to preserve baseline behavior. |
| `asymptotic_ethics_mcp_server.py` | MCP server exposing the simulation as 9 callable tools: run/compare/sweep simulations, documentation lookup, test-suite execution, and governance compliance checks. |
| `governance_compliance.py` | Three stateless compliance rules (emergency declaration, resource transfer, shared-site continuation), each extracted verbatim from the simulation's logic and verified against real captured simulation data. |
| `reference_gateway.py` | A worked example of the *honest* way to consume the compliance rules — as one signal among several (auth, rate limiting, compliance) in a real decision, not as a security layer on its own. |
| `test_asymptotic_ethics_model.py` | 13 persisted regression tests covering the load-bearing findings everything else depends on. |
| `FINDINGS.md` | The full experimental record — every finding, bug, and fix, in order. |
| `LICENSE` | Apache License 2.0. |

---

## Architecture

- **`Citizen`** — behavioral strategy, `resources`, `reputation`,
  `contribution`, relational `affinities`, `experience`. Pays
  `effort_cost = contribution ** 2` unless `post_labor_economy_enabled`.
- **`CommunityNode`** — governance policy, `care_load`, `crisis_severity`,
  `emergency_declared`, plus (depending on which subsystems are enabled)
  federated trust/reserves, latency/distance state, and the raw-material
  economy's production and trade state.
- **`SystemLedger`** — two genuinely separate roles: a migration-decision
  helper, and `ship_raw_materials()`, which is **structurally blind** to
  everything except raw material levels — verified by direct source
  inspection in the test suite, not just claimed in a docstring.
- **`AsymptoticEthicsModel`** — orchestrates every subsystem, all
  opt-in, all defaulted to preserve original behavior when disabled.

Two full resource-allocation architectures exist side by side and are
directly comparable: a centralized ledger, and a fully federated network
of local commons using peer-to-peer trust-based negotiation — including
under simulated communication latency, relevant to any framing involving
distributed or off-world coordination.

---

## Honest scope

This is a stylized research simulation — scripted behavioral strategies,
not adaptive agents; no physical production; no real politics. It tests
whether a governance framework's internal logic holds together and
surfaces concrete, reproducible failure modes when you actually try to
break it. It does not, and cannot, prove the framework would work if
built by real institutions with real humans in them. Read `FINDINGS.md`
for exactly what's been tested, what's been found broken and fixed, and
what's still an open question.
