import { Link } from "react-router-dom";

const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export default function RecentList({ title, items, empty, viewLink, travel = false }) {
  return (
    <section className="recent-section">
      <div className="section-heading">
        <div><span className="eyebrow">A QUICK LOOK</span><h2>{title}</h2></div>
        <Link className="secondary-button" to={viewLink}>View all</Link>
      </div>
      <div className="recent-list">
        {items.map((item) => (
          <article className="recent-item" key={item.id}>
            <div className="recent-icon">
              {travel ? (item.people || "T").charAt(0).toUpperCase() : item.category.charAt(0)}
            </div>
            <div className="recent-details">
              <b>{item.title}</b>
              <small>
                {travel
                  ? `Travel · ${item.date}${item.people ? ` · ${item.people}` : ""}`
                  : `${item.category} · ${item.date}`}
              </small>
            </div>
            <strong>{money(item.amount)}</strong>
          </article>
        ))}
      </div>
      {!items.length && <p className="empty-state">{empty}</p>}
    </section>
  );
}
