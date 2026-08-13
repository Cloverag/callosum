import { FileText, Upload } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function DocumentsPage() {
  return (
    <div className="p-6">
      <PageHeader
        title="Documents"
        description="Source documents ingested into the workspace memory graph."
        icon={<FileText />}
      />
      <Card className="mt-6">
        <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
          <span className="flex size-12 items-center justify-center rounded-full border border-border bg-surface-elevated text-muted-foreground">
            <FileText className="size-6" />
          </span>
          <div>
            <h3 className="text-sm font-medium text-foreground">No documents yet</h3>
            <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
              Ingest a board pack, transcript, or PDF to build institutional memory. Every source stays
              attributable and permission-scoped.
            </p>
          </div>
          <Button className="mt-1">
            <Upload className="size-4" />
            Ingest document
          </Button>
        </div>
      </Card>
    </div>
  );
}
