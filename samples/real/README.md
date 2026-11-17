# Private docs live here. They must never be committed.

This directory is the one exception to "everything in the repo": PDFs under
`samples/real/` are gitignored (see `.gitignore`), and truth lives in the
gitignored `evals/real_truth_local.py`. Keep it that way:

- never `git add -f` anything in this directory;
- prefer absolute paths outside the repo for new private docs (the truth file
  accepts any `pdf` path, e.g. `~/Documents/client_x/agreement.pdf`);
- if a private file ever lands in git history, rotate any exposed secrets and
  rewrite history before pushing (`git filter-repo`).
