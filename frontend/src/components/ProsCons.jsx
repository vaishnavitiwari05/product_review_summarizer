import { titleCase } from "../utils/format.js";

function Themes({ item }) {
  const t = item.themes?.slice(0, 2).map((x) => x.label) || [];
  return t.length ? <p className="muted small">“{t.join("” · “")}”</p> : null;
}

/** One recurring opinion (a strength or an issue): aspect, how often, how one-sided, typical phrases. */
function OpinionCard({ item, kind }) {
  const good = kind === "strength";
  const share = Math.round(item.share_of_aspect * 100);
  return (
    <li>
      <div className="issue-head">
        <b>{titleCase(item.aspect)}</b>
        <span className={`badge ${good ? "badge-good" : "badge-bad"}`}>
          {item.count} {good ? "praises" : "complaints"}
        </span>
      </div>
      <div className="bar slim">
        <div className={`bar-fill ${good ? "good" : "bad"}`} style={{ width: `${share}%` }} />
      </div>
      <p className="muted small">
        {share}% of reviews that discuss it are {good ? "positive" : "negative"}
        {item.contested ? " · opinions are mixed" : ""}
      </p>
      <Themes item={item} />
    </li>
  );
}

export default function ProsCons({ results }) {
  const { summary, recurring_strengths: strengths, recurring_issues: issues, contested_aspects: contested } = results;
  const pros = summary?.pros?.length ? summary.pros : strengths.map((s) => `${titleCase(s.aspect)} (${s.count} positive mentions)`);
  const cons = summary?.cons?.length ? summary.cons : issues.map((s) => `${titleCase(s.aspect)} (${s.count} negative mentions)`);
  return (
    <>
      <section className="card pros" data-testid="pros">
        <h3><span className="tone-positive">✓</span> Pros</h3>
        {pros.length ? <ul className="check-list">{pros.map((p, i) => <li key={i}>{p}</li>)}</ul>
          : <p className="muted">No clear strengths stood out.</p>}
      </section>
      <section className="card cons" data-testid="cons">
        <h3><span className="tone-negative">✕</span> Cons</h3>
        {cons.length ? <ul className="cross-list">{cons.map((p, i) => <li key={i}>{p}</li>)}</ul>
          : <p className="muted">No clear weaknesses stood out.</p>}
      </section>
      <section className="card strengths" data-testid="strengths">
        <h3><span className="tone-positive">★</span> Recurring strengths</h3>
        {strengths.length === 0 && <p className="muted">No praise recurs often enough to be flagged.</p>}
        <ul className="issue-list">
          {strengths.map((s) => <OpinionCard key={s.aspect} item={s} kind="strength" />)}
        </ul>
      </section>
      <section className="card issues" data-testid="issues">
        <h3>⚠ Recurring issues</h3>
        {issues.length === 0 && <p className="muted">No complaint recurs often enough to be flagged.</p>}
        <ul className="issue-list">
          {issues.map((i) => <OpinionCard key={i.aspect} item={i} kind="issue" />)}
        </ul>
        {contested?.length > 0 && (
          <p className="muted small">Mixed opinions: {contested.map((c) => `${titleCase(c.aspect)} (${c.positive}↑ ${c.negative}↓)`).join(", ")}</p>
        )}
      </section>
    </>
  );
}
