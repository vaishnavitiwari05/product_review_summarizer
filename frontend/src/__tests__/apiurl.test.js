describe("API base URL modes", () => {
  afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

  it("empty VITE_API_URL means same-origin (used behind nginx / the dev proxy)", async () => {
    vi.stubEnv("VITE_API_URL", "");
    vi.resetModules();
    const { API_URL, api } = await import("../api.js");
    expect(API_URL).toBe("");
    const seen = [];
    globalThis.fetch = vi.fn(async (url) => { seen.push(url); throw new TypeError("down"); });
    const err = await api.health().catch((e) => e);
    expect(seen[0]).toBe("/health");                                   // relative URL
    expect(err.message).toMatch(/Cannot reach the analysis server\./);  // no "at http://..."
  });

  it("a set VITE_API_URL is used, trailing slash stripped", async () => {
    vi.stubEnv("VITE_API_URL", "http://api.example.com/");
    vi.resetModules();
    const { API_URL } = await import("../api.js");
    expect(API_URL).toBe("http://api.example.com");
  });
});
