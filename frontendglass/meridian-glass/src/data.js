// Board Operating System — content model.
// Swap for live Callosum data once the API is wired in.

export const sideNav = [
  { icon: 'dashboard', label: 'Overview', active: true },
  { icon: 'event', label: 'Meetings' },
  { icon: 'how_to_vote', label: 'Decisions' },
  { icon: 'account_tree', label: 'Memory' },
  { icon: 'settings', label: 'Settings' },
]

// Top — Daily Brief
export const brief = {
  greeting: 'Good morning, Raghav',
  summary: 'The board convenes in 2 days. 3 items need you, and documents are trailing target.',
  date: 'Sunday, November 10',
  chips: [
    { icon: 'schedule', label: '2 days to board meeting', tone: 'neutral' },
    { icon: 'priority_high', label: '3 items need you', tone: 'warning' },
    { icon: 'description', label: 'Docs 60% ready', tone: 'warning' },
  ],
}

// Top — Upcoming Meeting Hero (one rich surface)
export const meeting = {
  countdown: 'In 2 days',
  when: 'Nov 12 · 10:00 AM PST',
  location: 'Executive Suite · Zoom',
  title: 'Q4 Strategic Planning & Annual Review',
  readiness: 78,
  readinessTrend: '+8%',
  owner: 'Sarah Jenkins',
  updated: '2h ago',
  // agenda healthy, approvals + docs need attention, risks critical
  stats: [
    { icon: 'checklist', label: 'Agenda', value: '6 / 8 ready', tone: 'success' },
    { icon: 'approval', label: 'Approvals pending', value: '3', tone: 'warning' },
    { icon: 'description', label: 'Documents', value: '14 · 2 awaiting', tone: 'warning' },
    { icon: 'warning', label: 'Risks flagged', value: '2', tone: 'error' },
  ],
  attendees: [
    { initials: 'SJ', name: 'Sarah Jenkins' },
    { initials: 'MR', name: 'Marcus Reed' },
    { initials: 'KT', name: 'Keiko Tan' },
    { initials: 'DA', name: 'Diego Alvarez' },
  ],
  attendeeTotal: 7,
}

// Middle — Needs You
export const needsYou = [
  { icon: 'how_to_vote', title: 'Approve 4 decisions', sub: 'Strategy Committee', meta: 'Due today', count: 4, tone: 'error' },
  { icon: 'gavel', title: 'Review conflict of interest', sub: 'Board governance', meta: 'Due Nov 11', count: 1, tone: 'warning' },
  { icon: 'upload_file', title: 'Ingest Q3 audit docs', sub: 'Feeds Institutional Memory', meta: 'No due date', count: null, tone: 'neutral' },
]

// Middle — Board Readiness
export const readiness = {
  overall: 78,
  trend: '+8%',
  trendWindow: 'this week',
  updated: '1h ago',
  breakdown: [
    { label: 'Agenda coverage', value: 85, note: 'On track', tone: 'success' },
    { label: 'Documents ready', value: 60, note: 'Below target', tone: 'warning' },
    { label: 'Pre-approvals', value: 40, note: 'Below target', tone: 'warning' },
  ],
}

// Middle — Institutional Memory (the knowledge graph — violet identity)
export const memory = {
  graphHealth: 92,
  confidence: 'High',
  updated: '4h ago',
  verification: [
    { label: 'Verified', value: 92, tone: 'success' },
    { label: 'Pending', value: 6, tone: 'warning' },
    { label: 'Quarantined', value: 2, tone: 'error' },
  ],
  stats: [
    { label: 'Entities', value: '12.4k' },
    { label: 'Edges', value: '84.2k' },
    { label: 'Communities', value: '342' },
  ],
  throughput: '+14%',
  throughputWindow: 'this week',
  provenanceSources: 128,
  coverage: 94,
  recentFacts: [
    { text: 'Revenue peaked 22% above target in November', source: 'Q3 Performance Review' },
    { text: 'Acquisition valuation adjusted −5% for technical debt', source: 'M&A Sub-Committee' },
  ],
}

// Bottom — Verified Decisions
export const verifiedDecisions = [
  { title: 'Product Roadmap 2024', status: 'Approved', owner: 'Strategy Committee', when: '2 days ago', confidence: 'High' },
  { title: 'APAC Market Expansion', status: 'Approved', owner: 'Board', when: '1 week ago', confidence: 'High' },
  { title: 'Q3 Budget Allocation', status: 'Pending', owner: 'Awaiting CFO sign-off', when: 'Due today', confidence: 'Medium' },
]

// Bottom — Provenance
export const provenance = [
  { source: 'Q3 Performance Review', type: 'Meeting', facts: 12, updated: '4h ago', confidence: 'High' },
  { source: 'M&A Sub-Committee (Oct 12)', type: 'Committee', facts: 8, updated: '1d ago', confidence: 'High' },
  { source: 'Finance Memo — H2 Freeze', type: 'Document', facts: 5, updated: '3d ago', confidence: 'Medium' },
]

// Bottom — AI Insights
export const aiInsights = [
  {
    icon: 'lightbulb',
    tone: 'warning',
    text: '2 unresolved items from the last planning session need addressing before Nov 12.',
    action: 'View items',
  },
  {
    icon: 'trending_down',
    tone: 'error',
    text: 'Documents Ready (60%) is trending below target for the upcoming board meeting.',
    action: 'Open readiness',
  },
]

// Chrome — AI dock (quiet copilot)
export const suggestedActions = ['Summarize board deck', 'Draft agenda email', 'Find unresolved items']
