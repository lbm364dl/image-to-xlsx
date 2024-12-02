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
            - Assume words are in {lang_name.get(lang) or lang_name["en"]} and may contain spelling mistakes
            - If you find Chinese characters, remove them
            - The second column should always be the measure unit. If it is a numeric cell, just shift the whole
            row to include an empty cell in the second column.
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
