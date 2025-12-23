
import os
import subprocess
import chardet
from pathlib import Path
import sys

SOURCE_DIR = Path("source-code")
DOCS_DIR = Path("documents")
REPORT_FILE = DOCS_DIR / "analysis_report.md"

def get_file_type(file_path):
    try:
        # Run file command only on things we suspect to be binary or matching specific criteria
        result = subprocess.run(["file", "-b", str(file_path)], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error running file command: {e}"

def is_binary_content(content):
    if b'\0' in content:
        return True
    return False

def check_encoding(rawdata):
    # specific check for shift_jis
    try:
        rawdata.decode('shift_jis')
        # If it decodes successfully, it MIGHT be shift_jis. 
        # But ASCII is also valid shift_jis.
        try:
            rawdata.decode('ascii')
            return "ASCII"
        except UnicodeDecodeError:
            return "Shift-JIS"
    except UnicodeDecodeError:
        pass

    # Detect other
    # Limit chardet to first 10KB for speed
    result = chardet.detect(rawdata[:10000])
    return result['encoding']

def analyze_directory(directory):
    results = []
    file_count = 0
    
    # Pre-count for progress
    total_files = sum([len(files) for r, d, files in os.walk(directory)])
    print(f"Found {total_files} files to analyze.")

    for root, _, files in os.walk(directory):
        for file in files:
            file_path = Path(root) / file
            file_count += 1
            if file_count % 100 == 0:
                print(f"Processing {file_count}/{total_files}: {file_path}", end='\r')

            is_rcs = file.endswith(",v")
            
            # Read first chunk to detect binary
            try:
                with open(file_path, 'rb') as f:
                    rawdata = f.read() # Read all for encoding detection, or chunk?
                    # Reading all might be memory heavy for huge files, but source code is usually small.
                    # Let's read up to 1MB.
                    if len(rawdata) > 1000000:
                        rawdata = rawdata[:1000000]
            except Exception as e:
                results.append({"path": str(file_path), "error": str(e)})
                continue

            if is_binary_content(rawdata):
                # Run 'file' command
                file_type_str = get_file_type(file_path)
                encoding = "Binary"
            else:
                file_type_str = "Text" # Placeholder, or maybe don't run `file` for text
                encoding = check_encoding(rawdata)
            
            # If RCS, it might look like binary or text depending on content (often text but with weird chars maybe?)
            # Actually RCS files are text, ensuring they are treated as such.
            if is_rcs and encoding == "Binary":
                 # RCS files are technically text but might contain binary keywords or just be large
                 # Let's assume text for RCS unless it's really weird.
                 # But 'is_binary_content' checks for NUL. RCS shouldn't have NUL unless the checked-in file was binary.
                 pass

            results.append({
                "path": str(file_path),
                "is_rcs": is_rcs,
                "file_type": file_type_str,
                "encoding": encoding
            })
    print(f"\nFinished processing {file_count} files.")
    return results

def main():
    if not SOURCE_DIR.exists():
        print(f"Directory {SOURCE_DIR} not found.")
        return

    print("Analyzing files...")
    results = analyze_directory(SOURCE_DIR)
    
    print(f"Generating report at {REPORT_FILE}...")
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("# Source Code Analysis Report\n\n")
        f.write(f"Total files analyzed: {len(results)}\n\n")
        
        # Summary statistics
        rcs_count = sum(1 for r in results if r.get('is_rcs'))
        shift_jis_count = sum(1 for r in results if r.get('encoding') == "Shift-JIS")
        binary_count = sum(1 for r in results if r.get('encoding') == "Binary")
        
        f.write(f"- RCS Files: {rcs_count}\n")
        f.write(f"- Shift-JIS Files: {shift_jis_count}\n")
        f.write(f"- Binary Files: {binary_count}\n\n")
        
        f.write("## File Details\n")
        f.write("| File Path | RCS | Encoding | File Type | Error |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for res in results:
            path_str = res.get('path', '')
            # Truncate path for table if too long? Or just relative
            rel_path = path_str
            if str(SOURCE_DIR) in path_str:
                rel_path = os.path.relpath(path_str, start=SOURCE_DIR)
            
            f.write(f"| {rel_path} | {res.get('is_rcs', False)} | {res.get('encoding', 'N/A')} | {res.get('file_type', 'N/A')} | {res.get('error', '')} |\n")

if __name__ == "__main__":
    main()
