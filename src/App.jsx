import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, currentUser, jsonBody, logout, storeSession } from "./api.js";
import ErrorMessage from "./components/ErrorMessage.jsx";
import {
  AuthPage,
  DashboardPage,
  ExpensesPage,
  NotificationsPage,
  ProfilePage,
  TravelDashboardPage
} from "./pages.jsx";

function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(() => localStorage.getItem("token") ? null : currentUser());
  const [checkingSession, setCheckingSession] = useState(() => Boolean(localStorage.getItem("token")));
  const [sessionError, setSessionError] = useState("");

  useEffect(() => {
    let active = true;
    if (localStorage.getItem("token")) {
      api("/profile")
        .then((profile) => {
          if (!active) return;
          localStorage.setItem("user", JSON.stringify(profile));
          setUser(profile);
        })
        .catch((error) => {
          if (!active) return;
          if (error.status === 401) {
            localStorage.removeItem("token");
            localStorage.removeItem("user");
            setUser(null);
          } else {
            setSessionError(`Could not verify the saved session. ${error.message}`);
            setUser(currentUser());
          }
        })
        .finally(() => { if (active) setCheckingSession(false); });
    }
    const expired = () => {
      logout(navigate);
      setUser(null);
    };
    const loggedOut = () => setUser(null);
    const profileUpdated = (event) => setUser(event.detail);
    window.addEventListener("auth-expired", expired);
    window.addEventListener("auth-logged-out", loggedOut);
    window.addEventListener("profile-updated", profileUpdated);
    return () => {
      active = false;
      window.removeEventListener("auth-expired", expired);
      window.removeEventListener("auth-logged-out", loggedOut);
      window.removeEventListener("profile-updated", profileUpdated);
    };
  }, [navigate]);

  const authenticated = Boolean(localStorage.getItem("token") && user);
  const submit = async (mode, values) => {
    const session = await api(`/auth/${mode}`, {
      method: "POST",
      body: jsonBody(values)
    });
    storeSession(session);
    setUser(session.user);
    navigate("/", { replace: true });
  };

  return (
    <>
      {sessionError && <ErrorMessage>{sessionError}</ErrorMessage>}
      {checkingSession ? <main className="session-loading" role="status">Checking your session…</main> : <Routes>
        <Route
          path="/login"
          element={authenticated ? <Navigate to="/" replace /> : <AuthPage mode="login" onSubmit={submit} />}
        />
        <Route
          path="/register"
          element={authenticated ? <Navigate to="/" replace /> : <AuthPage mode="register" onSubmit={submit} />}
        />
        <Route path="/" element={authenticated ? <DashboardPage user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/expenses" element={authenticated ? <ExpensesPage user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/travel" element={authenticated ? <TravelDashboardPage user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/travel/expenses" element={authenticated ? <ExpensesPage user={user} travel /> : <Navigate to="/login" replace />} />
        <Route path="/notifications" element={authenticated ? <NotificationsPage user={user} /> : <Navigate to="/login" replace />} />
        <Route path="/profile" element={authenticated ? <ProfilePage user={user} /> : <Navigate to="/login" replace />} />
        <Route path="*" element={<Navigate to={authenticated ? "/" : "/login"} replace />} />
      </Routes>}
    </>
  );
}

export default App;
