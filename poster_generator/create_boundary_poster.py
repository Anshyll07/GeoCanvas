#!/usr/bin/env python3
"""
Watercolor Boundary Poster Generator

Generates high-end antique/watercolor-style maps of countries or states divided
into their administrative boundaries (states, counties, or districts).
Implements concentric watercolor ocean shading, greedy polygon coloring,
hand-inked outline highlights, and procedural paper aging.
"""

import argparse
import hashlib
import json
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import cast

import matplotlib.colors as mcolors
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
from geopandas import GeoDataFrame
from geopy.geocoders import Nominatim
from matplotlib.font_manager import FontProperties
from shapely.geometry import Point, Polygon, MultiPolygon
from tqdm import tqdm
from PIL import Image

# Reconfigure console encoding for Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)
POSTERS_DIR = "posters"

# Playfair Display Font cache path
from font_management import load_fonts

FONTS = load_fonts()

# Watercolor Antique Palette (derived from the New York vintage theme)
WATERCOLOR_PALETTE = [
    {"fill": "#E5D8C3", "stroke": "#CBB99C"},  # Warm parchment/beige
    {"fill": "#C5CCB6", "stroke": "#A6B093"},  # Soft olive green (derived from #333C29)
    {"fill": "#B5C8C1", "stroke": "#91AEA3"},  # Soft teal/blue (derived from #7BBBA6)
    {"fill": "#EFEADF", "stroke": "#DDD3BE"},  # Light cream
    {"fill": "#D9CBA9", "stroke": "#C2AF84"},  # Warm sand/gold
]

DEEP_OCEAN = "#436359"  # Dark vintage green-teal
SHALLOW_WATER_GRADIENT = [
    "#4D6D63",  # Deep intermediate
    "#5A7C71",  # Intermediate
    "#6A8D82",  # Shallow
    "#7BBBA6",  # Coastline shallow (New York map water color!)
]

INK_COLOR = "#1C1917"  # Soft charcoal black (matching New York lines)


def cache_get(key: str):
    safe = key.replace(os.sep, "_").replace(" ", "_")
    path = CACHE_DIR / f"{safe}.pkl"
    if path.exists():
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return None


