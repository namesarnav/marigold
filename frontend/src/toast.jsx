import { createContext, useContext, useState, useCallback, useRef } from "react";

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
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`animate-slide-in flex items-center gap-2 bg-fl-card rounded-lg px-4 py-3 text-sm font-sans text-fl-black border-l-4 ${
              t.type === "success" ? "border-fl-green" : "border-fl-red"
            }`}
            style={{
              boxShadow: "0 4px 16px rgba(40,40,40,0.12)",
              minWidth: "220px",
              maxWidth: "320px",
            }}
          >
            <span className="text-base">{t.type === "success" ? "✓" : "✕"}</span>
            <span>{message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
