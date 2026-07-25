import Icon from '../Icon'
import Section from '../Section'
import { aiInsights } from '../../data'
import { toneSoft } from '../../tone'

export default function AIInsights() {
  return (
    <Section title="AI insights">
      <div className="os-surface-quiet divide-y divide-hairline">
        {aiInsights.map((insight) => (
          <div key={insight.text} className="flex items-start gap-3 px-5 py-4">
            <span className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${toneSoft[insight.tone]}`}>
              <Icon name={insight.icon} className="text-[18px]" />
            </span>
            <div>
              <p className="text-body-sm text-on-surface text-pretty">{insight.text}</p>
              <button className="inline-flex items-center gap-1 text-primary text-label-md font-medium mt-1.5 hover:underline">
                {insight.action}
                <Icon name="arrow_forward" className="text-[14px]" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}
