import Link from "next/link";
import { Card } from "@/components/ui/card";

/**
 * A route that does not exist.
 *
 * Separate from `error.tsx` on purpose: nothing failed here, so the page must
 * not suggest retrying. The only useful action is to go somewhere real, and the
 * dashboard is where `/` already resolves to.
 */
export default function NotFound() {
  return (
    <div className="p-8">
      <Card className="mx-auto max-w-lg p-10 text-center">
        <p className="text-sm text-foreground">That page does not exist.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          The link may be out of date, or the record may have been superseded.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-block rounded-[12px] border border-border-strong px-4 py-2 text-sm font-medium text-foreground hover:bg-surface-alt focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
        >
          Go to the dashboard
        </Link>
      </Card>
    </div>
  );
}
