// Minimal {{var}} renderer that refuses to leave a placeholder unfilled
export function render(text: string, vars: Record<string, string | number>): string {
  return text.replace(/\{\{(\w+)\}\}/g, (_, key: string) => {
    if (!(key in vars)) throw new Error(`Unknown template variable: ${key}`);
    return String(vars[key]);
  });
}
