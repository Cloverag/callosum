import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import CalendarPage from '../src/app/calendar/page';
import { meetingsApi, type Meeting } from '../src/lib/meetings';
import { agendaApi } from '../src/lib/agenda';

/**
 * The Calendar page: month / week / day views, search, status filters, the
 * detail dialog, and roving-focus keyboard navigation.
 *
 * Two things make this page awkward to test, both handled once here rather than
 * in each case:
 *
 * 1. **The cursor defaults to `new Date()`.** Every assertion about which month
 *    is on screen would start failing the moment real time moved past it, so the
 *    clock is pinned to 15 July 2026 — mid-month, mid-week, well away from any
 *    boundary that could mask an off-by-one.
 * 2. **`meetingsApi` is mocked, the rest of the module is not.** The page also
 *    imports `MEETING_STATUSES` and the label/tone maps from there, and those
 *    must stay real — a test that mocked them would pass against status values
 *    the domain does not have.
 *
 * `AnimatePresence` is exercised here (the detail dialog opens and closes) and
 * works under jsdom. #28 was filed as blocked on the belief that it does not;
 * see #15, where that diagnosis turned out to be a stale assertion instead.
 */

jest.mock('../src/lib/meetings', () => {
  const actual = jest.requireActual('../src/lib/meetings');
  return {
    ...actual,
    meetingsApi: {
      list: jest.fn(),
      get: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
    },
  };
});

jest.mock('../src/lib/agenda', () => ({
  agendaApi: { list: jest.fn(), get: jest.fn() },
}));

const listMock = meetingsApi.list as jest.Mock;
const agendaMock = agendaApi.list as jest.Mock;

/** Wednesday, mid-month, mid-week — no boundary to hide an off-by-one behind. */
const TODAY = new Date(2026, 6, 15, 9, 0, 0);

function meeting(overrides: Partial<Meeting> & Pick<Meeting, 'id' | 'title' | 'start'>): Meeting {
  return {
    status: 'scheduled',
    end: overrides.start,
    ...overrides,
  } as Meeting;
}

const MEETINGS: Meeting[] = [
  meeting({
    id: 'm-board',
    title: 'Board Meeting #14',
    status: 'completed',
    start: '2026-07-09T10:00:00',
    end: '2026-07-09T11:30:00',
    location: 'Boardroom',
  }),
  meeting({
    id: 'm-q3',
    title: 'Q3 Board Meeting',
    status: 'in_progress',
    start: '2026-07-15T09:00:00',
    end: '2026-07-15T12:00:00',
    location: 'Zoom',
  }),
  meeting({
    id: 'm-comp',
    title: 'Comp Committee Sync',
    status: 'scheduled',
    start: '2026-07-15T14:00:00',
    end: '2026-07-15T15:00:00',
  }),
  meeting({
    // Deliberately in August: it must never appear while July is on screen.
    id: 'm-august',
    title: 'August Planning',
    status: 'draft',
    start: '2026-08-05T10:00:00',
    end: '2026-08-05T11:00:00',
  }),
];

/** The `data-daykey` cell for a given local date, as the grid renders it. */
function dayCell(container: HTMLElement, key: string): HTMLElement {
  const cell = container.querySelector<HTMLElement>(`[data-daykey="${key}"]`);
  if (!cell) throw new Error(`no day cell for ${key}`);
  return cell;
}

async function renderCalendar(meetings: Meeting[] = MEETINGS) {
  listMock.mockResolvedValue(meetings);
  const utils = render(<CalendarPage />);
  if (meetings.length > 0) {
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /Q3 Board Meeting/i }).length).toBeGreaterThan(0);
    });
  }
  return utils;
}

beforeAll(() => {
  jest.useFakeTimers({ now: TODAY, doNotFake: ['queueMicrotask', 'nextTick'] });
});

afterAll(() => {
  jest.useRealTimers();
});

beforeEach(() => {
  jest.clearAllMocks();
  // Agenda is a separate aggregate as of CP-C, so the detail dialog fetches it
  // rather than reading it off the meeting.
  agendaMock.mockResolvedValue([
    {
      id: 'a1',
      meeting_id: 'm-board',
      workspace_id: 'w',
      title: 'Q2 metrics review',
      description: null,
      duration_minutes: 20,
      presenter: 'Raj Malhotra',
      position: 1,
      version: 1,
      created_at: '2026-07-01T09:00:00Z',
      updated_at: '2026-07-01T09:00:00Z',
    },
  ]);
});

