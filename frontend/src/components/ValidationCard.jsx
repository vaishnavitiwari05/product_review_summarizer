import { useState } from "react";

const ICON = { pass: "✓", warn: "!", fail: "✕" };
const CLAIM_LABEL = { supported: "Supported", weak: "Weak", unverified: "Unverified", unsupported: "Unsupported", contradicted: "Contradicted" };
const CLAIM_TONE = { supported: "good", weak: "warn", unverified: "muted", unsupported: "bad", contradicted: "bad" };

export default function ValidationCard({ validation }) {
  const [showClaims, setShowClaims] = useState(false);
  if (!validation) {
    return (
      <section className="card validation" data-testid="validation">
        <div className="card-head"><h3>Evidence validation</h3><span className="badge badge-muted">Not run</span></div>
        <p className="muted">The summary could not be generated, so there is nothing to validate.</p>
      </section>
    );
  }
  const ok = validation.verdict === "Evidence-backed";
  const flagged = validation.claims.filter((c) => !["supported"].includes(c.status));
  const shown = showClaims ? validation.claims : flagged;
  return (
    <section className={`card validation ${ok ? "ok" : "review"}`} data-testid="validation">
      <div className="card-head">
        <h3>Evidence validation</h3>
        <span className={`badge badge-lg ${ok ? "badge-good" : "badge-warn"}`} data-testid="verdict">
          {ok ? "✓ " : "⚠ "}{validation.verdict}
        </span>
      </div>
      <div className="score-row">
        <div className="bar" role="progressbar" aria-valuenow={validation.score} aria-valuemin={0} aria-valuemax={100} aria-label="Evidence score">
          <div className={`bar-fill ${ok ? "" : "warn"}`} style={{ width: `${validation.score}%` }} />
        </div>
        <b data-testid="score">{validation.score}/100</b>
      </div>
      <p className="muted">{validation.headline}</p>

      <ul className="checks">
        {validation.checks.map((c) => (
          <li key={c.id} className={`check ${c.status}`}>
            <span className="check-icon" aria-label={c.status}>{ICON[c.status]}</span>
            <div>
              <b>{c.name}</b>
              <p className="small">{c.message}</p>
              {c.status !== "pass" && c.details?.slice(0, 3).map((d, i) => <p key={i} className="muted small detail">{d}</p>)}
            </div>
          </li>
        ))}
      </ul>

      <button className="link" onClick={() => setShowClaims(!showClaims)} aria-expanded={showClaims}>
        {showClaims ? "Show flagged statements only" : `Show all ${validation.claims.length} checked statements`}
      </button>
      {shown.length > 0 && (
        <ul className="claims" data-testid="claims">
          {shown.map((c, i) => (
            <li key={i}>
              <span className={`badge badge-${CLAIM_TONE[c.status]}`}>{CLAIM_LABEL[c.status]}</span>
              <div>
                <p className="claim-text">“{c.text}”</p>
                <p className="muted small">{c.message}</p>
                {c.examples?.[0] && <p className="muted small">Example review text: “{c.examples[0]}”</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {shown.length === 0 && <p className="muted small">Every statement in the summary is supported by the data.</p>}
    </section>
  );
}
