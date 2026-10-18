import { useState } from "react";
import { num } from "../utils/format.js";

export default function UploadSummary({ upload }) {
  const [open, setOpen] = useState(false);
  if (!upload) return null;
  const c = upload.cleaning;
  const warnings = [...(upload.validation?.warnings || []), ...(c?.warnings || [])];
  return (
    <section className="card upload-summary" data-testid="upload-summary">
      <div className="upload-head">
        <strong>{upload.filename}</strong>
        <span className="muted"> loaded</span>
      </div>
      <dl className="stat-row">
        <div><dt>Rows in file</dt><dd>{num(c.total_reviews)}</dd></div>
        <div><dt>Valid reviews</dt><dd>{num(c.valid_reviews)}</dd></div>
        <div><dt>Duplicates removed</dt><dd>{num(c.duplicates_removed)}</dd></div>
        <div><dt>Empty / noise removed</dt><dd>{num(c.empty_removed + c.noise_removed)}</dd></div>
        <div><dt>Products in file</dt><dd>{num(upload.uploaded_product_ids?.length ?? upload.products.length)}</dd></div>
      </dl>
      {warnings.length > 0 && (
        <>
          <button className="link" onClick={() => setOpen(!open)} aria-expanded={open}>
            {warnings.length} data-quality note{warnings.length > 1 ? "s" : ""} {open ? "▲" : "▼"}
          </button>
          {open && <ul className="notes">{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
        </>
      )}
    </section>
  );
}
