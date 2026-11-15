import type { ReactNode } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AppProviders } from "./providers";
import { ProtectedRoute, PublicOnlyRoute } from "@/routes/ProtectedRoute";
import { AppShell } from "@/components/shell/AppShell";

import { LoginPage } from "@/features/auth/pages/LoginPage";
import { RegisterPage } from "@/features/auth/pages/RegisterPage";
import { ForgotPasswordPage } from "@/features/auth/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "@/features/auth/pages/ResetPasswordPage";

import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { InboxPage } from "@/features/inbox/InboxPage";
import { CampaignsPage } from "@/features/campaigns/CampaignsPage";
import { SenderAccountsPage } from "@/features/linkedin-accounts/AccountsPage";
import { ReconnectPage } from "@/features/linkedin-accounts/ReconnectPage";
import { LeadsHub } from "@/features/leads/LeadsHub";
import { TemplatesPage } from "@/features/templates/TemplatesPage";
import { OthersPage } from "@/features/others/OthersPage";
import { HelpPage } from "@/features/help/HelpPage";
import { WelcomePage } from "@/features/onboarding/WelcomePage";
import { DesignPage } from "@/features/design/DesignPage";
import { NotFoundPage } from "@/components/shared/NotFoundPage";
import { PublishingLayout } from "@/features/publishing/PublishingLayout";
import { Overview, AccountsPage, Studio, CalendarPage, AutomationPage, ActivityPage, AnalyticsPage, SettingsPage, ExtensionPage } from "@/features/publishing/Workspace";

/** Old addresses keep working: each one lands on its new home. */
const redirects: [string, string][] = [
  ["/studio", "/others/publishing/studio"],
  ["/calendar", "/others/publishing/calendar"],
  ["/automation", "/others/publishing/queue"],
  ["/activity", "/others/publishing/activity"],
  ["/analytics", "/others/publishing/analytics"],
  ["/publishing/connections", "/others/publishing/connections"],
  ["/extension", "/others/extension"],
  ["/help/extension", "/others/extension"],
  ["/lead-lists", "/leads?tab=lists"],
];

/** An old address keeps whatever came after it, such as the idea the browser extension passes in ?text=. */
function Redirect({ to }: { to: string }) {
  const { search } = useLocation();
  const extra = search.replace(/^\?/, "");
  const target = extra ? `${to}${to.includes("?") ? "&" : "?"}${extra}` : to;
  return <Navigate to={target} replace />;
}

/** Pages written as fragments get the same 24px rhythm as every other page. */
function Stack({ children }: { children: ReactNode }) {
  return <div className="grid gap-6">{children}</div>;
}

export function App() {
  return (
    <AppProviders>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />

        {/* Auth (redirects to dashboard when already signed in) */}
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
        </Route>

        {/* Authenticated app */}
        <Route element={<ProtectedRoute />}>
          <Route path="/welcome" element={<WelcomePage />} />
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/campaigns" element={<CampaignsPage />} />
            <Route path="/linkedin-accounts" element={<SenderAccountsPage />} />
            <Route path="/leads" element={<LeadsHub />} />
            <Route path="/templates" element={<TemplatesPage />} />
            <Route path="/others" element={<OthersPage />} />
            <Route path="/others/extension" element={<Stack><ExtensionPage /></Stack>} />
            <Route path="/others/publishing" element={<PublishingLayout />}>
              <Route index element={<Overview />} />
              <Route path="studio" element={<Studio />} />
              <Route path="calendar" element={<CalendarPage />} />
              <Route path="queue" element={<AutomationPage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="analytics" element={<AnalyticsPage />} />
              <Route path="connections" element={<AccountsPage />} />
            </Route>
            <Route path="/settings" element={<Stack><SettingsPage /></Stack>} />
            <Route path="/help" element={<HelpPage />} />
            {redirects.map(([from, to]) => (
              <Route key={from} path={from} element={<Redirect to={to} />} />
            ))}
          </Route>
        </Route>

        {/* The design system reference, for reviewing tokens and components. Not part of a production build. */}
        {import.meta.env.DEV && <Route path="/design" element={<DesignPage />} />}

        {/* Public: opened from a single-use link, no session needed */}
        <Route path="/reconnect/:token" element={<ReconnectPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppProviders>
  );
}
