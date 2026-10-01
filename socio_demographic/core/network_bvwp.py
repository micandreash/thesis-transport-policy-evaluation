import gzip
import xml.etree.ElementTree as ET


class NetworkBVWPParser :
    """
    Core utility to parse MATSim network files and evaluate road segments
    against the BVWP (Federal Transport Infrastructure Plan) accident cost rates.
    """

    def __init__(self, network_file: str) :
        self.network_file = network_file

    @staticmethod
    def _get_cost_rate_table() -> list :
        """
        Returns the BVWP cost rate table as a 3D list.
        Accessed via: table[index0][index2 - 1][index1]
        """
        return [
            [  # index0 = 0 (Motorways)
                [0.0, 0.0, 0.0, 0.0],
                [23.165, 23.165, 0.0, 0.0],
                [23.79, 23.79, 0.0, 0.0],
                [23.79, 23.79, 0.0, 0.0]
            ],
            [  # index0 = 1 (Built-up or standard roads)
                [61.785, 101.2, 61.785, 101.2],
                [31.63, 101.53, 31.63, 101.53],
                [37.84, 82.62, 34.735, 101.53],
                [0.0, 0.0, 0.0, 101.53]
            ],
            [  # index0 = 2 (Rural / non-built-up standard roads)
                [9.56, 15.09, 9.56, 15.09],
                [11.735, 14.67425, 0.0, 17.57],
                [11.735, 11.735, 0.0, 17.57],
                [9.11, 9.11, 0.0, 17.57]
            ]
        ]

    def parse_links(self) -> dict :
        """
        Parses the complete network.xml.gz to extract link lengths and
        dynamically assign BVWP cost rates based on road attributes.
        Returns a dictionary mapping Link IDs to their properties.
        """
        print(f"Parsing complete network and mapping BVWP rates from {self.network_file}...")
        links_db = {}
        cost_table = self._get_cost_rate_table()

        open_func = gzip.open if self.network_file.endswith('.gz') else open
        mode = 'rt' if self.network_file.endswith('.gz') else 'r'

        with open_func(self.network_file, mode, encoding='utf-8') as f :
            context = ET.iterparse(f, events=("end",))
            for event, elem in context :
                if elem.tag == "link" :
                    link_id = elem.get("id")
                    length = float(elem.get("length", 0.0))
                    freespeed = float(elem.get("freespeed", 0.0))
                    lanes = float(elem.get("permlanes", 1.0))

                    osm_highway = None
                    attrs = elem.find("attributes")
                    if attrs is not None :
                        for attr in attrs.findall("attribute") :
                            if attr.get("name") == "osm:way:highway" :
                                osm_highway = attr.text
                                break

                    # BVWP Translation Logic
                    speed_kmh = freespeed * 3.6
                    index0 = 1
                    index1 = 3
                    index2 = int(lanes)

                    if index2 < 1 : index2 = 1
                    if index2 > 4 : index2 = 4

                    is_built_up = True
                    if osm_highway is not None :
                        if "motorway" in osm_highway :
                            index0 = 0
                            is_built_up = speed_kmh <= 90
                        elif any(hw in osm_highway for hw in
                                 ["trunk", "primary", "secondary", "tertiary", "unclassified"]) :
                            index0 = 1
                            is_built_up = speed_kmh <= 50
                        elif "residential" in osm_highway or "living_street" in osm_highway :
                            index0 = 1
                            is_built_up = True
                    else :
                        if speed_kmh > 90 :
                            index0 = 0
                            is_built_up = False
                        else :
                            index0 = 1
                            is_built_up = speed_kmh <= 50

                    if is_built_up :
                        index1 = 1 if speed_kmh > 57.6 else 3
                    else :
                        index1 = 0 if speed_kmh > 57.6 else 2

                    cost_rate = cost_table[index0][index2 - 1][index1]

                    links_db[link_id] = {
                        "length_km" : length / 1000.0,
                        "cost_rate" : cost_rate
                    }

                    elem.clear()

        print(f"Successfully processed {len(links_db)} links for BVWP costs.")
        return links_db