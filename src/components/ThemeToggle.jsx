import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const [dark, setDark] = useState(
    document.documentElement.dataset.theme === "dark"
  );

  useEffect(() => {
    const syncTheme = (event) => {
      if (event.key !== "expenseTrackerTheme") return;
      const next = event.newValue === "dark";
      setDark(next);
      document.documentElement.dataset.theme = next ? "dark" : "light";
    };
    window.addEventListener("storage", syncTheme);
    return () => window.removeEventListener("storage", syncTheme);
  }, []);

  const toggle = () => {
    const next = !dark;
    document.documentElement.dataset.theme = next ? "dark" : "light";
    setDark(next);
    try {
      localStorage.setItem("expenseTrackerTheme", next ? "dark" : "light");
    } catch (error) {
      console.warn("Could not save the theme preference.", error);
    }
  };

  return (
    <button
      className="theme-toggle global-theme-toggle"
      type="button"
      aria-pressed={dark}
      onClick={toggle}
    >
      {dark ? "☀ Light mode" : "☾ Dark mode"}
    </button>
  );
}
