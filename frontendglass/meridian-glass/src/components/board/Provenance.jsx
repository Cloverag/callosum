import Icon from '../Icon'
import Section from '../Section'
import { provenance } from '../../data'

const typeIcon = {
  Meeting: 'groups',
  Committee: 'gavel',
  Document: 'description',
}

export default function Provenance() {
  return (
    <Section title="Provenance">
      <div className="flex flex-col divide-y divide-hairline">
        {provenance.map((p) => (
          <div key={p.source} className="flex items-center justify-between gap-3 py-4 first:pt-0 last:pb-0">
            <span className="flex items-center gap-3 min-w-0">
              <span className="w-9 h-9 rounded-xl bg-surface-container flex items-center justify-center text-secondary shrink-0">
                <Icon name={typeIcon[p.type] ?? 'article'} className="text-[18px]" />
              </span>
              <span className="min-w-0">
                <span className="block text-body-sm font-medium text-on-surface truncate">{p.source}</span>
                <span className="block text-label-md text-secondary truncate">
                  {p.type} · {p.facts} facts · Updated {p.updated}
                </span>
              </span>
            </span>
            <span className="flex items-center gap-2 shrink-0">
              <span className="text-label-md text-secondary hidden sm:inline">{p.confidence}</span>
              <Icon name="verified" className="text-success text-[18px]" />
            </span>
          </div>
        ))}
      </div>
    </Section>
  )
}
