import { defineConfig } from 'vite'
import type { Plugin } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * `/` is the landing page in development too, as it is in production.
 *
 * In production Traefik rewrites `/` to /landing/index.html (router sies-root).
 * The dev stack sends every unclaimed path to this server, and Vite answers
 * anything outside `base` with "The server is configured with a public base URL
 * of /myadmin/ — did you mean to visit /myadmin/ instead?". Rewriting here,
 * before Vite's own middleware, makes localhost:5000/ show the page the domain
 * will show — served from public/, exactly as the build ships it.
 */
function landingAtRoot(): Plugin {
  return {
    name: 'sies-landing-at-root',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (req.url === '/' || req.url?.startsWith('/?')) {
          req.url = '/myadmin/landing/index.html'
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), landingAtRoot()],
  // Must match <BrowserRouter basename="/myadmin">. Every hashed asset is then
  // requested as /myadmin/assets/…, which is the path Traefik routes to this
  // container — a bare '/' base works on a direct port and 404s through the
  // proxy, which is the only way anyone ever reaches it.
  base: '/myadmin/',
  server: {
    port: 5173,
    host: '0.0.0.0',
    // Vite refuses a request whose Host header it does not recognise. Behind
    // Traefik the browser's Host is localhost:5000 in dev and the real domain
    // in production preview — never this container — so without this the dev
    // server answers 403 to every page. Only the dev server has this check;
    // the built SPA has none.
    allowedHosts: true,
    // The HMR websocket is proxied too, so the client must be told the port
    // the BROWSER reached us on rather than the one we listen on.
    hmr: { clientPort: 5000 },
    // Bind-mounted source across the Docker VM boundary does not deliver
    // inotify events, so a save would never trigger a reload.
    watch: { usePolling: true },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
