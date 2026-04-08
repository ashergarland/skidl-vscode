import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

// Module-level log so we know if VS Code even loads this file
console.log("[SKiDL] extension.ts module loaded");

let client: LanguageClient | undefined;
let outputChannel: vscode.OutputChannel;

export async function activate(context: vscode.ExtensionContext) {
  console.log("[SKiDL] activate() called");
  try {
  outputChannel = vscode.window.createOutputChannel("SKiDL Language Server");
  outputChannel.appendLine(`SKiDL Language Server v${context.extension.packageJSON.version} activating...`);
  outputChannel.appendLine(`Extension path: ${context.extensionPath}`);
  outputChannel.appendLine(`Platform: ${process.platform}, LOCALAPPDATA: ${process.env.LOCALAPPDATA || '(not set)'}`);
  outputChannel.show(true); // Force the output panel open
  const config = vscode.workspace.getConfiguration("skidl");
  const pythonPath = getPythonPath(config);
  outputChannel.appendLine(`Detected Python path: ${pythonPath}`);
  outputChannel.appendLine(`Python exists on disk: ${fs.existsSync(pythonPath)}`);
  console.log(`[SKiDL] Python path: ${pythonPath}, exists: ${fs.existsSync(pythonPath)}`);
  const serverModule = context.asAbsolutePath(
    path.join("lsp_server", "server.py")
  );

  // Ensure Python server dependencies are installed
  console.log("[SKiDL] Checking Python dependencies...");
  const depsOk = await ensureDependencies(pythonPath);
  console.log(`[SKiDL] Dependencies check result: ${depsOk}`);
  if (!depsOk) {
    vscode.window.showErrorMessage(
      "SKiDL Language Server: Failed to install Python dependencies (pygls, lsprotocol, mcp). " +
      "Please install them manually: pip install pygls lsprotocol mcp"
    );
    return;
  }

  // Command: setup MCP integration
  const mcpSetupCmd = vscode.commands.registerCommand(
    "skidl.setupMcpServer",
    async () => {
      const mcpPath = context.asAbsolutePath(path.join("mcp_server", "server.py"));
      const picked = await vscode.window.showQuickPick(
        [
          { label: "VS Code (workspace)", description: "Write .vscode/mcp.json in current workspace", id: "vscode" },
          { label: "Claude Desktop", description: "Update Claude Desktop config file", id: "claude" },
          { label: "Copy to clipboard", description: "Copy JSON config snippet to clipboard", id: "clipboard" },
        ],
        { placeHolder: "Where should the MCP server be configured?" }
      );
      if (!picked) { return; }

      const snippet = buildMcpConfigSnippet(pythonPath, mcpPath, config);

      if (picked.id === "vscode") {
        await writeVsCodeMcpConfig(snippet);
      } else if (picked.id === "claude") {
        await writeClaudeDesktopConfig(snippet);
      } else {
        await vscode.env.clipboard.writeText(JSON.stringify(snippet, null, 2));
        vscode.window.showInformationMessage("MCP config copied to clipboard.");
      }
    }
  );
  context.subscriptions.push(mcpSetupCmd);

  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: [serverModule],
    transport: TransportKind.stdio,
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "python" }],
    synchronize: {
      configurationSection: "skidl",
    },
    initializationOptions: {
      kicadSymbolDir: config.get<string>("kicadSymbolDir", ""),
      kicadFootprintDir: config.get<string>("kicadFootprintDir", ""),
      enableDiagnostics: config.get<boolean>("enableDiagnostics", true),
      enableAutocomplete: config.get<boolean>("enableAutocomplete", true),
      enableHover: config.get<boolean>("enableHover", true),
    },
  };

  client = new LanguageClient(
    "skidlLanguageServer",
    "SKiDL Language Server",
    serverOptions,
    clientOptions
  );

  // Status bar click: cache-aware refresh (fast if nothing changed)
  const refreshCmd = vscode.commands.registerCommand(
    "skidl.refreshIndex",
    () => {
      if (client) {
        client.sendNotification("skidl/refreshIndex");
      }
    }
  );
  context.subscriptions.push(refreshCmd);

  // Command palette: force full re-parse ignoring cache
  const rebuildCmd = vscode.commands.registerCommand(
    "skidl.rebuildIndex",
    () => {
      if (client) {
        client.sendNotification("skidl/rebuildIndex");
      }
    }
  );
  context.subscriptions.push(rebuildCmd);

  // Status bar item — created and shown before client starts so we catch early notifications
  const statusItem = vscode.window.createStatusBarItem("skidl.status", vscode.StatusBarAlignment.Left, 0);
  statusItem.name = "SKiDL";
  statusItem.text = "$(loading~spin) SKiDL: Starting...";
  statusItem.tooltip = "SKiDL Language Server is starting";
  statusItem.command = "skidl.refreshIndex";
  statusItem.show();
  context.subscriptions.push(statusItem);

  // Register notification handlers BEFORE starting the client
  // so we don't miss fast cached loads
  client.onNotification("skidl/indexStart", () => {
    console.log("[SKiDL] Index build started");
    outputChannel.appendLine("Indexing KiCad libraries...");
    statusItem.text = "$(loading~spin) SKiDL: Indexing...";
    statusItem.tooltip = "Building KiCad symbol and footprint index";
  });
  client.onNotification("skidl/indexEnd", (params: { message?: string }) => {
    console.log(`[SKiDL] Index build finished: ${params?.message}`);
    outputChannel.appendLine(`Index ready: ${params?.message}`);
    statusItem.text = "$(circuit-board) SKiDL";
    statusItem.tooltip = `SKiDL: ${params?.message || "Ready"} (click to refresh)`;
  });

  outputChannel.appendLine("Starting language client...");
  console.log("[SKiDL] Starting language client...");
  await client.start();
  outputChannel.appendLine("Language client started successfully.");
  console.log("[SKiDL] Language client started successfully.");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[SKiDL] Activation failed: ${msg}`);
    if (outputChannel) {
      outputChannel.appendLine(`ACTIVATION ERROR: ${msg}`);
      outputChannel.show(true);
    }
    vscode.window.showErrorMessage(`SKiDL Language Server failed to start: ${msg}`);
  }
}

export async function deactivate(): Promise<void> {
  if (client) {
    await client.stop();
    client = undefined;
  }
}

function getPythonPath(config: vscode.WorkspaceConfiguration): string {
  const configured = config.get<string>("pythonPath", "");
  if (configured) {
    return configured;
  }

  // Try the Python extension's selected interpreter
  const pythonExt = vscode.extensions.getExtension("ms-python.python");
  if (pythonExt?.isActive) {
    const pythonApi = pythonExt.exports;
    const envPath = pythonApi?.environments?.getActiveEnvironmentPath?.();
    if (envPath?.path) {
      return envPath.path;
    }
  }

  // Try the python.defaultInterpreterPath setting (set by the Python extension)
  const pythonConfig = vscode.workspace.getConfiguration("python");
  const defaultInterpreter = pythonConfig.get<string>("defaultInterpreterPath", "");
  if (defaultInterpreter && defaultInterpreter !== "python") {
    return defaultInterpreter;
  }

  // Try common locations on disk
  const candidates: string[] = [];
  if (process.platform === "win32") {
    const localAppData = process.env.LOCALAPPDATA || "";
    if (localAppData) {
      // Check for standard Python installs (Python 3.14, 3.13, 3.12, etc.)
      for (const ver of ["Python314", "Python313", "Python312", "Python311", "Python310"]) {
        candidates.push(path.join(localAppData, "Programs", "Python", ver, "python.exe"));
      }
    }
    const programFiles = process.env.PROGRAMFILES || "C:\\Program Files";
    for (const ver of ["Python314", "Python313", "Python312", "Python311", "Python310"]) {
      candidates.push(path.join(programFiles, "Python", ver, "python.exe"));
    }
  } else {
    candidates.push("/usr/bin/python3", "/usr/local/bin/python3");
  }

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  // Last resort
  return process.platform === "win32" ? "python" : "python3";
}

/**
 * Check if pygls and mcp are importable. If not, install them via pip.
 * Returns true if dependencies are available after the check.
 */
async function ensureDependencies(pythonPath: string): Promise<boolean> {
  outputChannel.appendLine(`Checking if pygls and mcp are importable with: ${pythonPath}`);
  const canImport = await runQuiet(pythonPath, ["-c", "import pygls; import mcp"]);
  if (canImport) {
    outputChannel.appendLine("pygls and mcp are already installed.");
    return true;
  }
  outputChannel.appendLine("Dependencies not found. Prompting for install.");

  const install = await vscode.window.showInformationMessage(
    "SKiDL Language Server: Python dependencies (pygls, lsprotocol, mcp) are not installed. Install them now?",
    "Install",
    "Cancel"
  );
  if (install !== "Install") {
    outputChannel.appendLine("User declined install.");
    return false;
  }

  const success = await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "SKiDL: Installing Python dependencies...",
      cancellable: false,
    },
    async () => {
      return runQuiet(pythonPath, ["-m", "pip", "install", "pygls", "lsprotocol", "mcp"]);
    }
  );

  if (!success) {
    outputChannel.appendLine("pip install failed.");
    return false;
  }

  // Verify the install worked
  const verified = await runQuiet(pythonPath, ["-c", "import pygls"]);
  outputChannel.appendLine(verified ? "Install verified." : "Post-install import still failed.");
  return verified;
}

function runQuiet(command: string, args: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    cp.execFile(command, args, { timeout: 60000 }, (err, _stdout, stderr) => {
      if (err) {
        outputChannel.appendLine(`Command failed: ${command} ${args.join(" ")}`);
        outputChannel.appendLine(`Error: ${err.message}`);
        if (stderr) { outputChannel.appendLine(`Stderr: ${stderr}`); }
      }
      resolve(!err);
    });
  });
}

// ---------------------------------------------------------------------------
// MCP integration helpers
// ---------------------------------------------------------------------------

interface McpServerConfig {
  command: string;
  args: string[];
  env?: Record<string, string>;
}

function buildMcpConfigSnippet(
  pythonPath: string,
  mcpServerPath: string,
  config: vscode.WorkspaceConfiguration
): McpServerConfig {
  const snippet: McpServerConfig = {
    command: pythonPath,
    args: [mcpServerPath],
  };
  const symDir = config.get<string>("kicadSymbolDir", "");
  const fpDir = config.get<string>("kicadFootprintDir", "");
  if (symDir || fpDir) {
    snippet.env = {};
    if (symDir) { snippet.env.SKIDL_KICAD_SYMBOL_DIR = symDir; }
    if (fpDir) { snippet.env.SKIDL_KICAD_FOOTPRINT_DIR = fpDir; }
  }
  return snippet;
}

async function writeVsCodeMcpConfig(snippet: McpServerConfig): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage("No workspace folder open. Open a folder first.");
    return;
  }
  const dotVscode = vscode.Uri.joinPath(folders[0].uri, ".vscode");
  const mcpJsonUri = vscode.Uri.joinPath(dotVscode, "mcp.json");

  let existing: Record<string, unknown> = {};
  try {
    const raw = await vscode.workspace.fs.readFile(mcpJsonUri);
    existing = JSON.parse(Buffer.from(raw).toString("utf-8"));
  } catch {
    // File doesn't exist yet, start fresh
  }

  // Merge under servers.skidl-kicad, preserving other servers
  if (!existing.servers || typeof existing.servers !== "object") {
    existing.servers = {};
  }
  (existing.servers as Record<string, unknown>)["skidl-kicad"] = snippet;

  // Ensure .vscode directory exists
  try { await vscode.workspace.fs.createDirectory(dotVscode); } catch { /* already exists */ }
  const content = Buffer.from(JSON.stringify(existing, null, 2) + "\n", "utf-8");
  await vscode.workspace.fs.writeFile(mcpJsonUri, content);
  vscode.window.showInformationMessage("MCP server configured in .vscode/mcp.json");
}

async function writeClaudeDesktopConfig(snippet: McpServerConfig): Promise<void> {
  let configDir: string;
  if (process.platform === "win32") {
    configDir = path.join(process.env.APPDATA || "", "Claude");
  } else if (process.platform === "darwin") {
    configDir = path.join(process.env.HOME || "", "Library", "Application Support", "Claude");
  } else {
    configDir = path.join(process.env.HOME || "", ".config", "Claude");
  }
  const configPath = path.join(configDir, "claude_desktop_config.json");

  let existing: Record<string, unknown> = {};
  try {
    const raw = fs.readFileSync(configPath, "utf-8");
    existing = JSON.parse(raw);
  } catch {
    // File doesn't exist yet
  }

  if (!existing.mcpServers || typeof existing.mcpServers !== "object") {
    existing.mcpServers = {};
  }
  (existing.mcpServers as Record<string, unknown>)["skidl-kicad"] = snippet;

  // Ensure directory exists
  fs.mkdirSync(configDir, { recursive: true });
  fs.writeFileSync(configPath, JSON.stringify(existing, null, 2) + "\n", "utf-8");
  vscode.window.showInformationMessage(`MCP server configured in ${configPath}`);
}
