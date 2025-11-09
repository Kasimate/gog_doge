import csv
from pathlib import Path
from typing import List, Dict, Any, Union

class CsvExportError(Exception):
    """Custom exception for CSV export failures."""
    pass

def export_to_csv(data: List[Dict[str, Any]], filepath: Union[str, Path]) -> None:
    """
    Exports a list of dictionaries to a CSV file.

    The CSV headers are derived from the keys of the first dictionary in the list.

    Args:
        data: A list of dictionaries to be written to the CSV file.
        filepath: The path to the output CSV file.

    Raises:
        CsvExportError: If the data list is empty, as headers cannot be determined.
        IOError: If there's an issue writing to the file.
    """
    if not data:
        raise CsvExportError("Cannot export empty data list to CSV.")

    path_obj = Path(filepath)

    # Ensure the parent directory exists
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Get headers from the first item's keys
    headers = list(data[0].keys())

    try:
        with open(path_obj, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
    except IOError as e:
        raise IOError(f"Failed to write to CSV file at {path_obj}: {e}") from e
