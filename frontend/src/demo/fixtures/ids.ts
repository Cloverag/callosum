/**
 * Every identifier the demo dataset uses, in one place.
 *
 * ---------------------------------------------------------------------------
 * WHY THEY LOOK LIKE THIS
 * ---------------------------------------------------------------------------
 * The API's ids are UUIDs, and the fixtures have to be UUID-shaped or the
 * surfaces that `encodeURIComponent` them into paths would be exercising a
 * shape the real system never produces. But a *plausible* UUID is a hazard: a
 * screenshot of demo mode is indistinguishable from a screenshot of a tenant,
 * and a workspace id copied out of one and pasted into a real console looks
 * like a lookup that merely failed rather than a thing that never existed.
 *
 * So every id here is UUID-shaped and unmistakably synthetic: the reserved
 * `demo` group, and a body that reads as a label rather than as entropy. They
 * are valid UUID *syntax* and are not valid UUIDs — no version nibble, no
 * variant bits — which is the intended combination. Anything that parses these
 * strictly should reject them.
 */

/** The workspace the whole fixture set lives in. Reads as fake at a glance. */
export const DEMO_WORKSPACE_ID = "deadbeef-demo-0000-0000-fabricated00";

/** The principal the demo session is signed in as. */
export const DEMO_PRINCIPAL_ID = "deadbeef-demo-0000-0001-fabricated00";

/**
 * The name on the header avatar.
 *
 * Deliberately not a person. The director's note is the reason: a fabricated
 * board member with a plausible name is the same failure as a fabricated
 * conflict count, only further from the screen and therefore easier to quote
 * out of context. Nobody screenshots this and asks who it is.
 */
export const DEMO_PRINCIPAL_NAME = "DEMO — fabricated data";

/**
 * Not one of `BoardRole`'s five values, and not one of the membership roles in
 * `0001_workspace_and_membership.py` either. The header renders `role` as free
 * text, so this says what it is rather than impersonating an office.
 */
export const DEMO_PRINCIPAL_ROLE = "demo (not a real role)";

const mk = (kind: string, n: number) =>
  `deadbeef-demo-${kind}-${String(n).padStart(4, "0")}-fabricated00`;

export const MEETING = [1, 2, 3, 4, 5, 6].map((n) => mk("mtg0", n));
export const MEMBER = [1, 2, 3, 4, 5, 6].map((n) => mk("bmem", n));
export const DOCUMENT = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => mk("docu", n));
export const AGENDA = [1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => mk("agnd", n));
export const PACK = [1, 2, 3].map((n) => mk("pack", n));
export const PACK_ITEM = [1, 2, 3, 4, 5, 6, 7].map((n) => mk("pcki", n));
export const MINUTES = [1, 2, 3].map((n) => mk("minu", n));
export const DECISION = [1, 2, 3, 4, 5, 6].map((n) => mk("deci", n));
export const STANCE = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => mk("stnc", n));
export const RESOLUTION = [1, 2, 3, 4].map((n) => mk("reso", n));
export const VOTE = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((n) => mk("vote", n));
export const COMMITMENT = [1, 2, 3, 4, 5, 6, 7].map((n) => mk("cmmt", n));
export const UPDATE = [1, 2, 3, 4].map((n) => mk("updt", n));
export const CONFLICT = [1, 2, 3].map((n) => mk("cnfl", n));
export const QUARANTINE = [1, 2, 3].map((n) => mk("qrnt", n));
