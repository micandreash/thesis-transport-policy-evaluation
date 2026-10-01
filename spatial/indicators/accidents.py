import os
import warnings

import geopandas as gpd
import pandas as pd
from core.grids import SquareGrid, HexagonalGrid
from core.spatial_ops import NetworkParser, SpatialAggregator
from core.plotters import CostPlotter

warnings.filterwarnings('ignore')


class AccidentsAnalyzer :
    """
    Object-Oriented spatial pipeline for Accidents indicator.
    Reads aggregated extension CSVs, applies length-based apportionment
    for spatial mapping, and generates standardized visual outputs.
    """

    def __init__(self, network_xml: str, ext_info_before: str, ext_cost_before: str,
                 ext_info_after: str, ext_cost_after: str, stadtbezirke_json: str, output_dir: str) :
        self.network_xml = network_xml
        self.ext_info_before = ext_info_before
        self.ext_cost_before = ext_cost_before
        self.ext_info_after = ext_info_after
        self.ext_cost_after = ext_cost_after
        self.stadtbezirke_json = stadtbezirke_json
        self.output_dir = output_dir

        self.target_crs = "EPSG:25832"
        self.neighborhood_col = "sb_name"
        self.grid_size = 1000

        # State variables
        self.neighborhoods = None
        self.network_gdf = None
        self.link_accidents = None
        self.grid_gdf = None
        self.hex_gdf = None
        self.map_stadtbezirke = None
        self.map_grid = None
        self.map_hex = None

        self.export_metrics = [
            'kmt_before', 'kmt_after', 'kmt_difference',
            'monetary_before', 'monetary_after', 'monetary_difference'
        ]

    def _extract_metrics(self, info_csv: str, cost_csv: str) -> pd.DataFrame :
        """Helper method to load extension outputs and scale them down to 1% baseline."""
        print(f"Extracting metrics from extension CSVs:\n- {info_csv}\n- {cost_csv}")
        df_info = pd.read_csv(info_csv, sep=';', dtype=str)
        df_cost = pd.read_csv(cost_csv, sep=';', dtype=str)

        df_info.columns = df_info.columns.str.strip()
        df_cost.columns = df_cost.columns.str.strip()

        df_info = df_info.rename(columns={'Link_ID' : 'LinkId', 'Link ID' : 'LinkId'})
        df_cost = df_cost.rename(columns={'Link ID' : 'LinkId', 'Link_ID' : 'LinkId'})

        df_info = df_info[['LinkId', 'demandPerDay']].copy()
        df_info['demandPerDay'] = pd.to_numeric(df_info['demandPerDay'], errors='coerce').fillna(0)

        df_cost = df_cost[['LinkId', 'Costs per Day [EUR]']].copy()
        df_cost['Costs per Day [EUR]'] = pd.to_numeric(df_cost['Costs per Day [EUR]'], errors='coerce').fillna(0)

        df_ext = pd.merge(df_info, df_cost, on='LinkId', how='outer').fillna(0)

        lengths_db = self.network_gdf.set_index('LinkId')['length_km'].to_dict()
        df_ext['length_km'] = df_ext['LinkId'].map(lengths_db).fillna(0)

        # Scale metrics down by 100 for the 1% scenario baseline
        df_ext['kmt'] = (df_ext['demandPerDay'] / 100.0) * df_ext['length_km']
        df_ext['monetary'] = df_ext['Costs per Day [EUR]'] / 100.0

        return df_ext[['LinkId', 'kmt', 'monetary']]

    def load_and_prepare_data(self) :
        print("Loading boundaries and parsing network geometry...")
        raw_bounds = gpd.read_file(self.stadtbezirke_json).to_crs(self.target_crs)
        self.neighborhoods = raw_bounds[[self.neighborhood_col, 'geometry']].dissolve(
            by=self.neighborhood_col).reset_index()

        parser = NetworkParser(self.network_xml, self.target_crs)
        self.network_gdf = parser.get_network_gdf()

        df_before = self._extract_metrics(self.ext_info_before, self.ext_cost_before)
        df_after = self._extract_metrics(self.ext_info_after, self.ext_cost_after)

        print("Intersecting network with boundaries to establish base segments...")
        intersected_links = gpd.overlay(self.network_gdf, self.neighborhoods, how='intersection')
        intersected_links['segment_length'] = intersected_links.geometry.length

        total_length = intersected_links.groupby('LinkId')['segment_length'].transform('sum')
        raw_weight = intersected_links['segment_length'] / total_length
        segment_count = intersected_links.groupby('LinkId')['LinkId'].transform('count')
        intersected_links['apportion_weight'] = raw_weight.fillna(1.0 / segment_count)

        print("Applying apportionment weights to Link-level metrics...")
        links_merged = intersected_links.merge(df_before, on='LinkId', how='left')
        self.link_accidents = links_merged.merge(df_after, on='LinkId', how='left', suffixes=('_before', '_after'))

        num_cols = self.link_accidents.select_dtypes(include=['number']).columns
        self.link_accidents[num_cols] = self.link_accidents[num_cols].fillna(0.0)

        for metric in ['kmt', 'monetary'] :
            self.link_accidents[f'{metric}_before'] = self.link_accidents[f'{metric}_before'] * self.link_accidents[
                'apportion_weight']
            self.link_accidents[f'{metric}_after'] = self.link_accidents[f'{metric}_after'] * self.link_accidents[
                'apportion_weight']
            self.link_accidents[f'{metric}_difference'] = self.link_accidents[f'{metric}_after'] - self.link_accidents[
                f'{metric}_before']

    def process_spatial_aggregation(self) :
        print("Generating grid polygons...")
        square_generator = SquareGrid(grid_size=self.grid_size, crs=self.target_crs)
        hex_generator = HexagonalGrid(grid_size=self.grid_size, crs=self.target_crs)

        self.grid_gdf = square_generator.generate_shape(self.neighborhoods)
        self.hex_gdf = hex_generator.generate_shape(self.neighborhoods)

        print("Aggregating metrics spatially (Length-based Apportionment)...")
        # 1. Bezirke (Since link_accidents is already explicitly cut by neighborhood, simple groupby suffices)
        agg_bezirke = self.link_accidents.groupby(self.neighborhood_col)[self.export_metrics].sum().reset_index()
        self.map_stadtbezirke = self.neighborhoods.merge(agg_bezirke, on=self.neighborhood_col, how="left")

        # 2. Square Grid (Overlay line-to-polygon cuts)
        self.map_grid = SpatialAggregator.aggregate_lines(
            self.link_accidents, self.grid_gdf, 'grid_id', self.export_metrics
        )
        self.map_grid['xcoord'] = self.map_grid.geometry.centroid.x
        self.map_grid['ycoord'] = self.map_grid.geometry.centroid.y

        # 3. Hexagon Grid
        self.map_hex = SpatialAggregator.aggregate_lines(
            self.link_accidents, self.hex_gdf, 'hex_id', self.export_metrics
        )
        self.map_hex['xcoord'] = self.map_hex.geometry.centroid.x
        self.map_hex['ycoord'] = self.map_hex.geometry.centroid.y

    def export_results(self) :
        print("Exporting tabular and spatial data...")
        os.makedirs(self.output_dir, exist_ok=True)
        gpkg_path = os.path.join(self.output_dir, "spatial_accidents.gpkg")
        if os.path.exists(gpkg_path) :
            os.remove(gpkg_path)

        # Links Export
        link_export_cols = ['LinkId', self.neighborhood_col] + self.export_metrics
        self.link_accidents[link_export_cols].to_csv(os.path.join(self.output_dir, "accidents_aggregated_links.csv"),
                                                     index=False)
        self.link_accidents[['LinkId', 'geometry'] + self.export_metrics].to_file(gpkg_path, layer='accidents_links',
                                                                                  driver='GPKG')

        # Bezirke Export
        self.map_stadtbezirke[[self.neighborhood_col] + self.export_metrics].to_csv(
            os.path.join(self.output_dir, "accidents_aggregated_bezirke.csv"), index=False)
        self.map_stadtbezirke.to_file(gpkg_path, layer='accidents_bezirke', driver='GPKG')

        # Grid Export
        self.map_grid[['grid_id', 'xcoord', 'ycoord'] + self.export_metrics].to_csv(
            os.path.join(self.output_dir, "accidents_aggregated_grid.csv"), index=False)
        self.map_grid.to_file(gpkg_path, layer='accidents_grid', driver='GPKG')

        # Hex Export
        self.map_hex[['hex_id', 'xcoord', 'ycoord'] + self.export_metrics].to_csv(
            os.path.join(self.output_dir, "accidents_aggregated_hex.csv"), index=False)
        self.map_hex.to_file(gpkg_path, layer='accidents_hex', driver='GPKG')

    def generate_visualizations(self) :
        print("Rendering maps and saving high-res PNGs...")
        plot_dir = os.path.join(self.output_dir, "plots")
        os.makedirs(plot_dir, exist_ok=True)

        # Initialize the CostPlotter (Positive diff = Red/Bad)
        plotter = CostPlotter(alpha=0.75)

        geometries = [
            ("Stadtbezirke", self.map_stadtbezirke),
            ("Square Grid", self.map_grid),
            ("Hexagon Grid", self.map_hex)
        ]

        metrics = [
            ('kmt', 'KMT', '{x:,.0f}'),
            ('monetary', 'Monetary EUR', '{x:,.0f}')
        ]

        for geom_name, gdf in geometries :
            for metric_col, metric_label, fmt in metrics :
                before_col = f"{metric_col}_before"
                after_col = f"{metric_col}_after"
                diff_col = f"{metric_col}_difference"

                vmin = min(gdf[before_col].min(), gdf[after_col].min())
                vmax = max(gdf[before_col].max(), gdf[after_col].max())

                title_b = f"{metric_label} Before - {geom_name}"
                plotter.plot_map(gdf, before_col, title_b,
                                 os.path.join(plot_dir, f"{title_b.replace(' ', '_').replace('-', '').lower()}.png"),
                                 vmin, vmax, fmt)

                title_a = f"{metric_label} After - {geom_name}"
                plotter.plot_map(gdf, after_col, title_a,
                                 os.path.join(plot_dir, f"{title_a.replace(' ', '_').replace('-', '').lower()}.png"),
                                 vmin, vmax, fmt)

                title_d = f"{metric_label} Difference - {geom_name}"
                plotter.plot_map(gdf, diff_col, title_d,
                                 os.path.join(plot_dir, f"{title_d.replace(' ', '_').replace('-', '').lower()}.png"),
                                 fmt_string=fmt)

    def run_pipeline(self) :
        self.load_and_prepare_data()
        self.process_spatial_aggregation()
        self.export_results()
        self.generate_visualizations()
        print("Accidents pipeline execution completed successfully.")