#!/usr/bin/env python3
"""Render the A92BM weather panel (weather.svg) for Diyar Al Muharraq, Bahrain.

Condition data:
  now       METAR from Bahrain International Airport (OBBI), aviationweather.gov
  forecast  Open-Meteo hourly WMO weather codes, sunrise and sunset (CC BY 4.0)
Icon artwork:
  Meteocons 2.0.0 by Bas Milius (MIT), in tools/icons

Icons are chosen only from reported condition codes. Missing or unknown codes
show the "not-available" icon labelled "Unavailable"; old observations are
marked STALE. Day/night variants use local sunrise and sunset for each time.

  weather.py OUT.svg
"""
import base64
import datetime as dt
import html
import json
import math
import os
import re
import sys
import time
import urllib.request

LAT, LNG = 26.30, 50.62            # Diyar Al Muharraq area (approximate, no home location)
TZ = dt.timezone(dt.timedelta(hours=3), 'AST')   # Bahrain, no DST
STATION = 'OBBI'
UA = 'A92BM-weather-panel (https://basilalmejna.github.io/a92bm-globe/)'
ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
METAR_STALE_MIN = 90
SLOTS, STEP_H = 8, 3                # forecast strip: 8 slots, every 3 hours
PANEL_W, PANEL_H = 640, 540         # every panel on the QRZ card shares this size

METAR_URL = f'https://aviationweather.gov/api/data/metar?ids={STATION}&format=json&hours=3'
OM_URL = ('https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}'
          '&current=temperature_2m,relative_humidity_2m,dew_point_2m,pressure_msl,wind_speed_10m,'
          'wind_direction_10m,wind_gusts_10m,weather_code,visibility'
          '&hourly=temperature_2m,weather_code,precipitation,precipitation_probability&daily=sunrise,sunset'
          '&timezone=Asia%2FBahrain&wind_speed_unit=kmh&forecast_days=3').format(LAT, LNG)
AQ_URL = ('https://air-quality-api.open-meteo.com/v1/air-quality?latitude={}&longitude={}'
          '&current=dust&timezone=Asia%2FBahrain').format(LAT, LNG)


def fetch_json(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))


# ---------------------------------------------------------------- sun times
def solar_sun_times(day):
    """NOAA sunrise/sunset approximation, used if Open-Meteo is unavailable."""
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    lat = math.radians(LAT)
    ha = math.degrees(math.acos(math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl))
                                - math.tan(lat) * math.tan(decl)))
    base = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    rise = base + dt.timedelta(minutes=720 - 4 * (LNG + ha) - eqt)
    sett = base + dt.timedelta(minutes=720 - 4 * (LNG - ha) - eqt)
    return rise.astimezone(TZ), sett.astimezone(TZ)


class Sun:
    def __init__(self, om):
        self.days = {}
        if om:
            for d, r, s in zip(om['daily']['time'], om['daily']['sunrise'], om['daily']['sunset']):
                self.days[d] = (dt.datetime.fromisoformat(r).replace(tzinfo=TZ),
                                dt.datetime.fromisoformat(s).replace(tzinfo=TZ))

    def times(self, when):
        local = when.astimezone(TZ)
        return self.days.get(local.date().isoformat()) or solar_sun_times(local.date())

    def is_day(self, when):
        rise, sett = self.times(when)
        return rise <= when.astimezone(TZ) < sett


# ------------------------------------------------------------ condition maps
def dn(name, day):
    return f'{name}-{"day" if day else "night"}'


