import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../../i18n/i18n";
import apiClient from "../../api/apiClient";
import SessionGuard from "../layout/SessionGuard";
import { ReauthProvider, useReauth } from "../../context/ReauthContext";
import { copySecret } from "../../lib/clipboard";
import { httpError } from "../../test/axiosError";

describe("Clipboard clearing (Requirement 16.6)", () => {
  let content = "";
  beforeEach(() => {
    vi.useFakeTimers();
    content = "";
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn(async (text: string) => {
          content = text;
        }),
        readText: vi.fn(async () => content),
      },
    });
  });
  afterEach(() => vi.useRealTimers());

  it("clears the copied password after 30 seconds", async () => {
    expect(await copySecret("S3cret!")).toBe(true);
    expect(content).toBe("S3cret!");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_000);
    });
    expect(content).toBe("S3cret!");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(content).toBe("");
  });

  it("leaves something else the person copied afterwards", async () => {
    await copySecret("S3cret!");
    content = "my own text";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(content).toBe("my own text");
  });
});

describe("SessionGuard (Requirement 16.4)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers();
    window.localStorage.clear();
  });
  afterEach(() => vi.useRealTimers());

  async function mount(limits: { idle_seconds: number; expires_in_seconds: number | null }) {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { extend_minutes: 30, ...limits } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { idle_seconds: limits.idle_seconds, expires_in_seconds: 1800, extend_minutes: 30 },
    });
    const onEnd = vi.fn();
    render(<SessionGuard onEnd={onEnd} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    return { post, onEnd };
  }

  it("warns a minute before the idle limit and stays signed in on request", async () => {
    const { post, onEnd } = await mount({ idle_seconds: 120, expires_in_seconds: 3600 });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(61_000);
    });
    expect(screen.getByRole("alertdialog")).toHaveTextContent("you will be signed out in");
    fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
    expect(post).toHaveBeenCalledWith("/api/profile/session/ping");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(121_000);
    });
    expect(onEnd).toHaveBeenCalledWith("idle");
  });

  it("offers to extend a minute before the maximum", async () => {
    const { post, onEnd } = await mount({ idle_seconds: 3600, expires_in_seconds: 90 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000);
    });
    fireEvent.click(screen.getByRole("button", { name: "Extend 30 min" }));
    expect(post).toHaveBeenCalledWith("/api/profile/session/extend");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });
    expect(onEnd).not.toHaveBeenCalled();
  });
});

describe("Re-authentication for administration (Requirement 16.5)", () => {
  beforeEach(() => vi.restoreAllMocks());

  function Action({ request }: { request: () => Promise<string> }) {
    const withReauth = useReauth();
    const [result, setResult] = useState("");
    return (
      <>
        <button type="button" onClick={() => void withReauth(request).then(setResult, () => setResult("cancelled"))}>
          act
        </button>
        <output>{result}</output>
      </>
    );
  }

  it("asks for the password once and retries the action", async () => {
    const request = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(httpError(403, "Re-authentication required."))
      .mockResolvedValueOnce("done");
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    render(
      <ReauthProvider>
        <Action request={request} />
      </ReauthProvider>
    );
    await userEvent.click(screen.getByRole("button", { name: "act" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(dialog.querySelector("input")!, "Str0ngPassw0rd!");
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(post).toHaveBeenCalledWith("/api/profile/session/reauth", { account_password: "Str0ngPassw0rd!" });
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("done")).toBeInTheDocument();
  });
});
