import { useState, useEffect, useRef } from "react";
import { getFlashcards, patchFlashcard, deleteFlashcard, createFlashcard } from "../api.js";
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
      const updated = await patchFlashcard(card.id, { question: q.trim(), answer: a.trim(), topic: topic.trim() || null });
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

  if (editing) {
    return (
      <div className="bg-fl-card border border-fl-black rounded-xl p-4" style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.06)" }}>
        <div className="grid sm:grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-[11px] font-sans font-medium text-fl-muted uppercase tracking-wider mb-1">Question</label>
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              rows={2}
              className="w-full bg-cream border-[1.5px] border-fl-border rounded-lg px-3 py-2 text-sm font-sans text-fl-black focus:outline-none focus:border-fl-black resize-none"
            />
          </div>
          <div>
            <label className="block text-[11px] font-sans font-medium text-fl-muted uppercase tracking-wider mb-1">Answer</label>
            <textarea
              value={a}
              onChange={(e) => setA(e.target.value)}
              rows={2}
              className="w-full bg-cream border-[1.5px] border-fl-border rounded-lg px-3 py-2 text-sm font-sans text-fl-black focus:outline-none focus:border-fl-black resize-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Topic (optional)"
            className="flex-1 bg-cream border-[1.5px] border-fl-border rounded-lg px-3 py-1.5 text-xs font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black"
          />
          <button onClick={save} disabled={saving || !q.trim() || !a.trim()} className="btn-press px-4 py-1.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-xs font-sans font-semibold disabled:opacity-50 transition-colors">
            {saving ? "Saving…" : "Save"}
          </button>
          <button onClick={() => { setEditing(false); setQ(card.question); setA(card.answer); setTopic(card.topic || ""); }} className="text-xs font-sans text-fl-muted hover:text-fl-black">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-fl-card border border-fl-border rounded-xl px-4 py-3 flex items-start gap-3 card-hover" style={{ boxShadow: "0 2px 8px rgba(40,40,40,0.04)" }}>
      <div className="flex-1 min-w-0 grid sm:grid-cols-2 gap-2">
        <p className="text-sm font-sans text-fl-black truncate">{card.question}</p>
        <p className="text-sm font-sans text-fl-muted truncate">{card.answer}</p>
      </div>
      {card.topic && (
        <span className="shrink-0 px-2 py-0.5 rounded-full bg-fl-yellow text-fl-black text-[10px] font-sans font-semibold uppercase tracking-wider">
          {card.topic}
        </span>
      )}
      <button onClick={() => setEditing(true)} className="shrink-0 text-fl-muted hover:text-fl-black transition-colors text-sm" title="Edit">✏️</button>
      <button onClick={handleDelete} className="shrink-0 text-fl-muted hover:text-fl-red transition-colors text-sm" title="Delete">🗑</button>
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
      setQ(""); setA(""); setTopic("");
      toast("Card added", "success");
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-fl-card border-2 border-dashed border-fl-border rounded-xl p-4">
      <p className="text-xs font-sans font-medium text-fl-muted mb-3">New card</p>
      <div className="grid sm:grid-cols-2 gap-3 mb-3">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Question"
          rows={2}
          className="w-full bg-cream border-[1.5px] border-fl-border rounded-lg px-3 py-2 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black resize-none"
        />
        <textarea
          value={a}
          onChange={(e) => setA(e.target.value)}
          placeholder="Answer"
          rows={2}
          className="w-full bg-cream border-[1.5px] border-fl-border rounded-lg px-3 py-2 text-sm font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black resize-none"
        />
      </div>
      <div className="flex items-center gap-3">
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Topic (optional)"
          className="flex-1 bg-cream border-[1.5px] border-fl-border rounded-lg px-3 py-1.5 text-xs font-sans text-fl-black placeholder-fl-muted focus:outline-none focus:border-fl-black"
        />
        <button onClick={save} disabled={saving || !q.trim() || !a.trim()} className="btn-press px-4 py-1.5 rounded-lg bg-fl-yellow hover:bg-fl-yellow-h text-fl-black text-xs font-sans font-semibold disabled:opacity-50 transition-colors">
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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-serif text-fl-black">Edit cards</h2>
          <p className="text-sm text-fl-muted font-sans mt-0.5">{docName}</p>
        </div>
        <span className="text-sm font-sans text-fl-muted">{cards.length} cards</span>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-fl-muted font-sans">
          <span className="h-4 w-4 border-2 border-fl-black border-t-transparent rounded-full animate-spin" />
          Loading…
        </div>
      )}
      {error && <p className="text-sm text-fl-red font-sans">{error}</p>}

      <div className="space-y-2 mb-4">
        {cards.map((card) => (
          <CardRow
            key={card.id}
            card={card}
            onSave={(updated) => setCards((cs) => cs.map((c) => (c.id === updated.id ? updated : c)))}
            onDelete={(id) => setCards((cs) => cs.filter((c) => c.id !== id))}
          />
        ))}
      </div>

      <NewCardRow docId={docId} onCreated={(card) => setCards((cs) => [...cs, card])} />
    </div>
  );
}
