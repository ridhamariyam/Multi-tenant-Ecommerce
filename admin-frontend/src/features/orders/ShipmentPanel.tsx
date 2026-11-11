import { useState } from 'react';
import { Link } from 'react-router-dom';
import { createShipment, getCourierRates, getShipments, shipmentAction } from '../../api/shipments';
import Badge from '../../components/common/Badge';
import ConfirmDialog from '../../components/common/ConfirmDialog';
import Field from '../../components/common/Field';
import StatusMessage from '../../components/common/StatusMessage';
import { useAction } from '../../hooks/useAction';
import { useApi } from '../../hooks/useApi';
import type { CourierRate, OrderShipments } from '../../types/shipment';
import { formatDate, formatMoney, label } from '../../utils/formatters';
import ParcelFields, { EMPTY_PARCEL } from '../shipping/ParcelFields';

function safeLink(url: string | null) {
  try { return url && new URL(url).protocol === 'https:' ? url : undefined; }
  catch { return undefined; }
}

export default function ShipmentPanel({ orderId, currency, canManage, onDone }: {
  orderId: string; currency: string; canManage: boolean; onDone: () => void;
}) {
  const shipments = useApi(() => getShipments(orderId), [orderId]);
  return <section className="panel" aria-label="Courier fulfilment">
    <h3>Courier fulfilment</h3>
    {shipments.error && <div className="status status-error" role="alert">{shipments.error} <button onClick={shipments.reload}>Reload shipments</button></div>}
    {!shipments.data && !shipments.error && <p>Loading shipments…</p>}
    {shipments.data && <ShipmentControls key={`${orderId}-${shipments.data.current?.id ?? 'new'}`}
      data={shipments.data} orderId={orderId} currency={currency} canManage={canManage}
      onDone={() => { shipments.reload(); onDone(); }} />}
  </section>;
}