def wmo_icon(code, day):
    """Open-Meteo WMO weather code -> (icon, label). Unknown -> Unavailable."""
    c = code
    if c is None:
        return 'not-available', 'Unavailable'
    table = {
        0: (dn('clear', day), 'Clear'),
        1: (dn('partly-cloudy', day), 'Mainly clear'),
        2: (dn('partly-cloudy', day), 'Partly cloudy'),
        3: ('overcast', 'Overcast'),
        45: (dn('fog', day), 'Fog'), 48: (dn('fog', day), 'Rime fog'),
        51: ('drizzle', 'Light drizzle'), 53: ('drizzle', 'Drizzle'), 55: ('drizzle', 'Heavy drizzle'),
        56: ('sleet', 'Freezing drizzle'), 57: ('sleet', 'Freezing drizzle'),
        61: ('rain', 'Light rain'), 63: ('rain', 'Rain'), 65: ('rain', 'Heavy rain'),
        66: ('sleet', 'Freezing rain'), 67: ('sleet', 'Freezing rain'),
        71: ('snow', 'Light snow'), 73: ('snow', 'Snow'), 75: ('snow', 'Heavy snow'), 77: ('snow', 'Snow grains'),
        80: (dn('partly-cloudy', day) + '-rain', 'Showers'), 81: (dn('partly-cloudy', day) + '-rain', 'Showers'),
        82: (dn('partly-cloudy', day) + '-rain', 'Heavy showers'),
        85: (dn('partly-cloudy', day) + '-snow', 'Snow showers'), 86: (dn('partly-cloudy', day) + '-snow', 'Snow showers'),
        95: (dn('thunderstorms', day) + '-rain', 'Thunderstorm'),
        96: (dn('thunderstorms', day) + '-rain', 'Thunderstorm, hail'),
        99: (dn('thunderstorms', day) + '-rain', 'Thunderstorm, hail'),
    }
    return table.get(int(c), ('not-available', 'Unavailable'))


def metar_icon(m, day):
    """METAR present weather and sky cover -> (icon, label), most significant first."""
    raw = m.get('rawOb') or ''
    wx = (m.get('wxString') or '').split()
    joined = ' '.join(wx)

    def has(*codes):
        return any(c in tok for tok in wx for c in codes)

    def intensity(label, tok_codes):
        tok = next((t for t in wx if any(c in t for c in tok_codes)), '')
        return ('Light ' + label.lower() if tok.startswith('-') else
                'Heavy ' + label.lower() if tok.startswith('+') else label)

    if has('FC'):
        return 'tornado', 'Funnel cloud'
    if has('TS'):
        near = all(t.startswith('VC') for t in wx if 'TS' in t)
        return dn('thunderstorms', day) + '-rain', 'Thunderstorm nearby' if near else 'Thunderstorm'
    if has('SS', 'DS'):
        return 'dust-wind', intensity('Dust storm' if 'DS' in joined else 'Sandstorm', ['SS', 'DS'])
    if has('GR', 'GS'):
        return 'hail', 'Hail'
    if has('SN', 'SG'):
        return 'snow', intensity('Snow', ['SN', 'SG'])
    if has('FZRA', 'FZDZ', 'PL'):
        return 'sleet', 'Freezing rain'
    if has('SHRA'):
        return dn('partly-cloudy', day) + '-rain', intensity('Showers', ['SHRA'])
    if has('RA'):
        return 'rain', intensity('Rain', ['RA'])
    if has('DZ'):
        return 'drizzle', intensity('Drizzle', ['DZ'])
    if has('FG'):
        return dn('fog', day), 'Fog'
    if has('DU', 'SA', 'PO'):
        return 'dust', 'Blowing dust' if has('BLDU', 'BLSA') else 'Dust'
    if has('FU'):
        return 'smoke', 'Smoke'
    if has('HZ'):
        return dn('haze', day), 'Haze'
    if has('BR'):
        return 'mist', 'Mist'
    if wx and not all(t.startswith('VC') for t in wx):
        return 'not-available', 'Unavailable'   # reported but unrecognised
    covers = [c.get('cover') for c in (m.get('clouds') or [])]
    if 'OVC' in covers or 'VV' in covers:
        return 'overcast', 'Overcast'
    if 'BKN' in covers:
        return dn('overcast', day), 'Mostly cloudy'
    if 'SCT' in covers:
        return dn('partly-cloudy', day), 'Partly cloudy'
    if 'FEW' in covers:
        return dn('partly-cloudy', day), 'Mainly clear'
    if re.search(r'\b(CAVOK|NSC|SKC|CLR|NCD)\b', raw):
        return dn('clear', day), 'Clear'
    return 'not-available', 'Unavailable'


