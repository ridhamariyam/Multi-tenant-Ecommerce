import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api/shipments';
import ProviderSettings from './ProviderSettings';

vi.mock('../../api/shipments', () => ({
  getProviderSettings: vi.fn(), saveProviderSettings: vi.fn(), getPickupLocations: vi.fn(),
}));

const defaults = {
  is_enabled: false, credentials_configured: true, webhook_configured: false,
  pickup_location: null, pickup_postcode: null, fallback_email: null,
  package_defaults: null, updated_at: null,
};
const envelope = <T,>(data: T) => ({ success: true, message: 'OK', data, meta: null });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getProviderSettings).mockResolvedValue(envelope(defaults));
  vi.mocked(api.saveProviderSettings).mockResolvedValue(envelope(defaults));
});

describe('courier provider setup', () => {
  it('cannot enable booking without server credentials', async () => {
    vi.mocked(api.getProviderSettings).mockResolvedValue(envelope({ ...defaults, credentials_configured: false }));
    render(<ProviderSettings canEdit />);
    expect(await screen.findByRole('checkbox', { name: 'Enable real courier bookings' })).toBeDisabled();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  });

  it('uses registered pickup details and keeps unconfigured package defaults empty', async () => {
    vi.mocked(api.getPickupLocations).mockResolvedValue(envelope([
      { name: 'Warehouse', postcode: '682001', city: 'Kochi', state: 'Kerala', is_primary: true },
    ]));
    render(<ProviderSettings canEdit />);
    await userEvent.click(await screen.findByRole('button', { name: 'Load registered pickup locations' }));
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: 'Registered pickup location' }), 'Warehouse');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Enable real courier bookings' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save courier settings' }));
    await waitFor(() => expect(api.saveProviderSettings).toHaveBeenCalledWith({
      is_enabled: true, pickup_location: 'Warehouse', pickup_postcode: '682001',
      fallback_email: null, package_defaults: null,
    }));
  });

  it('keeps settings read only without management permission', async () => {
    render(<ProviderSettings canEdit={false} />);
    expect(await screen.findByRole('checkbox', { name: 'Enable real courier bookings' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save courier settings' })).not.toBeInTheDocument();
  });
});
