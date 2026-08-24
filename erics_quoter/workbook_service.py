"""Generate quote workbooks while preserving the supplied Excel templates."""

from __future__ import annotations

import os
import re
import sys
from copy import copy, deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

from .models import LocationSpec, QuoteMode, QuoteRequest

MULTI_LOCATION_TEMPLATE = Path("Costing sheets") / "Costing Sheet Multiple Location.2026.xlsx"
MULTI_YEAR_TEMPLATE = Path("Costing sheets") / "Costing Sheet.template 2026.xlsx"
MAX_LOCATIONS = 6
MAX_CONTRACT_YEARS = 5
MAX_INPUT_CHARACTERS = 500
OPTION_ROW_COUNT = 6
OPTION_INSERT_AT = 32
OPTION_INSERT_COUNT = 4
ILLEGAL_EXCEL_TEXT = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]")
CELL_REFERENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_!.])(?P<column>\$?[A-Z]{1,3})(?P<absolute_row>\$?)(?P<row>\d+)"
    r"(?![A-Za-z0-9_]|\s*\()"
)


class WorkbookGenerationError(RuntimeError):
    """Raised when a user request cannot produce a safe workbook."""


def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def generate_quote(request: QuoteRequest) -> Path:
    normalized = _validate_request(request)
    output_directory = normalized.output_directory.expanduser().resolve()
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkbookGenerationError(f"Could not use the output folder: {exc}") from exc

    template_name = (
        MULTI_LOCATION_TEMPLATE
        if normalized.mode is QuoteMode.MULTI_LOCATION
        else MULTI_YEAR_TEMPLATE
    )
    template_path = resource_root() / template_name
    if not template_path.is_file():
        raise WorkbookGenerationError(f"Template not found: {template_path}")

    workbook = None
    temp_path: Path | None = None
    destination: Path | None = None
    committed = False
    try:
        workbook = load_workbook(template_path, data_only=False, keep_links=True)
        if normalized.mode is QuoteMode.MULTI_LOCATION:
            _prepare_multi_location(workbook, normalized)
        else:
            _prepare_multi_year(workbook, normalized)

        _sanitize_workbook_metadata(workbook)
        _request_full_recalculation(workbook)
        with NamedTemporaryFile(
            prefix="erics-quoter-",
            suffix=".xlsx",
            dir=output_directory,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        workbook.save(temp_path)
        destination = _unique_destination(normalized, output_directory)
        temp_path.replace(destination)
        committed = True
    except Exception as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if destination is not None and not committed:
            try:
                if destination.stat().st_size == 0:
                    destination.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, WorkbookGenerationError):
            raise
        raise WorkbookGenerationError(f"Could not create the workbook: {exc}") from exc
    finally:
        if workbook is not None:
            workbook.close()

    if destination is None:
        raise WorkbookGenerationError("Could not reserve a destination workbook name.")
    return destination


def _validate_request(request: QuoteRequest) -> QuoteRequest:
    if not isinstance(request.mode, QuoteMode):
        raise WorkbookGenerationError("Choose a valid quote mode.")

    customer = _validated_text(request.customer_name, "customer name", required=True)
    project = _validated_text(request.project_scope, "project description")

    try:
        raw_locations = tuple(request.locations)
    except TypeError as exc:
        raise WorkbookGenerationError("Locations must be a list of location entries.") from exc

    locations: list[LocationSpec] = []
    for location in raw_locations:
        if not isinstance(location, LocationSpec):
            raise WorkbookGenerationError("Every location must be a valid location entry.")
        locations.append(
            LocationSpec(
                _validated_text(location.name, "location name", required=True),
                bool(location.optional),
            )
        )
    normalized_locations = tuple(locations)
    if request.mode is QuoteMode.MULTI_LOCATION:
        if not 1 <= len(normalized_locations) <= MAX_LOCATIONS:
            raise WorkbookGenerationError("Choose between 1 and 6 locations.")
    else:
        if isinstance(request.contract_years, bool) or not isinstance(
            request.contract_years, int
        ):
            raise WorkbookGenerationError("Contract years must be a whole number.")
        if not 1 <= request.contract_years <= MAX_CONTRACT_YEARS:
            raise WorkbookGenerationError("Choose between 1 and 5 contract years.")

    try:
        output_directory = Path(request.output_directory)
    except TypeError as exc:
        raise WorkbookGenerationError("Choose a valid output folder.") from exc

    return QuoteRequest(
        mode=request.mode,
        customer_name=customer,
        project_scope=project,
        locations=normalized_locations,
        contract_years=request.contract_years,
        output_directory=output_directory,
    )


