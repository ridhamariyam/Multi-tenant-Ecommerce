// Photos chosen while creating a product: uploaded first, then attached on create.
export const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

export interface NewImages {
  files: File[];
}

/** Why these photos can't be used, or null when they're fine. */
export function checkNewImages(files: File[]): string | null {
  if (files.length === 0) return "Add at least one photo.";
  const wrongType = files.find((f) => !IMAGE_TYPES.includes(f.type));
  if (wrongType) return `${wrongType.name}: only JPEG, PNG or WebP photos.`;
  const tooBig = files.find((f) => f.size > MAX_IMAGE_BYTES);
  if (tooBig) return `${tooBig.name} is larger than 5 MB.`;
  return null;
}
