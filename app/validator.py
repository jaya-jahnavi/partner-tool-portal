"""Deterministic dataset checks; never executes uploaded content."""
import csv
import io
import math
from collections import Counter

MAX_BYTES = 1_000_000
MAX_ROWS = 10_000
MAX_COLUMNS = 100
csv.field_size_limit(MAX_BYTES)

def validate_shape(content):
    if not content.strip(): raise ValueError('The CSV is empty.')
    try:
        reader = csv.reader(io.StringIO(content), strict=True)
        header = next(reader)
        if not header or len(header) > MAX_COLUMNS:
            raise ValueError('Use between 1 and 100 columns.')
        if any(not h.strip() for h in header) or len(set(header)) != len(header):
            raise ValueError('Column names must be nonempty and unique.')
        count = 0
        for row in reader:
            count += 1
            if count > MAX_ROWS: raise ValueError('The limit is 10,000 data rows.')
            if len(row) != len(header): raise ValueError(f'Row {count + 1} has an inconsistent column count.')
        if not count: raise ValueError('Include at least one data row.')
    except (csv.Error, StopIteration) as exc:
        raise ValueError('Invalid CSV format.') from exc
    return header, count

def analyze(content):
    header, count = validate_shape(content)
    rows = list(csv.DictReader(io.StringIO(content)))
    duplicates = sum(n - 1 for n in Counter(tuple(row[h] for h in header) for row in rows).values())
    columns, issues = [], []
    for key in header:
        values = [row[key].strip() for row in rows]
        missing = sum(not v for v in values)
        numbers = []
        for v in values:
            if v:
                try:
                    n = float(v)
                    if math.isfinite(n): numbers.append(n)
                except ValueError: pass
        item = {'name': key, 'missing': missing, 'unique': len(set(values) - {''}),
                'type': 'number' if numbers and len(numbers) == count - missing else 'text'}
        if item['type'] == 'number': item.update(min=min(numbers), max=max(numbers))
        columns.append(item)
        if missing: issues.append(f'{key}: {missing} missing value(s)')
    if duplicates: issues.append(f'{duplicates} duplicate row(s)')
    return {'rows': count, 'column_count': len(header), 'duplicates': duplicates,
            'missing_cells': sum(c['missing'] for c in columns),
            'verdict': 'needs_attention' if issues else 'passed', 'issues': issues, 'columns': columns}
