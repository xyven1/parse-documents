# Drive OCR
A repo for analyzing a drive folder containing documents to be OCRed, translated, and have metadata extracted from.

## Running
To get help for the CLI run:
```sh
nix run .# -- -h
```

You need to set the following environment variables:
- `OPENAI_API_KEY`: An Open AI development key starting with `sk-...`
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to a `service-account.json` file

## Developing
Run
```
nix develop
```
or if using `direnv` add
```
use flake
```
to `.envrc`.
