import sqlite3
import os
import sys
import subprocess
import markdown
import re
import json

from pygments import highlight
from pygments.lexers import get_lexer_for_filename, TextLexer
from pygments.formatters import HtmlFormatter
from flask import Flask, render_template, request, jsonify, abort
from database import init_db, add_file, get_db

# Adjust path to import custom tools if needed
sys.path.append(os.getcwd())

app = Flask(__name__)
SOURCE_ROOT = os.path.abspath("source-code")

# --- Toolbelt Registration ---
TOOLS = {
    "extract_sjis": {
        "name": "Extract Shift-JIS Text",
        "description": "Extracts Japanese string literals from binary files.",
        "command": ["python3", "tools/extract_sjis.py"],
        "extensions": []
    },
    "file_info": {
        "name": "File Info",
        "description": "Run the 'file' command to detect type.",
        "command": ["file"],
        "extensions": []
    },
    "auto_translate_sentence": {
        "name": "Translate (Global/Sentence)",
        "description": "Detects Japanese (SJIS/UTF8) and translates grouped sentences.",
        "command": ["python3", "tools/auto_translate_file.py", "--strategy", "sentence"],
        "extensions": []
    },
    "auto_translate_line": {
        "name": "Translate (Line-by-Line)",
        "description": "Translates every specific line individually, no grouping.",
        "command": ["python3", "tools/auto_translate_file.py", "--strategy", "line"],
        "extensions": []
    },
    "format_code": {
        "name": "Format C Code",
        "description": "Formats code using clang-format.",
        "command": ["clang-format", "-i"],
        "extensions": [".c", ".h"]
    },
    "open_vscode": {
        "name": "Open Folder in VS Code",
        "description": "Opens the parent directory of this file in VS Code.",
        "command": ["python3", "tools/open_vscode.py"],
        "extensions": []
    }
}

@app.before_request
def startup_check():
    if not getattr(app, 'db_initialized', False):
        init_db()
        app.db_initialized = True

def scan_files():
    print("Scanning source-code directory...")
    count = 0
    with get_db() as conn:
        for root, dirs, files in os.walk(SOURCE_ROOT):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, start=os.getcwd())
                
                # Sanitize for DB (remove surrogates)
                try:
                    rel_path.encode('utf-8')
                    file.encode('utf-8')
                except UnicodeEncodeError:
                    # Replace bad chars
                    rel_path = rel_path.encode('utf-8', 'replace').decode('utf-8')
                    file = file.encode('utf-8', 'replace').decode('utf-8')

                # Check if exists
                cur = conn.execute("SELECT id FROM files WHERE path = ?", (rel_path,))
                if not cur.fetchone():
                    conn.execute("INSERT INTO files (path, filename) VALUES (?, ?)", (rel_path, file))
                    count += 1
        conn.commit()
    print(f"Scanned {count} new files.")

def parse_file_annotations(md_blob):
    """
    Parses a combined markdown blob into a global note and a dictionary of line notes.
    Format:
    [Global Markdown]
    @lines
    # [number]
    [Line Markdown]
    """
    if not md_blob:
        return "", {}, ""
        
    global_md = md_blob
    lines_dict = {}
    
    if "@lines" in md_blob:
        parts = md_blob.split("@lines", 1)
        global_md = parts[0].strip()
        lines_part = parts[1].strip()
        
        # Split by "# [number]" pattern at START of line
        import re
        # This matches "# 123" at the start of a line, then captures the rest of the content until the next match
        line_splits = re.split(r'^#\s*(\d+)\s*', lines_part, flags=re.MULTILINE)
        
        # re.split with groups returns [before, group1, content1, group2, content2...]
        for i in range(1, len(line_splits), 2):
            line_num = int(line_splits[i])
            content = line_splits[i+1].strip()
            if content:
                lines_dict[line_num] = markdown.markdown(content)

    global_html = markdown.markdown(global_md) if global_md else ""
    return global_html, lines_dict, md_blob, lines_dict # Return raw dict as 4th element (temporary hack or just use lines_dict? lines_dict IS raw)

