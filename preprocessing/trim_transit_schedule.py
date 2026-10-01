import gzip
import sys
import xml.etree.ElementTree as ET

from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
input_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_network_connected.xml.gz"
input_schedule = r"D:\Michael_Thesis\data\eqasim_population_bavaria\pop_generation_bavaria\bavaria_1pct_transit_schedule.xml.gz"
output_schedule = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_transit_schedule.xml.gz"

# ==========================================
# 2. EXTRACT VALID LINKS FROM NETWORK
# ==========================================
print(f"Reading valid links from {input_network}...", flush=True)
valid_links = set()

with gzip.open(input_network, 'rt', encoding='utf-8') as f:
    net_tree = ET.parse(f)
    for link in tqdm(net_tree.getroot().find('links').findall('link'), desc="Caching links", unit=" links",
                     file=sys.stdout):
        valid_links.add(link.get('id'))

# ==========================================
# 3. PARSE GZ TRANSIT SCHEDULE
# ==========================================
print(f"Decompressing and parsing transit schedule from {input_schedule}...", flush=True)
with gzip.open(input_schedule, 'rt', encoding='utf-8') as f:
    tree = ET.parse(f)
    root = tree.getroot()

# Map all stops to their respective links first
stop_to_link = {}
stops_elem = root.find('transitStops')
if stops_elem is not None:
    for stop in stops_elem.findall('stopFacility'):
        stop_to_link[stop.get('id')] = stop.get('linkRefId')

# ==========================================
# 4. FILTER LINES, ROUTES, AND COLLECT ACTIVE STOPS
# ==========================================
print("Evaluating routes and collecting active stops...", flush=True)
used_stops = set()
lines_to_remove = []
all_lines = root.findall('transitLine')

for line in tqdm(all_lines, desc="Processing lines", unit=" lines", file=sys.stdout):
    routes_to_remove = []

    for route in line.findall('transitRoute'):
        keep_route = True

        # Rule A: All links in the route must exist in Munich network
        route_links = route.find('route')
        if route_links is not None:
            for link in route_links.findall('link'):
                if link.get('refId') not in valid_links:
                    keep_route = False
                    break

        # Rule B: All stops in the route profile must be attached to valid Munich links
        if keep_route:
            route_profile = route.find('routeProfile')
            if route_profile is not None:
                for stop in route_profile.findall('stop'):
                    stop_id = stop.get('refId')
                    link_ref = stop_to_link.get(stop_id)
                    if link_ref not in valid_links:
                        keep_route = False
                        break

        # If route is valid, register all its stops as ACTIVE/USED
        if keep_route:
            route_profile = route.find('routeProfile')
            if route_profile is not None:
                for stop in route_profile.findall('stop'):
                    used_stops.add(stop.get('refId'))
        else:
            routes_to_remove.append(route)

    # Remove invalid routes
    for route in routes_to_remove:
        line.remove(route)

    # Drop line completely if no routes survived
    if len(line.findall('transitRoute')) == 0:
        lines_to_remove.append(line)

for line in lines_to_remove:
    root.remove(line)

# ==========================================
# 5. FILTER TRANSIT STOPS (REMOVE ORPHANS)
# ==========================================
print("Cleaning up orphaned transit stops...", flush=True)
stops_to_remove = []

if stops_elem is not None:
    for stop in stops_elem.findall('stopFacility'):
        if stop.get('id') not in used_stops:
            stops_to_remove.append(stop)

    for stop in stops_to_remove:
        stops_elem.remove(stop)

# ==========================================
# 6. FILTER MINIMAL TRANSFER TIMES
# ==========================================
print("Filtering minimal transfer times...", flush=True)
transfer_elem = root.find('minimalTransferTimes')
if transfer_elem is not None:
    transfers_to_remove = []
    for relation in transfer_elem.findall('relation'):
        from_stop = relation.get('fromStop')
        to_stop = relation.get('toStop')
        # Only keep transfers where BOTH stops are actively used
        if from_stop not in used_stops or to_stop not in used_stops:
            transfers_to_remove.append(relation)

    for relation in transfers_to_remove:
        transfer_elem.remove(relation)

# ==========================================
# 7. EXPORT COMPRESSED TRIMMED SCHEDULE
# ==========================================
print(f"Compressing and exporting to {output_schedule}...", flush=True)
with gzip.open(output_schedule, 'wt', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write('<!DOCTYPE transitSchedule SYSTEM "http://www.matsim.org/files/dtd/transitSchedule_v2.dtd">\n')
    f.write(ET.tostring(root, encoding='unicode'))

print("\n--- PROCESS COMPLETED ---")
print(f"Valid links referenced    : {len(valid_links):,}")
print(f"Active stops retained     : {len(used_stops):,}")
print(f"Orphaned stops removed    : {len(stops_to_remove):,}")
print(f"Transit lines removed     : {len(lines_to_remove):,}")