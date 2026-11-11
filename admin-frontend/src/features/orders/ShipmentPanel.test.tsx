import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api/shipments';
import type { CourierShipment, OrderShipments } from '../../types/shipment';
import ShipmentPanel from './ShipmentPanel';

vi.mock('../../api/shipments', () => ({
  getShipments: vi.fn(), createShipment: vi.fn(), getCourierRates: vi.fn(), shipmentAction: vi.fn(),
}));

const parcel = { weight_kg: '0.750', length_cm: '25.0', breadth_cm: '20.0', height_cm: '4.0' };
const envelope = <T,>(data: T) => ({ success: true, message: 'OK', data, meta: null });
const booked: CourierShipment = {
  id: 'shipment-1', state: 'READY_TO_SHIP', attempt: 1, channel_order_id: '12345-1',
  awb_code: 'AWB123', courier_name: 'Courier', tracking_url: 'https://courier.invalid/track',
  label_url: null, manifest_url: null, pickup_scheduled_date: null, pickup_token_number: null,
  provider_etd: null, package: parcel, payment_mode: 'COD', declared_value: '1050.00',
  cod_amount: '850.00', freight_charge: '40.00', cod_charge: '20.00',
  provider_status_label: null, pending_operation: null, operation_status: null,
  last_error: null, recovery_hint: null, last_synced_at: null, events: [],
  actions: ['schedule_pickup', 'label', 'sync', 'cancel'],
};
const data: OrderShipments = {
  provider_enabled: true, credentials_configured: true, can_create: true,
  create_blocked_reason: null, package_defaults: parcel, current: null, history: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getShipments).mockResolvedValue(envelope(data));
  vi.mocked(api.createShipment).mockResolvedValue(envelope(booked));
  vi.mocked(api.shipmentAction).mockResolvedValue(envelope(booked));
});

function show(canManage = true) {
  return render(<MemoryRouter><ShipmentPanel orderId="order-1" currency="INR"
    canManage={canManage} onDone={vi.fn()} /></MemoryRouter>);
}

describe('courier fulfilment', () => {
  it('confirms a real booking and sends the measured parcel', async () => {
    show();
    await userEvent.click(await screen.findByRole('button', { name: 'Create courier shipment' }));
    expect(api.createShipment).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toHaveTextContent('real booking');
    await userEvent.click(screen.getByRole('button', { name: 'Book shipment' }));
    await waitFor(() => expect(api.createShipment).toHaveBeenCalledExactlyOnceWith('order-1', parcel, null));
  });

  it('offers provider rates and submits the selected courier without changing order totals', async () => {
    vi.mocked(api.getCourierRates).mockResolvedValue(envelope({ couriers: [{
      courier_id: '10', courier_name: 'Courier', freight_charge: '40.00', cod_charge: '20.00',
      total_charge: '60.00', cod_available: true, etd: 'Nov 2, 2026',
      estimated_delivery_days: '4', is_recommended: true,
    }] }));
    show();
    await userEvent.click(await screen.findByRole('button', { name: 'Check live courier rates' }));
    const option = await screen.findByRole('option', { name: /Courier.*60/ });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Booking courier' }), option);
    await userEvent.click(screen.getByRole('button', { name: 'Create courier shipment' }));
    await userEvent.click(screen.getByRole('button', { name: 'Book shipment' }));
    await waitFor(() => expect(api.createShipment).toHaveBeenCalledWith('order-1', parcel, '10'));
  });

  it('hides write controls from staff without order management permission', async () => {
    vi.mocked(api.getShipments).mockResolvedValue(envelope({ ...data, current: booked, can_create: false }));
    show(false);
    await screen.findByText('AWB123', { exact: false });
    expect(screen.queryByRole('button', { name: 'Schedule pickup' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel courier shipment' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open courier tracking' })).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('shows recovery guidance and reconciles the same shipment', async () => {
    vi.mocked(api.getShipments).mockResolvedValue(envelope({ ...data, can_create: false,
      current: { ...booked, pending_operation: 'CREATE', operation_status: 'UNKNOWN',
        recovery_hint: 'Check the existing booking before retrying.', actions: ['retry'] } }));
    vi.mocked(api.shipmentAction).mockRejectedValue(new Error('Booking remains unconfirmed'));
    show();
    await userEvent.click(await screen.findByRole('button', { name: 'Retry / reconcile' }));
    await waitFor(() => expect(api.shipmentAction).toHaveBeenCalledWith('order-1', 'shipment-1', 'retry', {}));
    expect(await screen.findByText(/Courier request failed: Booking remains unconfirmed/)).toBeInTheDocument();
    expect(api.createShipment).not.toHaveBeenCalled();
    expect(vi.mocked(api.getShipments).mock.calls.length).toBeGreaterThan(1);
  });

  it('schedules pickup using the chosen date', async () => {
    vi.mocked(api.getShipments).mockResolvedValue(envelope({ ...data, current: booked, can_create: false }));
    show();
    const input = await screen.findByLabelText('Pickup date');
    await userEvent.type(input, '2026-11-01');
    await userEvent.click(screen.getByRole('button', { name: 'Schedule pickup' }));
    await waitFor(() => expect(api.shipmentAction).toHaveBeenCalledWith(
      'order-1', 'shipment-1', 'pickup', { pickup_date: '2026-11-01' }));
  });

  it('shows verified label links and rejects unsafe URLs', async () => {
    vi.mocked(api.getShipments).mockResolvedValue(envelope({ ...data, current: {
      ...booked, label_url: 'https://files.invalid/label.pdf', manifest_url: 'javascript:alert(1)',
    } }));
    show();
    expect(await screen.findByRole('link', { name: 'Download courier label' })).toHaveAttribute('href', 'https://files.invalid/label.pdf');
    expect(screen.queryByRole('link', { name: 'Download manifest' })).not.toBeInTheDocument();
  });
});
