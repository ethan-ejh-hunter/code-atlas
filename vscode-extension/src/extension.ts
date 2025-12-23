import * as vscode from 'vscode';
import axios from 'axios';

let commentController: vscode.CommentController;

export function activate(context: vscode.ExtensionContext) {
    console.log('CodeAtlas Annotations active');

    // Create the Comment Controller
    commentController = vscode.comments.createCommentController('codeAtlas', 'CodeAtlas Annotations');
    context.subscriptions.push(commentController);

    // Enable commenting on all files? 
    // The commenting range provider controls where comments can be added.
    commentController.commentingRangeProvider = {
        provideCommentingRanges: (document: vscode.TextDocument, token: vscode.CancellationToken) => {
            const lineCount = document.lineCount;
            // Allow commenting on any line
            return [new vscode.Range(0, 0, lineCount - 1, 0)];
        }
    };

    // Load annotations when active editor changes or document opens
    if (vscode.window.activeTextEditor) {
        updateAnnotations(vscode.window.activeTextEditor.document);
    }

    context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(editor => {
        if (editor) {
            updateAnnotations(editor.document);
        }
    }));

    context.subscriptions.push(vscode.workspace.onDidOpenTextDocument(doc => {
        updateAnnotations(doc);
    }));

    // Handle "Reply" (adding a new note)
    // Note: Our backend currently supports one "note block" per line.
    // If the user "replies", we basically just append or edit.
    // However, the VS Code API is thread-based.
    // We will treat the "thread" as the line's annotation.
    // If a thread exists, "replying" adds to it.
}

async function updateAnnotations(document: vscode.TextDocument) {
    if (document.uri.scheme !== 'file') return;

    const config = vscode.workspace.getConfiguration('codeAtlas');
    const serverUrl = config.get('serverUrl', 'http://localhost:5000');

    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (!workspaceFolder) return;

    // Calculate relative path
    const relPath = vscode.workspace.asRelativePath(document.uri);

    try {
        const response = await axios.get(`${serverUrl}/api/file_annotations`, {
            params: { path: relPath }
        });

        const data = response.data;
        const lineAnnotations = data.line_annotations; // Dict[string, string]

        // Clear existing threads for this file? 
        // We can't easily query "all threads for file", but we can track them map.
        // For simplicity API: dispose all threads we created for this doc?
        // Actually, creating a new thread on the same line might duplicate.
        // We really should track created threads in a Map<uri_string, Thread[]>.
        // TODO: Implement tracking.

        // For now, let's just log what we got
        console.log(`Loaded ${Object.keys(lineAnnotations).length} annotations for ${relPath}`);

        for (const [lineStr, content] of Object.entries(lineAnnotations)) {
            const line = parseInt(lineStr);
            console.log(`Line ${line}: ${content}`);
            // TODO: Create thread
            const range = new vscode.Range(line, 0, line, 0);
            const thread = commentController.createCommentThread(document.uri, range, []);
            thread.canReply = false; // For now

            const comment = new MyComment(
                content as string,
                vscode.CommentMode.Preview,
                { name: 'CodeAtlas' }
            );
            thread.comments = [comment];
        }

    } catch (e) {
        console.error('Failed to fetch annotations', e);
    }
}

class MyComment implements vscode.Comment {
    mode: vscode.CommentMode;
    author: vscode.CommentAuthorInformation;
    body: string | vscode.MarkdownString;

    constructor(body: string, mode: vscode.CommentMode, author: vscode.CommentAuthorInformation) {
        this.body = body;
        this.mode = mode;
        this.author = author;
    }
}

export function deactivate() { }
