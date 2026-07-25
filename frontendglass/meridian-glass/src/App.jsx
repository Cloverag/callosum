import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import AIWorkspace from './components/AIWorkspace'
import MobileNav from './components/MobileNav'
import DailyBrief from './components/board/DailyBrief'
import MeetingHero from './components/board/MeetingHero'
import NeedsYou from './components/board/NeedsYou'
import BoardReadiness from './components/board/BoardReadiness'
import InstitutionalMemory from './components/board/InstitutionalMemory'
import VerifiedDecisions from './components/board/VerifiedDecisions'
import Provenance from './components/board/Provenance'
import AIInsights from './components/board/AIInsights'

export default function App() {
  return (
    <div className="text-on-surface antialiased min-h-screen relative flex">
      <TopBar />
      <Sidebar />

      {/* One continuous canvas — sections grouped by space, not boxes */}
      <main className="flex-1 md:ml-[300px] lg:mr-[340px] pt-[104px] pb-24 md:pb-16 px-6 lg:px-10 min-h-screen z-10 w-full max-w-[1080px] mx-auto flex flex-col gap-14">
        {/* Top */}
        <DailyBrief />
        <MeetingHero />

        {/* Middle — asymmetric: light column of tasks + the violet memory focal point */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] gap-x-12 gap-y-14 items-start">
          <div className="flex flex-col gap-14">
            <NeedsYou />
            <BoardReadiness />
          </div>
          <InstitutionalMemory />
        </div>

        {/* Bottom — calm evidence sections */}
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-x-12 gap-y-14 items-start">
          <VerifiedDecisions />
          <div className="flex flex-col gap-14">
            <Provenance />
            <AIInsights />
          </div>
        </div>
      </main>

      <AIWorkspace />
      <MobileNav />
    </div>
  )
}
