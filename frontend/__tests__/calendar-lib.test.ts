import {
  WEEKDAYS,
  addDays,
  addMonths,
  dayKey,
  isSameDay,
  isSameMonth,
  monthGrid,
  startOfDay,
  startOfMonth,
  startOfWeek,
  weekDays,
} from '../src/lib/calendar';

/**
 * The calendar's date maths, tested without rendering anything.
 *
 * `src/lib/calendar.ts` uses native `Date` with no date library, which means
 * every off-by-one that libraries normally absorb — Sunday-vs-Monday week
 * starts, month rollover, DST — is this module's problem. These are the cases
 * where hand-rolled date code actually breaks, rather than a restatement of the
 * implementation.
 *
 * Months are 0-indexed in `Date`, so `new Date(2026, 6, 1)` is 1 July 2026.
 */

describe('startOfWeek is Monday-based', () => {
  it('treats Monday as the start of its own week', () => {
    // 6 July 2026 is a Monday.
    const monday = new Date(2026, 6, 6);
    expect(isSameDay(startOfWeek(monday), monday)).toBe(true);
  });

  it('maps Sunday back to the PRECEDING Monday, not the following one', () => {
    // The single most likely bug in a Monday-based calendar: JS `getDay()` makes
    // Sunday 0, so a naive implementation sends Sunday forward six days.
    const sunday = new Date(2026, 6, 12); // Sunday
    expect(sunday.getDay()).toBe(0);
    expect(startOfWeek(sunday)).toEqual(startOfDay(new Date(2026, 6, 6)));
  });

  it('maps every day of one week to the same Monday', () => {
    const monday = startOfDay(new Date(2026, 6, 6));
    for (let i = 0; i < 7; i++) {
      expect(startOfWeek(addDays(monday, i))).toEqual(monday);
    }
  });

  it('crosses a month boundary backwards', () => {
    // 1 July 2026 is a Wednesday, so its week starts in June.
    const firstOfJuly = new Date(2026, 6, 1);
    expect(startOfWeek(firstOfJuly)).toEqual(startOfDay(new Date(2026, 5, 29)));
  });

  it('zeroes the time component', () => {
    const afternoon = new Date(2026, 6, 8, 15, 42, 17, 500);
    const start = startOfWeek(afternoon);
    expect([start.getHours(), start.getMinutes(), start.getSeconds(), start.getMilliseconds()]).toEqual([0, 0, 0, 0]);
  });
});

describe('monthGrid', () => {
  it('always returns exactly 42 cells', () => {
    // A fixed 6x7 grid is what keeps the month view from reflowing between
    // months. February 2027 starts on a Monday and has 28 days — the case that
    // would produce a short grid if the length were computed from the month.
    for (const d of [new Date(2026, 6, 1), new Date(2027, 1, 1), new Date(2026, 10, 1)]) {
      expect(monthGrid(d)).toHaveLength(42);
    }
  });

  it('starts on the Monday on or before the 1st', () => {
    // July 2026 begins on a Wednesday, so the grid opens with 29 June.
    const grid = monthGrid(new Date(2026, 6, 15));
    expect(grid[0]).toEqual(startOfDay(new Date(2026, 5, 29)));
    expect(WEEKDAYS[0]).toBe('Mon');
  });

  it('is contiguous — every cell is one day after the last', () => {
    const grid = monthGrid(new Date(2026, 6, 15));
    for (let i = 1; i < grid.length; i++) {
      expect(grid[i]).toEqual(addDays(grid[i - 1], 1));
    }
  });

  it('contains every day of the target month', () => {
    const grid = monthGrid(new Date(2026, 6, 15));
    const inJuly = grid.filter((d) => isSameMonth(d, new Date(2026, 6, 1)));
    expect(inJuly).toHaveLength(31);
    expect(inJuly[0].getDate()).toBe(1);
    expect(inJuly[30].getDate()).toBe(31);
  });

  it('pads with leading and trailing days from the neighbouring months', () => {
    const grid = monthGrid(new Date(2026, 6, 15));
    expect(isSameMonth(grid[0], new Date(2026, 5, 1))).toBe(true); // June
    expect(isSameMonth(grid[41], new Date(2026, 7, 1))).toBe(true); // August
  });

  it('gives the same grid for any day within the month', () => {
    // The grid is a property of the month, not of the cursor's day.
    expect(monthGrid(new Date(2026, 6, 1))).toEqual(monthGrid(new Date(2026, 6, 31)));
  });
});

