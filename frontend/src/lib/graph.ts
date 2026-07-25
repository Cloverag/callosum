// The verified knowledge graph, as actually seeded.
//
// GENERATED from `src/callosum/evaluate.py` GOLD_GROUPS — every node, edge and
// evidence quote below appears in the research corpus. Nothing here is invented,
// which is the entire point: this view is the thesis made visible, so a fabricated
// node would undermine the thing it exists to demonstrate.
//
// Regenerate with the script recorded in docs (deterministic Fruchterman-Reingold
// layout, seed 7) whenever the gold graph changes. Positions are baked so the
// picture is stable across loads and needs no layout library.
//
// Swaps to a real endpoint at P3 behind this same shape.

export type GraphNodeType =
  | "Person" | "Decision" | "Meeting" | "Topic"
  | "ActionItem" | "Metric" | "Document" | "Organization";

export type GraphNodeData = {
  id: string;
  label: string;
  type: GraphNodeType;
  /** Person role, where the ontology recorded one. */
  role: string;
  /** Decision status or metric value, where recorded. */
  detail: string;
  /** Source document the entity was extracted from. */
  document: string;
  /** Sits above the default clearance — withheld for lower-clearance callers. */
  restricted: boolean;
  /** Edges touching this node; drives node size. */
  degree: number;
  x: number;
  y: number;
};

export type GraphEdgeData = {
  id: string;
  source: string;
  target: string;
  relation: string;
  /** The verbatim quote located in the source. No edge exists without one. */
  quote: string;
  document: string;
  restricted: boolean;
};

/** Ontology type -> how it reads in the UI. Neutral by default; only Decision
 *  and Person carry emphasis, because those are what a board member looks for. */
export const NODE_TYPE_LABEL: Record<GraphNodeType, string> = {
  Person: "Person",
  Decision: "Decision",
  Meeting: "Meeting",
  Topic: "Topic",
  ActionItem: "Action item",
  Metric: "Metric",
  Document: "Document",
  Organization: "Organization",
};

