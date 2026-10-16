# a92bm-globe
Interactive globe of A92BM's LoTW-confirmed QSOs

## What is here

- `index.html`, `qsos.js` – interactive globe of every QSO in A92BM's log (globe.gl).
- `stats.svg` – log statistics shown on qrz.com/db/A92BM. `qsos.js` and `stats.svg` are pushed from the station PC when new QSOs are logged.
- `weather.svg`, `spaceweather.svg`, `gulfmap.png`, `greyline.png` – rebuilt every hour by `.github/workflows/pages.yml` (`tools/build.sh`). They are never committed.

Locations are approximate (Diyar Al Muharraq area, 26.30 N 50.62 E, grid LL56); no home location is shown.

## Sources and credits

- Observations: METAR for Bahrain International (OBBI), NOAA Aviation Weather Center – https://aviationweather.gov
- Forecast, sunrise/sunset, regional temperature and wind, dust: Open-Meteo – https://open-meteo.com (CC BY 4.0)
- Space weather: NOAA Space Weather Prediction Center – https://www.swpc.noaa.gov
- Weather icons: Meteocons by Bas Milius, MIT licence – https://github.com/basmilius/weather-icons (`tools/icons/LICENSE-meteocons.txt`)
- Coastlines, borders, places: Natural Earth (public domain) – https://www.naturalearthdata.com
- Earth images: NASA Blue Marble and Black Marble (public domain)
- Globe: globe.gl by Vasco Asturiano (MIT)
