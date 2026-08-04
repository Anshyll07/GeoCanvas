#!/usr/bin/env python3
"""
City Map Poster Generator

This module generates beautiful, minimalist map posters for any city in the world.
It fetches OpenStreetMap data using OSMnx, applies customizable themes, and creates
high-quality poster-ready images with roads, water features, and parks.
"""

import argparse
import asyncio
import json
import os
import pickle
import sys

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
import time
from datetime import datetime
from pathlib import Path
from typing import cast

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import osmnx as ox
from geopandas import GeoDataFrame
from geopy.geocoders import Nominatim
from lat_lon_parser import parse
from matplotlib.font_manager import FontProperties
from networkx import MultiDiGraph
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import voronoi_diagram
from tqdm import tqdm

from font_management import load_fonts


class CacheError(Exception):
    """Raised when a cache operation fails."""


CACHE_DIR_PATH = os.environ.get("CACHE_DIR", "cache")
CACHE_DIR = Path(CACHE_DIR_PATH)
CACHE_DIR.mkdir(exist_ok=True)

THEMES_DIR = str(Path(__file__).resolve().parent / "themes")
FONTS_DIR = str(Path(__file__).resolve().parent / "fonts")
POSTERS_DIR = str(Path(__file__).resolve().parent / "posters")

FILE_ENCODING = "utf-8"

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


def _cache_path(key: str) -> str:
    """
    Generate a safe cache file path from a cache key.

    Args:
        key: Cache key identifier

    Returns:
        Path to cache file with .pkl extension
    """
    safe = key.replace(os.sep, "_")
    return os.path.join(CACHE_DIR, f"{safe}.pkl")


def cache_get(key: str):
    """
    Retrieve a cached object by key.

    Args:
        key: Cache key identifier

    Returns:
        Cached object if found, None otherwise

    Raises:
        CacheError: If cache read operation fails
    """
    try:
        path = _cache_path(key)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        raise CacheError(f"Cache read failed: {e}") from e