def parse_file_annotations_raw(md_blob):
    """
    Returns global_raw, lines_raw_dict
    """
    if not md_blob:
        return "", {}
        
    global_md = md_blob
    lines_dict = {}
    
    if "@lines" in md_blob:
        parts = md_blob.split("@lines", 1)
        global_md = parts[0].strip()
        lines_part = parts[1].strip()
        
        # Split by "# [number]" pattern at START of line
        import re
        line_splits = re.split(r'^#\s*(\d+)\s*', lines_part, flags=re.MULTILINE)
        
        for i in range(1, len(line_splits), 2):
            line_num = int(line_splits[i])
            content = line_splits[i+1].strip()
            if content:
                lines_dict[line_num] = content
                
    return global_md, lines_dict

def reconstruct_markdown(global_md, lines_dict):
    """
    Rebuilds the master blob from components.
    """
    blob = global_md.strip() + "\n\n"
    if lines_dict:
        blob += "@lines\n"
        # Sort by line number
        for lnum in sorted(lines_dict.keys()):
            content = lines_dict[lnum].strip()
            if content:
                blob += f"# {lnum}\n{content}\n"
    return blob.strip()

@app.route('/')
def index():
    # Simple file tree view
    # For MVP, just list top directories or something? 
    # Let's just list everything in a flat list for now or use JS to fetch.
    return render_template('index.html')


@app.route('/api/files')
def api_files():
    # Deprecated for full tree, but kept for legacy?
    pass

@app.route('/api/tree')
def api_tree():
    req_path = request.args.get('path', '')
    
    # Security: prevent breakout
    if '..' in req_path or req_path.startswith('/'):
         return jsonify([]), 400
         
    abs_path = os.path.join(SOURCE_ROOT, req_path)
    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        return jsonify([]), 404
        
    entries = []
    try:
        with os.scandir(abs_path) as it:
            for entry in it:
                # Type
                is_dir = entry.is_dir()
                entries.append({
                    "name": entry.name,
                    "path": os.path.join(req_path, entry.name),
                    "type": "dir" if is_dir else "file"
                })
    except PermissionError:
        pass
        
    entries.sort(key=lambda x: (0 if x['type']=='dir' else 1, x['name'].lower()))
    return jsonify(entries)

@app.route('/api/folder_details')
def api_folder_details():
    req_path = request.args.get('path', '')
    abs_path = os.path.join(SOURCE_ROOT, req_path)
    
    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        return jsonify({"error": "Path not found"}), 404

    # Ensure indexed
    conn = get_db()
    file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (req_path,)).fetchone()
    if not file_rec:
         try:
             conn.execute("INSERT INTO files (path, filename, file_type) VALUES (?, ?, ?)", 
                         (req_path, os.path.basename(req_path), 'dir'))
             conn.commit()
             file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (req_path,)).fetchone()
         except: pass
    
    notes_html = ""
    notes_raw = ""
    if file_rec:
        cur = conn.execute("SELECT content FROM annotations WHERE file_id = ? AND type = 'manual' ORDER BY id DESC LIMIT 1", (file_rec['id'],))
        row = cur.fetchone()
        if row:
            notes_raw = row['content']
            notes_html = markdown.markdown(notes_raw)
            
    # Children
    children = []
    with os.scandir(abs_path) as it:
        for entry in it:
            children.append({
                "name": entry.name,
                "path": os.path.join(req_path, entry.name),
                "type": "dir" if entry.is_dir() else "file"
            })
    children.sort(key=lambda x: (0 if x['type']=='dir' else 1, x['name'].lower()))
    
    return jsonify({
        "name": os.path.basename(req_path),
        "path": req_path,
        "notes_html": notes_html,
        "notes_raw": notes_raw,
        "children": children
    })


