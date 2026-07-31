"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { LoadFailed, asApiError } from "@/components/ui/load-failed";
import type { ApiError } from "@/lib/http";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  addDays,
  addMonths,
  dayKey,
  formatDayFull,
  formatMonthYear,
  isSameDay,
  isSameMonth,
  isToday,
  monthGrid,
  startOfDay,
  startOfWeek,
  weekDays,
} from "@/lib/calendar";
import {
  scheduledOnly,
  type ScheduledMeeting,
  meetingsApi,
  MEETING_STATUSES,
  MEETING_STATUS_DOT,
  MEETING_STATUS_LABEL,
  type Meeting,
  type MeetingStatus,
} from "@/lib/meetings";
import { MonthView } from "./month-view";
import { WeekView } from "./week-view";
import { DayView } from "./day-view";
import { MeetingDetail } from "./meeting-detail";
import { MeetingForm } from "./meeting-form";

type View = "month" | "week" | "day";
const VIEWS: View[] = ["month", "week", "day"];

function StatusChip({ status, active, onToggle }: { status: MeetingStatus; active: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
        active
          ? "border-accent bg-accent-subtle text-accent-emphasis"
          : "border-border bg-surface-elevated text-muted-foreground hover:text-foreground"
      )}
    >
      <span className={cn("size-1.5 rounded-full", MEETING_STATUS_DOT[status])} aria-hidden />
      {MEETING_STATUS_LABEL[status]}
    </button>
  );
}

