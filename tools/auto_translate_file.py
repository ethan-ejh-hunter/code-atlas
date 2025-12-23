import sys
import os
import json
import re
import argparse
from deep_translator import GoogleTranslator
from concurrent.futures import ThreadPoolExecutor
import time

def contains_japanese(text):
    for char in text:
        code = ord(char)
        if (0x3040 <= code <= 0x309f) or \
           (0x30a0 <= code <= 0x30ff) or \
           (0x4e00 <= code <= 0x9fff):
            return True
    return False

def get_line_number(content, index):
    return content.count('\n', 0, index) + 1

def parse_lines(content):
    """
    Parses plain text line-by-line without grouping.
    """
    items = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if line and contains_japanese(line):
            items.append((i + 1, line))
    return items

def parse_sentences(content):
    """
    Parses plain text by treating each line as a potential segment.
    Groups lines into sentences/paragraphs.
    """
    items = []
    lines = content.splitlines()
    
    buffer = ""
    start_line = -1
    
    terminators = ('。', '．', '.', '!', '?', '！', '？')
    
    for i, line in enumerate(lines):
        striped = line.strip()
        
        # Empty line -> Flush
        if not striped:
            if buffer:
                if contains_japanese(buffer):
                    items.append((start_line, buffer))
                buffer = ""
                start_line = -1
            continue
            
        # Start new block
        if start_line == -1:
            start_line = i + 1
            
        # Append
        if buffer:
            buffer += " " + striped # Space separation for English, simple concat for JP? 
            # Actually for mixed JP, spaces are usually fine or ignored.
        else:
            buffer = striped
            
        # Check termination
        if buffer.endswith(terminators):
            if contains_japanese(buffer):
                items.append((start_line, buffer))
            buffer = ""
            start_line = -1
            
    # Flush remaining
    if buffer and contains_japanese(buffer):
        items.append((start_line, buffer))
        
    return items

def parse_and_process(file_path, strategy='sentence'):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return {"error": str(e)}

    # Determine mode based on extension or content?
    # Simple check for code extensions
    is_code = file_path.lower().endswith(('.c', '.h', '.cpp', '.hpp', '.java', '.js', '.py', '.rs', '.go'))
    
    if not is_code:
        if strategy == 'line':
            detected_items = parse_lines(content)
        else:
            detected_items = parse_sentences(content)
    else:
        length = len(content)
        # We want to find Japanese segments and their line numbers
        detected_items = [] # (line_num, text)
    
        i = 0
        while i < length:
            # String Literal
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
                text = content[start_idx+1:i-1] # content inside quotes
                if contains_japanese(text):
                    detected_items.append((get_line_number(content, start_idx), text))
            
            # Single line comment
            elif content[i:i+2] == '//':
                start_idx = i
                end_idx = content.find('\n', i)
                if end_idx == -1: end_idx = length
                
                text = content[start_idx+2:end_idx].strip()
                if contains_japanese(text):
                    detected_items.append((get_line_number(content, start_idx), text))
                i = end_idx

            # Block comment
            elif content[i:i+2] == '/*':
                start_idx = i
                end_idx = content.find('*/', i + 2)
                if end_idx == -1: end_idx = length
                else: end_idx += 2
                
                text = content[start_idx+2:end_idx-2].strip()
                if contains_japanese(text):
                    # For block comments, we might want the start line
                    detected_items.append((get_line_number(content, start_idx), text))
                i = end_idx
                
            else:
                i += 1

    if not detected_items:
        return {"annotations": {}}

    # Deduplicate texts to save API calls
    unique_texts = list(set(item[1] for item in detected_items))
    translations = {}
    
    # Translate concurrently
    translator = GoogleTranslator(source='auto', target='en')
    
    def translate_single(text):
        if not text.strip(): return (text, "")
        try:
            res = translator.translate(text)
            return (text, res)
        except Exception as e:
            return (text, f"[Trans Fail: {str(e)[:20]}]")

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(translate_single, unique_texts))
        
    for text, res in results:
        translations[text] = res

    # Build Result
    annotations = {}
    for line, text in detected_items:
        if text in translations:
            trans = translations[text]
            if trans and trans != text and "[Trans Fail" not in trans:
                # Append if multiple on same line?
                note = f"Translated: {trans}"
                if line in annotations:
                    annotations[line] += f"\n{note}"
                else:
                    annotations[line] = note

    return {"annotations": annotations}

    return {"annotations": annotations}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Auto-translate file.')
    parser.add_argument('file_path', help='Path to the file to translate')
    parser.add_argument('--strategy', choices=['line', 'sentence'], default='sentence', 
                        help='Translation strategy for text files')
    
    args = parser.parse_args()
        
    result = parse_and_process(args.file_path, strategy=args.strategy)
    print(json.dumps(result, indent=2))
