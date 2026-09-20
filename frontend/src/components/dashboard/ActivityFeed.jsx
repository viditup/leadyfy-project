import { PackageCheck, IndianRupee, FileText, Camera, LifeBuoy, Bell } from 'lucide-react';
import { EmptyState } from '../common/States';

const ICONS = {
  delivery: { icon: PackageCheck, tint: 'green' },
  payment: { icon: IndianRupee, tint: 'amber' },
  script: { icon: FileText, tint: 'blue' },
  shoot: { icon: Camera, tint: 'purple' },
  ticket: { icon: LifeBuoy, tint: 'red' },
  default: { icon: Bell, tint: 'gray' },
};

const TINTS = {
  green: { bg: 'var(--green-soft)', fg: '#4ade80' },
  amber: { bg: 'var(--amber-soft)', fg: 'var(--amber-text)' },
  blue: { bg: 'var(--blue-soft)', fg: '#93c5fd' },
  purple: { bg: 'var(--purple-soft)', fg: '#c4b5fd' },
  red: { bg: 'var(--red-soft)', fg: '#fca5a5' },
  gray: { bg: 'var(--gray-soft)', fg: 'var(--text-secondary)' },
};

export default function ActivityFeed({ items }) {
  if (!items || items.length === 0) return <EmptyState title="No recent activity" />;
  return (
    <div>
      {items.map((item) => {
        const conf = ICONS[item.type] || ICONS.default;
        const Icon = conf.icon;
        const tint = TINTS[conf.tint];
        return (
          <div className="activity-item" key={item.id}>
            <span className="activity-icon" style={{ background: tint.bg, color: tint.fg }}>
              <Icon size={14} />
            </span>
            <div>
              <div className="activity-text">{item.text}</div>
              <div className="activity-time">{item.time}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
