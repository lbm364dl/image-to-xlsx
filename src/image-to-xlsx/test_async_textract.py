import boto3
import io
import time
from surya.input.load import load_from_file
from surya.settings import settings
import pickle

# Upload the document to S3
bucket_name = 'test-textract-large-files'
file_name = "inputs/test_cust.pdf"
s3 = boto3.client('s3')
s3.upload_file(file_name, bucket_name, file_name)


# Initialize Textract client
textract = boto3.client("textract")

# Specify the document file

# document_path = "IIA/1938-39_pag_306_307centenosup_prod_rend.pdf"

pages, _, text_lines = load_from_file(
    file_name, dpi=settings.IMAGE_DPI_HIGHRES, load_text_lines=True
)

img = pages[0]
img_byte_arr = io.BytesIO()
img.save(img_byte_arr, format="PNG")
img_byte_arr = img_byte_arr.getvalue()

# Call Textract to analyze the document
response = textract.start_document_analysis(
    DocumentLocation={'S3Object': {'Bucket': bucket_name, 'Name': file_name}},
    FeatureTypes=["TABLES"],  # Extract tables and forms; omit for raw text
)

print("my aws response", response)

job_id = response['JobId']
print(f"Started Document Analysis Job. Job ID: {job_id}")

# Poll for job completion
while True:
    response = textract.get_document_analysis(JobId=job_id)
    status = response['JobStatus']
    print(f"Job Status: {status}")
    if status in ['SUCCEEDED', 'FAILED']:
        break
    time.sleep(5)

if status == 'SUCCEEDED':
    with open("test_cust.pkl", "wb") as f:
        pickle.dump(response, f)
else:
    print("Document analysis failed.")

# Delete the file from S3 after processing
s3.delete_object(Bucket=bucket_name, Key=file_name)
print(f"Deleted {file_name} from bucket {bucket_name}")

# Process the response
for block in response["Blocks"]:
    if block["BlockType"] == "LINE":
        print(block["Text"])
