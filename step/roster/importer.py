"""Importing the client's roster spreadsheet without knowing its shape.

Three properties matter more than anything else here:

1. **Nothing is written until the whole sheet is understood.** An insufficient
   mapping raises before a single row is touched, so a wrong file cannot half-
   import.
2. **Re-import is idempotent.** Rows are matched through `step.identity`, the
   same resolver signup uses. Updates happen in place.
3. **Nobody is ever deleted.** A person absent from a re-import is flagged.
   Deleting would cascade away their submission history, which is the one thing
   in this system that cannot be recreated.
"""

from dataclasses import dataclass, field
from pathlib import Path

from django.core.files import File
from django.db import transaction
from openpyxl import load_workbook

from step import identity
from step.models import Educator, RosterImport, School, UnresolvedRow
from step.roster import geo
from step.roster.mapping import check_sufficiency, propose_mapping


class InsufficientMapping(Exception):
    """The sheet lacks an identity key or a geographic anchor."""


@dataclass
class ImportResult:
    created_count: int = 0
    updated_count: int = 0
    unresolved_count: int = 0
    row_count: int = 0
    mapping: dict = field(default_factory=dict)
    roster_import: RosterImport | None = None


def read_rows(path, header_row: int = 1):
    """Return (headers, [row dicts]) from the first worksheet.

    Opened read-only: the client's files are treated as read-only source
    material, matching the convention in the diagnostics extraction code.
    """
    workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    rows = []
    headers = []
    for index, raw in enumerate(sheet.iter_rows(values_only=True), start=1):
        if index < header_row:
            continue
        if index == header_row:
            headers = [h for h in raw]
            continue
        if all(cell is None or str(cell).strip() == "" for cell in raw):
            continue
        rows.append({headers[i]: raw[i] for i in range(min(len(headers), len(raw)))})
    workbook.close()
    return headers, rows


def _value(row, mapping_dict, field_name):
    for header, target in mapping_dict.items():
        if target == field_name:
            raw = row.get(header)
            return "" if raw is None else str(raw).strip()
    return ""


def _place(row, mapping_dict):
    """Return (region, district, school_name) or raise ValueError with a reason."""
    region_raw = _value(row, mapping_dict, "region")
    district_raw = _value(row, mapping_dict, "district")
    school_name = _value(row, mapping_dict, "school")

    region = geo.resolve_region(region_raw) if region_raw else None
    district = geo.resolve_district(district_raw, region) if district_raw else None

    if region is None and district is not None:
        region = district.region
    if region is None:
        if region_raw:
            raise ValueError(f"could not resolve region {region_raw!r}")
        if district_raw:
            raise ValueError(f"could not resolve district {district_raw!r}")
        raise ValueError("no region or district given")

    return region, district, school_name


@transaction.atomic
def import_file(path, *, header_row: int = 1, dry_run: bool = False, user=None) -> ImportResult:
    headers, rows = read_rows(path, header_row=header_row)
    mapping_dict = propose_mapping(headers)

    sufficient, missing = check_sufficiency(mapping_dict)
    if not sufficient:
        raise InsufficientMapping(
            "The sheet is missing " + " and ".join(missing) + f". Headers seen: {headers}"
        )

    result = ImportResult(row_count=len(rows), mapping={k: v for k, v in mapping_dict.items() if v})

    roster_import = None
    if not dry_run:
        roster_import = RosterImport(header_row=header_row, mapping=result.mapping, imported_by=user)
        # `Path(path).name` handles both a Path and a plain string uniformly.
        # A naive `str(path).split("/")[-1]` leaves the full absolute path
        # untouched on Windows (backslash-separated), which Django's storage
        # then tries to use as a filename and fails.
        with open(path, "rb") as handle:
            roster_import.file.save(Path(path).name, File(handle), save=False)
        roster_import.save()
        result.roster_import = roster_import

    seen_ids = []
    for number, row in enumerate(rows, start=header_row + 1):
        email = _value(row, mapping_dict, "email")
        passport_no = _value(row, mapping_dict, "passport_no")
        pinfl = _value(row, mapping_dict, "pinfl")

        if not any([email, passport_no, pinfl]):
            result.unresolved_count += 1
            if not dry_run:
                UnresolvedRow.objects.create(
                    roster_import=roster_import, row_number=number,
                    reason="no identity value in this row", payload=_payload(row),
                )
            continue

        try:
            region, district, school_name = _place(row, mapping_dict)
        except ValueError as exc:
            result.unresolved_count += 1
            if not dry_run:
                UnresolvedRow.objects.create(
                    roster_import=roster_import, row_number=number,
                    reason=str(exc), payload=_payload(row),
                )
            continue

        try:
            existing, _key = identity.resolve(email=email, passport_no=passport_no, pinfl=pinfl)
        except identity.AmbiguousIdentity as exc:
            result.unresolved_count += 1
            if not dry_run:
                UnresolvedRow.objects.create(
                    roster_import=roster_import, row_number=number,
                    reason=str(exc), payload=_payload(row),
                )
            continue

        if dry_run:
            if existing:
                result.updated_count += 1
            else:
                result.created_count += 1
            continue

        school = None
        if school_name:
            # district may be None here — a row can carry a school name with
            # only a region resolved, and the school must still be recorded
            # rather than silently dropped (School.district is nullable).
            school, _ = School.objects.get_or_create(name=school_name, district=district)

        defaults = {
            "full_name": _value(row, mapping_dict, "full_name") or (existing.full_name if existing else email),
            "email": email,
            "passport_no": passport_no,
            "pinfl": pinfl,
            "region": region,
            "district": district,
            "source_fields": _unmapped(row, mapping_dict),
            "missing_from_last_import": False,
        }
        if school is not None:
            defaults["school"] = school

        if existing:
            for name, value in defaults.items():
                setattr(existing, name, value)
            existing.save()
            result.updated_count += 1
            seen_ids.append(existing.pk)
        else:
            created = Educator.objects.create(**defaults)
            result.created_count += 1
            seen_ids.append(created.pk)

    if not dry_run:
        Educator.objects.exclude(pk__in=seen_ids).update(missing_from_last_import=True)
        roster_import.row_count = result.row_count
        roster_import.created_count = result.created_count
        roster_import.updated_count = result.updated_count
        roster_import.unresolved_count = result.unresolved_count
        roster_import.save()

    return result


def _payload(row):
    return {str(k): ("" if v is None else str(v)) for k, v in row.items() if k}


def _unmapped(row, mapping_dict):
    return {
        str(header): ("" if value is None else str(value))
        for header, value in row.items()
        if header and mapping_dict.get(header) is None
    }
