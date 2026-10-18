import Header from "./components/Header.jsx";
import ControlBar from "./components/ControlBar.jsx";
import UploadSummary from "./components/UploadSummary.jsx";
import ProgressPanel from "./components/ProgressPanel.jsx";
import ErrorBanner from "./components/ErrorBanner.jsx";
import EmptyState from "./components/EmptyState.jsx";
import Dashboard from "./components/Dashboard.jsx";
import { useAnalysis } from "./hooks/useAnalysis.js";

export default function App({ pollMs }) {
  const a = useAnalysis({ pollMs });
  const selected = a.products.find((p) => p.product_id === a.selectedId);
  return (
    <div className="app">
      <Header health={a.health} />
      <main className="container">
        <ControlBar
          products={a.products}
          selectedId={a.selectedId}
          busy={a.busy}
          onUpload={a.uploadFile}
          onSample={a.useSample}
          onSelect={a.selectProduct}
          onAnalyze={a.analyze}
        />
        <ErrorBanner error={a.error} onDismiss={a.dismissError} />
        {a.busy === "uploading" && <p className="muted center" role="status">Reading and cleaning your file…</p>}
        <UploadSummary upload={a.upload} />
        {a.busy === "analyzing" && <ProgressPanel progress={a.progress} />}
        {a.results && a.busy !== "analyzing" ? (
          <Dashboard results={a.results} />
        ) : (
          a.busy !== "analyzing" && <EmptyState hasProducts={a.products.length > 0} analyzed={!!selected?.analyzed} />
        )}
      </main>
      <footer className="footer">
        Insights are generated from the uploaded reviews. Statements are checked against the review statistics, not guaranteed.
      </footer>
    </div>
  );
}
