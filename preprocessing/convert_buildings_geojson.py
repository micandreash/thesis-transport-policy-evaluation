import os
import sys
import traceback
import xml.etree.ElementTree as ET

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPoint, Polygon
from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
gml_folder = r"D:\Michael_Thesis\data\bavaria\final_Buildings LoD2 Munich"
output_geojson = r"D:\Michael_Thesis\data\bavaria\final_Buildings LoD2 Munich\final_buildings_lod2.geojson"
os.makedirs(os.path.dirname(output_geojson), exist_ok=True)

# ==========================================
# 2. PARSING LOGIC WITH GRANULAR ERROR HANDLING
# ==========================================
building_records = []
gml_files = [f for f in os.listdir(gml_folder) if f.endswith('.gml')]

print(f"Starting extraction for {len(gml_files)} GML files...")

for file_name in tqdm(gml_files, desc="Processing LoD2 Buildings"):
    file_path = os.path.join(gml_folder, file_name)

    # Parse the XML file
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        print(f"\nWARNING: Could not read file {file_name} due to XML format error: {e}")
        continue

    # Iterate through all XML elements
    for elem in root.iter():
        if elem.tag.endswith('Building') or elem.tag.endswith('BuildingPart'):

            # Use an isolated try-except block per building
            try:
                bldg_id = "unknown_id"
                for attr, val in elem.attrib.items():
                    if attr.endswith('id'):
                        bldg_id = val
                        break

                all_x = []
                all_y = []
                all_z = []

                # Extract coordinates from sub-elements
                for child in elem.iter():

                    # Type 1: <gml:posList> (space separated)
                    if child.tag.endswith('posList') and child.text:
                        coords = child.text.split()
                        for i in range(0, len(coords) - 2, 3):
                            all_x.append(float(coords[i]))
                            all_y.append(float(coords[i + 1]))
                            all_z.append(float(coords[i + 2]))

                    # Type 2: <gml:pos> (space separated, single coordinate)
                    elif child.tag.endswith('pos') and child.text:
                        coords = child.text.split()
                        if len(coords) >= 3:
                            all_x.append(float(coords[0]))
                            all_y.append(float(coords[1]))
                            all_z.append(float(coords[2]))

                    # Type 3: <gml:coordinates> (often comma separated tuples)
                    elif child.tag.endswith('coordinates') and child.text:
                        # Example format: 11.1,22.2,33.3 44.4,55.5,66.6
                        tuples = child.text.split()
                        for t in tuples:
                            coords = t.split(',')
                            if len(coords) >= 3:
                                all_x.append(float(coords[0]))
                                all_y.append(float(coords[1]))
                                all_z.append(float(coords[2]))

                # Skip if building has no valid spatial data
                if not all_x:
                    continue

                height = max(all_z) - min(all_z)
                base_z = min(all_z)

                points_2d = [(x, y) for x, y in zip(all_x, all_y)]
                footprint_2d = MultiPoint(points_2d).convex_hull

                if footprint_2d.geom_type == 'Polygon':
                    centroid_x = footprint_2d.centroid.x
                    centroid_y = footprint_2d.centroid.y

                    coords_2d = list(footprint_2d.exterior.coords)
                    coords_3d = [(x, y, base_z) for x, y in coords_2d]

                    footprint_3d = Polygon(coords_3d)

                    building_records.append({
                        'id': bldg_id,
                        'centroid_x': round(centroid_x, 3),
                        'centroid_y': round(centroid_y, 3),
                        'base_z': round(base_z, 3),
                        'height': round(height, 2),
                        'geometry': footprint_3d
                    })

            except Exception as bldg_err:
                print(f"\n[CRASH DETECTED]")
                print(f"Failed at Building ID: {bldg_id}")
                print(f"Error Type: {type(bldg_err).__name__}")
                print(f"Error Message: {bldg_err}")
                print("\nFull Stack Trace:")
                traceback.print_exc()

                print("\nHalting script immediately so you can inspect the error above...")
                sys.exit(1)

# ==========================================
# 3. EXPORT TO GEOPACKAGE
# ==========================================
print(f"\nExtraction complete! Found {len(building_records)} valid building footprints.")

if len(building_records) == 0:
    print("CRITICAL ERROR: Still 0 buildings found.")
else:
    print("Converting to GeoDataFrame...")
    df = pd.DataFrame(building_records)
    gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:25832")

    print(f"Exporting to {output_geojson}...")
    gdf.to_file(output_geojson, driver="GeoJSON")
    print("Done! The GeoJSON is ready for MATSim.")