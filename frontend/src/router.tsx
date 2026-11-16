import React, { Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router";

import AppLayout from "./components/AppLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import SignUpPage from "./pages/SignUpPage";
import ViewSearchPage from "./pages/ViewSearchPage";
import SaveCredentialPage from "./pages/SaveCredentialPage";
import EditCredentialPage from "./pages/EditCredentialPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";

// ForbiddenPage is created in task 24.2. Lazy-loaded so this router file
// compiles before that task completes; once the file exists it resolves
// normally at runtime.
const ForbiddenPage = React.lazy(() => import("./pages/ForbiddenPage"));

/**
 * Application router (react-router v7 data router).
 *
 * Route structure:
 *  /login                  → LoginPage (public)
 *  /signup                 → SignUpPage (public)
 *  /verify-email?token=…   → VerifyEmailPage (public, spec Phase 2)
 *  /credentials            → ProtectedRoute(permission="credentials.view")    → ViewSearchPage
 *  /credentials/new        → ProtectedRoute(permission="credentials.create")  → SaveCredentialPage
 *  /credentials/:id/edit   → ProtectedRoute(permission="credentials.edit")    → EditCredentialPage
 *  /admin/users            → ProtectedRoute(permission="users.manage")        → AdminUsersPage
 *  /403                    → ForbiddenPage (public — shown after redirect)
 *  *                       → redirect to /login
 *
 * Requirements: 2.5, 3.5, 10.1 (permissions: task 37.1)
 */
const router = createBrowserRouter([
  {
    // Shell with header (language toggle, nav, logout) around every page.
    element: <AppLayout />,
    children: [
      {
        path: "/login",
        element: <LoginPage />,
      },
      {
        path: "/signup",
        element: <SignUpPage />,
      },
      {
        path: "/verify-email",
        element: <VerifyEmailPage />,
      },
      {
        path: "/credentials",
        element: (
          <ProtectedRoute permission="credentials.view">
            <ViewSearchPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "/credentials/new",
        element: (
          <ProtectedRoute permission="credentials.create">
            <SaveCredentialPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "/credentials/:id/edit",
        element: (
          <ProtectedRoute permission="credentials.edit">
            <EditCredentialPage />
          </ProtectedRoute>
        ),
      },
      {
        path: "/admin/users",
        element: (
          <ProtectedRoute permission="users.manage">
            <AdminUsersPage />
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
    ],
  },
]);

export default router;