describe('weekDays', () => {
  it('returns 7 consecutive days beginning on Monday', () => {
    const days = weekDays(new Date(2026, 6, 9)); // a Thursday
    expect(days).toHaveLength(7);
    expect(days[0]).toEqual(startOfDay(new Date(2026, 6, 6)));
    expect(days[6]).toEqual(startOfDay(new Date(2026, 6, 12)));
    expect(days[0].getDay()).toBe(1); // Monday
    expect(days[6].getDay()).toBe(0); // Sunday
  });
});

describe('addMonths', () => {
  it('moves forward and back, normalising to the 1st', () => {
    expect(addMonths(new Date(2026, 6, 15), 1)).toEqual(new Date(2026, 7, 1));
    expect(addMonths(new Date(2026, 6, 15), -1)).toEqual(new Date(2026, 5, 1));
  });

  it('rolls across a year boundary in both directions', () => {
    expect(addMonths(new Date(2026, 11, 10), 1)).toEqual(new Date(2027, 0, 1));
    expect(addMonths(new Date(2026, 0, 10), -1)).toEqual(new Date(2025, 11, 1));
  });

  it('does not overflow from the end of a long month into the wrong month', () => {
    // The classic bug: 31 January + 1 month lands on 31 February, which JS
    // normalises to 3 March. Normalising to the 1st is what avoids it.
    expect(addMonths(new Date(2026, 0, 31), 1)).toEqual(new Date(2026, 1, 1));
  });
});

describe('addDays', () => {
  it('crosses month and year boundaries', () => {
    expect(addDays(new Date(2026, 6, 31), 1)).toEqual(new Date(2026, 7, 1));
    expect(addDays(new Date(2026, 11, 31), 1)).toEqual(new Date(2027, 0, 1));
    expect(addDays(new Date(2026, 0, 1), -1)).toEqual(new Date(2025, 11, 31));
  });

  it('handles a leap day', () => {
    expect(addDays(new Date(2028, 1, 28), 1)).toEqual(new Date(2028, 1, 29));
    expect(addDays(new Date(2028, 1, 29), 1)).toEqual(new Date(2028, 2, 1));
  });

  it('does not mutate its argument', () => {
    const original = new Date(2026, 6, 15);
    addDays(original, 10);
    expect(original).toEqual(new Date(2026, 6, 15));
  });
});

describe('dayKey', () => {
  it('is local, zero-padded yyyy-mm-dd', () => {
    expect(dayKey(new Date(2026, 6, 9))).toBe('2026-07-09');
    expect(dayKey(new Date(2026, 11, 25))).toBe('2026-12-25');
  });

  it('does not shift across the local/UTC boundary', () => {
    // The reason this exists rather than `toISOString().slice(0, 10)`: late-
    // evening local times are already tomorrow in UTC, which would file a
    // meeting into the wrong day cell for anyone east or west of Greenwich.
    const lateEvening = new Date(2026, 6, 9, 23, 30);
    expect(dayKey(lateEvening)).toBe('2026-07-09');
    const earlyMorning = new Date(2026, 6, 9, 0, 30);
    expect(dayKey(earlyMorning)).toBe('2026-07-09');
  });

  it('is stable regardless of time of day', () => {
    const morning = new Date(2026, 6, 9, 8, 0);
    const night = new Date(2026, 6, 9, 22, 0);
    expect(dayKey(morning)).toBe(dayKey(night));
  });
});

describe('isSameDay / isSameMonth', () => {
  it('compares calendar position, not elapsed time', () => {
    expect(isSameDay(new Date(2026, 6, 9, 1, 0), new Date(2026, 6, 9, 23, 0))).toBe(true);
    // 23 hours apart but different days.
    expect(isSameDay(new Date(2026, 6, 9, 23, 0), new Date(2026, 6, 10, 22, 0))).toBe(false);
  });

  it('does not confuse the same month in different years', () => {
    expect(isSameMonth(new Date(2026, 6, 9), new Date(2027, 6, 9))).toBe(false);
    expect(isSameMonth(new Date(2026, 6, 1), new Date(2026, 6, 31))).toBe(true);
  });
});

describe('startOfMonth', () => {
  it('returns midnight on the 1st', () => {
    expect(startOfMonth(new Date(2026, 6, 20, 14, 30))).toEqual(new Date(2026, 6, 1));
  });
});
