// App name rules: a DNS label that cannot clash with the lab's own Argo CD Applications
const NAME_RE = /^[a-z]([a-z0-9-]{0,28}[a-z0-9])?$/;
const RESERVED = new Set(["monitoring", "platform-root", "service-root"]);

export function validateAppName(name: string): void {
  if (!NAME_RE.test(name))
    throw new Error(`Invalid app name "${name}": use lowercase letters, digits and "-" (max 30, start with a letter)`);
  if (RESERVED.has(name)) throw new Error(`App name "${name}" is reserved by the lab; pick another`);
}
