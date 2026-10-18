const STEPS = [
  ["Loading", 8],
  ["Sentiment", 15],
  ["Aspects", 40],
  ["Opinions", 62],
  ["AI summary", 72],
  ["Validation", 90],
];

export default function ProgressPanel({ progress }) {
  const pct = Math.max(2, Math.min(100, progress.pct || 0));
  return (
    <section className="card progress" role="status" aria-live="polite" data-testid="progress">
      <div className="progress-head">
        <span className="spinner" aria-hidden="true" />
        <strong>{progress.stage || "Working"}…</strong>
        <span className="muted">{pct}%</span>
      </div>
      <div className="bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <ol className="steps">
        {STEPS.map(([label, at], i) => {
          const next = STEPS[i + 1]?.[1] ?? 101;
          const state = pct >= next ? "done" : pct >= at ? "active" : "todo";
          return <li key={label} className={state}>{label}</li>;
        })}
      </ol>
    </section>
  );
}
