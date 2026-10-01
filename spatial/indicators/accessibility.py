import os
import warnings

import geopandas as gpd
import pandas as pd
from core.grids import SquareGrid, HexagonalGrid
from core.spatial_ops import SpatialAggregator
from core.plotters import UtilityPlotter

warnings.filterwarnings('ignore')


class AccessibilityAnalyzer :
    """
    Object-Oriented spatial pipeline for Accessibility indicator.
    Calculates utility differences, monetizes them, aggregates spatially (mean & sum),
    and generates automated visualizations.
    """

    def __init__(self, csv_before: str, csv_after: str, stadtbezirke_json: str, output_dir: str) :
        self.csv_before = csv_before
        self.csv_after = csv_after
        self.stadtbezirke_json = stadtbezirke_json
        self.output_dir = output_dir

        self.target_crs = "EPSG:25832"
        self.neighborhood_col = "sb_name"
        self.grid_size = 1000
        self.beta_money = 0.310998

        # State variables to store processed data
        self.points_inside = None
        self.neighborhoods = None
        self.grid_gdf = None
        self.hex_gdf = None
        self.map_stadtbezirke = None
        self.map_grid = None
        self.map_hex = None

        # Define output columns
        self.agg_cols = [
            'average_car_accessibility_before', 'average_car_accessibility_after', 'average_car_accessibility_diff',
            'sum_car_accessibility_before', 'sum_car_accessibility_after', 'sum_car_accessibility_diff',
            'average_monetary_accessibility_before', 'average_monetary_accessibility_after',
            'average_monetary_accessibility_diff',
            'sum_monetary_accessibility_before', 'sum_monetary_accessibility_after', 'sum_monetary_accessibility_diff'
        ]

    def load_and_prepare_data(self) :
        print("Loading Accessibility CSV files...")
        df_before = pd.read_csv(self.csv_before)
        df_after = pd.read_csv(self.csv_after)

        print("Cleaning coordinates and merging scenarios...")
        df_before['xcoord'] = df_before['xcoord'].astype(str).str.replace("'", "").astype(float)
        df_before['ycoord'] = df_before['ycoord'].astype(str).str.replace("'", "").astype(float)

        df_merged = df_before.merge(
            df_after[['id', 'car_accessibility']],
            on='id',
            suffixes=('_before', '_after')
        )

        df_merged['car_accessibility_before'] = pd.to_numeric(df_merged['car_accessibility_before'], errors='coerce')
        df_merged['car_accessibility_after'] = pd.to_numeric(df_merged['car_accessibility_after'], errors='coerce')
        df_merged['car_accessibility_diff'] = df_merged['car_accessibility_after'] - df_merged[
            'car_accessibility_before']

        print("Applying beta_money for monetization...")
        df_merged['monetary_accessibility_before'] = df_merged['car_accessibility_before'] / self.beta_money
        df_merged['monetary_accessibility_after'] = df_merged['car_accessibility_after'] / self.beta_money
        df_merged['monetary_accessibility_diff'] = df_merged['monetary_accessibility_after'] - df_merged[
            'monetary_accessibility_before']

        print("Converting to GeoDataFrame...")
        gdf_points = gpd.GeoDataFrame(
            df_merged,
            geometry=gpd.points_from_xy(df_merged['xcoord'], df_merged['ycoord']),
            crs=self.target_crs
        )

        print("Loading boundaries and filtering points...")
        self.neighborhoods = gpd.read_file(self.stadtbezirke_json).to_crs(self.target_crs)
        self.neighborhoods = self.neighborhoods[[self.neighborhood_col, 'geometry']].dissolve(
            by=self.neighborhood_col).reset_index()

        self.points_inside = gpd.sjoin(gdf_points, self.neighborhoods[['geometry']], how="inner", predicate="intersects")
        self.points_inside = self.points_inside.drop(columns=['index_right'], errors='ignore')

    def process_spatial_aggregation(self) :
        print("Generating grid polygons...")
        square_generator = SquareGrid(grid_size=self.grid_size, crs=self.target_crs)
        hex_generator = HexagonalGrid(grid_size=self.grid_size, crs=self.target_crs)

        self.grid_gdf = square_generator.generate_shape(self.neighborhoods)
        self.hex_gdf = hex_generator.generate_shape(self.neighborhoods)

        # Calculate centroids for tabular export
        self.grid_gdf['xcoord'] = self.grid_gdf.geometry.centroid.x
        self.grid_gdf['ycoord'] = self.grid_gdf.geometry.centroid.y
        self.hex_gdf['xcoord'] = self.hex_gdf.geometry.centroid.x
        self.hex_gdf['ycoord'] = self.hex_gdf.geometry.centroid.y

        print("Aggregating metrics spatially (Average and Sum)...")
        # 1. Bezirke
        self.map_stadtbezirke = SpatialAggregator.aggregate_points_mean_and_sum(
            self.points_inside, self.neighborhoods, self.neighborhood_col,
            ['car_accessibility_before', 'car_accessibility_after', 'car_accessibility_diff',
             'monetary_accessibility_before', 'monetary_accessibility_after', 'monetary_accessibility_diff']
        )

        # 2. Square Grid
        self.map_grid = SpatialAggregator.aggregate_points_mean_and_sum(
            self.points_inside, self.grid_gdf, 'grid_id',
            ['car_accessibility_before', 'car_accessibility_after', 'car_accessibility_diff',
             'monetary_accessibility_before', 'monetary_accessibility_after', 'monetary_accessibility_diff']
        )

        # 3. Hexagon Grid
        self.map_hex = SpatialAggregator.aggregate_points_mean_and_sum(
            self.points_inside, self.hex_gdf, 'hex_id',
            ['car_accessibility_before', 'car_accessibility_after', 'car_accessibility_diff',
             'monetary_accessibility_before', 'monetary_accessibility_after', 'monetary_accessibility_diff']
        )

    def export_results(self) :
        print("Exporting tabular data to CSV...")
        os.makedirs(self.output_dir, exist_ok=True)

        points_export_cols = ['id', 'xcoord', 'ycoord',
                              'car_accessibility_before', 'car_accessibility_after', 'car_accessibility_diff',
                              'monetary_accessibility_before', 'monetary_accessibility_after',
                              'monetary_accessibility_diff']

        self.points_inside[points_export_cols].to_csv(os.path.join(self.output_dir, "accessibilities_points.csv"),
                                                      index=False)
        self.map_stadtbezirke[[self.neighborhood_col] + self.agg_cols].to_csv(
            os.path.join(self.output_dir, "accessibilities_stadtbezirke.csv"), index=False)
        self.map_grid[['grid_id', 'xcoord', 'ycoord'] + self.agg_cols].to_csv(
            os.path.join(self.output_dir, "accessibilities_square_grid.csv"), index=False)
        self.map_hex[['hex_id', 'xcoord', 'ycoord'] + self.agg_cols].to_csv(
            os.path.join(self.output_dir, "accessibilities_hex_grid.csv"), index=False)

        print("Exporting spatial data to GeoPackage...")
        gpkg_path = os.path.join(self.output_dir, "spatial_accessibilities.gpkg")
        if os.path.exists(gpkg_path) :
            os.remove(gpkg_path)

        self.map_stadtbezirke.to_file(gpkg_path, layer='stadtbezirke', driver="GPKG")
        self.map_grid.to_file(gpkg_path, layer='square_grid', driver="GPKG")
        self.map_hex.to_file(gpkg_path, layer='hexagon_grid', driver="GPKG")

    def generate_visualizations(self) :
        print("Rendering maps and saving high-res PNGs...")
        plot_dir = os.path.join(self.output_dir, "plots")
        os.makedirs(plot_dir, exist_ok=True)

        # Initialize the UtilityPlotter (Positive diff = Blue/Good)
        plotter = UtilityPlotter(alpha=0.75, base_cmap='YlGn')

        metrics = [
            ('average_car_accessibility', 'Average Car Accessibility'),
            ('sum_car_accessibility', 'Sum Car Accessibility'),
            ('sum_monetary_accessibility', 'Sum Monetary Accessibility')
        ]

        geometries = [
            ("Stadtbezirke", self.map_stadtbezirke),
            ("Square Grid", self.map_grid),
            ("Hexagon Grid", self.map_hex)
        ]

        # Generate the 27 configurations dynamically
        for geom_name, gdf in geometries :
            for metric_col, metric_label in metrics :
                before_col = f"{metric_col}_before"
                after_col = f"{metric_col}_after"
                diff_col = f"{metric_col}_diff"

                # Plot Before
                vmin = min(gdf[before_col].min(), gdf[after_col].min())
                vmax = max(gdf[before_col].max(), gdf[after_col].max())

                title_b = f"{metric_label} Before - {geom_name}"
                plotter.plot_map(gdf, before_col, title_b,
                                 os.path.join(plot_dir, f"{title_b.replace(' ', '_').replace('-', '').lower()}.png"),
                                 vmin, vmax)

                # Plot After
                title_a = f"{metric_label} After - {geom_name}"
                plotter.plot_map(gdf, after_col, title_a,
                                 os.path.join(plot_dir, f"{title_a.replace(' ', '_').replace('-', '').lower()}.png"),
                                 vmin, vmax)

                # Plot Difference
                title_d = f"{metric_label} Difference - {geom_name}"
                plotter.plot_map(gdf, diff_col, title_d,
                                 os.path.join(plot_dir, f"{title_d.replace(' ', '_').replace('-', '').lower()}.png"))

    def run_pipeline(self) :
        self.load_and_prepare_data()
        self.process_spatial_aggregation()
        self.export_results()
        self.generate_visualizations()
        print("Accessibility pipeline execution completed successfully.")