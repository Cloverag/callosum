import Icon from '../Icon'
import Section from '../Section'
import { needsYou } from '../../data'
import { toneSoft } from '../../tone'

export default function NeedsYou() {
  return (
    <Section
      title="Needs you"
      action={<button className="text-primary text-label-md hover:underline">View all</button>}
    >
      <div className="flex flex-col divide-y divide-hairline">
        {needsYou.map((item) => (
          <button
            key={item.title}
            className="flex items-center justify-between gap-3 py-4 first:pt-0 last:pb-0 text-left group"
          >
            <span className="flex items-center gap-3 min-w-0">
              <span className="w-9 h-9 rounded-xl bg-surface-container flex items-center justify-center text-secondary group-hover:text-on-surface transition-colors shrink-0">
                <Icon name={item.icon} className="text-[18px]" />
              </span>
              <span className="min-w-0">
                <span className="block text-body-sm font-medium text-on-surface truncate">{item.title}</span>
                <span className="block text-label-md text-secondary truncate">{item.sub} · {item.meta}</span>
              </span>
            </span>
            {item.count != null ? (
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-label-md font-semibold shrink-0 ${toneSoft[item.tone]}`}>
                {item.count}
              </span>
            ) : (
              <Icon name="chevron_right" className="text-secondary group-hover:text-on-surface transition-colors shrink-0" />
            )}
          </button>
        ))}
      </div>
    </Section>
  )
}
