import { useState } from "react";
import { listProducts } from "../../api/products";
import { useApi } from "../../hooks/useApi";
import type { Product } from "../../types/catalogue";

/** Pick products by searching the catalogue; keeps the chosen order. */
function ProductPicker({ value, onChange, max }: { value: string[]; onChange: (ids: string[]) => void; max: number }) {
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});
  const results = useApi(() => (term ? listProducts({ search: term, page_size: 10 }) : Promise.resolve({ success: true, message: "", data: [] as Product[], meta: null })), [term]);
  const move = (i: number, d: number) => {
    const next = [...value];
    const [x] = next.splice(i, 1);
    next.splice(i + d, 0, x);
    onChange(next);
  };
  return (
    <div className="form">
      <ol>
        {value.map((id, i) => (
          <li key={id} className="toolbar">
            {names[id] ?? id.slice(0, 8)}
            <button type="button" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Up">↑</button>
            <button type="button" disabled={i === value.length - 1} onClick={() => move(i, 1)} aria-label="Down">↓</button>
            <button type="button" className="danger" onClick={() => onChange(value.filter((x) => x !== id))}>Remove</button>
          </li>
        ))}
      </ol>
      <div className="toolbar">
        <input placeholder="Search products to add" value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setTerm(search.trim()); } }} style={{ width: 240 }} />
        <button type="button" onClick={() => setTerm(search.trim())}>Search</button>
      </div>
      <ul className="list-plain">
        {results.data?.filter((p) => !value.includes(p.id)).map((p) => (
          <li key={p.id} className="toolbar">
            {p.name} <span className="muted">{p.status}</span>
            <button type="button" disabled={value.length >= max} onClick={() => { setNames({ ...names, [p.id]: p.name }); onChange([...value, p.id]); }}>Add</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default ProductPicker;
