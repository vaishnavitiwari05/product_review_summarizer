import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App.jsx";
import { good, health, products, upload, mockFetch } from "./fixtures.js";

const unanalyzed = { products: products.products.map((p) => ({ ...p, analyzed: false })) };
const base = { "GET /health": health };

const runBody = (over = {}) => ({ run_id: "r1", product_id: "P001", status: "queued", stage: "Queued", progress: 0, error: null, ...over });

describe("App flows", () => {
  it("shows the empty state and demo-mode pill on first load", async () => {
    mockFetch({ ...base, "GET /products": { products: [] } });
    render(<App pollMs={1} />);
    expect(await screen.findByTestId("empty-state")).toHaveTextContent(/Upload a CSV/);
    expect(await screen.findByTestId("llm-mode")).toHaveTextContent(/Demo mode/);
    expect(screen.getByRole("button", { name: /Analyze/ })).toBeDisabled();
  });

  it("loads sample data, analyzes with a progress indicator, then shows the dashboard", async () => {
    let polls = 0;
    const calls = mockFetch({
      ...base,
      "GET /products": { products: [] },
      "POST /sample": upload,
      "POST /analyze": { status: 202, body: runBody() },
      "GET /analyze/r1": () => {
        polls += 1;
        return polls < 4 ? runBody({ status: "running", stage: "Extracting aspects", progress: 40 })
                         : runBody({ status: "done", stage: "Complete", progress: 100 });
      },
      "GET /results/P001": good,
      "GET /results/*": good,
    });
    render(<App pollMs={40} />);
    await screen.findByTestId("empty-state");

    await userEvent.click(screen.getByRole("button", { name: /Try sample data/ }));
    const summary = await screen.findByTestId("upload-summary");
    expect(summary).toHaveTextContent("103");            // valid reviews
    expect(summary).toHaveTextContent("Duplicates removed");
    const select = screen.getByLabelText("Product");
    expect(within(select).getAllByRole("option")).toHaveLength(2);

    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByTestId("progress")).toHaveTextContent(/Extracting aspects|Starting|Queued/);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow");
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument();
    expect(screen.queryByTestId("progress")).not.toBeInTheDocument();
    expect(screen.getByTestId("verdict")).toHaveTextContent("Evidence-backed");
    expect(calls).toContain("POST /analyze");
  });

  it("auto-loads results for an already analyzed product", async () => {
    mockFetch({ ...base, "GET /products": products, "GET /results/P001": good });
    render(<App pollMs={1} />);
    expect(await screen.findByTestId("dashboard")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-analyze" })).toBeEnabled();
  });

  it("switches product and clears stale results", async () => {
    mockFetch({ ...base, "GET /products": { products: [products.products[0], { ...products.products[1], analyzed: false }] },
      "GET /results/P001": good });
    render(<App pollMs={1} />);
    await screen.findByTestId("dashboard");
    await userEvent.selectOptions(screen.getByLabelText("Product"), "P002");
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument();
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/Ready to analyze/);
  });

  it("uploads a CSV file through the file input", async () => {
    const calls = mockFetch({ ...base, "GET /products": { products: [] }, "POST /upload": upload });
    render(<App pollMs={1} />);
    await screen.findByTestId("empty-state");
    const file = new File(["review\nnice"], "mine.csv", { type: "text/csv" });
    await userEvent.upload(screen.getByTestId("file-input"), file);
    await screen.findByTestId("upload-summary");
    expect(calls).toContain("POST /upload");
  });
});