def cache_set(key: str, value):
    safe = key.replace(os.sep, "_").replace(" ", "_")
    path = CACHE_DIR / f"{safe}.pkl"
    try:
        with open(path, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def decimal_to_dms(decimal_val):
    val = abs(decimal_val)
    degrees = int(val)
    minutes_float = (val - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60)
    if seconds >= 60:
        seconds = 0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1
    return degrees, minutes, seconds


def format_coords_dms(lat, lon):
    lat_deg, lat_min, lat_sec = decimal_to_dms(lat)
    lat_dir = "N" if lat >= 0 else "S"
    lon_deg, lon_min, lon_sec = decimal_to_dms(lon)
    lon_dir = "E" if lon >= 0 else "W"
    return f"{lat_deg}°{lat_min:02d}'{lat_sec:02d}\" {lat_dir} / {lon_deg}°{lon_min:02d}'{lon_sec:02d}\" {lon_dir}"


def draw_compass_rose(ax, cx, cy, r, color, bg_color, font_props=None):
    import copy

    circle_outer = patches.Circle(
        (cx, cy),
        r,
        edgecolor=color,
        facecolor="none",
        linewidth=1.5,
        transform=ax.transAxes,
        zorder=12,
    )
    circle_inner = patches.Circle(
        (cx, cy),
        r * 0.85,
        edgecolor=color,
        facecolor="none",
        linewidth=0.75,
        transform=ax.transAxes,
        zorder=12,
    )
    ax.add_patch(circle_outer)
    ax.add_patch(circle_inner)

    w_main = r * 0.12
    w_sec = r * 0.08
    r_sec = r * 0.65

    mains = [(90, r, w_main), (0, r, w_main), (270, r, w_main), (180, r, w_main)]
    secs = [
        (45, r_sec, w_sec),
        (315, r_sec, w_sec),
        (225, r_sec, w_sec),
        (135, r_sec, w_sec),
    ]

    for theta_deg, L, W in mains + secs:
        theta = np.radians(theta_deg)
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        peak_x = cx + L * cos_t
        peak_y = cy + L * sin_t
        off_x = -W * sin_t
        off_y = W * cos_t

        poly_dark = patches.Polygon(
            [(cx, cy), (peak_x, peak_y), (cx - off_x, cy - off_y)],
            facecolor=color,
            edgecolor=color,
            linewidth=0.5,
            transform=ax.transAxes,
            zorder=13,
        )

        poly_light = patches.Polygon(
            [(cx, cy), (peak_x, peak_y), (cx + off_x, cy + off_y)],
            facecolor=bg_color,
            edgecolor=color,
            linewidth=0.5,
            transform=ax.transAxes,
            zorder=13,
        )

        ax.add_patch(poly_dark)
        ax.add_patch(poly_light)

    label_dist = r * 1.18
    labels = [("N", 90), ("E", 0), ("S", 270), ("W", 180)]
    for text, deg in labels:
        rad = np.radians(deg)
        lx = cx + label_dist * np.cos(rad)
        ly = cy + label_dist * np.sin(rad)
        if font_props:
            compass_font = copy.copy(font_props)
            compass_font.set_size(8)
            compass_font.set_weight("bold")
            ax.text(
                lx,
                ly,
                text,
                color=color,
                ha="center",
                va="center",
                fontproperties=compass_font,
                transform=ax.transAxes,
                zorder=14,
            )
        else:
            ax.text(
                lx,
                ly,
                text,
                color=color,
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                transform=ax.transAxes,
                zorder=14,
            )


COUNTRY_NAME_MAP = {
    "united states": "United States of America",
    "usa": "United States of America",
    "us": "United States of America",
    "united states of america": "United States of America",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "great britain": "United Kingdom",
}


def ensure_natural_earth_file():
    geojson_path = "cache/ne_10m_states.geojson"
    if not os.path.exists(geojson_path):
        import urllib.request

        url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson"
        print(
            "Downloading Natural Earth 10m states and provinces GeoJSON (approx 38MB)..."
        )
        os.makedirs("cache", exist_ok=True)
        try:
            urllib.request.urlretrieve(url, geojson_path)
            print("✓ Download completed successfully!")
        except Exception as e:
            print(f"⚠ Failed to download Natural Earth dataset: {e}")


def fetch_boundary_data(region, admin_level):
    region_lower = region.lower()
    mapped_country = COUNTRY_NAME_MAP.get(region_lower, region)

    # For known countries, use Natural Earth offline database
    # Check if this region appears to be a country or if we are requesting level 4
    # (Since OSMnx country downloads are huge and fail Overpass max size limits)
    is_major_country = region_lower in COUNTRY_NAME_MAP or admin_level == 4

    if is_major_country:
        ensure_natural_earth_file()
        geojson_path = "cache/ne_10m_states.geojson"
        if os.path.exists(geojson_path):
            import geopandas as gpd

            try:
                print(
                    f"Loading '{mapped_country}' states from offline Natural Earth database..."
                )
                gdf_full = gpd.read_file(geojson_path)
                gdf_filtered = gdf_full[
                    gdf_full["admin"].str.lower() == mapped_country.lower()
                ]
                if not gdf_filtered.empty:
                    print(f"✓ Found {len(gdf_filtered)} states/provinces.")
                    return gdf_filtered
                else:
                    print(
                        f"⚠ Country '{mapped_country}' not found in Natural Earth. Falling back to OSMnx."
                    )
            except Exception as e:
                print(f"⚠ Offline read failed: {e}. Falling back to OSMnx.")

    cache_key = f"boundary_{region}_{admin_level}"
    cached = cache_get(cache_key)
    if cached is not None:
        print("✓ Using cached boundary features")
        return cached

    print(
        f"Downloading boundary features for '{region}' (admin_level={admin_level}) via OSMnx..."
    )
    try:
        gdf = ox.features_from_place(
            region, tags={"boundary": "administrative", "admin_level": str(admin_level)}
        )
        # Keep only Polygons / MultiPolygons
        gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if gdf.empty:
            raise ValueError(
                "No administrative boundary polygons found for the specified region and level."
            )
        cache_set(cache_key, gdf)
        return gdf
    except Exception as e:
        print(f"Error fetching boundaries: {e}")
        return None


def color_states(gdf):
    """
    Greedy coloring algorithm to assign colors from WATERCOLOR_PALETTE
    such that adjacent states do not have the same color.
    """
    colors = [-1] * len(gdf)
    for i in range(len(gdf)):
        geom_i = gdf.iloc[i].geometry
        neighbors = []
        for j in range(i):
            if gdf.iloc[j].geometry.intersects(geom_i):
                neighbors.append(colors[j])

        # Find first color not used by neighbors
        for c in range(len(WATERCOLOR_PALETTE)):
            if c not in neighbors:
                colors[i] = c
                break
        if colors[i] == -1:
            colors[i] = i % len(WATERCOLOR_PALETTE)
    return colors


def apply_paper_texture(output_file, grain_intensity=0.36):
    print("Applying watercolor paper texture and vignette post-processing...")
    try:
        img = Image.open(output_file)
        width, height = img.size

        # 1. Generate fine paper grain
        fine_w, fine_h = width // 2, height // 2
        seed = int(hashlib.md5(output_file.encode("utf-8")).hexdigest()[:8], 16)
        np.random.seed(seed)

        fine_grain = np.random.normal(128, 12, (fine_h, fine_w))
        fine_img = Image.fromarray(fine_grain.astype(np.uint8), mode="L")
        fine_img = fine_img.resize((width, height), resample=Image.Resampling.BILINEAR)
        fine_arr = np.array(fine_img, dtype=float)

        # 2. Generate organic paper blotches
        blotches_w, blotches_h = width // 16, height // 16
        blotches = np.random.normal(128, 14, (blotches_h, blotches_w))
        blotches_img = Image.fromarray(blotches.astype(np.uint8), mode="L")
        blotches_img = blotches_img.resize(
            (width, height), resample=Image.Resampling.BILINEAR
        )
        blotches_arr = np.array(blotches_img, dtype=float)

        # Combine
        combined_noise = 0.6 * fine_arr + 0.4 * blotches_arr

        # Scale to range (e.g. 0.82 to 1.18 for strong grain)
        min_factor = 1.0 - (grain_intensity / 2.0)
        noise_factor = min_factor + grain_intensity * (combined_noise / 255.0)

        # 3. Soft radial vignette
        x = np.linspace(-1, 1, width)
        y = np.linspace(-1, 1, height)
        X, Y = np.meshgrid(x, y)
        d = np.sqrt(X**2 + Y**2)
        vignette_arr = 1.0 - 0.25 * np.clip((d - 0.5) / (np.sqrt(2) - 0.5), 0, 1)

        # Sepia staining
        vignette_r = vignette_arr
        vignette_g = vignette_arr * 0.97
        vignette_b = vignette_arr * 0.93

        # Apply
        img_rgb = img.convert("RGB")
        img_arr = np.array(img_rgb, dtype=float)

        img_arr[:, :, 0] = np.clip(img_arr[:, :, 0] * noise_factor * vignette_r, 0, 255)
        img_arr[:, :, 1] = np.clip(img_arr[:, :, 1] * noise_factor * vignette_g, 0, 255)
        img_arr[:, :, 2] = np.clip(img_arr[:, :, 2] * noise_factor * vignette_b, 0, 255)

        final_img = Image.fromarray(img_arr.astype(np.uint8), mode="RGB")
        final_img.save(output_file)
        print("✓ Watercolor post-processing completed successfully!")
    except Exception as e:
        print(f"⚠ Texture post-processing failed: {e}")


def create_boundary_poster(
    region,
    admin_level=4,
    title=None,
    subtitle=None,
    contiguous=True,
    width=12,
    height=16,
    output_file=None,
    grain_intensity=0.36,
):
    # Fetch boundaries
    gdf = fetch_boundary_data(region, admin_level)
    if gdf is None or gdf.empty:
        print("Error: Could not retrieve boundary data.")
        return

    # Contiguous US Filter
    if (
        region.lower() in ["united states", "usa", "united states of america", "us"]
        and contiguous
    ):

        def is_contiguous(geom):
            c = geom.centroid
            return 24.0 <= c.y <= 50.0 and -125.0 <= c.x <= -65.0

        gdf = gdf[gdf.geometry.apply(is_contiguous)]
        if gdf.empty:
            print("Error: US contiguous filter removed all geometries.")
            return

    # Project to appropriate projected CRS (metric)
    print("Projecting map geometries...")
    gdf_proj = ox.projection.project_gdf(gdf)

    # Simplify geometries slightly to give hand-drawn feel and speed up rendering
    minx, miny, maxx, maxy = gdf_proj.total_bounds
    diag = np.sqrt((maxx - minx) ** 2 + (maxy - miny) ** 2)
    simplify_tolerance = diag * 0.0006
    gdf_proj["geometry"] = gdf_proj["geometry"].simplify(
        tolerance=simplify_tolerance, preserve_topology=True
    )

    # Greedily assign colors
    print("Assigning watercolor palette colors...")
    color_indices = color_states(gdf_proj)
    gdf_proj["color_idx"] = color_indices

    # Render Setup
    print("Rendering map layers...")
    fig, ax = plt.subplots(figsize=(width, height), facecolor=DEEP_OCEAN)
    ax.set_facecolor(DEEP_OCEAN)
    ax.set_position((0.0, 0.0, 1.0, 1.0))

    # 1. Concentric Shallow Water ocean shading
    print("Computing coastal water buffer bands...")
    land_union = gdf_proj.unary_union

    # Render ocean bands in reverse order (widest buffer first, drawn underneath)
    buffer_fractions = [0.08, 0.05, 0.025, 0.01]
    opacities = [0.15, 0.3, 0.5, 0.8]

    for i, frac in enumerate(buffer_fractions):
        dist = diag * frac
        buffered = land_union.buffer(dist)
        # Plot water band
        color = SHALLOW_WATER_GRADIENT[i]
        opacity = opacities[i]

        # Handle Polygon / MultiPolygon plotting
        if isinstance(buffered, (Polygon, MultiPolygon)):
            xs, ys = [], []
            if isinstance(buffered, Polygon):
                polys = [buffered]
            else:
                polys = list(buffered.geoms)

            for poly in polys:
                patch = patches.Polygon(
                    np.array(poly.exterior.coords),
                    facecolor=color,
                    edgecolor="none",
                    alpha=opacity,
                    zorder=1.0 + i * 0.1,
                )
                ax.add_patch(patch)

    # 2. Plot Land Fills & Borders
    print("Plotting states/countries...")
    for idx, row in gdf_proj.iterrows():
        geom = row.geometry
        palette_color = WATERCOLOR_PALETTE[row.color_idx]

        if isinstance(geom, Polygon):
            polys = [geom]
        elif isinstance(geom, MultiPolygon):
            polys = list(geom.geoms)
        else:
            continue

        for poly in polys:
            # Step A: Draw main land fill
            fill_patch = patches.Polygon(
                np.array(poly.exterior.coords),
                facecolor=palette_color["fill"],
                edgecolor="none",
                zorder=5.0,
            )
            ax.add_patch(fill_patch)

            # Step B: Draw thick semi-transparent colored outline (simulates watercolor pooling)
            # Center of the line is on boundary, creating an interior shading highlight
            stroke_patch = patches.Polygon(
                np.array(poly.exterior.coords),
                facecolor="none",
                edgecolor=palette_color["stroke"],
                linewidth=6.0,
                alpha=0.6,
                zorder=6.0,
            )
            ax.add_patch(stroke_patch)

            # Step C: Draw thin charcoal "hand-inked" line on top
            ink_patch = patches.Polygon(
                np.array(poly.exterior.coords),
                facecolor="none",
                edgecolor=INK_COLOR,
                linewidth=0.75,
                zorder=7.0,
            )
            ax.add_patch(ink_patch)

    # Crop viewport to fit land boundaries with small margin (5%)
    margin = diag * 0.05
    ax.set_xlim(minx - margin, maxx + margin)
    ax.set_ylim(miny - margin, maxy + margin)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    # 3. Add Compass Rose (Top-Right)
    draw_compass_rose(ax, cx=0.88, cy=0.88, r=0.06, color=INK_COLOR, bg_color="#E3DEC3")

    # 4. Double-line Boundary Frame
    frame_margin = 0.015
    rect_outer = patches.Rectangle(
        (frame_margin, frame_margin),
        1.0 - 2 * frame_margin,
        1.0 - 2 * frame_margin,
        facecolor="none",
        edgecolor=INK_COLOR,
        linewidth=2.0,
        transform=ax.transAxes,
        zorder=20,
    )
    rect_inner = patches.Rectangle(
        (frame_margin + 0.005, frame_margin + 0.005),
        1.0 - 2 * (frame_margin + 0.005),
        1.0 - 2 * (frame_margin + 0.005),
        facecolor="none",
        edgecolor=INK_COLOR,
        linewidth=0.75,
        transform=ax.transAxes,
        zorder=20,
    )
    ax.add_patch(rect_outer)
    ax.add_patch(rect_inner)

    # 5. Geocode / Calculate center coordinates for display
    print("Resolving coordinates for labels...")
    geolocator = Nominatim(user_agent="boundary_map_poster", timeout=10)
    try:
        loc = geolocator.geocode(region)
        lat, lon = loc.latitude, loc.longitude
    except Exception:
        # Fallback to centroid
        centroid_wgs84 = gdf.unary_union.centroid
        lat, lon = centroid_wgs84.y, centroid_wgs84.x

    coords_str = format_coords_dms(lat, lon)

    # 6. Title Card Cardboard Box (Bottom Center)
    card_w, card_h = 0.40, 0.10
    card_x, card_y = 0.5 - card_w / 2, 0.04

    # White/Beige card box
    card_bg = patches.Rectangle(
        (card_x, card_y),
        card_w,
        card_h,
        facecolor="#E6DBC6",
        edgecolor=INK_COLOR,
        linewidth=1.5,
        transform=ax.transAxes,
        zorder=22,
    )
    # Inner border line
    card_border_inner = patches.Rectangle(
        (card_x + 0.003, card_y + 0.003),
        card_w - 0.006,
        card_h - 0.006,
        facecolor="none",
        edgecolor=INK_COLOR,
        linewidth=0.5,
        transform=ax.transAxes,
        zorder=22,
    )
    ax.add_patch(card_bg)
    ax.add_patch(card_border_inner)

    # Scale font sizes
    scale_factor = min(height, width) / 12.0

    # Setup fonts
    if FONTS:
        font_main = FontProperties(fname=FONTS["bold"], size=24 * scale_factor)
        font_sub = FontProperties(fname=FONTS["light"], size=10 * scale_factor)
        font_coords = FontProperties(fname=FONTS["regular"], size=7 * scale_factor)
    else:
        font_main = FontProperties(
            family="serif", weight="bold", size=24 * scale_factor
        )
        font_sub = FontProperties(
            family="serif", style="italic", size=10 * scale_factor
        )
        font_coords = FontProperties(family="monospace", size=7 * scale_factor)

    display_title = title or region.upper()
    display_subtitle = subtitle or f"ADMINISTRATIVE DIVISIONS"

    # Add text inside the card
    text_color = INK_COLOR
    # Center text lines
    ax.text(
        0.5,
        card_y + 0.055,
        display_title,
        color=text_color,
        ha="center",
        va="center",
        fontproperties=font_main,
        transform=ax.transAxes,
        zorder=23,
    )
    ax.text(
        0.5,
        card_y + 0.030,
        display_subtitle,
        color=text_color,
        ha="center",
        va="center",
        fontproperties=font_sub,
        transform=ax.transAxes,
        zorder=23,
    )
    ax.text(
        0.5,
        card_y + 0.012,
        coords_str,
        color=text_color,
        ha="center",
        va="center",
        fontproperties=font_coords,
        transform=ax.transAxes,
        zorder=23,
    )

    # Save initial output
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        region_slug = region.lower().replace(" ", "_").replace(",", "")
        output_file = os.path.join(
            POSTERS_DIR, f"{region_slug}_watercolor_{timestamp}.png"
        )

    os.makedirs(POSTERS_DIR, exist_ok=True)
    plt.savefig(
        output_file, dpi=300, facecolor=DEEP_OCEAN, edgecolor="none", bbox_inches=None
    )
    plt.close()
    print(f"✓ Initial poster saved to {output_file}")

    # Apply aging texture
    apply_paper_texture(output_file, grain_intensity=grain_intensity)
    return output_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watercolor Boundary Poster Generator")
    parser.add_argument(
        "--region",
        "-r",
        required=True,
        help="Region name (e.g., 'United States', 'India', 'Germany')",
    )
    parser.add_argument(
        "--admin-level",
        "-l",
        type=int,
        default=4,
        help="OSM administrative level (default: 4 for states)",
    )
    parser.add_argument(
        "--title", "-t", help="Title override (defaults to region name)"
    )
    parser.add_argument("--subtitle", "-s", help="Subtitle override")
    parser.add_argument(
        "--width", type=int, default=12, help="Poster width in inches (default: 12)"
    )
    parser.add_argument(
        "--height", type=int, default=16, help="Poster height in inches (default: 16)"
    )
    parser.add_argument(
        "--grain",
        type=float,
        default=0.36,
        help="Grain texture intensity (default: 0.36)",
    )
    parser.add_argument(
        "--contiguous",
        action="store_true",
        default=True,
        help="Filter to contiguous US states only if region is USA",
    )
    parser.add_argument(
        "--no-contiguous",
        action="store_false",
        dest="contiguous",
        help="Do not filter out Alaska/Hawaii for USA",
    )
    parser.add_argument("--output", "-o", help="Output file path")

    args = parser.parse_args()

    create_boundary_poster(
        region=args.region,
        admin_level=args.admin_level,
        title=args.title,
        subtitle=args.subtitle,
        contiguous=args.contiguous,
        width=args.width,
        height=args.height,
        output_file=args.output,
        grain_intensity=args.grain,
    )
