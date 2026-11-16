import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { apiFetch, requestJson, subscribeAuthRequired } from "../lib/api";

const statusSchema = z.object({
  public: z.boolean(),
  authenticated: z.boolean(),
  read_only: z.boolean(),
});

const STATUS_KEY = ["auth", "status"] as const;

function LoginScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await apiFetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (response.ok) {
        setPassword("");
        onSignedIn();
        return;
      }
      setMessage(
        response.status === 429
          ? "Too many attempts. Wait a moment and try again."
          : "Incorrect password.",
      );
    } catch {
      setMessage("Could not reach the API.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="dashboard" aria-labelledby="login-title">
      <form className="glass panel field" onSubmit={(event) => void submit(event)} style={{ maxWidth: 380, margin: "12vh auto 0" }}>
        <h1 id="login-title" className="panel-title">
          Sign in
        </h1>
        <label htmlFor="ledger-password">Password</label>
        <input
          id="ledger-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        {message ? (
          <small role="alert" data-testid="login-error">
            {message}
          </small>
        ) : null}
        <button type="submit" className="btn btn-primary" disabled={busy || password === ""}>
          {busy ? "Signing in" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: STATUS_KEY,
    queryFn: () => requestJson("/api/auth/status", statusSchema),
    retry: 1,
  });

  useEffect(
    () => subscribeAuthRequired(() => void client.invalidateQueries({ queryKey: STATUS_KEY })),
    [client],
  );

  // If the status route is unreachable, show the app; its own offline handling explains the problem.
  const needsLogin = status.data?.public === true && !status.data.authenticated;
  if (status.isPending) return null;
  if (needsLogin) {
    return <LoginScreen onSignedIn={() => void client.invalidateQueries()} />;
  }
  return (
    <>
      {status.data?.read_only ? (
        <div role="status" className="glass" data-testid="read-only-banner" style={{ padding: "6px 16px", textAlign: "center" }}>
          Read-only demo. Changes are turned off.
        </div>
      ) : null}
      {children}
    </>
  );
}
