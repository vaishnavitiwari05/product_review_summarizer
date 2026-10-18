export default function Header({ health }) {
  const live = health?.llm_mode === "live";
  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
          </svg>
        </div>
        <div>
          <h1>Product Review Intelligence</h1>
          <p>AI-powered insights from customer reviews</p>
        </div>
      </div>
      {health && (
        <span
          className={`pill ${live ? "pill-good" : "pill-muted"}`}
          title={live ? "Summaries are written by a live LLM" : "Summaries use the offline demo generator"}
          data-testid="llm-mode"
        >
          <span className="dot" /> {live ? "Live LLM" : "Demo mode · mock LLM"}
        </span>
      )}
    </header>
  );
}
