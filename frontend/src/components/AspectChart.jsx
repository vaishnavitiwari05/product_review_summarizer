import { useState } from "react";
import { stackWidths, titleCase } from "../utils/format.js";

function Examples({ aspect }) {
  const groups = [["positive", "What people like"], ["negative", "What people dislike"]]
    .map(([k, label]) => [k, label, aspect.examples?.[k] || []])
    .filter(([, , list]) => list.length);
  if (!groups.length) return <p className="muted small">No example quotes for this aspect.</p>;
  return (
    <div className="examples">
      {groups.map(([k, label, list]) => (
        <div key={k}>
          <h5 className={`tone-${k}`}>{label}</h5>
          <ul>{list.map((e) => <li key={`${k}-${e.review_id}`}>“{e.clause}”</li>)}</ul>
        </div>
      ))}
    </div>
  );
}

export default function AspectChart({ aspects }) {
  const [open, setOpen] = useState(null);
  const top = aspects.slice(0, 10);
  const max = Math.max(...top.map((a) => a.frequency), 1);
  return (
    <section className="card aspects" data-testid="aspects">
      <div className="card-head">
        <h3>Most discussed aspects</h3>
        <span className="legend inline">
          <span><i className="swatch" style={{ background: "var(--good)" }} />Positive</span>
          <span><i className="swatch" style={{ background: "var(--muted-fill)" }} />Neutral</span>
          <span><i className="swatch" style={{ background: "var(--bad)" }} />Negative</span>
        </span>
      </div>
      {top.length === 0 && <p className="muted">No recurring aspects were found in these reviews.</p>}
      <ul className="aspect-list">
        {top.map((a) => {
          const w = stackWidths(a, max);
          const isOpen = open === a.aspect;
          return (
            <li key={a.aspect}>
              <button className="aspect-row" onClick={() => setOpen(isOpen ? null : a.aspect)}
                      aria-expanded={isOpen} aria-label={`${titleCase(a.aspect)}: ${a.positive} positive, ${a.neutral} neutral, ${a.negative} negative`}>
                <span className="aspect-name">{titleCase(a.aspect)}</span>
                <span className="stack" aria-hidden="true">
                  <i className="seg pos" style={{ width: `${w.positive}%` }} />
                  <i className="seg neu" style={{ width: `${w.neutral}%` }} />
                  <i className="seg neg" style={{ width: `${w.negative}%` }} />
                </span>
                <span className="aspect-count">
                  <b>{a.frequency}</b>
                  <span className="muted small"> <span className="tone-positive">{a.positive}</span>/<span className="tone-neutral">{a.neutral}</span>/<span className="tone-negative">{a.negative}</span></span>
                </span>
              </button>
              {isOpen && <Examples aspect={a} />}
            </li>
          );
        })}
      </ul>
      <p className="muted small">Bar length = number of reviews mentioning the aspect. Click a row for example quotes.</p>
    </section>
  );
}
