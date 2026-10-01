import gzip
import os
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
from scipy.spatial import cKDTree
from core.demographics import DemographicParser
from core.plotters import ViolinPlotter

warnings.filterwarnings('ignore')


class NoiseAgentAnalyzer :
    """
    Object-Oriented pipeline for Agent-Level Noise (Socio-Demographic).
    Uses spatial indexing (KD-Tree) to snap agent activities to receiver points,
    calculates exact exposure durations, applies time-based thresholds,
    and monetizes the impact.
    """

    CONSIDERED_ACTIVITIES = {"home", "work", "education", "leisure", "other", "shop"}

    def __init__(self, rp_coords_file: str, immission_dir_before: str, immission_dir_after: str,
                 plans_before: str, plans_after: str, output_dir: str) :
        self.rp_coords_file = rp_coords_file
        self.immission_dir_before = immission_dir_before
        self.immission_dir_after = immission_dir_after
        self.plans_before = plans_before
        self.plans_after = plans_after
        self.output_dir = output_dir
        self.df_final = None

    @staticmethod
    def _parse_time_to_sec(time_str: str) -> float :
        """Converts MATSim HH:MM:SS time string to seconds."""
        if not time_str :
            return 86400.0
        try :
            parts = time_str.split(':')
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        except Exception :
            return 86400.0

    @staticmethod
    def _get_threshold(hour_idx: int) -> float :
        """Returns the legal threshold dB(A) based on the time of day."""
        if 6 <= hour_idx < 18 :
            return 50.0
        elif 18 <= hour_idx < 22 :
            return 45.0
        else :
            return 40.0

    def _build_rp_tree(self) -> tuple :
        """Builds a KD-Tree directly from Receiver Points for fast spatial snapping."""
        print(f"Building spatial index for Receiver Points from {self.rp_coords_file}...")
        df_rp = pd.read_csv(self.rp_coords_file)
        rp_ids = df_rp['id'].values
        rp_coords = df_rp[['xcoord', 'ycoord']].values
        tree = cKDTree(rp_coords)
        clean_rp_ids = [str(int(float(rp))) for rp in rp_ids]
        return tree, clean_rp_ids

    def _load_immissions(self, immission_dir: str, rp_ids_needed: list) -> dict :
        """Loads hourly immission data from 00:00 to 23:00 into memory."""
        print(f"Loading hourly immission data from {immission_dir}...")
        rp_ids_set = set(rp_ids_needed)
        immission_data = {rp_id : {h : 0.0 for h in range(24)} for rp_id in rp_ids_set}

        for h in range(24) :
            time_sec = (h + 1) * 3600.0
            file_path = os.path.join(immission_dir, f"immission_{time_sec}.csv")

            if os.path.exists(file_path) :
                df_imm = pd.read_csv(file_path, sep=';')
                rp_col, imm_col = df_imm.columns[0], df_imm.columns[1]

                df_imm['clean_id'] = df_imm[rp_col].apply(lambda x : str(int(float(x))))
                df_filtered = df_imm[df_imm['clean_id'].isin(rp_ids_set)]

                for _, row in df_filtered.iterrows() :
                    immission_data[row['clean_id']][h] = float(row[imm_col])
        return immission_data

    def _process_agent_activities(self, plans_file: str, rp_tree: cKDTree, rp_ids: list, immission_data: dict,
                                  scale_factor: float = 100.0) -> dict :
        """Parses plans to calculate exact noise exposure durations and costs."""
        print(f"Processing 24h agent plans and calculating costs from {plans_file}...")
        agent_stats = {}

        open_func = gzip.open if plans_file.endswith('.gz') else open
        mode = 'rt' if plans_file.endswith('.gz') else 'r'

        with open_func(plans_file, mode, encoding='utf-8') as f :
            context = ET.iterparse(f, events=("start", "end"))
            context = iter(context)

            try :
                event, root = next(context)
            except StopIteration :
                return agent_stats

            current_person = None
            selected_plan = False

            for event, elem in context :
                if event == "start" and elem.tag == "person" :
                    current_person = elem.get("id")
                elif event == "start" and elem.tag == "plan" :
                    selected_plan = (elem.get("selected") == "yes")
                elif event == "end" and elem.tag in ["act", "activity"] and selected_plan :
                    act_type = elem.get("type")

                    if act_type and act_type in self.CONSIDERED_ACTIVITIES :
                        x_str, y_str = elem.get("x"), elem.get("y")
                        if x_str and y_str :
                            x, y = float(x_str), float(y_str)
                            dist, idx = rp_tree.query([x, y], k=1)
                            rp_id = rp_ids[idx]

                            start_sec = self._parse_time_to_sec(elem.get("start_time"))
                            end_sec = self._parse_time_to_sec(elem.get("end_time"))

                            if current_person not in agent_stats :
                                agent_stats[current_person] = {
                                    "durations" : {h : 0.0 for h in range(24)},
                                    "costs" : {h : 0.0 for h in range(24)}
                                }

                            for h in range(24) :
                                bin_start = h * 3600.0
                                bin_end = (h + 1) * 3600.0
                                overlap_start = max(start_sec, bin_start)
                                overlap_end = min(end_sec, bin_end)

                                if overlap_end > overlap_start :
                                    duration_days = (overlap_end - overlap_start) / 86400.0
                                    agent_stats[current_person]["durations"][h] += duration_days

                                    imm_val = immission_data.get(rp_id, {}).get(h, 0.0)
                                    threshold = self._get_threshold(h)

                                    if imm_val >= threshold :
                                        cost = 63.3 * (duration_days / 365.24) * (
                                                    2 ** (0.1 * (imm_val - threshold))) * scale_factor
                                        agent_stats[current_person]["costs"][h] += cost

                elif event == "end" and elem.tag == "person" :
                    current_person = None

                if event == "end" :
                    elem.clear()
                    if elem.tag == "person" :
                        root.clear()

        return agent_stats

    def load_and_process_data(self) :
        rp_tree, rp_ids = self._build_rp_tree()

        imm_data_before = self._load_immissions(self.immission_dir_before, rp_ids)
        imm_data_after = self._load_immissions(self.immission_dir_after, rp_ids)

        # Scale factor 1.0 because we are at the agent level (each agent represents themselves)
        stats_before = self._process_agent_activities(self.plans_before, rp_tree, rp_ids, imm_data_before,
                                                      scale_factor=1.0)
        stats_after = self._process_agent_activities(self.plans_after, rp_tree, rp_ids, imm_data_after,
                                                     scale_factor=1.0)

        affected_agents = set(stats_before.keys()).union(set(stats_after.keys()))
        if not affected_agents :
            raise ValueError("No agents were processed! Check plans for valid activities.")

        print("Extracting socio-demographics via core module...")
        demo_parser = DemographicParser(self.plans_before)
        demographics = demo_parser.parse_to_dict(filter_agents=affected_agents)

        print("Compiling final agent data...")
        agent_records = []
        for pid in affected_agents :
            info = demographics.get(pid, {})

            sb = stats_before.get(pid,
                                  {"durations" : {h : 0.0 for h in range(24)}, "costs" : {h : 0.0 for h in range(24)}})
            sa = stats_after.get(pid,
                                 {"durations" : {h : 0.0 for h in range(24)}, "costs" : {h : 0.0 for h in range(24)}})

            row = {
                "person_id" : pid,
                "gender" : info.get("gender", "Unknown"),
                "age_group" : info.get("age_group", "Unknown"),
                "occupation" : info.get("occupation", "Unknown")
            }

            tot_mon_b = 0.0
            tot_mon_a = 0.0

            for h in range(24) :
                k = str(h).zfill(2) + ":00"
                db, cb = sb["durations"][h], sb["costs"][h]
                da, ca = sa["durations"][h], sa["costs"][h]

                row[f"duration_before_{k}"] = db
                row[f"duration_after_{k}"] = da
                row[f"duration_diff_{k}"] = da - db
                row[f"monetary_before_{k}"] = cb
                row[f"monetary_after_{k}"] = ca
                row[f"monetary_diff_{k}"] = ca - cb

                tot_mon_b += cb
                tot_mon_a += ca

            row["total_monetary_before"] = tot_mon_b
            row["total_monetary_after"] = tot_mon_a
            row["total_monetary_diff"] = tot_mon_a - tot_mon_b

            agent_records.append(row)

        self.df_final = pd.DataFrame(agent_records)

        # Ordering columns
        base_cols = ["person_id", "gender", "age_group", "occupation"]
        dur_before_cols = [f"duration_before_{str(h).zfill(2)}:00" for h in range(24)]
        dur_after_cols = [f"duration_after_{str(h).zfill(2)}:00" for h in range(24)]
        dur_diff_cols = [f"duration_diff_{str(h).zfill(2)}:00" for h in range(24)]
        mon_before_cols = [f"monetary_before_{str(h).zfill(2)}:00" for h in range(24)]
        mon_after_cols = [f"monetary_after_{str(h).zfill(2)}:00" for h in range(24)]
        mon_diff_cols = [f"monetary_diff_{str(h).zfill(2)}:00" for h in range(24)]

        final_cols = (
                base_cols +
                dur_before_cols + dur_after_cols + dur_diff_cols +
                mon_before_cols + mon_after_cols + mon_diff_cols +
                ["total_monetary_before", "total_monetary_after", "total_monetary_diff"]
        )
        self.df_final = self.df_final[final_cols]

    def export_results(self) :
        os.makedirs(self.output_dir, exist_ok=True)
        output_csv = os.path.join(self.output_dir, "noise_by_sociodemographic.csv")
        print(f"Exporting noise outputs to {output_csv}...")
        self.df_final.to_csv(output_csv, index=False)
        print("Total Monetary Before :", self.df_final['total_monetary_before'].sum())
        print("Total Monetary After  :", self.df_final['total_monetary_after'].sum())

    def generate_visualizations(self) :
        print("Delegating rendering tasks to ViolinPlotter...")
        plotter = ViolinPlotter(self.output_dir)
        plotter.plot_split_violin(
            df=self.df_final, y_col='total_monetary_diff', y_label='Monetary Difference [EUR]',
            title='Total Monetary Difference by Age and Gender (Noise)',
            filename='violin_noise_total_monetary_diff_split_gender.png'
        )

    def run_pipeline(self) :
        self.load_and_process_data()
        self.export_results()
        self.generate_visualizations()
        print("Noise agent-level pipeline completed successfully.")