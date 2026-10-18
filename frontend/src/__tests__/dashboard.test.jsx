import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Dashboard from "../components/Dashboard.jsx";
import { donutSegments, stackWidths, dateRange, titleCase } from "../utils/format.js";
import { good, needsReview, partial, phone } from "./fixtures.js";

describe("Dashboard with real API output (headphones, evidence-backed)", () => {
  beforeEach(() => render(<Dashboard results={good} />));

  it("shows the product overview", () => {
    const o = screen.getByTestId("overview");
    expect(within(o).getByText(/AuraBeat X1/)).toBeInTheDocument();
    expect(screen.getByTestId("total-reviews")).toHaveTextContent("67");
    expect(within(o).getByText(/3\.48/)).toBeInTheDocument();
  });

  it("shows sentiment percentages and overall label from the data", () => {
    expect(screen.getByTestId("pct-positive")).toHaveTextContent("58.2%");
    expect(screen.getByTestId("pct-neutral")).toHaveTextContent("17.9%");
    expect(screen.getByTestId("pct-negative")).toHaveTextContent("23.9%");
    expect(screen.getByTestId("overall")).toHaveTextContent("Mostly Positive");
  });

  it("lists the most discussed aspects and reveals example quotes on click", async () => {
    const box = screen.getByTestId("aspects");
    const rows = within(box).getAllByRole("button");
    expect(rows[0]).toHaveAccessibleName(/Sound: 13 positive/);
    expect(within(box).getByRole("button", { name: /Microphone: 1 positive, 2 neutral, 7 negative/ })).toBeInTheDocument();
    await userEvent.click(within(box).getByRole("button", { name: /Microphone/ }));
    expect(within(box).getByText("What people dislike")).toBeInTheDocument();
    expect(within(box).getAllByText(/“.*mic.*”/i).length).toBeGreaterThan(0);
  });

  it("renders pros, cons and recurring issues", () => {
    expect(within(screen.getByTestId("pros")).getByText(/Sound: 13 positive/)).toBeInTheDocument();
    expect(within(screen.getByTestId("cons")).getByText(/Microphone: 7 negative/)).toBeInTheDocument();
    const issues = within(screen.getByTestId("issues"));
    expect(issues.getByText("Microphone")).toBeInTheDocument();
    expect(issues.getByText("7 complaints")).toBeInTheDocument();
  });

  it("shows recurring strengths as their own section, next to recurring issues", () => {
    const box = within(screen.getByTestId("strengths"));
    expect(box.getByText("Recurring strengths")).toBeInTheDocument();
    expect(box.getByText("Sound")).toBeInTheDocument();
    expect(box.getByText("13 praises")).toBeInTheDocument();
    expect(box.getAllByText(/of reviews that discuss it are positive/).length).toBeGreaterThan(0);
    expect(box.getByText(/Sound was great at first/)).toBeInTheDocument();            // typical phrase (theme)
    // issues keep their own wording
    expect(within(screen.getByTestId("issues")).getAllByText(/of reviews that discuss it are negative/).length).toBeGreaterThan(0);
    expect(within(screen.getByTestId("issues")).getByText("7 complaints")).toBeInTheDocument();
  });

  it("shows the AI summary with a demo-mode label", () => {
    const s = screen.getByTestId("summary");
    expect(within(s).getByText("Demo summary")).toBeInTheDocument();
    expect(within(s).getByText(/Customers are mostly positive about AuraBeat/)).toBeInTheDocument();
  });

  it("shows an Evidence-backed verdict with score and all checks", () => {
    expect(screen.getByTestId("verdict")).toHaveTextContent("Evidence-backed");
    expect(screen.getByTestId("score")).toHaveTextContent("100/100");
    const v = within(screen.getByTestId("validation"));
    expect(v.getAllByRole("listitem").length).toBeGreaterThanOrEqual(6);
    expect(v.getByText(/Every statement in the summary is supported/)).toBeInTheDocument();
  });
});

