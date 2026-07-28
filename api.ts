// API client - matches assets/api.js structure

function getDefaultApiBase(): string {
  const saved = localStorage.getItem('probotum_api_base');
  const host = window.location.hostname;

  const isLocalhost = host === 'localhost' || host === '127.0.0.1' || host === '::1';

  // Local dashboard is usually served by `python -m http.server 8080`,
  // while FastAPI runs on port 3000. If an old wrong value `/api` was saved,
  // ignore it on localhost and use the FastAPI port.
  if (isLocalhost && (!saved || saved === '/api')) {
    return 'http://localhost:3000/api';
  }

  if (saved) return saved;

  // Production/default: same-origin API.
  return '/api';
}

function getDefaultDashboardToken(): string {
  const saved = localStorage.getItem('probotum_dashboard_token');
  if (saved) return saved;
  const host = window.location.hostname;
  const isLocalhost = host === 'localhost' || host === '127.0.0.1' || host === '::1';
  // Matches .env.example default for local development.
  if (isLocalhost) return 'change-me-secret';
  return '';
}

// API state
let baseUrl = getDefaultApiBase();
let token = getDefaultDashboardToken();
let connected = false;
let lastError: string | null = null;
let data: ApiData | null = null;

export interface ApiData {
  overview: any;
  modules: any;
  logs: any;
}

// Getters
export function getBaseUrl(): string { return baseUrl; }
export function getToken(): string { return token; }
export function isConnected(): boolean { return connected; }
export function getLastError(): string | null { return lastError; }
export function getData(): ApiData | null { return data; }

// Setters
export function setBaseUrl(url: string): void {
  baseUrl = url || '/api';
  localStorage.setItem('probotum_api_base', baseUrl);
}

export function setToken(t: string): void {
  token = t;
  if (t) {
    localStorage.setItem('probotum_dashboard_token', t);
  } else {
    localStorage.removeItem('probotum_dashboard_token');
  }
}

// API request
export async function request(path: string, options: RequestInit = {}): Promise<any> {
  const url = baseUrl.replace(/\/$/, '') + path;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers as Record<string, string> || {}),
    },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`);
  return res.json();
}

// Health check
export async function health(): Promise<any> {
  try {
    const result = await request('/health');
    connected = true;
    lastError = null;
    return result;
  } catch (e: any) {
    connected = false;
    lastError = e.message;
    return null;
  }
}

// Load guild dashboard data
export async function loadGuildDashboard(guildId: string = 'current'): Promise<ApiData | null> {
  try {
    const [overview, modules, logs] = await Promise.all([
      request(`/guilds/${guildId}/overview`),
      request(`/guilds/${guildId}/modules`),
      request(`/guilds/${guildId}/logs?limit=20`),
    ]);
    connected = true;
    lastError = null;
    data = { overview, modules, logs };
    return data;
  } catch (e: any) {
    connected = false;
    lastError = e.message;
    data = null;
    return null;
  }
}

// Save module config
export async function saveModuleConfig(guildId: string, moduleId: string, config: any): Promise<any> {
  return request(`/guilds/${guildId}/modules/${moduleId}`, {
    method: 'PUT',
    body: JSON.stringify(config),
  });
}

// Access Portals
export async function getAccessPortals(guildId: string = 'current'): Promise<any> {
  return request(`/guilds/${guildId}/access-portals`);
}

export async function saveAccessPortals(guildId: string = 'current', config: any): Promise<any> {
  return request(`/guilds/${guildId}/access-portals`, {
    method: 'PUT',
    body: JSON.stringify(config),
  });
}

// Permissions
export async function getPermissions(guildId: string = 'current', command?: string): Promise<any> {
  const query = command ? `?command=${encodeURIComponent(command)}` : '';
  return request(`/guilds/${guildId}/permissions${query}`);
}

export async function savePermissions(guildId: string = 'current', rules: any[]): Promise<any> {
  return request(`/guilds/${guildId}/permissions`, {
    method: 'PUT',
    body: JSON.stringify({ rules }),
  });
}

// Actions
export async function applyAction(guildId: string = 'current', payload: any): Promise<any> {
  return request(`/guilds/${guildId}/actions/apply`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function createLogChannels(guildId: string = 'current', config: any): Promise<any> {
  return request(`/guilds/${guildId}/actions/create-log-channels`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

// Auth
export async function getAuthMe(): Promise<any> {
  return request('/auth/me');
}

// Helper to format Discord channel from API response
export function formatDiscordChannel(c: any): string {
  if (typeof c !== 'object') return String(c);
  const name = c.name || c.id || 'unknown-channel';
  const type = Number(c.type);
  if (type === 0) return `#${name}`;          // text
  if (type === 2) return `🔊 ${name}`;        // voice
  if (type === 4) return `📁 ${name}`;        // category
  if (type === 5) return `📣 ${name}`;        // announcement
  if (type === 13) return `🎙️ ${name}`;      // stage
  if (type === 15) return `🧵 ${name}`;       // forum
  if (type === 16) return `📌 ${name}`;       // media
  return name;
}
