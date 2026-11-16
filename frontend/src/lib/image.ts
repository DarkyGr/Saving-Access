/** Largest picture accepted before resizing (the upload itself is ≤ 256 KB). */
export const PICTURE_MAX_INPUT_BYTES = 10 * 1024 * 1024;
export const PICTURE_TYPES = ["image/png", "image/jpeg", "image/webp"];
const SIZE = 256;

/**
 * Re-encode a picture in the browser (task 37.3): centre-cropped square of
 * 256 px as WebP (PNG where WebP encoding is missing). Re-encoding drops any
 * metadata or payload the original carried; the server still checks the
 * format from the bytes.
 */
export async function toSquarePicture(file: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas unavailable");
  ctx.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, SIZE, SIZE);
  bitmap.close?.();
  const encode = (type: string) =>
    new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.85));
  const webp = await encode("image/webp");
  if (webp && webp.type === "image/webp") return webp;
  const png = await encode("image/png");
  if (!png) throw new Error("Could not encode the picture");
  return png;
}
