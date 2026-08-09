import { render, screen } from '@testing-library/react';
import { Stages, STAGES } from '../src/app/prepare/stages';
import { sourceHref, prepSignals, suggestAgenda, type PrepSource } from '../src/lib/prep';
import type { Commitment } from '../src/lib/commitments';
import type { Decision } from '../src/lib/decisions';

/**
 * Regressions for the two defects found while verifying `/prepare` on 2026-08-04.
 *
 * Both were mine, both were the same underlying mistake in different clothes: the page
 * asserted something it had not established. The stepper claimed four of five steps
 * complete because the *fetch* had finished, and the source lines named a record
 * without letting anyone reach it.
 *
 * These tests are written to fail if either returns, including by a reasonable-looking
 * change — a "current step" prop added back to `Stages`, or a source rendered without
 * its id.
 */

const TODAY = '2026-08-04';

describe('the stages index makes no completion claim', () => {
  it('renders all five stages as links, none marked complete or current', () => {
    const { container } = render(<Stages />);

    const links = container.querySelectorAll('a');
    expect(links).toHaveLength(5);

    for (const link of Array.from(links)) {
      // A progress stepper marks state with aria-current or aria-disabled. An index
      // has neither: every stage is equally reachable because none of them is "done".
      expect(link.getAttribute('aria-current')).toBeNull();
      expect(link.getAttribute('aria-disabled')).toBeNull();
    }
  });

  it('links each stage to its section anchor rather than tracking position', () => {
    const { container } = render(<Stages />);
    const hrefs = Array.from(container.querySelectorAll('a')).map((a) => a.getAttribute('href'));

    expect(hrefs).toEqual(STAGES.map((s) => `#${s.id}`));
  });

  it('takes no progress argument at all', () => {
    // The defect was `current={data ? 4 : 0}` -- a hard-coded 4 that meant "the fetch
    // resolved", rendered as "four steps are done". The component cannot regress to
    // that while it accepts no props: a caller trying to pass one fails typecheck.
    expect(Stages).toHaveLength(0);
  });

  it('names the five stages in reading order', () => {
    render(<Stages />);
    for (const stage of STAGES) {
      expect(screen.getByText(stage.label)).toBeInTheDocument();
    }
  });
});

describe('every source resolves, or admits that it cannot', () => {
  it('sends a commitment to the surface that anchors it by id', () => {
    const source: PrepSource = { kind: 'commitment', id: 'c-42', label: 'Commitment' };
    // /commitments renders `id={c.id}` with scroll-mt-8, so the fragment resolves.
    expect(sourceHref(source)).toBe('/commitments#c-42');
  });

  it('sends a decision to the surface that anchors it by id', () => {
    const source: PrepSource = { kind: 'decision', id: 'd-7', label: 'Decision' };
    expect(sourceHref(source)).toBe('/decisions#d-7');
  });

  it('returns null for an agenda item, because no route resolves one', () => {
    // Agenda items render inside the calendar's meeting detail, not on a route that
    // can resolve one by id. Returning a plausible "/agenda#id" would 404, and the
    // reader would only find out by clicking.
    const source: PrepSource = { kind: 'agenda_item', id: 'a-1', label: 'Agenda item' };
    expect(sourceHref(source)).toBeNull();
  });

  it('carries the real record id through to the href, not an index or a label', () => {
    const commitments = [
      {
        id: 'c-real-id',
        title: 'Ship pricing',
        status: 'open',
        due_date: null,
      } as Commitment,
    ];
    const decisions = [
      { id: 'd-real-id', title: 'Adopt pricing', status: 'proposed' } as Decision,
    ];

    const hrefs = [
      ...prepSignals(commitments, decisions, TODAY),
      ...suggestAgenda(commitments, decisions, [], TODAY),
    ].map((x) => sourceHref(x.source));

    // Every derived claim can be checked against the row it came from.
    expect(hrefs).toEqual([
      '/commitments#c-real-id',
      '/decisions#d-real-id',
      '/commitments#c-real-id',
      '/decisions#d-real-id',
    ]);
  });
});