@app.route('/view/<path:file_path>')
def view_file(file_path):
    # Security check: ensure path is within source-code
    conn = get_db()
    # Try direct path
    abs_path = os.path.abspath(file_path)
    
    # If not found, try prefixing 'source-code' (fix for Tree API mismatch)
    if not os.path.exists(abs_path):
        alt_path = os.path.join("source-code", file_path)
        if os.path.exists(os.path.abspath(alt_path)):
            file_path = alt_path
            abs_path = os.path.abspath(alt_path)

    if not abs_path.startswith(SOURCE_ROOT):
        # Allow checking tools/ etc if we want?
        pass # Allow for now if relative path is correct
    
    if not os.path.exists(abs_path):
        return "File not found", 404
        
    tree_path = os.path.relpath(abs_path, SOURCE_ROOT)
    if tree_path == ".": tree_path = ""

    # Handle Directory
    if os.path.isdir(abs_path):
         # Ensure indexed (for annotations)
         file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (tree_path,)).fetchone()
         if not file_rec:
             conn.execute("INSERT INTO files (path, filename, file_type) VALUES (?, ?, ?)", 
                         (tree_path, os.path.basename(tree_path), 'dir'))
             conn.commit()
             file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (tree_path,)).fetchone()
             
         file_id = file_rec['id']
         
         # Fetch annotations
         cur = conn.execute("SELECT * FROM annotations WHERE file_id = ?", (file_id,))
         annotations = [dict(row) for row in cur.fetchall()]
         
         # List children
         entries = []
         with os.scandir(abs_path) as it:
            for entry in it:
                entries.append({
                    "name": entry.name,
                    "path": os.path.join(tree_path, entry.name),
                    "type": "dir" if entry.is_dir() else "file"
                })
         entries.sort(key=lambda x: (0 if x['type']=='dir' else 1, x['name'].lower()))

         # Pass tools (e.g. open_vscode)
         folder_tools = {
             "open_vscode": TOOLS["open_vscode"]
         }

         return render_template('view_folder.html',
                                file_path=tree_path,
                                tree_path=tree_path,
                                name=os.path.basename(abs_path),
                                annotations=annotations,
                                children=entries,
                                tools=folder_tools)

    # Handle File
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            is_binary = False
    except:
        content = "[Binary File]"
        is_binary = True

    # Fetch annotations
    conn = get_db()
    # Need to look up file_id by path
    # If path in DB is relative 'source-code/...', ensure we match
    # The file_path arg comes from URL, likely relative.
    
    file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (tree_path,)).fetchone()
    if not file_rec:
        conn.execute("INSERT INTO files (path, filename, file_type) VALUES (?, ?, ?)", 
                    (tree_path, os.path.basename(abs_path), 'file'))
        conn.commit()
        file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (tree_path,)).fetchone()
    
    global_notes_html = ""
    line_annotations = {}
    lines_raw = {}
    notes_raw = ""

    if file_rec:
        # Fetch the master annotation (line 0)
        cur = conn.execute("SELECT content FROM annotations WHERE file_id = ? AND line_number = 0 ORDER BY created_at DESC LIMIT 1", (file_rec['id'],))
        row = cur.fetchone()
        if row:
            # We need both HTML for display and RAW for editing
            global_raw, lines_raw = parse_file_annotations_raw(row['content'])
            
            # HTML for display
            global_notes_html = markdown.markdown(global_raw) if global_raw else ""
            line_annotations = {k: markdown.markdown(v) for k, v in lines_raw.items()}
            notes_raw = row['content']

    # Syntax Highlighting
    from pygments.lexers.c_cpp import CLexer
    
    if tree_path.lower().endswith(('.c', '.h')):
        lexer = CLexer(stripnl=False, stripall=False)
    else:
        try:
            lexer = get_lexer_for_filename(tree_path, stripnl=False, stripall=False)
        except:
            lexer = TextLexer(stripnl=False, stripall=False)
    
    style_name = 'tango'
    formatter = HtmlFormatter(nowrap=True, style=style_name)
    # Highlight the whole content, then split into lines
    # This ensures multiline comments/tokens are handled correctly
    full_highlighted = highlight(content, lexer, formatter)
    highlighted_lines = full_highlighted.splitlines()

    pygments_css = HtmlFormatter(style=style_name).get_style_defs('.highlight')

    # Filter tools based on extensions
    available_tools = {}
    for k, t in TOOLS.items():
        if not t.get('extensions') or tree_path.lower().endswith(tuple(t['extensions'])):
            available_tools[k] = t

    return render_template('view_file.html', 
                           file_path=tree_path, 
                           tree_path=tree_path,
                           content=content,
                           highlighted_lines=highlighted_lines,
                           pygments_css=pygments_css,
                           is_binary=is_binary,
                           global_notes_html=global_notes_html,
                           line_annotations=line_annotations,
                           lines_raw=lines_raw,
                           notes_raw=notes_raw,
                           tools=available_tools)

