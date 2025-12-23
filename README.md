# CodeAtlas

CodeAtlas is a web-based tool for exploring, annotating, and analyzing source code. It is designed to help structure documentation efforts for large legacy codebases. It came out of my off-and-on hobby of documenting a... uh... leak of giga size, if you know what I mean. I just found it fascinating to look through (especially as a low level guy). Eventually, I realized I needed a tool to help document this, without making *too* many changes to the original code. 

Keep in mind, I did have AI write most of this. Some of the tools it uses were originally made by me, most were not. Again, I'm a firmware/hardware guy, not a web developer. I'm sure there are some security issues, but I'm not going to fix them: just don't have this exposed to the internet. I do plan to go through and rewrite chunks of it, to at least understand the code? It would be nice to know how web stuff works. 

## Setup

### Prerequisites
*   Python 3
*   Pip dependencies: `flask`, `markdown`, `pygments`

### Directory Structure
CodeAtlas expects the target source code to be located in a directory named `source-code` within the project root.

1.  Create a directory named `source-code` in the root of the project.
2.  Place the source code you wish to analyze into this `source-code` directory.

Example structure:
/project_root
  /code_atlas
  /source-code
    /my_game_source
      main.c
      ...

## Database Initialization
CodeAtlas uses a SQLite database (`code_atlas.db`) to store file indices and annotations.

To initialize the database and scan the `source-code` directory for files, run the following command from the project root:

python3 code_atlas/app.py scan

This will create `code_atlas.db` if it does not exist and populate the `files` table.

## Running the Server
To start the web server, run:

python3 code_atlas/app.py

By default, the server runs on port 5000. You can access it in your web browser at:
http://localhost:5000

If you want to change the port it runs on (for instance, to have seperate servers for different projects), pass in --port <port> to the app.py script. 
 
## Features

### File Browser
Navigate through the directory structure of your source code. The interface mirrors the file system within `source-code`.

### Source Viewer & Annotation
*   **Syntax Highlighting:** Supports various languages via Pygments.
*   **Global Annotations:** Add high-level markdown notes to any file.
*   **Line Annotations:** Add comments to specific lines of code.

### Tools
CodeAtlas integrates several tools to assist with analysis:
*   **Extract Shift-JIS:** specific tool to extract Japanese strings from binary files.
*   **File Info:** Run the system `file` command to identify file types.
*   **Auto Translate:** Automated translation of Japanese comments. Uses deep_translator internally. It can either group lines into sentences (good for READMEs), or translate each line individually. 
*   **Format Code:** Run `clang-format` on C/C++ files.
*   **Open in VS Code:** Open the current file's directory in VS Code. I found this especially useful for for seeing where functions/variables are located, since I really didn't want to implement it in this web interface when VS-code already has it built in. 

## Architecture
*   **Frontend:** HTML/CSS/JS (served via Flask templates).
*   **Backend:** Flask (Python).
*   **Database:** SQLite.
