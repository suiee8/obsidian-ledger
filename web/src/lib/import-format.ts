export const IMPORT_TEMPLATE = "/templates/obsidian-ledger-template.csv";

export const IMPORT_COLUMNS = [
  ["trade_id", "Your trade identifier", "Unique text", "example-001"],
  ["account", "Account name", "Text", "Paper"],
  ["symbol", "Instrument", "Broker symbol", "AAPL"],
  ["asset_class", "Asset type", "Text", "stock"],
  ["side", "Trade direction", "long, short, buy, sell", "long"],
  ["entry_time", "When the trade opened", "ISO 8601 timestamp with offset", "2026-01-06T14:35:00Z"],
  ["exit_time", "When the trade closed", "ISO 8601 timestamp with offset", "2026-01-06T15:10:00Z"],
  ["qty", "Quantity traded", "Positive number", "10"],
  ["entry_price", "Entry price per unit", "Number", "188.20"],
  ["exit_price", "Exit price per unit", "Number", "189.05"],
] as const;