def compass(deg):
    if not isinstance(deg, (int, float)):
        return 'Variable'
    return ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW',
            'W', 'WNW', 'NW', 'NNW'][int((deg % 360) / 22.5 + 0.5) % 16]


def rel_humidity(t, td):
    if t is None or td is None:
        return None
    a, b = 17.625, 243.04
    return round(100 * math.exp(a * td / (b + td)) / math.exp(a * t / (b + t)))


def visibility_km(v):
    if v is None:
        return None
    s = str(v)
    if s.endswith('+'):
        return '10+ km'
    try:
        km = float(s) * 1.609
    except ValueError:
        return None
    return '10+ km' if km >= 9.95 else f'{km:.1f} km'


# --------------------------------------------------------------------- render
class Icons:
    def __init__(self):
        self.used = {}

    def use(self, name, x, y, size):
        if name not in self.used:
            path = os.path.join(ICONS, name + '.svg')
            if not os.path.exists(path):
                name = 'not-available'
                path = os.path.join(ICONS, name + '.svg')
            data = base64.b64encode(open(path, 'rb').read()).decode()
            self.used[name] = (f'<symbol id="i-{name}" viewBox="0 0 512 512"><image width="512" height="512" '
                               f'href="data:image/svg+xml;base64,{data}"/></symbol>')
        return f'<use href="#i-{name}" x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}"/>'

    def defs(self):
        return ''.join(self.used.values())


def text(x, y, s, size=13, fill='#e9eaf5', anchor='start', weight='normal', extra=''):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}"{extra}>{html.escape(str(s))}</text>')


