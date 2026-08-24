import { render, screen, waitFor } from "@testing-library/react";
import { MaterialList } from "../src/app/meetings/material-list";
import { meetingsApi, type MeetingMaterial } from "../src/lib/meetings";
import type { Document } from "../src/lib/documents";
import { ApiError } from "../src/lib/http";

/**
 * A meeting's material list, and the disclosure it makes (ADR-018).
 *
 * The load-bearing assertions here are the *negative* ones. This surface is allowed to
 * say how many documents a reader may not see and is allowed to say nothing else, so
 * the tests that matter check what never reaches the DOM.
 *
 * The count is asserted through `FieldValue`'s shared wording ("N withheld"), which this
 * surface and the document version chain both render. Pinning that phrase is deliberate:
 * it is the product's one vocabulary for this disclosure, and a surface drifting to its
 * own phrasing is how two screens come to tell a reader different things about the same
 * fact. The sentence AFTER it is this component's own and is asserted separately.
 */

jest.mock("../src/lib/meetings", () => {
  const actual = jest.requireActual("../src/lib/meetings");
  return { ...actual, meetingsApi: { material: jest.fn() } };
});

const api = meetingsApi as unknown as { material: jest.Mock };

function doc(over: Partial<Document> = {}): Document {
  return {
    id: "d-1",
    title: "Vendor terms — Northwind",
    doc_type: "contract",
    source_uri: null,
    sensitivity: 1,
    authored_at: null,
    ingested_at: "2026-08-01T09:00:00Z",
    revision: 1,
    superseded_by_id: null,
    ...over,
  };
}

function material(over: Partial<MeetingMaterial> = {}): MeetingMaterial {
  return { documents: [doc()], withheld: 0, ...over };
}

beforeEach(() => jest.clearAllMocks());

describe("what the reader may see", () => {
  it("lists assigned material", async () => {
    api.material.mockResolvedValue(material());
    render(<MaterialList meetingId="m-1" />);
    expect(await screen.findByText("Vendor terms — Northwind")).toBeInTheDocument();
  });

  it("badges a revision above the first, and not v1", async () => {
    api.material.mockResolvedValue(
      material({ documents: [doc({ revision: 3, title: "Revised terms" })] }),
    );
    render(<MaterialList meetingId="m-1" />);
    expect(await screen.findByText("v3")).toBeInTheDocument();
    expect(screen.queryByText("v1")).not.toBeInTheDocument();
  });
});

describe("what the reader may not see", () => {
  it("renders a withheld count", async () => {
    api.material.mockResolvedValue(material({ withheld: 2 }));
    render(<MaterialList meetingId="m-1" />);
    // "2 withheld" is `FieldValue`'s shared wording, rendered as one node.
    await waitFor(() => expect(screen.getByText(/2 withheld/)).toBeInTheDocument());
    expect(screen.getByText(/above your clearance/i)).toBeInTheDocument();
  });

  it("says the list is not everything, so it is not read as complete", async () => {
    // The whole reason this surface counts instead of erasing: someone prepares from it.
    api.material.mockResolvedValue(material({ withheld: 1 }));
    render(<MaterialList meetingId="m-1" />);
    expect(await screen.findByText(/not everything the board holds/i)).toBeInTheDocument();
  });

  it("distinguishes an empty meeting from a fully withheld one", async () => {
    // Both have zero documents. Only the count separates "nothing here" from
    // "something here you may not see" — conflating them is the ADR-018 failure.
    api.material.mockResolvedValue({ documents: [], withheld: 0 });
    const { unmount } = render(<MaterialList meetingId="m-1" />);
    expect(await screen.findByText(/No material has been assigned/i)).toBeInTheDocument();
    unmount();

    api.material.mockResolvedValue({ documents: [], withheld: 3 });
    render(<MaterialList meetingId="m-2" />);
    expect(await screen.findByText(/above your clearance/i)).toBeInTheDocument();
    expect(screen.queryByText(/No material has been assigned/i)).not.toBeInTheDocument();
  });

  it("never renders a title handed to it in a withheld slot", async () => {
    // The server sends no rows for withheld material, only the integer — so a payload
    // carrying one is malformed, and the component must not render it anyway. This is
    // the assertion that would have caught `superseded_by_id` leaking a withheld id.
    // Cast, not `@ts-expect-error`: the mock is typed loosely enough that the extra
    // field is not a type error, and an unused directive fails `tsc --noEmit`.
    api.material.mockResolvedValue({
      documents: [doc()],
      withheld: 1,
      withheld_documents: [doc({ id: "secret", title: "SECRET_BOARD_COMP_MEMO" })],
    } as unknown as MeetingMaterial);
    render(<MaterialList meetingId="m-1" />);
    await screen.findByText("Vendor terms — Northwind");
    expect(screen.queryByText(/SECRET_BOARD_COMP_MEMO/)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("secret");
  });
});

describe("failure states", () => {
  it("reports a load failure instead of rendering an empty list", async () => {
    // An error rendered as "no material" would tell a reader the meeting has none.
    api.material.mockRejectedValue(new ApiError(500, "server_error", "Boom."));
    render(<MaterialList meetingId="m-1" />);
    expect(await screen.findByRole("status")).toHaveTextContent(/could not be loaded/i);
    expect(screen.queryByText(/No material has been assigned/i)).not.toBeInTheDocument();
  });
});
