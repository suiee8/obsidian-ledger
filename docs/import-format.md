# Import file format

[Download the CSV template](../web/public/templates/obsidian-ledger-template.csv). Each row describes one completed trade. Fill in the symbol, side, quantity, entry and exit times, and both prices. Keep the header row and replace the example trades with yours. Other supported exports can still be imported.

An ISO 8601 time with an offset keeps its offset. The import setting supplies the timezone for dates without one.

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
| `entry_price` | Entry price per unit | Number | `188.20` |
| `exit_price` | Exit price per unit | Number | `189.05` |
