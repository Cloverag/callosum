import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { PackBuilder } from "../src/app/packs/pack-builder";
import { PackCreateDialog } from "../src/app/packs/pack-create-dialog";
import { PackCard } from "../src/app/packs/pack-card";
import { packsApi, type BoardPack } from "../src/lib/packs";
import { meetingsApi, type Meeting } from "../src/lib/meetings";
import type { Document } from "../src/lib/documents";
import { ApiError } from "../src/lib/http";

/**
 * The pack builder (P5 CP5B).
 *
 * The assertions that matter are about order and honesty: publish must not fire until
 * the confirmation is accepted, must carry the version the server last reported rather
 * than the one the dialog opened with, and nothing here may total the items in a pack.
 */

jest.mock("../src/lib/packs", () => {
  const actual = jest.requireActual("../src/lib/packs");
  return {
    ...actual,
    packsApi: {
      get: jest.fn(),
      create: jest.fn(),
      addItem: jest.fn(),
      removeItem: jest.fn(),
      reorder: jest.fn(),
      publish: jest.fn(),
      supersede: jest.fn(),
    },
  };
});
jest.mock("../src/lib/meetings", () => {
  const actual = jest.requireActual("../src/lib/meetings");
  return { ...actual, meetingsApi: { material: jest.fn() } };
});

const packs = packsApi as unknown as Record<string, jest.Mock>;
const meetings = meetingsApi as unknown as { material: jest.Mock };

function doc(id: string, title: string): Document {
  return {
    id,
    title,
    doc_type: "memo",
    source_uri: null,
    sensitivity: 1,
    authored_at: null,
    ingested_at: "2026-08-01T09:00:00Z",
    revision: 1,
    superseded_by_id: null,
  };
}

function meeting(over: Partial<Meeting> = {}): Meeting {
  return { id: "m-1", title: "Q3 Board", status: "scheduled", ...over } as Meeting;
}

function pack(over: Partial<BoardPack> = {}, itemDocs: string[] = []): BoardPack {
  return {
    id: "p-1",
    meeting_id: "m-1",
    title: "Q3 pre-read",
    status: "draft",
    version_no: 1,
    superseded_by_id: null,
    published_at: null,
    version: 1,
    created_at: "2026-08-01T09:00:00Z",
    updated_at: "2026-08-01T09:00:00Z",
    workspace_id: "w",
    withheld_items: 0,
    items: itemDocs.map((document_id, i) => ({
      id: `i-${i + 1}`,
      board_pack_id: "p-1",
      document_id,
      agenda_item_id: null,
      position: i + 1,
      note: null,
      created_at: "2026-08-01T09:00:00Z",
      workspace_id: "w",
    })),
    ...over,
  };
}

const deck = doc("d-1", "Board deck");
const memo = doc("d-2", "CFO memo");

function setup(p: BoardPack, m: Meeting = meeting()) {
  const onChanged = jest.fn();
  const onClose = jest.fn();
  render(
    <PackBuilder pack={p} meeting={m} documents={[deck, memo]} onChanged={onChanged} onClose={onClose} />,
  );
  return { onChanged, onClose };
}

beforeEach(() => {
  jest.resetAllMocks();
  meetings.material.mockResolvedValue({ documents: [deck, memo], withheld: 0 });
});

describe("adding and removing", () => {
  it("offers only material not already in the pack, and re-reads after adding", async () => {
    const after = pack({ version: 2 }, ["d-1"]);
    packs.addItem.mockResolvedValue({});
    packs.get.mockResolvedValue(after);
    const { onChanged } = setup(pack({}, ["d-1"]));

    // d-1 is already in the pack, so only d-2 can be added.
    expect(await screen.findByRole("button", { name: "Add CFO memo" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Board deck" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add CFO memo" }));
    expect(packs.addItem).toHaveBeenCalledWith("p-1", { document_id: "d-2" });
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(after));
  });

  it("removes by item id", async () => {
    packs.removeItem.mockResolvedValue(undefined);
    packs.get.mockResolvedValue(pack({ version: 2 }));
    setup(pack({}, ["d-1"]));

    fireEvent.click(await screen.findByRole("button", { name: "Remove Board deck" }));
    expect(packs.removeItem).toHaveBeenCalledWith("i-1");
  });

  it("says so when the meeting has no material, rather than showing an empty list", async () => {
    meetings.material.mockResolvedValue({ documents: [], withheld: 0 });
    setup(pack());
    expect(await screen.findByText(/No material has been assigned/i)).toBeInTheDocument();
  });
});

