"""Entry point for the NiceGUI web application.

Run with: python -m gui  (from src/image-to-xlsx/)
"""

import os
import asyncio
from multiprocessing import freeze_support, Manager

freeze_support()

from nicegui import ui
from gui.page import register_pages

manager = Manager()
max_concurrent = int(os.environ.get("MAX_CONCURRENT_EXTRACTIONS", "1"))
extraction_semaphore = asyncio.Semaphore(max_concurrent)

register_pages(manager, extraction_semaphore)

ui.run(
    native=False,
    reload=False,
    host=os.environ.get("HOST", "127.0.0.1"),
    port=int(os.environ.get("PORT", "8080")),
    storage_secret=os.environ.get("STORAGE_SECRET", "dev-secret-change-me"),
)
