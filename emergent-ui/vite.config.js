// Az Emergentben készült Szelvénymodell felülete (a futó előnézet forrástérképéből visszaállítva),
// a betting-agent szervere szolgálja ki a /emergent/ alatt; az /emergent/api/* kéréseket az
// Emergent-szerverhez továbbítja.
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/emergent/",
  plugins: [react({ include: /\.(js|jsx)$/ })],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  esbuild: { loader: "jsx", include: /src\/.*\.jsx?$/, exclude: [] },
  optimizeDeps: { esbuildOptions: { loader: { ".js": "jsx" } } },
  define: { "process.env.REACT_APP_BACKEND_URL": JSON.stringify("/emergent") },
  build: { outDir: "../betting-agent/static/emergent", emptyOutDir: true, sourcemap: false },
});
