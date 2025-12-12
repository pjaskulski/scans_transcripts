""" przetwarzanie obrazów (skanów) przez Gemini Pro 3 """
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types


# zmienne środowiskowe
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)

# prompt z pliku tekstowego
with open('prompt.txt', 'r', encoding='utf-8') as f:
    prompt = f.read()


# ----------------------------- FUNCTIONS --------------------------------------
def generate(image_path):
    """ odczytywanie tekstu ze skanu """

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY")
    )

    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    model = "gemini-3-pro-preview"

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/jpeg'
                )
            ]
        )
    ]

    generate_content_config = types.GenerateContentConfig(
        temperature=0,
        thinkingConfig= types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.LOW),
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH
    )

    chunk = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config
    )

    return chunk.text


# -------------------------------- MAIN ----------------------------------------
if __name__ == "__main__":

    # ścieżka do katalogu ze skanami
    dir_path = Path('..') / 'nazwa_folderu'

    for file_path in dir_path.glob('*.jpg'):
        txt_path = file_path.with_suffix('.txt')
        if txt_path.exists():
            continue

        print(f'Przetwarzanie: {file_path}')
        result = generate(image_path=file_path)
        if result:
            with open(txt_path, 'w', encoding='utf-8') as f_out:
                f_out.write(result + '\n')
                print(f'Zapisano wynik w pliku: {txt_path}')
        else:
            print(f'ERROR: model zwrócił pusty wynik dla pliku: {file_path}')

        time.sleep(3)
