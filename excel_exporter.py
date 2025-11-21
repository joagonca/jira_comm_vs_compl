"""
Excel exporter for JIRA metrics
"""

from datetime import datetime
from typing import Optional, Tuple

import numpy
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from state_manager import State
from utils import (seconds_to_pretty, AGING_THRESHOLDS, 
                   PerformanceThreshold, ReworkThreshold, TrendThreshold, StatusLabel, TrendLabel)


class ExcelExporter:
    """Export JIRA metrics to Excel with multiple sheets"""

    def __init__(self, state: State, output_path: Optional[str] = None):
        """
        Initialize Excel exporter
        
        Args:
            state: State object containing all metrics
            output_path: Optional path for output file. If None, generates default name
        """
        self.state = state
        self.output_path = output_path or self._generate_default_filename()
        self.workbook = Workbook()
        
        # Remove default sheet
        if 'Sheet' in self.workbook.sheetnames:
            self.workbook.remove(self.workbook['Sheet'])
        
        self.header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        self.header_font = Font(bold=True, color="FFFFFF", size=12)
        self.subheader_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
        self.subheader_font = Font(bold=True, size=11)
        self.border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        self.good_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        self.warning_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        self.bad_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    def _generate_default_filename(self) -> str:
        """Generate default filename with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"jira_metrics_{timestamp}.xlsx"

    def export(self) -> str:
        """
        Export all metrics to Excel file
        
        Returns:
            Path to the generated Excel file
        """
        self._create_overall_summary_sheet()
        
        if self.state.monthly_metrics:
            sorted_months = sorted(self.state.monthly_metrics.keys())
            for month_key in sorted_months:
                self._create_monthly_sheet(month_key)
        
        self.workbook.save(self.output_path)
        return self.output_path

    def _create_overall_summary_sheet(self) -> None:
        """Create the overall summary sheet"""
        ws = self.workbook.create_sheet("Overall Summary", 0)
        row = self._write_title(ws, "JIRA Team Performance - Overall Summary")
        
        # Commitment vs Delivery section
        row = self._write_commitment_delivery_section(
            ws, row,
            self.state.delivered, self.state.carryover,
            self.state.delivered_sp, self.state.carryover_sp,
            show_total_label=True
        )
        row += 1

        # Monthly trends section
        if self.state.monthly_metrics and len(self.state.monthly_metrics) >= 2:
            row = self._write_monthly_trends_section(ws, row)
            row += 1
        
        # Rework Ratio section
        row = self._write_rework_ratio_section(ws, row, self.state.effort_per_type, "Rework Ratio (Overall)")
        row += 1
        
        # Cycle Time sections
        row = self._write_cycle_time_by_type_section(ws, row)
        row += 1
        row = self._write_cycle_time_by_sp_section(ws, row)
        row += 1
        
        # Work Item Aging section
        row = self._write_aging_section(ws, row)
        
        self._autosize_columns(ws)

    def _write_monthly_trends_section(self, ws: Worksheet, row: int) -> int:
        """Write monthly trends section"""
        row = self._write_section_header(ws, row, "Monthly Trends")
        
        sorted_months = sorted(self.state.monthly_metrics.keys())
        ratios_by_issues = []
        ratios_by_sp = []
        
        for month_key in sorted_months:
            metrics = self.state.monthly_metrics[month_key]
            total = metrics['delivered'] + metrics['carryover']
            total_sp_month = metrics['delivered_sp'] + metrics['carryover_sp']
            
            if total > 0:
                ratios_by_issues.append(metrics['delivered'] / total)
                ratios_by_sp.append((metrics['delivered_sp'] / total_sp_month) if total_sp_month > 0 else 0)
        
        issue_trend = self.state.calculate_linear_trend(ratios_by_issues)
        sp_trend = self.state.calculate_linear_trend(ratios_by_sp)
        
        trend_data = [
            ["Metric", "Trend Direction", "Status"],
            ["Commitment vs Delivery (Issues)", self._trend_to_text(issue_trend), 
             self._trend_to_status(issue_trend)],
            ["Commitment vs Delivery (Story Points)", self._trend_to_text(sp_trend), 
             self._trend_to_status(sp_trend)],
        ]
        
        return self._write_data_table(ws, row, trend_data, apply_status_coloring=True)

    def _write_cycle_time_by_type_section(self, ws: Worksheet, row: int) -> int:
        """Write cycle time by issue type section"""
        row = self._write_section_header(ws, row, "Average Cycle Time by Issue Type")
        
        cycle_data = [["Issue Type", "Count", "Average", "Top 1%", "Bottom 1%", "Std Deviation"]]
        
        for issue_type, items in self.state.cycle_time_per_type.items():
            values = numpy.array([item[1] for item in items])
            cycle_data.append([
                issue_type,
                len(items),
                seconds_to_pretty(float(numpy.mean(values))),
                seconds_to_pretty(float(numpy.percentile(values, 99))),
                seconds_to_pretty(float(numpy.percentile(values, 1))),
                seconds_to_pretty(float(numpy.std(values)))
            ])
        
        return self._write_data_table(ws, row, cycle_data)

    def _write_cycle_time_by_sp_section(self, ws: Worksheet, row: int) -> int:
        """Write cycle time by story points section"""
        row = self._write_section_header(ws, row, "Average Cycle Time by Story Points")
        
        sp_data = [["Story Points", "Count", "Average", "Std Deviation"]]
        sorted_sp_keys = sorted(self.state.cycle_time_per_sp.keys(), 
                               key=lambda x: float('inf') if x == -1 else x)
        
        for sp_key in sorted_sp_keys:
            items = self.state.cycle_time_per_sp[sp_key]
            values = numpy.array([item[1] for item in items])
            sp_display = f"{sp_key} SPs" if sp_key != -1 else "No SPs"
            sp_data.append([
                sp_display,
                len(items),
                seconds_to_pretty(float(numpy.mean(values))),
                seconds_to_pretty(float(numpy.std(values)))
            ])
        
        return self._write_data_table(ws, row, sp_data)

    def _write_aging_section(self, ws: Worksheet, row: int) -> int:
        """Write work item aging section"""
        row = self._write_section_header(ws, row, "Work Item Aging")
        
        if not self.state.aging_items:
            ws[f'A{row}'] = "No items currently in progress"
            ws[f'A{row}'].font = Font(italic=True)
            return row + 1
        
        aged_items = [item for item in self.state.aging_items if item['is_aged']]
        
        if not aged_items:
            ws[f'A{row}'] = f"No aged items found ({len(self.state.aging_items)} items in progress)"
            ws[f'A{row}'].font = Font(italic=True)
            return row + 1
        
        aging_data = [["Issue Key", "Type", "Days In Progress", "Threshold", "Status"]]
        
        for item in sorted(aged_items, key=lambda x: x['days'], reverse=True):
            threshold = AGING_THRESHOLDS.get(item['type'], 14)
            aging_data.append([
                item['key'],
                item['type'],
                f"{item['days']:.1f}",
                threshold,
                StatusLabel.AGED if item['is_aged'] else StatusLabel.OK
            ])
        
        return self._write_data_table(ws, row, aging_data, apply_status_coloring=True)

    def _create_monthly_sheet(self, month_key: str) -> None:
        """Create a sheet for a specific month"""
        ws = self.workbook.create_sheet(month_key)
        metrics = self.state.monthly_metrics[month_key]
        
        row = self._write_title(ws, f"Performance Metrics - {month_key}")
        row = self._write_commitment_delivery_section(
            ws, row,
            metrics['delivered'], metrics['carryover'],
            metrics['delivered_sp'], metrics['carryover_sp'],
            show_total_label=False
        )
        row += 1
        row = self._write_rework_ratio_section(ws, row, metrics['effort_per_type'])
        
        self._autosize_columns(ws)

    def _write_title(self, ws: Worksheet, title: str) -> int:
        """Write a sheet title and return next row"""
        row = 1
        ws.merge_cells(f'A{row}:D{row}')
        cell = ws[f'A{row}']
        cell.value = title
        cell.font = Font(bold=True, size=14)
        cell.alignment = Alignment(horizontal='center')
        return row + 2

    def _calculate_ratios(self, delivered: int, carryover: int, 
                         delivered_sp: float, carryover_sp: float) -> Tuple[float, float]:
        """Calculate commitment vs delivery ratios"""
        total_issues = delivered + carryover
        total_sp = delivered_sp + carryover_sp
        ratio_issue = (delivered / total_issues * 100) if total_issues > 0 else 0
        ratio_sp = (delivered_sp / total_sp * 100) if total_sp > 0 else 0
        return ratio_issue, ratio_sp

    def _write_commitment_delivery_section(self, ws: Worksheet, row: int, delivered: int, carryover: int,
                                          delivered_sp: float, carryover_sp: float,
                                          show_total_label: bool = False) -> int:
        """Write commitment vs delivery section (reusable for overall and monthly)"""
        row = self._write_section_header(ws, row, "Commitment vs Delivery")
        
        total_issues = delivered + carryover
        total_sp = delivered_sp + carryover_sp
        ratio_issue, ratio_sp = self._calculate_ratios(delivered, carryover, delivered_sp, carryover_sp)
        
        total_label = "Total Valid Issues" if show_total_label else "Total Issues"
        
        data = [
            ["Metric", "Value", "Percentage", "Status"],
            [total_label, total_issues, "", ""],
            ["Delivered Issues", delivered, f"{ratio_issue:.2f}%", self._get_status(ratio_issue)],
            ["Carryover Issues", carryover, f"{100-ratio_issue:.2f}%", ""],
            ["Total Story Points", total_sp, "", ""],
            ["Delivered Story Points", delivered_sp, f"{ratio_sp:.2f}%", self._get_status(ratio_sp)],
            ["Carryover Story Points", carryover_sp, f"{100-ratio_sp:.2f}%", ""],
        ]
        
        return self._write_data_table(ws, row, data, apply_status_coloring=True)

    def _calculate_rework_metrics(self, effort_per_type: dict) -> Tuple[float, float, float]:
        """Calculate rework ratio and related metrics"""
        defect_effort = effort_per_type.get("Defect", 0) + effort_per_type.get("Bug", 0)
        story_effort = effort_per_type.get("Story", 0)
        total_effort = defect_effort + story_effort
        return defect_effort, story_effort, total_effort

    def _write_rework_ratio_section(self, ws: Worksheet, row: int, effort_per_type: dict, 
                                    title: str = "Rework Ratio") -> int:
        """Write rework ratio section (reusable for overall and monthly)"""
        row = self._write_section_header(ws, row, title)
        
        defect_effort, story_effort, total_effort = self._calculate_rework_metrics(effort_per_type)
        
        if total_effort > 0:
            rework_ratio = (defect_effort / total_effort) * 100
            rework_data = [
                ["Metric", "Time (seconds)", "Percentage", "Status"],
                ["Fixing Time (Defects + Bugs)", defect_effort, f"{rework_ratio:.2f}%", 
                 self._get_rework_status(rework_ratio)],
                ["Building Time (Stories)", story_effort, f"{100-rework_ratio:.2f}%", ""],
                ["Total Time", total_effort, "100.00%", ""],
            ]
        else:
            rework_data = [
                ["Metric", "Value"],
                ["Status", "No data available"],
            ]
        
        return self._write_data_table(ws, row, rework_data, apply_status_coloring=True)

    def _write_section_header(self, ws: Worksheet, row: int, title: str) -> int:
        """Write a section header and return next row"""
        ws.merge_cells(f'A{row}:D{row}')
        cell = ws[f'A{row}']
        cell.value = title
        cell.font = self.subheader_font
        cell.fill = self.subheader_fill
        cell.alignment = Alignment(horizontal='left')
        return row + 1

    def _write_data_table(self, ws: Worksheet, start_row: int, data: list[list], apply_status_coloring: bool = False) -> int:
        """Write a data table with headers and return next available row"""
        for row_idx, row_data in enumerate(data):
            current_row = start_row + row_idx
            
            for col_idx, value in enumerate(row_data):
                col_letter = get_column_letter(col_idx + 1)
                cell = ws[f'{col_letter}{current_row}']
                cell.value = value
                cell.border = self.border
                cell.alignment = Alignment(horizontal='left', vertical='center')
                
                # Header row styling
                if row_idx == 0:
                    cell.font = self.header_font
                    cell.fill = self.header_fill
                
                # Apply status coloring if enabled
                if apply_status_coloring and row_idx > 0 and col_idx == len(row_data) - 1:
                    if value == StatusLabel.GOOD:
                        cell.fill = self.good_fill
                    elif value == StatusLabel.WARNING:
                        cell.fill = self.warning_fill
                    elif value in (StatusLabel.POOR, StatusLabel.AGED):
                        cell.fill = self.bad_fill
        
        return start_row + len(data)

    def _get_status(self, percentage: float) -> StatusLabel:
        """Get status label based on percentage (for commitment/delivery)"""
        if percentage >= PerformanceThreshold.GOOD:
            return StatusLabel.GOOD
        elif percentage >= PerformanceThreshold.WARNING:
            return StatusLabel.WARNING
        else:
            return StatusLabel.POOR

    def _get_rework_status(self, percentage: float) -> StatusLabel:
        """Get status label for rework percentage (inverted - lower is better)"""
        if percentage >= ReworkThreshold.POOR:
            return StatusLabel.POOR
        elif percentage >= ReworkThreshold.WARNING:
            return StatusLabel.WARNING
        else:
            return StatusLabel.GOOD

    def _trend_to_text(self, slope: float, threshold: float = TrendThreshold.COMMITMENT_DELIVERY) -> str:
        """Convert trend slope to text description"""
        if slope > threshold:
            return TrendLabel.IMPROVING.value
        elif slope < -threshold:
            return TrendLabel.DECLINING.value
        else:
            return TrendLabel.STABLE.value

    def _trend_to_status(self, slope: float, threshold: float = TrendThreshold.COMMITMENT_DELIVERY) -> StatusLabel:
        """Convert trend slope to status for coloring"""
        if slope > threshold:
            return StatusLabel.GOOD
        elif slope < -threshold:
            return StatusLabel.POOR
        else:
            return StatusLabel.WARNING

    def _autosize_columns(self, ws: Worksheet) -> None:
        """Auto-size all columns based on content"""
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column or 1)
            
            for cell in column:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
