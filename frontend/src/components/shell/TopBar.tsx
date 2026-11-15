import { Fragment, type Ref } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { breadcrumbsFor } from "./navigation";
import { UserMenu } from "./UserMenu";

export function TopBar({ onOpenNavigation, openerRef }: { onOpenNavigation: () => void; openerRef: Ref<HTMLButtonElement> }) {
  const crumbs = breadcrumbsFor(useLocation().pathname);
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/95 px-4 backdrop-blur lg:px-8">
      <Button ref={openerRef} variant="ghost" size="icon" className="lg:hidden" onClick={onOpenNavigation} aria-label="Open navigation">
        <Menu />
      </Button>
      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex items-center gap-2 text-sm">
          {crumbs.map((crumb, index) => (
            <Fragment key={crumb.label}>
              {index > 0 && (
                <li aria-hidden className="text-muted-foreground">
                  /
                </li>
              )}
              <li className="min-w-0 truncate">
                {crumb.to ? (
                  <Link to={crumb.to} className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="font-medium">
                    {crumb.label}
                  </span>
                )}
              </li>
            </Fragment>
          ))}
        </ol>
      </nav>
      <UserMenu compact />
    </header>
  );
}
