import os
import warnings

import pandas as pd
from core.demographics import DemographicParser
from core.plotters import ViolinPlotter

warnings.filterwarnings('ignore')


class AccessibilityAgentAnalyzer :
    """
    Object-Oriented pipeline for Agent-Level Accessibility (Socio-Demographic).
    Extracts agent utilities, enriches with demographics, calculates monetized differences,
    and generates automated violin plots.
    """

    def __init__(self, plans_xml: str, before_csv: str, after_csv: str, output_dir: str) :
        self.plans_xml = plans_xml
        self.before_csv = before_csv
        self.after_csv = after_csv
        self.output_dir = output_dir
        self.beta_money = 0.310998
        self.df_final = None

    def load_and_process_data(self) :
        print("Loading DMC utility data from CSV files...")
        df_before = pd.read_csv(self.before_csv, sep=';')
        df_after = pd.read_csv(self.after_csv, sep=';')

        # Ensure person_id is string for safe merging
        df_before['person_id'] = df_before['person_id'].astype(str)
        df_after['person_id'] = df_after['person_id'].astype(str)

        print("Merging BEFORE and AFTER utilities (Outer Join)...")
        df = pd.merge(df_before, df_after, on='person_id', how='outer', suffixes=('_before', '_after'))

        print("Handling missing utilities (Locking difference to 0 for unobserved states)...")
        df['utility_before'] = df['utility_before'].fillna(df['utility_after'])
        df['utility_after'] = df['utility_after'].fillna(df['utility_before'])
        df['utility_before'] = df['utility_before'].fillna(0)
        df['utility_after'] = df['utility_after'].fillna(0)

        print("Calculating utility and monetary differences...")
        df['utility_diff'] = df['utility_after'] - df['utility_before']
        df['monetary_before'] = df['utility_before'] / self.beta_money
        df['monetary_after'] = df['utility_after'] / self.beta_money
        df['monetary_diff'] = df['utility_diff'] / self.beta_money

        print("Extracting socio-demographics from Plans...")
        parser = DemographicParser(self.plans_xml)
        df_demo = parser.parse_to_dataframe()

        print("Joining socio-demographic attributes to agent utilities...")
        self.df_final = pd.merge(df, df_demo, on='person_id', how='left')

        self.df_final['gender'] = self.df_final['gender'].fillna('Unknown')
        self.df_final['age_group'] = self.df_final['age_group'].fillna('Unknown')
        self.df_final['occupation'] = self.df_final['occupation'].fillna('Unknown')

        expected_columns = [
            'person_id', 'gender', 'age_group', 'occupation',
            'utility_before', 'utility_after', 'utility_diff',
            'monetary_before', 'monetary_after', 'monetary_diff'
        ]
        self.df_final = self.df_final[expected_columns]

    def export_results(self) :
        os.makedirs(self.output_dir, exist_ok=True)
        output_csv = os.path.join(self.output_dir, "accessibility_by_sociodemographic.csv")
        print(f"Exporting final dataset to {output_csv}...")
        self.df_final.to_csv(output_csv, index=False)

    def generate_visualizations(self) :
        print("Delegating rendering tasks to ViolinPlotter...")
        plotter = ViolinPlotter(self.output_dir)

        # 1. Utility Diff (Single)
        plotter.plot_single_violin(
            df=self.df_final, y_col='utility_diff', y_label='Utility Difference',
            title='Utility Difference by Age', filename='violin_utility_diff.png', color="lightblue"
        )
        # 2. Utility Diff (Split by Gender)
        plotter.plot_split_violin(
            df=self.df_final, y_col='utility_diff', y_label='Utility Difference',
            title='Utility Difference by Age and Gender', filename='violin_utility_diff_split_gender.png'
        )
        # 3. Monetary Diff (Single)
        plotter.plot_single_violin(
            df=self.df_final, y_col='monetary_diff', y_label='Monetary Difference [EUR]',
            title='Monetary Difference by Age', filename='violin_monetary_diff.png', color="lightgreen"
        )
        # 4. Monetary Diff (Split by Gender)
        plotter.plot_split_violin(
            df=self.df_final, y_col='monetary_diff', y_label='Monetary Difference [EUR]',
            title='Monetary Difference by Age and Gender', filename='violin_monetary_diff_split_gender.png'
        )

    def run_pipeline(self) :
        self.load_and_process_data()
        self.export_results()
        self.generate_visualizations()
        print("Accessibility agent-level pipeline completed successfully.")