import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(), // Podpora pro Tailwind CSS
  ],
  server: {
    host: '0.0.0.0', // Umožní přístup i z lokální sítě (mobil apod.)
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // Směrování požadavků na FastAPI backend
        changeOrigin: true,
        secure: false,
      },
    },
  },
});