export default function CalendarPage() {
  const [view, setView] = useState<View>("month");
  const [cursor, setCursor] = useState(() => new Date());
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Meeting | null>(null);
  const [formDate, setFormDate] = useState<Date | null>(null);
  const [query, setQuery] = useState("");
  const [statuses, setStatuses] = useState<Set<MeetingStatus>>(new Set());
  const [focusedDate, setFocusedDate] = useState<Date>(() => startOfDay(new Date()));

  const load = useCallback(() => {
    meetingsApi.list()
      .then(setMeetings)
      .catch((e) => setError(asApiError(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (meetings ?? []).filter((m) => {
      const matchesQuery =
        !q || m.title.toLowerCase().includes(q) || (m.location?.toLowerCase().includes(q) ?? false);
      const matchesStatus = statuses.size === 0 || statuses.has(m.status);
      return matchesQuery && matchesStatus;
    });
  }, [meetings, query, statuses]);

  const byDay = useMemo(() => {
    // Only meetings with a window can be placed on a calendar. A `draft` has none
    // until it is scheduled, and `scheduledOnly` narrows the type so the compiler —
    // rather than a runtime Invalid Date — is what stops anyone reading the field
    // without checking. Undated meetings still appear on the Meetings list, where
    // they belong; they simply have no cell to sit in here.
    const map = new Map<string, ScheduledMeeting[]>();
    for (const m of scheduledOnly(filtered)) {
      const k = dayKey(new Date(m.scheduled_start));
      const list = map.get(k);
      if (list) list.push(m);
      else map.set(k, [m]);
    }
    return map;
  }, [filtered]);

  const toggleStatus = (s: MeetingStatus) =>
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  const filtersActive = query.trim() !== "" || statuses.size > 0;

  const shift = (dir: number) =>
    setCursor((c) => (view === "month" ? addMonths(c, dir) : addDays(c, view === "week" ? dir * 7 : dir)));

  const label = useMemo(() => {
    if (view === "month") return formatMonthYear(cursor);
    if (view === "day") return formatDayFull(cursor);
    const d = weekDays(cursor);
    const fmt = (x: Date) => x.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    return `${fmt(d[0])} – ${fmt(d[6])}`;
  }, [view, cursor]);

  // Keyboard navigation. `active` is the day that carries roving focus — the
  // focused day if it's on-screen, otherwise a sensible visible fallback so the
  // grid always has exactly one tabbable cell.
  const visibleDays = useMemo(
    () => (view === "month" ? monthGrid(cursor) : view === "week" ? weekDays(cursor) : [startOfDay(cursor)]),
    [view, cursor]
  );

  const active = useMemo(
    () =>
      visibleDays.find((d) => isSameDay(d, focusedDate)) ??
      visibleDays.find((d) => isToday(d)) ??
      visibleDays[0],
    [visibleDays, focusedDate]
  );

  // Move focus to `d`, shifting the visible period when the day falls off-grid.
  const goToDate = useCallback(
    (d: Date) => {
      const day = startOfDay(d);
      setFocusedDate(day);
      setCursor((c) => {
        if (view === "month") return isSameMonth(day, c) ? c : day;
        if (view === "week") return isSameDay(startOfWeek(day), startOfWeek(c)) ? c : day;
        return day;
      });
    },
    [view]
  );

  const newMeetingOn = useCallback((d: Date) => {
    setEditing(null);
    setFormDate(startOfDay(d));
    setFormOpen(true);
  }, []);

  return (
    <div className="p-6">
      <PageHeader
        title="Calendar"
        description="Board meetings across the Acme Corp workspace."
        icon={<CalendarDays />}
        actions={
          <>
            <div className="inline-flex rounded-md border border-border bg-surface-elevated p-0.5">
              {VIEWS.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setView(v)}
                  aria-pressed={view === v}
                  className={cn(
                    "rounded px-2.5 py-1 text-xs font-medium capitalize transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus",
                    view === v ? "bg-surface-raised text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {v}
                </button>
              ))}
            </div>

            <Button variant="secondary" size="sm" onClick={() => goToDate(new Date())}>
              Today
            </Button>

            <div className="flex items-center gap-1">
              <Button variant="ghost" size="sm" aria-label="Previous" onClick={() => shift(-1)}>
                <ChevronLeft className="size-4" />
              </Button>
              <span className="min-w-[10rem] text-center text-sm font-medium text-foreground">{label}</span>
              <Button variant="ghost" size="sm" aria-label="Next" onClick={() => shift(1)}>
                <ChevronRight className="size-4" />
              </Button>
            </div>

            <Button
              size="sm"
              onClick={() => {
                setEditing(null);
                setFormDate(null);
                setFormOpen(true);
              }}
            >
              <Plus className="size-4" />
              New meeting
            </Button>
          </>
        }
      />

      {/* Stated once, above the grid. Without it a failed load renders an empty
          calendar — a confident claim that there are no meetings, when the truth is
          that we could not find out. */}
      {error && (
        <div className="mt-6">
          <LoadFailed what="Meetings" error={error} />
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Input
          icon={<Search />}
          type="search"
          placeholder="Search meetings…"
          aria-label="Search meetings"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full sm:w-64"
        />
        <div className="flex flex-wrap items-center gap-1.5">
          {MEETING_STATUSES.map((s) => (
            <StatusChip key={s} status={s} active={statuses.has(s)} onToggle={() => toggleStatus(s)} />
          ))}
        </div>
        {filtersActive && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQuery("");
              setStatuses(new Set());
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {view === "month" && (
        <MonthView
          cursor={cursor}
          byDay={byDay}
          active={active}
          onSelect={setSelected}
          onNavigate={goToDate}
          onActivate={newMeetingOn}
        />
      )}
      {view === "week" && (
        <WeekView
          cursor={cursor}
          byDay={byDay}
          active={active}
          onSelect={setSelected}
          onNavigate={goToDate}
          onActivate={newMeetingOn}
        />
      )}
      {view === "day" && (
        <DayView cursor={cursor} byDay={byDay} onSelect={setSelected} onNavigate={goToDate} />
      )}

      <MeetingDetail
        meeting={selected}
        onClose={() => setSelected(null)}
        onEdit={(m) => {
          setSelected(null);
          setEditing(m);
          setFormOpen(true);
        }}
      />
      <MeetingForm
        open={formOpen}
        editing={editing}
        defaultDate={formDate}
        onClose={() => setFormOpen(false)}
        onSaved={load}
      />
    </div>
  );
}
