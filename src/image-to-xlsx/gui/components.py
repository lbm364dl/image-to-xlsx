"""UI component builders for the table extraction app.

Each function builds a section of the UI. Functions that need per-session
state receive a Session instance as their first parameter.
"""

import re

from nicegui import ui

MAX_WIDTH = 650


# ---------------------------------------------------------------------------
# Utility helpers (no UI, no state)
# ---------------------------------------------------------------------------


def validate_page_range(value):
    """Validate a page range string like '1,2-5,7-9'."""
    value = value.replace(" ", "").strip()
    return bool(re.match(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$", value))


# ---------------------------------------------------------------------------
# Stateless UI components
# ---------------------------------------------------------------------------


def page_header():
    ui.label("Table extraction tool").classes("text-[24px]")
    ui.label("Extract data tables from PDFs/images to Excel sheets").classes(
        "text-[16px]"
    )


def methods_explanation():
    ui.label("Methods:")
    with ui.list().classes(f"w-[{MAX_WIDTH}px]").props("separator"):
        ui.item(
            "Surya OCR: uses free open source AI models (surya-ocr) for table "
            "structure recognition and text extraction."
        )
        ui.item(
            "PaddleOCR-VL 1.5: uses the PaddleOCR Vision-Language model for "
            "document parsing and table extraction. Supports 109 languages."
        )
        ui.item(
            "GLM-OCR: uses the GLM-OCR multimodal model for document parsing "
            "and table extraction. Excellent at complex tables, formulas, and "
            "multilingual documents."
        )
        ui.item(
            "PDF text: uses information stored in the PDF directly. Only use "
            "if your PDF has embedded/selectable text."
        )


# ---------------------------------------------------------------------------
# Stateful UI components (receive Session)
# ---------------------------------------------------------------------------


def method_selector(session):
    """Build the extraction method dropdown."""
    return ui.select(
        {
            "surya": "Surya OCR (free open source)",
            "paddleocr-vl": "PaddleOCR-VL 1.5 (free open source)",
            "glm-ocr": "GLM-OCR (API-based)",
            "pdf-text": "No OCR, use text in PDF",
        },
        label="Extraction method",
        value=session.options.get("method", "surya"),
        on_change=lambda e: session.toggle_option(e, "method"),
    ).classes("w-full")


def option_checkboxes(method_option, session):
    """Build the options panel with all checkboxes and selectors."""
    with ui.column().classes(f"w-[{MAX_WIDTH}px]"):
        ui.label("Other options")

        ui.checkbox(
            "Try to fix image rotation (can be very slow for large inputs)",
            on_change=lambda e: session.toggle_option(e, "unskew"),
            value=session.options.get("unskew", False),
        ).bind_visibility_from(
            method_option,
            "value",
            lambda v: v not in ("pdf-text", "paddleocr-vl", "glm-ocr"),
        )

        ui.checkbox(
            "Dewarp document image before extraction (uses GeoTr AI model, "
            "recommended for photos of curved/folded pages). "
            "Dewarped images are saved in the results zip.",
            on_change=lambda e: session.toggle_option(e, "dewarp"),
            value=session.options.get("dewarp", False),
        ).bind_visibility_from(
            method_option, "value", lambda v: v not in ("pdf-text",)
        )

        ui.checkbox(
            "Create one row for each text detected inside a cell instead of "
            "joining with a space. Only try this if adjacent rows are mixed "
            "into a single row by mistake.",
            on_change=lambda e: session.toggle_option(e, "extend_rows"),
            value=session.options.get("extend_rows", False),
        )

        ui.checkbox(
            "Force substitution of common wrongly detected digits as letters, "
            "e.g., change I to 1, b to 6, O to 0, etc...",
            on_change=lambda e: session.toggle_option(e, "fix_num_misspellings"),
            value=session.options.get("fix_num_misspellings", True),
        )
        remove_dots_and_commas = ui.checkbox(
            "Remove all commas and dots from cells. Try this if the OCR "
            "scanning struggles differentiating between commas and dots "
            "and/or you want a fixed number of decimal places.",
            on_change=lambda e: session.toggle_option(e, "remove_dots_and_commas"),
            value=session.options.get("remove_dots_and_commas", False),
        )
        with ui.row(align_items="center").bind_visibility_from(
            remove_dots_and_commas, "value"
        ):
            ui.number(
                "Decimal places",
                placeholder="0",
                on_change=lambda e: session.toggle_option(e, "fixed_decimal_places"),
                precision=0,
                min=0,
            )
            ui.label(
                "Forcefully write a decimal point this number of places to "
                "the left of the last digit in numeric cells."
            ).classes("w-1/2")

        with ui.column().bind_visibility_from(
            remove_dots_and_commas, "value", lambda v: not v
        ):
            with ui.row(align_items="center"):
                ui.select(
                    {",": "Comma (,)", ".": "Dot (.)"},
                    value=session.options.get("thousands_separator", ","),
                    on_change=lambda e: session.toggle_option(
                        e, "thousands_separator"
                    ),
                ).classes("w-[20%]")
                ui.label(
                    " Thousands separator (will be ignored when trying to "
                    "convert numeric cells) "
                ).classes("w-[50%]")
            with ui.row(align_items="center"):
                ui.select(
                    {".": "Dot (.)", ",": "Comma (,)"},
                    value=session.options.get("decimal_separator", "."),
                    on_change=lambda e: session.toggle_option(
                        e, "decimal_separator"
                    ),
                ).classes("w-[20%]")
                ui.label(
                    "Decimal separator (will be used as decimal point when "
                    "trying to convert numeric cells)"
                ).classes("w-[50%]")


def file_upload_input(on_upload):
    """Build the file upload area."""
    ui.label(
        "Add files you want to process. Only PDFs and images are accepted. "
        "For images, at least PNG and JPEG should be valid. After uploading "
        "the files, you can select page ranges to process in each PDF or "
        "leave blank for all pages."
    ).classes(f"w-[{MAX_WIDTH}px]")
    return (
        ui.upload(
            label="First add files and then upload them with the upside arrow in the right.",
            multiple=True,
            on_upload=on_upload,
        )
        .props('accept="image/*,application/pdf"')
        .classes("w-full")
    )


def uploaded_files_view(file_upload, session, on_reset):
    """Build the uploaded files list with page range inputs."""
    session.uploaded_files_list = ui.column()

    for file in session.uploaded_files.values():
        if file["type"] == "application/pdf":
            add_to_uploaded_files_list(session, file["name"])

    ui.button("Clear file list", on_click=on_reset).classes("w-full")


def add_to_uploaded_files_list(session, file_name):
    """Add a file entry to the uploaded files list with page range input."""

    def set_page_ranges(event, name):
        if not validate_page_range(event.value):
            return
        page_ranges = []
        for page_range in event.value.split(","):
            page_range = page_range.split("-")
            if len(page_range) == 1:
                page_range = [page_range[0], page_range[0]]
            start, end = page_range
            page_ranges.append((int(start), int(end)))
        session.uploaded_files_pages[name] = page_ranges

    with session.uploaded_files_list:
        with ui.row(align_items="center"):
            ui.label(file_name)
            ui.input(
                label="Pages",
                placeholder="1,2-5,7-9",
                on_change=lambda e: set_page_ranges(e, file_name),
                validation={"Wrong page range": validate_page_range},
            )


def extract_tables_button(session, on_click):
    """Build the extract button, progress indicator, and download button."""
    ui.label(
        "A zip file with the results will be downloaded, containing one "
        "folder for each input file. The output Excels will contain one "
        "sheet for each table detected in the file."
    ).classes(f"w-[{MAX_WIDTH}px]")
    ui.checkbox(
        "Include original files in output zip",
        on_change=lambda e: session.toggle_option(e, "include_input_files_in_output"),
        value=session.options.get("include_input_files_in_output"),
    )

    ui.html(
        'The cells in the output Excels have a color code. For more details see '
        '<a href="https://saco.csic.es/s/ESYzMcR9NWjWbrB" target="_blank" '
        'style="color: #1976d2; text-decoration: underline;">the legend sheet</a>.'
    ).classes(f"w-[{MAX_WIDTH}px]")

    session.extract_button = ui.button(
        "Extract tables", on_click=on_click
    ).classes("w-full")

    with ui.row(align_items="center").classes("w-full justify-center"):
        ui.spinner(size="lg").bind_visibility_from(session, "in_progress")
        session.in_progress_label = ui.label(
            "Initializing..."
        ).bind_visibility_from(session, "in_progress")

    # Download button (hidden until results are ready)
    session.download_button = (
        ui.button(
            "Download results",
            on_click=lambda: ui.download(
                session.results_zip, session.results_filename
            ),
        )
        .classes(
            "w-full shadow-md q-btn q-btn-item q-btn--flat q-btn--rectangle "
            "bg-primary text-white hover:cursor-pointer"
        )
        .style("display: none;")
    )


def set_timers(session):
    """Set up polling timers for inter-process communication."""
    ui.timer(
        0.1,
        callback=lambda: (
            session.in_progress_label.set_text(session.queue.get())
            if not session.queue.empty()
            else None
        ),
    )
    ui.timer(
        0.1,
        callback=lambda: (
            ui.notify(session.exception_queue.get(), type="negative")
            if not session.exception_queue.empty()
            else None
        ),
    )
