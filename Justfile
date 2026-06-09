packages := "emulator trouble-shooter"

ci:
    #!/usr/bin/env bash
    set -e
    for pkg in {{packages}}; do
        echo "=== $pkg ==="
        just -f "$pkg/Justfile" --working-directory "$pkg" ci
    done

test:
    #!/usr/bin/env bash
    set -e
    for pkg in {{packages}}; do
        echo "=== $pkg ==="
        just -f "$pkg/Justfile" --working-directory "$pkg" test
    done

lint:
    #!/usr/bin/env bash
    set -e
    for pkg in {{packages}}; do
        echo "=== $pkg ==="
        just -f "$pkg/Justfile" --working-directory "$pkg" lint
    done

format:
    #!/usr/bin/env bash
    set -e
    for pkg in {{packages}}; do
        echo "=== $pkg ==="
        just -f "$pkg/Justfile" --working-directory "$pkg" format
    done

types:
    #!/usr/bin/env bash
    set -e
    for pkg in {{packages}}; do
        echo "=== $pkg ==="
        just -f "$pkg/Justfile" --working-directory "$pkg" types
    done