def cache_set(key: str, value):
    """
    Store an object in the cache.

    Args:
        key: Cache key identifier
        value: Object to cache (must be picklable)

    Raises:
        CacheError: If cache write operation fails
    """
    try:
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        path = _cache_path(key)
        with open(path, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        raise CacheError(f"Cache write failed: {e}") from e


def decimal_to_dms(decimal_val):
    """
    Convert a decimal coordinate to Degrees, Minutes, Seconds.
    """
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
    """
    Format latitude and longitude to DMS string.
    Example: 40°42'46" N / 74°00'22" W
    """
    lat_deg, lat_min, lat_sec = decimal_to_dms(lat)
    lat_dir = "N" if lat >= 0 else "S"

    lon_deg, lon_min, lon_sec = decimal_to_dms(lon)
    lon_dir = "E" if lon >= 0 else "W"

    return f"{lat_deg}°{lat_min:02d}'{lat_sec:02d}\" {lat_dir} / {lon_deg}°{lon_min:02d}'{lon_sec:02d}\" {lon_dir}"


def draw_compass_rose(ax, cx, cy, r, color, bg_color, font_props=None):
    """
    Draw a classic 8-point compass rose in axes coordinates.
    cx, cy: center coordinates (0-1)
    r: radius/size (0-1)
    color: primary theme text color (for dark halves of star, circle lines, text)
    bg_color: theme background color (for light halves of star)
    """
    import matplotlib.patches as patches
    import copy

    # 1. Draw outer double circles
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

    # 2. Draw the 8-point star
    w_main = r * 0.12
    w_sec = r * 0.08
    r_sec = r * 0.65

    mains = [
        (90, r, w_main),  # North
        (0, r, w_main),  # East
        (270, r, w_main),  # South
        (180, r, w_main),  # West
    ]

    secs = [
        (45, r_sec, w_sec),  # NE
        (315, r_sec, w_sec),  # SE
        (225, r_sec, w_sec),  # SW
        (135, r_sec, w_sec),  # NW
    ]

    for theta_deg, L, W in mains + secs:
        theta = np.radians(theta_deg)
        cos_t, sin_t = np.cos(theta), np.sin(theta)

        peak_x = cx + L * cos_t
        peak_y = cy + L * sin_t

        off_x = -W * sin_t
        off_y = W * cos_t

        # Clockwise triangle (dark)
        poly_dark = patches.Polygon(
            [(cx, cy), (peak_x, peak_y), (cx - off_x, cy - off_y)],
            facecolor=color,
            edgecolor=color,
            linewidth=0.5,
            transform=ax.transAxes,
            zorder=13,
        )

        # Counter-clockwise triangle (light/bg)
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

    # 3. Add text labels N, S, E, W
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


def is_latin_script(text):
    """
    Check if text is primarily Latin script.
    Used to determine if letter-spacing should be applied to city names.

    :param text: Text to analyze
    :return: True if text is primarily Latin script, False otherwise
    """
    if not text:
        return True

    latin_count = 0
    total_alpha = 0

    for char in text:
        if char.isalpha():
            total_alpha += 1
            # Latin Unicode ranges:
            # - Basic Latin: U+0000 to U+007F
            # - Latin-1 Supplement: U+0080 to U+00FF
            # - Latin Extended-A: U+0100 to U+017F
            # - Latin Extended-B: U+0180 to U+024F
            if ord(char) < 0x250:
                latin_count += 1

    # If no alphabetic characters, default to Latin (numbers, symbols, etc.)
    if total_alpha == 0:
        return True

    # Consider it Latin if >80% of alphabetic characters are Latin
    return (latin_count / total_alpha) > 0.8


def generate_output_filename(city, theme_name, output_format):
    """
    Generate unique output filename with city, theme, and datetime.
    """
    if not os.path.exists(POSTERS_DIR):
        os.makedirs(POSTERS_DIR)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    city_slug = city.lower().replace(" ", "_")
    ext = output_format.lower()
    filename = f"{city_slug}_{theme_name}_{timestamp}.{ext}"
    return os.path.join(POSTERS_DIR, filename)


def get_available_themes():
    """
    Scans the themes directory and returns a list of available theme names.
    """
    if not os.path.exists(THEMES_DIR):
        os.makedirs(THEMES_DIR)
        return []

    themes = []
    for file in sorted(os.listdir(THEMES_DIR)):
        if file.endswith(".json"):
            theme_name = file[:-5]  # Remove .json extension
            themes.append(theme_name)
    return themes


def load_theme(theme_name="terracotta"):
    """
    Load theme from JSON file in themes directory.
    """
    theme_file = os.path.join(THEMES_DIR, f"{theme_name}.json")

    if not os.path.exists(theme_file):
        print(f"⚠ Theme file '{theme_file}' not found. Using default terracotta theme.")
        # Fallback to embedded terracotta theme
        return {
            "name": "Terracotta",
            "description": "Mediterranean warmth - burnt orange and clay tones on cream",
            "bg": "#F5EDE4",
            "text": "#8B4513",
            "gradient_color": "#F5EDE4",
            "water": "#A8C4C4",
            "parks": "#E8E0D0",
            "road_motorway": "#A0522D",
            "road_primary": "#B8653A",
            "road_secondary": "#C9846A",
            "road_tertiary": "#D9A08A",
            "road_residential": "#E5C4B0",
            "road_default": "#D9A08A",
        }

    with open(theme_file, "r", encoding=FILE_ENCODING) as f:
        theme = json.load(f)
        print(f"Loaded theme: {theme.get('name', theme_name)}")
        if "description" in theme:
            print(f"  {theme['description']}")
        return theme


# Load theme (can be changed via command line or input)
THEME = dict[str, str]()  # Will be loaded later


def create_gradient_fade(ax, color, location="bottom", zorder=10):
    """
    Creates a fade effect at the top or bottom of the map.
    """
    vals = np.linspace(0, 1, 256).reshape(-1, 1)
    gradient = np.hstack((vals, vals))

    rgb = mcolors.to_rgb(color)
    my_colors = np.zeros((256, 4))
    my_colors[:, 0] = rgb[0]
    my_colors[:, 1] = rgb[1]
    my_colors[:, 2] = rgb[2]

    if location == "bottom":
        my_colors[:, 3] = np.linspace(1, 0, 256)
        extent_y_start = 0
        extent_y_end = 0.25
    else:
        my_colors[:, 3] = np.linspace(0, 1, 256)
        extent_y_start = 0.75
        extent_y_end = 1.0

    custom_cmap = mcolors.ListedColormap(my_colors)

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    y_range = ylim[1] - ylim[0]

    y_bottom = ylim[0] + y_range * extent_y_start
    y_top = ylim[0] + y_range * extent_y_end

    ax.imshow(
        gradient,
        extent=[xlim[0], xlim[1], y_bottom, y_top],
        aspect="auto",
        cmap=custom_cmap,
        zorder=zorder,
        origin="lower",
    )


def get_edge_colors_by_type(g):
    """
    Assigns colors to edges based on road type hierarchy.
    Returns a list of colors corresponding to each edge in the graph.
    """
    edge_colors = []

    for _u, _v, data in g.edges(data=True):
        # Get the highway type (can be a list or string)
        highway = data.get("highway", "unclassified")

        # Handle list of highway types (take the first one)
        if isinstance(highway, list):
            highway = highway[0] if highway else "unclassified"

        # Assign color based on road type
        if highway in ["motorway", "motorway_link"]:
            color = THEME["road_motorway"]
        elif highway in ["trunk", "trunk_link", "primary", "primary_link"]:
            color = THEME["road_primary"]
        elif highway in ["secondary", "secondary_link"]:
            color = THEME["road_secondary"]
        elif highway in ["tertiary", "tertiary_link"]:
            color = THEME["road_tertiary"]
        elif highway in ["residential", "living_street", "unclassified"]:
            color = THEME["road_residential"]
        else:
            color = THEME["road_default"]

        edge_colors.append(color)

    return edge_colors


def get_edge_widths_by_type(g):
    """
    Assigns line widths to edges based on road type.
    Major roads get thicker lines.
    """
    edge_widths = []

    for _u, _v, data in g.edges(data=True):
        highway = data.get("highway", "unclassified")

        if isinstance(highway, list):
            highway = highway[0] if highway else "unclassified"

        # Assign width based on road importance
        if THEME.get("layout") == "vintage":
            # 2x to 3x thicker than normal to match user request
            if highway in ["motorway", "motorway_link"]:
                width = 3.0
            elif highway in ["trunk", "trunk_link", "primary", "primary_link"]:
                width = 2.5
            elif highway in ["secondary", "secondary_link"]:
                width = 1.6
            elif highway in ["tertiary", "tertiary_link"]:
                width = 1.0
            else:
                width = 0.5
        else:
            if highway in ["motorway", "motorway_link"]:
                width = 1.2
            elif highway in ["trunk", "trunk_link", "primary", "primary_link"]:
                width = 1.0
            elif highway in ["secondary", "secondary_link"]:
                width = 0.8
            elif highway in ["tertiary", "tertiary_link"]:
                width = 0.6
            else:
                width = 0.4

        edge_widths.append(width)

    return edge_widths


def get_coordinates(city, country):
    """
    Fetches coordinates for a given city and country using geopy.
    Includes rate limiting to be respectful to the geocoding service.
    """
    coords = f"coords_{city.lower()}_{country.lower()}"
    cached = cache_get(coords)
    if cached:
        print(f"Using cached coordinates for {city}, {country}")
        return cached

    print("Looking up coordinates...")
    geolocator = Nominatim(user_agent="city_map_poster", timeout=10)

    # Add a small delay to respect Nominatim's usage policy
    time.sleep(1)

    try:
        location = geolocator.geocode(f"{city}, {country}")
    except Exception as e:
        raise ValueError(f"Geocoding failed for {city}, {country}: {e}") from e

    # If geocode returned a coroutine in some environments, run it to get the result.
    if asyncio.iscoroutine(location):
        try:
            location = asyncio.run(location)
        except RuntimeError as exc:
            # If an event loop is already running, try using it to complete the coroutine.
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Running event loop in the same thread; raise a clear error.
                raise RuntimeError(
                    "Geocoder returned a coroutine while an event loop is already running. "
                    "Run this script in a synchronous environment."
                ) from exc
            location = loop.run_until_complete(location)

    if location:
        # Use getattr to safely access address (helps static analyzers)
        addr = getattr(location, "address", None)
        if addr:
            print(f"Found: {addr}")
        else:
            print("Found location (address not available)")
        print(f"Coordinates: {location.latitude}, {location.longitude}")
        try:
            cache_set(coords, (location.latitude, location.longitude))
        except CacheError as e:
            print(e)
        return (location.latitude, location.longitude)


def color_neighborhoods(gdf):
    """
    Greedy coloring algorithm to assign colors from WATERCOLOR_PALETTE
    such that adjacent neighborhoods do not have the same color.
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


def draw_blueprint_grid(ax, grid_color="#FFFFFF", alpha=0.28):
    """
    Draw a fine technical grid across the axes.
    """
    # Vertical lines every 0.04 units
    for x in np.arange(0, 1.01, 0.04):
        ax.plot(
            [x, x],
            [0, 1],
            color=grid_color,
            alpha=alpha,
            linewidth=0.8,
            transform=ax.transAxes,
            zorder=0.1,
        )
    # Horizontal lines every 0.04 units
    for y in np.arange(0, 1.01, 0.04):
        ax.plot(
            [0, 1],
            [y, y],
            color=grid_color,
            alpha=alpha,
            linewidth=0.8,
            transform=ax.transAxes,
            zorder=0.1,
        )


def get_crop_limits(g_proj, center_lat_lon, fig, dist):
    """
    Crop inward to preserve aspect ratio while guaranteeing
    full coverage of the requested radius.
    """
    lat, lon = center_lat_lon

    # Project center point into graph CRS
    center = ox.projection.project_geometry(
        Point(lon, lat), crs="EPSG:4326", to_crs=g_proj.graph["crs"]
    )[0]
    center_x, center_y = center.x, center.y

    fig_width, fig_height = fig.get_size_inches()
    aspect = fig_width / fig_height

    # Start from the *requested* radius
    half_x = dist
    half_y = dist

    # Cut inward to match aspect
    if aspect > 1:  # landscape → reduce height
        half_y = half_x / aspect
    else:  # portrait → reduce width
        half_x = half_y * aspect

    return (
        (center_x - half_x, center_x + half_x),
        (center_y - half_y, center_y + half_y),
    )


def fetch_graph(point, dist) -> MultiDiGraph | None:
    """
    Fetch street network graph from OpenStreetMap.

    Uses caching to avoid redundant downloads. Fetches all network types
    within the specified distance from the center point.

    Args:
        point: (latitude, longitude) tuple for center point
        dist: Distance in meters from center point

    Returns:
        MultiDiGraph of street network, or None if fetch fails
    """
    lat, lon = point
    graph = f"graph_{lat}_{lon}_{dist}"
    cached = cache_get(graph)
    if cached is not None:
        print("Using cached street network")
        return cast(MultiDiGraph, cached)

    try:
        g = ox.graph_from_point(
            point,
            dist=dist,
            dist_type="bbox",
            network_type="all",
            truncate_by_edge=True,
        )
        # Rate limit between requests
        time.sleep(0.5)
        try:
            cache_set(graph, g)
        except CacheError as e:
            print(e)
        return g
    except Exception as e:
        print(f"OSMnx error while fetching graph: {e}")
        return None


def fetch_features(point, dist, tags, name) -> GeoDataFrame | None:
    """
    Fetch geographic features (water, parks, etc.) from OpenStreetMap.

    Uses caching to avoid redundant downloads. Fetches features matching
    the specified OSM tags within distance from center point.

    Args:
        point: (latitude, longitude) tuple for center point
        dist: Distance in meters from center point
        tags: Dictionary of OSM tags to filter features
        name: Name for this feature type (for caching and logging)

    Returns:
        GeoDataFrame of features, or None if fetch fails
    """
    lat, lon = point
    tag_str = "_".join(tags.keys())
    features = f"{name}_{lat}_{lon}_{dist}_{tag_str}"
    cached = cache_get(features)
    if cached is not None:
        print(f"Using cached {name}")
        return cast(GeoDataFrame, cached)

    try:
        data = ox.features_from_point(point, tags=tags, dist=dist)
        # Rate limit between requests
        time.sleep(0.3)
        try:
            cache_set(features, data)
        except CacheError as e:
            print(e)
        return data
    except Exception as e:
        print(f"OSMnx error while fetching features: {e}")
        return None


def create_poster(
    city,
    country,
    point,
    dist,
    output_file,
    output_format,
    width=12,
    height=16,
    country_label=None,
    name_label=None,
    display_city=None,
    display_country=None,
    fonts=None,
    draw_buildings=False,
    draw_transit=False,
    draw_contours=False,
    text_position="bottom",
    show_text=True,
    marker_lat=None,
    marker_lon=None,
    marker_style="pin",
    marker_color="#E74C3C",
):
    """
    Generate a complete map poster with roads, water, parks, and typography.

    Creates a high-quality poster by fetching OSM data, rendering map layers,
    applying the current theme, and adding text labels with coordinates.

    Args:
        city: City name for display on poster
        country: Country name for display on poster
        point: (latitude, longitude) tuple for map center
        dist: Map radius in meters
        output_file: Path where poster will be saved
        output_format: File format ('png', 'svg', or 'pdf')
        width: Poster width in inches (default: 12)
        height: Poster height in inches (default: 16)
        country_label: Optional override for country text on poster
        _name_label: Optional override for city name (unused, reserved for future use)

    Raises:
        RuntimeError: If street network data cannot be retrieved
    """
    # Handle display names for i18n support
    # Priority: display_city/display_country > name_label/country_label > city/country
    display_city = display_city or name_label or city
    display_country = display_country or country_label or country

    print(f"\nGenerating map for {city}, {country}...")
    if point is None:
        point = get_coordinates(city, country)

    # Progress bar for data fetching
    fetch_steps = 3
    if draw_buildings:
        fetch_steps += 1
    if draw_transit:
        fetch_steps += 1

    with tqdm(
        total=fetch_steps,
        desc="Fetching map data",
        unit="step",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}",
    ) as pbar:
        # 1. Fetch Street Network
        pbar.set_description("Downloading street network")
        compensated_dist = (
            dist * (max(height, width) / min(height, width)) / 4
        )  # To compensate for viewport crop
        g = fetch_graph(point, compensated_dist)
        if g is None:
            raise RuntimeError("Failed to retrieve street network data.")
        pbar.update(1)

        # 2. Fetch Water Features
        pbar.set_description("Downloading water features")
        water = fetch_features(
            point,
            compensated_dist,
            tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
            name="water",
        )
        pbar.update(1)

        # 3. Fetch Parks
        pbar.set_description("Downloading parks/green spaces")
        parks = fetch_features(
            point,
            compensated_dist,
            tags={"leisure": "park", "landuse": "grass"},
            name="parks",
        )
        pbar.update(1)

        buildings = None
        if draw_buildings:
            pbar.set_description("Downloading building footprints")
            buildings = fetch_features(
                point,
                compensated_dist,
                tags={"building": True},
                name="buildings",
            )
            pbar.update(1)

        transit = None
        if draw_transit:
            pbar.set_description("Downloading transit lines")
            transit = fetch_features(
                point,
                compensated_dist,
                tags={"railway": ["subway", "light_rail", "tram", "monorail", "train"]},
                name="transit",
            )
            pbar.update(1)

    print("All data retrieved successfully!")

    # 1.5 Fetch Neighborhoods if watercolor layout is active
    neighborhoods = None
    if THEME.get("watercolor"):
        print("Downloading neighborhood boundaries...")
        # Fetch suburb, neighbourhood, borough, quarter features
        neighborhoods = fetch_features(
            point,
            compensated_dist,
            tags={
                "place": [
                    "suburb",
                    "neighbourhood",
                    "borough",
                    "quarter",
                    "town",
                    "city_district",
                ]
            },
            name="neighborhoods",
        )

    # 2. Setup Plot
    print("Rendering map...")
    fig, ax = plt.subplots(
        figsize=(width, height),
        facecolor=THEME["bg"] if not THEME.get("watercolor") else DEEP_OCEAN,
    )
    ax.set_facecolor(THEME["bg"] if not THEME.get("watercolor") else DEEP_OCEAN)
    ax.set_position((0.0, 0.0, 1.0, 1.0))

    # Project graph to a metric CRS so distances and aspect are linear (meters)
    g_proj = ox.project_graph(g)

    # Determine cropping limits to maintain the poster aspect ratio
    crop_xlim, crop_ylim = get_crop_limits(g_proj, point, fig, compensated_dist)

    # 2.5 Topography Contours
    if draw_contours:
        print("Fetching and rendering topography contours...")
        try:
            import srtm
            from pyproj import Transformer

            minx, maxx = crop_xlim
            miny, maxy = crop_ylim

            transformer_back = Transformer.from_crs(
                g_proj.graph["crs"], "EPSG:4326", always_xy=True
            )
            transformer_fwd = Transformer.from_crs(
                "EPSG:4326", g_proj.graph["crs"], always_xy=True
            )

            lon_min, lat_min = transformer_back.transform(minx, miny)
            lon_max, lat_max = transformer_back.transform(maxx, maxy)

            # Generate grid (expand slightly to prevent edge cutoffs)
            lats = np.linspace(
                min(lat_min, lat_max) - 0.01, max(lat_min, lat_max) + 0.01, 150
            )
            lons = np.linspace(
                min(lon_min, lon_max) - 0.01, max(lon_min, lon_max) + 0.01, 150
            )

            elevation_data = srtm.get_data()
            Z = np.zeros((150, 150))
            for i, r in enumerate(lats):
                for j, c in enumerate(lons):
                    e = elevation_data.get_elevation(r, c)
                    Z[i, j] = e if e is not None else 0

            LONS, LATS = np.meshgrid(lons, lats)
            X_proj, Y_proj = transformer_fwd.transform(LONS, LATS)

            contour_color = THEME.get("contour", THEME.get("text", "#888888"))
            contour_alpha = THEME.get("contour_alpha", 0.25)

            ax.contour(
                X_proj,
                Y_proj,
                Z,
                levels=20,
                colors=contour_color,
                linewidths=0.5,
                alpha=contour_alpha,
                zorder=0.2,
            )
        except Exception as e:
            print(f"Error rendering contours: {e}")

    # 3. Plot Layers
    if THEME.get("layout") == "blueprint":
        print("Rendering blueprint technical styling...")
        # Draw blueprint grid
        draw_blueprint_grid(ax)

        # A. Setup blueprint background on figure and axes
        fig.patch.set_facecolor(THEME["bg"])
        ax.set_facecolor(THEME["bg"])

        # B. Draw water outlines
        if water is not None and not water.empty:
            water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if not water_polys.empty:
                try:
                    water_polys = ox.projection.project_gdf(water_polys)
                except Exception:
                    water_polys = water_polys.to_crs(g_proj.graph["crs"])
                water_polys.boundary.plot(
                    ax=ax, color="#FFFFFF", linewidth=1.2, alpha=0.8, zorder=0.5
                )

        # C. Draw parks outlines
        if parks is not None and not parks.empty:
            parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if not parks_polys.empty:
                try:
                    parks_polys = ox.projection.project_gdf(parks_polys)
                except Exception:
                    parks_polys = parks_polys.to_crs(g_proj.graph["crs"])
                parks_polys.boundary.plot(
                    ax=ax, color="#FFFFFF", linewidth=0.8, alpha=0.5, zorder=0.8
                )

    elif THEME.get("watercolor"):
        print("Rendering hand-painted watercolor styling...")
        from shapely.geometry import box

        minx, maxx = crop_xlim
        miny, maxy = crop_ylim
        diag = np.sqrt((maxx - minx) ** 2 + (maxy - miny) ** 2)
        bbox_poly = box(minx, miny, maxx, maxy)

        # A. Setup deep ocean background
        fig.patch.set_facecolor(DEEP_OCEAN)
        ax.set_facecolor(DEEP_OCEAN)

        # B. Get water features within viewport
        water_union = None
        water_polys = None
        if water is not None and not water.empty:
            water_polys_filtered = water[
                water.geometry.type.isin(["Polygon", "MultiPolygon"])
            ]
            if not water_polys_filtered.empty:
                try:
                    water_polys = ox.projection.project_gdf(water_polys_filtered)
                except Exception:
                    water_polys = water_polys_filtered.to_crs(g_proj.graph["crs"])
                water_polys_proj = water_polys.intersection(bbox_poly)
                water_polys_proj = water_polys_proj[~water_polys_proj.is_empty]
                if not water_polys_proj.empty:
                    water_union = water_polys_proj.unary_union

        # C. Calculate Land Area
        if water_union is not None and not water_union.is_empty:
            viewport_land = bbox_poly.difference(water_union)
        else:
            viewport_land = bbox_poly

        # D. Plot concentric water bands (watercolor bleed along shores)
        if (
            water_union is not None
            and not water_union.is_empty
            and not viewport_land.is_empty
        ):
            buffer_fractions = [0.08, 0.05, 0.025, 0.01]
            opacities = [0.15, 0.3, 0.5, 0.8]
            for i, frac in enumerate(buffer_fractions):
                dist_m = diag * frac
                water_band = water_union.intersection(viewport_land.buffer(dist_m))
                if not water_band.is_empty:
                    # Draw band patch
                    if isinstance(water_band, (Polygon, MultiPolygon)):
                        if isinstance(water_band, Polygon):
                            polys = [water_band]
                        else:
                            polys = list(water_band.geoms)
                        for poly in polys:
                            patch = patches.Polygon(
                                np.array(poly.exterior.coords),
                                facecolor=SHALLOW_WATER_GRADIENT[i],
                                edgecolor="none",
                                alpha=opacities[i],
                                zorder=1.0 + i * 0.1,
                            )
                            ax.add_patch(patch)

        # E. Plot default parchment background for land
        if not viewport_land.is_empty:
            if isinstance(viewport_land, Polygon):
                polys = [viewport_land]
            elif isinstance(viewport_land, MultiPolygon):
                polys = list(viewport_land.geoms)
            else:
                polys = []
            for poly in polys:
                patch = patches.Polygon(
                    np.array(poly.exterior.coords),
                    facecolor=THEME["bg"],
                    edgecolor="none",
                    zorder=2.0,
                )
                ax.add_patch(patch)

        # F. Fetch, color and plot neighborhoods/districts
        neighborhood_polys = []

        if neighborhoods is not None and not neighborhoods.empty:
            try:
                neighborhoods_proj = ox.projection.project_gdf(neighborhoods)
            except Exception:
                neighborhoods_proj = neighborhoods.to_crs(g_proj.graph["crs"])

            # Collect points (centroids) of place features
            points = []
            for geom in neighborhoods_proj.geometry:
                if geom is not None and not geom.is_empty:
                    points.append(geom.centroid)

            if len(points) >= 3:
                # Compute Voronoi cells bounded by bbox
                from shapely.geometry import MultiPoint

                mp = MultiPoint(points)
                vor_cells = voronoi_diagram(mp, envelope=bbox_poly)
                if vor_cells is not None:
                    from shapely.geometry import GeometryCollection

                    if isinstance(vor_cells, GeometryCollection):
                        geoms = list(vor_cells.geoms)
                    else:
                        geoms = [vor_cells]
                    for cell in geoms:
                        # Intersect with land to crop to coastlines
                        cell_cropped = cell.intersection(viewport_land)
                        if not cell_cropped.is_empty:
                            neighborhood_polys.append(cell_cropped)
            else:
                # Fallback to direct polygons if not enough points for Voronoi
                neighborhoods_proj = neighborhoods_proj.intersection(viewport_land)
                neighborhoods_proj = neighborhoods_proj[~neighborhoods_proj.is_empty]
                for geom in neighborhoods_proj.geometry:
                    neighborhood_polys.append(geom)

        # If still empty or too few, create a simple 4x4 grid partition so we always have colored districts
        if len(neighborhood_polys) < 3:
            print(
                "Not enough neighborhood points. Creating a grid partition for watercolor effect..."
            )
            x_coords = np.linspace(minx, maxx, 5)
            y_coords = np.linspace(miny, maxy, 5)
            for ix in range(4):
                for iy in range(4):
                    cell = box(
                        x_coords[ix], y_coords[iy], x_coords[ix + 1], y_coords[iy + 1]
                    )
                    cell_cropped = cell.intersection(viewport_land)
                    if not cell_cropped.is_empty:
                        neighborhood_polys.append(cell_cropped)

        if neighborhood_polys:
            from geopandas import GeoSeries

            gdf_neigh = GeoDataFrame(geometry=GeoSeries(neighborhood_polys))
            # Apply greedy coloring
            color_indices = color_neighborhoods(gdf_neigh)
            gdf_neigh["color_idx"] = color_indices

            # Draw neighborhood shapes
            for idx, row in gdf_neigh.iterrows():
                geom = row.geometry
                palette_color = WATERCOLOR_PALETTE[row.color_idx]

                if isinstance(geom, Polygon):
                    polys = [geom]
                elif isinstance(geom, MultiPolygon):
                    polys = list(geom.geoms)
                else:
                    continue

                for poly in polys:
                    # Draw fill
                    fill_patch = patches.Polygon(
                        np.array(poly.exterior.coords),
                        facecolor=palette_color["fill"],
                        edgecolor="none",
                        zorder=2.1,
                    )
                    ax.add_patch(fill_patch)

                    # Draw thick inner border tint
                    stroke_patch = patches.Polygon(
                        np.array(poly.exterior.coords),
                        facecolor="none",
                        edgecolor=palette_color["stroke"],
                        linewidth=5.0,
                        alpha=0.5,
                        zorder=2.2,
                    )
                    ax.add_patch(stroke_patch)

                    # Draw thin ink boundary line
                    ink_patch = patches.Polygon(
                        np.array(poly.exterior.coords),
                        facecolor="none",
                        edgecolor=INK_COLOR,
                        linewidth=0.5,
                        zorder=2.3,
                    )
                    ax.add_patch(ink_patch)

        # G. Plot parks on top of neighborhood fills
        if parks is not None and not parks.empty:
            parks_polys_filtered = parks[
                parks.geometry.type.isin(["Polygon", "MultiPolygon"])
            ]
            if not parks_polys_filtered.empty:
                try:
                    parks_polys = ox.projection.project_gdf(parks_polys_filtered)
                except Exception:
                    parks_polys = parks_polys_filtered.to_crs(g_proj.graph["crs"])
                parks_polys_proj = parks_polys.intersection(bbox_poly)
                parks_polys_proj = parks_polys_proj[~parks_polys_proj.is_empty]
                if not parks_polys_proj.empty:
                    # Filter out any park that intersects with water to avoid overlap
                    if water_union is not None and not water_union.is_empty:
                        parks_polys_proj = parks_polys_proj.difference(water_union)
                        parks_polys_proj = parks_polys_proj[~parks_polys_proj.is_empty]

                    if not parks_polys_proj.empty:
                        if isinstance(parks_polys_proj, GeoSeries):
                            parks_polys_proj = GeoDataFrame(geometry=parks_polys_proj)
                        parks_polys_proj.plot(
                            ax=ax,
                            facecolor=THEME["parks"],
                            edgecolor="none",
                            zorder=3.0,
                        )

    else:
        # Standard rendering layout (non-watercolor)
        if water is not None and not water.empty:
            water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if not water_polys.empty:
                try:
                    water_polys = ox.projection.project_gdf(water_polys)
                except Exception:
                    water_polys = water_polys.to_crs(g_proj.graph["crs"])
                water_polys.plot(
                    ax=ax, facecolor=THEME["water"], edgecolor="none", zorder=0.5
                )

        if parks is not None and not parks.empty:
            parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if not parks_polys.empty:
                try:
                    parks_polys = ox.projection.project_gdf(parks_polys)
                except Exception:
                    parks_polys = parks_polys.to_crs(g_proj.graph["crs"])
                parks_polys.plot(
                    ax=ax, facecolor=THEME["parks"], edgecolor="none", zorder=0.8
                )

        if draw_buildings and buildings is not None and not buildings.empty:
            bldgs = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])]
            if not bldgs.empty:
                try:
                    bldgs = ox.projection.project_gdf(bldgs)
                except Exception:
                    bldgs = bldgs.to_crs(g_proj.graph["crs"])
                building_color = THEME.get("buildings", THEME.get("text", "#888888"))
                bldgs.plot(
                    ax=ax,
                    facecolor=building_color,
                    edgecolor="none",
                    alpha=THEME.get("buildings_alpha", 0.08),
                    zorder=1.5,
                )

    # Layer 2: Roads with hierarchy coloring
    print("Applying road hierarchy colors...")
    edge_colors = get_edge_colors_by_type(g_proj)
    edge_widths = get_edge_widths_by_type(g_proj)

    # Plot the projected graph and then apply the cropped limits
    ox.plot_graph(
        g_proj,
        ax=ax,
        bgcolor=THEME["bg"] if not THEME.get("watercolor") else DEEP_OCEAN,
        node_size=0,
        edge_color=edge_colors,
        edge_linewidth=edge_widths,
        show=False,
        close=False,
    )
    # Set roads zorder to 4 to draw on top of watercolor neighborhood fills
    if ax.collections:
        ax.collections[-1].set_zorder(4)

    if draw_transit and transit is not None and not transit.empty:
        lines = transit[transit.geometry.type.isin(["LineString", "MultiLineString"])]
        if not lines.empty:
            try:
                lines = ox.projection.project_gdf(lines)
            except Exception:
                lines = lines.to_crs(g_proj.graph["crs"])
            # Fallback to motorway or text color so it naturally matches the active theme
            transit_color = THEME.get(
                "transit", THEME.get("road_motorway", THEME.get("text", "#FF0055"))
            )
            transit_width = THEME.get("transit_width", 1.5)
            lines.plot(
                ax=ax,
                color=transit_color,
                linewidth=transit_width,
                alpha=0.9,
                zorder=5.0,
            )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim)

    # Layer 3: Custom Marker
    if marker_lat is not None and marker_lon is not None:
        try:
            from shapely.geometry import Point
            import geopandas as gpd

            # Create a GeoDataFrame for the marker point using WGS84 CRS (epsg:4326)
            marker_gdf = gpd.GeoDataFrame(
                geometry=[Point(marker_lon, marker_lat)], crs="epsg:4326"
            )
            # Project to the local CRS
            marker_proj = marker_gdf.to_crs(g_proj.graph["crs"])
            mx, my = marker_proj.geometry.iloc[0].x, marker_proj.geometry.iloc[0].y

            if marker_style == "heart":
                marker_path = r"$\heartsuit$"
                marker_size = 800
            elif marker_style == "dot":
                marker_path = "o"
                marker_size = 200
            else:  # pin
                marker_path = "^"  # A simple triangle pin
                marker_size = 400

            ax.scatter(
                mx,
                my,
                color=marker_color,
                marker=marker_path,
                s=marker_size,
                zorder=8,
                edgecolor="white",
                linewidth=1.5,
            )
            print(
                f"Added custom {marker_style} marker at ({marker_lat}, {marker_lon})."
            )
        except Exception as e:
            print(f"Failed to add custom marker: {e}")

    # Layer 4: Gradients (Top and Bottom)
    if THEME.get("layout") != "vintage":
        create_gradient_fade(ax, THEME["gradient_color"], location="bottom", zorder=10)
        create_gradient_fade(ax, THEME["gradient_color"], location="top", zorder=10)

    # Calculate scale factor based on smaller dimension (reference 12 inches)
    # This ensures text scales properly for both portrait and landscape orientations
    scale_factor = min(height, width) / 12.0

    # Base font sizes (at 12 inches width)
    if THEME.get("layout") == "vintage":
        base_main = 32
        base_sub = 16
        base_coords = 11
        base_attr = 8
    else:
        base_main = 60
        base_sub = 22
        base_coords = 14
        base_attr = 8

    # 4. Typography - use custom fonts if provided, otherwise use default FONTS
    active_fonts = fonts or FONTS
    if active_fonts:
        # font_main is calculated dynamically later based on length
        font_sub = FontProperties(
            fname=active_fonts["light"], size=base_sub * scale_factor
        )
        font_coords = FontProperties(
            fname=active_fonts["regular"], size=base_coords * scale_factor
        )
        font_attr = FontProperties(
            fname=active_fonts["light"], size=base_attr * scale_factor
        )
    else:
        # Fallback to system fonts
        font_sub = FontProperties(
            family="monospace", weight="normal", size=base_sub * scale_factor
        )
        font_coords = FontProperties(
            family="monospace", size=base_coords * scale_factor
        )
        font_attr = FontProperties(family="monospace", size=base_attr * scale_factor)

    # Format city name based on script type
    # Latin scripts: apply uppercase and letter spacing for aesthetic
    # Non-Latin scripts (CJK, Thai, Arabic, etc.): no spacing, preserve case structure
    if THEME.get("layout") == "vintage":
        spaced_city = display_city.upper()
        # Widely space country name for vintage look
        spaced_country = "  ".join(list(display_country.upper()))
    else:
        if is_latin_script(display_city):
            # Latin script: uppercase with letter spacing (e.g., "P  A  R  I  S")
            spaced_city = "  ".join(list(display_city.upper()))
        else:
            # Non-Latin script: no spacing, no forced uppercase
            # For scripts like Arabic, Thai, Japanese, etc.
            spaced_city = display_city
        spaced_country = display_country.upper()

    # Dynamically adjust font size based on city name length to prevent truncation
    # We use the already scaled "main" font size as the starting point.
    base_adjusted_main = base_main * scale_factor
    city_char_count = len(display_city)

    # Heuristic: If length is > 10, start reducing.
    if city_char_count > 10:
        length_factor = 10 / city_char_count
        adjusted_font_size = max(base_adjusted_main * length_factor, 10 * scale_factor)
    else:
        adjusted_font_size = base_adjusted_main

    if active_fonts:
        font_main_adjusted = FontProperties(
            fname=active_fonts["bold"], size=adjusted_font_size
        )
    else:
        font_main_adjusted = FontProperties(
            family="monospace", weight="bold", size=adjusted_font_size
        )

    # Set text coordinates and format coords
    lat, lon = point
    has_text = bool(display_city and display_city.strip()) and (
        show_text or THEME.get("layout") == "blueprint"
    )

    if THEME.get("layout") == "blueprint":
        coords = None
        city_y = None
        country_y = None
        coords_y = None
        text_zorder = 15
    elif THEME.get("watercolor"):
        coords = (
            format_coords_dms(lat, lon)
            if (show_text or THEME.get("layout") == "blueprint")
            else None
        )
        if has_text:
            if text_position == "top":
                city_y = 0.928
                country_y = 0.898
                coords_y = 0.872
            else:
                city_y = 0.118
                country_y = 0.088
                coords_y = 0.062
        else:
            city_y = None
            country_y = None
            coords_y = None
        text_zorder = 15
    elif THEME.get("layout") == "vintage":
        coords = (
            format_coords_dms(lat, lon)
            if (
                (show_text or THEME.get("layout") == "blueprint")
                and not THEME.get("hide_coords", False)
            )
            else None
        )
        if text_position == "top":
            city_y = 0.925
            country_y = 0.895
            coords_y = (
                0.872
                if (
                    (show_text or THEME.get("layout") == "blueprint")
                    and not THEME.get("hide_coords", False)
                )
                else None
            )
        else:
            city_y = 0.105
            country_y = 0.075
            coords_y = (
                0.052
                if (
                    (show_text or THEME.get("layout") == "blueprint")
                    and not THEME.get("hide_coords", False)
                )
                else None
            )
        text_zorder = 15
    else:
        coords = (
            (
                f"{lat:.4f}° N / {lon:.4f}° E"
                if lat >= 0
                else f"{abs(lat):.4f}° S / {lon:.4f}° E"
            )
            if (show_text or THEME.get("layout") == "blueprint")
            else None
        )
        if coords and lon < 0:
            coords = coords.replace("E", "W")
        if text_position == "top":
            city_y = 0.93
            country_y = 0.89
            coords_y = 0.86
        else:
            city_y = 0.14
            country_y = 0.10
            coords_y = 0.07
        text_zorder = 11

    if THEME.get("layout") == "blueprint":
        # Draw the complete blueprint decorations
        # A. Dashed map bounding box
        ax.plot(
            [0.05, 0.95, 0.95, 0.05, 0.05],
            [0.17, 0.17, 0.83, 0.83, 0.17],
            color="#FFFFFF",
            linestyle="--",
            linewidth=1.2 * scale_factor,
            transform=ax.transAxes,
            zorder=20,
        )

        # Calculate viewport dimensions in kilometers
        minx, maxx = crop_xlim
        miny, maxy = crop_ylim
        map_w_m = maxx - minx
        map_h_m = maxy - miny
        map_w_km = map_w_m / 1000.0
        map_h_km = map_h_m / 1000.0

        # Bottom dimension line and label
        ax.annotate(
            "",
            xy=(0.05, 0.155),
            xytext=(0.95, 0.155),
            arrowprops=dict(
                arrowstyle="<->", color="#FFFFFF", linewidth=1 * scale_factor
            ),
            transform=ax.transAxes,
        )
        ax.text(
            0.5,
            0.136,
            f"{map_w_km:.2f} Kilometers",
            transform=ax.transAxes,
            color="#FFFFFF",
            ha="center",
            fontproperties=font_coords,
            size=11 * scale_factor,
            zorder=21,
        )

        # Left dimension line and label
        ax.annotate(
            "",
            xy=(0.03, 0.17),
            xytext=(0.03, 0.83),
            arrowprops=dict(
                arrowstyle="<->", color="#FFFFFF", linewidth=1 * scale_factor
            ),
            transform=ax.transAxes,
        )
        ax.text(
            0.018,
            0.5,
            f"{map_h_km:.2f} Kilometers",
            transform=ax.transAxes,
            color="#FFFFFF",
            rotation=90,
            ha="center",
            va="center",
            fontproperties=font_coords,
            size=11 * scale_factor,
            zorder=21,
        )

        # Clip all map collections to the map bounding box (0.05 to 0.95, 0.17 to 0.83)
        clip_rect = patches.Rectangle((0.05, 0.17), 0.90, 0.66, transform=ax.transAxes)
        for col in ax.collections:
            col.set_clip_path(clip_rect)
        for patch in ax.patches:
            if patch.get_zorder() is not None and patch.get_zorder() < 10:
                patch.set_clip_path(clip_rect)

        # Draw top title block
        if has_text:
            # Massive title in Playfair Display
            # Draw vertical arrow lines on left and right of the title area (x=0.15, 0.85)
            # Arrow height from y=0.86 to 0.94
            ax.annotate(
                "",
                xy=(0.15, 0.86),
                xytext=(0.15, 0.94),
                arrowprops=dict(
                    arrowstyle="<->",
                    color="#FFFFFF",
                    linewidth=1 * scale_factor,
                    alpha=0.9,
                ),
                transform=ax.transAxes,
            )
            ax.annotate(
                "",
                xy=(0.85, 0.86),
                xytext=(0.85, 0.94),
                arrowprops=dict(
                    arrowstyle="<->",
                    color="#FFFFFF",
                    linewidth=1 * scale_factor,
                    alpha=0.9,
                ),
                transform=ax.transAxes,
            )
            # Horizontal connecting dashed line
            ax.plot(
                [0.15, 0.85],
                [0.86, 0.86],
                color="#FFFFFF",
                linestyle="--",
                linewidth=1 * scale_factor,
                alpha=0.8,
                transform=ax.transAxes,
            )

            # Draw city title centered at y=0.88 (huge and sketchy or bold)
            ax.text(
                0.5,
                0.88,
                display_city.upper(),
                transform=ax.transAxes,
                color="#FFFFFF",
                ha="center",
                fontproperties=font_main_adjusted,
                size=adjusted_font_size * 1.5,
                zorder=15,
            )
            ax.text(
                0.5,
                0.84,
                "SCALE 1:25,000 | BLUEPRINT-MAP-N°8",
                transform=ax.transAxes,
                color="#FFFFFF",
                alpha=0.9,
                ha="center",
                fontproperties=font_coords,
                size=10 * scale_factor,
                zorder=15,
            )

        # Draw bottom-left stats data box
        # Box from x=0.05 to 0.49, y=0.03 to 0.12 (increased for larger text)
        # Draw double border for technical data box
        rect_outer = patches.Rectangle(
            (0.05, 0.03),
            0.44,
            0.09,
            facecolor="none",
            edgecolor="#FFFFFF",
            linewidth=2 * scale_factor,
            transform=ax.transAxes,
            zorder=12,
        )
        ax.add_patch(rect_outer)
        rect_inner = patches.Rectangle(
            (0.053, 0.033),
            0.434,
            0.084,
            facecolor="none",
            edgecolor="#FFFFFF",
            linewidth=0.8 * scale_factor,
            transform=ax.transAxes,
            zorder=13,
        )
        ax.add_patch(rect_inner)

        # Technical text lines inside the box
        dms_coords = format_coords_dms(lat, lon)
        lines = [
            display_city.upper(),
            f'"{display_country.upper()}"',
            f"COORDS: {dms_coords}",
            f"VIEWPORT: {map_w_km:.2f} KM x {map_h_km:.2f} KM",
            f"PROJ: TRANSVERSE MERCATOR / WGS 84",
            "GRID REF: UTM-ZONE-54N",
        ]

        y_positions = [0.104, 0.091, 0.078, 0.065, 0.052, 0.040]
        # Make fonts for lines inside the box (substantially enlarged!)
        font_box_title = (
            FontProperties(fname=active_fonts["bold"], size=15 * scale_factor)
            if active_fonts
            else FontProperties(
                family="monospace", weight="bold", size=15 * scale_factor
            )
        )
        font_box_sub = (
            FontProperties(fname=active_fonts["light"], size=12 * scale_factor)
            if active_fonts
            else FontProperties(family="monospace", size=12 * scale_factor)
        )
        font_box_regular = (
            FontProperties(fname=active_fonts["regular"], size=10 * scale_factor)
            if active_fonts
            else FontProperties(family="monospace", size=10 * scale_factor)
        )

        for idx, line_text in enumerate(lines):
            line_y = y_positions[idx]
            line_font = (
                font_box_title
                if idx == 0
                else (font_box_sub if idx == 1 else font_box_regular)
            )
            ax.text(
                0.06,
                line_y,
                line_text,
                transform=ax.transAxes,
                color="#FFFFFF",
                ha="left",
                va="center",
                fontproperties=line_font,
                zorder=15,
            )

        # Draw the compass rose in the bottom-right corner (doubled radius to 0.065, shifted y to 0.095) -> Now radius 0.055, y to 0.082
        draw_compass_rose(
            ax, 0.85, 0.082, 0.055, "#FFFFFF", THEME["bg"], font_props=font_coords
        )

    else:
        # Standard borders and text rendering
        # --- DECORATIVE BORDERS, BOXES, AND COMPASS FOR VINTAGE LAYOUT ---
        if THEME.get("layout") == "vintage":
            # Draw double outer border around the map poster canvas
            ax.plot(
                [0.015, 0.985, 0.985, 0.015, 0.015],
                [0.015, 0.015, 0.985, 0.985, 0.015],
                color=THEME["text"],
                linewidth=3 * scale_factor,
                transform=ax.transAxes,
                zorder=20,
            )
            ax.plot(
                [0.02, 0.98, 0.98, 0.02, 0.02],
                [0.02, 0.02, 0.98, 0.98, 0.02],
                color=THEME["text"],
                linewidth=1 * scale_factor,
                transform=ax.transAxes,
                zorder=20,
            )

            if THEME.get("watercolor"):
                # Draw the wide rounded bottom bar only if text is present
                if has_text:
                    bar_y = 0.85 if text_position == "top" else 0.04
                    # Background fill
                    bottom_bar_bg = patches.FancyBboxPatch(
                        (0.04, bar_y),
                        0.92,
                        0.11,
                        boxstyle="round,pad=0.005,rounding_size=0.015",
                        facecolor=THEME["bg"],
                        edgecolor="none",
                        alpha=0.75,
                        transform=ax.transAxes,
                        zorder=12,
                    )
                    ax.add_patch(bottom_bar_bg)

                    # Outer border outline
                    bottom_bar_outer = patches.FancyBboxPatch(
                        (0.04, bar_y),
                        0.92,
                        0.11,
                        boxstyle="round,pad=0.005,rounding_size=0.015",
                        facecolor="none",
                        edgecolor=THEME["text"],
                        linewidth=3 * scale_factor,
                        transform=ax.transAxes,
                        zorder=13,
                    )
                    ax.add_patch(bottom_bar_outer)

                    # Inner nested border outline
                    bottom_bar_inner = patches.FancyBboxPatch(
                        (0.044, bar_y + 0.004),
                        0.912,
                        0.102,
                        boxstyle="round,pad=0.005,rounding_size=0.012",
                        facecolor="none",
                        edgecolor=THEME["text"],
                        linewidth=1 * scale_factor,
                        transform=ax.transAxes,
                        zorder=14,
                    )
                    ax.add_patch(bottom_bar_inner)
            else:
                if show_text or THEME.get("layout") == "blueprint":
                    # Draw the standard vintage label box centered at the bottom (compact dimensions)
                    box_bg = THEME.get("box_bg", THEME["bg"])
                    box_y = 0.86 if text_position == "top" else 0.04
                    # Outer box filled
                    rect_outer = patches.Rectangle(
                        (0.30, box_y),
                        0.40,
                        0.10,
                        facecolor=box_bg,
                        edgecolor=THEME["text"],
                        linewidth=3 * scale_factor,
                        transform=ax.transAxes,
                        zorder=12,
                    )
                    ax.add_patch(rect_outer)
                    # Inner box outline
                    rect_inner = patches.Rectangle(
                        (0.304, box_y + 0.004),
                        0.392,
                        0.092,
                        facecolor="none",
                        edgecolor=THEME["text"],
                        linewidth=1 * scale_factor,
                        transform=ax.transAxes,
                        zorder=13,
                    )
                    ax.add_patch(rect_inner)

            # Draw the compass rose in the top-right corner or bottom-right corner if text is top
            if show_text or THEME.get("layout") == "blueprint":
                compass_y = 0.12 if text_position == "top" else 0.88
                draw_compass_rose(
                    ax,
                    0.88,
                    compass_y,
                    0.05,
                    THEME["text"],
                    THEME["bg"],
                    font_props=font_coords,
                )

        # --- BOTTOM TEXT ---
        if has_text:
            if city_y is not None:
                ax.text(
                    0.5,
                    city_y,
                    spaced_city,
                    transform=ax.transAxes,
                    color=THEME["text"],
                    ha="center",
                    fontproperties=font_main_adjusted,
                    zorder=text_zorder,
                )

            if country_y is not None and spaced_country:
                ax.text(
                    0.5,
                    country_y,
                    spaced_country,
                    transform=ax.transAxes,
                    color=THEME["text"],
                    ha="center",
                    fontproperties=font_sub,
                    zorder=text_zorder,
                )

        if coords_y is not None and coords:
            ax.text(
                0.5,
                coords_y,
                coords,
                transform=ax.transAxes,
                color=THEME["text"],
                alpha=(
                    0.7 if THEME.get("layout") != "vintage" else 0.9
                ),  # slightly higher opacity for readability on paper
                ha="center",
                fontproperties=font_coords,
                zorder=text_zorder,
            )

    if THEME.get("layout") not in ["vintage", "blueprint"] and (
        show_text or THEME.get("layout") == "blueprint"
    ):
        sep_y = 0.875 if text_position == "top" else 0.125
        ax.plot(
            [0.4, 0.6],
            [sep_y, sep_y],
            transform=ax.transAxes,
            color=THEME["text"],
            linewidth=1 * scale_factor,
            zorder=11,
        )

    # --- ATTRIBUTION (bottom right) ---
    # if FONTS:
    #     font_attr = FontProperties(fname=FONTS["light"], size=8)
    # else:
    #     font_attr = FontProperties(family="monospace", size=8)

    # attr_x = 0.975 if THEME.get("layout") == "vintage" else 0.98
    # attr_y = 0.03 if THEME.get("layout") == "vintage" else 0.02

    # ax.text(
    #     attr_x,
    #     attr_y,
    #     "© OpenStreetMap contributors",
    #     transform=ax.transAxes,
    #     color=THEME["text"],
    #     alpha=0.5,
    #     ha="right",
    #     va="bottom",
    #     fontproperties=font_attr,
    #     zorder=11,
    # )

    # 5. Save
    import io

    in_memory = output_file is None
    if in_memory:
        output_file_name_for_hash = f"map_{city}_{THEME.get('name', 'theme')}"
        buf = io.BytesIO()
        dest = buf
    else:
        output_file_name_for_hash = output_file
        dest = output_file
        print(f"Saving to {output_file}...")

    fmt = output_format.lower()
    save_kwargs = dict(
        facecolor=THEME["bg"] if not THEME.get("watercolor") else DEEP_OCEAN,
        bbox_inches="tight",
        pad_inches=0.05,
    )

    # DPI matters mainly for raster formats
    if fmt == "png":
        save_kwargs["dpi"] = 300

    plt.savefig(dest, format=fmt, **save_kwargs)
    plt.close()

    # Apply texture post-processing
    post_process = THEME.get(
        "post_process", "vintage" if THEME.get("layout") == "vintage" else None
    )

    if post_process in ["vintage", "dark_paper"] and fmt == "png":
        try:
            print(
                f"Applying {post_process} paper texture and vignette post-processing..."
            )
            from PIL import Image
            import hashlib

            # Load the saved map image
            if in_memory:
                buf.seek(0)
                img = Image.open(buf)
            else:
                img = Image.open(output_file)
            width, height = img.size

            # 1. Generate fine paper grain (half-resolution for speed/smoothness)
            fine_w, fine_h = width // 2, height // 2

            # Set random seed based on filename hash to make texture reproducible yet unique
            seed = int(
                hashlib.md5(output_file_name_for_hash.encode("utf-8")).hexdigest()[:8],
                16,
            )
            np.random.seed(seed)

            # Generate fine grain
            fine_grain = np.random.normal(128, 12, (fine_h, fine_w))
            fine_img = Image.fromarray(fine_grain.astype(np.uint8), mode="L")
            fine_img = fine_img.resize(
                (width, height), resample=Image.Resampling.BILINEAR
            )
            fine_arr = np.array(fine_img, dtype=float)

            # 2. Generate organic paper blotches (low-frequency noise)
            blotches_w, blotches_h = width // 16, height // 16
            blotches = np.random.normal(128, 14, (blotches_h, blotches_w))
            blotches_img = Image.fromarray(blotches.astype(np.uint8), mode="L")
            blotches_img = blotches_img.resize(
                (width, height), resample=Image.Resampling.BILINEAR
            )
            blotches_arr = np.array(blotches_img, dtype=float)

            # Combine them: 60% fine grain, 40% blotches
            combined_noise = 0.6 * fine_arr + 0.4 * blotches_arr

            # Normalize and scale to range around 1.0 (e.g. 0.82 to 1.18 for stronger grain)
            noise_factor = 0.82 + 0.36 * (combined_noise / 255.0)

            # 3. Generate a soft radial vignette (darker edges)
            x = np.linspace(-1, 1, width)
            y = np.linspace(-1, 1, height)
            X, Y = np.meshgrid(x, y)
            d = np.sqrt(X**2 + Y**2)
            img_rgb = img.convert("RGB")
            img_arr = np.array(img_rgb, dtype=float)

            if post_process == "vintage":
                # Vignette factor: starts fading at 0.4 radius, corners reach about 0.65 intensity
                vignette_arr = 1.0 - 0.35 * np.clip(
                    (d - 0.4) / (np.sqrt(2) - 0.4), 0, 1
                )
                # Sepia / warm staining vignette (warm corners)
                vignette_r = vignette_arr
                vignette_g = vignette_arr * 0.97
                vignette_b = vignette_arr * 0.92

                # Apply noise and vignette everywhere
                img_arr[:, :, 0] *= noise_factor * vignette_r
                img_arr[:, :, 1] *= noise_factor * vignette_g
                img_arr[:, :, 2] *= noise_factor * vignette_b
            elif post_process == "dark_paper":
                # dark_paper: NO vignette, and grain is ONLY applied to the water!
                water_hex = THEME.get("water", "#000000").lstrip("#")
                water_rgb = tuple(int(water_hex[i : i + 2], 16) for i in (0, 2, 4))

                # Calculate distance from each pixel to the water color
                diff = np.abs(img_arr - np.array(water_rgb, dtype=float))
                dist = np.sum(diff, axis=2)

                # Soft mask: 1.0 where exactly water, fading to 0.0 at a distance of 30
                water_mask = np.clip(1.0 - (dist / 30.0), 0, 1)

                # Apply noise only to water masked areas
                img_arr[:, :, 0] = (
                    img_arr[:, :, 0] * (1 - water_mask)
                    + (img_arr[:, :, 0] * noise_factor) * water_mask
                )
                img_arr[:, :, 1] = (
                    img_arr[:, :, 1] * (1 - water_mask)
                    + (img_arr[:, :, 1] * noise_factor) * water_mask
                )
                img_arr[:, :, 2] = (
                    img_arr[:, :, 2] * (1 - water_mask)
                    + (img_arr[:, :, 2] * noise_factor) * water_mask
                )

            # Clip values to [0, 255] and convert back to uint8
            img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)
            final_img = Image.fromarray(img_arr)

            # Save back
            if in_memory:
                out_buf = io.BytesIO()
                final_img.save(out_buf, format="PNG")
                buf = out_buf
            else:
                final_img.save(output_file, format="PNG")
                print("Vintage post-processing completed successfully!")
        except Exception as e:
            print(f"⚠ Warning: Vintage post-processing failed: {e}")

    # Apply mystic gold post-processing (deep vignette and canvas texture)
    if THEME.get("layout") == "mystic_gold" and fmt == "png":
        try:
            print("Applying mystic gold canvas texture and vignette...")
            from PIL import Image

            if in_memory:
                buf.seek(0)
                img = Image.open(buf)
            else:
                img = Image.open(output_file)
            width, height = img.size

            # 1. Very fine canvas noise
            noise = np.random.normal(128, 8, (height, width))
            noise_img = Image.fromarray(noise.astype(np.uint8), mode="L")
            noise_arr = np.array(noise_img, dtype=float)
            noise_factor = 0.90 + 0.20 * (noise_arr / 255.0)

            # 2. Deep vignette (very dark edges)
            x = np.linspace(-1, 1, width)
            y = np.linspace(-1, 1, height)
            X, Y = np.meshgrid(x, y)
            d = np.sqrt(X**2 + Y**2)
            vignette = 1.0 - 0.7 * np.clip((d - 0.5) / (np.sqrt(2) - 0.5), 0, 1)

            # Apply
            img_rgb = img.convert("RGB")
            img_arr = np.array(img_rgb, dtype=float)
            for c in range(3):
                img_arr[:, :, c] *= noise_factor * vignette

            img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)
            final_img = Image.fromarray(img_arr)
            if in_memory:
                out_buf = io.BytesIO()
                final_img.save(out_buf, format="PNG")
                buf = out_buf
            else:
                final_img.save(output_file, format="PNG")
                print("Mystic Gold post-processing completed successfully!")
        except Exception as e:
            print(f"Warning: Mystic Gold post-processing failed: {e}")

    if in_memory:
        buf.seek(0)
        return buf.getvalue()
    else:
        print(f"Done! Poster saved as {output_file}")


def print_examples():
    """Print usage examples."""
    print(
        """
City Map Poster Generator
=========================

Usage:
  python create_map_poster.py --city <city> --country <country> [options]

Examples:
  # Iconic grid patterns
  python create_map_poster.py -c "New York" -C "USA" -t noir -d 12000           # Manhattan grid
  python create_map_poster.py -c "Barcelona" -C "Spain" -t warm_beige -d 8000   # Eixample district grid

  # Waterfront & canals
  python create_map_poster.py -c "Venice" -C "Italy" -t blueprint -d 4000       # Canal network
  python create_map_poster.py -c "Amsterdam" -C "Netherlands" -t ocean -d 6000  # Concentric canals
  python create_map_poster.py -c "Dubai" -C "UAE" -t midnight_blue -d 15000     # Palm & coastline

  # Radial patterns
  python create_map_poster.py -c "Paris" -C "France" -t pastel_dream -d 10000   # Haussmann boulevards
  python create_map_poster.py -c "Moscow" -C "Russia" -t noir -d 12000          # Ring roads

  # Organic old cities
  python create_map_poster.py -c "Tokyo" -C "Japan" -t japanese_ink -d 15000    # Dense organic streets
  python create_map_poster.py -c "Marrakech" -C "Morocco" -t terracotta -d 5000 # Medina maze
  python create_map_poster.py -c "Rome" -C "Italy" -t warm_beige -d 8000        # Ancient street layout

  # Coastal cities
  python create_map_poster.py -c "San Francisco" -C "USA" -t sunset -d 10000    # Peninsula grid
  python create_map_poster.py -c "Sydney" -C "Australia" -t ocean -d 12000      # Harbor city
  python create_map_poster.py -c "Mumbai" -C "India" -t contrast_zones -d 18000 # Coastal peninsula

  # River cities
  python create_map_poster.py -c "London" -C "UK" -t noir -d 15000              # Thames curves
  python create_map_poster.py -c "Budapest" -C "Hungary" -t copper_patina -d 8000  # Danube split

  # List themes
  python create_map_poster.py --list-themes

Options:
  --city, -c        City name (required)
  --country, -C     Country name (required)
  --country-label   Override country text displayed on poster
  --theme, -t       Theme name (default: terracotta)
  --all-themes      Generate posters for all themes
  --distance, -d    Map radius in meters (default: 18000)
  --list-themes     List all available themes

Distance guide:
  4000-6000m   Small/dense cities (Venice, Amsterdam old center)
  8000-12000m  Medium cities, focused downtown (Paris, Barcelona)
  15000-20000m Large metros, full city view (Tokyo, Mumbai)

Available themes can be found in the 'themes/' directory.
Generated posters are saved to 'posters/' directory.
"""
    )


def list_themes():
    """List all available themes with descriptions."""
    available_themes = get_available_themes()
    if not available_themes:
        print("No themes found in 'themes/' directory.")
        return

    print("\nAvailable Themes:")
    print("-" * 60)
    for theme_name in available_themes:
        theme_path = os.path.join(THEMES_DIR, f"{theme_name}.json")
        try:
            with open(theme_path, "r", encoding=FILE_ENCODING) as f:
                theme_data = json.load(f)
                display_name = theme_data.get("name", theme_name)
                description = theme_data.get("description", "")
        except (OSError, json.JSONDecodeError):
            display_name = theme_name
            description = ""
        print(f"  {theme_name}")
        print(f"    {display_name}")
        if description:
            print(f"    {description}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate beautiful map posters for any city",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_map_poster.py --city "New York" --country "USA"
  python create_map_poster.py --city "New York" --country "USA" -l 40.776676 -73.971321 --theme neon_cyberpunk
  python create_map_poster.py --city Tokyo --country Japan --theme midnight_blue
  python create_map_poster.py --city Paris --country France --theme noir --distance 15000
  python create_map_poster.py --list-themes
        """,
    )

    parser.add_argument("--city", "-c", type=str, help="City name")
    parser.add_argument("--country", "-C", type=str, help="Country name")
    parser.add_argument(
        "--latitude",
        "-lat",
        dest="latitude",
        type=str,
        help="Override latitude center point",
    )
    parser.add_argument(
        "--longitude",
        "-long",
        dest="longitude",
        type=str,
        help="Override longitude center point",
    )
    parser.add_argument(
        "--country-label",
        dest="country_label",
        type=str,
        help="Override country text displayed on poster",
    )
    parser.add_argument(
        "--theme",
        "-t",
        type=str,
        default="terracotta",
        help="Theme name (default: terracotta)",
    )
    parser.add_argument(
        "--all-themes",
        "--All-themes",
        dest="all_themes",
        action="store_true",
        help="Generate posters for all themes",
    )
    parser.add_argument(
        "--distance",
        "-d",
        type=int,
        default=18000,
        help="Map radius in meters (default: 18000)",
    )
    parser.add_argument(
        "--width",
        "-W",
        type=float,
        default=12,
        help="Image width in inches (default: 12, max: 20 )",
    )
    parser.add_argument(
        "--height",
        "-H",
        type=float,
        default=16,
        help="Image height in inches (default: 16, max: 20)",
    )
    parser.add_argument(
        "--buildings",
        "-b",
        action="store_true",
        help="Draw highly detailed building footprints",
    )
    parser.add_argument(
        "--transit",
        "-T",
        action="store_true",
        help="Draw subway and metro transit lines",
    )
    parser.add_argument(
        "--contours",
        action="store_true",
        help="Draw topography contour lines in the background",
    )
    parser.add_argument(
        "--list-themes", action="store_true", help="List all available themes"
    )
    parser.add_argument(
        "--display-city",
        "-dc",
        type=str,
        help="Custom display name for city (for i18n support)",
    )
    parser.add_argument(
        "--display-country",
        "-dC",
        type=str,
        help="Custom display name for country (for i18n support)",
    )
    parser.add_argument(
        "--font-family",
        type=str,
        help='Google Fonts family name (e.g., "Noto Sans JP", "Open Sans"). If not specified, uses local Roboto fonts.',
    )
    parser.add_argument(
        "--format",
        "-f",
        default="png",
        choices=["png", "svg", "pdf"],
        help="Output format for the poster (default: png)",
    )

    # Custom Marker
    parser.add_argument("--marker-lat", type=float, help="Latitude for custom marker")
    parser.add_argument("--marker-lon", type=float, help="Longitude for custom marker")
    parser.add_argument(
        "--marker-style",
        type=str,
        default="pin",
        help="Marker style (e.g. pin, heart, dot)",
    )
    parser.add_argument(
        "--marker-color",
        type=str,
        default="#E74C3C",
        help="Hex color for custom marker",
    )

    args = parser.parse_args()

    # If no arguments provided, show examples
    if len(sys.argv) == 1:
        print_examples()
        sys.exit(0)

    # List themes if requested
    if args.list_themes:
        list_themes()
        sys.exit(0)

    # Validate required arguments
    if not args.city or not args.country:
        print("Error: --city and --country are required.\n")
        print_examples()
        sys.exit(1)

    # Enforce maximum dimensions
    if args.width > 20:
        print(
            f"⚠ Width {args.width} exceeds the maximum allowed limit of 20. It's enforced as max limit 20."
        )
        args.width = 20.0
    if args.height > 20:
        print(
            f"⚠ Height {args.height} exceeds the maximum allowed limit of 20. It's enforced as max limit 20."
        )
        args.height = 20.0

    available_themes = get_available_themes()
    if not available_themes:
        print("No themes found in 'themes/' directory.")
        sys.exit(1)

    if args.all_themes:
        themes_to_generate = available_themes
    else:
        if args.theme not in available_themes:
            print(f"Error: Theme '{args.theme}' not found.")
            print(f"Available themes: {', '.join(available_themes)}")
            sys.exit(1)
        themes_to_generate = [args.theme]

    print("=" * 50)
    print("City Map Poster Generator")
    print("=" * 50)

    # Load custom fonts if specified
    custom_fonts = None
    if args.font_family:
        custom_fonts = load_fonts(args.font_family)
        if not custom_fonts:
            print(f"⚠ Failed to load '{args.font_family}', falling back to Roboto")

    # Get coordinates and generate poster
    try:
        if args.latitude and args.longitude:
            lat = parse(args.latitude)
            lon = parse(args.longitude)
            coords = [lat, lon]
            print(f"✓ Coordinates: {', '.join([str(i) for i in coords])}")
        else:
            coords = get_coordinates(args.city, args.country)

        for theme_name in themes_to_generate:
            THEME = load_theme(theme_name)
            output_file = generate_output_filename(args.city, theme_name, args.format)

            # Determine font to use: command-line overrides theme font
            theme_fonts = custom_fonts
            if not theme_fonts and THEME.get("font_family"):
                print(
                    f"Theme '{theme_name}' requests font family: {THEME['font_family']}"
                )
                theme_fonts = load_fonts(THEME["font_family"])
                if not theme_fonts:
                    print(
                        f"⚠ Failed to load '{THEME['font_family']}', falling back to Roboto"
                    )

            create_poster(
                args.city,
                args.country,
                coords,
                args.distance,
                output_file,
                args.format,
                args.width,
                args.height,
                country_label=args.country_label,
                display_city=args.display_city,
                display_country=args.display_country,
                fonts=theme_fonts,
                draw_buildings=args.buildings,
                draw_transit=args.transit,
                draw_contours=args.contours,
                marker_lat=args.marker_lat,
                marker_lon=args.marker_lon,
                marker_style=args.marker_style,
                marker_color=args.marker_color,
            )

        print("\nPoster generation complete!")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
