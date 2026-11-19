import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Settings, ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { useAuth } from "@/features/auth/AuthContext";
import { api } from "@/services/client";
import { usePreferences, useRefresh, formatDate } from "./data";
import { Header, Status, Load, ZoneList } from "./shared";

export function SettingsPage() {
  const { user, updateUser, logout } = useAuth(),
    prefs = usePreferences(),
    refresh = useRefresh();
  const [name, setName] = useState(user?.fullName ?? ""),
    [company, setCompany] = useState(user?.company ?? ""),
    [phone, setPhone] = useState(user?.phone ?? ""),
    [designation, setDesignation] = useState(user?.designation ?? ""),
    [zone, setZone] = useState("UTC"),
    [zoneEdited, setZoneEdited] = useState(false),
    [busy, setBusy] = useState(false),
    [oldPassword, setOldPassword] = useState(""),
    [password, setPassword] = useState("");
  const team = useQuery({
    queryKey: ["team"],
    queryFn: () =>
      api.get<{ seat: { role: string }; members: unknown[] }>("/team"),
  });
  const identity = useQuery({
    queryKey: ["publishing", "identity"],
    queryFn: () => api.get<{ linked: boolean }>("/linkedin/sign-in-identity"),
  });
  const [unlinkPassword, setUnlinkPassword] = useState("");
  const identityAction = async () => {
    setBusy(true);
    try {
      if (identity.data?.linked) {
        await api.post("/linkedin/unlink-sign-in", {
          password: unlinkPassword,
        });
        setUnlinkPassword("");
        await identity.refetch();
        toast.success("LinkedIn sign-in removed");
      } else {
        const result = await api.post<{ url: string }>(
          "/linkedin/link-sign-in",
        );
        window.location.assign(result.url);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const status = new URLSearchParams(window.location.search).get("linkedin");
    if (status) {
      toast[status === "linked" ? "success" : "error"](
        status === "linked"
          ? "LinkedIn sign-in linked"
          : "LinkedIn sign-in could not be linked. Please try again.",
      );
      window.history.replaceState(null, "", "/settings");
    }
  }, []);
  const diagnostics = useQuery({
    queryKey: ["publishing", "diagnostics"],
    queryFn: () =>
      api.get<{
        oauthConfigured: boolean;
        workerHealthy: boolean;
        workerLastSeen: string | null;
        aiConfigured: boolean;
      }>("/publishing/diagnostics"),
    enabled: team.data?.seat.role === "admin",
    refetchInterval: 30000,
  });
  useEffect(() => {
    // The saved value fills the box once it arrives, but never over something the person has already typed.
    if (prefs.data && !zoneEdited) setZone(prefs.data.timezone);
  }, [prefs.data, zoneEdited]);
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await api.put<typeof user>("/auth/me", {
        fullName: name,
        company,
        phone,
        designation,
      });
      await api.put("/publishing/preferences", { timezone: zone });
      if (u) updateUser(u);
      setZoneEdited(false);
      await refresh();
      toast.success("Preferences saved");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const change = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/settings", {
        action: "change-password",
        currentPassword: oldPassword,
        newPassword: password,
      });
      toast.success("Password changed. Sign in again.");
      logout();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Header
        title="Settings"
        description="Your profile, preferences, and workspace connections."
      />
      <div className="settings-grid">
        <section>
          <h2>My account</h2>
          <p className="muted">Your personal workspace details.</p>
        </section>
        <form onSubmit={save} className="settings-form">
          <label className="field">
            Full name
            <input
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            Email
            <input value={user?.email ?? ""} disabled />
          </label>
          <label className="field">
            Company
            <input
              maxLength={160}
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </label>
          <label className="field">
            Designation
            <input maxLength={120} value={designation} placeholder="For example, Founder" onChange={(e) => setDesignation(e.target.value)} />
          </label>
          <label className="field">
            Phone
            <input type="tel" maxLength={40} value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label className="field">
            Time zone
            <input
              required
              list="timezones"
              value={zone}
              onChange={(e) => {
                setZone(e.target.value);
                setZoneEdited(true);
              }}
            />
          </label>
          <ZoneList />
          <p className="footnote">
            Used for the calendar and scheduling. Existing scheduled instants
            stay unchanged.
          </p>
          <Button type="submit" loading={busy}>
            Save changes
          </Button>
        </form>
      </div>
      <div className="settings-grid">
        <section>
          <h2>Security</h2>
          <p className="muted">Password changes sign out all sessions.</p>
        </section>
        <form onSubmit={change} className="settings-form">
          <label className="field">
            Current password
            <input
              required
              type="password"
              autoComplete="current-password"
              value={oldPassword}
              onChange={(e) => setOldPassword(e.target.value)}
            />
          </label>
          <label className="field">
            New password
            <input
              required
              minLength={8}
              maxLength={256}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button type="submit" variant="outline" loading={busy}>
            Change password
          </Button>
          <p className="footnote">
            If you signed up with LinkedIn, use password reset to establish an
            email password when email delivery is configured.
          </p>
        </form>
      </div>
      <div className="settings-grid">
        <section>
          <h2>LinkedIn sign-in</h2>
          <p className="muted">
            Control who can enter your Synex account. Publishing permissions are
            managed separately.
          </p>
        </section>
        <div className="settings-form">
          <Load error={identity.error} loading={identity.isLoading} />
          {identity.data && (
            <>
              <Status value={identity.data.linked ? "linked" : "not_linked"} />
              {identity.data.linked && (
                <label className="field">
                  Confirm Synex password to unlink
                  <input
                    type="password"
                    value={unlinkPassword}
                    onChange={(e) => setUnlinkPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                </label>
              )}
              <Button
                variant="outline"
                disabled={identity.data.linked && !unlinkPassword}
                loading={busy}
                onClick={identityAction}
              >
                {identity.data.linked
                  ? "Unlink LinkedIn sign-in"
                  : "Link my LinkedIn sign-in"}
              </Button>
            </>
          )}
        </div>
      </div>
      {team.data?.seat.role === "admin" && (
        <div className="settings-grid">
          <section>
            <h2>Connection diagnostics</h2>
            <p className="muted">Visible to workspace administrators.</p>
          </section>
          <div>
            <Load error={diagnostics.error} loading={diagnostics.isLoading} />
            {diagnostics.data && (
              <>
                <div className="diagnostic-row">
                  <span>LinkedIn OAuth configuration</span>
                  <Status
                    value={
                      diagnostics.data.oauthConfigured
                        ? "configured"
                        : "not_configured"
                    }
                  />
                </div>
                <div className="diagnostic-row">
                  <span>Publishing worker</span>
                  <Status
                    value={
                      diagnostics.data.workerHealthy ? "healthy" : "not_running"
                    }
                  />
                </div>
                <div className="diagnostic-row">
                  <span>Last worker heartbeat</span>
                  <span>{formatDate(diagnostics.data.workerLastSeen)}</span>
                </div>
                <div className="diagnostic-row">
                  <span>Writing assistance</span>
                  <Status
                    value={
                      diagnostics.data.aiConfigured
                        ? "configured"
                        : "not_configured"
                    }
                  />
                </div>
                <p className="footnote">
                  A configured client still requires LinkedIn product approval
                  and a successful authorization. If the worker is offline, ask
                  your operator to start the publishing worker.
                </p>
              </>
            )}
            <Button variant="outline" onClick={() => diagnostics.refetch()}>
              Refresh diagnostics
            </Button>
          </div>
        </div>
      )}
      <div className="settings-grid">
        <section>
          <h2>Resources</h2>
        </section>
        <div className="resource-links">
          <Link to="/others/publishing/connections">
            LinkedIn connections <ArrowUpRight size={16} />
          </Link>
          <Link to="/leads?tab=lists">
            Contact lists <ArrowUpRight size={16} />
          </Link>
          <Link to="/campaigns">
            Campaign archive <ArrowUpRight size={16} />
          </Link>
          <Link to="/inbox">
            Conversation archive <ArrowUpRight size={16} />
          </Link>
        </div>
      </div>
    </>
  );
}
