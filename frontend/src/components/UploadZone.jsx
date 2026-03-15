import { useState } from "react";
import { uploadPdf } from "../api.js";

export default function UploadZone({ onUploaded }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);

  const handleFile = async (file) => {
    if (!file) return;
    setError("");
    setLoading(true);
    try {
      const data = await uploadPdf(file);
      onUploaded(data.doc_id, file.name);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-xl p-10 cursor-pointer transition-all duration-200 ${
          dragging
            ? "border-fl-black bg-fl-yellow/10"
            : "border-fl-border bg-fl-card hover:border-fl-black"
        } ${loading ? "pointer-events-none opacity-60" : ""}`}
      >
        {loading ? (
          <div className="flex flex-col items-center gap-3">
            <span className="h-6 w-6 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
            <p className="text-sm font-sans text-fl-muted">Uploading and generating flashcards…</p>
          </div>
        ) : (
          <>
            <div className="h-10 w-10 rounded-full bg-cream flex items-center justify-center border border-fl-border">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-fl-muted">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="12" y1="18" x2="12" y2="12"/>
                <line x1="9" y1="15" x2="15" y2="15"/>
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-sans font-medium text-fl-black">Drop your PDF here</p>
              <p className="text-xs font-sans text-fl-muted mt-0.5">or click to browse</p>
            </div>
            <span className="px-4 py-1.5 rounded-lg bg-fl-yellow text-fl-black text-sm font-sans font-semibold btn-press hover:bg-fl-yellow-h transition-colors">
              Select PDF
            </span>
          </>
        )}
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          disabled={loading}
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </label>
      {error && (
        <p className="mt-3 text-sm text-fl-red font-sans">{error}</p>
      )}
    </div>
  );
}
