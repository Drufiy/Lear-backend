import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X, Sparkles } from 'lucide-react';
import { AppNotification } from '../hooks/useNotifications';
import { useLear } from '../context/LearContext';

interface NotificationToastProps {
  toasts: AppNotification[];
  onDismiss: (id: string) => void;
}

export const NotificationToast: React.FC<NotificationToastProps> = ({ toasts, onDismiss }) => {
  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
      <AnimatePresence>
        {toasts.map(toast => (
          <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
};

const ToastItem: React.FC<{ toast: AppNotification; onDismiss: (id: string) => void }> = ({
  toast,
  onDismiss,
}) => {
  const { openChat } = useLear();

  // B2. Severity-based auto-dismiss (5s for info/success, 10s for warning/error)
  useEffect(() => {
    const duration = toast.severity === 'error' || toast.severity === 'warning' ? 10000 : 5000;
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, duration);
    return () => clearTimeout(timer);
  }, [toast.id, toast.severity, onDismiss]);

  const getIcon = () => {
    switch (toast.severity) {
      case 'error':
        return <AlertCircle size={18} className="text-rose-400 shrink-0 mt-0.5" />;
      case 'warning':
        return <AlertTriangle size={18} className="text-amber-400 shrink-0 mt-0.5" />;
      case 'success':
        return <CheckCircle2 size={18} className="text-accent shrink-0 mt-0.5" />;
      default:
        return <Info size={18} className="text-cyan-400 shrink-0 mt-0.5" />;
    }
  };

  const getBorderColor = () => {
    switch (toast.severity) {
      case 'error':
        return 'border-rose-500/30 bg-rose-950/40 shadow-rose-950/50';
      case 'warning':
        return 'border-amber-500/30 bg-amber-950/40 shadow-amber-950/50';
      case 'success':
        return 'border-accent/30 bg-surface-elevated/90 shadow-accent/10';
      default:
        return 'border-border-subtle bg-surface-elevated/90 shadow-black/50';
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
      className={`pointer-events-auto p-4 rounded-xl border backdrop-blur-xl shadow-2xl flex items-start justify-between gap-3 text-white ${getBorderColor()}`}
    >
      <div className="flex items-start gap-3 min-w-0 flex-1">
        {getIcon()}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-bold text-xs truncate">{toast.title}</span>
            {toast.connector && (
              <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-white/10 text-gray-300">
                {toast.connector}
              </span>
            )}
          </div>
          <p className="text-[11px] text-gray-300 mt-1 line-clamp-2 leading-relaxed">{toast.message}</p>
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-[9px] text-gray-500 font-mono">
              {new Date(toast.timestamp).toLocaleTimeString()}
            </span>
            {toast.incidentId || toast.connector ? (
              <button
                onClick={() => {
                  if (toast.incidentId) {
                    openChat({
                      incidentId: toast.incidentId,
                      title: toast.title,
                      errorSummary: toast.message,
                      ...(toast.incidentData || {}),
                    });
                  } else {
                    openChat({ connectorId: toast.connector });
                  }
                  onDismiss(toast.id);
                }}
                className="text-[10px] text-accent hover:underline flex items-center gap-1 font-bold cursor-pointer"
              >
                <Sparkles size={11} />
                {toast.incidentId ? 'Review in Copilot' : 'Investigate'}
              </button>
            ) : null}
          </div>
        </div>
      </div>

      <button
        onClick={() => onDismiss(toast.id)}
        className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors shrink-0 cursor-pointer"
      >
        <X size={14} />
      </button>
    </motion.div>
  );
};

export default NotificationToast;