describe('month view', () => {
  it('renders a 6x7 grid with Monday-first weekday headers', async () => {
    const { container } = await renderCalendar();

    expect(container.querySelectorAll('[data-daykey]')).toHaveLength(42);
    const headers = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    for (const h of headers) expect(screen.getByText(h)).toBeInTheDocument();
  });

  it('opens on the current month and spans the neighbouring ones', async () => {
    const { container } = await renderCalendar();

    expect(screen.getByText('July 2026')).toBeInTheDocument();
    // July 2026 starts on a Wednesday, so the grid opens on 29 June and runs to
    // 9 August.
    expect(container.querySelector('[data-daykey="2026-06-29"]')).toBeInTheDocument();
    expect(container.querySelector('[data-daykey="2026-08-09"]')).toBeInTheDocument();
  });

  it('places each meeting in its own day cell', async () => {
    const { container } = await renderCalendar();

    expect(
      within(dayCell(container, '2026-07-09')).getByText('Board Meeting #14'),
    ).toBeInTheDocument();

    // Two meetings on the 15th, both in that cell and nowhere else.
    const fifteenth = within(dayCell(container, '2026-07-15'));
    expect(fifteenth.getByText('Q3 Board Meeting')).toBeInTheDocument();
    expect(fifteenth.getByText('Comp Committee Sync')).toBeInTheDocument();
    expect(within(dayCell(container, '2026-07-09')).queryByText('Q3 Board Meeting')).toBeNull();
  });

  it('renders an out-of-month meeting only in the padded cell that holds it', async () => {
    const { container } = await renderCalendar();
    // 5 August is outside July but inside the 42-cell grid, so it does show.
    expect(
      within(dayCell(container, '2026-08-05')).getByText('August Planning'),
    ).toBeInTheDocument();
  });

  it('labels each day cell with its meeting count', async () => {
    const { container } = await renderCalendar();

    // The count is the only thing a screen-reader user has to tell a busy day
    // from an empty one, since the chips are visual.
    expect(dayCell(container, '2026-07-15')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('2 meetings'),
    );
    expect(dayCell(container, '2026-07-09')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('1 meeting'),
    );
    expect(dayCell(container, '2026-07-10')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('no meetings'),
    );
  });

  it('renders the grid before meetings arrive, without crashing', () => {
    listMock.mockReturnValue(new Promise(() => {}));
    const { container } = render(<CalendarPage />);

    expect(container.querySelectorAll('[data-daykey]')).toHaveLength(42);
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();
  });

  it('renders an empty grid when there are no meetings at all', async () => {
    listMock.mockResolvedValue([]);
    const { container } = render(<CalendarPage />);

    await waitFor(() => {
      expect(container.querySelectorAll('[data-daykey]')).toHaveLength(42);
    });
    expect(screen.queryByRole('button', { name: /Board Meeting/i })).not.toBeInTheDocument();
  });
});

describe('period navigation is view-aware', () => {
  it('moves a whole month in month view', async () => {
    await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('August 2026')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(screen.getByText('June 2026')).toBeInTheDocument();
  });

  it('moves seven days in week view', async () => {
    const { container } = await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: 'week' }));
    // Week of Monday 13 July.
    expect(container.querySelector('[data-daykey="2026-07-13"]')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-daykey]')).toHaveLength(7);

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(container.querySelector('[data-daykey="2026-07-20"]')).toBeInTheDocument();
    expect(container.querySelector('[data-daykey="2026-07-13"]')).toBeNull();
  });

  it('moves one day in day view', async () => {
    await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: 'day' }));
    expect(screen.getByText('Q3 Board Meeting')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    // 16 July has nothing on it.
    expect(screen.getByText(/No meetings on/)).toBeInTheDocument();
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();
  });

  it('returns to today from another month', async () => {
    await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('August 2026')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Today' }));
    expect(screen.getByText('July 2026')).toBeInTheDocument();
  });
});

