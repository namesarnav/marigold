import { createContext, useCallback, useContext, useRef, useState } from "react";

const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(0);

  const toast = useCallback((message, type = "success") => {
    const id = ++nextId.current;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3000);
  }, []);

  return (
    <ToastCtx.Provider value={toast}>
      {children}

      <div className="toast toast-end z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`animate-slide-in alert ${
              t.type === "success" ? "alert-success" : "alert-error"
            } shadow-lift`}
          >
            <span className="text-sm">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
