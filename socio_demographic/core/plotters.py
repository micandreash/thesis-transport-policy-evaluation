import os
import warnings

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

warnings.filterwarnings('ignore')


class ViolinPlotter :
    """
    Core visualization class for socio-demographic agent-level data.
    Handles data filtering, custom x-axis labeling, and generation of high-res violin plots.
    """

    def __init__(self, output_dir: str) :
        self.plot_dir = os.path.join(output_dir, "plots")
        os.makedirs(self.plot_dir, exist_ok=True)

        # Set standardized Seaborn theme
        sns.set_theme(style="whitegrid", font_scale=1.2)
        self.gender_palette = {"male" : "#4C72B0", "female" : "#C44E52"}

    def _generate_custom_x_labels(self, df: pd.DataFrame) -> tuple :
        """
        Generates custom x-axis labels appending male/female agent counts.
        Returns the original age order and a dictionary mapping.
        """
        age_order = ['0-18', '19-29', '30-49', '50-64', '65+']
        label_mapping = {}

        for age in age_order :
            subset = df[df['age_group'] == age]
            m_count = len(subset[subset['gender'] == 'male'])
            f_count = len(subset[subset['gender'] == 'female'])
            label_mapping[age] = f"{age}\n(m:{m_count}, f:{f_count})"

        return age_order, label_mapping

    def _prepare_plot_data(self, df: pd.DataFrame) -> tuple :
        """
        Filters out 'Unknown' categories for a clean visualization and maps the custom labels.
        """
        plot_df = df[(df['age_group'] != 'Unknown') & (df['gender'] != 'Unknown')].copy()

        age_order, label_mapping = self._generate_custom_x_labels(plot_df)
        plot_df['age_label'] = plot_df['age_group'].map(label_mapping)
        x_order_mapped = [label_mapping[age] for age in age_order]

        return plot_df, x_order_mapped

    def plot_single_violin(self, df: pd.DataFrame, y_col: str, y_label: str, title: str, filename: str,
                           color: str = "lightblue") :
        """
        Generates a standard violin plot across age groups.
        """
        plot_df, x_order_mapped = self._prepare_plot_data(df)

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.canvas.manager.set_window_title(title)

        sns.violinplot(
            data=plot_df, x='age_label', y=y_col, order=x_order_mapped,
            color=color, inner="quartile", ax=ax
        )

        ax.set_xlabel("", fontsize=16)
        ax.set_ylabel(y_label, fontsize=16)
        ax.tick_params(axis='x', labelsize=14)
        ax.tick_params(axis='y', labelsize=14)

        plt.tight_layout()
        out_path = os.path.join(self.plot_dir, filename)
        plt.savefig(out_path, dpi=300, bbox_inches='tight')
        plt.close(fig)  # Free up memory

    def plot_split_violin(self, df: pd.DataFrame, y_col: str, y_label: str, title: str, filename: str) :
        """
        Generates a split violin plot comparing male vs. female across age groups.
        """
        plot_df, x_order_mapped = self._prepare_plot_data(df)

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.canvas.manager.set_window_title(title)

        sns.violinplot(
            data=plot_df, x='age_label', y=y_col, hue='gender', split=True,
            hue_order=['male', 'female'], order=x_order_mapped,
            palette=self.gender_palette, inner="quartile", ax=ax, cut=0
        )

        ax.set_xlabel("", fontsize=16)
        ax.set_ylabel(y_label, fontsize=16)
        ax.tick_params(axis='x', labelsize=14)
        ax.tick_params(axis='y', labelsize=14)

        # Position legend neatly at the bottom
        ax.legend(title="", loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=16)

        plt.tight_layout()
        out_path = os.path.join(self.plot_dir, filename)
        plt.savefig(out_path, dpi=300, bbox_inches='tight')
        plt.close(fig)  # Free up memory