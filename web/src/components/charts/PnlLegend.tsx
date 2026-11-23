export function PnlLegend() {
  return (
    <ul className="pnl-legend" aria-label="P&L color key">
      <li><span className="pnl-swatch pnl-swatch-profit" aria-hidden="true" /> Profit</li>
      <li><span className="pnl-swatch pnl-swatch-loss" aria-hidden="true" /> Loss</li>
      <li><span className="pnl-swatch pnl-swatch-flat" aria-hidden="true" /> Break-even</li>
      <li><span className="pnl-swatch pnl-swatch-empty" aria-hidden="true" /> No trades</li>
    </ul>
  );
}
