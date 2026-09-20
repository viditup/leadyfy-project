export default function Button({
  children,
  variant = 'secondary',
  size,
  icon: Icon,
  loading = false,
  className = '',
  ...rest
}) {
  return (
    <button
      className={`btn btn-${variant} ${size === 'sm' ? 'btn-sm' : ''} ${className}`}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> : Icon ? <Icon size={15} /> : null}
      {children}
    </button>
  );
}
