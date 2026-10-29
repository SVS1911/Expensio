import { useEffect, useState } from "react";

export const themes = [
  { id: "previous", label: "Original violet, pink & yellow", colors: ["#9929ea", "#cc66da", "#faeb92"] },
  { id: "ivory-charcoal", label: "Ivory & charcoal", colors: ["#383832", "#6d715f", "#f5f0e6"] },
  { id: "beige-blue", label: "Muted yellow beige & royal blue", colors: ["#2852a1", "#d8c47e", "#f2ead4"] },
  { id: "lime-orange", label: "Lime yellow & orange", colors: ["#df7137", "#d7e75c", "#f4f6df"] },
  { id: "bronze-pearl", label: "Bronze & pearl", colors: ["#98683e", "#d6c1a8", "#f2ece3"] },
  { id: "ruby-seafoam", label: "Deep ruby & seafoam", colors: ["#8d2635", "#a7d8c3", "#eef7f2"] },
  { id: "yellow-sage", label: "Yellow & sage", colors: ["#82966d", "#dfc849", "#f7f4df"] }
];

export function readThemePreference(value) {
  let storedValue = value;
  if (storedValue === undefined) {
    try {
      storedValue = localStorage.getItem("expenseTrackerTheme");
    } catch {
      storedValue = "";
    }
  }
  const [storedPalette, storedMode] = String(storedValue || "").split(":");
  if (storedPalette === "dark" || storedPalette === "light") {
    return { palette: "previous", mode: storedPalette };
  }
  const palette = themes.some((theme) => theme.id === storedPalette) ? storedPalette : "previous";
  const mode = storedMode === "dark" ? "dark" : "light";
  return { palette, mode };
}

export function applyThemePreference(preference) {
  document.documentElement.dataset.palette = preference.palette;
  document.documentElement.dataset.theme = preference.mode;
}

export default function ThemeToggle() {
  const [preference, setPreference] = useState(() => readThemePreference());

  useEffect(() => {
    applyThemePreference(preference);
    try {
      localStorage.setItem("expenseTrackerTheme", `${preference.palette}:${preference.mode}`);
    } catch (error) {
      console.warn("Could not save the theme preference.", error);
    }
  }, [preference]);

  const chooseMode = (mode) => setPreference((current) => ({ ...current, mode }));
  const choosePalette = (palette) => setPreference((current) => ({ ...current, palette }));

  return (
    <section className="theme-settings" aria-labelledby="theme-settings-title">
      <div>
        <span className="eyebrow">PERSONALIZE</span>
        <h2 id="theme-settings-title">Appearance</h2>
        <p className="card-note">Choose a color palette and light or dark mode.</p>
      </div>
      <fieldset className="theme-mode-options">
        <legend>Display mode</legend>
        {["light", "dark"].map((mode) => (
          <label className={`theme-mode-option${preference.mode === mode ? " selected" : ""}`} key={mode}>
            <input
              type="radio"
              name="theme-mode"
              value={mode}
              checked={preference.mode === mode}
              onChange={() => chooseMode(mode)}
            />
            <span>{mode === "light" ? "☀ Light" : "☾ Dark"}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="theme-palette-options">
        <legend>Color palette</legend>
        {themes.map((theme) => (
          <label className={`theme-palette-option${preference.palette === theme.id ? " selected" : ""}`} key={theme.id}>
            <input
              type="radio"
              name="theme-palette"
              value={theme.id}
              checked={preference.palette === theme.id}
              onChange={() => choosePalette(theme.id)}
            />
            <span className="theme-palette-colors" aria-hidden="true">
              {theme.colors.map((color) => <i key={color} style={{ backgroundColor: color }} />)}
            </span>
            <span>{theme.label}</span>
          </label>
        ))}
      </fieldset>
    </section>
  );
}
