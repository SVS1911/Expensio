import { useEffect, useState } from "react";

const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const cents = (value) => Math.round(Number(value || 0) * 100);

export default function BudgetEditor({
  limit,
  total,
  onSave,
  label = "SPENDING LIMIT",
  inputLabel = "Maximum spending limit"
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(limit || "");
  const [error, setError] = useState("");
  const exceeded = Number(limit) > 0 && cents(total) > cents(limit);

  useEffect(() => setValue(limit || ""), [limit]);

  const save = async (event) => {
    event.preventDefault();
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a limit greater than zero.");
      return;
    }
    try {
      await onSave(amount);
      setEditing(false);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <article className="summary-card budget-card">
      <div className="card-heading">
        <span className="eyebrow">{label}</span>
        <button className="text-button" type="button" onClick={() => { setEditing(true); setError(""); }}>Set limit</button>
      </div>
      <p className="large-number">{limit ? money(limit) : "Not set"}</p>
      {editing && (
        <form className="inline-editor" onSubmit={save}>
          <label className="visually-hidden" htmlFor={`budget-${label}`}>{inputLabel}</label>
          <input
            id={`budget-${label}`}
            type="number"
            min="0.01"
            step="0.01"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Enter maximum limit"
            required
          />
          <div className="editor-actions">
            <button className="confirm-button" type="submit">Confirm</button>
            <button className="cancel-button" type="button" onClick={() => { setEditing(false); setError(""); }}>Cancel</button>
          </div>
          <p className="inline-error" aria-live="polite">{error}</p>
        </form>
      )}
      <div className="progress-track">
        <div
          className={`progress-value${exceeded ? " over-limit" : ""}`}
          style={{ width: limit ? `${Math.min(total / Number(limit) * 100, 100)}%` : "0%" }}
        />
      </div>
      <p className="card-note">
        {!limit
          ? "Choose a limit to start tracking your pace."
          : exceeded
            ? `${money(total - Number(limit))} over your spending limit.`
            : `${money(Number(limit) - total)} left in your spending limit.`}
      </p>
    </article>
  );
}
