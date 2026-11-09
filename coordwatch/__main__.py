import sys

# Windows consoles default to a legacy code page; scraped posts contain emoji / Arabic / Hindi. Never crash on print.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .cli import main
sys.exit(main())
