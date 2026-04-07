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
