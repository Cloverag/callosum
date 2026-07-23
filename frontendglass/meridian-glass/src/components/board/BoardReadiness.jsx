import Icon from '../Icon'
import Section from '../Section'
import { readiness } from '../../data'
import { toneText, toneVar } from '../../tone'

export default function BoardReadiness() {
  return (
    <Section title="Board readiness">
      <div className="flex items-start justify-between gap-4 mb-7">
        <div>
          <div className="font-mono text-[3.25rem] font-bold text-on-surface leading-none tracking-tight">
            {readiness.overall}
            <span className="text-[2rem] text-secondary">%</span>
          </div>
          <p className="text-body-sm text-secondary mt-1.5">ready for the board</p>
        </div>
        <div className="text-right shrink-0">
          <span className="inline-flex items-center gap-1 text-body-sm font-medium text-success">
            <Icon name="arrow_upward" className="text-[14px]" />
            {readiness.trend} {readiness.trendWindow}
          </span>
          <p className="text-label-md text-secondary mt-1">Updated {readiness.updated}</p>
        </div>
      </div>

      <div className="flex flex-col gap-5">
        {readiness.breakdown.map((b) => (
          <div key={b.label}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-body-sm font-medium text-on-surface">{b.label}</span>
              <span className="flex items-center gap-2.5">
                <span className={`text-label-md ${toneText[b.tone]}`}>{b.note}</span>
                <span className="font-mono text-body-sm font-semibold text-on-surface">{b.value}%</span>
              </span>
            </div>
            <div className="h-2 rounded-full bg-surface-container overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{ width: `${b.value}%`, background: toneVar[b.tone] }}
              />
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}
