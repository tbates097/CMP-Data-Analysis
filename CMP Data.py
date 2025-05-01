import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
import numpy as np
import json
import re

# --- Configuration ---
# <<< POINT THIS TO YOUR JSON FILE (Output of the NEW Base Data SQL Query) >>>
DATA_FILE_BASE = 'base_labor_data.json'

# Output directory
OUTPUT_DIR = 'employee_efficiency_charts'
PRODUCT_SPECS_FILE = 'Product Specs.json'
# --- End Configuration ---

def load_part_mapping(filepath):
    """Load and create part number mapping dictionary"""
    try:
        with open(filepath, 'r') as f:
            specs = json.load(f)
            
        # Create mapping dictionary based on base models
        part_mapping = {}
        for base_model in specs.keys():
            # Create regex pattern to match base model at start of part number
            pattern = f"^{base_model}.*"
            part_mapping[pattern] = base_model
            
        return part_mapping

    except Exception as e:
        print(f"Error loading part mapping: {e}")
        return None

def map_part_number(part_num, mapping, part_desc=None):
    """
    Map a part number to its base model
    Special handling for PM100 parts - uses first 8 chars of part description
    """
    # Special handling for PM100 parts
    if part_num.startswith('PM100') and part_desc:
        return part_desc[:8]  # Return first 8 characters of description
        
    # Standard mapping for other parts
    for pattern, base_model in mapping.items():
        if re.match(pattern, part_num):
            return base_model
    return None

