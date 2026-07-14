"""
reference_gateway.py

A REFERENCE PATTERN, not a product. This demonstrates the honest,
buildable shape of "governance as one signal in a real decision," in
direct contrast to the previous framing ("Governance Primitive... enforces
commons-based resource limits... mitigates tool-poisoning risks"), which
described a gateway-grade system this project doesn't have.

WHAT'S REAL HERE: the rate limiter and the audit log are genuinely
functional, working code -- not stubs, not comments describing what would
go there. The compliance check calls the already-verified rules in
governance_compliance.py. All three signals combine into an actual
allow/block decision.

WHAT'S DELIBERATELY A STUB, MARKED EXPLICITLY: authentication. A real
deployment needs cryptographic identity (OAuth/OIDC, per MCP 2026-07-28's
own auth-hardening SEPs) verifying WHICH agent is calling, not a fixed
allow-list of strings. That's a well-solved problem with existing
standards -- it does not need to be reinvented here, and pretending a
toy allow-list is "identity verification" would be exactly the kind of
overclaim this file exists to avoid.

THE ARCHITECTURAL POINT, made in code rather than prose: no single
signal decides anything alone. Compliance-with-governance-rules is one
input. Rate limiting is another. Real auth would be a third. A gateway's
job is composing multiple imperfect signals into one decision with a
full audit trail -- not any single signal claiming to BE the decision.
That's what separates this from the earlier "circuit breaker" framing:
a circuit breaker that only ever looks at one signal isn't a circuit
breaker, it's that one signal wearing a bigger title.
"""
import time
import json
from collections import defaultdict, deque

from governance_compliance import RULES


# ============================================================
# Signal 1: rate limiting -- REAL, working, in-memory.
# A production version would back this with Redis or similar for
# multi-instance deployments (the same "explicit handle, server-managed
# state" pattern MCP 2026-07-28 itself adopted when it dropped protocol-
# level sessions) -- the LOGIC below is genuine, only the storage backend
# would need to change for horizontal scale.
# ============================================================

class RateLimiter:
    def __init__(self, max_calls: int = 10, window_seconds: float = 60.0):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls = defaultdict(deque)  # agent_id -> deque of call timestamps

    def check(self, agent_id: str) -> dict:
        now = time.time()
        calls = self._calls[agent_id]
        while calls and now - calls[0] > self.window_seconds:
            calls.popleft()
        if len(calls) >= self.max_calls:
            return {"passed": False, "reason": f"rate limit exceeded: {len(calls)}/{self.max_calls} "
                                                 f"calls in the last {self.window_seconds}s"}
        calls.append(now)
        return {"passed": True, "reason": f"{len(calls)}/{self.max_calls} calls in window"}


# ============================================================
# Signal 2: authentication -- DELIBERATE STUB.
# A fixed allow-list is not identity verification -- it's a placeholder
# making the composition pattern runnable. Do not deploy this signal as
# written. Replace with real OAuth/OIDC token validation per MCP
# 2026-07-28's auth-hardening SEPs before this touches anything real.
# ============================================================

class StubAuthenticator:
    """NOT PRODUCTION AUTH. Exists only so the gateway below has three
    genuinely composed signals to demonstrate, rather than two real ones
    and a hand-wave. Replace entirely."""
    def __init__(self, known_agent_ids: set):
        self._known = known_agent_ids

    def check(self, agent_id: str) -> dict:
        if agent_id not in self._known:
            return {"passed": False, "reason": f"'{agent_id}' not in the (STUB, non-cryptographic) allow-list"}
        return {"passed": True, "reason": "present in stub allow-list -- NOT a real identity guarantee"}


# ============================================================
# Signal 3: governance compliance -- the already-verified logic from
# governance_compliance.py, used exactly as before. Nothing about this
# signal changed; what changed is that it's now explicitly ONE input to
# a decision, not the decision itself.
# ============================================================

