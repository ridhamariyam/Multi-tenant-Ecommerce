import type { BlogPost, CmsPage, Faq, FaqCategory, HomeSection, Media, NavItem, SiteSettings } from "../types/cms";
import { request } from "./client";

const C = "/admin/cms";

export const listMedia = (query: object = {}) => request<Media[]>(`${C}/media`, { query });
export function uploadMedia(file: File, altText: string | null) {
  const form = new FormData();
  form.append("file", file);
  if (altText) form.append("alt_text", altText);
  return request<Media>(`${C}/media`, { method: "POST", formData: form });
}
export const updateMedia = (id: string, altText: string | null) =>
  request<Media>(`${C}/media/${id}`, { method: "PATCH", body: { alt_text: altText } });
export const getSite = () => request<SiteSettings>(`${C}/site`);
export const updateSite = (data: Omit<SiteSettings, "updated_at">) =>
  request<SiteSettings>(`${C}/site`, { method: "PUT", body: data });
export const deleteMedia = (id: string) => request<null>(`${C}/media/${id}`, { method: "DELETE" });

export const listSections = () => request<HomeSection[]>(`${C}/sections`);
export const createSection = (data: object) => request<HomeSection>(`${C}/sections`, { method: "POST", body: data });
export const updateSection = (id: string, data: object) =>
  request<HomeSection>(`${C}/sections/${id}`, { method: "PATCH", body: data });
export const deleteSection = (id: string) => request<null>(`${C}/sections/${id}`, { method: "DELETE" });
export const reorderSections = (ids: string[]) =>
  request<HomeSection[]>(`${C}/sections/order`, { method: "PUT", body: { ids } });

export const listPages = (query: object = {}) => request<CmsPage[]>(`${C}/pages`, { query });
export const getPage = (id: string) => request<CmsPage>(`${C}/pages/${id}`);
export const createPage = (data: object) => request<CmsPage>(`${C}/pages`, { method: "POST", body: data });
export const updatePage = (id: string, data: object) =>
  request<CmsPage>(`${C}/pages/${id}`, { method: "PATCH", body: data });
export const deletePage = (id: string) => request<null>(`${C}/pages/${id}`, { method: "DELETE" });

type Kind = "pages" | "faqs" | "blog";
export const publish = (kind: Kind, id: string, publishAt: string | null) =>
  request<unknown>(`${C}/${kind}/${id}/publish`, { method: "POST", body: { publish_at: publishAt } });
export const unpublish = (kind: Kind, id: string) =>
  request<unknown>(`${C}/${kind}/${id}/unpublish`, { method: "POST" });

export const listFaqCategories = () => request<FaqCategory[]>(`${C}/faq-categories`);
export const createFaqCategory = (data: object) =>
  request<FaqCategory>(`${C}/faq-categories`, { method: "POST", body: data });
export const updateFaqCategory = (id: string, data: object) =>
  request<FaqCategory>(`${C}/faq-categories/${id}`, { method: "PATCH", body: data });
export const deleteFaqCategory = (id: string) => request<null>(`${C}/faq-categories/${id}`, { method: "DELETE" });
export const reorderFaqCategories = (ids: string[]) =>
  request<FaqCategory[]>(`${C}/faq-categories/order`, { method: "PUT", body: { ids } });
export const listFaqs = (categoryId?: string) => request<Faq[]>(`${C}/faqs`, { query: { category_id: categoryId } });
export const createFaq = (data: object) => request<Faq>(`${C}/faqs`, { method: "POST", body: data });
export const updateFaq = (id: string, data: object) => request<Faq>(`${C}/faqs/${id}`, { method: "PATCH", body: data });
export const deleteFaq = (id: string) => request<null>(`${C}/faqs/${id}`, { method: "DELETE" });
export const reorderFaqs = (categoryId: string, ids: string[]) =>
  request<Faq[]>(`${C}/faq-categories/${categoryId}/faqs/order`, { method: "PUT", body: { ids } });

export const listNavigation = (menu: string) => request<NavItem[]>(`${C}/navigation`, { query: { menu } });
export const createNavItem = (data: object) => request<NavItem>(`${C}/navigation`, { method: "POST", body: data });
export const updateNavItem = (id: string, data: object) =>
  request<NavItem>(`${C}/navigation/${id}`, { method: "PATCH", body: data });
export const deleteNavItem = (id: string) => request<null>(`${C}/navigation/${id}`, { method: "DELETE" });
export const reorderNav = (menu: string, ids: string[]) =>
  request<NavItem[]>(`${C}/navigation/${menu}/order`, { method: "PUT", body: { ids } });

export const listPosts = (query: object = {}) => request<BlogPost[]>(`${C}/blog`, { query });
export const getPost = (id: string) => request<BlogPost>(`${C}/blog/${id}`);
export const createPost = (data: object) => request<BlogPost>(`${C}/blog`, { method: "POST", body: data });
export const updatePost = (id: string, data: object) =>
  request<BlogPost>(`${C}/blog/${id}`, { method: "PATCH", body: data });
export const deletePost = (id: string) => request<null>(`${C}/blog/${id}`, { method: "DELETE" });