def load_base_data(filepath):
    """Loads data from the new base SQL query output."""
    print(f"\nAttempting to load base data from: {filepath}")
    df = None
    try:
        if not os.path.exists(filepath):
            print(f"Error: Data file not found at {filepath}")
            sys.exit(1)

        if filepath.lower().endswith('.csv'):
            df = pd.read_csv(filepath)
        elif filepath.lower().endswith(('.xls', '.xlsx')):
            df = pd.read_excel(filepath)
        elif filepath.lower().endswith('.json'):
            df = pd.read_json(filepath, orient='records')
        else:
            print(f"Error: Unsupported file format: {filepath}")
            sys.exit(1)

        if df is None or df.empty:
             print("Error: Data loading resulted in an empty DataFrame.")
             sys.exit(1)

        print(f"Data loaded successfully. Found {len(df)} rows.")
        print("Columns found:", df.columns.tolist())

        # Expected columns from the new base query
        expected_cols = ['Name', 'JobNum', 'OprSeq', 'BasePartNum', 'PartDescription',
                         'ProdStandard', 'ProdQty', 'LaborHrs', 'StartDate']
        # Include FullPartNum if selected in SQL
        if 'FullPartNum' in df.columns: expected_cols.append('FullPartNum')
        # Include LaborDate if selected in SQL
        if 'LaborDate' in df.columns: expected_cols.append('LaborDate')

        numeric_cols = ['OprSeq', 'ProdStandard', 'ProdQty', 'LaborHrs']

        # Basic Cleaning Example (adapt as needed)
        missing_cols = [col for col in expected_cols if col not in df.columns]
        if missing_cols:
            print(f"Warning: Missing expected columns: {missing_cols}")

        df.replace(["", "NULL", "None", "null"], np.nan, inplace=True)
        for col in numeric_cols:
             if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Drop rows essential for analysis if null after conversion
        essential_cols = ['Name', 'JobNum', 'OprSeq', 'BasePartNum', 'PartDescription',
                          'ProdStandard', 'ProdQty', 'LaborHrs', 'StartDate']
        original_rows = len(df)
        df.dropna(subset=essential_cols, inplace=True)
        if len(df) < original_rows:
             print(f"Dropped {original_rows - len(df)} rows with missing essential data.")

        # Further filtering based on SQL WHERE clauses (redundant but safe)
        df = df[df['ProdQty'] > 0]
        df = df[df['ProdStandard'] > 0]
        df = df[df['LaborHrs'] >= 0] # Allow zero hours reported, but filter negative

        # Ensure correct types for keys / categorical data AFTER cleaning/dropping
        if not df.empty:
            df['OprSeq'] = df['OprSeq'].astype(int).astype(str)
            df['JobNum'] = df['JobNum'].astype(str)
            df['BasePartNum'] = df['BasePartNum'].astype(str)
            df['PartDescription'] = df['PartDescription'].astype(str)
            df['Name'] = df['Name'].astype(str)
            df['StartDate'] = pd.to_datetime(df['StartDate'], errors='coerce')
        else:
             print("DataFrame became empty after cleaning/dropping rows.")
             sys.exit(1)

        try:
            # Load part mapping
            part_mapping = load_part_mapping(PRODUCT_SPECS_FILE)
            if part_mapping:
                # Add normalized part numbers column using the mapping function with part description
                df['NormalizedPartNum'] = df.apply(
                    lambda row: map_part_number(
                        row['BasePartNum'], 
                        part_mapping, 
                        row['PartDescription']
                    ), 
                    axis=1
                )
                # Calculate stats before filtering
                total_rows = len(df)
                mapped_count = df['NormalizedPartNum'].notna().sum()
                unmapped_count = total_rows - mapped_count
                
                # Get unmapped parts with their descriptions
                unmapped_df = df[df['NormalizedPartNum'].isna()][['BasePartNum', 'PartDescription']].drop_duplicates()
                
                # Write unmapped parts to log file
                log_file = 'unmapped_parts.log'
                with open(log_file, 'w') as f:
                    f.write(f"Unmapped Part Numbers Report\n")
                    f.write(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"\nTotal Parts: {total_rows}")
                    f.write(f"\nMapped Parts: {mapped_count}")
                    f.write(f"\nUnmapped Parts: {unmapped_count}\n")
                    f.write("\nUnique Unmapped Part Numbers:\n")
                    f.write("=" * 80 + "\n")
                    f.write("Part Number\tDescription\n")
                    f.write("-" * 80 + "\n")
                    for _, row in unmapped_df.iterrows():
                        f.write(f"{row['BasePartNum']}\t{row['PartDescription']}\n")
                
                print(f"\nFound {mapped_count} rows with valid part number mappings")
                print(f"Found {unmapped_count} rows with unmapped part numbers")
                print(f"Unmapped parts have been written to: {log_file}")
                
                # Filter to keep only mapped rows
                df = df[df['NormalizedPartNum'].notna()]
                print(f"\nKept {len(df)} rows after filtering")
        except Exception as e:
            print(f"Error applying part number mapping: {e}")
            sys.exit(1)

        print(f"Cleaned data ready: {len(df)} rows.")
        df.info()
        print(df.head())
        return df

    except Exception as e:
        print(f"Error loading or cleaning base data: {e}")
        sys.exit(1)

