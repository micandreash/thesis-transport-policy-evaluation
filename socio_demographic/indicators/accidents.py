import gzip
import os
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
from core.demographics import DemographicParser
from core.network_bvwp import NetworkBVWPParser
from core.plotters import ViolinPlotter

warnings.filterwarnings('ignore')


class AccidentsAgentAnalyzer :
    """
    Object-Oriented pipeline for Agent-Level Accidents (Socio-Demographic).
    Utilizes BVWP cost matrices to evaluate link usage per agent, enriches with
    demographics, and generates gender-split violin plots.
    """

    def __init__(self, network_xml: str, events_before: str, events_after: str, plans_xml: str, output_dir: str) :
        self.network_xml = network_xml
        self.events_before = events_before
        self.events_after = events_after
        self.plans_xml = plans_xml
        self.output_dir = output_dir
        self.df_final = None

    def _extract_stats_from_events(self, events_file: str, links_db: dict) -> dict :
        """
        Reads MATSim events to directly accumulate KMT and monetary costs for all agents.
        """
        print(f"Processing events and accumulating KMT/Costs from {events_file}...")
        stats = {}
        open_func = gzip.open if events_file.endswith('.gz') else open
        mode = 'rt' if events_file.endswith('.gz') else 'r'

        with open_func(events_file, mode, encoding='utf-8') as f :
            context = ET.iterparse(f, events=("end",))
            for event, elem in context :
                if elem.tag == "event" and elem.get("type") == "entered link" :
                    veh_id = elem.get("vehicle")
                    # Only process valid person vehicles (ignoring transit vehicles without ':')
                    if veh_id and ":" in veh_id :
                        person_id = veh_id.split(":")[0]
                        link_id = elem.get("link")

                        if link_id in links_db :
                            if person_id not in stats :
                                stats[person_id] = {"kmt" : 0.0, "cost" : 0.0}

                            link_kmt = links_db[link_id]["length_km"]
                            # BVWP cost rates are usually EUR per 1000 vehicle-km
                            link_cost = links_db[link_id]["cost_rate"] * (link_kmt / 1000.0)

                            stats[person_id]["kmt"] += link_kmt
                            stats[person_id]["cost"] += link_cost
                elem.clear()

        return stats

    def load_and_process_data(self) :
        print("Parsing network geometry and BVWP rates via core module...")
        net_parser = NetworkBVWPParser(self.network_xml)
        links_db = net_parser.parse_links()

        stats_before = self._extract_stats_from_events(self.events_before, links_db)
        stats_after = self._extract_stats_from_events(self.events_after, links_db)

        # Establish the union of all agents who traveled in either scenario
        all_agents = set(stats_before.keys()).union(set(stats_after.keys()))

        print("Extracting socio-demographics from Plans via core module...")
        demo_parser = DemographicParser(self.plans_xml)
        # Using dictionary parsing to specifically filter only traveling agents (saves memory)
        demographics = demo_parser.parse_to_dict(filter_agents=all_agents)

        print("Compiling final agent-level accident dataset...")
        records = []
        for pid in all_agents :
            info = demographics.get(pid, {})

            kmt_b = stats_before.get(pid, {}).get("kmt", 0.0)
            cost_b = stats_before.get(pid, {}).get("cost", 0.0)

            kmt_a = stats_after.get(pid, {}).get("kmt", 0.0)
            cost_a = stats_after.get(pid, {}).get("cost", 0.0)

            records.append({
                "person_id" : pid,
                "gender" : info.get("gender", "Unknown"),
                "age_group" : info.get("age_group", "Unknown"),
                "occupation" : info.get("occupation", "Unknown"),
                "kmt_before" : kmt_b,
                "kmt_after" : kmt_a,
                "kmt_difference" : kmt_a - kmt_b,
                "monetary_before" : cost_b,
                "monetary_after" : cost_a,
                "monetary_difference" : cost_a - cost_b
            })

        self.df_final = pd.DataFrame(records)

    def export_results(self) :
        os.makedirs(self.output_dir, exist_ok=True)
        output_csv = os.path.join(self.output_dir, "accidents_by_sociodemographic.csv")
        print(f"Exporting final dataset to {output_csv}...")
        self.df_final.to_csv(output_csv, index=False)

    def generate_visualizations(self) :
        print("Delegating rendering tasks to ViolinPlotter...")
        plotter = ViolinPlotter(self.output_dir)

        # Split plot for KMT
        plotter.plot_split_violin(
            df=self.df_final, y_col='kmt_difference', y_label='KMT Difference [km]',
            title='KMT Difference by Age and Gender', filename='violin_kmt_diff_split_gender.png'
        )
        # Split plot for Monetary costs
        plotter.plot_split_violin(
            df=self.df_final, y_col='monetary_difference', y_label='Monetary Difference [EUR]',
            title='Monetary Difference by Age and Gender', filename='violin_monetary_diff_split_gender.png'
        )

    def run_pipeline(self) :
        self.load_and_process_data()
        self.export_results()
        self.generate_visualizations()
        print("Accidents agent-level pipeline completed successfully.")