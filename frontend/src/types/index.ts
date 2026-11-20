/* ------------------------------------------------------------------ */
/* Shared domain types for the SYNEX frontend.                         */
/* These mirror the FastAPI / PostgreSQL schema.                       */
/* ------------------------------------------------------------------ */

export type ID = string;

export interface User {
  id: ID;
  email: string;
  fullName: string;
  avatarUrl?: string | null;
  company?: string | null;
  phone?: string | null;
  designation?: string | null;
  role: string;
  plan: "free" | "pro" | "scale";
  /** True when role is Admin — full access, no subscription prompts. */
  isAdmin?: boolean;
  createdAt: string;
}

export type LinkedInAccountStatus =
  | "pending"
  | "active"
  | "connected"
  | "needs_reconnect"
  | "restricted"
  | "paused"
  | "warming"
  | "disconnected"
  | "session_expired"
  | "proxy_error"
  | "error";

export type LeadStatus =
  | "new"
  | "contacted"
  | "connected"
  | "replied"
  | "interested"
  | "not_interested"
  | "bounced";

export interface Lead {
  id: ID;
  firstName: string;
  lastName: string;
  company: string;
  jobTitle: string;
  headline?: string | null;
  linkedinUrl: string;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  industry?: string | null;
  /** IANA time zone for this lead's working hours; blank uses the campaign's. */
  timezone?: string | null;
  connectedAt?: string | null;
  mutualConnections?: number | null;
  tags: string[];
  /** Custom campaign variables for this person, used as {{name}} in messages. */
  variables?: Record<string, string>;
  source?: string | null;
  status: LeadStatus;
  notes?: string | null;
  listIds: ID[];
  campaignId?: ID | null;
  avatarUrl?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface LeadList {
  id: ID;
  name: string;
  description?: string | null;
  color: string;
  leadCount: number;
  /** Every lead on the list is already a 1st-degree connection, so no connection request is needed. */
  allConnections?: boolean;
  createdAt: string;
}

export type CampaignStatus = "draft" | "active" | "paused" | "completed";

export type StepType =
  | "connection_request"
  | "message"
  | "follow_up"
  | "profile_visit"
  | "follow_profile"
  | "like_post"
  | "wait"
  | "end";

export interface CampaignStep {
  id: ID;
  type: StepType;
  order: number;
  /** For message-like steps */
  message?: string;
  /** For wait steps, in hours */
  delayHours?: number;
}

export interface Campaign {
  id: ID;
  name: string;
  description?: string | null;
  status: CampaignStatus;
  accountId: ID;
  /** Additional sending accounts (load-balanced pool). */
  accountIds: ID[];
  accountName: string;
  accountStatus?: LinkedInAccountStatus | null;
  leadListId: ID;
  leadListName: string;
  dailyConnectionLimit: number;
  dailyMessageLimit: number;
  schedule: {
    timezone: string;
    days: number[]; // 0=Sun ... 6=Sat
    startHour: number;
    endHour: number;
  };
  settings: {
    randomDelay: boolean;
    stopWhenReplied: boolean;
    stopWhenAccepted: boolean;
    aiPersonalization: boolean;
    pauseOnFailure: boolean;
  };
  audienceSource?: {
    type: string;
    filters?: Record<string, string>;
    sourceUrl?: string;
  } | null;
  steps: CampaignStep[];
  stats: {
    totalLeads: number;
    invitesSent: number;
    connected: number;
    replied: number;
    interested: number;
    messagesSent: number;
    acceptanceRate: number;
    replyRate: number;
  };
  createdAt: string;
  updatedAt: string;
}

export type ConversationStatus =
  | "active"
  | "interested"
  | "not_interested"
  | "archived";

export interface Conversation {
  id: ID;
  leadId: ID;
  leadName: string;
  leadTitle: string;
  leadCompany: string;
  linkedinUrl?: string | null;
  avatarUrl?: string | null;
  accountId: ID;
  campaignId?: ID | null;
  campaignName?: string | null;
  lastMessagePreview: string;
  lastMessageAt: string;
  unread: boolean;
  status: ConversationStatus;
}

export interface Message {
  id: ID;
  conversationId: ID;
  direction: "inbound" | "outbound";
  body: string;
  sentAt: string;
  read: boolean;
  // Outbound replies are queued for the extension to deliver, then flip to
  // sent/failed when it reports back. Synced/inbound messages are "sent".
  deliveryStatus?: "queued" | "sent" | "failed";
  deliveryError?: string | null;
}

export type TemplateCategory =
  | "connection"
  | "first_message"
  | "follow_up"
  | "reply";

export interface Template {
  id: ID;
  name: string;
  category: TemplateCategory;
  body: string;
  usageCount: number;
  replyRate: number;
  shortcut?: string | null;
  createdAt: string;
  updatedAt: string;
}

/* ----------------------------- Analytics ---------------------------- */

export interface DashboardStats {
  totalLeads: number;
  totalLeadsDelta: number;
  activeCampaigns: number;
  invitationsSent: number;
  invitationsSentDelta: number;
  repliesReceived: number;
  repliesReceivedDelta: number;
  connectionRate: number;
  replyRate: number;
}

export interface ActivityItem {
  id: ID;
  type:
    | "connection_accepted"
    | "reply_received"
    | "invite_sent"
    | "lead_imported"
    | "campaign_started"
    | "marked_interested";
  title: string;
  description: string;
  timestamp: string;
  leadName?: string;
}

/* --------------------------- Auth payloads -------------------------- */

export interface AuthResponse {
  user: User;
}

