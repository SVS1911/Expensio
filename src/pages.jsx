import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, jsonBody, logout } from "./api.js";
import BudgetEditor from "./components/BudgetEditor.jsx";
import ErrorMessage from "./components/ErrorMessage.jsx";
import Header from "./components/Header.jsx";
import HeroOrbit from "./components/HeroOrbit.jsx";
import RecentList from "./components/RecentList.jsx";
import ThemeSettings from "./components/ThemeToggle.jsx";

const CATEGORIES = ["Academic", "Food", "Travel", "Shopping", "Bills", "Entertainment", "Other"];
const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const cents = (value) => Math.round(Number(value || 0) * 100);
const localDate = (daysAgo = 0, fromDate = new Date()) => {
  const date = new Date(fromDate);
  date.setDate(date.getDate() - daysAgo);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 10);
};
const greeting = (name) => {
  const hour = new Date().getHours();
  const time = hour < 5 || hour >= 22 ? "Burning the midnight oil" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  return `${time}, ${String(name || "").trim().split(/\s+/)[0] || "there"}.`;
};

export function AuthPage({ mode, onSubmit }) {
  const [values, setValues] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const register = mode === "register";
  const handleSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSubmit(mode, values);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <h1>{register ? "Create account" : "Login"}</h1>
      <form onSubmit={handleSubmit} autoComplete="on">
        {register && <input name="name" autoComplete="name" placeholder="Name" value={values.name} onChange={(event) => setValues({ ...values, name: event.target.value })} required />}
        <input name="email" type="email" autoComplete="email" placeholder="Email" value={values.email} onChange={(event) => setValues({ ...values, email: event.target.value })} required />
        <input name="password" type="password" autoComplete={register ? "new-password" : "current-password"} minLength={register ? 8 : undefined} placeholder="Password" value={values.password} onChange={(event) => setValues({ ...values, password: event.target.value })} required />
        <button type="submit" disabled={busy}>{busy ? "Please wait…" : register ? "Register" : "Login"}</button>
      </form>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <Link className="auth-link" to={register ? "/login" : "/register"}>{register ? "Already have an account? Login" : "Create account"}</Link>
    </main>
  );
}

export function DashboardPage({ user }) {
  const [expenses, setExpenses] = useState([]);
  const [settings, setSettings] = useState({ expenseLimit: null, travelLimit: null });
  const [error, setError] = useState("");
  const load = async () => {
    try {
      const [rows, prefs] = await Promise.all([api("/expenses"), api("/settings")]);
      setExpenses(rows);
      setSettings(prefs);
      setError("");
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);

  const regular = expenses.filter((item) => item.expenseType !== "travel");
  const travel = expenses.filter((item) => item.expenseType === "travel");
  const total = regular.reduce((sum, item) => sum + Number(item.amount), 0);
  const sortRecent = (rows) => [...rows].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 4);
  const updateLimit = async (amount) => {
    const updated = await api("/settings", { method: "PUT", body: jsonBody({ expenseLimit: amount }) });
    setSettings(updated);
  };

  return (
    <main className="landing app">
      <Header title={greeting(user.name)} subtitle="A calm space to understand where your money goes." user={user} />
      <section className="hero-card">
        <div className="hero-copy">
          <span className="eyebrow">ALL TIME</span><h2>Spend with intention.</h2>
          <p>Set a comfortable limit, then let your daily choices add up.</p>
          <div className="landing-actions">
            <Link className={`primary-button add-expense-button${settings.expenseLimit && cents(total) > cents(settings.expenseLimit) ? " disabled" : ""}`} to="/expenses">＋ Add expense</Link>
            <Link className="secondary-button travel-link" to="/travel">Travel expenses</Link>
          </div>
          {settings.expenseLimit && cents(total) > cents(settings.expenseLimit) && <p className="limit-notice">Maximum limit exceeded — set a new limit to continue adding expenses.</p>}
        </div>
        <HeroOrbit />
      </section>
      <section className="overview-grid">
        <BudgetEditor limit={settings.expenseLimit} total={total} onSave={updateLimit} />
        <article className="summary-card"><span className="eyebrow">TOTAL SPENT</span><p className="large-number">{money(total)}</p><p className="card-note">Across all recorded expenses</p></article>
        <article className="summary-card"><span className="eyebrow">NO. OF EXPENSES</span><p className="large-number">{regular.length}</p><p className="card-note">Expenses added so far</p></article>
      </section>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <RecentList title="Recent expenses" items={sortRecent(regular)} empty="Your recent expenses will appear here." viewLink="/expenses" />
      <RecentList title="Travel expenses" items={sortRecent(travel)} empty="Your travel expenses will appear here." viewLink="/travel" travel />
    </main>
  );
}

