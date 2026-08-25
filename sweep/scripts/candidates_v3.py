#!/usr/bin/env python3
"""Candidate projects for the second expansion of the corpus.

Chosen against three gaps rather than by popularity alone, because another 200
of what we already cover would mostly re-measure what we already know.

1. Ecosystems with no representation at all. The original brief asked for
   findings on missing lockfile support, and a stack we never point the tool at
   cannot produce one. Haskell, OCaml, Clojure, Erlang, Perl, R, Julia, Lua,
   Nim, Zig, Nix and CocoaPods are all absent today.

2. The positive path of fixes whose negative path we have already measured.
   #351 is verified against Swift projects with no Package.resolved; nothing
   yet checks that a Swift project *with* one produces a good SBOM. Same for
   .NET: every repository in the corpus lacks packages.lock.json, so the branch
   that fetches the SDK is untested against real code.

3. Monorepos, deliberately. The re-run has just shown discovery filling all 200
   of its slots with .csproj files in abpframework/abp and evicting every
   lockfile the repo has. That is one observation; a class of repository needs
   more than one before we know how the ranking behaves under load.

Each entry is (ecosystem, slug, note). The note records why the project earns
its place -- which lock file or which awkwardness -- so a later reader can tell
a deliberate choice from a popular name.
"""

