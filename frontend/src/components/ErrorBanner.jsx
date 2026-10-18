const HINTS = {
  llm_api_key_missing:
    "Add LLM_API_KEY to backend/.env (or set USE_MOCK_LLM=true for the offline demo), then restart the backend.",
  network: "Start the backend with: uvicorn app.main:app --reload --port 8000",
  missing_columns: "Your CSV needs a column containing the review text, e.g. a header named “review”.",
  llm_unavailable: "Your sentiment and aspect results are still shown below. Try re-analyzing in a moment.",
  llm_auth_failed: "Check the API key in backend/.env.",
};

export default function ErrorBanner({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div className="banner banner-error" role="alert" data-testid="error-banner">
      <div>
        <strong>{error.message}</strong>
        {HINTS[error.code] && <p>{HINTS[error.code]}</p>}
      </div>
      <button className="icon-btn" onClick={onDismiss} aria-label="Dismiss error">✕</button>
    </div>
  );
}
