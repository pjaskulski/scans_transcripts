# Scans and Transcriptions

Do you have a collection of scanned manuscripts or typescripts? Do you need a transcription? This simple desktop application makes using Gemini for this purpose easy. Once the transcriptions are complete, you can review, verify and correct them.

The 'Scans and Transcriptions' viewer offers the option of reading scans using the Gemini Pro 3 model (please note that using this model via API is subject to a fee!) and the ability to manually correct transcriptions. The application can prepare transcriptions for a single image or a series of files. The Gemini API key should be stored in the `.env` file as the `GEMINI_API_KEY` environment variable (or in the `config/config.json` file under the `api_key` field).

Application Features:
  - Viewing scans and transcripts. The application assumes that the specified directory contains scan files and transcript files with identical names but with the *.txt extension. If a text file is missing, the application will automatically create an empty one.
  - Creating transcripts using the LLM model (Gemini Pro 3, requires internet access) for the current scan or scan series. For scan series, the application displays all scans in the viewed directory and selects those that do not yet have a txt transcript file or that have an empty transcript file. This selection can, of course, be changed.
  - Transcription files are automatically saved when moving to the next/previous file; you can also force saving by pressing the SAVE button.
  - Transcriptions can be saved in a bulk txt file or in a docx file. For docx files, the application also concatenates broken words and lines into paragraphs. 
  - To facilitate verification of transcription accuracy, the application allows you to pan the scan (left mouse button), zoom in/out (mouse scroll wheel), and display a magnifying glass window at a selected location (right mouse button). 
  - Simple filters can be applied to scans: contrast enhancement and image inversion.
  - A feature that aids verification is the ability to read the transcript aloud (TTS reader), this feature requires internet access.
  - Ability to adjust the font size in the transcription field.
  - Due to the fact that transcription errors quite often appear in proper names (people, places, institutions), the option to highlight such words (NER button) has been added so that special attention can be paid to them during transcription verification.


## Screenshots and description:

Application window with a visible enlargement of the fragment (magnifying glass):

![Screen](/doc/screen_scan_transcript.png)

In the left panel with the scan, you can move the image - left mouse button, zoom in / out - mouse wheel, enlarge a fragment (magnifying glass) - right mouse button.

Application window while Gemini is reading the scan

![Screen](/doc/screen_scan_transcript_przetwarzanie.png)

Above the text field in the right panel of the application, there's a bar with the name of the scan directory currently being viewed (processed). On the right, there's a button that allows you to change the folder. This button displays a folder selection window, then loads the scan files and transcription files (txt, if they're already in the folder). The same folder selection window appears automatically when the application starts.

![Screen](/doc/images_folder.png)

Below there is a bar with information about the current (displayed) scan file: its name and sequence number in the series, and the number of all scans in the folder. On the right side there are 'A+' and 'A-' buttons that can be used to adjust the font size in the text field. In the center are buttons for reading the transcript aloud: READ starts reading, and STOP stops it. A combo box allows you to select the language. The read aloud function uses the gTTS library and requires internet access, so there may be a short wait before it begins.

![Screen](/doc/image_info.png)

Toolbar:

![Screen](/doc/toolbar.png)

List of buttons:

  - Go to the first file
  - Go to the previous file
  - Save changes to the current file
  - Read a scan with Gemini
  - Read a series of scans with Gemini
  - Save the read text for all files in a merged txt file
  - Save the read text for all files in a merged docx file
  - Go to the next file
  - Go to the last file

Below the list of buttons there is information with the name of the currently set prompt file, the button on the right allows you to change the prompt.

If no transcription file exists for the current file, an empty file will be automatically created. Transcription files can be edited manually. In addition to saving via the 'SAVE' button, files are automatically saved when moving to the next/previous file and when exiting the application.

The application can also be closed with the Ctrl+Q shortcut.
  
Reading a series of scans by the Gemini model:

![Screen](/doc/screen_scan_transcript_seria.png)

The file batch reading window displays all scan files in the directory. You can select which files Gemini will read. By default, those for which there is no text file with transcription yet, or only an empty file, are selected. Buttons at the bottom of the window allow you to select or deselect all scans and initiate the transcription process for the selected scans, during which a progress bar is displayed (processing multiple files can be time-consuming).

Example of a typescript transcription:

![Screen](/doc/typescript_example.jpg)

Prompt editor:

![Screen](/doc/prompt_editor.jpg)

Highlighting of entity names in the transcription text:

![Screen](/doc/highlighting_entity_names.jpg)

BOX - experimental function for marking entity names in the scan. The names are marked with frames, and the name read by the model is placed above the frame (on yellow background). This allows you to quickly compare the name with the actual content of the scan. See the screenshot below.

![Screen](/doc/entity_names_on_scan.jpg)

**Note**: access to the Gemini Pro 3 model via API is subject to a fee, as per the Google pricing page.

In some scans, manual reading of text can be facilitated by image filters, the following filters are available: negative and contrast (the screenshot below shows the negative filter used).

![Screen](/doc/screen_scan_transcript_filtr.png)

The Gemini model was involved in the application programming :-)

Project carried out at the Digital History Lab of the Institute of History of the Polish Academy of Sciences [https://ai.ihpan.edu.pl](https://ai.ihpan.edu.pl).

**Note 2**: A similar but more advanced transcription application (also using Python and TKinter!) is 
[Transcription Pearl](https://github.com/mhumphries2323/Transcription_Pearl) (Mark Humphries and Lianne C. Leddy, 2024. Transcription Pearl 1.0 Beta. Department of History: Wilfrid Laurier University.) – it allows you to use various models from OpenAI, Google, and Anthropic, import images from PDF files, etc. The same authors have another application: [ArchiveStudio](https://github.com/mhumphries2323/Archive_Studio), which is designed for the Windows system.


## Installation

Ensure you have Python installed (version 3.10 or newer is recommended).
Install the required libraries:

```
pip install -r requirements.txt
```

## Configuration 

API key: Create a .env file in the main application directory and add your Gemini key to it: 

```
GEMINI_API_KEY=your_key_here
```

**Prompts**: The content of the instructions for the AI model (prompts) should be located in .txt files in the ../prompt/ subdirectory. This directory already contains sample prompts.

**Settings**: The application stores preferences (font size, TTS reader language) in the config.json file. You can also save your API key in the ‘api_key’ field in this file. The application first looks for the GEMINI_API_KEY environment variable, and if it is not found, it tries to load the key from the config.json file.