def create_employee_efficiency_charts(df, target_name, base_output_dir='employee_efficiency_charts'):
    """Creates efficiency ratio bar charts for a specific employee."""
    print(f"\n--- Generating Efficiency Ratio/Difference Charts for: {target_name} ---")

    # Create employee-specific output directory
    employee_dir = os.path.join(base_output_dir, target_name.replace(' ', '_'))
    if not os.path.exists(employee_dir):
        os.makedirs(employee_dir)
        print(f"Created employee directory: {employee_dir}")

    df_user = df[df['Name'] == target_name].copy()
    if df_user.empty:
        print(f"No data found for employee: {target_name}")
        return

    # --- Chart 1: Efficiency Ratio per Job/Operation ---
    print("Preparing data for Chart 1: Job/Op Efficiency Ratio/Difference")
    # Group by Job/Op for the selected user
    df_job_op = df_user.groupby(['JobNum', 'OprSeq'], as_index=False).agg(
        SumTotalLaborHrs=('LaborHrs', 'sum'),
        ProdStandard=('ProdStandard', 'first'), # Assumes ProdStd constant per Job/Op
        ProdQty=('ProdQty', 'first'),           # Assumes ProdQty constant per JobNum
        BasePartNum=('BasePartNum', 'first'),   # **** Added BasePartNum to aggregation ****
        PartDescription=('PartDescription', 'first') # Added for clarity
    )
    # Calculate HrsPerUnit
    df_job_op['HrsPerUnit'] = np.where(df_job_op['ProdQty'] > 0,
                                       df_job_op['SumTotalLaborHrs'] / df_job_op['ProdQty'],
                                       np.nan)
    # Calculate Ratio and Difference
    df_job_op['EfficiencyRatio'] = np.where(df_job_op['ProdStandard'] > 0,
                                            df_job_op['HrsPerUnit'] / df_job_op['ProdStandard'],
                                            np.nan)
    df_job_op['TimeDifference'] = df_job_op['HrsPerUnit'] - df_job_op['ProdStandard']

    # Keep only rows with a valid ratio to plot
    df_job_op.dropna(subset=['EfficiencyRatio'], inplace=True)

    if not df_job_op.empty:
        print(f"  - Plotting {len(df_job_op)} Job/Op combinations for Chart 1...")
        # Create combined Job-Op identifier for unique axis labels
        df_job_op['OprSeq'] = df_job_op['OprSeq'].astype(str) # Ensure OprSeq is string
        df_job_op['JobOp'] = df_job_op['JobNum'].astype(str) + '-' + df_job_op['OprSeq']

        fig_1 = px.bar(df_job_op.sort_values('JobOp'), # Sort for consistent axis
                       x='JobOp', y='EfficiencyRatio',
                       title=f"Job/Operation Efficiency Ratio for {target_name}<br>(Actual HrsPerUnit / ProdStandard; Target = 1.0)",
                       labels={'EfficiencyRatio': 'Efficiency Ratio (Actual/Standard)', 'JobOp': 'Job-Operation'},
                       # **** Added BasePartNum to hover_data ****
                       hover_data={'BasePartNum': True, # Display BasePartNum on hover
                                   'PartDescription': True, # Display PartDescription on hover
                                   'TimeDifference': ':.2f', 'HrsPerUnit': ':.2f',
                                   'ProdStandard': ':.2f', 'SumTotalLaborHrs':':.2f', 'ProdQty':':.0f'}
                      )
        # Add horizontal line at y=1 (Standard efficiency)
        fig_1.add_hline(y=1.0, line_dash="dash", line_color="red", # Use red for standard line
                        annotation_text="Standard", annotation_position="bottom right")
        fig_1.update_layout(legend_title_text='Metric')
        fig_1.update_xaxes(tickangle=45, type='category')

        # Save the chart
        chart_filename_1 = f"1_Ratio_JobOp_Efficiency.html"
        fig_1.write_html(os.path.join(employee_dir, chart_filename_1))
        print(f"  - Chart 1 saved: {os.path.join(target_name.replace(' ', '_'), chart_filename_1)}")
    else:
        print(f"  - No valid data to plot for Chart 1 for {target_name}.")

    # --- Chart 2: Avg Efficiency Ratio per Part/Operation ---
    print("Preparing data for Chart 2: Part/Op Efficiency Ratio/Difference (Normalized)")

    # We need df_job_op which was calculated for Chart 1 and already contains:
    # JobNum, OprSeq, SumTotalLaborHrs, ProdStandard, ProdQty, BasePartNum, HrsPerUnit, EfficiencyRatio, TimeDifference
    # Make sure df_job_op calculation happened before this section

    if 'df_job_op' in locals() and not df_job_op.empty: # Check if df_job_op exists and is not empty

        # Group the JOB/OP level data (which has HrsPerUnit) by BasePart/Op
        df_part_op = df_job_op.groupby(['BasePartNum', 'OprSeq'], as_index=False).agg(
            # Calculate Avg of the NORMALIZED HrsPerUnit for this Part/Op across jobs
            AvgHrsPerUnit=('HrsPerUnit', 'mean'),
            # Calculate Avg standard if it varies for same BasePart/Op across different jobs
            AvgProdStandard=('ProdStandard', 'mean'),
            # Count how many unique Job/Op instances contribute to this Part/Op average
            JobOpInstanceCount=('JobNum', 'nunique'), # Count distinct jobs for this part/op
            PartDescription=('PartDescription', 'first') # Added for clarity
        )
        # Calculate Avg Ratio and Difference based on the AVERAGED normalized hours and standards
        df_part_op['AvgEfficiencyRatio'] = np.where(df_part_op['AvgProdStandard'] > 0,
                                                     df_part_op['AvgHrsPerUnit'] / df_part_op['AvgProdStandard'],
                                                     np.nan)
        df_part_op['AvgTimeDifference'] = df_part_op['AvgHrsPerUnit'] - df_part_op['AvgProdStandard']

        # Keep only rows with a valid ratio
        df_part_op.dropna(subset=['AvgEfficiencyRatio'], inplace=True)

        if not df_part_op.empty:
            print(f"  - Plotting {len(df_part_op)} Part/Op combinations for Chart 2...")
            # Create combined Part-Op identifier
            df_part_op['OprSeq'] = df_part_op['OprSeq'].astype(str) # Ensure OprSeq is string
            df_part_op['PartOp'] = df_part_op['BasePartNum'].astype(str) + '-' + df_part_op['OprSeq']

            fig_2 = px.bar(df_part_op.sort_values('PartOp'), # Sort for consistent axis
                           x='PartOp', y='AvgEfficiencyRatio',
                           title=f"Part/Operation Average Efficiency Ratio for {target_name}<br>(Avg HrsPerUnit / Avg ProdStandard; Target = 1.0)",
                           labels={'AvgEfficiencyRatio': 'Avg Efficiency Ratio (NormHrs/Std)', 'PartOp': 'BasePart-Operation'},
                           # Include Difference and original Avg values in hover
                           hover_data={'PartDescription': True, 'AvgTimeDifference': ':.2f', 'AvgHrsPerUnit': ':.3f',
                                       'AvgProdStandard': ':.3f', 'JobOpInstanceCount': True}
                          )
            # Add horizontal line at y=1
            fig_2.add_hline(y=1.0, line_dash="dash", line_color="red",
                            annotation_text="Standard", annotation_position="bottom right")
            fig_2.update_layout(legend_title_text='Metric')
            fig_2.update_xaxes(tickangle=45, type='category')

            # Save the chart
            chart_filename_2 = f"2_Ratio_PartOp_Efficiency_Normalized.html"
            fig_2.write_html(os.path.join(employee_dir, chart_filename_2))
            print(f"  - Chart 2 saved: {os.path.join(target_name.replace(' ', '_'), chart_filename_2)}")
        else:
            print(f"  - No valid data to plot for Chart 2 (Normalized) for {target_name}.")
    else:
         print("  - Skipping Chart 2 because Chart 1 data preparation failed or was empty.")

    print(f"\nChart generation complete for {target_name}.")

