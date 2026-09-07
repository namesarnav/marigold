import { useState } from "react";
import { uploadPdf, waitForDocument } from "../api.js";

export default function UploadZone({ onUploaded }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  // "uploading" while the file is in flight, "generating" while the server
  // builds cards. Two phases because the second one is the slow one, and a
  // spinner that never changes reads as a hang.
  const [phase, setPhase] = useState("uploading");

  const handleFile = async (file) => {
    if (!file) return;
    setError("");
    setLoading(true);
    setPhase("uploading");
    try {
      // The upload returns as soon as the document row exists; card generation
      // runs server-side afterwards. Poll until it reaches a terminal state
      // rather than holding the request open, which would time out on a large
      // PDF.
      const data = await uploadPdf(file);
      setPhase("generating");
      await waitForDocument(data.doc_id);
      onUploaded(data.doc_id, file.name);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setPhase("uploading");
    }
  };

  return (
    <div>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-9 transition-colors ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-base-300 bg-base-100 hover:border-primary/50 hover:bg-base-200/40"
        } ${loading ? "pointer-events-none opacity-70" : ""}`}
      >
        {loading ? (
          <div className="flex flex-col items-center gap-3 py-1">
            <span className="loading loading-spinner loading-md text-primary" />
            <p className="text-sm text-base-content/60">
              {phase === "generating"
                ? "Reading your PDF and writing flashcards…"
                : "Uploading…"}
            </p>
          </div>
        ) : (
          <>
            <span className="text-3xl" aria-hidden="true">📄</span>
            <div className="text-center">
              <p className="text-sm font-medium">Drop your PDF here</p>
              <p className="mt-0.5 text-xs text-base-content/50">or click to browse</p>
            </div>
            {/* A span, not a button: the whole label is already the control, and
                a nested button would swallow the click that opens the picker. */}
            <span className="btn btn-primary btn-sm">Select PDF</span>
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
        <div role="alert" className="alert alert-error mt-3 py-2.5">
          <span className="text-sm">{error}</span>
        </div>
      )}
    </div>
  );
}
