import good from "../fixtures/results.good.json";
import phone from "../fixtures/results.phone.json";
import needsReview from "../fixtures/results.needs_review.json";
import partial from "../fixtures/results.partial.json";
import upload from "../fixtures/upload.sample.json";
import products from "../fixtures/products.json";
import health from "../fixtures/health.json";

export { good, phone, needsReview, partial, upload, products, health };

/** Tiny fetch mock: routes = { "GET /products": body | (init)=>body | Response-like } */
export function mockFetch(routes) {
  const calls = [];
  globalThis.fetch = vi.fn(async (url, init = {}) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");
    const key = `${init.method || "GET"} ${path}`;
    calls.push(key);
    let handler = routes[key];
    if (handler === undefined) {
      const k = Object.keys(routes).find((r) => r.endsWith("*") && key.startsWith(r.slice(0, -1)));
      handler = k ? routes[k] : { status: 404, body: { error: "http_error", message: `no mock for ${key}` } };
    }
    if (typeof handler === "function") handler = handler(init, key);
    if (handler instanceof Error) throw handler;
    const { status = 200, body = handler } = handler && handler.body !== undefined ? handler : { body: handler };
    return { ok: status < 400, status, json: async () => body };
  });
  return calls;
}
