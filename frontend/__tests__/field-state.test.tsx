import { render, screen } from "@testing-library/react";
import { FieldValue, fieldHint, NOT_MEASURED } from "../src/components/ui/field-value";
import {
  fromNullable,
  measured,
  notMeasured,
  withheld,
  resourceStateFromError,
} from "../src/lib/field-state";
import { ApiError } from "../src/lib/http";

/**
 * The four data states from `docs/ux/dashboard-content-spec.md`.
 *
 * The case that matters most is the third one below: a measured `0` and an
 * unmeasured field are different facts, and every previous encoding of them —
 * `number | null` read through a truthiness check — collapsed the two. That is
 * the bug the whole module exists to make unrepresentable, so it is tested
 * first and directly rather than implied by a rendering test.
 */
describe("FieldState", () => {
  it("treats a null as not measured, and says why", () => {
    const state = fromNullable<number>(null, "no extraction run has populated the queue");
    expect(state).toEqual({
      status: "not_measured",
      reason: "no extraction run has populated the queue",
    });
  });

  it("keeps a real zero measured", () => {
    // The whole point. `0` is a count someone took; it must not become an em dash.
    const state = fromNullable<number>(0, "unused");
    expect(state).toEqual({ status: "measured", value: 0 });
  });

  it("renders an em dash for an unmeasured field, never a zero", () => {
    render(<FieldValue state={notMeasured<number>("the queue was never populated")} />);
    const el = screen.getByText(NOT_MEASURED);
    expect(el).toBeInTheDocument();
    // The reason has to reach a screen reader too — an unexplained em dash is
    // indistinguishable from a rendering bug.
    expect(el).toHaveAttribute("aria-label", "Not measured — the queue was never populated");
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders a measured zero as a zero", () => {
    render(<FieldValue state={measured(0)} />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText(NOT_MEASURED)).not.toBeInTheDocument();
  });

  it("discloses withheld content as a count and not a title", () => {
    render(<FieldValue state={withheld<number>(3)} />);
    expect(screen.getByText("3 withheld")).toBeInTheDocument();
  });

  it("writes the metric's meaning once, whichever state applies", () => {
    const meaning = "Facts waiting for a human to approve them.";
    expect(fieldHint(measured(5), meaning)).toBe(meaning);
    expect(fieldHint(notMeasured<number>("nothing ran"), meaning)).toBe(
      `${meaning} Not measured — nothing ran`,
    );
  });
});

describe("resourceStateFromError", () => {
  it("reads a stale write, carrying both version numbers", () => {
    const state = resourceStateFromError(
      new ApiError(409, "stale_resource", "expected version 3, current 4"),
    );
    expect(state).toEqual({ status: "stale", expected: 3, current: 4 });
  });

  it("leaves the versions null when the server did not send them", () => {
    // `ApiError.versions` refuses to guess, and so must this — an invented
    // version number is worse than an absent one.
    const state = resourceStateFromError(new ApiError(409, "stale_resource", "conflict"));
    expect(state).toEqual({ status: "stale", expected: null, current: null });
  });

  it("reads a refusal that no refetch can fix as locked", () => {
    const state = resourceStateFromError(
      new ApiError(409, "pack_locked", "The pack was published and can no longer be reordered."),
    );
    expect(state).toEqual({
      status: "locked",
      reason: "The pack was published and can no longer be reordered.",
    });
  });

  it("returns null for a failure that is not a state of the resource", () => {
    // A 500 is state 3, not state 6 or 7. Dressing it up as "locked" would tell
    // the user their pack is frozen when the truth is the server is down.
    expect(resourceStateFromError(new ApiError(500, "internal", "boom"))).toBeNull();
    expect(resourceStateFromError(new ApiError(422, "invalid", "bad field"))).toBeNull();
    // Choosing a workspace is the session gate's job, not a widget's.
    expect(
      resourceStateFromError(new ApiError(409, "workspace_not_selected", "pick one")),
    ).toBeNull();
  });
});
