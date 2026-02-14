# ADR-001: Reject Tail-End High-Certainty (>99c) Strategy

- **Status:** Rejected
- **Date:** 2025-02-14
- **Context:** Polymarket trading strategy evaluation

## Question

Is it profitable to buy shares priced >$0.99 near the end of an event's resolution on Polymarket?

## Analysis

### Revenue Structure

| Outcome | Probability | P&L per Share |
|---------|------------|---------------|
| Win     | ~99%       | +$0.01        |
| Lose    | ~1%        | -$0.99        |

### Expected Value

```
EV = P(win) x (+$0.01) - P(lose) x (-$0.99)
   = 0.99 x 0.01 - 0.01 x 0.99
   = 0
```

At fair pricing, EV = 0. No edge exists.

### Simulated 100 Trades

| Outcome | Count | Per Trade | Total   |
|---------|-------|-----------|---------|
| Win     | 99    | +$0.01    | +$0.99  |
| Lose    | 1     | -$0.99    | -$0.99  |
| **Net** |       |           | **$0.00** |

99 small wins are exactly offset by 1 loss.

### Factors Making It Negative EV in Practice

1. **Fees** - Polymarket charges fees on winnings, reducing the +$0.01 profit further while losses remain unchanged
2. **Tail risk underpricing** - Markets tend to underestimate tail risk; true flip probability may be >1%, making real EV negative
3. **Capital inefficiency** - Locking large capital for ~1% max return; opportunity cost is significant
4. **Liquidity impact** - Large orders near expiry push price above $0.99, reducing profit margin further
5. **Ruin risk** - Strategy is equivalent to selling insurance; one black swan wipes out all accumulated gains

### Risk Profile

This strategy is structurally identical to "picking up pennies in front of a steamroller":

- **Win/Loss ratio:** 1:99 (asymmetrically unfavorable)
- **Required win rate to break even (after fees):** >99.5%
- **Historical precedent:** Events have flipped from 95%+ in the final hours on Polymarket

## Decision

**Rejected.** This strategy has no positive edge at fair market prices and becomes negative EV after fees and tail risk adjustment. It is not suitable for systematic trading.

## Key Takeaway

High win rate does not imply profitability. A profitable strategy requires:

```
EV = win_rate x avg_win - loss_rate x avg_loss > 0
```

All three conditions must hold simultaneously:

1. **Edge** - EV > 0 (market mispricing in your favor)
2. **Survivability** - Position sizing that avoids ruin before EV materializes
3. **Repetition** - Sufficient sample size for the law of large numbers to take effect

This strategy fails condition #1, and its extreme loss asymmetry makes condition #2 fragile even if a marginal edge were found.

## Implications for Strategy Selection

Focus research effort on strategies where:

- Edge is quantifiable and derived from superior information or modeling (e.g., `strategies/crypto-mispricing/`)
- Risk/reward is symmetric or positively skewed (lose small, win big)
- Fees do not consume the entire edge
