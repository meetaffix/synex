import { ApiError } from "@/services/client";
import type { AttemptErrorCode } from "./schemas";

export const identifierHelp = "Enter an email address, or a phone number with country code like +14155550123.";

export const complianceNote =
  "Automating LinkedIn goes against LinkedIn's terms, so accounts can be restricted. Keep daily limits conservative.";

/** One message per failure code: what happened and what to do next. */
export const failureCopy: Record<AttemptErrorCode, { title: string; detail: string }> & { gone: string } = {
  invalid_credentials: {
    title: "LinkedIn did not accept those details",
    detail: "Check the email and password, and any verification code, then try again.",
  },
  timeout: {
    title: "LinkedIn took too long to respond",
    detail: "Nothing was saved. Try again in a few minutes.",
  },
  proxy_error: {
    title: "Synex could not connect through the proxy",
    detail: "Check the proxy address and credentials, or remove the proxy, then try again.",
  },
  cancelled: {
    title: "The connection was cancelled",
    detail: "Nothing was saved. Start again whenever you are ready.",
  },
  unknown: {
    title: "The connection did not complete",
    detail: "Nothing was saved. Try again. If it keeps failing, check that you can sign in to LinkedIn yourself.",
  },
  gone: "This connection attempt is no longer available. Start again.",
};

export const codeCopy = {
  email_code: { label: "Email code", prompt: "LinkedIn emailed you a verification code. Enter it to continue." },
  sms_code: { label: "Text message code", prompt: "LinkedIn texted you a verification code. Enter it to continue." },
  authenticator_code: {
    label: "Authenticator code",
    prompt: "Enter the current code from your authenticator app to continue.",
  },
} as const;

/** Explains a failed request in terms of what the person should do next. */
export function requestFailureMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  switch (error.status) {
    case 404:
      return "This link has expired or was already used. Ask for a new one.";
    case 409:
      return "Another connection for this account is already running. Wait for it to finish or cancel it, then try again.";
    case 429:
      return "Too many attempts. Wait a minute, then try again.";
    default:
      return error.message;
  }
}