describe("reordering", () => {
  it("is reachable by keyboard and sends every item id in the new order", async () => {
    packs.reorder.mockResolvedValue(pack());
    packs.get.mockResolvedValue(pack({}, ["d-2", "d-1"]));
    setup(pack({}, ["d-1", "d-2"]));

    const down = await screen.findByRole("button", { name: "Move Board deck down" });
    // A real <button>: focusable and activated by Enter/Space natively, no custom
    // key handling to get wrong.
    down.focus();
    expect(down).toHaveFocus();
    expect(down.tagName).toBe("BUTTON");
    fireEvent.click(down);
    expect(packs.reorder).toHaveBeenCalledWith("p-1", ["i-2", "i-1"]);
  });

  it("disables moving the first item up and the last item down", async () => {
    setup(pack({}, ["d-1", "d-2"]));
    expect(await screen.findByRole("button", { name: "Move Board deck up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move CFO memo down" })).toBeDisabled();
  });
});

describe("when the re-read fails", () => {
  it("says the pack may be stale instead of leaving it looking current", async () => {
    packs.addItem.mockResolvedValue({});
    packs.get.mockRejectedValue(new ApiError(0, "network", "Could not reach the server."));
    setup(pack({}, ["d-1"]));

    fireEvent.click(await screen.findByRole("button", { name: "Add CFO memo" }));
    expect(await screen.findByText(/saved, but the pack could not be reloaded/i)).toBeInTheDocument();
  });

  it("does not leave an unhandled rejection when a failed change is followed by a failed re-read", async () => {
    packs.removeItem.mockRejectedValue(new ApiError(409, "conflict", "locked"));
    packs.get.mockRejectedValue(new ApiError(0, "network", "Could not reach the server."));
    setup(pack({}, ["d-1"]));

    fireEvent.click(await screen.findByRole("button", { name: "Remove Board deck" }));
    expect(await screen.findByText(/could not be reloaded/i)).toBeInTheDocument();
  });
});

