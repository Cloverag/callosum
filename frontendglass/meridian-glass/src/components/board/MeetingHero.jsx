import Icon from '../Icon'
import { meeting as m } from '../../data'
import { toneText } from '../../tone'

export default function MeetingHero() {
  const r = 34
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - m.readiness / 100)

  return (
    <section>
      <h2 className="text-[1.375rem] leading-tight font-semibold tracking-[-0.01em] text-on-surface mb-4">
        Upcoming meeting
      </h2>

      <div className="os-surface-raised p-6 md:p-8 relative overflow-hidden">
        <div className="absolute -right-24 -top-24 w-72 h-72 bg-primary/5 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 grid grid-cols-1 md:grid-cols-[1.35fr_minmax(0,1fr)] gap-8">
          {/* Identity + readiness + attendees */}
          <div className="flex flex-col">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 mb-4">
              <span className="inline-flex items-center gap-1.5 pl-2 pr-3 py-1 rounded-full bg-surface-container text-on-surface-variant text-label-md">
                <Icon name="schedule" className="text-[14px]" />
                {m.countdown}
              </span>
              <span className="text-label-md text-secondary">{m.when} · {m.location}</span>
            </div>

            <h3 className="text-headline-lg text-on-surface text-balance max-w-[22ch] mb-7">
              {m.title}
            </h3>

            {/* Readiness — the big number */}
            <div className="flex items-center gap-5 mb-3">
              <div className="relative w-[88px] h-[88px] shrink-0">
                <svg className="w-full h-full" viewBox="0 0 80 80">
                  <circle className="text-surface-container" cx="40" cy="40" r={r} fill="transparent" stroke="currentColor" strokeWidth="6" />
                  <circle
                    className="text-success progress-ring__circle"
                    cx="40"
                    cy="40"
                    r={r}
                    fill="transparent"
                    stroke="currentColor"
                    strokeWidth="6"
                    strokeLinecap="round"
                    style={{ strokeDasharray: circumference, strokeDashoffset: offset }}
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="font-mono text-[1.75rem] font-bold text-on-surface leading-none">{m.readiness}</span>
                </div>
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-body-lg font-semibold text-on-surface">Meeting readiness</p>
                  <span className="inline-flex items-center gap-0.5 text-label-md font-medium text-success">
                    <Icon name="arrow_upward" className="text-[13px]" />
                    {m.readinessTrend}
                  </span>
                </div>
                <p className="text-body-sm text-success">On track for Nov 12</p>
                <p className="text-label-md text-secondary mt-1">Led by {m.owner} · Updated {m.updated}</p>
              </div>
            </div>

            <div className="flex items-center gap-3 mt-6">
              <div className="flex -space-x-2">
                {m.attendees.map((a) => (
                  <div
                    key={a.initials}
                    title={a.name}
                    className="w-8 h-8 rounded-full border-2 border-white bg-surface-container text-on-surface-variant flex items-center justify-center text-[11px] font-semibold"
                  >
                    {a.initials}
                  </div>
                ))}
                <div className="w-8 h-8 rounded-full border-2 border-white bg-surface-container-high text-on-surface-variant flex items-center justify-center text-[11px] font-medium">
                  +{m.attendeeTotal - m.attendees.length}
                </div>
              </div>
              <span className="text-label-md text-secondary">{m.attendeeTotal} attending</span>
            </div>
          </div>

          {/* Rich stat column — divided by space, colour carries meaning */}
          <div className="md:pl-8 md:border-l md:border-hairline flex flex-col divide-y divide-hairline">
            {m.stats.map((s) => (
              <div key={s.label} className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0">
                <span className="flex items-center gap-2.5 text-body-sm text-on-surface-variant">
                  <Icon name={s.icon} className={`text-[18px] ${toneText[s.tone]}`} />
                  {s.label}
                </span>
                <span className={`font-mono text-body-lg font-semibold whitespace-nowrap ${toneText[s.tone]}`}>
                  {s.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Quick actions */}
        <div className="relative z-10 flex flex-wrap items-center gap-2 mt-7 pt-6 border-t border-hairline">
          <button className="inline-flex items-center gap-2 bg-primary-container text-on-primary text-button px-4 py-2.5 rounded-xl shadow-sm hover:shadow-md transition-shadow">
            Prepare meeting
            <Icon name="arrow_forward" className="text-sm" />
          </button>
          <button className="inline-flex items-center gap-2 bg-surface-container hover:bg-surface-container-high text-on-surface-variant text-button px-4 py-2.5 rounded-xl transition-colors">
            View agenda
          </button>
          <button className="inline-flex items-center gap-2 bg-surface-container hover:bg-surface-container-high text-on-surface-variant text-button px-4 py-2.5 rounded-xl transition-colors">
            <Icon name="add" className="text-sm" />
            Add note
          </button>
        </div>
      </div>
    </section>
  )
}
