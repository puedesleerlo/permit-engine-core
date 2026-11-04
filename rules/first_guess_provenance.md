# How the first guess was written

A fresh agent wrote `first_guess.json` on 2026-11-03, before any model had read a case. It worked from a folder holding only the ordinance, the hazards and the tree question lists, with its prompt saved at `prompts/first_guess_author.md`. It was told to open nothing else, and it reported that it did not. That is its own report, not something enforced or checked by a file-access log.

SHA-256 of its 11 input files, concatenated in sorted path order: `e84f090af7eeb45493c7358f568dd0f74cce380b00f30fa9175dd38164edd5c5`

The truth table had already been written by then, by a different agent, so the project owner's session was not blind to it. Only the author of these weights was.
