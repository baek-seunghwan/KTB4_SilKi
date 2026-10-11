import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./styles/fonts.css";
import "./index.css";
import App from "./App.jsx";

const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
const applySystemTheme = ({ matches: isDark }) => {
  document.documentElement.classList.toggle("dark", isDark);
  document.documentElement.classList.toggle("light", !isDark);
};
applySystemTheme(systemTheme);
systemTheme.addEventListener("change", applySystemTheme);

createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>,
);
