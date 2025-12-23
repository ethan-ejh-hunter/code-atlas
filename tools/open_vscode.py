
import sys
import os
import json
import subprocess

def open_vscode(file_path):
    try:
        # Get directory of the file
        abs_path = os.path.abspath(file_path)
        if os.path.isdir(abs_path):
            folder_path = abs_path
        else:
            folder_path = os.path.dirname(abs_path)
        
        # Run code command
        # We use Popen or run. code typically returns immediately.
        subprocess.run(["code", folder_path], check=True)
        
        return {"output": f"Opened VS Code in: {folder_path}"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No file path provided"}))
        sys.exit(1)
        
    result = open_vscode(sys.argv[1])
    print(json.dumps(result))
