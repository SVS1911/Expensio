import { useEffect, useState } from "react";

const themes = [
  { id: "ivory-charcoal", label: "Ivory & charcoal", swatch: "#383832" },
  { id: "beige-blue", label: "Beige & royal blue", swatch: "#2852a1" },
  { id: "lime-orange", label: "Lime & orange", swatch: "#de6b35" },
  { id: "bronze-pearl", label: "Bronze & pearl", swatch: "#98683e" }
];

const applyTheme = (theme) => {
  document.documentElement.dataset.theme = theme;
};

export default function ThemeToggle() {
  const [selected, setSelected] = useState(
    document.documentElement.dataset.theme || themes[0].id
  );

  useEffect(() => {
    const syncTheme = (event) => {
      if (event.key !== "expenseTrackerTheme") return;
      const next = themes.some((theme) => theme.id === event.newValue) ? event.newValue : themes[0].id;
      setSelected(next);
      applyTheme(next);
    };
    window.addEventListener("storage", syncTheme);
    return () => window.removeEventListener("storage", syncTheme);
  }, []);

  const chooseTheme = (theme) => {
    applyTheme(theme.id);
    setSelected(theme.id);
    try {
      localStorage.setItem("expenseTrackerTheme", theme.id);
    } catch (error) {
      console.warn("Could not save the theme preference.", error);
    }
  };

  return (
    <div className="theme-picker" role="group" aria-label="Choose a color theme">
      <span className="theme-picker-label">Theme</span>
      {themes.map((theme) => (
        <button
          className="theme-swatch"
          key={theme.id}
          type="button"
          title={theme.label}
          aria-label={theme.label}
          aria-pressed={selected === theme.id}
          onClick={() => chooseTheme(theme)}
        >
          <span style={{ backgroundColor: theme.swatch }} />
        </button>
      ))}
    </div>
  );
}
