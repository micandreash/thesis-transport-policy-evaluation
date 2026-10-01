import os
import shutil
import xml.etree.ElementTree as ET

import geopandas as gpd
from shapely.geometry import box
from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
study_area_json = r"D:\Michael_Thesis\data\stadtbezirke\final_stadtbezirke_munich.json"

gml_source_dir = r"D:\Michael_Thesis\data\bavaria\buildings LoD2"

gml_strict_dir = r"D:\Michael_Thesis\data\bavaria\final_Buildings LoD2 Munich"
os.makedirs(gml_strict_dir, exist_ok=True)

# ==========================================
# 2. GET EXACT STUDY AREA POLYGON
# ==========================================
print(f"Loading exact administrative boundary from: {study_area_json}...", flush=True)
gdf_boundary = gpd.read_file(study_area_json)

# Ensure CRS matches the GML coordinate system (EPSG:25832)
if gdf_boundary.crs is None or gdf_boundary.crs.to_epsg() != 25832:
    print("Reprojecting administrative boundary to EPSG:25832...", flush=True)
    gdf_boundary = gdf_boundary.to_crs(epsg=25832)

# Exact Munich administrative boundary shape
munich_poly = gdf_boundary.geometry.union_all()

# ==========================================
# 3. SCAN & STRICT FILTER GML FILES
# ==========================================
print("\nStarting scan of GML files (reading headers only)...", flush=True)
gml_files = [f for f in os.listdir(gml_source_dir) if f.endswith('.gml')]
matched_files = 0

ns = {'gml': 'http://www.opengis.net/gml'}

for file_name in tqdm(gml_files, desc="Filtering GMLs strictly"):
    file_path = os.path.join(gml_source_dir, file_name)

    try:
        # Use iterparse to read only the initial tags without loading the huge GML into RAM
        context = ET.iterparse(file_path, events=('end',))
        for event, elem in context:
            if 'boundedBy' in elem.tag:
                lower_corner = elem.find('.//gml:lowerCorner', ns)
                upper_corner = elem.find('.//gml:upperCorner', ns)

                if lower_corner is not None and upper_corner is not None:
                    lx, ly = map(float, lower_corner.text.split()[:2])
                    ux, uy = map(float, upper_corner.text.split()[:2])

                    gml_box = box(lx, ly, ux, uy)

                    # Check spatial intersection
                    if munich_poly.intersects(gml_box):
                        shutil.copy2(file_path, os.path.join(gml_strict_dir, file_name))
                        matched_files += 1

                break  # Stop parsing this file once the bounding box is found
    except Exception as e:
        pass

print(f"\nStrict scan complete! Found {matched_files} GML files that intersect the actual Munich boundary.", flush=True)
print(f"Files copied to: {gml_strict_dir}", flush=True)