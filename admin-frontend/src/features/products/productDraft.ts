const NEW_PRODUCT_DRAFT_KEY = "cliq-admin-new-product-form";

export const productDraftKey = (tenantId: string, userId: string) =>
  `${NEW_PRODUCT_DRAFT_KEY}:${tenantId}:${userId}`;

export function clearUnsavedProductDraft(tenantId: string, userId: string) {
  sessionStorage.removeItem(productDraftKey(tenantId, userId));
}
