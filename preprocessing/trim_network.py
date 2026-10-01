import gzip
import xml.etree.ElementTree as ET

import geopandas as gpd
from shapely.geometry import Point
from shapely.prepared import prep
from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
cleaned_geojson_path = r"D:\Michael_Thesis\data\stadtbezirke\final_stadtbezirke_munich.json"
input_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\pop_generation_bavaria\bavaria_1pct_network.xml.gz"
output_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_network.xml.gz"

# ==========================================
# 2. EXTRACT PRE-CLEANED POLYGON
# ==========================================
print("Loading pre-cleaned Munich administrative boundary...")
munich_gdf = gpd.read_file(cleaned_geojson_path)

if munich_gdf.empty:
    raise ValueError("Cleaned boundary not found. Please verify the GeoJSON data.")

target_crs = "EPSG:25832"
if munich_gdf.crs and munich_gdf.crs != target_crs:
    print(f"Reprojecting boundary from {munich_gdf.crs} to {target_crs}...")
    munich_gdf = munich_gdf.to_crs(target_crs)

munich_polygon = munich_gdf.geometry.union_all()
prepared_munich = prep(munich_polygon)

# ==========================================
# 3. PARSE GZ NETWORK AND IDENTIFY CORE NODES
# ==========================================
print(f"Decompressing and parsing network from {input_network}...")
with gzip.open(input_network, 'rb') as f:
    tree = ET.parse(f)
    root = tree.getroot()

nodes_elem = root.find('nodes')
links_elem = root.find('links')

if nodes_elem is None or links_elem is None:
    raise ValueError("Invalid MATSim network XML: Missing <nodes> or <links> tags.")

print("Identifying core nodes within Munich boundaries...")
core_nodes = set()
all_nodes = nodes_elem.findall('node')

for node in tqdm(all_nodes, desc="Scanning nodes", unit=" nodes"):
    x_str = node.get('x')
    y_str = node.get('y')
    if x_str and y_str:
        x, y = float(x_str), float(y_str)
        if prepared_munich.contains(Point(x, y)):
            core_nodes.add(node.get('id'))

# ==========================================
# 4. FILTER LINKS (INTERSECTION LOGIC)
# ==========================================
print("Filtering links intersecting Munich...")
kept_nodes = set()
valid_links = []
all_links = links_elem.findall('link')

for link in tqdm(all_links, desc="Scanning links", unit=" links"):
    from_id = link.get('from')
    to_id = link.get('to')

    if from_id in core_nodes or to_id in core_nodes:
        kept_nodes.add(from_id)
        kept_nodes.add(to_id)
        valid_links.append(link)

links_elem[:] = valid_links

# ==========================================
# 5. CLEAN UP DANGLING NODES
# ==========================================
print("Cleaning up dangling external nodes...")
valid_nodes = []

for node in tqdm(all_nodes, desc="Filtering dangling nodes", unit=" nodes"):
    if node.get('id') in kept_nodes:
        valid_nodes.append(node)

nodes_elem[:] = valid_nodes

# ==========================================
# 6. EXPORT COMPRESSED TRIMMED NETWORK
# ==========================================
print(f"Compressing and writing network to {output_network}...")

with gzip.open(output_network, 'wt', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write('<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">\n')
    f.write(ET.tostring(root, encoding='unicode'))

print("\n--- PROCESS COMPLETED ---")
print(f"Original nodes : {len(all_nodes):,}")
print(f"Retained nodes : {len(kept_nodes):,}")
print(f"Original links : {len(all_links):,}")
print(f"Retained links : {len(valid_links):,}")