"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { CalendarClock, MapPin, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDayFull, formatTime, startOfDay } from "@/lib/calendar";
import { MEETING_STATUS_LABEL, MEETING_STATUS_TONE, isScheduled, type Meeting } from "@/lib/meetings";

/** "Today" / "Tomorrow" / "in 3 days" — the operator's first read on urgency. */
function relativeDay(start: Date): string {
  const days = Math.round((startOfDay(start).getTime() - startOfDay(new Date()).getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days < 7) return `in ${days} days`;
  if (days < 14) return "next week";
  return `in ${Math.round(days / 7)} weeks`;
}

/**
 * A compact scannable fact in the hero's quick-stat strip.
 *
 * Tinted from `--focal-foreground`, not from the page surface tokens. Those
 * describe a light ground: on the focal surface `surface-sunken` renders a pale
 * chip in light theme and an almost invisible one in dark, because in dark it is
 * the darkest token in the system sitting on an already-dark ramp. A surface
 * that inverts needs its own foreground, which is the whole reason
 * `--focal-foreground` exists rather than reusing `--foreground`.
 */
function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-focal-foreground/10 px-3 py-2">
      <div className="flex items-center gap-1.5 text-focal-foreground/70">
        <span className="[&_svg]:size-3.5" aria-hidden>{icon}</span>
        <span className="text-[10px] font-medium uppercase tracking-[0.08em]">{label}</span>
      </div>
      <div className="mt-1 truncate text-sm font-medium tabular-nums text-focal-foreground">{value}</div>
    </div>
  );
}

export function MeetingHero({ meeting, loading }: { meeting: Meeting | null; loading: boolean }) {
  const router = useRouter();

  /**
   * Loading and empty both render ON the focal surface rather than falling back
   * to a plain card. A focal surface that disappears when the workspace is quiet
   * takes the page's whole hierarchy with it — and quiet is the state this
   * product is actually in most weeks. The skeleton and the empty message are
   * held by the same surface that will hold the meeting.
   */
  if (loading) {
    return (
      <section className="surface-focal-action min-h-[16rem] rounded-[--radius-card] p-8" aria-busy="true">
        <div className="h-3 w-32 rounded bg-focal-foreground/15" />
        <div className="mt-4 h-8 w-2/3 rounded bg-focal-foreground/15" />
        <div className="mt-4 h-5 w-1/2 rounded bg-focal-foreground/15" />
        <div className="mt-5 grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-12 rounded-lg bg-focal-foreground/10" />
          ))}
        </div>
        <div className="mt-6 flex gap-3">
          <div className="h-10 w-32 rounded-[--radius-control] bg-focal-foreground/15" />
          <div className="h-10 w-32 rounded-[--radius-control] bg-focal-foreground/15" />
        </div>
      </section>
    );
  }

  // An unscheduled meeting has no date to headline, so it is treated like no
  // upcoming meeting rather than rendered with a fabricated one.
  if (!meeting || !isScheduled(meeting)) {
    return (
      <section className="surface-focal-action flex min-h-[16rem] flex-col items-center justify-center rounded-[--radius-card] p-8 text-center">
        <CalendarClock className="size-6 text-focal-foreground/70" aria-hidden />
        <h2 className="mt-3 text-lg font-medium text-focal-foreground">No upcoming meetings</h2>
        <p className="mt-1.5 max-w-xs text-sm text-focal-foreground/75">
          Your next board meeting will appear here with its agenda and prep at a glance.
        </p>
        <Button variant="focalGhost" size="sm" className="mt-5" onClick={() => router.push("/calendar")}>
          Open calendar
        </Button>
      </section>
    );
  }

  const start = new Date(meeting.scheduled_start);

  /**
   * The focal surface — elevation level 4, `rules.md` §6 (2026-08-13).
   *
   * The dashboard's problem was never colour: it was twelve cards at one weight,
   * so nothing on the page claimed to matter more than anything else. This is the
   * one surface that does. Hierarchy comes from size, elevation and a display-scale
   * title; the ramp is what makes the weight visible rather than merely stated.
   *
   * `Card` is deliberately not used. Card owns the L1/L2 border-and-shadow
   * treatment for content surfaces, and a focal surface is neither — it carries
   * its own elevation from `.surface-focal-action`.
   */
  return (
    <section className="surface-focal-action flex min-h-[16rem] flex-col rounded-[--radius-card] p-8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-focal-foreground/70">
            Upcoming board meeting
          </span>
          {/* The Display step (1.875rem), the top of the documented ramp. The old
              `text-xl` sat one step above body copy, which is why the page read
              flat. Deliberately NOT a new larger step: the hero already outranks
              the page title by surface and elevation, so buying the same
              hierarchy twice would cost a ramp step to say nothing new. */}
          <h2 className="mt-2 truncate text-3xl font-medium leading-tight tracking-tight text-focal-foreground">
            {meeting.title}
          </h2>
        </div>
        <Badge tone={MEETING_STATUS_TONE[meeting.status]}>{MEETING_STATUS_LABEL[meeting.status]}</Badge>
      </div>

      {/* Prominent when */}
      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-lg font-medium text-focal-foreground">{relativeDay(start)}</span>
        <span className="text-sm tabular-nums text-focal-foreground/75">
          {formatDayFull(start)} · {formatTime(meeting.scheduled_start)} – {formatTime(meeting.scheduled_end)}
        </span>
      </div>

      {/* Quick stats */}
      {/* Agenda readiness and "Clearance Level N" used to sit here. Both came from
          fields the domain has never had: agenda is a separate aggregate, and a
          meeting carries no clearance — that is a property of a membership. A stat
          asserting something the system does not model is the same defect as a
          number nobody measured, so they are gone rather than approximated. */}
      <dl className="mt-5 grid grid-cols-1 gap-3">
        <Stat icon={<MapPin />} label="Location" value={meeting.location ?? "—"} />
      </dl>

      <div className="mt-auto flex flex-wrap items-center gap-3 pt-7">
        {/* Went to /calendar, which is where meetings are listed rather than where one
            is prepared. The prepare flow now exists, so the button leads to it. */}
        <Button variant="focal" size="md" className="px-6" onClick={() => router.push("/prepare")}>
          Prepare meeting
          <ArrowRight className="size-4" />
        </Button>
        <Button variant="focalGhost" size="md" onClick={() => router.push("/calendar")}>
          View agenda
        </Button>
      </div>
    </section>
  );
}