def create_weekly_efficiency_analysis(df, output_dir='employee_efficiency_charts'):
    """Analyzes weekly efficiency metrics per employee at Job-Operation level"""
    print("\nGenerating Weekly Efficiency Analysis...")
    
    # Count total raw entries per employee before any aggregation
    raw_entry_counts = df.groupby('Name').size().reset_index(name='TotalEntries')
    print("\nTotal raw entries per employee:")
    print(raw_entry_counts.to_string())
    
    # Add date range validation and logging at the start
    date_range = pd.date_range(df['StartDate'].min(), df['StartDate'].max())
    total_weeks = len(pd.period_range(df['StartDate'].min(), df['StartDate'].max(), freq='W'))
    print(f"\nAnalyzing data from {df['StartDate'].min().strftime('%Y-%m-%d')} to {df['StartDate'].max().strftime('%Y-%m-%d')}")
    print(f"Total weeks in date range: {total_weeks}")
    
    # Calculate active weeks per employee for context
    employee_weeks = df.groupby('Name').agg({
        'StartDate': lambda x: len(pd.period_range(x.min(), x.max(), freq='W'))
    }).rename(columns={'StartDate': 'WeeksActive'})
    print("\nWeeks active per employee:")
    print(employee_weeks.to_string())
    
    # First, calculate efficiency at Job-Operation level
    df_job_op = df.groupby(['Name', 'JobNum', 'OprSeq']).agg({
        'LaborHrs': 'sum',
        'ProdStandard': 'first',
        'ProdQty': 'first',
        'StartDate': 'first'
    }).reset_index()
    
    # Calculate efficiency ratio at Job-Operation level
    df_job_op['HrsPerUnit'] = np.where(df_job_op['ProdQty'] > 0,
                                      df_job_op['LaborHrs'] / df_job_op['ProdQty'],
                                      np.nan)
    df_job_op['EfficiencyRatio'] = np.where(df_job_op['ProdStandard'] > 0,
                                           df_job_op['HrsPerUnit'] / df_job_op['ProdStandard'],
                                           np.nan)
    
    # Add week start date
    df_job_op['WeekStart'] = pd.to_datetime(df_job_op['StartDate']).dt.to_period('W').dt.start_time
    
    # First group by Name, WeekStart, and JobNum to count unique operations per job
    job_ops_per_week = df_job_op.groupby(['Name', 'WeekStart', 'JobNum'])['OprSeq'].nunique().reset_index()
    
    # Then calculate weekly metrics
    weekly_metrics = job_ops_per_week.groupby(['Name', 'WeekStart']).agg({
        'JobNum': 'nunique',                # Unique jobs per week
        'OprSeq': 'sum'                     # Sum of unique operations across all jobs that week
    }).reset_index()
    
    # Add efficiency metrics
    efficiency_metrics = df_job_op.groupby(['Name', 'WeekStart']).agg({
        'EfficiencyRatio': 'mean',          # Average efficiency ratio
        'ProdStandard': 'mean'             # Average production standard
    }).reset_index()
    
    # Merge the metrics
    weekly_metrics = weekly_metrics.merge(efficiency_metrics, on=['Name', 'WeekStart'])
    
    # Calculate employee averages with proper weekly division
    employee_averages = weekly_metrics.merge(employee_weeks, on='Name').groupby('Name').agg({
        'JobNum': lambda x: x.sum() / x.count(),    # Average jobs per active week
        'OprSeq': lambda x: x.sum() / x.count(),    # Average operations per active week
        'EfficiencyRatio': 'mean',                  # Average efficiency ratio
        'ProdStandard': 'mean',                     # Average production standard
        'WeeksActive': 'first'                      # Keep weeks active for reference
    }).reset_index()
    
    # Add raw entry counts
    employee_averages = employee_averages.merge(raw_entry_counts, on='Name')
    
    # Update scatter plot to use TotalEntries for marker size
    fig = px.scatter(
        employee_averages,
        x='OprSeq',
        y='EfficiencyRatio',
        color='ProdStandard',
        size='TotalEntries',                # Changed to use total raw entries
        size_max=50,
        color_continuous_scale=['lightblue', 'darkblue'],
        text='Name',
        title='Employee Efficiency Analysis (Job-Operation Level)',
        labels={
            'OprSeq': 'Average Operations per Week',
            'EfficiencyRatio': 'Average Efficiency Ratio (Lower is Better)',
            'ProdStandard': 'Avg Production Standard (Hours)',
            'TotalEntries': 'Total Number of Entries'  # Added label for hover
        },
        hover_data={
            'Name': True,
            'JobNum': ':.1f',
            'OprSeq': ':.1f',
            'EfficiencyRatio': ':.2f',
            'ProdStandard': ':.2f',
            'TotalEntries': True            # Show raw count in hover
        }
    )
    
    # Add reference lines
    fig.add_hline(
        y=1.0, 
        line_dash="dash", 
        line_color="red",
        annotation_text="Target Efficiency (1.0)"
    )
    
    group_avg_ops = employee_averages['OprSeq'].mean()
    group_avg_ratio = employee_averages['EfficiencyRatio'].mean()
    
    fig.add_hline(
        y=group_avg_ratio,
        line_dash="dash", 
        line_color="gray",
        annotation_text=f"Group Avg ({group_avg_ratio:.2f})"
    )
    
    fig.add_vline(
        x=group_avg_ops, 
        line_dash="dash", 
        line_color="gray",
        annotation_text=f"Group Avg Ops ({group_avg_ops:.1f})"
    )
    
    # Update layout
    fig.update_traces(textposition='top center')
    fig.update_layout(
        showlegend=True,
        legend_title_text='Avg Production Standard',
        xaxis_title="Average Unique Operations per Week",
        yaxis_title="Average Efficiency Ratio (Lower is Better)"
    )
    
    # Save the plot
    output_file = os.path.join(output_dir, "weekly_efficiency_analysis.html")
    fig.write_html(output_file)
    print(f"Weekly efficiency analysis saved to: {output_file}")
    
    # Return the metrics dataframes
    return weekly_metrics, employee_averages

