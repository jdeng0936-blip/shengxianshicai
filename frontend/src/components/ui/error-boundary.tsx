"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-50">
            <AlertTriangle className="h-7 w-7 text-red-500" />
          </div>
          <h3 className="mt-4 text-sm font-medium text-slate-700">
            页面出现异常
          </h3>
          <p className="mt-1 max-w-sm text-sm text-slate-400">
            {this.state.error?.message || "未知错误"}
          </p>
          <Button
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={this.handleReset}
          >
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            重试
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
