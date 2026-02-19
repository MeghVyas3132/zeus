import type { ErrorEnvelope } from "@rift/contracts";

export function buildErrorEnvelope(
  code: string,
  message: string,
  details?: Record<string, unknown>
): ErrorEnvelope {
  return {
    error: {
      code,
      message,
      ...(details ? { details } : {})
    }
  };
}
