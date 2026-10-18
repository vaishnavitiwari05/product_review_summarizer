import ProductOverview from "./ProductOverview.jsx";
import SentimentCard from "./SentimentCard.jsx";
import SummaryCard from "./SummaryCard.jsx";
import ValidationCard from "./ValidationCard.jsx";
import AspectChart from "./AspectChart.jsx";
import ProsCons from "./ProsCons.jsx";

export default function Dashboard({ results }) {
  const llmError = results.analysis?.run?.status === "failed" ? results.analysis.run.error : null;
  return (
    <div className="dashboard" data-testid="dashboard">
      <div className="span-2"><ProductOverview product={results.product} /></div>
      <SentimentCard sentiment={results.sentiment} />
      <SummaryCard summary={results.summary} llmError={llmError} />
      <AspectChart aspects={results.aspects} />
      <ValidationCard validation={results.validation} />
      <ProsCons results={results} />
    </div>
  );
}
