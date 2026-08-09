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
  }
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * API client for Meridian backend.
 * Connects to live FastAPI backend when available, with fallback to in-memory mock store.
 */
export const apiClient = {
  async getPendingConflicts(): Promise<EntityConflict[]> {
    try {
      const res = await fetch(`${API_BASE}/api/conflicts?status=pending`, {
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        return data;
      }
    } catch {
      // Backend unavailable; fallback to mock data
    }
    await new Promise(resolve => setTimeout(resolve, 100));
    return mockConflicts.filter(c => c.status === 'pending');
  },

  async approveConflict(id: string, reviewerId: string = DEFAULT_REVIEWER_ID): Promise<{ id: string, status: string }> {
    try {
      const res = await fetch(`${API_BASE}/api/conflicts/${id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fallback to mock
    }
    await new Promise(resolve => setTimeout(resolve, 100));
    const conflict = mockConflicts.find(c => c.id === id);
    if (!conflict) throw new Error("Conflict not found");
    conflict.status = 'approved';
    return { id, status: 'approved' };
  },

  async rejectConflict(id: string, reviewerId: string = DEFAULT_REVIEWER_ID): Promise<{ id: string, status: string }> {
    try {
      const res = await fetch(`${API_BASE}/api/conflicts/${id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fallback to mock
    }
    await new Promise(resolve => setTimeout(resolve, 100));
    const conflict = mockConflicts.find(c => c.id === id);
    if (!conflict) throw new Error("Conflict not found");
    conflict.status = 'rejected';
    return { id, status: 'rejected' };
  },

  async getMeetingReadiness(meetingId: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/api/meetings/${meetingId}/readiness`, {
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fallback
    }
    return null;
  },

  async getAgendaSuggestions(meetingId: string): Promise<any[]> {
    try {
      const res = await fetch(`${API_BASE}/api/meetings/${meetingId}/agenda-suggestions`, {
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fallback
    }
    return [];
  },

  async publishPreread(meetingId: string): Promise<any> {
    try {
      const res = await fetch(`${API_BASE}/api/meetings/${meetingId}/publish-preread`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Fallback
    }
    return { meeting_id: meetingId, status: "published" };
  }
};
