import gzip
import os
import warnings
import xml.etree.ElementTree as ET

import geopandas as gpd
import pandas as pd
from core.grids import SquareGrid, HexagonalGrid
from core.spatial_ops import NetworkParser, SpatialAggregator
from core.plotters import CostPlotter

warnings.filterwarnings('ignore')


class EmissionsAnalyzer :
    """
    Object-Oriented spatial pipeline for Emissions indicator.
    Extracts raw MATSim emission events, filters ghost agents, calculates derived
    pollutants and monetary costs, and aggregates them spatially.
    """

    GHOST_AGENTS = {"2803131", "3212152"}
    RAW_EMISSION_COLS = ['CO', 'CO2_TOTAL', 'CO2_rep', 'CO2e', 'HC', 'NH3', 'NOx', 'PM', 'PM2_5',
                         'PM2_5_non_exhaust', 'PM_non_exhaust', 'SO2']

    MONETARY_RATES = {
        'PM2.5_tons' : 578500.0,
        'PMcoarse_tons' : 8800.0,
        'NOx_tons' : 46700.0,
        'SO2_tons' : 41100.0,
        'HC_tons' : 2100.0,
        'NH3_tons' : 47800.0,
        'CO2e_tons' : 880.0
    }

    def __init__(self, events_before: str, events_after: str, network_xml: str,
                 stadtbezirke_json: str, output_dir: str) :
        self.events_before = events_before
        self.events_after = events_after
        self.network_xml = network_xml
        self.stadtbezirke_json = stadtbezirke_json
        self.output_dir = output_dir

        self.target_crs = "EPSG:25832"
        self.neighborhood_col = "sb_name"
        self.grid_size = 1000

        self.pollutants_tons = list(self.MONETARY_RATES.keys())
        self.raw_csv_cols = self.RAW_EMISSION_COLS + ['PMcoarse', 'PM2.5']

        # State variables
        self.neighborhoods = None
        self.network_gdf = None
        self.link_emissions = None
        self.grid_gdf = None
        self.hex_gdf = None
        self.map_stadtbezirke = None
        self.map_grid = None
        self.map_hex = None
        self.all_metrics = []
        self.ordered_export_cols = []

    def _extract_events(self, events_file: str) -> pd.DataFrame :
        """Parses emission events directly from MATSim events.xml.gz."""
        print(f"Parsing emission events from {events_file}...")
        stats = {}

        with gzip.open(events_file, 'rt', encoding='utf-8') as f :
            for event, elem in ET.iterparse(f, events=("end",)) :
                if elem.get("type") in ["warmEmissionEvent", "coldEmissionEvent"] :
                    veh_id = elem.get("vehicleId")
                    if not veh_id :
                        elem.clear()
                        continue

                    person_id = veh_id.split(":")[0]
                    if person_id in self.GHOST_AGENTS :
                        elem.clear()
                        continue

                    link_id = elem.get("linkId")
                    if link_id not in stats :
                        stats[link_id] = {col : 0.0 for col in self.RAW_EMISSION_COLS}

                    for attr_key, attr_val in elem.items() :
                        if attr_key in self.RAW_EMISSION_COLS :
                            stats[link_id][attr_key] += float(attr_val)
                elem.clear()

        df = pd.DataFrame.from_dict(stats, orient='index').reset_index()
        df.rename(columns={'index' : 'LinkId'}, inplace=True)
        df['LinkId'] = df['LinkId'].astype(str)

        # Derived pollutants
        df['PMcoarse'] = df['PM'].fillna(0) + df['PM_non_exhaust'].fillna(0) - df['PM2_5'].fillna(0) - df[
            'PM2_5_non_exhaust'].fillna(0)
        df['PM2.5'] = df['PM2_5'].fillna(0) + df['PM2_5_non_exhaust'].fillna(0)

        analysis_pollutants = ['CO2e', 'HC', 'NH3', 'NOx', 'PMcoarse', 'PM2.5', 'SO2']
        for p in analysis_pollutants :
            df[f'{p}_tons'] = df[p] / 1_000_000.0

        return df

    def load_and_prepare_data(self) :
        print("Loading boundaries and parsing network geometry...")
        raw_bounds = gpd.read_file(self.stadtbezirke_json).to_crs(self.target_crs)
        self.neighborhoods = raw_bounds[[self.neighborhood_col, 'geometry']].dissolve(
            by=self.neighborhood_col).reset_index()

        parser = NetworkParser(self.network_xml, self.target_crs)
        self.network_gdf = parser.get_network_gdf()

        df_before = self._extract_events(self.events_before)
        df_after = self._extract_events(self.events_after)

        print("Intersecting network with boundaries to establish base segments...")
        intersected_links = gpd.overlay(self.network_gdf, self.neighborhoods, how='intersection')
        intersected_links['segment_length'] = intersected_links.geometry.length

        total_length = intersected_links.groupby('LinkId')['segment_length'].transform('sum')
        raw_weight = intersected_links['segment_length'] / total_length
        segment_count = intersected_links.groupby('LinkId')['LinkId'].transform('count')
        intersected_links['apportion_weight'] = raw_weight.fillna(1.0 / segment_count)

        print("Merging emissions and calculating monetary costs...")
        self.link_emissions = intersected_links.merge(df_before, on='LinkId', how='left')
        self.link_emissions = self.link_emissions.merge(df_after, on='LinkId', how='left',
                                                        suffixes=('_before', '_after'))

        num_cols = self.link_emissions.select_dtypes(include=['number']).columns
        self.link_emissions[num_cols] = self.link_emissions[num_cols].fillna(0.0)

        unique_cols = list(dict.fromkeys(self.raw_csv_cols + self.pollutants_tons))

        # 1. Apply Apportionment Weight
        for c in unique_cols :
            self.link_emissions[f'{c}_before'] = self.link_emissions[f'{c}_before'] * self.link_emissions[
                'apportion_weight']
            self.link_emissions[f'{c}_after'] = self.link_emissions[f'{c}_after'] * self.link_emissions[
                'apportion_weight']
            self.link_emissions[f'{c}_diff'] = self.link_emissions[f'{c}_after'] - self.link_emissions[f'{c}_before']
            self.all_metrics.extend([f'{c}_before', f'{c}_after', f'{c}_diff'])

        # 2. Monetize
        for p_tons, rate in self.MONETARY_RATES.items() :
            p_base = p_tons.replace('_tons', '')
            self.link_emissions[f'monetary_{p_base}_before'] = self.link_emissions[f'{p_tons}_before'] * rate
            self.link_emissions[f'monetary_{p_base}_after'] = self.link_emissions[f'{p_tons}_after'] * rate
            self.link_emissions[f'monetary_{p_base}_diff'] = self.link_emissions[f'monetary_{p_base}_after'] - \
                                                             self.link_emissions[f'monetary_{p_base}_before']
            self.all_metrics.extend(
                [f'monetary_{p_base}_before', f'monetary_{p_base}_after', f'monetary_{p_base}_diff'])

        # 3. Total Monetization
        monetary_b_cols = [f'monetary_{p.replace("_tons", "")}_before' for p in self.pollutants_tons]
        monetary_a_cols = [f'monetary_{p.replace("_tons", "")}_after' for p in self.pollutants_tons]

        self.link_emissions['monetary_TOTAL_before'] = self.link_emissions[monetary_b_cols].sum(axis=1)
        self.link_emissions['monetary_TOTAL_after'] = self.link_emissions[monetary_a_cols].sum(axis=1)
        self.link_emissions['monetary_TOTAL_diff'] = self.link_emissions['monetary_TOTAL_after'] - self.link_emissions[
            'monetary_TOTAL_before']
        self.all_metrics.extend(['monetary_TOTAL_before', 'monetary_TOTAL_after', 'monetary_TOTAL_diff'])

        # Setup structured column lists for clean exporting
        raw_before = [f'{c}_before' for c in self.raw_csv_cols]
        raw_after = [f'{c}_after' for c in self.raw_csv_cols]
        raw_diff = [f'{c}_diff' for c in self.raw_csv_cols]
        monetary_b = [f'monetary_{p.replace("_tons", "")}_before' for p in self.pollutants_tons]
        monetary_a = [f'monetary_{p.replace("_tons", "")}_after' for p in self.pollutants_tons]
        monetary_d = [f'monetary_{p.replace("_tons", "")}_diff' for p in self.pollutants_tons]
        monetary_tot = ['monetary_TOTAL_before', 'monetary_TOTAL_after', 'monetary_TOTAL_diff']

        self.ordered_export_cols = raw_before + raw_after + raw_diff + monetary_b + monetary_a + monetary_d + monetary_tot

    def process_spatial_aggregation(self) :
        print("Generating grid polygons...")
        square_generator = SquareGrid(grid_size=self.grid_size, crs=self.target_crs)
        hex_generator = HexagonalGrid(grid_size=self.grid_size, crs=self.target_crs)

        self.grid_gdf = square_generator.generate_shape(self.neighborhoods)
        self.hex_gdf = hex_generator.generate_shape(self.neighborhoods)

        print("Aggregating metrics spatially (Length-based Apportionment)...")
        # 1. Bezirke
        agg_bezirke = self.link_emissions.groupby(self.neighborhood_col)[self.all_metrics].sum().reset_index()
        self.map_stadtbezirke = self.neighborhoods.merge(agg_bezirke, on=self.neighborhood_col, how="left")

        # 2. Square Grid
        self.map_grid = SpatialAggregator.aggregate_lines(
            self.link_emissions, self.grid_gdf, 'grid_id', self.all_metrics
        )
        self.map_grid['xcoord'] = self.map_grid.geometry.centroid.x
        self.map_grid['ycoord'] = self.map_grid.geometry.centroid.y

        # 3. Hexagon Grid
        self.map_hex = SpatialAggregator.aggregate_lines(
            self.link_emissions, self.hex_gdf, 'hex_id', self.all_metrics
        )
        self.map_hex['xcoord'] = self.map_hex.geometry.centroid.x
        self.map_hex['ycoord'] = self.map_hex.geometry.centroid.y

    def export_results(self) :
        print("Exporting tabular and spatial data...")
        os.makedirs(self.output_dir, exist_ok=True)
        gpkg_path = os.path.join(self.output_dir, "spatial_emissions.gpkg")
        if os.path.exists(gpkg_path) :
            os.remove(gpkg_path)

        # Links
        link_export_cols = ['LinkId', self.neighborhood_col] + self.ordered_export_cols
        self.link_emissions[link_export_cols].to_csv(os.path.join(self.output_dir, "emissions_apportioned_links.csv"),
                                                     index=False)
        self.link_emissions[['LinkId', 'geometry'] + self.ordered_export_cols].to_file(gpkg_path,
                                                                                       layer='emissions_links',
                                                                                       driver='GPKG')

        # Bezirke
        self.map_stadtbezirke[[self.neighborhood_col] + self.ordered_export_cols].to_csv(
            os.path.join(self.output_dir, "emissions_aggregated_bezirke.csv"), index=False)
        self.map_stadtbezirke.to_file(gpkg_path, layer='emissions_bezirke', driver='GPKG')

        # Grid
        self.map_grid[['grid_id', 'xcoord', 'ycoord'] + self.ordered_export_cols].to_csv(
            os.path.join(self.output_dir, "emissions_aggregated_grid.csv"), index=False)
        self.map_grid.to_file(gpkg_path, layer='emissions_grid', driver='GPKG')

        # Hex
        self.map_hex[['hex_id', 'xcoord', 'ycoord'] + self.ordered_export_cols].to_csv(
            os.path.join(self.output_dir, "emissions_aggregated_hex.csv"), index=False)
        self.map_hex.to_file(gpkg_path, layer='emissions_hex', driver='GPKG')

    def generate_visualizations(self) :
        print("Rendering maps and saving high-res PNGs...")
        plot_dir = os.path.join(self.output_dir, "plots")
        os.makedirs(plot_dir, exist_ok=True)

        # CostPlotter ensures red means BAD (Emissions increased)
        plotter = CostPlotter(alpha=0.75)

        geometries = [
            ("Stadtbezirke", self.map_stadtbezirke),
            ("Square Grid", self.map_grid),
            ("Hexagon Grid", self.map_hex)
        ]

        for geom_name, gdf in geometries :
            for p_tons in self.pollutants_tons :
                p_base = p_tons.replace('_tons', '')

                unit = "Tons" if p_base == 'CO2e' else "Grams"
                phys_b = f"{p_base}_tons_before" if p_base == 'CO2e' else f"{p_base}_before"
                phys_a = f"{p_base}_tons_after" if p_base == 'CO2e' else f"{p_base}_after"
                phys_d = f"{p_base}_tons_diff" if p_base == 'CO2e' else f"{p_base}_diff"

                configs = [
                    (phys_b, f"Physical {p_base} Before {unit} - {geom_name}"),
                    (phys_a, f"Physical {p_base} After {unit} - {geom_name}"),
                    (phys_d, f"Physical {p_base} Difference {unit} - {geom_name}"),
                    (f'monetary_{p_base}_before', f"Monetary {p_base} Before EUR - {geom_name}"),
                    (f'monetary_{p_base}_after', f"Monetary {p_base} After EUR - {geom_name}"),
                    (f'monetary_{p_base}_diff', f"Monetary {p_base} Difference EUR - {geom_name}")
                ]

                for col_name, title in configs :
                    out_file = os.path.join(plot_dir, f"{title.replace(' ', '_').replace('-', '').lower()}.png")
                    vmin, vmax = None, None

                    if 'diff' not in col_name.lower() :
                        partner_col = col_name.replace('before', 'after') if 'before' in col_name else col_name.replace(
                            'after', 'before')
                        if partner_col in gdf.columns :
                            vmin = min(gdf[col_name].min(), gdf[partner_col].min())
                            vmax = max(gdf[col_name].max(), gdf[partner_col].max())

                    plotter.plot_map(gdf, col_name, title, out_file, vmin, vmax)

            # Total Monetary Maps
            tot_configs = [
                ('monetary_TOTAL_before', f"Total Monetary Before EUR - {geom_name}"),
                ('monetary_TOTAL_after', f"Total Monetary After EUR - {geom_name}"),
                ('monetary_TOTAL_diff', f"Total Monetary Difference EUR - {geom_name}")
            ]
            for col_name, title in tot_configs :
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
        print("Emissions pipeline execution completed successfully.")