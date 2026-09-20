export default function Card({ title, action, children, padded = true, className = '' }) {
  return (
    <div className={`card ${className}`}>
      {title && (
        <div className="card-header">
          <h3>{title}</h3>
          {action}
        </div>
      )}
      <div className={padded ? 'card-pad' : ''}>{children}</div>
    </div>
  );
}
