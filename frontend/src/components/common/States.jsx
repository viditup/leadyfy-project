import { Inbox, AlertTriangle } from 'lucide-react';

export function LoadingState({ label = 'Loading…' }) {
  return (
    <div className="state-block">
      <span className="spinner" />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title = 'Nothing here yet', description, action }) {
  return (
    <div className="state-block">
      <span className="state-icon">
        <Icon size={20} />
      </span>
      <h4>{title}</h4>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title = 'Something went wrong', description = 'Try refreshing the page.', onRetry }) {
  return (
    <div className="state-block">
      <span className="state-icon" style={{ color: 'var(--red)' }}>
        <AlertTriangle size={20} />
      </span>
      <h4>{title}</h4>
      <p>{description}</p>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
