import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, logout } from "../api.js";

export default function Header({ title, subtitle, back }) {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [notificationError, setNotificationError] = useState("");

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const notifications = await api("/notifications");
        if (active) {
          setUnread(notifications.unreadCount);
          setNotificationError("");
        }
      } catch (error) {
        if (active) setNotificationError(error.message);
      }
    };
    refresh();
    const interval = window.setInterval(refresh, 30_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <header className="page-header">
      <div>
        {back && <Link className="back-link" to={back.to}>{back.label}</Link>}
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      <div className="header-actions">
        <nav className="app-nav" aria-label="Main navigation">
          <Link to="/">Overview</Link>
          <Link to="/expenses">Expenses</Link>
          <Link to="/travel">Travel</Link>
          <Link to="/notifications">
            Notifications{unread > 0 && <span className="notification-badge">{unread}</span>}
          </Link>
          <Link to="/profile">Profile</Link>
        </nav>
        {notificationError && <span className="navigation-error" role="status" title={notificationError}>Notifications unavailable</span>}
        <button className="outline-button" type="button" onClick={() => logout(navigate)}>Logout</button>
      </div>
    </header>
  );
}