def render(metar, om, aq, now):
    sun = Sun(om)
    ic = Icons()
    W, H = PANEL_W, PANEL_H
    cur = (om or {}).get('current') or {}
    body = []
    body.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#000030" stroke="#31336e"/>')
    body.append(text(24, 32, 'WEATHER · DIYAR AL MUHARRAQ AREA', 11, '#17f9da', extra=' letter-spacing="3.5"'))

    # ---- now: airport observation first, model as labelled fallback
    obs_parts = {}
    if metar:
        obs = dt.datetime.fromtimestamp(metar['obsTime'], dt.timezone.utc)
        day = sun.is_day(obs)
        icon, label = metar_icon(metar, day)
        stale = (now - obs).total_seconds() / 60 > METAR_STALE_MIN
        source = f'Observed {obs.astimezone(TZ):%H:%M} AST at Bahrain Intl ({STATION})'
        t, td = metar.get('temp'), metar.get('dewp')
        rh = rel_humidity(t, td)
        wspd, wgst = metar.get('wspd'), metar.get('wgst')
        wind = ('Calm' if wspd == 0 else f"{compass(metar.get('wdir'))} {round(wspd * 1.852)} km/h") if wspd is not None else '—'
        obs_parts = {'dew': td, 'qnh': metar.get('altim'), 'gust': round(wgst * 1.852) if wgst else None,
                     'vis': visibility_km(metar.get('visib'))}
    elif cur:
        day = bool(cur.get('is_day', sun.is_day(now)))
        icon, label = wmo_icon(cur.get('weather_code'), sun.is_day(now))
        t, rh, stale = cur.get('temperature_2m'), cur.get('relative_humidity_2m'), False
        wind = f"{compass(cur.get('wind_direction_10m'))} {round(cur['wind_speed_10m'])} km/h" if cur.get('wind_speed_10m') is not None else '—'
        source = f"Model estimate {dt.datetime.fromisoformat(cur['time']):%H:%M} AST (no airport observation)"
    else:
        icon, label, t, rh, wind, stale = 'not-available', 'Unavailable', None, None, '—', False
        source = 'No current weather data available'

    body.append(ic.use(icon, 18, 44, 132))
    body.append(text(160, 82, label, 26, '#ffffff', weight='800'))
    body.append(text(160, 128, f'{round(t)}°C' if t is not None else '— °C', 42, '#17f9da', weight='800'))
    body.append(text(160, 160, source, 11, '#a9abd0'))
    if stale:
        body.append('<rect x="520" y="62" width="96" height="24" rx="12" fill="#c0106f"/>')
        body.append(text(568, 79, 'STALE DATA', 11, '#ffffff', 'middle', 'bold', ' letter-spacing="1"'))
    rise, sett = sun.times(now)
    body.append(ic.use('sunrise', 506, 110, 40) + text(546, 136, f'{rise:%H:%M}', 13, '#e9eaf5'))
    body.append(ic.use('sunset', 506, 146, 40) + text(546, 172, f'{sett:%H:%M}', 13, '#e9eaf5'))

    # ---- detail tiles: observed where the airport reports it, model otherwise (labelled)
    def pick(obs_val, model_val, fmt):
        if obs_val is not None:
            return fmt(obs_val), 'observed'
        if model_val is not None:
            return fmt(model_val), 'model'
        return 'Unavailable', ''
    hourly = (om or {}).get('hourly') or {}
    times = hourly.get('time') or []
    nxt = (now.astimezone(TZ) + dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:00')
    i0 = times.index(nxt) if nxt in times else None
    rain24 = prob24 = None
    if i0 is not None:
        win = range(i0, min(i0 + 24, len(times)))
        rain24 = sum(hourly['precipitation'][j] or 0 for j in win)
        prob24 = max((hourly['precipitation_probability'][j] or 0) for j in win)
    dust = ((aq or {}).get('current') or {}).get('dust')
    tiles = [
        ('DEW POINT',) + pick(obs_parts.get('dew'), cur.get('dew_point_2m'), lambda v: f'{round(v)}°C'),
        ('PRESSURE',) + pick(obs_parts.get('qnh'), cur.get('pressure_msl'), lambda v: f'{round(v)} hPa'),
        ('GUSTS',) + pick(obs_parts.get('gust'), cur.get('wind_gusts_10m'), lambda v: f'{round(v)} km/h'),
        ('VISIBILITY',) + pick(obs_parts.get('vis'), cur.get('visibility'),
                               lambda v: v if isinstance(v, str) else ('10+ km' if v >= 10000 else f'{v / 1000:.1f} km')),
        ('DUST',) + ((f'{round(dust)} µg/m³', 'CAMS model') if dust is not None else ('Unavailable', '')),
        ('RAIN, NEXT 24 H',) + ((f'{rain24:.1f} mm', f'max chance {prob24}%') if rain24 is not None else ('Unavailable', '')),
    ]
    tiles.insert(0, ('WIND', wind if wind != '\u2014' else 'Unavailable', 'observed' if metar else ('model' if cur else '')))
    tiles.insert(0, ('HUMIDITY', f'{rh}%' if rh is not None else 'Unavailable', 'observed' if metar else ('model' if cur else '')))
    tile_icons = {'HUMIDITY': 'humidity', 'WIND': 'wind', 'DEW POINT': 'thermometer-glass-celsius', 'PRESSURE': 'barometer',
                  'GUSTS': 'windsock', 'VISIBILITY': 'horizon', 'DUST': 'dust', 'RAIN, NEXT 24 H': 'raindrops'}
    body.append('<rect x="40" y="184" width="560" height="2" rx="1" fill="url(#line)" opacity="0.8"/>')
    tw = (W - 32) / 4
    for k, (name, value, note) in enumerate(tiles):
        x0, y0 = 16 + tw * (k % 4), 194 + 66 * (k // 4)
        body.append(f'<rect x="{x0 + 3:.1f}" y="{y0}" width="{tw - 6:.1f}" height="60" rx="9" fill="#151541" stroke="#31336e"/>')
        body.append(ic.use(tile_icons[name], x0 + 6, y0 + 8, 44))
        body.append(text(x0 + 52, y0 + 19, name, 8.5, '#a9abd0', extra=' letter-spacing="0.8"'))
        body.append(text(x0 + 52, y0 + 38, value, 14 if len(value) < 12 else 12, '#ffffff', weight='bold'))
        body.append(text(x0 + 52, y0 + 52, note, 9, '#7f82b0'))

    # ---- forecast strip, each icon for its own valid time
    body.append('<rect x="40" y="334" width="560" height="2" rx="1" fill="url(#line)" opacity="0.8"/>')
    body.append(text(24, 356, f'NEXT {SLOTS * STEP_H} HOURS · rain is the total for each {STEP_H}-hour period', 11, '#17f9da',
                     extra=' letter-spacing="1.5"'))
    cw = (W - 32) / SLOTS
    slots = []
    if i0 is not None:
        for k in range(SLOTS):
            j = i0 + k * STEP_H
            if j >= len(times):
                break
            vt = dt.datetime.fromisoformat(times[j]).replace(tzinfo=TZ)
            rain = sum(hourly['precipitation'][x] or 0 for x in range(j, min(j + STEP_H, len(times))))
            slots.append((vt, hourly['weather_code'][j], hourly['temperature_2m'][j], rain))
    if slots:
        for k, (vt, code, temp, rain) in enumerate(slots):
            cx = 16 + cw * k + cw / 2
            fi, fl = wmo_icon(code, sun.is_day(vt))
            body.append(text(cx, 378, f'{vt:%H:%M}', 12, '#a9abd0', 'middle'))
            body.append(ic.use(fi, cx - 28, 382, 56))
            body.append(text(cx, 452, fl, 11, '#e9eaf5', 'middle'))
            body.append(text(cx, 472, f'{round(temp)}°C' if temp is not None else '—', 15, '#ffffff', 'middle', 'bold'))
            body.append(text(cx, 490, f'{rain:.1f} mm', 11, '#7fb8ff', 'middle'))
    else:
        body.append(ic.use('not-available', W / 2 - 110, 384, 70))
        body.append(text(W / 2 - 30, 426, 'Forecast unavailable', 16, '#e9eaf5'))

    body.append(text(W / 2, H - 28, f'Updated {now.astimezone(TZ):%d %b %Y %H:%M} AST (Bahrain time)  ·  reload the page for the latest',
                     11, '#a9abd0', 'middle'))
    body.append(text(W / 2, H - 12, 'Observed: METAR OBBI (NOAA aviationweather.gov) · Forecast &amp; dust: Open-Meteo.com (CC BY 4.0) · Icons: Meteocons (MIT)'.replace('&amp;', '&'),
                     9.5, '#7f82b0', 'middle'))

    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            'font-family="Segoe UI, Arial, Helvetica, sans-serif">'
            '<defs><linearGradient id="line" x1="0" x2="1"><stop offset="0" stop-color="#33a0b8"/>'
            f'<stop offset="1" stop-color="#c0106f"/></linearGradient>{ic.defs()}</defs>')
    return head + '\n'.join(body) + '</svg>\n'


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'weather.svg'
    now = dt.datetime.now(dt.timezone.utc)
    metar = om = None
    try:
        data = fetch_json(METAR_URL)
        metar = max(data, key=lambda r: r['obsTime']) if data else None
    except Exception as e:  # keep going: the panel shows what is missing
        print('METAR unavailable:', e)
    try:
        om = fetch_json(OM_URL)
    except Exception as e:
        print('Open-Meteo unavailable:', e)
    aq = None
    try:
        aq = fetch_json(AQ_URL)
    except Exception as e:
        print('Open-Meteo air quality unavailable:', e)
    open(out, 'w').write(render(metar, om, aq, now))
    print('wrote', out, '| now:', metar_icon(metar, Sun(om).is_day(now)) if metar else 'no METAR')


if __name__ == '__main__':
    main()
