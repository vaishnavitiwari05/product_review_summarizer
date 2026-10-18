import { SENTIMENT_TONE, donutSegments, pct } from "../utils/format.js";

const COLORS = { positive: "var(--good)", neutral: "var(--muted-fill)", negative: "var(--bad)" };

export default function SentimentCard({ sentiment }) {
  const order = ["positive", "neutral", "negative"];
  const values = order.map((k) => sentiment.counts[k]);
  const segs = donutSegments(values);
  const rc = sentiment.rating_check;
  return (
    <section className="card sentiment" data-testid="sentiment">
      <h3>Sentiment</h3>
      <div className="sentiment-body">
        <svg viewBox="0 0 100 100" className="donut" role="img"
             aria-label={`Sentiment: ${order.map((k) => `${sentiment.percentages[k]}% ${k}`).join(", ")}`}>
          <circle cx="50" cy="50" r="42" fill="none" stroke="var(--track)" strokeWidth="14" />
          {segs.map((s, i) => s.length > 0 && (
            <circle key={order[i]} cx="50" cy="50" r="42" fill="none" stroke={COLORS[order[i]]}
                    strokeWidth="14" strokeDasharray={s.dash} strokeDashoffset={s.offset}
                    transform="rotate(-90 50 50)" />
          ))}
          <text x="50" y="47" textAnchor="middle" className="donut-num">{Math.round(sentiment.percentages.positive)}%</text>
          <text x="50" y="62" textAnchor="middle" className="donut-lbl">positive</text>
        </svg>
        <ul className="legend">
          {order.map((k) => (
            <li key={k}>
              <span className="swatch" style={{ background: COLORS[k] }} />
              <span className="cap">{k}</span>
              <b data-testid={`pct-${k}`}>{pct(sentiment.percentages[k], 1)}</b>
              <span className="muted small">{sentiment.counts[k]}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="overall">
        <span className="muted">Overall sentiment</span>
        <span className={`badge badge-${SENTIMENT_TONE[sentiment.overall] || "warn"}`} data-testid="overall">
          {sentiment.overall}
        </span>
      </div>
      <p className="muted small">
        Net sentiment {sentiment.net_sentiment > 0 ? "+" : ""}{sentiment.net_sentiment} pts
        {rc?.agreement_pct != null && <> · text agrees with star ratings {rc.agreement_pct}% of the time</>}
      </p>
    </section>
  );
}
