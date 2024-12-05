from openai import OpenAI
import dotenv
import os

dotenv.load_dotenv()

# create .env file in same directory
TOKEN = os.getenv("OPENAI_TOKEN")

lang_name = {
    "en": "English",
    "fr": "French",
}


def nlp_clean(table, lang="en"):
    client = OpenAI(api_key=TOKEN)

    output = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": f"""
            Can you try to fix this structured data? Some information:
            - Do not change anything from the structure of the data, keep each cell as it is. You should only
            ever change the content of each cell.
            - Assume words are in {lang_name.get(lang) or lang_name["en"]} and may contain spelling mistakes
            - Try to fix small spelling mistakes in numeric cells, e.g., if it looks like a number, an I
            is probably a 1, an O is probably a 0, a G is probably a 6, etc...
            - If you find Chinese characters, remove them
            - Do not add any new separators
            - Remove column with number indexes if there is one
            - Only reply back with the corrected text
            {table_to_csv(table)}
            """,
            }
        ],
    )

    content = output.choices[0].message.content.strip("```").strip()
    return csv_to_table(content)


def table_to_csv(table):
    return "\n".join(";".join(row) for row in table)


def csv_to_table(csv):
    return [row.split(";") for row in csv.split("\n")]
