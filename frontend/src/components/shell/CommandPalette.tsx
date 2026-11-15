import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CornerDownLeft, Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { UserAvatar } from "@/components/ui/avatar";
import { useCampaignList } from "@/features/campaigns/hooks";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { leadsService } from "@/services/resources";
import { cn } from "@/lib/utils";
import { footerNav, primaryNav } from "./navigation";

interface Item {
  id: string;
  group: "Pages" | "Campaigns" | "Sender accounts" | "Leads";
  label: string;
  hint?: string;
  to: string;
  leading?: ReactNode;
}

const MAX_RESULTS = 8;

/** Ctrl or Cmd + K: jump to any page, campaign, sender account or lead. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const list = useRef<HTMLUListElement>(null);

  // Only fetched while the palette is open; the campaign and account lists are usually already cached.
  const leads = useQuery({ queryKey: ["palette", "leads"], queryFn: () => leadsService.list(), enabled: open, staleTime: 60_000 });
  const campaigns = useCampaignList();
  const accounts = useSenderAccounts();

  const items = useMemo<Item[]>(() => {
    const pages: Item[] = [...primaryNav, ...footerNav, { label: "Content publishing", to: "/others/publishing", icon: primaryNav[0].icon }].map((page) => ({
      id: `page-${page.to}`,
      group: "Pages",
      label: page.label,
      to: page.to,
    }));
    const campaignItems: Item[] = (campaigns.data ?? []).map((campaign) => ({ id: `c-${campaign.id}`, group: "Campaigns", label: campaign.name, hint: campaign.status, to: "/campaigns" }));
    const accountItems: Item[] = (accounts.data ?? []).map((account) => ({
      id: `a-${account.id}`,
      group: "Sender accounts",
      label: account.name,
      to: "/linkedin-accounts",
      leading: <UserAvatar name={account.name} src={account.avatarUrl} className="size-6" />,
    }));
    const leadItems: Item[] = (leads.data ?? []).map((lead) => ({
      id: `l-${lead.id}`,
      group: "Leads",
      label: `${lead.firstName} ${lead.lastName}`.trim(),
      hint: lead.company || undefined,
      to: "/leads",
      leading: <UserAvatar name={`${lead.firstName} ${lead.lastName}`} src={lead.avatarUrl} className="size-6" />,
    }));
    return [...pages, ...campaignItems, ...accountItems, ...leadItems];
  }, [campaigns.data, accounts.data, leads.data]);

  const results = useMemo(() => {
    const query = text.trim().toLowerCase();
    const matching = query ? items.filter((item) => `${item.label} ${item.hint ?? ""}`.toLowerCase().includes(query)) : items.filter((item) => item.group === "Pages");
    const perGroup = new Map<string, Item[]>();
    for (const item of matching) perGroup.set(item.group, [...(perGroup.get(item.group) ?? []), item]);
    return [...perGroup.values()].flatMap((group) => group.slice(0, query ? 5 : 20)).slice(0, MAX_RESULTS * 2);
  }, [items, text]);

  useEffect(() => setActive(0), [text, open]);
  useEffect(() => {
    if (!open) setText("");
  }, [open]);
  useEffect(() => {
    list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const go = (item: Item | undefined) => {
    if (!item) return;
    onOpenChange(false);
    navigate(item.to);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(index + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(results[active]);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent hideClose className="top-[20%] max-w-xl translate-y-0 gap-0 p-0">
        <DialogTitle className="sr-only">Search Synex</DialogTitle>
        <DialogDescription className="sr-only">Type to find a page, campaign, sender account or lead. Use the arrow keys and Enter.</DialogDescription>
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            role="combobox"
            aria-expanded
            aria-controls="palette-results"
            aria-activedescendant={results[active] ? `palette-${results[active].id}` : undefined}
            aria-label="Search pages, campaigns, accounts and leads"
            placeholder="Search pages, campaigns, accounts and leads"
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            className="h-14 w-full bg-transparent text-base text-foreground placeholder:text-subtle focus:outline-none"
          />
        </div>
        <ul id="palette-results" ref={list} role="listbox" aria-label="Results" className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted-foreground">Nothing matches "{text}". Try a name, a company or a page.</li>}
          {results.map((item, index) => (
            <li key={item.id} role="presentation">
              {(index === 0 || results[index - 1].group !== item.group) && <p className="px-3 pb-1 pt-3 text-xs font-medium text-muted-foreground">{item.group}</p>}
              <button
                type="button"
                id={`palette-${item.id}`}
                role="option"
                aria-selected={index === active}
                tabIndex={-1}
                onMouseMove={() => setActive(index)}
                onClick={() => go(item)}
                className={cn("flex min-h-10 w-full items-center gap-3 rounded-md px-3 text-left text-sm", index === active ? "bg-primary-soft text-primary-soft-foreground" : "text-foreground")}
              >
                {item.leading}
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.hint && <span className="truncate text-xs text-muted-foreground">{item.hint}</span>}
                {index === active && <CornerDownLeft className="size-4 shrink-0" aria-hidden />}
              </button>
            </li>
          ))}
        </ul>
        <p className="border-t border-border px-4 py-2 text-xs text-muted-foreground">Arrow keys to move, Enter to open, Esc to close.</p>
      </DialogContent>
    </Dialog>
  );
}

/** Ctrl or Cmd + K opens the palette from anywhere in the app. */
export function usePaletteShortcut(toggle: () => void) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
}
