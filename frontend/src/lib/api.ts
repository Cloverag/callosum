export type EntityConflict = {
  id: string;
  name_a: string;
  type_a: string;
  name_b: string;
  type_b: string;
  similarity: number;
  quote_a: string;
  quote_b: string;
  sensitivity: number;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
};

// In-memory mock data store to allow interactive testing of Approve/Reject
const mockConflicts: EntityConflict[] = [
  {
    id: "3f1c019d-a442-491b-90f7-5264b387cf3e",
    name_a: "Raj Patel",
    type_a: "PERSON",
    name_b: "Rajesh Patel",
    type_b: "PERSON",
    similarity: 0.91,
    quote_a: "Raj Patel expressed concerns about the Q3 pricing model.",
    quote_b: "Rajesh Patel strongly disagreed with the board's new direction.",
    sensitivity: 2,
    status: "pending",
    created_at: "2026-07-19T10:00:00Z"
  },
  {
    id: "9d8b1e4c-1234-4abc-8def-112233445566",
    name_a: "Sequoia",
    type_a: "ORGANIZATION",
    name_b: "Sequoia Capital",
    type_b: "ORGANIZATION",
    similarity: 0.82,
    quote_a: "The term sheet from Sequoia requires an answer by Friday.",
    quote_b: "Sequoia Capital has requested additional cap table details.",
    sensitivity: 3,
    status: "pending",
    created_at: "2026-07-19T10:15:00Z"
  },
  {
    id: "a1b2c3d4-e5f6-7a8b-9c0d-123456789012",
    name_a: "Acme Corp",
    type_a: "ORGANIZATION",
    name_b: "Acme Corporation",
    type_b: "ORGANIZATION",
    similarity: 0.95,
    quote_a: "Acme Corp is targeting a Q4 IPO.",
    quote_b: "Acme Corporation's public offering is scheduled for Q4.",
    sensitivity: 1,
    status: "pending",
    created_at: "2026-07-20T08:00:00Z"
  },
  {
    id: "b2c3d4e5-f6a7-8b9c-0d1e-234567890123",
    name_a: "Sarah Jones",
    type_a: "PERSON",
    name_b: "S. Jones",
    type_b: "PERSON",
    similarity: 0.75,
    quote_a: "Sarah Jones will lead the new engineering initiative.",
    quote_b: "S. Jones was appointed as the lead for the engineering team.",
    sensitivity: 2,
    status: "pending",
    created_at: "2026-07-20T08:30:00Z"
  },
  {
    id: "c3d4e5f6-a7b8-9c0d-1e2f-345678901234",
    name_a: "Project Phoenix",
    type_a: "PROJECT",
    name_b: "Phoenix Initiative",
    type_b: "PROJECT",
    similarity: 0.65,
    quote_a: "Project Phoenix is our highest priority this year.",
    quote_b: "The Phoenix Initiative must not be delayed.",
    sensitivity: 4,
    status: "pending",
    created_at: "2026-07-20T09:00:00Z"
  },
  {
    id: "d4e5f6a7-b8c9-0d1e-2f3a-456789012345",
    name_a: "Alpha Release",
    type_a: "EVENT",
    name_b: "V1 Alpha",
    type_b: "EVENT",
    similarity: 0.88,
    quote_a: "The Alpha Release is scheduled for November.",
    quote_b: "We are pushing for the V1 Alpha by late November.",
    sensitivity: 1,
    status: "pending",
    created_at: "2026-07-20T09:15:00Z"
  },
  {
    id: "e5f6a7b8-c9d0-1e2f-3a4b-567890123456",
    name_a: "David Smith",
    type_a: "PERSON",
    name_b: "Dave Smith",
    type_b: "PERSON",
    similarity: 0.98,
    quote_a: "David Smith approved the final budget.",
    quote_b: "Dave Smith signed off on the financial plan.",
    sensitivity: 2,
    status: "approved",
    created_at: "2026-07-18T14:00:00Z"
  },
  {
    id: "f6a7b8c9-d0e1-2f3a-4b5c-678901234567",
    name_a: "AWS",
    type_a: "ORGANIZATION",
    name_b: "Amazon Web Services",
    type_b: "ORGANIZATION",
    similarity: 0.90,
    quote_a: "We are migrating our infrastructure to AWS.",
    quote_b: "Amazon Web Services will be our primary cloud provider.",
    sensitivity: 1,
    status: "rejected",
    created_at: "2026-07-18T15:30:00Z"
  }
];

const DEFAULT_REVIEWER_ID = "00000000-0000-0000-0000-000000000000";

/**
 * Mocked API client for Meridian backend.
 * All functions simulate network latency.
 */
export const apiClient = {
  async getConflicts(): Promise<EntityConflict[]> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 600));
    return [...mockConflicts];
  },

  async approveConflict(id: string, reviewerId: string = DEFAULT_REVIEWER_ID): Promise<{ id: string, status: string }> {
    await new Promise(resolve => setTimeout(resolve, 400));
    const conflict = mockConflicts.find(c => c.id === id);
    if (!conflict) throw new Error("Conflict not found");
    conflict.status = 'approved';
    console.log(`Conflict ${id} approved by ${reviewerId}`);
    return { id, status: 'approved' };
  },

  async rejectConflict(id: string, reviewerId: string = DEFAULT_REVIEWER_ID): Promise<{ id: string, status: string }> {
    await new Promise(resolve => setTimeout(resolve, 400));
    const conflict = mockConflicts.find(c => c.id === id);
    if (!conflict) throw new Error("Conflict not found");
    conflict.status = 'rejected';
    console.log(`Conflict ${id} rejected by ${reviewerId}`);
    return { id, status: 'rejected' };
  }
};
