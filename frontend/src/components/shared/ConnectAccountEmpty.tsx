import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { EmptyState } from "./EmptyState";

interface Props {
  title: string;
  description: string;
}

/** Shown on outreach pages when no sender account exists: everything else depends on one. */
export function ConnectAccountEmpty({ title, description }: Props) {
  return (
    <EmptyState
      illustration="accounts"
      title={title}
      description={description}
      action={
        <Button asChild>
          <Link to="/linkedin-accounts?connect=1">Connect LinkedIn account</Link>
        </Button>
      }
    />
  );
}
