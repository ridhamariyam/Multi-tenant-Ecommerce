/** Shown on a domain no published store answers at (unknown, unpublished or suspended). */
export default function StoreUnavailable() {
  return (
    <main
      style={{
        minHeight: '100dvh',
        display: 'grid',
        placeItems: 'center',
        padding: '24px 16px',
        fontFamily: 'Inter, Helvetica, Arial, sans-serif',
        textAlign: 'center',
        color: '#0d133c',
        background: '#fff',
      }}
    >
      <div style={{ maxWidth: 440 }}>
        <h1 style={{ fontSize: 28, margin: '0 0 12px' }}>This store isn&apos;t available</h1>
        <p style={{ margin: 0, lineHeight: 1.6, color: '#555' }}>
          There is no open store at this address. If you own it, check that it is published and that the domain is
          connected in your CliQ. dashboard.
        </p>
      </div>
    </main>
  );
}
