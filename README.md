# scans_transcripts

A simple scan and transcription viewer with the option of reading scans using the Gemini Pro 3 model (using this model via API is subject to a fee) and the ability to manually correct transcriptions. The application has the ability to prepare transcriptions for a series of files, but in addition, a script (to be run from the console) for reading the entire series of scans by the Gemini Pro 3 model has also been prepared. The Gemini API key should be stored in the `.env` file as the `GEMINI_API_KEY` environment variable (or in the `config/config.json` file under the `api_key` field).

## Screenshots and description:

Application window with a visible enlargement of the fragment (magnifying glass):

![Screen](/doc/screen_scan_transcript.png)

In the left panel with the scan, you can move the image - left mouse button, zoom in / out - mouse wheel, enlarge a fragment (magnifying glass) - right mouse button.

Application window while Gemini is reading the scan

![Screen](/doc/screen_scan_transcript_przetwarzanie.png)

Above the text field in the right panel of the application, there's a bar with the name of the scan directory currently being viewed (processed). On the right, there's a button that allows you to change the folder. This button displays a folder selection window, then loads the scan files and transcription files (txt, if they're already in the folder). The same folder selection window appears automatically when the application starts.

![Screen](/doc/images_folder.png)

Below there is a bar with information about the current (displayed) scan file: its name and sequence number in the series, and the number of all scans in the folder. On the right side there are 'A+' and 'A-' buttons that can be used to adjust the font size in the text field.

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

**Note**: access to the Gemini Pro 3 model via API is subject to a fee, as per the Google pricing page.

In some scans, manual reading of text can be facilitated by image filters, the following filters are available: negative and contrast (the screenshot below shows the negative filter used).

![Screen](/doc/screen_scan_transcript_filtr.png)
