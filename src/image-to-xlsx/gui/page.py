"""Page route definitions and event handlers.

This module registers the NiceGUI page routes and wires up per-session
state with UI components. Each client connection gets its own Session.
"""

import datetime
from nicegui import ui, run
from definitions import INF
from gui.session import Session
from gui.processing import extract_tables
from gui import components


def register_pages(manager, extraction_semaphore):
    """Register all NiceGUI page routes.

    Args:
        manager: multiprocessing.Manager instance (shared, creates per-session dicts)
        extraction_semaphore: asyncio.Semaphore limiting concurrent extractions
    """

    @ui.page("/")
    async def index():
        session = Session(manager)

        # -- Event handlers (closures over this session's state) --

        async def handle_extract_tables_click():
            session.in_progress = True
            session.extract_button.enabled = False
            session.download_button.style("display: none;")

            if extraction_semaphore.locked():
                session.in_progress_label.set_text(
                    "Another extraction is in progress. Waiting in queue..."
                )

            async with extraction_semaphore:
                session.in_progress_label.set_text("Initializing...")
                results_zip = await run.cpu_bound(
                    extract_tables,
                    session.uploaded_files,
                    session.uploaded_files_pages,
                    session.exception_queue,
                    session.queue,
                    session.options,
                )

            session.extract_button.enabled = True
            session.in_progress = False

            if results_zip:
                when = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
                session.results_zip = results_zip
                session.results_filename = f"results_{when}.zip"
                session.download_button.style("display: block;")
                ui.notify("Processing done. Please download results.")
            else:
                ui.notify("Nothing to process")

        async def handle_upload(e):
            filename = getattr(e.file, "name", "uploaded_file")
            content_type = getattr(e.file, "content_type", "")
            read_result = e.file.read()
            if hasattr(read_result, "__await__"):
                raw_content = await read_result
            else:
                raw_content = read_result

            if raw_content is None:
                ui.notify("Upload failed: could not read file contents.")
                return

            if (content_type == "application/pdf" or raw_content[:4] == b"%PDF"):
                content_type = "application/pdf"
                if not filename.lower().endswith(".pdf"):
                    filename = f"{filename}.pdf"

            ui.notify(f"Uploaded {filename}")

            if content_type == "application/pdf":
                components.add_to_uploaded_files_list(session, filename)

            session.uploaded_files[filename] = {
                "name": filename,
                "content": raw_content,
                "type": content_type,
            }
            session.uploaded_files_pages[filename] = [(1, INF)]

        def reset_uploaded_files(file_upload):
            session.uploaded_files.clear()
            session.uploaded_files_pages.clear()
            session.uploaded_files_list.clear()
            file_upload.reset()
            session.download_button.style("display: none;")
            ui.notify("Removed all uploaded files")

        # -- Build the page --

        with ui.column().classes("w-full h-full items-center justify-center"):
            with ui.card().classes("p-8 shadow-lg rounded-xl"):
                components.page_header()
                components.methods_explanation()
                method_option = components.method_selector(session)
                components.aws_credentials_card(method_option, session)
                components.option_checkboxes(method_option, session)
                file_upload = components.file_upload_input(on_upload=handle_upload)
                components.uploaded_files_view(
                    file_upload,
                    session,
                    on_reset=lambda: reset_uploaded_files(file_upload),
                )
                components.extract_tables_button(
                    session, on_click=handle_extract_tables_click
                )
                components.set_timers(session)
