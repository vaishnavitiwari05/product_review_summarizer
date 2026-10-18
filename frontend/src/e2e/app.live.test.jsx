// The real <App/> (real hook, real components) against the real backend, in jsdom.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App.jsx";

describe("App against the live backend", () => {
  it("sample data -> analyze -> live progress -> dashboard -> second product", async () => {
    render(<App pollMs={60} />);

    // first load talks to /health and /products
    expect(await screen.findByTestId("llm-mode")).toHaveTextContent(/Demo mode/);
    await userEvent.click(await screen.findByRole("button", { name: /Try sample data/ }));

    const upload = await screen.findByTestId("upload-summary");
    expect(upload).toHaveTextContent("103");
    const select = screen.getByLabelText("Product");
    expect(within(select).getAllByRole("option")).toHaveLength(2);

    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByTestId("progress")).toBeInTheDocument();
    const dash = await screen.findByTestId("dashboard", {}, { timeout: 30000 });

    expect(within(dash).getByTestId("overview")).toHaveTextContent(/AuraBeat X1/);
    expect(within(dash).getByTestId("total-reviews")).toHaveTextContent("67");
    const pcts = ["positive", "neutral", "negative"].map((k) => parseFloat(within(dash).getByTestId(`pct-${k}`).textContent));
    expect(pcts.reduce((a, b) => a + b, 0)).toBeGreaterThan(99.5);
    expect(within(dash).getByTestId("overall")).toHaveTextContent(/Positive|Mixed|Negative/);
    expect(within(dash).getByRole("button", { name: /Microphone: \d+ positive/ })).toBeInTheDocument();
    expect(within(dash).getByTestId("cons")).toHaveTextContent(/Microphone/);
    expect(within(dash).getByTestId("summary")).toHaveTextContent(/AuraBeat/);
    expect(within(dash).getByTestId("verdict")).toHaveTextContent("Evidence-backed");

    // switch to the phone: stale headphone results disappear, analyze works again
    await userEvent.selectOptions(screen.getByLabelText("Product"), "P002");
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await waitFor(() => expect(within(screen.getByTestId("overview")).getByText(/Nova S5/)).toBeInTheDocument(),
      { timeout: 30000 });

    // headphones are remembered as analyzed (loaded from the database, no re-run)
    await userEvent.selectOptions(screen.getByLabelText("Product"), "P001");
    expect(await screen.findByTestId("dashboard")).toHaveTextContent(/AuraBeat/);
    expect(screen.getByRole("button", { name: "Re-analyze" })).toBeEnabled();
  });

  it("shows the friendly server error when the file is rejected", async () => {
    render(<App pollMs={60} />);
    await screen.findByTestId("llm-mode");
    // a File built in jsdom cannot be sent by Node's fetch, so use the client-side guard here;
    // real multipart rejection is covered in api.live.test.js
    const input = screen.getByTestId("file-input");
    await userEvent.upload(input, new File(["x"], "notes.txt"), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/\.csv/);
  });
});
