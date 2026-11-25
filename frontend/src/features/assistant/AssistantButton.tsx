import { MessagesSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAssistant } from "./AssistantProvider";

/** Top bar button. Ctrl or Cmd + J does the same. */
export function AssistantButton() {
  const { open, toggle } = useAssistant();
  return (
    <Button
      id="assistant-button"
      variant="secondary"
      size="sm"
      onClick={toggle}
      aria-pressed={open}
      aria-keyshortcuts="Control+J Meta+J"
      title="Assistant (Ctrl or Cmd + J)"
    >
      <MessagesSquare aria-hidden />
      <span className="max-sm:sr-only">Assistant</span>
    </Button>
  );
}
