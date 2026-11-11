import type { PincodeRule } from "../../types/settings";

export const PIN = /^[1-9]\d{5}$/;

// "pincode,serviceable,cod,min_days,max_days,shipping,city,state" -- header row optional.
export function parsePincodeCsv(text: string): { rules: PincodeRule[]; errors: string[] } {
  const rules: PincodeRule[] = [];
  const errors: string[] = [];
  const yes = (v: string | undefined, dflt: boolean) => (v === undefined || v.trim() === "" ? dflt : /^(y|yes|true|1)$/i.test(v.trim()));
  const num = (v: string | undefined) => (v && v.trim() ? Number(v) : null);
  text.split(/\r?\n/).forEach((line, i) => {
    const cells = line.split(",").map((c) => c.trim());
    if (!cells[0] || (i === 0 && /pincode/i.test(cells[0]))) return;
    if (!PIN.test(cells[0])) return errors.push(`Line ${i + 1}: "${cells[0]}" is not a 6-digit pincode`);
    rules.push({ pincode: cells[0], is_serviceable: yes(cells[1], true), cod_available: yes(cells[2], true), min_delivery_days: num(cells[3]), max_delivery_days: num(cells[4]), shipping_amount: cells[5] || null, city: cells[6] || null, state: cells[7] || null });
  });
  return { rules, errors };
}
