import { statusColor } from '../../utils/status';
import { humanize } from '../../data/mockData';

export default function Badge({ status, label, color, dot = true }) {
  const variant = color || statusColor(status);
  return (
    <span className={`badge badge-${variant}`}>
      {dot && <span className="badge-dot" />}
      {label || humanize(status)}
    </span>
  );
}
