import { Badge } from "@/components/ui";
import { useEnv } from "./env-context";

/** Says on a page that the values shown are one environment's, not the neutral base. */
export function EnvBadge() {
  const { env } = useEnv();
  if (!env) return null;
  return (
    <Badge tone="warning" title="Values of this environment: its exceptions and constants">
      {env} values
    </Badge>
  );
}
