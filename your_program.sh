#!/bin/sh
set -e # Exit early if any commands fail
exec uv run --quiet -m app.main "$@"
