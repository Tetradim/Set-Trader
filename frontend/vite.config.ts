import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

const backendUrl = process.env.VITE_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || 'http://127.0.0.1:8002'

export default defineConfig({
  plugins: [react()],
  envPrefix: ['VITE_', 'REACT_APP_'],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    // Cache-busting: use content hashes in filenames
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('recharts')) return 'charts';
          if (id.includes('@radix-ui')) return 'radix-ui';
          if (id.includes('lucide-react')) return 'icons';
          if (id.includes('framer-motion')) return 'motion';
          return 'vendor';
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 3000,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
