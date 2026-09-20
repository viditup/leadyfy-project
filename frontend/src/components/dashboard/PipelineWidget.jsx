export default function PipelineWidget({ stages }) {
  const max = Math.max(...stages.map((s) => s.count), 1);
  return (
    <div className="flex-col gap-10">
      {stages.map((s) => (
        <div key={s.key}>
          <div className="flex justify-between" style={{ marginBottom: 5, fontSize: 12.5 }}>
            <span className="muted">{s.key}</span>
            <span style={{ fontWeight: 600 }}>{s.count}</span>
          </div>
          <div style={{ height: 6, borderRadius: 999, background: 'var(--bg-surface)', overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${(s.count / max) * 100}%`,
                background: 'var(--amber)',
                borderRadius: 999,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