@app.route('/api/run_tool', methods=['POST'])
def run_tool():
    data = request.json
    tool_key = data.get('tool')
    file_path = data.get('file_path')
    
    if tool_key not in TOOLS:
        return jsonify({"error": "Unknown tool"}), 400
        
    tool_def = TOOLS[tool_key]
    
    # Path resolution logic (same as view_file)
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        alt_path = os.path.join("source-code", file_path)
        if os.path.exists(os.path.abspath(alt_path)):
            abs_path = os.path.abspath(alt_path)
    
    cmd = tool_def['command'] + [abs_path]
    print(f"Running tool: {cmd}")
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = res.stdout + "\n" + res.stderr
        
        # Check if output is JSON with annotations
        if tool_key.startswith('auto_translate'):
            try:
                # Find the JSON part if there is mixed output
                json_start = output.find('{')
                if json_start != -1:
                    json_str = output[json_start:]
                    result = json.loads(json_str)
                    
                    if "annotations" in result:
                         count = 0
                         conn = get_db()
                         # Get file_id
                         # file_path might be relative or absolute, need exact match
                         # We rely on the request passing the correct tree path
                         rel_path = data.get('file_path') 
                         
                         file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (rel_path,)).fetchone()
                         if file_rec:
                             file_id = file_rec['id']
                             # Get master
                             cur = conn.execute("SELECT content FROM annotations WHERE file_id = ? AND line_number = 0 ORDER BY created_at DESC LIMIT 1", (file_id,))
                             row = cur.fetchone()
                             current_blob = row['content'] if row else ""
                             global_raw, lines_raw = parse_file_annotations_raw(current_blob)
                             
                             # Merge
                             for lnum_str, note in result['annotations'].items():
                                 lnum = int(lnum_str)
                                 # Append if exists?
                                 if lnum in lines_raw:
                                     if note not in lines_raw[lnum]:
                                         lines_raw[lnum] += f"\n\n{note}"
                                 else:
                                     lines_raw[lnum] = note
                                 count += 1
                                 
                             # Reconstruct and save
                             if count > 0:
                                 new_blob = reconstruct_markdown(global_raw, lines_raw)
                                 conn.execute(
                                    "INSERT INTO annotations (file_id, line_number, content, type) VALUES (?, ?, ?, ?)",
                                    (file_id, 0, new_blob, 'auto_translate')
                                 )
                                 conn.commit()
                                 output = f"Successfully translated and added {count} annotations.\nRaw Output:\n{output}"
                         else:
                             output = "Error: File not found in DB for annotation update.\n" + output
                         conn.close()
            except Exception as e:
                output = f"Error processing translation results: {e}\nRaw Output:\n{output}"

        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"})



