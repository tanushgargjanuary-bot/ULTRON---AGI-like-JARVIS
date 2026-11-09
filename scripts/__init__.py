"""Local scripts package.

Provides `scripts.*` imports (e.g. `scripts.agent_workspace`,
`scripts.deep_scan`). Without this file, a site-packages package named
`scripts` shadows the local folder on Windows and imports fail.
"""
