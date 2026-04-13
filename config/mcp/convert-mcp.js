#!/usr/bin/env node
/**
 * convert-mcp.js — Convert canonical MCP server definitions to agent-specific formats
 *
 * Reads: $CODING_AGENT_INSTALL_DIR/config/mcp/servers.json
 * Writes to each agent's native MCP config location.
 *
 * Canonical format (servers.json):
 * {
 *   "servers": {
 *     "server-name": {
 *       "command": "npx",
 *       "args": ["-y", "@modelcontextprotocol/server-github"],
 *       "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" },
 *       "transport": "stdio",
 *       "url": null
 *     }
 *   }
 * }
 *
 * Sources:
 * - Claude Code .mcp.json: https://code.claude.com/docs/en/mcp
 * - Codex config.toml [mcp_servers]: https://developers.openai.com/codex/config-reference
 * - OpenCode opencode.json mcp: https://opencode.ai/docs/config/
 * - Pi mcp.json (via pi-mcp-adapter): https://github.com/nicobailon/pi-mcp-adapter
 * - Gemini CLI settings.json mcpServers: https://geminicli.com/docs/core/subagents/
 * - Amp settings: https://ampcode.com/manual
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const home = os.homedir();
const installDir = process.env.CODING_AGENT_INSTALL_DIR || path.join(home, 'coding_agents');
const serversPath = path.join(installDir, 'config', 'mcp', 'servers.json');

if (!fs.existsSync(serversPath)) {
  console.log('No servers.json found at', serversPath);
  console.log('Create it to define shared MCP servers.');
  process.exit(0);
}

const canonical = JSON.parse(fs.readFileSync(serversPath, 'utf8'));
const servers = canonical.servers || {};

if (Object.keys(servers).length === 0) {
  console.log('No MCP servers defined in servers.json');
  process.exit(0);
}

// Helper: merge into existing JSON file
function mergeJson(filePath, data) {
  let existing = {};
  try { existing = JSON.parse(fs.readFileSync(filePath, 'utf8')); } catch {}
  const merged = { ...existing, ...data };
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(merged, null, 2) + '\n');
}

// --- Claude Code: ~/.mcp.json ---
const claudeMcp = { mcpServers: {} };
for (const [name, srv] of Object.entries(servers)) {
  claudeMcp.mcpServers[name] = {
    type: srv.transport || 'stdio',
    ...(srv.command && { command: srv.command, args: srv.args || [] }),
    ...(srv.url && { url: srv.url }),
    ...(srv.env && { env: srv.env }),
  };
}
mergeJson(path.join(home, '.mcp.json'), claudeMcp);

// --- Codex CLI: append to ~/.codex/config.toml ---
let codexToml = '\n# --- Auto-generated MCP servers (coding-agents sync) ---\n';
for (const [name, srv] of Object.entries(servers)) {
  codexToml += `\n[mcp_servers.${name}]\n`;
  if (srv.command) {
    codexToml += `command = ${JSON.stringify([srv.command, ...(srv.args || [])])}\n`;
  }
  if (srv.url) codexToml += `url = "${srv.url}"\n`;
  if (srv.env) {
    const envPairs = Object.entries(srv.env)
      .map(([k, v]) => `"${k}" = "${v}"`).join(', ');
    codexToml += `env = { ${envPairs} }\n`;
  }
  codexToml += `enabled = true\n`;
}
const codexConfig = path.join(home, '.codex', 'config.toml');
if (fs.existsSync(codexConfig)) {
  // Remove old auto-generated section
  let content = fs.readFileSync(codexConfig, 'utf8');
  content = content.replace(/\n# --- Auto-generated MCP servers.*$/s, '');
  fs.writeFileSync(codexConfig, content + codexToml);
}

// --- Pi: ~/.pi/agent/mcp.json (for pi-mcp-adapter) ---
const piMcp = {
  settings: { toolPrefix: 'mcp', idleTimeout: 10 },
  mcpServers: {},
};
for (const [name, srv] of Object.entries(servers)) {
  piMcp.mcpServers[name] = {
    ...(srv.command && { command: srv.command, args: srv.args || [] }),
    ...(srv.url && { url: srv.url }),
    ...(srv.env && { env: srv.env }),
    lifecycle: 'lazy',
  };
}
const piMcpPath = path.join(home, '.pi', 'agent', 'mcp.json');
if (!fs.existsSync(path.dirname(piMcpPath))) fs.mkdirSync(path.dirname(piMcpPath), { recursive: true });
fs.writeFileSync(piMcpPath, JSON.stringify(piMcp, null, 2) + '\n');

// --- Gemini CLI: ~/.gemini/settings.json mcpServers ---
const geminiMcp = { mcpServers: {} };
for (const [name, srv] of Object.entries(servers)) {
  geminiMcp.mcpServers[name] = {
    ...(srv.command && { command: srv.command, args: srv.args || [] }),
    ...(srv.url && { url: srv.url }),
    ...(srv.env && { env: srv.env }),
  };
}
mergeJson(path.join(home, '.gemini', 'settings.json'), geminiMcp);

// --- OpenCode: merge into opencode.json mcp section ---
const opencodeMcp = { mcp: {} };
for (const [name, srv] of Object.entries(servers)) {
  opencodeMcp.mcp[name] = {
    ...(srv.command && { command: srv.command, args: srv.args || [] }),
    ...(srv.url && { url: srv.url }),
    ...(srv.env && { env: srv.env }),
  };
}
mergeJson(path.join(home, '.config', 'opencode', 'opencode.json'), opencodeMcp);

console.log(`✅ MCP configs written for ${Object.keys(servers).length} server(s)`);
console.log('   → Claude Code (~/.mcp.json)');
console.log('   → Codex CLI (~/.codex/config.toml)');
console.log('   → Pi (~/.pi/agent/mcp.json)');
console.log('   → Gemini CLI (~/.gemini/settings.json)');
console.log('   → OpenCode (~/.config/opencode/opencode.json)');
