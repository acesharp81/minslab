import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

const projectDir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/poc/field-inspection-platform/",
  envDir: path.resolve(projectDir, "../.."),
  plugins: [tsconfigPaths(), tailwindcss(), react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
