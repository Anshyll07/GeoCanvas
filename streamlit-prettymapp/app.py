import copy
import json

import streamlit as st
from streamlit_image_select import image_select
from pathlib import Path

from utils import (
    st_get_osm_geometries,
    st_plot_all,
    plt_to_svg,
    slugify,
)
from prettymapp.geo import GeoCodingError, get_aoi
from prettymapp.osm import OsmDataError
from prettymapp.settings import STYLES


st.set_page_config(
    page_title="Map_Generator", page_icon="", initial_sidebar_state="collapsed", layout="wide"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

    .stApp {
        background: #0E1117 !important;
        color: #F0F6FC !important;
        font-family: 'Outfit', sans-serif !important;
    }

    .block-container {
        padding-top: 1.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: min(96vw, 1500px) !important;
    }

    h1 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 800 !important;
        letter-spacing: 0 !important;
        background: linear-gradient(135deg, #FFF 0%, #8E9297 100%) !important;
        -webkit-background-clip: text !important;
        -webkit-text-fill-color: transparent !important;
        font-size: 2.5rem !important;
        margin-top: 0.5rem !important;
        margin-bottom: 0.5rem !important;
    }

    h3 {
        font-size: 1.05rem !important;
        margin-top: 1rem !important;
        margin-bottom: 0.55rem !important;
    }

    div[role="radiogroup"] {
        flex-direction: row !important;
        background-color: rgba(255, 255, 255, 0.04) !important;
        padding: 3px !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        width: fit-content !important;
        display: inline-flex !important;
        gap: 3px !important;
    }
    div[role="radiogroup"] label > div:first-child {
        display: none !important;
    }
    div[role="radiogroup"] > label {
        min-height: 34px !important;
        padding: 0 !important;
        background-color: transparent !important;
        border-radius: 6px !important;
        border: none !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer !important;
        flex: 0 0 auto !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    div[role="radiogroup"] > label p {
        padding: 7px 14px !important;
        color: #8E9297 !important;
        font-size: 0.84rem !important;
        line-height: 1.1 !important;
        white-space: nowrap !important;
    }
    div[role="radiogroup"] > label:hover {
        background-color: rgba(255, 255, 255, 0.04) !important;
    }
    div[role="radiogroup"] > label:hover p {
        color: #FFFFFF !important;
    }
    div[role="radiogroup"] > label:has(input:checked) {
        background-color: #FF4B4B !important;
        box-shadow: 0px 4px 12px rgba(255, 75, 75, 0.25) !important;
    }
    div[role="radiogroup"] > label:has(input:checked) p {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }

    div[data-testid="stForm"] {
        background-color: rgba(255, 255, 255, 0.02) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 8px !important;
        padding: 18px !important;
        box-shadow: 0px 8px 32px rgba(0, 0, 0, 0.3) !important;
        width: 100% !important;
    }

    div[data-testid="stVerticalBlock"],
    div[data-testid="stHorizontalBlock"] {
        width: 100% !important;
    }

    .streamlit-expanderHeader {
        background-color: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-radius: 8px !important;
        color: #FFFFFF !important;
        font-family: 'Outfit', sans-serif !important;
        font-weight: 500 !important;
    }
    .streamlit-expanderContent {
        background-color: rgba(255, 255, 255, 0.01) !important;
        border: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-top: none !important;
        border-radius: 0 0 8px 8px !important;
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] div[role="combobox"] {
        background-color: #1E2229 !important;
        border: 1px solid #2D3139 !important;
        border-radius: 8px !important;
        color: #FFFFFF !important;
        min-height: 38px !important;
        height: 38px !important;
        padding: 6px 10px !important;
        font-family: 'Outfit', sans-serif !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stNumberInput"] input:focus {
        border-color: #FF4B4B !important;
        box-shadow: 0 0 0 1px #FF4B4B !important;
    }

    label, div[data-testid="stWidgetLabel"] p {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 500 !important;
        color: #FFFFFF !important;
        font-size: 0.9rem !important;
    }

    div[data-testid="stSlider"] {
        padding-top: 0.15rem !important;
        padding-bottom: 0.25rem !important;
    }
    div[data-testid="stSlider"] [role="slider"] {
        background-color: #FF4B4B !important;
        border-color: #FF4B4B !important;
    }
    div[data-testid="stSlider"] div[data-testid="stSliderTrack"] > div {
        background-color: #FF4B4B !important;
    }

    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-primary"],
    button[data-testid="baseButton-secondaryFormSubmit"],
    button[data-testid="baseButton-primaryFormSubmit"] {
        background: linear-gradient(135deg, #FF4B4B 0%, #D82F2F 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-family: 'Outfit', sans-serif !important;
        font-weight: 600 !important;
        padding: 8px 18px !important;
        min-height: 38px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0px 4px 12px rgba(255, 75, 75, 0.25) !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    div[data-testid="stButton"] button,
    div[data-testid="stButton"] button p {
        white-space: nowrap !important;
    }
    button[data-testid="stBaseButton-secondary"]:hover,
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="baseButton-secondaryFormSubmit"]:hover,
    button[data-testid="baseButton-primaryFormSubmit"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0px 6px 20px rgba(255, 75, 75, 0.4) !important;
        background: linear-gradient(135deg, #FF6060 0%, #FF3333 100%) !important;
    }
    button[data-testid="stBaseButton-secondary"]:active,
    button[data-testid="stBaseButton-primary"]:active,
    button[data-testid="baseButton-secondaryFormSubmit"]:active,
    button[data-testid="baseButton-primaryFormSubmit"]:active {
        transform: translateY(0) !important;
    }

    button[key="view_fullscreen_poster"],
    button[key="view_fullscreen"],
    button[data-testid="stBaseButton-secondary"]:not([class*="FormSubmit"]):not([class*="submit"]),
    div[data-testid="column"] button:not([class*="FormSubmit"]) {
        background: rgba(255, 255, 255, 0.04) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        box-shadow: none !important;
    }
    button[key="view_fullscreen_poster"]:hover,
    button[key="view_fullscreen"]:hover,
    button[data-testid="stBaseButton-secondary"]:not([class*="FormSubmit"]):not([class*="submit"]):hover,
    div[data-testid="column"] button:not([class*="FormSubmit"]):hover {
        background: rgba(255, 255, 255, 0.08) !important;
        border-color: rgba(255, 255, 255, 0.2) !important;
    }

    div[data-testid="column"] img {
        border-radius: 8px !important;
        border: 2px solid transparent !important;
        transition: all 0.25s ease !important;
    }
    div[data-testid="column"] img:hover {
        transform: scale(1.03) !important;
        border-color: rgba(255, 75, 75, 0.4) !important;
    }

    div[data-testid="stAlert"] {
        background-color: rgba(255, 255, 255, 0.03) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
        color: #F0F6FC !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("# Prettymapp")

_HERE = Path(__file__).resolve().parent
with (_HERE / "examples.json").open("r", encoding="utf8") as f:
    EXAMPLES = json.load(f)

if not st.session_state:
    st.session_state.update(EXAMPLES["Default"])

    from prettymapp.settings import LANDCOVER_CLASSES
    st.session_state.lc_classes = list(LANDCOVER_CLASSES.keys())
    st.session_state["previous_style"] = "Default"

theme_category = st.selectbox(
    "Theme category",
    ["Classic (Customizable)", "Poster (Artist Themes)"],
    index=0,
    key="theme_category",
)

@st.dialog("Fullscreen View", width="large")
def show_fullscreen_image(image_path, title):
    st.image(image_path, caption=title, use_container_width=True)

@st.cache_data(show_spinner=False)
def st_create_poster(
    city,
    country,
    point,
    dist,
    theme_name,
    width,
    height,
    display_city,
    display_country,
    draw_buildings,
    draw_transit,
    draw_contours,
    text_position,
    show_text,
    output_format="png"
):
    import sys
    from pathlib import Path
    _HERE = Path(__file__).resolve().parent
    sys.path.append(str(_HERE.parent / "poster_generator"))
    import create_map_poster
    from create_map_poster import create_poster, load_theme
    create_map_poster.THEME = load_theme(theme_name)
    return create_poster(
        city=city,
        country=country,
        point=point,
        dist=dist,
        output_file=None,
        output_format=output_format,
        width=width,
        height=height,
        display_city=display_city,
        display_country=display_country,
        draw_buildings=draw_buildings,
        draw_transit=draw_transit,
        draw_contours=draw_contours,
        text_position=text_position,
        show_text=show_text,
    )

if theme_category == "Classic (Customizable)":
    theme_names = list(STYLES.keys())
    theme_image_pattern = str(_HERE / "assets" / "themes" / "{}.png")
    theme_image_fp = [theme_image_pattern.format(name) for name in theme_names]

    st.markdown("### Select a Color Theme")
    selected_theme_index = image_select(
        "",
        images=theme_image_fp,
        captions=theme_names,
        index=theme_names.index(st.session_state.get("style", "Peach")) if st.session_state.get("style") in theme_names else 0,
        return_value="index",
        key="classic_theme_image_select"
    )

    style = theme_names[selected_theme_index]
    st.session_state["style"] = style

    if st.button("🔍 View selected theme in full screen", key="view_fullscreen_classic"):
        show_fullscreen_image(theme_image_fp[selected_theme_index], style)
else:
    new_themes_dir = _HERE.parent / "poster_generator" / "themes"
    new_theme_names = sorted([f.stem for f in new_themes_dir.glob("*.json")]) if new_themes_dir.exists() else []

    theme_image_pattern = str(_HERE / "assets" / "themes" / "{}.png")
    theme_image_fp = [theme_image_pattern.format(name) for name in new_theme_names]

    default_img = str(_HERE / "assets" / "themes" / "Default.png")
    theme_image_fp_safe = []
    for fp in theme_image_fp:
        if Path(fp).exists():
            theme_image_fp_safe.append(fp)
        else:
            theme_image_fp_safe.append(default_img)

    st.markdown("### Select an Artist Poster Theme")

    current_poster_theme = st.session_state.get("poster_theme", "terracotta")
    default_index = new_theme_names.index(current_poster_theme) if current_poster_theme in new_theme_names else 0

    selected_theme_index = image_select(
        "",
        images=theme_image_fp_safe,
        captions=[name.replace("_", " ").title() for name in new_theme_names],
        index=default_index,
        return_value="index",
        key="poster_theme_image_select"
    )

    selected_new_theme = new_theme_names[selected_theme_index]
    st.session_state["poster_theme"] = selected_new_theme
    style = selected_new_theme



    if st.button("🔍 View selected theme in full screen", key="view_fullscreen_poster"):
        show_fullscreen_image(theme_image_fp_safe[selected_theme_index], style.replace("_", " ").title())

    theme_file_path = new_themes_dir / f"{selected_new_theme}.json"
    if theme_file_path.exists():
        with open(theme_file_path, "r", encoding="utf-8") as f:
            try:
                t_data = json.load(f)
                st.info(f"🎨 **{t_data.get('name', selected_new_theme)}**: {t_data.get('description', 'No description available.')}")
            except Exception:
                pass



input_mode = st.radio("Select Input Mode", ["Enter Address", "Draw on Map"], horizontal=True)

drawings = None
if input_mode == "Draw on Map":
    import folium
    from folium.plugins import Draw
    from streamlit_folium import st_folium

    if "map_center" not in st.session_state:
        st.session_state.map_center = [22.19, 113.54]

    m = folium.Map(location=st.session_state.map_center, zoom_start=13)
    draw = Draw(
        draw_options={
            "polyline": False,
            "rectangle": True,
            "polygon": True,
            "circle": True,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": False}
    )
    m.add_child(draw)
    map_data = st_folium(m, width="100%", height=400)
    if map_data:
        drawings = map_data.get("all_drawings")



form = st.form(key="form_settings")
col1, col2 = form.columns([3, 1])

if input_mode == "Enter Address":
    address = col1.text_input(
        "Location address",
        key="address",
    )
    if address and (address.startswith("http://") or address.startswith("https://") or "localhost:" in address or "#" in address):
        col1.warning("⚠️ It looks like your browser autofilled the page URL here. Please type a valid location address instead (e.g. 'Paris').")
    radius = col2.slider(
        "Radius (meter)",
        100,
        1500,
        key="radius",
    )
else:
    address = "Custom Area"
    radius = 1000
    st.session_state["address"] = address
    st.session_state["radius"] = radius

form_left, form_right = form.columns(2)

if theme_category == "Classic (Customizable)":
    expander = form_left.expander("Customize map style")
    col1style, col2style = expander.columns(2)

    shape_options = ["circle", "rectangle"]
    if input_mode == "Draw on Map" and drawings is not None and len(drawings) > 0:
        shape_options.append("custom")
    shape = col1style.radio(
        "Map Shape",
        options=shape_options,
        key="shape",
    )

    bg_shape_options = ["rectangle", "circle", "match the image", None] if input_mode == "Draw on Map" else ["rectangle", "circle", None]
    if "bg_shape" in st.session_state and st.session_state.bg_shape not in bg_shape_options:
        st.session_state.bg_shape = "rectangle"
    col1style.markdown("---")
    contour_color = col1style.color_picker(
        "Map contour color",
        key="contour_color",
    )
    contour_width = col1style.slider(
        "Map contour width",
        0,
        30,
        value=1,
        help="Thickness of contour line sourrounding the map.",
        key="contour_width",
    )

    if style != st.session_state["previous_style"]:
        st.session_state["previous_style"] = style

    draw_settings = copy.deepcopy(STYLES[style])
    layer_expander = form_right.expander("Customize map layers")

    layer_expander.markdown("**Background**")
    bg_shape_col, bg_buffer_col = layer_expander.columns(2)
    bg_shape = bg_shape_col.radio("Shape", options=bg_shape_options, key="bg_shape")
    bg_buffer = bg_buffer_col.slider(
        "Size",
        min_value=0,
        max_value=50,
        help="How much the background extends beyond the figure.",
        key="bg_buffer",
    )

    bg1, bg2, bg3, bg4 = layer_expander.columns(4)

    bg_settings = draw_settings.get("background", {})
    default_bg_fc = bg_settings.get("fc", "#F2F4CB")
    bg_fc = bg1.color_picker("Face (bg)", value=default_bg_fc, key=f"{style}_bg_fc")
    bg_settings["fc"] = bg_fc

    default_bg_ec = bg_settings.get("ec", "#dadbc1")
    bg_ec = bg2.color_picker("Edge (bg)", value=default_bg_ec, key=f"{style}_bg_ec")
    bg_settings["ec"] = bg_ec

    default_bg_hatch = bg_settings.get("hatch", "")
    bg_hatch = bg3.text_input("Hatch (bg)", value=default_bg_hatch, key=f"{style}_bg_hatch")
    if bg_hatch:
        bg_settings["hatch"] = bg_hatch
    elif "hatch" in bg_settings:
        del bg_settings["hatch"]

    default_bg_hatch_c = bg_settings.get("hatch_c", default_bg_ec)
    if bg_hatch:
        bg_hatch_c = bg4.color_picker("Hatch Color (bg)", value=default_bg_hatch_c, key=f"{style}_bg_hatch_c")
        bg_settings["hatch_c"] = bg_hatch_c
    elif "hatch_c" in bg_settings:
        del bg_settings["hatch_c"]

    draw_settings["background"] = bg_settings
    bg_color = bg_fc

    layer_expander.markdown("---")

    from prettymapp.settings import LANDCOVER_CLASSES
    for lc_class in LANDCOVER_CLASSES.keys():
        class_settings = draw_settings.get(lc_class, {})
        layer_expander.markdown(f"**{lc_class.capitalize()}**")
        c1, c2, c3, c4 = layer_expander.columns(4)

        default_fc = class_settings.get("fc", "#000000")
        if "cmap" in class_settings:
            default_fc = class_settings["cmap"][0]

        is_fc_trans = (default_fc == "None")
        if c1.checkbox(f"Fill ({lc_class})", value=not is_fc_trans, key=f"{style}_{lc_class}_fill_cb"):
            if is_fc_trans: default_fc = "#FFFFFF"
            fc = c1.color_picker(f"Face Color ({lc_class})", value=default_fc, key=f"{style}_{lc_class}_fc")
            class_settings["fc"] = fc
        else:
            class_settings["fc"] = "None"

        if "cmap" in class_settings:
            del class_settings["cmap"]

        default_ec = class_settings.get("ec", "#000000")
        is_ec_trans = (default_ec == "None")
        if c2.checkbox(f"Outline ({lc_class})", value=not is_ec_trans, key=f"{style}_{lc_class}_ec_cb"):
            if is_ec_trans: default_ec = "#000000"
            ec = c2.color_picker(f"Edge Color ({lc_class})", value=default_ec, key=f"{style}_{lc_class}_ec")
            class_settings["ec"] = ec
        else:
            class_settings["ec"] = "None"

        default_lw = float(class_settings.get("lw", 0.0))
        lw = c3.number_input(f"Width ({lc_class})", value=default_lw, min_value=0.0, max_value=10.0, step=0.5, key=f"{style}_{lc_class}_lw")
        class_settings["lw"] = lw

        default_hatch = class_settings.get("hatch", "")
        if default_hatch is None: default_hatch = ""
        hatch = c4.text_input(f"Hatch ({lc_class})", value=default_hatch, key=f"{style}_{lc_class}_hatch")
        if hatch:
            class_settings["hatch"] = hatch
            default_hatch_c = class_settings.get("hatch_c", "#000000")
            hatch_c = c4.color_picker(f"Hatch Color ({lc_class})", value=default_hatch_c, key=f"{style}_{lc_class}_hatch_c")
            class_settings["hatch_c"] = hatch_c
        else:
            if "hatch" in class_settings: del class_settings["hatch"]
            if "hatch_c" in class_settings: del class_settings["hatch_c"]

        draw_settings[lc_class] = class_settings
else:
    shape = "rectangle"
    contour_width = 0
    contour_color = "#000000"
    draw_settings = {}
    bg_color = "#FFFFFF"

    expander = form_left.expander("Poster Layout Settings", expanded=True)
    col1style, col2style = expander.columns(2)

    poster_size = col1style.selectbox(
        "Poster Dimensions",
        options=["Portrait Poster (12x16 in)", "Standard Large (18x24 in)", "Square Poster (12x12 in)", "Landscape Poster (16x12 in)"],
        key="poster_size_selection"
    )
    size_map = {
        "Portrait Poster (12x16 in)": (12, 16),
        "Standard Large (18x24 in)": (18, 24),
        "Square Poster (12x12 in)": (12, 12),
        "Landscape Poster (16x12 in)": (16, 12),
    }
    st.session_state["poster_size_val"] = size_map[poster_size]

    st.session_state["draw_buildings_val"] = col2style.checkbox("Draw Buildings", value=False, key="draw_buildings")
    st.session_state["draw_transit_val"] = col2style.checkbox("Draw Transit Lines", value=False, key="draw_transit")
    st.session_state["draw_contours_val"] = col2style.checkbox("Draw Topography Contours", value=False, key="draw_contours")

    form_right.markdown("### 🎨 Artist Theme")
    form_right.info("ℹ Map shape, layers, outlines, and colors are automatically designed and optimized by the artist for this theme.")

submitted = form.form_submit_button(label="Generate Map")

if submitted:
    with st.spinner("Creating map... (may take up to a minute)"):
        rectangular = True if theme_category == "Poster (Artist Themes)" else (shape != "circle")

        if input_mode == "Draw on Map":
            if not drawings:
                st.error("Please draw a polygon on the map first!")
                st.stop()

            from shapely.geometry import shape as shapely_shape
            from shapely.ops import unary_union
            import geopandas as gp

            polygons = []
            for drawing in drawings:
                geom = drawing["geometry"]
                if geom["type"] in ["Polygon", "MultiPolygon"]:
                    polygons.append(shapely_shape(geom))
                elif geom["type"] == "Point" and "radius" in drawing.get("properties", {}):
                    import osmnx as ox
                    lon, lat = geom["coordinates"]
                    radius_m = drawing["properties"]["radius"]
                    point_series = gp.GeoSeries([shapely_shape(geom)], crs="EPSG:4326")
                    point_utm = ox.projection.project_gdf(gp.GeoDataFrame(geometry=point_series))
                    circle_utm = point_utm.buffer(radius_m)
                    circle_wgs = ox.projection.project_gdf(gp.GeoDataFrame(geometry=circle_utm), to_crs="EPSG:4326")
                    polygons.append(circle_wgs.geometry.iloc[0])

            if not polygons:
                st.error("Please draw at least one Polygon or Rectangle!")
                st.stop()

            combined_poly = unary_union(polygons)
            aoi = combined_poly
        else:
            if address and (address.startswith("http://") or address.startswith("https://") or "localhost:" in address or "#" in address):
                st.error("⚠️ Error: It looks like your browser autofilled the URL of this page into the location input. Please enter a valid location address or city name instead (e.g. 'Paris').")
                st.stop()
            try:
                aoi = get_aoi(address=address, radius=radius, rectangular=rectangular)
            except GeoCodingError as e:
                st.error(f"ERROR: {str(e)}")
                st.stop()

        if theme_category == "Classic (Customizable)":
            try:
                df = st_get_osm_geometries(aoi=aoi)
            except OsmDataError as e:
                st.error(f"ERROR: {str(e)}")
                st.stop()
            except Exception:
                st.error(
                    "ERROR: Could not download OpenStreetMap data for this area. "
                    "The service may be busy or unavailable - please try again."
                )
                st.stop()
            config = {
                "aoi_bounds": aoi.bounds,
                "aoi_geometry": aoi,
                "draw_settings": draw_settings,
                "name_on": False,
                "shape": shape,
                "contour_width": contour_width,
                "contour_color": contour_color,
                "bg_shape": bg_shape,
                "bg_buffer": bg_buffer,
                "bg_color": bg_color,
                "credits": False,
            }
            try:
                fig = st_plot_all(_df=df, **config)
                st.session_state.current_fig = fig
                st.session_state.current_df = df
                st.session_state.current_config = config
                st.session_state.current_address = address
                st.session_state["last_classic_style"] = style
                st.session_state["poster_generated"] = False
                if "current_poster_bytes" in st.session_state:
                    del st.session_state["current_poster_bytes"]
            except Exception as e:
                st.error(f"ERROR: Could not render the map for this area. Please try again. {e}")
                import traceback
                st.error(traceback.format_exc())
                st.stop()
        else:
            centroid = aoi.centroid
            point = (centroid.y, centroid.x)

            if input_mode == "Draw on Map":
                from prettymapp.geo import get_utm_crs
                import geopandas as gp
                from shapely.geometry import Point as ShapelyPoint
                gdf_pt = gp.GeoDataFrame(geometry=[ShapelyPoint(point[1], point[0])], crs="EPSG:4326")
                utm_crs = get_utm_crs(point[0], point[1])
                gdf_pt_utm = gdf_pt.to_crs(utm_crs)
                gdf_aoi_utm = gp.GeoDataFrame(geometry=[aoi], crs="EPSG:4326").to_crs(utm_crs)
                dist = int(gdf_aoi_utm.geometry.iloc[0].centroid.distance(gdf_aoi_utm.geometry.iloc[0].boundary).max())
                dist = max(min(dist, 1500), 100)
            else:
                dist = radius

            import sys
            from pathlib import Path
            _HERE = Path(__file__).resolve().parent
            sys.path.append(str(_HERE.parent / "poster_generator"))
            from create_map_poster import create_poster, load_theme
            import create_map_poster

            output_file = str(_HERE / "cache" / "current_poster.png")
            Path(_HERE / "cache").mkdir(exist_ok=True)

            create_map_poster.THEME = load_theme(selected_new_theme)

            parts = [p.strip() for p in address.split(",")]
            city_name = parts[0] if parts else "City"
            country_name = parts[-1] if len(parts) > 1 else ""

            poster_w, poster_h = st.session_state.get("poster_size_val", (12, 16))
            draw_buildings_val = st.session_state.get("draw_buildings_val", False)
            draw_transit_val = st.session_state.get("draw_transit_val", False)
            draw_contours_val = st.session_state.get("draw_contours_val", False)

            if "poster_custom_title" not in st.session_state:
                st.session_state["poster_custom_title"] = city_name
            if "poster_custom_subtitle" not in st.session_state:
                st.session_state["poster_custom_subtitle"] = country_name
            if "text_position_val" not in st.session_state:
                st.session_state["text_position_val"] = "Bottom"
            if "poster_show_text" not in st.session_state:
                st.session_state["poster_show_text"] = True

            text_pos = st.session_state.get("text_position_val", "Bottom")

            try:
                poster_bytes = st_create_poster(
                    city=city_name,
                    country=country_name,
                    point=point,
                    dist=dist,
                    theme_name=selected_new_theme,
                    width=poster_w,
                    height=poster_h,
                    display_city=st.session_state["poster_custom_title"],
                    display_country=st.session_state["poster_custom_subtitle"],
                    draw_buildings=draw_buildings_val,
                    draw_transit=draw_transit_val,
                    draw_contours=draw_contours_val,
                    text_position=text_pos.lower(),
                    show_text=st.session_state["poster_show_text"],
                )

                st.session_state["poster_generated"] = True
                st.session_state["poster_point"] = point
                st.session_state["poster_dist"] = dist
                st.session_state["poster_city_name"] = city_name
                st.session_state["poster_country_name"] = country_name
                st.session_state["current_poster_bytes"] = poster_bytes
                st.session_state["current_address"] = address
                st.session_state["last_poster_theme"] = selected_new_theme
                st.session_state["last_poster_w"] = poster_w
                st.session_state["last_poster_h"] = poster_h
                st.session_state["last_draw_buildings"] = draw_buildings_val
                st.session_state["last_draw_transit"] = draw_transit_val
                st.session_state["last_draw_contours"] = draw_contours_val
                st.session_state["last_poster_show_text"] = st.session_state["poster_show_text"]
                st.session_state["current_fig"] = None
            except Exception as e:
                st.error(f"ERROR: Could not generate the map poster. Please try again. {e}")
                import traceback
                st.error(traceback.format_exc())
                st.stop()

if theme_category == "Classic (Customizable)" and st.session_state.get("current_fig") is not None:
    st.markdown("---")
    st.markdown("### 🎨 Live Title Settings")
    t_col1, t_col2 = st.columns(2)
    name_on = t_col1.checkbox("Display title", value=True, help="If checked, adds the selected address as the title.", key="name_on")
    custom_title = t_col1.text_input("Custom title (optional)", max_chars=30, key="custom_title")
    font_size = t_col1.slider("Title font size", min_value=1, max_value=50, value=25, key="font_size")
    font_color = t_col1.color_picker("Title font color", value="#2F3737", key="font_color")

    text_design = t_col2.selectbox("Text Design", options=["Straight", "Circular", "Wave", "Staircase", "Spiral"], index=0, key="text_design")
    text_x = t_col2.slider("Title X Position (%)", -100, 100, value=47, help="0 is center, -50 is left, 50 is right", key="text_x")
    text_y = t_col2.slider("Title Y Position (%)", -100, 100, value=-47, help="0 is center, -50 is bottom, 50 is top", key="text_y")
    text_rotation = t_col2.slider("Title Rotation (degrees)", -360, 360, value=0, key="text_rotation")

    intensity = 1.0
    frequency = 1.0
    if text_design == "Circular":
        intensity = t_col2.slider("Character Spacing", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="intensity_circ")
    elif text_design == "Wave":
        intensity = t_col2.slider("Wave Amplitude", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="intensity_wave")
        frequency = t_col2.slider("Wave Frequency", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="frequency_wave")
    elif text_design == "Staircase":
        intensity = t_col2.slider("Step Height", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="intensity_stair")
    elif text_design == "Spiral":
        intensity = t_col2.slider("Spiral Tightness", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="intensity_spiral")
        frequency = t_col2.slider("Character Spacing", min_value=0.1, max_value=5.0, value=1.0, step=0.1, key="frequency_spiral")

    fig = st.session_state.current_fig
    df = st.session_state.current_df
    config = st.session_state.current_config
    address = st.session_state.current_address

    ax = fig.axes[0]
    for txt in list(ax.texts):
        txt.remove()

    display_title = custom_title if custom_title else address

    if name_on and display_title:
        bounds = config["aoi_bounds"]
        xmin, ymin, xmax, ymax = bounds
        xmid = (xmin + xmax) / 2
        ymid = (ymin + ymax) / 2
        xdif = xmax - xmin
        ydif = ymax - ymin

        from pathlib import Path
        import matplotlib.font_manager as fm
        import prettymapp
        import math
        _location_ = Path(prettymapp.__file__).resolve().parent
        fpath = _location_ / "fonts" / "PermanentMarker-Regular.ttf"
        fontproperties = fm.FontProperties(fname=fpath.resolve())

        x_base = xmid + text_x / 100 * xdif
        y_base = ymid + text_y / 100 * ydif

        if text_design == "Straight":
            ax.text(
                x=x_base, y=y_base, s=display_title,
                color=font_color, zorder=99, ha="center", va="center",
                rotation=text_rotation * -1, fontproperties=fontproperties, size=font_size
            )
        elif text_design == "Circular":
            dx = text_x
            dy = text_y
            r_pct = math.sqrt(dx**2 + dy**2)
            angle_rad = math.atan2(dy, dx)
            rx = (r_pct / 100) * (xdif / 2)
            ry = (r_pct / 100) * (ydif / 2)
            r_avg = (rx + ry) / 2

            if r_avg == 0:
                ax.text(xmid, ymid, display_title, color=font_color, zorder=99, ha="center", va="center", fontproperties=fontproperties, size=font_size)
            else:
                char_spacing = ((font_size * xdif / 350) / r_avg) * intensity
                total_angle = len(display_title) * char_spacing
                start_angle = angle_rad + (total_angle / 2) + math.radians(text_rotation * -1)
                for i, char in enumerate(display_title):
                    theta = start_angle - i * char_spacing
                    x_c = xmid + rx * math.cos(theta)
                    y_c = ymid + ry * math.sin(theta)
                    rot = math.degrees(theta) - 90
                    ax.text(x_c, y_c, char, color=font_color, zorder=99, ha="center", va="center", rotation=rot, fontproperties=fontproperties, size=font_size)
        elif text_design == "Wave":
            amp = (font_size / 300) * ydif * intensity
            char_width = (font_size / 800) * xdif
            total_width = len(display_title) * char_width
            start_x = x_base - total_width / 2

            angle_rad = math.radians(text_rotation * -1)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)

            for i, char in enumerate(display_title):
                raw_x = start_x + i * char_width
                raw_y = y_base + math.sin(i * 1.0 * frequency) * amp
                dx_pt, dy_pt = raw_x - x_base, raw_y - y_base
                x_c = x_base + (dx_pt * cos_a - dy_pt * sin_a)
                y_c = y_base + (dx_pt * sin_a + dy_pt * cos_a)
                ax.text(x_c, y_c, char, color=font_color, zorder=99, ha="center", va="center", rotation=text_rotation * -1, fontproperties=fontproperties, size=font_size)
        elif text_design == "Staircase":
            char_width = (font_size / 800) * xdif
            char_height = ((font_size / 800) * ydif) * intensity
            total_width = len(display_title) * char_width
            start_x = x_base - total_width / 2
            start_y = y_base + (len(display_title) / 2) * char_height

            angle_rad = math.radians(text_rotation * -1)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)

            for i, char in enumerate(display_title):
                raw_x = start_x + i * char_width
                raw_y = start_y - i * char_height
                dx_pt, dy_pt = raw_x - x_base, raw_y - y_base
                x_c = x_base + (dx_pt * cos_a - dy_pt * sin_a)
                y_c = y_base + (dx_pt * sin_a + dy_pt * cos_a)
                ax.text(x_c, y_c, char, color=font_color, zorder=99, ha="center", va="center", rotation=text_rotation * -1, fontproperties=fontproperties, size=font_size)
        elif text_design == "Spiral":
            base_r = (font_size / 2000) * xdif
            char_spacing = 0.5 * frequency
            start_angle = math.radians(text_rotation * -1)
            for i, char in enumerate(display_title):
                theta = start_angle + i * char_spacing
                r = base_r + (i * base_r * 0.5 * intensity)
                x_c = x_base + r * math.cos(theta)
                y_c = y_base + r * math.sin(theta)
                rot = math.degrees(theta) - 90
                ax.text(x_c, y_c, char, color=font_color, zorder=99, ha="center", va="center", rotation=rot, fontproperties=fontproperties, size=font_size)

    with st.expander("Export image"):
        img_format = st.selectbox(
            "File type",
            options=["png", "svg"],
            index=0,
            help="Export the rendered map in different formats.",
            key="export_image_format",
            format_func=lambda v: "PNG (300 dpi)" if v == "png" else "SVG (lossless)",
        )
        fname_base = slugify(address) if str(address).strip() else "prettymapp"
        mime_by_format = {
            "png": "image/png",
            "svg": "image/svg+xml",
        }

        def _make_download_data():
            if img_format == "svg":
                return plt_to_svg(fig)
            import io
            buf = io.BytesIO()
            savefig_kwargs = dict(
                format=img_format,
                pad_inches=0,
                bbox_inches="tight",
                transparent=True,
            )
            if img_format == "png":
                savefig_kwargs["dpi"] = 300
            fig.savefig(buf, **savefig_kwargs)
            buf.seek(0)
            return buf.getvalue()

        export_signature = (
            img_format,
            id(fig),
            display_title,
            name_on,
            font_size,
            font_color,
            text_design,
            text_x,
            text_y,
            text_rotation,
            intensity,
            frequency,
        )
        prepared_export = st.session_state.get("classic_prepared_export")

        if st.button("Prepare download", key="prepare_classic_export"):
            with st.spinner("Preparing file..."):
                prepared_export = {
                    "signature": export_signature,
                    "data": _make_download_data(),
                }
                st.session_state["classic_prepared_export"] = prepared_export

        if prepared_export and prepared_export.get("signature") == export_signature:
            st.download_button(
                label="Download",
                data=prepared_export["data"],
                file_name=f"{fname_base}.{img_format}",
                mime=mime_by_format[img_format],
                key=f"download_image_{img_format}",
                on_click="ignore",
            )
        else:
            st.caption("Prepare the file when you are ready to export.")

    st.pyplot(fig, pad_inches=0, bbox_inches="tight", transparent=True, dpi=160)

    st.markdown("</br>", unsafe_allow_html=True)
    st.markdown("</br>", unsafe_allow_html=True)

    ex1, ex2 = st.columns(2)
    with ex1.expander("Export geometries as GeoJSON"):
        st.write(f"{df.shape[0]} geometries")
        geojson_fname_base = slugify(address) if str(address).strip() else "prettymapp"
        st.download_button(
            label="Download",
            data=df.to_json().encode("utf-8"),
            file_name=f"{geojson_fname_base}.geojson",
            mime="application/geo+json",
        )

    config = {"address": address, **config}
    with ex2.expander("Export map configuration"):
        st.write(config)

elif theme_category == "Poster (Artist Themes)" and st.session_state.get("poster_generated"):
    st.markdown("---")
    st.markdown("### 🎨 Live Poster Settings")
    t_col1, t_col2 = st.columns(2)

    city_default = st.session_state.get("poster_city_name", "")
    country_default = st.session_state.get("poster_country_name", "")

    custom_title_val = t_col1.text_input("Custom Title (City)", value=st.session_state.get("poster_custom_title", city_default), key="poster_custom_title_input")
    custom_subtitle_val = t_col1.text_input("Custom Subtitle (Country)", value=st.session_state.get("poster_custom_subtitle", country_default), key="poster_custom_subtitle_input")

    import sys
    from pathlib import Path
    _HERE = Path(__file__).resolve().parent
    sys.path.append(str(_HERE.parent / "poster_generator"))
    from create_map_poster import load_theme
    theme_dict = load_theme(st.session_state.get("poster_theme", "terracotta"))
    is_blueprint = (theme_dict.get("layout") == "blueprint")

    if is_blueprint:
        show_text_val = True
        t_col1.checkbox("Display title & text", value=True, disabled=True, key="poster_show_text_checkbox_blueprint", help="In blueprint layouts, titles and dimensions are always displayed.")
    else:
        show_text_val = t_col1.checkbox("Display title & text", value=st.session_state.get("poster_show_text", True), key="poster_show_text_checkbox_main")

    if not is_blueprint:
        text_position_val = t_col2.selectbox("Text Position", options=["Bottom", "Top"], index=0, key="text_position_select")
    else:
        text_position_val = "Bottom"
        t_col2.info("ℹ In blueprint layout, title text is only available at the top location.")

    changed = False
    if st.session_state.get("poster_custom_title") != custom_title_val:
        st.session_state["poster_custom_title"] = custom_title_val
        changed = True
    if st.session_state.get("poster_custom_subtitle") != custom_subtitle_val:
        st.session_state["poster_custom_subtitle"] = custom_subtitle_val
        changed = True
    if st.session_state.get("text_position_val") != text_position_val:
        st.session_state["text_position_val"] = text_position_val
        changed = True
    if st.session_state.get("poster_show_text", True) != show_text_val:
        st.session_state["poster_show_text"] = show_text_val
        changed = True

    poster_w, poster_h = st.session_state.get("poster_size_val", (12, 16))
    draw_buildings_val = st.session_state.get("draw_buildings_val", False)
    draw_transit_val = st.session_state.get("draw_transit_val", False)
    draw_contours_val = st.session_state.get("draw_contours_val", False)

    if changed:

        with st.spinner("Updating poster..."):
            poster_bytes = st_create_poster(
                city=st.session_state.poster_city_name,
                country=st.session_state.poster_country_name,
                point=st.session_state.poster_point,
                dist=st.session_state.poster_dist,
                theme_name=st.session_state.last_poster_theme,
                width=st.session_state.last_poster_w,
                height=st.session_state.last_poster_h,
                display_city=custom_title_val,
                display_country=custom_subtitle_val,
                draw_buildings=st.session_state.last_draw_buildings,
                draw_transit=st.session_state.last_draw_transit,
                draw_contours=st.session_state.last_draw_contours,
                text_position=text_position_val.lower(),
                show_text=show_text_val,
            )

            st.session_state["current_poster_bytes"] = poster_bytes
            st.session_state["last_poster_show_text"] = show_text_val
            st.rerun()

    st.image(st.session_state.current_poster_bytes, use_container_width=True)

    with st.expander("Export image"):
        img_format = st.selectbox(
            "File type",
            options=["png", "svg"],
            index=0,
            help="Export the rendered map in different formats.",
            key="export_poster_format",
            format_func=lambda v: "PNG (300 dpi)" if v == "png" else "SVG (lossless)",
        )
        fname_base = slugify(st.session_state.poster_city_name)
        mime_by_format = {
            "png": "image/png",
            "svg": "image/svg+xml",
        }

        def _make_poster_download_data():
            if img_format == "png":
                return st.session_state.current_poster_bytes

            return st_create_poster(
                city=st.session_state.poster_city_name,
                country=st.session_state.poster_country_name,
                point=st.session_state.poster_point,
                dist=st.session_state.poster_dist,
                theme_name=st.session_state.last_poster_theme,
                width=st.session_state.last_poster_w,
                height=st.session_state.last_poster_h,
                display_city=custom_title_val,
                display_country=custom_subtitle_val,
                draw_buildings=st.session_state.last_draw_buildings,
                draw_transit=st.session_state.last_draw_transit,
                draw_contours=st.session_state.last_draw_contours,
                text_position=text_position_val.lower(),
                show_text=show_text_val,
                output_format="svg",
            )

        poster_export_signature = (
            img_format,
            st.session_state.poster_city_name,
            st.session_state.poster_country_name,
            st.session_state.poster_point,
            st.session_state.poster_dist,
            custom_title_val,
            custom_subtitle_val,
            text_position_val,
            show_text_val,
            st.session_state.last_poster_theme,
            st.session_state.last_poster_w,
            st.session_state.last_poster_h,
            st.session_state.last_draw_buildings,
            st.session_state.last_draw_transit,
            st.session_state.last_draw_contours,
        )
        prepared_poster_export = st.session_state.get("poster_prepared_export")

        if img_format == "png":
            prepared_poster_export = {
                "signature": poster_export_signature,
                "data": st.session_state.current_poster_bytes,
            }
            st.session_state["poster_prepared_export"] = prepared_poster_export
        elif st.button("Prepare SVG", key="prepare_poster_svg"):
            with st.spinner("Preparing SVG..."):
                prepared_poster_export = {
                    "signature": poster_export_signature,
                    "data": _make_poster_download_data(),
                }
                st.session_state["poster_prepared_export"] = prepared_poster_export

        if prepared_poster_export and prepared_poster_export.get("signature") == poster_export_signature:
            st.download_button(
                label="Download Poster",
                data=prepared_poster_export["data"],
                file_name=f"{fname_base}.{img_format}",
                mime=mime_by_format[img_format],
                key=f"download_poster_{img_format}",
                on_click="ignore",
            )
        elif img_format == "svg":
            st.caption("Prepare the SVG when you are ready to export.")

st.session_state["previous_style"] = style
