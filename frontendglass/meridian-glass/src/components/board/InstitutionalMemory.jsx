import Icon from '../Icon'
import Section from '../Section'
import { memory } from '../../data'
import { toneVar } from '../../tone'

// The knowledge graph — the ONE surface that carries violet (its identity).
// Verification uses semantic green/amber/red; violet stays the brand accent.
export default function InstitutionalMemory() {
  const r = 40
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - memory.graphHealth / 100)

  return (
    <Section
      title="Institutional Memory"
      action={
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-tertiary/10 text-tertiary text-label-md">
          <Icon name="account_tree" className="text-[14px]" />
          Knowledge graph
        </span>
      }
    >
      <div className="os-surface p-6 md:p-7 flex flex-col gap-6">
        {/* Graph health + verification */}
        <div className="flex flex-col sm:flex-row items-center gap-6">
          <div className="relative w-32 h-32 shrink-0">
            <svg className="w-full h-full" viewBox="0 0 100 100">
              <circle className="text-tertiary/15" cx="50" cy="50" r={r} fill="transparent" stroke="currentColor" strokeWidth="9" />
              <circle
                className="text-tertiary progress-ring__circle drop-shadow-[0_0_8px_rgba(124,58,237,0.35)]"
                cx="50"
                cy="50"
                r={r}
                fill="transparent"
                stroke="currentColor"
                strokeWidth="9"
                strokeLinecap="round"
                style={{ strokeDasharray: circumference, strokeDashoffset: offset }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="font-mono text-[2.5rem] font-bold text-tertiary leading-none">
                {memory.graphHealth}
                <span className="text-lg">%</span>
              </span>
            </div>
          </div>

          <div className="flex-1 w-full">
            <p className="text-body-lg font-semibold text-on-surface mb-0.5">Graph health: Strong</p>
            <p className="text-label-md text-secondary mb-4">
              Confidence {memory.confidence} · Updated {memory.updated}
            </p>
            {/* Segmented verification bar */}
            <div className="flex h-2.5 rounded-full overflow-hidden mb-3">
              {memory.verification.map((v) => (
                <div key={v.label} style={{ width: `${v.value}%`, background: toneVar[v.tone] }} />
              ))}
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-1.5">
              {memory.verification.map((v) => (
                <span key={v.label} className="inline-flex items-center gap-1.5 text-label-md text-secondary">
                  <span className="w-2 h-2 rounded-full" style={{ background: toneVar[v.tone] }} />
                  {v.label}
                  <span className="font-mono font-semibold text-on-surface">{v.value}%</span>
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Graph stats — big numbers */}
        <div className="grid grid-cols-3 border-t border-hairline pt-5">
          {memory.stats.map((s) => (
            <div key={s.label}>
              <p className="font-mono text-[1.75rem] font-bold text-on-surface leading-none">{s.value}</p>
              <p className="text-label-md text-secondary mt-1.5">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Recently verified facts */}
        <div className="border-t border-hairline pt-5">
          <p className="text-label-md text-secondary mb-3">Recently verified</p>
          <div className="flex flex-col gap-3">
            {memory.recentFacts.map((f) => (
              <div key={f.text} className="flex items-start gap-2.5">
                <Icon name="verified" className="text-success text-[18px] mt-0.5 shrink-0" />
                <p className="text-body-sm text-on-surface">
                  {f.text}
                  <span className="text-secondary"> · {f.source}</span>
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Trend footer */}
        <div className="flex items-center justify-between border-t border-hairline pt-4">
          <span className="flex items-center gap-2 text-label-md text-secondary">
            <Icon name="hub" className="text-[18px]" />
            {memory.provenanceSources} sources · {memory.coverage}% coverage
          </span>
          <span className="inline-flex items-center gap-1.5 text-body-sm font-medium text-success">
            <Icon name="trending_up" className="text-[18px]" />
            <span className="font-mono">{memory.throughput}</span>
            <span className="text-secondary font-normal">{memory.throughputWindow}</span>
          </span>
        </div>
      </div>
    </Section>
  )
}
