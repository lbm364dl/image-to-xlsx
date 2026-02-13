"""Pure processing functions for table extraction.

These run in subprocesses via NiceGUI's run.cpu_bound, so they must be
importable without importing the UI layer.
"""

from io import BytesIO
from pathlib import Path
import zipfile

CHUNK_SIZE = 1024 * 1024


def extract_tables(
    uploaded_files, uploaded_files_pages, exception_queue, queue, options
):
    """Extract tables from uploaded files. Runs in a subprocess."""
    import traceback
    import main

    method = options.get("method")
    aws_region_errors = ()
    aws_credential_errors = ()
    if method in {"textract", "textract-pickle-debug"}:
        import botocore.exceptions as aws_exceptions

        aws_region_errors = (
            aws_exceptions.EndpointConnectionError,
            aws_exceptions.NoRegionError,
        )
        aws_credential_errors = (
            aws_exceptions.ClientError,
            aws_exceptions.NoCredentialsError,
        )

    results = []
    total_files = len(uploaded_files)
    for i, (file, pages) in enumerate(
        zip(uploaded_files.values(), uploaded_files_pages.values())
    ):
        queue.put_nowait(
            f"({i + 1} out of {total_files}) Processing file {file['name']}"
        )
        file = {**file, "pages": pages}
        try:
            options["fixed_decimal_places"] = int(options["fixed_decimal_places"])
            table_workbook, footers_workbook = main.run(file, **options)
            results.append(
                {
                    "table_workbook": table_workbook,
                    "footers_workbook": footers_workbook,
                    "name": file["name"],
                    "input_content": file["content"],
                }
            )
        except aws_region_errors:
            exception_queue.put_nowait("Wrong AWS region. Try to fix credentials.")
            continue
        except aws_credential_errors:
            exception_queue.put_nowait("Wrong AWS client credentials. Try to fix them.")
            continue
        except Exception:
            traceback.print_exc()
            exception_queue.put_nowait(
                "Unexpected error, try again or check command line error and contact developers"
            )

    # Free GPU memory after extraction (important since cpu_bound reuses processes)
    try:
        from page import clear_gpu_memory
        clear_gpu_memory()
    except Exception:
        pass

    return create_results_zip(results, options) if results else None


def create_results_zip(results, options):
    """Create a zip file containing all extraction results."""
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
            if options.get("include_input_files_in_output"):
                zipf.writestr(
                    f"{name}/{result['name']}",
                    result["input_content"],
                )
    buffer.seek(0)
    return buffer.read()


def workbook_to_bytes(workbook):
    """Convert an openpyxl workbook to bytes."""
    from utils import save_workbook

    virtual_workbook = BytesIO()
    save_workbook(workbook, virtual_workbook)
    virtual_workbook.seek(0)
    return virtual_workbook.read()
