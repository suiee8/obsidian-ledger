export type SampleFile = {
  file: string;
  source: string;
  shape: string;
  note: string;
};

export const sampleFiles: readonly SampleFile[] = [
  {
    file: "mt5_statement.csv",
    source: "MetaTrader 5",
    shape: "Closed positions",
    note: "Header repeats Price for the open and the close.",
  },
  {
    file: "tradingview_trades.csv",
    source: "TradingView",
    shape: "Entry and exit rows",
    note: "P&L and excursion land on the exit row.",
  },
  {
    file: "ibkr_executions.csv",
    source: "Interactive Brokers",
    shape: "Raw executions",
    note: "DateTime is YYYYMMDD;HHMMSS. MNQ multiplier is 2.",
  },
  {
    file: "messy_journal.csv",
    source: "Hand-broken export",
    shape: "Semicolon, European numbers",
    note: "Duplicates, impossible dates, formula text, and a note that tries to instruct a model. Notes are data.",
  },
  {
    file: "synthetic_preview.csv",
    source: "Generator, seed 42",
    shape: "1,000 canonical trades",
    note: "Same USD model as the 100k file.",
  },
  {
    file: "coach_planted.csv",
    source: "Coach test generator, seed 7",
    shape: "1,358 canonical trades",
    note: "Revenge re-entries, a losing 14:00 UTC hour, and overtrading days are hidden in it. The Coach should find all three.",
  },
  {
    file: "coach_noise.csv",
    source: "Coach test generator, seed 11",
    shape: "819 canonical trades",
    note: "Pure noise. The Coach should report no leak and no strength.",
  },
  {
    file: "synthetic_100k.csv",
    source: "Generator, seed 42",
    shape: "100,000 canonical trades",
    note: "Built by benchmarks/generate_trades.py. Verified by its manifest checksum.",
  },
];
