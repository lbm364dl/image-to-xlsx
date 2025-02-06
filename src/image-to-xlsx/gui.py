from nicegui import app, ui, run
from pathlib import Path
import main
import zipfile
from multiprocessing import Manager
from io import BytesIO

options = {"method": "surya+paddle", "unskew": False, "show-detected-boxes": False}
manager = Manager()
uploaded_files = manager.dict()
in_progress = False
queue = manager.Queue()


def handle_upload(file):
    uploaded_files[file.name] = {"name": file.name, "content": file.content}
    ui.notify(f"Uploaded {file.name}")


def reset_uploaded_files(file_upload):
    uploaded_files.clear()
    file_upload.reset()
    ui.notify("Removed all uploaded files")


def toggle_option(event, option):
    options[option] = event.value


def extract_tables():
    results = []
    for file in uploaded_files.values():
        queue.put_nowait(f"Processing file {file['name']}")
        file_content = file["content"].read()
        table_workbook, footers_workbook = main.run(file_content, **options)
        results.append({
            "table_workbook": table_workbook,
            "footers_workbook": footers_workbook,
            "name": file["name"],
            "input_content": file_content,
        })

    return results


def workbook_to_bytes(workbook):
    virtual_workbook = BytesIO()
    workbook.save(virtual_workbook)
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


@ui.page("/")
def index():
    ui.select(
        {
            "surya+paddle": "Surya and Paddle OCR (free open source)",
            "pdf-text": "No OCR, use text in PDF",
            "textract": "AWS Textract (commercial)",
        },
        value="surya+paddle",
        on_change=lambda e: toggle_option(e, "method"),
    )
    ui.checkbox(
        "Try to fix image rotation", on_change=lambda e: toggle_option(e, "unskew")
    )
    ui.checkbox(
        "Show detected boxes",
        on_change=lambda e: toggle_option(e, "show-detected-boxes"),
    )

    file_upload = ui.upload(
        label="First add files and then upload them with the upside arrow in the right",
        multiple=True,
        on_upload=handle_upload,
    ).props('accept="image/*,application/pdf"')

    ui.button("Clear file list", on_click=lambda: reset_uploaded_files(file_upload))
    with ui.row():
        global extract_button
        extract_button = ui.button(
            "Extract tables", on_click=handle_extract_tables_click
        )
        spinner = ui.spinner(size="lg").bind_visibility_from(globals(), "in_progress")
        global in_progress_label
        in_progress_label = ui.label("").bind_visibility_from(globals(), "in_progress")

    # Update the progress bar on the main process
    ui.timer(
        0.1,
        callback=lambda: in_progress_label.set_text(queue.get())
        if not queue.empty()
        else None,
    )


ui.run(native=True)