describe('view switcher', () => {
  it('shows one view at a time and marks the active button', async () => {
    const { container } = await renderCalendar();

    expect(screen.getByRole('button', { name: 'month' })).toHaveAttribute('aria-pressed', 'true');
    expect(container.querySelectorAll('[data-daykey]')).toHaveLength(42);

    fireEvent.click(screen.getByRole('button', { name: 'week' }));
    expect(screen.getByRole('button', { name: 'week' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'month' })).toHaveAttribute('aria-pressed', 'false');
    expect(container.querySelectorAll('[data-daykey]')).toHaveLength(7);

    // Day view is a list, not a day grid, so it has no day cells at all.
    fireEvent.click(screen.getByRole('button', { name: 'day' }));
    expect(container.querySelectorAll('[data-daykey]')).toHaveLength(0);
  });
});

describe('search and status filters', () => {
  it('narrows by title, case-insensitively', async () => {
    await renderCalendar();

    fireEvent.change(screen.getByLabelText('Search meetings'), { target: { value: 'comp' } });

    expect(screen.getByText('Comp Committee Sync')).toBeInTheDocument();
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();
    expect(screen.queryByText('Board Meeting #14')).not.toBeInTheDocument();
  });

  it('narrows by location as well as title', async () => {
    await renderCalendar();

    fireEvent.change(screen.getByLabelText('Search meetings'), { target: { value: 'boardroom' } });

    // Matched on location, which is not rendered on the chip — so this passes
    // only if the filter really reads `location`.
    expect(screen.getByText('Board Meeting #14')).toBeInTheDocument();
    expect(screen.queryByText('Comp Committee Sync')).not.toBeInTheDocument();
  });

  it('filters by status, and multiple statuses are a union', async () => {
    await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: /Completed/ }));
    expect(screen.getByText('Board Meeting #14')).toBeInTheDocument();
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();

    // Adding a second status widens rather than narrowing.
    fireEvent.click(screen.getByRole('button', { name: /In progress/ }));
    expect(screen.getByText('Board Meeting #14')).toBeInTheDocument();
    expect(screen.getByText('Q3 Board Meeting')).toBeInTheDocument();
    expect(screen.queryByText('Comp Committee Sync')).not.toBeInTheDocument();
  });

  it('combines search and status as an intersection', async () => {
    await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: /Scheduled/ }));
    fireEvent.change(screen.getByLabelText('Search meetings'), { target: { value: 'board' } });

    // "Board Meeting #14" matches the query but is completed; "Comp Committee
    // Sync" is scheduled but does not match. Neither survives both.
    expect(screen.queryByText('Board Meeting #14')).not.toBeInTheDocument();
    expect(screen.queryByText('Comp Committee Sync')).not.toBeInTheDocument();
  });

  it('applies filters in week and day views too', async () => {
    await renderCalendar();

    fireEvent.click(screen.getByRole('button', { name: 'week' }));
    fireEvent.change(screen.getByLabelText('Search meetings'), { target: { value: 'comp' } });
    expect(screen.getByText('Comp Committee Sync')).toBeInTheDocument();
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'day' }));
    expect(screen.getByText('Comp Committee Sync')).toBeInTheDocument();
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();
  });

  it('clears every filter at once', async () => {
    await renderCalendar();

    fireEvent.change(screen.getByLabelText('Search meetings'), { target: { value: 'comp' } });
    fireEvent.click(screen.getByRole('button', { name: /Scheduled/ }));
    expect(screen.queryByText('Q3 Board Meeting')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));

    expect(screen.getByText('Q3 Board Meeting')).toBeInTheDocument();
    expect(screen.getByText('Board Meeting #14')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Scheduled/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('offers no Clear control until a filter is active', async () => {
    await renderCalendar();

    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search meetings'), { target: { value: 'x' } });
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
  });
});

