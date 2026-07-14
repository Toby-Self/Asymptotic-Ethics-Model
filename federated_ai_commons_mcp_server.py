#!/usr/bin/env python3
"""
federated_ai_commons_mcp_server.py

An MCP (Model Context Protocol) server exposing the Federated AI-Commons
Model as a set of callable tools, rather than requiring hand-written
bash+python boilerplate for every experiment -- which is how every single
experiment in this project's actual development was run, turn after turn.

HONEST SCOPE, stated up front: this file is complete and its tool logic
is directly tested (every function below works correctly when called as
plain Python -- see the accompanying test run). What it does NOT do is
connect itself to any MCP client automatically. That step happens outside
this file, in whatever MCP client you're using, by pointing its
configuration at this script. See the bottom of this file for exact,
tested instructions -- building the server and connecting it to a client
are two different steps, and only the first one happens here.

Run standalone (this is what an MCP client actually launches):
    python3 federated_ai_commons_mcp_server.py
"""
import json
import sys
import os
import subprocess
import inspect
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from federated_ai_commons_model import FederatedAICommonsModel, Citizen, gini
from governance_compliance import RULES

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("federated-ai-commons")


def _summarize_run(m):
    """Shared summary extraction, reused by every tool below so results
    are consistently shaped regardless of which tool produced them --
    the same discipline this project applied to its own datacollector
    fields throughout development."""
    citizens = [a for a in m.agents if isinstance(a, Citizen)]
    honest = [c.resources for c in citizens if c.strategy == "honest"]
    df = m.datacollector.get_model_vars_dataframe()

    def last(col):
        return float(df[col].iloc[-1]) if col in df.columns and len(df) else None

    def tail_mean(col, n=20):
        return float(df[col].tail(n).mean()) if col in df.columns and len(df) else None

    return {
        "final_tick": m.tick,
        "pct_honest": last("pct_honest"),
        "resource_gini": last("resource_gini"),
        "reputation_gini": float(gini([c.reputation for c in citizens])) if citizens else None,
        "honest_min_resources": float(min(honest)) if honest else None,
        "honest_mean_resources": float(np.mean(honest)) if honest else None,
        "pct_crisis_mgmt": tail_mean("pct_crisis_mgmt"),
        "pct_emergency_declared": tail_mean("pct_emergency_declared"),
    }


