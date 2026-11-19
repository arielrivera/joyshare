#!/usr/bin/env bash
# Renders docs/infographic.html to docs/infographic.png, the picture GitHub shows in docs/INFOGRAPHIC.md.
# Run it after editing the infographic:  tools/render_infographic.sh
# Needs Google Chrome (or Chromium). Set CHROME=/path/to/chrome to use another one.
set -euo pipefail
cd "$(dirname "$0")/.."

WIDTH=1200   # CSS pixels; the page lays out its four "Where things run" cards side by side from 860 up
SCALE=2      # sharp on high-density screens

CHROME="${CHROME:-}"
if [[ -z "$CHROME" ]]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium" \
           "$(command -v google-chrome || true)" "$(command -v chromium || true)" "$(command -v chromium-browser || true)"; do
    [[ -n "$c" && -x "$c" ]] && { CHROME="$c"; break; }
  done
fi
[[ -n "$CHROME" ]] || { echo "Error: Chrome or Chromium is needed. Set CHROME=/path/to/chrome." >&2; exit 1; }

page="$(pwd)/docs/infographic.html"
measure="$(pwd)/docs/.infographic-measure.html"   # next to the page, so its pictures load the same way
trap 'rm -f "$measure"' EXIT

# 1. Measure the page's full height at this width (fonts and pictures loaded), in a throwaway copy.
sed 's#</body>#<script>addEventListener("load",()=>setTimeout(()=>{document.body.dataset.height=document.documentElement.scrollHeight},800))</script></body>#' \
  "$page" > "$measure"
height="$("$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-color-profile=srgb \
  --window-size="$WIDTH,1000" --virtual-time-budget=8000 --dump-dom "file://$measure" 2>/dev/null \
  | grep -o 'data-height="[0-9]*"' | grep -o '[0-9]*' || true)"
[[ -n "$height" ]] || { echo "Error: couldn't measure the page." >&2; exit 1; }

# 2. Take the picture at exactly that size, in the light look.
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-color-profile=srgb \
  --blink-settings=preferredColorScheme=1 --force-device-scale-factor="$SCALE" \
  --window-size="$WIDTH,$height" --virtual-time-budget=8000 \
  --screenshot="$(pwd)/docs/infographic.png" "file://$page" >/dev/null 2>&1

echo "Saved docs/infographic.png ($WIDTH x $height, at ${SCALE}x)."
