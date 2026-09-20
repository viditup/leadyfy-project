import { Search } from 'lucide-react';

export function Field({ label, error, hint, required, children }) {
  return (
    <div className="field">
      {label && (
        <label>
          {label} {required && <span style={{ color: 'var(--red)' }}>*</span>}
        </label>
      )}
      {children}
      {error ? <span className="field-error">{error}</span> : hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  );
}

export function Input({ error, className = '', ...rest }) {
  return <input className={`input ${error ? 'input-error' : ''} ${className}`} {...rest} />;
}

export function Textarea({ error, className = '', ...rest }) {
  return <textarea className={`input ${error ? 'input-error' : ''} ${className}`} rows={4} {...rest} />;
}

export function Select({ error, className = '', children, ...rest }) {
  return (
    <select className={`select ${error ? 'input-error' : ''} ${className}`} {...rest}>
      {children}
    </select>
  );
}

export function SearchInput({ value, onChange, placeholder = 'Search…' }) {
  return (
    <div className="search-input">
      <Search size={15} />
      <input className="input" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  );
}
