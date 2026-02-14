# ADR Inbox: Cross-Region Market Arbitrage (US vs Global)

- **Status:** Inbox / Pending Evaluation
- **Date:** 2026-02-14
- **Owner:** Strategy Research
- **Related ADR:** `adr/001-reject-tail-end-high-certainty-strategy.md`

## Why This Is Separate

`ADR-001` only covers and rejects the tail-end high-certainty (>99c) strategy.

Cross-region arbitrage is a different strategy class, with different assumptions and risks, so it must be evaluated independently.

## Current Context

The team wants to explore whether equivalent US and Global markets can produce actionable cross-venue price dislocations.

Initial view: opportunity may exist, but only if contract definitions and execution conditions are strictly aligned.

## Scope (For Future Evaluation)

- Compare equivalent markets across US and Global venues
- Measure net edge after fees, spread, slippage, and latency
- Assess execution feasibility for two-leg synchronization
- Validate legal/operational constraints per deployment environment

## Key Risks To Validate

1. Contract mismatch (resolution rules, source, timing)
2. Execution mismatch (one leg fills, other leg fails)
3. Venue-specific fee and rebate differences
4. Capital fragmentation and transfer latency
5. Region/access constraints impacting continuity

## Minimum Go/No-Go Criteria (Draft)

1. Deterministic market-pair matching with rule equivalence checks
2. Positive expected net edge after all trading costs
3. Simulated two-leg execution with bounded leg risk
4. Stable fill rates under target position size
5. Operational compliance checks passed

## Next Step

Create a dedicated ADR draft (`ADR-00X`) after data collection for market-pair coverage, observed spreads, and executable edge.
