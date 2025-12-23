
import os
import subprocess
import chardet
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

SOURCE_DIR = Path("source-code")
DOCS_DIR = Path("documents")
MODERNIZE_LOG = DOCS_DIR / "modernization_log.md"

# Thread-safe logging
log_lock = threading.Lock()
log_entries = []

def log_message(message):
    with log_lock:
        log_entries.append(message)

def get_encoding(rawdata):
    # Try Shift-JIS first as it's a priority
    try:
        rawdata.decode('shift_jis')
        # Check if ASCII
        try:
            rawdata.decode('ascii')
            return "ASCII"
        except UnicodeDecodeError:
            return "Shift-JIS"
    except UnicodeDecodeError:
        pass
    
    # Try EUC-JP
    try:
        rawdata.decode('euc-jp')
        try:
            rawdata.decode('ascii')
            return "ASCII"
        except UnicodeDecodeError:
            return "EUC-JP"
    except UnicodeDecodeError:
        pass

    # Use chardet for others, limit sample size
    result = chardet.detect(rawdata[:20000])
    return result['encoding']

def convert_to_utf8(file_path):
    try:
        with open(file_path, 'rb') as f:
            rawdata = f.read()
        
        encoding = get_encoding(rawdata)
        
        if not encoding or encoding.lower() in ['ascii', 'utf-8', 'binary']:
            return None # No conversion needed or not possible
            
        # List of encodings to modernize
        targets = ['shift_jis', 'shift_jis_2004', 'shift_jisx0213', 'euc-jp', 'iso-8859-1', 'macroman', 'shift_jisx0213']
        
        if encoding.lower() not in targets:
            # If we are unsure, maybe skip?
            # But the user wants to modernize. 
            pass

        try:
            content = rawdata.decode(encoding)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return encoding
        except Exception as e:
            return f"Error converting from {encoding}: {e}"
            
    except Exception as e:
        return f"Error reading: {e}"

def extract_rcs(rcs_path, target_path):
    try:
        # use co -p to print to stdout
        with open(target_path, 'wb') as f:
            subprocess.run(["co", "-p", str(rcs_path)], stdout=f, check=True, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        return str(e)

def process_file(file_path, root):
    file_name = file_path.name
    results = []

    # RCS Extraction
    if file_name.endswith(",v"):
        target_name = file_name[:-2]
        target_path = root / target_name
        
        # Idempotency check: Don't re-extract if target exists
        if target_path.exists():
             # If target exists, we assume it was extracted. 
             # We should check if we still have the RCS file to clean up.
             try:
                 file_path.unlink()
                 results.append(f"Cleaned up RCS: {file_name} (Target already existed)")
             except Exception as e:
                 results.append(f"Failed to delete RCS {file_name}: {e}")
             return results

        res = extract_rcs(file_path, target_path)
        if res is True:
            results.append(f"Extracted RCS: {file_name} -> {target_name}")
            
            # CLEANUP: Delete the ,v file
            try:
                file_path.unlink()
                results.append(f"Deleted RCS archive: {file_name}")
            except Exception as e:
                results.append(f"Failed to delete RCS archive {file_name}: {e}")

            # Now convert the newly extracted file
            conv_res = convert_to_utf8(target_path)
            if conv_res:
                results.append(f"Converted Extracted File: {target_name} ({conv_res} -> UTF-8)")
        else:
            results.append(f"Failed to extract RCS {file_name}: {res}")
    
    # Encoding Conversion (for non-RCS files)
    elif not file_name.endswith(",v"):
        # Binary check
        try:
            with open(file_path, 'rb') as f:
                header = f.read(1024)
                if b'\0' in header:
                    return [] # Skip binary
        except:
            return []

        conv_res = convert_to_utf8(file_path)
        if conv_res and not conv_res.startswith("Error"):
            results.append(f"Converted: {file_name} ({conv_res} -> UTF-8)")
        elif conv_res and conv_res.startswith("Error"):
            results.append(f"Failed to convert {file_name}: {conv_res}")

    return results

def process_directory(directory):
    all_files = []
    print(f"Scanning files in {directory}...")
    for root, _, files in os.walk(directory):
        for file in files:
            all_files.append((Path(root) / file, Path(root)))
    
    total_files = len(all_files)
    print(f"Found {total_files} files. Starting threaded processing...")

    # Use ThreadPoolExecutor for concurrency
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_file, f, r): f for f, r in all_files}
        
        completed_count = 0
        for future in as_completed(futures):
            completed_count += 1
            if completed_count % 100 == 0:
                print(f"Processed {completed_count}/{total_files} files...", end='\r')
            
            try:
                results = future.result()
                for res in results:
                    # pass
                    log_message(res)
            except Exception as e:
                log_message(f"Error processing file: {e}")
                
    print(f"\nFinished processing {total_files} files.")
    return log_entries

def main():
    if not SOURCE_DIR.exists():
        print(f"Directory {SOURCE_DIR} not found.")
        return
        
    log = process_directory(SOURCE_DIR)
    
    print("\nModernization complete.")
    print(f"Writing log to {MODERNIZE_LOG}...")
    
    with open(MODERNIZE_LOG, "w") as f:
        f.write("# Modernization Log\n\n")
        for entry in log:
            f.write(f"- {entry}\n")

if __name__ == "__main__":
    main()
