import math
from abc import ABC, abstractmethod

import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon


class BaseGrid(ABC) :
    """
    Abstract base class for all grid generators.
    Enforces a strict grid_size property and provides a unified method
    to trim the generated grid to the exact municipal boundaries.
    """

    def __init__(self, grid_size: float, crs: str = "EPSG:25832") :
        self.grid_size = grid_size  # Trigger the setter
        self.crs = crs

    @property
    def grid_size(self) -> float :
        return self._grid_size

    @grid_size.setter
    def grid_size(self, value: float) :
        if value <= 0 :
            raise ValueError("Grid size must be strictly positive (greater than 0).")
        self._grid_size = value

    @abstractmethod
    def generate_raw_grid(self, bounds: tuple) -> gpd.GeoDataFrame :
        """
        Child classes must implement this method to mathematically construct
        the polygons across the total bounds (xmin, ymin, xmax, ymax).
        Must return a GeoDataFrame with a unique ID column (e.g., 'grid_id') and geometry.
        """
        pass

    def generate_shape(self, boundary_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame :
        """
        Template method that dictates the overall grid generation pipeline:
        1. Extract the bounding box.
        2. Call the child's raw grid generation logic.
        3. Trim the resulting grid cleanly against the actual municipal polygon.
        """
        # 1. Generate the raw mathematical grid covering the rectangular bounding box
        bounds = boundary_gdf.total_bounds
        raw_grid = self.generate_raw_grid(bounds)

        # 2. Identify the ID column dynamically ('grid_id' or 'hex_id')
        id_col = raw_grid.columns[0]

        # 3. Trim the grid to only keep polygons that intersect the actual city boundary
        print(f"Trimming {self.__class__.__name__} to exact municipal boundaries...")
        trimmed_grid = gpd.sjoin(
            raw_grid,
            boundary_gdf[['geometry']],
            how="inner",
            predicate="intersects"
        )

        # 4. Clean up the spatial join artifacts
        trimmed_grid = trimmed_grid.drop_duplicates(id_col).drop(columns=['index_right'], errors='ignore')

        # 5. Reset index for clean exports
        return trimmed_grid.reset_index(drop=True)


class SquareGrid(BaseGrid) :
    """Generates standard square polygons."""

    def generate_raw_grid(self, bounds: tuple) -> gpd.GeoDataFrame :
        print(f"Generating raw Square Grid polygons with {self.grid_size}m spacing...")
        xmin, ymin, xmax, ymax = bounds

        cols = np.arange(xmin, xmax + self.grid_size, self.grid_size)
        rows = np.arange(ymin, ymax + self.grid_size, self.grid_size)

        polygons = []
        for x in cols[:-1] :
            for y in rows[:-1] :
                polygons.append(Polygon([
                    (x, y),
                    (x + self.grid_size, y),
                    (x + self.grid_size, y + self.grid_size),
                    (x, y + self.grid_size)
                ]))

        return gpd.GeoDataFrame({'grid_id' : range(len(polygons))}, geometry=polygons, crs=self.crs)


class HexagonalGrid(BaseGrid) :
    """Generates perfect pointy-topped hexagonal polygons."""

    def generate_raw_grid(self, bounds: tuple) -> gpd.GeoDataFrame :
        print(f"Generating raw Hexagonal Grid polygons with {self.grid_size}m centroid distance...")
        xmin, ymin, xmax, ymax = bounds

        w = self.grid_size
        R = w / math.sqrt(3)
        dx = w
        dy = 1.5 * R

        polygons = []
        row_idx = 0
        y = ymin

        while y <= ymax + dy :
            x_offset = w / 2.0 if row_idx % 2 != 0 else 0
            x = xmin + x_offset

            while x <= xmax + dx :
                vertices = [
                    (x, y + R),
                    (x + w / 2.0, y + R / 2.0),
                    (x + w / 2.0, y - R / 2.0),
                    (x, y - R),
                    (x - w / 2.0, y - R / 2.0),
                    (x - w / 2.0, y + R / 2.0)
                ]
                polygons.append(Polygon(vertices))
                x += dx
            y += dy
            row_idx += 1

        return gpd.GeoDataFrame({'hex_id' : range(len(polygons))}, geometry=polygons, crs=self.crs)