import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import DocumentsPage from "../src/app/documents/page";
import { documentsApi, type Document, type QuarantineItem } from "../src/lib/documents";
import { ApiError } from "../src/lib/http";

/**
 * The documents surface: intake, the document list, and the quarantine queue.
 *
 * The assertions that matter here are the sensitivity ones. #143 removed a
 * server-side default of `0` — *public* — because omitting the field published a
 * document at the widest visibility in the system. A form that pre-selects a level
 * would reintroduce exactly that one layer up, and it would look like a courtesy
 * while doing it, so it is tested directly rather than left to review.
 */

jest.mock("../src/lib/documents", () => {
  const actual = jest.requireActual("../src/lib/documents");
  return {
    ...actual,
    documentsApi: {
      list: jest.fn(),
      get: jest.fn(),
      intake: jest.fn(),
      quarantine: jest.fn(),
    },
  };
});

const api = documentsApi as jest.Mocked<typeof documentsApi>;

const DOC: Document = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Q3 Board Transcript",
  doc_type: "transcript",
  source_uri: null,
  sensitivity: 1,
  authored_at: null,
  ingested_at: "2026-08-01T09:00:00Z",
};

const QUARANTINED: QuarantineItem = {
  id: "22222222-2222-2222-2222-222222222222",
  workspace_id: "33333333-3333-3333-3333-333333333333",
  document_id: DOC.id,
  chunk_id: null,
  source: "Priya Nair",
  relation: "APPROVED",
  target: "Pricing Model B",
  quote: "We should probably look at the pricing again next quarter.",
  confidence: 0.62,
  reason: "quote_not_found",
  detail: "The quote was not located verbatim in the source chunk.",
  provider: "ollama",
  extractor_model: "qwen2.5:7b",
  created_at: "2026-08-01T09:05:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  api.list.mockResolvedValue([DOC]);
  api.quarantine.mockResolvedValue([]);
});

async function openIntake() {
  render(<DocumentsPage />);
  await waitFor(() => expect(screen.getByText("Q3 Board Transcript")).toBeInTheDocument());
  fireEvent.click(screen.getAllByRole("button", { name: /ingest document/i })[0]);
  return screen.getByLabelText(/classification/i) as HTMLSelectElement;
}

describe("the sensitivity control", () => {
  it("pre-selects nothing", async () => {
    const select = await openIntake();
    // The empty string is "not chosen" and is deliberately distinct from level 0.
    // A default of 0 here would be the fail-open behaviour #143 removed server-side.
    expect(select.value).toBe("");
    expect(screen.getByRole("option", { name: /choose a classification/i })).toBeInTheDocument();
  });

  it("will not submit until a classification is chosen", async () => {
    const select = await openIntake();
    fireEvent.change(screen.getByLabelText(/^title$/i), { target: { value: "Comp Review" } });
    fireEvent.change(screen.getByLabelText(/source text/i), { target: { value: "Salary bands." } });

    const submit = screen.getByRole("button", { name: /^ingest$/i });
    expect(submit).toBeDisabled();

    fireEvent.change(select, { target: { value: "3" } });
    expect(submit).toBeEnabled();
  });

  it("does not offer level 4, which intake refuses", async () => {
    // `4 restricted` is reserved pending the policy in #143. Offering it would
    // invite a choice the API answers with a 422.
    const select = await openIntake();
    const options = within(select).getAllByRole("option").map((o) => o.textContent ?? "");
    expect(options.some((t) => /Restricted/.test(t))).toBe(false);
    expect(options.filter((t) => /^\d/.test(t))).toHaveLength(4);
  });
});

describe("when the server refuses the filing", () => {
  it("shows the refusal verbatim and does not retry at a lower level", async () => {
    // The 403 detail names the level this caller may actually use. Paraphrasing it
    // to "permission denied" would discard the only actionable part.
    api.intake.mockRejectedValue(
      new ApiError(403, "forbidden", "Sensitivity 3 is above your clearance (1). You may file at level 1 or below."),
    );

    const select = await openIntake();
    fireEvent.change(screen.getByLabelText(/^title$/i), { target: { value: "Comp Review" } });
    fireEvent.change(screen.getByLabelText(/source text/i), { target: { value: "Salary bands." } });
    fireEvent.change(select, { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /^ingest$/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/above your clearance \(1\)/));
    // Exactly one attempt: a silent re-file at a lower level would tell the user
    // their document is protected at a level it is not.
    expect(api.intake).toHaveBeenCalledTimes(1);
    expect(api.intake.mock.calls[0][0].sensitivity).toBe(3);
  });

  it("reports a duplicate as recognition, not as an error", async () => {
    api.intake.mockRejectedValue(
      new ApiError(409, "conflict", "Document with content hash 'abc' already exists in this workspace"),
    );

    const select = await openIntake();
    fireEvent.change(screen.getByLabelText(/^title$/i), { target: { value: "Same Memo" } });
    fireEvent.change(screen.getByLabelText(/source text/i), { target: { value: "Identical body." } });
    fireEvent.change(select, { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: /^ingest$/i }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/already in memory/i));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("the quarantine queue", () => {
  it("renders the refused quote and its provenance, not a count", async () => {
    // A count would summarise the one thing this product refuses to summarise.
    api.quarantine.mockResolvedValue([QUARANTINED]);
    render(<DocumentsPage />);

    fireEvent.click(await screen.findByRole("tab", { name: /quarantine/i }));

    expect(await screen.findByText(/We should probably look at the pricing again next quarter/)).toBeInTheDocument();
    expect(screen.getByText("Quote not found in the source")).toBeInTheDocument();
    expect(screen.getByText(/qwen2\.5:7b/)).toBeInTheDocument();
  });

  it("says an empty queue is a result, not an absence of checking", async () => {
    render(<DocumentsPage />);
    fireEvent.click(await screen.findByRole("tab", { name: /quarantine/i }));
    expect(await screen.findByText("Nothing quarantined")).toBeInTheDocument();
  });
});

describe("the document list", () => {
  it("offers the action that ends the empty state", async () => {
    api.list.mockResolvedValue([]);
    render(<DocumentsPage />);
    await waitFor(() => expect(screen.getByText("No documents yet")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: /ingest document/i }).length).toBeGreaterThan(1);
  });

  it("states a failed load once rather than rendering an empty workspace", async () => {
    api.list.mockRejectedValue(new ApiError(500, "internal", "Server error."));
    render(<DocumentsPage />);
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
  });

  it("shows a newly ingested document without a refetch", async () => {
    const created: Document = { ...DOC, id: "44444444-4444-4444-4444-444444444444", title: "Freshly Ingested" };
    api.intake.mockResolvedValue(created);

    const select = await openIntake();
    fireEvent.change(screen.getByLabelText(/^title$/i), { target: { value: "Freshly Ingested" } });
    fireEvent.change(screen.getByLabelText(/source text/i), { target: { value: "Body." } });
    fireEvent.change(select, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: /^ingest$/i }));

    await waitFor(() => expect(screen.getByText("Freshly Ingested")).toBeInTheDocument());
    expect(api.list).toHaveBeenCalledTimes(1);
  });
});
