import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { signOut } from "./actions";

export default async function ChatPage() {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) {
    redirect("/login");
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data.claims) redirect("/login");

  const email = typeof data.claims.email === "string" ? data.claims.email : "Signed-in user";

  return (
    <main className="workspace-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark small" aria-hidden="true">U</span>
          <span>ULTRON</span>
        </div>
        <div className="sidebar-label">WORKSPACE</div>
        <div className="nav-item active"><span aria-hidden="true">◈</span>New conversation</div>
        <div className="sidebar-bottom">
          <div className="user-chip">
            <span className="user-dot" aria-hidden="true" />
            <span title={email}>{email}</span>
          </div>
          <form action={signOut}>
            <button className="sign-out-button" type="submit">Sign out</button>
          </form>
        </div>
      </aside>

      <section className="chat-workspace">
        <header className="workspace-header">
          <div><p className="eyebrow">REMOTE WORKSPACE</p><h1>ULTRON</h1></div>
          <span className="connection-status"><span className="status-dot" />AUTHENTICATED</span>
        </header>

        <div className="chat-empty-state">
          <div className="orb" aria-hidden="true">U</div>
          <p className="eyebrow">WEB INTERFACE INITIALISED</p>
          <h2>Your workspace is ready.</h2>
          <p className="muted">
            Google authentication is active. The ULTRON agent service is not connected in this first release.
          </p>
          <div className="runtime-notice">
            <span className="notice-icon" aria-hidden="true">!</span>
            <span>Chat execution will be enabled after the secure Python backend connection is added.</span>
          </div>
        </div>

        <div className="composer-wrap">
          <div className="composer-disabled" aria-disabled="true">
            <span>Agent connection pending…</span>
            <button type="button" disabled aria-label="Send message">↑</button>
          </div>
          <p className="composer-caption">This workspace does not send or store prompts yet.</p>
        </div>
      </section>
    </main>
  );
}