def create_department_weekly_charts(df, output_dir='employee_efficiency_charts'):
    """Creates weekly efficiency charts for the entire department."""
    print("\nGenerating Department Weekly Analysis...")
    
    # Create department charts directory
    dept_dir = os.path.join(output_dir, 'Department_Analysis')
    if not os.path.exists(dept_dir):
        os.makedirs(dept_dir)
        print(f"Created department directory: {dept_dir}")
    
    # Calculate efficiency at Job-Operation level first
    df_job_op = df.groupby(['JobNum', 'OprSeq', 'StartDate']).agg({
        'LaborHrs': 'sum',
        'ProdStandard': 'first',
        'ProdQty': 'first'
    }).reset_index()
    
    # Calculate efficiency ratios
    df_job_op['HrsPerUnit'] = np.where(df_job_op['ProdQty'] > 0,
                                      df_job_op['LaborHrs'] / df_job_op['ProdQty'],
                                      np.nan)
    df_job_op['EfficiencyRatio'] = np.where(df_job_op['ProdStandard'] > 0,
                                           df_job_op['HrsPerUnit'] / df_job_op['ProdStandard'],
                                           np.nan)
    
    # Add week start date
    df_job_op['WeekStart'] = pd.to_datetime(df_job_op['StartDate']).dt.to_period('W').dt.start_time
    
    # Calculate weekly metrics with confidence intervals
    weekly_metrics = df_job_op.groupby('WeekStart').agg({
        'JobNum': 'nunique',
        'OprSeq': 'nunique',
        'EfficiencyRatio': ['mean', 'std', 'count', 'sem'],  # Added standard error of mean
        'ProdStandard': 'mean'
    }).reset_index()
    
    # Flatten column names and calculate confidence intervals
    weekly_metrics.columns = ['WeekStart', 'UniqueJobs', 'UniqueOperations', 
                            'AvgEfficiency', 'StdDevEfficiency', 'SampleSize',
                            'StdError', 'AvgProdStandard']
    
    # Calculate 95% confidence intervals
    confidence_level = 0.95
    z_score = 1.96  # z-score for 95% confidence level
    weekly_metrics['CI_Lower'] = weekly_metrics['AvgEfficiency'] - (z_score * weekly_metrics['StdError'])
    weekly_metrics['CI_Upper'] = weekly_metrics['AvgEfficiency'] + (z_score * weekly_metrics['StdError'])
    
    # Create bar chart with confidence intervals
    fig = go.Figure()
    
    # Add efficiency ratio bars with confidence intervals
    fig.add_trace(go.Bar(
        x=weekly_metrics['WeekStart'],
        y=weekly_metrics['AvgEfficiency'],
        name='Weekly Efficiency',
        error_y=dict(
            type='data',
            array=(weekly_metrics['CI_Upper'] - weekly_metrics['AvgEfficiency']),
            arrayminus=(weekly_metrics['AvgEfficiency'] - weekly_metrics['CI_Lower']),
            visible=True,
            color='rgba(0,0,0,0.3)',  # Semi-transparent black
            thickness=1.5
        )
    ))
    
    # Add target line
    fig.add_hline(
        y=1.0,
        line_dash="dash",
        line_color="red",
        annotation_text="Target Efficiency (1.0)"
    )
    
    # Update layout
    fig.update_layout(
        title='Department Weekly Efficiency Ratio',
        xaxis_title="Week Starting",
        yaxis_title="Average Efficiency Ratio (Lower is Better)",
        showlegend=True,
        hovermode='x unified',
        hoverlabel=dict(namelength=-1),
    )
    
    # Add hover template
    fig.update_traces(
        hovertemplate="Week: %{x}<br>" +
                     "Efficiency: %{y:.2f}<br>" +
                     "Jobs: " + weekly_metrics['UniqueJobs'].astype(str) + "<br>" +
                     "Operations: " + weekly_metrics['UniqueOperations'].astype(str) + "<br>" +
                     "Sample Size: " + weekly_metrics['SampleSize'].astype(str)
    )
    
    # Save the plot
    output_file = os.path.join(dept_dir, "department_weekly_efficiency.html")
    fig.write_html(output_file)
    print(f"Department weekly analysis saved to: {output_file}")
    
    return weekly_metrics

