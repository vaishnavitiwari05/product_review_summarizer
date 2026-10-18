import { useRef, useState } from "react";
import { num } from "../utils/format.js";

export default function ControlBar({ products, selectedId, busy, onUpload, onSample, onSelect, onAnalyze }) {
  const input = useRef(null);
  const [drag, setDrag] = useState(false);
  const disabled = !!busy;
  const selected = products.find((p) => p.product_id === selectedId);

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    if (!disabled) onUpload(e.dataTransfer.files?.[0]);
  };

  return (
    <section
      className={`card controls ${drag ? "dragging" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
      aria-label="Data controls"
    >
      <div className="control-group">
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          hidden
          data-testid="file-input"
          onChange={(e) => { onUpload(e.target.files?.[0]); e.target.value = ""; }}
        />
        <button className="btn" disabled={disabled} onClick={() => input.current?.click()}>
          <span aria-hidden="true">⬆</span> Upload CSV
        </button>
        <button className="btn btn-ghost" disabled={disabled} onClick={onSample}>
          Try sample data
        </button>
        <span className="hint">or drop a .csv file here</span>
      </div>

      <div className="control-group grow">
        <label htmlFor="product-select" className="sr-only">Product</label>
        <select
          id="product-select"
          value={selectedId}
          disabled={disabled || products.length === 0}
          onChange={(e) => onSelect(e.target.value)}
        >
          {products.length === 0 && <option value="">No products yet</option>}
          {products.map((p) => (
            <option key={p.product_id} value={p.product_id}>
              {p.product_name} · {num(p.review_count)} reviews{p.analyzed ? " ✓" : ""}
            </option>
          ))}
        </select>
        <button className="btn btn-primary" disabled={disabled || !selected} onClick={onAnalyze}>
          {busy === "analyzing" ? "Analyzing…" : selected?.analyzed ? "Re-analyze" : "Analyze"}
        </button>
      </div>
    </section>
  );
}
