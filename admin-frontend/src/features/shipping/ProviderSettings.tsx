import { useState } from 'react';
import { getPickupLocations, getProviderSettings, saveProviderSettings } from '../../api/shipments';
import Field from '../../components/common/Field';
import StatusMessage from '../../components/common/StatusMessage';
import { useApi } from '../../hooks/useApi';
import { useAction } from '../../hooks/useAction';
import type { PickupLocation, ProviderSettings as Settings } from '../../types/shipment';
import ParcelFields, { EMPTY_PARCEL } from './ParcelFields';

export default function ProviderSettings({ canEdit }: { canEdit: boolean }) {
  const settings = useApi(getProviderSettings, []);
  if (settings.error) return <div className="status status-error" role="alert">{settings.error}</div>;
  if (!settings.data) return <div className="state">Loading courier setup…</div>;
  return <ProviderForm key={settings.data.updated_at ?? 'new'} initial={settings.data} canEdit={canEdit} />;
}

function ProviderForm({ initial, canEdit }: { initial: Settings; canEdit: boolean }) {
  const [form, setForm] = useState(initial);
  const [parcel, setParcel] = useState(initial.package_defaults ?? EMPTY_PARCEL);
  const [useDefaults, setUseDefaults] = useState(!!initial.package_defaults);
  const [locations, setLocations] = useState<PickupLocation[] | null>(null);
  const action = useAction();
  return <section className="panel">
    <h3>Shiprocket courier setup</h3>
    <p>{initial.credentials_configured ? 'API credentials are configured for this store.' : 'Ask your administrator to configure this store’s Shiprocket API credentials.'}</p>
    <p className="muted">Booking is available from each order. Checkout uses your delivery rules below. Courier charges are billed separately to the store.</p>
    <p className="muted">Tracking webhooks: {initial.webhook_configured ? 'configured' : 'not configured; periodic tracking sync is available'}.</p>
    <StatusMessage status={action.status} />
    <form className="form" onSubmit={async e => {
      e.preventDefault();
      await action.run(() => saveProviderSettings({
        is_enabled: form.is_enabled, pickup_location: form.pickup_location || null,
        pickup_postcode: form.pickup_postcode || null, fallback_email: form.fallback_email || null,
        package_defaults: useDefaults ? parcel : null,
      }), 'Courier settings saved', 'Could not save courier settings');
    }}>
      <fieldset className="form" disabled={!canEdit || action.busy} style={{ border: 0, padding: 0 }}>
        <label className="check"><input type="checkbox" checked={form.is_enabled}
          disabled={!initial.credentials_configured && !form.is_enabled} onChange={e => setForm({ ...form, is_enabled: e.target.checked })} />Enable real courier bookings</label>
        <button type="button" disabled={!initial.credentials_configured} onClick={() => action.run(async () => {
          const result = await getPickupLocations(); setLocations(result.data);
        }, null, 'Could not load pickup locations')}>Load registered pickup locations</button>
        {locations && <Field label="Registered pickup location"><select value={form.pickup_location ?? ''} onChange={e => {
          const location = locations.find(l => l.name === e.target.value);
          if (location) setForm({ ...form, pickup_location: location.name, pickup_postcode: location.postcode });
        }}><option value="">Choose a location…</option>{locations.map(l => <option key={l.name} value={l.name}>{l.name} · {l.postcode}</option>)}</select></Field>}
        <div className="form-grid">
          <Field label="Pickup location name" required={form.is_enabled} hint="Use the exact name registered in Shiprocket."><input required={form.is_enabled} maxLength={100} value={form.pickup_location ?? ''} onChange={e => setForm({ ...form, pickup_location: e.target.value })} /></Field>
          <Field label="Origin pincode" required={form.is_enabled}><input required={form.is_enabled} pattern="[1-9][0-9]{5}" inputMode="numeric" maxLength={6} value={form.pickup_postcode ?? ''} onChange={e => setForm({ ...form, pickup_postcode: e.target.value })} /></Field>
          <Field label="Fallback buyer email" hint="Used only when the order has no email; Shiprocket requires one."><input type="email" value={form.fallback_email ?? ''} onChange={e => setForm({ ...form, fallback_email: e.target.value })} /></Field>
        </div>
        <label className="check"><input type="checkbox" checked={useDefaults} onChange={e => setUseDefaults(e.target.checked)} />Set package defaults</label>
        <p className="muted">Measure the packed parcel. Defaults can be overridden for each order.</p>
        {useDefaults && <ParcelFields value={parcel} onChange={setParcel} />}
        {canEdit && <button className="primary" disabled={action.busy}>Save courier settings</button>}
      </fieldset>
    </form>
  </section>;
}