CANDIDATES = [
    # -- Swift, with Package.resolved committed: the positive path for #351 ---
    ("swift", "pointfreeco/swift-composable-architecture", "Package.resolved committed"),
    ("swift", "supabase/supabase-swift", "Package.resolved committed"),
    ("swift", "stripe/stripe-ios", "Package.resolved, large SDK"),
    ("swift", "firebase/firebase-ios-sdk", "Package.resolved, very large"),
    ("swift", "realm/realm-swift", "Package.resolved + Podfile"),
    ("swift", "SDWebImage/SDWebImage", "CocoaPods and SwiftPM"),
    ("swift", "ReactiveX/RxSwift", "SwiftPM, no resolved"),
    ("swift", "onevcat/Kingfisher", "SwiftPM"),
    ("swift", "SwiftyBeaver/SwiftyBeaver", "SwiftPM small"),
    ("swift", "groue/GRDB.swift", "SwiftPM"),
    ("swift", "swiftlang/swift-syntax", "SwiftPM, compiler-adjacent"),
    ("swift", "apple/swift-algorithms", "SwiftPM, apple-owned"),
    ("swift", "Moya/Moya", "SwiftPM + Podfile"),
    ("swift", "kean/Nuke", "SwiftPM"),

    # -- .NET: packages.lock.json where it exists, plus monorepo pressure -----
    ("dotnet", "dotnet/aspnetcore", "huge monorepo, hundreds of csproj"),
    ("dotnet", "dotnet/efcore", "monorepo, central package management"),
    ("dotnet", "dotnet/runtime", "very large monorepo"),
    ("dotnet", "dotnet/roslyn", "large monorepo"),
    ("dotnet", "jellyfin/jellyfin", "app, many csproj"),
    ("dotnet", "bitwarden/server", "csproj + Directory.Packages.props"),
    ("dotnet", "OrchardCMS/OrchardCore", "modular monorepo"),
    ("dotnet", "dotnet/maui", "monorepo"),
    ("dotnet", "ppy/osu", "large app, csproj"),
    ("dotnet", "quartznet/quartznet", "previously matched a stray lockfile"),
    ("dotnet", "serilog/serilog", "library"),
    ("dotnet", "MassTransit/MassTransit", "library, many projects"),
    ("dotnet", "dotnet/orleans", "framework monorepo"),
    ("dotnet", "AvaloniaUI/Avalonia", "UI framework monorepo"),
    ("dotnet", "SixLabors/ImageSharp", "library"),
    ("dotnet", "npgsql/npgsql", "data provider"),

    # -- Haskell: no representation at all ------------------------------------
    ("haskell", "haskell/cabal", "cabal.project"),
    ("haskell", "commercialhaskell/stack", "stack.yaml + cabal"),
    ("haskell", "PostgREST/postgrest", "cabal, real app"),
    ("haskell", "jgm/pandoc", "cabal, widely used"),
    ("haskell", "koalaman/shellcheck", "cabal"),
    ("haskell", "haskell/haskell-language-server", "cabal, large"),

    # -- OCaml / Reason -------------------------------------------------------
    ("ocaml", "ocaml/dune", "dune-project"),
    ("ocaml", "mirage/mirage", "opam"),
    ("ocaml", "ocaml/opam", "opam itself"),
    ("ocaml", "facebook/pyre-check", "dune + python mix"),

    # -- Clojure --------------------------------------------------------------
    ("clojure", "metabase/metabase", "deps.edn, large app"),
    ("clojure", "clojure/clojure", "maven pom"),
    ("clojure", "weavejester/ring", "project.clj"),
    ("clojure", "babashka/babashka", "deps.edn + graalvm"),

    # -- Erlang ---------------------------------------------------------------
    ("erlang", "erlang/otp", "rebar, very large"),
    ("erlang", "rabbitmq/rabbitmq-server", "rebar/erlang.mk monorepo"),
    ("erlang", "emqx/emqx", "rebar.lock"),
    ("erlang", "ninenines/cowboy", "rebar.lock"),

    # -- Perl -----------------------------------------------------------------
    ("perl", "mojolicious/mojo", "cpanfile"),
    ("perl", "Perl/perl5", "core, no lockfile"),
    ("perl", "metacpan/metacpan-web", "cpanfile + snapshot"),
    ("perl", "openresty/lua-nginx-module", "mixed lua/perl tests"),

    # -- R ---------------------------------------------------------------------
    ("r", "tidyverse/dplyr", "DESCRIPTION"),
    ("r", "tidyverse/ggplot2", "DESCRIPTION"),
    ("r", "rstudio/shiny", "DESCRIPTION + renv"),
    ("r", "rstudio/renv", "renv.lock, the R lockfile"),

    # -- Julia -----------------------------------------------------------------
    ("julia", "JuliaLang/Pkg.jl", "Project.toml/Manifest.toml"),
    ("julia", "FluxML/Flux.jl", "Project.toml"),
    ("julia", "JuliaData/DataFrames.jl", "Project.toml"),
    ("julia", "SciML/DifferentialEquations.jl", "Project.toml"),

    # -- Lua / Nim / Zig -------------------------------------------------------
    ("lua", "nvim-lua/kickstart.nvim", "no manifest at all"),
    ("lua", "kong/kong", "rockspec, real app"),
    ("lua", "luvit/luvit", "rockspec"),
    ("nim", "nim-lang/Nim", "nimble"),
    ("nim", "status-im/nimbus-eth2", "nimble, large"),
    ("nim", "treeform/pixie", "nimble"),
    ("zig", "ziglang/zig", "build.zig.zon"),
    ("zig", "oven-sh/bun", "build.zig.zon + package.json"),
    ("zig", "tigerbeetle/tigerbeetle", "build.zig.zon"),

    # -- Nix -------------------------------------------------------------------
    ("nix", "NixOS/nixpkgs", "flake.nix, enormous"),
    ("nix", "nix-community/home-manager", "flake.lock"),
    ("nix", "cachix/devenv", "flake.lock + rust"),

    # -- Terraform / IaC (under-represented today) -----------------------------
    ("terraform", "terraform-aws-modules/terraform-aws-vpc", ".terraform.lock.hcl"),
    ("terraform", "terraform-aws-modules/terraform-aws-eks", "modules"),
    ("terraform", "cloudposse/terraform-aws-components", "large module monorepo"),
    ("terraform", "gruntwork-io/terragrunt", "go + terraform"),
    ("terraform", "hashicorp/terraform-provider-aws", "go provider, huge"),
    ("terraform", "kubernetes-sigs/cluster-api", "go, manifests"),

    # -- C / C++ with real dependency manifests --------------------------------
    ("cpp", "conan-io/conan-center-index", "conanfiles at scale"),
    ("cpp", "microsoft/vcpkg", "vcpkg.json manifests"),
    ("cpp", "microsoft/terminal", "vcpkg.json + msbuild"),
    ("cpp", "godotengine/godot", "scons, no manifest"),
    ("cpp", "opencv/opencv", "cmake"),
    ("cpp", "protocolbuffers/protobuf", "cmake + bazel + multi-language"),
    ("cpp", "grpc/grpc", "bazel + cmake, polyglot"),
    ("cpp", "envoyproxy/envoy", "bazel"),
    ("cpp", "duckdb/duckdb", "cmake, vendored"),
    ("cpp", "ClickHouse/ClickHouse", "cmake, very large"),

    # -- Kotlin ----------------------------------------------------------------
    ("kotlin", "JetBrains/kotlin", "gradle, enormous"),
    ("kotlin", "square/okhttp", "gradle + version catalog"),
    ("kotlin", "InsertKoinIO/koin", "gradle"),
    ("kotlin", "ktorio/ktor", "gradle"),
    ("kotlin", "detekt/detekt", "gradle"),
    ("kotlin", "arrow-kt/arrow", "gradle"),
    ("kotlin", "coil-kt/coil", "gradle"),
    ("kotlin", "cashapp/sqldelight", "gradle"),

    # -- Java: gradle.lockfile and maven both ----------------------------------
    ("java", "apache/kafka", "gradle, self-bootstrapping wrapper"),
    ("java", "apache/lucene", "gradle, newer JDK"),
    ("java", "elastic/elasticsearch", "gradle monorepo"),
    ("java", "apache/dubbo", "maven multi-module"),
    ("java", "alibaba/nacos", "maven"),
    ("java", "apache/flink", "maven, very large"),
    ("java", "quarkusio/quarkus", "maven monorepo"),
    ("java", "spring-projects/spring-framework", "gradle"),
    ("java", "google/guava", "maven"),
    ("java", "apache/camel", "maven, huge"),
    ("java", "keycloak/keycloak", "maven"),
    ("java", "apache/pulsar", "maven"),
    ("java", "OpenAPITools/openapi-generator", "maven"),
    ("java", "debezium/debezium", "maven"),

    # -- Scala -----------------------------------------------------------------
    ("scala", "scala/scala3", "sbt, compiler"),
    ("scala", "akka/akka", "sbt"),
    ("scala", "playframework/playframework", "sbt"),
    ("scala", "zio/zio", "sbt"),
    ("scala", "apache/incubator-pekko", "sbt"),
    ("scala", "scalatest/scalatest", "sbt"),

    # -- Elixir ----------------------------------------------------------------
    ("elixir", "phoenixframework/phoenix", "mix.lock"),
    ("elixir", "elixir-ecto/ecto", "mix.lock"),
    ("elixir", "absinthe-graphql/absinthe", "mix.lock"),
    ("elixir", "oban-bg/oban", "mix.lock"),
    ("elixir", "livebook-dev/livebook", "mix.lock + assets"),
    ("elixir", "thoughtbot/bamboo", "mix.lock"),

    # -- Dart / Flutter --------------------------------------------------------
    ("dart", "flutter/packages", "monorepo of pubspecs"),
    ("dart", "dart-lang/sdk", "very large"),
    ("dart", "bloclibrary-dev/bloc", "melos monorepo"),
    ("dart", "flame-engine/flame", "melos monorepo"),
    ("dart", "rrousselGit/riverpod", "melos monorepo"),
    ("dart", "dart-lang/http", "pubspec"),
    ("dart", "firebase/flutterfire", "monorepo"),
    ("dart", "invertase/react-native-firebase", "js + dart mix"),

    # -- Ruby ------------------------------------------------------------------
    ("ruby", "rubygems/rubygems", "Gemfile.lock"),
    ("ruby", "hotwired/turbo-rails", "Gemfile.lock + js"),
    ("ruby", "mastodon/mastodon", "Gemfile.lock + package.json"),
    ("ruby", "gitlabhq/gitlabhq", "very large polyglot"),
    ("ruby", "chatwoot/chatwoot", "rails + vue"),
    ("ruby", "solidusio/solidus", "monorepo gems"),
    ("ruby", "rubocop/rubocop", "Gemfile.lock"),
    ("ruby", "sidekiq/sidekiq", "Gemfile.lock"),

    # -- PHP -------------------------------------------------------------------
    ("php", "laravel/laravel", "composer.lock, app skeleton"),
    ("php", "symfony/demo", "composer.lock"),
    ("php", "nextcloud/server", "composer + js, large"),
    ("php", "magento/magento2", "composer, enormous"),
    ("php", "WordPress/WordPress", "no composer.lock"),
    ("php", "phpstan/phpstan-src", "composer.lock"),
    ("php", "sebastianbergmann/phpunit", "composer.lock"),
    ("php", "filamentphp/filament", "monorepo packages"),
    ("php", "spatie/laravel-permission", "composer"),
    ("php", "bagisto/bagisto", "laravel app"),

    # -- Python: uv, pdm, conda, and heavy science -----------------------------
    ("python", "astral-sh/uv", "rust + python, uv.lock"),
    ("python", "astral-sh/ruff", "rust + python"),
    ("python", "pdm-project/pdm", "pdm.lock"),
    ("python", "python-poetry/cleo", "poetry.lock"),
    ("python", "conda/conda", "conda, no pep621 lock"),
    ("python", "apache/airflow", "huge, constraints files"),
    ("python", "scikit-learn/scikit-learn", "meson build"),
    ("python", "scipy/scipy", "meson, native deps"),
    ("python", "huggingface/transformers", "large, setup.py"),
    ("python", "langchain-ai/langchain", "monorepo of poetry projects"),
    ("python", "Textualize/textual", "poetry"),
    ("python", "encode/httpx", "pep621"),
    ("python", "pydantic/pydantic", "pep621 + rust core"),
    ("python", "streamlit/streamlit", "mixed js + python"),
    ("python", "home-assistant/core", "requirements, enormous"),
    ("python", "openai/openai-python", "pep621"),

    # -- JavaScript / TypeScript: pnpm, bun, workspaces ------------------------
    ("javascript", "vercel/turborepo", "pnpm workspace + rust"),
    ("javascript", "vitejs/vite", "pnpm workspace"),
    ("javascript", "withastro/astro", "pnpm monorepo"),
    ("javascript", "nrwl/nx", "pnpm monorepo"),
    ("javascript", "vuejs/core", "pnpm"),
    ("javascript", "sveltejs/svelte", "pnpm monorepo"),
    ("javascript", "remix-run/react-router", "pnpm"),
    ("javascript", "elysiajs/elysia", "bun.lock"),
    ("javascript", "honojs/hono", "bun/npm"),
    ("javascript", "trpc/trpc", "pnpm monorepo"),
    ("javascript", "prisma/prisma", "pnpm monorepo + rust"),
    ("javascript", "supabase/supabase", "pnpm monorepo, polyglot"),
    ("javascript", "immich-app/immich", "monorepo, ts + dart"),
    ("javascript", "excalidraw/excalidraw", "yarn workspace"),
    ("javascript", "typeorm/typeorm", "npm"),
    ("javascript", "expressjs/express", "npm, small"),

    # -- Go --------------------------------------------------------------------
    ("go", "kubernetes/kubernetes", "go.sum, enormous"),
    ("go", "grafana/grafana", "go + js monorepo"),
    ("go", "prometheus/prometheus", "go.sum + js"),
    ("go", "hashicorp/vault", "go, large"),
    ("go", "docker/cli", "go"),
    ("go", "traefik/traefik", "go"),
    ("go", "cli/cli", "go"),
    ("go", "minio/minio", "go"),
    ("go", "cockroachdb/cockroach", "go + bazel, huge"),
    ("go", "argoproj/argo-cd", "go + ui"),
    ("go", "ollama/ollama", "go + cpp"),
    ("go", "syncthing/syncthing", "go"),

    # -- Rust ------------------------------------------------------------------
    ("rust", "rust-lang/cargo", "Cargo.lock"),
    ("rust", "tokio-rs/tokio", "workspace"),
    ("rust", "serde-rs/serde", "workspace"),
    ("rust", "clap-rs/clap", "workspace"),
    ("rust", "rust-lang/rust-analyzer", "workspace, large"),
    ("rust", "paritytech/polkadot-sdk", "enormous workspace"),
    ("rust", "vectordotdev/vector", "large workspace"),
    ("rust", "starship/starship", "Cargo.lock"),
    ("rust", "sharkdp/fd", "Cargo.lock"),
    ("rust", "helix-editor/helix", "workspace"),
    ("rust", "zed-industries/zed", "very large workspace"),
    ("rust", "surrealdb/surrealdb", "workspace"),

    # -- Container images ------------------------------------------------------
    ("docker", "docker.io/library/postgres:17", "official image"),
    ("docker", "docker.io/library/node:22-alpine", "alpine, musl"),
    ("docker", "docker.io/library/golang:1.24", "toolchain image"),
    ("docker", "docker.io/library/rust:1-slim", "toolchain image"),
    ("docker", "docker.io/library/nginx:stable", "official image"),
    ("docker", "docker.io/library/mariadb:11", "official image"),
    ("docker", "gcr.io/distroless/static-debian12:latest", "distroless, near-empty"),
    ("docker", "docker.io/library/wordpress:php8.3", "php image"),
    ("docker", "docker.io/library/eclipse-temurin:21-jdk", "jdk image"),
    ("docker", "docker.io/library/ruby:3.3-slim", "ruby image"),

    # -- Deliberately polyglot monorepos, to stress discovery ranking ----------
    ("polyglot", "microsoft/vscode", "ts + native, very large"),
    ("polyglot", "apache/spark", "scala + python + java"),
    ("polyglot", "tensorflow/tensorflow", "cpp + python + bazel"),
    ("polyglot", "pytorch/pytorch", "cpp + python"),
    ("polyglot", "apache/arrow", "many languages in one tree"),
    ("polyglot", "opensearch-project/OpenSearch", "java + others"),
    ("polyglot", "backstage/backstage", "ts monorepo, plugins"),
    ("polyglot", "n8n-io/n8n", "ts monorepo"),
]

