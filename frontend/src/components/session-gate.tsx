"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/http";
import { authApi, LOGIN_URL, type AuthContext } from "@/lib/auth";

/**
 * Stands between an unauthenticated browser and the application shell.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS EXISTS
 * ---------------------------------------------------------------------------
 * The API had `/auth/login`, `/auth/callback` and `/auth/workspace` from CP-A, and the
 * curl walkthrough in `docs/demo-setup.md` exercised all three. The browser never
 * could: the root route redirected straight to `/dashboard`, nothing linked to
 * `/auth/login`, and no surface could select a workspace. A visitor signed in — or did
 * not — and either way got a shell of failing panels.
 *
 * `lib/http.ts` already distinguished both cases (`isUnauthenticated`, `needsWorkspace`)
 * and `LoadFailed` already rendered "Select a workspace to continue." That was copy for
 * a control nobody had built. This is the control.
 *
 * ---------------------------------------------------------------------------
 * WHY IT IS A CLIENT GATE AND NOT MIDDLEWARE
 * ---------------------------------------------------------------------------
 * The session is an httpOnly signed cookie. Middleware could see that a cookie exists
 * but not whether it is valid, whether the membership behind it still stands, or
 * whether a workspace was chosen — so it would have to guess, and a guess that lets a
 * revoked member through is worse than no guard. `GET /auth/context` re-derives all of
 * it from the database on every call, which makes the honest check also the simple one.
 *
 * This is a routing convenience, not a security boundary. The boundary is RLS plus
 * `deps.current_principal`; every endpoint refuses on its own whatever this renders.
 */

type State =
  | { phase: "checking" }
  | { phase: "ready"; context: AuthContext }
  | { phase: "signed-out" }
  /**
   * `stale` marks the case where a workspace WAS selected and the server has
   * since refused it (403). The distinction only changes the copy — the remedy
   * is identical, because re-selecting is the one action that can overwrite the
   * workspace held in the session cookie.
   */
  | { phase: "needs-workspace"; stale?: boolean }
  | { phase: "failed"; error: ApiError };

const WORKSPACE_STORAGE_KEY = "meridian.workspace_id";

/**
 * The authenticated session, for the shell that renders inside the gate.
 *
 * There is deliberately **one** fetch of `/auth/context` in the application. `Header`
 * consumes this rather than fetching for itself: two components asking independently
 * is how a header ends up naming one principal while the page below it renders
 * another's data.
 *
 * `null` outside the provider rather than a throw, so a component can be rendered in a
 * test without standing up the whole gate.
 */
type Session = { context: AuthContext; signOut: () => Promise<void> };

const SessionContext = createContext<Session | null>(null);

/** The signed-in principal, or `null` when rendered outside an authenticated shell. */
export function useSession(): Session | null {
  return useContext(SessionContext);
}

/** Matches `needs-you.tsx`, which set the house curve. Mirrors `--ease-out-quart`. */
const EASE = [0.22, 1, 0.36, 1] as const;

export function SessionGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ phase: "checking" });

  const check = useCallback(async () => {
    try {
      const context = await authApi.context();
      setState({ phase: "ready", context });
    } catch (e) {
      const error =
        e instanceof ApiError ? e : new ApiError(0, "network", "Could not reach the server.");
      if (error.isUnauthenticated) setState({ phase: "signed-out" });
      else if (error.needsWorkspace) setState({ phase: "needs-workspace" });
      /**
       * 403 used to fall through to `failed`, whose only affordance is "Try
       * again" — which re-issues the identical request and gets the identical
       * 403. That is a dead end, not a retry: the workspace is held in the
       * httpOnly session cookie, so nothing the client can clear will change
       * the outcome, and only a fresh `POST /auth/workspace` overwrites it.
       * Selection is therefore the remedy, and it is the screen we already have.
       */
      else if (error.isForbidden) setState({ phase: "needs-workspace", stale: true });
      else setState({ phase: "failed", error });
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  /**
   * Ends the session and returns to the signed-out screen.
   *
   * The gate's own state is reset rather than the page reloaded: the shell unmounts,
   * so every surface inside it drops the data it fetched under the previous identity.
   * A reload would achieve the same thing more slowly and with a white flash.
   *
   * The remembered workspace id is deliberately kept. It is a device convenience, not
   * session state — it records which workspace this browser last used, never who may
   * enter it, and the server re-verifies membership on the next selection regardless.
   */
  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Swallowed on purpose, and `catch` rather than `finally` because `finally` sets
      // the state and then re-throws — which surfaces as an unhandled rejection in the
      // click handler while the screen behaves correctly. A test caught exactly that.
      //
      // Either way the browser returns to the signed-out screen: the cookie may or may
      // not have been cleared, the next request settles it, and leaving someone staring
      // at a shell they have asked to leave is the worse of the two outcomes.
    }
    setState({ phase: "signed-out" });
  }, []);

  // Deliberately renders nothing but a line of text while checking. A full-screen
  // sign-in panel that flashes for 80ms and disappears is worse than a brief blank,
  // and a spinner would be looping motion for a wait that is normally imperceptible.
  if (state.phase === "checking") {
    return (
      <div className="grid h-screen place-items-center bg-surface">
        <p className="text-sm text-muted-foreground" role="status">
          Checking your session…
        </p>
      </div>
    );
  }

  if (state.phase === "ready") {
    return (
      <SessionContext.Provider value={{ context: state.context, signOut }}>
        {children}
      </SessionContext.Provider>
    );
  }

  return (
    <div className="grid h-screen place-items-center bg-surface px-6">
      <Panel>
        {state.phase === "signed-out" ? (
          <SignedOut />
        ) : state.phase === "needs-workspace" ? (
          <ChooseWorkspace onSelected={check} stale={state.stale} />
        ) : (
          <Failed error={state.error} onRetry={check} />
        )}
      </Panel>
    </div>
  );
}

