# Import file format

[Download the CSV template](../web/public/templates/obsidian-ledger-template.csv). Each row describes one completed trade. Supply symbol, side, entry and exit times, quantity, and either both prices or net P&L. Keep the header row and replace the example trades with yours. Other supported exports can still be imported.

An ISO 8601 time with an offset keeps its offset. The import setting supplies the timezone for dates without one. The template follows the existing sample header. The last two entries below are additional fields detected when present in an export.

| Column | Meaning | Accepted values | Example |
| --- | --- | --- | --- |
| `trade_id` | Your trade identifier | Unique text | `example-001` |
| `account` | Account name | Text | `Paper` |
| `symbol` | Instrument | Broker symbol | `AAPL` |
| `asset_class` | Asset type | Text | `stock` |
| `side` | Trade direction | long, short, buy, sell | `long` |
| `entry_time` | When the trade opened | ISO 8601 timestamp with offset | `2026-01-06T14:35:00Z` |
| `exit_time` | When the trade closed | ISO 8601 timestamp with offset | `2026-01-06T15:10:00Z` |
| `qty` | Quantity traded | Positive number | `10` |
| `entry_price` | Entry price per unit | Number; pair with exit_price | `188.20` |
| `exit_price` | Exit price per unit | Number; pair with entry_price | `189.05` |
| `fees` | Total trading costs | Nonnegative number | `0.40` |
| `planned_risk` | Amount you planned to risk | Positive number | `4.00` |
| `r_multiple` | Outcome in units of risk | Signed number | `2.025` |
| `net_pnl` | Profit or loss after costs | Signed number; usable without prices | `8.10` |
| `currency` | Currency of the trade | Three-letter code | `USD` |
| `setup` | Trading setup | Text | `Opening range` |
| `session` | Trading session | Text | `New York` |
| `emotion` | How you felt | Text | `calm` |
| `plan_followed` | Whether you followed the plan | true or false | `true` |
| `notes` | Notes about the trade | Text; quote values containing commas | `Exited at the target` |
| `stop_loss` | Planned stop, if your export has one | Price; enables risk calculation with entry and quantity | `187.80` |
| `tags` | Labels, if your export has a tags column | Text | `breakout` |
