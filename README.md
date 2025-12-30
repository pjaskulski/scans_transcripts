# Scans and Transcriptions

Do you have a collection of scanned manuscripts or typescripts? Do you need a transcription? This simple **desktop** application makes using Gemini for this purpose easy. Once the transcriptions are complete, you can review, verify and correct them.

The idea is simple: the user prepares a folder with scans of manuscripts, typescripts, and old prints, and the application uses various Gemini models to prepare transcriptions, assisting in their verification through visual comparison of scans and transcriptions, voice recordings, and named entity recognition (NER) in areas where errors are more likely to occur. Finally, you receive a folder with scans, transcription files in txt format, mp3 voice recordings, and metadata saved in json files.

Since the application uses models via API, their use is subject to a fee, in accordance with Google's current [price list](https://ai.google.dev/gemini-api/docs/pricing). 

The Gemini Pro 3 model is used for transcription, the Gemini Flash model is used for searching for proper names, and the Gemini Pro 3 Image model (also known as Nano Banana Pro) is used for locating proper names on a scan.  The application can prepare transcriptions for a single image or a series of files. The Gemini API key should be stored in the `.env` file as the `GEMINI_API_KEY` environment variable (or in the `config/config.json` file under the `api_key` field).

## Application Features:

  - **Browsing scans and transcriptions**. The application assumes that the specified directory contains scan files and transcript files with identical names but with the *.txt extension. If a text file is missing, the application will automatically create an empty one.
  - **Creating transcripts using the LLM model** (Gemini Pro 3, requires internet access) for the current scan or scan series. For scan series, the application displays all scans in the viewed directory and selects those that do not yet have a txt transcript file or that have an empty transcript file. This selection can, of course, be changed.
  - To perform transcription, you can use one of the **predefined prompts** (prompts for documents in Polish are currently available), or you can prepare your own prompt.
  - Transcription files are automatically saved when moving to the next/previous file; you can also force saving by pressing the SAVE button.
  - Transcriptions can be saved in a **bulk txt file** or in a **docx file**. For docx files, the application also concatenates broken words and lines into paragraphs. Transcriptions can also be saved in **TEI-XML** format. 
  - To facilitate verification of transcription accuracy, the application allows you to pan the scan (left mouse button), **zoom in/out** (mouse scroll wheel), and display a **magnifying glass** window at a selected location (right mouse button). 
  - Simple **filters** can be applied to scans: contrast enhancement and image inversion.
  - A feature that aids verification is the ability to **read the transcript aloud (TTS reader)**, this feature requires internet access.
  - Ability to adjust the font size in the transcription field.
  - Due to the fact that transcription errors quite often appear in proper names (people, places, institutions), the option to **highlight** such words (**NER** button) has been added so that special attention can be paid to them during transcription verification. Experimental function (BOX button) for **automatic marking entity names in the scan**. The names are marked with frames, and the name from transcription is placed above the frame, for quick assessment of transcription accuracy. The frames for entity names can be adjusted in terms of size and position. The list of found **entity names can be exported to a CSV file** for further use.
  - The application **records the cost of all API calls** for the current catalog, with information about the date, name of the model used, number of tokens used (input, output), cost of the call, and summarizes the cost for the entire current scan catalog.
  - The user interface supports **multiple language versions**. Currently, two languages are defined: **PL** and **EN** (definitions in the localization.json file). 


## Screenshots and description:

Application window with a visible enlargement of the fragment (magnifying glass):

![Screen](/doc/screen_scan_transcript.png)

In the left panel with the scan, you can move the image - left mouse button, zoom in / out - mouse wheel, enlarge a fragment (magnifying glass) - right mouse button.

Application window while Gemini is reading the scan (progress bar visible at the top of the right panel, the Gemini button is unavailable while the model is processing the image):

![Screen](/doc/screen_scan_transcript_przetwarzanie.png)