def check_compliance_signal(action_type: str, action_args: dict) -> dict:
    if action_type not in RULES:
        return {"passed": False, "reason": f"unknown action_type '{action_type}'"}
    try:
        result = RULES[action_type](**action_args)
    except TypeError as e:
        return {"passed": False, "reason": f"malformed action_args for {action_type}: {e}"}
    return {"passed": result["compliant"], "reason": result["reason"]}


# ============================================================
# The gateway itself: composes all three signals, makes one decision,
# writes one audit entry. This function, not any single signal above,
# is what would actually sit in front of a real tool call in a real
# deployment -- and even this reference version only decides; a real
# gateway would also need the actual interception/proxy plumbing to sit
# between an agent and its tool calls, which is out of scope here.
# ============================================================

class ReferenceGateway:
    def __init__(self, known_agent_ids: set, max_calls_per_minute: int = 10):
        self.authenticator = StubAuthenticator(known_agent_ids)
        self.rate_limiter = RateLimiter(max_calls=max_calls_per_minute)
        self.audit_log = []  # real, in-memory; a production version persists this durably

    def decide(self, agent_id: str, action_type: str, action_args: dict) -> dict:
        auth_result = self.authenticator.check(agent_id)
        rate_result = self.rate_limiter.check(agent_id)
        # Short-circuit before spending compute on a compliance check for
        # a request that's already going to be blocked -- genuine
        # engineering reason, not just a stylistic one.
        if not auth_result["passed"]:
            decision = self._log(agent_id, action_type, action_args, "BLOCK",
                                  {"auth": auth_result, "rate_limit": None, "compliance": None})
            return decision
        if not rate_result["passed"]:
            decision = self._log(agent_id, action_type, action_args, "BLOCK",
                                  {"auth": auth_result, "rate_limit": rate_result, "compliance": None})
            return decision

        compliance_result = check_compliance_signal(action_type, action_args)
        verdict = "ALLOW" if compliance_result["passed"] else "BLOCK"
        decision = self._log(agent_id, action_type, action_args, verdict,
                              {"auth": auth_result, "rate_limit": rate_result, "compliance": compliance_result})
        return decision

    def _log(self, agent_id, action_type, action_args, verdict, signals) -> dict:
        entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "action_type": action_type,
            "action_args": action_args,
            "verdict": verdict,
            "signals": signals,
        }
        self.audit_log.append(entry)
        return entry


if __name__ == "__main__":
    print("=== Demonstrating genuine multi-signal composition, not a single check wearing a bigger title ===\n")

    gateway = ReferenceGateway(known_agent_ids={"agent-research-01"}, max_calls_per_minute=3)

    print("1. Unknown agent -- blocked on auth, compliance never even runs:")
    result = gateway.decide("agent-unknown-99", "resource_transfer",
                             {"proposed_amount": 5, "need": 20, "donor_surplus": 50, "trust_level": 0.8})
    print(json.dumps(result, indent=2))

    print("\n2. Known agent, compliant transfer -- allowed:")
    result = gateway.decide("agent-research-01", "resource_transfer",
                             {"proposed_amount": 5, "need": 20, "donor_surplus": 50, "trust_level": 0.8})
    print(json.dumps(result, indent=2))

    print("\n3. Known agent, NON-compliant transfer (over cap) -- blocked on compliance:")
    result = gateway.decide("agent-research-01", "resource_transfer",
                             {"proposed_amount": 40, "need": 20, "donor_surplus": 50, "trust_level": 0.8})
    print(json.dumps(result, indent=2))

    print("\n4. Same agent, hammering the gateway past its rate limit (3/min) -- blocked on rate, not compliance:")
    for i in range(4):
        result = gateway.decide("agent-research-01", "resource_transfer",
                                 {"proposed_amount": 5, "need": 20, "donor_surplus": 50, "trust_level": 0.8})
    print(json.dumps(result, indent=2))

    print(f"\n=== Full audit trail: {len(gateway.audit_log)} entries, every decision traceable to its signals ===")
