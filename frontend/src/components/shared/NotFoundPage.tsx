import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/shared/Logo";
import { EmptyState } from "@/components/shared/EmptyState";

export function NotFoundPage() {
  return (
    <main className="grid min-h-dvh content-center justify-items-center gap-8 bg-background px-4 py-12">
      <Logo />
      <h1 className="sr-only">Page not found</h1>
      <EmptyState
        illustration="error"
        title="This page does not exist"
        description="The address may be mistyped, or the page has moved. Your work is still where you left it."
        action={
          <Button asChild>
            <Link to="/dashboard">Go to the dashboard</Link>
          </Button>
        }
        className="w-full max-w-lg"
      />
    </main>
  );
}
