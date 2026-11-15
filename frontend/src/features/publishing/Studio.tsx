import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  PenLine,
  CalendarDays,
  FileText,
  ArrowUpRight,
  Plus,
  Check,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { api, config } from "@/services/client";
import {
  usePosts,
  useAccounts,
  usePreferences,
  useRefresh,
  statusLabel,
  formatDate,
  zonedInstant,
  type Post,
} from "./data";
import { Header, Status, Notice, Load, Profile, ZoneList } from "./shared";

export function Studio() {
  const posts = usePosts(),
    accounts = useAccounts(),
    refresh = useRefresh(),
    prefs = usePreferences();
  const [params, setParams] = useSearchParams();
  const [current, setCurrent] = useState<Post | null>(null),
    [title, setTitle] = useState(""),
    [body, setBody] = useState(""),
    [account, setAccount] = useState("");
  const [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all"),
    [confirm, setConfirm] = useState<"publish" | "schedule" | null>(null),
    [date, setDate] = useState(""),
    [zone, setZone] = useState("UTC");
  const [instruction, setInstruction] = useState("Improve clarity"),
    [suggestion, setSuggestion] = useState("");
  const id = params.get("id"),
    newKey = params.get("new");
  useEffect(() => {
    if (prefs.data) setZone(prefs.data.timezone);
  }, [prefs.data]);
  useEffect(() => {
    if (!posts.data) return;
    const selected = posts.data.find((p) => p.id === id) ?? null;
    if (dirty && selected?.id === current?.id) return;
    setCurrent(selected);
    setTitle(selected?.title ?? "");
    setBody(selected?.body ?? (params.get("text") ?? "").slice(0, 3000));
    setAccount(selected?.accountId ?? "");
    setDirty(!!params.get("text"));
  }, [id, newKey, posts.data]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    const guard = (event: MouseEvent) => {
      const link = (event.target as Element)?.closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        dirty &&
        link &&
        link.origin === window.location.origin &&
        link.pathname !== window.location.pathname &&
        !window.confirm("Discard unsaved changes and leave this draft?")
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener("click", guard, true);
    return () => document.removeEventListener("click", guard, true);
  }, [dirty]);
  const editable =
    !current ||
    ["draft", "paused", "failed", "cancelled"].includes(current.status);
  const canPublish =
    accounts.data?.find((a) => a.id === account)?.capabilities.publishing ===
    "available";
  const save = async () => {
    const data = {
      title,
      body,
      accountId: account || null,
      version: current?.version ?? 1,
    };
    const result = current
      ? await api.put<Post>(`/publishing/posts/${current.id}`, data)
      : await api.post<Post>("/publishing/posts", data);
    setCurrent(result);
    setDirty(false);
    setParams({ id: result.id }, { replace: true });
    await refresh();
    return result;
  };
  const saveClick = async () => {
    setBusy(true);
    try {
      await save();
      toast.success("Draft saved");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const action = async (kind: string) => {
    setBusy(true);
    try {
      const scheduledAt =
        kind === "schedule" ? zonedInstant(date, zone) : undefined;
      if (scheduledAt && new Date(scheduledAt) <= new Date())
        throw new Error("Choose a future date and time.");
      const p = dirty || !current ? await save() : current;
      const result = await api.post<Post>(`/publishing/posts/${p.id}/action`, {
        action: kind,
        version: p.version,
        scheduledAt,
        timezone: zone,
      });
      setCurrent(result);
      setConfirm(null);
      await refresh();
      toast.success(
        kind === "publish"
          ? "Approved and queued for publishing"
          : "Post updated",
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const assist = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ body: string }>("/publishing/assist", {
        body,
        instruction,
      });
      setSuggestion(r.body);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const imageChange = async (file: File | null) => {
    setBusy(true);
    try {
      if (
        file &&
        (file.size > 5 * 1024 * 1024 ||
          !["image/png", "image/jpeg"].includes(file.type))
      )
        throw new Error("Choose a JPEG or PNG up to 5 MB.");
      const p = dirty || !current ? await save() : current;
      let updated: Post;
      if (file) {
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Image could not be read"));
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.readAsDataURL(file);
        });
        updated = await api.put<Post>(`/publishing/posts/${p.id}/image`, {
          version: p.version,
          data,
        });
      } else
        updated = await api.delete<Post>(
          `/publishing/posts/${p.id}/image?version=${p.version}`,
        );
      setCurrent(updated);
      await refresh();
      toast.success(file ? "Image attached" : "Image removed");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const select = (p: Post) => {
    if (dirty && !window.confirm("Discard unsaved changes and open this post?"))
      return;
    setDirty(false);
    setParams({ id: p.id });
  };
  const filtered = (posts.data ?? []).filter(
    (p) =>
      (filter === "all" || p.status === filter) &&
      `${p.title} ${p.body}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <Header
        title="Content studio"
        description="A considered space to write, review, and publish."
        action={
          <Button
            variant="outline"
            onClick={() => {
              if (dirty && !window.confirm("Discard unsaved changes?")) return;
              setDirty(false);
              setParams({ new: String(Date.now()) });
            }}
          >
            <Plus />
            New draft
          </Button>
        }
      />
      <Load
        error={posts.error || accounts.error}
        loading={posts.isLoading || accounts.isLoading}
      />
      {id && posts.data && !current && (
        <Notice>This post could not be found in your workspace.</Notice>
      )}
      <div className="studio-grid">
        <section className="editor-panel">
          <div className="editor-toolbar">
            <span>
              <PenLine size={16} /> {current ? "Edit post" : "New post"}
            </span>
            <span className="muted" role="status">
              {busy
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : current
                    ? "Saved"
                    : "Draft"}
            </span>
          </div>
          <label className="field">
            Publish as
            <select
              value={account}
              disabled={!editable}
              onChange={(e) => {
                setAccount(e.target.value);
                setDirty(true);
              }}
            >
              <option value="">Select a LinkedIn account</option>
              {accounts.data?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} · {statusLabel(a.status)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Internal title
            <input
              placeholder="Give this draft a name"
              maxLength={160}
              value={title}
              disabled={!editable}
              onChange={(e) => {
                setTitle(e.target.value);
                setDirty(true);
              }}
            />
          </label>
          <label className="field writing-field">
            <span>Post</span>
            <textarea
              aria-label="Post"
              placeholder="What would you like to share?"
              maxLength={3000}
              value={body}
              disabled={!editable}
              onChange={(e) => {
                setBody(e.target.value);
                setDirty(true);
              }}
            />
          </label>
          <div className="editor-meta">
            <span>Plain text · One optional image</span>
            <span>{body.length.toLocaleString()} / 3,000</span>
          </div>
          {editable && (
            <div className="image-field">
              <label className="field">
                {current?.hasImage ? "Replace image" : "Attach image"}
                <input
                  type="file"
                  accept="image/jpeg,image/png"
                  disabled={busy}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) imageChange(file);
                    e.target.value = "";
                  }}
                />
              </label>
              <small>
                JPEG or PNG, up to 5 MB. Attaching saves your draft.
              </small>
              {current?.hasImage && (
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => imageChange(null)}
                >
                  Remove image
                </Button>
              )}
            </div>
          )}
          {editable && (
            <details className="writing-assist">
              <summary>Writing assistance</summary>
              <p>
                Review every suggestion before applying it. Requires a
                configured AI provider.
              </p>
              <div className="inline-actions">
                <select
                  aria-label="Writing instruction"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                >
                  {["Improve clarity", "Make concise", "Suggest hashtags"].map(
                    (i) => (
                      <option key={i}>{i}</option>
                    ),
                  )}
                </select>
                <Button
                  variant="outline"
                  disabled={!body.trim()}
                  loading={busy}
                  onClick={assist}
                >
                  Suggest revision
                </Button>
              </div>
              {suggestion && (
                <>
                  <p className="suggestion">{suggestion}</p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setBody(suggestion);
                      setDirty(true);
                      setSuggestion("");
                    }}
                  >
                    Apply suggestion
                  </Button>
                </>
              )}
            </details>
          )}
          <div className="editor-actions">
            {editable ? (
              <>
                <Button
                  variant="outline"
                  disabled={!body.trim() && !title.trim()}
                  loading={busy}
                  onClick={saveClick}
                >
                  Save draft
                </Button>
                <div>
                  <Button
                    variant="outline"
                    disabled={!canPublish || !body.trim() || busy}
                    onClick={() => setConfirm("schedule")}
                  >
                    <CalendarDays />
                    Schedule
                  </Button>
                  <Button
                    disabled={!canPublish || !body.trim() || busy}
                    onClick={() => setConfirm("publish")}
                  >
                    Publish now
                  </Button>
                </div>
              </>
            ) : (
              <>
                <Status value={current!.status} />
                {["scheduled", "retrying"].includes(current!.status) && (
                  <div>
                    <Button
                      variant="outline"
                      loading={busy}
                      onClick={() => action("pause")}
                    >
                      Pause & edit
                    </Button>
                    <Button
                      variant="outline"
                      loading={busy}
                      onClick={() => action("cancel")}
                    >
                      Cancel schedule
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
          {!canPublish && editable && (
            <p className="footnote">
              Save a draft anytime.{" "}
              <Link to="/others/publishing/connections">
                Connect an account with publishing permission
              </Link>{" "}
              to schedule or publish.
            </p>
          )}
          {current?.error && <Notice>{current.error}</Notice>}
          {current?.linkedinId && (
            <a
              className="published-link"
              href={`https://www.linkedin.com/feed/update/${encodeURIComponent(current.linkedinId)}/`}
              target="_blank"
              rel="noreferrer"
            >
              View published post <ArrowUpRight size={15} />
            </a>
          )}
        </section>
        <aside className="preview-column">
          <div className="eyebrow">LinkedIn preview</div>
          <div className="post-preview">
            {accounts.data?.find((a) => a.id === account) ? (
              <Profile account={accounts.data.find((a) => a.id === account)!} />
            ) : (
              <div className="profile-line">
                <span className="profile-placeholder">in</span>
                <div>
                  <strong>Your LinkedIn profile</strong>
                  <small>Public post</small>
                </div>
              </div>
            )}
            <div className="preview-body">
              {body || (
                <span className="muted">
                  Your words, as your audience will see them.
                </span>
              )}
            </div>
            {current?.hasImage && (
              <img
                className="media-preview"
                src={`${config.API_URL}/publishing/posts/${current.id}/image?v=${current.version}`}
                alt="Attached post image"
              />
            )}
            <div className="preview-footer">
              Post preview · Formatting may vary
            </div>
          </div>
          <div className="preview-note">
            <Check size={16} />
            <p>
              You review and approve every post. Scheduled posts publish from
              the server, even when your browser is closed.
            </p>
          </div>
        </aside>
      </div>
      <section className="section library">
        <div className="section-heading">
          <h2>Content library</h2>
          <span className="muted">{posts.data?.length ?? 0} {posts.data?.length === 1 ? "post" : "posts"}</span>
        </div>
        <div className="filter-bar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search content"
              placeholder="Search your content…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            aria-label="Filter content by status"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            {[
              "all",
              "draft",
              "scheduled",
              "paused",
              "published",
              "failed",
              "needs_review",
              "cancelled",
            ].map((s) => (
              <option value={s} key={s}>
                {s === "all" ? "All statuses" : statusLabel(s)}
              </option>
            ))}
          </select>
        </div>
        {filtered.map((p) => (
          <button
            className={`post-row ${p.id === id ? "selected-row" : ""}`}
            key={p.id}
            onClick={() => select(p)}
          >
            <FileText size={18} />
            <span className="post-row-main">
              <strong>
                {p.title || p.body.slice(0, 65) || "Untitled draft"}
              </strong>
              <small>
                {formatDate(p.scheduledAt || p.updatedAt, prefs.data?.timezone)}
              </small>
            </span>
            <Status value={p.status} />
          </button>
        ))}
        {!filtered.length && (
          <div className="quiet-empty">No posts match this view.</div>
        )}
      </section>
      <Dialog
        open={!!confirm}
        onOpenChange={(open) => !open && setConfirm(null)}
      >
        <DialogContent>
          <DialogTitle>
            {confirm === "publish"
              ? "Publish this post?"
              : "Schedule your post"}
          </DialogTitle>
          <DialogDescription>
            {confirm === "publish"
              ? "This approves your post for public publishing to the selected LinkedIn account."
              : "Choose the date, local time, and time zone. The worker will publish this approved post when it is due."}
          </DialogDescription>
          <p>
            <strong>
              {accounts.data?.find((a) => a.id === account)?.name}
            </strong>{" "}
            · {title || "Untitled post"}
          </p>
          {confirm === "schedule" && (
            <>
              <label className="field">
                Date and time
                <input
                  type="datetime-local"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
              <label className="field">
                Time zone
                <input
                  list="timezones"
                  value={zone}
                  onChange={(e) => setZone(e.target.value)}
                />
              </label>
              <ZoneList />
              <p className="footnote">
                During a repeated daylight-saving hour, verify the UTC time
                below.
              </p>
              {date && (
                <p className="muted">
                  {(() => {
                    try {
                      return "Scheduled instant: " + zonedInstant(date, zone);
                    } catch {
                      return "Choose a valid local time and zone.";
                    }
                  })()}
                </p>
              )}
            </>
          )}
          <div className="dialog-actions">
            <Button variant="outline" onClick={() => setConfirm(null)}>
              Keep editing
            </Button>
            <Button
              loading={busy}
              disabled={confirm === "schedule" && !date}
              onClick={() => confirm && action(confirm)}
            >
              {confirm === "publish"
                ? "Approve & publish"
                : "Approve & schedule"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
