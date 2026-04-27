"""Runtime helpers shipped to ``<install_dir>/bin/`` for use at agent spawn time.

These modules are designed to run as standalone scripts from the install dir
without depending on the rest of the ``coding_agents`` package — they're invoked
by VSCode extension hooks where the user's PATH may not include the typer entry
point. Keep imports minimal and the runtime surface boring.
"""