describe("Needs Review summary (contradicting the data)", () => {
  it("flags contradicted claims prominently", async () => {
    render(<Dashboard results={needsReview} />);
    expect(screen.getByTestId("verdict")).toHaveTextContent("Needs Review");
    expect(Number(screen.getByTestId("score").textContent.split("/")[0])).toBeLessThan(75);
    const claims = within(screen.getByTestId("claims"));
    expect(claims.getAllByText("Contradicted").length).toBeGreaterThan(0);
    expect(claims.getByText(/Crystal-clear microphone/)).toBeInTheDocument();
    expect(claims.getByText("Unverified")).toBeInTheDocument();
    const v = within(screen.getByTestId("validation"));
    expect(v.getAllByText(/conflict with the data|not backed by the data|ignores a major/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^✕$/).length).toBeGreaterThan(0);          // failed checks are marked
  });

  it("can expand to show every checked statement", async () => {
    render(<Dashboard results={needsReview} />);
    const before = within(screen.getByTestId("claims")).getAllByRole("listitem").length;
    await userEvent.click(screen.getByRole("button", { name: /Show all/ }));
    expect(within(screen.getByTestId("claims")).getAllByRole("listitem").length).toBeGreaterThan(before);
  });
});

describe("Partial results when the LLM failed", () => {
  it("still shows NLP results and explains the missing summary", () => {
    render(<Dashboard results={partial} />);
    const s = screen.getByTestId("summary");
    expect(within(s).getByText("Unavailable")).toBeInTheDocument();
    expect(within(s).getByText(/could not be reached/)).toBeInTheDocument();
    expect(screen.getByTestId("validation")).toHaveTextContent("Not run");
    expect(screen.getByTestId("sentiment")).toBeInTheDocument();
    // pros/cons fall back to data-derived lists
    expect(within(screen.getByTestId("cons")).getByText(/Microphone \(7 negative mentions\)/)).toBeInTheDocument();
  });
});

describe("Other product", () => {
  it("lists strengths even when the summary is missing (LLM failed)", () => {
    render(<Dashboard results={partial} />);
    expect(within(screen.getByTestId("strengths")).getByText("13 praises")).toBeInTheDocument();
  });

  it("says so when nothing recurs", () => {
    render(<Dashboard results={{ ...good, recurring_strengths: [], recurring_issues: [] }} />);
    expect(within(screen.getByTestId("strengths")).getByText(/No praise recurs/)).toBeInTheDocument();
    expect(within(screen.getByTestId("issues")).getByText(/No complaint recurs/)).toBeInTheDocument();
  });

  it("renders a product with no recurring issues", () => {
    render(<Dashboard results={phone} />);
    expect(within(screen.getByTestId("overview")).getByText(/Nova S5/)).toBeInTheDocument();
    expect(within(screen.getByTestId("issues")).getByText(/No complaint recurs/)).toBeInTheDocument();
  });
});

describe("format helpers", () => {
  it("donut segments add up to the full circle", () => {
    const segs = donutSegments([58, 18, 24]);
    const total = segs.reduce((a, s) => a + s.length, 0);
    expect(total).toBeCloseTo(2 * Math.PI * 42, 5);
    expect(segs[1].offset).toBeCloseTo(-segs[0].length, 5);
  });
  it("stack widths are proportional to the largest aspect", () => {
    const w = stackWidths({ positive: 5, neutral: 0, negative: 5 }, 20);
    expect(w).toEqual({ positive: 25, neutral: 0, negative: 25 });
    expect(stackWidths({ positive: 1, neutral: 0, negative: 0 }, 0).positive).toBe(0);
  });
  it("formats dates and titles", () => {
    expect(dateRange(null, null)).toBe("Not available");
    expect(dateRange("2024-01-07", "2025-12-28")).toBe("Jan 2024 – Dec 2025");
    expect(titleCase("noise cancellation")).toBe("Noise cancellation");
  });
});
