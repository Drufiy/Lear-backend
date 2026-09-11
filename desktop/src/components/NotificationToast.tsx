import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { AppNotification } from '../hooks/useNotifications';

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
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id);
    }, 6000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

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
        return 'border-rose-500/30 bg-rose-500/10';
      case 'warning':
        return 'border-amber-500/30 bg-amber-500/10';
      case 'success':
        return 'border-accent/30 bg-accent/10';
      default:
        return 'border-border-subtle bg-surface-elevated/90';
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
      <div className="flex items-start gap-3 min-w-0">
        {getIcon()}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-bold text-xs truncate">{toast.title}</span>
            {toast.connector && (
              <span className="text-[9px] uppercase font-mono px-1.5 py-0.2 rounded bg-white/10 text-gray-300">
                {toast.connector}
              </span>
            )}
          </div>
          <p className="text-[11px] text-gray-300 mt-1 line-clamp-2">{toast.message}</p>
          <span className="text-[9px] text-gray-500 font-mono mt-1 block">
            {new Date(toast.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </div>

      <button
        onClick={() => onDismiss(toast.id)}
        className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors shrink-0"
      >
        <X size={14} />
      </button>
    </motion.div>
  );
};

export default NotificationToast;
