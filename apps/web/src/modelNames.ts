// Official version labels verified 2026-10-30:
// https://api-docs.deepseek.com/quick_start/pricing/
// These are presentation labels; API aliases and stored turn identifiers stay intact.
const officialModelNames: Readonly<Record<string, string>> = {
  'deepseek-v4-pro': 'DeepSeek-V4-Pro-0813',
  'deepseek-flash': 'DeepSeek-V4.1-Flash-1017',
};

export function modelDisplayName(model: string | null | undefined): string {
  return model ? officialModelNames[model] ?? model : '';
}
