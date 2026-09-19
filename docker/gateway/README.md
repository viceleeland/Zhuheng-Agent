# Static release gateway

This gateway publishes only `work/web-release`, copied from a completed web production build. It does not mount the repository, the Vite server, credentials or backend source. The API stays on the existing Docker network.

Run `./scripts/start-public-gateway.ps1 -RefreshStatic` after a successful production build in `changwei-web-dev`. Without `-RefreshStatic`, the existing release is retained. `compose.public.yml` pins nginx stable-alpine-slim Linux/amd64 to `mirror.gcr.io/library/nginx@sha256:48d6de146898643e53f6795420bd79340125c264905f4e8855310edc4a7ff1c7`. This digest was first verified against the official Docker Hub registry and then fetched from Google Cloud Docker Hub cache without changing daemon settings. Local image size: 12,733,555 bytes. Provenance and runtime checks are in work/nginx-image-receipt.json and work/container-gateway-validation.json.

The only host binding is `127.0.0.1:5184`. This script does not enable a public tunnel or change Tailscale. Public endpoint authentication review and HTTPS publication must be completed separately.

`/api/` supports WebSocket Upgrade and unbuffered streaming responses (SSE); no API response cache. Backend authentication is still required. API docs/OpenAPI, dotfiles, source maps and Vite source/HMR paths are blocked. Object-storage URLs are not proxied by default. Access logs omit query strings and headers.

Stop only this gateway with `docker compose -p jiangqing-public -f compose.public.yml stop gateway`. Refreshing static files is not an atomic deployment; stop gateway first for release changes requiring a consistent asset set. Existing build assets remain until a deliberate release cleanup.

Public-route hardening: CLI device authorization, first-run initialization, unused OIDC login/callback/exchange, registration aliases and all MinIO paths return 404. Login metadata routes remain available. Login token requests are limited to 10/minute with burst 10; all clients share the proxy source address until a trustworthy ingress client-IP mechanism is verified. Incoming X-Forwarded-For is discarded and replaced with the immediate remote address.


## Project-local Windows fallback

When Docker Hub blob downloads fail, the verified official Windows package may be extracted at `work/nginx-windows/nginx-1.30.5`. Run `./scripts/start-public-gateway.ps1 -Windows` to generate equivalent restrictions and start a hidden project-local process (or gracefully reload its existing PID). This uses `127.0.0.1:5051` for API and binds `127.0.0.1:5184`. It installs no service and changes no global PATH. This fallback is for this development workstation, not the Linux customer image.

Official download: https://nginx.org/download/nginx-1.30.5.zip . Verified downloaded ZIP SHA256: `E5AFE28B6A50BEC92C478BFE1A4D3758206B80FB77159277BC5C4E88955C2A35` (local checksum, not a detached-signature verification).
