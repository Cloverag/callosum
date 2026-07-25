import { Settings as SettingsIcon } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";

const rows = [
  { label: "Workspace", value: "Acme Corp" },
  { label: "Stage", value: "Series B" },
  { label: "Members", value: "6" },
  { label: "Default clearance", value: "Level 2 — Internal" },
];

export default function SettingsPage() {
  return (
    <div className="p-6">
      <PageHeader
        title="Settings"
        description="Workspace configuration and access policy."
        icon={<SettingsIcon />}
      />
      <Card className="mt-6 max-w-2xl overflow-hidden">
        <dl className="divide-y divide-border">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-4 px-5 py-3">
              <dt className="text-sm text-muted-foreground">{r.label}</dt>
              <dd className="text-sm font-medium text-foreground">{r.value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <p className="mt-3 text-xs text-muted-foreground">Editable settings arrive in a later release.</p>
    </div>
  );
}
