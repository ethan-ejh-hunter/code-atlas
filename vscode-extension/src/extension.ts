import * as vscode from 'vscode';
import axios from 'axios';

let commentController: vscode.CommentController;
const threadMap = new Map<string, vscode.CommentThread>(); // Key: uri.toString() + '#' + line

export function activate(context: vscode.ExtensionContext) {
    console.log('CodeAtlas Annotations active');

    commentController = vscode.comments.createCommentController('codeAtlas', 'CodeAtlas Annotations');
    context.subscriptions.push(commentController);

    // Allow commenting on any line
    commentController.commentingRangeProvider = {
        provideCommentingRanges: (document: vscode.TextDocument, token: vscode.CancellationToken) => {
            const lineCount = document.lineCount;
            return [new vscode.Range(0, 0, lineCount - 1, 0)];
        }
    };

    // Load on open/change
    context.subscriptions.push(vscode.window.onDidChangeActiveTextEditor(editor => {
        if (editor) updateAnnotations(editor.document);
    }));
    context.subscriptions.push(vscode.workspace.onDidOpenTextDocument(doc => {
        updateAnnotations(doc);
    }));
    if (vscode.window.activeTextEditor) {
        updateAnnotations(vscode.window.activeTextEditor.document);
    }

    // Command to refresh
    context.subscriptions.push(vscode.commands.registerCommand('codeAtlas.refresh', () => {
        if (vscode.window.activeTextEditor) {
            updateAnnotations(vscode.window.activeTextEditor.document);
        }
    }));

    // Command to SAVE comment (Reply)
    context.subscriptions.push(vscode.commands.registerCommand('codeAtlas.saveComment', async (reply: vscode.CommentReply) => {
        // reply.thread is the thread
        // reply.text is the content

        const thread = reply.thread;
        const text = reply.text;

        if (!thread.range) return; // Should not happen based on our creation logic

        const line = thread.range.start.line;
        const document = vscode.workspace.textDocuments.find(d => d.uri.toString() === thread.uri.toString());

        if (!document) return;

        await saveAnnotation(document, line, text);

        // After save, refresh
        // Optimistic update:
        const comment = new MyComment(
            text,
            vscode.CommentMode.Preview,
            { name: 'CodeAtlas' }
        );
        thread.comments = [comment];
        thread.canReply = false; // Disable further replies for now (one note per line)

        // Actually, we should pull from server to be sure, but let's assume success
    }));
}

async function saveAnnotation(document: vscode.TextDocument, line: number, content: string) {
    const config = vscode.workspace.getConfiguration('codeAtlas');
    const serverUrl = config.get('serverUrl', 'http://localhost:5000');
    const relPath = vscode.workspace.asRelativePath(document.uri);

    try {
        await axios.post(`${serverUrl}/api/annotate`, {
            file_path: relPath,
            line: line,
            content: content,
            type: 'manual'
        });
        vscode.window.showInformationMessage('Annotation saved.');
    } catch (e: any) {
        vscode.window.showErrorMessage(`Failed to save annotation: ${e.message}`);
    }
}

async function updateAnnotations(document: vscode.TextDocument) {
    if (document.uri.scheme !== 'file') return;

    const config = vscode.workspace.getConfiguration('codeAtlas');
    const serverUrl = config.get('serverUrl', 'http://localhost:5000');

    // We need a workspace-relative path
    const relPath = vscode.workspace.asRelativePath(document.uri);

    try {
        const response = await axios.get(`${serverUrl}/api/file_annotations`, {
            params: { path: relPath }
        });

        const data = response.data;
        if (!data || !data.line_annotations) return;

        const lineAnnotations = data.line_annotations as Record<string, string>;

        // 1. Identify lines that have annotations
        const activeLines = new Set<number>();

        for (const [lineStr, content] of Object.entries(lineAnnotations)) {
            const line = parseInt(lineStr);
            activeLines.add(line);

            const key = getThreadKey(document.uri, line);
            let thread = threadMap.get(key);

            if (!thread) {
                // Create new thread
                const range = new vscode.Range(line, 0, line, 0);
                thread = commentController.createCommentThread(document.uri, range, []);
                threadMap.set(key, thread);
            }

            // Update comments
            thread.canReply = false; // Read-only view + edit button maybe? For now just view.
            thread.collapsibleState = vscode.CommentThreadCollapsibleState.Expanded;

            if (thread.comments.length === 0 || (thread.comments[0].body as vscode.MarkdownString).value !== content) {
                const comment = new MyComment(
                    content,
                    vscode.CommentMode.Preview,
                    { name: 'CodeAtlas' }
                );
                thread.comments = [comment];
            }
        }

        // 2. Cleanup threads
        const uriStr = document.uri.toString();
        // Convert map keys to array to avoid modification issues
        const keys = Array.from(threadMap.keys());
        for (const key of keys) {
            if (key.startsWith(uriStr + '#')) {
                const thread = threadMap.get(key);
                if (thread && thread.range) {
                    const line = thread.range.start.line;
                    if (!activeLines.has(line)) {
                        // If it has no comments, dispose it (unless user is typing?)
                        // User typing thread has comments=[] usually?
                        if (thread.comments.length > 0) {
                            thread.dispose();
                            threadMap.delete(key);
                        }
                    }
                }
            }
        }

    } catch (e) {
        // console.error(`Failed to fetch annotations for ${relPath}:`, e);
    }
}

function getThreadKey(uri: vscode.Uri, line: number) {
    return `${uri.toString()}#${line}`;
}

class MyComment implements vscode.Comment {
    mode: vscode.CommentMode;
    author: vscode.CommentAuthorInformation;
    body: vscode.MarkdownString;

    constructor(body: string, mode: vscode.CommentMode, author: vscode.CommentAuthorInformation) {
        this.body = new vscode.MarkdownString(body);
        this.mode = mode;
        this.author = author;
    }
}

export function deactivate() { }
