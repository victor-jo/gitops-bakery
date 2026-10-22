// Reads GitLab's root password and mints a root API token through the toolbox's Rails runner
import { GITLAB_HOST_URL } from "../lib/config.js";
import { GitLab } from "../lib/gitlab.js";
import { kubectl, secretValue } from "../lib/kube.js";
import { randomSecret, updateSecrets } from "../lib/secrets.js";
import type { Step } from "./types.js";

export function patRubyScript(token: string): string {
  return [
    "u = User.find_by_username('root')",
    "u.personal_access_tokens.where(name: 'gitops-bakery').each(&:revoke!)",
    "t = u.personal_access_tokens.build(name: 'gitops-bakery', scopes: ['api'], expires_at: 364.days.from_now)",
    `t.set_token('${token}')`,
    "t.save!",
  ].join("; ");
}

// The script travels on stdin so the token never shows up in `ps` or in an error's command line
export async function mintRootToken(token: string, exec: (args: string[], input?: string) => Promise<string>): Promise<void> {
  await exec(["-n", "gitlab", "exec", "-i", "deploy/gitlab-toolbox", "-c", "toolbox", "--", "gitlab-rails", "runner", "-"], patRubyScript(token));
}

export const gitlabAuthStep: Step = {
  id: "gitlab-auth",
  title: "GitLab root token",
  async run(ctx) {
    const rootPassword = await secretValue("gitlab", "gitlab-gitlab-initial-root-password", "password");
    const token = `glpat-${randomSecret(20)}`;
    await mintRootToken(token, (args, input) => kubectl(args, input, [token]));
    const me = await new GitLab(GITLAB_HOST_URL, token).currentUser();
    if (me.username !== "root") throw new Error(`New token belongs to ${me.username}, expected root`);
    ctx.secrets = updateSecrets({ gitlabRootPassword: rootPassword, gitlabPat: token });
  },
};
