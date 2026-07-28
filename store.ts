// Global state store with localStorage persistence

const APP_STORAGE_VERSION = 'no-fake-roles-channels-v3';

// Version check & cleanup
if (localStorage.getItem('pb_storage_version') !== APP_STORAGE_VERSION) {
  localStorage.removeItem('pb_access_portals');
  localStorage.removeItem('pb_permissions');
  localStorage.removeItem('pb_logs_setup');
  localStorage.setItem('pb_storage_version', APP_STORAGE_VERSION);
}

function safeParse<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

export interface LogsSetup {
  category: string;
  mode: string;
  roles: string[];
  channels: Record<string, boolean>;
}

export interface PortalLevel {
  roles: string[];
  users: string[];
  sections: string[];
}

export interface PortalConfig {
  owner: PortalLevel;
  admin: PortalLevel;
  moderator: PortalLevel;
  member: PortalLevel;
}

export interface PermissionEntry {
  mode: string;
  roles: Record<string, string>;
  denyRoles: Record<string, string>;
  syncVisibility: boolean;
}

// State
export let config: Record<string, Record<string, string>> = safeParse('pb_console_config', {});
export let pending: Record<string, Record<string, string>> = safeParse('pb_console_pending', {});
export let permState: Record<string, PermissionEntry> = safeParse('pb_permissions', {});

export let logsSetup: LogsSetup = safeParse('pb_logs_setup', {
  category: '📁 Logs',
  mode: 'auto',
  roles: [],
  channels: {
    mod: true,
    message: true,
    member: true,
    voice: true,
    ticket: true,
    security: true,
    bot: true,
  },
});

export let portalConfig: PortalConfig = safeParse('pb_access_portals', {
  owner: { roles: [], users: [], sections: ['All dashboard', 'API', 'Permissions', 'Logs Setup', 'Apply actions'] },
  admin: { roles: [], users: [], sections: ['Modules', 'Permissions', 'Logs Setup', 'Tickets', 'Logs'] },
  moderator: { roles: [], users: [], sections: ['Moderation', 'Tickets', 'Member logs', 'Warnings'] },
  member: { roles: [], users: [], sections: ['My profile', 'Rank', 'Open ticket', 'Server rules', 'Role selection'] },
});

export function save() {
  localStorage.setItem('pb_console_config', JSON.stringify(config));
  localStorage.setItem('pb_console_pending', JSON.stringify(pending));
  localStorage.setItem('pb_permissions', JSON.stringify(permState));
  localStorage.setItem('pb_logs_setup', JSON.stringify(logsSetup));
  localStorage.setItem('pb_access_portals', JSON.stringify(portalConfig));
}

export function setConfig(id: string, data: Record<string, string>) {
  config[id] = data;
  save();
}

export function setPending(id: string, field: string, value: string) {
  if (!pending[id]) pending[id] = {};
  pending[id][field] = value;
  save();
}

export function clearPending(id: string) {
  delete pending[id];
  save();
}

export function resetModule(id: string) {
  delete config[id];
  delete pending[id];
  save();
}

export function saveModuleDraft(id: string) {
  config[id] = { ...(config[id] || {}), ...(pending[id] || {}) };
  delete pending[id];
  save();
}

export function getDefaultPerm(command: string): PermissionEntry {
  if (!permState[command]) {
    permState[command] = { mode: 'everyone', roles: {}, denyRoles: {}, syncVisibility: false };
  }
  return permState[command];
}

export function readinessScore(id: string): number {
  const c = config[id] || {};
  const checks = ['primaryChannel', 'logChannel', 'staffRole', 'memberRole', 'enabled'];
  const done = checks.filter(k => c[k]).length;
  return Math.round((done / checks.length) * 100);
}

export function defaultFieldValue(f: string): string {
  const map: Record<string, string> = {
    mode: 'manual', preset: 'enterprise', enabled: 'false', dryRun: 'true',
    autoCreateMissing: 'ask', embedColor: '#6d5dfc', cooldown: '60s',
    limit: '5/hour', action: 'warn', duration: '10m',
    escalation: 'warn>mute>kick>ban', scenario: 'dry-run',
    expectedResult: 'no server changes', retryPolicy: '3 retries',
    auditLevel: 'full', debug: 'false',
  };
  return map[f] || '';
}
