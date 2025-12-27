{
  description = "Flake for Drive OCR Python app";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};
      lib = nixpkgs.lib;
      pythonPackages = pkgs.python313Packages;
    in {
      packages.default = pythonPackages.buildPythonApplication {
        pname = "drive-ocr";
        version = "0.1.0";
        src = lib.cleanSource ./.;
        pyproject = true;

        build-system = with pythonPackages; [
          hatchling
        ];

        propagatedBuildInputs = with pythonPackages; [
          google-api-python-client
          openai
          pydantic
        ];

        doCheck = false;

        meta = {
          description = "Recursive Google Drive OCR and document analysis using ChatGPT";
          license = lib.licenses.mit;
          mainProgram = "drive-ocr";
        };
      };

      devShells.default = pkgs.mkShell {
        inputsFrom = [self.packages.${system}.default];
        buildInputs = [
          pkgs.ruff
          pkgs.basedpyright
        ];
      };
    });
}
