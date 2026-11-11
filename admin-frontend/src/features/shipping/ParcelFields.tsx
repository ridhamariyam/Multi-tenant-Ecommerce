import Field from '../../components/common/Field';
import type { Parcel } from '../../types/shipment';

export const EMPTY_PARCEL: Parcel = { weight_kg: '', length_cm: '', breadth_cm: '', height_cm: '' };

export default function ParcelFields({ value, onChange, required = true }: {
  value: Parcel; onChange: (parcel: Parcel) => void; required?: boolean;
}) {
  return <div className="form-grid">
    {([
      ['weight_kg', 'Parcel weight (kg)', '0.001', '0.001', '100'],
      ['length_cm', 'Parcel length (cm)', '0.6', '0.1', '300'],
      ['breadth_cm', 'Parcel breadth (cm)', '0.6', '0.1', '300'],
      ['height_cm', 'Parcel height (cm)', '0.6', '0.1', '300'],
    ] as const).map(([key, title, min, step, max]) =>
      <Field key={key} label={title} required={required}>
        <input type="number" min={min} max={max} step={step} required={required}
          value={value[key]} onChange={e => onChange({ ...value, [key]: e.target.value })} />
      </Field>,
    )}
  </div>;
}
