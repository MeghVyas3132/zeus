import errorEnvelopeSchema from "../schemas/error-envelope.schema.json" with { type: "json" };
import runAgentRequestSchema from "../schemas/run-agent-request.schema.json" with { type: "json" };
import runAgentResponseSchema from "../schemas/run-agent-response.schema.json" with { type: "json" };
import runAgentDuplicateResponseSchema from "../schemas/run-agent-duplicate-response.schema.json" with { type: "json" };
import resultsSchema from "../schemas/results.schema.json" with { type: "json" };
import thoughtEventSchema from "../schemas/socket-thought-event.schema.json" with { type: "json" };
import fixAppliedEventSchema from "../schemas/socket-fix-applied.schema.json" with { type: "json" };
import ciUpdateEventSchema from "../schemas/socket-ci-update.schema.json" with { type: "json" };
import telemetryTickEventSchema from "../schemas/socket-telemetry-tick.schema.json" with { type: "json" };
import runCompleteEventSchema from "../schemas/socket-run-complete.schema.json" with { type: "json" };

export * from "./types.js";

export const schemas = {
  errorEnvelopeSchema,
  runAgentRequestSchema,
  runAgentResponseSchema,
  runAgentDuplicateResponseSchema,
  resultsSchema,
  thoughtEventSchema,
  fixAppliedEventSchema,
  ciUpdateEventSchema,
  telemetryTickEventSchema,
  runCompleteEventSchema
};