# --- Main Execution ---
if __name__ == "__main__":
    base_data = load_base_data(DATA_FILE_BASE)

    if base_data is not None and not base_data.empty:
        available_names = sorted(base_data['Name'].unique())
        print("\nAvailable names for analysis in the loaded data:")
        if not available_names:
             print("No names found in the data after cleaning!")
             sys.exit(1)

        for i, name in enumerate(available_names):
            print(f"{i+1}. {name}")

        while True:
            try:
                choice = input(f"\nEnter the number corresponding to the name (1-{len(available_names)}) or 'q' to quit: ")
                if choice.lower() == 'q':
                    break
                choice_int = int(choice)
                if 1 <= choice_int <= len(available_names):
                    target_name = available_names[choice_int - 1]
                    # Filter data *once* for the selected user
                    user_data = base_data[base_data['Name'] == target_name].copy()
                    if user_data.empty:
                        print(f"No data rows remain for {target_name} after initial loading/cleaning.")
                        continue # Ask for another name
                    # Pass only the user's data to the charting function
                    create_employee_efficiency_charts(user_data, target_name)
                else:
                    print("Invalid number. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number or 'q'.")
            except Exception as e:
                print(f"An error occurred during chart generation: {e}")
                # Decide if you want to break the loop or allow user to try another name
                # break

        # Generate weekly efficiency analysis for all employees
        weekly_metrics, employee_averages = create_weekly_efficiency_analysis(base_data)
        
        print("\nEmployee Weekly Averages:")
        print(employee_averages.sort_values('EfficiencyRatio')[
            ['Name', 'JobNum', 'OprSeq', 'EfficiencyRatio', 'ProdStandard', 'TotalEntries']
        ].to_string(index=False, float_format=lambda x: '{:.2f}'.format(x)))

        # Generate department-wide analysis
        print("\nGenerating Department-wide Analysis...")
        dept_weekly_metrics = create_department_weekly_charts(base_data)

    print("\nScript finished.")