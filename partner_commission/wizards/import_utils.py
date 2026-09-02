# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Shared helpers to read a header-based data table (RefNo/Amount/... or
ACC ID/NAME/...) out of an uploaded xlsx or csv file, used by both import
wizards of this module."""
import csv
import datetime
import io


def to_float(value):
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\xa0", "").replace(" ", "")
    if not text:
        return 0.0
    text = text.rstrip("%")
    if "," in text and "." in text:
        text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def to_datetime(value):
    if value in (None, ""):
        return False
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text or text.startswith("0000-00-00"):
        return False
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%m/%d/%y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return False


def to_bool(value):
    text = str(value).strip().lower() if value not in (None, "") else ""
    return text in ("1", "true", "yes", "y", "да")


def _detect_delimiter(text):
    """Pick the delimiter (';', ',' or tab) most frequent on the header
    line. More robust than csv.Sniffer for our files: Sniffer needs
    several *consistent* sample lines to decide and raises "Could not
    determine delimiter" on some real exports (e.g. a short sample, or
    values containing a comma decimal separator like "3,47" confusing
    its heuristic) - whereas the header line alone, with our known
    semicolon- or comma-separated column names, is always enough."""
    header_line = text.split("\n", 1)[0]
    counts = {d: header_line.count(d) for d in (";", ",", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def build_col_map(header_row, known_headers):
    """Return {header name: column index} for the headers we recognize,
    matched by exact (stripped) name."""
    col_map = {}
    for idx, cell in enumerate(header_row):
        name = cell.strip() if isinstance(cell, str) else cell
        if name in known_headers:
            col_map[name] = idx
    return col_map


def read_rows_xlsx(data, known_headers):
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "The 'openpyxl' Python library is required to import xlsx files."
        ) from exc
    workbook = openpyxl.load_workbook(
        io.BytesIO(data), data_only=True, read_only=True
    )
    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], {}
    col_map = build_col_map(header_row, known_headers)
    rows = []
    for raw_row in rows_iter:
        row = {
            header: raw_row[idx] if idx < len(raw_row) else None
            for header, idx in col_map.items()
        }
        if any(v not in (None, "") for v in row.values()):
            rows.append(row)
    return rows, col_map


def read_rows_csv(data, known_headers):
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode the CSV file.")
    reader = csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text))
    try:
        header_row = next(reader)
    except StopIteration:
        return [], {}
    col_map = build_col_map(header_row, known_headers)
    rows = []
    for raw_row in reader:
        if not any((cell or "").strip() for cell in raw_row):
            continue
        row = {
            header: raw_row[idx] if idx < len(raw_row) else None
            for header, idx in col_map.items()
        }
        rows.append(row)
    return rows, col_map


def read_rows(filename, data, known_headers):
    """Dispatch to the xlsx or csv reader based on the file extension.
    Returns (rows, col_map) like read_rows_xlsx/read_rows_csv."""
    lower_name = (filename or "").lower()
    if lower_name.endswith(".xlsx") or lower_name.endswith(".xlsm"):
        return read_rows_xlsx(data, known_headers)
    if lower_name.endswith(".csv"):
        return read_rows_csv(data, known_headers)
    raise ValueError("Unsupported file type. Use .xlsx or .csv.")
