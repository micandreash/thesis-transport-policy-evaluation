import gzip
import warnings
import xml.etree.ElementTree as ET

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

warnings.filterwarnings('ignore')


class NetworkParser :
    """
    Parses MATSim network.xml.gz to extract road geometries and lengths.
    Returns a GeoDataFrame suitable for line-in-polygon spatial apportionment.
    """

    def __init__(self, xml_path: str, crs: str = "EPSG:25832") :
        self.xml_path = xml_path
        self.crs = crs

    def get_network_gdf(self) -> gpd.GeoDataFrame :
        print(f"Parsing network geometry from {self.xml_path}...")
        nodes = {}
        links = []

        with gzip.open(self.xml_path, 'rt', encoding='utf-8') as f :
            context = ET.iterparse(f, events=('end',))
            for event, elem in context :
                if elem.tag == 'node' :
                    nodes[elem.attrib['id']] = (float(elem.attrib['x']), float(elem.attrib['y']))
                    elem.clear()
                elif elem.tag == 'link' :
                    link_id = elem.attrib['id']
                    from_node = elem.attrib['from']
                    to_node = elem.attrib['to']
                    length = float(elem.get("length", 0.0))

                    if from_node in nodes and to_node in nodes :
                        geom = LineString([nodes[from_node], nodes[to_node]])
                        links.append({
                            'LinkId' : link_id,
                            'geometry' : geom,
                            'length_km' : length / 1000.0
                        })
                    elem.clear()

        return gpd.GeoDataFrame(links, crs=self.crs)


class SpatialAggregator :
    """
    Handles both Line-based (length-apportionment) and Point-based spatial aggregations.
    """

    @staticmethod
    def aggregate_lines(lines_gdf: gpd.GeoDataFrame, poly_gdf: gpd.GeoDataFrame, poly_id_col: str,
                        metric_cols: list) -> gpd.GeoDataFrame :
        """
        Intersects road lines with polygons. Apportions metrics based on the length
        of the cut segment divided by the original segment length.
        Used for: Accidents, Emissions.
        """
        print(f"Executing spatial overlay and length-based apportionment for {poly_id_col}...")

        # Overlay cuts the lines at polygon boundaries
        intersected = gpd.overlay(lines_gdf, poly_gdf, how='intersection')

        # Calculate proportional weight
        intersected['grid_weight'] = intersected.geometry.length / intersected['segment_length']

        # Apply weight to metrics
        for col in metric_cols :
            intersected[f'{col}_weighted'] = intersected[col] * intersected['grid_weight']

        # Aggregate by polygon ID
        agg_dict = {f'{col}_weighted' : 'sum' for col in metric_cols}
        agg = intersected.groupby(poly_id_col).agg(agg_dict).reset_index()
        agg.rename(columns={f'{col}_weighted' : col for col in metric_cols}, inplace=True)

        merged_poly = poly_gdf.merge(agg, on=poly_id_col, how='left')

        return merged_poly

    @staticmethod
    def aggregate_points_sum(points_gdf: gpd.GeoDataFrame, poly_gdf: gpd.GeoDataFrame, poly_id_col: str,
                             metric_cols: list, unique_id_col: str = None) -> gpd.GeoDataFrame :
        """
        Spatial join for points where only the SUM is required.
        Used for: Noise Damages.
        """
        print(f"Executing point-in-polygon SUM aggregation for {poly_id_col}...")
        joined = gpd.sjoin(points_gdf, poly_gdf, how='inner', predicate='intersects')

        if unique_id_col and unique_id_col in joined.columns :
            joined = joined.drop_duplicates(subset=[unique_id_col])

        agg = joined.groupby(poly_id_col)[metric_cols].sum().reset_index()

        merged_poly = poly_gdf.merge(agg, on=poly_id_col, how='left')

        return merged_poly

    @staticmethod
    def aggregate_points_mean_and_sum(points_gdf: gpd.GeoDataFrame, poly_gdf: gpd.GeoDataFrame, poly_id_col: str,
                                      metric_cols: list) -> gpd.GeoDataFrame :
        """
        Spatial join for points requiring both MEAN (Average) and SUM calculations,
        flattening the multi-level columns.
        Used for: Accessibility.
        """
        print(f"Executing point-in-polygon MEAN & SUM aggregation for {poly_id_col}...")
        joined = gpd.sjoin(points_gdf, poly_gdf, how='inner', predicate='intersects')

        agg_df = joined.groupby(poly_id_col)[metric_cols].agg(['mean', 'sum'])

        # Flatten MultiIndex columns -> 'average_car_accessibility_before', 'sum_car_accessibility_before', etc.
        agg_df.columns = [f"{'average' if stat == 'mean' else 'sum'}_{col}" for col, stat in agg_df.columns]
        agg_df = agg_df.reset_index()

        merged_poly = poly_gdf.merge(agg_df, on=poly_id_col, how='left')

        return merged_poly


class SpatialValidator :
    """
    Validates spatial joins and merging across different indicators to ensure integrity.
    """

    @staticmethod
    def validate_geometry_centroids(df_csv: pd.DataFrame, gdf_generated: gpd.GeoDataFrame, id_col: str) :
        """
        Cross-checks CSV X/Y coordinates against freshly generated polygon centroids.
        Prevents spatial drift or mismatch errors.
        """
        print(f"Validating {id_col} CSV coordinates against generated polygon centroids...")

        centroids_df = gdf_generated.copy()
        centroids_df['xcoord_gen'] = centroids_df.geometry.centroid.x
        centroids_df['ycoord_gen'] = centroids_df.geometry.centroid.y

        check_df = df_csv.merge(centroids_df[[id_col, 'xcoord_gen', 'ycoord_gen']], on=id_col, how='inner')

        if len(check_df) != len(df_csv) :
            raise ValueError(f"CRITICAL ERROR: Generated {id_col} geometries do not match CSV entries.")

        x_match = np.allclose(check_df['xcoord'].values, check_df['xcoord_gen'].values, atol=1e-3)
        y_match = np.allclose(check_df['ycoord'].values, check_df['ycoord_gen'].values, atol=1e-3)

        if not (x_match and y_match) :
            raise ValueError(f"CRITICAL ERROR: CSV coordinates for {id_col} differ from polygon centroids.")

        print(f"Validation PASSED: {id_col} centroids align perfectly.")