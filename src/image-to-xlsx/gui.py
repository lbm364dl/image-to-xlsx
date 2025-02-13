from nicegui import ui, run
from pathlib import Path
from definitions import INF
from multiprocessing import Manager
from io import BytesIO
from utils import save_workbook
import main
import traceback
import re
import zipfile
import textwrap
import botocore.exceptions as aws_exceptions


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

def add_to_uploaded_files_list(file_name):
    with uploaded_files_list:
        with ui.row(align_items="center"):
            ui.label(file_name)
            ui.input(
                label="Pages",
                placeholder="1,2-5,7-9",
                on_change=lambda e: set_page_ranges(e, file_name),
                validation={"Wrong page range": validate_page_range},
            )

def handle_upload(file):
    uploaded_files[file.name] = {
        "name": file.name,
        "content": file.content.read(),
        "pages": [(1, INF)],
    }
    ui.notify(f"Uploaded {file.name}")

    if file.type == "application/pdf":
        add_to_uploaded_files_list(file.name)

def reset_uploaded_files(file_upload):
    uploaded_files.clear()
    uploaded_files_list.clear()
    file_upload.reset()
    ui.notify("Removed all uploaded files")

def toggle_option(event, option):
    options[option] = event.value

def extract_tables(uploaded_files, exception_queue, queue, options):
    results = []
    for file in uploaded_files.values():
        queue.put_nowait(f"Processing file {file['name']}")
        try:
            table_workbook, footers_workbook = main.run(
                file["content"], page_ranges=file["pages"], **options
            )
            results.append({
                "table_workbook": table_workbook,
                "footers_workbook": footers_workbook,
                "name": file["name"],
                "input_content": file["content"],
            })
        except (
            aws_exceptions.EndpointConnectionError,
            aws_exceptions.NoRegionError,
        ):
            exception_queue.put_nowait("Wrong AWS region. Try to fix credentials.")
            continue
        except (aws_exceptions.ClientError, aws_exceptions.NoCredentialsError):
            exception_queue.put_nowait(
                "Wrong AWS client credentials. Try to fix them."
            )
            continue
        except Exception:
            traceback.print_exc()
            exception_queue.put_nowait(
                "Unexpected error, try again or check command line error and contact developers"
            )

    return results

def aws_config_present():
    aws_dir = Path.home() / ".aws"
    config_file = aws_dir / "config"
    credentials_file = aws_dir / "credentials"
    return config_file.exists() and credentials_file.exists()

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
    results = await run.cpu_bound(extract_tables, uploaded_files, exception_queue, queue, options)
    extract_button.enabled = True
    in_progress = False
    if results:
        ui.notify("Processing done. Downloading results...")
        ui.download(create_results_zip(results), "results.zip")
    else:
        ui.notify("Nothing to process")

def validate_page_range(value):
    value = value.replace(" ", "").strip()
    return bool(re.match(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$", value))

def set_aws_credentials():
    aws_config = textwrap.dedent(f"""\
    [default]
    region = {options.get("aws_region")}
    output = json
    """)
    aws_credentials = textwrap.dedent(f"""\
    [default]
    aws_access_key_id = {options.get("aws_access_key_id")}
    aws_secret_access_key = {options.get("aws_secret_access_key")}
    """)

    aws_dir = Path.home() / ".aws"
    with open(aws_dir / "config", "w") as f_config:
        f_config.write(aws_config)

    with open(aws_dir / "credentials", "w") as f_credentials:
        f_credentials.write(aws_credentials)

    ui.notify("AWS credentials set correctly")

@ui.page("/")
def index():
    with ui.column().classes("w-full h-full items-center justify-center"):
        with ui.card().classes("p-8 shadow-lg rounded-xl"):
            method_option = ui.select(
                {
                    "surya+paddle": "Surya and Paddle OCR (free open source)",
                    "pdf-text": "No OCR, use text in PDF",
                    "textract": "AWS Textract (commercial)",
                },
                value=options.get("method", "surya+paddle"),
                on_change=lambda e: toggle_option(e, "method"),
            ).classes("w-full")

            with (
                ui.column()
                .bind_visibility_from(
                    method_option, "value", lambda v: v == "textract"
                )
                .classes("w-full")
            ):
                edit_aws_credentials = ui.checkbox("Modify current AWS credentials")

                if not aws_config_present():
                    edit_aws_credentials = edit_aws_credentials.set_visibility(
                        False
                    )

                aws_options_column = ui.card().classes("w-full")
                if aws_config_present():
                    aws_options_column = aws_options_column.bind_visibility_from(
                        edit_aws_credentials, "value"
                    )

                with aws_options_column:
                    ui.label("Configure access to AWS Textract")
                    ui.input(
                        "AWS region",
                        on_change=lambda e: toggle_option(e, "aws_region"),
                    ).classes("w-full")
                    ui.input(
                        "AWS Access Key Id",
                        on_change=lambda e: toggle_option(e, "aws_access_key_id"),
                    ).classes("w-full")
                    ui.input(
                        "AWS Secret Access key",
                        on_change=lambda e: toggle_option(
                            e, "aws_secret_access_key"
                        ),
                    ).classes("w-full")
                    ui.button(
                        "Use these credentials", on_click=set_aws_credentials
                    ).classes("w-full")

            ui.checkbox(
                "Try to fix image rotation (can be very slow for large inputs)",
                on_change=lambda e: toggle_option(e, "unskew"),
                value=options.get("unskew", False),
            ).bind_visibility_from(
                method_option, "value", lambda v: v != "pdf-text"
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

            for file in uploaded_files.values():
                add_to_uploaded_files_list(file["name"])

            ui.button(
                "Clear file list",
                on_click=lambda: reset_uploaded_files(file_upload),
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
            ui.timer(
                0.1,
                callback=lambda: ui.notify(exception_queue.get(), type="negative")
                if not exception_queue.empty()
                else None,
            )

if __name__ in {"__main__"}:
    manager = Manager()
    uploaded_files = manager.dict()
    options = manager.dict({
        "method": "surya+paddle",
        "unskew": False,
        "show-detected-boxes": False,
    })
    in_progress = False
    queue = manager.Queue()
    exception_queue = manager.Queue()
    ui.run(native=False, reload=False)
