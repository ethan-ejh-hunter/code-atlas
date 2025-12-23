
import sys
import os
import time
import csv
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from deep_translator import GoogleTranslator

CACHE_FILE = "translation_cache.csv"
TRANSLATION_CACHE = {}
CACHE_LOCK = threading.Lock()

PROCESSED_COUNT = 0
TOTAL_FILES = 0
COUNTER_LOCK = threading.Lock()

API_LOCK = threading.Lock()
LAST_API_CALL = 0
MIN_DELAY = 2.0 # Seconds between API calls to be safe

def load_cache():
    global TRANSLATION_CACHE
    if not os.path.exists(CACHE_FILE):
        return
    
    print(f"Loading cache from {CACHE_FILE}...")
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    TRANSLATION_CACHE[row[0]] = row[1]
    except Exception as e:
        print(f"Error loading cache: {e}")


def save_cache_entry(original, translated):
    global TRANSLATION_CACHE
    with CACHE_LOCK:
        if original in TRANSLATION_CACHE:
            return
        
        TRANSLATION_CACHE[original] = translated
        try:
            with open(CACHE_FILE, 'a', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([original, translated])
        except Exception as e:
            print(f"Error saving to cache: {e}")


def batch_translate(texts):
    """
    Translates a list of texts using Google Translator.
    Checks cache first.
    """
    if not texts:
        return []
    
    results = []
    to_fetch = []
    to_fetch_indices = []
    
    # Check cache
    for i, text in enumerate(texts):
        if text in TRANSLATION_CACHE:
            results.append(TRANSLATION_CACHE[text])
        else:
            results.append(None) # Placeholder
            to_fetch.append(text)
            to_fetch_indices.append(i)
            
    if not to_fetch:
        return results
        
    # Translate remaining
    print(f"Fetching {len(to_fetch)} translations from API...")
    
    fetched_results = []
    
    chunk_size = 20
    translator = GoogleTranslator(source='auto', target='en')
    
    for i in range(0, len(to_fetch), chunk_size):
        chunk = to_fetch[i:i+chunk_size]
        try:
            # Rate limiting block
            with API_LOCK:
                global LAST_API_CALL
                elapsed = time.time() - LAST_API_CALL
                if elapsed < MIN_DELAY:
                    time.sleep(MIN_DELAY - elapsed)
                
                try:
                    translated = translator.translate_batch(chunk)
                    fetched_results.extend(translated)
                finally:
                    LAST_API_CALL = time.time()
                    
        except Exception as e:
            print(f"Batch translation error: {e}. Cooling down 30s...")
            time.sleep(30)
            print("Resuming with individual fallbacks...")
            
            for text in chunk:
                # Rate limiting for individual fallback too
                with API_LOCK:
                    elapsed = time.time() - LAST_API_CALL
                    if elapsed < MIN_DELAY:
                        time.sleep(MIN_DELAY - elapsed)
                        
                    try:
                        res = translator.translate(text)
                        fetched_results.append(res)
                    except Exception as ex:
                        print(f"Failed to translate: {text[:20]}... {ex}")
                        fetched_results.append("[Translation Failed]")
                    finally:
                         LAST_API_CALL = time.time()

        
    # Merge and Save
    for i, res in enumerate(fetched_results):
        original_idx = to_fetch_indices[i]
        results[original_idx] = res
        original_text = to_fetch[i]
        if res and "[Translation Failed]" not in res:
            save_cache_entry(original_text, res)
            
    return results

def contains_japanese(text):
    for char in text:
        code = ord(char)
        if (0x3040 <= code <= 0x309f) or \
           (0x30a0 <= code <= 0x30ff) or \
           (0x4e00 <= code <= 0x9fff):
            return True
    return False

def parse_and_process(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    length = len(content)
    segments = [] 
    
    i = 0
    while i < length:
        if content[i] == '"':
            start_idx = i
            i += 1
            while i < length:
                if content[i] == '"':
                     bc = 0
                     j = i - 1
                     while j >= start_idx and content[j] == '\\':
                         bc += 1
                         j -= 1
                     if bc % 2 == 0:
                         break
                i += 1
            i += 1
            segments.append({'type': 'string_literal', 'text': content[start_idx:i]})
            
        elif content[i] == "'":
            start_idx = i
            i += 1
            while i < length:
                if content[i] == "'":
                     bc = 0
                     j = i - 1
                     while j >= start_idx and content[j] == '\\':
                         bc += 1
                         j -= 1
                     if bc % 2 == 0:
                         break
                i += 1
            i += 1
            segments.append({'type': 'code', 'text': content[start_idx:i]})

        elif content[i:i+2] == '//':
            start_idx = i
            end_idx = content.find('\n', i)
            if end_idx == -1: end_idx = length
            
            raw = content[start_idx:end_idx]
            content_text = raw[2:].strip()
            
            # Indentation
            j = start_idx - 1
            while j >= 0 and content[j] in ' \t': j -= 1
            if j < 0 or content[j] == '\n': indentation = content[j+1:start_idx]
            else:
                last_nl = content.rfind('\n', 0, start_idx)
                if last_nl == -1: line_prefix = content[0:start_idx]
                else: line_prefix = content[last_nl+1:start_idx]
                indentation = ""
                for char in line_prefix:
                    if char == '\t': indentation += '\t'
                    else: indentation += ' '
            
            segments.append({
                'type': 'comment_single',
                'raw': raw,
                'content_to_translate': content_text,
                'indentation': indentation
            })
            i = end_idx

        elif content[i:i+2] == '/*':
            start_idx = i
            end_idx = content.find('*/', i + 2)
            if end_idx == -1: end_idx = length
            else: end_idx += 2
            
            raw = content[start_idx:end_idx]
            inner = raw[2:-2].strip()
            
            last_nl = content.rfind('\n', 0, start_idx)
            if last_nl == -1: line_prefix = content[0:start_idx]
            else: line_prefix = content[last_nl+1:start_idx]
            indentation = ""
            for char in line_prefix:
                if char == '\t': indentation += '\t'
                else: indentation += ' '
                
            segments.append({
                'type': 'comment_block',
                'raw': raw,
                'content_to_translate': inner,
                'indentation': indentation
            })
            i = end_idx
            
        else:
            segments.append({'type': 'code', 'text': content[i]})
            i += 1

    # Cleanup segments
    consolidated = []
    curr_code = []
    for s in segments:
        if s['type'] == 'code':
            curr_code.append(s['text'])
        else:
            if curr_code:
                consolidated.append({'type': 'code', 'text': "".join(curr_code)})
                curr_code = []
            consolidated.append(s)
    if curr_code:
        consolidated.append({'type': 'code', 'text': "".join(curr_code)})
        
    return consolidated

def is_already_translated(segments, idx):
    """
    Look ahead to see if the next significant comment is a translation.
    """
    for j in range(idx + 1, len(segments)):
        seg = segments[j]
        if seg['type'] == 'code':
            # Verify if it's just whitespace/newlines
            if not seg['text'].strip():
                continue
            else:
                return False # Hit code, so no translation immediately following
        elif seg['type'] in ('comment_single', 'comment_block'):
            if seg['content_to_translate'].lower().startswith("translated:"):
                return True
            else:
                return False
        else:
            return False
    return False

def process_file_content(file_path):
    print(f"  Parsing {file_path}...")
    segments = parse_and_process(file_path)
    
    candidates = []
    indices = []
    
    for i, seg in enumerate(segments):
        text = None
        if seg['type'] in ('comment_single', 'comment_block'):
            t = seg['content_to_translate']
            if contains_japanese(t):
                text = t
        elif seg['type'] == 'string_literal':
            t = seg['text'][1:-1]
            if contains_japanese(t):
                text = t
        
        if text:
            print(f"    Found: {text[:20]}...")
            # Check idempotency
            if is_already_translated(segments, i):
                # print(f"    Skipping (already translated): {text[:20]}...")
                continue
                
            candidates.append(text)
            indices.append(i)
    
    if not candidates:
        return None
        
    print(f"  Translating {len(candidates)} items...")
    translations = batch_translate(candidates)
    
    # Attach translations
    for i, trans in enumerate(translations):
        if not trans or "[Translation Failed]" in trans: continue
        
        idx = indices[i]
        seg = segments[idx]
        original = candidates[i]
        
        if trans.strip() == original.strip(): continue
        
        if seg['type'] == 'string_literal':
             if trans.strip() == seg['text'][1:-1].strip(): continue
             seg['string_translation'] = trans
        else:
             seg['translation_appendix'] = f"\n{seg.get('indentation','')}//Translated: {trans}"

    # Reconstruct
    output = []
    pending_strs = []
    
    for seg in segments:
        if seg['type'] == 'string_literal':
            output.append(seg['text'])
            if 'string_translation' in seg:
                pending_strs.append(seg['string_translation'])
                
        elif seg['type'] == 'comment_single':
            output.append(seg['raw'])
            if 'translation_appendix' in seg:
                output.append(seg['translation_appendix'])
            
            if pending_strs:
                indent = seg.get('indentation', '')
                for s in pending_strs:
                    output.append(f"\n{indent}//Translated: \"{s}\"")
                pending_strs = []
                
        elif seg['type'] == 'comment_block':
            output.append(seg['raw'])
            if 'translation_appendix' in seg:
                output.append(seg['translation_appendix'])
                
        elif seg['type'] == 'code':
            text = seg['text']
            start = 0
            while True:
                nl = text.find('\n', start)
                if nl == -1:
                    output.append(text[start:])
                    break
                
                output.append(text[start:nl+1])
                
                if pending_strs:
                    # Just append logic
                    # Try to use a tab?
                    for s in pending_strs:
                        output.append(f"\t//Translated: \"{s}\"\n")
                    pending_strs = []
                
                start = nl + 1
                
    if pending_strs:
        output.append("\n")
        for s in pending_strs:
            output.append(f"//Translated: \"{s}\"\n")
            
    return "".join(output)



def safe_process_file(full_path):
    global PROCESSED_COUNT
    try:
        new_content = process_file_content(full_path)
        if new_content:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
    except Exception as e:
        print(f"Error processing {full_path}: {e}")
        
    with COUNTER_LOCK:
        PROCESSED_COUNT += 1
        if PROCESSED_COUNT % 100 == 0:
            sys.stdout.write(f"Processed {PROCESSED_COUNT}/{TOTAL_FILES} files...\r")
            sys.stdout.flush()


def main(target_path):
    load_cache()
    
    files_to_process = []
    if os.path.isfile(target_path):
        files_to_process.append(target_path)
    else:
        print(f"Scanning {target_path} for files...")
        for root, dirs, files in os.walk(target_path):
            for file in files:
                if file.endswith('.c') or file.endswith('.h'):
                    files_to_process.append(os.path.join(root, file))
    
    total = len(files_to_process)
    global TOTAL_FILES
    TOTAL_FILES = total
    print(f"Found {total} files. Starting threaded processing (max 8 workers)...")
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        executor.map(safe_process_file, files_to_process)
    
    print("Processing complete.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python translate_comments.py <path>")
        sys.exit(1)
    
    main(sys.argv[1])
