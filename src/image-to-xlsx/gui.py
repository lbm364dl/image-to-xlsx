from io import BytesIO
from pathlib import Path
from nicegui import ui
from fastapi.responses import StreamingResponse
import datetime
import zipfile

MAX_WIDTH = 650
CHUNK_SIZE = 1024 * 1024


def extract_tables(
    uploaded_files,
    uploaded_files_pages,
    exception_queue,
    queue,
    options,
    cancel_event,
):
    import botocore.exceptions as aws_exceptions
    import traceback
    import main

    results = []
    cancelled = False
    file_names = list(uploaded_files.keys())
    total_files = len(file_names)
    for i, file_name in enumerate(file_names):
        file = uploaded_files[file_name]
        pages = uploaded_files_pages.get(file_name, [(1, options.get("last_page", 10**9))])
        if cancel_event.is_set():
            cancelled = True
            break

        queue.put_nowait(
            f"({i + 1} out of {total_files}) Processing file {file['name']}"
        )
        file = {**file, "pages": pages}
        try:
            options["fixed_decimal_places"] = int(options["fixed_decimal_places"])
            table_workbook, footers_workbook = main.run(
                file,
                stop_event=cancel_event,
                **options,
            )

            if cancel_event.is_set():
                cancelled = True
                break

            results.append(
                {
                    "table_workbook": table_workbook,
                    "footers_workbook": footers_workbook,
                    "name": file["name"],
                    "input_content": file["content"],
                }
            )
        except (
            aws_exceptions.EndpointConnectionError,
            aws_exceptions.NoRegionError,
        ):
            exception_queue.put_nowait("Wrong AWS region. Try to fix credentials.")
            continue
        except (aws_exceptions.ClientError, aws_exceptions.NoCredentialsError):
            exception_queue.put_nowait("Wrong AWS client credentials. Try to fix them.")
            continue
        except main.ProcessingCancelled:
            cancelled = True
            break
        except Exception:
            traceback.print_exc()
            exception_queue.put_nowait(
                "Unexpected error, try again or check command line error and contact developers"
            )

    if cancelled or cancel_event.is_set():
        queue.put_nowait("Processing stopped")

    return {
        "results_zip": create_results_zip(results, options) if results else None,
        "cancelled": cancelled or cancel_event.is_set(),
    }


def create_results_zip(results, options):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for result in results:
            relative_name = Path(result["name"])
            output_base = relative_name.parent / relative_name.stem
            zipf.writestr(
                (output_base / f"{relative_name.stem}.xlsx").as_posix(),
                workbook_to_bytes(result["table_workbook"]),
            )
            zipf.writestr(
                (output_base / f"footers_{relative_name.stem}.xlsx").as_posix(),
                workbook_to_bytes(result["footers_workbook"]),
            )
            if options.get("include_input_files_in_output"):
                zipf.writestr(
                    (output_base / relative_name.name).as_posix(),
                    result["input_content"],
                )
    buffer.seek(0)
    return buffer.read()


def workbook_to_bytes(workbook):
    from utils import save_workbook

    virtual_workbook = BytesIO()
    save_workbook(workbook, virtual_workbook)
    virtual_workbook.seek(0)
    return virtual_workbook.read()


@ui.page("/download")
async def download_file():
    when = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    return StreamingResponse(
        iter_bytes(results_zip),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=results_{when}.zip"},
    )


