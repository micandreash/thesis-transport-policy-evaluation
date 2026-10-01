import gzip
import sys
import xml.etree.ElementTree as ET

import networkx as nx
from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
input_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_network.xml.gz"
output_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_network_connected.xml.gz"

# ==========================================
# 2. DECOMPRESS AND PARSE NETWORK
# ==========================================
print("Decompressing and parsing network...", flush=True)
with gzip.open(input_network, 'rt', encoding='utf-8') as f:
    tree = ET.parse(f)
    root = tree.getroot()

links_elem = root.find('links')
all_links = links_elem.findall('link')

# ==========================================
# 3. BUILD DIRECTED GRAPH FOR 'CAR'
# ==========================================
print("Building directed graph for 'car' mode...", flush=True)
graph = nx.DiGraph()

for link in all_links:
    modes = link.get('modes', '').split(',')
    if 'car' in modes:
        graph.add_edge(link.get('from'), link.get('to'), id=link.get('id'))

# ==========================================
# 4. IDENTIFY MAIN CONNECTED COMPONENT (SCC)
# ==========================================
print("Calculating the largest strongly connected component (SCC)...", flush=True)
scc = max(nx.strongly_connected_components(graph), key=len)
valid_car_nodes = set(scc)

print(f"Original car-accessible nodes     : {len(graph.nodes):,}", flush=True)
print(f"Nodes in main connected component : {len(valid_car_nodes):,}", flush=True)

# ==========================================
# 5. REMOVE CAR ACCESS FROM ISOLATED LINKS
# ==========================================
print("Removing 'car' access from isolated links...", flush=True)
modes_modified = 0

for link in tqdm(all_links, desc="Cleaning link modes", unit=" links", file=sys.stdout):
    modes = link.get('modes', '').split(',')

    if 'car' in modes:
        from_node = link.get('from')
        to_node = link.get('to')

        # Check if link is outside the main connected component
        if from_node not in valid_car_nodes or to_node not in valid_car_nodes:
            new_modes = [m for m in modes if m not in ['car', 'car_passenger']]

            if len(new_modes) > 0:
                link.set('modes', ','.join(new_modes))
            else:
                link.set('modes', '')

            modes_modified += 1

# ==========================================
# 6. EXPORT CONNECTED NETWORK
# ==========================================
print(f"Compressing and exporting to {output_network}...", flush=True)
with gzip.open(output_network, 'wt', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write('<!DOCTYPE network SYSTEM "http://www.matsim.org/files/dtd/network_v2.dtd">\n')
    f.write(ET.tostring(root, encoding='unicode'))

print("\n--- PROCESS COMPLETED ---")
print(f"Links modified (car access revoked) : {modes_modified:,}")