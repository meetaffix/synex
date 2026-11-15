import React from "react";
import { RotateCw } from "lucide-react";
import { Illustration } from "@/components/brand/Illustration";
import { Button } from "@/components/ui/button";

interface Props {
  children: React.ReactNode;
}
interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // In production this would be reported to Sentry / Logflare.
    console.error("Uncaught render error:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="grid min-h-[60vh] place-items-center p-6">
          <div className="max-w-md rounded-lg border border-border bg-surface p-4 text-center sm:p-6">
            <Illustration name="error" className="mx-auto mb-4" />
            <h2 className="text-xl font-semibold">This part of the page failed to load</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Synex hit an unexpected problem drawing this view. Your data is safe. Try again, and if it keeps happening, reload the page.
            </p>
            {this.state.error && (
              <pre className="mt-4 max-h-32 overflow-auto rounded-md bg-surface-muted p-3 text-left text-xs text-muted-foreground">
                {this.state.error.message}
              </pre>
            )}
            <Button onClick={this.handleReset} className="mt-5" variant="secondary">
              <RotateCw className="h-4 w-4" />
              Try again
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