def iter_bytes(data):
    for i in range(0, len(data), CHUNK_SIZE):
        yield data[i : i + CHUNK_SIZE]


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    from nicegui import ui, run
    from definitions import INF
    from multiprocessing import Manager
    import re
    import textwrap

    def aws_config_present():
        aws_dir = Path.home() / ".aws"
        config_file = aws_dir / "config"
        credentials_file = aws_dir / "credentials"
        return config_file.exists() and credentials_file.exists()

    def create_download_link():
        global download_link
        with ui.row().classes("w-full"):
            download_link = (
                ui.link("Download results", "/download", new_tab=True)
                .classes(
                    "w-full shadow-md q-btn q-btn-item q-btn--flat q-btn--rectangle bg-primary text-white hover:cursor-pointer"
                )
                .style("display: none;")
            )

    async def handle_extract_tables_click():
        global in_progress
        cancel_event.clear()
        in_progress = True
        extract_button.enabled = False
        stop_button.enabled = True
        download_link.style("display: none;")
        global results_zip

        in_progress_label.set_text("Initializing...")
        extraction_result = await run.cpu_bound(
            extract_tables,
            uploaded_files,
            uploaded_files_pages,
            exception_queue,
            queue,
            options,
            cancel_event,
        )
        results_zip = extraction_result["results_zip"]
        extract_button.enabled = True
        stop_button.enabled = False
        in_progress = False
        if extraction_result["cancelled"] and results_zip:
            ui.notify(
                "Processing stopped by user. Partial results are available for download.",
                type="warning",
            )
            download_link.style("display: block;")
        elif extraction_result["cancelled"]:
            ui.notify("Processing stopped by user. No files were completed.", type="warning")
        elif results_zip:
            ui.notify("Processing done. Please download results.")
            download_link.style("display: block;")
        else:
            ui.notify("Nothing to process")

    def stop_processing():
        if not in_progress:
            return

        cancel_event.set()
        in_progress_label.set_text("Stopping processing...")
        ui.notify("Stopping processing...", type="warning")

    def validate_page_range(value):
        value = value.replace(" ", "").strip()
        return bool(re.match(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$", value))

    def set_aws_credentials():
        aws_config = textwrap.dedent(
            f"""\
        [default]
        region = {options.get("aws_region")}
        output = json
        """
        )
        aws_credentials = textwrap.dedent(
            f"""\
        [default]
        aws_access_key_id = {options.get("aws_access_key_id")}
        aws_secret_access_key = {options.get("aws_secret_access_key")}
        """
        )

        aws_dir = Path.home() / ".aws"
        aws_dir.mkdir(parents=True, exist_ok=True)
        with open(aws_dir / "config", "w") as f_config:
            f_config.write(aws_config)

        with open(aws_dir / "credentials", "w") as f_credentials:
            f_credentials.write(aws_credentials)

        ui.notify("AWS credentials set correctly")

    def aws_credentials_card(method_option):
        with (
            ui.column()
            .bind_visibility_from(method_option, "value", lambda v: v == "textract")
            .classes("w-full")
        ):
            edit_aws_credentials = ui.checkbox("Modify current AWS credentials")

            if not aws_config_present():
                edit_aws_credentials = edit_aws_credentials.set_visibility(False)

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
                    on_change=lambda e: toggle_option(e, "aws_secret_access_key"),
                ).classes("w-full")
                ui.button(
                    "Use these credentials", on_click=set_aws_credentials
                ).classes("w-full")

    def method_selector():
        return ui.select(
            {
                "textract": "AWS Textract (commercial)",
                "surya+paddle": "Surya and Paddle OCR (free open source)",
                "pdf-text": "No OCR, use text in PDF",
            },
            label="Extraction method",
            value=options.get("method", "textract"),
            on_change=lambda e: toggle_option(e, "method"),
        ).classes("w-full")

    def option_checkboxes(method_option):
        with ui.column().classes(f"w-[{MAX_WIDTH}px]"):
            ui.label("Other options")

            ui.checkbox(
                "Try to fix image rotation (can be very slow for large inputs)",
                on_change=lambda e: toggle_option(e, "unskew"),
                value=options.get("unskew", False),
            ).bind_visibility_from(method_option, "value", lambda v: v != "pdf-text")

            ui.checkbox(
                "Create one row for each text detected inside a cell instead of joining with a space. Only try this if you see that adjacent rows are mixed into a single row by mistake.",
                on_change=lambda e: toggle_option(e, "extend_rows"),
                value=options.get("extend_rows", False),
            )

            ui.checkbox(
                "Force substitution of common wrongly detected digits as letters, e.g., change I to 1, b to 6, O to 0, etc...",
                on_change=lambda e: toggle_option(e, "fix_num_misspellings"),
                value=options.get("fix_num_misspellings", True),
            )
            remove_dots_and_commas = ui.checkbox(
                "Remove all commas and dots from cells. Try this if the OCR scanning struggles differentiating between commas and dots and/or you want a fixed number of decimal places.",
                on_change=lambda e: toggle_option(e, "remove_dots_and_commas"),
                value=options.get("remove_dots_and_commas", False),
            )
            with ui.row(align_items="center").bind_visibility_from(
                remove_dots_and_commas, "value"
            ):
                ui.number(
                    "Decimal places",
                    placeholder="0",
                    on_change=lambda e: toggle_option(e, "fixed_decimal_places"),
                    precision=0,
                    min=0,
                )
                ui.label(
                    "Forcefully write a decimal point this number of places to the left of the last digit in numeric cells. "
                ).classes("w-1/2")

            with ui.column().bind_visibility_from(
                remove_dots_and_commas, "value", lambda v: not v
            ):
                with ui.row(align_items="center"):
                    ui.select(
                        {
                            ",": "Comma (,)",
                            ".": "Dot (.)",
                        },
                        value=options.get("thousands_separator", ","),
                        on_change=lambda e: toggle_option(e, "thousands_separator"),
                    ).classes("w-[20%]")
                    ui.label(
                        " Thousands separator (will be ignored when trying to convert numeric cells) "
                    ).classes("w-[50%]")
                with ui.row(align_items="center"):
                    ui.select(
                        {
                            ".": "Dot (.)",
                            ",": "Comma (,)",
                        },
                        value=options.get("decimal_separator", "."),
                        on_change=lambda e: toggle_option(e, "decimal_separator"),
                    ).classes("w-[20%]")
                    ui.label(
                        "Decimal separator (will be used as decimal point when trying to convert numeric cells)"
                    ).classes("w-[50%]")

    def file_upload_input():
        ui.label(
            "Add files or folders you want to process. Only PDFs and images are accepted. For images, at least PNG and JPEG should be valid. Folders are processed recursively and the output mirrors the input folder structure. You can select page ranges to process in each PDF or leave blank for all pages."
        ).classes(f"w-[{MAX_WIDTH}px]")

        with ui.row().classes("w-full"):

            async def _run_picker(mode):
                import asyncio
                import subprocess
                import sys

                script = (
                    "import sys\n"
                    "from PyQt6.QtWidgets import QApplication, QFileDialog\n"
                    "app = QApplication(sys.argv)\n"
                )
                if mode == "files":
                    script += (
                        "files, _ = QFileDialog.getOpenFileNames(None, 'Select files', '',\n"
                        "    'Supported files (*.pdf *.png *.jpg *.jpeg)')\n"
                        "print('\\n'.join(files))\n"
                    )
                else:
                    script += (
                        "folder = QFileDialog.getExistingDirectory(None, 'Select folder')\n"
                        "print(folder)\n"
                    )

                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", script,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                stdout, _ = await proc.communicate()
                return stdout.decode().strip()

            async def pick_files():
                result = await _run_picker("files")
                if result:
                    for file_path in result.splitlines():
                        if file_path:
                            add_local_file(file_path)

            async def pick_folder():
                result = await _run_picker("folder")
                if result:
                    add_files_from_folder(result)

            ui.button("Add files", on_click=pick_files).classes("flex-grow")
            ui.button("Add folder", on_click=pick_folder).classes("flex-grow")

    def uploaded_files_view():
        global uploaded_files_list, uploaded_files_rows, search_input, files_list_container

        uploaded_files_rows = {}

        def filter_files():
            term = search_input.value.lower() if search_input.value else ""
            for name, row in uploaded_files_rows.items():
                row.set_visibility(term in name.lower())

        search_input = ui.input(
            placeholder="Search through uploaded files...",
            on_change=lambda _: filter_files(),
        ).classes("w-full").props('clearable clear-icon="close" icon="search"')
        search_input.set_visibility(False)

        files_list_container = ui.column().classes("w-full")
        files_list_container.set_visibility(False)

        with files_list_container:
            with ui.scroll_area().classes(f"w-full max-h-[300px] border rounded"):
                uploaded_files_list = ui.column().classes("w-full p-2")

            ui.button(
                "Clear file list",
                on_click=reset_uploaded_files,
            ).classes("w-full")

        for file in uploaded_files.values():
            add_to_uploaded_files_list(file["name"], file["type"])

    def extract_tables_button():
        ui.label(
            "A zip file with the results will be downloaded, containing one folder for each input file. The output Excels will contain one sheet for each table detected in the file."
        ).classes(f"w-[{MAX_WIDTH}px]")
        ui.checkbox(
            "Include original files in output zip",
            on_change=lambda e: toggle_option(e, "include_input_files_in_output"),
            value=options.get("include_input_files_in_output"),
        )

        ui.html(
            'The cells in the output Excels have a color code. For more details see '
            '<a href="https://saco.csic.es/s/ESYzMcR9NWjWbrB" target="_blank" style="color: #1976d2; text-decoration: underline;">the legend sheet</a>.'
        ).classes(f"w-[{MAX_WIDTH}px]")

        global extract_button
        extract_button = ui.button(
            "Extract tables", on_click=handle_extract_tables_click
        ).classes("w-full")
        global stop_button
        stop_button = ui.button(
            "Stop Processing", on_click=stop_processing
        ).classes("w-full bg-red-600 text-white").bind_visibility_from(
            globals(), "in_progress"
        )
        stop_button.enabled = False
        with ui.row(align_items="center").classes("w-full justify-center"):
            ui.spinner(size="lg").bind_visibility_from(globals(), "in_progress")
            global in_progress_label
            in_progress_label = ui.label("Initializing...").bind_visibility_from(
                globals(), "in_progress"
            )

        create_download_link()

    def set_timers():
        ui.timer(
            0.1,
            callback=lambda: (
                in_progress_label.set_text(queue.get()) if not queue.empty() else None
            ),
        )
        ui.timer(
            0.1,
            callback=lambda: (
                ui.notify(exception_queue.get(), type="negative")
                if not exception_queue.empty()
                else None
            ),
        )

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

        uploaded_files_pages[file_name] = page_ranges

    def add_files_from_folder(folder_path):
        from utils import get_document_paths

        if not folder_path:
            ui.notify("No folder selected", type="warning")
            return

        folder_path = Path(folder_path).expanduser()
        if not folder_path.is_dir():
            ui.notify("Folder path is not valid", type="negative")
            return

        root_dir_path, relative_paths = get_document_paths(folder_path)
        if not relative_paths:
            ui.notify("No supported files found in folder", type="warning")
            return

        added_count = 0
        for relative_path in relative_paths:
            real_path = root_dir_path / relative_path
            file_name = str(relative_path)
            if file_name in uploaded_files:
                continue

            with real_path.open("rb") as f:
                uploaded_files[file_name] = {
                    "name": file_name,
                    "content": f.read(),
                    "type": "application/pdf"
                    if real_path.suffix.lower() == ".pdf"
                    else "image/*",
                }
            uploaded_files_pages[file_name] = [(1, INF)]
            add_to_uploaded_files_list(file_name, uploaded_files[file_name]["type"])
            added_count += 1

        if added_count:
            ui.notify(f"Added {added_count} files from folder")
        else:
            ui.notify("No new files were added", type="warning")

    def add_to_uploaded_files_list(file_name, file_type=None):
        if not uploaded_files_rows:
            search_input.set_visibility(True)
            files_list_container.set_visibility(True)

        is_pdf = file_type == "application/pdf" if file_type else file_name.lower().endswith(".pdf")
        with uploaded_files_list:
            row = ui.row(align_items="center").classes("w-full flex-nowrap gap-2")
            uploaded_files_rows[file_name] = row
            with row:

                def remove_file(fn=file_name, r=row):
                    uploaded_files.pop(fn, None)
                    uploaded_files_pages.pop(fn, None)
                    uploaded_files_rows.pop(fn, None)
                    r.delete()
                    if not uploaded_files_rows:
                        search_input.set_visibility(False)
                        files_list_container.set_visibility(False)
                        search_input.set_value("")

                ui.button(icon="delete", on_click=remove_file).props(
                    "flat dense color=negative"
                ).classes("flex-shrink-0")

                if is_pdf:
                    ui.input(
                        label="Pages",
                        placeholder="1,2-5,7-9",
                        on_change=lambda e: set_page_ranges(e, file_name),
                        validation={"Wrong page range": validate_page_range},
                    ).classes("flex-shrink-0").props("no-error-icon hide-bottom-space dense").style("width: 140px;")

                ui.label(file_name).classes(
                    "flex-grow overflow-x-auto whitespace-nowrap text-sm"
                ).style("min-width: 0;")

    def add_local_file(file_path):
        file_path = Path(file_path)
        file_name = file_path.name
        if file_name in uploaded_files:
            return

        file_type = (
            "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/*"
        )
        with file_path.open("rb") as f:
            uploaded_files[file_name] = {
                "name": file_name,
                "content": f.read(),
                "type": file_type,
            }
        uploaded_files_pages[file_name] = [(1, INF)]
        add_to_uploaded_files_list(file_name, file_type)

    def reset_uploaded_files():
        uploaded_files.clear()
        uploaded_files_pages.clear()
        uploaded_files_rows.clear()
        uploaded_files_list.clear()
        search_input.set_visibility(False)
        search_input.set_value("")
        files_list_container.set_visibility(False)
        download_link.style("display: none;")
        ui.notify("Removed all uploaded files")

    def toggle_option(event, option):
        options[option] = event.value

    def page_header():
        ui.label("Table extraction tool").classes("text-[24px]")
        ui.label("Extract data tables from PDFs/images to Excel sheets").classes(
            "text-[16px]"
        )

    def methods_explanation():
        ui.label("Methods:")
        with ui.list().classes(f"w-[{MAX_WIDTH}px]").props("separator"):
            ui.item(
                "AWS Textract: uses paid Amazon Web Services tool Textract for table recognition. Most reliable option but requires AWS credentials."
            )
            ui.item(
                "Surya and Paddle OCR: uses free open source AI models for table recognition. More experimental and slower. The first time it takes even longer because it has to download the models."
            )
            ui.item(
                "PDF text: does not rely on AI models and instead uses information stored in the PDF. Only use if your PDF has embedded text, that is, if you can select and copy the contents of the table."
            )

    @ui.page("/")
    async def index():
        with ui.column().classes("w-full h-full items-center justify-center"):
            with ui.card().classes("p-8 shadow-lg rounded-xl"):
                page_header()
                methods_explanation()
                method_option = method_selector()
                aws_credentials_card(method_option)
                option_checkboxes(method_option)
                file_upload_input()
                uploaded_files_view()
                extract_tables_button()
                set_timers()

    manager = Manager()
    uploaded_files = manager.dict()
    uploaded_files_pages = manager.dict()
    options = manager.dict(
        {
            "method": "textract",
            "unskew": False,
            "show_detected_boxes": False,
            "extend_rows": False,
            "remove_dots_and_commas": False,
            "fix_num_misspellings": True,
            "fixed_decimal_places": 0,
            "thousands_separator": ",",
            "decimal_separator": ".",
            "include_input_files_in_output": True,
        }
    )

    in_progress = False
    queue = manager.Queue()
    exception_queue = manager.Queue()
    cancel_event = manager.Event()
    ui.run(native=False, reload=False)
