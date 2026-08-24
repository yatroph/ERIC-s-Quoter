from __future__ import annotations

from openpyxl import load_workbook

from erics_quoter.models import LocationSpec, QuoteMode, QuoteRequest
from erics_quoter.workbook_service import _shift_formula_rows, generate_quote


def test_structural_formula_shift_only_moves_local_references():
    formula = "=SUM(A31,A32,'Other sheet'!P36,$K$70,LOG10(A1))"

    assert _shift_formula_rows(formula, insertion_row=32, amount=4) == (
        "=SUM(A31,A36,'Other sheet'!P36,$K$74,LOG10(A1))"
    )


def test_generates_multi_year_copy_with_customer_and_full_print_area(tmp_path):
    destination = generate_quote(
        QuoteRequest(
            mode=QuoteMode.MULTI_YEAR,
            customer_name="Northwind Foods",
            project_scope="Service agreement",
            output_directory=tmp_path,
        )
    )

    assert destination.exists()
    workbook = load_workbook(destination, data_only=False)
    sheet = workbook["Multi Year Contract Pricing"]
    assert sheet["A1"].value == (
        "Customer and Project Scope - Northwind Foods | Service agreement"
    )
    assert sheet["Q8"].value == "=P8*$Q$6"
    assert sheet.print_area == "'Multi Year Contract Pricing'!$A$1:$V$80"
    assert workbook["Pricing"].sheet_state == "hidden"
    assert workbook["Pricing"]["R37"].value == "=IFERROR(M37/P37,0)"
    assert workbook["Pricing"]["R51"].value == "=IFERROR(M51/P51,0)"
    assert workbook.active.title == "Multi Year Contract Pricing"
    assert sheet.sheet_view.tabSelected is True


def test_generates_required_and_optional_location_sheets(tmp_path):
    destination = generate_quote(
        QuoteRequest(
            mode=QuoteMode.MULTI_LOCATION,
            customer_name="Contoso",
            project_scope="Plant retrofit",
            locations=(
                LocationSpec("Main plant"),
                LocationSpec("Warehouse option", optional=True),
                LocationSpec("Admin building"),
                LocationSpec("Future line", optional=True),
            ),
            output_directory=tmp_path,
        )
    )

    workbook = load_workbook(destination, data_only=False)
    summary = workbook["Cost Summary"]
    assert summary["A1"].value == "Customer and Project Scope - Contoso | Plant retrofit"
    assert workbook["Location 1"]["R1"].value == "Main plant"
    assert workbook["Location 2"]["R1"].value == "Admin building"
    assert workbook["Option 1"]["R1"].value == "Warehouse option"
    assert workbook["Option 2"]["R1"].value == "Future line"
    assert summary["B21"].value == "='Location 1'!R1"
    assert summary["B22"].value == "='Location 2'!R1"
    assert summary["B30"].value == "='Option 1'!R1"
    assert summary["B31"].value == "='Option 2'!R1"
    assert summary["J36"].value == "=SUM(J30:J35)"
    assert summary["H30"].value == "=F30*G30"
    assert summary["J49"].value == "=J39+J41+J43+J45+J47"
    assert summary["A27"].value == "Subtotal Required Locations"
    assert summary["B29"].value == "Optional Location"
    assert summary["A36"].value == "Subtotal Optional Locations"
    assert summary.print_area == "'Cost Summary'!$A$1:$J$36"
    assert workbook["Location 3"].sheet_state == "hidden"
    assert summary.sheet_view.tabSelected is True
    assert workbook["Location 1"].sheet_view.tabSelected is False
    assert summary["D65"].value == "=(C65+17)"
    assert summary["C74"].value == "=C65/$K$74"
    assert summary["I90"].value == "=I89/0.9"
    assert summary["K74"].value == 0.8
    assert str(summary.data_validations.dataValidation[0].sqref) == (
        "I6:I12 I16 K74"
    )
    assert summary.row_dimensions[64].height == 32.25
    assert summary.row_dimensions[73].height == 32.25
    assert workbook["Option 2"].print_area == "'Option 2'!$A$1:$P$62"


def test_supports_six_optional_locations_without_overwriting(tmp_path):
    request = QuoteRequest(
        mode=QuoteMode.MULTI_LOCATION,
        customer_name="Fabrikam",
        locations=tuple(
            LocationSpec(f"Optional site {index}", optional=True)
            for index in range(1, 7)
        ),
        output_directory=tmp_path,
    )

    first = generate_quote(request)
    second = generate_quote(request)
    assert first != second

    workbook = load_workbook(first, data_only=False)
    summary = workbook["Cost Summary"]
    assert workbook["Option 6"]["R1"].value == "Optional site 6"
    assert summary["B35"].value == "='Option 6'!R1"
    assert summary.row_dimensions[35].hidden is False
    assert all(workbook[f"Location {index}"].sheet_state == "hidden" for index in range(1, 7))
