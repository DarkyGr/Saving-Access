import { useMemo } from "react";
import qrcode from "qrcode-generator";

/**
 * A QR code drawn as SVG squares (task 37.5). Always dark on white so phone
 * cameras read it in the dark theme too.
 */
export default function QrCode({ value, label, size = 192 }: { value: string; label: string; size?: number }) {
  const cells = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(value);
    qr.make();
    const count = qr.getModuleCount();
    const dark: string[] = [];
    for (let row = 0; row < count; row++) {
      for (let col = 0; col < count; col++) {
        if (qr.isDark(row, col)) dark.push(`M${col + 4} ${row + 4}h1v1h-1z`);
      }
    }
    return { count, path: dark.join("") };
  }, [value]);

  const box = cells.count + 8; // 4-module quiet zone on each side
  return (
    <svg
      role="img"
      aria-label={label}
      width={size}
      height={size}
      viewBox={`0 0 ${box} ${box}`}
      shapeRendering="crispEdges"
      style={{ background: "#ffffff" }}
    >
      <rect width={box} height={box} fill="#ffffff" />
      <path d={cells.path} fill="#000000" />
    </svg>
  );
}