function ShipmentControls({ data, orderId, currency, canManage, onDone }: {
  data: OrderShipments; orderId: string; currency: string; canManage: boolean; onDone: () => void;
}) {
  const s = data.current;
  const [parcel, setParcel] = useState(s?.package ?? data.package_defaults ?? EMPTY_PARCEL);
  const [rates, setRates] = useState<CourierRate[] | null>(null);
  const [courierId, setCourierId] = useState('');
  const [pickupDate, setPickupDate] = useState('');
  const [confirm, setConfirm] = useState<'create' | 'cancel' | null>(null);
  const action = useAction();
  const available = (step: string) => canManage && !!s?.actions.includes(step);
  const perform = async (step: string, body = {}) => {
    if (!s) return;
    await action.run(async () => {
      try { return await shipmentAction(orderId, s.id, step, body); }
      finally { onDone(); }
    }, 'Courier shipment updated', 'Courier request failed');
  };

  return <>
    <StatusMessage status={action.status} />
    {!data.provider_enabled && <p>Courier booking is disabled. <Link to="/delivery">Open delivery settings</Link>.</p>}
    {s ? <>
      <dl className="kv">
        <dt>Shipment</dt><dd><Badge value={s.state} /></dd>
        <dt>Courier status</dt><dd>{s.provider_status_label ?? 'Awaiting a tracking update'}</dd>
        <dt>Courier / AWB</dt><dd>{s.courier_name ?? 'Unassigned'} · {s.awb_code ?? 'No AWB yet'}</dd>
        <dt>Booking reference</dt><dd>{s.channel_order_id}</dd>
        <dt>Payment</dt><dd>{label(s.payment_mode)} · collect {formatMoney(s.cod_amount, currency)} at delivery</dd>
        <dt>Order value</dt><dd>{formatMoney(s.declared_value, currency)}</dd>
        <dt>Courier freight</dt><dd>{s.freight_charge === null ? 'Not reported' : formatMoney(s.freight_charge, currency)}</dd>
        <dt>Courier COD fee</dt><dd>{s.cod_charge === null ? 'Not reported' : formatMoney(s.cod_charge, currency)}</dd>
        <dt>Parcel</dt><dd>{s.package.weight_kg} kg · {s.package.length_cm} × {s.package.breadth_cm} × {s.package.height_cm} cm</dd>
        {s.pickup_scheduled_date && <><dt>Pickup</dt><dd>{s.pickup_scheduled_date} {s.pickup_token_number}</dd></>}
        {s.provider_etd && <><dt>Courier delivery estimate</dt><dd>{s.provider_etd}</dd></>}
        {s.last_synced_at && <><dt>Tracking checked</dt><dd>{formatDate(s.last_synced_at)}</dd></>}
      </dl>
      {s.last_error && <p className="status status-error" role="alert">{s.last_error}</p>}
      {s.recovery_hint && <p className="notice">{s.recovery_hint}</p>}
      <div className="toolbar">
        {safeLink(s.tracking_url) && <a className="btn" href={safeLink(s.tracking_url)} target="_blank" rel="noopener noreferrer">Open courier tracking</a>}
        {safeLink(s.label_url) && <a className="btn" href={safeLink(s.label_url)} target="_blank" rel="noopener noreferrer">Download courier label</a>}
        {safeLink(s.manifest_url) && <a className="btn" href={safeLink(s.manifest_url)} target="_blank" rel="noopener noreferrer">Download manifest</a>}
        {([
          ['label', 'Generate courier label'], ['manifest', 'Generate manifest'],
          ['sync', 'Refresh courier tracking'], ['retry', 'Retry / reconcile'],
        ] as const).map(([step, title]) => available(step) && <button key={step} disabled={action.busy} onClick={() => perform(step)}>{title}</button>)}
        {available('cancel') && <button disabled={action.busy} onClick={() => setConfirm('cancel')}>Cancel courier shipment</button>}
      </div>
      {available('schedule_pickup') && <form className="form" onSubmit={e => { e.preventDefault(); void perform('pickup', { pickup_date: pickupDate || null }); }}>
        <Field label="Pickup date" hint="Blank lets the provider choose the next available slot."><input type="date" value={pickupDate} onChange={e => setPickupDate(e.target.value)} /></Field>
        <button disabled={action.busy}>Schedule pickup</button>
      </form>}
      {!!s.events.length && <details><summary>Courier event history ({s.events.length})</summary>
        <ul className="list-plain timeline detail-scroll-list">{[...s.events].reverse().map((event, index) =>
          <li key={`${event.occurred_at}-${index}`}><span>{formatDate(event.occurred_at)}</span><span>{event.activity ?? event.status_label ?? (event.state ? label(event.state) : `Provider status ${event.provider_status_code}`)}{event.location && ` · ${event.location}`}</span></li>,
        )}</ul>
      </details>}
    </> : <p className="muted">{data.create_blocked_reason ?? 'Book this order with a courier once the parcel is packed.'}</p>}

    {canManage && ((data.can_create && data.credentials_configured) || available('assign_awb')) && <form className="form" onSubmit={e => {
      e.preventDefault();
      if (s) void perform('awb', { courier_id: courierId || null });
      else setConfirm('create');
    }}>
      {!s && <ParcelFields value={parcel} onChange={next => { setParcel(next); setRates(null); setCourierId(''); }} />}
      <button type="button" disabled={action.busy || Object.values(parcel).some(value => !value || Number(value) <= 0)} onClick={() => action.run(async () => {
        const result = await getCourierRates(orderId, parcel); setRates(result.data.couriers); setCourierId('');
      }, null, 'Could not retrieve courier rates')}>Check live courier rates</button>
      {rates !== null && rates.length === 0 && <p>No couriers are available for this parcel and destination.</p>}
      <Field label="Booking courier" hint="Leave automatic selection to Shiprocket, or check rates and choose a courier.">
        <select value={courierId} onChange={e => setCourierId(e.target.value)}>
          <option value="">{s ? 'Shiprocket default courier' : 'Assign courier after booking'}</option>
          {rates?.map(rate => <option key={rate.courier_id} value={rate.courier_id}>{rate.courier_name} · {rate.total_charge === null ? 'Price not reported' : formatMoney(rate.total_charge, currency)}{rate.etd ? ` · ${rate.etd}` : ''}{rate.is_recommended ? ' · Recommended' : ''}</option>)}
        </select>
      </Field>
      <p className="muted">These are current provider quotes for the store. The customer’s checkout total stays as agreed.</p>
      <button className="primary" disabled={action.busy}>{s ? 'Assign courier and AWB' : 'Create courier shipment'}</button>
    </form>}
    {!!data.history.length && <details><summary>Earlier shipment attempts ({data.history.length})</summary>
      <ul>{data.history.map(previous => <li key={previous.id}>Attempt {previous.attempt}: {label(previous.state)} · {previous.awb_code ?? previous.channel_order_id}</li>)}</ul>
    </details>}
    {confirm && <ConfirmDialog title={confirm === 'create' ? 'Book this courier shipment?' : 'Cancel this courier shipment?'}
      message={confirm === 'create' ? 'This creates a real booking in the configured Shiprocket account. Courier charges may apply.' : 'This cancels the courier booking. Handle order cancellation and any refund separately.'}
      confirmLabel={confirm === 'create' ? 'Book shipment' : 'Cancel courier shipment'}
      onCancel={() => setConfirm(null)} onConfirm={() => {
        const step = confirm; setConfirm(null);
        if (step === 'cancel') void perform('cancel');
        else void action.run(async () => {
          try { return await createShipment(orderId, parcel, courierId || null); }
          finally { onDone(); }
        }, 'Courier shipment created', 'Booking failed');
      }} />}
  </>;
}
