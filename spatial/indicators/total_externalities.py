import os
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from core.grids import SquareGrid, HexagonalGrid
from core.spatial_ops import SpatialValidator

from core.plotters import CostPlotter

warnings.filterwarnings('ignore')


class TotalExternalitiesAnalyzer :
    """
    Object-Oriented spatial pipeline for Combined Total Externalities.
    Merges Accidents, Emissions, and Noise. Applies dynamic population scaling
    (e.g., 1% to 100%), executes strict spatial validations, and plots the results.
    """

    def __init__(self, paths_dict: dict, stadtbezirke_json: str, output_dir: str, population_scale: float = 100.0) :
        self.paths = paths_dict
        self.stadtbezirke_json = stadtbezirke_json
        self.output_dir = output_dir
        self.population_scale = population_scale  # The dynamic scaling factor (100.0)

        self.target_crs = "EPSG:25832"
        self.grid_size = 1000

        # State variables
        self.df_bezirke = None
        self.df_grid = None
        self.df_hex = None

        self.map_bezirke = None
        self.map_grid = None
        self.map_hex = None

    def _validate_tabular_consistency(self, dfs: list, names: list, id_col: str, coord_cols: list = None) :
        """Cross-checks that all input CSVs have the exact same spatial IDs and coordinates."""
        print(f"Validating spatial consistency for {id_col} across input CSVs...")
        base_df = dfs[0]
        base_set = set(base_df[id_col])

        for i, df in enumerate(dfs[1 :], 1) :
            curr_set = set(df[id_col])
            if base_set != curr_set :
                raise ValueError(f"CRITICAL ERROR: ID mismatch between {names[0]} and {names[i]} for {id_col}.")

        if coord_cols :
            base_coords = base_df.sort_values(by=id_col)[coord_cols].reset_index(drop=True)
            for i, df in enumerate(dfs[1 :], 1) :
                curr_coords = df.sort_values(by=id_col)[coord_cols].reset_index(drop=True)
                if not np.allclose(base_coords.values, curr_coords.values, atol=1e-3) :
                    raise ValueError(f"CRITICAL ERROR: Coordinate mismatch between {names[0]} and {names[i]}.")

        print(f"Validation PASSED for {id_col} across input CSVs.")

    def _process_resolution(self, resolution: str, id_col: str, coord_cols: list = None) -> pd.DataFrame :
        """Loads, validates, merges, and SCALES the data for a specific resolution."""
        print(f"\nProcessing {resolution.upper()} data...")
        df_acd = pd.read_csv(self.paths["accidents"][resolution])
        df_emi = pd.read_csv(self.paths["emissions"][resolution])
        df_noi = pd.read_csv(self.paths["noise"][resolution])

        self._validate_tabular_consistency(
            [df_acd, df_emi, df_noi],
            ["Accidents", "Emissions", "Noise"],
            id_col, coord_cols
        )

        # 1. Standardize column names
        base_cols_acd = [id_col] + (coord_cols if coord_cols else []) + ['monetary_before', 'monetary_after']
        df_acd_sub = df_acd[base_cols_acd].copy()
        df_acd_sub.rename(
            columns={'monetary_before' : 'monetary_before_accidents', 'monetary_after' : 'monetary_after_accidents'},
            inplace=True)

        df_emi_sub = df_emi[[id_col, 'monetary_TOTAL_before', 'monetary_TOTAL_after']].copy()
        df_emi_sub.rename(columns={'monetary_TOTAL_before' : 'monetary_before_emissions',
                                   'monetary_TOTAL_after' : 'monetary_after_emissions'}, inplace=True)

        df_noi_sub = df_noi[[id_col, 'total_monetary_before', 'total_monetary_after']].copy()
        df_noi_sub.rename(columns={'total_monetary_before' : 'monetary_before_noise',
                                   'total_monetary_after' : 'monetary_after_noise'}, inplace=True)

        # 2. Merge sequentially
        df_merged = df_acd_sub.merge(df_emi_sub, on=id_col).merge(df_noi_sub, on=id_col)
        df_merged.fillna(0.0, inplace=True)

        # 3. APPLY POPULATION SCALING (e.g., * 100)
        print(f"Applying population scaling factor: x{self.population_scale}")
        monetary_cols = [
            'monetary_before_accidents', 'monetary_after_accidents',
            'monetary_before_emissions', 'monetary_after_emissions',
            'monetary_before_noise', 'monetary_after_noise'
        ]
        for col in monetary_cols :
            df_merged[col] = df_merged[col] * self.population_scale

        # 4. Calculate Total Externalities
        df_merged['total_externalities_before'] = df_merged['monetary_before_accidents'] + df_merged[
            'monetary_before_emissions'] + df_merged['monetary_before_noise']
        df_merged['total_externalities_after'] = df_merged['monetary_after_accidents'] + df_merged[
            'monetary_after_emissions'] + df_merged['monetary_after_noise']
        df_merged['total_externalities_difference'] = df_merged['total_externalities_after'] - df_merged[
            'total_externalities_before']

        final_cols = [id_col] + (coord_cols if coord_cols else []) + monetary_cols + [
            'total_externalities_before', 'total_externalities_after', 'total_externalities_difference'
        ]

        df_final = df_merged[final_cols]
        scale_pct = int(self.population_scale)
        output_csv = os.path.join(self.output_dir, f"{resolution}_externalities_{scale_pct}pct.csv")
        df_final.to_csv(output_csv, index=False)
        print(f"Exported scaled data to {output_csv}")

        return df_final

    def merge_with_geometries(self) :
        """Generates the background grids, validates centroids, and merges the data."""
        self.df_bezirke = self._process_resolution("bezirke", "sb_name")
        self.df_grid = self._process_resolution("grid", "grid_id", ["xcoord", "ycoord"])
        self.df_hex = self._process_resolution("hexagon", "hex_id", ["xcoord", "ycoord"])

        print("\nGenerating Spatial Polygons for Rendering...")
        raw_bounds = gpd.read_file(self.stadtbezirke_json).to_crs(self.target_crs)
        neighborhoods = raw_bounds[['sb_name', 'geometry']].dissolve(by='sb_name').reset_index()

        square_generator = SquareGrid(grid_size=self.grid_size, crs=self.target_crs)
        hex_generator = HexagonalGrid(grid_size=self.grid_size, crs=self.target_crs)

        grid_gdf = square_generator.generate_shape(neighborhoods)
        hex_gdf = hex_generator.generate_shape(neighborhoods)

        print("\nExecuting Final Polygon vs CSV Centroid Validation...")
        SpatialValidator.validate_geometry_centroids(self.df_grid, grid_gdf, 'grid_id')
        SpatialValidator.validate_geometry_centroids(self.df_hex, hex_gdf, 'hex_id')

        # Merge for visualization
        self.map_bezirke = neighborhoods.merge(self.df_bezirke, on='sb_name', how='inner')
        self.map_grid = grid_gdf.merge(self.df_grid, on='grid_id', how='inner')
        self.map_hex = hex_gdf.merge(self.df_hex, on='hex_id', how='inner')

    def generate_visualizations(self) :
        print("\nRendering maps and saving high-res PNGs...")
        plot_dir = os.path.join(self.output_dir, "plots")
        os.makedirs(plot_dir, exist_ok=True)

        # CostPlotter ensures red means BAD (Externalities increased)
        plotter = CostPlotter(alpha=0.75)

        geometries = [
            ("Stadtbezirke", self.map_bezirke),
            ("Square Grid", self.map_grid),
            ("Hexagon Grid", self.map_hex)
        ]

        configs = [
            ('total_externalities_before', 'Total Externalities Before'),
            ('total_externalities_after', 'Total Externalities After'),
            ('total_externalities_difference', 'Total Externalities Difference')
        ]

        for geom_name, gdf in geometries :
            for col_name, base_title in configs :
                title = f"{base_title} - {geom_name}"
                out_file = os.path.join(plot_dir, f"{title.replace(' ', '_').replace('-', '').lower()}.png")

                vmin, vmax = None, None
                if 'difference' not in col_name.lower() :
                    partner_col = col_name.replace('before', 'after') if 'before' in col_name else col_name.replace(
                        'after', 'before')
                    if partner_col in gdf.columns :
                        vmin = min(gdf[col_name].min(), gdf[partner_col].min())
                        vmax = max(gdf[col_name].max(), gdf[partner_col].max())

                plotter.plot_map(gdf, col_name, title, out_file, vmin, vmax)

    def run_pipeline(self) :
        os.makedirs(self.output_dir, exist_ok=True)
        self.merge_with_geometries()
        self.generate_visualizations()
        print("Total Externalities pipeline execution completed successfully.")