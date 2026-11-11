import { useNavigate } from "react-router-dom";
import { getStore } from "../api/platform";
import { useAuth } from "../auth/AuthContext";
import { useApi } from "../hooks/useApi";

/** In merchant mode: which brand is open, and the way back to the brand list. */
export default function BrandSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const { brandId } = useAuth();
  return brandId ? <OpenBrand brandId={brandId} onNavigate={onNavigate} /> : null;
}

function OpenBrand({ brandId, onNavigate }: { brandId: string; onNavigate?: () => void }) {
  const { leaveBrand } = useAuth();
  const navigate = useNavigate();
  const store = useApi(() => getStore(), [brandId]);
  return (
    <div className="brand-switcher">
      <span className="brand-switcher-label">Managing</span>
      <strong className="brand-switcher-name">{store.data?.name ?? "…"}</strong>
      <button
        type="button"
        className="brand-switcher-button"
        onClick={() => {
          leaveBrand();
          onNavigate?.();
          navigate("/brands");
        }}
      >
        Switch brand
      </button>
    </div>
  );
}