@app.route('/api/file_annotations')
def api_file_annotations():
    req_path = request.args.get('path', '')
    print(f"DEBUG: api_file_annotations called with path='{req_path}'")
    
    conn = get_db()
    
    # Strategy 1: Exact Match (assuming req_path is relative to scan root)
    file_rec = conn.execute("SELECT id, path FROM files WHERE path = ?", (req_path,)).fetchone()
    
    # Strategy 2: Filename Match (Optimized with Index)
    if not file_rec:
        # Extract filename (basename) from req_path
        # Use substring after last / (or full string if no /)
        # Note: req_path might use \ on Windows client, but we normalized it in client??
        # We should handle separators robustly here just in case.
        import os
        base_name = req_path.replace('\\', '/').split('/')[-1]
        
        # print(f"DEBUG: Exact match failed. Searching for filename='{base_name}'")
        
        # Query index
        cur = conn.execute("SELECT id, path FROM files WHERE filename = ?", (base_name,))
        candidates = cur.fetchall()
        
        # Filter in Python (fast since usually few files have same name)
        # We want path ending with req_path (normalized)
        search_suffix = req_path.replace('\\', '/')
        
        matches = []
        for c in candidates:
             # Normalize DB path for comparison
             result_path = c['path'].replace('\\', '/')
             if result_path.endswith(search_suffix):
                 matches.append(c)
        
        if len(matches) == 1:
            file_rec = matches[0]
            # print(f"DEBUG: Found single suffix match via index: {file_rec['path']}")
        elif len(matches) > 1:
            # print(f"DEBUG: Found {len(matches)} matches via index. Picking first.")
            file_rec = matches[0]
        
        if len(matches) == 1:
            file_rec = matches[0]
            print(f"DEBUG: Found single suffix match: {file_rec['path']}")
        elif len(matches) > 1:
            # Ambiguous. Try to pick the shortest one? Or one that matches mostly?
            print(f"DEBUG: Found {len(matches)} matches. Picking first.")
            file_rec = matches[0]
        else:
             print("DEBUG: No matches found.")

    global_md = ""
    lines_dict = {}
    db_path = ""
    
    if file_rec:
        db_path = file_rec['path']
        cur = conn.execute("SELECT content FROM annotations WHERE file_id = ? AND line_number = 0 ORDER BY created_at DESC LIMIT 1", (file_rec['id'],))
        row = cur.fetchone()
        if row:
            global_md, lines_dict = parse_file_annotations_raw(row['content'])
    else:
        # 404 if not found? Or just return empty?
        # User saw 404 in logs, so let's stick to 404 if truly not found to help debug
        return jsonify({"error": "File not found in DB"}), 404

    return jsonify({
        "path": db_path,
        "global_annotations": global_md,
        "line_annotations": lines_dict
    })

@app.route('/api/annotate', methods=['POST'])
def add_annotation():
    data = request.json
    print(f"DEBUG: add_annotation called with data={data}")
    
    path = data.get('file_path')
    line = int(data.get('line', 0))
    content = data.get('content', '')
    kind = data.get('type', 'manual')
    
    conn = get_db()
    
    # Resolve path (Same logic as above, essential!)
    file_rec = conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
    
    if not file_rec:
        # Optimized lookup
        base_name = path.replace('\\', '/').split('/')[-1]
        search_suffix = path.replace('\\', '/')
        
        cur = conn.execute("SELECT id, path FROM files WHERE filename = ?", (base_name,))
        candidates = cur.fetchall()
        
        matches = []
        for c in candidates:
             if c['path'].replace('\\', '/').endswith(search_suffix):
                 matches.append(c)

        if len(matches) > 0:
             file_rec = matches[0]
    
    if not file_rec:
        print("DEBUG: File not indexed for annotation.")
        return jsonify({"error": "File not indexed"}), 404
        
    file_id = file_rec['id']
    
    # Fetch current master blob
    cur = conn.execute("SELECT content FROM annotations WHERE file_id = ? AND line_number = 0 ORDER BY created_at DESC LIMIT 1", (file_id,))
    row = cur.fetchone()
    current_blob = row['content'] if row else ""
    
    # Parse existing
    global_raw, lines_raw = parse_file_annotations_raw(current_blob)
    
    # Update logic
    if line == 0:
        new_blob = content
    else:
        if content.strip() == "":
            if line in lines_raw: del lines_raw[line]
        else:
            lines_raw[line] = content
        new_blob = reconstruct_markdown(global_raw, lines_raw)
    
    conn.execute(
        "INSERT INTO annotations (file_id, line_number, content, type) VALUES (?, ?, ?, ?)",
        (file_id, 0, new_blob, kind)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success"})


# CLI command to scan
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='CodeAtlas Server')
    parser.add_argument('command', nargs='?', help='Command to run (e.g., scan)')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on')
    
    args = parser.parse_args()
    
    if args.command == 'scan':
        init_db()
        scan_files()
    else:
        print(f"Starting CodeAtlas on port {args.port}...")
        app.run(host='0.0.0.0', port=args.port, debug=True)
