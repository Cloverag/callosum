import Icon from '../Icon'
import Section from '../Section'
import { verifiedDecisions } from '../../data'
import { toneSoft } from '../../tone'

function StatusPill({ status }) {
  const approved = status === 'Approved'
  const tone = approved ? 'success' : 'warning'
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-label-md font-medium shrink-0 ${toneSoft[tone]}`}>
      <Icon name={approved ? 'check' : 'schedule'} className="text-[13px]" />
      {status}
    </span>
  )
}

export default function VerifiedDecisions() {
  return (
    <Section
      title="Verified decisions"
      action={<button className="text-primary text-label-md hover:underline">View all</button>}
    >
      <div className="os-surface-quiet divide-y divide-hairline">
        {verifiedDecisions.map((d) => (
          <div key={d.title} className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="min-w-0">
              <p className="text-body-sm font-medium text-on-surface truncate">{d.title}</p>
              <p className="text-label-md text-secondary truncate">
                {d.owner} · {d.when} · {d.confidence} confidence
              </p>
            </div>
            <StatusPill status={d.status} />
          </div>
        ))}
      </div>
    </Section>
  )
}
