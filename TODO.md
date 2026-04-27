# TODO

Optional / deferred work — items we know about but haven't built yet.
Each item should say what, why, and the most minimal first cut so a
future implementer doesn't have to re-derive the design.

## Per-user Pi extension install (HPC mode)

**What:** A first-class path for a user to install a Pi extension that
is NOT in the lab-default set baked into the SIF.

**Why:** Today the SIF's `/usr/lib/node_modules/` is read-only at
runtime, so `pi install npm:foo` from inside the SIF fails. The four
lab-default extensions (`pi-ask-user`, `pi-subagents`, `pi-web-access`,
`pi-mcp-adapter`) are baked into the SIF in `%post`; anything beyond
that requires a SIF rebuild + republish, which only the lab admin can
do. The cleanest sharable route stays "PR the extension into
`coding_agent_hpc.def`'s `%post`", but that's overkill for a one-off
personal extension.

**Minimal first cut:**

1. New subcommand `coding-agents pi-extension install <npm-spec>` that:
   - Creates `~/.pi/agent/extensions/` if absent.
   - Runs `apptainer exec --no-mount home --writable-tmpfs --bind
     "$HOME/.pi/agent:$HOME/.pi/agent" SIF npm install --prefix
     "$HOME/.pi/agent/extensions" <spec>`.
   - Patches `~/.pi/agent/settings.json` to add a `file:`-source
     reference to the new extension's `lib/node_modules/<name>`.
2. Mirror `pi-extension list` and `pi-extension remove`.
3. Doctor row: walk the user's settings.json `file:` entries and warn
   if any path doesn't resolve.

**Why this minimal cut works:** the host bind `~/.pi/agent` is already
in the wrapper, so the extension dir is visible inside the SIF at the
same path. The SIF's npm is the install tool; nothing has to change in
the SIF or the wrapper. Settings.json picks up the new extension via
its `file:` source — same mechanism Pi uses for local development.

**Why it's deferred:**
- Compute-node npm registry reachability isn't guaranteed lab-wide;
  needs a fallback "pre-stage from a login node, copy to compute" UX
  story before this is robust.
- Personal extensions duplicate effort — for anything more than one
  user wants, the right answer is still "PR the extension into the
  `.def`". A `pi-extension install` command might inadvertently push
  users toward the personal route when the shared route is better.
- Settings.json patching is fiddly: Pi expects exact paths, and the
  user's path may not match across two machines if `$HOME` differs.

**Related context:**
- `src/coding_agents/bundled/coding_agent_hpc.def` — `%post` block
  with the four `pi install npm:...` lines.
- `src/coding_agents/bundled/templates/wrapper/agent.template.sh` —
  Pi first-run seed copies `/opt/pi-default-settings.json` →
  `~/.pi/agent/settings.json` if absent.