/**
 * The card these three states share.
 *
 * Enter is `opacity` + a 6px rise over 200ms — the `--duration-state` tier, and the
 * only motion on this screen. It earns its place because the panel replaces a blank
 * viewport: without it the card appears with no indication of where it came from.
 * Frequency justifies it too — a sign-in screen is seen once a session, not hundreds
 * of times a day.
 */
function Panel({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={{ opacity: 0, y: reduce ? 0 : 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduce ? 0 : 0.2, ease: EASE }}
      className="w-full max-w-sm"
    >
      <Card className="p-8">{children}</Card>
    </motion.div>
  );
}

function SignedOut() {
  return (
    <>
      <h1 className="text-lg font-semibold text-foreground">Meridian</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        The governed institutional-memory layer for startup boards.
      </p>
      <p className="mt-6 text-sm text-foreground">Sign in to continue.</p>
      {/*
        A full navigation, not a fetch. The OIDC flow redirects to the identity
        provider and back, which an XHR cannot follow.
      */}
      <Button className="mt-4 w-full" onClick={() => { window.location.href = LOGIN_URL; }}>
        Sign in
      </Button>
    </>
  );
}

/**
 * Workspace selection.
 *
 * **There is no list, and its absence is the design.** `membership` and `workspace` are
 * RLS-scoped, so no endpoint can answer "which workspaces does this person belong to"
 * — that question is a membership oracle, and CP5b refused to build one. Selection is
 * verification: you name a workspace and the server confirms or refuses.
 *
 * The last accepted id is remembered locally so that a returning demo is one click.
 * It is a convenience on this device, never an assertion of access — the server
 * re-verifies membership on selection and again on every subsequent request.
 */
function ChooseWorkspace({ onSelected, stale }: { onSelected: () => void; stale?: boolean }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const remembered = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
    if (remembered) setValue(remembered);
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const workspaceId = value.trim();
    if (!workspaceId) return;

    setBusy(true);
    setError(null);
    try {
      await authApi.selectWorkspace(workspaceId);
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceId);
      onSelected();
    } catch (e) {
      // The server's own message is shown rather than a friendlier invention. It
      // deliberately does not distinguish "no such workspace" from "you are not a
      // member" — telling them apart is the oracle this endpoint refuses to be.
      setError(e instanceof ApiError ? e.message : "Could not reach the server.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <h1 className="text-lg font-semibold text-foreground">Choose a workspace</h1>
      {/*
        The `stale` copy says the selection is no longer available and stops
        there. It does not say whether the membership was revoked, was never
        held, or the workspace does not exist — the server refuses to
        distinguish those (a membership oracle), and a client that guessed would
        leak exactly what the API withholds.
      */}
      <p className="mt-1 text-sm text-muted-foreground">
        {stale
          ? "The workspace this session was using is no longer available to you. Choose one to continue."
          : "You are signed in. Meridian acts inside one workspace at a time, so this session needs one before it can read anything."}
      </p>

      <label htmlFor="workspace-id" className="mt-6 block text-sm font-medium text-foreground">
        Workspace ID
      </label>
      <Input
        id="workspace-id"
        className="mt-2"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="00000000-0000-0000-0000-000000000000"
        autoComplete="off"
        spellCheck={false}
        autoFocus
        aria-describedby={error ? "workspace-error" : undefined}
        aria-invalid={error ? true : undefined}
      />

      {error && (
        <p id="workspace-error" role="alert" className="mt-2 text-sm text-danger-emphasis">
          {error}
        </p>
      )}

      <Button type="submit" className="mt-4 w-full" loading={busy} disabled={!value.trim()}>
        Continue
      </Button>
    </form>
  );
}

function Failed({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <>
      <h1 className="text-lg font-semibold text-foreground">Meridian is unavailable</h1>
      <p className="mt-1 text-sm text-muted-foreground">{error.message}</p>
      <Button variant="secondary" className="mt-6 w-full" onClick={onRetry}>
        Try again
      </Button>
    </>
  );
}