export const GRAPH_NODES: GraphNodeData[] = [
  { id: "Raj Malhotra", label: "Raj Malhotra", type: "Person", role: "CEO, co-founder", detail: "", document: "board_meeting_12_transcript", restricted: false, degree: 6, x: 649.8, y: 548.6 },
  { id: "Priya Nair", label: "Priya Nair", type: "Person", role: "CFO", detail: "", document: "board_meeting_12_transcript", restricted: false, degree: 6, x: 1160.6, y: 388.5 },
  { id: "Marcus Webb", label: "Marcus Webb", type: "Person", role: "Sequoia, board", detail: "", document: "board_meeting_12_transcript", restricted: false, degree: 2, x: 1180.0, y: 557.0 },
  { id: "Reject Pricing Model B", label: "Reject Pricing Model B", type: "Decision", role: "", detail: "rejected", document: "board_meeting_12_transcript", restricted: false, degree: 7, x: 1030.9, y: 571.7 },
  { id: "Pricing Model B", label: "Pricing Model B", type: "Topic", role: "", detail: "", document: "board_meeting_12_transcript", restricted: false, degree: 3, x: 889.9, y: 660.0 },
  { id: "Board Meeting 12", label: "Board Meeting 12", type: "Meeting", role: "", detail: "", document: "board_meeting_12_transcript", restricted: false, degree: 1, x: 1158.6, y: 729.5 },
  { id: "Write pricing decision pack", label: "Write pricing decision pack", type: "ActionItem", role: "", detail: "", document: "board_meeting_12_transcript", restricted: false, degree: 1, x: 1194.6, y: 623.7 },
  { id: "Elena Duarte", label: "Elena Duarte", type: "Person", role: "Accel, board", detail: "", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 1105.0, y: 677.5 },
  { id: "Tom Fischer", label: "Tom Fischer", type: "Person", role: "independent director", detail: "", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 172.0, y: 660.0 },
  { id: "Adopt Usage-Based Pricing", label: "Adopt Usage-Based Pricing", type: "Decision", role: "", detail: "approved", document: "board_meeting_13_transcript", restricted: false, degree: 8, x: 1002.5, y: 519.7 },
  { id: "Board Meeting 13", label: "Board Meeting 13", type: "Meeting", role: "", detail: "", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 1032.0, y: 625.5 },
  { id: "Northwind", label: "Northwind", type: "Organization", role: "largest customer", detail: "", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 768.5, y: 660.0 },
  { id: "March Board Deck", label: "March Board Deck", type: "Document", role: "", detail: "", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 0.0, y: 712.0 },
  { id: "gross margin", label: "gross margin", type: "Metric", role: "", detail: "66%", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 0.0, y: 608.0 },
  { id: "Germany Expansion", label: "Germany Expansion", type: "Topic", role: "", detail: "", document: "board_meeting_13_transcript", restricted: false, degree: 1, x: 39.2, y: 660.0 },
  { id: "Raj", label: "Raj", type: "Person", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 1, x: 576.2, y: 660.0 },
  { id: "R. Malhotra", label: "R. Malhotra", type: "Person", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 1, x: 448.4, y: 660.0 },
  { id: "Rajesh Kumar", label: "Rajesh Kumar", type: "Person", role: "Staff Engineer, Platform", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 5, x: -12.3, y: 348.4 },
  { id: "Rajesh", label: "Rajesh", type: "Person", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 1, x: 0.0, y: 472.2 },
  { id: "R. Kumar", label: "R. Kumar", type: "Person", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 1, x: 0.0, y: 406.5 },
  { id: "Board Meeting 14", label: "Board Meeting 14", type: "Meeting", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 4, x: 297.6, y: 429.3 },
  { id: "Approve billing pipeline deploy", label: "Approve billing pipeline deploy", type: "Decision", role: "", detail: "approved", document: "board_meeting_14_transcript", restricted: false, degree: 2, x: 137.8, y: 328.9 },
  { id: "Approve rollback and customer credits", label: "Approve rollback and customer credits", type: "Decision", role: "", detail: "approved", document: "board_meeting_14_transcript", restricted: false, degree: 2, x: 441.3, y: 498.5 },
  { id: "Billing pipeline remediation", label: "Billing pipeline remediation", type: "ActionItem", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 1, x: 0.0, y: 217.7 },
  { id: "Customer-credit reconciliation", label: "Customer-credit reconciliation", type: "ActionItem", role: "", detail: "", document: "board_meeting_14_transcript", restricted: false, degree: 1, x: 1180.0, y: 207.8 },
  { id: "Finance FY27 ARR forecast", label: "Finance FY27 ARR forecast", type: "Metric", role: "", detail: "$12.0M", document: "finance_fy27_forecast", restricted: false, degree: 1, x: 0.0, y: 50.4 },
  { id: "Finance FY27 Forecast", label: "Finance FY27 Forecast", type: "Document", role: "", detail: "", document: "finance_fy27_forecast", restricted: false, degree: 3, x: 98.3, y: -53.6 },
  { id: "Sales FY27 ARR forecast", label: "Sales FY27 ARR forecast", type: "Metric", role: "", detail: "$11.6M", document: "sales_fy27_forecast", restricted: false, degree: 1, x: 11.7, y: -1.6 },
  { id: "Sales FY27 Forecast", label: "Sales FY27 Forecast", type: "Document", role: "", detail: "", document: "sales_fy27_forecast", restricted: false, degree: 3, x: 183.6, y: 28.4 },
  { id: "Board Meeting 15", label: "Board Meeting 15", type: "Meeting", role: "", detail: "", document: "board_meeting_15_transcript", restricted: false, degree: 2, x: 258.9, y: -37.8 },
  { id: "FY27 ARR forecast", label: "FY27 ARR forecast", type: "Topic", role: "", detail: "", document: "board_meeting_15_transcript", restricted: false, degree: 2, x: 341.2, y: 14.2 },
  { id: "Board Meeting 16", label: "Board Meeting 16", type: "Meeting", role: "", detail: "", document: "board_meeting_16_transcript", restricted: false, degree: 1, x: 1019.1, y: 0.0 },
  { id: "Pricing rollout plan", label: "Pricing rollout plan", type: "ActionItem", role: "", detail: "", document: "board_meeting_16_transcript", restricted: false, degree: 2, x: 1180.0, y: 460.8 },
  { id: "International expansion motion", label: "International expansion motion", type: "Decision", role: "", detail: "deferred", document: "board_meeting_16_transcript", restricted: false, degree: 1, x: 1183.4, y: 14.9 },
  { id: "Vendor security questionnaire", label: "Vendor security questionnaire", type: "ActionItem", role: "", detail: "", document: "messy_board_followup_email", restricted: false, degree: 1, x: 1180.0, y: 259.8 },
  { id: "Nisha Shah", label: "Nisha Shah", type: "Person", role: "security operations", detail: "", document: "messy_audit_followup_email", restricted: false, degree: 1, x: 1180.0, y: -37.1 },
  { id: "SOC 2 evidence request", label: "SOC 2 evidence request", type: "ActionItem", role: "", detail: "", document: "messy_audit_followup_email", restricted: false, degree: 1, x: 1181.7, y: 66.9 },
  { id: "Meridian Inc", label: "Meridian Inc", type: "Organization", role: "", detail: "", document: "compensation_review_CONFIDENTIAL", restricted: true, degree: 1, x: 1180.0, y: 311.8 },
];

