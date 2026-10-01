import gzip
import xml.etree.ElementTree as ET

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep


class FacilitiesBoundaryCropper:
    """
    Crops a MATSim facilities XML file using an exact administrative boundary polygon
    extracted from a pre-cleaned GeoJSON file.
    """
    def __init__(self, boundary_file, input_xml, output_xml):
        self.boundary_file = boundary_file
        self.input_xml = input_xml
        self.output_xml = output_xml
        self.boundary_geom = self._load_and_prepare_boundary()

    def _load_and_prepare_boundary(self):
        print(f"Loading administrative boundary from: {self.boundary_file}...", flush=True)
        gdf = gpd.read_file(self.boundary_file)

        if gdf.empty:
            raise ValueError("The provided GeoJSON is empty. Check your boundary file.")

        target_crs = "EPSG:25832"
        if gdf.crs is None or gdf.crs != target_crs:
            print(f"Reprojecting administrative boundary to {target_crs}...", flush=True)
            gdf = gdf.to_crs(target_crs)

        unified_polygon = gdf.geometry.union_all()

        print("Preparing spatial geometry for rapid intersection lookups...", flush=True)
        return prep(unified_polygon)

    def crop(self):
        print(f"Starting spatial crop process from {self.input_xml}...", flush=True)

        open_func = gzip.open if self.input_xml.endswith('.gz') else open
        out_open_func = gzip.open if self.output_xml.endswith('.gz') else open

        context = ET.iterparse(open_func(self.input_xml, 'rb'), events=('start', 'end'))

        with out_open_func(self.output_xml, 'wt', encoding='utf-8') as out_file:
            out_file.write('<?xml version="1.0" encoding="utf-8"?>\n')
            out_file.write('<!DOCTYPE facilities SYSTEM "http://www.matsim.org/files/dtd/facilities_v1.dtd">\n')
            out_file.write('<facilities>\n')

            kept_count = 0
            for event, elem in context:
                if event == 'end' and elem.tag == 'facility':
                    x = float(elem.get('x', 0))
                    y = float(elem.get('y', 0))

                    point = Point(x, y)

                    if self.boundary_geom.contains(point):
                        xml_str = ET.tostring(elem, encoding='unicode')
                        out_file.write(f"  {xml_str}\n")
                        kept_count += 1

                    elem.clear()

            out_file.write('</facilities>\n')

        print(f"Process complete. Kept {kept_count} facilities strictly within the administrative boundary.", flush=True)


if __name__ == "__main__":
    BOUNDARY_FILE = r"D:\Michael_Thesis\data\stadtbezirke\final_stadtbezirke_munich.json"
    INPUT_FACILITIES = r"D:\Michael_Thesis\data\eqasim_population_bavaria\pop_generation_bavaria\bavaria_1pct_facilities.xml.gz"
    OUTPUT_FACILITIES = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_facilities.xml.gz"

    cropper = FacilitiesBoundaryCropper(
        boundary_file=BOUNDARY_FILE,
        input_xml=INPUT_FACILITIES,
        output_xml=OUTPUT_FACILITIES
    )
    cropper.crop()