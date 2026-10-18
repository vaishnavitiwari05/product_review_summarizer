export default function EmptyState({ hasProducts, analyzed }) {
  return (
    <section className="card empty" data-testid="empty-state">
      <div className="empty-icon" aria-hidden="true">📈</div>
      <h2>{hasProducts && !analyzed ? "Ready to analyze" : "Turn thousands of reviews into clear insights"}</h2>
      <p>
        {hasProducts
          ? "Pick a product and press Analyze to see sentiment, key aspects, recurring issues and an evidence-checked AI summary."
          : "Upload a CSV of product reviews, or try the built-in sample data to see the full pipeline in action."}
      </p>
      <ol className="pipeline">
        {["Clean", "Sentiment", "Aspects", "Recurring opinions", "AI synthesis", "Evidence check"].map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
    </section>
  );
}
