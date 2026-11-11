// Shapes shared by every backend response.

export interface PageMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

// Every successful response is wrapped in this envelope.
export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  meta: PageMeta | null;
}

// One field-level problem reported by the backend (e.g. validation errors).
export interface ApiErrorDetail {
  field?: string;
  message?: string;
  type?: string;
}

export type CatalogueStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";

export const CATALOGUE_STATUSES: CatalogueStatus[] = ["DRAFT", "ACTIVE", "ARCHIVED"];
