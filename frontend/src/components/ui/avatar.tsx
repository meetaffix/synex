import * as React from "react";
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import { cn } from "@/lib/utils";
import { getInitials } from "@/utils/format";

const Avatar = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Root>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Root
    ref={ref}
    className={cn(
      "relative flex h-9 w-9 shrink-0 overflow-hidden rounded-full",
      className
    )}
    {...props}
  />
));
Avatar.displayName = AvatarPrimitive.Root.displayName;

const AvatarImage = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Image>,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Image>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Image
    ref={ref}
    className={cn("aspect-square h-full w-full object-cover", className)}
    {...props}
  />
));
AvatarImage.displayName = AvatarPrimitive.Image.displayName;

const AvatarFallback = React.forwardRef<
  React.ElementRef<typeof AvatarPrimitive.Fallback>,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Fallback>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Fallback
    ref={ref}
    className={cn(
      "flex h-full w-full items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary-soft-foreground",
      className
    )}
    {...props}
  />
));
AvatarFallback.displayName = AvatarPrimitive.Fallback.displayName;

/** Five tint pairs, each already measured for contrast in both themes (docs/DESIGN.md): a person always gets the same one. */
const TONES = [
  "bg-primary-soft text-primary-soft-foreground",
  "bg-info-soft text-info",
  "bg-accent-soft text-accent",
  "bg-success-soft text-success",
  "bg-warning-soft text-warning",
];

export function toneFor(name: string): string {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return TONES[hash % TONES.length];
}

interface UserAvatarProps {
  name: string;
  src?: string | null;
  className?: string;
}

/** A picture, or the person's initials on a colour taken from their name. */
function UserAvatar({ name, src, className }: UserAvatarProps) {
  return (
    <Avatar className={className}>
      {src ? <AvatarImage src={src} alt="" /> : null}
      <AvatarFallback className={toneFor(name)}>{getInitials(name)}</AvatarFallback>
    </Avatar>
  );
}

/** Overlapping avatars for the people or accounts that share something, with a count for the rest. */
function AvatarStack({ people, max = 3, className }: { people: { name: string; src?: string | null }[]; max?: number; className?: string }) {
  const shown = people.slice(0, max);
  const rest = people.length - shown.length;
  return (
    <span role="img" aria-label={people.map((person) => person.name).join(", ")} className={cn("inline-flex -space-x-1.5", className)}>
      {shown.map((person) => (
        <UserAvatar key={person.name} name={person.name} src={person.src} className="size-7 ring-2 ring-surface" />
      ))}
      {rest > 0 && <span className="grid size-7 place-items-center rounded-full bg-surface-muted text-xs font-medium text-muted-foreground ring-2 ring-surface">+{rest}</span>}
    </span>
  );
}

export { Avatar, AvatarImage, AvatarFallback, UserAvatar, AvatarStack };
