#!/usr/bin/env python3
"""
Unified Map & Poster CLI Generator

Generates custom maps in both Classic prettymapp vector style and high-end Poster style.
Supports full CLI customization for location, coordinates, themes, fonts, text placement,
contour widths, shapes, background colors, and output formats.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure UTF-8 console output on Windows
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

# Add project root and poster_generator to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "poster_generator"))

from prettymapp.geo import get_aoi
from prettymapp.osm import get_osm_geometries
from prettymapp.plotting import Plot
from prettymapp.settings import STYLES

import create_map_poster
from create_map_poster import create_poster, load_theme, get_available_themes
from font_management import load_fonts


def list_all_themes():
    """Print all available classic and poster themes."""
    print("AVAILABLE MAP THEMES")

    print("\nCLASSIC VECTOR THEMES:")
    for style_name in STYLES.keys():
        print(f"  * {style_name}")

    print("\nPOSTER THEMES (30+):")
    poster_themes = get_available_themes()
    for theme in sorted(poster_themes):
        print(f"  * {theme}")


def generate_classic_map(args):
    """Generate map using Classic prettymapp style."""
    print("Generating Classic map...")

    # Resolve location / coordinates
    address = args.location or args.address
    coords = None
    if args.latitude is not None and args.longitude is not None:
        coords = (args.latitude, args.longitude)
        address = None
    elif not address and (args.city or args.country):
        parts = [p for p in [args.city, args.country] if p]
        address = ", ".join(parts)

    if not address and not coords:
        raise ValueError(
            "Location required! Use --location 'City, Country' or --latitude/--longitude coordinates."
        )

    location_desc = address if address else f"({args.latitude}, {args.longitude})"
    print(f"Location: {location_desc}")
    print(f"Radius: {args.radius} meters")

    # 1. Get Area of Interest
    is_rectangular = args.shape == "rectangle"
    aoi = get_aoi(
        address=address,
        coordinates=coords,
        radius=args.radius,
        rectangular=is_rectangular,
    )

    # 2. Get Geometries
    print("Fetching OpenStreetMap data...")
    df = get_osm_geometries(aoi=aoi)

    # 3. Resolve Draw Settings / Style
    theme_key = args.theme or "Peach"
    if theme_key in STYLES:
        draw_settings = STYLES[theme_key].copy()
    else:
        print(f"Theme '{theme_key}' not in Classic themes, using default 'Peach'.")
        draw_settings = STYLES["Peach"].copy()

    # Title / Text
    title_text = args.title or (address.split(",")[0] if address else "Map")
    name_on = args.show_text and bool(title_text)

    # Background shape & buffer
    bg_shape_val = None if args.bg_shape == "none" else args.bg_shape

    print(
        f"Rendering map (Shape: {args.shape}, Contour Width: {args.contour_width})..."
    )
    plotter = Plot(
        df=df,
        aoi_bounds=aoi.bounds,
        draw_settings=draw_settings,
        shape=args.shape,
        contour_width=args.contour_width,
        contour_color=args.contour_color,
        name_on=name_on,
        name=title_text,
        font_size=args.font_size,
        font_color=args.font_color,
        bg_shape=bg_shape_val,
        bg_color=args.bg_color,
        bg_buffer=args.bg_buffer,
        dpi=args.dpi,
    )

    fig = plotter.plot_all()

    # Output file
    output_path = args.output
    if not output_path:
        os.makedirs("output", exist_ok=True)
        city_slug = title_text.lower().replace(" ", "_")
        output_path = os.path.join(
            "output", f"classic_{city_slug}_{theme_key.lower()}.png"
        )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    fig.savefig(output_path, dpi=args.dpi)
    print(f"Successfully saved Classic map to {output_path}")
    return output_path


def generate_poster_map(args):
    """Generate map using Poster Generator style."""
    print("Generating Poster map...")

    city = args.city
    country = args.country

    if not city and args.location:
        parts = [p.strip() for p in args.location.split(",")]
        city = parts[0]
        country = parts[-1] if len(parts) > 1 else ""
    elif not city:
        city = "City"
        country = "Country"

    point = None
    if args.latitude is not None and args.longitude is not None:
        point = (args.latitude, args.longitude)

    theme_name = args.theme or "terracotta"
    create_map_poster.THEME = load_theme(theme_name)

    print(f"Location: {city}, {country}")
    print(f"Poster Theme: {theme_name}")
    print(f"Distance: {args.radius} meters")

    fonts = load_fonts(args.font_family) if args.font_family else None

    fig = create_poster(
        city=city,
        country=country,
        point=point,
        dist=args.radius,
        output_file=args.output,
        output_format=args.output_format,
        width=args.width,
        height=args.height,
        display_city=args.title,
        display_country=args.subtitle,
        fonts=fonts,
        draw_buildings=args.draw_buildings,
        draw_transit=args.draw_transit,
        draw_contours=args.draw_contours,
        text_position=args.text_position,
        show_text=args.show_text,
    )

    output_path = args.output
    if not output_path:
        output_path = f"posters/{city.lower()}_{theme_name}.png"

    print(f"Successfully saved Poster map to {output_path}")
    return output_path


def read_single_key():
    """Read a single keypress or arrow key event from terminal."""
    if os.name == "nt":
        import msvcrt

        try:
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ch2 = msvcrt.getch()
                if ch2 == b"H":
                    return "UP"
                elif ch2 == b"P":
                    return "DOWN"
                elif ch2 == b"K":
                    return "LEFT"
                elif ch2 == b"M":
                    return "RIGHT"
                return ""
            elif ch in (b"\r", b"\n"):
                return "ENTER"
            elif ch == b"\x1b":
                return "ESC"
            elif ch == b"\x08":
                return "BACKSPACE"
            else:
                try:
                    return ch.decode("utf-8", errors="ignore")
                except Exception:
                    return ""
        except Exception:
            return ""
    else:
        import sys, tty, termios

        try:
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    ch2 = sys.stdin.read(1)
                    ch3 = sys.stdin.read(1)
                    if ch2 == "[":
                        if ch3 == "A":
                            return "UP"
                        elif ch3 == "B":
                            return "DOWN"
                        elif ch3 == "C":
                            return "RIGHT"
                        elif ch3 == "D":
                            return "LEFT"
                    return "ESC"
                elif ch in ("\r", "\n"):
                    return "ENTER"
                elif ch in ("\x7f", "\x08"):
                    return "BACKSPACE"
                else:
                    return ch
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            return ""


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    BOLD_CYAN = "\033[1;36m"
    GREEN = "\033[32m"
    BOLD_GREEN = "\033[1;32m"
    YELLOW = "\033[33m"
    BOLD_YELLOW = "\033[1;33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    HIGHLIGHT = "\033[1;30;46m"  # Black text on bright Cyan background
    DIM = "\033[2m"


def print_card_header(title, width=70):
    border = Colors.BOLD_CYAN + "+" + "-" * (width - 2) + "+" + Colors.RESET
    padded = title.center(width - 2)
    content = (
        Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
        + Colors.BOLD_YELLOW
        + padded
        + Colors.RESET
        + Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
    )
    print(border)
    print(content)
    print(border)


def print_step_banner(step_num, title, width=70):
    banner_text = f" [STEP {step_num}/6] {title.upper()} "
    print("\n" + Colors.BOLD_CYAN + banner_text.ljust(width, "-") + Colors.RESET)


def interactive_select(title, options, default_idx=0):
    """Interactive arrow-key selection menu with cursor highlight."""
    if not sys.stdin.isatty():
        print(f"\n{Colors.BOLD_CYAN}{title}{Colors.RESET}")
        for idx, opt in enumerate(options, 1):
            print(f"  [{idx}] {opt}")
        choice = input(
            f"Select choice (1-{len(options)}, default {default_idx+1}): "
        ).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        return default_idx

    current_idx = default_idx
    max_visible = 12
    scroll_offset = 0

    while True:
        try:
            os.system("cls" if os.name == "nt" else "clear")
        except Exception:
            pass

        print_card_header(title)
        print(
            f" {Colors.DIM}Controls:{Colors.RESET} {Colors.BOLD_YELLOW}[UP / DOWN]{Colors.RESET} {Colors.DIM}Arrow Keys = Navigate Cursor |{Colors.RESET} {Colors.BOLD_GREEN}[ENTER]{Colors.RESET} {Colors.DIM}= Confirm Selection{Colors.RESET}\n"
        )

        # Adjust scroll window for large lists (like 30+ themes)
        if current_idx < scroll_offset:
            scroll_offset = current_idx
        elif current_idx >= scroll_offset + max_visible:
            scroll_offset = current_idx - max_visible + 1

        visible_options = options[scroll_offset : scroll_offset + max_visible]

        for i, opt in enumerate(visible_options):
            idx = scroll_offset + i
            if idx == current_idx:
                print(
                    f"  {Colors.HIGHLIGHT} >> [ {opt.upper()} ] {Colors.RESET} {Colors.BOLD_GREEN}<-- (SELECTED){Colors.RESET}"
                )
            else:
                print(f"     {Colors.CYAN}[ {opt} ]{Colors.RESET}")

        if len(options) > max_visible:
            print(
                f"\n   {Colors.DIM}-- (Showing {scroll_offset+1}-{min(scroll_offset+max_visible, len(options))} of {len(options)} options. Use arrows to scroll) --{Colors.RESET}"
            )

        print("\n" + Colors.BOLD_CYAN + "-" * 70 + Colors.RESET)

        key = read_single_key()
        if key == "UP":
            current_idx = (current_idx - 1) % len(options)
        elif key == "DOWN":
            current_idx = (current_idx + 1) % len(options)
        elif key == "ENTER":
            return current_idx


def run_interactive_cli_wizard(args, parser):
    """Keyboard-navigable terminal studio wizard."""
    # Step 1: Mode Selection
    mode_options = [
        "Poster Artwork (Print-ready minimalist city poster)",
        "Classic Vector Map (High-contrast OSM spatial vector map)",
    ]
    mode_idx = interactive_select(
        "STEP 1/6: MAP STYLE SELECTION", mode_options, default_idx=0
    )
    args.style = "poster" if mode_idx == 0 else "classic"

    # Step 2: Location Method Selection
    loc_options = [
        "City & Country Name (e.g. Paris, France)",
        "Full Address String (e.g. Shinjuku, Tokyo, Japan)",
        "GPS Coordinates (Exact Latitude & Longitude)",
    ]
    loc_idx = interactive_select(
        "STEP 2/6: LOCATION & GEOCODING METHOD", loc_options, default_idx=0
    )

    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass

    print_card_header(f"STEP 2/6: ENTER LOCATION DETAILS ({args.style.upper()} MODE)")
    if loc_idx == 2:
        lat_str = input(
            f"{Colors.BOLD_YELLOW}>> Enter Latitude (e.g. 48.8566): {Colors.RESET}"
        ).strip()
        long_str = input(
            f"{Colors.BOLD_YELLOW}>> Enter Longitude (e.g. 2.3522): {Colors.RESET}"
        ).strip()
        args.latitude = float(lat_str) if lat_str else 48.8566
        args.longitude = float(long_str) if long_str else 2.3522
        args.city = (
            input(
                f"{Colors.BOLD_YELLOW}>> City Title Label (default: Map): {Colors.RESET}"
            ).strip()
            or "Map"
        )
        args.country = (
            input(
                f"{Colors.BOLD_YELLOW}>> Country Subtitle Label (optional): {Colors.RESET}"
            ).strip()
            or ""
        )
    elif loc_idx == 1:
        args.location = (
            input(
                f"{Colors.BOLD_YELLOW}>> Enter Full Address / Location (default: Paris, France): {Colors.RESET}"
            ).strip()
            or "Paris, France"
        )
        parts = [p.strip() for p in args.location.split(",")]
        args.city = parts[0]
        args.country = parts[-1] if len(parts) > 1 else ""
    else:
        args.city = (
            input(
                f"{Colors.BOLD_YELLOW}>> Enter City Name (default: Paris): {Colors.RESET}"
            ).strip()
            or "Paris"
        )
        args.country = (
            input(
                f"{Colors.BOLD_YELLOW}>> Enter Country Name (default: France): {Colors.RESET}"
            ).strip()
            or "France"
        )
        args.location = f"{args.city}, {args.country}"

    # Step 3: Theme Selection Menu
    if args.style == "classic":
        available_themes = list(STYLES.keys())
        default_theme = "Auburn"
    else:
        available_themes = sorted(get_available_themes())
        default_theme = "terracotta"

    default_theme_idx = (
        available_themes.index(default_theme)
        if default_theme in available_themes
        else 0
    )
    theme_idx = interactive_select(
        f"STEP 3/6: COLOR THEME PRESET SELECTION ({args.style.upper()} MODE)",
        available_themes,
        default_idx=default_theme_idx,
    )
    args.theme = available_themes[theme_idx]

    # Step 4: Map Radius / Distance
    radius_options = [
        "12,000 meters - Full City & Coastal Views (Default)",
        "8,000 meters  - Medium Cities & Downtown Focus",
        "4,000 meters  - Small / Dense Historic Centers",
        "18,000 meters - Metropolitan Region",
        "Custom Distance Entry",
    ]
    rad_idx = interactive_select(
        "STEP 4/6: MAP RADIUS & DISTANCE SCALE", radius_options, default_idx=0
    )
    if rad_idx == 0:
        args.radius = 12000 if args.style == "poster" else 1200
    elif rad_idx == 1:
        args.radius = 8000
    elif rad_idx == 2:
        args.radius = 4000
    elif rad_idx == 3:
        args.radius = 18000
    else:
        try:
            os.system("cls" if os.name == "nt" else "clear")
        except Exception:
            pass
        print_card_header("CUSTOM RADIUS ENTRY")
        r_str = input(
            f"{Colors.BOLD_YELLOW}>> Enter radius in meters (e.g. 5000): {Colors.RESET}"
        ).strip()
        args.radius = int(r_str) if r_str.isdigit() else 12000

    # Step 5: Typography & Custom Labels
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass
    print_card_header("STEP 5/6: TYPOGRAPHY & LABEL CUSTOMIZATION")
    print(f"Current Title    : {Colors.BOLD_GREEN}{args.city}{Colors.RESET}")
    print(f"Current Subtitle : {Colors.BOLD_GREEN}{args.country}{Colors.RESET}\n")
    custom_title = input(
        f"{Colors.BOLD_YELLOW}>> Custom Title Text (press ENTER to keep '{args.city}'): {Colors.RESET}"
    ).strip()
    if custom_title:
        args.title = custom_title

    if args.style == "poster":
        custom_sub = input(
            f"{Colors.BOLD_YELLOW}>> Custom Subtitle Text (press ENTER to keep '{args.country}'): {Colors.RESET}"
        ).strip()
        if custom_sub:
            args.subtitle = custom_sub

        font_choice = input(
            f"{Colors.BOLD_YELLOW}>> Google Font Family (e.g. 'Noto Sans JP', 'Roboto', press ENTER for standard): {Colors.RESET}"
        ).strip()
        if font_choice:
            args.font_family = font_choice

    # Step 6: Output Path
    default_out = (
        f"output/{args.city.lower().replace(' ', '_')}_{args.theme.lower()}.png"
    )
    out_input = input(
        f"\n{Colors.BOLD_YELLOW}>> Output File Path (press ENTER for '{default_out}'): {Colors.RESET}"
    ).strip()
    args.output = out_input if out_input else default_out

    # Step 7: Confirmation Menu
    confirm_options = [
        f"START GENERATION NOW  --> Output: {args.output}",
        "CANCEL GENERATION",
    ]

    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass

    print_card_header("GENERATION CONFIGURATION SUMMARY")
    print(
        Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
        + f"  Style Mode   : {Colors.BOLD_YELLOW}{args.style.upper()}{Colors.RESET}".ljust(
            77
        )
        + Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
    )
    print(
        Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
        + f"  Target City  : {Colors.BOLD_GREEN}{args.city}, {args.country}{Colors.RESET}".ljust(
            77
        )
        + Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
    )
    if args.latitude is not None and args.longitude is not None:
        print(
            Colors.BOLD_CYAN
            + "|"
            + Colors.RESET
            + f"  Coordinates  : {Colors.BOLD_GREEN}{args.latitude}, {args.longitude}{Colors.RESET}".ljust(
                77
            )
            + Colors.BOLD_CYAN
            + "|"
            + Colors.RESET
        )
    print(
        Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
        + f"  Color Theme  : {Colors.BOLD_MAGENTA}{args.theme}{Colors.RESET}".ljust(77)
        + Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
    )
    print(
        Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
        + f"  Map Radius   : {Colors.BOLD_YELLOW}{args.radius:,} meters{Colors.RESET}".ljust(
            77
        )
        + Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
    )
    print(
        Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
        + f"  Output Path  : {Colors.BOLD_GREEN}{args.output}{Colors.RESET}".ljust(77)
        + Colors.BOLD_CYAN
        + "|"
        + Colors.RESET
    )
    print(Colors.BOLD_CYAN + "+" + "-" * 68 + "+" + Colors.RESET + "\n")

    action_idx = interactive_select(
        "CONFIRM GENERATION", confirm_options, default_idx=0
    )

    if action_idx == 0:
        print(
            f"\n{Colors.BOLD_GREEN}[+] Initializing spatial rendering pipeline...{Colors.RESET}\n"
        )
        if args.style == "classic":
            generate_classic_map(args)
        else:
            generate_poster_map(args)
    else:
        print(f"\n{Colors.BOLD_YELLOW}[-] Generation cancelled by user.{Colors.RESET}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Unified Map & Poster Generator CLI - Generate Classic & Poster Style Maps",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Interactive CLI Wizard flag
    parser.add_argument(
        "--run_cli",
        "--run-cli",
        "--cli",
        action="store_true",
        help="Launch interactive step-by-step terminal wizard",
    )

    # Utility flags
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="List all available classic and poster themes",
    )

    # Mode selection
    parser.add_argument(
        "-s",
        "--style",
        "--mode",
        choices=["classic", "poster"],
        default="classic",
        help="Map style mode: 'classic' (vector prettymapp) or 'poster' (minimalist poster artwork)",
    )

    # Location arguments
    parser.add_argument(
        "-l",
        "--location",
        "--address",
        type=str,
        help="Location address (e.g. 'Paris, France')",
    )
    parser.add_argument(
        "-c", "--city", type=str, help="City name (used for geocoding & poster title)"
    )
    parser.add_argument(
        "-C",
        "--country",
        type=str,
        help="Country name (used for geocoding & poster subtitle)",
    )
    parser.add_argument(
        "-lat", "--latitude", type=float, help="Latitude center coordinate override"
    )
    parser.add_argument(
        "-long", "--longitude", type=float, help="Longitude center coordinate override"
    )
    parser.add_argument(
        "-r",
        "-d",
        "--radius",
        "--distance",
        type=int,
        default=1200,
        help="Map radius / distance in meters",
    )

    # Theme selection
    parser.add_argument(
        "-t",
        "--theme",
        type=str,
        help="Theme preset name (e.g. 'Peach', 'Auburn', 'terracotta', 'blueprint_classic')",
    )

    # Typography & Text options
    parser.add_argument(
        "--title", "-dc", "--display-city", type=str, help="Custom map title text"
    )
    parser.add_argument(
        "--subtitle",
        "-dC",
        "--display-country",
        type=str,
        help="Custom map subtitle text",
    )
    parser.add_argument(
        "--font-family",
        type=str,
        help="Font family name (e.g. 'Noto Sans JP', 'Roboto', 'Permanent Marker')",
    )
    parser.add_argument(
        "--font-size", type=int, default=25, help="Font size for title (Classic mode)"
    )
    parser.add_argument(
        "--font-color",
        type=str,
        default="#2F3737",
        help="Font color hex code (Classic mode)",
    )
    parser.add_argument(
        "--text-position",
        choices=["Bottom", "Top", "bottom", "top"],
        default="Bottom",
        help="Text position (Poster mode)",
    )
    parser.add_argument(
        "--show-text", action="store_true", default=True, help="Display map text/labels"
    )
    parser.add_argument(
        "--hide-text",
        action="store_false",
        dest="show_text",
        help="Hide map text/labels",
    )

    # Custom Layout & Aesthetic controls (Classic mode)
    parser.add_argument(
        "--shape",
        choices=["circle", "rectangle"],
        default="circle",
        help="Map shape contour (Classic mode)",
    )
    parser.add_argument(
        "--contour-width",
        type=int,
        default=0,
        help="Contour border width (Classic mode)",
    )
    parser.add_argument(
        "--contour-color",
        type=str,
        default="#2F3537",
        help="Contour border color hex (Classic mode)",
    )
    parser.add_argument(
        "--bg-shape",
        choices=["rectangle", "circle", "none"],
        default="rectangle",
        help="Background shape (Classic mode)",
    )
    parser.add_argument(
        "--bg-color",
        type=str,
        default="#F2F4CB",
        help="Background color hex code (Classic mode)",
    )
    parser.add_argument(
        "--bg-buffer",
        type=int,
        default=2,
        help="Background buffer percentage (Classic mode)",
    )
    parser.add_argument("--dpi", type=int, default=300, help="DPI image resolution")

    # Dimension & Poster flags
    parser.add_argument(
        "-W", "--width", type=float, default=12.0, help="Poster width in inches"
    )
    parser.add_argument(
        "-H", "--height", type=float, default=16.0, help="Poster height in inches"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output image file path (e.g. 'output/my_map.png')",
    )
    parser.add_argument(
        "--output-format",
        choices=["png", "svg", "jpg"],
        default="png",
        help="Output file format",
    )

    # Geometry toggles
    parser.add_argument(
        "--draw-buildings", action="store_true", default=True, help="Draw buildings"
    )
    parser.add_argument(
        "--no-buildings",
        action="store_false",
        dest="draw_buildings",
        help="Disable drawing buildings",
    )
    parser.add_argument(
        "--draw-transit",
        action="store_true",
        default=True,
        help="Draw transit/railways",
    )
    parser.add_argument(
        "--no-transit",
        action="store_false",
        dest="draw_transit",
        help="Disable drawing transit",
    )
    parser.add_argument(
        "--draw-contours",
        action="store_true",
        default=True,
        help="Draw topography/contours",
    )
    parser.add_argument(
        "--no-contours",
        action="store_false",
        dest="draw_contours",
        help="Disable drawing contours",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.run_cli:
        run_interactive_cli_wizard(args, parser)
        sys.exit(0)

    if args.list_themes:
        list_all_themes()
        sys.exit(0)

    style_mode = args.style.lower()
    if style_mode == "classic":
        generate_classic_map(args)
    elif style_mode == "poster":
        generate_poster_map(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
