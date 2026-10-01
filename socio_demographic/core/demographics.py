import gzip
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd


class DemographicParser:
    """
    Core parser for MATSim plans.xml.gz to extract socio-demographic attributes.
    Provides methods to return data either as a fast-lookup Dictionary or a pandas DataFrame.
    """
    def __init__(self, plans_xml: str):
        self.plans_xml = plans_xml

    @staticmethod
    def categorize_age(age_val) -> str:
        """Categorizes raw age integer into predefined groups."""
        try:
            age = int(float(age_val))
            if age <= 18:
                return '0-18'
            elif age <= 29:
                return '19-29'
            elif age <= 49:
                return '30-49'
            elif age <= 64:
                return '50-64'
            else:
                return '65+'
        except (ValueError, TypeError):
            return 'Unknown'

    @staticmethod
    def format_gender(sex_val) -> str:
        """Normalizes gender attributes to strictly male/female/Unknown."""
        if not sex_val:
            return 'Unknown'
        sex_val = str(sex_val).strip().lower()
        if sex_val.startswith('m'):
            return 'male'
        elif sex_val.startswith('f') or sex_val.startswith('w'):
            return 'female'
        return 'Unknown'

    @staticmethod
    def format_occupation(emp_val) -> str:
        """Normalizes employment status to employed/unemployed."""
        if not emp_val:
            return 'unemployed'
        emp_val = str(emp_val).strip().lower()
        if emp_val in ['true', 'yes', '1']:
            return 'employed'
        return 'unemployed'

    def parse_to_dict(self, filter_agents: set = None) -> dict:
        """
        Parses demographics and returns a dictionary.
        If filter_agents is provided, it only extracts data for those specific IDs
        to save memory (useful for Accidents and Noise).
        """
        print(f"Parsing demographics to dictionary from {self.plans_xml}...")
        open_func = gzip.open if self.plans_xml.endswith('.gz') else open
        mode = 'rt' if self.plans_xml.endswith('.gz') else 'r'

        data = {}
        with open_func(self.plans_xml, mode, encoding='utf-8') as f:
            context = ET.iterparse(f, events=('start', 'end'))
            current_person = None
            attributes = {}

            for event, elem in context:
                if event == 'start' and elem.tag == 'person':
                    current_person = elem.attrib.get('id')
                    attributes = {}

                elif event == 'end' and elem.tag == 'attribute' and current_person:
                    name = elem.attrib.get('name')
                    if name in ['age', 'sex', 'employed']:
                        attributes[name] = elem.text

                elif event == 'end' and elem.tag == 'person':
                    if current_person is not None:
                        if filter_agents is None or current_person in filter_agents:
                            data[current_person] = {
                                'age_val': float(attributes.get('age')) if attributes.get('age') else np.nan,
                                'age_group': self.categorize_age(attributes.get('age')),
                                'gender': self.format_gender(attributes.get('sex')),
                                'occupation': self.format_occupation(attributes.get('employed'))
                            }
                    current_person = None
                    elem.clear()

        return data

    def parse_to_dataframe(self) -> pd.DataFrame:
        """
        Parses all demographics and returns a pandas DataFrame.
        Useful for quick merges (e.g., Accessibility and Emissions).
        """
        print(f"Parsing demographics to DataFrame from {self.plans_xml}...")
        open_func = gzip.open if self.plans_xml.endswith('.gz') else open
        mode = 'rt' if self.plans_xml.endswith('.gz') else 'r'

        records = []
        with open_func(self.plans_xml, mode, encoding='utf-8') as f:
            context = ET.iterparse(f, events=('start', 'end'))
            current_person = None
            attributes = {}

            for event, elem in context:
                if event == 'start' and elem.tag == 'person':
                    current_person = elem.attrib.get('id')
                    attributes = {}

                elif event == 'end' and elem.tag == 'attribute' and current_person:
                    name = elem.attrib.get('name')
                    if name in ['age', 'sex', 'employed']:
                        attributes[name] = elem.text

                elif event == 'end' and elem.tag == 'person':
                    if current_person is not None:
                        records.append({
                            'person_id': current_person,
                            'gender': self.format_gender(attributes.get('sex')),
                            'age_group': self.categorize_age(attributes.get('age')),
                            'occupation': self.format_occupation(attributes.get('employed'))
                        })
                    current_person = None
                    elem.clear()

        return pd.DataFrame(records)