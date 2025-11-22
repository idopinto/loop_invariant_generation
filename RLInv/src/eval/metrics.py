import json
import numpy as np
import pandas as pd
from pathlib import Path
import plotly.graph_objects as go

def load_results(results_path: Path) -> pd.DataFrame:
    with open(results_path, "r") as f:
        results = json.load(f)
    df = pd.json_normalize(results["results"])
    return df

class InvBenchMetrics:
    """Class for calculating InvBench metrics."""

    @staticmethod
    def _calculate_speedup_metrics(df: pd.DataFrame, speedup_col: str, percent_correct: float) -> dict:
        """
        Calculate speedup metrics for a given speedup column.
        
        Args:
            df: DataFrame containing the results
            speedup_col: Name of the speedup column to use
            percent_correct: Percentage of correct invariants (0-1)
            
        Returns:
            dict: Dictionary containing the calculated metrics
        """
        n_samples = df.shape[0]
        mask_speedup_gt1 = (
            (df[speedup_col] > 1)
            & (df["report.final_decision"] != "UNKNOWN")
            & (df["report.invariant_correctness_report.decision"] == "TRUE")
        )
        speedup_gt1 = df[mask_speedup_gt1]
        df_speedup_all = df.copy()
        mask_no_speedup = ~mask_speedup_gt1
        df_speedup_all.loc[mask_no_speedup, speedup_col] = 1
        percent_speedup_gt1 = speedup_gt1.shape[0] / n_samples

        avg_speedup_gt1 = speedup_gt1[speedup_col].mean()
        if pd.isna(avg_speedup_gt1):
            avg_speedup_gt1 = 1

        avg_speedup_all = df_speedup_all[speedup_col].mean()
        if pd.isna(avg_speedup_all):
            avg_speedup_all = 1
        metrics = {
            "% Correct Invariant": float(np.round(percent_correct * 100, 2)),
            "% Speedup": float(np.round(percent_speedup_gt1 * 100, 2)),
            "Speedup>1": float(np.round(avg_speedup_gt1, 2)),
            "Speedup_all": float(np.round(avg_speedup_all, 2)),
        }
        return metrics

    @staticmethod
    def calculate_metrics(results_path: Path) -> dict:
        """
        Calculate metrics for both 'with gen' and 'without gen' scenarios.
        
        Returns:
            dict: Dictionary containing metrics for "with gen" and "without gen" scenarios
        """
        df = load_results(results_path=results_path)
        n_samples = df.shape[0]
        df["speedup_with_gen"] = df["baseline_time"] / pd.to_numeric(df["report.total_time_taken"], errors="coerce")
        df["speedup_without_gen"] = df["baseline_time"] / pd.to_numeric(df["report.verification_time_taken"], errors="coerce")

        # Only keep correct invariants (potentially filter for usefulness if needed)
        correct_invariants = df[df["report.invariant_correctness_report.decision"] == "TRUE"]
        percent_correct = correct_invariants.shape[0] / n_samples

        metrics_with_gen = InvBenchMetrics._calculate_speedup_metrics(df, "speedup_with_gen", percent_correct)
        metrics_without_gen = InvBenchMetrics._calculate_speedup_metrics(df, "speedup_without_gen", percent_correct)

        metrics = {
            "metrics_with_gen": metrics_with_gen,
            "metrics_without_gen": metrics_without_gen
        }
        return metrics

    @staticmethod
    def plot_verification_vs_baseline(
        results_path: Path,
        model_name: str = "gpt-oss-20b",
        baseline_name: str = "UAutomizer25 (0.3.0-dev-d790fec)",
        split_name: str = "hard",
        fig_size: tuple = (800, 800),
        metrics: dict = None,
        plot_path: Path = Path("plot.html")
    ):
        """
        Quickly plot LLM verification vs. baseline time,
        color by decision. Show metrics below the plot.
        Interactive checkboxes allow toggling UNKNOWN point visibility and generation time.
        """

        df = load_results(results_path)
        n_total = len(df)
        y_col = "baseline_time"

        # Prepare both time columns
        df["report.verification_time_taken"] = pd.to_numeric(df["report.verification_time_taken"], errors="coerce").round(2)
        df["report.total_time_taken"] = pd.to_numeric(df["report.total_time_taken"], errors="coerce").round(2)
        df[y_col] = pd.to_numeric(df[y_col], errors="coerce").round(2)
        df["speedup_without_gen"] = (df[y_col] / df["report.verification_time_taken"]).round(2)
        df["speedup_with_gen"] = (df[y_col] / df["report.total_time_taken"]).round(2)
        df["report.model_generation_time"] = pd.to_numeric(df.get("report.model_generation_time", 0), errors="coerce").round(2)

        # Count decisions
        dec_label = "report.final_decision"
        decision_counts = df[dec_label].value_counts().to_dict()
        count_true = decision_counts.get("TRUE", 0)
        count_false = decision_counts.get("FALSE", 0)
        count_unknown = decision_counts.get("UNKNOWN", 0)
        counts_str = f"Model results: TRUE ({count_true}) | FALSE ({count_false}) | UNKNOWN ({count_unknown})"

        # Color coding
        color_map = {"TRUE": "green", "FALSE": "red", "UNKNOWN": "blue"}
        symbol_map = {"TRUE": "circle", "FALSE": "diamond", "UNKNOWN": "triangle-up"}

        # Prepare hover data
        df["hover_correct"] = df["report.invariant_correctness_report.decision"]
        df["hover_useful"] = df["report.invariant_usefulness_report.decision"]
        df["hover_final_decision"] = df["report.final_decision"]
        df["hover_rule"] = df["report.decision_rule"]
        df["task_index"] = range(len(df))

        # Create figure with subplots (we'll create two sets of traces)
        fig = go.Figure()

        no_gen_indices_always = []
        no_gen_indices_unknown = []
        gen_indices_always = []
        gen_indices_unknown = []

        # Add traces for WITHOUT gen time (visible by default)
        for idx, decision in enumerate(["TRUE", "FALSE", "UNKNOWN"]):
            df_subset = df[df[dec_label] == decision]
            if len(df_subset) > 0:
                hover_without = (
                    "<b>%{customdata[0]}</b><br>" +
                    "Final Decision=%{customdata[1]}<br>" +
                    "LLM-assisted Verification Time (s)=%{x}<br>" +
                    "Baseline Timing (s)=%{y}<br>" +
                    "Task Index=%{customdata[2]}<br>" +
                    "Speedup=%{customdata[3]}<br>" +
                    "Correctness Decision=%{customdata[4]}<br>" +
                    "Usefulness Decision=%{customdata[5]}<br>" +
                    "Rule=%{customdata[6]}<br>"
                )
                fig.add_trace(go.Scatter(
                    x=df_subset["report.verification_time_taken"],
                    y=df_subset[y_col],
                    mode='markers',
                    marker=dict(size=10, color=color_map[decision], symbol=symbol_map[decision]),
                    name=decision,
                    customdata=df_subset[["task_name", "hover_final_decision", "task_index", "speedup_without_gen", "hover_correct", "hover_useful", "hover_rule"]].values,
                    hovertemplate=hover_without,
                    visible=True,
                    legendgroup=decision,
                    showlegend=True
                ))
                current_idx = len(fig.data) - 1
                if decision == "UNKNOWN":
                    no_gen_indices_unknown.append(current_idx)
                else:
                    no_gen_indices_always.append(current_idx)

        # Add traces for WITH gen time (hidden by default)
        for idx, decision in enumerate(["TRUE", "FALSE", "UNKNOWN"]):
            df_subset = df[df[dec_label] == decision]
            if len(df_subset) > 0:
                hover_with = (
                    "<b>%{customdata[0]}</b><br>" +
                    "Final Decision=%{customdata[1]}<br>" +
                    "LLM-assisted Verification+Gen Time (s)=%{x}<br>" +
                    "Baseline Timing (s)=%{y}<br>" +
                    "Task Index=%{customdata[2]}<br>" +
                    "Speedup=%{customdata[3]}<br>" +
                    "Correctness Decision=%{customdata[4]}<br>" +
                    "Usefulness Decision=%{customdata[5]}<br>" +
                    "Rule=%{customdata[6]}<br>"
                )
                fig.add_trace(go.Scatter(
                    x=df_subset["report.total_time_taken"],
                    y=df_subset[y_col],
                    mode='markers',
                    marker=dict(size=10, color=color_map[decision], symbol=symbol_map[decision]),
                    name=decision,
                    customdata=df_subset[["task_name", "hover_final_decision", "task_index", "speedup_with_gen", "hover_correct", "hover_useful", "hover_rule"]].values,
                    hovertemplate=hover_with,
                    visible=False,
                    legendgroup=decision,
                    showlegend=False
                ))
                current_idx = len(fig.data) - 1
                if decision == "UNKNOWN":
                    gen_indices_unknown.append(current_idx)
                else:
                    gen_indices_always.append(current_idx)

        # Diagonal and time-out lines as circles (shapes mode: type="circle")
        lims = [min(df["report.verification_time_taken"].min(), df["report.total_time_taken"].min(), df[y_col].min()), 
                max(df["report.verification_time_taken"].max(), df["report.total_time_taken"].max(), df[y_col].max(), 600)]
        # Draw main diagonal (orange line)
        fig.add_shape(type="line",
            x0=lims[0], y0=lims[0], x1=lims[1], y1=lims[1], line=dict(color="orange")
        )
        # Timeout "box" at 600
        # Add dashed lines for time limit
        fig.add_shape(type="line",
            x0=600, y0=lims[0], x1=600, y1=lims[1], line=dict(color="gray", dash="dash")
        )
        fig.add_shape(type="line",
            x0=lims[0], y0=600, x1=lims[1], y1=600, line=dict(color="gray", dash="dash")
        )

        # Leave more space at the bottom for metrics (increase b margin)
        fig.update_layout(
            width=fig_size[0], height=fig_size[1],
            showlegend=True,
            xaxis=dict(
                range=[lims[0]*0.95, lims[1]*1.05],
                title="LLM-assisted Verification Time (s)",
                autorange=False,
                fixedrange=False  # Allow zoom but keep range fixed when toggling traces
            ),
            yaxis=dict(
                range=[lims[0]*0.95, lims[1]*1.05],
                title="Baseline Time (s)",
                autorange=False,
                fixedrange=False
            ),
            margin=dict(t=140, b=120),  # Top and bottom margins (increased top for counts)
            title={
                "text": (
                    f"<b>LLM-assisted Verification vs Baseline</b><br>"
                    f"<span style='font-size:1.1em; color: #666;'>"
                    f"Model: {model_name} | Baseline: {baseline_name} | Split: {split_name} [{n_total}]"
                    f"</span><br>"
                    f"<span style='font-size:1.1em; color: #666;'>"
                    f"Timeout: set to baseline time."
                    f"</span><br>"
                    f"<span style='font-size:1.0em; color: #333;'>"
                    f"{counts_str}"
                    f"</span>"
                ),
                "x": 0.5
            }
        )

        # Prepare metrics for both versions
        m_without = metrics["metrics_without_gen"]
        m_with = metrics["metrics_with_gen"]
        metric_str_without = " | ".join([f"<b>{k}: {v}</b>" for k, v in m_without.items()])
        metric_str_with = " | ".join([f"<b>{k}: {v}</b>" for k, v in m_with.items()])
        
        # Add bold metrics annotation below plot area (will be updated by JavaScript)
        fig.add_annotation(
            text=f"{metric_str_without}",
            xref="paper", yref="paper",
            x=0.5, y=-0.18,  # y=0 is bottom of plot, so y<0 is below
            showarrow=False,
            align="center",
            font=dict(size=15, color="#111", family="Arial"),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="rgba(0,0,0,0.2)",
            borderpad=4,
            name="metricsAnnotation"
        )

        # Add custom HTML with checkboxes to toggle UNKNOWN visibility and gen time
        html_string = fig.to_html(include_plotlyjs='cdn')
        
        # Serialize indices for JS
        ng_always_js = json.dumps(no_gen_indices_always)
        ng_unk_js = json.dumps(no_gen_indices_unknown)
        g_always_js = json.dumps(gen_indices_always)
        g_unk_js = json.dumps(gen_indices_unknown)

        # Inject custom checkbox controls and centering CSS
        checkbox_html = f"""
        <style>
        body {{
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }}
        .plotly-graph-div {{
            margin: 0 auto;
        }}
        </style>
        <div style="position: fixed; top: 10px; right: 10px; background: white; padding: 12px; border: 2px solid #ddd; border-radius: 5px; z-index: 1000; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="margin-bottom: 8px;">
                <label style="cursor: pointer; font-family: Arial; font-size: 14px;">
                    <input type="checkbox" id="toggleUnknown" checked style="margin-right: 5px; cursor: pointer;">
                    Show UNKNOWN points
                </label>
            </div>
            <div>
                <label style="cursor: pointer; font-family: Arial; font-size: 14px;">
                    <input type="checkbox" id="toggleGenTime" style="margin-right: 5px; cursor: pointer;">
                    Include Generation Time
                </label>
            </div>
        </div>
        <script>
        var metricWithoutGen = "{metric_str_without}";
        var metricWithGen = "{metric_str_with}";

        // Dynamically injected indices
        var noGenIndicesAlways = {ng_always_js};
        var noGenIndicesUnknown = {ng_unk_js};
        var genIndicesAlways = {g_always_js};
        var genIndicesUnknown = {g_unk_js};

        // Helper function to set visibility for a set of indices
        function setVisible(plotDiv, indices, isVisible) {{
            if (indices.length > 0) {{
                Plotly.restyle(plotDiv, {{
                    'visible': isVisible,
                    'showlegend': isVisible
                }}, indices);
            }}
        }}

        function updatePlot() {{
            var plotDiv = document.getElementsByClassName('plotly-graph-div')[0];
            var showUnknown = document.getElementById('toggleUnknown').checked;
            var includeGenTime = document.getElementById('toggleGenTime').checked;

            // Capture current ranges BEFORE any changes
            var currentXRange = plotDiv.layout.xaxis.range.slice();
            var currentYRange = plotDiv.layout.yaxis.range.slice();

            if (includeGenTime) {{
                // Hide NO-GEN traces
                setVisible(plotDiv, noGenIndicesAlways, false);
                setVisible(plotDiv, noGenIndicesUnknown, false);
                
                // Show GEN traces
                setVisible(plotDiv, genIndicesAlways, true);
                setVisible(plotDiv, genIndicesUnknown, showUnknown);

                // Update annotation metrics and x-axis label
                var annotations = plotDiv.layout.annotations;
                if (annotations && annotations.length > 0) {{
                    annotations[annotations.length - 1].text = metricWithGen;
                }}
                Plotly.relayout(plotDiv, {{
                    'xaxis.title.text': 'LLM Verification+Gen Time (s)',
                    'xaxis.range': currentXRange,
                    'xaxis.autorange': false,
                    'yaxis.range': currentYRange,
                    'yaxis.autorange': false,
                    'annotations': annotations
                }});
            }} else {{
                // Hide GEN traces
                setVisible(plotDiv, genIndicesAlways, false);
                setVisible(plotDiv, genIndicesUnknown, false);

                // Show NO-GEN traces
                setVisible(plotDiv, noGenIndicesAlways, true);
                setVisible(plotDiv, noGenIndicesUnknown, showUnknown);

                // Update annotation metrics and x-axis label
                var annotations = plotDiv.layout.annotations;
                if (annotations && annotations.length > 0) {{
                    annotations[annotations.length - 1].text = metricWithoutGen;
                }}
                Plotly.relayout(plotDiv, {{
                    'xaxis.title.text': 'LLM Verification Time (s)',
                    'xaxis.range': currentXRange,
                    'xaxis.autorange': false,
                    'yaxis.range': currentYRange,
                    'yaxis.autorange': false,
                    'annotations': annotations
                }});
            }}
        }}

        // Ensure toggles work after DOM is fully loaded
        document.addEventListener('DOMContentLoaded', function() {{
            document.getElementById('toggleUnknown').addEventListener('change', updatePlot);
            document.getElementById('toggleGenTime').addEventListener('change', updatePlot);
        }});
        </script>
        """

        # Insert checkbox HTML after the opening body tag
        html_string = html_string.replace('<body>', '<body>\n' + checkbox_html)
        
        with open(plot_path, 'w') as f:
            f.write(html_string)



def main(): 
    results_dir = Path("/cs/labs/guykatz/idopinto12/projects/loop_invariant_generation/RLInv/experiments")
    plot_config = {
        "exp_name": "oss_20b_low_hard",
        "model_name": "gpt-oss-20b",
        "baseline_name": "UAutomizer25 (0.3.0-dev-d790fec)",
        "split_name": "hard"
    }
    results_path = results_dir / f"{plot_config['exp_name']}/{plot_config['model_name']}/{plot_config['model_name']}_results.json"
    metrics = InvBenchMetrics.calculate_metrics(results_path=results_path)
    print(metrics["metrics_with_gen"])
    print(metrics["metrics_without_gen"])
    InvBenchMetrics.plot_verification_vs_baseline(results_path=results_path,
                                                  model_name=plot_config["model_name"], 
                                                  baseline_name=plot_config["baseline_name"],
                                                  split_name=plot_config["split_name"],
                                                  metrics=metrics,
                                                  plot_path=Path(f"{plot_config['exp_name']}_plot.html"))
if __name__ == "__main__":
    main()