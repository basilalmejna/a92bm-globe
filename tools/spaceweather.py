#!/usr/bin/env python3
"""Render the space-weather / HF conditions panel (spaceweather.svg) from NOAA SWPC.

Every value carries its own observation time; values past their expected
publishing interval are marked STALE, and missing values say Unavailable.

  spaceweather.py OUT.svg
"""
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request

B = 'https://services.swpc.noaa.gov'
UA = 'A92BM-space-weather-panel (https://basilalmejna.github.io/a92bm-globe/)'
TZ = dt.timezone(dt.timedelta(hours=3), 'AST')
UTC = dt.timezone.utc


def get(path, as_json=True, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(B + path, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = r.read().decode('utf-8', 'replace')
            return json.loads(data) if as_json else data
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(10 * (attempt + 1))


def ts(s):
    s = s.replace('Z', '')
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def safe(fn):
    try:
        return fn()
    except Exception as e:  # one failed feed must not blank the whole panel
        print(fn.__name__, 'unavailable:', e)
        return None


# ------------------------------------------------------------------ readers
def sfi():
    r = get('/products/summary/10cm-flux.json')[0]
    return {'value': int(round(float(r['flux']))), 'time': ts(r['time_tag'])}


def ssn():
    rows = [l.split() for l in get('/text/daily-solar-indices.txt', False).splitlines()
            if re.match(r'^\d{4} \d\d \d\d', l)]
    y, m, d, _flux, n = rows[-1][:5]
    return {'value': int(n), 'time': dt.datetime(int(y), int(m), int(d), tzinfo=UTC)}


def kp():
    r = get('/products/noaa-planetary-k-index.json')[-1]
    return {'value': float(r['Kp']), 'time': ts(r['time_tag'])}


def ap():
    for line in reversed(get('/text/daily-geomagnetic-indices.txt', False).splitlines()):
        if not re.match(r'^\d{4} \d\d \d\d', line):
            continue
        tok = line.split()
        if tok[-1] == '-1.00':
            continue  # today's day is not complete yet
        y, m, d = map(int, line[:10].split())
        return {'value': int(tok[-9]), 'time': dt.datetime(y, m, d, tzinfo=UTC)}


def flare():
    r = get('/json/goes/primary/xray-flares-latest.json')[0]
    return {'value': r['max_class'], 'time': ts(r['max_time']), 'now': r.get('current_class')}


def scales():
    r = get('/products/noaa-scales.json')['0']
    return {'R': r['R'], 'S': r['S'], 'G': r['G'], 'time': ts(f"{r['DateStamp']}T{r['TimeStamp']}")}


def solar_wind():
    rows = [r for r in get('/json/rtsw/rtsw_wind_1m.json') if r.get('active') and r.get('proton_speed') is not None]
    r = max(rows, key=lambda r: r['time_tag'])
    return {'value': round(r['proton_speed']), 'time': ts(r['time_tag'])}


def bz():
    rows = [r for r in get('/json/rtsw/rtsw_mag_1m.json') if r.get('active') and r.get('bz_gsm') is not None]
    r = max(rows, key=lambda r: r['time_tag'])
    return {'value': r['bz_gsm'], 'time': ts(r['time_tag'])}


# ------------------------------------------------------------------ render
GOOD, WARN, SERIOUS, CRIT = '#2bd67b', '#f5c518', '#ff8a3d', '#ff4d6d'


def kp_level(item):
    v = item["value"]
    if v >= 7:
        return CRIT, f'Storm G{min(5, int(v) - 4)}'
    if v >= 5:
        return SERIOUS, f'Storm G{int(v) - 4}'
    if v >= 4:
        return WARN, 'Active'
    return GOOD, 'Quiet' if v < 3 else 'Unsettled'


def text(x, y, s, size=13, fill='#e9eaf5', anchor='middle', weight='normal', extra=''):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}"{extra}>{html.escape(str(s))}</text>')


def render(d, now):
    W, H = 640, 330
    out = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#000030" stroke="#31336e"/>',
           text(24, 32, 'SPACE WEATHER · HF PROPAGATION', 11, '#17f9da', 'start', extra=' letter-spacing="3.5"')]

    def tile(col, row, name, item, fmt, max_age_h, note_fmt, status=None):
        tw = (W - 32) / 4
        cx = 16 + tw * col + tw / 2
        y0 = 52 + row * 118
        out.append(f'<rect x="{cx - tw / 2 + 5:.1f}" y="{y0}" width="{tw - 10:.1f}" height="106" rx="10" fill="#151541" stroke="#31336e"/>')
        out.append(text(cx, y0 + 22, name, 10, '#a9abd0', extra=' letter-spacing="1.5"'))
        if not item:
            out.append(text(cx, y0 + 58, 'Unavailable', 16, '#7f82b0', weight='bold'))
            return
        out.append(text(cx, y0 + 60, fmt(item), 26, '#17f9da', weight='800'))
        note = note_fmt(item)
        if status:
            color, word = status(item)
            out.append(f'<circle cx="{cx - 4 - len(word) * 3.2:.1f}" cy="{y0 + 77}" r="4" fill="{color}"/>')
            out.append(text(cx + 6, y0 + 81, word, 11, '#e9eaf5', weight='bold'))
        stale = (now - item['time']).total_seconds() / 3600 > max_age_h
        out.append(text(cx, y0 + 97, ('STALE · ' if stale else '') + note, 9.5, '#ff4d6d' if stale else '#7f82b0'))

    hm = lambda t: f'{t:%H:%M} UTC'
    day = lambda t: f'{t:%d %b} UTC'
    tile(0, 0, 'SOLAR FLUX (SFI)', d['sfi'], lambda i: i['value'], 30, lambda i: f"10.7 cm · {i['time']:%d %b %H:%M} UTC")
    tile(1, 0, 'SUNSPOT NUMBER', d['ssn'], lambda i: i['value'], 54, lambda i: f"observed {day(i['time'])}")
    tile(2, 0, 'PLANETARY Kp', d['kp'], lambda i: f"{i['value']:.2f}".rstrip('0').rstrip('.'), 6,
         lambda i: f"{i['time']:%H}–{(i['time'] + dt.timedelta(hours=3)):%H} UTC {i['time']:%d %b}", kp_level)
    tile(3, 0, 'DAILY Ap', d['ap'], lambda i: i['value'], 54, lambda i: day(i['time']))
    tile(0, 1, 'LATEST FLARE', d['flare'], lambda i: i['value'], 24, lambda i: f"peak {i['time']:%d %b %H:%M} UTC")
    tile(1, 1, 'SOLAR WIND', d['wind'], lambda i: f"{i['value']} km/s", 0.5, lambda i: hm(i['time']),
         lambda i: (GOOD, 'Normal') if i['value'] < 500 else (WARN, 'Elevated') if i['value'] < 700 else (SERIOUS, 'High'))
    tile(2, 1, 'IMF Bz', d['bz'], lambda i: f"{i['value']:+.1f} nT", 0.5, lambda i: hm(i['time']),
         lambda i: (GOOD, 'North') if i['value'] >= 0 else (WARN, 'South') if i['value'] > -10 else (SERIOUS, 'Strong south'))
    sc = d['scales']
    tile(3, 1, 'NOAA SCALES', sc,
         lambda i: f"R{i['R']['Scale']} S{i['S']['Scale']} G{i['G']['Scale']}", 3, lambda i: hm(i['time']),
         lambda i: (GOOD, 'No alerts') if all(i[k]['Scale'] in ('0', None) for k in 'RSG') else (SERIOUS, 'Storm alert'))

    local = now.astimezone(TZ)
    out.append(text(W / 2, H - 30, f'As of {now:%H:%M} UTC  ·  {local:%H:%M} Bahrain (UTC+3), {local:%a %d %b %Y}  ·  updated hourly, reload for the latest',
                    11, '#a9abd0'))
    out.append(text(W / 2, H - 13, 'Data: NOAA Space Weather Prediction Center (SWPC) · GOES X-ray · real-time solar wind (DSCOVR/ACE/IMAP)',
                    9.5, '#7f82b0'))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            'font-family="Segoe UI, Arial, Helvetica, sans-serif">' + '\n'.join(out) + '</svg>\n')


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'spaceweather.svg'
    d = {'sfi': safe(sfi), 'ssn': safe(ssn), 'kp': safe(kp), 'ap': safe(ap), 'flare': safe(flare),
         'scales': safe(scales), 'wind': safe(solar_wind), 'bz': safe(bz)}
    open(out, 'w').write(render(d, dt.datetime.now(UTC)))
    print('wrote', out, {k: (v or {}).get('value') for k, v in d.items()})


if __name__ == '__main__':
    main()
