import Icon from '../Icon'
import { brief } from '../../data'
import { toneSoft } from '../../tone'

export default function DailyBrief() {
  return (
    <section className="pt-1">
      <p className="text-label-md text-secondary mb-2">{brief.date}</p>
      <h1 className="text-display-lg text-on-surface text-balance">{brief.greeting}</h1>
      <p className="text-body-lg text-on-surface-variant mt-3 max-w-[58ch] text-pretty">
        {brief.summary}
      </p>
      <div className="flex flex-wrap gap-2 mt-6">
        {brief.chips.map((chip) => (
          <span
            key={chip.label}
            className={`inline-flex items-center gap-1.5 pl-2.5 pr-3.5 py-1.5 rounded-full text-body-sm font-medium ${
              chip.tone === 'neutral' ? 'os-surface-quiet text-on-surface-variant' : toneSoft[chip.tone]
            }`}
          >
            <Icon name={chip.icon} className="text-[16px]" />
            {chip.label}
          </span>
        ))}
      </div>
    </section>
  )
}
