import { dateRange, num } from "../utils/format.js";

function Stars({ value }) {
  const v = value ?? 0;
  return (
    <span className="stars" aria-label={value == null ? "No rating" : `${value} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={v >= i - 0.25 ? "on" : v >= i - 0.75 ? "half" : ""}>★</span>
      ))}
    </span>
  );
}

export default function ProductOverview({ product }) {
  return (
    <section className="card overview" data-testid="overview">
      <p className="eyebrow">Product</p>
      <h2>{product.product_name}</h2>
      <dl className="stat-row">
        <div><dt>Reviews analyzed</dt><dd data-testid="total-reviews">{num(product.total_reviews)}</dd></div>
        <div>
          <dt>Average rating</dt>
          <dd>{product.average_rating ?? "–"} <Stars value={product.average_rating} /></dd>
        </div>
        <div><dt>Review period</dt><dd>{dateRange(product.date_min, product.date_max)}</dd></div>
        <div>
          <dt>Removed in cleaning</dt>
          <dd title="Empty, noise-only and duplicate reviews">{num(product.removed_as_empty_noise_or_duplicate)}</dd>
        </div>
      </dl>
    </section>
  );
}
