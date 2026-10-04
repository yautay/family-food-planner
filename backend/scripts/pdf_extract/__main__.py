"""`python -m scripts.pdf_extract <komenda>` — wołane przez Taskfile (`task pdfx-*`)."""

from scripts.pdf_extract.cli import main

raise SystemExit(main())
