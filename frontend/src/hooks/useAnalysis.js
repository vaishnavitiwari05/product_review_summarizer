import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api.js";

const MAX_UPLOAD_MB = 25;
const POLL_MS = 700;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const asError = (e) =>
  e instanceof ApiError ? e : new ApiError("unexpected", "Something went wrong. Please try again.");

/**
 * All application state and the flows: load data -> pick product -> analyze (poll) -> results.
 */
export function useAnalysis({ pollMs = POLL_MS } = {}) {
  const [health, setHealth] = useState(null);
  const [products, setProducts] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [upload, setUpload] = useState(null); // last upload/sample summary
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(null); // 'uploading' | 'analyzing' | null
  const [progress, setProgress] = useState({ pct: 0, stage: "" });
  const [error, setError] = useState(null);
  const alive = useRef(true);
  const token = useRef(0); // invalidates in-flight polling when the user switches product

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const loadResults = useCallback(async (productId) => {
    const my = ++token.current;
    try {
      const r = await api.results(productId);
      if (alive.current && my === token.current) setResults(r);
    } catch (e) {
      if (!alive.current || my !== token.current) return;
      setResults(null);
      if (e.code !== "not_analyzed") setError(asError(e));
    }
  }, []);

  const refreshProducts = useCallback(
    async (preferId) => {
      const list = await api.products();
      if (!alive.current) return list;
      setProducts(list);
      const pick = list.find((p) => p.product_id === preferId) || list[0];
      setSelectedId(pick ? pick.product_id : "");
      setResults(null);
      if (pick?.analyzed) await loadResults(pick.product_id);
      return list;
    },
    [loadResults]
  );

  // initial load
  useEffect(() => {
    (async () => {
      try {
        setHealth(await api.health());
        await refreshProducts();
      } catch (e) {
        if (alive.current) setError(asError(e));
      }
    })();
  }, [refreshProducts]);

  const ingest = useCallback(
    async (fn) => {
      setError(null);
      setBusy("uploading");
      setResults(null);
      try {
        const up = await fn();
        if (!alive.current) return;
        setUpload(up);
        setProducts(up.products);
        // select a product from the file that was just loaded (not an older one that sorts first)
        const firstId = up.uploaded_product_ids?.[0] ?? up.products[0]?.product_id ?? "";
        setSelectedId(firstId);
      } catch (e) {
        if (alive.current) setError(asError(e));
      } finally {
        if (alive.current) setBusy(null);
      }
    },
    []
  );

  const uploadFile = useCallback(
    (file) => {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".csv")) {
        setError(new ApiError("unsupported_file", "Please choose a .csv file. Other file types are not supported."));
        return;
      }
      if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        setError(new ApiError("file_too_large", `That file is larger than the ${MAX_UPLOAD_MB} MB limit.`));
        return;
      }
      return ingest(() => api.uploadCsv(file));
    },
    [ingest]
  );

  const useSample = useCallback(() => ingest(() => api.loadSample()), [ingest]);

  const selectProduct = useCallback(
    (id) => {
      token.current++;
      setSelectedId(id);
      setResults(null);
      setError(null);
      const p = products.find((x) => x.product_id === id);
      if (p?.analyzed) loadResults(id);
    },
    [products, loadResults]
  );

  const analyze = useCallback(async () => {
    if (!selectedId) return;
    const id = selectedId;
    const my = ++token.current;
    setError(null);
    setResults(null);
    setBusy("analyzing");
    setProgress({ pct: 2, stage: "Starting analysis" });
    try {
      const run = await api.startAnalysis(id);
      let status = run;
      while (alive.current && my === token.current && !["done", "failed"].includes(status.status)) {
        setProgress({ pct: status.progress ?? 0, stage: status.stage || "Working" });
        await sleep(pollMs);
        status = await api.runStatus(run.run_id);
      }
      if (!alive.current || my !== token.current) return;
      setProgress({ pct: status.progress ?? 100, stage: status.stage });
      // partial results (e.g. LLM failed) are still available
      await loadResults(id);
      if (status.status === "failed" && status.error) {
        setError(new ApiError(status.error.error, status.error.message, 0, status.error.details));
      }
      const list = await api.products();
      if (alive.current) setProducts(list);
    } catch (e) {
      if (alive.current) setError(asError(e));
    } finally {
      if (alive.current) setBusy(null);
    }
  }, [selectedId, loadResults, pollMs]);

  return {
    health, products, selectedId, upload, results, busy, progress, error,
    dismissError: () => setError(null),
    uploadFile, useSample, selectProduct, analyze,
  };
}
