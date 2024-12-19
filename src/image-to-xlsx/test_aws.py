import boto3
import io
from surya.input.load import load_from_file
from surya.settings import settings
import pickle

# Initialize Textract client
textract = boto3.client("textract")

# Specify the document file

# document_path = "IIA/1938-39_pag_306_307centenosup_prod_rend.pdf"
document_path = "inputs/test_footnotes.pdf"

pages, _, text_lines = load_from_file(
    document_path, dpi=settings.IMAGE_DPI_HIGHRES, load_text_lines=True
)

img = pages[4]
img_byte_arr = io.BytesIO()
img.save(img_byte_arr, format="PNG")
img_byte_arr = img_byte_arr.getvalue()

# Call Textract to analyze the document
response = textract.analyze_document(
    Document={"Bytes": img_byte_arr},
    FeatureTypes=["TABLES"],  # Extract tables and forms; omit for raw text
)

print("my aws response", response)

with open("test_footnotes_p4.pkl", "wb") as f:
    pickle.dump(response, f)

# Process the response
for block in response["Blocks"]:
    if block["BlockType"] == "LINE":
        print(block["Text"])
