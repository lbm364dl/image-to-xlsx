"""Per-session state management.

Each user connecting to the app gets their own Session instance,
ensuring uploaded files, options, and processing state are isolated.
"""

from definitions import INF

DEFAULT_OPTIONS = {
    "method": "paddleocr-vl",
    "unskew": False,
    "dewarp": False,
    "show-detected-boxes": False,
    "extend_rows": False,
    "remove_dots_and_commas": False,
    "fix_num_misspellings": True,
    "fixed_decimal_places": 0,
    "thousands_separator": ",",
    "decimal_separator": ".",
    "include_input_files_in_output": True,
    "glm_ocr_host": "localhost",
    "glm_ocr_port": 8081,
    "glm_ocr_api_key": "",
    "glm_ocr_model": "glm-ocr",
}


class Session:
    """Holds all per-user session state.

    Created fresh for each client connecting to the app. Attributes
    are used by NiceGUI's bind_visibility_from for reactive UI updates.
    """

    def __init__(self, manager):
        # Multiprocessing-safe shared state (needed for run.cpu_bound subprocesses)
        self.uploaded_files = manager.dict()
        self.uploaded_files_pages = manager.dict()
        self.options = manager.dict(DEFAULT_OPTIONS)
        self.queue = manager.Queue()
        self.exception_queue = manager.Queue()

        # UI-bound state (read by NiceGUI bindings)
        self.in_progress = False

        # Download state
        self.results_zip = None
        self.results_filename = None

        # UI element references (set during page build)
        self.extract_button = None
        self.download_button = None
        self.in_progress_label = None
        self.uploaded_files_list = None

    def toggle_option(self, event, option):
        """Update an option value from a UI event."""
        self.options[option] = event.value

    def cleanup(self):
        """Clean up multiprocessing resources on disconnect."""
        self.uploaded_files.clear()
        self.uploaded_files_pages.clear()
