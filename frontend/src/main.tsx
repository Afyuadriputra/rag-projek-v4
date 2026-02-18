import React from "react";
import { createRoot } from "react-dom/client";
import { createInertiaApp } from "@inertiajs/react";
import axios from "axios";
import setupLocatorUI from "@locator/runtime";

import "./index.css";
import "./styles/glass.css";

if (import.meta.env.DEV) {
  // LocatorJS runtime: Alt+Click -> buka file komponen di editor
  setupLocatorUI();
}

// ==========================================
// 1) GLOBAL AXIOS (CSRF FOR DJANGO)
// ==========================================
axios.defaults.xsrfHeaderName = "X-CSRFToken";
axios.defaults.xsrfCookieName = "csrftoken";

// ==========================================
// 2) INERTIA BOOTSTRAP
// ==========================================
const el = document.getElementById("app");

if (el?.dataset?.page) {
  const pages = import.meta.glob(
    [
      "./pages/**/*.tsx",
      "!./pages/**/*.test.tsx",
      "!./pages/**/*.spec.tsx",
      "!./pages/**/__tests__/**",
    ],
    { eager: true }
  );

  createInertiaApp({
    resolve: (name) => {
      const expectedPath = `./pages/${name}.tsx`;
      const page = pages[expectedPath];

      if (!page) {
        console.error(`🚨 CRITICAL ERROR: Halaman '${name}' tidak ditemukan!`);
        return {
          default: () => (
            <div className="p-10 text-red-500 font-bold">
              ERROR: Page '{name}' Not Found.
            </div>
          ),
        };
      }

      return page as any;
    },

setup({ el, App, props }) {
  const root = createRoot(el);
  root.render(
    <React.StrictMode>
      <App {...props} />
    </React.StrictMode>
  );
},
  });
} else {
  console.warn("Inertia root not found or missing data-page. Skipping Inertia init.");
}
