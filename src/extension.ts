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
    path.join("server", "server.py")
  );

  // Ensure Python server dependencies are installed
  console.log("[SKiDL] Checking Python dependencies...");
  const depsOk = await ensureDependencies(pythonPath);
  console.log(`[SKiDL] Dependencies check result: ${depsOk}`);
  if (!depsOk) {
    vscode.window.showErrorMessage(
      "SKiDL Language Server: Failed to install Python dependencies (pygls, lsprotocol). " +
      "Please install them manually: pip install pygls lsprotocol"
    );
    return;
  }

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

  const rebuildCmd = vscode.commands.registerCommand(
    "skidl.rebuildIndex",
    async () => {
      if (client) {
        await client.sendRequest("skidl/rebuildIndex");
      }
    }
  );
  context.subscriptions.push(rebuildCmd);

  // Status bar item — created and shown before client starts so we catch early notifications
  const statusItem = vscode.window.createStatusBarItem("skidl.status", vscode.StatusBarAlignment.Left, 0);
  statusItem.name = "SKiDL";
  statusItem.text = "$(loading~spin) SKiDL: Starting...";
  statusItem.tooltip = "SKiDL Language Server is starting";
  statusItem.command = "skidl.rebuildIndex";
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
    statusItem.tooltip = `SKiDL: ${params?.message || "Ready"} (click to rebuild)`;
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
 * Check if pygls is importable. If not, install it (and lsprotocol) via pip.
 * Returns true if dependencies are available after the check.
 */
async function ensureDependencies(pythonPath: string): Promise<boolean> {
  outputChannel.appendLine(`Checking if pygls is importable with: ${pythonPath}`);
  const canImport = await runQuiet(pythonPath, ["-c", "import pygls"]);
  if (canImport) {
    outputChannel.appendLine("pygls is already installed.");
    return true;
  }
  outputChannel.appendLine("pygls not found. Prompting for install.");

  const install = await vscode.window.showInformationMessage(
    "SKiDL Language Server: Python dependencies (pygls, lsprotocol) are not installed. Install them now?",
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
      return runQuiet(pythonPath, ["-m", "pip", "install", "pygls", "lsprotocol"]);
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
