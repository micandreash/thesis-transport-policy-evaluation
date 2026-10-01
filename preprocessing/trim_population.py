import gzip
import json
import sys
import xml.etree.ElementTree as ET

from tqdm import tqdm

# ==========================================
# 1. SETUP PATHS
# ==========================================
input_network = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_network_connected.xml.gz"
input_schedule = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_transit_schedule.xml.gz"
input_population = r"D:\Michael_Thesis\data\eqasim_population_bavaria\pop_generation_bavaria\bavaria_1pct_population.xml.gz"
output_population = r"D:\Michael_Thesis\data\eqasim_population_bavaria\final_munich_1pct_population.xml.gz"

# ==========================================
# 2. CACHE VALID LINKS FROM NETWORK
# ==========================================
print(f"Reading valid links from {input_network}...", flush=True)
valid_links = set()
with gzip.open(input_network, 'rt', encoding='utf-8') as f:
    net_tree = ET.parse(f)
    for link in tqdm(net_tree.getroot().find('links').findall('link'), desc="Caching links", file=sys.stdout):
        valid_links.add(link.get('id'))

# ==========================================
# 3. CACHE VALID TRANSIT ROUTES FROM SCHEDULE
# ==========================================
print(f"Reading valid PT routes from {input_schedule}...", flush=True)
valid_pt_routes = set()
with gzip.open(input_schedule, 'rt', encoding='utf-8') as f:
    sched_tree = ET.parse(f)
    for line in sched_tree.getroot().findall('transitLine'):
        line_id = line.get('id')
        for route in line.findall('transitRoute'):
            route_id = route.get('id')
            # Create signature matching Eqasim standards
            valid_pt_routes.add(f"{line_id}==={route_id}")

# ==========================================
# 4. STRICT POPULATION FILTERING
# ==========================================
print(f"Decompressing and strictly filtering population from {input_population}...", flush=True)
with gzip.open(input_population, 'rt', encoding='utf-8') as f:
    tree = ET.parse(f)
    root = tree.getroot()

persons_to_remove = []
all_persons = root.findall('person')

for person in tqdm(all_persons, desc="Cross-referencing agents", file=sys.stdout):
    keep_person = True

    for plan in person.findall('plan'):
        # --- A. Check all activity locations ---
        for act in plan.findall('activity'):
            link_id = act.get('link')
            if link_id and link_id not in valid_links:
                keep_person = False
                break

        if not keep_person:
            break

        # --- B. Check route consistency for all legs ---
        for leg in plan.findall('leg'):
            route = leg.find('route')

            if route is not None:
                # 1. Validate start and end link attributes for ALL modes
                start_link = route.get('start_link')
                end_link = route.get('end_link')

                if start_link and start_link not in valid_links:
                    keep_person = False
                    break
                if end_link and end_link not in valid_links:
                    keep_person = False
                    break

                route_text = route.text.strip() if route.text else ""
                mode = leg.get('mode', '')

                # 2. Check Car / Car Passenger modes (Space-separated link IDs)
                if mode in ['car', 'car_passenger'] and route_text:
                    route_links = route_text.split()
                    for r_link in route_links:
                        if r_link not in valid_links:
                            keep_person = False
                            break

                # 3. Check PT mode (JSON string embedded in XML)
                elif mode == 'pt' and route_text.startswith('{'):
                    try:
                        pt_data = json.loads(route_text)
                        line_id = pt_data.get('transitLineId')
                        route_id = pt_data.get('transitRouteId')

                        if line_id and route_id:
                            pt_signature = f"{line_id}==={route_id}"
                            if pt_signature not in valid_pt_routes:
                                keep_person = False
                                break
                    except json.JSONDecodeError:
                        # Fallback if JSON parsing fails for any unexpected reason
                        keep_person = False
                        break

            if not keep_person:
                break
        if not keep_person:
            break

    if not keep_person:
        persons_to_remove.append(person)

# Execute removal
for person in persons_to_remove:
    root.remove(person)

# ==========================================
# 5. EXPORT PRISTINE POPULATION
# ==========================================
print(f"Compressing and exporting to {output_population}...", flush=True)
with gzip.open(output_population, 'wt', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write('<!DOCTYPE population SYSTEM "http://www.matsim.org/files/dtd/population_v6.dtd">\n')
    f.write(ET.tostring(root, encoding='unicode'))

print("\n--- PROCESS COMPLETED ---")
print(f"Original Bavaria population  : {len(all_persons):,}")
print(f"Agents with 100% valid plans : {len(all_persons) - len(persons_to_remove):,}")
print(f"Agents with broken routes    : {len(persons_to_remove):,}")