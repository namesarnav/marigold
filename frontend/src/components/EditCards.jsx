import { useEffect, useState } from "react";
import { createFlashcard, deleteFlashcard, getFlashcards, patchFlashcard } from "../api.js";
import { useToast } from "../toast.jsx";

function CardRow({ card, onSave, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [q, setQ] = useState(card.question);
  const [a, setA] = useState(card.answer);
  const [topic, setTopic] = useState(card.topic || "");
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const save = async () => {
    if (!q.trim() || !a.trim()) return;
    setSaving(true);
    try {
      const updated = await patchFlashcard(card.id, {
        question: q.trim(),
        answer: a.trim(),
        topic: topic.trim() || null,
      });
      onSave(updated);
      setEditing(false);
      toast("Card saved", "success");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    try {
      await deleteFlashcard(card.id);
      onDelete(card.id);
      toast("Card deleted", "success");
    } catch (err) {
      toast(err.message, "error");
    }
  };

  const cancel = () => {
    setEditing(false);
    setQ(card.question);
    setA(card.answer);
    setTopic(card.topic || "");
  };

  if (editing) {
    return (
      <div className="rounded-xl border-2 border-primary bg-base-100 p-4">
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <label className="form-control">
            <div className="label pt-0">
              <span className="label-text text-xs font-medium">Question</span>
            </div>
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              rows={3}
              className="textarea textarea-bordered resize-none text-sm"
            />
          </label>

          <label className="form-control">
            <div className="label pt-0">
              <span className="label-text text-xs font-medium">Answer</span>
            </div>
            <textarea
              value={a}
              onChange={(e) => setA(e.target.value)}
              rows={3}
              className="textarea textarea-bordered resize-none text-sm"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Topic (optional)"
            className="input input-bordered input-sm flex-1"
          />
          <button
            onClick={save}
            disabled={saving || !q.trim() || !a.trim()}
            className="btn btn-primary btn-sm"
          >
            {saving && <span className="loading loading-spinner loading-xs" />}
            {saving ? "Saving…" : "Save"}
          </button>
          <button onClick={cancel} className="btn btn-ghost btn-sm">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="surface flex items-start gap-3 px-4 py-3">
      <div className="grid min-w-0 flex-1 gap-1 sm:grid-cols-2 sm:gap-3">
        <p className="truncate text-sm">{card.question}</p>
        <p className="truncate text-sm text-base-content/50">{card.answer}</p>
      </div>

      {card.topic && (
        <span className="badge badge-ghost badge-sm shrink-0 font-medium">{card.topic}</span>
      )}

      <button
        onClick={() => setEditing(true)}
        className="btn btn-ghost btn-xs shrink-0"
        aria-label="Edit card"
      >
        Edit
      </button>
      <button
        onClick={handleDelete}
        className="btn btn-ghost btn-xs shrink-0 text-error"
        aria-label="Delete card"
      >
        Delete
      </button>
    </div>
  );
}

function NewCardRow({ docId, onCreated }) {
  const [q, setQ] = useState("");
  const [a, setA] = useState("");
  const [topic, setTopic] = useState("");
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const save = async () => {
    if (!q.trim() || !a.trim()) return;
    setSaving(true);
    try {
      const card = await createFlashcard(docId, q.trim(), a.trim(), topic.trim() || null);
      onCreated(card);
      setQ("");
      setA("");
      setTopic("");
      toast("Card added", "success");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border-2 border-dashed border-base-300 bg-base-100 p-4">
      <p className="mb-3 text-xs font-medium text-base-content/50">New card</p>

      <div className="mb-3 grid gap-3 sm:grid-cols-2">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Question"
          rows={3}
          className="textarea textarea-bordered resize-none text-sm"
        />
        <textarea
          value={a}
          onChange={(e) => setA(e.target.value)}
          placeholder="Answer"
          rows={3}
          className="textarea textarea-bordered resize-none text-sm"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Topic (optional)"
          className="input input-bordered input-sm flex-1"
        />
        <button
          onClick={save}
          disabled={saving || !q.trim() || !a.trim()}
          className="btn btn-primary btn-sm"
        >
          {saving && <span className="loading loading-spinner loading-xs" />}
          {saving ? "Adding…" : "Add card"}
        </button>
      </div>
    </div>
  );
}

export default function EditCards({ docId, docName, onBack }) {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getFlashcards(docId)
      .then(setCards)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [docId]);

  return (
    <div className="animate-fade-up">
      <div className="mb-5 flex items-center justify-between gap-4">
        <p className="text-sm text-base-content/60">
          {cards.length} card{cards.length === 1 ? "" : "s"}
          {docName && <span className="text-base-content/40"> · {docName}</span>}
        </p>
        {onBack && (
          <button onClick={onBack} className="btn btn-ghost btn-xs">
            Done
          </button>
        )}
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner loading-md text-primary" />
        </div>
      )}

      {error && (
        <div role="alert" className="alert alert-error mb-4">
          <span className="text-sm">{error}</span>
        </div>
      )}

      <div className="mb-4 space-y-2">
        {cards.map((card) => (
          <CardRow
            key={card.id}
            card={card}
            onSave={(updated) =>
              setCards((cs) => cs.map((c) => (c.id === updated.id ? updated : c)))
            }
            onDelete={(id) => setCards((cs) => cs.filter((c) => c.id !== id))}
          />
        ))}
      </div>

      <NewCardRow docId={docId} onCreated={(card) => setCards((cs) => [...cs, card])} />
    </div>
  );
}
