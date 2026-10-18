import { useState } from "react";

export default function SummaryCard({ summary, llmError }) {
  const [open, setOpen] = useState(false);
  if (!summary) {
    return (
      <section className="card summary" data-testid="summary">
        <div className="card-head"><h3>AI summary</h3><span className="badge badge-warn">Unavailable</span></div>
        <p className="muted">
          {llmError?.message || "No summary has been generated yet."} The statistics below are still based on your reviews.
        </p>
      </section>
    );
  }
  const demo = summary.mode === "mock";
  return (
    <section className="card summary" data-testid="summary">
      <div className="card-head">
        <h3>AI summary</h3>
        <span className={`badge ${demo ? "badge-muted" : "badge-info"}`} title={summary.model}>
          {demo ? "Demo summary" : `AI · ${summary.model}`}
        </span>
      </div>
      <p className="summary-text">{summary.overall_summary}</p>
      {summary.sentiment_explanation && (
        <>
          <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>
            Why this sentiment? {open ? "▲" : "▼"}
          </button>
          {open && <p className="muted">{summary.sentiment_explanation}</p>}
        </>
      )}
      {summary.important_aspects?.length > 0 && (
        <ul className="aspect-notes">
          {summary.important_aspects.map((a) => (
            <li key={a.aspect}><b>{a.aspect}</b> {a.note}</li>
          ))}
        </ul>
      )}
      {demo && summary.warnings?.[0] && <p className="muted small">{summary.warnings[0]}</p>}
    </section>
  );
}
