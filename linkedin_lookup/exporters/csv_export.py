"""Export search results to CSV or Excel."""

import csv
import os
from datetime import datetime
from linkedin_lookup.models import SearchResult


def export_csv(result: SearchResult, output_dir: str = "output", export_all: bool = False) -> str:
    """Export employees to a CSV file.

    Args:
        result: Search result with employees.
        output_dir: Directory to save the CSV file.
        export_all: If True, export ALL employees; if False, export filtered only.

    Returns the file path.
    """
    os.makedirs(output_dir, exist_ok=True)

    safe_name = "".join(c if c.isalnum() else "_" for c in result.company.name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "all" if export_all else "filtered"
    filename = f"{safe_name}_{suffix}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    employees = result.employees if export_all else result.filtered_employees

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Title", "Employer", "LinkedIn", "Location", "Has Email"])
        for emp in employees:
            writer.writerow([emp.name, emp.title, emp.employer, emp.profile_url, emp.location, emp.has_email])

    return filepath
