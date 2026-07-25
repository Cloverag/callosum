// Mocked "Ask Meridian" assistant. The product thesis, made conversational:
// answers come ONLY from approved, source-backed board memory, every claim shows
// its verbatim evidence, and withheld sources are disclosed as a count — never
// their content. Unknown questions are marked unknown, never fabricated.

export type Citation = {
  /** Verbatim source quote grounding the answer (contiguous, single-speaker). */
  quote: string;
  source: string;
};

export type AssistantAnswer = {
  answer: string;
  citations: Citation[];
  /** Related approved facts the operator might follow. */
  related: string[];
  /** Sources excluded by clearance before the answer was assembled (count only). */
  withheld: number;
  /** True when no verified answer exists — the assistant abstains rather than guess. */
  abstained?: boolean;
};

export type AssistantTurn = {
  id: string;
  question: string;
  answer: AssistantAnswer | null; // null while thinking
};

export const SUGGESTED_PROMPTS = [
  "Why did we reverse the Q3 pricing decision?",
  "Who is leading the Series B?",
  "What did the board decide about hiring?",
  "Summarize the last board meeting.",
];

const KNOWLEDGE: { match: RegExp; answer: AssistantAnswer }[] = [
  {
    match: /pricing|reverse|q3|model b/i,
    answer: {
      answer:
        "The board reversed its earlier Q3 pricing rejection and adopted usage-based pricing (Pricing Model B), which supersedes the flat-rate proposal.",
      citations: [
        { quote: "On reflection we're moving ahead with usage-based pricing after all.", source: "Board Meeting 13" },
        { quote: "Model B replaces the flat-rate structure we tabled last quarter.", source: "Board Meeting 13" },
      ],
      related: [
        "Pricing Model B supersedes the earlier flat-rate proposal.",
        "The original rejection was recorded in Board Meeting #14.",
      ],
      withheld: 0,
    },
  },
  {
    match: /series b|sequoia|raise|valuation|round/i,
    answer: {
      answer: "Sequoia will lead the Series B round at the proposed valuation.",
      citations: [
        { quote: "Sequoia has confirmed they'll lead the Series B at the proposed valuation.", source: "Investor Update — Sequoia" },
      ],
      related: ["The Sequoia term sheet requires a response by Friday."],
      // One source (detailed terms) sits above the asker's clearance — disclosed as a count only.
      withheld: 1,
    },
  },
  {
    match: /hir|engineer|headcount|team|recruit/i,
    answer: {
      answer: "The board approved a six-person engineering hire for the half.",
      citations: [{ quote: "We signed off on the six-engineer hiring plan for the half.", source: "Board Meeting #14" }],
      related: ["Hiring plan sign-off was agenda item 3 of Board Meeting #14."],
      withheld: 0,
    },
  },
  {
    match: /summar|last meeting|recent meeting|q3 board/i,
    answer: {
      answer:
        "The most recent board meeting (Q3 Board Meeting) covered the Q3 board pack, Series B terms, and runway. It is currently in progress.",
      citations: [{ quote: "Q3 board pack, Series B terms, runway.", source: "Q3 Board Meeting" }],
      related: ["Priya Nair owns the revised FY27 forecast.", "Series B terms are under review."],
      withheld: 0,
    },
  },
];

const ABSTENTION: AssistantAnswer = {
  answer:
    "I don't have a verified answer for that yet. I only answer from approved, source-backed board memory — I won't guess.",
  citations: [],
  related: [],
  withheld: 0,
  abstained: true,
};

const delay = (ms = 700) => new Promise((r) => setTimeout(r, ms));

export const assistantApi = {
  async ask(question: string): Promise<AssistantAnswer> {
    await delay();
    const hit = KNOWLEDGE.find((k) => k.match.test(question));
    return structuredClone(hit ? hit.answer : ABSTENTION);
  },
};
