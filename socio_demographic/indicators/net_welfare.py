import os
import warnings
from functools import reduce

import pandas as pd
from core.plotters import ViolinPlotter

warnings.filterwarnings('ignore')

class NetWelfareAnalyzer:
    """
    Object-Oriented pipeline for Agent-Level Net Welfare (Socio-Demographic).
    Consolidates Accessibility, Accidents, Emissions, and Noise.
    Calculates Net Welfare = Accessibility (Benefit) - Externalities (Costs),
    and visualizes the final distribution.
    """
    def __init__(self, path_accessibility: str, path_accidents: str,
                 path_emissions: str, path_noise: str, output_dir: str):
        self.path_accessibility = path_accessibility
        self.path_accidents = path_accidents
        self.path_emissions = path_emissions
        self.path_noise = path_noise
        self.output_dir = output_dir
        self.df_final = None

    def load_and_process_data(self):
        print("Loading individual indicator DataFrames...")
        df_acc = pd.read_csv(self.path_accessibility)
        df_acd = pd.read_csv(self.path_accidents)
        df_emi = pd.read_csv(self.path_emissions)
        df_noi = pd.read_csv(self.path_noise)

        # Ensure person_id is a string across all dataframes for safe merging
        for df in [df_acc, df_acd, df_emi, df_noi]:
            df['person_id'] = df['person_id'].astype(str)

        print("Extracting unique demographics across all scenarios...")
        df_all_concat = pd.concat([df_acc, df_acd, df_emi, df_noi], ignore_index=True)
        df_demographics = df_all_concat[['person_id', 'gender', 'age_group', 'occupation']].drop_duplicates(subset=['person_id'])

        print("Renaming monetary columns for consolidation...")
        df_acc_sub = df_acc[['person_id', 'monetary_before', 'monetary_after']].rename(columns={
            'monetary_before': 'monetary_before_accessibility',
            'monetary_after': 'monetary_after_accessibility'
        })

        df_acd_sub = df_acd[['person_id', 'monetary_before', 'monetary_after']].rename(columns={
            'monetary_before': 'monetary_before_accidents',
            'monetary_after': 'monetary_after_accidents'
        })

        df_emi_sub = df_emi[['person_id', 'total_monetary_before', 'total_monetary_after']].rename(columns={
            'total_monetary_before': 'monetary_before_emissions',
            'total_monetary_after': 'monetary_after_emissions'
        })

        df_noi_sub = df_noi[['person_id', 'total_monetary_before', 'total_monetary_after']].rename(columns={
            'total_monetary_before': 'monetary_before_noise',
            'total_monetary_after': 'monetary_after_noise'
        })

        print("Merging all datasets (Outer Join)...")
        data_frames = [df_demographics, df_acc_sub, df_acd_sub, df_emi_sub, df_noi_sub]
        self.df_final = reduce(lambda left, right: pd.merge(left, right, on='person_id', how='outer'), data_frames)

        # Replace NaNs in monetary columns with 0.0 to ensure correct mathematical operations
        monetary_cols = [c for c in self.df_final.columns if 'monetary' in c]
        self.df_final[monetary_cols] = self.df_final[monetary_cols].fillna(0.0)

        print("Calculating Net Welfare...")
        # Welfare Calculation: Accessibility (Benefit) - Externalities (Costs)
        self.df_final['total_monetary_before'] = (
            self.df_final['monetary_before_accessibility'] -
            self.df_final['monetary_before_accidents'] -
            self.df_final['monetary_before_emissions'] -
            self.df_final['monetary_before_noise']
        )

        self.df_final['total_monetary_after'] = (
            self.df_final['monetary_after_accessibility'] -
            self.df_final['monetary_after_accidents'] -
            self.df_final['monetary_after_emissions'] -
            self.df_final['monetary_after_noise']
        )

        self.df_final['total_monetary_difference'] = self.df_final['total_monetary_after'] - self.df_final['total_monetary_before']

        # Enforce exact final column order
        final_cols = [
            'person_id', 'gender', 'age_group', 'occupation',
            'monetary_before_accessibility', 'monetary_before_accidents', 'monetary_before_emissions', 'monetary_before_noise',
            'monetary_after_accessibility', 'monetary_after_accidents', 'monetary_after_emissions', 'monetary_after_noise',
            'total_monetary_before', 'total_monetary_after', 'total_monetary_difference'
        ]
        self.df_final = self.df_final[final_cols]

    def export_results(self):
        os.makedirs(self.output_dir, exist_ok=True)
        output_csv = os.path.join(self.output_dir, "net_welfare_by_sociodemographic.csv")
        print(f"Exporting consolidated Net Welfare dataset to {output_csv}...")
        self.df_final.to_csv(output_csv, index=False)

    def generate_visualizations(self):
        print("Delegating rendering tasks to ViolinPlotter...")
        plotter = ViolinPlotter(self.output_dir)
        plotter.plot_split_violin(
            df=self.df_final, y_col='total_monetary_difference', y_label='Net Welfare Difference [EUR]',
            title='Net Welfare Difference by Age and Gender',
            filename='violin_net_welfare_diff_split_gender.png'
        )

    def run_pipeline(self):
        self.load_and_process_data()
        self.export_results()
        self.generate_visualizations()
        print("Net Welfare agent-level pipeline completed successfully.")