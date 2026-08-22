import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import EntityConflictsPage from '../src/app/entity-conflicts/page';
import { apiClient, type EntityConflict } from '../src/lib/api';

/**
 * These tests previously asserted copy from the old violet "Situation Room"
 * design — "Initializing neural matrix...", "System optimal" — which the v2
 * "Calm Desk" rebuild replaced. The component was fine throughout; the test had
 * simply never been updated, so it failed on strings that no longer exist.
 *
 * That is worth stating because issue #15 recorded the cause as a jsdom /
 * framer-motion `AnimatePresence` rendering problem. It was not: `AnimatePresence`
 * renders correctly here, as the approve and reject cases below demonstrate by
 * observing an exit from the list.
 *
 * Assertions are pinned to the exact copy and structure the page renders today.
 * Nothing here is loosened to make it pass — a broad matcher would let the same
 * drift happen again silently, which is the failure mode this file just had.
 */

jest.mock('../src/lib/api', () => ({
  apiClient: {
    getPendingConflicts: jest.fn(),
    approveConflict: jest.fn(),
    rejectConflict: jest.fn(),
  },
}));

/** Two conflicts so a resolution can be observed as a removal, not an emptying. */
const mockData: EntityConflict[] = [
  {
    id: '1',
    name_a: 'Raj Patel',
    type_a: 'PERSON',
    name_b: 'Rajesh Patel',
    type_b: 'PERSON',
    similarity: 0.91,
    quote_a: 'Raj Patel expressed concerns about the Q3 pricing model.',
    quote_b: "Rajesh Patel strongly disagreed with the board's new direction.",
    sensitivity: 1,
    status: 'pending',
    created_at: '2026-07-19T10:00:00Z',
  },
  {
    id: '2',
    name_a: 'Sequoia',
    type_a: 'ORGANIZATION',
    name_b: 'Sequoia Capital',
    type_b: 'ORGANIZATION',
    similarity: 0.82,
    quote_a: 'The term sheet from Sequoia requires an answer by Friday.',
    quote_b: 'Sequoia Capital has requested additional cap table details.',
    sensitivity: 3,
    status: 'pending',
    created_at: '2026-07-19T10:15:00Z',
  },
];

