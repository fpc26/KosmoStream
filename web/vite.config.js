import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte()],
  base: '/KosmoStream/',
  server: {
    fs: {
      // Allow importing JSON assets from the workspace root (e.g. bd_calendar_2026.json)
      allow: ['..'],
    },
  },
})
