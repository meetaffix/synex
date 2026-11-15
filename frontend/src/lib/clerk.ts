/** Clerk mode is on when a publishable key is built in. Without one the app uses its own email and password sign-in. */
export const clerkPublishableKey: string | undefined = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || undefined;
export const clerkEnabled = !!clerkPublishableKey;
