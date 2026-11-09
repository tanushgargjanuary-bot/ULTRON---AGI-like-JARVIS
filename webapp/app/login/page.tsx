import GoogleSignInButton from "./google-sign-in-button";

export default function LoginPage() {
  return (
    <main className="page-shell login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">U</div>
        <p className="eyebrow">PERSONAL AI ASSISTANT</p>
        <h1 id="login-title">ULTRON Web</h1>
        <p className="muted">Sign in to open your private ULTRON workspace.</p>
        <GoogleSignInButton />
        <p className="fine-print">
          Google is used for identity only. This app does not request access to Gmail, Drive, Contacts, or other Google services.
        </p>
      </section>
      <footer className="page-footer">ULTRON · WEB ACCESS</footer>
    </main>
  );
}
