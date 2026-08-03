import {
  nextMeetingToPrepare,
  openDecisions,
  prepReadiness,
  prepSignals,
  suggestAgenda,
  unresolvedCommitments,
} from '../src/lib/prep';
import type { Commitment } from '../src/lib/commitments';
import type { Decision } from '../src/lib/decisions';
import type { AgendaItem } from '../src/lib/agenda';
import type { BoardPack } from '../src/lib/packs';

/**
 * These pin the property that matters more than any output shape: **nothing this module
 * produces exists without a row behind it.** The suggestion engine is a query, and the
 * test that would catch it quietly becoming a generator is the one asserting that every
 * signal and every suggestion carries a source id that appears in the input.
 *
 * The readiness tests exist for the opposite reason — to pin an absence. The prototype
 * these screens follow shows Agenda 90% and Approvals 40%; there is no denominator for
 * either, so readiness must report counts. A future change adding a percentage should
 * have to delete an assertion to do it.
 */

const TODAY = '2026-08-04';

function commitment(over: Partial<Commitment> & { id: string; title: string }): Commitment {
  return {
    decision_id: 'd-1',
    resolution_id: null,
    owner_board_member_id: 'bm-1',
    accountable_team: null,
    detail: null,
    due_date: null,
    status: 'open',
    completed_at: null,
    external_system: null,
    external_ref: null,
    last_sync_at: null,
    sync_error: null,
    updates: [],
    meeting_id: 'm-1',
    workspace_id: 'w-1',
    version: 1,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  } as Commitment;
}

function decision(over: Partial<Decision> & { id: string; title: string }): Decision {
  return {
    meeting_id: 'm-1',
    agenda_item_id: null,
    workspace_id: 'w-1',
    rationale: null,
    status: 'proposed',
    superseded_by_id: null,
    version: 1,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    stances: [],
    ...over,
  } as Decision;
}

function agendaItem(id: string, title: string): AgendaItem {
  return {
    id,
    meeting_id: 'm-1',
    workspace_id: 'w-1',
    title,
    description: null,
    duration_minutes: null,
    presenter: null,
    position: 1,
    version: 1,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
  } as AgendaItem;
}

function pack(over: Partial<BoardPack> & { id: string }): BoardPack {
  return {
    meeting_id: 'm-1',
    title: 'Pack',
    status: 'draft',
    version_no: 1,
    superseded_by_id: null,
    published_at: null,
    version: 1,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    workspace_id: 'w-1',
    items: [],
    ...over,
  } as BoardPack;
}

describe('unresolved commitments', () => {
  it('puts overdue before merely open, and undated last', () => {
    const items = [
      commitment({ id: 'c-undated', title: 'No date' }),
      commitment({ id: 'c-open', title: 'Due later', due_date: '2026-09-01' }),
      commitment({ id: 'c-late', title: 'Was due', due_date: '2026-07-02' }),
    ];

    expect(unresolvedCommitments(items, TODAY).map((c) => c.id)).toEqual([
      'c-late',
      'c-open',
      'c-undated',
    ]);
  });

  it('excludes anything already finished', () => {
    const items = [
      commitment({ id: 'c-done', title: 'Done', status: 'completed' }),
      commitment({ id: 'c-cancelled', title: 'Dropped', status: 'cancelled' }),
      commitment({ id: 'c-open', title: 'Live' }),
    ];

    expect(unresolvedCommitments(items, TODAY).map((c) => c.id)).toEqual(['c-open']);
  });
});

describe('open decisions', () => {
  it('counts only proposed — approved, deferred and superseded are settled', () => {
    const items = [
      decision({ id: 'd-open', title: 'Open', status: 'proposed' }),
      decision({ id: 'd-approved', title: 'Approved', status: 'approved' }),
      decision({ id: 'd-deferred', title: 'Deferred', status: 'deferred' }),
      decision({ id: 'd-superseded', title: 'Superseded', status: 'superseded' }),
      decision({ id: 'd-rejected', title: 'Rejected', status: 'rejected' }),
    ];

    expect(openDecisions(items).map((d) => d.id)).toEqual(['d-open']);
  });
});

describe('every derived claim carries its source', () => {
  it('gives each signal a source id that came from the input', () => {
    const commitments = [commitment({ id: 'c-1', title: 'Ship pricing', due_date: '2026-07-02' })];
    const decisions = [decision({ id: 'd-1', title: 'Adopt usage pricing' })];

    const signals = prepSignals(commitments, decisions, TODAY);
    const inputIds = new Set(['c-1', 'd-1']);

    expect(signals).toHaveLength(2);
    for (const s of signals) {
      // The load-bearing assertion. A generated suggestion would have nothing to put
      // here, so this is what fails if this module ever stops being a query.
      expect(inputIds.has(s.source.id)).toBe(true);
    }
  });

  it('marks a commitment past its due date as critical and says the date', () => {
    const signals = prepSignals(
      [commitment({ id: 'c-1', title: 'Ship pricing', due_date: '2026-07-02' })],
      [],
      TODAY,
    );

    expect(signals[0].tone).toBe('critical');
    expect(signals[0].statement).toContain('2026-07-02');
  });
});

