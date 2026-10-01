import gzip
import os
import warnings
import xml.etree.ElementTree as ET

import pandas as pd
from core.demographics import DemographicParser
from core.plotters import ViolinPlotter

warnings.filterwarnings('ignore')


class EmissionsAgentAnalyzer :
    """
    Object-Oriented pipeline for Agent-Level Emissions (Socio-Demographic).
    Extracts raw emission events, filters ghost agents, calculates physical derived pollutants,
    converts them to monetized values, enriches with demographics, and visualizes the results.
    """

    GHOST_AGENTS = {"2803131", "3212152"}

    MONETARY_RATES = {
        'PM2_5_TOTAL' : 578500.0,
        'PMcoarse' : 8800.0,
        'NOx' : 46700.0,
        'SO2' : 41100.0,
        'HC' : 2100.0,
        'NH3' : 47800.0,
        'CO2e' : 880.0
    }

    RAW_EMISSION_COLS = [
        'CO', 'CO2_TOTAL', 'CO2_rep', 'CO2e', 'HC', 'NH3', 'NOx',
        'PM', 'PM2_5', 'PM2_5_non_exhaust', 'PM_non_exhaust', 'SO2'
    ]

    DERIVED_EMISSION_COLS = ['PMcoarse', 'PM2_5_TOTAL']

    def __init__(self, events_before: str, events_after: str, plans_xml: str, output_dir: str) :
        self.events_before = events_before
        self.events_after = events_after
        self.plans_xml = plans_xml
        self.output_dir = output_dir

        self.all_emission_cols = self.RAW_EMISSION_COLS + self.DERIVED_EMISSION_COLS
        self.df_final = None

    def _extract_agent_emissions(self, events_file: str) -> pd.DataFrame :
        """
        Parses emission events directly from MATSim events.xml.gz.
        Filters out predefined ghost agents and accumulates raw pollutants per person.
        """
        print(f"Parsing emission events from {events_file}...")
        stats = {}
        open_func = gzip.open if events_file.endswith('.gz') else open
        mode = 'rt' if events_file.endswith('.gz') else 'r'

        with open_func(events_file, mode, encoding='utf-8') as f :
            context = ET.iterparse(f, events=("end",))
            for event, elem in context :
                event_type = elem.get("type")

                if event_type in ["warmEmissionEvent", "coldEmissionEvent"] :
                    veh_id = elem.get("vehicleId")
                    if not veh_id :
                        elem.clear()
                        continue

                    person_id = veh_id.split(":")[0]

                    if person_id in self.GHOST_AGENTS :
                        elem.clear()
                        continue

                    if person_id not in stats :
                        stats[person_id] = {col : 0.0 for col in self.RAW_EMISSION_COLS}

                    for attr_key, attr_val in elem.items() :
                        if attr_key in self.RAW_EMISSION_COLS :
                            stats[person_id][attr_key] += float(attr_val)

                elem.clear()

        df = pd.DataFrame.from_dict(stats, orient='index').reset_index()
        df.rename(columns={'index' : 'PersonId'}, inplace=True)
        return df

    def _calculate_derived_pollutants(self, df: pd.DataFrame) -> pd.DataFrame :
        """Calculates PMcoarse and PM2_5_TOTAL from raw PM components."""
        df['PMcoarse'] = (
                df['PM'].fillna(0) - df['PM2_5'].fillna(0) -
                df['PM2_5_non_exhaust'].fillna(0) + df['PM_non_exhaust'].fillna(0)
        )
        df['PM2_5_TOTAL'] = df['PM2_5'].fillna(0) + df['PM2_5_non_exhaust'].fillna(0)
        return df

    def load_and_process_data(self) :
        print("Extracting raw events data into DataFrames...")
        df_before = self._extract_agent_emissions(self.events_before)
        df_after = self._extract_agent_emissions(self.events_after)

        df_before['PersonId'] = df_before['PersonId'].astype(str)
        df_after['PersonId'] = df_after['PersonId'].astype(str)

        df_before = self._calculate_derived_pollutants(df_before)
        df_after = self._calculate_derived_pollutants(df_after)

        print("Merging before and after scenarios...")
        df_emissions = pd.merge(df_before, df_after, on='PersonId', how='outer', suffixes=('_before', '_after'))

        # Standardize physical metrics
        for col in self.all_emission_cols :
            df_emissions[f'{col}_before'] = df_emissions[f'{col}_before'].fillna(0)
            df_emissions[f'{col}_after'] = df_emissions[f'{col}_after'].fillna(0)
            df_emissions[f'{col}_diff'] = df_emissions[f'{col}_after'] - df_emissions[f'{col}_before']

        print("Extracting socio-demographics from Plans via core module...")
        parser = DemographicParser(self.plans_xml)
        df_demographics = parser.parse_to_dataframe()

        print("Joining socio-demographic attributes...")
        # Left join from emissions to ensure all agents are kept (right join in procedural was flipped)
        self.df_final = pd.merge(df_demographics, df_emissions, left_on='person_id', right_on='PersonId', how='right')

        self.df_final['person_id'] = self.df_final['PersonId']
        self.df_final.drop(columns=['PersonId'], inplace=True)
        self.df_final['gender'] = self.df_final['gender'].fillna('Unknown')
        self.df_final['age_group'] = self.df_final['age_group'].fillna('Unknown')
        self.df_final['occupation'] = self.df_final['occupation'].fillna('Unknown')

        print("Calculating monetized impacts...")
        monetary_cols_before, monetary_cols_after, monetary_cols_diff = [], [], []

        for pollutant, rate in self.MONETARY_RATES.items() :
            col_before = f'monetary_{pollutant}_before'
            col_after = f'monetary_{pollutant}_after'
            col_diff = f'monetary_{pollutant}_diff'

            # Convert grams to tons (/ 1_000_000) before applying the rate
            self.df_final[col_before] = (self.df_final[f'{pollutant}_before'] / 1_000_000.0) * rate
            self.df_final[col_after] = (self.df_final[f'{pollutant}_after'] / 1_000_000.0) * rate
            self.df_final[col_diff] = self.df_final[col_after] - self.df_final[col_before]

            monetary_cols_before.append(col_before)
            monetary_cols_after.append(col_after)
            monetary_cols_diff.append(col_diff)

        self.df_final['total_monetary_before'] = self.df_final[monetary_cols_before].sum(axis=1)
        self.df_final['total_monetary_after'] = self.df_final[monetary_cols_after].sum(axis=1)
        self.df_final['total_monetary_diff'] = self.df_final['total_monetary_after'] - self.df_final[
            'total_monetary_before']

        demographic_cols = ['person_id', 'gender', 'age_group', 'occupation']
        physical_before = [f'{c}_before' for c in self.all_emission_cols]
        physical_after = [f'{c}_after' for c in self.all_emission_cols]
        physical_diff = [f'{c}_diff' for c in self.all_emission_cols]
        total_monetary_cols = ['total_monetary_before', 'total_monetary_after', 'total_monetary_diff']

        final_column_order = (
                demographic_cols +
                physical_before + physical_after + physical_diff +
                monetary_cols_before + monetary_cols_after + monetary_cols_diff +
                total_monetary_cols
        )
        self.df_final = self.df_final[final_column_order]

    def export_results(self) :
        os.makedirs(self.output_dir, exist_ok=True)
        output_csv = os.path.join(self.output_dir, "emissions_by_sociodemographic.csv")
        print(f"Exporting comprehensive agent dataset to {output_csv}...")
        self.df_final.to_csv(output_csv, index=False)

    def generate_visualizations(self) :
        print("Delegating rendering tasks to ViolinPlotter...")
        plotter = ViolinPlotter(self.output_dir)

        plotter.plot_split_violin(
            df=self.df_final, y_col='total_monetary_diff', y_label='Monetary Difference [EUR]',
            title='Monetary Difference by Age and Gender (Emissions)',
            filename='violin_emissions_total_monetary_diff_split_gender.png'
        )

    def run_pipeline(self) :
        self.load_and_process_data()
        self.export_results()
        self.generate_visualizations()
        print("Emissions agent-level pipeline completed successfully.")