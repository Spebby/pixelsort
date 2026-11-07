{
  description = "pixelsort - Python image pixel sorting";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";

    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      git-hooks,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        inherit (pkgs) lib;

        python = pkgs.python3;
        pythonPackages = python.pkgs;

        help = pkgs.writeShellApplication {
          name = "help";
          text = ''
            cat <<'EOF'
            pixelsort development commands

            Build:
              nix build             Build the Python package
              nix run               Run pixelsort
              nix run .#help        Show this help message

            Development:
              nix develop           Enter the development shell

            Checks:
              nix flake check       Run all flake checks
              nix fmt              Format Nix files

            Usage:
              pixelsort IMAGE [OPTIONS]
              python -m pixelsort IMAGE [OPTIONS]

            EOF
          '';
        };

        # Only files required to build the Python package.
        packageSource = lib.fileset.toSource {
          root = ./.;
          fileset = lib.fileset.unions [
            ./README.md
            ./setup.py
            ./pixelsort
          ];
        };

        # All repository files used by lint checks.
        repoSource = lib.fileset.toSource {
          root = ./.;
          fileset = lib.fileset.difference ./. (lib.fileset.maybeMissing ./.git);
        };

        pixelsort = pythonPackages.buildPythonPackage {
          pname = "pixelsort";
          version = "1.0.2";
          src = packageSource;

          format = "setuptools";

          propagatedBuildInputs = with pythonPackages; [ pillow ];

          pythonImportsCheck = [ "pixelsort" ];

          meta = {
            description = "An image pixelsorter for Python";
            homepage = "https://github.com/satyarth/pixelsort";
            license = lib.licenses.mit;
            platforms = lib.platforms.all;
          };
        };

        pythonEnv = python.withPackages (_: [ pixelsort ]);

        pixelsortCli = pkgs.writeShellApplication {
          name = "pixelsort";
          runtimeInputs = [ pythonEnv ];
          text = ''
            exec python -m pixelsort "$@"
          '';
        };

        lint =
          name: tools: script:
          pkgs.runCommand name { nativeBuildInputs = tools; } ''
            export HOME="$TMPDIR"
            cd ${repoSource}
            ${script}
            touch "$out"
          '';

        gitHooks = pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux (
          git-hooks.lib.${system}.run {
            src = ./.;
            excludes = [ ];
            hooks = {
              flake-checker.enable = true;

              nixfmt = {
                enable = true;
                settings.width = 100;
              };

              shfmt.enable = true;
              typos.enable = true;
            };
          }
        );
      in
      {
        packages = {
          default = pixelsortCli;
          library = pixelsort;
          cli = pixelsortCli;
        };

        apps = {
          pixelsort = {
            type = "app";
            program = "${pixelsortCli}/bin/pixelsort";
            meta.description = "Run the pixelsort CLI";
          };

          help = {
            type = "app";
            program = "${help}/bin/help";
            meta.description = "Show available project commands";
          };

          default = self.apps.${system}.pixelsort;
        };

        checks = {
          inherit pixelsort;

          nixfmt = lint "nixfmt" [ pkgs.nixfmt ] "nixfmt --strict --check flake.nix";
          statix = lint "statix" [ pkgs.statix ] "statix check .";
          deadnix = lint "deadnix" [ pkgs.deadnix ] "deadnix --fail .";
          typos = lint "typos" [ pkgs.typos ] "typos";

          cli-help = pkgs.runCommand "pixelsort-cli-help" { } ''
            ${pixelsort}/bin/pixelsort --help > "$out"
          '';
        }
        // pkgs.lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux { git-check = gitHooks; };

        formatter = pkgs.nixfmt;

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pixelsortCli
            pkgs.nil
            pkgs.nixfmt
            pkgs.statix
            pkgs.deadnix
            pkgs.typos
          ]
          ++ (gitHooks.enabledPackages or [ ]);

          shellHook = ''
            ${gitHooks.shellHook or ""}
            nix run .#help
          '';
        };
      }
    );
}
