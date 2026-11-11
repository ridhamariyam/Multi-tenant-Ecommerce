import { useState } from "react";
import { mediaUrl } from "../../api/client";

function ProductImage({ url, alt = "", className = "" }: { url: string | null | undefined; alt?: string; className?: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const failed = !url || failedUrl === url;
  return failed ? (
    <div className={`product-image-placeholder ${className}`} role="img" aria-label="Product image unavailable">
      <span aria-hidden="true">▧</span>
    </div>
  ) : <img className={className} src={mediaUrl(url)} alt={alt} onError={() => setFailedUrl(url)} />;
}

export default ProductImage;
