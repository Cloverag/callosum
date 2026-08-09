/**
 * @jest-environment node
 */
import { agendaApi } from '../src/lib/agenda';
import { ApiError } from '../src/lib/http';

/**
 * The write path for `/prepare`'s one action.
 *
 * Node environment on purpose: jsdom shadows `Response` and `fetch` with nothing, so a
 * client test under jsdom asserts against stubs rather than the real Fetch API. This is
 * the same reason the other client tests carry the pragma.
 *
 * What these pin is the contract, not the happy path — the API sets
 * `extra="forbid"`, so a field this client invents is a 422 rather than a value the
 * server quietly ignores. The `workspace_id` assertion is the load-bearing one: it is
 * session-derived (ADR-013) and an endpoint accepting it would make RLS advisory.
 */

const originalFetch = global.fetch;

function mockFetch(status: number, body: unknown) {
  const fn = jest.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

afterEach(() => {
  global.fetch = originalFetch;
  jest.restoreAllMocks();
});

describe('agendaApi.create', () => {
  it('POSTs to /api/agenda and returns the created record', async () => {
    const created = { id: 'a-new', title: 'Ship pricing', position: 3, version: 1 };
    const fetchMock = mockFetch(201, created);

    const result = await agendaApi.create({ meeting_id: 'm-1', title: 'Ship pricing' });

    expect(result).toEqual(created);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/agenda');
    expect(init.method).toBe('POST');
    // The session is an httpOnly cookie; a request that omitted it would read as
    // logged-out rather than as misconfigured.
    expect(init.credentials).toBe('same-origin');
  });

  it('never sends workspace_id — it is session-derived, not a client argument', async () => {
    const fetchMock = mockFetch(201, { id: 'a-new' });

    await agendaApi.create({ meeting_id: 'm-1', title: 'Ship pricing' });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).not.toHaveProperty('workspace_id');
    expect(body).not.toHaveProperty('clearance');
  });

  it('sends only the fields the server declares, since extra is forbidden', async () => {
    const fetchMock = mockFetch(201, { id: 'a-new' });

    await agendaApi.create({
      meeting_id: 'm-1',
      title: 'Ship pricing',
      description: 'Open commitment, past its due date of 2026-06-30.',
    });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(Object.keys(body).sort()).toEqual(['description', 'meeting_id', 'title']);
  });

  it('omits position so the item appends rather than inserting', async () => {
    const fetchMock = mockFetch(201, { id: 'a-new' });

    await agendaApi.create({ meeting_id: 'm-1', title: 'Ship pricing' });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    // Supplying a position INSERTS and shifts everything after it. Appending is the
    // only correct default for a suggestion accepted one at a time.
    expect(body).not.toHaveProperty('position');
  });

  it('raises the server error rather than resolving, so the row can report it', async () => {
    mockFetch(409, { error: { code: 'invalid_transition', detail: 'Agenda is locked.' } });

    await expect(
      agendaApi.create({ meeting_id: 'm-1', title: 'Ship pricing' }),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it('marks a locked agenda as an unretryable conflict, not a stale read', async () => {
    mockFetch(409, { error: { code: 'invalid_transition', detail: 'Agenda is locked.' } });

    // The distinction decides the copy: a stale 409 says "reload and retry", this one
    // says the operation itself is refused. Offering retry here promises the
    // impossible.
    await expect(
      agendaApi.create({ meeting_id: 'm-1', title: 'Ship pricing' }),
    ).rejects.toMatchObject({ status: 409, isUnretryableConflict: true, isStale: false });
  });
});
