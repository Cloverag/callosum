import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AgendaEditor } from "../src/app/prepare/agenda-editor";
import { agendaApi, type AgendaItem } from "../src/lib/agenda";
import { ApiError } from "../src/lib/http";

jest.mock("../src/lib/agenda", () => {
  const actual = jest.requireActual("../src/lib/agenda");
  return { ...actual, agendaApi: { list: jest.fn(), update: jest.fn(), remove: jest.fn(), reorder: jest.fn() } };
});

const api = agendaApi as unknown as Record<"list" | "update" | "remove" | "reorder", jest.Mock>;

function item(over: Partial<AgendaItem>): AgendaItem {
  return {
    id: "a-1", meeting_id: "m-1", workspace_id: "w", title: "Pricing", description: null,
    duration_minutes: 15, presenter: "Raj", position: 1, version: 1,
    created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z", ...over,
  };
}

const A = item({});
const B = item({ id: "a-2", title: "Hiring", position: 2, duration_minutes: null, presenter: null, version: 4 });

beforeEach(() => jest.clearAllMocks());

it("shows each item, an untimed item as untimed, and the timeboxed total", () => {
  render(<AgendaEditor meetingId="m-1" items={[A, B]} onChange={jest.fn()} />);
  expect(screen.getByText("Untimed · No presenter")).toBeTruthy();
  expect(screen.getByText(/min timeboxed/).textContent).toMatch(/15 min timeboxed across 1 of 2 items/);
});

it("move down sends the swapped order and adopts the server's list", async () => {
  const onChange = jest.fn();
  api.reorder.mockResolvedValue([B, A]);
  render(<AgendaEditor meetingId="m-1" items={[A, B]} onChange={onChange} />);

  expect((screen.getByLabelText('Move "Pricing" up') as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByLabelText('Move "Pricing" down'));

  await waitFor(() => expect(onChange).toHaveBeenCalledWith([B, A]));
  expect(api.reorder).toHaveBeenCalledWith("m-1", ["a-2", "a-1"]);
});

it("an edit sends the item's version and only what changed; an empty minutes field clears the timebox", async () => {
  const onChange = jest.fn();
  api.update.mockResolvedValue({ ...A, duration_minutes: null, version: 2 });
  render(<AgendaEditor meetingId="m-1" items={[A, B]} onChange={onChange} />);

  fireEvent.click(screen.getByLabelText('Edit "Pricing"'));
  fireEvent.change(screen.getByLabelText("Minutes"), { target: { value: "" } });
  fireEvent.click(screen.getByText("Save"));

  await waitFor(() => expect(onChange).toHaveBeenCalled());
  // Only the changed field: #227 records `changed_fields` in the audit trail.
  expect(api.update).toHaveBeenCalledWith("a-1", { expected_version: 1, duration_minutes: null });
});

it("a refused edit keeps the form open with what was typed, and says why", async () => {
  api.update.mockRejectedValue(new ApiError(409, "locked", "meeting in progress"));
  render(<AgendaEditor meetingId="m-1" items={[A]} onChange={jest.fn()} />);

  fireEvent.click(screen.getByLabelText('Edit "Pricing"'));
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Pricing v2" } });
  fireEvent.click(screen.getByText("Save"));

  expect(await screen.findByRole("alert")).toBeTruthy();
  expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Pricing v2");
});

it("rejects a non-integer timebox before anything is sent", () => {
  render(<AgendaEditor meetingId="m-1" items={[A]} onChange={jest.fn()} />);
  fireEvent.click(screen.getByLabelText('Edit "Pricing"'));
  fireEvent.change(screen.getByLabelText("Minutes"), { target: { value: "1.5" } });

  expect(screen.getByRole("alert").textContent).toMatch(/whole number/);
  expect((screen.getByText("Save").closest("button") as HTMLButtonElement).disabled).toBe(true);
});

it("removal needs a confirm, then renumbers locally exactly as the server does", async () => {
  const onChange = jest.fn();
  api.remove.mockResolvedValue(undefined);
  render(<AgendaEditor meetingId="m-1" items={[A, B]} onChange={onChange} />);

  fireEvent.click(screen.getByLabelText('Remove "Pricing"'));
  expect(api.remove).not.toHaveBeenCalled();
  expect(document.activeElement?.textContent).toBe("Keep"); // focus lands on the safe choice
  fireEvent.click(screen.getByText("Remove"));

  // delete_agenda_item runs `position = position - 1` on the tail and changes no version.
  await waitFor(() => expect(onChange).toHaveBeenCalledWith([{ ...B, position: 1 }]));
  expect(api.remove).toHaveBeenCalledWith("a-1", 1);
  expect(api.list).not.toHaveBeenCalled();
  expect(screen.getByText('"Pricing" removed from the agenda.')).toBeTruthy();
});

it("a save that changes nothing sends nothing", async () => {
  render(<AgendaEditor meetingId="m-1" items={[A]} onChange={jest.fn()} />);
  fireEvent.click(screen.getByLabelText('Edit "Pricing"'));
  fireEvent.click(screen.getByText("Save"));

  await waitFor(() => expect(screen.getByLabelText('Edit "Pricing"')).toBeTruthy());
  expect(api.update).not.toHaveBeenCalled();
});

it("cancelling an edit returns focus to the Edit button", async () => {
  render(<AgendaEditor meetingId="m-1" items={[A]} onChange={jest.fn()} />);
  fireEvent.click(screen.getByLabelText('Edit "Pricing"'));
  expect(document.activeElement).toBe(screen.getByLabelText("Title"));
  fireEvent.click(screen.getByText("Cancel"));

  await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('Edit "Pricing"')));
});

it("a move is announced and keeps focus on the moved item", async () => {
  const { rerender } = render(<AgendaEditor meetingId="m-1" items={[A, B]} onChange={(next) => rerender(<AgendaEditor meetingId="m-1" items={next} onChange={jest.fn()} />)} />);
  api.reorder.mockResolvedValue([{ ...B, position: 1 }, { ...A, position: 2 }]);

  fireEvent.click(screen.getByLabelText('Move "Pricing" down'));

  expect(await screen.findByText('"Pricing" moved to position 2 of 2.')).toBeTruthy();
  // Now last, so its "down" is disabled; focus goes to its "up".
  await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText('Move "Pricing" up')));
});

it.each([
  [new ApiError(409, "stale_resource", "x"), /Someone else changed the agenda/],
  [new ApiError(409, "locked", "x"), /in progress, completed or cancelled/],
  [new TypeError("fetch failed"), /Could not reach the server/],
])("explains a refused write: %s", async (error, copy) => {
  api.reorder.mockRejectedValue(error);
  render(<AgendaEditor meetingId="m-1" items={[A, B]} onChange={jest.fn()} />);
  fireEvent.click(screen.getByLabelText('Move "Pricing" down'));

  expect((await screen.findByRole("alert")).textContent).toMatch(copy);
});