def _validated_text(value: object, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise WorkbookGenerationError(f"Enter a valid {label}.")
    normalized = value.strip()
    if required and not normalized:
        if label == "customer name":
            raise WorkbookGenerationError("Enter a customer name.")
        raise WorkbookGenerationError("Every location needs a name.")
    if len(normalized) > MAX_INPUT_CHARACTERS:
        raise WorkbookGenerationError(
            f"Keep the {label} to {MAX_INPUT_CHARACTERS} characters or fewer."
        )
    if ILLEGAL_EXCEL_TEXT.search(normalized):
        raise WorkbookGenerationError(f"The {label} contains an unsupported character.")
    return normalized


def _prepare_multi_year(workbook, request: QuoteRequest) -> None:
    title = _customer_title(request)
    for sheet_name in ("Pricing", "Multi Year Contract Pricing"):
        worksheet = workbook[sheet_name]
        _set_title_cell(worksheet, title)

    pricing = workbook["Pricing"]
    multi_year = workbook["Multi Year Contract Pricing"]
    pricing["R27"] = "=IFERROR((N27+H27)/P27,0)"
    pricing["R37"] = "=IFERROR(M37/P37,0)"
    pricing["R51"] = "=IFERROR(M51/P51,0)"
    if request.contract_years == 1:
        pricing.sheet_state = "visible"
        multi_year.sheet_state = "hidden"
        pricing.print_area = "A1:P65"
        pricing.sheet_properties.pageSetUpPr.fitToPage = True
        pricing.page_setup.fitToWidth = 1
        pricing.page_setup.fitToHeight = 1
        _select_only(workbook, pricing)
        return

    pricing.sheet_state = "hidden"
    multi_year.sheet_state = "visible"
    year_columns = ("P", "Q", "R", "S", "T")
    for year_number, column in enumerate(year_columns, start=1):
        multi_year.column_dimensions[column].hidden = year_number > request.contract_years

    last_year_column = year_columns[request.contract_years - 1]
    for row in (69, 71, 73, 75, 77, 78, 79):
        multi_year[f"V{row}"] = f"=SUM(P{row}:{last_year_column}{row})"

    multi_year.print_area = "A1:V80"
    multi_year.sheet_properties.pageSetUpPr.fitToPage = True
    multi_year.page_setup.orientation = "landscape"
    multi_year.page_setup.fitToWidth = 1
    multi_year.page_setup.fitToHeight = 1
    _select_only(workbook, multi_year)


def _prepare_multi_location(workbook, request: QuoteRequest) -> None:
    summary = workbook["Cost Summary"]
    _set_title_cell(summary, _customer_title(request))
    _expand_optional_summary_rows(summary)

    required_specs = [location for location in request.locations if not location.optional]
    optional_specs = [location for location in request.locations if location.optional]

    required_sheets = [workbook[f"Location {index}"] for index in range(1, 7)]
    required_totals = ["P53", "P55", "P73", "P73", "P73", "P73"]
    required_subcontractors = ["P37", "P33", "P36", "P36", "P36", "P36"]
    required_materials = ["P42", "P44", "P62", "P62", "P62", "P62"]

    active_required: list[tuple[object, str, str, str]] = []
    for index, worksheet in enumerate(required_sheets):
        if index < len(required_specs):
            spec = required_specs[index]
            worksheet.sheet_state = "visible"
            _set_location_name(worksheet, spec.name)
            active_required.append(
                (
                    worksheet,
                    required_totals[index],
                    required_subcontractors[index],
                    required_materials[index],
                )
            )
        else:
            worksheet.sheet_state = "hidden"

    option_template = workbook["Option 1"]
    option_sheets = [option_template]
    for option_index in range(2, len(optional_specs) + 1):
        clone = workbook.copy_worksheet(option_template)
        clone.title = f"Option {option_index}"
        clone.data_validations = deepcopy(option_template.data_validations)
        clone.print_area = "A1:P62"
        option_sheets.append(clone)

    active_options: list[object] = []
    for index, worksheet in enumerate(option_sheets):
        if index < len(optional_specs):
            worksheet.sheet_state = "visible"
            _set_location_name(worksheet, optional_specs[index].name)
            active_options.append(worksheet)
        else:
            worksheet.sheet_state = "hidden"
    if not optional_specs:
        option_template.sheet_state = "hidden"

    _populate_required_summary(summary, active_required)
    _populate_optional_summary(summary, active_options)
    _repair_summary_totals(summary)

    subcontractor_references = [
        f"'{worksheet.title}'!{subtotal}"
        for worksheet, _, subtotal, _ in active_required
    ] + [f"'{worksheet.title}'!P36" for worksheet in active_options]
    material_references = [
        f"'{worksheet.title}'!{subtotal}"
        for worksheet, _, _, subtotal in active_required
    ] + [f"'{worksheet.title}'!P62" for worksheet in active_options]
    summary["G9"] = _sum_formula(subcontractor_references)
    summary["G10"] = _sum_formula(material_references)

    summary.print_area = "A1:J36"
    summary.sheet_properties.pageSetUpPr.fitToPage = True
    summary.page_setup.fitToWidth = 1
    summary.page_setup.fitToHeight = 1
    summary.sheet_state = "visible"
    _select_only(workbook, summary)


def _expand_optional_summary_rows(worksheet) -> None:
    formula_cells = [
        (cell.column, cell.row, cell.value)
        for row in worksheet.iter_rows()
        for cell in row
        if cell.data_type == "f"
    ]
    shifted_row_dimensions = {
        row_index: copy(dimension)
        for row_index, dimension in worksheet.row_dimensions.items()
        if row_index >= OPTION_INSERT_AT
    }
    for row_index in shifted_row_dimensions:
        del worksheet.row_dimensions[row_index]

    affected_ranges: list[tuple[int, int, int, int]] = []
    for merged_range in list(worksheet.merged_cells.ranges):
        if merged_range.max_row >= OPTION_INSERT_AT:
            affected_ranges.append(
                (
                    merged_range.min_row,
                    merged_range.max_row,
                    merged_range.min_col,
                    merged_range.max_col,
                )
            )
            worksheet.unmerge_cells(str(merged_range))

    worksheet.insert_rows(OPTION_INSERT_AT, amount=OPTION_INSERT_COUNT)

    for column, original_row, formula in formula_cells:
        target_row = (
            original_row + OPTION_INSERT_COUNT
            if original_row >= OPTION_INSERT_AT
            else original_row
        )
        worksheet.cell(target_row, column).value = _shift_formula_rows(
            formula,
            OPTION_INSERT_AT,
            OPTION_INSERT_COUNT,
        )

    for original_row, dimension in shifted_row_dimensions.items():
        target_row = original_row + OPTION_INSERT_COUNT
        dimension.index = target_row
        worksheet.row_dimensions[target_row] = dimension

    _shift_data_validation_rows(
        worksheet,
        OPTION_INSERT_AT,
        OPTION_INSERT_COUNT,
    )

    for min_row, max_row, min_col, max_col in affected_ranges:
        if min_row >= OPTION_INSERT_AT:
            min_row += OPTION_INSERT_COUNT
        max_row += OPTION_INSERT_COUNT
        worksheet.merge_cells(
            start_row=min_row,
            end_row=max_row,
            start_column=min_col,
            end_column=max_col,
        )

    source_row = 31
    for target_row in range(OPTION_INSERT_AT, OPTION_INSERT_AT + OPTION_INSERT_COUNT):
        worksheet.row_dimensions[target_row].height = worksheet.row_dimensions[source_row].height
        for column in range(1, 11):
            source = worksheet.cell(source_row, column)
            target = worksheet.cell(target_row, column)
            target._style = copy(source._style)
            if source.has_style:
                target.number_format = source.number_format
            target.alignment = copy(source.alignment)
            target.protection = copy(source.protection)


def _populate_required_summary(worksheet, active_required) -> None:
    for index, row in enumerate(range(21, 27)):
        for column in (1, 2, 3, 4, 5, 7):
            worksheet.cell(row, column).value = None
        worksheet[f"F{row}"] = f"=C{row}*D{row}*E{row}"
        worksheet[f"H{row}"] = f"=(F{row}*G{row})"
        worksheet[f"I{row}"] = 1
        worksheet[f"J{row}"] = f"=H{row}/I{row}"

        if index < len(active_required):
            location_sheet, total_cell, _, _ = active_required[index]
            worksheet[f"A{row}"] = index + 1
            worksheet[f"B{row}"] = f"='{location_sheet.title}'!R1"
            worksheet[f"C{row}"] = 1
            worksheet[f"D{row}"] = 1
            worksheet[f"E{row}"] = 1
            worksheet[f"G{row}"] = f"='{location_sheet.title}'!{total_cell}"

    worksheet["H27"] = "=SUM(H21:H26)"
    worksheet["J27"] = "=SUM(J21:J26)"


def _populate_optional_summary(worksheet, option_sheets) -> None:
    for index, row in enumerate(range(30, 30 + OPTION_ROW_COUNT)):
        worksheet.row_dimensions[row].hidden = index >= len(option_sheets)
        for column in (1, 2, 3, 4, 5, 7):
            worksheet.cell(row, column).value = None
        worksheet[f"F{row}"] = f"=C{row}*D{row}*E{row}"
        worksheet[f"H{row}"] = f"=F{row}*G{row}"
        worksheet[f"I{row}"] = 1
        worksheet[f"J{row}"] = f"=H{row}/I{row}"

        if index < len(option_sheets):
            option_sheet = option_sheets[index]
            worksheet[f"A{row}"] = index + 1
            worksheet[f"B{row}"] = f"='{option_sheet.title}'!R1"
            worksheet[f"C{row}"] = 1
            worksheet[f"D{row}"] = 1
            worksheet[f"E{row}"] = 1
            worksheet[f"G{row}"] = f"='{option_sheet.title}'!P73"

    worksheet["H36"] = "=SUM(H30:H35)"
    worksheet["J36"] = "=SUM(J30:J35)"


def _repair_summary_totals(worksheet) -> None:
    worksheet["A27"] = "Subtotal Required Locations"
    worksheet["B29"] = "Optional Location"
    worksheet["A36"] = "Subtotal Optional Locations"
    worksheet["G7"] = "=J6+J8+J9+J10+J11+J12+J16+J27+J36"
    worksheet["J39"] = "=J18+J27"
    worksheet["J47"] = "=(J36)"
    worksheet["J49"] = "=J39+J41+J43+J45+J47"
    worksheet["J50"] = "=J49*0.13"
    worksheet["J51"] = "=J49+J50"
    worksheet["J52"] = "=J49*1.13"
    worksheet["J57"] = "=J49"


def _shift_formula_rows(formula: str, insertion_row: int, amount: int) -> str:
    """Apply Excel-style structural row insertion to local A1 references."""

    def replace_reference(match: re.Match[str]) -> str:
        row = int(match.group("row"))
        if row < insertion_row:
            return match.group(0)
        return (
            f"{match.group('column')}{match.group('absolute_row')}"
            f"{row + amount}"
        )

    return CELL_REFERENCE_PATTERN.sub(replace_reference, formula)


def _shift_data_validation_rows(worksheet, insertion_row: int, amount: int) -> None:
    for validation in worksheet.data_validations.dataValidation:
        shifted_ranges: list[str] = []
        for cell_range in validation.ranges.ranges:
            min_column = get_column_letter(cell_range.min_col)
            max_column = get_column_letter(cell_range.max_col)
            min_row = cell_range.min_row
            max_row = cell_range.max_row
            if min_row >= insertion_row:
                min_row += amount
                max_row += amount
            elif max_row >= insertion_row:
                max_row += amount
            shifted_ranges.append(
                f"{min_column}{min_row}:"
                f"{max_column}{max_row}"
                if (
                    cell_range.min_col != cell_range.max_col
                    or min_row != max_row
                )
                else f"{min_column}{min_row}"
            )
        validation.sqref = " ".join(shifted_ranges)
        if isinstance(validation.formula1, str) and validation.formula1.startswith("="):
            validation.formula1 = _shift_formula_rows(
                validation.formula1,
                insertion_row,
                amount,
            )


def _set_location_name(worksheet, name: str) -> None:
    _set_title_cell(worksheet, name)
    _set_literal_text(worksheet["R1"], name)


def _set_title_cell(worksheet, title: str) -> None:
    cell = worksheet["A1"]
    if isinstance(cell, MergedCell):
        raise WorkbookGenerationError(f"Cannot update the title on {worksheet.title}.")
    _set_literal_text(cell, title)
    alignment = copy(cell.alignment)
    alignment.wrap_text = True
    alignment.shrink_to_fit = True
    cell.alignment = alignment


def _set_literal_text(cell, value: str) -> None:
    """Store user-controlled text without letting Excel interpret it as a formula."""
    cell.value = value
    cell.data_type = "s"


def _customer_title(request: QuoteRequest) -> str:
    details = request.customer_name
    if request.project_scope:
        details = f"{details} | {request.project_scope}"
    return f"Customer and Project Scope - {details}"


def _sum_formula(references: list[str]) -> str:
    if not references:
        return "=0"
    return f"=SUM({','.join(references)})"


def _request_full_recalculation(workbook) -> None:
    workbook.calculation.calcMode = "auto"
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True


def _sanitize_workbook_metadata(workbook) -> None:
    """Remove personal source-template metadata from every generated workbook."""
    workbook.properties.creator = "GDI Ainsworth"
    workbook.properties.lastModifiedBy = "GDI Ainsworth"
    workbook.properties.lastPrinted = None


def _select_only(workbook, selected_worksheet) -> None:
    """Prevent source-template tab grouping from leaking into generated files."""
    for worksheet in workbook.worksheets:
        worksheet.sheet_view.tabSelected = False
    selected_worksheet.sheet_view.tabSelected = True
    selected_index = workbook.sheetnames.index(selected_worksheet.title)
    workbook.active = selected_index
    if workbook.views:
        workbook.views[0].activeTab = selected_index


def _unique_destination(request: QuoteRequest, output_directory: Path) -> Path:
    if request.mode is QuoteMode.MULTI_LOCATION:
        mode_name = "Multi Location"
    elif request.contract_years == 1:
        mode_name = "Pricing"
    else:
        mode_name = f"{request.contract_years} Year Contract"
    project_part = f" - {request.project_scope}" if request.project_scope else ""
    base = _safe_filename(f"{request.customer_name}{project_part} - {mode_name}")
    candidate = output_directory / f"{base}.xlsx"
    suffix = 2
    while True:
        try:
            descriptor = os.open(
                candidate,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            candidate = output_directory / f"{base} ({suffix}).xlsx"
            suffix += 1
            continue
        os.close(descriptor)
        return candidate


def _safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:150] or "Quote"