describe('agenda suggestions', () => {
  it('does not re-suggest what is already on the agenda', () => {
    const commitments = [commitment({ id: 'c-1', title: 'Finalize pricing tiers' })];
    const existing = [agendaItem('a-1', 'Finalize pricing tiers')];

    expect(suggestAgenda(commitments, [], existing, TODAY)).toHaveLength(0);
  });

  it('matches existing items ignoring case and whitespace', () => {
    const commitments = [commitment({ id: 'c-1', title: 'Finalize   Pricing Tiers' })];
    const existing = [agendaItem('a-1', 'finalize pricing tiers')];

    expect(suggestAgenda(commitments, [], existing, TODAY)).toHaveLength(0);
  });

  it('suggests unfinished business and explains each in terms of its row', () => {
    const commitments = [commitment({ id: 'c-1', title: 'Ship pricing', due_date: '2026-07-02' })];
    const decisions = [decision({ id: 'd-1', title: 'Adopt usage pricing' })];

    const suggestions = suggestAgenda(commitments, decisions, [], TODAY);

    expect(suggestions.map((s) => s.title)).toEqual(['Ship pricing', 'Adopt usage pricing']);
    expect(suggestions[0].reason).toContain('2026-07-02');
    expect(suggestions[0].source).toEqual({ kind: 'commitment', id: 'c-1', label: 'Commitment' });
    expect(suggestions[1].source.kind).toBe('decision');
  });
});

describe('readiness reports counts, never a percentage', () => {
  it('counts what exists', () => {
    const readiness = prepReadiness(
      [agendaItem('a-1', 'One'), agendaItem('a-2', 'Two')],
      [pack({ id: 'p-1', status: 'published', items: [{}, {}, {}] as BoardPack['items'] })],
      [
        commitment({ id: 'c-late', title: 'Late', due_date: '2026-07-02' }),
        commitment({ id: 'c-open', title: 'Open', due_date: '2026-09-01' }),
      ],
      [decision({ id: 'd-1', title: 'Open decision' })],
      TODAY,
    );

    expect(readiness).toEqual({
      agendaItems: 2,
      packItems: 3,
      packPublished: true,
      overdueCommitments: 1,
      openCommitments: 2,
      openDecisions: 1,
    });
  });

  it('reports packItems as null when nothing is published, which is not zero', () => {
    // Zero would claim the pack is empty. Null says there is no published pack to
    // count -- a different statement, and the only true one.
    const readiness = prepReadiness([], [pack({ id: 'p-1', status: 'draft' })], [], [], TODAY);

    expect(readiness.packItems).toBeNull();
    expect(readiness.packPublished).toBe(false);
  });

  it('exposes no percentage or score field', () => {
    const readiness = prepReadiness([], [], [], [], TODAY);
    const keys = Object.keys(readiness);

    expect(keys.some((k) => /percent|score|ready|pct/i.test(k) && k !== 'packPublished')).toBe(
      false,
    );
  });
});

/**
 * Regressions for Devguru's review of #109. Both were real, both latent under the
 * demo corpus — the sort because every seeded meeting has a date, the pack selection
 * because only one pack is ever published.
 */
describe('review findings, #109', () => {
  it('picks the newest published pack even when handed them newest-first', () => {
    // `list_packs` returns ORDER BY version_no DESC. The previous implementation took
    // the last element and so reported the OLDEST published pack's item count.
    const readiness = prepReadiness(
      [],
      [
        pack({ id: 'p-v3', status: 'published', version_no: 3, items: [{}, {}, {}] as BoardPack['items'] }),
        pack({ id: 'p-v2', status: 'published', version_no: 2, items: [{}] as BoardPack['items'] }),
      ],
      [],
      [],
      TODAY,
    );

    expect(readiness.packItems).toBe(3);
  });

  it('is order-independent: the same packs ascending give the same answer', () => {
    const packs = [
      pack({ id: 'p-v2', status: 'published', version_no: 2, items: [{}] as BoardPack['items'] }),
      pack({ id: 'p-v3', status: 'published', version_no: 3, items: [{}, {}, {}] as BoardPack['items'] }),
    ];

    expect(prepReadiness([], packs, [], [], TODAY).packItems).toBe(3);
  });
});

describe('nextMeetingToPrepare', () => {
  const m = (title: string, status: string, scheduled_start: string | null) =>
    ({ title, status, scheduled_start });

  it('prefers a dated meeting over an undated draft', () => {
    // The bug: "" compares below every ISO timestamp, so the undated draft sorted
    // FIRST and the page prepared it instead of the meeting with a real date.
    const chosen = nextMeetingToPrepare([
      m('Unscheduled draft', 'draft', null),
      m('Q3 Board Meeting', 'draft', '2026-08-08T03:30:00Z'),
    ]);

    expect(chosen?.title).toBe('Q3 Board Meeting');
  });

  it('takes the earliest of several dated meetings', () => {
    const chosen = nextMeetingToPrepare([
      m('Later', 'scheduled', '2026-11-18T10:00:00Z'),
      m('Sooner', 'draft', '2026-08-08T03:30:00Z'),
    ]);

    expect(chosen?.title).toBe('Sooner');
  });

  it('ignores meetings that have already happened', () => {
    const chosen = nextMeetingToPrepare([
      m('Done', 'completed', '2026-03-11T10:00:00Z'),
      m('Next', 'scheduled', '2026-11-18T10:00:00Z'),
    ]);

    expect(chosen?.title).toBe('Next');
  });

  it('falls back to any meeting rather than showing an empty page', () => {
    const chosen = nextMeetingToPrepare([m('Done', 'completed', '2026-03-11T10:00:00Z')]);
    expect(chosen?.title).toBe('Done');
  });

  it('returns null when there are no meetings at all', () => {
    expect(nextMeetingToPrepare([])).toBeNull();
  });
});
