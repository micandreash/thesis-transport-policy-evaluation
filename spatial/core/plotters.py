import warnings
from abc import ABC, abstractmethod

import contextily as cx
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import StrMethodFormatter

warnings.filterwarnings('ignore')

class BaseSpatialPlotter(ABC):
    """
    Abstract base class for all spatial map plotters.
    Handles figure setup, basemap addition, legend formatting, and exporting.
    Child classes dictate the specific colormap logic for difference maps.
    """
    def __init__(self, alpha: float = 0.75, base_cmap: str = 'YlOrRd'):
        self.alpha = alpha
        self.base_cmap = base_cmap  # Default colormap for Before/After maps

    @abstractmethod
    def get_difference_cmap(self) -> LinearSegmentedColormap:
        """
        Must be implemented by child classes to return the correct diverging
        colormap based on whether a positive difference is 'good' or 'bad'.
        """
        pass

    def plot_map(
        self,
        gdf_map: gpd.GeoDataFrame,
        col_name: str,
        title: str,
        output_path: str,
        vmin: float = None,
        vmax: float = None,
        fmt_string: str = '{x:,.0f}'
    ):
        """
        Main plotting engine. Dynamically adjusts symbology if it's a difference map,
        applies consistent Esri basemaps, and exports high-res PNGs cleanly.
        """
        fig, ax = plt.subplots(figsize=(9, 8))
        fig.canvas.manager.set_window_title(title)

        is_diff = 'diff' in col_name.lower() or 'difference' in col_name.lower()
        cmap = self.get_difference_cmap() if is_diff else self.base_cmap

        plot_kwargs = {
            'column': col_name,
            'cmap': cmap,
            'ax': ax,
            'linewidth': 0.5,
            'edgecolor': 'white',
            'alpha': self.alpha,
            'legend': True,
            'legend_kwds': {
                'label': "",
                'orientation': "horizontal",
                'pad': 0.02,
                'format': StrMethodFormatter(fmt_string),
                'shrink': 1
            }
        }

        # Value Scaling Logic
        if is_diff:
            # Force absolute symmetry around 0 for difference maps
            max_abs = max(abs(gdf_map[col_name].min()), abs(gdf_map[col_name].max()))
            max_abs = 0.01 if max_abs == 0 else max_abs
            plot_kwargs['vmin'] = -max_abs
            plot_kwargs['vmax'] = max_abs
        else:
            # Use provided global bounds to sync 'Before' and 'After' maps
            if vmin is not None:
                plot_kwargs['vmin'] = vmin
            if vmax is not None:
                plot_kwargs['vmax'] = vmax

        # Execute Plot
        gdf_map.plot(**plot_kwargs)

        # Format Legend Text Size
        cax = fig.axes[-1]
        cax.tick_params(labelsize=20)

        # Add High-Res Esri Basemap
        cx.add_basemap(
            ax,
            crs=gdf_map.crs,
            source=cx.providers.Esri.WorldStreetMap,
            zoom='auto',
            zoom_adjust=1
        )

        ax.set_axis_off()
        plt.tight_layout()

        # Save and aggressively close to free up RAM (prevents IDE freezing)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)


class CostPlotter(BaseSpatialPlotter):
    """
    Plotter for Negative Externalities (Accidents, Emissions, Noise).
    A positive difference (+) means costs INCREASED, which is BAD.
    Diverging Colormap: Blue (Benefit/Decrease) -> White (0) -> Red (Cost/Increase).
    """
    def get_difference_cmap(self) -> LinearSegmentedColormap:
        diff_colors = ['#00008B', '#9999FF', '#F5F5F5', '#FF9999', '#8B0000']
        diff_nodes = [0.0, 0.499, 0.5, 0.501, 1.0]
        return LinearSegmentedColormap.from_list('cost_diff', list(zip(diff_nodes, diff_colors)))


class UtilityPlotter(BaseSpatialPlotter):
    """
    Plotter for Positive Externalities (Accessibility).
    A positive difference (+) means utility INCREASED, which is GOOD.
    Diverging Colormap: Red (Loss/Decrease) -> White (0) -> Blue (Gain/Increase).
    """
    def get_difference_cmap(self) -> LinearSegmentedColormap:
        # Colors are inverted compared to CostPlotter
        diff_colors = ['#8B0000', '#FF9999', '#F5F5F5', '#9999FF', '#00008B']
        diff_nodes = [0.0, 0.499, 0.5, 0.501, 1.0]
        return LinearSegmentedColormap.from_list('util_diff', list(zip(diff_nodes, diff_colors)))