if __name__ == "__main__":
    import collections
    print(f"{len(CANDIDATES)} candidates")
    for eco, n in sorted(collections.Counter(c[0] for c in CANDIDATES).items(),
                         key=lambda x: -x[1]):
        print(f"  {n:3d}  {eco}")


# A second pass. The first draft overlapped the existing corpus by 89 -- the
# obvious name in an ecosystem is obvious to whoever picked last time too --
# so these fill the gap with projects the corpus does not already hold.
EXTRA = [
    ("swift", "vapor/fluent", "SwiftPM, ORM"),
    ("swift", "apple/swift-nio-ssl", "SwiftPM, resolved"),
    ("swift", "apple/swift-protobuf", "SwiftPM"),
    ("swift", "swiftlang/swift-package-manager", "SwiftPM itself"),
    ("swift", "hummingbird-project/hummingbird", "SwiftPM server"),
    ("swift", "airbnb/lottie-ios", "SwiftPM + Podfile"),

    ("dotnet", "dotnet/aspire", "monorepo, newer"),
    ("dotnet", "AutoFixture/AutoFixture", "library"),
    ("dotnet", "reactiveui/ReactiveUI", "monorepo"),
    ("dotnet", "dotnet/machinelearning", "monorepo"),
    ("dotnet", "App-vNext/Polly.Contrib.WaitAndRetry", "small library"),
    ("dotnet", "PomeloFoundation/Pomelo.EntityFrameworkCore.MySql", "provider"),
    ("dotnet", "dotnet/wpf", "large monorepo"),
    ("dotnet", "abpframework/abp-samples", "csproj-dense samples"),

    ("haskell", "haskell/aeson", "cabal, json"),
    ("haskell", "snoyberg/conduit", "stack + cabal"),
    ("haskell", "yesodweb/yesod", "stack monorepo"),
    ("haskell", "haskell-servant/servant", "cabal monorepo"),

    ("ocaml", "ocsigen/lwt", "opam"),
    ("ocaml", "janestreet/core", "dune"),
    ("ocaml", "ocaml-batteries-team/batteries-included", "opam"),

    ("clojure", "clojure/tools.deps", "deps.edn"),
    ("clojure", "seancorfield/next-jdbc", "deps.edn"),
    ("clojure", "technomancy/leiningen", "project.clj"),

    ("erlang", "erlang/rebar3", "rebar.lock"),
    ("erlang", "processone/ejabberd", "rebar.lock"),
    ("erlang", "inaka/elvis", "rebar.lock"),

    ("perl", "houseabsolute/DateTime.pm", "cpanfile"),
    ("perl", "plack/Plack", "cpanfile"),
    ("perl", "libwww-perl/libwww-perl", "no lock"),

    ("r", "r-lib/devtools", "DESCRIPTION"),
    ("r", "r-lib/testthat", "DESCRIPTION"),
    ("r", "tidyverse/tidyr", "DESCRIPTION"),

    ("julia", "JuliaPlots/Plots.jl", "Project.toml"),
    ("julia", "JuliaWeb/HTTP.jl", "Project.toml"),
    ("julia", "JuliaGPU/CUDA.jl", "Project.toml"),

    ("lua", "hoelzro/lua-http", "rockspec"),
    ("lua", "lunarmodules/luasocket", "rockspec"),
    ("nim", "nim-lang/nimble", "nimble itself"),
    ("nim", "zedeus/nitter", "nimble app"),
    ("zig", "zigtools/zls", "build.zig.zon"),
    ("zig", "karlseguin/http.zig", "build.zig.zon"),

    ("nix", "NixOS/nix", "the package manager"),
    ("nix", "numtide/devshell", "flake.lock"),

    ("terraform", "hashicorp/terraform-provider-google", "go provider"),
    ("terraform", "hashicorp/terraform-provider-azurerm", "go provider"),
    ("terraform", "Azure/terraform-azurerm-caf-enterprise-scale", "modules"),

    ("cpp", "nlohmann/json_test_data", "data-only repo"),
    ("cpp", "catchorg/Catch2", "cmake, tests"),
    ("cpp", "gabime/spdlog", "cmake"),
    ("cpp", "fmtlib/fmt", "cmake"),
    ("cpp", "abseil/abseil-cpp", "bazel + cmake"),

    ("kotlin", "square/retrofit", "gradle"),
    ("kotlin", "Kotlin/kotlinx.coroutines", "gradle"),
    ("kotlin", "mockk/mockk", "gradle"),
    ("kotlin", "Kotlin/kotlinx.serialization", "gradle"),

    ("java", "apache/hadoop", "maven, enormous"),
    ("java", "apache/zookeeper", "maven"),
    ("java", "netty/netty-incubator-codec-http3", "maven small"),
    ("java", "junit-team/junit-framework", "gradle, newer JDK"),
    ("java", "mockito/mockito", "gradle"),
    ("java", "google/gson", "maven"),
    ("java", "apache/tomcat", "ant + maven"),
    ("java", "jenkinsci/jenkins-test-harness", "maven"),

    ("scala", "typelevel/fs2", "sbt"),
    ("scala", "http4s/http4s", "sbt"),
    ("scala", "softwaremill/tapir", "sbt monorepo"),

    ("elixir", "elixir-lang/elixir", "mix, the language"),
    ("elixir", "beam-telemetry/telemetry", "rebar/mix"),
    ("elixir", "plausible/analytics", "mix.lock + js"),

    ("dart", "flutter/flutter", "very large"),
    ("dart", "google/json_serializable.dart", "melos monorepo"),
    ("dart", "dart-lang/shelf", "pubspec"),
    ("dart", "cfug/dio", "pubspec"),

    ("ruby", "rails/rails", "monorepo of gems"),
    ("ruby", "jekyll/jekyll", "Gemfile.lock"),
    ("ruby", "fastlane/fastlane", "Gemfile.lock"),
    ("ruby", "discourse/discourse", "rails + js, large"),
    ("ruby", "puma/puma", "Gemfile.lock + C"),

    ("php", "composer/composer", "composer.lock itself"),
    ("php", "yiisoft/yii2", "composer"),
    ("php", "thephpleague/flysystem", "composer monorepo"),
    ("php", "doctrine/orm", "composer.lock"),
    ("php", "pestphp/pest", "composer.lock"),

    ("python", "pypa/pip", "no lockfile"),
    ("python", "psf/black", "pep621"),
    ("python", "fastapi/sqlmodel", "poetry"),
    ("python", "pola-rs/polars", "rust + python"),
    ("python", "vllm-project/vllm", "large, native"),
    ("python", "mlflow/mlflow", "mixed js + python"),
    ("python", "dbt-labs/dbt-core", "monorepo"),

    ("javascript", "facebook/react", "yarn workspace monorepo"),
    ("javascript", "angular/angular", "bazel + pnpm"),
    ("javascript", "nodejs/node", "cpp + js, no lockfile"),
    ("javascript", "storybookjs/storybook", "pnpm monorepo"),
    ("javascript", "TanStack/query", "pnpm monorepo"),
    ("javascript", "eslint/eslint", "npm"),
    ("javascript", "webpack/webpack", "yarn"),
    ("javascript", "denoland/fresh", "deno, no npm lock"),

    ("go", "gohugoio/hugo", "go.sum"),
    ("go", "etcd-io/etcd", "go, multi-module"),
    ("go", "goreleaser/goreleaser", "go"),
    ("go", "open-telemetry/opentelemetry-collector", "go, multi-module"),
    ("go", "influxdata/telegraf", "go, many plugins"),
    ("go", "caddyserver/caddy", "go"),

    ("rust", "rust-lang/rust", "the compiler, enormous"),
    ("rust", "denoland/rusty_v8", "Cargo.lock + native"),
    ("rust", "meilisearch/meilisearch", "workspace"),
    ("rust", "rustdesk/rustdesk", "workspace + flutter"),
    ("rust", "sharkdp/bat", "Cargo.lock"),
    ("rust", "BurntSushi/regex", "workspace"),

    ("polyglot", "apache/beam", "java + python + go"),
    ("polyglot", "elastic/kibana", "ts monorepo, huge"),
    ("polyglot", "grpc/grpc-java", "gradle"),
    ("polyglot", "apache/druid", "java + js"),
    ("polyglot", "temporalio/temporal", "go + java"),
    ("polyglot", "hasura/graphql-engine", "haskell + ts"),
]

