import { pathToFileURL } from "node:url";
import { delimiter, join } from "node:path";
import { existsSync, readFileSync } from "node:fs";

function packageRoot() {
  const roots = (process.env.NODE_PATH || "").split(delimiter).filter(Boolean);
  for (const root of roots) {
    const candidate = join(root, "@mariozechner", "pi-coding-agent");
    if (existsSync(join(candidate, "package.json"))) return candidate;
  }
  throw new Error("pi package not found on NODE_PATH");
}

const pkgRoot = packageRoot();
const { parseArgs } = await import(pathToFileURL(join(pkgRoot, "dist/cli/args.js")).href);
const {
  VERSION,
  AuthStorage,
  DefaultResourceLoader,
  ModelRegistry,
  SessionManager,
  SettingsManager,
  createAgentSession,
} = await import(pathToFileURL(join(pkgRoot, "dist/index.js")).href);

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
if (input.home) process.env.HOME = input.home;
if (input.agentDir) process.env.PI_CODING_AGENT_DIR = input.agentDir;
const parsed = parseArgs(input.argv);
const cwd = input.cwd;
const agentDir = input.agentDir;
const settings = SettingsManager.create(cwd, agentDir);
const loader = new DefaultResourceLoader({
  cwd,
  agentDir,
  settingsManager: settings,
  noExtensions: Boolean(parsed.noExtensions),
  noSkills: Boolean(parsed.noSkills),
  noPromptTemplates: Boolean(parsed.noPromptTemplates),
  noContextFiles: Boolean(parsed.noContextFiles),
  appendSystemPrompt: parsed.appendSystemPrompt,
  additionalExtensionPaths: parsed.extensions || [],
});
await loader.reload();
const auth = AuthStorage.create(join(agentDir, "auth.json"));
const models = ModelRegistry.create(auth, join(agentDir, "models.json"));
const { session } = await createAgentSession({
  cwd,
  agentDir,
  resourceLoader: loader,
  settingsManager: settings,
  authStorage: auth,
  modelRegistry: models,
  sessionManager: SessionManager.inMemory(),
  tools: parsed.tools,
});
const extensions = loader.getExtensions();
const prompts = loader.getPrompts();
const skills = loader.getSkills();
const agents = loader.getAgentsFiles();
const out = {
  version: VERSION,
  noExtensions: Boolean(parsed.noExtensions),
  noSkills: Boolean(parsed.noSkills),
  noPromptTemplates: Boolean(parsed.noPromptTemplates),
  noContextFiles: Boolean(parsed.noContextFiles),
  append: parsed.appendSystemPrompt || [],
  tools: parsed.tools || [],
  extensions: parsed.extensions || [],
  systemPrompt: session.systemPrompt,
  contextFiles: (agents.agentsFiles || []).map((file) => ({ path: file.path, content: file.content })),
  skills: (skills.skills || []).map((skill) => ({
    name: skill.name,
    description: skill.description,
    filePath: skill.filePath,
  })),
  loadedExtensions: (extensions.extensions || []).map((ext) => ext.path || ext.sourcePath || ""),
  extensionErrors: (extensions.errors || []).map((err) => err.path || ""),
  prompts: (prompts.prompts || []).map((prompt) => prompt.name || ""),
};
process.stdout.write(JSON.stringify(out));