export function ExpensesPage({ user, travel = false }) {
  const [expenses, setExpenses] = useState([]);
  const [travelers, setTravelers] = useState([]);
  const [limit, setLimit] = useState(null);
  const [form, setForm] = useState({ title: "", amount: "", category: "", date: localDate(), description: "", people: "" });
  const [filters, setFilters] = useState(() => {
    const today = new Date();
    return { search: "", category: "", date: "", from: localDate(19, today), to: localDate(0, today) };
  });
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [all, prefs, people] = await Promise.all([
        api("/expenses"), api("/settings"), travel ? api("/travelers") : Promise.resolve([])
      ]);
      setExpenses(all.filter((item) => travel ? item.expenseType === "travel" : item.expenseType !== "travel"));
      setLimit(travel ? prefs.travelLimit : prefs.expenseLimit);
      setTravelers(people);
      setError("");
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, [travel]);

  const total = expenses.reduce((sum, item) => sum + Number(item.amount), 0);
  const shown = useMemo(() => {
    if (filters.from && filters.to && filters.from > filters.to) return [];
    return expenses.filter((item) => {
      const text = `${item.title} ${item.description || ""} ${item.people || ""}`.toLowerCase();
      return text.includes(filters.search.toLowerCase()) &&
        (!filters.category || item.category === filters.category) &&
        (!filters.date || item.date === filters.date) &&
        (!filters.from || item.date >= filters.from) &&
        (!filters.to || item.date <= filters.to);
    });
  }, [expenses, filters]);

  const saveNew = async (event) => {
    event.preventDefault();
    setError("");
    if (Number(limit) > 0 && cents(total) + cents(form.amount) > cents(limit)) {
      setError(`This expense would exceed your ${travel ? "travel" : "regular"} spending limit of ${money(limit)}.`);
      return;
    }
    if (!form.title.trim()) { setError("Enter an expense title."); return; }
    if (!Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { setError("Amount must be a number greater than zero."); return; }
    if (form.date > localDate()) { setError("Future dates are not allowed."); return; }
    if (travel && !form.people) { setError("Select a traveler from your saved traveler list."); return; }
    const payload = {
      title: form.title.trim(), amount: Number(form.amount),
      category: travel ? "Travel" : form.category,
      date: form.date, description: form.description.trim(),
      ...(travel ? { expenseType: "travel", people: form.people } : {})
    };
    try {
      await api("/expenses", { method: "POST", body: jsonBody(payload) });
      setForm({ title: "", amount: "", category: "", date: localDate(), description: "", people: "" });
      await load();
    } catch (err) { setError(err.message); }
  };

  const remove = async (id) => {
    try {
      await api(`/expenses/${id}`, { method: "DELETE" });
      await load();
    } catch (err) { setError(err.message); }
  };

  const update = async (event, item) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = Object.fromEntries(data.entries());
    payload.amount = Number(payload.amount);
    payload.category = travel ? "Travel" : payload.category;
    if (!payload.title.trim() || payload.amount <= 0 || payload.date > localDate()) {
      setError("Enter a title, a positive amount, and a valid date.");
      return;
    }
    try {
      await api(`/expenses/${item.id}`, { method: "PATCH", body: jsonBody(payload) });
      setEditing(null);
      setError("");
      await load();
    } catch (err) { setError(err.message); }
  };

  const categories = CATEGORIES.map((category) => [category, expenses.filter((item) => item.category === category).reduce((sum, item) => sum + Number(item.amount), 0)]);

  return (
    <main className="app">
      <Header title={travel ? "Travel expenses" : "Expenses"} subtitle={travel ? "Track trip purchases and the people sharing them." : "Keep your spending clear and intentional."}
        back={{ to: travel ? "/travel" : "/", label: travel ? "← Travel overview" : "← Overview" }} user={user} />
      {Number(limit) > 0 && cents(total) > cents(limit) && <p className="limit-alert">Maximum limit exceeded — set a new limit on Overview to continue.</p>}
      <form id="expenseForm" onSubmit={saveNew}>
        <input placeholder="Title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
        <input type="number" min="0.01" step="0.01" inputMode="decimal" placeholder="Amount" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} required />
        {travel
          ? <select value={form.people} onChange={(event) => setForm({ ...form, people: event.target.value })} required>
              <option value="" disabled>Select a traveler</option>{travelers.map((person) => <option key={person.id} value={person.name}>{person.name}</option>)}
            </select>
          : <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} required>
              <option value="" disabled>Select a category</option>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}
            </select>}
        <input type="date" max={localDate()} value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} required />
        <input placeholder="Description" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
        <button type="submit" disabled={(travel && travelers.length === 0) || (Number(limit) > 0 && cents(total) + cents(form.amount) > cents(limit))}>{travel ? "Add Travel Expense" : "Add Expense"}</button>
      </form>
      {Number(limit) > 0 && Number(form.amount) > 0 && cents(total) + cents(form.amount) > cents(limit) &&
        <p className="limit-alert">This expense would exceed your spending limit of {money(limit)}.</p>}
      {travel && travelers.length === 0 && <p className="card-note">Add at least one traveler in the Travel overview before recording travel expenses.</p>}
      <section className="dashboard">
        <div className="card">Total Expense<b>{money(total)}</b></div>
        {categories.filter(([, amount]) => amount > 0 || !travel).map(([category, amount]) => <div className="card" key={category}>{category}<b>{money(amount)}</b></div>)}
      </section>
      <div className="tools">
        <input aria-label="Search expenses" placeholder="Search" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
        <select aria-label="Filter by category" value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })}>
          <option value="">All Categories</option>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}
        </select>
        <div className="filter-group"><label>Filter by date</label><input type="date" max={localDate()} value={filters.date} onChange={(event) => setFilters({ ...filters, date: event.target.value })} /></div>
        <div className="filter-group"><label>From date</label><input type="date" max={localDate()} value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} /></div>
        <div className="filter-group"><label>To date</label><input type="date" max={localDate()} value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} /></div>
      </div>
      {filters.from && filters.to && filters.from > filters.to && <ErrorMessage>The start date must be before or equal to the end date.</ErrorMessage>}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <section aria-label="Expense list">
        {shown.map((item) => <article className="expense" key={item.id}>
          {editing === item.id
            ? <form className="expense-edit-form" onSubmit={(event) => update(event, item)}>
                <div className="edit-fields">
                  <input name="title" aria-label="Expense title" defaultValue={item.title} required />
                  <input name="amount" aria-label="Amount" type="number" min="0.01" step="0.01" defaultValue={item.amount} required />
                  {travel ? <select name="people" defaultValue={item.people || ""} required>{travelers.map((person) => <option key={person.id} value={person.name}>{person.name}</option>)}</select>
                    : <select name="category" defaultValue={item.category} required>{CATEGORIES.map((category) => <option key={category}>{category}</option>)}</select>}
                  <input name="date" aria-label="Expense date" type="date" max={localDate()} defaultValue={item.date} required />
                  <input name="description" aria-label="Description" defaultValue={item.description || ""} />
                </div>
                <div className="actions editor-actions"><button className="confirm-button" type="submit">Confirm</button><button className="cancel-button" type="button" onClick={() => setEditing(null)}>Cancel</button></div>
              </form>
            : <>
                <div><b>{item.title}</b> — {money(item.amount)}<br /><small>{item.category} · {item.date}{item.description ? ` · ${item.description}` : ""}{item.people ? ` · With: ${item.people}` : ""}</small></div>
                <div className="actions"><button type="button" onClick={() => setEditing(item.id)}>Edit</button><button type="button" className="delete" onClick={() => remove(item.id)}>Delete</button></div>
              </>}
        </article>)}
        {!shown.length && <p className="empty-state">No expenses match these filters.</p>}
      </section>
    </main>
  );
}

