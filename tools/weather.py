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
import urllib.request

LAT, LNG = 26.312, 50.625          # Diyar Al Muharraq
TZ = dt.timezone(dt.timedelta(hours=3), 'AST')   # Bahrain, no DST
STATION = 'OBBI'
UA = 'A92BM-weather-panel (https://basilalmejna.github.io/a92bm-globe/)'
ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
METAR_STALE_MIN = 90
SLOTS, STEP_H = 8, 3                # forecast strip: 8 slots, every 3 hours

METAR_URL = f'https://aviationweather.gov/api/data/metar?ids={STATION}&format=json&hours=3'
OM_URL = ('https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}'
          '&hourly=temperature_2m,weather_code&daily=sunrise,sunset'
          '&timezone=Asia%2FBahrain&forecast_days=3').format(LAT, LNG)


def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


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


def render(metar, om, now):
    sun = Sun(om)
    ic = Icons()
    W, H = 640, 400
    body = []
    body.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#000030" stroke="#31336e"/>')
    body.append(text(24, 32, 'WEATHER · DIYAR AL MUHARRAQ', 11, '#17f9da', extra=' letter-spacing="3.5"'))

    # ---- now
    if metar:
        obs = dt.datetime.fromtimestamp(metar['obsTime'], dt.timezone.utc)
        day = sun.is_day(obs)
        icon, label = metar_icon(metar, day)
        age = (now - obs).total_seconds() / 60
        stale = age > METAR_STALE_MIN
        source = f'Observed {obs.astimezone(TZ):%H:%M} AST at Bahrain Intl ({STATION})'
        t, td = metar.get('temp'), metar.get('dewp')
        rh = rel_humidity(t, td)
        wspd, wgst = metar.get('wspd'), metar.get('wgst')
        wind = 'Calm' if wspd == 0 else (
            f"{compass(metar.get('wdir'))} {round(wspd * 1.852)} km/h" + (f', gusts {round(wgst * 1.852)}' if wgst else '')
            if wspd is not None else '—')
        vis = visibility_km(metar.get('visib'))
    elif om:
        day = sun.is_day(now)
        idx = om['hourly']['time'].index(now.astimezone(TZ).strftime('%Y-%m-%dT%H:00'))
        icon, label = wmo_icon(om['hourly']['weather_code'][idx], day)
        t, rh, wind, vis, stale = om['hourly']['temperature_2m'][idx], None, '—', None, False
        source = 'Model forecast (no airport observation available)'
    else:
        day, icon, label, t, rh, wind, vis, stale = sun.is_day(now), 'not-available', 'Unavailable', None, None, '—', None, False
        source = 'No current weather data available'

    body.append(ic.use(icon, 18, 44, 132))
    body.append(text(160, 82, label, 26, '#ffffff', weight='800'))
    body.append(text(160, 128, f'{round(t)}°C' if t is not None else '— °C', 42, '#17f9da', weight='800'))
    details = [f'Humidity {rh}%' if rh is not None else None, f'Wind {wind}', f'Visibility {vis}' if vis else None]
    body.append(text(160, 154, '  ·  '.join(d for d in details if d), 13, '#e9eaf5'))
    body.append(text(160, 176, source, 11, '#a9abd0'))
    if stale:
        body.append('<rect x="520" y="62" width="96" height="24" rx="12" fill="#c0106f"/>')
        body.append(text(568, 79, 'STALE DATA', 11, '#ffffff', 'middle', 'bold', ' letter-spacing="1"'))
    rise, sett = sun.times(now)
    body.append(ic.use('sunrise', 506, 110, 40) + text(546, 136, f'{rise:%H:%M}', 13, '#e9eaf5'))
    body.append(ic.use('sunset', 506, 146, 40) + text(546, 172, f'{sett:%H:%M}', 13, '#e9eaf5'))

    # ---- forecast strip
    body.append('<rect x="40" y="196" width="560" height="2" rx="1" fill="url(#line)" opacity="0.8"/>')
    body.append(text(24, 222, f'NEXT {SLOTS * STEP_H} HOURS', 11, '#17f9da', extra=' letter-spacing="3.5"'))
    cw = (W - 32) / SLOTS
    slots = []
    if om:
        times = om['hourly']['time']
        start = (now.astimezone(TZ) + dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:00')
        i = times.index(start) if start in times else None
        if i is not None:
            for k in range(SLOTS):
                j = i + k * STEP_H
                if j >= len(times):
                    break
                vt = dt.datetime.fromisoformat(times[j]).replace(tzinfo=TZ)
                slots.append((vt, om['hourly']['weather_code'][j], om['hourly']['temperature_2m'][j]))
    if slots:
        for k, (vt, code, temp) in enumerate(slots):
            cx = 16 + cw * k + cw / 2
            fi, fl = wmo_icon(code, sun.is_day(vt))
            body.append(text(cx, 246, f'{vt:%H:%M}', 12, '#a9abd0', 'middle'))
            body.append(ic.use(fi, cx - 30, 252, 60))
            body.append(text(cx, 326, fl, 11, '#e9eaf5', 'middle'))
            body.append(text(cx, 348, f'{round(temp)}°C' if temp is not None else '—', 15, '#ffffff', 'middle', 'bold'))
    else:
        body.append(ic.use('not-available', W / 2 - 110, 240, 70))
        body.append(text(W / 2 - 30, 284, 'Forecast unavailable', 16, '#e9eaf5'))

    body.append(text(W / 2, H - 28, f'Updated {now.astimezone(TZ):%d %b %Y %H:%M} AST (Bahrain time)  ·  reload the page for the latest',
                     11, '#a9abd0', 'middle'))
    body.append(text(W / 2, H - 12, 'Data: METAR OBBI via NOAA aviationweather.gov · Forecast: Open-Meteo.com (CC BY 4.0) · Icons: Meteocons (MIT)',
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
    open(out, 'w').write(render(metar, om, now))
    print('wrote', out, '| now:', metar_icon(metar, Sun(om).is_day(now)) if metar else 'no METAR')


if __name__ == '__main__':
    main()
