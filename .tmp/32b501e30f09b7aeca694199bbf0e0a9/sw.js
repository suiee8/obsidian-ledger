import {clientsClaim as workbox_core_clientsClaim} from 'C:/Users/MADHVIK PANCHAL/obsidian-ledger/node_modules/.pnpm/workbox-core@7.4.1/node_modules/workbox-core/clientsClaim.mjs';
import {precacheAndRoute as workbox_precaching_precacheAndRoute} from 'C:/Users/MADHVIK PANCHAL/obsidian-ledger/node_modules/.pnpm/workbox-precaching@7.4.1/node_modules/workbox-precaching/precacheAndRoute.mjs';
import {cleanupOutdatedCaches as workbox_precaching_cleanupOutdatedCaches} from 'C:/Users/MADHVIK PANCHAL/obsidian-ledger/node_modules/.pnpm/workbox-precaching@7.4.1/node_modules/workbox-precaching/cleanupOutdatedCaches.mjs';
import {registerRoute as workbox_routing_registerRoute} from 'C:/Users/MADHVIK PANCHAL/obsidian-ledger/node_modules/.pnpm/workbox-routing@7.4.1/node_modules/workbox-routing/registerRoute.mjs';
import {NavigationRoute as workbox_routing_NavigationRoute} from 'C:/Users/MADHVIK PANCHAL/obsidian-ledger/node_modules/.pnpm/workbox-routing@7.4.1/node_modules/workbox-routing/NavigationRoute.mjs';
import {createHandlerBoundToURL as workbox_precaching_createHandlerBoundToURL} from 'C:/Users/MADHVIK PANCHAL/obsidian-ledger/node_modules/.pnpm/workbox-precaching@7.4.1/node_modules/workbox-precaching/createHandlerBoundToURL.mjs';/**
 * Welcome to your Workbox-powered service worker!
 *
 * You'll need to register this file in your web app.
 * See https://goo.gl/nhQhGp
 *
 * The rest of the code is auto-generated. Please don't update this file
 * directly; instead, make changes to your Workbox build configuration
 * and re-run your build process.
 * See https://goo.gl/2aRDsh
 */




self.skipWaiting();
workbox_core_clientsClaim();
/**
 * The precacheAndRoute() method efficiently caches and responds to
 * requests for URLs in the manifest.
 * See https://goo.gl/S9QRab
 */
workbox_precaching_precacheAndRoute([
  {
    "url": "registerSW.js",
    "revision": "1872c500de691dce40960bb85481de07"
  },
  {
    "url": "index.html",
    "revision": "1e3f31d2aafe4bceb27ddcca723e2323"
  },
  {
    "url": "assets/WaveGridBackground-84MmF5Vt.js",
    "revision": null
  },
  {
    "url": "assets/useChartPalette-DB61G2pm.js",
    "revision": null
  },
  {
    "url": "assets/useChart-D3dv60Al.js",
    "revision": null
  },
  {
    "url": "assets/Trades-9HuG57v5.js",
    "revision": null
  },
  {
    "url": "assets/tokens-CPuIj4Tp.js",
    "revision": null
  },
  {
    "url": "assets/Simulator-C2Joe2fL.js",
    "revision": null
  },
  {
    "url": "assets/Settings-Cs-JAhrv.js",
    "revision": null
  },
  {
    "url": "assets/ScreenStates-BPrqxqXW.js",
    "revision": null
  },
  {
    "url": "assets/SapphireAurora-BFtH68HA.js",
    "revision": null
  },
  {
    "url": "assets/Panel-Byx4XvVH.js",
    "revision": null
  },
  {
    "url": "assets/LineBands-BMqNy9w3.js",
    "revision": null
  },
  {
    "url": "assets/index-SeA4Zpvj.css",
    "revision": null
  },
  {
    "url": "assets/index-Ql65VjZe.js",
    "revision": null
  },
  {
    "url": "assets/Import-Cu6AO2UE.js",
    "revision": null
  },
  {
    "url": "assets/format-TmPMO_81.js",
    "revision": null
  },
  {
    "url": "assets/FindingChart-DiXRxCSu.js",
    "revision": null
  },
  {
    "url": "assets/EquityAurora-CwwdVEjU.js",
    "revision": null
  },
  {
    "url": "assets/Dashboard-BUDsrbUj.js",
    "revision": null
  },
  {
    "url": "assets/Behavior-UYi2aOQX.js",
    "revision": null
  },
  {
    "url": "assets/Bars-BdarEEXL.js",
    "revision": null
  },
  {
    "url": "assets/Availability-DKIviTtB.js",
    "revision": null
  },
  {
    "url": "assets/Analytics-Lmihx4Yr.js",
    "revision": null
  },
  {
    "url": "apple-touch-icon.png",
    "revision": "f500f52cca686bbd2fbc69e5cfa23f6d"
  },
  {
    "url": "favicon.svg",
    "revision": "f98db49810ce7bc0a7a4308a74606211"
  },
  {
    "url": "icon-192.png",
    "revision": "88dadf7de173f1a6defdd33fdf52fdf0"
  },
  {
    "url": "icon-512.png",
    "revision": "87d794892d425075138380c61d519fdb"
  },
  {
    "url": "manifest.webmanifest",
    "revision": "bda99cde0c18693eec30dd487d09c058"
  }
], {});
workbox_precaching_cleanupOutdatedCaches();workbox_routing_registerRoute(new workbox_routing_NavigationRoute(workbox_precaching_createHandlerBoundToURL("index.html")));


