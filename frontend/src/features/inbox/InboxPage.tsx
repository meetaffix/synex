import { useDeferredValue, useState } from "react";
import { Link } from "react-router-dom";
import { Illustration } from "@/components/brand/Illustration";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { ConnectAccountEmpty } from "@/components/shared/ConnectAccountEmpty";
import { PageHeader } from "@/components/shared/PageHeader";
import { requestFailureMessage } from "@/features/linkedin-accounts/copy";
import { useSenderAccounts } from "@/features/linkedin-accounts/hooks";
import { ConversationList, ConversationListLoading, ListMessage } from "./ConversationList";
import { useConversationList } from "./hooks";
import type { ConversationStatus, InboxFilters } from "./service";
import { ThreadView } from "./ThreadView";

const STATUS_OPTIONS: { value: InboxFilters["status"]; label: string }[] = [
  { value: "all", label: "All conversations" },
  { value: "active", label: "Active" },
  { value: "interested", label: "Interested" },
  { value: "not_interested", label: "Not interested" },
  { value: "archived", label: "Archived" },
];

export function InboxPage() {
  const accounts = useSenderAccounts();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<InboxFilters["status"]>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const filters = { search: useDeferredValue(search), status };
  const conversations = useConversationList(filters);
  const filtered = search !== "" || status !== "all";
  const selected = conversations.data?.find((c) => c.id === selectedId) ?? null;

  if (accounts.isSuccess && accounts.data.length === 0) {
    return (
      <div className="grid gap-6">
        <PageHeader title="Inbox" description="Replies from the people your campaigns contact." />
        <ConnectAccountEmpty
          title="Connect LinkedIn account to receive replies"
          description="The inbox shows conversations from your connected LinkedIn accounts. Connect LinkedIn account, run a campaign, and replies from leads appear here."
        />
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      <PageHeader title="Inbox" description="Replies from the people your campaigns contact." />
      <div className="grid grid-cols-[minmax(0,1fr)] overflow-hidden rounded-lg border border-border bg-surface shadow-raised lg:min-h-[32rem] lg:grid-cols-[22rem_minmax(0,1fr)]">
        <section aria-label="Conversation list" className={selected ? "hidden border-border lg:block lg:border-r" : "border-border lg:border-r"}>
          <div className="grid gap-3 border-b border-border p-4">
            <div className="grid gap-2">
              <Label htmlFor="inbox-search">Search conversations</Label>
              <Input id="inbox-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or company" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="inbox-status">Show</Label>
              <NativeSelect id="inbox-status" value={status} onChange={(event) => setStatus(event.target.value as ConversationStatus | "all")}>
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          {conversations.isLoading && <ConversationListLoading />}
          {conversations.isError && (
            <ListMessage title="Conversations could not be loaded" action={{ label: "Try again", onClick: () => void conversations.refetch() }}>
              {requestFailureMessage(conversations.error)}
            </ListMessage>
          )}
          {conversations.data?.length === 0 && filtered && (
            <ListMessage title="No conversations match" action={{ label: "Clear filters", onClick: () => { setSearch(""); setStatus("all"); } }}>
              Try a different name, or show all conversations.
            </ListMessage>
          )}
          {conversations.data?.length === 0 && !filtered && (
            <div className="grid justify-items-center gap-3 p-6 text-center">
              <Illustration name="inbox" className="h-24" />
              <p className="text-sm font-medium">No conversations yet</p>
              <p className="text-sm text-muted-foreground">Conversations appear here once a lead replies to a campaign message.</p>
              <Button asChild size="sm" variant="secondary">
                <Link to="/campaigns">View campaigns</Link>
              </Button>
            </div>
          )}
          {!!conversations.data?.length && (
            <ConversationList conversations={conversations.data} selectedId={selectedId} onSelect={setSelectedId} />
          )}
        </section>
        <section aria-label="Conversation" className={selected ? "" : "hidden lg:block"}>
          {selected ? (
            <ThreadView key={selected.id} conversation={selected} onBack={() => setSelectedId(null)} />
          ) : (
            <div className="grid h-full place-items-center content-center gap-3 p-8 text-center">
              <Illustration name="inbox" />
              <p className="max-w-xs text-sm text-muted-foreground">Select a conversation to read it.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
