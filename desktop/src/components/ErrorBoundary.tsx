import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error in component tree:', error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 rounded-2xl bg-surface/80 border border-rose-500/30 text-white my-4 max-w-2xl mx-auto shadow-2xl backdrop-blur-md">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
              <AlertTriangle size={20} />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-bold text-rose-200">
                {this.props.fallbackTitle || 'Component Error'}
              </h3>
              <p className="text-xs text-gray-300 mt-1 mb-3">
                {this.props.fallbackMessage || 'An unexpected rendering error occurred in this view.'}
              </p>
              {this.state.error && (
                <pre className="text-[11px] font-mono bg-background/80 p-3 rounded-lg border border-border-subtle text-rose-300 overflow-x-auto max-h-32 mb-4">
                  {this.state.error.message || String(this.state.error)}
                </pre>
              )}
              <button
                onClick={this.handleReset}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent text-gray-950 font-bold text-xs hover:bg-accent-light transition-all cursor-pointer shadow"
              >
                <RefreshCw size={13} /> Try Again
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
