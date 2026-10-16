#!/bin/sh
# Build every hosted panel. A failing panel is replaced by an "Unavailable"
# placeholder so the QRZ page never shows a broken image.
cd "$(dirname "$0")/.."
placeholder() {  # $1 file  $2 title
  printf '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="160" font-family="Segoe UI, Arial, sans-serif"><rect x="0.5" y="0.5" width="639" height="159" rx="14" fill="#000030" stroke="#31336e"/><text x="24" y="32" font-size="11" fill="#17f9da" letter-spacing="3.5">%s</text><text x="320" y="92" font-size="20" font-weight="bold" fill="#a9abd0" text-anchor="middle">Unavailable</text><text x="320" y="118" font-size="11" fill="#7f82b0" text-anchor="middle">Build failed at %s UTC; it will retry next hour</text></svg>\n' "$2" "$(date -u +%H:%M)" > "$1"
}
python3 tools/weather.py weather.svg           || placeholder weather.svg 'WEATHER'
python3 tools/spaceweather.py spaceweather.svg || placeholder spaceweather.svg 'SPACE WEATHER'
python3 tools/maps.py gulf gulfmap.png         || true
python3 tools/maps.py greyline greyline.png    || true
ls -la weather.svg spaceweather.svg gulfmap.png greyline.png