export const GRAPH_EDGES: GraphEdgeData[] = [
  { id: "e0", source: "Reject Pricing Model B", target: "Pricing Model B", relation: "ABOUT", quote: "Pricing Model B — the usage-based tier", document: "board_meeting_12_transcript", restricted: false },
  { id: "e1", source: "Reject Pricing Model B", target: "Board Meeting 12", relation: "MADE_IN", quote: "Board Meeting 12", document: "board_meeting_12_transcript", restricted: false },
  { id: "e2", source: "Raj Malhotra", target: "Reject Pricing Model B", relation: "APPROVED", quote: "We're not doing Model B.", document: "board_meeting_12_transcript", restricted: false },
  { id: "e3", source: "Priya Nair", target: "Reject Pricing Model B", relation: "SUPPORTED", quote: "I can't recommend it in its current form.", document: "board_meeting_12_transcript", restricted: false },
  { id: "e4", source: "Marcus Webb", target: "Reject Pricing Model B", relation: "OPPOSED", quote: "I want to push back on that framing.", document: "board_meeting_12_transcript", restricted: false },
  { id: "e5", source: "Write pricing decision pack", target: "Reject Pricing Model B", relation: "DERIVED_FROM", quote: "write it up for the board pack with the margin analysis attached", document: "board_meeting_12_transcript", restricted: false },
  { id: "e6", source: "Adopt Usage-Based Pricing", target: "Reject Pricing Model B", relation: "SUPERSEDES", quote: "I'm comfortable reversing our decision from March", document: "board_meeting_13_transcript", restricted: false },
  { id: "e7", source: "Adopt Usage-Based Pricing", target: "Pricing Model B", relation: "ABOUT", quote: "usage-based is our forward pricing model", document: "board_meeting_13_transcript", restricted: false },
  { id: "e8", source: "Adopt Usage-Based Pricing", target: "Board Meeting 13", relation: "MADE_IN", quote: "Board Meeting 13", document: "board_meeting_13_transcript", restricted: false },
  { id: "e9", source: "Raj Malhotra", target: "Adopt Usage-Based Pricing", relation: "APPROVED", quote: "usage-based is our forward pricing model. That's my call.", document: "board_meeting_13_transcript", restricted: false },
  { id: "e10", source: "Marcus Webb", target: "Adopt Usage-Based Pricing", relation: "SUPPORTED", quote: "I supported this a year ago and I support it now", document: "board_meeting_13_transcript", restricted: false },
  { id: "e11", source: "Priya Nair", target: "Adopt Usage-Based Pricing", relation: "SUPPORTED", quote: "With that floor and the Series C closed, I can get behind it. I'm a yes.", document: "board_meeting_13_transcript", restricted: false },
  { id: "e12", source: "Elena Duarte", target: "Adopt Usage-Based Pricing", relation: "SUPPORTED", quote: "so I'm supportive of the direction", document: "board_meeting_13_transcript", restricted: false },
  { id: "e13", source: "Northwind", target: "Pricing Model B", relation: "REQUESTED", quote: "Our single largest account has formally asked to move to a usage-based contract", document: "board_meeting_13_transcript", restricted: false },
  { id: "e14", source: "gross margin", target: "March Board Deck", relation: "REPORTED_IN", quote: "Appendix C in the March board deck projected gross margin at 71%", document: "board_meeting_13_transcript", restricted: false },
  { id: "e15", source: "Tom Fischer", target: "Germany Expansion", relation: "OWNS", quote: "Tom owns the Germany expansion workstream through Q2", document: "board_meeting_13_transcript", restricted: false },
  { id: "e16", source: "Raj", target: "Raj Malhotra", relation: "ALIAS_OF", quote: "Raj is short for Raj Malhotra, the CEO", document: "board_meeting_14_transcript", restricted: false },
  { id: "e17", source: "R. Malhotra", target: "Raj Malhotra", relation: "ALIAS_OF", quote: "R. Malhotra is Raj, our CEO", document: "board_meeting_14_transcript", restricted: false },
  { id: "e18", source: "Rajesh", target: "Rajesh Kumar", relation: "ALIAS_OF", quote: "Rajesh is Rajesh Kumar, the engineer", document: "board_meeting_14_transcript", restricted: false },
  { id: "e19", source: "R. Kumar", target: "Rajesh Kumar", relation: "ALIAS_OF", quote: "R. Kumar — that's me, Rajesh Kumar — approved the deploy window", document: "board_meeting_14_transcript", restricted: false },
  { id: "e20", source: "Rajesh Kumar", target: "Approve billing pipeline deploy", relation: "APPROVED", quote: "Rajesh Kumar approved the deploy", document: "board_meeting_14_transcript", restricted: false },
  { id: "e21", source: "Raj Malhotra", target: "Approve rollback and customer credits", relation: "APPROVED", quote: "Raj Malhotra approved the rollback and the credits", document: "board_meeting_14_transcript", restricted: false },
  { id: "e22", source: "Approve billing pipeline deploy", target: "Board Meeting 14", relation: "MADE_IN", quote: "Board Meeting 14", document: "board_meeting_14_transcript", restricted: false },
  { id: "e23", source: "Approve rollback and customer credits", target: "Board Meeting 14", relation: "MADE_IN", quote: "Board Meeting 14", document: "board_meeting_14_transcript", restricted: false },
  { id: "e24", source: "Rajesh Kumar", target: "Billing pipeline remediation", relation: "OWNS", quote: "Rajesh Kumar owns the billing pipeline remediation", document: "board_meeting_14_transcript", restricted: false },
  { id: "e25", source: "Priya Nair", target: "Customer-credit reconciliation", relation: "OWNS", quote: "Priya Nair owns the customer-credit reconciliation", document: "board_meeting_14_transcript", restricted: false },
  { id: "e26", source: "Raj Malhotra", target: "Board Meeting 14", relation: "ATTENDED", quote: "Raj Malhotra (CEO, co-founder)", document: "board_meeting_14_transcript", restricted: false },
  { id: "e27", source: "Rajesh Kumar", target: "Board Meeting 14", relation: "ATTENDED", quote: "Rajesh Kumar (Staff Engineer, Platform)", document: "board_meeting_14_transcript", restricted: false },
  { id: "e28", source: "Finance FY27 ARR forecast", target: "Finance FY27 Forecast", relation: "REPORTED_IN", quote: "Finance forecast: FY27 ARR is $12.0M.", document: "finance_fy27_forecast", restricted: false },
  { id: "e29", source: "Sales FY27 ARR forecast", target: "Sales FY27 Forecast", relation: "REPORTED_IN", quote: "Sales forecast: FY27 ARR is $11.6M.", document: "sales_fy27_forecast", restricted: false },
  { id: "e30", source: "Finance FY27 Forecast", target: "Board Meeting 15", relation: "PRESENTED_AT", quote: "The Finance FY27 Forecast says $12.0M; the Sales FY27 Forecast says $11.6M.", document: "board_meeting_15_transcript", restricted: false },
  { id: "e31", source: "Sales FY27 Forecast", target: "Board Meeting 15", relation: "PRESENTED_AT", quote: "The Finance FY27 Forecast says $12.0M; the Sales FY27 Forecast says $11.6M.", document: "board_meeting_15_transcript", restricted: false },
  { id: "e32", source: "Finance FY27 Forecast", target: "FY27 ARR forecast", relation: "ABOUT", quote: "The Finance FY27 Forecast says $12.0M", document: "board_meeting_15_transcript", restricted: false },
  { id: "e33", source: "Sales FY27 Forecast", target: "FY27 ARR forecast", relation: "ABOUT", quote: "the Sales FY27 Forecast says $11.6M", document: "board_meeting_15_transcript", restricted: false },
  { id: "e34", source: "Pricing rollout plan", target: "Adopt Usage-Based Pricing", relation: "DERIVED_FROM", quote: "That proposal means the pricing rollout plan Priya circulated yesterday.", document: "board_meeting_16_transcript", restricted: false },
  { id: "e35", source: "Priya Nair", target: "Pricing rollout plan", relation: "OWNS", quote: "Priya owns that pricing rollout plan.", document: "board_meeting_16_transcript", restricted: false },
  { id: "e36", source: "International expansion motion", target: "Board Meeting 16", relation: "MADE_IN", quote: "The international expansion motion stays deferred.", document: "board_meeting_16_transcript", restricted: false },
  { id: "e37", source: "Priya Nair", target: "Vendor security questionnaire", relation: "OWNS", quote: "Priya owns the vendor-security questionnaire", document: "messy_board_followup_email", restricted: false },
  { id: "e38", source: "Nisha Shah", target: "SOC 2 evidence request", relation: "OWNS", quote: "Nisha owns the SOC 2 evidence request", document: "messy_audit_followup_email", restricted: false },
  { id: "e39", source: "Priya Nair", target: "Meridian Inc", relation: "WORKS_AT", quote: "Priya Nair, CFO, is at $185K base", document: "compensation_review_CONFIDENTIAL", restricted: true },
];

const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

export type GraphView = {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  /** Nodes and edges removed for this caller's clearance, disclosed as a count
   *  only — never as titles. Withholding silently would be the failure mode the
   *  whole project exists to avoid. */
  withheldNodes: number;
  withheldEdges: number;
};

export const graphApi = {
  /**
   * `canSeeRestricted` stands in for the clearance check the backend already
   * enforces in SQL and Cypher. Filtering here is presentation only — the real
   * guarantee is that a low-clearance caller is never sent the rows at all.
   */
  async get(canSeeRestricted = true): Promise<GraphView> {
    await delay();
    if (canSeeRestricted) {
      return { nodes: GRAPH_NODES, edges: GRAPH_EDGES, withheldNodes: 0, withheldEdges: 0 };
    }
    const nodes = GRAPH_NODES.filter((n) => !n.restricted);
    const allowed = new Set(nodes.map((n) => n.id));
    const edges = GRAPH_EDGES.filter(
      (e) => !e.restricted && allowed.has(e.source) && allowed.has(e.target)
    );
    return {
      nodes,
      edges,
      withheldNodes: GRAPH_NODES.length - nodes.length,
      withheldEdges: GRAPH_EDGES.length - edges.length,
    };
  },
};
