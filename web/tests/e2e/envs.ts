import os from "node:os";
import path from "node:path";

/** The second server of the tests: a repository with one branch per environment. */
export const ENVS_PORT = process.env.CTMCHAIN_E2E_ENVS_PORT ?? "8798";
export const ENVS_URL = `http://127.0.0.1:${ENVS_PORT}`;
/** Where that server leaves a newer export of uat, for the refresh to be tried with. */
export const EXPORT_FILE = path.join(os.tmpdir(), `ctmchain-e2e-${ENVS_PORT}-uat_export.xml`);
