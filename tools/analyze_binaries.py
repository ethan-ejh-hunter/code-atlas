
import os
import subprocess
from pathlib import Path
from collections import Counter
import sys

SOURCE_DIR = Path("source-code")
DOCS_DIR = Path("documents")
REPORT_FILE = DOCS_DIR / "binary_analysis_report.md"

def is_binary_content(content):
    if b'\0' in content:
        return True
    return False

def get_file_type(file_path):
    try:
        result = subprocess.run(["file", "-b", str(file_path)], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def analyze_binaries(directory):
    extension_counts = Counter()
    file_type_counts = Counter()
    binary_files_count = 0
    total_scanned = 0
    
    files_to_scan = []
    print("Enumerating files...")
    for root, _, files in os.walk(directory):
        for file in files:
            files_to_scan.append(Path(root) / file)
            
    total_files = len(files_to_scan)
    print(f"Scanning {total_files} files for binaries...")
    
    for i, file_path in enumerate(files_to_scan):
        total_scanned += 1
        if i % 100 == 0:
            sys.stdout.write(f"Processing {i}/{total_files}...\r")
            sys.stdout.flush()
            
        try:
            # Skip if file is too small to likely be an interesting binary? No, check all.
            # Read header
            with open(file_path, 'rb') as f:
                header = f.read(1024)
                
            if is_binary_content(header):
                binary_files_count += 1
                
                # Extension
                ext = file_path.suffix.lower()
                if not ext:
                    ext = "(no extension)"
                extension_counts[ext] += 1
                
                # File Type
                ftype = get_file_type(file_path)
                # Generalize file type?
                # e.g. "ELF 32-bit LSB executable, MIPS, N32 MIPS-III..." -> "ELF 32-bit LSB executable"
                # For now keep raw to capture specific architecture details if user wants.
                # Just counting raw strings.
                file_type_counts[ftype] += 1
                
        except Exception as e:
            # Permission denied or broken link
            continue

    print(f"\nFinished. Found {binary_files_count} binary files.")
    return extension_counts, file_type_counts, binary_files_count

def generate_report(ext_counts, type_counts, total_binaries):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("# Binary File Analysis Report\n\n")
        f.write(f"Total Binary Files Found: {total_binaries}\n\n")
        
        f.write("## Top Binary Extensions\n")
        f.write("| Extension | Count |\n")
        f.write("| :--- | :--- |\n")
        for ext, count in ext_counts.most_common(20):
            f.write(f"| {ext} | {count} |\n")
        f.write("\n")
        
        f.write("## Top File Types (via `file` command)\n")
        f.write("| File Type Description | Count |\n")
        f.write("| :--- | :--- |\n")
        for ftype, count in type_counts.most_common(20):
            # Escape pipes if any
            safe_type = ftype.replace("|", "\\|")
            f.write(f"| {safe_type} | {count} |\n")
        f.write("\n")
        
    print(f"Report saved to {REPORT_FILE}")

def main():
    if not SOURCE_DIR.exists():
        print(f"{SOURCE_DIR} does not exist.")
        return
        
    ext_c, type_c, total = analyze_binaries(SOURCE_DIR)
    generate_report(ext_c, type_c, total)

if __name__ == "__main__":
    main()
