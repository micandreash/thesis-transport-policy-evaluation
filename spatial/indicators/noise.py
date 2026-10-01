import os
import warnings

import geopandas as gpd
import pandas as pd
from core.grids import SquareGrid, HexagonalGrid
from core.spatial_ops import SpatialAggregator
from core.plotters import CostPlotter

warnings.filterwarnings('ignore')


class NoiseAnalyzer :
    """
    Object-Oriented spatial pipeline for Noise indicator.
    Loads hourly damage data from MATSim Noise Extension, maps them to receiver
    point coordinates, scales them to 1% baseline, and aggregates spatially.
    """

    def __init__(self, rp_coords_file: str, damages_dir_before: str, damages_dir_after: str,
                 stadtbezirke_json: str, output_dir: str) :
        self.rp_coords_file = rp_coords_file
        self.damages_dir_before = damages_dir_before
        self.damages_dir_after = damages_dir_after
        self.stadtbezirke_json = stadtbezirke_json
        self.output_dir = output_dir

        self.target_crs = "EPSG:25832"
        self.neighborhood_col = "sb_name"
        self.grid_size = 1000

        # State variables
        self.gdf_rp = None
        self.df_rp = None
        self.neighborhoods = None
        self.grid_gdf = None
        self.hex_gdf = None
        self.map_bezirke = None
        self.map_grid = None
        self.map_hex = None
        self.metric_cols = []

    def _load_extension_damages(self, damage_dir: str, rp_ids_needed: list) -> dict :
        """Loads hourly damage data and scales it down by 100 for the 1% scenario baseline."""
        print(f"Loading hourly damages data from {damage_dir}...")
        rp_ids_set = set(rp_ids_needed)
        damage_data = {rp_id : {h : 0.0 for h in range(24)} for rp_id in rp_ids_set}

        for h in range(24) :
            time_sec = (h + 1) * 3600.0
            file_path = os.path.join(damage_dir, f"damages_receiverPoint_{time_sec}.csv")

            if os.path.exists(file_path) :
                df_dmg = pd.read_csv(file_path, sep=';')
                rp_col, dmg_col = df_dmg.columns[0], df_dmg.columns[1]

                df_dmg['clean_id'] = df_dmg[rp_col].apply(lambda x : str(int(float(x))))
                df_filtered = df_dmg[df_dmg['clean_id'].isin(rp_ids_set)]

                for _, row in df_filtered.iterrows() :
                    # Scale down from 100% back to 1% baseline
                    damage_data[row['clean_id']][h] = float(row[dmg_col]) / 100.0
            else :
                print(f"Warning: File not found -> {file_path}")

        return damage_data

    def load_and_prepare_data(self) :
        print("Loading Receiver Point coordinates...")
        df_rp_coords = pd.read_csv(self.rp_coords_file)
        rp_ids_clean = [str(int(float(rp))) for rp in df_rp_coords['id'].values]

        x_map = dict(zip(rp_ids_clean, df_rp_coords['xcoord']))
        y_map = dict(zip(rp_ids_clean, df_rp_coords['ycoord']))

        stats_before = self._load_extension_damages(self.damages_dir_before, rp_ids_clean)
        stats_after = self._load_extension_damages(self.damages_dir_after, rp_ids_clean)

        print("Compiling spatial receiver data...")
        records = []

        for rp_id in rp_ids_clean :
            row = {"receiver_id" : rp_id, "x" : x_map[rp_id], "y" : y_map[rp_id]}
            tot_b, tot_a = 0.0, 0.0

            for h in range(24) :
                k = str(h).zfill(2) + ":00"
                cb = stats_before[rp_id][h]
                ca = stats_after[rp_id][h]

                row[f"monetary_before_{k}"] = cb
                row[f"monetary_after_{k}"] = ca
                row[f"monetary_diff_{k}"] = ca - cb

                tot_b += cb
                tot_a += ca

            row["total_monetary_before"] = tot_b
            row["total_monetary_after"] = tot_a
            row["total_monetary_diff"] = tot_a - tot_b
            records.append(row)

        self.df_rp = pd.DataFrame(records)

        mon_b_cols = [f"monetary_before_{str(h).zfill(2)}:00" for h in range(24)]
        mon_a_cols = [f"monetary_after_{str(h).zfill(2)}:00" for h in range(24)]
        mon_d_cols = [f"monetary_diff_{str(h).zfill(2)}:00" for h in range(24)]
        tot_cols = ["total_monetary_before", "total_monetary_after", "total_monetary_diff"]

        self.metric_cols = mon_b_cols + mon_a_cols + mon_d_cols + tot_cols

        self.df_rp = self.df_rp[["receiver_id", "x", "y"] + self.metric_cols]
        self.gdf_rp = gpd.GeoDataFrame(
            self.df_rp,
            geometry=gpd.points_from_xy(self.df_rp.x, self.df_rp.y),
            crs=self.target_crs
        )

        print("Loading spatial boundaries...")
        raw_bounds = gpd.read_file(self.stadtbezirke_json).to_crs(self.target_crs)
        self.neighborhoods = raw_bounds[[self.neighborhood_col, 'geometry']].dissolve(
            by=self.neighborhood_col).reset_index()

    def process_spatial_aggregation(self) :
        print("Generating grid polygons...")
        square_generator = SquareGrid(grid_size=self.grid_size, crs=self.target_crs)
        hex_generator = HexagonalGrid(grid_size=self.grid_size, crs=self.target_crs)

        self.grid_gdf = square_generator.generate_shape(self.neighborhoods)
        self.hex_gdf = hex_generator.generate_shape(self.neighborhoods)

        print("Aggregating points to polygons (Sum)...")
        # 1. Bezirke
        self.map_bezirke = SpatialAggregator.aggregate_points_sum(
            self.gdf_rp, self.neighborhoods, self.neighborhood_col, self.metric_cols, unique_id_col='receiver_id'
        )

        # 2. Square Grid
        self.map_grid = SpatialAggregator.aggregate_points_sum(
            self.gdf_rp, self.grid_gdf, 'grid_id', self.metric_cols, unique_id_col='receiver_id'
        )
        self.map_grid['xcoord'] = self.map_grid.geometry.centroid.x
        self.map_grid['ycoord'] = self.map_grid.geometry.centroid.y

        # 3. Hexagon Grid
        self.map_hex = SpatialAggregator.aggregate_points_sum(
            self.gdf_rp, self.hex_gdf, 'hex_id', self.metric_cols, unique_id_col='receiver_id'
        )
        self.map_hex['xcoord'] = self.map_hex.geometry.centroid.x
        self.map_hex['ycoord'] = self.map_hex.geometry.centroid.y

    def export_results(self) :
        print("Exporting tabular and spatial data...")
        os.makedirs(self.output_dir, exist_ok=True)
        gpkg_path = os.path.join(self.output_dir, "noise_spatial_results.gpkg")

        if os.path.exists(gpkg_path) :
            os.remove(gpkg_path)

        # Receivers
        self.df_rp.to_csv(os.path.join(self.output_dir, "noise_aggregated_receivers.csv"), index=False)
        self.gdf_rp.to_file(gpkg_path, layer='noise_receivers', driver='GPKG')

        # Bezirke
        self.map_bezirke[[self.neighborhood_col] + self.metric_cols].to_csv(
            os.path.join(self.output_dir, "noise_aggregated_bezirke.csv"), index=False)
        self.map_bezirke.to_file(gpkg_path, layer='noise_bezirke', driver='GPKG')

        # Grid
        grid_export_cols = ['grid_id', 'xcoord', 'ycoord'] + self.metric_cols
        self.map_grid[grid_export_cols].to_csv(os.path.join(self.output_dir, "noise_aggregated_grid.csv"), index=False)
        self.map_grid.to_file(gpkg_path, layer='noise_grid', driver='GPKG')

        # Hex
        hex_export_cols = ['hex_id', 'xcoord', 'ycoord'] + self.metric_cols
        self.map_hex[hex_export_cols].to_csv(os.path.join(self.output_dir, "noise_aggregated_hex.csv"), index=False)
        self.map_hex.to_file(gpkg_path, layer='noise_hex', driver='GPKG')

    def generate_visualizations(self) :
        print("Rendering maps and saving high-res PNGs...")
        plot_dir = os.path.join(self.output_dir, "plots")
        os.makedirs(plot_dir, exist_ok=True)

        # CostPlotter ensures red means BAD (Noise increased)
        plotter = CostPlotter(alpha=0.75)

        geometries = [
            ("Stadtbezirke", self.map_bezirke),
            ("Square Grid", self.map_grid),
            ("Hexagon Grid", self.map_hex)
        ]

        configs = [
            ('total_monetary_before', 'Total Monetary Before EUR'),
            ('total_monetary_after', 'Total Monetary After EUR'),
            ('total_monetary_diff', 'Total Monetary Difference EUR')
        ]

        for geom_name, gdf in geometries :
            for col_name, base_title in configs :
                title = f"{base_title} - {geom_name}"
                out_file = os.path.join(plot_dir, f"{title.replace(' ', '_').replace('-', '').lower()}.png")

                vmin, vmax = None, None
                if 'diff' not in col_name.lower() :
                    partner_col = col_name.replace('before', 'after') if 'before' in col_name else col_name.replace(
                        'after', 'before')
                    if partner_col in gdf.columns :
                        vmin = min(gdf[col_name].min(), gdf[partner_col].min())
                        vmax = max(gdf[col_name].max(), gdf[partner_col].max())

                plotter.plot_map(gdf, col_name, title, out_file, vmin, vmax)

    def run_pipeline(self) :
        self.load_and_prepare_data()
        self.process_spatial_aggregation()
        self.export_results()
        self.generate_visualizations()
        print("Noise pipeline execution completed successfully.")