describe("focus and announcements", () => {
  it("returns focus to the pack list after an add and announces it", async () => {
    packs.addItem.mockResolvedValue({});
    packs.get.mockResolvedValue(pack({ version: 2 }, ["d-1", "d-2"]));
    setup(pack({}, ["d-1"]));

    fireEvent.click(await screen.findByRole("button", { name: "Add CFO memo" }));
    await waitFor(() => expect(screen.getByRole("list", { name: "In this pack" })).toHaveFocus());
    expect(screen.getByText("CFO memo added to the pack.")).toBeInTheDocument();
  });

  it("keeps focus on the pressed move button, or its opposite when the row reaches an end", async () => {
    packs.reorder.mockResolvedValue(pack());
    // After moving Board deck down it is last, so "down" is disabled: focus should land on "up".
    const swapped = pack({}, ["d-2", "d-1"]);
    swapped.items[0].id = "i-2"; // items keep their ids when they move
    swapped.items[1].id = "i-1";
    packs.get.mockResolvedValue(swapped);
    setup(pack({}, ["d-1", "d-2"]));

    fireEvent.click(await screen.findByRole("button", { name: "Move Board deck down" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Move Board deck up" })).toHaveFocus());
    expect(screen.getByText("Board deck moved to position 2 of 2.")).toBeInTheDocument();
  });

  it("moves focus into the confirmation and back out again", async () => {
    setup(pack({}, ["d-1"]));
    fireEvent.click(await screen.findByRole("button", { name: /Publish…/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Back" })).toHaveFocus());

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Publish…/ })).toHaveFocus());
  });
});

describe("publishing", () => {
  it("asks first, states the version, and does not publish until confirmed", async () => {
    setup(pack({ version_no: 3 }, ["d-1"]));

    fireEvent.click(await screen.findByRole("button", { name: /Publish…/ }));
    expect(screen.getByRole("heading", { name: "Publish version 3?" })).toBeInTheDocument();
    expect(screen.getByText(/To change it afterwards you issue version 4/)).toBeInTheDocument();
    expect(screen.getByText(/does not send anything/i)).toBeInTheDocument();
    expect(packs.publish).not.toHaveBeenCalled();
  });

  it("publishes with the pack's current concurrency version, not a stale one", async () => {
    // The builder was opened at version 1; adding an item moved the server to 2.
    packs.addItem.mockResolvedValue({});
    packs.get.mockResolvedValue(pack({ version: 2 }, ["d-2"]));
    packs.publish.mockResolvedValue(pack({ status: "published", version: 3 }));
    setup(pack({ version: 1 }));

    fireEvent.click(await screen.findByRole("button", { name: "Add CFO memo" }));
    // Publish… is disabled while the add is in flight; wait for the re-read to land.
    const publish = await screen.findByRole("button", { name: /Publish…/ });
    await waitFor(() => expect(publish).toBeEnabled());
    fireEvent.click(publish);
    fireEvent.click(screen.getByRole("button", { name: "Publish version 1" }));

    expect(packs.publish).toHaveBeenCalledWith("p-1", 2);
  });

  it("Back returns to editing without publishing", async () => {
    setup(pack({}, ["d-1"]));
    fireEvent.click(await screen.findByRole("button", { name: /Publish…/ }));
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("button", { name: "Move Board deck down" })).toBeInTheDocument();
    expect(packs.publish).not.toHaveBeenCalled();
  });

  it("shows a refusal in the confirmation and re-reads the pack", async () => {
    packs.publish.mockRejectedValue(new ApiError(409, "stale_resource", "expected version 1, current 2"));
    packs.get.mockResolvedValue(pack({ version: 2 }));
    setup(pack());

    fireEvent.click(await screen.findByRole("button", { name: /Publish…/ }));
    fireEvent.click(screen.getByRole("button", { name: "Publish version 1" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("expected version 1, current 2");
    expect(packs.get).toHaveBeenCalledWith("p-1");
  });
});

describe("what cannot be edited", () => {
  it("offers no controls on a published pack", async () => {
    setup(pack({ status: "published", published_at: "2026-08-02T09:00:00Z" }, ["d-1"]));
    expect(await screen.findByText(/This version is published and cannot be edited/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publish…/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Remove/ })).not.toBeInTheDocument();
  });

  it("offers no controls once the meeting is under way", async () => {
    setup(pack({}, ["d-1"]), meeting({ status: "in_progress" }));
    expect(await screen.findByText(/cannot be edited while its meeting/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Publish…/ })).not.toBeInTheDocument();
  });

  it("discloses how many items are withheld, as a count and nothing else (ADR-018)", async () => {
    setup(pack({ withheld_items: 4 }, ["d-1"]));
    await screen.findByText("Board deck");
    // The shared wording, so every surface says the same thing about the same fact.
    expect(screen.getByText("4 withheld")).toBeInTheDocument();
    expect(screen.getByText(/not everything the board holds/i)).toBeInTheDocument();
    // No derived total, no placeholder rows.
    expect(screen.queryByText(/\bof \d+\b.*items|\d+ items?\b/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem").length).toBe(1 + 1); // pack row + the one addable doc
  });

  it("says nothing about withheld items when there are none", async () => {
    setup(pack({ withheld_items: 0 }, ["d-1"]));
    await screen.findByText("Board deck");
    expect(screen.queryByText(/withheld/i)).not.toBeInTheDocument();
  });

  it("switches reordering off when anything is withheld, and says why", async () => {
    setup(pack({ withheld_items: 1 }, ["d-1", "d-2"]));
    expect(await screen.findByRole("button", { name: "Move Board deck down" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move CFO memo up" })).toBeDisabled();
    expect(screen.getByText(/Reordering is unavailable/)).toBeInTheDocument();
    // Removing is still possible: it needs one id, not all of them.
    expect(screen.getByRole("button", { name: "Remove Board deck" })).toBeEnabled();
  });

  it("shows — for a meeting it cannot name, not an invented one", async () => {
    render(
      <PackBuilder pack={pack()} meeting={undefined} documents={[]} onChanged={jest.fn()} onClose={jest.fn()} />,
    );
    expect(await screen.findByText(/— · Version 1/)).toBeInTheDocument();
  });
});

describe("starting a pack", () => {
  it("pre-selects nothing and only offers meetings the server would accept", async () => {
    render(
      <PackCreateDialog
        meetings={[meeting({ id: "m-a", title: "Open one" }), meeting({ id: "m-b", title: "Under way", status: "in_progress" })]}
        onCreated={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    const select = screen.getByLabelText("Meeting");
    expect(select).toHaveValue("");
    expect(within(select).queryByRole("option", { name: "Under way" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create pack" })).toBeDisabled();

    fireEvent.change(select, { target: { value: "m-a" } });
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Q3 pre-read" } });
    expect(screen.getByRole("button", { name: "Create pack" })).toBeEnabled();
  });

  it("issues a new version from the published one's concurrency version", async () => {
    const published = pack({ status: "published", version: 5, version_no: 2 });
    const replacement = pack({ id: "p-2", version_no: 3 });
    packs.supersede.mockResolvedValue({ superseded: published, replacement });
    const onCreated = jest.fn();
    render(
      <PackCreateDialog meetings={[meeting()]} supersedes={published} onCreated={onCreated} onClose={jest.fn()} />,
    );

    expect(screen.getByRole("heading", { name: "Issue version 3" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(packs.supersede).toHaveBeenCalledWith("p-1", { new_title: "Q3 pre-read", expected_version: 5 });
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(replacement, published));
  });
});

describe("the version trail", () => {
  it("lists every version of the meeting's pack and marks the current one", () => {
    const v1 = pack({ status: "published", superseded_by_id: "p-2", published_at: "2026-08-02T09:00:00Z" });
    const v2 = pack({ id: "p-2", version_no: 2 });
    render(<PackCard pack={v2} all={[v2, v1]} documents={[]} meetingTitle="Q3 Board" />);

    const nav = screen.getByRole("navigation", { name: "Versions of this pack" });
    expect(within(nav).getByText(/2 · Draft/)).toHaveAttribute("aria-current", "true");
    expect(within(nav).getByRole("link", { name: /1 · Published/ })).toHaveAttribute("href", "#p-1");
  });

  it("offers a new version only on the latest published pack of an editable meeting", () => {
    const published = pack({ status: "published" });
    const { rerender } = render(
      <PackCard pack={published} all={[published]} documents={[]} meetingStatus="scheduled" onNewVersion={jest.fn()} />,
    );
    expect(screen.getByRole("button", { name: "New version" })).toBeInTheDocument();

    rerender(
      <PackCard pack={published} all={[published]} documents={[]} meetingStatus="in_progress" onNewVersion={jest.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "New version" })).not.toBeInTheDocument();

    const replaced = pack({ status: "published", superseded_by_id: "p-2" });
    rerender(
      <PackCard pack={replaced} all={[replaced]} documents={[]} meetingStatus="scheduled" onNewVersion={jest.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "New version" })).not.toBeInTheDocument();
  });
});
