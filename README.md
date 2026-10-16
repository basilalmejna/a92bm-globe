# a92bm-globe
Interactive globe of A92BM's LoTW-confirmed QSOs

## What is here

- `index.html`, `qsos.js` – interactive globe of every QSO in A92BM's log (globe.gl).
- `stats.svg` – log statistics shown on qrz.com/db/A92BM. `qsos.js` and `stats.svg` are pushed from the station PC when new QSOs are logged.
- `weather.svg` – weather panel for Diyar Al Muharraq, rebuilt every 30 minutes by `.github/workflows/pages.yml` running `tools/weather.py`.

Weather data: METAR for Bahrain International (OBBI) from NOAA aviationweather.gov; forecast, sunrise and sunset from [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0).
Icons: [Meteocons](https://github.com/basmilius/weather-icons) by Bas Milius, MIT licence (`tools/icons/LICENSE-meteocons.txt`).
