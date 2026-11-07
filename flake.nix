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
              nix build             Build the GUI application
              nix build .#cli       Build the CLI
              nix build .#library   Build the Python library
              nix run               Launch the GUI
              nix run .#pixelsort   Run the CLI
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

          propagatedBuildInputs = with pythonPackages; [
            pillow
            numpy
          ];
          pythonImportsCheck = [ "pixelsort" ];

          meta = {
            description = "An image pixelsorter for Python";
            homepage = "https://github.com/spebby/pixelsort";
            license = lib.licenses.mit;
            platforms = lib.platforms.all;
          };
        };

        # CLI environment deliberately excludes GUI dependencies.
        pythonEnv = python.withPackages (_: [ pixelsort ]);

        pixelsortCli = pkgs.writeShellApplication {
          name = "pixelsort-cli";
          runtimeInputs = [ pythonEnv ];
          text = ''
            exec python -m pixelsort "$@"
          '';
        };

        # GUI environment adds PyGObject without changing the library's
        # dependencies or requiring GTK for CLI users.
        pythonGuiEnv = python.withPackages (_: [
          pixelsort
          pythonPackages.pygobject3
        ]);

        pixelsortGuiBase = pkgs.stdenv.mkDerivation {
          pname = "pixelsort-gui";
          version = "1.0.2";

          dontUnpack = true;

          nativeBuildInputs = [
            pkgs.makeWrapper
            pkgs.wrapGAppsHook4
          ];

          buildInputs = [
            pythonGuiEnv
            pkgs.gobject-introspection
            pkgs.gtk4
            pkgs.libadwaita
            pkgs.adwaita-icon-theme
            pkgs.gsettings-desktop-schemas
          ];

          installPhase = ''
            runHook preInstall
            mkdir -p "$out/bin"
            makeWrapper ${pythonGuiEnv}/bin/python "$out/bin/pixelsort-gui" \
              --add-flags "-m pixelsort.gui"
            runHook postInstall
          '';

          meta = {
            description = "GTK4/libadwaita graphical interface for pixelsort";
            homepage = "https://github.com/spebby/pixelsort";
            license = lib.licenses.mit;
            platforms = lib.platforms.linux;
            mainProgram = "pixelsort-gui";
          };
        };

        pixelsortDesktopItem = pkgs.makeDesktopItem {
          name = "pixelsort";
          desktopName = "PixelSort";
          genericName = "Pixel Sorting Image Editor";
          comment = "Sort pixels in images";
          exec = "${pixelsortGuiBase}/bin/pixelsort-gui";
          icon = "image-x-generic";
          terminal = false;
          categories = [
            "Graphics"
            "RasterGraphics"
          ];
          keywords = [
            "image"
            "pixel"
            "sorting"
          ];
        };

        pixelsortGui = pkgs.symlinkJoin {
          name = "pixelsort-gui";
          paths = [
            pixelsortGuiBase
            pixelsortDesktopItem
          ];
          inherit (pixelsortGuiBase) meta;
        };

        lint =
          name: tools: script:
          pkgs.runCommand name { nativeBuildInputs = tools; } ''
            export HOME="$TMPDIR"
            cd ${repoSource}
            ${script}
            touch "$out"
          '';

        gitHooks = lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux (
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
          default = pixelsortGui;
          gui = pixelsortGui;
          cli = pixelsortCli;
          library = pixelsort;
        };

        apps = {
          gui = {
            type = "app";
            program = "${pixelsortGui}/bin/pixelsort-gui";
            meta.description = "Launch the pixelsort GUI";
          };

          pixelsort-cli = {
            type = "app";
            program = "${pixelsortCli}/bin/pixelsort-cli";
            meta.description = "Run the pixelsort CLI";
          };

          help = {
            type = "app";
            program = "${help}/bin/help";
            meta.description = "Show available project commands";
          };

          default = self.apps.${system}.gui;
        };

        checks = {
          inherit pixelsort pixelsortGui;

          nixfmt = lint "nixfmt" [ pkgs.nixfmt ] "nixfmt --strict --check flake.nix";
          statix = lint "statix" [ pkgs.statix ] "statix check .";
          deadnix = lint "deadnix" [ pkgs.deadnix ] "deadnix --fail .";
          typos = lint "typos" [ pkgs.typos ] "typos";

          cli-help = pkgs.runCommand "pixelsort-cli-help" { } ''
            ${pixelsortCli}/bin/pixelsort --help > "$out"
          '';
        }
        // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux { git-check = gitHooks; };

        formatter = pkgs.nixfmt;

        devShells.default = pkgs.mkShell {
          packages = [
            pythonGuiEnv
            pixelsortCli

            pkgs.gtk4
            pkgs.libadwaita
            pkgs.adwaita-icon-theme
            pkgs.gsettings-desktop-schemas
            pkgs.gobject-introspection

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
    )
    // {
      overlays.default = final: prev: {
        pixelsort = self.packages.${final.stdenv.hostPlatform.system}.gui;
        pixelsort-cli = self.packages.${final.stdenv.hostPlatform.system}.cli;
        pixelsort-library = self.packages.${final.stdenv.hostPlatform.system}.library;
      };
    };
}
