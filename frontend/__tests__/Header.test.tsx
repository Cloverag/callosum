import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import Header from '../src/components/Header';
import { SessionGate } from '../src/components/session-gate';
import { authApi, type AuthContext } from '../src/lib/auth';
import { ApiError } from '../src/lib/http';

/**
 * The header was previously two controls that did nothing — a notification bell with a
 * permanent unread dot for a subsystem deferred to P8, and a search box bound to `⌘K`
 * that had no handler. These tests pin the replacement and, just as importantly, pin
 * the removals: a later redesign that reinstates a decorative bell should fail here.
 *
 * Identity is asserted against values the fake session returns, never against literals
 * that also appear in the component. `RAJ` and `MARCUS` differ in every field for that
 * reason — a test seeded with one principal cannot tell "reads the session" from
 * "prints a hard-coded name".
 */

jest.mock('../src/lib/auth', () => {
  const actual = jest.requireActual('../src/lib/auth');
  return {
    ...actual,
    authApi: {
      context: jest.fn(),
      selectWorkspace: jest.fn(),
      logout: jest.fn(),
    },
  };
});

const mocked = authApi as jest.Mocked<typeof authApi>;

const RAJ: AuthContext = {
  principal_id: 'p-raj',
  name: 'Raj Malhotra',
  role: 'Founder',
  clearance: 4,
  workspace_id: '00000000-0000-0000-0000-000000000001',
};

const MARCUS: AuthContext = {
  principal_id: 'p-marcus',
  name: 'Marcus Webb',
  role: 'Investor',
  clearance: 1,
  workspace_id: '00000000-0000-0000-0000-000000000001',
};

/** Renders the header inside the gate, which is the only thing that supplies a session. */
function renderInGate() {
  return render(
    <SessionGate>
      <Header />
    </SessionGate>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('identity comes from the session', () => {
  it('shows the signed-in principal, their role and their clearance', async () => {
    mocked.context.mockResolvedValue(RAJ);
    renderInGate();

    expect(await screen.findByText('Raj Malhotra')).toBeInTheDocument();
    expect(screen.getByText(/Founder/)).toBeInTheDocument();
    expect(screen.getByText(/Clearance 4/)).toBeInTheDocument();
  });

  it('renders a different principal entirely from the session, not a fixed one', async () => {
    // The RBAC demo depends on this: sign in as someone else and the header must
    // follow. A hard-coded name would pass the test above and fail this one.
    mocked.context.mockResolvedValue(MARCUS);
    renderInGate();

    expect(await screen.findByText('Marcus Webb')).toBeInTheDocument();
    expect(screen.getByText(/Investor/)).toBeInTheDocument();
    expect(screen.getByText(/Clearance 1/)).toBeInTheDocument();
    expect(screen.queryByText('Raj Malhotra')).not.toBeInTheDocument();
  });
});

describe('the removed controls stay removed', () => {
  it('has no notifications control and no unread indicator', async () => {
    mocked.context.mockResolvedValue(RAJ);
    const { container } = renderInGate();
    await screen.findByText('Raj Malhotra');

    expect(screen.queryByRole('button', { name: /notification/i })).not.toBeInTheDocument();
    // The fake unread dot was an aria-hidden span, so it is invisible to queries by
    // role or text and has to be asserted structurally.
    expect(container.querySelector('.bg-accent.rounded-full')).toBeNull();
  });

  it('has no search control', async () => {
    mocked.context.mockResolvedValue(RAJ);
    renderInGate();
    await screen.findByText('Raj Malhotra');

    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/search/i)).not.toBeInTheDocument();
  });
});

describe('signing out', () => {
  it('calls the logout endpoint and returns to the signed-out screen', async () => {
    mocked.context.mockResolvedValue(RAJ);
    mocked.logout.mockResolvedValue({ status: 'logged_out' });
    renderInGate();
    await screen.findByText('Raj Malhotra');

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    await waitFor(() => expect(mocked.logout).toHaveBeenCalledTimes(1));
    // The shell unmounts, which is what drops every surface's data along with it.
    await waitFor(() => expect(screen.queryByText('Raj Malhotra')).not.toBeInTheDocument());
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('still returns to the signed-out screen when logout fails', async () => {
    // Leaving someone inside a shell they have asked to leave is the worse of the two
    // outcomes; the next request settles whether the cookie actually died.
    mocked.context.mockResolvedValue(RAJ);
    mocked.logout.mockRejectedValue(new ApiError(0, 'network', 'Could not reach the server.'));
    renderInGate();
    await screen.findByText('Raj Malhotra');

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });
});

describe('the gate decides what the shell sees', () => {
  it('renders no header at all when the caller is not authenticated', async () => {
    mocked.context.mockRejectedValue(new ApiError(401, 'unauthenticated', 'Sign in.'));
    renderInGate();

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByRole('banner')).not.toBeInTheDocument();
  });

  it('asks for a workspace before showing the shell', async () => {
    mocked.context.mockRejectedValue(
      new ApiError(409, 'workspace_not_selected', 'Choose a workspace.'),
    );
    renderInGate();

    expect(await screen.findByLabelText('Workspace ID')).toBeInTheDocument();
    expect(screen.queryByRole('banner')).not.toBeInTheDocument();
  });
});
