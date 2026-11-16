# One compile database for every PlatformIO project in the repo, so IntelliSense
# works from a single VS Code window. Bench tools under firmware/tools/ are found
# automatically. Run again after adding a tool, adding files or changing build flags.
set -euo pipefail
shopt -s nullglob                     # no tools yet -> empty list, not a literal pattern
cd "$(dirname "$0")/.."

# The car firmware: only the device environment, because the native test
# environment would add a second, conflicting entry for every file in lib/core.
projects=(firmware)
pio run -d firmware -e esp32s3 -t compiledb

for ini in firmware/tools/*/platformio.ini; do
  tool="$(dirname "$ini")"
  pio run -d "$tool" -t compiledb
  projects+=("$tool")
done

python3 - "${projects[@]}" <<'EOF'
import json
import sys

entries = []
for project in sys.argv[1:]:
    with open(f"{project}/compile_commands.json") as f:
        entries += json.load(f)
with open("compile_commands.json", "w") as f:
    json.dump(entries, f, indent=1)
print(f"compile_commands.json: {len(entries)} entries from {len(sys.argv) - 1} projects")
EOF
