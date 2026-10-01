/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend API origin for hosted builds, e.g. https://insightboard-api.onrender.com */
  readonly VITE_API_URL?: string;
}
