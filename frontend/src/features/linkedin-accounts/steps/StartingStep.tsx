import { useEffect, useState } from "react";
import { WaitingStep } from "./WaitingStep";

/** After this long the wait is no longer "usual": say so, and say what happens next. */
export const SLOW_AFTER_SECONDS = 45;

interface Props {
  onCancel: () => void;
}

/** "Signing in" with the time spent so far, so a long wait never looks the same as a short one. */
export function StartingStep({ onCancel }: Props) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const slow = seconds >= SLOW_AFTER_SECONDS;
  return (
    <WaitingStep title="Signing in to LinkedIn" onCancel={onCancel}>
      {slow
        ? `Waiting ${seconds} seconds. This is taking longer than usual. If LinkedIn's page cannot be read, Synex stops after about a minute and a half and says what LinkedIn showed. Nothing is saved until the sign-in succeeds.`
        : `Waiting ${seconds} seconds. This usually takes under a minute. Keep this window open.`}
    </WaitingStep>
  );
}