export function TravelDashboardPage({ user }) {
  const [expenses, setExpenses] = useState([]);
  const [travelers, setTravelers] = useState([]);
  const [limit, setLimit] = useState(null);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newImage, setNewImage] = useState(null);
  const [selectedTraveler, setSelectedTraveler] = useState(null);
  const [sendingSummary, setSendingSummary] = useState(null);
  const [emailMessage, setEmailMessage] = useState("");
  const [error, setError] = useState("");
  const load = async () => {
    try {
      const [all, people, settings] = await Promise.all([api("/expenses"), api("/travelers"), api("/settings")]);
      setExpenses(all.filter((item) => item.expenseType === "travel"));
      setTravelers(people);
      setLimit(settings.travelLimit);
      setError("");
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (!selectedTraveler) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setSelectedTraveler(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedTraveler]);

  const total = expenses.reduce((sum, item) => sum + Number(item.amount), 0);
  const totalsByPerson = useMemo(() => {
    const names = new Set([...travelers.map((person) => person.name), ...expenses.map((item) => item.people).filter(Boolean)]);
    return [...names].map((name) => ({ name, total: expenses.filter((item) => item.people === name).reduce((sum, item) => sum + Number(item.amount), 0) }))
      .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
  }, [travelers, expenses]);

  const addTraveler = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    setError("");
    try {
      await api("/travelers", { method: "POST", body: jsonBody({ name: newName.trim(), email: newEmail.trim(), image: newImage }) });
      setNewName("");
      setNewEmail("");
      setNewImage(null);
      form.reset();
      await load();
    } catch (err) { setError(err.message); }
  };
  const selectTravelerPhoto = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setError("Choose a PNG, JPEG, or WebP photo.");
      event.target.value = "";
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("Traveler photos must be 5 MB or smaller.");
      event.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setNewImage(String(reader.result));
    reader.onerror = () => setError("Could not read that photo. Please try another file.");
    reader.readAsDataURL(file);
  };
  const sendSummary = async (traveler) => {
    setSendingSummary(traveler.id);
    setEmailMessage("");
    setError("");
    try {
      const result = await api(`/travelers/${traveler.id}/send-summary`, { method: "POST" });
      setEmailMessage(`Expense summary sent to ${result.recipient}.`);
    } catch (err) { setError(err.message); }
    finally { setSendingSummary(null); }
  };
  const removeTraveler = async (id) => {
    try {
      await api(`/travelers/${id}`, { method: "DELETE" });
      await load();
    } catch (err) { setError(err.message); }
  };
  const saveLimit = async (amount) => {
    const settings = await api("/settings", { method: "PUT", body: jsonBody({ travelLimit: amount }) });
    setLimit(settings.travelLimit);
  };
  const exceeded = Number(limit) > 0 && cents(total) > cents(limit);
  const recent = [...expenses].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5);

  return (
    <main className="landing app travel-landing">
      <Header title={greeting(user.name)} subtitle="Plan the trip, track the spend, and see each traveler's share." back={{ to: "/", label: "← Main overview" }} user={user} />
      <section className="hero-card">
        <div className="hero-copy"><span className="eyebrow">YOUR TRIP OVERVIEW</span><h2>Every journey, in balance.</h2><p>Add your travel companions, set a trip spending limit, then record expenses against a traveler.</p>
          <div className="landing-actions"><Link className={`primary-button add-expense-button${exceeded ? " disabled" : ""}`} to="/travel/expenses">＋ Add travel expense</Link></div>
          {exceeded && <p className="limit-notice">Maximum travel limit exceeded — set a new limit to continue adding expenses.</p>}
        </div><HeroOrbit />
      </section>
      <section className="overview-grid">
        <BudgetEditor limit={limit} total={total} onSave={saveLimit} label="TRAVEL SPENDING LIMIT" inputLabel="Maximum travel spending limit" />
        <article className="summary-card"><span className="eyebrow">TRAVEL SPENT</span><p className="large-number">{money(total)}</p><p className="card-note">Across recorded travel expenses</p></article>
        <article className="summary-card"><span className="eyebrow">TRAVELERS</span><p className="large-number">{travelers.length}</p><p className="card-note">People on your saved list</p></article>
      </section>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <section className="travel-panels">
        <article className="recent-section traveler-manager">
          <div className="section-heading"><div><span className="eyebrow">YOUR TRIP CREW</span><h2>Travelers</h2></div></div>
          <form className="traveler-form" onSubmit={addTraveler}><label className="visually-hidden" htmlFor="traveler-name">Traveler name</label>
            <input id="traveler-name" placeholder="Add a person's name" value={newName} onChange={(event) => setNewName(event.target.value)} required />
            <label className="visually-hidden" htmlFor="traveler-email">Traveler email</label>
            <input id="traveler-email" type="email" placeholder="Email address" value={newEmail} onChange={(event) => setNewEmail(event.target.value)} required />
            <label className="traveler-photo-label" htmlFor="traveler-photo">{newImage ? "Photo selected" : "Choose photo"}</label>
            <input id="traveler-photo" className="visually-hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={selectTravelerPhoto} />
            <button className="primary-button" type="submit">Add / update person</button>
          </form>
          <div className="traveler-list">{travelers.map((person) => <div className="traveler-chip" key={person.id}>
            <button className="traveler-profile-button" type="button" onClick={() => setSelectedTraveler(person)}>
              {person.image
                ? <img className="traveler-avatar" src={person.image} alt="" />
                : <span className="traveler-avatar traveler-avatar-placeholder">{person.name.charAt(0).toUpperCase()}</span>}
              <span className="traveler-contact"><b>{person.name}</b><small>{person.email}</small></span>
            </button>
            <button className="remove-traveler" type="button" onClick={() => removeTraveler(person.id)} aria-label={`Remove ${person.name}`}>Remove</button>
          </div>)}</div>
          {!travelers.length && <p className="empty-state">Add people traveling with you to begin.</p>}
        </article>
        <article className="recent-section person-dashboard">
          <div className="section-heading"><div><span className="eyebrow">SHARED SPENDING</span><h2>Spend by person</h2></div></div>
          <div className="person-totals">{totalsByPerson.map((item) => {
            const person = travelers.find((traveler) => traveler.name.toLowerCase() === item.name.toLowerCase());
            return <div className="person-total-row" key={item.name}>
              <button className="person-profile-button" type="button" onClick={() => person && setSelectedTraveler(person)} disabled={!person}>
                {person?.image
                  ? <img className="traveler-avatar" src={person.image} alt="" />
                  : <span className="traveler-avatar traveler-avatar-placeholder">{item.name.charAt(0).toUpperCase()}</span>}
                <b>{item.name}</b>
              </button>
              <strong>{money(item.total)}</strong>
              {person && <button className="text-button" type="button" onClick={() => sendSummary(person)} disabled={sendingSummary === person.id || item.total === 0}>
                {sendingSummary === person.id ? "Sending…" : "Send email"}
              </button>}
            </div>;
          })}</div>
          {emailMessage && <p className="success-message" role="status">{emailMessage}</p>}
          {!totalsByPerson.length && <p className="empty-state">Person-by-person totals appear when travel expenses are added.</p>}
        </article>
      </section>
      <RecentList title="Recent travel expenses" items={recent} empty="Your travel expenses will appear here." viewLink="/travel/expenses" travel />
      {selectedTraveler && (() => {
        const personExpenses = expenses.filter((item) => item.people?.toLowerCase() === selectedTraveler.name.toLowerCase())
          .sort((a, b) => b.date.localeCompare(a.date));
        const personTotal = personExpenses.reduce((sum, item) => sum + Number(item.amount), 0);
        return <div className="traveler-modal-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedTraveler(null);
        }}>
          <section className="traveler-modal" role="dialog" aria-modal="true" aria-labelledby="traveler-modal-title" tabIndex="-1">
            <button className="traveler-modal-close" type="button" onClick={() => setSelectedTraveler(null)} aria-label="Close traveler details">×</button>
            <div className="traveler-modal-heading">
              {selectedTraveler.image
                ? <img className="traveler-modal-avatar" src={selectedTraveler.image} alt={`${selectedTraveler.name}`} />
                : <span className="traveler-modal-avatar traveler-avatar-placeholder">{selectedTraveler.name.charAt(0).toUpperCase()}</span>}
              <div><h2 id="traveler-modal-title">{selectedTraveler.name}</h2><p>{selectedTraveler.email}</p></div>
            </div>
            <div className="traveler-modal-total"><span>{personExpenses.length} travel expenses</span><strong>{money(personTotal)}</strong></div>
            <h3>Expenses</h3>
            <div className="traveler-modal-expenses">
              {personExpenses.map((item) => <article className="traveler-expense-item" key={item.id}>
                <div><b>{item.title}</b><small>{item.date}{item.description ? ` · ${item.description}` : ""}</small></div>
                <strong>{money(item.amount)}</strong>
              </article>)}
              {!personExpenses.length && <p className="empty-state">No expenses have been recorded for this traveler yet.</p>}
            </div>
          </section>
        </div>;
      })()}
    </main>
  );
}

