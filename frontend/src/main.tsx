import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router/dom";

import { AuthProvider } from "./context/AuthContext";
import { PreferencesProvider } from "./context/PreferencesContext";
import SessionBootstrap from "./components/SessionBootstrap";
import router from "./router";
import "./index.css";
import "./i18n/i18n";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <PreferencesProvider>
        <SessionBootstrap>
          <RouterProvider router={router} />
        </SessionBootstrap>
      </PreferencesProvider>
    </AuthProvider>
  </React.StrictMode>
);
