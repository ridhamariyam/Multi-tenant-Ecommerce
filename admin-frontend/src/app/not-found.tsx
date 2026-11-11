export default function NotFound() {
  return (
    <main className="login-page">
      <section className="login-card form" aria-labelledby="not-found-title">
        <h1 id="not-found-title">Page not found</h1>
        <p className="muted">This CliQ. Admin page is not available.</p>
        <a className="primary login-submit" href="/admin/signin">Return to admin sign in</a>
      </section>
    </main>
  );
}