export function ProfilePage({ user }) {
  const navigate = useNavigate();
  const [profile, setProfile] = useState({
    name: user.name || "",
    email: user.email || "",
    emailNotifications: user.emailNotifications !== false,
    currentPassword: "",
    newPassword: ""
  });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let active = true;
    api("/profile").then((value) => {
      if (active) setProfile((current) => ({
        ...current,
        name: value.name,
        email: value.email,
        emailNotifications: value.emailNotifications
      }));
    }).catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const updated = await api("/profile", {
        method: "PATCH",
        body: jsonBody({
          ...profile,
          currentPassword: profile.currentPassword || null,
          newPassword: profile.newPassword || null
        })
      });
      localStorage.setItem("user", JSON.stringify(updated));
      window.dispatchEvent(new CustomEvent("profile-updated", { detail: updated }));
      setProfile((current) => ({ ...current, ...updated, currentPassword: "", newPassword: "" }));
      setSuccess("Your profile was updated.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };
  const deleteAccount = async () => {
    if (!window.confirm("Delete your profile and all saved expenses, travelers, and notifications? This cannot be undone.")) return;
    setDeleting(true);
    setError("");
    try {
      await api("/profile", { method: "DELETE" });
      logout(navigate);
    } catch (err) {
      setError(err.message);
      setDeleting(false);
    }
  };

  return (
    <main className="app">
      <Header title="Your profile" subtitle="Manage your account details and email alerts." back={{ to: "/", label: "← Overview" }} user={user} />
      <section className="recent-section profile-panel">
        <form className="profile-form" onSubmit={submit}>
          <label htmlFor="profile-name">Name</label>
          <input id="profile-name" autoComplete="name" value={profile.name} onChange={(event) => setProfile({ ...profile, name: event.target.value })} required />
          <label htmlFor="profile-email">Email address</label>
          <input id="profile-email" type="email" autoComplete="email" value={profile.email} onChange={(event) => setProfile({ ...profile, email: event.target.value })} required />
          <h2>Change password</h2>
          <p className="card-note">Leave both password fields blank to keep your current password.</p>
          <label htmlFor="current-password">Current password</label>
          <input id="current-password" type="password" autoComplete="current-password" value={profile.currentPassword} onChange={(event) => setProfile({ ...profile, currentPassword: event.target.value })} />
          <label htmlFor="new-password">New password</label>
          <input id="new-password" type="password" autoComplete="new-password" minLength={8} value={profile.newPassword} onChange={(event) => setProfile({ ...profile, newPassword: event.target.value })} />
          {error && <ErrorMessage>{error}</ErrorMessage>}
          {success && <p className="success-message" role="status">{success}</p>}
          <button className="primary-button profile-save" type="submit" disabled={saving}>{saving ? "Saving…" : "Save profile"}</button>
        </form>
      </section>
      <div className="profile-panel">
        <ThemeSettings />
      </div>
      <section className="recent-section profile-panel delete-profile-panel">
        <h2>Delete profile</h2>
        <p className="card-note">Permanently delete your account and all of its expenses, travel companions, and notifications.</p>
        <button className="delete-profile-button" type="button" onClick={deleteAccount} disabled={deleting}>
          {deleting ? "Deleting profile…" : "Delete my profile"}
        </button>
      </section>
    </main>
  );
}

const emailStatusLabel = {
  pending: "Not emailed — email is sent only when requested",
  not_sent: "Not emailed — email is sent only when requested",
  sent: "Email sent",
  failed: "Email failed — check the SMTP configuration",
  not_configured: "Email not configured — set SMTP variables on the server",
  disabled: "Email alerts disabled in your profile"
};

export function NotificationsPage({ user }) {
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const result = await api("/notifications");
      setItems(result.items);
      setUnread(result.unreadCount);
      setError("");
    } catch (err) { setError(err.message); }
  };
  useEffect(() => {
    load();
    const interval = window.setInterval(load, 5000);
    return () => window.clearInterval(interval);
  }, []);

  const markRead = async (id) => {
    try {
      await api(`/notifications/${id}/read`, { method: "PATCH" });
      await load();
    } catch (err) { setError(err.message); }
  };
  const markAllRead = async () => {
    try {
      await api("/notifications/read-all", { method: "PATCH" });
      await load();
    } catch (err) { setError(err.message); }
  };

  return (
    <main className="app">
      <Header title="Notifications" subtitle="Expense updates and spending-limit alerts." back={{ to: "/", label: "← Overview" }} user={user} />
      <section className="recent-section notification-panel">
        <div className="section-heading">
          <div><span className="eyebrow">YOUR INBOX</span><h2>{unread ? `${unread} unread` : "You're all caught up"}</h2></div>
          {unread > 0 && <button className="secondary-button" type="button" onClick={markAllRead}>Mark all as read</button>}
        </div>
        {error && <ErrorMessage>{error}</ErrorMessage>}
        <div className="notification-list">
          {items.map((item) => (
            <article className={`notification-item${item.isRead ? "" : " unread"}`} key={item.id}>
              <div className="notification-copy">
                <b>{item.title}</b>
                <p>{item.message}</p>
                <small>{new Date(item.createdAt).toLocaleString()} · {emailStatusLabel[item.emailStatus] || item.emailStatus}</small>
              </div>
              {!item.isRead && <button className="text-button" type="button" onClick={() => markRead(item.id)}>Mark read</button>}
            </article>
          ))}
        </div>
        {!items.length && <p className="empty-state">Notifications about new expenses and budget limits will appear here.</p>}
      </section>
    </main>
  );
}
