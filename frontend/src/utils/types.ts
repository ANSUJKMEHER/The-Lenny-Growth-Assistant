export interface Citation {
  source_id?: string;
  title: string;
  episode_id?: string;
  guest?: string;
  timestamp?: string;
  url?: string;
  excerpt?: string;
}

export interface Artifact {
  id: string;
  conversation_id?: string;
  title: string;
  kind: "markdown" | "html";
  content: string;
  created_at?: string;
}

export interface Message {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[] | null;
  created_at?: string;
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at?: string;
  messages?: Message[];
  artifacts?: Artifact[];
}

export interface ProviderInfo {
  name: string;
  model: string;
  available: boolean;
  reason?: string | null;
}

export interface AppConfig {
  provider: string;
  model: string;
  providers: ProviderInfo[];
  fallback_enabled: boolean;
}
