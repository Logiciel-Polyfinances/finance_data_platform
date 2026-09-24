/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Injected at build time (Dockerfile ARG) so the local stack's UI is
  // pre-authenticated. Empty/undefined in prod builds.
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
