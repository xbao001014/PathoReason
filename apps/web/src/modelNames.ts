// Official version labels verified 2026-10-30:
// https://api-docs.deepseek.com/quick_start/pricing/
// These are presentation labels; API aliases and stored turn identifiers stay intact.
const officialModelNames: Readonly<Record<string, string>> = {
  'deepseek-v4-pro': 'DeepSeek V4 Pro',
  'deepseek-v4.1-flash': 'DeepSeek V4.1 Flash（百炼）',
  'deepseek-flash': 'DeepSeek V4.1 Flash',
};

export function modelDisplayName(model: string | null | undefined): string {
  return model ? officialModelNames[model] ?? model : '';
}
