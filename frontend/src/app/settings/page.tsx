"use client";

import { Settings as SettingsIcon } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { useSession } from "@/components/session-gate";

/**
 * What this session actually is, and nothing else.
 *
 * This page previously rendered four fixed rows as workspace configuration:
 * "Acme Corp", "Series B", "Members 6", "Default clearance Level 2 — Internal".
 * Every one was invented. The workspace is called "Default Workspace"; nothing
 * in the domain models a funding stage or a default clearance; and the seeded
 * workspace has THREE memberships, so "6" was not merely unmeasured but wrong —
 * a countable number, stated confidently, off by a factor of two.
 *
 * That is the defect the whole product exists to refuse, sitting on the page a
 * reader would most reasonably trust for facts about their own workspace.
 *
 * Everything below now comes from `/auth/context`, which re-derives it from the
 * database on the request. The workspace NAME is deliberately absent rather than
 * guessed: that endpoint returns an id and no name, and an id is the identity
 * this session genuinely holds. Membership count is absent for the same reason —
 * `membership` is RLS-scoped and no endpoint exposes a count, so there is no
 * honest way for this page to know one.
 */
export default function SettingsPage() {
  const session = useSession();
  const ctx = session?.context;

  const rows: { label: string; value: string; mono?: boolean }[] = [
    { label: "Workspace", value: ctx?.workspace_id ?? "—", mono: true },
    { label: "Signed in as", value: ctx?.name ?? "—" },
    { label: "Your role", value: ctx?.role ?? "—" },
    {
      label: "Your clearance",
      value: ctx ? `Level ${ctx.clearance}` : "—",
    },
  ];

  return (
    <div className="p-6">
      <PageHeader
        title="Settings"
        description="What this session is, re-derived from the server on every request."
        icon={<SettingsIcon />}
      />
      <Card className="mt-6 max-w-2xl overflow-hidden">
        <dl className="divide-y divide-border">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-4 px-5 py-3">
              <dt className="text-sm text-muted-foreground">{r.label}</dt>
              <dd
                className={
                  r.mono
                    ? "font-mono text-[13px] font-medium text-foreground"
                    : "text-sm font-medium text-foreground"
                }
              >
                {r.value}
              </dd>
            </div>
          ))}
        </dl>
      </Card>
      <p className="mt-3 max-w-2xl text-xs text-muted-foreground">
        Workspace-level configuration — name, members, policy — is not shown because no
        endpoint exposes it. Membership is scoped by row-level security, so a count would
        have to be invented rather than read.
      </p>
    </div>
  );
}
