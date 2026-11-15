import { useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { aiService } from "@/services/resources";
import { toast } from "@/components/ui/sonner";

const VARIABLES = [
  { token: "{{first_name}}", label: "First name" },
  { token: "{{last_name}}", label: "Last name" },
  { token: "{{company}}", label: "Company" },
  { token: "{{job_title}}", label: "Job title" },
];

interface MessageEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  maxLength?: number;
  /** When set, shows an AI draft button that generates copy for this step type. */
  aiStepType?: "connection_request" | "message" | "follow_up";
}

export function MessageEditor({
  value,
  onChange,
  placeholder,
  maxLength,
  aiStepType,
}: MessageEditorProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [generating, setGenerating] = useState(false);

  const insert = (token: string) => {
    const el = ref.current;
    if (!el) {
      onChange(value + token);
      return;
    }
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    const next = value.slice(0, start) + token + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + token.length;
      el.setSelectionRange(pos, pos);
    });
  };

  const generate = async () => {
    setGenerating(true);
    try {
      const res = await aiService.generateMessage({ stepType: aiStepType });
      onChange(res.body);
    } catch {
      toast.error("Could not generate a draft");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {VARIABLES.map((v) => (
          <button
            key={v.token}
            type="button"
            onClick={() => insert(v.token)}
            className="rounded-sm border border-border bg-surface-muted/50 px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            {v.label}
          </button>
        ))}
        {aiStepType && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto h-6 px-2 text-xs text-primary"
            loading={generating}
            onClick={generate}
          >
            <Sparkles className="h-3.5 w-3.5" />
            Suggest draft
          </Button>
        )}
      </div>
      <Textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        className="min-h-[110px] resize-y"
      />
      {maxLength && (
        <p className="text-right text-xs text-muted-foreground">
          {value.length}/{maxLength}
        </p>
      )}
    </div>
  );
}
