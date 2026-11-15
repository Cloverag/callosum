/**
 * @jest-environment node
 */
import { agendaApi } from '../src/lib/agenda';

/**
 * The P5 CP5D write paths: edit, remove, reorder. Node environment for the same reason
 * as agenda-create.test.ts — the real Fetch API, not jsdom stubs.
 */

const originalFetch = global.fetch;

function mockFetch(status: number, body?: unknown) {
  const fn = jest.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

afterEach(() => {
  global.fetch = originalFetch;
});

describe('agendaApi writes', () => {
  it('update PATCHes the item with its expected_version', async () => {
    const fetchMock = mockFetch(200, { id: 'a-1', version: 3 });
    await agendaApi.update('a-1', { expected_version: 2, duration_minutes: null });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/agenda/a-1');
    expect(init.method).toBe('PATCH');
    // null clears the timebox; it must reach the server as null, not be dropped.
    expect(JSON.parse(init.body as string)).toEqual({ expected_version: 2, duration_minutes: null });
  });

  it('remove sends expected_version in the query string, not a body', async () => {
    const fetchMock = mockFetch(204);
    await agendaApi.remove('a-1', 5);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/agenda/a-1?expected_version=5');
    expect(init.method).toBe('DELETE');
    expect(init.body).toBeUndefined();
  });

  it('reorder POSTs the full order and never a workspace_id', async () => {
    const fetchMock = mockFetch(200, []);
    await agendaApi.reorder('m-1', ['a-2', 'a-1']);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/agenda/reorder');
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({ meeting_id: 'm-1', ordered_item_ids: ['a-2', 'a-1'] });
    expect(body).not.toHaveProperty('workspace_id');
  });
});
