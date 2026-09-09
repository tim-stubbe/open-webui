# Local computer-use bridge

The bridge runs on the Mac and exposes only a small fixed action set. Open WebUI
reaches it over the Mac's private Tailscale address. A random bearer token is
required for every request, request bodies are size-limited, redirects are not
followed, and typed text is never written to the bridge log.

The installed LaunchAgent reads its token from
`~/.local/share/open-webui-computer-use/token`. Set
`COMPUTER_USE_ALLOW_INPUT=false` and restart the LaunchAgent for an immediate
input stop. Screen observation may require macOS Screen Recording permission;
clicking and typing require Accessibility permission for the Python process.

The Chrome extension in `computer_use_chrome` reads the active page and polls
this bridge for fixed browser commands. Its options page stores the same token
in Chrome's local extension storage.
