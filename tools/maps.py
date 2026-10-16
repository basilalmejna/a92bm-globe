#!/usr/bin/env python3
"""Render the Gulf temperature/wind map and the grey-line (day/night) world map.

  maps.py gulf OUT.png       Open-Meteo model temperature and wind on a 1-degree grid
  maps.py greyline OUT.png   solar terminator over NASA day/night Earth images

Base layers in tools/basemap: Natural Earth land and borders (public domain),
NASA Blue Marble / Black Marble textures (public domain). No home marker is
drawn; Bahrain is shown at country level only.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, 'basemap')
UA = 'A92BM-maps (https://basilalmejna.github.io/a92bm-globe/)'
TZ = dt.timezone(dt.timedelta(hours=3), 'AST')
UTC = dt.timezone.utc
NAVY, PANEL, BORDER, MINT, MUTED, TEXT = (0, 0, 48), (21, 21, 65), (49, 51, 110), (23, 249, 218), (169, 171, 208), (233, 234, 245)


def font(size, bold=False):
    for p in (['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'] if bold else []) + \
             ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def frame(img, title, subtitle, footer, k=1):
    """Wrap a map in the page's card style with a title and a footer line (k = pixel scale)."""
    W = img.width
    out = Image.new('RGB', (W, img.height + 64 * k), NAVY)
    out.paste(img, (0, 44 * k))
    d = ImageDraw.Draw(out)
    d.text((14 * k, 8 * k), title, font=font(13 * k, True), fill=MINT)
    d.text((14 * k, 26 * k), subtitle, font=font(11 * k), fill=MUTED)
    d.text((W // 2, img.height + 54 * k), footer, font=font(10 * k), fill=(127, 130, 176), anchor='mm')
    return out


# ------------------------------------------------------------------ Gulf map
TEMP_STOPS = [(15, (43, 93, 170)), (22, (64, 170, 190)), (28, (225, 214, 160)), (34, (236, 140, 60)), (40, (200, 30, 90)), (46, (120, 0, 60))]


def temp_rgb(t):
    t = np.clip(t, TEMP_STOPS[0][0], TEMP_STOPS[-1][0])
    out = np.zeros(t.shape + (3,))
    for (t0, c0), (t1, c1) in zip(TEMP_STOPS, TEMP_STOPS[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[m][:, None]
        out[m] = np.array(c0) * (1 - f) + np.array(c1) * f
    return out


def gulf(path):
    meta = json.load(open(os.path.join(BASE, 'gulf.json')))
    W0, E0, S0, N0 = meta['bbox']
    W, H, kx, ky = meta['width'], meta['height'], meta['kx'], meta['ky']
    k = round(W / 640)                            # drawing scale (maps are rendered at 2x for wide screens)
    lons = np.arange(W0, E0 + 0.01, 1.0)
    lats = np.arange(S0, N0 + 0.51, 1.0)
    LA, LO = np.meshgrid(lats, lons, indexing='ij')
    url = ('https://api.open-meteo.com/v1/forecast?latitude=' + ','.join(f'{v:.2f}' for v in LA.ravel()) +
           '&longitude=' + ','.join(f'{v:.2f}' for v in LO.ravel()) +
           '&current=temperature_2m,wind_speed_10m,wind_direction_10m&wind_speed_unit=kmh&timezone=Asia%2FBahrain')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            data = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
    data = data if isinstance(data, list) else [data]
    T = np.array([p['current']['temperature_2m'] for p in data], float).reshape(LA.shape)
    SP = np.array([p['current']['wind_speed_10m'] for p in data], float).reshape(LA.shape)
    DIR = np.array([p['current']['wind_direction_10m'] for p in data], float).reshape(LA.shape)
    valid = dt.datetime.fromisoformat(data[0]['current']['time'])

    # bilinear temperature field over every pixel
    px_lon = W0 + (np.arange(W) + 0.5) / kx
    px_lat = N0 - (np.arange(H) + 0.5) / ky
    fi = np.clip((px_lat - lats[0]) / 1.0, 0, len(lats) - 1.001)
    fj = np.clip((px_lon - lons[0]) / 1.0, 0, len(lons) - 1.001)
    i0, j0 = fi.astype(int), fj.astype(int)
    di, dj = (fi - i0)[:, None], (fj - j0)[None, :]
    f = (T[i0][:, j0] * (1 - di) * (1 - dj) + T[i0 + 1][:, j0] * di * (1 - dj) +
         T[i0][:, j0 + 1] * (1 - di) * dj + T[i0 + 1][:, j0 + 1] * di * dj)
    rgb = temp_rgb(f)
    land = np.asarray(Image.open(os.path.join(BASE, 'gulf-land.png')).convert('L'), float)[:H, :W] / 255
    sea = rgb * 0.38 + np.array([14, 52, 120]) * 0.62    # water keeps a blue cast so land reads as land
    img = Image.fromarray(np.uint8(rgb * land[..., None] + sea * (1 - land[..., None])), 'RGB')
    d = ImageDraw.Draw(img, 'RGBA')
    coast = Image.open(os.path.join(BASE, 'gulf-land.png')).convert('L').filter(ImageFilter.FIND_EDGES)
    img.paste((255, 255, 255), (0, 0), coast.point(lambda v: min(255, v * 3)))
    borders = Image.open(os.path.join(BASE, 'gulf-borders.png')).convert('L')
    img.paste((40, 40, 70), (0, 0), borders.point(lambda v: int(v * 0.7)))

    def xy(lon, lat):
        return (lon - W0) * kx, (N0 - lat) * ky
    # wind arrows: point the way the wind blows, length grows with speed
    for a in range(LA.shape[0]):
        for b in range(LA.shape[1]):
            x, y = xy(LO[a, b], LA[a, b])
            if not (8 * k < x < W - 8 * k and 8 * k < y < H - 8 * k):
                continue
            to = math.radians(DIR[a, b] + 180)
            L = (8 + min(SP[a, b], 50) * 0.6) * k
            dx, dy = math.sin(to) * L, -math.cos(to) * L
            x0, y0, x1, y1 = x - dx / 2, y - dy / 2, x + dx / 2, y + dy / 2
            d.line([(x0, y0), (x1, y1)], fill=(0, 0, 40, 230), width=round(4 * k))
            d.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 255), width=round(2 * k))
            for s in (-1, 1):
                ang = to + math.pi + s * 0.5
                d.line([(x1, y1), (x1 + math.sin(ang) * 6 * k, y1 - math.cos(ang) * 6 * k)], fill=(255, 255, 255, 255), width=round(2 * k))
            if (a + b) % 2 == 0:
                d.text((x + 6 * k, y + 6 * k), f'{round(SP[a, b])}', font=font(round(10 * k)), fill=(0, 0, 40, 255))
    for c in meta['cities']:
        x, y = xy(c['lon'], c['lat'])
        d.ellipse([x - 2.5 * k, y - 2.5 * k, x + 2.5 * k, y + 2.5 * k], fill=(0, 0, 40, 255))
        right = x > W - 90 * k
        d.text((x - 5 * k if right else x + 5 * k, y - 6 * k), c['name'], font=font(round(11 * k), True), fill=(0, 0, 40, 255),
               stroke_width=round(2 * k), stroke_fill=(255, 255, 255, 200), anchor='ra' if right else 'la')
    # legend
    lg_w = round(260 * k)
    lx, ly = W - lg_w - 12 * k, H - 30 * k
    d.rounded_rectangle([lx - 8 * k, ly - 18 * k, lx + lg_w + 8 * k, ly + 22 * k], 8 * k, fill=(0, 0, 48, 210))
    ramp = temp_rgb(np.linspace(15, 46, lg_w))
    for c in range(lg_w):
        d.line([(lx + c, ly), (lx + c, ly + 8 * k)], fill=tuple(int(v) for v in ramp[c]))
    for tv in (15, 25, 35, 45):
        tx = lx + (tv - 15) / 31 * lg_w
        d.text((tx, ly + 10 * k), f'{tv}°', font=font(round(9 * k)), fill=TEXT, anchor='ma')
    d.text((lx, ly - 15 * k), '°C  ·  arrows: wind direction, numbers: km/h', font=font(round(9 * k)), fill=TEXT)
    out = frame(img, 'GULF · TEMPERATURE & WIND',
                f'Model analysis valid {valid:%d %b %H:%M} AST  ·  1° grid, interpolated  ·  updated hourly',
                'Data: Open-Meteo.com (CC BY 4.0)  ·  Coastlines & borders: Natural Earth (public domain)', k)
    out.save(path, optimize=True)
    print('wrote', path, out.size, f'T {T.min():.0f}-{T.max():.0f} C')


# ------------------------------------------------------------------ grey line
def sun_position(when):
    """Subsolar latitude/longitude (degrees) for a UTC datetime."""
    n = (when - dt.datetime(2000, 1, 1, 12, tzinfo=UTC)).total_seconds() / 86400
    L = math.radians((280.460 + 0.9856474 * n) % 360)
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    gmst = (280.46061837 + 360.98564736629 * n) % 360
    lon = (math.degrees(ra) - gmst + 540) % 360 - 180
    return math.degrees(dec), lon


def greyline(path, now=None):
    now = now or dt.datetime.now(UTC)
    W, H, k = 1280, 640, 2
    day = np.asarray(Image.open(os.path.join(BASE, 'earth-day-2048.jpg')).convert('RGB').resize((W, H), Image.LANCZOS), float)
    night = np.asarray(Image.open(os.path.join(BASE, 'earth-night-2048.jpg')).convert('RGB').resize((W, H), Image.LANCZOS), float)
    night = np.clip(night * 1.6 + 8, 0, 255)
    dec, slon = sun_position(now)
    lon = np.radians(-180 + (np.arange(W) + 0.5) * 360 / W)[None, :]
    lat = np.radians(90 - (np.arange(H) + 0.5) * 180 / H)[:, None]
    d, sl = math.radians(dec), math.radians(slon)
    alt = np.degrees(np.arcsin(np.sin(lat) * math.sin(d) + np.cos(lat) * math.cos(d) * np.cos(lon - sl)))
    w = np.clip((alt + 6) / 12, 0, 1)[..., None]           # civil twilight blend
    rgb = day * w + night * (1 - w)
    band = np.exp(-(alt / 1.2) ** 2)[..., None]             # the grey line itself
    rgb = rgb * (1 - 0.35 * band) + np.array([255, 196, 90]) * 0.35 * band
    img = Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), 'RGB')
    dr = ImageDraw.Draw(img, 'RGBA')
    for gx in range(-150, 181, 30):
        x = (gx + 180) / 360 * W
        dr.line([(x, 0), (x, H)], fill=(255, 255, 255, 28))
    for gy in range(-60, 61, 30):
        y = (90 - gy) / 180 * H
        dr.line([(0, y), (W, y)], fill=(255, 255, 255, 28))

    def xy(lo, la):
        return (lo + 180) / 360 * W, (90 - la) / 180 * H
    sx, sy = xy(slon, dec)
    dr.ellipse([sx - 7 * k, sy - 7 * k, sx + 7 * k, sy + 7 * k], fill=(255, 210, 60, 255), outline=(255, 255, 255, 255), width=k)
    bx, by = xy(50.6, 26.2)                                   # Bahrain, country level
    dr.ellipse([bx - 4 * k, by - 4 * k, bx + 4 * k, by + 4 * k], fill=(23, 249, 218, 255), outline=(0, 0, 40, 255), width=k)
    dr.text((bx + 7 * k, by - 7 * k), 'Bahrain', font=font(11 * k, True), fill=(255, 255, 255, 255), stroke_width=2 * k, stroke_fill=(0, 0, 40, 255))
    local = now.astimezone(TZ)
    out = frame(img, 'GREY LINE · DAY & NIGHT',
                f'{now:%d %b %Y %H:%M} UTC  ·  {local:%H:%M} Bahrain  ·  sun overhead at {abs(dec):.1f}°{"N" if dec >= 0 else "S"} {abs(slon):.1f}°{"E" if slon >= 0 else "W"}',
                'Solar position calculated  ·  Earth images: NASA Blue Marble & Black Marble (public domain)', k)
    out.save(path, quality=86, optimize=True, progressive=True) if path.endswith('.jpg') else out.save(path, optimize=True)
    print('wrote', path, out.size)


def unavailable(path, title, why):
    img = Image.new('RGB', (1280, 640), PANEL)
    d = ImageDraw.Draw(img)
    d.text((640, 300), 'Unavailable', font=font(44, True), fill=MUTED, anchor='mm')
    d.text((640, 364), why[:90], font=font(22), fill=MUTED, anchor='mm')
    frame(img, title, 'No data this hour', 'The map will return at the next successful update', 2).convert('RGB').save(path)


if __name__ == '__main__':
    kind, out = sys.argv[1], sys.argv[2]
    try:
        gulf(out) if kind == 'gulf' else greyline(out)
    except Exception as e:
        print(kind, 'failed:', e)
        unavailable(out, 'GULF · TEMPERATURE & WIND' if kind == 'gulf' else 'GREY LINE · DAY & NIGHT', str(e))
