import { useEffect } from "react";
import { fontFamilyName } from "./libraryModel";

export function FontFaceStyle({ assetId, url }: { assetId: string; url: string }) {
  const family = fontFamilyName(assetId);

  useEffect(() => {
    const id = `font-face-${family}`;
    let style = document.getElementById(id) as HTMLStyleElement | null;
    if (!style) {
      style = document.createElement("style");
      style.id = id;
      document.head.appendChild(style);
    }
    style.textContent = `@font-face { font-family: "${family}"; src: url("${url}"); font-display: swap; }`;
  }, [family, url]);

  return null;
}
