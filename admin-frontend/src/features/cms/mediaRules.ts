// What the backend accepts for CMS images (app/cms + core storage settings).
export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const IMAGE_ACCEPT = IMAGE_TYPES.join(",");
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

/** A friendly reason a file can't be used, or null when it's fine. */
export function checkImageFile(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return `"${file.name}" isn't a JPEG, PNG or WebP picture.`;
  if (file.size > MAX_IMAGE_BYTES) return `"${file.name}" is larger than 5 MB — please use a smaller picture.`;
  return null;
}
