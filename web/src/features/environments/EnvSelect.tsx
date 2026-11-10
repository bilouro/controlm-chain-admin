import { useRepo } from "@/lib/api/queries";
import { SelectInput } from "@/components/ui";
import { useEnv } from "./env-context";

/**
 * The environment the chain pages show: its folders and jobs, with its values. Not shown where
 * every environment has its own branch: there the branch button changes what is seen.
 */
export function EnvSelect() {
  const repo = useRepo();
  const { env, setEnv, selectable } = useEnv();
  const environments = repo.data?.environments ?? [];
  if (!selectable || environments.length === 0) return null;
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      <span>View</span>
      <SelectInput
        aria-label="View as environment"
        value={env ?? ""}
        onChange={(event) => setEnv(event.target.value || null)}
      >
        <option value="">neutral base</option>
        {environments.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </SelectInput>
    </label>
  );
}
