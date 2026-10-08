import React, { Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import SignUpPage from "./pages/SignUpPage";
import ViewSearchPage from "./pages/ViewSearchPage";
import SaveCredentialPage from "./pages/SaveCredentialPage";
import EditCredentialPage from "./pages/EditCredentialPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminProfilesPage from "./pages/AdminProfilesPage";

// ForbiddenPage is created in task 24.2. Lazy-loaded so this router file
// compiles before that task completes; once the file exists it resolves
// normally at runtime.
const ForbiddenPage = React.lazy(() => import("./pages/ForbiddenPage"));

/**
 * Application router (react-router-dom v6 data router).
 *
 * Route structure:
 *  /login                  → LoginPage (public)
 *  /signup                 → SignUpPage (public)
 *  /credentials            → ProtectedRoute(screen="credentials")       → ViewSearchPage
 *  /credentials/new        → ProtectedRoute(screen="credentials.new")   → SaveCredentialPage
 *  /credentials/:id/edit   → ProtectedRoute(screen="credentials.edit")  → EditCredentialPage
 *  /admin/users            → ProtectedRoute(screen="admin.users")       → AdminUsersPage
 *  /admin/profiles         → ProtectedRoute(screen="admin.profiles")    → AdminProfilesPage
 *  /403                    → ForbiddenPage (public — shown after redirect)
 *  *                       → redirect to /login
 *
 * Requirements: 2.5, 3.4, 3.6, 10.1
 */
const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/signup",
    element: <SignUpPage />,
  },
  {
    path: "/credentials",
    element: (
      <ProtectedRoute screen="credentials">
        <ViewSearchPage />
      </ProtectedRoute>
    ),
  },
  {
    path: "/credentials/new",
    element: (
      <ProtectedRoute screen="credentials.new">
        <SaveCredentialPage />
      </ProtectedRoute>
    ),
  },
  {
    path: "/credentials/:id/edit",
    element: (
      <ProtectedRoute screen="credentials.edit">
        <EditCredentialPage />
      </ProtectedRoute>
    ),
  },
  {
    path: "/admin/users",
    element: (
      <ProtectedRoute screen="admin.users">
        <AdminUsersPage />
      </ProtectedRoute>
    ),
  },
  {
    path: "/admin/profiles",
    element: (
      <ProtectedRoute screen="admin.profiles">
        <AdminProfilesPage />
      </ProtectedRoute>
    ),
  },
  {
    path: "/403",
    // Suspense boundary required for React.lazy; fallback renders nothing
    // while the chunk loads (the page is tiny so the flash is imperceptible).
    element: (
      <Suspense fallback={null}>
        <ForbiddenPage />
      </Suspense>
    ),
  },
  {
    // Catch-all: redirect any unrecognised path to /login (Req 2.5, 3.4)
    path: "*",
    element: <Navigate to="/login" replace />,
  },
]);

export default router;
