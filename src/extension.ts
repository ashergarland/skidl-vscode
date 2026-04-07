import * as cp from "child_process";
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("skidl");
  const pythonPath = getPythonPath(config);
  const serverModule = context.asAbsolutePath(
    path.join("server", "server.py")
  );

  // Ensure Python server dependencies are installed
  const depsOk = await ensureDependencies(pythonPath);
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
        vscode.window.showInformationMessage(
          "SKiDL: KiCad library index rebuilt."
        );
      }
    }
  );
  context.subscriptions.push(rebuildCmd);

  await client.start();
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

  // Fallback
  return process.platform === "win32" ? "python" : "python3";
}

/**
 * Check if pygls is importable. If not, install it (and lsprotocol) via pip.
 * Returns true if dependencies are available after the check.
 */
async function ensureDependencies(pythonPath: string): Promise<boolean> {
  const canImport = await runQuiet(pythonPath, ["-c", "import pygls"]);
  if (canImport) {
    return true;
  }

  const install = await vscode.window.showInformationMessage(
    "SKiDL Language Server: Python dependencies (pygls, lsprotocol) are not installed. Install them now?",
    "Install",
    "Cancel"
  );
  if (install !== "Install") {
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
    return false;
  }

  // Verify the install worked
  return runQuiet(pythonPath, ["-c", "import pygls"]);
}

function runQuiet(command: string, args: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    cp.execFile(command, args, { timeout: 60000 }, (err) => {
      resolve(!err);
    });
  });
}
