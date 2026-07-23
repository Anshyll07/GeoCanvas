from pathlib import Path
import colorsys
from dataclasses import dataclass, field
from geopandas import GeoDataFrame
import numpy as np
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import ListedColormap, cnames, to_rgb
from matplotlib.path import Path as MplPath
from matplotlib.pyplot import subplots, Rectangle
import matplotlib.font_manager as fm
from matplotlib.patches import Ellipse, PathPatch
import matplotlib.patheffects as PathEffects

from prettymapp.settings import STREETS_WIDTH, STYLES


def plot_polygon_collection(
    ax, geoms, values=None, cmap=None, **kwargs
) -> PatchCollection:
    """
    Plot shapely Polygons as a single matplotlib PatchCollection (honors holes).

    Faster than geodataframe.plot() as it does not use plt.draw(), the figure is
    rendered only once e.g. in st.pyplot.
    """
    patches = [
        PathPatch(
            MplPath.make_compound_path(
                MplPath(np.asarray(poly.exterior.coords)[:, :2]),
                *[MplPath(np.asarray(ring.coords)[:, :2]) for ring in poly.interiors],
            )
        )
        for poly in geoms
    ]
    collection = PatchCollection(patches, cmap=cmap, **kwargs)
    if values is not None:
        collection.set_array(np.asarray(values))
    ax.add_collection(collection, autolim=True)
    return collection


def plot_linestring_collection(ax, geoms, **kwargs) -> LineCollection:
    """
    Plot shapely LineStrings as a single matplotlib LineCollection.
    """
    collection = LineCollection(
        [np.asarray(line.coords)[:, :2] for line in geoms], **kwargs
    )
    ax.add_collection(collection, autolim=True)
    return collection