Above the text field in the right panel of the application, there's a bar with the name of the scan directory currently being viewed (processed). On the right, there's a button that allows you to change the folder. This button displays a folder selection window, then loads the scan files and transcription files (txt, if they're already in the folder). The same folder selection window appears automatically when the application starts.

![Screen](/doc/images_folder.png)

**Main toolbar**:

List of buttons:

  - Go to the first file
  - Go to the previous file
  - Save changes to the current file
  - Read a scan with Gemini
  - Read a series of scans with Gemini
  - Save the read text for all files in a merged txt file
  - Save the read text for all files in a merged docx file
  - Save the read text for all files in a TEI-XML file
  - Go to the next file
  - Go to the last file

![Screen](/doc/toolbar.png)

Below the list of buttons there is information with the name of the currently set prompt file, the buttons on the right allows you to change the prompt or edit prompt.

If no transcription file exists for the current file, an empty file will be automatically created. Transcription files can be edited manually. In addition to saving via the 'SAVE' button, files are automatically saved when moving to the next/previous file and when exiting the application.

The application can also be closed with the Ctrl+Q shortcut.

**Transcription toolbar**:

![Screen](/doc/image_info.png)

Below is a bar with information about the current (displayed) scan file: its name and number in the series, and the total number of scans in the folder. On the right are the ‘A+’ and ‘A-’ buttons, which are used to adjust the font size in the text field. Between the scan file name and the font size adjustment buttons, there is a search field in the transcription. After entering the text you are looking for and pressing the Enter key, the application highlights the found occurrences of the text. You can also use the arrow button to start the search, and the button with the “x” symbol removes the highlights and clears the search field. The drop-down menu on the right allows you to change the language version of the interface. Currently, Polish and English versions are available.

The second row of the toolbar contains buttons for reading the transcription aloud: “>” (read) starts reading, “■” stops it, and “||” means pause. The combo box allows you to select the reading language. The read aloud function uses the gTTS library and requires Internet access, so there may be a short wait before it starts.

The ‘NER’, ‘BOX’ and ‘CLS’ buttons assist in verifying the transcription – due to the higher frequency of errors in proper names, they can be marked in the transcription text (‘NER’) and, for comparison, also on the scan (“BOX”). The ‘CLS’ button clears the markings. ‘LEG’ displays a legend with a description of the colours used to mark different categories of proper names (people, places, organisations).
The ‘CSV’ button allows you to export the proper names found (in all scans of the current catalogue) to a CSV file.
The ‘LOG’ button displays a list of all API calls along with their cost.  

  
**Reading a series of scans** by the Gemini model:

![Screen](/doc/screen_scan_transcript_seria.png)

The file batch reading window displays all scan files in the directory. You can select which files Gemini will read. By default, those for which there is no text file with transcription yet, or only an empty file, are selected. Buttons at the bottom of the window allow you to select or deselect all scans and initiate the transcription process for the selected scans, during which a progress bar is displayed (processing multiple files can be time-consuming).

Example of a **typescript transcription**:

![Screen](/doc/typescript_example.jpg)

**Prompt editor**:

![Screen](/doc/prompt_editor.jpg)

**Highlighting** of entity names in the transcription text:

![Screen](/doc/highlighting_entity_names.jpg)

Transcription errors prepared by the LLM model often concern proper names; to make finding them easier, an experimental BOX function was prepared - for **marking entity names in the scan**. The names are marked with frames, and the name read by the model is placed above the frame. This allows you to quickly compare the name with the actual content of the scan. See the screenshot below.

Automatic marking isn't perfect, so it's possible to adjust the created frames: by grabbing the frame with the left mouse button, you can move it, and you can also adjust the frame size—the lower right corner of the frame is a handle that allows you to resize it. The new position or size is automatically saved when you release the mouse button. However, it's important to remember that the main purpose of this feature is to indicate (even inaccurately) the position of the proper name for visual verification of transcription accuracy.

![Screen](/doc/entity_names_on_scan.jpg)

Example of **colour coding** different categories of entity names (PERSON, LOC, ORG):

![Screen](/doc/entity_names_on_scan_2.jpg)

In some scans, manual reading of text can be facilitated by **image filters**, the following filters are available: negative and contrast (the screenshot below shows the negative filter used):

![Screen](/doc/screen_scan_transcript_filtr.jpg)

An example of transcription of an 18th-century Polish **old print**:

![Screen](/doc/screen_scan_transcript_print.jpg)

**API cost control** for the current catalog:

![Screen](/doc/cost_control.jpg)

English **language version**:

![Screen](/doc/screen_english.jpg)

Example of a manuscript in German (early 20th century):

![Screen](/doc/screen_htr_ger.png)

The "test" folder contains sample scans and transcripts: scans of manuscripts from the 18th, 19th and 20th centuries, scans of typescripts from the mid-20th century, scans of old prints from the 18th century - mostly in Polish.

**Note**: access to the Gemini Pro 3 model via API is subject to a fee, as per the Google pricing page.

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

