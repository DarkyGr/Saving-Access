import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import axios from "axios";
import SessionBootstrap from "../SessionBootstrap";
import { AuthProvider, useAuth } from "../../context/AuthContext";

function makeJwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${enc({ alg: "HS256" })}.${enc(payload)}.sig`;
}

function WhoAmI() {
  const { user } = useAuth();
  return <p>{user ? `signed in as ${user.username}` : "signed out"}</p>;
}

function renderApp() {
  render(
    <AuthProvider>
      <SessionBootstrap>
        <WhoAmI />
      </SessionBootstrap>
    </AuthProvider>
  );
}

describe("SessionBootstrap", () => {
  afterEach(() => vi.restoreAllMocks());

  it("restores the session from the refresh cookie after a reload", async () => {
    const token = makeJwt({ user_id: 3, username: "alice", role: "User", exp: 9999999999 });
    const post = vi.spyOn(axios, "post").mockResolvedValue({ data: { access_token: token } });
    renderApp();
    expect(await screen.findByText("signed in as alice")).toBeInTheDocument();
    expect(post.mock.calls[0][0]).toMatch(/\/api\/auth\/refresh$/);
    expect(post.mock.calls[0][2]).toMatchObject({ withCredentials: true });
  });

  it("renders signed out when there is no valid refresh cookie", async () => {
    vi.spyOn(axios, "post").mockRejectedValue(new Error("401"));
    renderApp();
    expect(await screen.findByText("signed out")).toBeInTheDocument();
  });
});
