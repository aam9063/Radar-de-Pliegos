#!/bin/sh
# Write the runtime configuration before nginx starts.
#
# The frontend needs to know where the API lives, and Vite bakes that value into
# the bundle at build time. Hosting platforms do not always pass build arguments
# the way Docker expects, so the address can also be provided at runtime: this
# script rewrites the small config file the page loads before the bundle.
#
# The official nginx entrypoint runs every executable script in
# /docker-entrypoint.d/ and then starts nginx, so this file must not start it.
set -e

CONFIG_FILE=/usr/share/nginx/html/config.js

if [ -n "${API_BASE_URL:-}" ]; then
  valor=$(printf '%s' "$API_BASE_URL" | tr -d '"\\' | tr -d '\n\r')
  printf 'window.__API_BASE__ = "%s";\n' "$valor" > "$CONFIG_FILE"
fi