describe("Selecting after upload", () => {
  it("selects the product from the file just uploaded, not an older one that sorts first", async () => {
    const newUpload = { ...upload, filename: "widgets.csv", uploaded_product_ids: ["W1"],
      products: [...upload.products, { product_id: "W1", product_name: "Zeta Widget", review_count: 8, avg_rating: null, analyzed: false }] };
    mockFetch({ ...base, "GET /products": { products: [] }, "POST /upload": newUpload });
    render(<App pollMs={1} />);
    await screen.findByTestId("empty-state");
    await userEvent.upload(screen.getByTestId("file-input"), new File(["review\nx"], "widgets.csv"));
    await screen.findByTestId("upload-summary");
    expect(screen.getByLabelText("Product")).toHaveValue("W1");
    expect(screen.getByTestId("upload-summary")).toHaveTextContent("Products in file1");
  });
});

describe("App error handling", () => {
  it("rejects non-CSV files on the client, without calling the server", async () => {
    const calls = mockFetch({ ...base, "GET /products": { products: [] } });
    render(<App pollMs={1} />);
    await screen.findByTestId("empty-state");
    const input = screen.getByTestId("file-input");
    await userEvent.upload(input, new File(["x"], "data.xlsx"), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/choose a \.csv file/);
    expect(calls).not.toContain("POST /upload");
  });

  it("shows the server's friendly message and a hint for a CSV with no review column", async () => {
    mockFetch({ ...base, "GET /products": { products: [] },
      "POST /upload": { status: 400, body: { error: "missing_columns", message: "Required column(s) missing: review. Found columns: product, rating." } } });
    render(<App pollMs={1} />);
    await screen.findByTestId("empty-state");
    await userEvent.upload(screen.getByTestId("file-input"), new File(["product,rating\nA,5"], "bad.csv"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Required column\(s\) missing: review/);
    expect(alert).toHaveTextContent(/header named “review”/);
    await userEvent.click(within(alert).getByLabelText("Dismiss error"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("explains a missing LLM API key with how to fix it", async () => {
    mockFetch({ ...base, "GET /products": unanalyzed,
      "POST /analyze": { status: 400, body: { error: "llm_api_key_missing", message: "No LLM API key configured. Set LLM_API_KEY in backend/.env, or set USE_MOCK_LLM=true to use the offline demo mode." } } });
    render(<App pollMs={1} />);
    await screen.findByRole("button", { name: "Analyze" });
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/No LLM API key configured/);
    expect(alert).toHaveTextContent(/USE_MOCK_LLM=true/);
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();     // can retry
  });

  it("tells the user when the backend is unreachable", async () => {
    globalThis.fetch = vi.fn(async () => { throw new TypeError("Failed to fetch"); });
    render(<App pollMs={1} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Cannot reach the analysis server/);
    expect(alert).toHaveTextContent(/uvicorn/);
  });

  it("keeps the NLP dashboard and shows the LLM error when the summary step fails", async () => {
    const { partial } = await import("./fixtures.js");
    mockFetch({ ...base, "GET /products": unanalyzed,
      "POST /analyze": { status: 202, body: runBody() },
      "GET /analyze/r1": runBody({ status: "failed", stage: "Failed", progress: 72,
        error: { error: "llm_unavailable", message: "The LLM service could not be reached after 3 attempts." } }),
      "GET /results/*": partial });
    render(<App pollMs={1} />);
    await screen.findByRole("button", { name: "Analyze" });
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be reached/);
    await waitFor(() => expect(screen.getByTestId("dashboard")).toBeInTheDocument());
    expect(screen.getByTestId("summary")).toHaveTextContent("Unavailable");
    expect(screen.getByTestId("sentiment")).toBeInTheDocument();
  });

  it("disables controls while analyzing", async () => {
    mockFetch({ ...base, "GET /products": unanalyzed, "POST /analyze": { status: 202, body: runBody() },
      "GET /analyze/r1": runBody({ status: "running", stage: "Analysing sentiment", progress: 15 }) });
    render(<App pollMs={5} />);
    await screen.findByRole("button", { name: "Analyze" });
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByTestId("progress");
    expect(screen.getByRole("button", { name: /Analyzing/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Upload CSV/ })).toBeDisabled();
    expect(screen.getByLabelText("Product")).toBeDisabled();
  });
});
