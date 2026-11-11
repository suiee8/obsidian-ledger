# Metrics definitions

This document is the contract for deterministic calculations. Every UI metric will carry its sample size and, where applicable, a confidence interval.

## Trade-level values

- **Net P&L** = `gross_pnl - fees - commission - swap_or_funding`.
- **R multiple** = `net_pnl / planned_risk` when planned risk is positive. If only a stop is available, planned risk is derived from entry, stop, quantity, and contract multiplier and shown as an import assumption.
- **Holding time** = `exit_time - entry_time`.
- **Win** = net P&L greater than zero. A zero result is flat and is not counted as a win or loss.

## Core aggregates

- **Win rate** = wins / non-flat trades.
- **Average win** = mean net P&L among winning trades.
- **Average loss** = absolute mean net P&L among losing trades.
- **Payoff ratio** = average win / average loss when both groups are non-empty.
- **Profit factor** = gross winning P&L / absolute gross losing P&L when losses exist.
- **Expectancy** = mean net P&L per trade. R expectancy uses the mean R multiple.
- **Median trade** = median net P&L.
- **Fee drag** = total fees and commissions / absolute gross P&L, with an explicit undefined state when gross P&L is zero.

## Risk and return

Daily return metrics require a user-provided starting equity. Without it, the application labels results as P&L-based or R-based rather than silently treating P&L as a percentage.

- **Equity** = starting equity + cumulative daily net P&L.
- **Drawdown** = equity - running equity high-water mark.
- **Maximum drawdown** = minimum drawdown, with depth, start, trough, duration, and recovery time.
- **Sharpe** = mean daily excess return / standard deviation of daily return, annualized by `sqrt(252)` when enough daily observations exist.
- **Sortino** = mean daily excess return / downside deviation, annualized by `sqrt(252)`.
- **Calmar** = annualized return / absolute maximum drawdown.
- **Recovery factor** = net P&L / absolute maximum drawdown.
- **SQN** = `sqrt(n) * mean(R) / standard_deviation(R)`.
- **Kelly upper bound** = `win_rate - (1 - win_rate) / payoff_ratio`. It is displayed as an upper bound, never as a recommended position size.

## Uncertainty and slicing

Bootstrap intervals resample the observed trades with replacement using a recorded seed. The default interval is the percentile 2.5%–97.5% interval over at least 5,000 resamples. Slices with fewer than 30 trades are marked low confidence. Segment rankings are evidence triage, not proof of a durable edge.

Monte Carlo resamples trade outcomes with replacement, reports the independence assumption, and returns path probabilities for configured drawdown and target thresholds. Comparisons across many segments show a multiple-comparisons warning and may apply Benjamini–Hochberg FDR or Bonferroni correction.

## Discipline score

The planned 0–100 score is transparent and weighted as follows:

`0.30 × plan adherence + 0.25 × risk consistency + 0.20 × post-loss behavior + 0.15 × overtrading control + 0.10 × stop usage`

Each component is normalized to 0–100 only when its source fields exist. Missing components are reported instead of treated as zero, and the displayed score includes the available-component count.

These metrics review past behavior. They are not financial advice and do not predict future returns.

## Implementation notes (Phase 2)

These notes describe what the code does. Where it differs from the definitions above, the difference is stated.

- **Filters** apply to exit date in UTC. Trades without a base-currency value are left out and counted in `excluded_no_fx`.
- **Costs** are converted with the same rate as net P&L. Gross P&L is net minus costs. Fee drag is absolute costs over absolute gross P&L.
- **Win rate** excludes flat trades (P&L exactly zero). Payoff, profit factor, and expectancy follow the formulas above.
- **Best and worst** day, week, and month group on exit date. Weeks start on Monday, the default for truncation.
- **Drawdown** uses an equity path that starts at the starting equity (or zero). Depth is a percentage only when a starting equity is known. Duration and recovery are counted in trades.
- **Daily ratios** (Sharpe, Sortino, Calmar) need a starting equity. Daily return is the day's P&L divided by equity at the start of the day. Annualized with 252 trading days. Calmar uses CAGR over the trading-day span.
- **SQN** is `sqrt(n) x mean(R) / sample sd(R)`. Undefined when R has fewer than two values or no variation.
- **Kelly** is shown as an upper bound with a warning. It is never a position size.
- **Bootstrap** intervals are percentile intervals over trade resamples. The default is 1,000 resamples with seed 42.
- **Monte Carlo** resamples trade outcomes with replacement. Paths are as long as the sample, capped at 1,000 trades. The default is 5,000 paths. Thresholds are in P&L currency. Without a starting equity, the drawdown threshold is ten times the average loss and the target is zero (chance of finishing above the start). Ruin is equity below half the starting equity.
- **Segments** compare each value with all other trades using Welch's t-test. Slices are adjusted across the values of one dimension with Benjamini-Hochberg. A slice below 30 trades is marked low confidence and cannot be labelled an edge or a leak. Intervals on segment means use Student's t, not a bootstrap.
- **Revenge** flags a trade entered after a losing trade when it enters within 10 minutes of that loss, or when its quantity is at least 50% larger. "After a loss" means the most recent trade that had already closed before the entry. Overlapping trades are not counted.
- **Overtrading** counts trades per entry day. A day above 10 trades is overtraded. The default threshold is set in the report parameters.
- **Discipline score** uses the weights in the formula string returned with each score. Missing components are removed and the remaining weights rescaled. The count of components used is returned with the score.
- **Simulator** replays trades in entry order. A trade's result updates its day's loss tally only at exit, so a decision never uses a result that was not yet known. Risk capping scales a trade's P&L by `cap / planned risk`, and leaves trades without planned risk unchanged. The change in expectancy is a paired bootstrap, with skipped trades counted as zero.

### Not implemented in Phase 2

- **Tilt score.** No definition yet that is separate from the revenge flag. Deferred to the Behavior screen work.
- **Note mining** (classifying free-text notes into FOMO, revenge, and similar tags) belongs to the Coach phase.
- **Closed-form risk of ruin.** Ruin is estimated by Monte Carlo instead.
- **Position-sizing simulation on forex lots and option contracts** beyond the contract sizes entered by the user.
