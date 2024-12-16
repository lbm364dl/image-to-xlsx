from openai import OpenAI
from io import StringIO
import dotenv
import os
import pandas as pd
import csv

dotenv.load_dotenv()

# create .env file in same directory
TOKEN = os.getenv("OPENAI_TOKEN")

lang_name = {
    "en": "English",
    "fr": "French",
}


def nlp_clean(table_matrix, lang="en", nlp_postprocess_prompt_file=None):
    client = OpenAI(api_key=TOKEN)

    if nlp_postprocess_prompt_file:
        with open(nlp_postprocess_prompt_file, "r") as f:
            prompt = f.read()
    else:
        prompt = f"""
        I have a CSV where the comma is the separator and all individual values are inside double quotes.
        Can you try to fix the data inside each pair of duoble quotes? Some information:
        - Do not change anything from the structure of the data, keep each individual entry as it is. You should only ever change the content of each entry
        - Assume words are in {lang_name.get(lang) or lang_name["en"]} and may contain spelling mistakes
        - Try to fix small spelling mistakes in numeric cells, e.g., if it looks like a number, an I
        is probably a 1, an O is probably a 0, a G is probably a 6, etc...
        - If you find Chinese characters, remove them
        - Do not add any new separators. For example, if you get a row like
            1 2,3 ,5 6
        do not try to split it into more columns like
            1,2,3,5,6
        instead just leave it the way it was, like
            1 2,3,5 6
        - Do not consider a space as another separator. Just leave them the way they are
        - Remove column with number indexes if there is one
        - The output should still be a valid CSV, that is, all rows must have the same number of columns
        - Only reply back with the corrected text
        """

    output = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": f"""
            {prompt}
            {table_to_csv(table_matrix)}
            """,
            }
        ],
    )

    content = output.choices[0].message.content.strip("```").strip()
    print("my_content", content)
    return csv_to_table(content)


def table_to_csv(table_matrix):
    output_csv = pd.DataFrame([
        [" ".join(col["text"].split()).replace('"', "") for col in row]
        for row in table_matrix
    ]).to_csv(quotechar='"', quoting=csv.QUOTE_ALL)
    print("my_csv", output_csv)
    return output_csv
    return "\n".join(";".join(row) for row in table)


def csv_to_table(csv):
    print("whatttttt", pd.read_csv(StringIO(csv)))
    return [row.split(";") for row in csv.split("\n")]