describe('meeting detail dialog', () => {
  it('opens on click and shows the meeting', async () => {
    await renderCalendar();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /Board Meeting #14/i })[0]);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Board Meeting #14')).toBeInTheDocument();

    // The agenda arrives from its own endpoint, keyed on the meeting.
    await waitFor(() => {
      expect(within(dialog).getByText('Q2 metrics review')).toBeInTheDocument();
    });
    expect(agendaMock).toHaveBeenCalledWith('m-board');
  });

  it('closes from both the header and the footer', async () => {
    await renderCalendar();

    async function openDetail() {
      fireEvent.click(screen.getAllByRole('button', { name: /Q3 Board Meeting/i })[0]);
      return screen.findByRole('dialog');
    }

    // The dialog offers two close affordances — the header ✕ and a footer
    // button, both named "Close". Testing only one would leave the other free to
    // regress, so both are exercised in DOM order.
    let dialog = await openDetail();
    expect(within(dialog).getAllByRole('button', { name: 'Close' })).toHaveLength(2);

    fireEvent.click(within(dialog).getAllByRole('button', { name: 'Close' })[0]); // header ✕
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    dialog = await openDetail();
    fireEvent.click(within(dialog).getAllByRole('button', { name: 'Close' })[1]); // footer
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});

describe('keyboard navigation', () => {
  it('makes exactly one day cell tabbable', async () => {
    const { container } = await renderCalendar();

    const tabbable = container.querySelectorAll('[data-daykey][tabindex="0"]');
    expect(tabbable).toHaveLength(1);
    // Roving focus starts on today.
    expect(tabbable[0]).toHaveAttribute('data-daykey', '2026-07-15');
  });

  it('moves left and right by one day', async () => {
    const { container } = await renderCalendar();
    const start = dayCell(container, '2026-07-15');
    start.focus();

    fireEvent.keyDown(start, { key: 'ArrowRight' });
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-16',
    );

    fireEvent.keyDown(dayCell(container, '2026-07-16'), { key: 'ArrowLeft' });
    fireEvent.keyDown(dayCell(container, '2026-07-15'), { key: 'ArrowLeft' });
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-14',
    );
  });

  it('moves a whole week with up and down', async () => {
    const { container } = await renderCalendar();
    const start = dayCell(container, '2026-07-15');
    start.focus();

    fireEvent.keyDown(start, { key: 'ArrowDown' });
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-22',
    );

    fireEvent.keyDown(dayCell(container, '2026-07-22'), { key: 'ArrowUp' });
    fireEvent.keyDown(dayCell(container, '2026-07-15'), { key: 'ArrowUp' });
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-08',
    );
  });

  it('jumps to the start and end of the week with Home and End', async () => {
    const { container } = await renderCalendar();
    const start = dayCell(container, '2026-07-15'); // Wednesday
    start.focus();

    fireEvent.keyDown(start, { key: 'Home' });
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-13',
    ); // Monday

    fireEvent.keyDown(dayCell(container, '2026-07-13'), { key: 'End' });
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-19',
    ); // Sunday
  });

  it('shifts the visible month when navigation leaves the grid', async () => {
    const { container } = await renderCalendar();
    const start = dayCell(container, '2026-07-15');
    start.focus();

    // Five weeks forward lands on 19 August, past the end of July's grid.
    for (const key of ['ArrowDown', 'ArrowDown', 'ArrowDown', 'ArrowDown', 'ArrowDown']) {
      const current = container.querySelector<HTMLElement>('[data-daykey][tabindex="0"]')!;
      fireEvent.keyDown(current, { key });
    }

    expect(screen.getByText('August 2026')).toBeInTheDocument();
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-08-19',
    );
  });

  it('opens the new-meeting form on Enter', async () => {
    const { container } = await renderCalendar();
    const cell = dayCell(container, '2026-07-16');
    cell.focus();

    fireEvent.keyDown(cell, { key: 'ArrowLeft' }); // move focus onto the 15th
    fireEvent.keyDown(dayCell(container, '2026-07-15'), { key: 'Enter' });

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('ignores arrow keys pressed on a meeting chip inside a cell', async () => {
    const { container } = await renderCalendar();

    const chip = screen.getAllByRole('button', { name: /Q3 Board Meeting/i })[0];
    fireEvent.keyDown(chip, { key: 'ArrowRight' });

    // The chip is not a day cell, so the grid must not move focus — otherwise
    // arrowing through a day's meetings would silently change the date.
    expect(container.querySelector('[data-daykey][tabindex="0"]')).toHaveAttribute(
      'data-daykey',
      '2026-07-15',
    );
  });
});