@dataclass
class Plot:
    """
    Main plotting class for prettymapp.

    Args:
        df: GeoDataFrame with the geometries to plot
        aoi_bounds: List of minx, miny, maxx, maxy coordinates, specifying the map extent
        draw_settings: Dictionary of color & draw settings, see prettymapp.settings.STYLES

        # Map layout
        shape: the map shape, "circle" or "rectangle"
        contour_width: width of the map contour, defaults to 0
        contour_color: color of the map contour, defaults to "#2F3537"

        # Optional map text settings e.g. to display location name
        name_on: whether to display the location name, defaults to False
        name: the location name to display, defaults to "some name"
        font_size: font size of the location name, defaults to 25
        font_color: color of the location name, defaults to "#2F3737"
        text_x: x-coordinate of the location name, defaults to 0
        text_y: y-coordinate of the location name, defaults to 0
        text_rotation: rotation of the location name, defaults to 0
        credits: Boolean whether to display the OSM&package credits, defaults to True

        # Map background settings
        bg_shape: the map background shape, "circle" or "rectangle", defaults to "rectangle"
        bg_buffer: buffer around the map, defaults to 2
        bg_color: color of the map background, defaults to "#F2F4CB"

        # Figure settings
        dpi: figure resolution in dots per inch, defaults to 300
    """

    df: GeoDataFrame
    aoi_bounds: list[
        float
    ]  # Not df bounds as could lead to weird plot shapes with unequal geometry distribution.
    draw_settings: dict = field(default_factory=lambda: STYLES["Peach"])
    # Map layout settings
    shape: str = "circle"
    contour_width: int = 0
    contour_color: str = "#2F3537"
    # Optional map text settings e.g. to display location name
    name_on: bool = False
    name: str = "some name"
    font_size: int = 25
    font_color: str = "#2F3737"
    text_x: int = 0
    text_y: int = 0
    text_rotation: int = 0
    credits: bool = True
    # Map background settings
    bg_shape: str = "rectangle"
    bg_buffer: int = 2
    bg_color: str = "#F2F4CB"
    # Figure settings
    dpi: int = 300
    aoi_geometry: object = None

    def __post_init__(self):
        (
            self.xmin,
            self.ymin,
            self.xmax,
            self.ymax,
        ) = self.aoi_bounds
        # take from aoi geometry bounds, otherwise probelematic if unequal geometry distribution over plot.
        self.xmid = (self.xmin + self.xmax) / 2
        self.ymid = (self.ymin + self.ymax) / 2
        self.xdif = self.xmax - self.xmin
        self.ydif = self.ymax - self.ymin

        self.bg_buffer_x = (self.bg_buffer / 100) * self.xdif
        self.bg_buffer_y = (self.bg_buffer / 100) * self.ydif

        self.fig, self.ax = subplots(
            1, 1, figsize=(12, 12), constrained_layout=True, dpi=self.dpi
        )
        self.ax.set_aspect(1 / np.cos(self.ymid * np.pi / 180))

        self.ax.axis("off")
        self.ax.set_xlim(self.xmin - self.bg_buffer_x, self.xmax + self.bg_buffer_x)
        self.ax.set_ylim(self.ymin - self.bg_buffer_y, self.ymax + self.bg_buffer_y)

    def plot_all(self):
        if self.bg_shape is not None:
            self.set_background()
        self.set_geometries()
        if self.contour_width:
            self.set_map_contour()
        if self.name_on:
            self.set_name()
        if self.credits:
            self.set_credits()

        return self.fig

    def set_geometries(self):
        """
        Avoids using geodataframe.plot() as this uses plt.draw(), but for the app, the figure needs to be rendered
        only in st.pyplot. Shaves off 1 sec.
        """
        # Seeded rng so identical inputs render identical (reproducible) maps.
        rng = np.random.default_rng(42)
        for lc_class in self.df["landcover_class"].unique():
            df_class = self.df[self.df["landcover_class"] == lc_class]
            try:
                draw_settings_class = self.draw_settings[lc_class].copy()
            except KeyError:
                continue

            # pylint: disable=no-else-continue
            if lc_class == "streets":
                df_class = df_class[df_class.geom_type == "LineString"]
                linewidth_values = list(
                    df_class["highway"].map(STREETS_WIDTH).fillna(1)
                )
                if "fc" in draw_settings_class:
                    draw_settings_class["ec"] = draw_settings_class.pop("fc")
                # Filter to only keep valid LineCollection properties to avoid AttributeError
                valid_line_keys = ["ec", "edgecolors", "lw", "linewidths", "alpha", "zorder", "label"]
                draw_settings_class = {k: v for k, v in draw_settings_class.items() if k in valid_line_keys}
                linecollection = plot_linestring_collection(
                    ax=self.ax, geoms=df_class.geometry, **draw_settings_class
                )
                linecollection.set_linewidth(linewidth_values)
                continue
            else:
                df_class = df_class[df_class.geom_type == "Polygon"]

            if "hatch_c" in draw_settings_class:
                # Matplotlib hatch color is set via ec. hatch_c is used as the edge color here by plotting the outlines
                # again above.
                plot_polygon_collection(
                    ax=self.ax,
                    geoms=df_class.geometry,
                    fc="None",
                    ec=draw_settings_class["hatch_c"],
                    lw=1,
                    zorder=6,
                )
                draw_settings_class.pop("hatch_c")

            if "cmap" in draw_settings_class:
                cmap_colors = draw_settings_class.pop("cmap")
                cmap_values = rng.integers(0, len(cmap_colors), df_class.shape[0])
                plot_polygon_collection(
                    ax=self.ax,
                    geoms=df_class.geometry,
                    values=cmap_values,
                    cmap=ListedColormap(cmap_colors),
                    **draw_settings_class,
                )
            else:
                plot_polygon_collection(
                    ax=self.ax, geoms=df_class.geometry, **draw_settings_class
                )

    def set_map_contour(self):
        if self.shape == "rectangle":
            patch = Rectangle(
                xy=(self.xmin, self.ymin),
                width=self.xdif,
                height=self.ydif,
                color="None",
                lw=self.contour_width,
                ec=self.contour_color,
                zorder=6,
                clip_on=True,
            )
            self.ax.add_patch(patch)
        elif self.shape == "circle":
            # axis aspect ratio no equal so ellipse required to display as circle
            ellipse = Ellipse(
                xy=(self.xmid, self.ymid),  # centroid
                width=self.xdif,
                height=self.ydif,
                color="None",
                lw=self.contour_width,
                ec=self.contour_color,
                zorder=6,
                clip_on=True,
            )
            self.ax.add_artist(ellipse)
            # re-enable patch for background color that is deactivated with axis
        elif self.shape == "custom" and self.aoi_geometry is not None:
            if hasattr(self.aoi_geometry, "geoms"):
                geoms = self.aoi_geometry.geoms
            else:
                geoms = [self.aoi_geometry]
            for poly in geoms:
                patch = PathPatch(
                    MplPath.make_compound_path(
                        MplPath(np.asarray(poly.exterior.coords)[:, :2]),
                        *[MplPath(np.asarray(ring.coords)[:, :2]) for ring in poly.interiors],
                    ),
                    facecolor="None",
                    lw=self.contour_width,
                    ec=self.contour_color,
                    zorder=6,
                    clip_on=True,
                )
                self.ax.add_patch(patch)
        self.ax.patch.set_zorder(6)

    def set_background(self):
        bg_settings = self.draw_settings.get("background", {})
        fc = bg_settings.get("fc", self.bg_color)
        ec = bg_settings.get("ec", adjust_lightness(fc, 0.78))
        hatch = bg_settings.get("hatch", "ooo...")
        hatch_c = bg_settings.get("hatch_c", ec)

        kwargs = {
            "facecolor": fc,
            "ec": hatch_c, # matplotlib uses ec for hatch color
            "hatch": hatch if hatch else None,
            "zorder": -1,
            "clip_on": True,
        }

        if self.bg_shape == "rectangle":
            patch = Rectangle(
                xy=(self.xmin - self.bg_buffer_x, self.ymin - self.bg_buffer_y),
                width=self.xdif + 2 * self.bg_buffer_x,
                height=self.ydif + 2 * self.bg_buffer_y,
                **kwargs
            )
            self.ax.add_patch(patch)
            
            # If we used hatch_c as ec for hatch color, we might want the actual boundary ec.
            # But the boundary of the background is usually outside the view or we can just draw another outline.
            # We'll just keep it simple.

        elif self.bg_shape == "circle":
            # axis aspect ratio no equal so ellipse required to display as circle
            ellipse = Ellipse(
                xy=(self.xmid, self.ymid),  # centroid
                width=self.xdif + 2 * self.bg_buffer_x,
                height=self.ydif + 2 * self.bg_buffer_y,
                **kwargs
            )
            self.ax.add_artist(ellipse)

        elif self.bg_shape == "match the image" and self.aoi_geometry is not None:
            # We buffer the polygon by bg_buffer_x (using max of bg_buffer_x and y for safety or just x is fine since it's unprojected).
            buffered_geom = self.aoi_geometry.buffer(self.bg_buffer_x)
            if hasattr(buffered_geom, "geoms"):
                geoms = buffered_geom.geoms
            else:
                geoms = [buffered_geom]
            
            for poly in geoms:
                patch = PathPatch(
                    MplPath.make_compound_path(
                        MplPath(np.asarray(poly.exterior.coords)[:, :2]),
                        *[MplPath(np.asarray(ring.coords)[:, :2]) for ring in poly.interiors],
                    ),
                    **kwargs
                )
                self.ax.add_patch(patch)
        
        # Draw a separate boundary if ec != hatch_c
        if ec != hatch_c:
            outline_kwargs = {
                "facecolor": "None",
                "ec": ec,
                "lw": 1,
                "zorder": -0.9,
                "clip_on": True,
            }
            if self.bg_shape == "rectangle":
                self.ax.add_patch(Rectangle(
                    xy=(self.xmin - self.bg_buffer_x, self.ymin - self.bg_buffer_y),
                    width=self.xdif + 2 * self.bg_buffer_x,
                    height=self.ydif + 2 * self.bg_buffer_y,
                    **outline_kwargs
                ))
            elif self.bg_shape == "circle":
                self.ax.add_artist(Ellipse(
                    xy=(self.xmid, self.ymid),
                    width=self.xdif + 2 * self.bg_buffer_x,
                    height=self.ydif + 2 * self.bg_buffer_y,
                    **outline_kwargs
                ))
            elif self.bg_shape == "match the image" and self.aoi_geometry is not None:
                for poly in geoms:
                    self.ax.add_patch(PathPatch(
                        MplPath.make_compound_path(
                            MplPath(np.asarray(poly.exterior.coords)[:, :2]),
                            *[MplPath(np.asarray(ring.coords)[:, :2]) for ring in poly.interiors],
                        ),
                        **outline_kwargs
                    ))

        # re-enable patch for background color that is deactivated with axis
        self.ax.patch.set_zorder(-1)


    def set_name(self):
        x = self.xmid + self.text_x / 100 * self.xdif
        y = self.ymid + self.text_y / 100 * self.ydif

        _location_ = Path(__file__).resolve().parent
        fpath = _location_ / "fonts/PermanentMarker-Regular.ttf"
        fontproperties = fm.FontProperties(fname=fpath.resolve())
        self.ax.text(
            x=x,
            y=y,
            s=self.name,
            color=self.font_color,
            zorder=99,
            ha="center",
            rotation=self.text_rotation * -1,
            fontproperties=fontproperties,
            size=self.font_size,
        )

    def set_credits(
        self,
        text: str = "© OpenStreetMap\n prettymapp | prettymaps",
        x: float | None = None,
        y: float | None = None,
        fontsize: int = 9,
        zorder: int = 6,
    ):
        """
        Add OSM credits. Defaults to lower right corner of map.
        """
        if x is None:
            x = self.xmin + 0.87 * self.xdif
        if y is None:
            y = self.ymin - 0.70 * self.bg_buffer_y
        text = self.ax.text(x=x, y=y, s=text, c="w", fontsize=fontsize, zorder=zorder)
        text.set_path_effects([PathEffects.withStroke(linewidth=3, foreground="black")])


def adjust_lightness(color: str, amount: float = 0.5) -> tuple[float, float, float]:
    """
    In-/Decrease color brightness amount by factor.

    Helper to avoid having the user define background ec color value which is similar to background color.

    via https://stackoverflow.com/questions/37765197/darken-or-lighten-a-color-in-matplotlib
    """
    try:
        c = cnames[color]
    except KeyError:
        c = color
    c = colorsys.rgb_to_hls(*to_rgb(c))
    adjusted_c = colorsys.hls_to_rgb(c[0], max(0, min(1, amount * c[1])), c[2])
    return adjusted_c
