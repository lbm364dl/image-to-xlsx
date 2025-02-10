from nicegui import ui, run
from pathlib import Path
from definitions import INF
from multiprocessing import Manager
from io import BytesIO
from utils import save_workbook
import main
import re
import zipfile

options = {"method": "surya+paddle", "unskew": False, "show-detected-boxes": False}
manager = Manager()
uploaded_files = manager.dict()
in_progress = False
queue = manager.Queue()


def set_page_ranges(event, file_name):
    if not validate_page_range(event.value):
        return

    page_ranges = []
    for page_range in event.value.split(","):
        page_range = page_range.split("-")
        if len(page_range) == 1:
            page_range = [page_range[0], page_range[0]]
        start, end = page_range
        page_ranges.append((int(start), int(end)))

    uploaded_files[file_name] = {**uploaded_files[file_name], "pages": page_ranges}


def handle_upload(file):
    uploaded_files[file.name] = {
        "name": file.name,
        "content": file.content,
        "pages": [(1, INF)],
    }
    ui.notify(f"Uploaded {file.name}")

    if file.type == "application/pdf":
        with uploaded_files_list:
            with ui.row(align_items="center"):
                ui.label(file.name)
                ui.input(
                    label="Pages",
                    placeholder="2-5",
                    on_change=lambda e: set_page_ranges(e, file.name),
                    validation={"Wrong page range": validate_page_range},
                )


def reset_uploaded_files(file_upload):
    uploaded_files.clear()
    uploaded_files_list.clear()
    file_upload.reset()
    ui.notify("Removed all uploaded files")


def toggle_option(event, option):
    options[option] = event.value


def extract_tables():
    results = []
    for file in uploaded_files.values():
        queue.put_nowait(f"Processing file {file['name']}")
        file_content = file["content"].read()
        table_workbook, footers_workbook = main.run(
            file_content, page_ranges=file["pages"], **options
        )
        results.append({
            "table_workbook": table_workbook,
            "footers_workbook": footers_workbook,
            "name": file["name"],
            "input_content": file_content,
        })

    return results


def workbook_to_bytes(workbook):
    virtual_workbook = BytesIO()
    save_workbook(workbook, virtual_workbook)
    virtual_workbook.seek(0)
    return virtual_workbook.read()


def create_results_zip(results):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for result in results:
            name = Path(result["name"]).stem
            zipf.writestr(
                f"{name}/{name}.xlsx", workbook_to_bytes(result["table_workbook"])
            )
            zipf.writestr(
                f"{name}/footers_{name}.xlsx",
                workbook_to_bytes(result["footers_workbook"]),
            )
            zipf.writestr(
                f"{name}/{result['name']}",
                result["input_content"],
            )
    buffer.seek(0)
    return buffer.read()


async def handle_extract_tables_click():
    global in_progress
    in_progress = True
    extract_button.enabled = False
    results = await run.cpu_bound(extract_tables)
    extract_button.enabled = True
    in_progress = False
    ui.notify("Processing done. Downloading results...")
    ui.download(create_results_zip(results), "results.zip")


def validate_page_range(value):
    value = value.replace(" ", "").strip()
    return bool(re.match(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$", value))


@ui.page("/")
def index():
    with ui.column().classes("w-full h-full items-center justify-center"):
        with ui.card().classes("p-8 shadow-lg rounded-xl"):
            ui.select(
                {
                    "surya+paddle": "Surya and Paddle OCR (free open source)",
                    "pdf-text": "No OCR, use text in PDF",
                    "textract": "AWS Textract (commercial)",
                },
                value="surya+paddle",
                on_change=lambda e: toggle_option(e, "method"),
            ).classes("w-full")
            ui.checkbox(
                "Try to fix image rotation (can be very slow for large inputs)",
                on_change=lambda e: toggle_option(e, "unskew"),
            )

            file_upload = (
                ui.upload(
                    label="First add files and then upload them with the upside arrow in the right",
                    multiple=True,
                    on_upload=handle_upload,
                )
                .props('accept="image/*,application/pdf"')
                .classes("w-full")
            )

            global uploaded_files_list
            uploaded_files_list = ui.column()

            ui.button(
                "Clear file list", on_click=lambda: reset_uploaded_files(file_upload)
            ).classes("w-full")

            global extract_button
            extract_button = ui.button(
                "Extract tables", on_click=handle_extract_tables_click
            ).classes("w-full")
            with ui.row(align_items="center").classes("w-full justify-center"):
                ui.spinner(size="lg").bind_visibility_from(globals(), "in_progress")
                global in_progress_label
                in_progress_label = ui.label("").bind_visibility_from(
                    globals(), "in_progress"
                )

            ui.timer(
                0.1,
                callback=lambda: in_progress_label.set_text(queue.get())
                if not queue.empty()
                else None,
            )


ui.run(native=False, reload=False)
