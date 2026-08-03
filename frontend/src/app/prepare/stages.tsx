/**
 * The five stages of meeting preparation, as an index.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS IS NAVIGATION AND NOT A PROGRESS BAR
 * ---------------------------------------------------------------------------
 * It was a progress stepper, and the stepper lied. It took `current={data ? 4 : 0}` —
 * a hard-coded 4 — so the moment the page finished fetching it marked Gathering,
 * Analysis, Agenda and Board pack as **complete**, while the agenda held zero items and
 * no pack existed. Fetching data is not the same as preparing a meeting, and a filled
 * step is a claim about the board's readiness, not about the browser's.
 *
 * There is no honest completion state available. "Agenda complete" has no definition —
 * the domain has no notion of an agenda being finished, and inventing a threshold
 * ("three or more items?") would be a measurement nobody took, which is the same defect
 * wearing a different shape.
 *
 * So the stages are what they truthfully are: the order of the page. Each is a link to
 * a section. None of them claims to be done, because none of them can be.
 *
 * What the reader learns about readiness comes from step 5, which counts real rows.
 */

export const STAGES = [
  { id: "gathering", label: "Gathering" },
  { id: "analysis", label: "Analysis" },
  { id: "agenda", label: "Agenda" },
  { id: "board-pack", label: "Board pack" },
  { id: "readiness", label: "Readiness" },
] as const;

export function Stages() {
  return (
    <nav aria-label="Preparation stages" className="mt-6">
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-2 text-xs">
        {STAGES.map((stage, i) => (
          <li key={stage.id} className="flex items-center gap-1">
            <a
              href={`#${stage.id}`}
              className="rounded-[8px] px-2 py-1 text-muted-foreground transition-colors duration-150 hover:bg-surface-sunken hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              <span className="tabular-nums text-subtle-foreground">{i + 1}</span>{" "}
              {stage.label}
            </a>
            {i < STAGES.length - 1 && (
              <span className="text-subtle-foreground" aria-hidden>
                ·
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
