import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { CommandPalette, usePaletteShortcut } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

const STORAGE_KEY = "synex.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  usePaletteShortcut(() => setPaletteOpen((open) => !open));
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const shownPath = useRef(pathname);

  useEffect(() => {
    if (shownPath.current === pathname) return;
    shownPath.current = pathname;
    setDrawerOpen(false);
    // After a route change, move focus to the content so keyboard and screen-reader users start there.
    main.current?.focus({ preventScroll: true });
  }, [pathname]);

  const toggle = () =>
    setCollapsed((current) => {
      try {
        localStorage.setItem(STORAGE_KEY, current ? "0" : "1");
      } catch {
        /* the preference is a convenience only */
      }
      return !current;
    });

  return (
    <div className="min-h-dvh bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-sm focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:shadow-float"
      >
        Skip to content
      </a>
      <aside
        aria-label="Sidebar"
        className={cn(
          "fixed inset-y-0 left-0 z-30 hidden border-r border-border bg-surface text-foreground transition-[width] duration-200 motion-reduce:transition-none lg:block",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <Sidebar collapsed={collapsed} onToggleCollapsed={toggle} onOpenPalette={() => setPaletteOpen(true)} />
      </aside>
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent
          onCloseAutoFocus={(event) => {
            // Return focus to the button that opened the drawer, unless a link already moved it to the page.
            event.preventDefault();
            if (document.activeElement === document.body || !main.current?.contains(document.activeElement)) opener.current?.focus();
          }}
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Pages in your workspace</SheetDescription>
          <Sidebar onOpenPalette={() => { setDrawerOpen(false); setPaletteOpen(true); }} />
        </SheetContent>
      </Sheet>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <div className={cn("flex min-h-dvh flex-col transition-[padding] motion-reduce:transition-none", collapsed ? "lg:pl-16" : "lg:pl-60")}>
        <TopBar onOpenNavigation={() => setDrawerOpen(true)} openerRef={opener} />
        <main id="main-content" ref={main} tabIndex={-1} className="mx-auto w-full min-w-0 max-w-screen-xl flex-1 px-4 py-6 focus-visible:outline-none sm:py-8 lg:px-8">
          <ErrorBoundary key={pathname}>
            {/* Each page fades and rises into place (200ms); reduced motion shows it at once. */}
            <div key={pathname} className="animate-rise">
              <Outlet />
            </div>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
