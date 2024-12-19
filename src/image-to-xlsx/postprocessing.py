from openai import OpenAI
import dotenv
import os
import pandas as pd

dotenv.load_dotenv()

# create .env file in same directory
TOKEN = os.getenv("OPENAI_TOKEN")

lang_name = {
    "en": "English",
    "fr": "French",
}


def nlp_clean(table_data, lang="en", nlp_postprocess_prompt_file=None):
    client = OpenAI(api_key=TOKEN)

    if nlp_postprocess_prompt_file:
        with open(nlp_postprocess_prompt_file, "r") as f:
            prompt = f.read()
    else:
        prompt = f"""
        I have a CSV where the comma is the separator. It has three columns, the first two being numeric, that must not be changed. 
        The third column contains text, which you should try to fix. Some information that you need for that:
        - Do not change anything from the structure of the data, keep each individual entry as it is. You should only ever change the content of each entry
        - Assume words are in {lang_name.get(lang) or lang_name["en"]} and may contain spelling mistakes
        - Try to fix small spelling mistakes in numeric cells, e.g., if it looks like a number, an I is probably a 1, an O is probably a 0, a G is probably a 6, IO is probably 10, etc...
        - In text cells there may be some shortened words referring to unit measures. Leave them like that, but you may remove unnecessary punctuation
        - There may be some indicators of footnotes in text, e.g., "7) 43423" contains numeric data (43423) and note number 7
        - If you find Chinese characters, remove them
        - Do not consider a space as another separator. Just leave them the way they are
        - The output should still be a valid CSV, that is, all rows must have the same number of columns. It must have three columns
        - Only reply back with the corrected text. Do not include headers or anything, start directly with the first row
        """

    print("my_prompt", prompt)
    print("my_table_data", table_data)

    output = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": f"""
            {prompt}
            {table_to_csv(table_data)}
            """,
            }
        ],
    )


    content = output.choices[0].message.content.strip("```").strip()
    print("my_response", content)
    return csv_to_table(content, table_data)


def clean_text(text):
    return " ".join(text.split()).replace('"', "").replace(",", "")


def table_to_csv(table_data):
    data = [
        [str(i), str(j), clean_text(cell["text"])]
        for i, row in enumerate(table_data)
        for j, cell in enumerate(row)
        if clean_text(cell["text"])
    ]
    return pd.DataFrame(data).to_csv(index=False, header=False, escapechar="\\")


def csv_to_table(csv, table_data):
    fixed = [row.split(",") for row in csv.split("\n") if len(row.split(",")) == 3]
    for y, x, text in fixed:
        table_data[int(y)][int(x)]["text"] = text

    return table_data
