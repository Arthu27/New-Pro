// Dashboard static data - matches assets/data.js structure

export type NavItem = [string, string, string, string]; // [group, id, label, icon]
export type ModuleItem = [string, string, string, string]; // [id, name, description, type]

export const nav: NavItem[] = [
  ['main', 'memberPortal', 'Member Portal', '◌'],
  ['main', 'start', 'Start Here', '●'],
  ['main', 'overview', 'Overview', '⌂'],
  ['main', 'setupWizard', 'Setup Wizard', '◌'],
  ['main', 'readiness', 'Readiness', '◍'],
  ['main', 'modules', 'Modules', '◈'],
  ['main', 'activity', 'Activity', '↯'],

  ['setup', 'automod', 'AutoMod', '◆'],
  ['setup', 'antiraid', 'Anti-Raid', '◆'],
  ['setup', 'welcome', 'Welcome', '◆'],
  ['setup', 'autorole', 'AutoRole', '◆'],
  ['setup', 'tickets', 'Tickets', '◆'],
  ['setup', 'levels', 'Levels', '◆'],
  ['setup', 'reactionRoles', 'Reaction Roles', '◆'],
  ['setup', 'economy', 'Economy', '◆'],
  ['setup', 'giveaways', 'Giveaways', '◆'],
  ['setup', 'music', 'Music', '◆'],
  ['setup', 'ai', 'AI Assistant', '◆'],

  ['builders', 'automodRules', 'AutoMod Rules', '▣'],
  ['builders', 'ticketPanel', 'Ticket Panel', '▣'],
  ['builders', 'welcomeFlow', 'Welcome Flow', '▣'],

  ['system', 'accessPortals', 'Access Portals', '◌'],
  ['system', 'permissions', 'Permissions', '◉'],
  ['system', 'logsSetup', 'Logs Setup', '◫'],
  ['system', 'channels', 'Channels', '▦'],
  ['system', 'roles', 'Roles', '▦'],
  ['system', 'logs', 'Logs', '▦'],
  ['system', 'settings', 'Settings', '⚙'],
];

export const modules: ModuleItem[] = [
  ['automod', 'AutoMod', 'Moderation filters, spam rules, escalation policies', 'security'],
  ['antiraid', 'Anti-Raid', 'Raid detection, lockdown, quarantine, mass-action protection', 'security'],
  ['welcome', 'Welcome', 'Join, leave, DM, image card and onboarding flow', 'community'],
  ['autorole', 'AutoRole', 'Role assignment after join, rules, captcha or delay', 'community'],
  ['tickets', 'Tickets', 'Panels, forms, SLA, transcripts and staff routing', 'support'],
  ['levels', 'Levels', 'Message XP, voice XP, rewards, seasons and rank cards', 'community'],
  ['reactionRoles', 'Reaction Roles', 'Buttons, select menus, role groups and limits', 'community'],
  ['economy', 'Economy', 'Currency, market, inventory, trade and anti-abuse', 'fun'],
  ['giveaways', 'Giveaways', 'Requirements, bonus entries, reroll and history', 'fun'],
  ['music', 'Music', 'Queue, DJ role, playlists, limits and autoplay', 'fun'],
  ['ai', 'AI Assistant', 'Ticket summaries, auto reply, toxicity and knowledge base', 'premium'],
];

export const settingsSchema: Record<string, string[]> = {
  setup: ['mode', 'preset', 'enabled', 'dryRun', 'autoCreateMissing'],
  channels: ['primaryChannel', 'logChannel', 'errorChannel', 'excludedChannels', 'fallbackChannel'],
  roles: ['adminRole', 'staffRole', 'memberRole', 'bypassRoles', 'quarantineRole'],
  messages: ['embedTitle', 'embedDescription', 'embedColor', 'buttons', 'variables'],
  rules: ['cooldown', 'limit', 'action', 'duration', 'escalation'],
  test: ['testUser', 'scenario', 'payload', 'expectedResult'],
  advanced: ['webhook', 'retryPolicy', 'auditLevel', 'jsonOverrides', 'debug'],
};

export const commands: string[] = [
  '/settings', '/config', '/ban', '/mute', '/kick', '/ticket',
  '/autorole', '/automod', '/giveaway', '/economy', '/rank', '/music',
];

export const endpoints: string[] = [
  'GET /health',
  'GET /guilds/:id/overview',
  'GET /guilds/:id/channels',
  'GET /guilds/:id/roles',
  'GET /guilds/:id/modules',
  'PUT /guilds/:id/modules/:moduleId',
  'POST /guilds/:id/actions/apply',
];

// These are filled from the Python API / Discord API
export let channels: string[] = [];
export let roles: string[] = [];
export let users: string[] = [];

export function setChannels(c: string[]) { channels = c; }
export function setRoles(r: string[]) { roles = r; }
export function setUsers(u: string[]) { users = u; }

// Helper to get module by id
export function getModule(id: string): ModuleItem | undefined {
  return modules.find(m => m[0] === id);
}

// Helper to get nav item by id
export function getNavItem(id: string): NavItem | undefined {
  return nav.find(n => n[1] === id);
}
