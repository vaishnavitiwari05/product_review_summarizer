// @vitest-environment node
// Talks to the real backend with the real api.js client (native fetch / FormData / File).
import { api, ApiError, API_URL } from "../api.js";

const csv = (text, name = "mine.csv") => new File([text], name, { type: "text/csv" });

async function runToCompletion(productId) {
  const run = await api.startAnalysis(productId);
  const seen = [];
  let status = run;
  for (let i = 0; i < 200 && !["done", "failed"].includes(status.status); i++) {
    seen.push({ stage: status.stage, progress: status.progress });
    await new Promise((r) => setTimeout(r, 100));
    status = await api.runStatus(run.run_id);
  }
  return { status, seen };
}

describe("live backend via api.js", () => {
  it("is reachable and reports its configuration", async () => {
    const h = await api.health();
    expect(h.status).toBe("ok");
    expect(h.llm_ready).toBe(true);
  });

  it("loads the bundled sample dataset", async () => {
    const up = await api.loadSample();
    expect(up.cleaning.valid_reviews).toBe(103);
    expect(up.cleaning.duplicates_removed).toBe(4);
    const list = await api.products();
    expect(list.map((p) => p.product_id).sort()).toEqual(["P001", "P002"]);
  });

  it("uploads a real multipart CSV (aliases, duplicates, empty rows)", async () => {
    const rows = ["product,review text,stars"];
    for (let i = 0; i < 8; i++) rows.push(`Widget,The battery on this widget is great number ${i},5`);
    rows.push("Widget,The battery on this widget is great number 1,5");        // duplicate
    rows.push("Widget,,4");                                                    // empty
    const up = await api.uploadCsv(csv(rows.join("\n")));
    expect(up.filename).toBe("mine.csv");
    expect(up.cleaning.total_reviews).toBe(10);
    expect(up.cleaning.valid_reviews).toBe(8);
    expect(up.cleaning.duplicates_removed).toBe(1);
    expect(up.uploaded_product_ids).toHaveLength(1);
    const widget = up.products.find((p) => p.product_id === up.uploaded_product_ids[0]);
    expect(widget.product_name).toBe("Widget");
    expect(up.products.length).toBeGreaterThan(1);                 // older products stay listed
  });

  it("returns friendly ApiErrors for bad uploads", async () => {
    const missing = await api.uploadCsv(csv("product,rating\nA,5\n", "bad.csv")).catch((e) => e);
    expect(missing).toBeInstanceOf(ApiError);
    expect(missing.code).toBe("missing_columns");
    expect(missing.message).toMatch(/review/);
    const wrongType = await api.uploadCsv(csv("a,b\n1,2", "data.xlsx")).catch((e) => e);
    expect(wrongType.code).toBe("unsupported_file");
    const empty = await api.uploadCsv(csv("", "empty.csv")).catch((e) => e);
    expect(empty.code).toBe("empty_file");
  });

  it("rejects a file over the server's size limit with 413", async () => {
    const big = "review\n" + "This is a fairly long review sentence about the product. ".repeat(20).concat("\n").repeat(1500);
    expect(big.length).toBeGreaterThan(1024 * 1024);
    const err = await api.uploadCsv(csv(big, "big.csv")).catch((e) => e);
    expect(err.code).toBe("file_too_large");
    expect(err.status).toBe(413);
  });

  it("handles unknown products and not-yet-analyzed products", async () => {
    await api.loadSample();
    expect((await api.startAnalysis("NOPE").catch((e) => e)).code).toBe("product_not_found");
    expect((await api.results("P001").catch((e) => e)).code).toBe("not_analyzed");
    expect((await api.runStatus("nope").catch((e) => e)).code).toBe("run_not_found");
  });

  it("runs a full analysis with progress and returns everything the dashboard needs", async () => {
    await api.loadSample();
    const { status, seen } = await runToCompletion("P001");
    expect(status.status).toBe("done");
    expect(status.progress).toBe(100);
    expect(seen.length).toBeGreaterThan(0);                                   // progress was observable

    const r = await api.results("P001");
    JSON.stringify(r);
    expect(r.product.product_name).toMatch(/AuraBeat/);
    expect(Object.keys(r.sentiment.percentages).sort()).toEqual(["negative", "neutral", "positive"]);
    expect(r.aspects.length).toBeGreaterThan(3);
    expect(r.aspects.every((a) => a.positive + a.neutral + a.negative === a.frequency)).toBe(true);
    expect(r.recurring_issues[0].aspect).toBe("microphone");
    expect(r.summary.mode).toBe("mock");
    expect(r.validation.verdict).toBe("Evidence-backed");
    expect(r.validation.checks.length).toBe(6);
    expect((await api.products()).find((p) => p.product_id === "P001").analyzed).toBe(true);
  });

  it("allows the frontend origin through CORS and blocks others", async () => {
    const pre = (origin) =>
      fetch(`${API_URL}/analyze`, {
        method: "OPTIONS",
        headers: { Origin: origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type" },
      });
    const ok = await pre("http://localhost:5173");
    expect(ok.status).toBe(200);
    expect(ok.headers.get("access-control-allow-origin")).toBe("http://localhost:5173");
    const bad = await pre("http://evil.example");
    expect(bad.headers.get("access-control-allow-origin")).toBeNull();
  });
});