@mcp.tool()
def check_governance_compliance(action_type: str, action_json: str) -> str:
    """Stateless compliance check: given a proposed action and the state
    needed to judge it (both supplied in action_json, nothing retained
    server-side between calls), returns whether the action is compliant
    with this framework's governance rules -- and why.

    Every rule here is a verified, faithful extraction of logic that
    already exists and is already tested in the underlying simulation,
    not a plausible-sounding reimplementation -- see governance_compliance.py's
    own verification block, which checks each rule against real captured
    votes/transfers from a live model run, not just against itself.

    Supported action_type values and their action_json schema:
      "emergency_declaration": {"total_citizens": int, "declare_votes": int}
        -- can this community legitimately declare emergency governance
        (forced policy suspension)? Requires majority consent.
      "resource_transfer": {"proposed_amount": float, "need": float,
        "donor_surplus": float, "trust_level": float,
        "max_transfer_fraction": float (optional, default 0.3)}
        -- is this transfer within the trust-scaled, capped amount the
        framework actually permits?
      "site_continuation": {"total_voters": int, "continue_votes": int}
        -- can building/use of a shared, ecologically-impacted site
        legitimately continue? Requires majority voter support.

    Call list_compliance_rules() for the full schema and rationale behind
    each rule before constructing action_json.
    """
    if action_type not in RULES:
        return json.dumps({
            "error": f"unknown action_type '{action_type}'",
            "supported_action_types": list(RULES.keys()),
        })
    try:
        args = json.loads(action_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid action_json: {e}"})
    try:
        result = RULES[action_type](**args)
    except TypeError as e:
        return json.dumps({"error": f"action_json arguments don't match {action_type}'s required schema: {e}"})
    return json.dumps(result, indent=2)


@mcp.tool()
def list_compliance_rules() -> str:
    """List every available governance compliance rule, its required
    action_json schema, and the rationale behind it -- read this before
    calling check_governance_compliance() to construct valid requests."""
    import inspect
    rules = {}
    for name, fn in RULES.items():
        sig = inspect.signature(fn)
        params = {}
        for pname, p in sig.parameters.items():
            default = p.default if p.default is not inspect.Parameter.empty else "required"
            params[pname] = str(default)
        rules[name] = {
            "parameters": params,
            "rationale": (fn.__doc__ or "").strip().split("\n\n")[0].strip(),
        }
    return json.dumps(rules, indent=2)


@mcp.tool()
def run_simulation(params_json: str = "{}", steps: int = 300, seed: int = 1,
                    n_citizens: int = 200, n_communities: int = 8) -> str:
    """Run a single Federated AI-Commons Model simulation and return key
    outcome metrics as JSON.

    params_json: a JSON object of any opt-in model parameters, e.g.
    '{"coupled_governance": true, "post_scarcity_enabled": true,
    "automation_care_absorption": 1.0}'. Call list_parameters() first if
    unsure what's available -- there are ~132 opt-in parameters across
    28 independently-toggleable subsystems, all defaulted off.
    """
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid params_json: {e}"})
    m = FederatedAICommonsModel(n_citizens, n_communities, seed=seed, debug_assertions=True, **params)
    for _ in range(steps):
        m.step()
    return json.dumps(_summarize_run(m), indent=2)


@mcp.tool()
def compare_configurations(config_a_json: str, config_b_json: str,
                            steps: int = 300, n_seeds: int = 4,
                            n_citizens: int = 200, n_communities: int = 8) -> str:
    """Run two model configurations across multiple seeds and return their
    averaged outcome metrics side by side. This is the actual pattern used
    throughout this project's development -- never trust a single seed;
    always compare configurations against each other directly rather than
    reasoning about one in isolation. Several real bugs in this codebase
    were only caught by exactly this kind of paired comparison.
    """
    try:
        config_a = json.loads(config_a_json)
        config_b = json.loads(config_b_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid config JSON: {e}"})

    def run_averaged(params):
        runs = []
        for seed in range(1, n_seeds + 1):
            m = FederatedAICommonsModel(n_citizens, n_communities, seed=seed,
                                        debug_assertions=True, **params)
            for _ in range(steps):
                m.step()
            runs.append(_summarize_run(m))
        averaged = {}
        for key in runs[0]:
            vals = [r[key] for r in runs if r[key] is not None]
            averaged[key] = float(np.mean(vals)) if vals else None
        return averaged

    return json.dumps({
        "config_a": run_averaged(config_a),
        "config_b": run_averaged(config_b),
        "n_seeds": n_seeds,
        "steps": steps,
    }, indent=2)


@mcp.tool()
def wide_seed_sweep(params_json: str = "{}", steps: int = 300, n_seeds: int = 20,
                     n_citizens: int = 200, n_communities: int = 8) -> str:
    """Run a configuration across many seeds specifically checking for
    crashes, assertion failures, or resource blowups -- the exact
    adversarial-testing pattern that caught every real bug found in this
    project's development (a billions-scale payout blowup that only
    appeared in 3 of 10 seeds, a negotiation over-commitment bug, several
    calibration failures). Returns a report of any seed that failed, not
    just aggregate statistics that could hide a rare failure.
    """
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid params_json: {e}"})

    failures = []
    for seed in range(1, n_seeds + 1):
        try:
            m = FederatedAICommonsModel(n_citizens, n_communities, seed=seed,
                                        debug_assertions=True, **params)
            for _ in range(steps):
                m.step()
            citizens = [a for a in m.agents if isinstance(a, Citizen)]
            max_res = max((c.resources for c in citizens), default=0)
            if max_res > 100000:
                failures.append({"seed": seed, "issue": f"resource blowup: {max_res}"})
        except AssertionError as e:
            failures.append({"seed": seed, "issue": f"assertion failed: {e}"})
        except Exception as e:
            failures.append({"seed": seed, "issue": f"crashed: {type(e).__name__}: {e}"})

    return json.dumps({
        "n_seeds_tested": n_seeds,
        "n_failures": len(failures),
        "failures": failures,
        "clean": len(failures) == 0,
    }, indent=2)


@mcp.tool()
def list_parameters() -> str:
    """List every opt-in model parameter with its default value, and
    separately list the 28 independent '_enabled' master switches -- the
    top-level subsystems worth knowing about before diving into the full
    ~132-parameter surface."""
    sig = inspect.signature(FederatedAICommonsModel.__init__)
    params = {}
    for name, p in sig.parameters.items():
        if name in ("self", "N_citizens", "N_communities"):
            continue
        default = p.default if p.default is not inspect.Parameter.empty else None
        params[name] = default
    enabled_flags = [p for p in params if p.endswith("_enabled")]
    return json.dumps({
        "total_parameters": len(params),
        "enabled_master_switches": enabled_flags,
        "all_parameters": params,
    }, indent=2, default=str)


@mcp.tool()
def get_findings() -> str:
    """Return the full contents of FINDINGS.md -- the project's
    experimental record, including every bug found and how, and current
    known open issues. Read this before running new experiments to avoid
    re-discovering an already-established result."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "FINDINGS.md")
    if not os.path.exists(path):
        return "FINDINGS.md not found alongside this server script."
    with open(path) as f:
        return f.read()


@mcp.tool()
def get_readme() -> str:
    """Return the full contents of README.md -- the project's quick-start
    map and condensed parameter reference."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
    if not os.path.exists(path):
        return "README.md not found alongside this server script."
    with open(path) as f:
        return f.read()


@mcp.tool()
def run_test_suite() -> str:
    """Run the persisted pytest regression suite and return a pass/fail
    summary. Run this before trusting results from a modified copy of the
    model file -- confirms the ~13 load-bearing findings this whole
    project depends on still hold, the same check that caught two real
    problems (a false regression alarm, an actual reversed finding) the
    one time this suite was itself first tested."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_federated_ai_commons_model.py")
    if not os.path.exists(path):
        return json.dumps({"error": "test_federated_ai_commons_model.py not found alongside this server script."})
    result = subprocess.run(
        [sys.executable, "-m", "pytest", path, "-v", "--tb=short"],
        capture_output=True, text=True, timeout=300,
    )
    return json.dumps({
        "passed": result.returncode == 0,
        "output_tail": result.stdout[-3000:],
    }, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")


# ============================================================
# HOW TO ACTUALLY CONNECT THIS -- the part that happens outside this file
# ============================================================
#
# This script, run standalone, speaks the MCP protocol over stdio and
# will sit waiting for a client to talk to it -- it will not do anything
# visible on its own. An MCP client has to be configured to LAUNCH it.
#
# For Claude Desktop, add to your claude_desktop_config.json:
#
#   {
#     "mcpServers": {
#       "federated-ai-commons": {
#         "command": "python3",
#         "args": ["/full/path/to/federated_ai_commons_mcp_server.py"]
#       }
#     }
#   }
#
# Requirements alongside this script: federated_ai_commons_model.py,
# README.md, FINDINGS.md, test_federated_ai_commons_model.py (the last three
# are optional -- only get_readme/get_findings/run_test_suite need them).
#
# Requires the `mcp` package: pip install mcp
