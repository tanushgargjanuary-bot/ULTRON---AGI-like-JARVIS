"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function GoogleSignInButton() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function signIn() {
    setLoading(true);
    setError("");
    try {
      const supabase = createClient();
      const redirectTo = new URL("/auth/callback?next=%2Fchat", window.location.origin).toString();
      const { error: signInError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo }
      });
      if (signInError) throw signInError;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Google sign-in could not start.");
      setLoading(false);
    }
  }

  return (
    <div className="sign-in-area">
      <button className="google-button" type="button" onClick={signIn} disabled={loading}>
        <span className="google-g" aria-hidden="true">G</span>
        {loading ? "Connecting…" : "Continue with Google"}
      </button>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
    </div>
  );
}
