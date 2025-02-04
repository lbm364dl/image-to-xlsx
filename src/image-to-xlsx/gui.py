from nicegui import app, ui
from local_file_picker import local_file_picker
import main

options = {"unskew": 0, "show-detected-boxes": 0}
uploaded_files = {}


def handle_upload(file):
    uploaded_files[file.name] = file  # Store file in dictionary
    print(uploaded_files)
    ui.notify(f"Uploaded {file.name}")


def reset_uploaded_files():
    uploaded_files.clear()
    file_upload.reset()
    print(uploaded_files)
    ui.notify("Removed all uploaded files")


def toggle_option(event, option):
    print(event)
    options[option] = int(event.value)
    print(options)

def extract_tables():
    main.run()

@ui.page("/")
async def index():
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
    )

    ui.button("Clear file list", on_click=reset_uploaded_files)

    ui.button("Extract tables", on_click=extract_tables)

    # ui.button('Choose file', on_click=choose_file, icon='folder')
    # ui.button('choose file', on_click=choose_file2)


ui.run(native=True)
