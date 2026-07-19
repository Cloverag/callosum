import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import EntityConflictsPage from '../src/app/entity-conflicts/page';
import { apiClient } from '../src/lib/api';

// Mock the API client
jest.mock('../src/lib/api', () => ({
  apiClient: {
    getPendingConflicts: jest.fn(),
    approveConflict: jest.fn(),
    rejectConflict: jest.fn(),
  },
}));

describe('EntityConflictsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders loading state initially', () => {
    (apiClient.getPendingConflicts as jest.Mock).mockReturnValue(new Promise(() => {}));
    render(<EntityConflictsPage />);
    expect(screen.getByText(/Initializing neural matrix.../i)).toBeInTheDocument();
  });

  it('renders empty state when no conflicts', async () => {
    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue([]);
    render(<EntityConflictsPage />);
    
    await waitFor(() => {
      expect(screen.getByText(/System optimal/i)).toBeInTheDocument();
    });
  });

  it('renders conflicts and handles approve action', async () => {
    const mockData = [
      {
        id: "1",
        name_a: "Raj Patel",
        type_a: "PERSON",
        name_b: "Rajesh Patel",
        type_b: "PERSON",
        similarity: 0.91,
        quote_a: "Quote A",
        quote_b: "Quote B",
        sensitivity: 1,
        status: "pending",
        created_at: "2026-07-19T10:00:00Z"
      }
    ];

    (apiClient.getPendingConflicts as jest.Mock).mockResolvedValue(mockData);
    (apiClient.approveConflict as jest.Mock).mockResolvedValue({ id: "1", status: "approved" });

    render(<EntityConflictsPage />);
    
    await waitFor(() => {
      expect(screen.getByText("Raj Patel")).toBeInTheDocument();
    });

    const approveBtn = screen.getByRole('button', { name: /Approve/i });
    fireEvent.click(approveBtn);

    expect(apiClient.approveConflict).toHaveBeenCalledWith("1");

    // After approval, it should remove the item from the list optimistically
    await waitFor(() => {
      expect(screen.queryByText("Raj Patel")).not.toBeInTheDocument();
    });
  });
});