describe('EntityConflictsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the page header in every state', async () => {
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue([]);
    render(<EntityConflictsPage />);

    // Anchors the other assertions: proves the page mounted rather than throwing
    // and leaving an empty container, which is how a broken render reads.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Entity Conflicts' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Review potential duplicate entities detected across the workspace memory graph.',
      ),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('No conflicts pending review')).toBeInTheDocument();
    });
  });

  it('renders skeleton placeholders while the request is in flight', () => {
    // A promise that never settles holds the component in its loading branch.
    (apiClient.getPendingConflicts as jest.Mock).mockReturnValue(new Promise(() => {}));
    const { container } = render(<EntityConflictsPage />);

    // The loading state carries no text at all — it is `ConflictSkeletons`, two
    // cards of pulsing blocks. So it is asserted structurally, and exactly: two
    // cards x (one header bar + two entity blocks x two bars) = 10.
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(10);

    // Loading must not be mistakable for either of the other two states.
    expect(screen.queryByText('No conflicts pending review')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Approve merge' })).not.toBeInTheDocument();
  });

  it('renders the empty state when there are no conflicts', async () => {
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue([]);
    render(<EntityConflictsPage />);

    await waitFor(() => {
      expect(screen.getByText('No conflicts pending review')).toBeInTheDocument();
    });
    expect(
      screen.getByText('New potential duplicate entities appear here as documents are ingested.'),
    ).toBeInTheDocument();
    // The empty state is not a skeleton that finished loading.
    expect(document.querySelectorAll('.animate-pulse')).toHaveLength(0);
  });

  it('says the load failed, and does NOT show the empty state', async () => {
    /**
     * This test used to be called "falls back to the empty state when the request
     * fails", and it asserted that a failed load rendered "No conflicts pending
     * review" — a green tick and the sentence "New potential duplicate entities
     * appear here as documents are ingested."
     *
     * `GET /api/conflicts` in fact returned 500 on every call from 2026-08-10
     * (`deps.resolve_principal` has never existed), so this was the state the page
     * was actually in, every time, for four days. The suite was certifying it.
     *
     * "Nothing needs your review" and "we could not ask" are opposite answers.
     * Whichever way the fallback is written, one of the two states has to be
     * unmistakable, and it is this one: an operator who is told the queue is clear
     * stops looking.
     */
    (apiClient.getPendingConflicts as jest.Mock).mockRejectedValue(new Error('network'));
    render(<EntityConflictsPage />);

    await waitFor(() => {
      expect(screen.getByText('Entity conflicts could not be loaded.')).toBeInTheDocument();
    });
    expect(screen.queryByText('No conflicts pending review')).not.toBeInTheDocument();
    // Nor is it left sitting on skeletons, which reads as "still loading".
    expect(document.querySelectorAll('.animate-pulse')).toHaveLength(0);
  });

  it('keeps the card and reports the failure when a resolution is refused', async () => {
    /**
     * The write path had the same shape as the read: `approveConflict` swallowed
     * the failure client-side and answered `{ status: 'approved' }` from a
     * module-level array. The card animated away and the operator was told a merge
     * had been written into an append-only graph that was never touched.
     *
     * A card may only leave the list once the server has said it did.
     */
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue(mockData);
    (apiClient.approveConflict as jest.Mock).mockRejectedValue(new Error('network'));

    render(<EntityConflictsPage />);
    await waitFor(() => {
      expect(screen.getByText('Raj Patel')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Approve merge' })[0]);

    await waitFor(() => {
      expect(screen.getByText('Entity conflicts could not be loaded.')).toBeInTheDocument();
    });
    expect(screen.getByText('Could not reach the server.')).toBeInTheDocument();
  });

  it('renders both entities of a conflict with their quotes and similarity', async () => {
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue(mockData);
    render(<EntityConflictsPage />);

    await waitFor(() => {
      expect(screen.getByText('Raj Patel')).toBeInTheDocument();
    });

    // Both sides of the pair, which is the whole point of the review surface —
    // a reviewer cannot judge a merge from one name.
    expect(screen.getByText('Rajesh Patel')).toBeInTheDocument();

    // Quotes render inside typographic quotation marks (&ldquo;/&rdquo;), so the
    // element's text includes them. Asserted with the marks rather than relaxing
    // to a substring match.
    expect(
      screen.getByText('“Raj Patel expressed concerns about the Q3 pricing model.”'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "“Rajesh Patel strongly disagreed with the board's new direction.”",
      ),
    ).toBeInTheDocument();

    // 0.91 -> "91%", the rounding the card performs.
    expect(screen.getByText('91%')).toBeInTheDocument();
    expect(screen.getByText('82%')).toBeInTheDocument();

    expect(screen.getAllByText('Source context')).toHaveLength(4); // 2 conflicts x 2 entities
  });

  it('approves a conflict and removes only that card', async () => {
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue(mockData);
    (apiClient.approveConflict as jest.Mock).mockResolvedValue({ id: '1', status: 'approved' });

    render(<EntityConflictsPage />);
    await waitFor(() => {
      expect(screen.getByText('Raj Patel')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Approve merge' })[0]);

    expect(apiClient.approveConflict).toHaveBeenCalledWith('1');
    expect(apiClient.approveConflict).toHaveBeenCalledTimes(1);
    expect(apiClient.rejectConflict).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(screen.queryByText('Raj Patel')).not.toBeInTheDocument();
    });
    // The second conflict survives. Asserting only the removal would pass even if
    // the handler cleared the whole list.
    expect(screen.getByText('Sequoia')).toBeInTheDocument();
  });

  it('rejects a conflict through rejectConflict, not approveConflict', async () => {
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue(mockData);
    (apiClient.rejectConflict as jest.Mock).mockResolvedValue({ id: '1', status: 'rejected' });

    render(<EntityConflictsPage />);
    await waitFor(() => {
      expect(screen.getByText('Raj Patel')).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole('button', { name: 'Reject' })[0]);

    // Both actions remove the card, so the observable outcome is identical and a
    // swapped call would otherwise go unnoticed.
    expect(apiClient.rejectConflict).toHaveBeenCalledWith('1');
    expect(apiClient.approveConflict).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(screen.queryByText('Raj Patel')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Sequoia')).toBeInTheDocument();
  });
});
