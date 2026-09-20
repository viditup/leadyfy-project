import { TrendingUp, TrendingDown } from 'lucide-react';

const TINTS = {
  amber: { bg: 'var(--amber-soft)', fg: 'var(--amber-text)' },
  green: { bg: 'var(--green-soft)', fg: '#4ade80' },
  blue: { bg: 'var(--blue-soft)', fg: '#93c5fd' },
  red: { bg: 'var(--red-soft)', fg: '#fca5a5' },
  purple: { bg: 'var(--purple-soft)', fg: '#c4b5fd' },
};

export default function KpiCard({ icon: Icon, label, value, delta, tint = 'amber' }) {
  const c = TINTS[tint] || TINTS.amber;
  return (
    <div className="card kpi-card">
      <div className="kpi-top">
        <span className="kpi-icon" style={{ background: c.bg, color: c.fg }}>
          <Icon size={16} />
        </span>
        {delta !== undefined && (
          <span className={`kpi-delta ${delta >= 0 ? 'up' : 'down'}`}>
            {delta >= 0 ? <TrendingUp size={12} style={{ verticalAlign: -2 }} /> : <TrendingDown size={12} style={{ verticalAlign: -2 }} />}{' '}
            {Math.abs(delta)}%
          </span>
        )}
      </div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}
